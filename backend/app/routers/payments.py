"""Оплата: вебхук ЮKassa, страница-заглушка fake-оплаты, возврат покупателя после оплаты."""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.integrations.payments import FakeProvider
from app.models import Payment, PaymentStatus
from app.schemas.trade import FakeActionIn, FakeCheckout, PaymentResult
from app.services import payments as svc

router = APIRouter(prefix="/api/payments", tags=["оплата"])
hook_log = logging.getLogger("codemarket.webhooks")


@router.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request, db: DB):
    """Вебхук ЮKassa. Тело уведомления не считается доказательством оплаты: статус перепроверяется запросом."""
    try:
        data = json.loads(await request.body())
        external_id = data["object"]["id"]
    except (ValueError, KeyError, TypeError):
        hook_log.warning("Вебхук ЮKassa: неверное тело")
        return PlainTextResponse("bad request", status_code=400)
    hook_log.info("Вебхук ЮKassa %s %s", data.get("event"), external_id)
    svc.handle_notification(db, external_id)
    db.commit()
    return "ok"


def _owner_id(payment: Payment) -> int:
    return payment.order.buyer_id if payment.order_id else payment.purchase.buyer_id


def _target_url(payment: Payment) -> str:
    return f"/orders/{payment.order_id}/" if payment.order_id else f"/me/purchases/{payment.purchase_id}/"


def _own_payment(db, user, **cond) -> Payment:
    stmt = select(Payment)
    for k, v in cond.items():
        stmt = stmt.where(getattr(Payment, k) == v)
    payment = db.scalar(stmt)
    if payment is None or _owner_id(payment) != user.id:
        raise NotFound("Платёж не найден")
    return payment


@router.get("/return/{pk}", response_model=PaymentResult)
def payment_return(pk: int, db: DB, user: CurrentUser):
    """Покупатель вернулся со страницы оплаты: проверить статус и показать результат."""
    payment = _own_payment(db, user, id=pk)
    svc.refresh_payment(db, payment)
    db.commit()
    if payment.status == PaymentStatus.SUCCEEDED:
        msg, level = "Оплата прошла.", "success"
    elif payment.status == PaymentStatus.CANCELED:
        msg, level = "Оплата отклонена.", "danger"
    else:
        msg, level = "Платёж ещё обрабатывается, обновите страницу через минуту.", "info"
    return PaymentResult(status=payment.status, message=msg, level=level, url=_target_url(payment))


def _fake(db, user, external_id):
    if settings.payment_provider != "fake":
        raise NotFound()
    data = FakeProvider().get(external_id)
    payment = _own_payment(db, user, external_id=external_id)
    if data is None:
        raise NotFound("Платёж не найден")
    return data, payment


@router.get("/fake/{external_id}", response_model=FakeCheckout)
def fake_checkout(external_id: str, db: DB, user: CurrentUser):
    """Страница-заглушка платёжной системы (только PAYMENT_PROVIDER=fake)."""
    data, payment = _fake(db, user, external_id)
    return FakeCheckout(
        external_id=external_id,
        amount=payment.amount,
        description=data["description"],
        status=data["status"],
        payment_id=payment.id,
    )


@router.post("/fake/{external_id}", response_model=PaymentResult)
def fake_action(external_id: str, data: FakeActionIn, db: DB, user: CurrentUser):
    """«Оплатить» или «Отклонить» на заглушке; дальше тот же обработчик, что у вебхука."""
    _, payment = _fake(db, user, external_id)
    FakeProvider().set_status(external_id, "succeeded" if data.action == "pay" else "canceled")
    svc.handle_notification(db, external_id)
    db.commit()
    return payment_return(payment.id, db, user)

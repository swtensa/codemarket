"""Оплата: создание платежа, обработка уведомления провайдера, отметка возврата.

Статус оплаты меняется только после проверки запросом к провайдеру (get_status).
Повторное уведомление идемпотентно: уже оплаченный платёж повторно не обрабатывается.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ServiceError
from app.integrations.payments import PaymentError, get_provider
from app.models import CustomOrder, Payment, PaymentStatus
from app.services.notifications import notify_admins

hook_log = logging.getLogger("codemarket.webhooks")
admin_log = logging.getLogger("codemarket.admin")
PS = PaymentStatus


def create_payment(db: Session, *, amount, description, purchase=None, order=None) -> Payment:
    """Создать платёж у провайдера с ключом идемпотентности; вернуть Payment (с confirmation_url)."""
    if purchase is None and order is None:
        raise ValueError("Нужна покупка или заказ")
    payment = Payment(
        purchase_id=purchase.id if purchase else None,
        order_id=order.id if order else None,
        amount=Decimal(amount),
        idempotence_key=uuid.uuid4().hex,
    )
    db.add(payment)
    db.flush()
    return_url = f"{settings.site_url.rstrip('/')}/payments/return/{payment.id}/"
    try:
        created = get_provider().create_payment(
            amount=payment.amount,
            description=description,
            idempotence_key=payment.idempotence_key,
            return_url=return_url,
            metadata={"payment_id": payment.id},
        )
    except PaymentError as e:
        payment.status = PS.CANCELED
        db.flush()
        raise ServiceError(str(e))
    payment.external_id = created.external_id
    payment.confirmation_url = created.confirmation_url
    db.flush()
    return payment


def pending_payment_for(db: Session, *, purchase=None, order=None) -> Payment | None:
    """Неоплаченный платёж покупки или заказа (чтобы не создавать второй)."""
    stmt = select(Payment).where(Payment.status == PS.PENDING, Payment.external_id != "")
    stmt = stmt.where(Payment.purchase_id == purchase.id) if purchase else stmt.where(Payment.order_id == order.id)
    return db.scalar(stmt.order_by(Payment.id).limit(1))


def handle_notification(db: Session, external_id: str) -> Payment | None:
    """Обработать уведомление провайдера (вебхук или страница-заглушка). Статус перепроверяется у провайдера."""
    hook_log.info("Уведомление об оплате %s", external_id)
    try:
        status = get_provider().get_status(external_id)
    except PaymentError as e:
        hook_log.warning("Проверка платежа %s не удалась: %s", external_id, e)
        return None
    payment = db.scalar(select(Payment).where(Payment.external_id == external_id).with_for_update())
    if payment is None:
        hook_log.warning("Платёж %s не найден", external_id)
        return None
    if payment.status == PS.CANCELED and status == "succeeded":
        # покупатель оплатил после отмены (таймаут, отмена заказа): деньги пришли, товар не выдаём
        payment.status = PS.SUCCEEDED
        db.flush()
        _alert_admins(
            db,
            f"Платёж №{payment.id} ({external_id}) на {payment.amount} ₽ оплачен после отмены покупки или заказа: "
            "верните деньги покупателю в кабинете ЮKassa.",
        )
        return payment
    if payment.status != PS.PENDING:
        hook_log.info("Платёж %s уже обработан (%s)", external_id, payment.status)
        return payment
    if status == "succeeded":
        payment.status = PS.SUCCEEDED
        db.flush()
        _dispatch_success(db, payment)
        hook_log.info("Платёж %s оплачен: %s ₽", external_id, payment.amount)
    elif status == "canceled":
        payment.status = PS.CANCELED
        db.flush()
        _dispatch_cancel(db, payment)
        hook_log.info("Платёж %s отменён", external_id)
    return payment


def _alert_admins(db: Session, text: str) -> None:
    hook_log.error(text)
    notify_admins(db, text, "/moderation/")


def _dispatch_success(db: Session, payment: Payment) -> None:
    if payment.order_id:
        from app.services.orders import on_payment_succeeded

        on_payment_succeeded(db, payment.order, payment)
    else:
        from app.services.purchases import on_payment_succeeded

        on_payment_succeeded(db, payment.purchase)


def _dispatch_cancel(db: Session, payment: Payment) -> None:
    if payment.purchase_id and not payment.order_id:
        from app.services.purchases import on_payment_canceled

        on_payment_canceled(db, payment.purchase)


def refresh_payment(db: Session, payment: Payment) -> Payment:
    """Проверить статус платежа у провайдера (страница возврата после оплаты)."""
    if payment.status == PS.PENDING and payment.external_id:
        handle_notification(db, payment.external_id)
        db.refresh(payment)
    return payment


def cancel_pending(db: Session, payment: Payment) -> None:
    """Отменить неоплаченный платёж у нас (по таймауту или отмене заказа)."""
    if payment.status == PS.PENDING:
        payment.status = PS.CANCELED
        db.flush()


def mark_refund(db: Session, *, amount, purchase=None, order=None, admin=None) -> Payment | None:
    """Отметить возврат по платежу. Сам возврат администратор проводит вручную в кабинете ЮKassa."""
    ok = [PS.SUCCEEDED, PS.PARTIALLY_REFUNDED]
    stmt = select(Payment).where(Payment.status.in_(ok)).order_by(Payment.id)
    if order is not None:
        payment = db.scalar(stmt.where(Payment.order_id == order.id))
    else:
        payment = db.scalar(stmt.where(Payment.purchase_id == purchase.id, Payment.order_id.is_(None)))
        if payment is None:
            # покупка оплачена в составе заказа «Купить с доработкой»: платёж заказа больше цены доработки
            payment = db.scalar(
                stmt.join(CustomOrder, CustomOrder.id == Payment.order_id).where(
                    CustomOrder.purchase_id == purchase.id, Payment.amount > CustomOrder.price
                )
            )
    if payment is None:
        return None
    amount = Decimal(amount)
    payment.refund_amount = min(payment.amount, payment.refund_amount + amount)
    payment.status = PS.REFUNDED if payment.refund_amount >= payment.amount else PS.PARTIALLY_REFUNDED
    db.flush()
    admin_log.info("refund marked payment=%s amount=%s admin=%s", payment.id, amount, getattr(admin, "username", None))
    notify_admins(
        db,
        f"Нужно вернуть {amount} ₽ по платежу №{payment.id} ({payment.external_id}) в кабинете ЮKassa.",
        "/moderation/disputes/",
    )
    return payment

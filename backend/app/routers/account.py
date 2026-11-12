"""Споры (открытие), отзывы, уведомления, баланс и вывод денег, статистика продавца."""

from fastapi import APIRouter
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser, SellerUser
from app.core.errors import NotFound, ServiceError
from app.models import CustomOrder, Notification, OpKind, OpStatus, Purchase, ReasonType
from app.schemas.common import Ok, Page, Redirect
from app.schemas.convert import product_ref
from app.schemas.trade import (
    BalanceOut,
    DisputeIn,
    NotificationOut,
    OperationOut,
    PayoutIn,
    ReviewIn,
    SellerStats,
    StatsProductRow,
    TargetInfo,
    UnreadOut,
)
from app.services import balance as balance_services
from app.services import catalog as catalog_services
from app.services import disputes as dispute_services
from app.services import notifications as notification_services
from app.services import purchases as purchase_services
from app.services import reports as report_services
from app.services import reviews as review_services

router = APIRouter(prefix="/api", tags=["кабинет"])


def _target(db, user, purchase_id: int | None, order_id: int | None):
    """Своя покупка (?purchase=) или свой заказ (?order=); чужие — 404."""
    if purchase_id:
        purchase = db.get(Purchase, purchase_id)
        if purchase is None or purchase.buyer_id != user.id:
            raise NotFound("Покупка не найдена")
        return purchase, None, purchase.product, f"/me/purchases/{purchase.id}/"
    order = db.get(CustomOrder, order_id or 0)
    if order is None or order.buyer_id != user.id:
        raise NotFound("Заказ не найден")
    return None, order, order.product, f"/orders/{order.id}/"


# ---------------------------------------------------------------- споры


@router.get("/disputes/new", response_model=TargetInfo)
def dispute_form(db: DB, user: CurrentUser, purchase: int | None = None, order: int | None = None):
    p, o, product, back = _target(db, user, purchase, order)
    return TargetInfo(
        product=product_ref(product),
        purchase_id=p.id if p else None,
        order_id=o.id if o else None,
        back=back,
        days_left=purchase_services.dispute_days_left(p) if p else None,
        reasons=[(r, ReasonType.label(r)) for r in dispute_services.BUYER_REASONS],
    )


@router.post("/disputes", response_model=Redirect, status_code=201)
def open_dispute(data: DisputeIn, db: DB, user: CurrentUser):
    """Открыть спор по покупке (в течение 7 дней) или по заказу. Причина «передумал» не принимается."""
    p, o, _product, back = _target(db, user, data.purchase_id, data.order_id)
    kwargs = {"reason_type": data.reason_type, "reason": data.reason}
    if p:
        dispute_services.open_purchase_dispute(db, user, p, **kwargs)
    else:
        dispute_services.open_order_dispute(db, user, o, **kwargs)
    db.commit()
    return Redirect(url=back)


# ---------------------------------------------------------------- отзывы


@router.get("/reviews/new", response_model=TargetInfo)
def review_form(db: DB, user: CurrentUser, purchase: int | None = None, order: int | None = None):
    p, o, product, back = _target(db, user, purchase, order)
    return TargetInfo(
        product=product_ref(product), purchase_id=p.id if p else None, order_id=o.id if o else None, back=back
    )


@router.post("/reviews", response_model=Redirect, status_code=201)
def create_review(data: ReviewIn, db: DB, user: CurrentUser):
    p, o, _product, back = _target(db, user, data.purchase_id, data.order_id)
    if p:
        review_services.create_purchase_review(db, user, p, rating=data.rating, text=data.text)
    else:
        review_services.create_order_review(db, user, o, rating=data.rating, text=data.text)
    db.commit()
    return Redirect(url=back)


# ---------------------------------------------------------------- уведомления


@router.get("/notifications", response_model=Page[NotificationOut])
def notifications(db: DB, user: CurrentUser, page: int = 1, page_size: int = 20):
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    items, total, page, pages = catalog_services.paginate(db, stmt, page, page_size)
    return Page(
        items=[
            NotificationOut(id=n.id, text=n.text, link=n.link, is_read=n.is_read, created_at=n.created_at)
            for n in items
        ],
        total=total,
        page=page,
        pages=pages,
    )


@router.get("/notifications/unread", response_model=UnreadOut)
def unread(db: DB, user: CurrentUser):
    """Число в колокольчике (интерфейс опрашивает раз в 30 секунд)."""
    return UnreadOut(count=notification_services.unread_count(db, user))


@router.post("/notifications/read-all", response_model=Ok)
def read_all(db: DB, user: CurrentUser):
    n = notification_services.mark_all_read(db, user)
    db.commit()
    return Ok(message=f"Отмечено прочитанными: {n}")


@router.post("/notifications/{pk}/open", response_model=Redirect)
def open_notification(pk: int, db: DB, user: CurrentUser):
    """Отметить уведомление прочитанным и вернуть его ссылку (только адреса этого сайта)."""
    link = notification_services.open_notification(db, user, pk)
    db.commit()
    return Redirect(url=link)


# ---------------------------------------------------------------- баланс


@router.get("/balance", response_model=BalanceOut)
def balance(db: DB, user: CurrentUser):
    """Баланс продавца: удержано, доступно, выведено, в заявках."""
    b = balance_services.get_balance(db, user)
    return BalanceOut(
        **b,
        min_payout=settings.min_payout,
        hold_days=settings.hold_days,
        commission_percent=int(settings.platform_commission * 100),
        kinds=[(k, OpKind.label(k)) for k in balance_services.SELLER_KINDS],
    )


def _op_title(op) -> str:
    if op.purchase_id and op.purchase is not None:
        return f"Покупка №{op.purchase_id}: «{op.purchase.product.title}»"
    if op.order_id and op.order is not None:
        return f"Заказ №{op.order_id}: «{op.order.product.title}»"
    if op.kind == OpKind.PAYOUT:
        return "Вывод по реквизитам"
    return ""


@router.get("/balance/operations", response_model=Page[OperationOut])
def operations(db: DB, user: CurrentUser, kind: str = "", page: int = 1, page_size: int = 20):
    stmt = balance_services.operations_stmt(user, kind or None)
    items, total, page, pages = catalog_services.paginate(db, stmt, page, page_size)
    return Page(
        items=[
            OperationOut(
                id=op.id,
                kind=op.kind,
                kind_label=OpKind.label(op.kind),
                amount=op.amount,
                status=op.status,
                status_label=OpStatus.label(op.status),
                created_at=op.created_at,
                available_at=op.available_at,
                processed_at=op.processed_at,
                purchase_id=op.purchase_id,
                order_id=op.order_id,
                title=_op_title(op),
                requisites=op.requisites,
            )
            for op in items
        ],
        total=total,
        page=page,
        pages=pages,
    )


@router.post("/balance/payouts", response_model=Ok, status_code=201)
def request_payout(data: PayoutIn, db: DB, user: CurrentUser):
    if data.amount in (None, ""):
        raise ServiceError("Укажите сумму числом.")
    balance_services.request_payout(db, user, data.amount, data.requisites)
    db.commit()
    return Ok(message="Заявка на вывод создана. Администратор обработает её в ближайшее время.")


# ---------------------------------------------------------------- статистика продавца


@router.get("/seller/stats", response_model=SellerStats)
def seller_stats(db: DB, user: SellerUser, date_from: str | None = None, date_to: str | None = None):
    """Продажи, выручка и просмотры по месяцам, конверсия, рейтинг, таблица по продуктам (по умолчанию полгода)."""
    d_from, d_to = report_services.parse_period(date_from, date_to)
    s = report_services.seller_stats(db, user, d_from, d_to)
    return SellerStats(
        date_from=d_from.isoformat(),
        date_to=d_to.isoformat(),
        **{k: v for k, v in s.items() if k != "products"},
        products=[StatsProductRow(**row) for row in s["products"]],
    )

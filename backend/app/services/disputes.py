"""Споры по покупкам и заказам. Деньги за купленный продукт возвращаются только решением администратора."""

import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import InvalidTransition, NotFound, ServiceError
from app.models import CustomOrder, Dispute, DisputeStatus, Message, Purchase, ReasonType, Resolution, User
from app.models.base import utcnow
from app.services.notifications import admins, notify, notify_many

admin_log = logging.getLogger("codemarket.admin")
R = ReasonType
BUYER_REASONS = [R.NOT_WORKING, R.NOT_AS_DESCRIBED, R.OTHER]


def _check_reason(reason_type: str, reason: str) -> None:
    if reason_type not in BUYER_REASONS:
        raise ServiceError("Выберите причину из списка.")
    if not reason or len(reason.strip()) < 10:
        raise ServiceError("Опишите проблему подробнее (не короче 10 символов).")


def _exists(db: Session, **cond) -> bool:
    stmt = select(Dispute.id)
    for k, v in cond.items():
        stmt = stmt.where(getattr(Dispute, k) == v)
    return db.scalar(stmt.limit(1)) is not None


def open_purchase_dispute(db: Session, user: User, purchase: Purchase, *, reason_type: str, reason: str) -> Dispute:
    """Спор по покупке: только покупатель, в течение HOLD_DAYS после оплаты, причина из списка."""
    from app.services import purchases as purchase_services

    if purchase.buyer_id != user.id:
        raise ServiceError("Спор может открыть только покупатель.")
    if _exists(db, purchase_id=purchase.id):
        raise ServiceError("Спор по этой покупке уже открывался.")
    if purchase.status != "paid" or purchase_services.dispute_days_left(purchase) <= 0:
        raise ServiceError("Срок открытия спора по этой покупке истёк.")
    _check_reason(reason_type, reason)
    dispute = Dispute(purchase_id=purchase.id, opened_by_id=user.id, reason_type=reason_type, reason=reason.strip())
    db.add(dispute)
    db.flush()
    purchase_services.open_dispute(db, purchase)
    notify(db, purchase.product.seller, f"Покупатель открыл спор по покупке «{purchase.product.title}».", "/sell/")
    notify_many(db, admins(db), f"Новый спор по покупке №{purchase.id}.", f"/moderation/disputes/{dispute.id}/")
    return dispute


def open_order_dispute(db: Session, user: User, order: CustomOrder, *, reason_type: str, reason: str) -> Dispute:
    """Спор по заказу: покупатель, статусы in_work, submitted, revision, спора ещё нет."""
    from app.services import orders as order_services

    if order.buyer_id != user.id:
        raise ServiceError("Спор может открыть только покупатель.")
    if _exists(db, order_id=order.id):
        raise ServiceError("Спор по этому заказу уже открывался.")
    if order.status not in ("in_work", "submitted", "revision"):
        raise ServiceError("По заказу в этом статусе спор открыть нельзя.")
    _check_reason(reason_type, reason)
    dispute = Dispute(order_id=order.id, opened_by_id=user.id, reason_type=reason_type, reason=reason.strip())
    db.add(dispute)
    db.flush()
    order_services.open_dispute(db, order)
    notify(db, order.product.seller, f"Покупатель открыл спор по заказу №{order.id}.", f"/orders/{order.id}/")
    notify_many(db, admins(db), f"Новый спор по заказу №{order.id}.", f"/moderation/disputes/{dispute.id}/")
    return dispute


def open_system_dispute(db: Session, order: CustomOrder, admin: User | None = None) -> Dispute:
    """Продавец заблокирован: оплаченный заказ переходит в спор для решения администратором."""
    from app.services import orders as order_services

    dispute = Dispute(
        order_id=order.id,
        opened_by_id=(admin or order.buyer).id,
        reason_type=R.SELLER_BLOCKED,
        reason="Продавец заблокирован администратором, заказ передан на решение.",
    )
    db.add(dispute)
    db.flush()
    order_services.open_dispute(db, order)
    notify(
        db,
        order.buyer,
        f"Продавец заблокирован. Заказ №{order.id} передан администратору для решения.",
        f"/orders/{order.id}/",
    )
    return dispute


def disputes_stmt(status: str | None = "open"):
    stmt = select(Dispute).options(
        selectinload(Dispute.purchase).selectinload(Purchase.product),
        selectinload(Dispute.purchase).selectinload(Purchase.buyer),
        selectinload(Dispute.order).selectinload(CustomOrder.product),
        selectinload(Dispute.order).selectinload(CustomOrder.buyer),
    )
    if status in ("open", "closed"):
        stmt = stmt.where(Dispute.status == status)
    return stmt.order_by(Dispute.opened_at.desc(), Dispute.id.desc())


def get_dispute(db: Session, pk: int) -> Dispute:
    d = db.get(Dispute, pk)
    if d is None:
        raise NotFound("Спор не найден")
    return d


def target_price(dispute: Dispute) -> Decimal:
    return dispute.purchase.price if dispute.purchase_id else dispute.order.price


def resolve(db: Session, dispute: Dispute, admin: User, *, resolution: str, refund_amount=None, comment: str = ""):
    """Решение администратора: в пользу продавца, полный возврат или частичный возврат (сумма).

    Возврат по покупке отзывает доступ к копии и отменяет начисление продавцу (refund_reversal).
    Сам возврат денег администратор проводит вручную в кабинете ЮKassa.
    """
    from app.services import orders as order_services
    from app.services import purchases as purchase_services
    from app.services.payments import mark_refund

    db.refresh(dispute, with_for_update=True)
    if dispute.status != DisputeStatus.OPEN:
        raise InvalidTransition("Спор уже закрыт")
    price = target_price(dispute)
    amount = Decimal("0")
    if resolution == Resolution.REFUND:
        amount = Decimal(price)
    elif resolution == Resolution.PARTIAL:
        try:
            amount = Decimal(str(refund_amount).replace(",", ".").replace(" ", ""))
        except (InvalidOperation, TypeError):
            raise ServiceError("Укажите сумму частичного возврата.")
        if not 0 < amount < price:
            raise ServiceError(f"Сумма частичного возврата должна быть больше 0 и меньше {price:.0f} ₽.")
    elif resolution != Resolution.SELLER:
        raise ServiceError("Выберите решение.")

    if dispute.purchase_id:
        purchase_services.resolve_dispute(db, dispute.purchase, outcome=resolution, refund_amount=amount)
        if amount:
            mark_refund(db, amount=amount, purchase=dispute.purchase, admin=admin)
        parties = [dispute.purchase.buyer, dispute.purchase.product.seller]
        link = f"/me/purchases/{dispute.purchase_id}/"
    else:
        order_services.resolve_dispute(db, dispute.order, outcome=resolution, refund_amount=amount)
        parties = [dispute.order.buyer, dispute.order.product.seller]
        link = f"/orders/{dispute.order_id}/"

    comment = (comment or "").strip()
    dispute.status = DisputeStatus.CLOSED
    dispute.resolution = resolution
    dispute.refund_amount = amount
    dispute.admin_id = admin.id
    dispute.admin_comment = comment
    dispute.closed_at = utcnow()
    db.flush()
    text = f"Спор решён: {Resolution.label(resolution).lower()}" + (f", возврат {amount:.0f} ₽" if amount else "")
    if comment:
        text += f". Комментарий: {comment}"
    notify_many(db, parties, text, link)
    admin_log.info(
        "admin=%s resolved dispute=%s resolution=%s amount=%s", admin.username, dispute.id, resolution, amount
    )
    return dispute


def dispute_context(db: Session, dispute: Dispute) -> dict:
    """Данные для страницы спора у администратора: переписка, результаты, версия кода."""
    from app.services.versions import current_version

    ctx: dict = {"dispute": dispute, "chat_messages": [], "results": [], "version": None, "order": None}
    if dispute.order_id:
        msgs = list(dispute.order.messages)
        ctx.update(chat_messages=msgs, results=[m for m in msgs if m.is_result], order=dispute.order)
        ctx["product"] = dispute.order.product
        ctx["purchase"] = None
    else:
        ctx["purchase"] = dispute.purchase
        ctx["product"] = dispute.purchase.product
        ctx["version"] = dispute.purchase.version
        orders = db.scalars(select(CustomOrder).where(CustomOrder.purchase_id == dispute.purchase_id)).all()
        ctx["chat_messages"] = [
            m for o in orders for m in db.scalars(select(Message).where(Message.order_id == o.id).order_by(Message.id))
        ]
    ctx["version"] = ctx["version"] or current_version(db, ctx["product"])
    ctx["price"] = target_price(dispute)
    return ctx

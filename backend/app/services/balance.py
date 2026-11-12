"""Баланс продавца и выплаты. Баланс считается из BalanceOperation одной функцией get_balance."""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import InvalidTransition, NotFound, ServiceError
from app.models import BalanceOperation, OpKind, OpStatus, User
from app.models.base import utcnow
from app.services.notifications import notify

K = OpKind
St = OpStatus
admin_log = logging.getLogger("codemarket.admin")
CENT = Decimal("0.01")
SELLER_KINDS = [K.INCOME, K.REFUND_REVERSAL, K.PAYOUT]


def money(x) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def commission_for(amount) -> Decimal:
    """Комиссия платформы с суммы (PLATFORM_COMMISSION, по умолчанию 10 %)."""
    return money(Decimal(amount) * settings.platform_commission)


def get_balance(db: Session, user: User) -> dict[str, Decimal]:
    """Баланс продавца: {'held', 'available', 'withdrawn', 'requested'} в рублях."""

    def total(*cond):
        return db.scalar(
            select(func.coalesce(func.sum(BalanceOperation.amount), 0)).where(
                BalanceOperation.user_id == user.id, BalanceOperation.kind.in_(SELLER_KINDS), *cond
            )
        ) or Decimal("0")

    held = total(BalanceOperation.status == St.HELD)
    payouts = total(BalanceOperation.kind == K.PAYOUT, BalanceOperation.status.in_([St.REQUESTED, St.PAID]))
    available = total(BalanceOperation.status == St.AVAILABLE) + payouts
    withdrawn = -total(BalanceOperation.kind == K.PAYOUT, BalanceOperation.status == St.PAID)
    requested = -total(BalanceOperation.kind == K.PAYOUT, BalanceOperation.status == St.REQUESTED)
    return {
        "held": Decimal(held),
        "available": Decimal(available),
        "withdrawn": Decimal(withdrawn),
        "requested": Decimal(requested),
    }


def _op(db: Session, **fields) -> BalanceOperation:
    op = BalanceOperation(**fields)
    db.add(op)
    db.flush()
    return op


def _exists(db: Session, *cond) -> bool:
    return db.scalar(select(BalanceOperation.id).where(*cond).limit(1)) is not None


# ---------------------------------------------------------------- начисления


def credit_sale(db: Session, purchase) -> BalanceOperation | None:
    """Начислить продавцу оплату продукта: income (цена − комиссия) в статусе held на HOLD_DAYS.

    Повторный вызов для той же покупки ничего не делает (защита от повторного вебхука).
    """
    if _exists(
        db,
        BalanceOperation.purchase_id == purchase.id,
        BalanceOperation.order_id.is_(None),
        BalanceOperation.kind == K.INCOME,
    ):
        return None
    seller_id = purchase.product.seller_id
    available_at = utcnow() + timedelta(days=settings.hold_days)
    income = _op(
        db,
        user_id=seller_id,
        purchase_id=purchase.id,
        kind=K.INCOME,
        amount=money(purchase.price - purchase.commission),
        status=St.HELD,
        available_at=available_at,
    )
    _op(
        db,
        user_id=seller_id,
        purchase_id=purchase.id,
        kind=K.COMMISSION,
        amount=money(purchase.commission),
        status=St.HELD,
        available_at=available_at,
    )
    return income


def credit_order(db: Session, order) -> BalanceOperation | None:
    """Начислить продавцу оплату доработки после приёмки: сразу available (цена − комиссия)."""
    if _exists(db, BalanceOperation.order_id == order.id, BalanceOperation.kind == K.INCOME):
        return None
    seller_id = order.product.seller_id
    commission = commission_for(order.price)
    now = utcnow()
    income = _op(
        db,
        user_id=seller_id,
        order_id=order.id,
        kind=K.INCOME,
        amount=money(order.price - commission),
        status=St.AVAILABLE,
        available_at=now,
        processed_at=now,
    )
    _op(
        db,
        user_id=seller_id,
        order_id=order.id,
        kind=K.COMMISSION,
        amount=commission,
        status=St.AVAILABLE,
        available_at=now,
    )
    return income


def credit_order_partial(db: Session, order, refund_amount) -> BalanceOperation | None:
    """Спор по заказу решён частичным возвратом: продавцу начисляется остаток за вычетом комиссии."""
    rest = money(Decimal(order.price) - Decimal(refund_amount))
    if rest <= 0 or _exists(db, BalanceOperation.order_id == order.id, BalanceOperation.kind == K.INCOME):
        return None
    commission = commission_for(rest)
    now = utcnow()
    seller_id = order.product.seller_id
    _op(db, user_id=seller_id, order_id=order.id, kind=K.COMMISSION, amount=commission, status=St.AVAILABLE)
    return _op(
        db,
        user_id=seller_id,
        order_id=order.id,
        kind=K.INCOME,
        amount=rest - commission,
        status=St.AVAILABLE,
        available_at=now,
        processed_at=now,
    )


def reverse_purchase(db: Session, purchase, refund_amount) -> BalanceOperation | None:
    """Отменить начисление по покупке при возврате (refund_reversal).

    Продавец возвращает долю refund_amount / цена от своего начисления, платформа — ту же долю комиссии.
    Операции получают тот же статус, что и начисление (held или available).
    """
    income = db.scalar(
        select(BalanceOperation).where(
            BalanceOperation.purchase_id == purchase.id,
            BalanceOperation.order_id.is_(None),
            BalanceOperation.kind == K.INCOME,
        )
    )
    if income is None or income.status == St.CANCELLED:
        return None
    share = min(Decimal(refund_amount) / Decimal(purchase.price), Decimal("1"))
    seller_part = money(income.amount * share)
    commission_part = money(purchase.commission * share)
    op = _op(
        db,
        user_id=income.user_id,
        purchase_id=purchase.id,
        kind=K.REFUND_REVERSAL,
        amount=-seller_part,
        status=income.status,
        available_at=income.available_at,
        processed_at=utcnow(),
    )
    _op(
        db,
        user_id=income.user_id,
        purchase_id=purchase.id,
        kind=K.COMMISSION,
        amount=-commission_part,
        status=income.status,
        available_at=income.available_at,
    )
    return op


def release_funds(db: Session, now=None) -> int:
    """Перевести held → available, если срок удержания прошёл и по покупке нет спора.

    Покупка при этом переходит в completed. Задача планировщика release_funds (раз в час).
    """
    from app.models import Purchase, PurchaseStatus
    from app.services.purchases import complete_purchase

    now = now or utcnow()
    ops = db.scalars(
        select(BalanceOperation)
        .where(BalanceOperation.status == St.HELD, BalanceOperation.available_at <= now)
        .with_for_update()
    ).all()
    purchase_ids = {op.purchase_id for op in ops if op.purchase_id}
    blocked = set(
        db.scalars(select(Purchase.id).where(Purchase.status == PurchaseStatus.DISPUTE, Purchase.id.in_(purchase_ids)))
    )
    released, purchases, net = 0, set(), {}
    for op in ops:
        if op.purchase_id in blocked:
            continue
        op.status = St.AVAILABLE
        op.processed_at = now
        if op.kind == K.INCOME:
            released += 1
        if op.kind in (K.INCOME, K.REFUND_REVERSAL):
            key = (op.user_id, op.purchase_id)
            net[key] = net.get(key, Decimal("0")) + op.amount
        if op.purchase_id:
            purchases.add(op.purchase_id)
    db.flush()
    # уведомление — чистая сумма по покупке (после полного возврата 0 — не уведомляем)
    for (uid, purchase_id), amount in net.items():
        if amount > 0:
            notify(
                db, db.get(User, uid), f"{money(amount)} ₽ за покупку №{purchase_id} доступны к выводу.", "/balance/"
            )
    for p in db.scalars(
        select(Purchase).where(Purchase.id.in_(purchases), Purchase.status == PurchaseStatus.PAID)
    ).all():
        complete_purchase(db, p)
    return released


# ---------------------------------------------------------------- выплаты


def request_payout(db: Session, user: User, amount, requisites: str) -> BalanceOperation:
    """Заявка на вывод: не меньше MIN_PAYOUT и не больше доступного, сумма списывается из доступного сразу."""
    try:
        amount = money(str(amount).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError):
        raise ServiceError("Укажите сумму числом.")
    if amount < settings.min_payout:
        raise ServiceError(f"Минимальная сумма вывода — {settings.min_payout:.0f} ₽.")
    # блокировка строк пользователя, чтобы две заявки одновременно не ушли в минус
    db.execute(select(BalanceOperation.id).where(BalanceOperation.user_id == user.id).with_for_update()).all()
    if amount > get_balance(db, user)["available"]:
        raise ServiceError("Сумма больше доступного остатка.")
    if not requisites or len(requisites.strip()) < 10:
        raise ServiceError("Укажите реквизиты для перевода.")
    return _op(db, user_id=user.id, kind=K.PAYOUT, amount=-amount, status=St.REQUESTED, requisites=requisites.strip())


def requested_payouts_stmt():
    return (
        select(BalanceOperation)
        .where(BalanceOperation.kind == K.PAYOUT, BalanceOperation.status == St.REQUESTED)
        .options(selectinload(BalanceOperation.user))
        .order_by(BalanceOperation.created_at)
    )


def recent_payouts_stmt():
    return (
        select(BalanceOperation)
        .where(BalanceOperation.kind == K.PAYOUT, BalanceOperation.status.in_([St.PAID, St.CANCELLED]))
        .options(selectinload(BalanceOperation.user))
        .order_by(BalanceOperation.processed_at.desc().nulls_last())
        .limit(20)
    )


def _payout(db: Session, op_id: int) -> BalanceOperation:
    op = db.scalar(
        select(BalanceOperation)
        .where(BalanceOperation.id == op_id, BalanceOperation.kind == K.PAYOUT)
        .with_for_update()
    )
    if op is None:
        raise NotFound("Заявка не найдена")
    if op.status != St.REQUESTED:
        raise InvalidTransition("Заявка уже обработана")
    return op


def mark_payout_paid(db: Session, op_id: int, admin: User) -> BalanceOperation:
    """Администратор отметил заявку выплаченной (реальный перевод вне системы)."""
    op = _payout(db, op_id)
    op.status = St.PAID
    op.processed_at = utcnow()
    db.flush()
    notify(db, op.user, f"Выплата {money(-op.amount)} ₽ отправлена по вашим реквизитам.", "/balance/")
    admin_log.info("admin=%s payout paid op=%s", admin.username, op.id)
    return op


def reject_payout(db: Session, op_id: int, admin: User, reason: str = "") -> BalanceOperation:
    """Отклонить заявку: деньги возвращаются в доступные."""
    op = _payout(db, op_id)
    op.status = St.CANCELLED
    op.processed_at = utcnow()
    db.flush()
    notify(
        db,
        op.user,
        f"Заявка на вывод {money(-op.amount)} ₽ отклонена{': ' + reason if reason else ''}. Деньги вернулись в доступные.",
        "/balance/",
    )
    admin_log.info("admin=%s payout rejected op=%s reason=%s", admin.username, op.id, reason)
    return op


def operations_stmt(user: User, kind: str | None = None):
    stmt = (
        select(BalanceOperation)
        .where(BalanceOperation.user_id == user.id, BalanceOperation.kind.in_(SELLER_KINDS))
        .options(selectinload(BalanceOperation.purchase), selectinload(BalanceOperation.order))
        .order_by(BalanceOperation.created_at.desc(), BalanceOperation.id.desc())
    )
    if kind in SELLER_KINDS:
        stmt = stmt.where(BalanceOperation.kind == kind)
    return stmt


__all__ = ["and_"]

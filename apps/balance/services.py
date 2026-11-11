"""Баланс продавца и выплаты. Баланс считается из BalanceOperation одной функцией get_balance."""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.exceptions import InvalidTransition, ServiceError
from apps.notifications.services import notify

from .models import BalanceOperation

K = BalanceOperation.Kind
St = BalanceOperation.Status
admin_log = logging.getLogger("codemarket.admin")
CENT = Decimal("0.01")
SELLER_KINDS = [K.INCOME, K.REFUND_REVERSAL, K.PAYOUT]


def money(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def commission_for(amount):
    """Комиссия платформы с суммы (PLATFORM_COMMISSION, по умолчанию 10 %)."""
    return money(Decimal(amount) * settings.PLATFORM_COMMISSION)


def get_balance(user):
    """Баланс продавца: {'held', 'available', 'withdrawn', 'requested'} в рублях."""
    ops = BalanceOperation.objects.filter(user=user, kind__in=SELLER_KINDS)

    def total(q):
        return ops.filter(q).aggregate(s=Sum("amount"))["s"] or Decimal("0")

    held = total(Q(status=St.HELD))
    available = total(Q(status=St.AVAILABLE)) + total(Q(kind=K.PAYOUT, status__in=[St.REQUESTED, St.PAID]))
    withdrawn = -total(Q(kind=K.PAYOUT, status=St.PAID))
    requested = -total(Q(kind=K.PAYOUT, status=St.REQUESTED))
    return {"held": held, "available": available, "withdrawn": withdrawn, "requested": requested}


# ---------------------------------------------------------------- начисления


def credit_sale(purchase):
    """Начислить продавцу оплату продукта: income (цена − комиссия) в статусе held на HOLD_DAYS.

    Повторный вызов для той же покупки ничего не делает (защита от повторного вебхука).
    """
    seller = purchase.product.seller
    if BalanceOperation.objects.filter(purchase=purchase, order__isnull=True, kind=K.INCOME).exists():
        return None
    available_at = timezone.now() + timedelta(days=settings.HOLD_DAYS)
    income = BalanceOperation.objects.create(
        user=seller,
        purchase=purchase,
        kind=K.INCOME,
        amount=money(purchase.price - purchase.commission),
        status=St.HELD,
        available_at=available_at,
    )
    BalanceOperation.objects.create(
        user=seller,
        purchase=purchase,
        kind=K.COMMISSION,
        amount=money(purchase.commission),
        status=St.HELD,
        available_at=available_at,
    )
    return income


def credit_order(order):
    """Начислить продавцу оплату доработки после приёмки: сразу available (цена − комиссия)."""
    if BalanceOperation.objects.filter(order=order, kind=K.INCOME).exists():
        return None
    seller = order.product.seller
    commission = commission_for(order.price)
    now = timezone.now()
    income = BalanceOperation.objects.create(
        user=seller,
        order=order,
        kind=K.INCOME,
        amount=money(order.price - commission),
        status=St.AVAILABLE,
        available_at=now,
        processed_at=now,
    )
    BalanceOperation.objects.create(
        user=seller, order=order, kind=K.COMMISSION, amount=commission, status=St.AVAILABLE, available_at=now
    )
    return income


def credit_order_partial(order, refund_amount):
    """Спор по заказу решён частичным возвратом: продавцу начисляется остаток за вычетом комиссии."""
    rest = money(Decimal(order.price) - Decimal(refund_amount))
    if rest <= 0 or BalanceOperation.objects.filter(order=order, kind=K.INCOME).exists():
        return None
    commission = commission_for(rest)
    now = timezone.now()
    BalanceOperation.objects.create(
        user=order.product.seller, order=order, kind=K.COMMISSION, amount=commission, status=St.AVAILABLE
    )
    return BalanceOperation.objects.create(
        user=order.product.seller,
        order=order,
        kind=K.INCOME,
        amount=rest - commission,
        status=St.AVAILABLE,
        available_at=now,
        processed_at=now,
    )


def reverse_purchase(purchase, refund_amount):
    """Отменить начисление по покупке при возврате (refund_reversal).

    Продавец возвращает долю refund_amount / цена от своего начисления, платформа — ту же долю комиссии.
    Операции получают тот же статус, что и начисление (held или available).
    """
    income = BalanceOperation.objects.filter(purchase=purchase, order__isnull=True, kind=K.INCOME).first()
    if income is None or income.status == St.CANCELLED:
        return None
    share = Decimal(refund_amount) / Decimal(purchase.price)
    share = min(share, Decimal("1"))
    seller_part = money(income.amount * share)
    commission_part = money(purchase.commission * share)
    op = BalanceOperation.objects.create(
        user=income.user,
        purchase=purchase,
        kind=K.REFUND_REVERSAL,
        amount=-seller_part,
        status=income.status,
        available_at=income.available_at,
        processed_at=timezone.now(),
    )
    BalanceOperation.objects.create(
        user=income.user,
        purchase=purchase,
        kind=K.COMMISSION,
        amount=-commission_part,
        status=income.status,
        available_at=income.available_at,
    )
    return op


@transaction.atomic
def release_funds(now=None):
    """Перевести held → available, если срок удержания прошёл и по покупке нет спора.

    Покупка при этом переходит в completed. Вызывается командой release_funds раз в час.
    """
    from apps.purchases.models import Purchase
    from apps.purchases.services import complete_purchase

    now = now or timezone.now()
    ops = list(BalanceOperation.objects.select_for_update().filter(status=St.HELD, available_at__lte=now))
    blocked = set(
        Purchase.objects.filter(
            status=Purchase.Status.DISPUTE, id__in={op.purchase_id for op in ops if op.purchase_id}
        ).values_list("id", flat=True)
    )
    released, purchases, net = 0, set(), {}
    for op in ops:
        if op.purchase_id in blocked:
            continue
        op.status = St.AVAILABLE
        op.processed_at = now
        op.save(update_fields=["status", "processed_at"])
        if op.kind == K.INCOME:
            released += 1
        if op.kind in (K.INCOME, K.REFUND_REVERSAL):
            key = (op.user_id, op.purchase_id)
            net[key] = net.get(key, Decimal("0")) + op.amount
        if op.purchase_id:
            purchases.add(op.purchase_id)
    # уведомление — чистая сумма по покупке (после возврата может быть 0, тогда не уведомляем)
    from apps.accounts.models import User

    users = User.objects.in_bulk({uid for uid, _ in net})
    for (uid, purchase_id), amount in net.items():
        if amount > 0:
            notify(users[uid], f"{money(amount)} ₽ за покупку №{purchase_id} доступны к выводу.", "/balance/")
    for p in Purchase.objects.filter(id__in=purchases, status=Purchase.Status.PAID):
        complete_purchase(p)
    return released


# ---------------------------------------------------------------- выплаты


@transaction.atomic
def request_payout(user, amount, requisites):
    """Заявка на вывод: не меньше MIN_PAYOUT и не больше доступного, сумма списывается из доступного сразу."""
    try:
        amount = money(amount)
    except Exception:
        raise ServiceError("Укажите сумму числом.")
    if amount < settings.MIN_PAYOUT:
        raise ServiceError(f"Минимальная сумма вывода — {settings.MIN_PAYOUT:.0f} ₽.")
    # блокировка строк пользователя, чтобы две заявки одновременно не ушли в минус
    list(BalanceOperation.objects.select_for_update().filter(user=user).values_list("id", flat=True))
    if amount > get_balance(user)["available"]:
        raise ServiceError("Сумма больше доступного остатка.")
    if not requisites or len(requisites.strip()) < 10:
        raise ServiceError("Укажите реквизиты для перевода.")
    return BalanceOperation.objects.create(
        user=user, kind=K.PAYOUT, amount=-amount, status=St.REQUESTED, requisites=requisites.strip()
    )


def requested_payouts():
    return BalanceOperation.objects.filter(kind=K.PAYOUT, status=St.REQUESTED).select_related("user")


def _payout(op_id):
    op = BalanceOperation.objects.select_for_update().get(pk=op_id, kind=K.PAYOUT)
    if op.status != St.REQUESTED:
        raise InvalidTransition("Заявка уже обработана")
    return op


@transaction.atomic
def mark_payout_paid(op_id, admin):
    """Администратор отметил заявку выплаченной (реальный перевод вне системы)."""
    op = _payout(op_id)
    op.status = St.PAID
    op.processed_at = timezone.now()
    op.save(update_fields=["status", "processed_at"])
    notify(op.user, f"Выплата {money(-op.amount)} ₽ отправлена по вашим реквизитам.", "/balance/")
    admin_log.info("admin=%s payout paid op=%s", admin, op.pk)
    return op


@transaction.atomic
def reject_payout(op_id, admin, reason=""):
    """Отклонить заявку: деньги возвращаются в доступные."""
    op = _payout(op_id)
    op.status = St.CANCELLED
    op.processed_at = timezone.now()
    op.save(update_fields=["status", "processed_at"])
    notify(
        op.user,
        f"Заявка на вывод {money(-op.amount)} ₽ отклонена{': ' + reason if reason else ''}. Деньги вернулись в доступные.",
        "/balance/",
    )
    admin_log.info("admin=%s payout rejected op=%s reason=%s", admin, op.pk, reason)
    return op


def operations(user, kind=None):
    qs = BalanceOperation.objects.filter(user=user, kind__in=SELLER_KINDS).select_related("purchase", "order")
    if kind in SELLER_KINDS:
        qs = qs.filter(kind=kind)
    return qs

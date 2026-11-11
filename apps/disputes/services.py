"""Споры по покупкам и заказам. Деньги за купленный продукт возвращаются только решением администратора."""

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import InvalidTransition, ServiceError
from apps.notifications.services import notify, notify_many

from .models import Dispute

admin_log = logging.getLogger("codemarket.admin")
R = Dispute.ReasonType
BUYER_REASONS = [R.NOT_WORKING, R.NOT_AS_DESCRIBED, R.OTHER]


def _admins():
    from apps.accounts.models import User

    return User.objects.filter(is_staff=True, status="active")


def _check_reason(reason_type, reason):
    if reason_type not in BUYER_REASONS:
        raise ServiceError("Выберите причину из списка.")
    if not reason or len(reason.strip()) < 10:
        raise ServiceError("Опишите проблему подробнее (не короче 10 символов).")


@transaction.atomic
def open_purchase_dispute(user, purchase, *, reason_type, reason):
    """Спор по покупке: только покупатель, в течение HOLD_DAYS после оплаты, причина из списка."""
    from apps.purchases import services as purchase_services

    if purchase.buyer_id != user.id:
        raise ServiceError("Спор может открыть только покупатель.")
    if purchase.disputes.exists():
        raise ServiceError("Спор по этой покупке уже открывался.")
    if purchase.status != "paid" or purchase_services.dispute_days_left(purchase) <= 0:
        raise ServiceError("Срок открытия спора по этой покупке истёк.")
    _check_reason(reason_type, reason)
    dispute = Dispute.objects.create(purchase=purchase, opened_by=user, reason_type=reason_type, reason=reason.strip())
    purchase_services.open_dispute(purchase)
    notify(purchase.product.seller, f"Покупатель открыл спор по покупке «{purchase.product.title}».", "/sell/")
    notify_many(_admins(), f"Новый спор по покупке №{purchase.pk}.", f"/moderation/disputes/{dispute.pk}/")
    return dispute


@transaction.atomic
def open_order_dispute(user, order, *, reason_type, reason):
    """Спор по заказу: покупатель, статусы in_work, submitted, revision, спора ещё нет."""
    from apps.orders import services as order_services

    if order.buyer_id != user.id:
        raise ServiceError("Спор может открыть только покупатель.")
    if order.disputes.exists():
        raise ServiceError("Спор по этому заказу уже открывался.")
    if order.status not in ("in_work", "submitted", "revision"):
        raise ServiceError("По заказу в этом статусе спор открыть нельзя.")
    _check_reason(reason_type, reason)
    dispute = Dispute.objects.create(order=order, opened_by=user, reason_type=reason_type, reason=reason.strip())
    order_services.open_dispute(order)
    notify(order.product.seller, f"Покупатель открыл спор по заказу №{order.pk}.", f"/orders/{order.pk}/")
    notify_many(_admins(), f"Новый спор по заказу №{order.pk}.", f"/moderation/disputes/{dispute.pk}/")
    return dispute


def open_system_dispute(order, admin=None):
    """Продавец заблокирован: оплаченный заказ переходит в спор для решения администратором."""
    from apps.orders import services as order_services

    dispute = Dispute.objects.create(
        order=order,
        opened_by=admin or order.buyer,
        reason_type=R.SELLER_BLOCKED,
        reason="Продавец заблокирован администратором, заказ передан на решение.",
    )
    order_services.open_dispute(order)
    notify(
        order.buyer,
        f"Продавец заблокирован. Заказ №{order.pk} передан администратору для решения.",
        f"/orders/{order.pk}/",
    )
    return dispute


def open_disputes():
    return Dispute.objects.filter(status=Dispute.Status.OPEN)


def target_price(dispute):
    return dispute.purchase.price if dispute.purchase_id else dispute.order.price


@transaction.atomic
def resolve(dispute, admin, *, resolution, refund_amount=None, comment=""):
    """Решение администратора: в пользу продавца, полный возврат или частичный возврат (сумма).

    Возврат по покупке отзывает доступ к копии и отменяет начисление продавцу (refund_reversal).
    Сам возврат денег администратор проводит вручную в кабинете ЮKassa.
    """
    from apps.orders import services as order_services
    from apps.payments.services import mark_refund
    from apps.purchases import services as purchase_services

    dispute = Dispute.objects.select_for_update().get(pk=dispute.pk)
    if dispute.status != Dispute.Status.OPEN:
        raise InvalidTransition("Спор уже закрыт")
    price = target_price(dispute)
    amount = Decimal("0")
    if resolution == Dispute.Resolution.REFUND:
        amount = Decimal(price)
    elif resolution == Dispute.Resolution.PARTIAL:
        try:
            amount = Decimal(str(refund_amount).replace(",", ".").replace(" ", ""))
        except (InvalidOperation, TypeError):
            raise ServiceError("Укажите сумму частичного возврата.")
        if not 0 < amount < price:
            raise ServiceError(f"Сумма частичного возврата должна быть больше 0 и меньше {price:.0f} ₽.")
    elif resolution != Dispute.Resolution.SELLER:
        raise ServiceError("Выберите решение.")

    outcome = {"seller": "seller", "refund": "refund", "partial": "partial"}[resolution]
    if dispute.purchase_id:
        purchase_services.resolve_dispute(dispute.purchase, outcome=outcome, refund_amount=amount)
        if amount:
            mark_refund(amount=amount, purchase=dispute.purchase, admin=admin)
        parties = [dispute.purchase.buyer, dispute.purchase.product.seller]
        link = f"/me/purchases/{dispute.purchase_id}/"
    else:
        order_services.resolve_dispute(dispute.order, outcome=outcome, refund_amount=amount)
        parties = [dispute.order.buyer, dispute.order.product.seller]
        link = f"/orders/{dispute.order_id}/"

    dispute.status = Dispute.Status.CLOSED
    dispute.resolution = resolution
    dispute.refund_amount = amount
    dispute.admin = admin
    dispute.admin_comment = comment.strip()
    dispute.closed_at = timezone.now()
    dispute.save()
    text = f"Спор решён: {dispute.get_resolution_display().lower()}" + (f", возврат {amount:.0f} ₽" if amount else "")
    if comment.strip():
        text += f". Комментарий: {comment.strip()}"
    notify_many(parties, text, link)
    admin_log.info("admin=%s resolved dispute=%s resolution=%s amount=%s", admin, dispute.pk, resolution, amount)
    return dispute


def dispute_context(dispute):
    """Данные для страницы спора у администратора: переписка, результат, версия кода."""
    ctx = {"dispute": dispute, "chat_messages": [], "results": [], "version": None}
    if dispute.order_id:
        msgs = list(dispute.order.messages.select_related("author"))
        ctx["chat_messages"] = msgs
        ctx["results"] = [m for m in msgs if m.is_result]
        ctx["order"] = dispute.order
        ctx["product"] = dispute.order.product
    else:
        ctx["purchase"] = dispute.purchase
        ctx["product"] = dispute.purchase.product
        ctx["version"] = dispute.purchase.version
        ctx["chat_messages"] = [m for o in dispute.purchase.orders.all() for m in o.messages.select_related("author")]
    from apps.versions.services import current_version

    ctx["version"] = ctx["version"] or current_version(ctx["product"])
    ctx["price"] = target_price(dispute)
    return ctx

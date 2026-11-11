"""Сервисы оплаты: создание платежа, обработка уведомления провайдера, отметка возврата.

Статус оплаты меняется только после проверки запросом к провайдеру (get_status).
Повторное уведомление идемпотентно: уже оплаченный платёж повторно не обрабатывается.
"""

import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F

from apps.core.exceptions import ServiceError

from .models import Payment
from .providers import PaymentError, get_provider

hook_log = logging.getLogger("codemarket.webhooks")
admin_log = logging.getLogger("codemarket.admin")


def create_payment(*, amount, description, purchase=None, order=None):
    """Создать платёж у провайдера с ключом идемпотентности; вернуть Payment (с confirmation_url)."""
    if purchase is None and order is None:
        raise ValueError("Нужна покупка или заказ")
    payment = Payment.objects.create(
        purchase=purchase, order=order, amount=Decimal(amount), idempotence_key=uuid.uuid4().hex
    )
    return_url = f"{settings.SITE_URL.rstrip('/')}/payments/return/{payment.pk}/"
    try:
        created = get_provider().create_payment(
            amount=payment.amount,
            description=description,
            idempotence_key=payment.idempotence_key,
            return_url=return_url,
            metadata={"payment_id": payment.pk},
        )
    except PaymentError as e:
        payment.status = Payment.Status.CANCELED
        payment.save(update_fields=["status"])
        raise ServiceError(str(e))
    payment.external_id = created.external_id
    payment.confirmation_url = created.confirmation_url
    payment.save(update_fields=["external_id", "confirmation_url"])
    return payment


def pending_payment_for(*, purchase=None, order=None):
    """Неоплаченный платёж покупки или заказа (чтобы не создавать второй)."""
    qs = Payment.objects.filter(status=Payment.Status.PENDING)
    qs = qs.filter(purchase=purchase) if purchase else qs.filter(order=order)
    return qs.exclude(external_id="").first()


def handle_notification(external_id):
    """Обработать уведомление провайдера (вебхук или страница-заглушка).

    Статус обязательно перепроверяется запросом к провайдеру. Возвращает Payment или None.
    """
    hook_log.info("Уведомление об оплате %s", external_id)
    try:
        status = get_provider().get_status(external_id)
    except PaymentError as e:
        hook_log.warning("Проверка платежа %s не удалась: %s", external_id, e)
        return None
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(external_id=external_id).first()
        if payment is None:
            hook_log.warning("Платёж %s не найден", external_id)
            return None
        if payment.status == Payment.Status.CANCELED and status == "succeeded":
            # покупатель оплатил после отмены (таймаут, отмена заказа): деньги пришли, товар не выдаём
            payment.status = Payment.Status.SUCCEEDED
            payment.save(update_fields=["status"])
            _alert_admins(
                f"Платёж №{payment.pk} ({external_id}) на {payment.amount} ₽ оплачен после отмены покупки или заказа: "
                "верните деньги покупателю в кабинете ЮKassa."
            )
            return payment
        if payment.status != Payment.Status.PENDING:
            hook_log.info("Платёж %s уже обработан (%s)", external_id, payment.status)
            return payment
        if status == "succeeded":
            payment.status = Payment.Status.SUCCEEDED
            payment.save(update_fields=["status"])
            _dispatch_success(payment)
            hook_log.info("Платёж %s оплачен: %s ₽", external_id, payment.amount)
        elif status == "canceled":
            payment.status = Payment.Status.CANCELED
            payment.save(update_fields=["status"])
            _dispatch_cancel(payment)
            hook_log.info("Платёж %s отменён", external_id)
    return payment


def _alert_admins(text):
    from apps.accounts.models import User
    from apps.notifications.services import notify_many

    hook_log.error(text)
    notify_many(User.objects.filter(is_staff=True), text, "/moderation/")


def _dispatch_success(payment):
    if payment.order_id:
        from apps.orders.services import on_payment_succeeded

        on_payment_succeeded(payment.order, payment)
    else:
        from apps.purchases.services import on_payment_succeeded

        on_payment_succeeded(payment.purchase)


def _dispatch_cancel(payment):
    if payment.purchase_id and not payment.order_id:
        from apps.purchases.services import on_payment_canceled

        on_payment_canceled(payment.purchase)


def refresh_payment(payment):
    """Проверить статус платежа у провайдера (страница возврата после оплаты)."""
    if payment.status == Payment.Status.PENDING and payment.external_id:
        handle_notification(payment.external_id)
        payment.refresh_from_db()
    return payment


def cancel_pending(payment):
    """Отменить неоплаченный платёж у нас (по таймауту или отмене заказа)."""
    if payment.status == Payment.Status.PENDING:
        payment.status = Payment.Status.CANCELED
        payment.save(update_fields=["status"])


def mark_refund(*, amount, purchase=None, order=None, admin=None):
    """Отметить возврат по платежу. Сам возврат администратор проводит вручную в кабинете ЮKassa."""
    qs = Payment.objects.filter(status__in=[Payment.Status.SUCCEEDED, Payment.Status.PARTIALLY_REFUNDED])
    payment = (qs.filter(order=order) if order else qs.filter(purchase=purchase, order__isnull=True)).first()
    if payment is None and purchase is not None:
        # покупка оплачена в составе заказа «Купить с доработкой»: платёж заказа больше цены доработки
        payment = qs.filter(order__purchase=purchase, amount__gt=F("order__price")).first()
    if payment is None:
        return None
    amount = Decimal(amount)
    payment.refund_amount = min(payment.amount, payment.refund_amount + amount)
    payment.status = (
        Payment.Status.REFUNDED if payment.refund_amount >= payment.amount else Payment.Status.PARTIALLY_REFUNDED
    )
    payment.save(update_fields=["refund_amount", "status"])
    admin_log.info("refund marked payment=%s amount=%s admin=%s", payment.pk, amount, admin)
    from apps.accounts.models import User
    from apps.notifications.services import notify_many

    notify_many(
        User.objects.filter(is_staff=True),
        f"Нужно вернуть {amount} ₽ по платежу №{payment.pk} ({payment.external_id}) в кабинете ЮKassa.",
        "/moderation/disputes/",
    )
    return payment

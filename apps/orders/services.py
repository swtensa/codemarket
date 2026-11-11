"""Сервисы заказов на доработку и чата. Все переходы — по таблице 7.4 ТЗ.

Недопустимый переход или действие не той стороной вызывает InvalidTransition.
Смена статуса пишется в чат системным сообщением — это и есть история статусов заказа.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.exceptions import InvalidTransition, ServiceError
from apps.notifications.services import notify

from .models import ORDER_MAX_DAYS, ORDER_MIN_DAYS, ORDER_MIN_PRICE, CustomOrder, Message

log = logging.getLogger("codemarket")
S = CustomOrder.Status
K = CustomOrder.Kind

TRANSITIONS = {
    S.NEW: {S.OFFER, S.CANCELLED},
    S.OFFER: {S.OFFER, S.AWAITING_PAYMENT, S.CANCELLED},
    S.AWAITING_PAYMENT: {S.IN_WORK, S.CANCELLED},
    S.IN_WORK: {S.SUBMITTED, S.REFUNDED, S.DISPUTE},
    S.REVISION: {S.SUBMITTED, S.REFUNDED, S.DISPUTE},
    S.SUBMITTED: {S.ACCEPTED, S.REVISION, S.DISPUTE},
    S.DISPUTE: {S.ACCEPTED, S.REFUNDED, S.PARTIALLY_REFUNDED},
}
REVISION_EXTRA_DAYS = 3
ATTACHMENT_MAX = 20 * 1024 * 1024
ATTACHMENT_EXT = {
    "zip", "rar", "7z", "pdf", "txt", "md", "doc", "docx", "xls", "xlsx", "csv", "png", "jpg", "jpeg", "webp", "gif",
    "html", "css", "js", "py", "php", "json", "sql", "patch", "diff",
}  # fmt: skip


def change_order_status(order, new_status, *, note=""):
    """Сменить статус заказа с проверкой перехода и записать системное сообщение в чат."""
    if new_status not in TRANSITIONS.get(order.status, set()):
        raise InvalidTransition(f"Заказ: переход {order.status} → {new_status} недопустим")
    order.status = new_status
    order.save(update_fields=["status"])
    text = f"Статус: {CustomOrder.Status(new_status).label}" + (f". {note}" if note else "")
    Message.objects.create(order=order, author=None, text=text, is_read=True)
    return order


def _is_buyer(order, user):
    return order.buyer_id == user.id


def _is_seller(order, user):
    return order.product.seller_id == user.id


def _require(cond, msg="Действие недоступно"):
    if not cond:
        raise InvalidTransition(msg)


def _other(order, user):
    return order.product.seller if _is_buyer(order, user) else order.buyer


def _link(order):
    return f"/orders/{order.pk}/"


# ---------------------------------------------------------------- чтение


def get_order_for(user, pk):
    """Заказ для страницы: участник или администратор, иначе PermissionError."""
    order = CustomOrder.objects.select_related("product", "product__seller", "buyer", "purchase").get(pk=pk)
    if not (_is_buyer(order, user) or _is_seller(order, user) or user.is_staff):
        raise PermissionError
    return order


def buyer_orders(user):
    return CustomOrder.objects.filter(buyer=user).select_related("product").order_by("-created_at")


def seller_orders(user):
    return CustomOrder.objects.filter(product__seller=user).select_related("product", "buyer").order_by("-created_at")


def orders_for_purchase(purchase):
    return list(CustomOrder.objects.filter(purchase=purchase).order_by("-created_at"))


def public_questions(product, limit=10):
    """Вопросы до покупки и первые ответы продавца (без имён покупателей) для страницы продукта."""
    out = []
    for order in CustomOrder.objects.filter(product=product, kind=K.QUESTION).order_by("-created_at")[:limit]:
        answer = order.messages.filter(author_id=product.seller_id).exclude(text="").order_by("created_at").first()
        out.append({"question": order.task, "answer": answer.text if answer else "", "created_at": order.created_at})
    return out


def includes_product(order):
    """Оплата заказа включает цену продукта: «Купить с доработкой» или вопрос, если продукт ещё не куплен."""
    from apps.purchases.services import active_purchase

    return order.kind in (K.WITH_PURCHASE, K.QUESTION) and active_purchase(order.buyer, order.product) is None


def payment_amount(order):
    amount = Decimal(order.price or 0)
    if includes_product(order):
        amount += order.product.price
    return amount


def allowed_actions(order, user):
    """Действия, доступные пользователю в текущем статусе (для кнопок на странице заказа)."""
    acts = []
    buyer, seller = _is_buyer(order, user), _is_seller(order, user)
    st = order.status
    if seller and st in (S.NEW, S.OFFER):
        acts.append("offer")
    if buyer and st == S.OFFER:
        acts.append("accept_offer")
    if buyer and st == S.AWAITING_PAYMENT:
        acts.append("pay")
    if (buyer or seller) and st in (S.NEW, S.OFFER, S.AWAITING_PAYMENT):
        acts.append("cancel")
    if seller and st in (S.IN_WORK, S.REVISION):
        acts += ["submit", "refuse"]
    if buyer and st == S.SUBMITTED:
        acts.append("accept")
        if order.revisions < settings.MAX_REVISIONS:
            acts.append("revision")
    if buyer and st in (S.IN_WORK, S.REVISION) and order.deadline and timezone.now() > order.deadline:
        acts.append("cancel_overdue")
    if buyer and st in (S.IN_WORK, S.SUBMITTED, S.REVISION) and not order.disputes.exists():
        acts.append("dispute")
    if buyer and st == S.ACCEPTED:
        from apps.reviews.services import review_for_order

        if review_for_order(order) is None:
            acts.append("review")
    return acts


# ---------------------------------------------------------------- создание


def _rate_limited_questions(user):
    since = timezone.now() - timedelta(hours=1)
    return (
        CustomOrder.objects.filter(buyer=user, kind=K.QUESTION, created_at__gte=since).count()
        >= settings.RATE_LIMIT_QUESTIONS_PER_HOUR
    )


@transaction.atomic
def create_order(buyer, product, *, kind, task, purchase=None):
    """Создать заказ (статус new): вопрос, «Купить с доработкой» или доработку купленного продукта."""
    from apps.purchases.services import active_purchase

    task = (task or "").strip()
    if len(task) < 5:
        raise ServiceError("Опишите задачу или вопрос подробнее.")
    if product.status != Product.Status.PUBLISHED or product.seller.is_blocked:
        if not (kind == K.CUSTOMIZATION and purchase):
            raise ServiceError("Продукт сейчас недоступен.")
    if product.seller_id == buyer.id:
        raise ServiceError("Нельзя заказать доработку собственного продукта.")
    if kind == K.CUSTOMIZATION:
        purchase = purchase or active_purchase(buyer, product)
        if (
            purchase is None
            or purchase.buyer_id != buyer.id
            or purchase.status
            not in (
                "paid",
                "completed",
                "partially_refunded",
            )
        ):
            raise ServiceError("Доработку можно заказать только для купленного продукта.")
    elif kind == K.WITH_PURCHASE:
        if active_purchase(buyer, product):
            raise ServiceError("Продукт уже куплен: закажите доработку со страницы покупки.")
    elif kind == K.QUESTION:
        if _rate_limited_questions(buyer):
            raise ServiceError("Слишком много вопросов за час, попробуйте позже.")
    else:
        raise ServiceError("Неизвестный тип заказа.")
    order = CustomOrder.objects.create(buyer=buyer, product=product, purchase=purchase, kind=kind, task=task)
    Message.objects.create(order=order, author=buyer, text=task)
    what = "Новый вопрос" if kind == K.QUESTION else "Новый заказ на доработку"
    notify(product.seller, f"{what} по «{product.title}» от {buyer.username}.", _link(order))
    return order


# ---------------------------------------------------------------- переходы


@transaction.atomic
def make_offer(order, user, *, price, days):
    """Продавец предлагает (или меняет) цену и срок: new/offer → offer."""
    _require(_is_seller(order, user), "Предложение делает продавец")
    try:
        price, days = Decimal(price), int(days)
    except Exception:
        raise ServiceError("Укажите цену и срок числами.")
    if price < ORDER_MIN_PRICE:
        raise ServiceError(f"Цена доработки — от {ORDER_MIN_PRICE} ₽.")
    if not ORDER_MIN_DAYS <= days <= ORDER_MAX_DAYS:
        raise ServiceError(f"Срок — от {ORDER_MIN_DAYS} до {ORDER_MAX_DAYS} дней.")
    changed = order.status == S.OFFER
    order.price, order.days = price, days
    order.save(update_fields=["price", "days"])
    change_order_status(order, S.OFFER, note=f"{price:.0f} ₽, {days} дн.")
    notify(
        order.buyer,
        f"{'Продавец изменил предложение' if changed else 'Предложение по заказу'} №{order.pk}: {price:.0f} ₽, {days} дн.",
        _link(order),
    )
    return order


@transaction.atomic
def accept_offer(order, user):
    """Покупатель согласен: offer → awaiting_payment, создаётся платёж. Возвращает адрес оплаты."""
    from apps.payments.services import create_payment

    _require(_is_buyer(order, user), "Согласиться с предложением может покупатель")
    change_order_status(order, S.AWAITING_PAYMENT)
    amount = payment_amount(order)
    what = "доработка" + (" и продукт" if includes_product(order) else "")
    payment = create_payment(amount=amount, description=f"CodeMarket: {what} «{order.product.title}»", order=order)
    return payment.confirmation_url


def payment_url(order, user):
    """Ссылка на оплату для кнопки «Оплатить» (продолжить созданный платёж или создать новый)."""
    from apps.payments.services import create_payment, pending_payment_for

    _require(_is_buyer(order, user) and order.status == S.AWAITING_PAYMENT)
    payment = pending_payment_for(order=order)
    if payment is None:
        payment = create_payment(
            amount=payment_amount(order), description=f"CodeMarket: доработка «{order.product.title}»", order=order
        )
    return payment.confirmation_url


@transaction.atomic
def on_payment_succeeded(order):
    """Оплата подтверждена: awaiting_payment → in_work, срок отсчитывается с оплаты.

    Для «Купить с доработкой» (и вопроса без покупки) создаётся оплаченная покупка с выдачей доступа.
    """
    from apps.purchases.services import create_paid_purchase_for_order

    order = CustomOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != S.AWAITING_PAYMENT:
        return order
    if includes_product(order):
        order.purchase = create_paid_purchase_for_order(order)
    now = timezone.now()
    order.paid_at = now
    order.deadline = now + timedelta(days=order.days)
    order.save(update_fields=["purchase", "paid_at", "deadline"])
    change_order_status(order, S.IN_WORK, note=f"Крайний срок {timezone.localtime(order.deadline):%d.%m.%Y %H:%M}")
    notify(order.product.seller, f"Заказ №{order.pk} оплачен, можно приступать к работе.", _link(order))
    notify(order.buyer, f"Оплата заказа №{order.pk} прошла, продавец приступает к работе.", _link(order))
    return order


@transaction.atomic
def cancel_order(order, user):
    """Отмена неоплаченного заказа любой стороной: new/offer/awaiting_payment → cancelled."""
    from apps.payments.models import Payment
    from apps.payments.services import cancel_pending

    _require(_is_buyer(order, user) or _is_seller(order, user) or user.is_staff)
    _require(order.status in (S.NEW, S.OFFER, S.AWAITING_PAYMENT), "Оплаченный заказ отменить нельзя")
    change_order_status(order, S.CANCELLED, note=f"Отменил {user.username}")
    for p in Payment.objects.filter(order=order, status=Payment.Status.PENDING):
        cancel_pending(p)
    notify(_other(order, user), f"Заказ №{order.pk} отменён.", _link(order))
    return order


def _refund_order(order, amount, note):
    from apps.payments.services import mark_refund

    mark_refund(amount=amount, order=order)
    return note


@transaction.atomic
def seller_refuse(order, user, reason):
    """Продавец отказывается: in_work/revision → refunded, полный возврат стоимости доработки."""
    _require(_is_seller(order, user), "Отказаться может продавец")
    if not reason or not reason.strip():
        raise ServiceError("Укажите причину отказа.")
    _require(order.status in (S.IN_WORK, S.REVISION))
    change_order_status(order, S.REFUNDED, note=f"Продавец отказался: {reason.strip()}")
    _refund_order(order, order.price, "refuse")
    notify(
        order.buyer, f"Продавец отказался от заказа №{order.pk}. Деньги за доработку будут возвращены.", _link(order)
    )
    return order


def has_new_result(order):
    """Есть ли сообщение-результат после оплаты или последнего возврата на доработку."""
    since = order.paid_at
    last_revision = order.messages.filter(author=None, text__startswith="Статус: На доработке").order_by("-id").first()
    if last_revision:
        since = last_revision.created_at
    qs = order.messages.filter(is_result=True, author_id=order.product.seller_id)
    if since:
        qs = qs.filter(created_at__gte=since)
    return qs.exists()


@transaction.atomic
def submit_result(order, user):
    """Продавец сдаёт работу: in_work/revision → submitted (нужно сообщение с отметкой «Результат»)."""
    _require(_is_seller(order, user), "Сдать работу может продавец")
    _require(order.status in (S.IN_WORK, S.REVISION))
    if not has_new_result(order):
        raise ServiceError("Сначала отправьте сообщение с результатом и отметкой «Результат».")
    order.submitted_at = timezone.now()
    order.save(update_fields=["submitted_at"])
    change_order_status(order, S.SUBMITTED)
    notify(
        order.buyer,
        f"Работа по заказу №{order.pk} сдана. Проверьте результат: через {settings.AUTO_ACCEPT_DAYS} дн. "
        "заказ будет принят автоматически.",
        _link(order),
    )
    return order


def _accept(order, note):
    from apps.balance.services import credit_order

    change_order_status(order, S.ACCEPTED, note=note)
    credit_order(order)


@transaction.atomic
def accept_result(order, user):
    """Покупатель принимает работу: submitted → accepted, продавцу начисляется оплата (сразу available)."""
    _require(_is_buyer(order, user), "Принять работу может покупатель")
    _require(order.status == S.SUBMITTED)
    _accept(order, "Работа принята покупателем")
    notify(order.product.seller, f"Работа по заказу №{order.pk} принята, деньги доступны к выводу.", _link(order))
    return order


@transaction.atomic
def request_revision(order, user, comment):
    """Возврат на доработку: submitted → revision, revisions + 1, срок + 3 дня."""
    _require(_is_buyer(order, user), "Вернуть на доработку может покупатель")
    _require(order.status == S.SUBMITTED)
    if order.revisions >= settings.MAX_REVISIONS:
        raise InvalidTransition(f"Можно вернуть на доработку не больше {settings.MAX_REVISIONS} раз")
    if not comment or not comment.strip():
        raise ServiceError("Напишите, что нужно исправить.")
    Message.objects.create(order=order, author=user, text=f"Замечания: {comment.strip()}")
    order.revisions += 1
    order.deadline = (order.deadline or timezone.now()) + timedelta(days=REVISION_EXTRA_DAYS)
    order.save(update_fields=["revisions", "deadline"])
    change_order_status(order, S.REVISION, note=f"Возврат {order.revisions} из {settings.MAX_REVISIONS}")
    notify(order.product.seller, f"Заказ №{order.pk} возвращён на доработку.", _link(order))
    return order


@transaction.atomic
def cancel_overdue(order, user):
    """Срок прошёл: покупатель отменяет заказ in_work/revision → refunded с полным возвратом."""
    _require(_is_buyer(order, user), "Отменить по сроку может покупатель")
    _require(order.status in (S.IN_WORK, S.REVISION))
    _require(order.deadline and timezone.now() > order.deadline, "Срок ещё не прошёл")
    change_order_status(order, S.REFUNDED, note="Срок выполнения прошёл, заказ отменён покупателем")
    _refund_order(order, order.price, "overdue")
    notify(order.product.seller, f"Заказ №{order.pk} отменён покупателем: срок прошёл.", _link(order))
    return order


def auto_accept(now=None):
    """Автоприёмка: submitted дольше AUTO_ACCEPT_DAYS без спора → accepted (команда auto_accept)."""
    now = now or timezone.now()
    limit = now - timedelta(days=settings.AUTO_ACCEPT_DAYS)
    done = 0
    for order in CustomOrder.objects.filter(status=S.SUBMITTED, submitted_at__lte=limit).select_related("product"):
        with transaction.atomic():
            if order.disputes.exists():
                continue
            _accept(order, f"Принято автоматически: покупатель не ответил за {settings.AUTO_ACCEPT_DAYS} дн.")
            text = f"Заказ №{order.pk} принят автоматически."
            notify(order.buyer, text, _link(order))
            notify(order.product.seller, text + " Деньги доступны к выводу.", _link(order))
            done += 1
    return done


def open_dispute(order):
    """Спор по заказу (вызывает модуль споров): in_work/submitted/revision → dispute, автоприёмка останавливается."""
    return change_order_status(order, S.DISPUTE)


def resolve_dispute(order, *, outcome, refund_amount=0):
    """Решение администратора по спору заказа."""
    from apps.balance.services import credit_order, credit_order_partial

    if outcome == "seller":
        change_order_status(order, S.ACCEPTED, note="Спор решён в пользу продавца")
        credit_order(order)
    elif outcome == "refund":
        change_order_status(order, S.REFUNDED, note="Спор решён: полный возврат")
        _refund_order(order, order.price, "dispute")
    else:
        change_order_status(order, S.PARTIALLY_REFUNDED, note=f"Спор решён: частичный возврат {refund_amount} ₽")
        _refund_order(order, refund_amount, "dispute")
        credit_order_partial(order, refund_amount)
    return order


@transaction.atomic
def handle_seller_blocked(seller, admin=None):
    """Продавца заблокировали: new/offer/awaiting_payment → cancelled, in_work/revision/submitted → dispute."""
    from apps.disputes.services import open_system_dispute

    count = 0
    for order in CustomOrder.objects.filter(product__seller=seller, status__in=[S.NEW, S.OFFER, S.AWAITING_PAYMENT]):
        change_order_status(order, S.CANCELLED, note="Продавец заблокирован")
        notify(order.buyer, f"Заказ №{order.pk} отменён: продавец заблокирован.", _link(order))
        count += 1
    for order in CustomOrder.objects.filter(product__seller=seller, status__in=[S.IN_WORK, S.REVISION, S.SUBMITTED]):
        open_system_dispute(order, admin=admin)
        count += 1
    return count


# ---------------------------------------------------------------- чат


def _rate_limited_messages(user):
    since = timezone.now() - timedelta(hours=1)
    return Message.objects.filter(author=user, created_at__gte=since).count() >= settings.RATE_LIMIT_MESSAGES_PER_HOUR


def validate_attachment(f):
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext not in ATTACHMENT_EXT:
        raise ServiceError("Такой тип файла прикрепить нельзя.")
    if f.size > ATTACHMENT_MAX:
        raise ServiceError("Вложение больше 20 МБ.")


@transaction.atomic
def post_message(order, user, *, text="", attachment=None, is_result=False):
    """Отправить сообщение в чат заказа. Отметить «Результат» может только продавец в работе."""
    _require(_is_buyer(order, user) or _is_seller(order, user), "Писать в чат могут только участники заказа")
    text = (text or "").strip()
    if not text and not attachment:
        raise ServiceError("Пустое сообщение.")
    if order.status == S.CANCELLED:
        raise ServiceError("Заказ отменён, переписка закрыта.")
    if _rate_limited_messages(user):
        raise ServiceError("Слишком много сообщений за час, попробуйте позже.")
    if attachment:
        validate_attachment(attachment)
    if is_result:
        _require(_is_seller(order, user) and order.status in (S.IN_WORK, S.REVISION), "Результат отправляет продавец")
    msg = Message(order=order, author=user, text=text, is_result=is_result)
    if attachment:
        msg.attachment.save(attachment.name, attachment, save=False)
    msg.save()
    if order.kind == K.QUESTION and order.status == S.NEW and _is_seller(order, user):
        notify(order.buyer, f"Продавец ответил на ваш вопрос по «{order.product.title}».", _link(order))
    elif is_result:
        notify(order.buyer, f"Продавец прислал результат по заказу №{order.pk}.", _link(order))
    return msg


def mark_result(order, user, message_id):
    """Продавец отмечает своё сообщение как «Результат»."""
    _require(_is_seller(order, user) and order.status in (S.IN_WORK, S.REVISION), "Отметить результат может продавец")
    msg = order.messages.get(pk=message_id, author=user)
    msg.is_result = True
    msg.save(update_fields=["is_result"])
    return msg


def messages_after(order, user, after_id=0):
    """Новые сообщения для опроса раз в 10 секунд; чужие отмечаются прочитанными."""
    qs = order.messages.filter(pk__gt=after_id).select_related("author")
    msgs = list(qs)
    if not user.is_staff or _is_buyer(order, user) or _is_seller(order, user):
        order.messages.filter(pk__gt=after_id, is_read=False).exclude(author=user).update(is_read=True)
    return msgs


def attachment_for(user, message_id):
    """Вложение сообщения: только участники заказа и администратор."""
    msg = Message.objects.select_related("order", "order__product").get(pk=message_id)
    order = msg.order
    if not (_is_buyer(order, user) or _is_seller(order, user) or user.is_staff) or not msg.attachment:
        raise PermissionError
    return msg

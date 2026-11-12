"""Заказы на доработку и чат. Все переходы — по таблице 7.4 ТЗ.

Недопустимый переход или действие не той стороной вызывает InvalidTransition (409).
Смена статуса пишется в чат системным сообщением — это и есть история статусов заказа.
"""

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import InvalidTransition, NotFound, ServiceError
from app.core.storage import save_private
from app.models import (
    ORDER_MAX_DAYS,
    ORDER_MIN_DAYS,
    ORDER_MIN_PRICE,
    CustomOrder,
    Dispute,
    Message,
    OrderKind,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    ProductStatus,
    User,
)
from app.models.base import utcnow
from app.services.notifications import notify

log = logging.getLogger("codemarket")
S = OrderStatus
K = OrderKind

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


def local_str(dt) -> str:
    return dt.astimezone(ZoneInfo(settings.time_zone)).strftime("%d.%m.%Y %H:%M")


def change_order_status(db: Session, order: CustomOrder, new_status: str, *, note: str = "") -> CustomOrder:
    """Сменить статус заказа с проверкой перехода и записать системное сообщение в чат."""
    if new_status not in TRANSITIONS.get(order.status, set()):
        raise InvalidTransition(f"Заказ: переход {order.status} → {new_status} недопустим")
    order.status = new_status
    text = f"Статус: {S.label(new_status)}" + (f". {note}" if note else "")
    db.add(Message(order_id=order.id, author_id=None, text=text, is_read=True))
    db.flush()
    return order


def _is_buyer(order, user) -> bool:
    return order.buyer_id == user.id


def _is_seller(order, user) -> bool:
    return order.product.seller_id == user.id


def _require(cond, msg="Действие недоступно"):
    if not cond:
        raise InvalidTransition(msg)


def _other(order, user):
    return order.product.seller if _is_buyer(order, user) else order.buyer


def _link(order) -> str:
    return f"/orders/{order.id}/"


def _has_dispute(db: Session, order) -> bool:
    return db.scalar(select(Dispute.id).where(Dispute.order_id == order.id).limit(1)) is not None


# ---------------------------------------------------------------- чтение


def get_order_for(db: Session, user: User, pk: int) -> CustomOrder:
    """Заказ для страницы: участник или администратор, иначе 404."""
    order = db.get(CustomOrder, pk)
    if order is None or not (_is_buyer(order, user) or _is_seller(order, user) or user.is_staff):
        raise NotFound("Заказ не найден")
    return order


def buyer_orders_stmt(user: User):
    return (
        select(CustomOrder)
        .where(CustomOrder.buyer_id == user.id)
        .options(selectinload(CustomOrder.product))
        .order_by(CustomOrder.created_at.desc(), CustomOrder.id.desc())
    )


def seller_orders_stmt(user: User):
    return (
        select(CustomOrder)
        .join(Product, Product.id == CustomOrder.product_id)
        .where(Product.seller_id == user.id)
        .options(selectinload(CustomOrder.product), selectinload(CustomOrder.buyer))
        .order_by(CustomOrder.created_at.desc(), CustomOrder.id.desc())
    )


def orders_for_purchase(db: Session, purchase) -> list[CustomOrder]:
    return list(
        db.scalars(
            select(CustomOrder).where(CustomOrder.purchase_id == purchase.id).order_by(CustomOrder.created_at.desc())
        )
    )


def public_questions(db: Session, product: Product, limit: int = 10) -> list[dict]:
    """Вопросы до покупки и первые ответы продавца (без имён покупателей) для страницы продукта."""
    out = []
    orders = db.scalars(
        select(CustomOrder)
        .where(CustomOrder.product_id == product.id, CustomOrder.kind == K.QUESTION)
        .order_by(CustomOrder.created_at.desc())
        .limit(limit)
    ).all()
    for order in orders:
        answer = db.scalar(
            select(Message)
            .where(Message.order_id == order.id, Message.author_id == product.seller_id, Message.text != "")
            .order_by(Message.created_at, Message.id)
            .limit(1)
        )
        out.append({"question": order.task, "answer": answer.text if answer else "", "created_at": order.created_at})
    return out


def includes_product(db: Session, order: CustomOrder) -> bool:
    """Оплата заказа включает цену продукта: «Купить с доработкой» или вопрос, если продукт ещё не куплен."""
    from app.services.purchases import active_purchase

    return order.kind in (K.WITH_PURCHASE, K.QUESTION) and active_purchase(db, order.buyer, order.product) is None


def payment_amount(db: Session, order: CustomOrder) -> Decimal:
    amount = Decimal(order.price or 0)
    if includes_product(db, order):
        amount += order.product.price
    return amount


def allowed_actions(db: Session, order: CustomOrder, user: User) -> list[str]:
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
        if order.revisions < settings.max_revisions:
            acts.append("revision")
    if buyer and st in (S.IN_WORK, S.REVISION) and order.deadline and utcnow() > order.deadline:
        acts.append("cancel_overdue")
    if buyer and st in (S.IN_WORK, S.SUBMITTED, S.REVISION) and not _has_dispute(db, order):
        acts.append("dispute")
    if buyer and st == S.ACCEPTED:
        from app.services.reviews import review_for_order

        if review_for_order(db, order) is None:
            acts.append("review")
    return acts


# ---------------------------------------------------------------- создание


def _rate_limited_questions(db: Session, user: User) -> bool:
    since = utcnow() - timedelta(hours=1)
    n = db.scalar(
        select(func.count()).where(
            CustomOrder.buyer_id == user.id, CustomOrder.kind == K.QUESTION, CustomOrder.created_at >= since
        )
    )
    return (n or 0) >= settings.rate_limit_questions_per_hour


def create_order(db: Session, buyer: User, product: Product, *, kind: str, task: str, purchase=None) -> CustomOrder:
    """Создать заказ (статус new): вопрос, «Купить с доработкой» или доработку купленного продукта."""
    from app.services.purchases import active_purchase

    task = (task or "").strip()
    if len(task) < 5:
        raise ServiceError("Опишите задачу или вопрос подробнее.")
    unavailable = product.status != ProductStatus.PUBLISHED or product.seller.is_blocked
    if unavailable and not (kind == K.CUSTOMIZATION and purchase):
        raise ServiceError("Продукт сейчас недоступен.")
    if product.seller_id == buyer.id:
        raise ServiceError("Нельзя заказать доработку собственного продукта.")
    if kind == K.CUSTOMIZATION:
        purchase = purchase or active_purchase(db, buyer, product)
        if (
            purchase is None
            or purchase.buyer_id != buyer.id
            or purchase.product_id != product.id
            or purchase.status not in ("paid", "completed", "partially_refunded")
        ):
            raise ServiceError("Доработку можно заказать только для купленного продукта.")
    elif kind == K.WITH_PURCHASE:
        if active_purchase(db, buyer, product):
            raise ServiceError("Продукт уже куплен: закажите доработку со страницы покупки.")
    elif kind == K.QUESTION:
        if _rate_limited_questions(db, buyer):
            raise ServiceError("Слишком много вопросов за час, попробуйте позже.")
    else:
        raise ServiceError("Неизвестный тип заказа.")
    order = CustomOrder(
        buyer_id=buyer.id, product_id=product.id, purchase_id=purchase.id if purchase else None, kind=kind, task=task
    )
    db.add(order)
    db.flush()
    db.add(Message(order_id=order.id, author_id=buyer.id, text=task))
    db.flush()
    what = "Новый вопрос" if kind == K.QUESTION else "Новый заказ на доработку"
    notify(db, product.seller, f"{what} по «{product.title}» от {buyer.username}.", _link(order))
    return order


# ---------------------------------------------------------------- переходы


def make_offer(db: Session, order: CustomOrder, user: User, *, price, days) -> CustomOrder:
    """Продавец предлагает (или меняет) цену и срок: new/offer → offer."""
    _require(_is_seller(order, user), "Предложение делает продавец")
    try:
        price, days = Decimal(str(price).replace(",", ".").replace(" ", "")), int(days)
    except (InvalidOperation, TypeError, ValueError):
        raise ServiceError("Укажите цену и срок числами.")
    if price < ORDER_MIN_PRICE:
        raise ServiceError(f"Цена доработки — от {ORDER_MIN_PRICE} ₽.")
    if not ORDER_MIN_DAYS <= days <= ORDER_MAX_DAYS:
        raise ServiceError(f"Срок — от {ORDER_MIN_DAYS} до {ORDER_MAX_DAYS} дней.")
    _require(order.status in (S.NEW, S.OFFER))
    changed = order.status == S.OFFER
    order.price, order.days = price, days
    change_order_status(db, order, S.OFFER, note=f"{price:.0f} ₽, {days} дн.")
    notify(
        db,
        order.buyer,
        f"{'Продавец изменил предложение' if changed else 'Предложение по заказу'} №{order.id}: {price:.0f} ₽, {days} дн.",
        _link(order),
    )
    return order


def _check_product_on_sale(db: Session, order: CustomOrder) -> None:
    """Если оплата включает продукт, он должен продаваться прямо сейчас."""
    product = order.product
    if includes_product(db, order) and (product.status != ProductStatus.PUBLISHED or product.seller.is_blocked):
        raise ServiceError("Продукт сейчас не продаётся, оплатить его вместе с доработкой нельзя.")


def accept_offer(db: Session, order: CustomOrder, user: User) -> str:
    """Покупатель согласен: offer → awaiting_payment, создаётся платёж. Возвращает адрес оплаты."""
    from app.services.payments import create_payment

    _require(_is_buyer(order, user), "Согласиться с предложением может покупатель")
    _check_product_on_sale(db, order)
    change_order_status(db, order, S.AWAITING_PAYMENT)
    amount = payment_amount(db, order)
    what = "доработка" + (" и продукт" if includes_product(db, order) else "")
    payment = create_payment(db, amount=amount, description=f"CodeMarket: {what} «{order.product.title}»", order=order)
    return payment.confirmation_url


def payment_url(db: Session, order: CustomOrder, user: User) -> str:
    """Ссылка на оплату для кнопки «Оплатить» (продолжить созданный платёж или создать новый)."""
    from app.services.payments import cancel_pending, create_payment, pending_payment_for

    _require(_is_buyer(order, user) and order.status == S.AWAITING_PAYMENT)
    payment = pending_payment_for(db, order=order)
    if payment is not None and payment.amount != payment_amount(db, order):
        # цена продукта изменилась или продукт куплен отдельно — старый платёж больше не подходит
        cancel_pending(db, payment)
        payment = None
    if payment is None:
        _check_product_on_sale(db, order)
        payment = create_payment(
            db,
            amount=payment_amount(db, order),
            description=f"CodeMarket: доработка «{order.product.title}»",
            order=order,
        )
    return payment.confirmation_url


def on_payment_succeeded(db: Session, order: CustomOrder, payment: Payment | None = None) -> CustomOrder:
    """Оплата подтверждена: awaiting_payment → in_work, срок отсчитывается с оплаты.

    Если платёж включал цену продукта («Купить с доработкой» или вопрос без покупки), создаётся
    оплаченная покупка с выдачей доступа; цена покупки — фактически оплаченная доля продукта.
    """
    from app.services.payments import _alert_admins
    from app.services.purchases import active_purchase, create_paid_purchase_for_order

    db.refresh(order, with_for_update=True)
    if order.status != S.AWAITING_PAYMENT:
        _alert_admins(
            db,
            f"Оплачен заказ №{order.id} в статусе «{S.label(order.status)}»: верните деньги покупателю в кабинете ЮKassa.",
        )
        return order
    paid = Decimal(payment.amount) if payment is not None else payment_amount(db, order)
    product_part = paid - Decimal(order.price or 0)
    if product_part > 0:
        if active_purchase(db, order.buyer, order.product):
            _alert_admins(
                db, f"Продукт по заказу №{order.id} уже был куплен отдельно: верните покупателю {product_part:.2f} ₽."
            )
        else:
            order.purchase_id = create_paid_purchase_for_order(db, order, price=product_part).id
    now = utcnow()
    order.paid_at = now
    order.deadline = now + timedelta(days=order.days)
    db.flush()
    change_order_status(db, order, S.IN_WORK, note=f"Крайний срок {local_str(order.deadline)}")
    notify(db, order.product.seller, f"Заказ №{order.id} оплачен, можно приступать к работе.", _link(order))
    notify(db, order.buyer, f"Оплата заказа №{order.id} прошла, продавец приступает к работе.", _link(order))
    return order


def _cancel_pending_payments(db: Session, order: CustomOrder) -> None:
    from app.services.payments import cancel_pending

    for p in db.scalars(select(Payment).where(Payment.order_id == order.id, Payment.status == PaymentStatus.PENDING)):
        cancel_pending(db, p)


def cancel_order(db: Session, order: CustomOrder, user: User) -> CustomOrder:
    """Отмена неоплаченного заказа любой стороной: new/offer/awaiting_payment → cancelled."""
    _require(_is_buyer(order, user) or _is_seller(order, user) or user.is_staff)
    _require(order.status in (S.NEW, S.OFFER, S.AWAITING_PAYMENT), "Оплаченный заказ отменить нельзя")
    change_order_status(db, order, S.CANCELLED, note=f"Отменил {user.username}")
    _cancel_pending_payments(db, order)
    notify(db, _other(order, user), f"Заказ №{order.id} отменён.", _link(order))
    return order


def _refund_order(db: Session, order: CustomOrder, amount) -> None:
    from app.services.payments import mark_refund

    mark_refund(db, amount=amount, order=order)


def seller_refuse(db: Session, order: CustomOrder, user: User, reason: str) -> CustomOrder:
    """Продавец отказывается: in_work/revision → refunded, полный возврат стоимости доработки."""
    _require(_is_seller(order, user), "Отказаться может продавец")
    if not reason or not reason.strip():
        raise ServiceError("Укажите причину отказа.")
    _require(order.status in (S.IN_WORK, S.REVISION))
    change_order_status(db, order, S.REFUNDED, note=f"Продавец отказался: {reason.strip()}")
    _refund_order(db, order, order.price)
    notify(
        db,
        order.buyer,
        f"Продавец отказался от заказа №{order.id}. Деньги за доработку будут возвращены.",
        _link(order),
    )
    return order


def has_new_result(db: Session, order: CustomOrder) -> bool:
    """Есть ли сообщение-результат после оплаты или последнего возврата на доработку."""
    since = order.paid_at
    last_revision = db.scalar(
        select(Message)
        .where(
            Message.order_id == order.id, Message.author_id.is_(None), Message.text.startswith("Статус: На доработке")
        )
        .order_by(Message.id.desc())
        .limit(1)
    )
    if last_revision:
        since = last_revision.created_at
    stmt = select(Message.id).where(
        Message.order_id == order.id, Message.is_result.is_(True), Message.author_id == order.product.seller_id
    )
    if since:
        stmt = stmt.where(Message.created_at >= since)
    return db.scalar(stmt.limit(1)) is not None


def submit_result(db: Session, order: CustomOrder, user: User) -> CustomOrder:
    """Продавец сдаёт работу: in_work/revision → submitted (нужно сообщение с отметкой «Результат»)."""
    _require(_is_seller(order, user), "Сдать работу может продавец")
    _require(order.status in (S.IN_WORK, S.REVISION))
    if not has_new_result(db, order):
        raise ServiceError("Сначала отправьте сообщение с результатом и отметкой «Результат».")
    order.submitted_at = utcnow()
    change_order_status(db, order, S.SUBMITTED)
    notify(
        db,
        order.buyer,
        f"Работа по заказу №{order.id} сдана. Проверьте результат: через {settings.auto_accept_days} дн. "
        "заказ будет принят автоматически.",
        _link(order),
    )
    return order


def _accept(db: Session, order: CustomOrder, note: str) -> None:
    from app.services.balance import credit_order

    change_order_status(db, order, S.ACCEPTED, note=note)
    credit_order(db, order)


def accept_result(db: Session, order: CustomOrder, user: User) -> CustomOrder:
    """Покупатель принимает работу: submitted → accepted, продавцу начисляется оплата (сразу available)."""
    _require(_is_buyer(order, user), "Принять работу может покупатель")
    _require(order.status == S.SUBMITTED)
    _accept(db, order, "Работа принята покупателем")
    notify(db, order.product.seller, f"Работа по заказу №{order.id} принята, деньги доступны к выводу.", _link(order))
    return order


def request_revision(db: Session, order: CustomOrder, user: User, comment: str) -> CustomOrder:
    """Возврат на доработку: submitted → revision, revisions + 1, срок + 3 дня."""
    _require(_is_buyer(order, user), "Вернуть на доработку может покупатель")
    _require(order.status == S.SUBMITTED)
    if order.revisions >= settings.max_revisions:
        raise InvalidTransition(f"Можно вернуть на доработку не больше {settings.max_revisions} раз")
    if not comment or not comment.strip():
        raise ServiceError("Напишите, что нужно исправить.")
    db.add(Message(order_id=order.id, author_id=user.id, text=f"Замечания: {comment.strip()}"))
    order.revisions += 1
    order.deadline = (order.deadline or utcnow()) + timedelta(days=REVISION_EXTRA_DAYS)
    db.flush()
    change_order_status(db, order, S.REVISION, note=f"Возврат {order.revisions} из {settings.max_revisions}")
    notify(db, order.product.seller, f"Заказ №{order.id} возвращён на доработку.", _link(order))
    return order


def cancel_overdue(db: Session, order: CustomOrder, user: User) -> CustomOrder:
    """Срок прошёл: покупатель отменяет заказ in_work/revision → refunded с полным возвратом."""
    _require(_is_buyer(order, user), "Отменить по сроку может покупатель")
    _require(order.status in (S.IN_WORK, S.REVISION))
    _require(order.deadline is not None and utcnow() > order.deadline, "Срок ещё не прошёл")
    change_order_status(db, order, S.REFUNDED, note="Срок выполнения прошёл, заказ отменён покупателем")
    _refund_order(db, order, order.price)
    notify(db, order.product.seller, f"Заказ №{order.id} отменён покупателем: срок прошёл.", _link(order))
    return order


def auto_accept(db: Session, now=None) -> int:
    """Автоприёмка: submitted дольше AUTO_ACCEPT_DAYS без спора → accepted (задача планировщика)."""
    now = now or utcnow()
    limit = now - timedelta(days=settings.auto_accept_days)
    done = 0
    for order in db.scalars(
        select(CustomOrder).where(CustomOrder.status == S.SUBMITTED, CustomOrder.submitted_at <= limit)
    ).all():
        if _has_dispute(db, order):
            continue
        _accept(db, order, f"Принято автоматически: покупатель не ответил за {settings.auto_accept_days} дн.")
        text = f"Заказ №{order.id} принят автоматически."
        notify(db, order.buyer, text, _link(order))
        notify(db, order.product.seller, text + " Деньги доступны к выводу.", _link(order))
        done += 1
    return done


def open_dispute(db: Session, order: CustomOrder) -> CustomOrder:
    """Спор по заказу (вызывает модуль споров): in_work/submitted/revision → dispute, автоприёмка останавливается."""
    return change_order_status(db, order, S.DISPUTE)


def resolve_dispute(db: Session, order: CustomOrder, *, outcome: str, refund_amount=Decimal("0")) -> CustomOrder:
    """Решение администратора по спору заказа."""
    from app.services.balance import credit_order, credit_order_partial

    if outcome == "seller":
        change_order_status(db, order, S.ACCEPTED, note="Спор решён в пользу продавца")
        credit_order(db, order)
    elif outcome == "refund":
        change_order_status(db, order, S.REFUNDED, note="Спор решён: полный возврат")
        _refund_order(db, order, order.price)
    else:
        change_order_status(db, order, S.PARTIALLY_REFUNDED, note=f"Спор решён: частичный возврат {refund_amount} ₽")
        _refund_order(db, order, refund_amount)
        credit_order_partial(db, order, refund_amount)
    return order


def handle_seller_blocked(db: Session, seller: User, admin: User | None = None) -> int:
    """Пользователя заблокировали: неоплаченные заказы отменяются, оплаченные (он продавец) — в спор."""
    from app.services.disputes import open_system_dispute

    count = 0
    unpaid = [S.NEW, S.OFFER, S.AWAITING_PAYMENT]
    seller_orders = select(CustomOrder).join(Product, Product.id == CustomOrder.product_id)
    for order in db.scalars(seller_orders.where(Product.seller_id == seller.id, CustomOrder.status.in_(unpaid))).all():
        change_order_status(db, order, S.CANCELLED, note="Продавец заблокирован")
        _cancel_pending_payments(db, order)
        notify(db, order.buyer, f"Заказ №{order.id} отменён: продавец заблокирован.", _link(order))
        count += 1
    # заблокированный покупатель не сможет оплатить свои неоплаченные заказы
    for order in db.scalars(
        select(CustomOrder).where(CustomOrder.buyer_id == seller.id, CustomOrder.status.in_(unpaid))
    ).all():
        change_order_status(db, order, S.CANCELLED, note="Покупатель заблокирован")
        _cancel_pending_payments(db, order)
        notify(db, order.product.seller, f"Заказ №{order.id} отменён: покупатель заблокирован.", _link(order))
        count += 1
    paid = [S.IN_WORK, S.REVISION, S.SUBMITTED]
    for order in db.scalars(seller_orders.where(Product.seller_id == seller.id, CustomOrder.status.in_(paid))).all():
        open_system_dispute(db, order, admin=admin)
        count += 1
    return count


# ---------------------------------------------------------------- чат


def _rate_limited_messages(db: Session, user: User) -> bool:
    since = utcnow() - timedelta(hours=1)
    n = db.scalar(select(func.count()).where(Message.author_id == user.id, Message.created_at >= since))
    return (n or 0) >= settings.rate_limit_messages_per_hour


def validate_attachment(filename: str, size: int) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ATTACHMENT_EXT:
        raise ServiceError("Такой тип файла прикрепить нельзя.")
    if size > ATTACHMENT_MAX:
        raise ServiceError("Вложение больше 20 МБ.")


def post_message(
    db: Session, order: CustomOrder, user: User, *, text: str = "", attachment=None, is_result: bool = False
) -> Message:
    """Отправить сообщение в чат заказа. attachment — (имя файла, байты). Результат отмечает продавец в работе."""
    _require(_is_buyer(order, user) or _is_seller(order, user), "Писать в чат могут только участники заказа")
    text = (text or "").strip()
    if not text and not attachment:
        raise ServiceError("Пустое сообщение.")
    if order.status == S.CANCELLED:
        raise ServiceError("Заказ отменён, переписка закрыта.")
    if _rate_limited_messages(db, user):
        raise ServiceError("Слишком много сообщений за час, попробуйте позже.")
    if attachment:
        validate_attachment(attachment[0], len(attachment[1]))
    if is_result:
        _require(_is_seller(order, user) and order.status in (S.IN_WORK, S.REVISION), "Результат отправляет продавец")
    msg = Message(order_id=order.id, author_id=user.id, text=text, is_result=is_result)
    if attachment:
        msg.attachment = save_private(f"attachments/{order.id}", attachment[0], attachment[1])
    db.add(msg)
    db.flush()
    if order.kind == K.QUESTION and order.status == S.NEW and _is_seller(order, user):
        notify(db, order.buyer, f"Продавец ответил на ваш вопрос по «{order.product.title}».", _link(order))
    elif is_result:
        notify(db, order.buyer, f"Продавец прислал результат по заказу №{order.id}.", _link(order))
    return msg


def mark_result(db: Session, order: CustomOrder, user: User, message_id: int) -> Message:
    """Продавец отмечает своё сообщение как «Результат»."""
    _require(_is_seller(order, user) and order.status in (S.IN_WORK, S.REVISION), "Отметить результат может продавец")
    msg = db.get(Message, message_id)
    if msg is None or msg.order_id != order.id or msg.author_id != user.id:
        raise NotFound("Сообщение не найдено")
    msg.is_result = True
    db.flush()
    return msg


def messages_after(db: Session, order: CustomOrder, user: User, after_id: int = 0) -> list[Message]:
    """Новые сообщения для опроса раз в 10 секунд; чужие отмечаются прочитанными."""
    msgs = db.scalars(
        select(Message)
        .where(Message.order_id == order.id, Message.id > after_id)
        .options(selectinload(Message.author))
        .order_by(Message.created_at, Message.id)
    ).all()
    if not user.is_staff or _is_buyer(order, user) or _is_seller(order, user):
        db.execute(
            update(Message)
            .where(
                Message.order_id == order.id,
                Message.id > after_id,
                Message.is_read.is_(False),
                (Message.author_id != user.id) | Message.author_id.is_(None),
            )
            .values(is_read=True)
        )
    return list(msgs)


def attachment_for(db: Session, user: User, message_id: int) -> Message:
    """Вложение сообщения: только участники заказа и администратор, иначе 404."""
    msg = db.get(Message, message_id)
    if msg is None or not msg.attachment:
        raise NotFound("Файл не найден")
    order = msg.order
    if not (_is_buyer(order, user) or _is_seller(order, user) or user.is_staff):
        raise NotFound("Файл не найден")
    return msg

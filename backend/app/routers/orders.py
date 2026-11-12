"""Заказы на доработку и вопросы: создание, страница заказа, действия по таблице 7.4, чат с вложениями."""

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.core.storage import private_path
from app.models import CustomOrder, Dispute, Message, OrderKind, OrderStatus, Product, Purchase
from app.models.base import utcnow
from app.schemas.common import Ok, Page
from app.schemas.convert import dispute_short, message_out, order_row, product_ref
from app.schemas.trade import (
    DisputeIn,
    MessagesPoll,
    OfferIn,
    OrderCreateIn,
    OrderDetail,
    OrderNewInfo,
    OrderRow,
    PayUrl,
    ReasonIn,
    RevisionIn,
    StepOut,
)
from app.services import catalog as catalog_services
from app.services import disputes as dispute_services
from app.services import orders as svc

router = APIRouter(prefix="/api", tags=["заказы"])

STEPS = [
    ("new", "Новый"),
    ("offer", "Предложение"),
    ("awaiting_payment", "Оплата"),
    ("in_work", "В работе"),
    ("submitted", "Сдан"),
    ("accepted", "Принят"),
]
STEP_INDEX = {"new": 0, "offer": 1, "awaiting_payment": 2, "in_work": 3, "revision": 3, "submitted": 4, "accepted": 5}


def _target(db, user, product_slug: str, kind: str, purchase_id: int | None):
    """Продукт, тип заказа и покупка для формы создания (как ?product=&kind= / ?purchase= в Django-версии)."""
    purchase = None
    if purchase_id:
        purchase = db.get(Purchase, purchase_id)
        if purchase is None or purchase.buyer_id != user.id:
            raise NotFound("Покупка не найдена")
        return purchase.product, OrderKind.CUSTOMIZATION, purchase
    product = db.scalar(select(Product).where(Product.slug == product_slug))
    if product is None:
        raise NotFound("Продукт не найден")
    if kind not in (OrderKind.QUESTION, OrderKind.WITH_PURCHASE):
        kind = OrderKind.QUESTION
    return product, kind, None


@router.get("/orders/new", response_model=OrderNewInfo)
def new_info(db: DB, user: CurrentUser, product: str = "", kind: str = "question", purchase: int | None = None):
    product_obj, kind, purchase_obj = _target(db, user, product, kind, purchase)
    return OrderNewInfo(
        product=product_ref(product_obj),
        kind=kind,
        kind_label=OrderKind.label(kind),
        purchase_id=purchase_obj.id if purchase_obj else None,
        is_owner=product_obj.seller_id == user.id,
    )


@router.post("/orders", response_model=OrderRow, status_code=201)
def create(data: OrderCreateIn, db: DB, user: CurrentUser):
    """«Задать вопрос», «Купить с доработкой» (со страницы продукта) или «Заказать доработку» (со страницы покупки)."""
    product, kind, purchase = _target(db, user, data.product_slug, data.kind, data.purchase_id)
    order = svc.create_order(db, user, product, kind=kind, task=data.task, purchase=purchase)
    db.commit()
    return order_row(order)


def _unread(db, order_ids, user) -> dict[int, int]:
    if not order_ids:
        return {}
    rows = db.execute(
        select(Message.order_id, func.count())
        .where(
            Message.order_id.in_(order_ids),
            Message.is_read.is_(False),
            Message.author_id.is_not(None),
            Message.author_id != user.id,
        )
        .group_by(Message.order_id)
    ).all()
    return dict(rows)


@router.get("/orders", response_model=Page[OrderRow])
def buyer_list(db: DB, user: CurrentUser, page: int = 1, page_size: int = 20):
    """Заказы и вопросы покупателя."""
    items, total, page, pages = catalog_services.paginate(db, svc.buyer_orders_stmt(user), page, page_size)
    unread = _unread(db, [o.id for o in items], user)
    return Page(items=[order_row(o, unread.get(o.id, 0)) for o in items], total=total, page=page, pages=pages)


@router.get("/seller/orders", response_model=Page[OrderRow])
def seller_list(db: DB, user: CurrentUser, kind: str = "", page: int = 1, page_size: int = 20):
    """Заказы и вопросы по продуктам продавца (kind=question — только вопросы, kind=orders — только заказы)."""
    stmt = svc.seller_orders_stmt(user)
    if kind == "question":
        stmt = stmt.where(CustomOrder.kind == OrderKind.QUESTION)
    elif kind == "orders":
        stmt = stmt.where(CustomOrder.kind != OrderKind.QUESTION)
    items, total, page, pages = catalog_services.paginate(db, stmt, page, page_size)
    unread = _unread(db, [o.id for o in items], user)
    return Page(items=[order_row(o, unread.get(o.id, 0)) for o in items], total=total, page=page, pages=pages)


@router.get("/orders/{pk}", response_model=OrderDetail)
def detail(pk: int, db: DB, user: CurrentUser):
    """Страница заказа: условия, шаги, обратный отсчёт, кнопки по статусу, чат."""
    order = svc.get_order_for(db, user, pk)
    msgs = svc.messages_after(db, order, user, 0)
    db.commit()
    is_seller = order.product.seller_id == user.id
    is_buyer = order.buyer_id == user.id
    step = STEP_INDEX.get(order.status)
    left = None
    if order.deadline and order.status in ("in_work", "revision"):
        left = int((order.deadline - utcnow()).total_seconds())
    dispute = db.scalar(select(Dispute).where(Dispute.order_id == order.id))
    return OrderDetail(
        id=order.id,
        kind=order.kind,
        kind_label=OrderKind.label(order.kind),
        task=order.task,
        status=order.status,
        status_label=OrderStatus.label(order.status),
        price=order.price,
        days=order.days,
        deadline=order.deadline,
        revisions=order.revisions,
        max_revisions=settings.max_revisions,
        created_at=order.created_at,
        paid_at=order.paid_at,
        submitted_at=order.submitted_at,
        product=product_ref(order.product),
        buyer=order.buyer.username,
        seller=order.product.seller.username,
        purchase_id=order.purchase_id,
        is_buyer=is_buyer,
        is_seller=is_seller,
        actions=svc.allowed_actions(db, order, user),
        steps=[
            StepOut(code=c, label=label, done=step is not None and i < step, current=i == step)
            for i, (c, label) in enumerate(STEPS)
        ],
        payment_amount=svc.payment_amount(db, order) if order.price else None,
        includes_product=svc.includes_product(db, order),
        deadline_left_seconds=left,
        overdue=left is not None and left < 0,
        can_write=(is_buyer or is_seller) and order.status != "cancelled",
        can_mark_result=is_seller and order.status in ("in_work", "revision"),
        dispute=dispute_short(dispute),
        auto_accept_days=settings.auto_accept_days,
        messages=[message_out(m, user) for m in msgs],
        last_id=msgs[-1].id if msgs else 0,
    )


@router.get("/orders/{pk}/messages", response_model=MessagesPoll)
def poll(pk: int, db: DB, user: CurrentUser, after: int = 0):
    """Опрос раз в 10 секунд: новые сообщения после after."""
    order = svc.get_order_for(db, user, pk)
    msgs = svc.messages_after(db, order, user, after)
    db.commit()
    return MessagesPoll(
        messages=[message_out(m, user) for m in msgs], last_id=msgs[-1].id if msgs else after, status=order.status
    )


@router.post("/orders/{pk}/messages", response_model=MessagesPoll, status_code=201)
def send_message(
    pk: int,
    db: DB,
    user: CurrentUser,
    text: str = Form(""),
    is_result: bool = Form(False),
    after: int = Form(0),
    attachment: UploadFile | None = File(None),
):
    """Сообщение в чат (текст и/или файл до 20 МБ). Отметку «Результат» ставит продавец в работе."""
    order = svc.get_order_for(db, user, pk)
    file = None
    if attachment is not None and attachment.filename:
        file = (attachment.filename, attachment.file.read())
    svc.post_message(db, order, user, text=text, attachment=file, is_result=is_result)
    db.commit()
    return poll(pk, db, user, after)


@router.post("/orders/{pk}/messages/{mid}/result", response_model=Ok)
def mark_result(pk: int, mid: int, db: DB, user: CurrentUser):
    svc.mark_result(db, svc.get_order_for(db, user, pk), user, mid)
    db.commit()
    return Ok(message="Сообщение отмечено как результат.")


@router.get("/orders/attachments/{mid}")
def attachment(mid: int, db: DB, user: CurrentUser):
    """Скачать вложение: только участники заказа и администратор (иначе 404)."""
    msg = svc.attachment_for(db, user, mid)
    return FileResponse(private_path(msg.attachment), filename=msg.attachment_name)


# ---------------------------------------------------------------- действия (таблица 7.4)


def _act(pk, db, user, fn, message, *args, **kwargs):
    order = svc.get_order_for(db, user, pk)
    fn(db, order, user, *args, **kwargs)
    db.commit()
    return Ok(message=message)


@router.post("/orders/{pk}/offer", response_model=Ok)
def offer(pk: int, data: OfferIn, db: DB, user: CurrentUser):
    return _act(pk, db, user, svc.make_offer, "Предложение отправлено покупателю.", price=data.price, days=data.days)


@router.post("/orders/{pk}/accept-offer", response_model=PayUrl)
def accept_offer(pk: int, db: DB, user: CurrentUser):
    url = svc.accept_offer(db, svc.get_order_for(db, user, pk), user)
    db.commit()
    return PayUrl(url=url)


@router.post("/orders/{pk}/pay", response_model=PayUrl)
def pay(pk: int, db: DB, user: CurrentUser):
    url = svc.payment_url(db, svc.get_order_for(db, user, pk), user)
    db.commit()
    return PayUrl(url=url)


@router.post("/orders/{pk}/cancel", response_model=Ok)
def cancel(pk: int, db: DB, user: CurrentUser):
    return _act(pk, db, user, svc.cancel_order, "Заказ отменён.")


@router.post("/orders/{pk}/submit", response_model=Ok)
def submit(pk: int, db: DB, user: CurrentUser):
    return _act(pk, db, user, svc.submit_result, "Работа сдана покупателю.")


@router.post("/orders/{pk}/refuse", response_model=Ok)
def refuse(pk: int, data: ReasonIn, db: DB, user: CurrentUser):
    return _act(
        pk, db, user, svc.seller_refuse, "Вы отказались от заказа, покупателю будет возвращена оплата.", data.reason
    )


@router.post("/orders/{pk}/accept", response_model=Ok)
def accept(pk: int, db: DB, user: CurrentUser):
    return _act(pk, db, user, svc.accept_result, "Работа принята. Спасибо!")


@router.post("/orders/{pk}/revision", response_model=Ok)
def revision(pk: int, data: RevisionIn, db: DB, user: CurrentUser):
    return _act(pk, db, user, svc.request_revision, "Заказ возвращён на доработку.", data.comment)


@router.post("/orders/{pk}/cancel-overdue", response_model=Ok)
def cancel_overdue(pk: int, db: DB, user: CurrentUser):
    return _act(pk, db, user, svc.cancel_overdue, "Заказ отменён, оплата будет возвращена.")


@router.post("/orders/{pk}/dispute", response_model=Ok)
def dispute(pk: int, data: DisputeIn, db: DB, user: CurrentUser):
    order = svc.get_order_for(db, user, pk)
    dispute_services.open_order_dispute(db, user, order, reason_type=data.reason_type, reason=data.reason)
    db.commit()
    return Ok(message="Спор открыт. Администратор рассмотрит его и сообщит решение.")

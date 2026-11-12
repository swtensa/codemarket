"""Заказ на доработку: все переходы таблицы 7.4 (включая недопустимые), чат и права, «Купить с доработкой»,
автоприёмка, блокировка продавца."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.errors import InvalidTransition, ServiceError
from app.integrations.payments import FakeProvider
from app.models import BalanceOperation, CustomOrder, Dispute, Message, Notification, Payment, Purchase
from app.models.base import utcnow
from app.services import catalog as catalog_services
from app.services import orders as svc
from app.services.balance import get_balance
from app.services.payments import handle_notification
from app.tasks import check_deadlines
from tests.factories import make_admin, make_product, make_user
from tests.helpers import make_published


@pytest.fixture
def product(db):
    p = make_product(db, price=Decimal("1000"))
    make_published(db, p, {"a.py": "x = 1\n"})
    return p


@pytest.fixture
def seller(product):
    return product.seller


@pytest.fixture
def buyer(db):
    return make_user(db, github_login="buyer1")


def notified(db, user, text) -> bool:
    return bool(
        db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.text.contains(text)))
    )


def paid_purchase(db, buyer, product):
    p = Purchase(
        buyer_id=buyer.id, product_id=product.id, price=product.price, commission=100, status="paid", paid_at=utcnow()
    )
    db.add(p)
    db.flush()
    return p


def confirm_payment(db, order):
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()))
    FakeProvider().set_status(payment.external_id, "succeeded")
    handle_notification(db, payment.external_id)
    db.refresh(order)
    return payment


def customization(db, buyer, product):
    purchase = paid_purchase(db, buyer, product)
    return svc.create_order(db, buyer, product, kind="customization", task="Добавить форму", purchase=purchase)


def in_work_order(db, buyer, seller, product, price=3000, days=5):
    order = customization(db, buyer, product)
    svc.make_offer(db, order, seller, price=price, days=days)
    svc.accept_offer(db, order, buyer)
    confirm_payment(db, order)
    assert order.status == "in_work"
    return order


def submit(db, order, seller):
    svc.post_message(db, order, seller, text="Готово, см. архив", is_result=True)
    return svc.submit_result(db, order, seller)


# ------------------------------------------------------------- создание


def test_create_question_notifies_seller(db, product, seller, buyer):
    order = svc.create_order(db, buyer, product, kind="question", task="Подойдёт для WordPress?")
    assert order.status == "new" and order.kind == "question"
    assert notified(db, seller, "Новый вопрос")
    assert [m.text for m in order.messages] == ["Подойдёт для WordPress?"]


def test_create_customization_requires_purchase(db, product, buyer):
    with pytest.raises(ServiceError):
        svc.create_order(db, buyer, product, kind="customization", task="Доработать")


def test_seller_cannot_order_own_product(db, product, seller):
    with pytest.raises(ServiceError):
        svc.create_order(db, seller, product, kind="question", task="Вопрос себе")


def test_unpublished_product_cannot_be_ordered(db, buyer):
    with pytest.raises(ServiceError):
        svc.create_order(db, buyer, make_product(db, status="hidden"), kind="with_purchase", task="Хочу доработку")


def test_questions_rate_limit(db, product, buyer, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_questions_per_hour", 2)
    svc.create_order(db, buyer, product, kind="question", task="Вопрос 1")
    svc.create_order(db, buyer, product, kind="question", task="Вопрос 2")
    with pytest.raises(ServiceError):
        svc.create_order(db, buyer, product, kind="question", task="Вопрос 3")


# ------------------------------------------------------------- предложение и оплата


def test_offer_validation_and_change(db, product, seller, buyer):
    order = customization(db, buyer, product)
    with pytest.raises(ServiceError):
        svc.make_offer(db, order, seller, price=200, days=5)
    with pytest.raises(ServiceError):
        svc.make_offer(db, order, seller, price=500, days=61)
    with pytest.raises(InvalidTransition):
        svc.make_offer(db, order, buyer, price=500, days=5)
    svc.make_offer(db, order, seller, price=500, days=5)
    assert order.status == "offer"
    svc.make_offer(db, order, seller, price=700, days=7)
    assert order.status == "offer" and order.price == 700
    assert notified(db, buyer, "изменил")


def test_accept_offer_creates_payment_and_pay_starts_work(db, product, seller, buyer):
    order = customization(db, buyer, product)
    svc.make_offer(db, order, seller, price=3000, days=5)
    with pytest.raises(InvalidTransition):
        svc.accept_offer(db, order, seller)
    url = svc.accept_offer(db, order, buyer)
    assert url.startswith("/payments/fake/") and order.status == "awaiting_payment"
    assert db.scalar(select(Payment).where(Payment.order_id == order.id)).amount == Decimal("3000")
    assert svc.payment_url(db, order, buyer) == url  # «Оплатить» продолжает тот же платёж
    confirm_payment(db, order)
    assert order.status == "in_work"
    assert order.deadline > utcnow() + timedelta(days=4, hours=23)


def test_with_purchase_creates_purchase_after_payment(db, product, seller, buyer):
    """«Купить с доработкой»: одна оплата на продукт и работу, покупка создаётся после оплаты."""
    from app.services.purchases import sync_access

    order = svc.create_order(db, buyer, product, kind="with_purchase", task="Купить и перекрасить")
    svc.make_offer(db, order, seller, price=500, days=3)
    svc.accept_offer(db, order, buyer)
    assert db.scalar(select(Payment).where(Payment.order_id == order.id)).amount == Decimal("1500")
    assert db.scalar(select(Purchase)) is None
    confirm_payment(db, order)
    purchase = db.scalar(select(Purchase))
    assert purchase.status == "paid" and purchase.buyer_id == buyer.id
    assert order.purchase_id == purchase.id and order.status == "in_work"
    income = db.scalar(
        select(BalanceOperation).where(BalanceOperation.purchase_id == purchase.id, BalanceOperation.kind == "income")
    )
    assert income.status == "held"
    sync_access(db)
    db.refresh(purchase)
    assert purchase.access_status == "invited"


def test_question_turns_into_order_with_purchase(db, product, seller, buyer):
    order = svc.create_order(db, buyer, product, kind="question", task="А можно добавить корзину?")
    svc.post_message(db, order, seller, text="Да, за 2000")
    assert notified(db, buyer, "ответил")
    svc.make_offer(db, order, seller, price=2000, days=4)
    svc.accept_offer(db, order, buyer)
    assert db.scalar(select(Payment).where(Payment.order_id == order.id)).amount == Decimal("3000")
    confirm_payment(db, order)
    assert order.status == "in_work" and order.purchase_id is not None
    assert svc.public_questions(db, product)[0]["answer"] == "Да, за 2000"


def test_repeated_payment_notification_is_idempotent(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product)
    handle_notification(db, db.scalar(select(Payment).where(Payment.order_id == order.id)).external_id)
    db.refresh(order)
    assert order.status == "in_work"


@pytest.mark.parametrize("status", ["new", "offer", "awaiting_payment"])
def test_cancel_by_either_party_before_payment(db, product, seller, buyer, status):
    order = customization(db, buyer, product)
    if status != "new":
        svc.make_offer(db, order, seller, price=500, days=2)
    if status == "awaiting_payment":
        svc.accept_offer(db, order, buyer)
    who = seller if status == "offer" else buyer
    svc.cancel_order(db, order, who)
    assert order.status == "cancelled"
    assert notified(db, buyer if who == seller else seller, "отменён")
    if status == "awaiting_payment":
        assert db.scalar(select(Payment).where(Payment.order_id == order.id)).status == "canceled"


def test_cannot_cancel_paid_order(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product)
    with pytest.raises(InvalidTransition):
        svc.cancel_order(db, order, buyer)


# ------------------------------------------------------------- работа


def test_submit_requires_result_message(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product)
    svc.post_message(db, order, seller, text="Работаю")
    with pytest.raises(ServiceError):
        svc.submit_result(db, order, seller)
    with pytest.raises(InvalidTransition):
        svc.post_message(db, order, buyer, text="я результат", is_result=True)
    submit(db, order, seller)
    assert order.status == "submitted" and order.submitted_at


def test_mark_existing_message_as_result(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product)
    msg = svc.post_message(db, order, seller, text="Архив с результатом")
    svc.mark_result(db, order, seller, msg.id)
    svc.submit_result(db, order, seller)
    assert order.status == "submitted"


def test_accept_credits_seller_immediately(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product, price=3000)
    submit(db, order, seller)
    with pytest.raises(InvalidTransition):
        svc.accept_result(db, order, seller)
    svc.accept_result(db, order, buyer)
    assert order.status == "accepted"
    income = db.scalar(
        select(BalanceOperation).where(BalanceOperation.order_id == order.id, BalanceOperation.kind == "income")
    )
    assert income.status == "available" and income.amount == Decimal("2700.00")
    assert get_balance(db, seller)["available"] == Decimal("2700.00")


def test_revision_limit_and_deadline_extension(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product)
    for i in range(settings.max_revisions):
        submit(db, order, seller)
        before = order.deadline
        with pytest.raises(ServiceError):
            svc.request_revision(db, order, buyer, "")
        svc.request_revision(db, order, buyer, "Поправьте отступы")
        assert order.status == "revision" and order.revisions == i + 1
        assert order.deadline == before + timedelta(days=3)
        with pytest.raises(ServiceError):
            svc.submit_result(db, order, seller)  # после возврата нужен новый результат
    submit(db, order, seller)
    with pytest.raises(InvalidTransition):
        svc.request_revision(db, order, buyer, "Ещё раз")
    assert "revision" not in svc.allowed_actions(db, order, buyer)


def test_seller_refuse_full_refund(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product, price=3000)
    with pytest.raises(ServiceError):
        svc.seller_refuse(db, order, seller, "")
    svc.seller_refuse(db, order, seller, "Не успеваю")
    assert order.status == "refunded"
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment.status == "refunded" and payment.refund_amount == Decimal("3000")
    assert db.scalar(select(BalanceOperation.id).where(BalanceOperation.order_id == order.id)) is None


def test_cancel_overdue_only_after_deadline_and_deadline_note(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product)
    with pytest.raises(InvalidTransition):
        svc.cancel_overdue(db, order, buyer)
    order.deadline = utcnow() - timedelta(minutes=1)
    db.flush()
    assert "cancel_overdue" in svc.allowed_actions(db, order, buyer)
    assert check_deadlines(db) == "просроченных заказов отмечено: 1"
    assert check_deadlines(db) == "просроченных заказов отмечено: 0"  # только один раз
    assert notified(db, buyer, "Срок по заказу")
    svc.cancel_overdue(db, order, buyer)
    assert order.status == "refunded"


def test_auto_accept_after_days(db, product, seller, buyer):
    order = in_work_order(db, buyer, seller, product)
    submit(db, order, seller)
    assert svc.auto_accept(db) == 0
    db.execute(
        update(CustomOrder)
        .where(CustomOrder.id == order.id)
        .values(submitted_at=utcnow() - timedelta(days=3, minutes=1))
    )
    assert svc.auto_accept(db) == 1
    db.refresh(order)
    assert order.status == "accepted"
    assert notified(db, buyer, "автоматически") and notified(db, seller, "автоматически")
    assert db.scalar(
        select(BalanceOperation.id).where(
            BalanceOperation.order_id == order.id,
            BalanceOperation.kind == "income",
            BalanceOperation.status == "available",
        )
    )


def test_dispute_stops_auto_accept(db, product, seller, buyer):
    from app.services.disputes import open_order_dispute

    order = in_work_order(db, buyer, seller, product)
    submit(db, order, seller)
    open_order_dispute(db, buyer, order, reason_type="not_working", reason="Форма не отправляет данные")
    assert order.status == "dispute"
    db.execute(update(CustomOrder).where(CustomOrder.id == order.id).values(submitted_at=utcnow() - timedelta(days=10)))
    assert svc.auto_accept(db) == 0
    db.refresh(order)
    assert order.status == "dispute"


@pytest.mark.parametrize(
    "status,action",
    [
        ("new", lambda db, o, s, b: svc.accept_offer(db, o, b)),
        ("new", lambda db, o, s, b: svc.submit_result(db, o, s)),
        ("offer", lambda db, o, s, b: svc.accept_result(db, o, b)),
        ("in_work", lambda db, o, s, b: svc.make_offer(db, o, s, price=500, days=3)),
        ("in_work", lambda db, o, s, b: svc.accept_result(db, o, b)),
        ("in_work", lambda db, o, s, b: svc.request_revision(db, o, b, "x")),
        ("submitted", lambda db, o, s, b: svc.seller_refuse(db, o, s, "причина")),
        ("submitted", lambda db, o, s, b: svc.cancel_overdue(db, o, b)),
        ("accepted", lambda db, o, s, b: svc.cancel_order(db, o, b)),
        ("cancelled", lambda db, o, s, b: svc.make_offer(db, o, s, price=500, days=3)),
        ("refunded", lambda db, o, s, b: svc.accept_result(db, o, b)),
    ],
)
def test_invalid_transitions(db, product, seller, buyer, status, action):
    order = customization(db, buyer, product)
    order.status, order.price, order.days = status, Decimal("500"), 3
    db.flush()
    with pytest.raises(InvalidTransition):
        action(db, order, seller, buyer)


def test_change_order_status_rejects_unknown_jump(db, product, buyer):
    with pytest.raises(InvalidTransition):
        svc.change_order_status(db, customization(db, buyer, product), "accepted")


def test_invalid_transition_via_api_is_409(api, db, product, seller, buyer):
    order = customization(db, buyer, product)
    api.login(buyer)
    resp = api.post(f"/api/orders/{order.id}/accept")
    assert resp.status_code == 409 and resp.json()["detail"]


# ------------------------------------------------------------- блокировка продавца


def test_blocking_seller_processes_orders(api, db, product, seller, buyer):
    from app.services.accounts import block_user

    admin = make_admin(db)
    o_new = customization(db, buyer, product)
    o_offer = svc.create_order(db, make_user(db), product, kind="question", task="Вопрос до покупки")
    svc.make_offer(db, o_offer, seller, price=500, days=2)
    o_work = in_work_order(db, make_user(db), seller, product)
    o_sub = in_work_order(db, make_user(db), seller, product)
    submit(db, o_sub, seller)
    block_user(db, seller, reason="Нарушение правил", admin=admin)
    assert o_new.status == "cancelled" and o_offer.status == "cancelled"
    assert o_work.status == "dispute" and o_sub.status == "dispute"
    assert db.scalar(select(Dispute).where(Dispute.order_id == o_work.id)).reason_type == "seller_blocked"
    assert not db.scalar(
        select(func.count()).where(
            catalog_services.visible_condition(), catalog_services.Product.seller_id == seller.id
        )
    )
    assert product.title not in [p["title"] for p in api.get("/api/catalog/products").json()["items"]]


# ------------------------------------------------------------- чат и права


def test_chat_attachment_and_permissions(api, db, product, seller, buyer):
    order = customization(db, buyer, product)
    api.login(buyer)
    resp = api.post(
        f"/api/orders/{order.id}/messages",
        data={"text": "ТЗ во вложении"},
        files={"attachment": ("spec.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    msg = db.scalar(select(Message).where(Message.order_id == order.id, Message.attachment != ""))
    assert api.get(f"/api/orders/attachments/{msg.id}").content == b"%PDF-1.4 test"
    api.login(seller)
    assert api.get(f"/api/orders/attachments/{msg.id}").status_code == 200
    api.login(make_user(db))
    assert api.get(f"/api/orders/{order.id}").status_code == 404
    assert api.get(f"/api/orders/attachments/{msg.id}").status_code == 404
    assert api.get(f"/api/orders/{order.id}/messages").status_code == 404


def test_admin_can_open_order_and_attachment(api, db, product, buyer):
    order = customization(db, buyer, product)
    msg = svc.post_message(db, order, buyer, text="файл", attachment=("a.txt", b"hello"))
    api.login(make_admin(db))
    assert api.get(f"/api/orders/{order.id}").status_code == 200
    assert api.get(f"/api/orders/attachments/{msg.id}").status_code == 200


def test_attachment_validation(db, product, buyer):
    order = customization(db, buyer, product)
    with pytest.raises(ServiceError):
        svc.post_message(db, order, buyer, attachment=("virus.exe", b"MZ"))
    with pytest.raises(ServiceError):
        svc.post_message(db, order, buyer, attachment=("big.zip", b"0" * (20 * 1024 * 1024 + 1)))


def test_messages_rate_limit(db, product, buyer, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_messages_per_hour", 3)
    order = customization(db, buyer, product)  # первое сообщение — задача
    svc.post_message(db, order, buyer, text="2")
    svc.post_message(db, order, buyer, text="3")
    with pytest.raises(ServiceError):
        svc.post_message(db, order, buyer, text="4")


def test_poll_returns_new_messages(api, db, product, seller, buyer):
    order = customization(db, buyer, product)
    last = order.messages[-1].id
    svc.post_message(db, order, seller, text="Привет из опроса")
    api.login(buyer)
    data = api.get(f"/api/orders/{order.id}/messages?after={last}").json()
    assert [m["text"] for m in data["messages"]] == ["Привет из опроса"] and data["last_id"] > last
    assert data["messages"][0]["is_mine"] is False


def test_order_page_actions_by_role(api, db, product, seller, buyer):
    order = customization(db, buyer, product)
    api.login(buyer)
    data = api.get(f"/api/orders/{order.id}").json()
    assert "offer" not in data["actions"] and "cancel" in data["actions"] and data["is_buyer"]
    assert data["steps"][0]["current"] is True
    api.login(seller)
    data = api.get(f"/api/orders/{order.id}").json()
    assert "offer" in data["actions"] and "accept" not in data["actions"]


def test_full_order_flow_through_api(api, db, product, seller, buyer):
    purchase = paid_purchase(db, buyer, product)
    api.login(buyer)
    assert api.get(f"/api/orders/new?purchase={purchase.id}").json()["kind"] == "customization"
    resp = api.post("/api/orders", {"purchase_id": purchase.id, "task": "Добавить тёмную тему"})
    assert resp.status_code == 201
    order_id = resp.json()["id"]
    api.login(seller)
    assert api.post(f"/api/orders/{order_id}/offer", {"price": "1500", "days": "3"}).status_code == 200
    api.login(buyer)
    url = api.post(f"/api/orders/{order_id}/accept-offer").json()["url"]
    assert api.post(f"/api{url.rstrip('/')}", {"action": "pay"}).json()["url"] == f"/orders/{order_id}/"
    api.login(seller)
    api.post(f"/api/orders/{order_id}/messages", data={"text": "Готово", "is_result": "true"})
    assert api.post(f"/api/orders/{order_id}/submit").status_code == 200
    api.login(buyer)
    assert api.post(f"/api/orders/{order_id}/accept").status_code == 200
    rows = api.get("/api/orders").json()["items"]
    assert rows[0]["status_label"] == "Принят"
    api.login(seller)
    assert api.get("/api/seller/orders?kind=orders").json()["total"] == 1
    assert api.get("/api/seller/orders?kind=question").json()["total"] == 0


def test_create_question_via_api(api, db, product, buyer):
    api.login(buyer)
    info = api.get(f"/api/orders/new?product={product.slug}&kind=with_purchase").json()
    assert info["kind"] == "with_purchase" and info["is_owner"] is False
    resp = api.post("/api/orders", {"product_slug": product.slug, "kind": "question", "task": "Есть ли тёмная тема?"})
    assert resp.status_code == 201 and resp.json()["kind"] == "question"
    assert api.post("/api/orders", {"product_slug": "nope", "kind": "question", "task": "xxxxx"}).status_code == 404

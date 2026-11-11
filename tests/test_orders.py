"""Переходы заказа на доработку (таблица 7.4 ТЗ), чат, права, «Купить с доработкой», автоприёмка."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.balance.models import BalanceOperation
from apps.balance.services import get_balance
from apps.core.exceptions import InvalidTransition, ServiceError
from apps.orders import services as svc
from apps.orders.models import CustomOrder, Message
from apps.payments.models import Payment
from apps.payments.providers import FakeProvider
from apps.payments.services import handle_notification
from apps.purchases.models import Purchase
from apps.versions.services import publish_to_mirror
from tests.factories import ProductFactory, UserFactory
from tests.helpers import make_version

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    p = ProductFactory(price=Decimal("1000"))
    v = make_version(p, {"a.py": "x = 1\n"}, status="approved")
    v.approved_at = timezone.now()
    v.save()
    publish_to_mirror(v)
    p.refresh_from_db()
    return p


@pytest.fixture
def seller(product):
    return product.seller


@pytest.fixture
def buyer():
    return UserFactory(github_login="buyer1")


def paid_purchase(buyer, product):
    return Purchase.objects.create(
        buyer=buyer, product=product, price=product.price, commission=100, status="paid", paid_at=timezone.now()
    )


def confirm_payment(order):
    payment = Payment.objects.filter(order=order).latest("id")
    FakeProvider().set_status(payment.external_id, "succeeded")
    handle_notification(payment.external_id)
    order.refresh_from_db()
    return payment


def customization(buyer, product, **kw):
    purchase = paid_purchase(buyer, product)
    return svc.create_order(buyer, product, kind="customization", task="Добавить форму", purchase=purchase, **kw)


def in_work_order(buyer, seller, product, price=3000, days=5):
    order = customization(buyer, product)
    svc.make_offer(order, seller, price=price, days=days)
    svc.accept_offer(order, buyer)
    confirm_payment(order)
    assert order.status == "in_work"
    return order


def submit(order, seller):
    svc.post_message(order, seller, text="Готово, см. архив", is_result=True)
    return svc.submit_result(order, seller)


# ------------------------------------------------------------- создание


def test_create_question_notifies_seller(product, seller, buyer):
    order = svc.create_order(buyer, product, kind="question", task="Подойдёт для WordPress?")
    assert order.status == "new" and order.kind == "question"
    assert seller.notifications.filter(text__contains="Новый вопрос").exists()
    assert order.messages.get().text == "Подойдёт для WordPress?"


def test_create_customization_requires_purchase(product, buyer):
    with pytest.raises(ServiceError):
        svc.create_order(buyer, product, kind="customization", task="Доработать")


def test_seller_cannot_order_own_product(product, seller):
    with pytest.raises(ServiceError):
        svc.create_order(seller, product, kind="question", task="Вопрос себе")


def test_unpublished_product_cannot_be_ordered(buyer):
    p = ProductFactory(status="hidden")
    with pytest.raises(ServiceError):
        svc.create_order(buyer, p, kind="with_purchase", task="Хочу доработку")


def test_questions_rate_limit(product, buyer, settings):
    settings.RATE_LIMIT_QUESTIONS_PER_HOUR = 2
    svc.create_order(buyer, product, kind="question", task="Вопрос 1")
    svc.create_order(buyer, product, kind="question", task="Вопрос 2")
    with pytest.raises(ServiceError):
        svc.create_order(buyer, product, kind="question", task="Вопрос 3")


# ------------------------------------------------------------- предложение и оплата


def test_offer_validation_and_change(product, seller, buyer):
    order = customization(buyer, product)
    with pytest.raises(ServiceError):
        svc.make_offer(order, seller, price=200, days=5)
    with pytest.raises(ServiceError):
        svc.make_offer(order, seller, price=500, days=61)
    with pytest.raises(InvalidTransition):
        svc.make_offer(order, buyer, price=500, days=5)  # не продавец
    svc.make_offer(order, seller, price=500, days=5)
    assert order.status == "offer"
    svc.make_offer(order, seller, price=700, days=7)  # offer → offer
    assert order.status == "offer" and order.price == 700
    assert buyer.notifications.filter(text__contains="изменил").exists()


def test_accept_offer_creates_payment_and_pay_starts_work(product, seller, buyer):
    order = customization(buyer, product)
    svc.make_offer(order, seller, price=3000, days=5)
    with pytest.raises(InvalidTransition):
        svc.accept_offer(order, seller)
    url = svc.accept_offer(order, buyer)
    assert url.startswith("/payments/fake/")
    assert order.status == "awaiting_payment"
    assert Payment.objects.get(order=order).amount == Decimal("3000")
    confirm_payment(order)
    assert order.status == "in_work"
    assert order.deadline > timezone.now() + timedelta(days=4, hours=23)


def test_with_purchase_creates_purchase_after_payment(client, product, seller, buyer):
    """«Купить с доработкой»: одна оплата на продукт и работу, покупка создаётся после оплаты."""
    order = svc.create_order(buyer, product, kind="with_purchase", task="Купить и перекрасить")
    svc.make_offer(order, seller, price=500, days=3)
    svc.accept_offer(order, buyer)
    assert Payment.objects.get(order=order).amount == Decimal("1500")
    assert not Purchase.objects.exists()
    confirm_payment(order)
    purchase = Purchase.objects.get()
    assert purchase.status == "paid" and purchase.buyer == buyer
    assert order.purchase == purchase and order.status == "in_work"
    assert BalanceOperation.objects.get(purchase=purchase, kind="income").status == "held"
    call_command("sync_access")
    purchase.refresh_from_db()
    assert purchase.access_status == "invited"


def test_question_turns_into_order_with_purchase(product, seller, buyer):
    order = svc.create_order(buyer, product, kind="question", task="А можно добавить корзину?")
    svc.post_message(order, seller, text="Да, за 2000")
    assert buyer.notifications.filter(text__contains="ответил").exists()
    svc.make_offer(order, seller, price=2000, days=4)
    svc.accept_offer(order, buyer)
    assert Payment.objects.get(order=order).amount == Decimal("3000")
    confirm_payment(order)
    assert order.status == "in_work" and order.purchase is not None
    assert svc.public_questions(product)[0]["answer"] == "Да, за 2000"


def test_repeated_payment_notification_is_idempotent(product, seller, buyer):
    order = in_work_order(buyer, seller, product)
    payment = Payment.objects.get(order=order)
    handle_notification(payment.external_id)
    order.refresh_from_db()
    assert order.status == "in_work"


@pytest.mark.parametrize("status", ["new", "offer", "awaiting_payment"])
def test_cancel_by_either_party_before_payment(product, seller, buyer, status):
    order = customization(buyer, product)
    if status != "new":
        svc.make_offer(order, seller, price=500, days=2)
    if status == "awaiting_payment":
        svc.accept_offer(order, buyer)
    who = seller if status == "offer" else buyer
    svc.cancel_order(order, who)
    assert order.status == "cancelled"
    other = buyer if who == seller else seller
    assert other.notifications.filter(text__contains="отменён").exists()
    if status == "awaiting_payment":
        assert Payment.objects.get(order=order).status == "canceled"


def test_cannot_cancel_paid_order(product, seller, buyer):
    order = in_work_order(buyer, seller, product)
    with pytest.raises(InvalidTransition):
        svc.cancel_order(order, buyer)


# ------------------------------------------------------------- работа


def test_submit_requires_result_message(product, seller, buyer):
    order = in_work_order(buyer, seller, product)
    svc.post_message(order, seller, text="Работаю")
    with pytest.raises(ServiceError):
        svc.submit_result(order, seller)
    with pytest.raises(InvalidTransition):
        svc.post_message(order, buyer, text="я результат", is_result=True)
    submit(order, seller)
    assert order.status == "submitted" and order.submitted_at


def test_mark_existing_message_as_result(product, seller, buyer):
    order = in_work_order(buyer, seller, product)
    msg = svc.post_message(order, seller, text="Архив с результатом")
    svc.mark_result(order, seller, msg.pk)
    svc.submit_result(order, seller)
    assert order.status == "submitted"


def test_accept_credits_seller_immediately(product, seller, buyer):
    order = in_work_order(buyer, seller, product, price=3000)
    submit(order, seller)
    with pytest.raises(InvalidTransition):
        svc.accept_result(order, seller)
    svc.accept_result(order, buyer)
    assert order.status == "accepted"
    income = BalanceOperation.objects.get(order=order, kind="income")
    assert income.status == "available" and income.amount == Decimal("2700.00")
    assert get_balance(seller)["available"] == Decimal("2700.00")


def test_revision_limit_and_deadline_extension(product, seller, buyer, settings):
    order = in_work_order(buyer, seller, product)
    for i in range(settings.MAX_REVISIONS):
        submit(order, seller)
        before = order.deadline
        with pytest.raises(ServiceError):
            svc.request_revision(order, buyer, "")
        svc.request_revision(order, buyer, "Поправьте отступы")
        assert order.status == "revision" and order.revisions == i + 1
        assert order.deadline == before + timedelta(days=3)
        # после возврата нужен новый результат
        with pytest.raises(ServiceError):
            svc.submit_result(order, seller)
    submit(order, seller)
    with pytest.raises(InvalidTransition):
        svc.request_revision(order, buyer, "Ещё раз")
    assert "revision" not in svc.allowed_actions(order, buyer)


def test_seller_refuse_full_refund(product, seller, buyer):
    order = in_work_order(buyer, seller, product, price=3000)
    with pytest.raises(ServiceError):
        svc.seller_refuse(order, seller, "")
    svc.seller_refuse(order, seller, "Не успеваю")
    assert order.status == "refunded"
    payment = Payment.objects.get(order=order)
    assert payment.status == "refunded" and payment.refund_amount == Decimal("3000")
    assert not BalanceOperation.objects.filter(order=order).exists()


def test_cancel_overdue_only_after_deadline(product, seller, buyer):
    order = in_work_order(buyer, seller, product)
    with pytest.raises(InvalidTransition):
        svc.cancel_overdue(order, buyer)
    CustomOrder.objects.filter(pk=order.pk).update(deadline=timezone.now() - timedelta(minutes=1))
    order.refresh_from_db()
    assert "cancel_overdue" in svc.allowed_actions(order, buyer)
    svc.cancel_overdue(order, buyer)
    assert order.status == "refunded"


def test_auto_accept_after_days(product, seller, buyer):
    order = in_work_order(buyer, seller, product)
    submit(order, seller)
    assert svc.auto_accept() == 0
    CustomOrder.objects.filter(pk=order.pk).update(submitted_at=timezone.now() - timedelta(days=3, minutes=1))
    call_command("auto_accept")
    order.refresh_from_db()
    assert order.status == "accepted"
    assert buyer.notifications.filter(text__contains="автоматически").exists()
    assert seller.notifications.filter(text__contains="автоматически").exists()
    assert BalanceOperation.objects.filter(order=order, kind="income", status="available").exists()


def test_dispute_stops_auto_accept(product, seller, buyer):
    from apps.disputes.services import open_order_dispute

    order = in_work_order(buyer, seller, product)
    submit(order, seller)
    open_order_dispute(buyer, order, reason_type="not_working", reason="Форма не отправляет данные")
    assert order.status == "dispute"
    CustomOrder.objects.filter(pk=order.pk).update(submitted_at=timezone.now() - timedelta(days=10))
    assert svc.auto_accept() == 0
    order.refresh_from_db()
    assert order.status == "dispute"


@pytest.mark.parametrize(
    "status,action",
    [
        ("new", lambda o, s, b: svc.accept_offer(o, b)),
        ("new", lambda o, s, b: svc.submit_result(o, s)),
        ("offer", lambda o, s, b: svc.accept_result(o, b)),
        ("in_work", lambda o, s, b: svc.make_offer(o, s, price=500, days=3)),
        ("in_work", lambda o, s, b: svc.accept_result(o, b)),
        ("in_work", lambda o, s, b: svc.request_revision(o, b, "x")),
        ("submitted", lambda o, s, b: svc.seller_refuse(o, s, "причина")),
        ("submitted", lambda o, s, b: svc.cancel_overdue(o, b)),
        ("accepted", lambda o, s, b: svc.cancel_order(o, b)),
        ("cancelled", lambda o, s, b: svc.make_offer(o, s, price=500, days=3)),
        ("refunded", lambda o, s, b: svc.accept_result(o, b)),
    ],
)
def test_invalid_transitions(product, seller, buyer, status, action):
    order = customization(buyer, product)
    CustomOrder.objects.filter(pk=order.pk).update(status=status, price=500, days=3)
    order.refresh_from_db()
    with pytest.raises(InvalidTransition):
        action(order, seller, buyer)


def test_change_order_status_rejects_unknown_jump(product, buyer):
    order = customization(buyer, product)
    with pytest.raises(InvalidTransition):
        svc.change_order_status(order, "accepted")


# ------------------------------------------------------------- блокировка продавца


def test_blocking_seller_processes_orders(product, seller, buyer, admin_user):
    from apps.accounts.services import block_user

    o_new = customization(buyer, product)
    b2 = UserFactory()
    o_offer = svc.create_order(b2, product, kind="question", task="Вопрос до покупки")
    svc.make_offer(o_offer, seller, price=500, days=2)
    b3 = UserFactory()
    o_work = in_work_order(b3, seller, product)
    b4 = UserFactory()
    o_sub = in_work_order(b4, seller, product)
    submit(o_sub, seller)
    block_user(seller, reason="Нарушение правил", admin=admin_user)
    for o in (o_new, o_offer, o_work, o_sub):
        o.refresh_from_db()
    assert o_new.status == "cancelled" and o_offer.status == "cancelled"
    assert o_work.status == "dispute" and o_sub.status == "dispute"
    assert o_work.disputes.get().reason_type == "seller_blocked"
    # продукты продавца скрыты из каталога
    from apps.catalog.services import visible_products

    assert not visible_products().filter(seller=seller).exists()


# ------------------------------------------------------------- чат и права


def test_chat_attachment_and_permissions(client, product, seller, buyer):
    order = customization(buyer, product)
    client.force_login(buyer)
    f = SimpleUploadedFile("spec.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    client.post(f"/orders/{order.pk}/", {"action": "message", "text": "ТЗ во вложении", "attachment": f})
    msg = Message.objects.filter(order=order).exclude(attachment="").get()
    assert client.get(f"/orders/attachments/{msg.pk}/").status_code == 200
    client.force_login(seller)
    assert client.get(f"/orders/attachments/{msg.pk}/").status_code == 200
    stranger = UserFactory()
    client.force_login(stranger)
    assert client.get(f"/orders/{order.pk}/").status_code == 403
    assert client.get(f"/orders/attachments/{msg.pk}/").status_code == 403
    assert client.get(f"/orders/{order.pk}/messages/").status_code == 403


def test_admin_can_open_order_and_attachment(client, product, buyer, admin_user):
    order = customization(buyer, product)
    msg = svc.post_message(order, buyer, text="файл", attachment=SimpleUploadedFile("a.txt", b"hello"))
    client.force_login(admin_user)
    assert client.get(f"/orders/{order.pk}/").status_code == 200
    assert client.get(f"/orders/attachments/{msg.pk}/").status_code == 200


def test_attachment_validation(product, buyer):
    order = customization(buyer, product)
    with pytest.raises(ServiceError):
        svc.post_message(order, buyer, attachment=SimpleUploadedFile("virus.exe", b"MZ"))
    big = SimpleUploadedFile("big.zip", b"0" * (20 * 1024 * 1024 + 1))
    with pytest.raises(ServiceError):
        svc.post_message(order, buyer, attachment=big)


def test_messages_rate_limit(product, buyer, settings):
    settings.RATE_LIMIT_MESSAGES_PER_HOUR = 3
    order = customization(buyer, product)  # первое сообщение — задача
    svc.post_message(order, buyer, text="2")
    svc.post_message(order, buyer, text="3")
    with pytest.raises(ServiceError):
        svc.post_message(order, buyer, text="4")


def test_poll_returns_new_messages_json(client, product, seller, buyer):
    order = customization(buyer, product)
    last = order.messages.last().pk
    svc.post_message(order, seller, text="Привет из опроса")
    client.force_login(buyer)
    data = client.get(f"/orders/{order.pk}/messages/?after={last}").json()
    assert "Привет из опроса" in data["html"] and data["last_id"] > last


def test_order_page_shows_only_allowed_buttons(client, product, seller, buyer):
    order = customization(buyer, product)
    client.force_login(buyer)
    html = client.get(f"/orders/{order.pk}/").content.decode()
    assert "Отправить предложение" not in html and "Отменить" in html
    client.force_login(seller)
    html = client.get(f"/orders/{order.pk}/").content.decode()
    assert "Отправить предложение" in html and "Принять работу" not in html


def test_full_order_flow_through_views(client, product, seller, buyer):
    purchase = paid_purchase(buyer, product)
    client.force_login(buyer)
    resp = client.post(f"/orders/new/?purchase={purchase.pk}", {"task": "Добавить тёмную тему"})
    order = CustomOrder.objects.get()
    assert resp["Location"] == f"/orders/{order.pk}/"
    client.force_login(seller)
    client.post(f"/orders/{order.pk}/", {"action": "offer", "price": "1500", "days": "3"})
    client.force_login(buyer)
    resp = client.post(f"/orders/{order.pk}/", {"action": "accept_offer"})
    client.post(resp["Location"], {"action": "pay"})
    order.refresh_from_db()
    assert order.status == "in_work"
    client.force_login(seller)
    client.post(f"/orders/{order.pk}/", {"action": "message", "text": "Готово", "is_result": "on"})
    client.post(f"/orders/{order.pk}/", {"action": "submit"})
    client.force_login(buyer)
    client.post(f"/orders/{order.pk}/", {"action": "accept"})
    order.refresh_from_db()
    assert order.status == "accepted"
    assert "Принят" in client.get("/me/orders/").content.decode()

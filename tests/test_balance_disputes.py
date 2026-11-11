"""Баланс, выплаты и споры (раздел 12 ТЗ)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.balance import services as bal
from apps.balance.models import BalanceOperation
from apps.core.exceptions import ServiceError
from apps.disputes import services as disp
from apps.disputes.models import Dispute
from apps.payments.models import Payment
from apps.payments.providers import FakeProvider
from apps.payments.services import handle_notification
from apps.purchases import services as purchase_services
from apps.purchases.models import Purchase
from apps.versions.services import publish_to_mirror
from tests.factories import ProductFactory, UserFactory
from tests.helpers import make_version

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    p = ProductFactory(price=Decimal("2000"))
    v = make_version(p, {"a.py": "x = 1\n"}, status="approved")
    v.approved_at = timezone.now()
    v.save()
    publish_to_mirror(v)
    p.refresh_from_db()
    return p


def buy(product, buyer=None):
    buyer = buyer or UserFactory(github_login="gh-buyer")
    purchase, _ = purchase_services.start_purchase(buyer, product, accept_license=True)
    payment = purchase.payments.get()
    FakeProvider().set_status(payment.external_id, "succeeded")
    handle_notification(payment.external_id)
    purchase.refresh_from_db()
    purchase_services.sync_access()
    purchase.refresh_from_db()
    return purchase


def later(days):
    return timezone.now() + timedelta(days=days, minutes=1)


# ------------------------------------------------------------- баланс


def test_held_becomes_available_after_hold_days(product):
    purchase = buy(product)
    seller = product.seller
    assert bal.get_balance(seller) == {
        "held": Decimal("1800.00"),
        "available": Decimal("0"),
        "withdrawn": Decimal("0"),
        "requested": Decimal("0"),
    }
    bal.release_funds(now=timezone.now() + timedelta(days=6))
    assert bal.get_balance(seller)["available"] == 0
    bal.release_funds(now=later(7))
    assert bal.get_balance(seller)["available"] == Decimal("1800.00")
    purchase.refresh_from_db()
    assert purchase.status == "completed"


def test_payout_more_than_available_forbidden(product):
    buy(product)
    bal.release_funds(now=later(7))
    seller = product.seller
    with pytest.raises(ServiceError):
        bal.request_payout(seller, "1900", "Карта 2200 0000 0000 0000")
    with pytest.raises(ServiceError):
        bal.request_payout(seller, "400", "Карта 2200 0000 0000 0000")  # меньше 500
    with pytest.raises(ServiceError):
        bal.request_payout(seller, "600", "")  # без реквизитов
    bal.request_payout(seller, "1000", "Карта 2200 0000 0000 0000")
    b = bal.get_balance(seller)
    assert b["available"] == Decimal("800.00") and b["requested"] == Decimal("1000.00")
    with pytest.raises(ServiceError):
        bal.request_payout(seller, "900", "Карта 2200 0000 0000 0000")


def test_payout_paid_and_rejected(product, admin_user):
    buy(product)
    bal.release_funds(now=later(7))
    seller = product.seller
    op1 = bal.request_payout(seller, "1000", "Карта 2200 0000 0000 0000")
    op2 = bal.request_payout(seller, "500", "Карта 2200 0000 0000 0000")
    bal.mark_payout_paid(op1.pk, admin_user)
    bal.reject_payout(op2.pk, admin_user, "неверные реквизиты")
    b = bal.get_balance(seller)
    assert b["withdrawn"] == Decimal("1000.00") and b["available"] == Decimal("800.00")
    assert seller.notifications.filter(text__contains="отклонена").exists()
    from apps.core.exceptions import InvalidTransition

    with pytest.raises(InvalidTransition):
        bal.mark_payout_paid(op2.pk, admin_user)


def test_balance_page_and_payout_form(client, product):
    buy(product)
    bal.release_funds(now=later(7))
    client.force_login(product.seller)
    resp = client.get("/balance/")
    assert "1\xa0800\xa0₽" in resp.content.decode()
    client.post("/balance/", {"amount": "600", "requisites": "Карта 2200 0000 0000 0000"})
    assert BalanceOperation.objects.filter(kind="payout", status="requested").count() == 1
    assert "Вывод" in client.get("/balance/?kind=payout").content.decode()


def test_admin_payouts_page(client, product, admin_user):
    buy(product)
    bal.release_funds(now=later(7))
    op = bal.request_payout(product.seller, "600", "Карта 2200 0000 0000 0000")
    client.force_login(admin_user)
    assert "Карта 2200" in client.get("/moderation/payouts/").content.decode()
    client.post("/moderation/payouts/", {"op": op.pk, "action": "paid"})
    op.refresh_from_db()
    assert op.status == "paid"


# ------------------------------------------------------------- споры по покупке


def test_dispute_stops_release(product):
    purchase = buy(product)
    disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="not_working", reason="Не запускается на PHP 8")
    bal.release_funds(now=later(7))
    assert bal.get_balance(product.seller)["available"] == 0
    purchase.refresh_from_db()
    assert purchase.status == "dispute"


def test_dispute_rules(product):
    purchase = buy(product)
    stranger = UserFactory()
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(stranger, purchase, reason_type="not_working", reason="Чужая покупка тут")
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="changed_mind", reason="Передумал покупать")
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="other", reason="коротко")
    Purchase.objects.filter(pk=purchase.pk).update(paid_at=timezone.now() - timedelta(days=8))
    purchase.refresh_from_db()
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="not_working", reason="Сломалось через неделю")


def test_full_refund_revokes_access_and_reverses_income(client, product, admin_user):
    purchase = buy(product)
    assert purchase.access_status == "invited"
    d = disp.open_purchase_dispute(
        purchase.buyer, purchase, reason_type="not_as_described", reason="Нет обещанной корзины"
    )
    disp.resolve(d, admin_user, resolution="refund", comment="Функции нет")
    purchase.refresh_from_db()
    assert purchase.status == "refunded" and purchase.access_status == "revoked"
    rev = BalanceOperation.objects.get(purchase=purchase, kind="refund_reversal")
    assert rev.amount == Decimal("-1800.00")
    bal.release_funds(now=later(7))
    assert bal.get_balance(product.seller) == {
        "held": Decimal("0"),
        "available": Decimal("0.00"),
        "withdrawn": Decimal("0"),
        "requested": Decimal("0"),
    }
    payment = Payment.objects.get(purchase=purchase)
    assert payment.status == "refunded" and payment.refund_amount == Decimal("2000")
    client.force_login(purchase.buyer)
    assert client.get(f"/me/purchases/{purchase.pk}/download/").status_code == 403
    # повторно купить после возврата можно
    purchase_services.check_can_buy(purchase.buyer, product)


def test_partial_refund(product, admin_user):
    purchase = buy(product)
    d = disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="other", reason="Часть функций не работает")
    with pytest.raises(ServiceError):
        disp.resolve(d, admin_user, resolution="partial", refund_amount="2500")
    disp.resolve(d, admin_user, resolution="partial", refund_amount="500")
    purchase.refresh_from_db()
    assert purchase.status == "partially_refunded" and purchase.access_status != "revoked"
    bal.release_funds(now=later(7))
    assert bal.get_balance(product.seller)["available"] == Decimal("1350.00")  # 1800 − 500 × 0.9
    d.refresh_from_db()
    assert d.status == "closed" and d.refund_amount == Decimal("500")


def test_resolve_in_favor_of_seller(product, admin_user):
    purchase = buy(product)
    d = disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="not_working", reason="Не работает вообще")
    disp.resolve(d, admin_user, resolution="seller")
    purchase.refresh_from_db()
    assert purchase.status == "paid"
    bal.release_funds(now=later(7))
    assert bal.get_balance(product.seller)["available"] == Decimal("1800.00")
    from apps.core.exceptions import InvalidTransition

    with pytest.raises(InvalidTransition):
        disp.resolve(d, admin_user, resolution="refund")


def test_one_dispute_per_purchase(product):
    purchase = buy(product)
    disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="not_working", reason="Не работает вообще")
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(purchase.buyer, purchase, reason_type="other", reason="Ещё раз пробую")


def test_dispute_pages(client, product, admin_user):
    purchase = buy(product)
    client.force_login(purchase.buyer)
    resp = client.get(f"/disputes/new/?purchase={purchase.pk}")
    assert "передумал" in resp.content.decode()
    client.post(
        f"/disputes/new/?purchase={purchase.pk}", {"reason_type": "not_working", "reason": "Ошибка 500 при запуске"}
    )
    d = Dispute.objects.get()
    assert client.get(f"/moderation/disputes/{d.pk}/").status_code == 403
    client.force_login(admin_user)
    assert "Ошибка 500" in client.get(f"/moderation/disputes/{d.pk}/").content.decode()
    client.post(f"/moderation/disputes/{d.pk}/", {"resolution": "refund"})
    d.refresh_from_db()
    assert d.status == "closed"


def test_other_user_cannot_open_dispute_page(client, product):
    purchase = buy(product)
    client.force_login(UserFactory())
    assert client.get(f"/disputes/new/?purchase={purchase.pk}").status_code == 404


# ------------------------------------------------------------- споры по заказу


def _order_in_work(product):
    from apps.orders import services as osvc

    buyer = UserFactory()
    purchase = buy(product, buyer)
    order = osvc.create_order(buyer, product, kind="customization", task="Доработать дизайн", purchase=purchase)
    osvc.make_offer(order, product.seller, price=1000, days=3)
    osvc.accept_offer(order, buyer)
    payment = Payment.objects.get(order=order)
    FakeProvider().set_status(payment.external_id, "succeeded")
    handle_notification(payment.external_id)
    order.refresh_from_db()
    return order


@pytest.mark.parametrize(
    "resolution,amount,status,available",
    [
        ("seller", None, "accepted", Decimal("900.00")),
        ("refund", None, "refunded", Decimal("0")),
        ("partial", "400", "partially_refunded", Decimal("540.00")),
    ],
)
def test_order_dispute_resolutions(product, admin_user, resolution, amount, status, available):
    order = _order_in_work(product)
    d = disp.open_order_dispute(order.buyer, order, reason_type="not_working", reason="Сроки сорваны, связи нет")
    disp.resolve(d, admin_user, resolution=resolution, refund_amount=amount)
    order.refresh_from_db()
    assert order.status == status
    ops = BalanceOperation.objects.filter(order=order, kind="income")
    assert sum((o.amount for o in ops), Decimal("0")) == available


def test_order_dispute_only_in_work_statuses(product):
    from apps.orders import services as osvc

    buyer = UserFactory()
    order = osvc.create_order(buyer, product, kind="question", task="Вопрос по продукту")
    with pytest.raises(ServiceError):
        disp.open_order_dispute(buyer, order, reason_type="other", reason="Хочу спор по вопросу")

"""Исправления после ревизии бизнес-логики: оплата после отмены, «Купить с доработкой» при смене цены,
возврат по заказу с продуктом, уведомления о доступных деньгах, удаление продукта, логин GitHub,
блокировка покупателя, исключение кода Bootstrap при проверке на заимствования."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts import services as account_services
from apps.balance.services import release_funds
from apps.catalog import services as catalog_services
from apps.core.exceptions import ServiceError
from apps.disputes import services as dispute_services
from apps.orders import services as order_services
from apps.payments.models import Payment
from apps.payments.providers import FakeProvider
from apps.payments.services import handle_notification
from apps.plagiarism.similarity import compare_dirs, fingerprint_files
from apps.purchases import services as purchase_services
from apps.purchases.models import Purchase
from apps.versions.services import publish_to_mirror
from tests.factories import ProductFactory, UserFactory
from tests.helpers import make_version

pytestmark = pytest.mark.django_db
SB = Path(settings.BASE_DIR) / "fixtures" / "demo" / "startbootstrap"


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
def buyer():
    return UserFactory(github_login="buyer-one")


@pytest.fixture
def admin():
    return UserFactory(is_staff=True)


def succeed(payment):
    FakeProvider().set_status(payment.external_id, "succeeded")
    return handle_notification(payment.external_id)


# ---------------------------------------------------------------- оплаты


def test_payment_after_cancel_alerts_admins_and_gives_nothing(product, buyer, admin):
    purchase, _ = purchase_services.start_purchase(buyer, product, accept_license=True)
    Purchase.objects.filter(pk=purchase.pk).update(created_at=timezone.now() - timedelta(hours=1))
    assert purchase_services.cancel_unpaid() == 1
    payment = purchase.payments.get()
    assert payment.status == "canceled"
    succeed(payment)  # покупатель всё же оплатил на странице провайдера
    payment.refresh_from_db()
    purchase.refresh_from_db()
    assert payment.status == "succeeded"
    assert purchase.status == "cancelled"
    assert not purchase.balance_operations.exists()
    assert admin.notifications.filter(text__contains="верните деньги").exists()


def test_with_purchase_uses_paid_product_price(product, buyer):
    """Продавец поднял цену после согласия покупателя: покупка — по фактически оплаченной цене."""
    order = order_services.create_order(buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(order, product.seller, price=500, days=3)
    order_services.accept_offer(order, buyer)
    product.price = Decimal("3000")
    product.save()
    succeed(Payment.objects.get(order=order))
    purchase = Purchase.objects.get(buyer=buyer)
    assert purchase.price == Decimal("1000") and purchase.commission == Decimal("100")


def test_with_purchase_payment_url_recreated_after_price_change(product, buyer):
    order = order_services.create_order(buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(order, product.seller, price=500, days=3)
    order_services.accept_offer(order, buyer)
    product.price = Decimal("1200")
    product.save()
    order_services.payment_url(order, buyer)
    amounts = sorted((p.amount, p.status) for p in Payment.objects.filter(order=order))
    assert amounts == [(Decimal("1500"), "canceled"), (Decimal("1700"), "pending")]


def test_with_purchase_cannot_be_accepted_for_hidden_product(product, buyer):
    order = order_services.create_order(buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(order, product.seller, price=500, days=3)
    catalog_services.hide_product(product, product.seller)
    order.refresh_from_db()
    with pytest.raises(ServiceError):
        order_services.accept_offer(order, buyer)
    order.refresh_from_db()
    assert order.status == "offer"


def test_refund_of_purchase_bought_with_order_marks_order_payment(product, buyer, admin):
    order = order_services.create_order(buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(order, product.seller, price=500, days=3)
    order_services.accept_offer(order, buyer)
    payment = Payment.objects.get(order=order)
    succeed(payment)
    purchase = Purchase.objects.get(buyer=buyer)
    dispute = dispute_services.open_purchase_dispute(
        buyer, purchase, reason_type="not_working", reason="Код не запускается совсем"
    )
    dispute_services.resolve(dispute, admin, resolution="refund")
    payment.refresh_from_db()
    assert payment.refund_amount == Decimal("1000") and payment.status == "partially_refunded"
    assert admin.notifications.filter(text__contains="Нужно вернуть 1000").exists()


def test_release_after_full_refund_sends_no_money_notification(product, buyer, admin):
    purchase, _ = purchase_services.start_purchase(buyer, product, accept_license=True)
    succeed(purchase.payments.get())
    purchase.refresh_from_db()
    dispute = dispute_services.open_purchase_dispute(
        buyer, purchase, reason_type="not_working", reason="Код не запускается совсем"
    )
    dispute_services.resolve(dispute, admin, resolution="refund")
    release_funds(now=timezone.now() + timedelta(days=settings.HOLD_DAYS + 1))
    assert not product.seller.notifications.filter(text__contains="доступны к выводу").exists()


# ---------------------------------------------------------------- продукт и аккаунт


def test_product_with_question_cannot_be_deleted(product, buyer):
    order_services.create_order(buyer, product, kind="question", task="Есть ли тёмная тема?")
    with pytest.raises(ServiceError):
        catalog_services.delete_product(product, product.seller)
    assert type(product).objects.filter(pk=product.pk).exists()


def test_github_login_change_moves_access(product, buyer):
    purchase, _ = purchase_services.start_purchase(buyer, product, accept_license=True)
    succeed(purchase.payments.get())
    purchase_services.sync_access()
    purchase.refresh_from_db()
    assert purchase.access_status == "invited"
    account_services.set_github_login(buyer, "new-login")
    purchase.refresh_from_db()
    assert purchase.access_status == "none"
    purchase_services.sync_access()
    purchase.refresh_from_db()
    assert purchase.access_status == "invited"


def test_invalid_github_login_is_rejected(buyer):
    with pytest.raises(ServiceError):
        account_services.set_github_login(buyer, "плохой логин!")
    buyer.refresh_from_db()
    assert buyer.github_login == "buyer-one"


def test_blocking_buyer_cancels_their_unpaid_orders(product, buyer, admin):
    order = order_services.create_order(buyer, product, kind="question", task="Есть ли тёмная тема?")
    order_services.make_offer(order, product.seller, price=500, days=3)
    order_services.accept_offer(order, buyer)
    account_services.block_user(buyer, reason="спам", admin=admin)
    order.refresh_from_db()
    assert order.status == "cancelled"
    assert Payment.objects.get(order=order).status == "canceled"


# ---------------------------------------------------------------- проверка на заимствования


def test_bootstrap_itself_gives_no_fingerprints():
    css = (settings.BASE_DIR / "apps" / "plagiarism" / "libs" / "bootstrap-5.3.3.css").read_text(encoding="utf-8")
    assert fingerprint_files([("css/site.css", css)], settings.PLAG_K, settings.PLAG_W) == {}


def test_different_start_bootstrap_templates_are_not_copies():
    """В styles.css шаблонов встроен весь Bootstrap — он не должен делать разные шаблоны копиями."""
    s, *_ = compare_dirs(SB / "landing-page", SB / "freelancer", settings.PLAG_K, settings.PLAG_W)
    assert s < settings.PLAG_FLAG

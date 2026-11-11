from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.balance.models import BalanceOperation
from apps.balance.services import get_balance, release_funds
from apps.core.exceptions import ServiceError
from apps.payments import services as payment_services
from apps.payments.models import Payment
from apps.payments.providers import FakeProvider
from apps.purchases import services
from apps.purchases.models import Purchase
from apps.versions.services import publish_to_mirror
from tests.factories import ProductFactory, UserFactory
from tests.helpers import make_version

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    p = ProductFactory(price=Decimal("2000"))
    v = make_version(p, {"index.html": "<p>демо</p>", "app.js": "let a = 1;"}, status="approved")
    v.approved_at = timezone.now()
    v.save()
    publish_to_mirror(v)
    p.refresh_from_db()
    return p


@pytest.fixture
def buyer():
    return UserFactory(github_login="buyer-gh")


def pay(client, purchase, action="pay"):
    payment = purchase.payments.get()
    return client.post(f"/payments/fake/{payment.external_id}/", {"action": action})


def test_full_purchase_path_on_fake_provider(client, product, buyer):
    client.force_login(buyer)
    resp = client.get(f"/buy/{product.slug}/")
    assert "Оплатить" in resp.content.decode()
    resp = client.post(f"/buy/{product.slug}/", {"accept_license": "on", "github_login": "buyer-gh"})
    purchase = Purchase.objects.get()
    assert purchase.status == "pending" and purchase.price == 2000 and purchase.commission == 200
    assert purchase.license_version == "1.0"
    assert resp["Location"].startswith("/payments/fake/")
    resp = client.post(resp["Location"], {"action": "pay"})
    assert resp.status_code == 302
    resp = client.get(resp["Location"], follow=True)
    assert "Оплата прошла" in resp.content.decode()
    purchase.refresh_from_db()
    assert purchase.status == "paid" and purchase.paid_at
    income = BalanceOperation.objects.get(purchase=purchase, kind="income")
    assert income.amount == Decimal("1800.00") and income.status == "held"
    assert income.available_at > timezone.now() + timedelta(days=6)
    product.refresh_from_db()
    assert product.sales_count == 1
    # фоновая выдача доступа
    call_command("sync_access")
    purchase.refresh_from_db()
    assert purchase.access_status == "invited"
    resp = client.get(f"/me/purchases/{purchase.pk}/")
    purchase.refresh_from_db()
    assert purchase.access_status == "granted"  # fake: приглашение принято
    assert "git clone" in resp.content.decode()
    # на странице продукта вместо «Купить» — «Перейти к покупке»
    assert "Перейти к покупке" in client.get(f"/p/{product.slug}/").content.decode()


def test_license_required(client, product, buyer):
    client.force_login(buyer)
    resp = client.post(f"/buy/{product.slug}/", {}, follow=True)
    assert "лицензии" in resp.content.decode()
    assert not Purchase.objects.exists()


def test_repeated_webhook_does_not_double_credit(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    pay(client, purchase)
    payment = purchase.payments.get()
    for _ in range(3):
        client.post("/payments/webhook/", {"object": {"id": payment.external_id}}, content_type="application/json")
        payment_services.handle_notification(payment.external_id)
    assert BalanceOperation.objects.filter(purchase=purchase, kind="income").count() == 1
    assert get_balance(product.seller)["held"] == Decimal("1800.00")


def test_webhook_body_alone_is_not_trusted(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    payment = purchase.payments.get()
    # уведомление «succeeded», но у провайдера платёж всё ещё pending
    client.post(
        "/payments/webhook/",
        {"event": "payment.succeeded", "object": {"id": payment.external_id, "status": "succeeded"}},
        content_type="application/json",
    )
    purchase.refresh_from_db()
    assert purchase.status == "pending"


def test_declined_payment_cancels_purchase(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    pay(client, purchase, action="decline")
    purchase.refresh_from_db()
    assert purchase.status == "cancelled"
    assert not BalanceOperation.objects.exists()


def test_author_cannot_buy_own_product(client, product):
    client.force_login(product.seller)
    resp = client.post(f"/buy/{product.slug}/", {"accept_license": "on"}, follow=True)
    assert "собственный продукт" in resp.content.decode()
    assert not Purchase.objects.exists()


def test_repeat_purchase_forbidden(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    pay(client, Purchase.objects.get())
    with pytest.raises(ServiceError):
        services.create_purchase(buyer, product, accept_license=True)
    resp = client.get(f"/buy/{product.slug}/")
    assert resp.status_code == 302 and "/me/purchases/" in resp["Location"]


def test_db_unique_active_purchase(product, buyer):
    Purchase.objects.create(buyer=buyer, product=product, price=1, commission=0, status="paid")
    with pytest.raises(IntegrityError), transaction.atomic():
        Purchase.objects.create(buyer=buyer, product=product, price=1, commission=0, status="completed")


def test_second_click_reuses_payment(client, product, buyer):
    client.force_login(buyer)
    r1 = client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    r2 = client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    assert r1["Location"] == r2["Location"]
    assert Purchase.objects.count() == 1 and Payment.objects.count() == 1


def test_unpublished_product_cannot_be_bought(client, buyer):
    p = ProductFactory(status="hidden")
    client.force_login(buyer)
    client.post(f"/buy/{p.slug}/", {"accept_license": "on"})
    assert not Purchase.objects.exists()


def test_download_zip_only_for_buyer(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    # до оплаты скачать нельзя
    assert client.get(f"/me/purchases/{purchase.pk}/download/").status_code == 403
    pay(client, purchase)
    resp = client.get(f"/me/purchases/{purchase.pk}/download/")
    assert resp.status_code == 200 and resp["Content-Type"] == "application/zip"
    assert b"".join(resp.streaming_content)[:2] == b"PK"
    other = UserFactory()
    client.force_login(other)
    assert client.get(f"/me/purchases/{purchase.pk}/").status_code == 403
    assert client.get(f"/me/purchases/{purchase.pk}/download/").status_code == 403


def test_access_button_without_github_login(client, product):
    buyer = UserFactory(github_login="")
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    pay(client, purchase)
    call_command("sync_access")
    purchase.refresh_from_db()
    assert purchase.access_status == "none"
    resp = client.get(f"/me/purchases/{purchase.pk}/")
    assert "Получить доступ" in resp.content.decode()
    client.post(f"/me/purchases/{purchase.pk}/", {"action": "access", "github_login": "late-login"})
    purchase.refresh_from_db()
    buyer.refresh_from_db()
    assert buyer.github_login == "late-login" and purchase.access_status == "invited"


def test_hold_then_release_and_complete(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    pay(client, purchase)
    assert release_funds() == 0
    assert get_balance(product.seller)["available"] == 0
    release_funds(now=timezone.now() + timedelta(days=7, minutes=1))
    purchase.refresh_from_db()
    assert purchase.status == "completed"
    bal = get_balance(product.seller)
    assert bal["held"] == 0 and bal["available"] == Decimal("1800.00")


def test_cancel_unpaid_after_timeout(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    Purchase.objects.filter(pk=purchase.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    call_command("cancel_unpaid")
    purchase.refresh_from_db()
    assert purchase.status == "cancelled"
    assert purchase.payments.get().status == "canceled"


def test_cancel_unpaid_rechecks_provider(client, product, buyer):
    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    purchase = Purchase.objects.get()
    FakeProvider().set_status(purchase.payments.get().external_id, "succeeded")  # оплачено, вебхук потерялся
    Purchase.objects.filter(pk=purchase.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    services.cancel_unpaid()
    purchase.refresh_from_db()
    assert purchase.status == "paid"


def test_new_version_notifies_buyers(client, product, buyer, admin_user):
    from apps.versions.services import approve_version

    client.force_login(buyer)
    client.post(f"/buy/{product.slug}/", {"accept_license": "on"})
    pay(client, Purchase.objects.get())
    v2 = make_version(product, {"index.html": "<p>v2</p>"}, status="moderation", tag="v1.1.0")
    approve_version(v2, admin_user)
    assert buyer.notifications.filter(text__contains="v1.1.0").exists()

"""Покупка: оформление, fake-оплата, повторный вебхук, холд, доступ к копии, ZIP, отмена по таймауту."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import ServiceError
from app.integrations.payments import FakeProvider
from app.models import BalanceOperation, Notification, Payment, Purchase
from app.models.base import utcnow
from app.services import payments as payment_services
from app.services import purchases as svc
from app.services.balance import get_balance, release_funds
from app.services.versions import approve_version
from tests.factories import make_admin, make_product, make_user
from tests.helpers import make_published, make_version


@pytest.fixture
def product(db):
    p = make_product(db, price=Decimal("2000"))
    make_published(db, p)
    return p


@pytest.fixture
def buyer(db):
    return make_user(db, github_login="buyer-gh")


def buy(api, product, **extra):
    return api.post("/api/purchases", {"slug": product.slug, "accept_license": True, **extra})


def the_purchase(db) -> Purchase:
    return db.scalar(select(Purchase))


def payment_of(db, purchase) -> Payment:
    return db.scalar(select(Payment).where(Payment.purchase_id == purchase.id))


def pay(api, db, purchase, action="pay"):
    return api.post(f"/api/payments/fake/{payment_of(db, purchase).external_id}", {"action": action})


def count(db, *where, model=BalanceOperation):
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_full_purchase_path_on_fake_provider(api, db, product, buyer):
    api.login(buyer)
    info = api.get(f"/api/purchases/buy/{product.slug}").json()
    assert info["error"] == "" and info["version"]["tag_name"] == "v1.0.0" and info["github_login"] == "buyer-gh"
    resp = buy(api, product, github_login="buyer-gh")
    assert resp.status_code == 200, resp.text
    purchase = the_purchase(db)
    assert purchase.status == "pending" and purchase.price == 2000 and purchase.commission == 200
    assert purchase.license_version == "1.0"
    assert resp.json()["url"].startswith("/payments/fake/")
    checkout = api.get(f"/api{resp.json()['url'].rstrip('/')}").json()
    assert checkout["amount"] == "2000.00" and checkout["status"] == "pending"
    result = pay(api, db, purchase).json()
    assert result["message"] == "Оплата прошла." and result["url"] == f"/me/purchases/{purchase.id}/"
    db.refresh(purchase)
    assert purchase.status == "paid" and purchase.paid_at
    income = db.scalar(
        select(BalanceOperation).where(BalanceOperation.purchase_id == purchase.id, BalanceOperation.kind == "income")
    )
    assert income.amount == Decimal("1800.00") and income.status == "held"
    assert income.available_at > utcnow() + timedelta(days=6)
    db.refresh(product)
    assert product.sales_count == 1
    assert count(
        db, Notification.user_id == product.seller_id, Notification.text.contains("Продажа"), model=Notification
    )
    svc.sync_access(db)
    db.refresh(purchase)
    assert purchase.access_status == "invited"
    page = api.get(f"/api/purchases/{purchase.id}").json()
    db.refresh(purchase)
    assert purchase.access_status == "granted"  # fake: приглашение принято
    assert page["clone_command"].startswith("git clone https://github.com/") and page["can_download"]
    assert api.get(f"/api/catalog/products/{product.slug}").json()["purchase_id"] == purchase.id
    assert api.get("/api/purchases").json()["items"][0]["id"] == purchase.id


def test_license_required(api, db, product, buyer):
    api.login(buyer)
    resp = api.post("/api/purchases", {"slug": product.slug})
    assert resp.status_code == 400 and "лицензии" in resp.json()["detail"]
    assert the_purchase(db) is None


def test_repeated_webhook_does_not_double_credit(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    pay(api, db, purchase)
    payment = payment_of(db, purchase)
    for _ in range(3):
        assert api.c.post("/api/payments/webhook", json={"object": {"id": payment.external_id}}).status_code == 200
        payment_services.handle_notification(db, payment.external_id)
    assert count(db, BalanceOperation.purchase_id == purchase.id, BalanceOperation.kind == "income") == 1
    assert get_balance(db, product.seller)["held"] == Decimal("1800.00")


def test_webhook_body_alone_is_not_trusted(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    payment = payment_of(db, purchase)
    api.c.post(
        "/api/payments/webhook",
        json={"event": "payment.succeeded", "object": {"id": payment.external_id, "status": "succeeded"}},
    )
    db.refresh(purchase)
    assert purchase.status == "pending"
    assert api.c.post("/api/payments/webhook", content=b"not json").status_code == 400


def test_declined_payment_cancels_purchase(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    assert pay(api, db, purchase, action="decline").json()["message"] == "Оплата отклонена."
    db.refresh(purchase)
    assert purchase.status == "cancelled"
    assert count(db) == 0


def test_author_cannot_buy_own_product(api, db, product):
    api.login(product.seller)
    assert "собственный продукт" in api.get(f"/api/purchases/buy/{product.slug}").json()["error"]
    resp = buy(api, product)
    assert resp.status_code == 400 and "собственный продукт" in resp.json()["detail"]
    assert the_purchase(db) is None


def test_repeat_purchase_forbidden(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    pay(api, db, the_purchase(db))
    with pytest.raises(ServiceError):
        svc.create_purchase(db, buyer, product, accept_license=True)
    assert api.get(f"/api/purchases/buy/{product.slug}").json()["existing_purchase_id"] == the_purchase(db).id


def test_db_unique_active_purchase(db, product, buyer):
    db.add(Purchase(buyer_id=buyer.id, product_id=product.id, price=1, commission=0, status="paid"))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(Purchase(buyer_id=buyer.id, product_id=product.id, price=1, commission=0, status="completed"))
        db.flush()


def test_second_click_reuses_payment(api, db, product, buyer):
    api.login(buyer)
    r1, r2 = buy(api, product), buy(api, product)
    assert r1.json()["url"] == r2.json()["url"]
    assert count(db, model=Purchase) == 1 and count(db, model=Payment) == 1


def test_unpublished_product_cannot_be_bought(api, db, buyer):
    p = make_product(db, status="hidden")
    api.login(buyer)
    assert buy(api, p).status_code == 400
    assert the_purchase(db) is None


def test_download_zip_only_for_buyer(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    assert api.get(f"/api/purchases/{purchase.id}/download").status_code == 404  # до оплаты нельзя
    pay(api, db, purchase)
    resp = api.get(f"/api/purchases/{purchase.id}/download")
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/zip"
    assert resp.content[:2] == b"PK"
    api.login(make_user(db))
    assert api.get(f"/api/purchases/{purchase.id}").status_code == 404
    assert api.get(f"/api/purchases/{purchase.id}/download").status_code == 404


def test_access_button_without_github_login(api, db, product):
    buyer = make_user(db, github_login="")
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    pay(api, db, purchase)
    svc.sync_access(db)
    db.refresh(purchase)
    assert purchase.access_status == "none"
    assert api.get(f"/api/purchases/{purchase.id}").json()["github_login"] == ""
    resp = api.post(f"/api/purchases/{purchase.id}/access", {"github_login": "плохой логин"})
    assert resp.status_code == 400
    resp = api.post(f"/api/purchases/{purchase.id}/access", {"github_login": "late-login"})
    assert resp.status_code == 200, resp.text
    db.refresh(purchase)
    db.refresh(buyer)
    assert buyer.github_login == "late-login" and purchase.access_status == "invited"


def test_hold_then_release_and_complete(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    pay(api, db, purchase)
    assert release_funds(db) == 0
    assert get_balance(db, product.seller)["available"] == 0
    release_funds(db, now=utcnow() + timedelta(days=7, minutes=1))
    db.refresh(purchase)
    assert purchase.status == "completed"
    bal = get_balance(db, product.seller)
    assert bal["held"] == 0 and bal["available"] == Decimal("1800.00")
    assert count(db, Notification.text.contains("доступны к выводу"), model=Notification) == 1


def test_cancel_unpaid_after_timeout(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    db.execute(update(Purchase).where(Purchase.id == purchase.id).values(created_at=utcnow() - timedelta(minutes=31)))
    assert svc.cancel_unpaid(db) == 1
    db.refresh(purchase)
    assert purchase.status == "cancelled" and payment_of(db, purchase).status == "canceled"


def test_cancel_unpaid_rechecks_provider(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    purchase = the_purchase(db)
    FakeProvider().set_status(payment_of(db, purchase).external_id, "succeeded")  # оплачено, вебхук потерялся
    db.execute(update(Purchase).where(Purchase.id == purchase.id).values(created_at=utcnow() - timedelta(minutes=31)))
    svc.cancel_unpaid(db)
    db.refresh(purchase)
    assert purchase.status == "paid"


def test_payment_return_page(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    payment = payment_of(db, the_purchase(db))
    assert api.get(f"/api/payments/return/{payment.id}").json()["level"] == "info"
    api.login(make_user(db))
    assert api.get(f"/api/payments/return/{payment.id}").status_code == 404
    assert api.get(f"/api/payments/fake/{payment.external_id}").status_code == 404


def test_new_version_notifies_buyers(api, db, product, buyer):
    api.login(buyer)
    buy(api, product)
    pay(api, db, the_purchase(db))
    v2 = make_version(db, product, {"index.html": "<p>v2</p>"}, status="moderation", tag="v1.1.0")
    approve_version(db, v2, make_admin(db))
    assert count(db, Notification.user_id == buyer.id, Notification.text.contains("v1.1.0"), model=Notification)


def test_profile_update(api, db, buyer):
    api.login(buyer)
    resp = api.put("/api/profile", {"username": "renamed", "github_login": "@octo-cat"})
    assert resp.status_code == 200
    db.refresh(buyer)
    assert buyer.username == "renamed" and buyer.github_login == "octo-cat"
    resp = api.put("/api/profile", {"username": "ab", "github_login": "bad login"})
    assert set(resp.json()["fields"]) == {"username", "github_login"}


def test_profile_requires_login(api):
    assert api.get("/api/profile").status_code == 401

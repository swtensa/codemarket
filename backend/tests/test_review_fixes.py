"""Исправления после проверки бизнес-логики: граничные случаи покупок, заказов и споров."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.errors import ServiceError
from app.integrations.payments import FakeProvider
from app.models import Notification, Payment, Product, Purchase
from app.models.base import utcnow
from app.services import accounts as account_services
from app.services import catalog as catalog_services
from app.services import disputes as dispute_services
from app.services import orders as order_services
from app.services import purchases as purchase_services
from app.services.balance import release_funds
from app.services.payments import handle_notification
from tests.factories import make_admin, make_product, make_user
from tests.helpers import make_published


@pytest.fixture
def product(db):
    p = make_product(db, price=Decimal("1000"))
    make_published(db, p, {"a.py": "x = 1\n"})
    return p


@pytest.fixture
def buyer(db):
    return make_user(db, github_login="buyer-one")


@pytest.fixture
def admin(db):
    return make_admin(db)


def succeed(db, payment):
    FakeProvider().set_status(payment.external_id, "succeeded")
    return handle_notification(db, payment.external_id)


def notified(db, user, text):
    return bool(
        db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.text.contains(text)))
    )


def order_payment(db, order):
    return db.scalar(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id))


def test_payment_after_cancel_alerts_admins_and_gives_nothing(db, product, buyer, admin):
    purchase, _ = purchase_services.start_purchase(db, buyer, product, accept_license=True)
    db.execute(update(Purchase).where(Purchase.id == purchase.id).values(created_at=utcnow() - timedelta(hours=1)))
    assert purchase_services.cancel_unpaid(db) == 1
    payment = db.scalar(select(Payment).where(Payment.purchase_id == purchase.id))
    assert payment.status == "canceled"
    succeed(db, payment)
    assert payment.status == "succeeded"
    db.refresh(purchase)
    assert purchase.status == "cancelled"
    assert notified(db, admin, "верните деньги")


def test_with_purchase_uses_paid_product_price(db, product, buyer):
    order = order_services.create_order(db, buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(db, order, product.seller, price=500, days=3)
    order_services.accept_offer(db, order, buyer)
    product.price = Decimal("3000")
    db.flush()
    succeed(db, order_payment(db, order))
    purchase = db.scalar(select(Purchase).where(Purchase.buyer_id == buyer.id))
    assert purchase.price == Decimal("1000") and purchase.commission == Decimal("100")


def test_with_purchase_payment_url_recreated_after_price_change(db, product, buyer):
    order = order_services.create_order(db, buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(db, order, product.seller, price=500, days=3)
    order_services.accept_offer(db, order, buyer)
    product.price = Decimal("1200")
    db.flush()
    order_services.payment_url(db, order, buyer)
    amounts = sorted((p.amount, p.status) for p in db.scalars(select(Payment).where(Payment.order_id == order.id)))
    assert amounts == [(Decimal("1500"), "canceled"), (Decimal("1700"), "pending")]


def test_with_purchase_cannot_be_accepted_for_hidden_product(db, product, buyer):
    order = order_services.create_order(db, buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(db, order, product.seller, price=500, days=3)
    catalog_services.hide_product(db, product, product.seller)
    with pytest.raises(ServiceError):
        order_services.accept_offer(db, order, buyer)
    assert order.status == "offer"


def test_order_paid_twice_alerts_admins(db, product, buyer, admin):
    order = order_services.create_order(db, buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(db, order, product.seller, price=500, days=3)
    order_services.accept_offer(db, order, buyer)
    payment = order_payment(db, order)
    # продукт куплен отдельно до оплаты заказа
    purchase_services.create_paid_purchase_for_order(db, order)
    succeed(db, payment)
    assert notified(db, admin, "уже был куплен отдельно")


def test_refund_of_purchase_bought_with_order_marks_order_payment(db, product, buyer, admin):
    order = order_services.create_order(db, buyer, product, kind="with_purchase", task="Купить и доработать")
    order_services.make_offer(db, order, product.seller, price=500, days=3)
    order_services.accept_offer(db, order, buyer)
    payment = order_payment(db, order)
    succeed(db, payment)
    purchase = db.scalar(select(Purchase).where(Purchase.buyer_id == buyer.id))
    dispute = dispute_services.open_purchase_dispute(
        db, buyer, purchase, reason_type="not_working", reason="Код не запускается совсем"
    )
    dispute_services.resolve(db, dispute, admin, resolution="refund")
    assert payment.refund_amount == Decimal("1000") and payment.status == "partially_refunded"
    assert notified(db, admin, "Нужно вернуть 1000")


def test_release_after_full_refund_sends_no_money_notification(db, product, buyer, admin):
    purchase, _ = purchase_services.start_purchase(db, buyer, product, accept_license=True)
    succeed(db, db.scalar(select(Payment).where(Payment.purchase_id == purchase.id)))
    dispute = dispute_services.open_purchase_dispute(
        db, buyer, purchase, reason_type="not_working", reason="Код не запускается совсем"
    )
    dispute_services.resolve(db, dispute, admin, resolution="refund")
    release_funds(db, now=utcnow() + timedelta(days=settings.hold_days + 1))
    assert not notified(db, product.seller, "доступны к выводу")


def test_product_with_question_cannot_be_deleted(db, product, buyer):
    order_services.create_order(db, buyer, product, kind="question", task="Есть ли тёмная тема?")
    with pytest.raises(ServiceError):
        catalog_services.delete_product(db, product, product.seller)
    assert db.get(Product, product.id) is not None


def test_github_login_change_moves_access(db, product, buyer):
    purchase, _ = purchase_services.start_purchase(db, buyer, product, accept_license=True)
    succeed(db, db.scalar(select(Payment).where(Payment.purchase_id == purchase.id)))
    purchase_services.sync_access(db)
    assert purchase.access_status == "invited"
    account_services.set_github_login(db, buyer, "new-login")
    assert purchase.access_status == "none"
    purchase_services.sync_access(db)
    assert purchase.access_status == "invited"


def test_invalid_github_login_is_rejected(db, buyer):
    with pytest.raises(ServiceError):
        account_services.set_github_login(db, buyer, "плохой логин!")
    assert buyer.github_login == "buyer-one"


def test_blocking_buyer_cancels_their_unpaid_orders(db, product, buyer, admin):
    order = order_services.create_order(db, buyer, product, kind="question", task="Есть ли тёмная тема?")
    order_services.make_offer(db, order, product.seller, price=500, days=3)
    order_services.accept_offer(db, order, buyer)
    account_services.block_user(db, buyer, reason="спам", admin=admin)
    assert order.status == "cancelled"
    assert order_payment(db, order).status == "canceled"

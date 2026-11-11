from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.exceptions import ServiceError
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.orders.models import CustomOrder
from apps.purchases.models import Purchase
from apps.reviews import services as rs
from tests.factories import ProductFactory, UserFactory

pytestmark = pytest.mark.django_db


def purchase_of(product, status="paid"):
    return Purchase.objects.create(
        buyer=UserFactory(), product=product, price=product.price, commission=10, status=status, paid_at=timezone.now()
    )


def test_product_rating_recalculated():
    product = ProductFactory()
    rs.create_purchase_review(purchase_of(product).buyer, Purchase.objects.last(), rating=5, text="Отлично")
    p2 = purchase_of(product, status="completed")
    rs.create_purchase_review(p2.buyer, p2, rating=4)
    product.refresh_from_db()
    assert product.rating_avg == Decimal("4.50") and product.rating_count == 2


def test_review_rules():
    product = ProductFactory()
    p = purchase_of(product)
    with pytest.raises(ServiceError):
        rs.create_purchase_review(UserFactory(), p, rating=5)
    with pytest.raises(ServiceError):
        rs.create_purchase_review(p.buyer, p, rating=6)
    rs.create_purchase_review(p.buyer, p, rating=3)
    with pytest.raises(ServiceError):
        rs.create_purchase_review(p.buyer, p, rating=5)
    pending = purchase_of(product, status="pending")
    with pytest.raises(ServiceError):
        rs.create_purchase_review(pending.buyer, pending, rating=5)


def test_order_review_only_after_accept_and_seller_rating():
    product = ProductFactory()
    p = purchase_of(product)
    rs.create_purchase_review(p.buyer, p, rating=5)
    order = CustomOrder.objects.create(buyer=p.buyer, product=product, kind="customization", task="t", status="in_work")
    with pytest.raises(ServiceError):
        rs.create_order_review(p.buyer, order, rating=2)
    order.status = "accepted"
    order.save()
    rs.create_order_review(p.buyer, order, rating=2, text="Долго")
    product.refresh_from_db()
    assert product.rating_avg == Decimal("5.00") and product.rating_count == 1  # отзыв о доработке не влияет
    avg, n = rs.seller_rating(product.seller)
    assert avg == Decimal("3.50") and n == 2
    about_product, about_orders = rs.product_reviews(product)
    assert len(about_product) == 1 and len(about_orders) == 1


def test_review_view_and_product_page(client):
    product = ProductFactory()
    p = purchase_of(product)
    client.force_login(p.buyer)
    resp = client.post(f"/reviews/new/?purchase={p.pk}", {"rating": "4", "text": "Хороший код"})
    assert resp.status_code == 302
    html = client.get(f"/p/{product.slug}/").content.decode()
    assert "Хороший код" in html
    assert Product.objects.get(pk=product.pk).rating_count == 1


def test_bell_count_and_mark_all_read(client):
    user = UserFactory()
    notify(user, "Первое", "/")
    notify(user, "Второе", "/me/")
    client.force_login(user)
    html = client.get("/").content.decode()
    assert "Уведомления: 2 непрочитанных" in html
    resp = client.get("/notifications/")
    assert "Первое" in resp.content.decode()
    client.post("/notifications/")
    assert not Notification.objects.filter(user=user, is_read=False).exists()


def test_open_notification_marks_read_and_redirects(client):
    user = UserFactory()
    n = notify(user, "Ссылка", "/me/purchases/")
    evil = notify(user, "Внешняя", "https://evil.example/")
    client.force_login(user)
    resp = client.get(f"/notifications/{n.pk}/")
    assert resp["Location"] == "/me/purchases/"
    n.refresh_from_db()
    assert n.is_read
    assert client.get(f"/notifications/{evil.pk}/")["Location"] == "/notifications/"
    other = UserFactory()
    client.force_login(other)
    assert client.get(f"/notifications/{n.pk}/").status_code == 404

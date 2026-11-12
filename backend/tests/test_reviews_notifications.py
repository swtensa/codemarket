"""Отзывы и рейтинг, уведомления и колокольчик."""

from decimal import Decimal

import pytest

from app.core.errors import ServiceError
from app.models import CustomOrder, Notification, Purchase
from app.models.base import utcnow
from app.services import reviews as rs
from app.services.notifications import notify
from tests.factories import make_product, make_user


def purchase_of(db, product, status="paid"):
    p = Purchase(
        buyer_id=make_user(db).id,
        product_id=product.id,
        price=product.price,
        commission=10,
        status=status,
        paid_at=utcnow(),
    )
    db.add(p)
    db.flush()
    return p


def test_product_rating_recalculated(db):
    product = make_product(db)
    p1 = purchase_of(db, product)
    rs.create_purchase_review(db, p1.buyer, p1, rating=5, text="Отлично")
    p2 = purchase_of(db, product, status="completed")
    rs.create_purchase_review(db, p2.buyer, p2, rating=4)
    db.refresh(product)
    assert product.rating_avg == Decimal("4.50") and product.rating_count == 2


def test_review_rules(db):
    product = make_product(db)
    p = purchase_of(db, product)
    with pytest.raises(ServiceError):
        rs.create_purchase_review(db, make_user(db), p, rating=5)
    with pytest.raises(ServiceError):
        rs.create_purchase_review(db, p.buyer, p, rating=6)
    with pytest.raises(ServiceError):
        rs.create_purchase_review(db, p.buyer, p, rating="пять")
    rs.create_purchase_review(db, p.buyer, p, rating=3)
    with pytest.raises(ServiceError):
        rs.create_purchase_review(db, p.buyer, p, rating=5)
    pending = purchase_of(db, product, status="pending")
    with pytest.raises(ServiceError):
        rs.create_purchase_review(db, pending.buyer, pending, rating=5)


def test_order_review_only_after_accept_and_seller_rating(db):
    product = make_product(db)
    p = purchase_of(db, product)
    rs.create_purchase_review(db, p.buyer, p, rating=5)
    order = CustomOrder(buyer_id=p.buyer_id, product_id=product.id, kind="customization", task="t", status="in_work")
    db.add(order)
    db.flush()
    with pytest.raises(ServiceError):
        rs.create_order_review(db, p.buyer, order, rating=2)
    order.status = "accepted"
    db.flush()
    rs.create_order_review(db, p.buyer, order, rating=2, text="Долго")
    with pytest.raises(ServiceError):
        rs.create_order_review(db, p.buyer, order, rating=4)
    db.refresh(product)
    assert product.rating_avg == Decimal("5.00") and product.rating_count == 1  # отзыв о доработке не влияет
    avg, n = rs.seller_rating(db, product.seller)
    assert avg == Decimal("3.50") and n == 2
    about_product, about_orders = rs.product_reviews(db, product)
    assert len(about_product) == 1 and len(about_orders) == 1


def test_review_api_and_product_page(api, db):
    product = make_product(db)
    p = purchase_of(db, product)
    api.login(p.buyer)
    assert api.get(f"/api/reviews/new?purchase={p.id}").json()["back"] == f"/me/purchases/{p.id}/"
    assert api.get(f"/api/purchases/{p.id}").json()["can_review"] is True
    resp = api.post("/api/reviews", {"purchase_id": p.id, "rating": "4", "text": "Хороший код"})
    assert resp.status_code == 201
    data = api.get(f"/api/catalog/products/{product.slug}").json()
    assert data["product_reviews"][0]["text"] == "Хороший код" and data["seller"]["reviews"] == 1
    db.refresh(product)
    assert product.rating_count == 1
    assert api.get(f"/api/purchases/{p.id}").json()["review"]["rating"] == 4
    api.login(make_user(db))
    assert api.get(f"/api/reviews/new?purchase={p.id}").status_code == 404


def test_bell_count_and_mark_all_read(api, db):
    user = make_user(db)
    notify(db, user, "Первое", "/")
    notify(db, user, "Второе", "/me/")
    api.login(user)
    assert api.get("/api/notifications/unread").json()["count"] == 2
    items = api.get("/api/notifications").json()["items"]
    assert [n["text"] for n in items] == ["Второе", "Первое"]
    assert api.post("/api/notifications/read-all").json()["message"] == "Отмечено прочитанными: 2"
    assert api.get("/api/notifications/unread").json()["count"] == 0


def test_open_notification_marks_read_and_returns_link(api, db):
    user = make_user(db)
    n = notify(db, user, "Ссылка", "/me/purchases/")
    evil = notify(db, user, "Внешняя", "https://evil.example/")
    api.login(user)
    assert api.post(f"/api/notifications/{n.id}/open").json()["url"] == "/me/purchases/"
    db.refresh(n)
    assert n.is_read
    assert api.post(f"/api/notifications/{evil.id}/open").json()["url"] == "/notifications/"
    api.login(make_user(db))
    assert api.post(f"/api/notifications/{n.id}/open").status_code == 404


def test_notification_text_is_trimmed(db):
    n = notify(db, make_user(db), "x" * 600)
    assert len(n.text) == 500 and isinstance(n, Notification)
    assert notify(db, None, "никому") is None

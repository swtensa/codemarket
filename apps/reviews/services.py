"""Отзывы и рейтинг. Рейтинг продукта пересчитывается при сохранении отзыва о продукте,
рейтинг продавца — среднее по всем отзывам на его продукты и доработки."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q

from apps.catalog import services as catalog_services
from apps.core.exceptions import ServiceError
from apps.notifications.services import notify

from .models import Review


def _clean(rating, text):
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise ServiceError("Поставьте оценку от 1 до 5.")
    if not 1 <= rating <= 5:
        raise ServiceError("Поставьте оценку от 1 до 5.")
    return rating, (text or "").strip()[:3000]


def recalc_product_rating(product):
    """Пересчитать rating_avg и rating_count продукта по отзывам о продукте."""
    agg = Review.objects.filter(purchase__product=product).aggregate(avg=Avg("rating"), n=Count("id"))
    avg = Decimal(agg["avg"] or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    catalog_services.set_rating(product.pk, avg, agg["n"])
    return avg, agg["n"]


@transaction.atomic
def create_purchase_review(user, purchase, *, rating, text=""):
    """Отзыв о продукте: покупка в статусе paid или completed, один на покупку."""
    rating, text = _clean(rating, text)
    if purchase.buyer_id != user.id:
        raise ServiceError("Отзыв оставляет покупатель.")
    if purchase.status not in ("paid", "completed"):
        raise ServiceError("Отзыв можно оставить только по оплаченной покупке.")
    if Review.objects.filter(purchase=purchase).exists():
        raise ServiceError("Вы уже оставили отзыв по этой покупке.")
    review = Review.objects.create(author=user, purchase=purchase, rating=rating, text=text)
    recalc_product_rating(purchase.product)
    notify(
        purchase.product.seller, f"Новый отзыв {rating}★ о «{purchase.product.title}».", f"/p/{purchase.product.slug}/"
    )
    return review


@transaction.atomic
def create_order_review(user, order, *, rating, text=""):
    """Отзыв о доработке: заказ в статусе accepted, один на заказ."""
    rating, text = _clean(rating, text)
    if order.buyer_id != user.id:
        raise ServiceError("Отзыв оставляет покупатель.")
    if order.status != "accepted":
        raise ServiceError("Отзыв о доработке можно оставить после приёмки работы.")
    if Review.objects.filter(order=order).exists():
        raise ServiceError("Вы уже оставили отзыв по этому заказу.")
    review = Review.objects.create(author=user, order=order, rating=rating, text=text)
    notify(order.product.seller, f"Новый отзыв {rating}★ о доработке по заказу №{order.pk}.", f"/orders/{order.pk}/")
    return review


def product_reviews(product):
    """Отзывы о продукте и о доработках по нему (раздельно)."""
    about_product = list(Review.objects.filter(purchase__product=product).select_related("author"))
    about_orders = list(Review.objects.filter(order__product=product).select_related("author"))
    return about_product, about_orders


def seller_rating(seller):
    """Рейтинг продавца: среднее по всем отзывам на его продукты и доработки, и их число."""
    agg = Review.objects.filter(Q(purchase__product__seller=seller) | Q(order__product__seller=seller)).aggregate(
        avg=Avg("rating"), n=Count("id")
    )
    return (Decimal(agg["avg"]).quantize(Decimal("0.01")) if agg["avg"] else None), agg["n"]


def review_for_purchase(purchase):
    return Review.objects.filter(purchase=purchase).first()


def review_for_order(order):
    return Review.objects.filter(order=order).first()

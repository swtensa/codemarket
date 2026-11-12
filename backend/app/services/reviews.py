"""Отзывы и рейтинг. Рейтинг продукта пересчитывается при сохранении отзыва о продукте,
рейтинг продавца — среднее по всем отзывам на его продукты и доработки."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ServiceError
from app.models import CustomOrder, Product, Purchase, Review, User
from app.services import catalog as catalog_services
from app.services.notifications import notify


def _clean(rating, text):
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise ServiceError("Поставьте оценку от 1 до 5.")
    if not 1 <= rating <= 5:
        raise ServiceError("Поставьте оценку от 1 до 5.")
    return rating, (text or "").strip()[:3000]


def recalc_product_rating(db: Session, product: Product):
    """Пересчитать rating_avg и rating_count продукта по отзывам о продукте."""
    avg, n = db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .join(Purchase, Purchase.id == Review.purchase_id)
        .where(Purchase.product_id == product.id)
    ).one()
    avg = Decimal(avg or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    catalog_services.set_rating(db, product.id, avg, n)
    db.refresh(product)
    return avg, n


def create_purchase_review(db: Session, user: User, purchase: Purchase, *, rating, text="") -> Review:
    """Отзыв о продукте: покупка в статусе paid или completed, один на покупку."""
    rating, text = _clean(rating, text)
    if purchase.buyer_id != user.id:
        raise ServiceError("Отзыв оставляет покупатель.")
    if purchase.status not in ("paid", "completed"):
        raise ServiceError("Отзыв можно оставить только по оплаченной покупке.")
    if review_for_purchase(db, purchase):
        raise ServiceError("Вы уже оставили отзыв по этой покупке.")
    review = Review(author_id=user.id, purchase_id=purchase.id, rating=rating, text=text)
    db.add(review)
    db.flush()
    recalc_product_rating(db, purchase.product)
    notify(
        db,
        purchase.product.seller,
        f"Новый отзыв {rating}★ о «{purchase.product.title}».",
        f"/p/{purchase.product.slug}/",
    )
    return review


def create_order_review(db: Session, user: User, order: CustomOrder, *, rating, text="") -> Review:
    """Отзыв о доработке: заказ в статусе accepted, один на заказ."""
    rating, text = _clean(rating, text)
    if order.buyer_id != user.id:
        raise ServiceError("Отзыв оставляет покупатель.")
    if order.status != "accepted":
        raise ServiceError("Отзыв о доработке можно оставить после приёмки работы.")
    if review_for_order(db, order):
        raise ServiceError("Вы уже оставили отзыв по этому заказу.")
    review = Review(author_id=user.id, order_id=order.id, rating=rating, text=text)
    db.add(review)
    db.flush()
    notify(
        db, order.product.seller, f"Новый отзыв {rating}★ о доработке по заказу №{order.id}.", f"/orders/{order.id}/"
    )
    return review


def product_reviews(db: Session, product: Product):
    """Отзывы о продукте и о доработках по нему (раздельно)."""
    about_product = db.scalars(
        select(Review)
        .join(Purchase, Purchase.id == Review.purchase_id)
        .where(Purchase.product_id == product.id)
        .options(selectinload(Review.author))
        .order_by(Review.created_at.desc())
    ).all()
    about_orders = db.scalars(
        select(Review)
        .join(CustomOrder, CustomOrder.id == Review.order_id)
        .where(CustomOrder.product_id == product.id)
        .options(selectinload(Review.author))
        .order_by(Review.created_at.desc())
    ).all()
    return list(about_product), list(about_orders)


def seller_rating(db: Session, seller: User):
    """Рейтинг продавца: среднее по всем отзывам на его продукты и доработки, и их число."""
    p1 = select(Product.id).where(Product.seller_id == seller.id)
    avg, n = db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .outerjoin(Purchase, Purchase.id == Review.purchase_id)
        .outerjoin(CustomOrder, CustomOrder.id == Review.order_id)
        .where(or_(Purchase.product_id.in_(p1), CustomOrder.product_id.in_(p1)))
    ).one()
    return (Decimal(avg).quantize(Decimal("0.01")) if avg else None), n


def review_for_purchase(db: Session, purchase: Purchase) -> Review | None:
    return db.scalar(select(Review).where(Review.purchase_id == purchase.id))


def review_for_order(db: Session, order: CustomOrder) -> Review | None:
    return db.scalar(select(Review).where(Review.order_id == order.id))

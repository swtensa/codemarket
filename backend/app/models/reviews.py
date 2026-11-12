"""Отзывы о продукте (по покупке) или о доработке (по заказу)."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Created


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="review_rating_1_5"),
        CheckConstraint(
            "(purchase_id IS NOT NULL AND order_id IS NULL) OR (purchase_id IS NULL AND order_id IS NOT NULL)",
            name="review_exactly_one_target",
        ),
        Index("uq_review_purchase", "purchase_id", unique=True, postgresql_where=text("purchase_id IS NOT NULL")),
        Index("uq_review_order", "order_id", unique=True, postgresql_where=text("order_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id", ondelete="CASCADE"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("custom_orders.id", ondelete="CASCADE"), nullable=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[Created]

    author: Mapped["User"] = relationship()  # noqa: F821
    purchase: Mapped["Purchase | None"] = relationship()  # noqa: F821
    order: Mapped["CustomOrder | None"] = relationship()  # noqa: F821


__all__ = ["Review"]

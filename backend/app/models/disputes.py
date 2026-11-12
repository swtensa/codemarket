"""Споры по покупке или по заказу (ровно одно из двух)."""

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Choices, Created, Money, OptDateTime


class ReasonType(Choices):
    NOT_WORKING = "not_working"
    NOT_AS_DESCRIBED = "not_as_described"
    OTHER = "other"
    SELLER_BLOCKED = "seller_blocked"
    LABELS = {
        NOT_WORKING: "Не работает",
        NOT_AS_DESCRIBED: "Не соответствует описанию",
        OTHER: "Другое",
        SELLER_BLOCKED: "Продавец заблокирован",
    }


class DisputeStatus(Choices):
    OPEN = "open"
    CLOSED = "closed"
    LABELS = {OPEN: "Открыт", CLOSED: "Закрыт"}


class Resolution(Choices):
    SELLER = "seller"
    REFUND = "refund"
    PARTIAL = "partial"
    LABELS = {SELLER: "В пользу продавца", REFUND: "Полный возврат", PARTIAL: "Частичный возврат"}


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint(
            "(purchase_id IS NOT NULL AND order_id IS NULL) OR (purchase_id IS NULL AND order_id IS NOT NULL)",
            name="dispute_exactly_one_target",
        ),
        Index("uq_dispute_purchase", "purchase_id", unique=True, postgresql_where=text("purchase_id IS NOT NULL")),
        Index("uq_dispute_order", "order_id", unique=True, postgresql_where=text("order_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("custom_orders.id", ondelete="RESTRICT"), nullable=True)
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason_type: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=DisputeStatus.OPEN)
    resolution: Mapped[str] = mapped_column(String(10), default="")
    refund_amount: Mapped[Money] = mapped_column(default=Decimal("0"))
    admin_comment: Mapped[str] = mapped_column(Text, default="")
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    opened_at: Mapped[Created]
    closed_at: Mapped[OptDateTime]

    purchase: Mapped["Purchase | None"] = relationship()  # noqa: F821
    order: Mapped["CustomOrder | None"] = relationship()  # noqa: F821
    opened_by: Mapped["User"] = relationship(foreign_keys=[opened_by_id])  # noqa: F821
    admin: Mapped["User | None"] = relationship(foreign_keys=[admin_id])  # noqa: F821


__all__ = ["Dispute", "ReasonType", "DisputeStatus", "Resolution"]

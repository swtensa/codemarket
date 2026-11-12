"""Платежи у провайдера: за покупку продукта или за заказ доработки."""

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Choices, Created, Money


class PaymentStatus(Choices):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    LABELS = {
        PENDING: "Ожидает оплаты",
        SUCCEEDED: "Оплачен",
        CANCELED: "Отменён",
        REFUNDED: "Возвращён",
        PARTIALLY_REFUNDED: "Возвращён частично",
    }


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("purchase_id IS NOT NULL OR order_id IS NOT NULL", name="payment_has_purchase_or_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_orders.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    amount: Mapped[Money]
    external_id: Mapped[str] = mapped_column(String(100), default="", index=True)
    idempotence_key: Mapped[str] = mapped_column(String(64), unique=True)
    confirmation_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.PENDING)
    refund_amount: Mapped[Money] = mapped_column(default=Decimal("0"))
    created_at: Mapped[Created]

    purchase: Mapped["Purchase | None"] = relationship()  # noqa: F821
    order: Mapped["CustomOrder | None"] = relationship()  # noqa: F821


__all__ = ["Payment", "PaymentStatus"]

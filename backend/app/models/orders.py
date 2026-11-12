"""Заказы на доработку (и вопросы продавцу) и сообщения чата."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Choices, Created, Money, OptDateTime

ORDER_MIN_PRICE = 300
ORDER_MIN_DAYS = 1
ORDER_MAX_DAYS = 60


class OrderKind(Choices):
    QUESTION = "question"
    WITH_PURCHASE = "with_purchase"
    CUSTOMIZATION = "customization"
    LABELS = {
        QUESTION: "Вопрос продавцу",
        WITH_PURCHASE: "Покупка с доработкой",
        CUSTOMIZATION: "Доработка купленного продукта",
    }


class OrderStatus(Choices):
    NEW = "new"
    OFFER = "offer"
    AWAITING_PAYMENT = "awaiting_payment"
    IN_WORK = "in_work"
    SUBMITTED = "submitted"
    REVISION = "revision"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    DISPUTE = "dispute"
    LABELS = {
        NEW: "Новый",
        OFFER: "Предложение",
        AWAITING_PAYMENT: "Ожидает оплаты",
        IN_WORK: "В работе",
        SUBMITTED: "Сдан",
        REVISION: "На доработке",
        ACCEPTED: "Принят",
        CANCELLED: "Отменён",
        REFUNDED: "Возврат",
        PARTIALLY_REFUNDED: "Частичный возврат",
        DISPUTE: "Спор",
    }


class CustomOrder(Base):
    """Заказ на доработку. Вопрос до покупки — тоже заказ (kind=question) без оплаты."""

    __tablename__ = "custom_orders"
    __table_args__ = (
        CheckConstraint(f"price IS NULL OR price >= {ORDER_MIN_PRICE}", name="order_price_min"),
        CheckConstraint(
            f"days IS NULL OR (days >= {ORDER_MIN_DAYS} AND days <= {ORDER_MAX_DAYS})", name="order_days_range"
        ),
        Index("ix_orders_status_submitted", "status", "submitted_at"),
        Index("ix_orders_buyer_kind", "buyer_id", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    purchase_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    task: Mapped[str] = mapped_column(Text)
    price: Mapped[Money | None]
    days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    deadline: Mapped[OptDateTime]
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.NEW)
    revisions: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[Created]
    paid_at: Mapped[OptDateTime]
    submitted_at: Mapped[OptDateTime]

    buyer: Mapped["User"] = relationship()  # noqa: F821
    product: Mapped["Product"] = relationship()  # noqa: F821
    purchase: Mapped["Purchase | None"] = relationship()  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(
        back_populates="order", order_by="(Message.created_at, Message.id)", cascade="all, delete-orphan"
    )

    @property
    def seller_id(self) -> int:
        return self.product.seller_id


class Message(Base):
    """Сообщение в чате заказа. author пустой — системное сообщение (смена статуса)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("custom_orders.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    attachment: Mapped[str] = mapped_column(String(300), default="")  # путь внутри storage/private
    is_result: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[Created]

    order: Mapped[CustomOrder] = relationship(back_populates="messages")
    author: Mapped["User | None"] = relationship()  # noqa: F821

    @property
    def attachment_name(self) -> str:
        return self.attachment.rsplit("/", 1)[-1] if self.attachment else ""


__all__ = ["CustomOrder", "Message", "OrderKind", "OrderStatus", "ORDER_MIN_PRICE", "ORDER_MIN_DAYS", "ORDER_MAX_DAYS"]

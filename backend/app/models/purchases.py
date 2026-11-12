"""Покупки продуктов."""

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Choices, Created, Money, OptDateTime


class PurchaseStatus(Choices):
    PENDING = "pending"
    PAID = "paid"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTE = "dispute"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    LABELS = {
        PENDING: "Ожидает оплаты",
        PAID: "Оплачена",
        COMPLETED: "Завершена",
        CANCELLED: "Отменена",
        DISPUTE: "Спор",
        REFUNDED: "Возврат",
        PARTIALLY_REFUNDED: "Частичный возврат",
    }


class AccessStatus(Choices):
    NONE = "none"
    INVITED = "invited"
    GRANTED = "granted"
    REVOKED = "revoked"
    LABELS = {NONE: "Не выдан", INVITED: "Приглашение отправлено", GRANTED: "Доступ есть", REVOKED: "Отозван"}


class Purchase(Base):
    __tablename__ = "purchases"
    __table_args__ = (
        Index(
            "uq_purchase_active_buyer_product",
            "buyer_id",
            "product_id",
            unique=True,
            postgresql_where=text("status IN ('paid', 'completed')"),
        ),
        Index("ix_purchases_status_paid", "status", "paid_at"),
        Index("ix_purchases_product_status", "product_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_versions.id", ondelete="SET NULL"), nullable=True
    )
    price: Mapped[Money]
    commission: Mapped[Money]
    status: Mapped[str] = mapped_column(String(20), default=PurchaseStatus.PENDING)
    access_status: Mapped[str] = mapped_column(String(10), default=AccessStatus.NONE)
    access_granted_at: Mapped[OptDateTime]
    access_revoked_at: Mapped[OptDateTime]
    license_version: Mapped[str] = mapped_column(String(10), default="")
    created_at: Mapped[Created]
    paid_at: Mapped[OptDateTime]

    buyer: Mapped["User"] = relationship()  # noqa: F821
    product: Mapped["Product"] = relationship()  # noqa: F821
    version: Mapped["ProductVersion | None"] = relationship()  # noqa: F821

    @property
    def seller_amount(self):
        return self.price - self.commission


__all__ = ["Purchase", "PurchaseStatus", "AccessStatus"]

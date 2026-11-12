"""Операции баланса продавца. Баланс считается только из операций (get_balance).

income — начисление продавцу (цена − комиссия), положительная сумма;
commission — комиссия платформы с этой продажи (для отчётов, в баланс продавца не входит);
refund_reversal — отмена начисления при возврате, отрицательная сумма;
payout — вывод денег, отрицательная сумма.
"""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Choices, Created, Money, OptDateTime


class OpKind(Choices):
    INCOME = "income"
    COMMISSION = "commission"
    REFUND_REVERSAL = "refund_reversal"
    PAYOUT = "payout"
    LABELS = {
        INCOME: "Начисление",
        COMMISSION: "Комиссия платформы",
        REFUND_REVERSAL: "Отмена начисления",
        PAYOUT: "Вывод",
    }


class OpStatus(Choices):
    HELD = "held"
    AVAILABLE = "available"
    REQUESTED = "requested"
    PAID = "paid"
    CANCELLED = "cancelled"
    LABELS = {
        HELD: "Удержано",
        AVAILABLE: "Доступно",
        REQUESTED: "Заявка на вывод",
        PAID: "Выплачено",
        CANCELLED: "Отменено",
    }


class BalanceOperation(Base):
    __tablename__ = "balance_operations"
    __table_args__ = (
        Index("ix_balance_user_status", "user_id", "status"),
        Index("ix_balance_status_available", "status", "available_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    purchase_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_orders.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Money]
    status: Mapped[str] = mapped_column(String(10))
    available_at: Mapped[OptDateTime]
    requisites: Mapped[str] = mapped_column(Text, default="")
    processed_at: Mapped[OptDateTime]
    created_at: Mapped[Created]

    user: Mapped["User"] = relationship()  # noqa: F821
    purchase: Mapped["Purchase | None"] = relationship()  # noqa: F821
    order: Mapped["CustomOrder | None"] = relationship()  # noqa: F821


__all__ = ["BalanceOperation", "OpKind", "OpStatus"]

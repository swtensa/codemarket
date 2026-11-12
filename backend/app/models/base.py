"""Общие типы колонок."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import mapped_column

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


Money = Annotated[Decimal, mapped_column(Numeric(12, 2))]
Created = Annotated[datetime, mapped_column(DateTime(timezone=True), default=utcnow)]
OptDateTime = Annotated[datetime | None, mapped_column(DateTime(timezone=True), nullable=True)]


class Choices:
    """Набор значений статуса с подписями: Status.PAID == "paid", Status.label("paid") == "Оплачена"."""

    LABELS: dict[str, str] = {}

    @classmethod
    def label(cls, value: str | None) -> str:
        return cls.LABELS.get(value or "", value or "")

    @classmethod
    def values(cls) -> list[str]:
        return list(cls.LABELS)


__all__ = ["Base", "Money", "Created", "OptDateTime", "Choices", "utcnow"]

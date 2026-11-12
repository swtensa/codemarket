"""Общие схемы: суммы строкой с двумя знаками, страницы списков."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer

Money = Annotated[Decimal, PlainSerializer(lambda v: f"{Decimal(v):.2f}", return_type=str, when_used="json")]
T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    pages: int


class Ok(BaseModel):
    ok: bool = True
    message: str = ""


class Redirect(BaseModel):
    """Ответ «перейти по адресу» (оплата, ссылка уведомления)."""

    url: str


__all__ = ["Money", "Schema", "Page", "Ok", "Redirect", "datetime"]

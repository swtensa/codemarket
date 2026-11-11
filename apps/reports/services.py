"""Статистика продавца и отчёты администратора (полностью реализуются на этапе 11)."""

from decimal import Decimal


def seller_tiles(user):
    """Плитки кабинета продавца: выручка за месяц, продажи, просмотры, рейтинг."""
    return {"revenue_month": Decimal("0"), "sales": 0, "views": 0, "rating": None}

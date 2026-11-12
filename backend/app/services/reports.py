"""Статистика продавца и отчёты администратора (с выгрузкой в Excel)."""

import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import BalanceOperation, Category, CustomOrder, Payment, Product, ProductView, Purchase, User
from app.models.base import utcnow

SOLD = ["paid", "completed", "dispute", "partially_refunded"]
MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def tz():
    return ZoneInfo(settings.time_zone)


def parse_period(date_from: str | None, date_to: str | None, default_days: int = 180) -> tuple[date, date]:
    """Период из параметров from/to (ГГГГ-ММ-ДД); по умолчанию последние полгода."""
    today = utcnow().astimezone(tz()).date()
    try:
        d_to = date.fromisoformat(date_to) if date_to else today
    except ValueError:
        d_to = today
    try:
        d_from = date.fromisoformat(date_from) if date_from else d_to - timedelta(days=default_days)
    except ValueError:
        d_from = d_to - timedelta(days=default_days)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to


def _bounds(d_from: date, d_to: date):
    return (
        datetime.combine(d_from, time.min, tzinfo=tz()),
        datetime.combine(d_to + timedelta(days=1), time.min, tzinfo=tz()),
    )


def month_keys(d_from: date, d_to: date):
    out, y, m = [], d_from.year, d_from.month
    while (y, m) <= (d_to.year, d_to.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_label(y: int, m: int) -> str:
    return f"{MONTHS[m - 1]} {y}"


def _by_month(db: Session, column, *where, value=None) -> dict:
    """{(год, месяц): число или сумма} с группировкой по месяцам местного времени."""
    month = func.date_trunc("month", func.timezone(settings.time_zone, column))
    agg = func.sum(value) if value is not None else func.count()
    rows = db.execute(select(month, agg).where(*where).group_by(month)).all()
    return {(m.year, m.month): v or 0 for m, v in rows}


# ---------------------------------------------------------------- продавец


def seller_tiles(db: Session, user: User) -> dict:
    """Плитки кабинета продавца: выручка за текущий месяц, продажи, просмотры, рейтинг."""
    from app.services.reviews import seller_rating

    start = utcnow().astimezone(tz()).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    revenue = db.scalar(
        select(func.coalesce(func.sum(BalanceOperation.amount), 0)).where(
            BalanceOperation.user_id == user.id,
            BalanceOperation.kind.in_(["income", "refund_reversal"]),
            BalanceOperation.created_at >= start,
            BalanceOperation.status != "cancelled",
        )
    )
    products = select(Product.id).where(Product.seller_id == user.id)
    sales = db.scalar(select(func.count()).where(Purchase.product_id.in_(products), Purchase.status.in_(SOLD)))
    views = db.scalar(select(func.count()).where(ProductView.product_id.in_(products)))
    rating, _ = seller_rating(db, user)
    return {"revenue_month": Decimal(revenue or 0), "sales": sales or 0, "views": views or 0, "rating": rating}


def seller_stats(db: Session, user: User, d_from: date, d_to: date) -> dict:
    """Продажи и выручка по месяцам, просмотры, конверсия, средний рейтинг, таблица по продуктам."""
    from app.services.reviews import seller_rating

    start, end = _bounds(d_from, d_to)
    products_q = select(Product.id).where(Product.seller_id == user.id)
    purch = [
        Purchase.product_id.in_(products_q),
        Purchase.status.in_(SOLD),
        Purchase.paid_at >= start,
        Purchase.paid_at < end,
    ]
    views = [ProductView.product_id.in_(products_q), ProductView.viewed_at >= start, ProductView.viewed_at < end]
    income = [
        BalanceOperation.user_id == user.id,
        BalanceOperation.kind.in_(["income", "refund_reversal"]),
        BalanceOperation.created_at >= start,
        BalanceOperation.created_at < end,
        BalanceOperation.status != "cancelled",
    ]
    keys = month_keys(d_from, d_to)
    sales_m = _by_month(db, Purchase.paid_at, *purch)
    revenue_m = _by_month(db, BalanceOperation.created_at, *income, value=BalanceOperation.amount)
    views_m = _by_month(db, ProductView.viewed_at, *views)

    rows = []
    for p in db.scalars(select(Product).where(Product.seller_id == user.id).order_by(Product.title)):
        v = db.scalar(select(func.count()).where(ProductView.product_id == p.id, *views[1:])) or 0
        s = db.scalar(select(func.count()).where(Purchase.product_id == p.id, *purch[1:])) or 0
        rev = db.scalar(
            select(func.coalesce(func.sum(BalanceOperation.amount), 0))
            .outerjoin(Purchase, Purchase.id == BalanceOperation.purchase_id)
            .outerjoin(CustomOrder, CustomOrder.id == BalanceOperation.order_id)
            .where(*income, or_(Purchase.product_id == p.id, CustomOrder.product_id == p.id))
        )
        rows.append(
            {
                "product_id": p.id,
                "title": p.title,
                "slug": p.slug,
                "status": p.status,
                "views": v,
                "sales": s,
                "revenue": Decimal(rev or 0),
                "conversion": (s / v * 100) if v else None,
                "rating": float(p.rating_avg) if p.rating_count else None,
            }
        )
    total_views = db.scalar(select(func.count()).where(*views)) or 0
    total_sales = db.scalar(select(func.count()).where(*purch)) or 0
    rating, rating_n = seller_rating(db, user)
    return {
        "labels": [month_label(y, m) for y, m in keys],
        "sales": [sales_m.get(k, 0) for k in keys],
        "revenue": [float(revenue_m.get(k, 0)) for k in keys],
        "views": [views_m.get(k, 0) for k in keys],
        "total_views": total_views,
        "total_sales": total_sales,
        "total_revenue": sum((Decimal(x) for x in revenue_m.values()), Decimal("0")),
        "conversion": (total_sales / total_views * 100) if total_views else None,
        "rating": rating,
        "rating_n": rating_n,
        "products": rows,
    }


# ---------------------------------------------------------------- администратор


def admin_report(db: Session, d_from: date, d_to: date) -> dict:
    """Сводка за период по месяцам и по разделам. Пустой период: is_empty=True."""
    start, end = _bounds(d_from, d_to)
    users = [User.created_at >= start, User.created_at < end]
    published = [Product.published_at >= start, Product.published_at < end]
    purchases = [Purchase.status.in_([*SOLD, "refunded"]), Purchase.paid_at >= start, Purchase.paid_at < end]
    orders = [CustomOrder.paid_at >= start, CustomOrder.paid_at < end]
    payments = [
        Payment.status.in_(["succeeded", "refunded", "partially_refunded"]),
        Payment.created_at >= start,
        Payment.created_at < end,
    ]
    commission = [
        BalanceOperation.kind == "commission",
        BalanceOperation.created_at >= start,
        BalanceOperation.created_at < end,
    ]

    keys = month_keys(d_from, d_to)
    series = {
        "users": _by_month(db, User.created_at, *users),
        "products": _by_month(db, Product.published_at, *published),
        "purchases": _by_month(db, Purchase.paid_at, *purchases),
        "orders": _by_month(db, CustomOrder.paid_at, *orders),
        "turnover": _by_month(db, Payment.created_at, *payments, value=Payment.amount),
        "refunds": _by_month(db, Payment.created_at, *payments, value=Payment.refund_amount),
        "income": _by_month(db, BalanceOperation.created_at, *commission, value=BalanceOperation.amount),
    }
    by_month = []
    for k in keys:
        row = {"label": month_label(*k)}
        for name, data in series.items():
            row[name] = data.get(k, 0)
        row["turnover"] = Decimal(row["turnover"]) - Decimal(row.pop("refunds"))
        row["income"] = Decimal(row["income"])
        by_month.append(row)

    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    by_section = []
    for section in db.scalars(select(Category).where(Category.parent_id.is_(None)).order_by(Category.position)):
        sub = select(Category.id).where(Category.parent_id == section.id)
        sec_products = select(Product.id).where(Product.category_id.in_(sub))
        pay = db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0), func.coalesce(func.sum(Payment.refund_amount), 0))
            .outerjoin(Purchase, Purchase.id == Payment.purchase_id)
            .outerjoin(CustomOrder, CustomOrder.id == Payment.order_id)
            .where(*payments, or_(Purchase.product_id.in_(sec_products), CustomOrder.product_id.in_(sec_products)))
        ).one()
        income = db.scalar(
            select(func.coalesce(func.sum(BalanceOperation.amount), 0))
            .outerjoin(Purchase, Purchase.id == BalanceOperation.purchase_id)
            .outerjoin(CustomOrder, CustomOrder.id == BalanceOperation.order_id)
            .where(*commission, or_(Purchase.product_id.in_(sec_products), CustomOrder.product_id.in_(sec_products)))
        )
        by_section.append(
            {
                "label": section.name,
                "products": count(Product, Product.category_id.in_(sub), *published),
                "purchases": count(Purchase, Purchase.product_id.in_(sec_products), *purchases),
                "orders": count(CustomOrder, CustomOrder.product_id.in_(sec_products), *orders),
                "turnover": Decimal(pay[0]) - Decimal(pay[1]),
                "income": Decimal(income or 0),
            }
        )
    totals = {
        "users": count(User, *users),
        "products": count(Product, *published),
        "purchases": count(Purchase, *purchases),
        "orders": count(CustomOrder, *orders),
        "turnover": sum((r["turnover"] for r in by_month), Decimal("0")),
        "income": Decimal(
            db.scalar(select(func.coalesce(func.sum(BalanceOperation.amount), 0)).where(*commission)) or 0
        ),
    }
    is_empty = not any(totals.values())
    return {"by_month": by_month, "by_section": by_section, "totals": totals, "is_empty": is_empty}


def admin_report_xlsx(db: Session, d_from: date, d_to: date) -> bytes:
    """Выгрузка отчёта администратора в Excel (openpyxl). Возвращает байты файла."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    rep = admin_report(db, d_from, d_to)
    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="293941")
    head_font = Font(bold=True, color="FFFFFF")
    money_fmt = '#,##0.00 "₽"'

    def sheet(ws, title, header, rows, money_cols):
        ws.title = title
        ws.append([f"CodeMarket — отчёт за период {d_from:%d.%m.%Y}–{d_to:%d.%m.%Y}"])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([])
        ws.append(header)
        for c in range(1, len(header) + 1):
            cell = ws.cell(row=3, column=c)
            cell.fill, cell.font = head_fill, head_font
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        if not rows:
            ws.append(["Нет данных"])
        for r in rows:
            ws.append(r)
        for row in ws.iter_rows(min_row=4, max_row=ws.max_row):
            for c in money_cols:
                if len(row) > c and isinstance(row[c].value, int | float | Decimal):
                    row[c].number_format = money_fmt
        for i, _ in enumerate(header, 1):
            ws.column_dimensions[get_column_letter(i)].width = 18 if i > 1 else 22

    header = ["Месяц", "Новые пользователи", "Опубликовано продуктов", "Покупки", "Заказы", "Оборот", "Доход платформы"]
    month_rows = [
        [r["label"], r["users"], r["products"], r["purchases"], r["orders"], float(r["turnover"]), float(r["income"])]
        for r in rep["by_month"]
    ]
    t = rep["totals"]
    if not rep["is_empty"]:
        month_rows.append(
            ["Итого", t["users"], t["products"], t["purchases"], t["orders"], float(t["turnover"]), float(t["income"])]
        )
    sheet(wb.active, "По месяцам", header, [] if rep["is_empty"] else month_rows, [5, 6])
    sec_header = ["Раздел", "Опубликовано продуктов", "Покупки", "Заказы", "Оборот", "Доход платформы"]
    sec_rows = [
        [r["label"], r["products"], r["purchases"], r["orders"], float(r["turnover"]), float(r["income"])]
        for r in rep["by_section"]
    ]
    sheet(wb.create_sheet(), "По разделам", sec_header, [] if rep["is_empty"] else sec_rows, [4, 5])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

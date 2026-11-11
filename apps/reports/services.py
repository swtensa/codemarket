"""Статистика продавца и отчёты администратора."""

import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.accounts.models import User
from apps.balance.models import BalanceOperation
from apps.catalog.models import Category, Product, ProductView
from apps.orders.models import CustomOrder
from apps.payments.models import Payment
from apps.purchases.models import Purchase

SOLD = ["paid", "completed", "dispute", "partially_refunded"]
MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def parse_period(params, default_days=180):
    """Период из GET-параметров from/to (ГГГГ-ММ-ДД); по умолчанию последние полгода."""
    today = timezone.localdate()
    try:
        d_to = date.fromisoformat(params.get("to", "")) if params.get("to") else today
    except ValueError:
        d_to = today
    try:
        d_from = (
            date.fromisoformat(params.get("from", "")) if params.get("from") else d_to - timedelta(days=default_days)
        )
    except ValueError:
        d_from = d_to - timedelta(days=default_days)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to


def _bounds(d_from, d_to):
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(d_from, time.min), tz),
        timezone.make_aware(datetime.combine(d_to + timedelta(days=1), time.min), tz),
    )


def month_keys(d_from, d_to):
    out, y, m = [], d_from.year, d_from.month
    while (y, m) <= (d_to.year, d_to.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_label(y, m):
    return f"{MONTHS[m - 1]} {y}"


def _by_month(qs, field, value=None):
    """{(год, месяц): число или сумма}."""
    tz = timezone.get_current_timezone()
    agg = Sum(value) if value else Count("id")
    rows = qs.annotate(m=TruncMonth(field, tzinfo=tz)).values("m").annotate(v=agg).values_list("m", "v")
    return {(m.year, m.month): v or 0 for m, v in rows}


# ---------------------------------------------------------------- продавец


def seller_tiles(user):
    """Плитки кабинета продавца: выручка за текущий месяц, продажи, просмотры, рейтинг."""
    from apps.reviews.services import seller_rating

    start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    revenue = BalanceOperation.objects.filter(
        user=user, kind__in=["income", "refund_reversal"], created_at__gte=start
    ).exclude(status="cancelled").aggregate(s=Sum("amount"))["s"] or Decimal("0")
    sales = Purchase.objects.filter(product__seller=user, status__in=SOLD + ["refunded"]).count()
    views = ProductView.objects.filter(product__seller=user).count()
    rating, _ = seller_rating(user)
    return {"revenue_month": revenue, "sales": sales, "views": views, "rating": rating}


def seller_stats(user, d_from, d_to):
    """Продажи и выручка по месяцам, просмотры, конверсия, средний рейтинг, таблица по продуктам."""
    from apps.reviews.services import seller_rating

    start, end = _bounds(d_from, d_to)
    purchases = Purchase.objects.filter(product__seller=user, status__in=SOLD, paid_at__gte=start, paid_at__lt=end)
    views = ProductView.objects.filter(product__seller=user, viewed_at__gte=start, viewed_at__lt=end)
    income = BalanceOperation.objects.filter(
        user=user, kind__in=["income", "refund_reversal"], created_at__gte=start, created_at__lt=end
    ).exclude(status="cancelled")

    keys = month_keys(d_from, d_to)
    sales_m = _by_month(purchases, "paid_at")
    revenue_m = _by_month(income, "created_at", "amount")
    views_m = _by_month(views, "viewed_at")

    products = []
    for p in Product.objects.filter(seller=user).order_by("title"):
        v = views.filter(product=p).count()
        s = purchases.filter(product=p).count()
        rev = income.filter(Q(purchase__product=p) | Q(order__product=p)).aggregate(x=Sum("amount"))["x"] or 0
        products.append(
            {
                "product": p,
                "views": v,
                "sales": s,
                "revenue": rev,
                "conversion": (s / v * 100) if v else None,
                "rating": p.rating_avg if p.rating_count else None,
            }
        )
    total_views, total_sales = views.count(), purchases.count()
    rating, rating_n = seller_rating(user)
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
        "products": products,
    }


# ---------------------------------------------------------------- администратор


def admin_report(d_from, d_to):
    """Сводка за период по месяцам и по разделам. Пустой период: rows пустые, is_empty=True."""
    start, end = _bounds(d_from, d_to)
    users = User.objects.filter(created_at__gte=start, created_at__lt=end)
    published = Product.objects.filter(published_at__gte=start, published_at__lt=end)
    purchases = Purchase.objects.filter(status__in=SOLD + ["refunded"], paid_at__gte=start, paid_at__lt=end)
    orders = CustomOrder.objects.filter(paid_at__gte=start, paid_at__lt=end)
    payments = Payment.objects.filter(
        status__in=["succeeded", "refunded", "partially_refunded"], created_at__gte=start, created_at__lt=end
    )
    commission = BalanceOperation.objects.filter(kind="commission", created_at__gte=start, created_at__lt=end)

    keys = month_keys(d_from, d_to)
    series = {
        "users": _by_month(users, "created_at"),
        "products": _by_month(published, "published_at"),
        "purchases": _by_month(purchases, "paid_at"),
        "orders": _by_month(orders, "paid_at"),
        "turnover": _by_month(payments, "created_at", "amount"),
        "refunds": _by_month(payments, "created_at", "refund_amount"),
        "income": _by_month(commission, "created_at", "amount"),
    }
    by_month = []
    for k in keys:
        row = {"label": month_label(*k)}
        for name, data in series.items():
            row[name] = data.get(k, 0)
        row["turnover"] = Decimal(row["turnover"]) - Decimal(row.pop("refunds"))
        by_month.append(row)

    by_section = []
    for section in Category.objects.filter(parent__isnull=True).order_by("position"):
        in_sec = Q(product__category__parent=section)
        sec_purchases = purchases.filter(in_sec)
        sec_orders = orders.filter(in_sec)
        by_section.append(
            {
                "label": section.name,
                "products": published.filter(category__parent=section).count(),
                "purchases": sec_purchases.count(),
                "orders": sec_orders.count(),
                "turnover": (sec_purchases.aggregate(s=Sum("price"))["s"] or 0)
                + (sec_orders.aggregate(s=Sum("price"))["s"] or 0),
                "income": commission.filter(
                    Q(purchase__product__category__parent=section) | Q(order__product__category__parent=section)
                ).aggregate(s=Sum("amount"))["s"]
                or 0,
            }
        )
    totals = {
        "users": users.count(),
        "products": published.count(),
        "purchases": purchases.count(),
        "orders": orders.count(),
        "turnover": sum((r["turnover"] for r in by_month), Decimal("0")),
        "income": commission.aggregate(s=Sum("amount"))["s"] or Decimal("0"),
    }
    is_empty = not any(v for k, v in totals.items())
    return {"by_month": by_month, "by_section": by_section, "totals": totals, "is_empty": is_empty}


def admin_report_xlsx(d_from, d_to):
    """Выгрузка отчёта администратора в Excel (openpyxl). Возвращает байты файла."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    rep = admin_report(d_from, d_to)
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

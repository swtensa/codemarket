"""Статистика продавца, отчёты администратора и выгрузка Excel."""

import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.models import ProductView, Purchase
from app.models.base import utcnow
from app.services import reports as services
from app.services.balance import credit_sale
from tests.factories import make_admin, make_product, make_user


@pytest.fixture
def sale(db):
    product = make_product(db, price=Decimal("1000"))
    p = Purchase(
        buyer_id=make_user(db).id, product_id=product.id, price=1000, commission=100, status="paid", paid_at=utcnow()
    )
    db.add(p)
    db.flush()
    credit_sale(db, p)
    for i in range(4):
        db.add(ProductView(product_id=product.id, session_key=f"s{i}"))
    db.flush()
    return p


def today():
    return utcnow().astimezone(services.tz()).date()


def test_seller_stats(api, db, sale):
    seller = sale.product.seller
    stats = services.seller_stats(db, seller, today() - timedelta(days=30), today())
    assert stats["total_sales"] == 1 and stats["total_views"] == 4
    assert stats["conversion"] == 25.0
    assert stats["total_revenue"] == Decimal("900.00")
    assert stats["products"][0]["revenue"] == Decimal("900.00")
    api.login(seller)
    data = api.get("/api/seller/stats").json()
    assert data["total_sales"] == 1 and data["labels"] and len(data["labels"]) == len(data["sales"])
    assert data["products"][0]["conversion"] == 25.0
    tiles = services.seller_tiles(db, seller)
    assert tiles["revenue_month"] == Decimal("900.00") and tiles["sales"] == 1 and tiles["views"] == 4


def test_admin_report_and_excel(api, db, sale):
    rep = services.admin_report(db, today() - timedelta(days=10), today())
    assert not rep["is_empty"]
    assert rep["totals"]["purchases"] == 1 and rep["totals"]["income"] == Decimal("100.00")
    api.login(make_admin(db))
    data = api.get("/api/admin/reports").json()
    assert data["totals"]["income"] == "100.00" and not data["is_empty"]
    resp = api.get(f"/api/admin/reports/excel?date_from={today() - timedelta(days=10)}&date_to={today()}")
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in resp.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["По месяцам", "По разделам"]
    assert wb["По месяцам"]["A3"].value == "Месяц"


def test_empty_period_says_no_data(api, db):
    assert services.admin_report(db, date(2001, 1, 1), date(2001, 2, 1))["is_empty"]
    api.login(make_admin(db))
    assert api.get("/api/admin/reports?date_from=2001-01-01&date_to=2001-02-01").json()["is_empty"] is True
    data = api.get("/api/admin/reports/excel?date_from=2001-01-01&date_to=2001-02-01").content
    assert load_workbook(io.BytesIO(data))["По месяцам"]["A4"].value == "Нет данных"


def test_reports_forbidden_for_non_admin(api, db):
    api.login(make_user(db))
    assert api.get("/api/admin/reports").status_code == 403
    assert api.get("/api/admin/reports/excel").status_code == 403
    assert api.get("/api/seller/stats").status_code == 403  # без GitHub


def test_parse_period_defaults_and_swap():
    d_from, d_to = services.parse_period("2026-05-01", "2026-01-01")
    assert d_from < d_to
    d_from, d_to = services.parse_period("bad", None)
    assert d_to == today() and (d_to - d_from).days == 180
    assert services.month_label(2026, 11) == "ноя 2026"

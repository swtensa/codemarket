import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from openpyxl import load_workbook

from apps.balance.services import credit_sale
from apps.catalog.models import ProductView
from apps.purchases.models import Purchase
from apps.reports import services
from tests.factories import ProductFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def sale():
    product = ProductFactory(price=Decimal("1000"))
    p = Purchase.objects.create(
        buyer=UserFactory(), product=product, price=1000, commission=100, status="paid", paid_at=timezone.now()
    )
    credit_sale(p)
    for i in range(4):
        ProductView.objects.create(product=product, session_key=f"s{i}")
    return p


def test_seller_stats(client, sale):
    seller = sale.product.seller
    today = timezone.localdate()
    stats = services.seller_stats(seller, today - timedelta(days=30), today)
    assert stats["total_sales"] == 1 and stats["total_views"] == 4
    assert stats["conversion"] == 25.0
    assert stats["total_revenue"] == Decimal("900.00")
    assert stats["products"][0]["revenue"] == Decimal("900.00")
    client.force_login(seller)
    resp = client.get("/sell/stats/")
    assert resp.status_code == 200 and "salesChart" in resp.content.decode()
    tiles = services.seller_tiles(seller)
    assert tiles["revenue_month"] == Decimal("900.00") and tiles["sales"] == 1 and tiles["views"] == 4


def test_admin_report_and_excel(client, sale, admin_user):
    today = timezone.localdate()
    rep = services.admin_report(today - timedelta(days=10), today)
    assert not rep["is_empty"]
    assert rep["totals"]["purchases"] == 1 and rep["totals"]["income"] == Decimal("100.00")
    client.force_login(admin_user)
    assert "Доход платформы" in client.get("/moderation/reports/").content.decode()
    resp = client.get(f"/moderation/reports/excel/?from={today - timedelta(days=10)}&to={today}")
    assert resp["Content-Type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["По месяцам", "По разделам"]
    assert wb["По месяцам"]["A3"].value == "Месяц"


def test_empty_period_says_no_data(client, admin_user):
    rep = services.admin_report(date(2001, 1, 1), date(2001, 2, 1))
    assert rep["is_empty"]
    client.force_login(admin_user)
    resp = client.get("/moderation/reports/?from=2001-01-01&to=2001-02-01")
    assert "Нет данных" in resp.content.decode()
    data = client.get("/moderation/reports/excel/?from=2001-01-01&to=2001-02-01").content
    assert load_workbook(io.BytesIO(data))["По месяцам"]["A4"].value == "Нет данных"


def test_reports_forbidden_for_non_admin(client, user):
    client.force_login(user)
    assert client.get("/moderation/reports/").status_code == 403
    assert client.get("/moderation/reports/excel/").status_code == 403


def test_parse_period_defaults_and_swap():
    from django.http import QueryDict

    d_from, d_to = services.parse_period(QueryDict("from=2026-05-01&to=2026-01-01"))
    assert d_from < d_to
    d_from, d_to = services.parse_period(QueryDict("from=bad"))
    assert d_to == timezone.localdate()

import pytest
from django.core.management import call_command

from apps.catalog.models import Product
from apps.disputes.models import Dispute
from apps.orders.models import CustomOrder
from apps.purchases.models import Purchase
from apps.versions.models import ProductVersion

pytestmark = pytest.mark.django_db


def test_seed_demo_fills_every_screen(settings, tmp_path):
    settings.GITHUB_FAKE_ROOT = tmp_path / "repos"
    call_command("seed_demo")
    assert Product.objects.filter(status="published").count() == 20
    assert set(ProductVersion.objects.values_list("status", flat=True)) >= {
        "approved",
        "appeal",
        "rejected_auto",
        "moderation",
    }
    statuses = set(CustomOrder.objects.values_list("status", flat=True))
    assert statuses >= {"new", "offer", "awaiting_payment", "in_work", "submitted", "revision", "accepted",
                        "cancelled", "refunded", "dispute"}  # fmt: skip
    assert set(Purchase.objects.values_list("status", flat=True)) >= {
        "completed",
        "paid",
        "dispute",
        "refunded",
        "pending",
    }
    assert Dispute.objects.filter(status="open").exists()
    # настоящие шаблоны Start Bootstrap: опубликованы, автор и лицензия указаны, есть скриншоты страниц
    templates = Product.objects.filter(slug__startswith="sb-")
    assert templates.count() == 4
    for p in templates:
        assert p.status == "published"
        assert "Start Bootstrap LLC" in p.description and "MIT" in p.description
        assert p.screenshots.count() >= 2
    # копия шаблона с переименованными классами отклонена автоматически
    copy = ProductVersion.objects.get(product__slug="startup-landing")
    assert copy.status == "rejected_auto" and copy.similarity >= 0.7
    # повторный запуск без --reset ничего не ломает
    call_command("seed_demo")
    assert Product.objects.filter(status="published").count() == 20

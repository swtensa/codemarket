from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.catalog import services
from apps.catalog.models import Product, ProductView
from apps.catalog.refs import ensure_reference_data
from apps.core.exceptions import InvalidTransition
from tests.factories import (
    CategoryFactory,
    PlatformFactory,
    ProductFactory,
    SubcategoryFactory,
    TechnologyFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def titles(resp):
    return [p.title for p in resp.context["products"]]


@pytest.fixture
def catalog():
    sites = CategoryFactory(name="Сайты", slug="sites")
    bots = CategoryFactory(name="Боты", slug="bots")
    landing = SubcategoryFactory(name="Лендинг", slug="landing", parent=sites)
    tg = SubcategoryFactory(name="Telegram", slug="tg", parent=bots)
    py = TechnologyFactory(name="Python", slug="python")
    js = TechnologyFactory(name="JavaScript", slug="javascript")
    tgp = PlatformFactory(name="Telegram", slug="telegram")
    a = ProductFactory(title="Лендинг кофейни", category=landing, price=990, rating_avg=Decimal("4.8"), sales_count=3)
    a.technologies.set([js])
    b = ProductFactory(title="Бот записи", category=tg, price=4900, rating_avg=Decimal("4.2"), sales_count=10)
    b.technologies.set([py])
    b.platforms.set([tgp])
    c = ProductFactory(title="Бот напоминаний", category=tg, price=2500, short_description="Напомнит о приёме")
    c.technologies.set([py, js])
    ProductFactory(title="Черновик", category=landing, status="draft")
    return {"a": a, "b": b, "c": c}


def test_catalog_shows_only_published(client, catalog):
    resp = client.get("/")
    assert resp.status_code == 200
    assert set(titles(resp)) == {"Лендинг кофейни", "Бот записи", "Бот напоминаний"}
    assert resp.context["total"] == 3


def test_catalog_hides_blocked_seller(client, catalog):
    seller = catalog["a"].seller
    seller.status = "blocked"
    seller.save()
    assert "Лендинг кофейни" not in titles(client.get("/"))


def test_search_by_title_and_short_description(client, catalog):
    assert titles(client.get("/?q=кофейн")) == ["Лендинг кофейни"]
    assert titles(client.get("/?q=приём")) == ["Бот напоминаний"]


def test_filter_section_category_price(client, catalog):
    assert set(titles(client.get("/?section=bots"))) == {"Бот записи", "Бот напоминаний"}
    assert titles(client.get("/?category=landing")) == ["Лендинг кофейни"]
    assert titles(client.get("/?price_min=1000&price_max=3000")) == ["Бот напоминаний"]


def test_filter_technologies_and_platforms(client, catalog):
    assert set(titles(client.get("/?tech=python"))) == {"Бот записи", "Бот напоминаний"}
    assert titles(client.get("/?tech=python&tech=javascript")) == ["Бот напоминаний"]
    assert titles(client.get("/?platform=telegram")) == ["Бот записи"]


def test_filter_rating(client, catalog):
    assert set(titles(client.get("/?rating=4.5"))) == {"Лендинг кофейни"}


@pytest.mark.parametrize(
    "sort,first",
    [
        ("cheap", "Лендинг кофейни"),
        ("expensive", "Бот записи"),
        ("rating", "Лендинг кофейни"),
        ("popular", "Бот записи"),
    ],
)
def test_sorting(client, catalog, sort, first):
    assert titles(client.get(f"/?sort={sort}"))[0] == first


def test_pagination_by_12(client):
    for _ in range(14):
        ProductFactory()
    resp = client.get("/")
    assert len(resp.context["products"]) == 12
    resp2 = client.get("/?page=2")
    assert len(resp2.context["products"]) == 2


def test_empty_result_message(client, catalog):
    resp = client.get("/?q=несуществующее")
    assert "Ничего не нашлось" in resp.content.decode()


def test_catalog_no_n_plus_one(client, django_assert_max_num_queries):
    for _ in range(12):
        p = ProductFactory()
        p.technologies.set([TechnologyFactory()])
    with django_assert_max_num_queries(15):
        client.get("/")


def test_product_page_and_view_recorded_once(client, catalog):
    p = catalog["b"]
    resp = client.get(f"/p/{p.slug}/")
    assert resp.status_code == 200
    assert "Купить с доработкой" in resp.content.decode()
    client.get(f"/p/{p.slug}/")
    assert ProductView.objects.filter(product=p).count() == 1


def test_owner_view_not_recorded(client, catalog):
    p = catalog["b"]
    client.force_login(p.seller)
    resp = client.get(f"/p/{p.slug}/")
    assert "Редактировать" in resp.content.decode()
    assert ProductView.objects.count() == 0


def test_draft_product_hidden_from_guests(client):
    p = ProductFactory(status="draft")
    assert client.get(f"/p/{p.slug}/").status_code == 404
    client.force_login(p.seller)
    assert client.get(f"/p/{p.slug}/").status_code == 200


def test_price_check_constraint():
    p = ProductFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=p.pk).update(price=50)


def test_product_transitions():
    p = ProductFactory(status="draft", published_at=None)
    services.on_release_submitted(p)
    assert p.status == "checking"
    services.on_version_checked(p, rejected_auto=False)
    assert p.status == "moderation"
    services.on_version_approved(p)
    assert p.status == "published" and p.published_at
    services.hide_product(p, p.seller)
    assert p.status == "hidden"
    services.unhide_product(p, p.seller)
    assert p.status == "published"
    with pytest.raises(InvalidTransition):
        services.change_product_status(p, "draft")


def test_rejected_product_back_to_checking():
    p = ProductFactory(status="checking", published_at=None)
    services.on_version_checked(p, rejected_auto=True)
    assert p.status == "rejected"
    services.on_release_submitted(p)
    assert p.status == "checking"


def test_reference_data_idempotent():
    ensure_reference_data()
    ensure_reference_data()
    from apps.catalog.models import Category, Platform, Technology

    assert Category.objects.filter(parent__isnull=True).count() == 4
    assert 10 <= Category.objects.filter(parent__isnull=False).count() <= 12
    assert Technology.objects.count() == 12
    assert Platform.objects.count() == 8


def test_unique_slug_transliterates():
    ProductFactory(slug="lending-kofeyni")
    assert services.unique_slug("Лендинг кофейни") == "lending-kofeyni-2"


def test_create_product_requires_github_and_terms():
    from apps.core.exceptions import ServiceError

    user = UserFactory()
    cat = SubcategoryFactory()
    data = {"title": "Тест", "short_description": "к", "description": "о", "price": 500, "category": cat}
    with pytest.raises(ServiceError):
        services.create_product(user, data=data)
    user.github_installation_id = 1
    with pytest.raises(ServiceError):
        services.create_product(user, data=data)

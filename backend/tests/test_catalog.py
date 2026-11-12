"""Каталог: фильтры, поиск, сортировка, пагинация, страница продукта, просмотры, статусы продукта."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.errors import InvalidTransition, ServiceError
from app.models import Category, Platform, ProductView, Technology
from app.services import catalog as svc
from app.services.refs import ensure_reference_data
from tests.factories import (
    make_platform,
    make_product,
    make_section,
    make_subcategory,
    make_technology,
    make_user,
)


def titles(api, query=""):
    resp = api.get(f"/api/catalog/products{query}")
    assert resp.status_code == 200, resp.text
    return [p["title"] for p in resp.json()["items"]]


@pytest.fixture
def catalog(db):
    sites = make_section(db, name="Сайты", slug="sites")
    bots = make_section(db, name="Боты", slug="bots", position=1)
    landing = make_subcategory(db, sites, name="Лендинг", slug="landing")
    tg = make_subcategory(db, bots, name="Telegram", slug="tg")
    py = make_technology(db, name="Python", slug="python")
    js = make_technology(db, name="JavaScript", slug="javascript")
    tgp = make_platform(db, name="Telegram", slug="telegram")
    a = make_product(db, title="Лендинг кофейни", category=landing, price=990, rating_avg=Decimal("4.8"), sales_count=3)
    a.technologies = [js]
    b = make_product(db, title="Бот записи", category=tg, price=4900, rating_avg=Decimal("4.2"), sales_count=10)
    b.technologies, b.platforms = [py], [tgp]
    c = make_product(db, title="Бот напоминаний", category=tg, price=2500, short_description="Напомнит о приёме")
    c.technologies = [py, js]
    make_product(db, title="Черновик", category=landing, status="draft")
    db.flush()
    return {"a": a, "b": b, "c": c}


def test_catalog_shows_only_published(api, catalog):
    resp = api.get("/api/catalog/products").json()
    assert {p["title"] for p in resp["items"]} == {"Лендинг кофейни", "Бот записи", "Бот напоминаний"}
    assert resp["total"] == 3 and resp["page"] == 1 and resp["pages"] == 1
    card = next(p for p in resp["items"] if p["title"] == "Бот записи")
    assert card["price"] == "4900.00" and card["section_name"] == "Боты" and card["technologies"] == ["Python"]


def test_catalog_hides_blocked_seller(api, db, catalog):
    catalog["a"].seller.status = "blocked"
    db.flush()
    assert "Лендинг кофейни" not in titles(api)


def test_search_by_title_and_short_description(api, catalog):
    assert titles(api, "?q=кофейн") == ["Лендинг кофейни"]
    assert titles(api, "?q=приём") == ["Бот напоминаний"]


def test_filter_section_category_price(api, catalog):
    assert set(titles(api, "?section=bots")) == {"Бот записи", "Бот напоминаний"}
    assert titles(api, "?category=landing") == ["Лендинг кофейни"]
    assert titles(api, "?price_min=1000&price_max=3000") == ["Бот напоминаний"]


def test_filter_technologies_and_platforms(api, catalog):
    assert set(titles(api, "?tech=python")) == {"Бот записи", "Бот напоминаний"}
    assert titles(api, "?tech=python&tech=javascript") == ["Бот напоминаний"]
    assert titles(api, "?platform=telegram") == ["Бот записи"]


def test_filter_rating(api, catalog):
    assert set(titles(api, "?rating=4.5")) == {"Лендинг кофейни"}


@pytest.mark.parametrize(
    "sort,first",
    [
        ("cheap", "Лендинг кофейни"),
        ("expensive", "Бот записи"),
        ("rating", "Лендинг кофейни"),
        ("popular", "Бот записи"),
    ],
)
def test_sorting(api, catalog, sort, first):
    assert titles(api, f"?sort={sort}")[0] == first


def test_pagination_by_12(api, db):
    for _ in range(14):
        make_product(db)
    first = api.get("/api/catalog/products").json()
    assert len(first["items"]) == 12 and first["total"] == 14 and first["pages"] == 2
    assert len(api.get("/api/catalog/products?page=2").json()["items"]) == 2
    assert api.get("/api/catalog/products?page=99").json()["page"] == 2


def test_empty_result(api, catalog):
    assert api.get("/api/catalog/products?q=несуществующее").json()["total"] == 0


def test_refs_with_counts(api, db, catalog):
    data = api.get("/api/catalog/refs").json()
    counts = {s["slug"]: s["product_count"] for s in data["sections"]}
    assert counts["sites"] == 1 and counts["bots"] == 2
    assert [c["slug"] for c in data["sections"][0]["children"]] == ["landing"]
    assert {t["slug"] for t in data["technologies"]} >= {"python", "javascript"}
    assert [s["key"] for s in data["sorts"]] == ["new", "cheap", "expensive", "rating", "popular"]


def test_product_page_and_view_recorded_once(api, db, catalog):
    p = catalog["b"]
    resp = api.get(f"/api/catalog/products/{p.slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Бот записи" and data["section"]["slug"] == "bots" and data["category"]["slug"] == "tg"
    assert data["is_owner"] is False and data["purchase_id"] is None
    api.get(f"/api/catalog/products/{p.slug}")
    assert db.scalar(select(func.count()).where(ProductView.product_id == p.id)) == 1


def test_owner_view_not_recorded(api, db, catalog):
    p = catalog["b"]
    api.login(p.seller)
    assert api.get(f"/api/catalog/products/{p.slug}").json()["is_owner"] is True
    assert db.scalar(select(func.count()).select_from(ProductView)) == 0


def test_draft_product_hidden_from_guests(api, db):
    p = make_product(db, status="draft")
    assert api.get(f"/api/catalog/products/{p.slug}").status_code == 404
    api.login(p.seller)
    assert api.get(f"/api/catalog/products/{p.slug}").status_code == 200


def test_price_check_constraint(db):
    p = make_product(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("UPDATE products SET price = 50 WHERE id = :id"), {"id": p.id})


def test_product_transitions(db):
    p = make_product(db, status="draft", published_at=None)
    svc.on_release_submitted(db, p)
    assert p.status == "checking"
    svc.on_version_checked(db, p, rejected_auto=False)
    assert p.status == "moderation"
    svc.on_version_approved(db, p)
    assert p.status == "published" and p.published_at
    svc.hide_product(db, p, p.seller)
    assert p.status == "hidden"
    svc.unhide_product(db, p, p.seller)
    assert p.status == "published"
    with pytest.raises(InvalidTransition):
        svc.change_product_status(db, p, "draft")


def test_rejected_product_back_to_checking(db):
    p = make_product(db, status="checking", published_at=None)
    svc.on_version_checked(db, p, rejected_auto=True)
    assert p.status == "rejected"
    svc.on_release_submitted(db, p)
    assert p.status == "checking"


def test_reference_data_idempotent(db):
    ensure_reference_data(db)
    ensure_reference_data(db)
    assert db.scalar(select(func.count()).where(Category.parent_id.is_(None))) == 4
    assert 10 <= db.scalar(select(func.count()).where(Category.parent_id.is_not(None))) <= 12
    assert db.scalar(select(func.count()).select_from(Technology)) == 12
    assert db.scalar(select(func.count()).select_from(Platform)) == 8


def test_unique_slug_transliterates(db):
    make_product(db, slug="lending-kofeyni")
    assert svc.unique_slug(db, "Лендинг кофейни") == "lending-kofeyni-2"


def test_create_product_requires_github_and_terms(db):
    user = make_user(db)
    cat = make_subcategory(db)
    data = {"title": "Тест", "short_description": "к", "description": "о", "price": 500, "category_id": cat.id}
    with pytest.raises(ServiceError):
        svc.create_product(db, user, data=dict(data))
    user.github_installation_id = 1
    with pytest.raises(ServiceError):
        svc.create_product(db, user, data=dict(data))

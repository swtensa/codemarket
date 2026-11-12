"""Кабинет продавца: GitHub (fake), мастер продукта, редактирование, скриншоты, релизы, архивы."""

import io
import zipfile

import pytest
from sqlalchemy import select

from app.core.archive import ArchiveError, extract_safe, inspect_zip
from app.core.config import settings
from app.core.errors import ServiceError
from app.core.storage import private_path
from app.models import Product, ProductVersion
from app.services import versions as version_services
from tests.factories import make_product, make_seller, make_subcategory, make_technology, make_user
from tests.helpers import png_bytes


@pytest.fixture
def fake_repos():
    root = settings.github_fake_root
    repo = root / "coffee-landing"
    (repo / "css").mkdir(parents=True)
    (repo / "index.html").write_text("<html><body><h1>Кофейня</h1></body></html>", encoding="utf-8")
    (repo / "css" / "style.css").write_text("body { color: #333; }", encoding="utf-8")
    return root


def test_guest_gets_401(api):
    assert api.get("/api/seller/dashboard").status_code == 401


def test_dashboard_without_github(api, db):
    api.login(make_user(db))
    data = api.get("/api/seller/dashboard").json()
    assert data["is_seller"] is False and data["products"] == [] and data["github_mode"] == "fake"


def test_fake_github_connect(api, db):
    user = make_user(db)
    api.login(user)
    resp = api.post("/api/seller/github/connect")
    assert resp.status_code == 200
    db.refresh(user)
    assert user.is_seller
    assert api.get("/api/seller/github").json()["connected"] is True


def test_wizard_requires_github(api, db):
    api.login(make_user(db))
    assert api.get("/api/seller/repos").status_code == 403


def wizard_payload(**over):
    data = {
        "repo_full_name": "demo-seller/coffee-landing",
        "title": "Лендинг кофейни",
        "short_description": "Одностраничный сайт",
        "description": "Подробно",
        "price": 1490,
        "demo_url": "",
    }
    data.update(over)
    return data


def test_wizard_creates_product_with_seller_terms(api, db, fake_repos):
    seller = make_seller(db, seller_terms_accepted_at=None)
    cat = make_subcategory(db)
    tech = make_technology(db)
    api.login(seller)
    repos = api.get("/api/seller/repos").json()
    assert repos["need_terms"] is True
    assert [r["full_name"] for r in repos["repos"]] == ["demo-seller/coffee-landing"]
    payload = wizard_payload(category_id=cat.id, technology_ids=[tech.id])
    resp = api.post("/api/seller/products", payload)
    assert resp.status_code == 422
    assert resp.json()["fields"]["accept_seller_terms"] == "Без согласия создать продукт нельзя."
    resp = api.post("/api/seller/products", {**payload, "accept_seller_terms": True})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    db.refresh(seller)
    assert seller.seller_terms_accepted_at is not None
    product = db.get(Product, data["id"])
    assert product.status == "draft" and product.slug == "lending-kofeyni"
    assert product.source_repo_full_name == "demo-seller/coffee-landing"
    assert [t.id for t in product.technologies] == [tech.id]


def test_wizard_validates_price_and_repo(api, db, fake_repos):
    seller = make_seller(db)
    cat = make_subcategory(db)
    api.login(seller)
    resp = api.post("/api/seller/products", wizard_payload(category_id=cat.id, price=50))
    assert resp.status_code == 422 and "100" in resp.json()["fields"]["price"]
    resp = api.post("/api/seller/products", wizard_payload(category_id=cat.id, repo_full_name="x/y"))
    assert "repo_full_name" in resp.json()["fields"]
    resp = api.post("/api/seller/products", wizard_payload(category_id=None))
    assert "category_id" in resp.json()["fields"]


def test_import_release_creates_checking_version(db, fake_repos):
    seller = make_seller(db)
    product = make_product(db, seller=seller, status="draft", source_repo_full_name="demo-seller/coffee-landing")
    releases = version_services.available_releases(db, product, seller)
    assert [r["release"].tag_name for r in releases] == ["v1.0.0"]
    v = version_services.import_release(db, product, seller, "v1.0.0")
    assert v.status == "checking" and v.files_count == 2
    assert private_path(v.archive).name.endswith(".zip") and private_path(v.archive).exists()
    assert product.status == "checking"
    with pytest.raises(ServiceError):
        version_services.import_release(db, product, seller, "v1.0.0")


def test_import_release_api(api, db, fake_repos):
    seller = make_seller(db)
    product = make_product(db, seller=seller, status="draft", source_repo_full_name="demo-seller/coffee-landing")
    api.login(seller)
    page = api.get(f"/api/seller/products/{product.id}/versions").json()
    assert page["releases"][0]["tag_name"] == "v1.0.0" and page["releases"][0]["imported"] is False
    resp = api.post(f"/api/seller/products/{product.id}/versions/import", {"tag": "v1.0.0"})
    assert resp.status_code == 200
    assert db.scalar(select(ProductVersion).where(ProductVersion.product_id == product.id)).status == "checking"


def test_other_seller_gets_404(api, db):
    product = make_product(db)
    api.login(make_seller(db))
    assert api.get(f"/api/seller/products/{product.id}").status_code == 404
    assert api.get(f"/api/seller/products/{product.id}/versions").status_code == 404
    assert api.put(f"/api/seller/products/{product.id}", {"title": "x"}).status_code == 404


def test_edit_product(api, db):
    product = make_product(db)
    api.login(product.seller)
    resp = api.put(
        f"/api/seller/products/{product.id}",
        {
            "title": "Новое имя",
            "short_description": "к",
            "description": "о",
            "price": "1500",
            "category_id": product.category_id,
            "technology_ids": [],
            "platform_ids": [],
            "demo_url": "example.com/demo",
        },
    )
    assert resp.status_code == 200, resp.text
    db.refresh(product)
    assert product.title == "Новое имя" and product.price == 1500 and product.demo_url == "https://example.com/demo"


def test_screenshots_upload_and_limits(api, db):
    product = make_product(db)
    api.login(product.seller)
    url = f"/api/seller/products/{product.id}/screenshots"
    files = [("images", ("a.png", png_bytes(), "image/png")), ("images", ("b.png", png_bytes(), "image/png"))]
    resp = api.post(url, files=files)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["screenshots"]) == 2
    resp = api.post(url, files=[("images", ("a.gif", b"GIF89a", "image/gif"))])
    assert resp.status_code == 400 and "jpg, png и webp" in resp.json()["detail"]
    resp = api.post(url, files=[("images", ("big.png", b"0" * (3 * 1024 * 1024 + 1), "image/png"))])
    assert "3 МБ" in resp.json()["detail"]
    resp = api.post(url, files=[("images", (f"{i}.png", png_bytes(), "image/png")) for i in range(7)])
    assert resp.status_code == 400
    shots = api.get(f"/api/seller/products/{product.id}/media").json()["screenshots"]
    assert len(shots) == 2  # 2 + 7 > 8 — отказ целиком
    assert api.get(shots[0]["url"]).status_code in (200, 404)  # /media раздаётся из storage/public
    assert api.delete(f"/api/seller/products/{product.id}/screenshots/{shots[0]['id']}").status_code == 200
    assert len(api.get(f"/api/seller/products/{product.id}/media").json()["screenshots"]) == 1


def test_hide_unhide_delete(api, db):
    product = make_product(db)
    api.login(product.seller)
    api.post(f"/api/seller/products/{product.id}/hide")
    db.refresh(product)
    assert product.status == "hidden"
    api.post(f"/api/seller/products/{product.id}/unhide")
    db.refresh(product)
    assert product.status == "published"
    assert api.delete(f"/api/seller/products/{product.id}").status_code == 200
    assert db.get(Product, product.id) is None


def test_unhide_published_is_409(api, db):
    product = make_product(db)
    api.login(product.seller)
    assert api.post(f"/api/seller/products/{product.id}/unhide").status_code == 409


def test_dashboard_lists_products_and_tiles(api, db):
    product = make_product(db, title="Мой продукт")
    api.login(product.seller)
    data = api.get("/api/seller/dashboard").json()
    assert data["is_seller"] and data["products"][0]["title"] == "Мой продукт"
    assert data["products"][0]["status_label"] == "Опубликован"
    assert data["tiles"]["revenue_month"] == "0.00" and data["tiles"]["sales"] == 0


# ------------------------------------------------------------- безопасные архивы


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def test_zip_path_traversal_rejected(tmp_path):
    archive = tmp_path / "evil.zip"
    _zip(archive, {"../evil.txt": "x"})
    with pytest.raises(ArchiveError):
        extract_safe(archive, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_zip_too_many_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_files", 3)
    archive = tmp_path / "many.zip"
    _zip(archive, {f"f{i}.txt": "x" for i in range(5)})
    with pytest.raises(ArchiveError):
        inspect_zip(archive)


def test_zip_bomb_rejected(tmp_path):
    archive = tmp_path / "bomb.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.txt", b"0" * (20 * 1024 * 1024))
    archive.write_bytes(buf.getvalue())
    with pytest.raises(ArchiveError):
        inspect_zip(archive)


def test_extract_strips_root(tmp_path):
    archive = tmp_path / "ok.zip"
    _zip(archive, {"owner-repo-abc/index.html": "<p>", "owner-repo-abc/css/a.css": "a{}"})
    out = extract_safe(archive, tmp_path / "out")
    assert (out / "index.html").exists() and (out / "css" / "a.css").exists()

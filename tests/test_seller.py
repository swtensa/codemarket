import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.models import Product
from apps.core.archive import ArchiveError, extract_safe, inspect_zip
from apps.core.exceptions import ServiceError
from apps.versions import services as version_services
from apps.versions.models import ProductVersion
from tests.factories import ProductFactory, SellerFactory, SubcategoryFactory, TechnologyFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake_repos(settings, tmp_path):
    root = tmp_path / "repos"
    repo = root / "coffee-landing"
    (repo / "css").mkdir(parents=True)
    (repo / "index.html").write_text("<html><body><h1>Кофейня</h1></body></html>", encoding="utf-8")
    (repo / "css" / "style.css").write_text("body { color: #333; }", encoding="utf-8")
    settings.GITHUB_FAKE_ROOT = root
    return root


def png(name="shot.png", size=(32, 20)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 80, 80)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def test_guest_redirected_to_login(client):
    resp = client.get("/sell/")
    assert resp.status_code == 302 and "/accounts/login/" in resp["Location"]


def test_dashboard_shows_connect_block(client, user):
    client.force_login(user)
    resp = client.get("/sell/")
    assert "Подключить GitHub" in resp.content.decode()


def test_fake_github_connect(client, user):
    client.force_login(user)
    resp = client.post("/sell/github/")
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.is_seller


def test_wizard_requires_github(client, user):
    client.force_login(user)
    resp = client.get("/sell/products/new/")
    assert resp.status_code == 302 and resp["Location"] == "/sell/"


def test_wizard_creates_product_with_seller_terms(client, fake_repos):
    seller = SellerFactory(seller_terms_accepted_at=None)
    sub = SubcategoryFactory()
    tech = TechnologyFactory()
    client.force_login(seller)
    # шаг 1 без согласия
    resp = client.post("/sell/products/new/?step=1", {"repo": "demo-seller/coffee-landing"})
    assert "Без согласия создать продукт нельзя" in resp.content.decode()
    resp = client.post(
        "/sell/products/new/?step=1", {"repo": "demo-seller/coffee-landing", "accept_seller_terms": "on"}
    )
    assert resp.status_code == 302
    seller.refresh_from_db()
    assert seller.seller_terms_accepted_at is not None
    resp = client.post(
        "/sell/products/new/?step=2",
        {"title": "Лендинг кофейни", "short_description": "Кратко", "description": "Подробно", "price": "990"},
    )
    assert resp.status_code == 302
    resp = client.post(
        "/sell/products/new/?step=3",
        {"category": sub.pk, "technologies": [tech.pk], "demo_url": "https://example.com"},
    )
    product = Product.objects.get()
    assert resp.status_code == 302 and resp["Location"] == f"/sell/products/{product.pk}/media/"
    assert product.status == "draft"
    assert product.slug == "lending-kofeyni"
    assert product.source_repo_full_name == "demo-seller/coffee-landing"
    assert list(product.technologies.all()) == [tech]


def test_wizard_validates_price(client, fake_repos):
    seller = SellerFactory()
    client.force_login(seller)
    client.post("/sell/products/new/?step=1", {"repo": "demo-seller/coffee-landing"})
    resp = client.post(
        "/sell/products/new/?step=2", {"title": "Т", "short_description": "к", "description": "о", "price": "50"}
    )
    assert resp.status_code == 200
    assert "100" in resp.content.decode()


def test_import_release_creates_checking_version(fake_repos):
    product = ProductFactory(status="draft", source_repo_full_name="demo-seller/coffee-landing", published_at=None)
    releases = version_services.available_releases(product, product.seller)
    assert [r["release"].tag_name for r in releases] == ["v1.0.0"]
    v = version_services.import_release(product, product.seller, "v1.0.0")
    assert v.status == "checking"
    assert v.files_count == 2
    assert v.archive.path.endswith(".zip")
    product.refresh_from_db()
    assert product.status == "checking"
    with pytest.raises(ServiceError):
        version_services.import_release(product, product.seller, "v1.0.0")


def test_import_release_view(client, fake_repos):
    product = ProductFactory(status="draft", source_repo_full_name="demo-seller/coffee-landing")
    client.force_login(product.seller)
    resp = client.get(f"/sell/products/{product.pk}/versions/")
    assert "Отправить на проверку" in resp.content.decode()
    client.post(f"/sell/products/{product.pk}/versions/import/", {"tag": "v1.0.0"})
    assert ProductVersion.objects.filter(product=product, status="checking").exists()


def test_other_seller_cannot_edit(client):
    product = ProductFactory()
    client.force_login(SellerFactory())
    assert client.get(f"/sell/products/{product.pk}/edit/").status_code == 404
    assert client.get(f"/sell/products/{product.pk}/versions/").status_code == 404


def test_edit_product(client):
    product = ProductFactory()
    client.force_login(product.seller)
    resp = client.post(
        f"/sell/products/{product.pk}/edit/",
        {
            "title": "Новое имя",
            "short_description": "к",
            "description": "о",
            "price": "1500",
            "category": product.category_id,
        },
    )
    assert resp.status_code == 302
    product.refresh_from_db()
    assert product.title == "Новое имя" and product.price == 1500


def test_screenshots_upload_and_limits(client):
    product = ProductFactory()
    client.force_login(product.seller)
    client.post(f"/sell/products/{product.pk}/media/", {"images": [png("a.png"), png("b.png")]})
    assert product.screenshots.count() == 2
    bad = SimpleUploadedFile("x.gif", b"GIF89a", content_type="image/gif")
    resp = client.post(f"/sell/products/{product.pk}/media/", {"images": [bad]}, follow=True)
    assert "jpg, png и webp" in resp.content.decode()
    big = SimpleUploadedFile("big.png", b"0" * (3 * 1024 * 1024 + 1), content_type="image/png")
    resp = client.post(f"/sell/products/{product.pk}/media/", {"images": [big]}, follow=True)
    assert "3 МБ" in resp.content.decode()
    client.post(f"/sell/products/{product.pk}/media/", {"images": [png(f"{i}.png") for i in range(7)]})
    assert product.screenshots.count() == 2  # 2 + 7 > 8 — отказ целиком


def test_hide_unhide_delete(client):
    product = ProductFactory()
    client.force_login(product.seller)
    client.post(f"/sell/products/{product.pk}/hide/")
    product.refresh_from_db()
    assert product.status == "hidden"
    client.post(f"/sell/products/{product.pk}/unhide/")
    product.refresh_from_db()
    assert product.status == "published"
    client.post(f"/sell/products/{product.pk}/delete/")
    assert not Product.objects.filter(pk=product.pk).exists()


def _zip(tmp_path, entries):
    path = tmp_path / "a.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def test_zip_path_traversal_rejected(tmp_path):
    path = _zip(tmp_path, {"root/ok.txt": "1", "root/../../evil.txt": "x"})
    with pytest.raises(ArchiveError):
        inspect_zip(path)
    with pytest.raises(ArchiveError):
        extract_safe(path, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_zip_too_many_files(tmp_path, settings):
    settings.MAX_FILES = 3
    path = _zip(tmp_path, {f"r/{i}.txt": "1" for i in range(5)})
    with pytest.raises(ArchiveError):
        inspect_zip(path)


def test_zip_bomb_rejected(tmp_path):
    path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("r/zeros.txt", b"\0" * (20 * 1024 * 1024))
    with pytest.raises(ArchiveError):
        inspect_zip(path)


def test_extract_strips_root(tmp_path):
    path = _zip(tmp_path, {"owner-repo-abc/index.html": "<p>", "owner-repo-abc/css/a.css": "a{}"})
    out = extract_safe(path, tmp_path / "out")
    assert (out / "index.html").exists() and (out / "css" / "a.css").exists()


def test_user_without_github_has_no_sales_menu(client):
    u = UserFactory()
    client.force_login(u)
    assert 'href="/sell/"><i class="bi bi-shop me-2"></i>Продажи' not in client.get("/").content.decode()

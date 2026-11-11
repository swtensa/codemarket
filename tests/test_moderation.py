from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog import services as catalog_services
from apps.catalog.models import Product
from apps.plagiarism.services import process_pending
from apps.versions import services as version_services
from tests.factories import ProductFactory, UserFactory
from tests.helpers import make_checked_approved, make_version

pytestmark = pytest.mark.django_db

PAIRS = Path(settings.BASE_DIR) / "fixtures" / "plag_pairs"


def _read(pair, side):
    base = PAIRS / pair / side
    return {p.relative_to(base).as_posix(): p.read_text(encoding="utf-8") for p in base.rglob("*") if p.is_file()}


def test_non_admin_gets_403(client):
    client.force_login(UserFactory())
    for url in ["/moderation/", "/moderation/users/"]:
        assert client.get(url).status_code == 403


def test_guest_redirected_from_moderation(client):
    resp = client.get("/moderation/")
    assert resp.status_code == 302 and "/accounts/login/" in resp["Location"]


def test_full_path_to_published(client, admin_user):
    product = ProductFactory(status="draft", published_at=None)
    catalog_services.on_release_submitted(product)
    v = make_version(product, _read("04_different_projects", "a"))
    process_pending()
    v.refresh_from_db()
    assert v.status == "moderation"
    client.force_login(admin_user)
    resp = client.get("/moderation/")
    assert product.title in resp.content.decode()
    resp = client.get(f"/moderation/versions/{v.pk}/")
    html = resp.content.decode()
    assert "inventory.py" in html and 'class="highlight"' in html
    resp = client.post(f"/moderation/versions/{v.pk}/", {"action": "approve"})
    assert resp.status_code == 302
    v.refresh_from_db()
    product.refresh_from_db()
    assert v.status == "approved" and v.approved_at
    assert product.status == "published" and product.published_at
    assert product.mirror_repo_full_name == f"{settings.GITHUB_ORG}/{product.slug}"
    mirror = Path(settings.PRIVATE_ROOT) / "fake_github" / "mirrors" / product.slug / "current" / "inventory.py"
    assert mirror.exists()
    assert product.seller.notifications.filter(text__contains="одобрена").exists()
    assert client.get(f"/p/{product.slug}/").status_code == 200


def test_reject_requires_comment(client, admin_user):
    product = ProductFactory(status="moderation", published_at=None)
    v = make_version(product, {"a.py": "x = 1\n"}, status="moderation")
    client.force_login(admin_user)
    client.post(f"/moderation/versions/{v.pk}/", {"action": "reject", "comment": ""})
    v.refresh_from_db()
    assert v.status == "moderation"
    client.post(f"/moderation/versions/{v.pk}/", {"action": "reject", "comment": "Нет README"})
    v.refresh_from_db()
    product.refresh_from_db()
    assert v.status == "rejected" and v.admin_comment == "Нет README"
    assert product.status == "rejected"


def test_appeal_flow(client, admin_user):
    make_checked_approved(ProductFactory(), _read("02_renamed_variables", "a"))
    product = ProductFactory(status="draft", published_at=None)
    catalog_services.on_release_submitted(product)
    v = make_version(product, _read("02_renamed_variables", "b"))
    process_pending()
    v.refresh_from_db()
    assert v.status == "rejected_auto"
    client.force_login(product.seller)
    resp = client.get(f"/sell/products/{product.pk}/versions/")
    assert "Обжаловать" in resp.content.decode() and "storage.py" in resp.content.decode()
    client.post(f"/sell/versions/{v.pk}/appeal/", {"appeal_text": "Это мой собственный код, писал сам"})
    v.refresh_from_db()
    product.refresh_from_db()
    assert v.status == "appeal" and product.status == "moderation"
    client.force_login(admin_user)
    resp = client.get("/moderation/")
    assert "Обжалование" in resp.content.decode()
    client.post(f"/moderation/versions/{v.pk}/", {"action": "approve"})
    v.refresh_from_db()
    product.refresh_from_db()
    assert v.status == "approved" and product.status == "published"


def test_new_version_of_published_product_keeps_it_published(admin_user):
    product = ProductFactory(status="published")
    make_version(product, {"a.py": "x = 1\n"}, status="approved", tag="v1")
    v2 = make_version(product, {"a.py": "x = 2\n"}, status="moderation", tag="v2")
    version_services.reject_version(v2, admin_user, "ошибка")
    product.refresh_from_db()
    assert product.status == Product.Status.PUBLISHED


def test_block_user_from_moderation(client, admin_user):
    target = UserFactory()
    client.force_login(admin_user)
    client.post(f"/moderation/users/{target.pk}/", {"action": "block", "reason": "мошенничество"})
    target.refresh_from_db()
    assert target.status == "blocked" and target.block_reason == "мошенничество"
    client.post(f"/moderation/users/{target.pk}/", {"action": "unblock"})
    target.refresh_from_db()
    assert target.status == "active"

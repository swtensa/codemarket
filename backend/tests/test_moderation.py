"""Модерация версий: права, полный путь до публикации, отклонение, обжалование."""

import pytest

from app.core.config import BASE_DIR, settings
from app.services import catalog as catalog_services
from app.services import versions as version_services
from app.services.plagiarism import process_pending
from tests.factories import make_admin, make_product, make_user
from tests.helpers import make_checked_approved, make_version

PAIRS = BASE_DIR / "fixtures" / "plag_pairs"


def read_pair(pair, side):
    base = PAIRS / pair / side
    return {p.relative_to(base).as_posix(): p.read_text(encoding="utf-8") for p in base.rglob("*") if p.is_file()}


@pytest.fixture
def admin(db):
    return make_admin(db)


def test_non_admin_gets_403(api, db):
    api.login(make_user(db))
    for url in ["/api/admin/versions", "/api/admin/counts"]:
        assert api.get(url).status_code == 403


def test_guest_gets_401(api):
    assert api.get("/api/admin/versions").status_code == 401


def test_full_path_to_published(api, db, admin):
    product = make_product(db, status="draft", published_at=None)
    catalog_services.on_release_submitted(db, product)
    v = make_version(db, product, read_pair("04_different_projects", "a"))
    process_pending(db)
    db.refresh(v)
    assert v.status == "moderation"
    api.login(admin)
    queue = api.get("/api/admin/versions").json()
    assert queue[0]["product_title"] == product.title and queue[0]["is_new_product"] is True
    assert api.get("/api/admin/counts").json()["versions"] == 1
    detail = api.get(f"/api/admin/versions/{v.id}").json()
    assert "inventory.py" in [t["path"] for t in detail["tree"]] and detail["can_decide"] is True
    code = api.get(f"/api/admin/versions/{v.id}/file", params={"path": "inventory.py"}).json()
    assert 'class="highlight"' in code["html"] and code["error"] is None
    assert api.get(f"/api/admin/versions/{v.id}/file", params={"path": "nope.py"}).json()["error"]
    resp = api.post(f"/api/admin/versions/{v.id}/approve")
    assert resp.status_code == 200
    db.refresh(v)
    db.refresh(product)
    assert v.status == "approved" and v.approved_at
    assert product.status == "published" and product.published_at
    assert product.mirror_repo_full_name == f"{settings.github_org}/{product.slug}"
    mirror = settings.storage_private / "fake_github" / "mirrors" / product.slug / "current" / "inventory.py"
    assert mirror.exists()
    assert api.get(f"/api/catalog/products/{product.slug}").status_code == 200
    assert api.post(f"/api/admin/versions/{v.id}/approve").status_code == 409


def test_reject_requires_comment(api, db, admin):
    product = make_product(db, status="moderation", published_at=None)
    v = make_version(db, product, {"a.py": "x = 1\n"}, status="moderation")
    api.login(admin)
    resp = api.post(f"/api/admin/versions/{v.id}/reject", {"comment": ""})
    assert resp.status_code == 400 and resp.json()["detail"] == "Укажите причину отклонения."
    db.refresh(v)
    assert v.status == "moderation"
    api.post(f"/api/admin/versions/{v.id}/reject", {"comment": "Нет README"})
    db.refresh(v)
    db.refresh(product)
    assert v.status == "rejected" and v.admin_comment == "Нет README" and product.status == "rejected"


def test_appeal_flow(api, db, admin):
    make_checked_approved(db, make_product(db), read_pair("02_renamed_variables", "a"))
    product = make_product(db, status="draft", published_at=None)
    catalog_services.on_release_submitted(db, product)
    v = make_version(db, product, read_pair("02_renamed_variables", "b"))
    process_pending(db)
    db.refresh(v)
    assert v.status == "rejected_auto"
    api.login(product.seller)
    page = api.get(f"/api/seller/products/{product.id}/versions").json()
    match = page["versions"][0]["matches"][0]
    assert "storage.py" in match["files"] and match["similarity"] >= 0.9
    resp = api.post(f"/api/seller/versions/{v.id}/appeal", {"appeal_text": "коротко"})
    assert resp.status_code == 400
    api.post(f"/api/seller/versions/{v.id}/appeal", {"appeal_text": "Это мой собственный код, писал сам"})
    db.refresh(v)
    db.refresh(product)
    assert v.status == "appeal" and product.status == "moderation"
    api.login(admin)
    queue = api.get("/api/admin/versions").json()
    assert queue[0]["version"]["status"] == "appeal" and queue[0]["version"]["appeal_text"]
    api.post(f"/api/admin/versions/{v.id}/approve")
    db.refresh(v)
    db.refresh(product)
    assert v.status == "approved" and product.status == "published"


def test_new_version_of_published_product_keeps_it_published(db, admin):
    product = make_product(db)
    make_version(db, product, {"a.py": "x = 1\n"}, status="approved", tag="v1")
    v2 = make_version(db, product, {"a.py": "x = 2\n"}, status="moderation", tag="v2")
    version_services.reject_version(db, v2, admin, "ошибка")
    assert product.status == "published"

"""Администратор: пользователи и блокировка, справочники вместо Django admin."""

from sqlalchemy import select

from app.models import Category
from tests.factories import make_admin, make_product, make_subcategory, make_technology, make_user


def test_block_and_unblock_user(api, db):
    admin = make_admin(db)
    target = make_user(db, username="target_user")
    api.login(admin)
    users = api.get("/api/admin/users?q=target").json()
    assert [u["username"] for u in users["items"]] == ["target_user"]
    assert api.post(f"/api/admin/users/{target.id}/block", {"reason": ""}).status_code == 400
    assert api.post(f"/api/admin/users/{target.id}/block", {"reason": "мошенничество"}).status_code == 200
    db.refresh(target)
    assert target.status == "blocked" and target.block_reason == "мошенничество"
    assert api.get("/api/admin/users?status=blocked").json()["total"] == 1
    api.post(f"/api/admin/users/{target.id}/unblock")
    db.refresh(target)
    assert target.status == "active" and target.block_reason == ""


def test_admin_cannot_be_blocked(api, db):
    admin = make_admin(db)
    other_admin = make_admin(db)
    api.login(admin)
    assert api.post(f"/api/admin/users/{other_admin.id}/block", {"reason": "тест"}).status_code == 400
    assert api.post("/api/admin/users/999999/block", {"reason": "тест"}).status_code == 404


def test_users_forbidden_for_non_admin(api, db):
    api.login(make_user(db))
    assert api.get("/api/admin/users").status_code == 403
    assert api.get("/api/admin/refs").status_code == 403


def test_refs_crud(api, db):
    api.login(make_admin(db))
    resp = api.post("/api/admin/refs/categories", {"name": "Игры", "slug": "games", "icon": "bi-controller"})
    assert resp.status_code == 201
    games = db.scalar(select(Category).where(Category.slug == "games"))
    resp = api.post("/api/admin/refs/categories", {"name": "Аркады", "slug": "arcade", "parent_id": games.id})
    assert resp.status_code == 201
    resp = api.post("/api/admin/refs/categories", {"name": "Дубль", "slug": "games"})
    assert resp.status_code == 422 and "slug" in resp.json()["fields"]
    resp = api.post("/api/admin/refs/categories", {"name": "Плохой", "slug": "Плохой адрес"})
    assert "slug" in resp.json()["fields"]
    refs = api.get("/api/admin/refs").json()
    section = next(c for c in refs["categories"] if c["slug"] == "games")
    assert section["children"] == 1
    # раздел с подкатегорией удалить нельзя
    assert api.delete(f"/api/admin/refs/categories/{games.id}").status_code == 400
    arcade = next(c for c in refs["categories"] if c["slug"] == "arcade")
    assert (
        api.put(f"/api/admin/refs/categories/{arcade['id']}", {"name": "Аркады 2D", "slug": "arcade"}).status_code
        == 200
    )
    assert api.delete(f"/api/admin/refs/categories/{arcade['id']}").status_code == 200
    assert api.delete(f"/api/admin/refs/categories/{games.id}").status_code == 200

    assert api.post("/api/admin/refs/technologies", {"name": "Go", "slug": "go"}).status_code == 201
    assert api.post("/api/admin/refs/technologies", {"name": "go", "slug": "golang"}).status_code == 422
    tech = next(t for t in api.get("/api/admin/refs").json()["technologies"] if t["slug"] == "go")
    assert api.put(f"/api/admin/refs/technologies/{tech['id']}", {"name": "Golang", "slug": "go"}).status_code == 200
    assert api.delete(f"/api/admin/refs/technologies/{tech['id']}").status_code == 200
    assert api.post("/api/admin/refs/platforms", {"name": "macOS", "slug": "macos"}).status_code == 201


def test_refs_in_use_cannot_be_deleted(api, db):
    sub = make_subcategory(db)
    tech = make_technology(db)
    product = make_product(db, category=sub)
    product.technologies = [tech]
    db.flush()
    api.login(make_admin(db))
    assert api.delete(f"/api/admin/refs/categories/{sub.id}").status_code == 400
    assert api.delete(f"/api/admin/refs/technologies/{tech.id}").status_code == 400
    row = next(t for t in api.get("/api/admin/refs").json()["technologies"] if t["id"] == tech.id)
    assert row["products"] == 1

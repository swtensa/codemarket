"""Регистрация с согласием, вход по email, блокировка, выход, refresh, CSRF, пароль."""

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.models import User
from tests.factories import PASSWORD, make_user


def reg(**over):
    data = {
        "email": "New@Test.ru",
        "username": "new_user",
        "password1": "secret123",
        "password2": "secret123",
        "accept_terms": True,
    }
    data.update(over)
    return data


def test_register_creates_user_and_logs_in(api, db):
    resp = api.post("/api/auth/register", reg())
    assert resp.status_code == 201, resp.text
    user = db.scalar(select(User).where(User.email == "new@test.ru"))
    assert user.terms_accepted_at is not None
    assert api.cookies.get("access_token")
    assert api.get("/api/auth/me").json()["username"] == "new_user"


def test_register_requires_terms(api, db):
    resp = api.post("/api/auth/register", reg(accept_terms=False))
    assert resp.status_code == 422
    assert resp.json()["fields"]["accept_terms"] == "Без согласия регистрация невозможна."
    assert db.scalar(select(User)) is None


@pytest.mark.parametrize(
    "over,field,error",
    [
        ({"password1": "short1", "password2": "short1"}, "password1", "не короче"),
        ({"password1": "onlyletters", "password2": "onlyletters"}, "password1", "буквы и цифры"),
        ({"password1": "12345678901", "password2": "12345678901"}, "password1", "буквы и цифры"),
        ({"password2": "other1234"}, "password2", "не совпадают"),
        ({"username": "ab"}, "username", "3–30"),
        ({"username": "имя"}, "username", "3–30"),
        ({"email": "not-an-email"}, "email", "адрес"),
    ],
)
def test_register_validation(api, db, over, field, error):
    resp = api.post("/api/auth/register", reg(**over))
    assert resp.status_code == 422
    assert error in resp.json()["fields"][field]
    assert db.scalar(select(User)) is None


def test_register_duplicate_email(api, db):
    make_user(db, email="new@test.ru")
    resp = api.post("/api/auth/register", reg())
    assert "уже есть" in resp.json()["fields"]["email"]


def test_login_by_email_case_insensitive(api, db):
    make_user(db, email="anna@test.ru")
    resp = api.post("/api/auth/login", {"email": "ANNA@test.ru", "password": PASSWORD})
    assert resp.status_code == 200
    assert api.cookies.get("access_token") and api.cookies.get("refresh_token")


def test_login_wrong_password(api, db):
    make_user(db, email="anna@test.ru")
    resp = api.post("/api/auth/login", {"email": "anna@test.ru", "password": "wrong1234"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Неверный email или пароль."


def test_blocked_user_cannot_login_and_sees_reason(api, db):
    make_user(db, email="bad@test.ru", status="blocked", block_reason="спам в чатах")
    resp = api.post("/api/auth/login", {"email": "bad@test.ru", "password": PASSWORD})
    assert resp.status_code == 400
    assert "спам в чатах" in resp.json()["detail"]
    assert not api.cookies.get("access_token")


def test_blocked_during_session_is_logged_out(api, db):
    user = make_user(db)
    api.login(user)
    user.status, user.block_reason = "blocked", "нарушение правил"
    db.flush()
    resp = api.get("/api/auth/me")
    assert resp.status_code == 403
    assert "нарушение правил" in resp.json()["detail"]
    assert api.get("/api/auth/me").json() is None


def test_logout(api, db):
    api.login(make_user(db))
    assert api.post("/api/auth/logout").status_code == 200
    assert api.get("/api/auth/me").json() is None


def test_refresh_issues_new_access_token(api, db):
    user = make_user(db)
    api.login(user)
    api.cookies.delete("access_token")
    assert api.get("/api/auth/me").json() is None
    resp = api.post("/api/auth/refresh")
    assert resp.status_code == 200
    assert api.get("/api/auth/me").json()["id"] == user.id


def test_refresh_without_cookie_is_401(api):
    assert api.post("/api/auth/refresh").status_code == 401


def test_csrf_header_required(api, db):
    make_user(db, email="anna@test.ru")
    resp = api.c.post("/api/auth/login", json={"email": "anna@test.ru", "password": PASSWORD})
    assert resp.status_code == 403
    resp = api.c.post(
        "/api/auth/login",
        json={"email": "anna@test.ru", "password": PASSWORD},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_password_reset_prints_console_email(api, db, capsys):
    user = make_user(db)
    resp = api.post("/api/auth/password/reset", {"email": user.email})
    assert resp.status_code == 200
    out = capsys.readouterr().out
    assert "/accounts/password/reset/" in out and user.email in out
    token = out.split("/accounts/password/reset/")[1].split("/")[0]
    resp = api.post(
        "/api/auth/password/reset/confirm", {"token": token, "new_password1": "brandnew1", "new_password2": "brandnew1"}
    )
    assert resp.status_code == 200
    db.refresh(user)
    assert verify_password("brandnew1", user.password_hash)
    # ссылка одноразовая: пароль сменился — токен больше не подходит
    resp = api.post(
        "/api/auth/password/reset/confirm", {"token": token, "new_password1": "another12", "new_password2": "another12"}
    )
    assert resp.status_code == 400


def test_password_reset_unknown_email_is_silent(api, capsys):
    assert api.post("/api/auth/password/reset", {"email": "nobody@test.ru"}).status_code == 200
    assert "Восстановление" not in capsys.readouterr().out


def test_password_change(api, db):
    user = make_user(db)
    api.login(user)
    resp = api.post(
        "/api/auth/password/change",
        {"old_password": PASSWORD, "new_password1": "newpass456", "new_password2": "newpass456"},
    )
    assert resp.status_code == 200
    db.refresh(user)
    assert verify_password("newpass456", user.password_hash)
    assert api.get("/api/auth/me").json()["id"] == user.id  # новые cookie выданы


def test_password_change_wrong_old(api, db):
    api.login(make_user(db))
    resp = api.post(
        "/api/auth/password/change", {"old_password": "nope12345", "new_password1": "newpass456", "new_password2": "x"}
    )
    assert resp.status_code == 422
    assert "old_password" in resp.json()["fields"]


def test_user_email_normalized(db):
    u = make_user(db, email="A@Example.ru")
    assert u.email == "a@example.ru" and u.status == "active" and not u.is_staff


def test_site_config(api):
    data = api.get("/api/auth/config").json()
    assert data["hold_days"] == 7 and data["commission_percent"] == 10 and data["max_revisions"] == 2

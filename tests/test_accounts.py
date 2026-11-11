import pytest
from django.core import mail

from apps.accounts.models import User
from tests.factories import PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


def _reg_data(**over):
    data = {
        "email": "New@Test.ru",
        "username": "new_user",
        "password1": "secret123",
        "password2": "secret123",
        "accept_terms": "on",
    }
    data.update(over)
    return data


def test_register_creates_user_and_logs_in(client):
    resp = client.post("/accounts/register/", _reg_data())
    assert resp.status_code == 302
    user = User.objects.get(email="new@test.ru")
    assert user.terms_accepted_at is not None
    assert client.get("/me/profile/").status_code == 200


def test_register_requires_terms(client):
    resp = client.post("/accounts/register/", _reg_data(accept_terms=""))
    assert resp.status_code == 200
    assert not User.objects.exists()
    assert "Без согласия регистрация невозможна" in resp.content.decode()


@pytest.mark.parametrize(
    "over,error",
    [
        ({"password1": "short1", "password2": "short1"}, "не короче"),
        ({"password1": "onlyletters", "password2": "onlyletters"}, "буквы и цифры"),
        ({"password1": "12345678901", "password2": "12345678901"}, "буквы и цифры"),
        ({"password2": "other1234"}, "не совпадают"),
        ({"username": "ab"}, "3–30"),
        ({"username": "имя"}, "3–30"),
    ],
)
def test_register_validation(client, over, error):
    resp = client.post("/accounts/register/", _reg_data(**over))
    assert resp.status_code == 200
    assert error in resp.content.decode().lower() or error in resp.content.decode()
    assert not User.objects.exists()


def test_register_duplicate_email(client):
    UserFactory(email="new@test.ru")
    resp = client.post("/accounts/register/", _reg_data())
    assert "уже есть" in resp.content.decode()


def test_login_by_email_case_insensitive(client):
    UserFactory(email="anna@test.ru")
    resp = client.post("/accounts/login/", {"username": "ANNA@test.ru", "password": PASSWORD})
    assert resp.status_code == 302
    assert "_auth_user_id" in client.session


def test_login_wrong_password(client):
    UserFactory(email="anna@test.ru")
    resp = client.post("/accounts/login/", {"username": "anna@test.ru", "password": "wrong1234"})
    assert resp.status_code == 200
    assert "Неверный email или пароль" in resp.content.decode()


def test_blocked_user_cannot_login_and_sees_reason(client):
    UserFactory(email="bad@test.ru", status=User.Status.BLOCKED, block_reason="спам в чатах")
    resp = client.post("/accounts/login/", {"username": "bad@test.ru", "password": PASSWORD})
    assert resp.status_code == 200
    assert "спам в чатах" in resp.content.decode()
    assert "_auth_user_id" not in client.session


def test_blocked_during_session_is_logged_out(client):
    user = UserFactory()
    client.force_login(user)
    User.objects.filter(pk=user.pk).update(status="blocked", block_reason="нарушение правил")
    resp = client.get("/", follow=True)
    assert "нарушение правил" in resp.content.decode()
    assert "_auth_user_id" not in client.session


def test_logout(client, user):
    client.force_login(user)
    resp = client.post("/accounts/logout/")
    assert resp.status_code == 302
    assert "_auth_user_id" not in client.session


def test_profile_update(client, user):
    client.force_login(user)
    resp = client.post("/me/profile/", {"username": "renamed", "github_login": "@octo-cat"})
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.username == "renamed"
    assert user.github_login == "octo-cat"


def test_profile_requires_login(client):
    resp = client.get("/me/profile/")
    assert resp.status_code == 302
    assert "/accounts/login/" in resp["Location"]


def test_password_reset_sends_console_email(client, user):
    resp = client.post("/accounts/password/reset/", {"email": user.email})
    assert resp.status_code == 302
    assert len(mail.outbox) == 1
    assert "/accounts/password/reset/" in mail.outbox[0].body


def test_password_change(client, user):
    client.force_login(user)
    resp = client.post(
        "/accounts/password/change/",
        {"old_password": PASSWORD, "new_password1": "newpass456", "new_password2": "newpass456"},
    )
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.check_password("newpass456")

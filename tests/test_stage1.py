import pytest
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_home_opens_with_styles(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "css/theme.css" in html
    assert "— CodeMarket</title>" in html
    assert "Code<span>Market</span>" in html


@pytest.mark.django_db
def test_custom_user_model():
    User = get_user_model()
    assert User._meta.label == "accounts.User"
    u = User.objects.create_user(email="A@Example.ru", username="anna_1", password="pass1234")
    assert u.email == "a@example.ru"
    assert u.status == "active"
    assert not u.is_staff


@pytest.mark.django_db
@pytest.mark.parametrize("slug", ["terms", "seller", "license", "privacy"])
def test_legal_pages(client, slug):
    resp = client.get(f"/legal/{slug}/")
    assert resp.status_code == 200
    assert "не является публичной офертой" in resp.content.decode()

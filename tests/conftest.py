import shutil

import pytest


@pytest.fixture(autouse=True)
def _isolated_storage(settings, tmp_path):
    """Файлы тестов пишутся во временные папки, а не в media/ и private/."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PRIVATE_ROOT = tmp_path / "private"
    settings.PAYMENT_PROVIDER = "fake"
    settings.GITHUB_MODE = "fake"
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    yield
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def user(db):
    from tests.factories import UserFactory

    return UserFactory()


@pytest.fixture
def admin_user(db):
    from tests.factories import UserFactory

    return UserFactory(is_staff=True, is_superuser=True, username="admin", email="admin@test.ru")

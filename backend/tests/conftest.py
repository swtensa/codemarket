"""Тестовая база codemarket_test (создаётся сама), транзакция на тест, изолированные папки файлов."""

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.core.config import settings

TEST_URL = settings.effective_test_database_url
settings.database_url = TEST_URL  # до импорта app.core.db: движок приложения смотрит в тестовую базу


def _ensure_database():
    url = make_url(TEST_URL)
    conninfo = dict(
        host=url.host or "localhost", port=url.port or 5432, user=url.username, password=url.password, dbname="postgres"
    )
    with psycopg.connect(**conninfo, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)).fetchone():
            conn.execute(f'CREATE DATABASE "{url.database}"')


@pytest.fixture(scope="session")
def engine():
    _ensure_database()
    eng = create_engine(TEST_URL)
    from alembic.config import Config

    from alembic import command
    from app.core.config import BASE_DIR

    with eng.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.attributes["url"] = TEST_URL
    command.upgrade(cfg, "head")  # заодно проверяется сама миграция
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """Сессия в транзакции, которая откатывается после теста (commit в коде = точка сохранения)."""
    from sqlalchemy.orm import Session

    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def _isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_public", tmp_path / "public")
    monkeypatch.setattr(settings, "storage_private", tmp_path / "private")
    monkeypatch.setattr(settings, "github_fake_root", tmp_path / "repos")
    monkeypatch.setattr(settings, "payment_provider", "fake")
    monkeypatch.setattr(settings, "github_mode", "fake")
    (tmp_path / "public").mkdir()
    (tmp_path / "private").mkdir()


class ApiClient:
    """TestClient с CSRF: перед изменяющим запросом подставляет заголовок X-CSRF-Token из cookie."""

    def __init__(self, client):
        self.c = client
        self.c.get("/api/auth/me")

    def _headers(self, kw):
        headers = kw.pop("headers", {}) or {}
        token = self.c.cookies.get("csrf_token")
        if token:
            headers.setdefault("X-CSRF-Token", token)
        return headers

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self._headers(kw), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=self._headers(kw), **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(url, json=json, headers=self._headers(kw), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._headers(kw), **kw)

    @property
    def cookies(self):
        return self.c.cookies

    def login(self, user, password="secret123"):
        resp = self.post("/api/auth/login", {"email": user.email, "password": password})
        assert resp.status_code == 200, resp.text
        return resp


@pytest.fixture
def api(db):
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import app

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, base_url="http://testserver") as client:
        yield ApiClient(client)
    app.dependency_overrides.clear()


def make_api(db):
    """Второй независимый клиент (другой пользователь) в том же тесте."""
    from fastapi.testclient import TestClient

    from app.main import app

    return ApiClient(TestClient(app, base_url="http://testserver"))


@pytest.fixture
def api2(api, db):
    return make_api(db)

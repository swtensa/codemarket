"""Настройки приложения: читаются из backend/.env (pydantic-settings). Пример — .env.example."""

from decimal import Decimal
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # папка backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    debug: bool = False
    secret_key: str = "dev-insecure-key-change-me"
    database_url: str = "postgresql+psycopg://codemarket:codemarket_password@localhost:5432/codemarket"
    test_database_url: str = ""
    site_url: str = "http://127.0.0.1:8000"
    time_zone: str = "Asia/Yekaterinburg"

    # авторизация
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    cookie_secure: bool = False

    # файлы
    storage_public: Path = BASE_DIR / "storage" / "public"
    storage_private: Path = BASE_DIR / "storage" / "private"
    github_fake_root: Path = BASE_DIR / "fixtures" / "demo" / "repos"
    log_dir: Path = BASE_DIR / "logs"
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"

    # бизнес-параметры (раздел 6 ТЗ)
    platform_commission: Decimal = Decimal("0.10")
    hold_days: int = 7
    auto_accept_days: int = 3
    payment_timeout_min: int = 30
    max_revisions: int = 2
    min_payout: Decimal = Decimal("500")
    license_version: str = "1.0"

    # проверка на заимствования
    plag_k: int = 15
    plag_w: int = 16
    plag_reject: float = 0.7
    plag_flag: float = 0.3
    plag_common_sellers: int = 6
    max_archive_mb: int = 50
    max_files: int = 2000

    rate_limit_questions_per_hour: int = 10
    rate_limit_messages_per_hour: int = 30

    # интеграции
    payment_provider: str = "fake"
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    github_mode: str = "fake"
    github_app_id: str = ""
    github_app_slug: str = ""
    github_private_key_path: str = ""
    github_org: str = "codemarket-demo"
    github_webhook_secret: str = ""

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        """postgres://… из старого .env → postgresql+psycopg://…"""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @property
    def effective_test_database_url(self) -> str:
        if self.test_database_url:
            return self.test_database_url
        base, _, _name = self.database_url.rpartition("/")
        return f"{base}/codemarket_test"


settings = Settings()

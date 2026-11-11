"""Настройки проекта CodeMarket.

Все секреты и параметры окружения читаются из файла `.env` (django-environ).
Пример значений лежит в `.env.example`.
"""

from decimal import Decimal
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.versions",
    "apps.plagiarism",
    "apps.purchases",
    "apps.orders",
    "apps.payments",
    "apps.balance",
    "apps.disputes",
    "apps.reviews",
    "apps.notifications",
    "apps.reports",
    "apps.moderation",
    "apps.integrations.github",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.BlockedUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "catalog:index"
LOGOUT_REDIRECT_URL = "catalog:index"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "apps.accounts.validators.LettersAndDigitsValidator"},
]

LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Yekaterinburg"
USE_I18N = True
USE_TZ = True
DATETIME_FORMAT = "d.m.Y H:i"
DATE_FORMAT = "d.m.Y"

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Публичные файлы (скриншоты) раздаются через MEDIA_URL.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Закрытое хранилище (архивы версий, вложения чата) вне MEDIA_ROOT,
# файлы отдаются только через view с проверкой права.
PRIVATE_ROOT = BASE_DIR / "private"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@codemarket.local"

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Бизнес-параметры площадки ---
PLATFORM_COMMISSION = Decimal(env("PLATFORM_COMMISSION", default="0.10"))
HOLD_DAYS = env.int("HOLD_DAYS", default=7)
AUTO_ACCEPT_DAYS = env.int("AUTO_ACCEPT_DAYS", default=3)
PAYMENT_TIMEOUT_MIN = env.int("PAYMENT_TIMEOUT_MIN", default=30)
MAX_REVISIONS = env.int("MAX_REVISIONS", default=2)
MIN_PAYOUT = Decimal(env("MIN_PAYOUT", default="500"))
LICENSE_VERSION = env("LICENSE_VERSION", default="1.0")

PLAG_K = env.int("PLAG_K", default=15)
PLAG_W = env.int("PLAG_W", default=16)
PLAG_REJECT = env.float("PLAG_REJECT", default=0.7)
PLAG_FLAG = env.float("PLAG_FLAG", default=0.3)
PLAG_COMMON_SELLERS = env.int("PLAG_COMMON_SELLERS", default=6)
MAX_ARCHIVE_MB = env.int("MAX_ARCHIVE_MB", default=50)
MAX_FILES = env.int("MAX_FILES", default=2000)

RATE_LIMIT_QUESTIONS_PER_HOUR = 10
RATE_LIMIT_MESSAGES_PER_HOUR = 30

# --- Интеграции ---
SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="fake")
YOOKASSA_SHOP_ID = env("YOOKASSA_SHOP_ID", default="")
YOOKASSA_SECRET_KEY = env("YOOKASSA_SECRET_KEY", default="")

GITHUB_MODE = env("GITHUB_MODE", default="fake")
GITHUB_APP_ID = env("GITHUB_APP_ID", default="")
GITHUB_APP_SLUG = env("GITHUB_APP_SLUG", default="")
GITHUB_PRIVATE_KEY_PATH = env("GITHUB_PRIVATE_KEY_PATH", default="")
GITHUB_ORG = env("GITHUB_ORG", default="codemarket-demo")
GITHUB_WEBHOOK_SECRET = env("GITHUB_WEBHOOK_SECRET", default="")
GITHUB_FAKE_ROOT = BASE_DIR / "fixtures" / "demo" / "repos"

# --- Логи ---
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "errors": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "errors.log",
            "level": "ERROR",
            "formatter": "plain",
            "encoding": "utf-8",
        },
        "webhooks": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "webhooks.log",
            "formatter": "plain",
            "encoding": "utf-8",
        },
        "admin_actions": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "admin_actions.log",
            "formatter": "plain",
            "encoding": "utf-8",
        },
        "integrations": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "integrations.log",
            "formatter": "plain",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "errors"], "level": "INFO"},
        "codemarket": {"handlers": ["console", "errors"], "level": "INFO"},
        "codemarket.webhooks": {"handlers": ["webhooks"], "level": "INFO"},
        "codemarket.admin": {"handlers": ["admin_actions"], "level": "INFO"},
        "codemarket.github": {"handlers": ["integrations"], "level": "INFO"},
    },
}

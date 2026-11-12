"""Пароли (pwdlib, argon2), JWT в httpOnly cookie, CSRF double submit."""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from .config import settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"
ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
VISITOR_COOKIE = "visitor"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


def hash_password(raw: str) -> str:
    return password_hash.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return password_hash.verify(raw, hashed)
    except Exception:
        return False


def password_errors(raw: str) -> list[str]:
    """Правила пароля Django-версии: не короче 8 символов, есть буквы и цифры."""
    errors = []
    if len(raw) < 8:
        errors.append("Пароль слишком короткий: не короче 8 символов.")
    if not re.search(r"[A-Za-zА-Яа-яЁё]", raw) or not re.search(r"\d", raw):
        errors.append("Пароль должен содержать буквы и цифры.")
    return errors


def _fingerprint(hashed: str) -> str:
    """Отпечаток хеша пароля в токене: после смены пароля старые токены недействительны."""
    return hashlib.sha256(hashed.encode()).hexdigest()[:16]


def make_token(user, kind: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "type": kind,
        "ph": _fingerprint(user.password_hash),
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def read_token(token: str | None, kind: str) -> tuple[int, str] | None:
    """(id пользователя, отпечаток пароля) или None, если токен неверный или истёк."""
    if not token:
        return None
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if data.get("type") != kind:
        return None
    try:
        return int(data["sub"]), data.get("ph", "")
    except (KeyError, ValueError):
        return None


def token_matches(user, fingerprint: str) -> bool:
    return secrets.compare_digest(_fingerprint(user.password_hash), fingerprint or "")


def set_auth_cookies(response: Response, user) -> None:
    common = {"httponly": True, "samesite": "lax", "secure": settings.cookie_secure, "path": "/"}
    response.set_cookie(
        ACCESS_COOKIE,
        make_token(user, "access", timedelta(minutes=settings.access_token_minutes)),
        max_age=settings.access_token_minutes * 60,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        make_token(user, "refresh", timedelta(days=settings.refresh_token_days)),
        max_age=settings.refresh_token_days * 86400,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)

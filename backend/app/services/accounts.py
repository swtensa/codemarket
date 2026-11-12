"""Аккаунты: регистрация с согласием, вход, пароль, профиль, логин GitHub, блокировка."""

import logging
import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import FieldsError, ServiceError
from app.core.security import (
    USERNAME_RE,
    hash_password,
    make_token,
    password_errors,
    read_token,
    token_matches,
    verify_password,
)
from app.models import User, UserStatus
from app.models.base import utcnow

log = logging.getLogger("codemarket")
admin_log = logging.getLogger("codemarket.admin")
GITHUB_LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_HASH = hash_password("timing-equaliser-1")


def by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == (email or "").strip().lower()))


def create_user(db: Session, *, email, username, password, is_staff=False, **extra) -> User:
    """Создать пользователя без проверок формы (seed, тесты, администратор)."""
    user = User(
        email=email.strip().lower(),
        username=username,
        password_hash=hash_password(password),
        is_staff=is_staff,
        is_superuser=is_staff,
        **extra,
    )
    db.add(user)
    db.flush()
    return user


def clean_github_login(value: str | None) -> str:
    login = (value or "").strip().lstrip("@")
    if login and not GITHUB_LOGIN_RE.fullmatch(login):
        raise ServiceError("Похоже, это не логин GitHub: латиница, цифры и дефис, до 39 символов.")
    return login


# ---------------------------------------------------------------- регистрация и вход


def register_user(db: Session, *, email, username, password1, password2, accept_terms) -> User:
    """Регистрация с обязательным согласием с соглашением и политикой ПДн (раздел 10 ТЗ)."""
    errors: dict[str, str] = {}
    email = (email or "").strip().lower()
    username = (username or "").strip()
    if not EMAIL_RE.match(email) or len(email) > 254:
        errors["email"] = "Введите правильный адрес электронной почты."
    elif by_email(db, email):
        errors["email"] = "Пользователь с таким email уже есть."
    if not USERNAME_RE.match(username):
        errors["username"] = "Имя пользователя: 3–30 символов, латинские буквы, цифры и знак подчёркивания."
    elif db.scalar(select(User.id).where(func.lower(User.username) == username.lower())):
        errors["username"] = "Это имя уже занято."
    if not password1:
        errors["password1"] = "Обязательное поле."
    else:
        problems = password_errors(password1)
        if problems:
            errors["password1"] = " ".join(problems)
    if password1 and password2 != password1:
        errors["password2"] = "Пароли не совпадают."
    if not accept_terms:
        errors["accept_terms"] = "Без согласия регистрация невозможна."
    if errors:
        raise FieldsError(errors)
    user = create_user(db, email=email, username=username, password=password1, terms_accepted_at=utcnow())
    user.last_login = utcnow()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    """Вход по email и паролю. Заблокированному показывается причина блокировки."""
    user = by_email(db, email)
    if user is None:
        verify_password(password or "", _DUMMY_HASH)  # выравнивание времени ответа
        raise ServiceError("Неверный email или пароль.")
    if not verify_password(password or "", user.password_hash):
        raise ServiceError("Неверный email или пароль.")
    if user.is_blocked:
        raise ServiceError(f"Аккаунт заблокирован. Причина: {user.block_reason or 'не указана'}")
    user.last_login = utcnow()
    return user


def user_from_refresh(db: Session, token: str | None) -> User | None:
    data = read_token(token, "refresh")
    if data is None:
        return None
    user = db.get(User, data[0])
    if user is None or not token_matches(user, data[1]) or user.is_blocked:
        return None
    return user


def change_password(db: Session, user: User, *, old_password, new_password1, new_password2) -> User:
    errors = {}
    if not verify_password(old_password or "", user.password_hash):
        errors["old_password"] = "Старый пароль введён неверно."
    problems = password_errors(new_password1 or "")
    if problems:
        errors["new_password1"] = " ".join(problems)
    elif new_password1 != new_password2:
        errors["new_password2"] = "Пароли не совпадают."
    if errors:
        raise FieldsError(errors)
    user.password_hash = hash_password(new_password1)
    return user


def request_password_reset(db: Session, email: str) -> None:
    """Письмо со ссылкой восстановления выводится в консоль сервера (почта не настраивается)."""
    user = by_email(db, email)
    if user is None or user.is_blocked:
        return
    token = make_token(user, "reset", timedelta(days=1))
    link = f"{settings.site_url.rstrip('/')}/accounts/password/reset/{token}/"
    letter = (
        "\n" + "=" * 70 + f"\nКому: {user.email}\nТема: Восстановление пароля на CodeMarket\n\n"
        f"Здравствуйте, {user.username}!\nЧтобы задать новый пароль, откройте ссылку (действует сутки):\n{link}\n"
        "Если вы не запрашивали восстановление, просто проигнорируйте письмо.\n" + "=" * 70
    )
    print(letter, flush=True)
    log.info("Письмо восстановления пароля для %s выведено в консоль", user.email)


def reset_password(db: Session, *, token, new_password1, new_password2) -> User:
    data = read_token(token, "reset")
    user = db.get(User, data[0]) if data else None
    if user is None or not token_matches(user, data[1]):
        raise ServiceError("Ссылка восстановления недействительна или уже использована. Запросите новую.")
    problems = password_errors(new_password1 or "")
    if problems:
        raise FieldsError({"new_password1": " ".join(problems)})
    if new_password1 != new_password2:
        raise FieldsError({"new_password2": "Пароли не совпадают."})
    user.password_hash = hash_password(new_password1)
    return user


# ---------------------------------------------------------------- профиль


def update_profile(db: Session, user: User, *, username: str, github_login: str) -> User:
    """Изменить имя и логин GitHub. При смене логина доступ к купленным копиям переходит на новый."""
    from app.services.purchases import on_github_login_changed

    username = (username or "").strip()
    errors = {}
    if not USERNAME_RE.match(username):
        errors["username"] = "Имя пользователя: 3–30 символов, латинские буквы, цифры и знак подчёркивания."
    elif db.scalar(select(User.id).where(func.lower(User.username) == username.lower(), User.id != user.id)):
        errors["username"] = "Это имя уже занято."
    try:
        login = clean_github_login(github_login)
    except ServiceError as e:
        errors["github_login"] = e.message
    if errors:
        raise FieldsError(errors)
    old_login = user.github_login
    user.username = username
    user.github_login = login
    db.flush()
    on_github_login_changed(db, user, old_login)
    return user


def set_github_login(db: Session, user: User, github_login: str) -> User:
    """Сохранить логин GitHub (со страницы покупки). Неверный формат — ServiceError."""
    from app.services.purchases import on_github_login_changed

    login = clean_github_login(github_login)
    old_login = user.github_login
    user.github_login = login
    db.flush()
    on_github_login_changed(db, user, old_login)
    return user


def accept_seller_terms(db: Session, user: User) -> User:
    """Зафиксировать принятие условий для продавцов (один раз)."""
    if user.seller_terms_accepted_at is None:
        user.seller_terms_accepted_at = utcnow()
    return user


def connect_github(db: Session, user: User, installation_id: int) -> User:
    """Сохранить id установки GitHub App (токены продавца не храним)."""
    user.github_installation_id = int(installation_id)
    return user


def disconnect_github_installation(db: Session, installation_id: int) -> int:
    """Установка удалена на стороне GitHub — забыть её."""
    users = db.scalars(select(User).where(User.github_installation_id == installation_id)).all()
    for u in users:
        u.github_installation_id = None
    return len(users)


# ---------------------------------------------------------------- блокировка


def block_user(db: Session, user: User, *, reason: str, admin: User) -> User:
    """Заблокировать: продукты скрываются из каталога, заказы обрабатываются по разделу 7.4 ТЗ."""
    from app.services.orders import handle_seller_blocked

    if not reason or not reason.strip():
        raise ServiceError("Укажите причину блокировки.")
    if user.is_staff:
        raise ServiceError("Нельзя заблокировать администратора.")
    user.status = UserStatus.BLOCKED
    user.block_reason = reason.strip()
    db.flush()
    handle_seller_blocked(db, user, admin=admin)
    admin_log.info("admin=%s blocked user=%s reason=%s", admin.username, user.id, reason)
    return user


def unblock_user(db: Session, user: User, *, admin: User) -> User:
    user.status = UserStatus.ACTIVE
    user.block_reason = ""
    admin_log.info("admin=%s unblocked user=%s", admin.username, user.id)
    return user

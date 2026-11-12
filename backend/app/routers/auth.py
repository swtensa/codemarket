"""Регистрация, вход, выход, обновление токена, пароль."""

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.deps import DB, CurrentUser, OptionalUser
from app.core.errors import Unauthorized
from app.core.security import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.schemas.common import Ok
from app.schemas.users import (
    LoginIn,
    PasswordChangeIn,
    RegisterIn,
    ResetConfirmIn,
    ResetRequestIn,
    SiteConfig,
    UserOut,
)
from app.services import accounts

router = APIRouter(prefix="/api/auth", tags=["авторизация"])


@router.get("/config", response_model=SiteConfig)
def site_config():
    """Параметры площадки для интерфейса (сроки, комиссия, режимы интеграций)."""
    return SiteConfig(
        hold_days=settings.hold_days,
        license_version=settings.license_version,
        max_revisions=settings.max_revisions,
        auto_accept_days=settings.auto_accept_days,
        payment_provider=settings.payment_provider,
        github_mode=settings.github_mode,
        commission_percent=int(settings.platform_commission * 100),
        min_payout=int(settings.min_payout),
        payment_timeout_min=settings.payment_timeout_min,
    )


@router.get("/me", response_model=UserOut | None)
def me(user: OptionalUser):
    """Текущий пользователь или null. Заодно выдаёт cookie csrf_token."""
    return user


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, response: Response, db: DB):
    user = accounts.register_user(db, **data.model_dump())
    db.commit()
    set_auth_cookies(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(data: LoginIn, response: Response, db: DB):
    user = accounts.authenticate(db, data.email, data.password)
    db.commit()
    set_auth_cookies(response, user)
    return user


@router.post("/logout", response_model=Ok)
def logout(response: Response):
    clear_auth_cookies(response)
    return Ok()


@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, db: DB):
    """Новая пара токенов по refresh-cookie (access живёт 30 минут, refresh — 14 дней)."""
    user = accounts.user_from_refresh(db, request.cookies.get(REFRESH_COOKIE))
    if user is None:
        clear_auth_cookies(response)
        raise Unauthorized("Сессия истекла, войдите снова.")
    set_auth_cookies(response, user)
    return user


@router.post("/password/change", response_model=Ok)
def password_change(data: PasswordChangeIn, response: Response, user: CurrentUser, db: DB):
    accounts.change_password(db, user, **data.model_dump())
    db.commit()
    set_auth_cookies(response, user)  # старые токены (и на других устройствах) больше не действуют
    return Ok(message="Пароль изменён.")


@router.post("/password/reset", response_model=Ok)
def password_reset(data: ResetRequestIn, db: DB):
    accounts.request_password_reset(db, data.email)
    return Ok(message="Если такой адрес зарегистрирован, мы отправили на него письмо со ссылкой.")


@router.post("/password/reset/confirm", response_model=Ok)
def password_reset_confirm(data: ResetConfirmIn, db: DB):
    accounts.reset_password(db, **data.model_dump())
    db.commit()
    return Ok(message="Пароль изменён. Теперь можно войти.")

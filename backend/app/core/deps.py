"""Зависимости роутеров: сессия БД, текущий пользователь, проверки ролей."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.models import User

from .db import get_db
from .errors import Forbidden, ServiceError, Unauthorized
from .security import ACCESS_COOKIE, read_token, token_matches

DB = Annotated[Session, Depends(get_db)]


class AccountBlocked(ServiceError):
    """Пользователя заблокировали: выйти из аккаунта и показать причину (cookie удаляет обработчик)."""

    status_code = 403
    clear_auth = True

    def __init__(self, reason: str):
        super().__init__(f"Аккаунт заблокирован. Причина: {reason or 'не указана'}")


def optional_user(request: Request, db: DB) -> User | None:
    data = read_token(request.cookies.get(ACCESS_COOKIE), "access")
    if data is None:
        return None
    user = db.get(User, data[0])
    if user is None or not token_matches(user, data[1]):
        return None
    if user.is_blocked:
        raise AccountBlocked(user.block_reason)
    return user


def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise Unauthorized()
    return user


def staff_user(user: Annotated[User, Depends(current_user)]) -> User:
    """Только администратор (is_staff), остальным — 403."""
    if not user.is_staff:
        raise Forbidden()
    return user


def seller_user(user: Annotated[User, Depends(current_user)]) -> User:
    """Только продавец с подключённым GitHub."""
    if not user.is_seller:
        raise Forbidden("Чтобы продавать, подключите GitHub.")
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]
CurrentUser = Annotated[User, Depends(current_user)]
StaffUser = Annotated[User, Depends(staff_user)]
SellerUser = Annotated[User, Depends(seller_user)]


def visitor_id(request: Request) -> str:
    return getattr(request.state, "visitor", "") or "anonymous"

"""Пользователь площадки. Администратор — флаг is_staff."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Choices, Created, OptDateTime


class UserStatus(Choices):
    ACTIVE = "active"
    BLOCKED = "blocked"
    LABELS = {ACTIVE: "Активен", BLOCKED: "Заблокирован"}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    username: Mapped[str] = mapped_column(String(30), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    github_login: Mapped[str] = mapped_column(String(39), default="")
    github_installation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default=UserStatus.ACTIVE)
    block_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[Created]
    last_login: Mapped[OptDateTime]
    terms_accepted_at: Mapped[OptDateTime]
    seller_terms_accepted_at: Mapped[OptDateTime]

    def __repr__(self) -> str:
        return f"<User {self.username}>"

    @property
    def is_blocked(self) -> bool:
        return self.status == UserStatus.BLOCKED

    @property
    def is_seller(self) -> bool:
        """Раздел «Продажи» появляется после подключения GitHub."""
        return self.github_installation_id is not None


__all__ = ["User", "UserStatus", "datetime"]

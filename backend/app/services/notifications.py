"""Уведомления на сайте."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Notification, User


def notify(db: Session, user: User | None, text: str, link: str = "") -> Notification | None:
    """Создать уведомление пользователю."""
    if user is None:
        return None
    n = Notification(user_id=user.id, text=text[:500], link=link or "")
    db.add(n)
    db.flush()
    return n


def notify_many(db: Session, users, text: str, link: str = "") -> int:
    """Создать одинаковое уведомление нескольким пользователям."""
    users = list(users)
    db.add_all([Notification(user_id=u.id, text=text[:500], link=link or "") for u in users])
    db.flush()
    return len(users)


def unread_count(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.is_read.is_(False))) or 0


def mark_all_read(db: Session, user: User) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    return result.rowcount or 0


def open_notification(db: Session, user: User, notification_id: int) -> str:
    """Отметить уведомление прочитанным и вернуть его ссылку (только внутренние адреса)."""
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise NotFound()
    n.is_read = True
    link = n.link or "/notifications/"
    if not link.startswith("/") or link.startswith("//"):
        link = "/notifications/"
    return link


def admins(db: Session):
    return db.scalars(select(User).where(User.is_staff.is_(True), User.status == "active")).all()


def notify_admins(db: Session, text: str, link: str = "/moderation/") -> int:
    return notify_many(db, db.scalars(select(User).where(User.is_staff.is_(True))).all(), text, link)

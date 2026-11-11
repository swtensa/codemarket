"""Сервис уведомлений на сайте."""

from .models import Notification


def notify(user, text, link=""):
    """Создать уведомление пользователю."""
    if user is None:
        return None
    return Notification.objects.create(user=user, text=text[:500], link=link or "")


def notify_many(users, text, link=""):
    """Создать одинаковое уведомление нескольким пользователям."""
    objs = [Notification(user=u, text=text[:500], link=link or "") for u in users]
    return Notification.objects.bulk_create(objs)


def unread_count(user):
    """Число непрочитанных уведомлений пользователя."""
    return Notification.objects.filter(user=user, is_read=False).count()


def mark_all_read(user):
    """Отметить все уведомления пользователя прочитанными."""
    return Notification.objects.filter(user=user, is_read=False).update(is_read=True)


def open_notification(user, notification_id):
    """Отметить уведомление прочитанным и вернуть его ссылку."""
    n = Notification.objects.get(pk=notification_id, user=user)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=["is_read"])
    return n.link or "/notifications/"

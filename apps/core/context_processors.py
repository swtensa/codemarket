from django.conf import settings


def site(request):
    """Общие данные для шапки: число непрочитанных уведомлений, режимы."""
    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from apps.notifications.services import unread_count

        unread = unread_count(user)
    return {
        "unread_notifications": unread,
        "SITE_NAME": "CodeMarket",
        "HOLD_DAYS": settings.HOLD_DAYS,
        "LICENSE_VERSION": settings.LICENSE_VERSION,
        "PAYMENT_PROVIDER": settings.PAYMENT_PROVIDER,
        "GITHUB_MODE": settings.GITHUB_MODE,
    }

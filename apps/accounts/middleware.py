from django.contrib.auth import logout
from django.shortcuts import redirect


class BlockedUserMiddleware:
    """Если пользователя заблокировали во время сессии — разлогинить и показать причину."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_blocked:
            reason = user.block_reason
            logout(request)
            request.session["blocked_reason"] = reason or "не указана"
            return redirect("accounts:blocked")
        return self.get_response(request)

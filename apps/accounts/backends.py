from django.contrib.auth.backends import ModelBackend

from .models import User


class EmailBackend(ModelBackend):
    """Вход по email (без учёта регистра). Заблокированные не входят."""

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        login = (email or username or "").strip().lower()
        if not login or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=login)
        except User.DoesNotExist:
            User().set_password(password)  # выравнивание времени ответа
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and not user.is_blocked

"""Интеграция с GitHub. Режим выбирается настройкой GITHUB_MODE=fake|real."""


def get_client():
    """Вернуть клиент GitHub для текущего режима."""
    from django.conf import settings

    if settings.GITHUB_MODE == "real":
        from .client import RealGitHubClient

        return RealGitHubClient()
    from .fake import FakeGitHubClient

    return FakeGitHubClient()

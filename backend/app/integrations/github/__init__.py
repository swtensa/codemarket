"""Интеграция с GitHub. Режим выбирается настройкой GITHUB_MODE=fake|real."""


def get_client():
    """Вернуть клиент GitHub для текущего режима."""
    from app.core.config import settings

    if settings.github_mode == "real":
        from .client import RealGitHubClient

        return RealGitHubClient()
    from .fake import FakeGitHubClient

    return FakeGitHubClient()

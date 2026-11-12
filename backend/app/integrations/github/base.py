"""Общий интерфейс клиента GitHub для реального и фейкового режимов."""

from dataclasses import dataclass
from datetime import datetime


class GitHubError(Exception):
    """Ошибка обращения к GitHub (текст можно показать пользователю)."""


@dataclass
class Repo:
    id: int
    full_name: str
    private: bool = True


@dataclass
class Release:
    tag_name: str
    published_at: datetime | None
    name: str = ""
    commit_sha: str = ""


class GitHubClientBase:
    """Интерфейс клиента. Реализации: RealGitHubClient (client.py) и FakeGitHubClient (fake.py)."""

    mode = "base"

    def install_url(self, state):
        """Адрес установки GitHub App (для кнопки «Подключить GitHub»)."""
        raise NotImplementedError

    def check_installation(self, installation_id):
        """Убедиться, что установка существует; вернуть логин аккаунта установки."""
        raise NotImplementedError

    def list_repositories(self, installation_id) -> list[Repo]:
        raise NotImplementedError

    def list_releases(self, installation_id, repo_full_name) -> list[Release]:
        raise NotImplementedError

    def download_zipball(self, installation_id, repo_full_name, tag, dest_path) -> str:
        """Скачать архив релиза в dest_path; вернуть SHA коммита (если известен)."""
        raise NotImplementedError

    def ensure_mirror_repo(self, name) -> str:
        """Создать (если нет) закрытый репозиторий-копию в организации платформы; вернуть full_name."""
        raise NotImplementedError

    def publish_version(self, mirror_full_name, source_dir, tag, message) -> str:
        """Положить файлы версии одним коммитом и поставить тег; вернуть SHA коммита."""
        raise NotImplementedError

    def add_collaborator(self, mirror_full_name, login) -> str:
        """Пригласить пользователя с правом pull. Возвращает 'invited' или 'granted'."""
        raise NotImplementedError

    def remove_collaborator(self, mirror_full_name, login) -> None:
        raise NotImplementedError

    def invitation_status(self, mirror_full_name, login) -> str:
        """'granted' — приглашение принято, 'invited' — ждёт, 'none' — доступа нет."""
        raise NotImplementedError

    def mirror_url(self, mirror_full_name) -> str:
        return f"https://github.com/{mirror_full_name}"

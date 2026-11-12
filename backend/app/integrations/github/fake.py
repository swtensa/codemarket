"""Фейковый клиент GitHub: работает с локальной папкой fixtures/demo/repos без интернета.

Структура: fixtures/demo/repos/<name>/ — код «репозитория»,
fixtures/demo/repos/<name>/releases/<tag>.zip — архивы релизов.
Если у репозитория нет ни одного релиза, при запросе списка автоматически
собирается релиз v1.0.0 из кода папки (как будто продавец его создал).
Публикация в копию и приглашения только пишутся в лог и в папку private/fake_github/.
"""

import hashlib
import json
import logging
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings

from .base import GitHubClientBase, GitHubError, Release, Repo

log = logging.getLogger("codemarket.github")

FAKE_OWNER = "demo-seller"


def _repo_dir(repo_full_name):
    name = repo_full_name.split("/")[-1]
    root = Path(settings.github_fake_root).resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.is_dir():
        raise GitHubError(f"Репозиторий {repo_full_name} не найден")
    return path


def build_release_zip(repo_dir, tag):
    """Собрать zip релиза из кода папки (как zipball GitHub: с корневой папкой)."""
    repo_dir = Path(repo_dir)
    releases = repo_dir / "releases"
    releases.mkdir(exist_ok=True)
    target = releases / f"{tag}.zip"
    files = sorted(p for p in repo_dir.rglob("*") if p.is_file() and releases not in p.parents)
    digest = hashlib.sha1()
    for f in files:
        digest.update(str(f.relative_to(repo_dir)).encode())
        digest.update(f.read_bytes())
    sha = digest.hexdigest()
    prefix = f"{FAKE_OWNER}-{repo_dir.name}-{sha[:7]}"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f"{prefix}/{f.relative_to(repo_dir).as_posix()}")
    return target


class FakeGitHubClient(GitHubClientBase):
    mode = "fake"

    @property
    def state_dir(self):
        d = Path(settings.storage_private) / "fake_github"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _state(self):
        f = self.state_dir / "state.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"collaborators": {}}

    def _save_state(self, state):
        (self.state_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def install_url(self, state):
        return None  # в fake-режиме установка подтверждается кнопкой на сайте

    def check_installation(self, installation_id):
        return FAKE_OWNER

    def list_repositories(self, installation_id):
        root = Path(settings.github_fake_root)
        if not root.exists():
            return []
        repos = []
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            rid = int(hashlib.md5(d.name.encode()).hexdigest()[:8], 16)
            repos.append(Repo(id=rid, full_name=f"{FAKE_OWNER}/{d.name}"))
        return repos

    def list_releases(self, installation_id, repo_full_name):
        repo = _repo_dir(repo_full_name)
        rel_dir = repo / "releases"
        if not rel_dir.exists() or not any(rel_dir.glob("*.zip")):
            build_release_zip(repo, "v1.0.0")
        out = []
        for z in sorted(rel_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
            out.append(
                Release(
                    tag_name=z.stem,
                    name=z.stem,
                    published_at=datetime.fromtimestamp(z.stat().st_mtime, tz=UTC),
                    commit_sha=hashlib.sha1(z.read_bytes()).hexdigest(),
                )
            )
        return out

    def download_zipball(self, installation_id, repo_full_name, tag, dest_path):
        src = _repo_dir(repo_full_name) / "releases" / f"{tag}.zip"
        if not src.exists():
            raise GitHubError(f"Релиз {tag} не найден")
        shutil.copyfile(src, dest_path)
        return hashlib.sha1(src.read_bytes()).hexdigest()

    def ensure_mirror_repo(self, name):
        full = f"{settings.github_org}/{name}"
        (self.state_dir / "mirrors" / name).mkdir(parents=True, exist_ok=True)
        return full

    def publish_version(self, mirror_full_name, source_dir, tag, message):
        name = mirror_full_name.split("/")[-1]
        dest = self.state_dir / "mirrors" / name / "current"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)
        sha = hashlib.sha1(f"{mirror_full_name}:{tag}".encode()).hexdigest()
        log.info("FAKE опубликовано: %s тег %s (%s), коммит «%s»", mirror_full_name, tag, sha[:7], message)
        return sha

    def add_collaborator(self, mirror_full_name, login):
        state = self._state()
        state["collaborators"].setdefault(mirror_full_name, {})[login.lower()] = "invited"
        self._save_state(state)
        log.info("FAKE приглашён: %s в %s (pull)", login, mirror_full_name)
        return "invited"

    def remove_collaborator(self, mirror_full_name, login):
        state = self._state()
        state["collaborators"].get(mirror_full_name, {}).pop(login.lower(), None)
        self._save_state(state)
        log.info("FAKE доступ отозван: %s из %s", login, mirror_full_name)

    def invitation_status(self, mirror_full_name, login):
        """В демо-режиме приглашение считается принятым при первой проверке статуса."""
        state = self._state()
        repo = state["collaborators"].get(mirror_full_name, {})
        current = repo.get(login.lower(), "none")
        if current == "invited":
            repo[login.lower()] = "granted"
            self._save_state(state)
            return "granted"
        return current

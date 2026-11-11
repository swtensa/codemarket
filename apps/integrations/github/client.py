"""Клиент GitHub API для режима GITHUB_MODE=real (GitHub App).

Аутентификация: JWT приложения (PyJWT, RS256) → токен установки (кэш 50 минут).
Токены продавцов не хранятся: только installation_id.
Публикация в репозиторий-копию идёт через Git Data API (blobs → tree → commit → ref),
поэтому git на компьютере не нужен.
"""

import base64
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.core.cache import cache

from .base import GitHubClientBase, GitHubError, Release, Repo

log = logging.getLogger("codemarket.github")

API = "https://api.github.com"
TOKEN_TTL = 50 * 60
TIMEOUT = 30


class RealGitHubClient(GitHubClientBase):
    mode = "real"

    def __init__(self):
        if not settings.GITHUB_APP_ID or not settings.GITHUB_PRIVATE_KEY_PATH:
            raise GitHubError("GitHub App не настроен: заполните GITHUB_APP_ID и GITHUB_PRIVATE_KEY_PATH в .env")
        self.app_id = settings.GITHUB_APP_ID
        self.org = settings.GITHUB_ORG
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})

    # ------------------------------------------------------------ аутентификация

    def _app_jwt(self):
        key = Path(settings.GITHUB_PRIVATE_KEY_PATH).read_text()
        now = int(time.time())
        return jwt.encode({"iat": now - 60, "exp": now + 9 * 60, "iss": str(self.app_id)}, key, algorithm="RS256")

    def _installation_token(self, installation_id):
        key = f"gh_token_{installation_id}"
        token = cache.get(key)
        if token:
            return token
        resp = self._request(
            "POST", f"/app/installations/{installation_id}/access_tokens", auth=f"Bearer {self._app_jwt()}"
        )
        token = resp.json()["token"]
        cache.set(key, token, TOKEN_TTL)
        return token

    def _org_installation_id(self):
        key = "gh_org_installation"
        iid = cache.get(key)
        if iid is None:
            iid = self._request("GET", f"/orgs/{self.org}/installation", auth=f"Bearer {self._app_jwt()}").json()["id"]
            cache.set(key, iid, 24 * 3600)
        return iid

    def _org_auth(self):
        return f"token {self._installation_token(self._org_installation_id())}"

    def _request(self, method, path, auth, expected=(200, 201, 204), **kwargs):
        url = path if path.startswith("http") else API + path
        try:
            resp = self.session.request(method, url, headers={"Authorization": auth}, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as e:
            log.error("GitHub %s %s: %s", method, path, e)
            raise GitHubError("GitHub недоступен, попробуйте позже") from e
        if resp.status_code not in expected:
            log.error("GitHub %s %s → %s %s", method, path, resp.status_code, resp.text[:300])
            raise GitHubError(f"GitHub ответил ошибкой {resp.status_code}")
        return resp

    # ------------------------------------------------------------ продавец

    def install_url(self, state):
        return f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?{urlencode({'state': state})}"

    def check_installation(self, installation_id):
        data = self._request("GET", f"/app/installations/{installation_id}", auth=f"Bearer {self._app_jwt()}").json()
        return data["account"]["login"]

    def list_repositories(self, installation_id):
        auth = f"token {self._installation_token(installation_id)}"
        repos, page = [], 1
        while True:
            data = self._request(
                "GET", "/installation/repositories", auth=auth, params={"per_page": 100, "page": page}
            ).json()
            repos += [Repo(id=r["id"], full_name=r["full_name"], private=r["private"]) for r in data["repositories"]]
            if len(data["repositories"]) < 100:
                return repos
            page += 1

    def list_releases(self, installation_id, repo_full_name):
        from django.utils.dateparse import parse_datetime

        auth = f"token {self._installation_token(installation_id)}"
        data = self._request("GET", f"/repos/{repo_full_name}/releases", auth=auth, params={"per_page": 30}).json()
        return [
            Release(
                tag_name=r["tag_name"],
                name=r.get("name") or r["tag_name"],
                published_at=parse_datetime(r["published_at"]) if r.get("published_at") else None,
            )
            for r in data
            if not r.get("draft")
        ]

    def download_zipball(self, installation_id, repo_full_name, tag, dest_path):
        auth = f"token {self._installation_token(installation_id)}"
        limit = settings.MAX_ARCHIVE_MB * 1024 * 1024
        resp = self._request("GET", f"/repos/{repo_full_name}/zipball/{tag}", auth=auth, stream=True)
        size = 0
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(64 * 1024):
                size += len(chunk)
                if size > limit:
                    f.close()
                    os.remove(dest_path)
                    raise GitHubError(f"Архив релиза больше {settings.MAX_ARCHIVE_MB} МБ")
                f.write(chunk)
        sha = self._request("GET", f"/repos/{repo_full_name}/commits/{tag}", auth=auth).json()["sha"]
        return sha

    # ------------------------------------------------------------ репозиторий-копия

    def ensure_mirror_repo(self, name):
        auth = self._org_auth()
        full = f"{self.org}/{name}"
        resp = self._request("GET", f"/repos/{full}", auth=auth, expected=(200, 404))
        if resp.status_code == 404:
            self._request(
                "POST",
                f"/orgs/{self.org}/repos",
                auth=auth,
                json={"name": name, "private": True, "auto_init": True, "description": "CodeMarket: одобренные версии"},
            )
            log.info("Создан репозиторий-копия %s", full)
        return full

    def publish_version(self, mirror_full_name, source_dir, tag, message):
        auth = self._org_auth()
        base = f"/repos/{mirror_full_name}"
        head = self._request("GET", f"{base}/git/ref/heads/main", auth=auth, expected=(200, 404))
        parent = head.json()["object"]["sha"] if head.status_code == 200 else None
        tree = []
        source_dir = Path(source_dir)
        for path in sorted(p for p in source_dir.rglob("*") if p.is_file()):
            content = base64.b64encode(path.read_bytes()).decode()
            blob = self._request(
                "POST", f"{base}/git/blobs", auth=auth, json={"content": content, "encoding": "base64"}
            )
            tree.append(
                {
                    "path": path.relative_to(source_dir).as_posix(),
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob.json()["sha"],
                }
            )
        tree_sha = self._request("POST", f"{base}/git/trees", auth=auth, json={"tree": tree}).json()["sha"]
        commit = self._request(
            "POST",
            f"{base}/git/commits",
            auth=auth,
            json={"message": message, "tree": tree_sha, "parents": [parent] if parent else []},
        ).json()["sha"]
        if parent:
            self._request("PATCH", f"{base}/git/refs/heads/main", auth=auth, json={"sha": commit, "force": True})
        else:
            self._request("POST", f"{base}/git/refs", auth=auth, json={"ref": "refs/heads/main", "sha": commit})
        self._request(
            "POST", f"{base}/git/refs", auth=auth, json={"ref": f"refs/tags/{tag}", "sha": commit}, expected=(201, 422)
        )
        log.info("Опубликована версия %s в %s (%s)", tag, mirror_full_name, commit[:7])
        return commit

    def add_collaborator(self, mirror_full_name, login):
        resp = self._request(
            "PUT",
            f"/repos/{mirror_full_name}/collaborators/{login}",
            auth=self._org_auth(),
            json={"permission": "pull"},
            expected=(201, 204),
        )
        log.info("Приглашён %s в %s (%s)", login, mirror_full_name, resp.status_code)
        return "invited" if resp.status_code == 201 else "granted"

    def remove_collaborator(self, mirror_full_name, login):
        auth = self._org_auth()
        self._request("DELETE", f"/repos/{mirror_full_name}/collaborators/{login}", auth=auth, expected=(204, 404))
        invitations = self._request("GET", f"/repos/{mirror_full_name}/invitations", auth=auth).json()
        for inv in invitations:
            if inv.get("invitee", {}).get("login", "").lower() == login.lower():
                self._request("DELETE", f"/repos/{mirror_full_name}/invitations/{inv['id']}", auth=auth)
        log.info("Отозван доступ %s к %s", login, mirror_full_name)

    def invitation_status(self, mirror_full_name, login):
        auth = self._org_auth()
        resp = self._request("GET", f"/repos/{mirror_full_name}/collaborators/{login}", auth=auth, expected=(204, 404))
        if resp.status_code == 204:
            return "granted"
        invitations = self._request("GET", f"/repos/{mirror_full_name}/invitations", auth=auth).json()
        if any(i.get("invitee", {}).get("login", "").lower() == login.lower() for i in invitations):
            return "invited"
        return "none"

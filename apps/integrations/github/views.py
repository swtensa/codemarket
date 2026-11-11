"""Подключение GitHub App продавцом и (этап 12) вебхук GitHub."""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts import services as account_services

from . import get_client
from .base import GitHubError

hook_log = logging.getLogger("codemarket.webhooks")

FAKE_INSTALLATION_BASE = 900_000_000


@login_required
def connect(request):
    """Страница «Подключить GitHub»."""
    client = get_client()
    if request.method == "POST":
        if client.mode != "fake":
            return HttpResponseBadRequest()
        account_services.connect_github(request.user, FAKE_INSTALLATION_BASE + request.user.id)
        messages.success(request, "GitHub подключён (демо-режим). Теперь можно создавать продукты.")
        return redirect("sell:dashboard")
    install_url = None
    if client.mode == "real":
        state = signing.dumps({"u": request.user.id}, salt="gh-install")
        install_url = client.install_url(state)
    return render(request, "sell/github_connect.html", {"install_url": install_url, "fake": client.mode == "fake"})


@login_required
def callback(request):
    """GitHub возвращает пользователя после установки приложения: ?installation_id=...&state=..."""
    try:
        data = signing.loads(request.GET.get("state", ""), salt="gh-install", max_age=3600)
    except signing.BadSignature:
        messages.error(request, "Ссылка подключения устарела, попробуйте ещё раз.")
        return redirect("sell:github")
    if data.get("u") != request.user.id:
        return HttpResponseForbidden()
    installation_id = request.GET.get("installation_id", "")
    if not installation_id.isdigit():
        messages.error(request, "GitHub не передал номер установки.")
        return redirect("sell:github")
    try:
        account = get_client().check_installation(int(installation_id))
    except GitHubError as e:
        messages.error(request, str(e))
        return redirect("sell:github")
    account_services.connect_github(request.user, int(installation_id))
    messages.success(request, f"GitHub подключён: {account}.")
    return redirect("sell:dashboard")


@csrf_exempt
@require_POST
def webhook(request):
    """Вебхук GitHub: проверка подписи X-Hub-Signature-256, события release.published и installation.deleted."""
    secret = settings.GITHUB_WEBHOOK_SECRET.encode()
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signature, expected):
        hook_log.warning("GitHub webhook: неверная подпись")
        return HttpResponseForbidden("bad signature")
    event = request.headers.get("X-GitHub-Event", "")
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    action = payload.get("action")
    hook_log.info("GitHub webhook %s.%s", event, action)
    if event == "installation" and action == "deleted":
        account_services.disconnect_github_installation(payload["installation"]["id"])
    elif event == "release" and action == "published":
        from apps.versions.services import release_published_webhook

        release_published_webhook(
            installation_id=payload.get("installation", {}).get("id"),
            repo_id=payload["repository"]["id"],
            tag_name=payload["release"]["tag_name"],
        )
    return HttpResponse("ok")

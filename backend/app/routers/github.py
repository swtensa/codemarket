"""Вебхук GitHub: проверка подписи X-Hub-Signature-256, события release.published и installation.deleted."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.deps import DB
from app.services import accounts as account_services
from app.services import versions as version_services

router = APIRouter(prefix="/api/github", tags=["GitHub"])
hook_log = logging.getLogger("codemarket.webhooks")


@router.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request, db: DB):
    body = await request.body()
    secret = settings.github_webhook_secret.encode()
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signature, expected):
        hook_log.warning("GitHub webhook: неверная подпись")
        return PlainTextResponse("bad signature", status_code=403)
    event = request.headers.get("X-GitHub-Event", "")
    try:
        payload = json.loads(body)
    except ValueError:
        return PlainTextResponse("bad request", status_code=400)
    action = payload.get("action")
    hook_log.info("GitHub webhook %s.%s", event, action)
    if event == "installation" and action == "deleted":
        account_services.disconnect_github_installation(db, payload["installation"]["id"])
    elif event == "release" and action == "published":
        version_services.release_published_webhook(
            db,
            installation_id=payload.get("installation", {}).get("id"),
            repo_id=payload["repository"]["id"],
            tag_name=payload["release"]["tag_name"],
        )
    db.commit()
    return "ok"

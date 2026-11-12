"""CSRF (double submit) и cookie посетителя для учёта просмотров."""

import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .security import CSRF_COOKIE, CSRF_HEADER, VISITOR_COOKIE, new_csrf_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# вебхуки приходят от ЮKassa и GitHub без cookie: их подлинность проверяется иначе
CSRF_EXEMPT = {"/api/payments/webhook", "/api/github/webhook"}


def install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def csrf_and_visitor(request: Request, call_next):
        path = request.url.path
        cookie = request.cookies.get(CSRF_COOKIE)
        if (
            request.method not in SAFE_METHODS
            and path.startswith("/api/")
            and path.rstrip("/") not in CSRF_EXEMPT
            and (not cookie or not secrets.compare_digest(cookie, request.headers.get(CSRF_HEADER, "")))
        ):
            return JSONResponse({"detail": "Сессия устарела: обновите страницу и повторите действие."}, status_code=403)
        visitor = request.cookies.get(VISITOR_COOKIE)
        request.state.visitor = visitor or secrets.token_hex(16)
        response = await call_next(request)
        if not cookie:
            response.set_cookie(
                CSRF_COOKIE, new_csrf_token(), samesite="lax", secure=settings.cookie_secure, path="/", httponly=False
            )
        if not visitor:
            response.set_cookie(
                VISITOR_COOKIE, request.state.visitor, max_age=365 * 86400, samesite="lax", httponly=True, path="/"
            )
        return response

"""Приложение FastAPI: роутеры /api/..., публичные файлы /media/, собранный интерфейс frontend/dist."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.errors import install_handlers
from .core.logging import setup_logging
from .core.middleware import install_middleware
from .routers import ROUTERS

setup_logging()

app = FastAPI(
    title="CodeMarket API",
    version="2.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
install_handlers(app)
install_middleware(app)
for _router in ROUTERS:
    app.include_router(_router)


@app.get("/api/health", tags=["служебное"])
def health() -> dict[str, str]:
    return {"status": "ok"}


settings.storage_public.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.storage_public), name="media")


# ---------------------------------------------------------------- интерфейс для защиты (без Vite)
_dist = settings.frontend_dist


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Собранный React: файлы из frontend/dist, все адреса интерфейса отдают index.html."""
    if path.startswith("api/"):
        return JSONResponse({"detail": "Не найдено"}, status_code=404)
    index = _dist / "index.html"
    if not index.exists():
        return JSONResponse(
            {
                "detail": "Интерфейс не собран: выполните npm run build в папке frontend или откройте http://localhost:5173"
            },
            status_code=404,
        )
    target = (_dist / path).resolve()
    if path and target.is_file() and _dist.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(index)


__all__ = ["app", "Path"]

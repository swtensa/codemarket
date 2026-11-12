"""Вспомогательные функции тестов: архивы версий."""

import io
import zipfile

from app.core.storage import save_private
from app.models import ProductVersion
from app.models.base import utcnow


def make_zip(files, root="owner-repo-abc1234") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(f"{root}/{name}", text)
    return buf.getvalue()


def make_version(db, product, files, status="checking", tag="v1.0.0", **extra) -> ProductVersion:
    """Создать версию продукта с архивом из словаря {путь: текст}."""
    data = make_zip(files)
    v = ProductVersion(
        product_id=product.id,
        tag_name=tag,
        status=status,
        size=len(data),
        files_count=len(files),
        archive=save_private(f"versions/{product.id}", f"{tag}.zip", data),
        **extra,
    )
    db.add(v)
    db.flush()
    db.refresh(v)
    return v


def make_checked_approved(db, product, files, tag="v1.0.0") -> ProductVersion:
    """Версия, прошедшая проверку (с отпечатками) и одобренная модератором."""
    from app.services.plagiarism import check_version

    v = make_version(db, product, files, tag=tag)
    check_version(db, v)
    v.status, v.approved_at = "approved", utcnow()
    db.flush()
    return v


def make_published(db, product, files=None, tag="v1.0.0"):
    """Одобренная версия + публикация в репозиторий-копию (fake): продукт можно покупать."""
    from app.services.versions import publish_to_mirror

    v = make_version(db, product, files or {"index.html": "<p>демо</p>", "app.js": "let a = 1;"}, status="approved")
    v.approved_at = utcnow()
    db.flush()
    publish_to_mirror(db, v)
    db.refresh(product)
    return v


def png_bytes(size=(32, 20)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (200, 80, 80)).save(buf, "PNG")
    return buf.getvalue()

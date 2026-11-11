"""Вспомогательные функции тестов: архивы версий."""

import io
import zipfile

from django.core.files.base import ContentFile

from apps.versions.models import ProductVersion


def make_zip(files, root="owner-repo-abc1234"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(f"{root}/{name}", text)
    return buf.getvalue()


def make_version(product, files, status="checking", tag="v1.0.0", **extra):
    """Создать версию продукта с архивом из словаря {путь: текст}."""
    data = make_zip(files)
    v = ProductVersion(product=product, tag_name=tag, status=status, size=len(data), files_count=len(files), **extra)
    v.archive.save(f"{tag}.zip", ContentFile(data), save=False)
    v.save()
    return v


def make_checked_approved(product, files, tag="v1.0.0"):
    """Версия, прошедшая проверку (с отпечатками) и одобренная модератором."""
    from django.utils import timezone

    from apps.plagiarism.services import check_version

    v = make_version(product, files, tag=tag)
    check_version(v)
    ProductVersion.objects.filter(pk=v.pk).update(status="approved", approved_at=timezone.now())
    v.refresh_from_db()
    return v

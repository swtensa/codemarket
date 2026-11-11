"""Сервисы версий продукта: получение релизов, статусы версии, публикация в репозиторий-копию."""

import logging
import shutil
import tempfile
from pathlib import Path

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from apps.catalog import services as catalog_services
from apps.core.archive import ArchiveError, extract_safe, inspect_zip
from apps.core.exceptions import InvalidTransition, ServiceError
from apps.integrations.github import get_client
from apps.integrations.github.base import GitHubError
from apps.notifications.services import notify

from .models import ProductVersion

log = logging.getLogger("codemarket")
admin_log = logging.getLogger("codemarket.admin")

S = ProductVersion.Status

# Раздел 7.2 ТЗ
VERSION_TRANSITIONS = {
    S.CHECKING: {S.REJECTED_AUTO, S.MODERATION},
    S.REJECTED_AUTO: {S.APPEAL},
    S.APPEAL: {S.MODERATION},
    S.MODERATION: {S.APPROVED, S.REJECTED},
}


def change_version_status(version, new_status):
    """Сменить статус версии с проверкой допустимости перехода."""
    if new_status not in VERSION_TRANSITIONS.get(version.status, set()):
        raise InvalidTransition(f"Версия: переход {version.status} → {new_status} недопустим")
    version.status = new_status
    version.save(update_fields=["status"])
    return version


# ---------------------------------------------------------------- чтение


def approved_versions(product):
    """Одобренные версии продукта, новые сверху."""
    return list(product.versions.filter(status=S.APPROVED).order_by("-approved_at"))


def current_version(product):
    """Последняя одобренная версия или None."""
    return product.versions.filter(status=S.APPROVED).order_by("-approved_at").first()


def product_versions(product):
    return product.versions.all().order_by("-created_at")


def pending_versions():
    """Очередь модерации: версии на модерации и обжалования."""
    return (
        ProductVersion.objects.filter(status__in=[S.MODERATION, S.APPEAL])
        .select_related("product", "product__seller")
        .order_by("created_at")
    )


# ---------------------------------------------------------------- релизы


def available_releases(product, user):
    """Релизы репозитория продавца и отметка, какие уже получены."""
    if product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")
    if not product.source_repo_full_name:
        raise ServiceError("У продукта не выбран репозиторий.")
    try:
        releases = get_client().list_releases(user.github_installation_id, product.source_repo_full_name)
    except GitHubError as e:
        raise ServiceError(str(e))
    known = set(product.versions.values_list("tag_name", flat=True))
    return [{"release": r, "imported": r.tag_name in known} for r in releases]


def import_release(product, user, tag_name):
    """Скачать zipball релиза, проверить размер и число файлов, сохранить и отправить на проверку.

    Сама проверка на заимствования выполняется в фоне командой process_checks.
    """
    if product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")
    if product.versions.filter(tag_name=tag_name).exists():
        raise ServiceError(f"Релиз {tag_name} уже получен.")
    if product.versions.filter(status__in=[S.CHECKING, S.MODERATION, S.APPEAL]).exists():
        raise ServiceError("Предыдущая версия ещё проверяется. Дождитесь решения.")
    if product.status in ("blocked",):
        raise ServiceError("Продукт заблокирован.")
    client = get_client()
    releases = {r.tag_name: r for r in client.list_releases(user.github_installation_id, product.source_repo_full_name)}
    if tag_name not in releases:
        raise ServiceError("Такого релиза нет в репозитории.")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "release.zip"
        try:
            sha = client.download_zipball(
                user.github_installation_id, product.source_repo_full_name, tag_name, zip_path
            )
            files_count, _ = inspect_zip(zip_path)
        except (GitHubError, ArchiveError) as e:
            raise ServiceError(str(e))
        with transaction.atomic():
            version = ProductVersion(
                product=product,
                tag_name=tag_name,
                commit_sha=(sha or releases[tag_name].commit_sha)[:40],
                size=zip_path.stat().st_size,
                files_count=files_count,
                released_at=releases[tag_name].published_at,
                status=S.CHECKING,
            )
            with open(zip_path, "rb") as f:
                version.archive.save(f"{tag_name}.zip", File(f), save=False)
            version.save()
            catalog_services.on_release_submitted(product)
    return version


# ---------------------------------------------------------------- итоги проверки и модерации


def apply_check_result(version, *, similarity, rejected_auto, flagged):
    """Записать итог автоматической проверки (вызывает модуль plagiarism)."""
    version.similarity = similarity
    version.flagged = flagged
    version.save(update_fields=["similarity", "flagged"])
    if rejected_auto:
        change_version_status(version, S.REJECTED_AUTO)
        notify(
            version.product.seller,
            f"Версия {version.tag_name} «{version.product.title}» отклонена автоматически: "
            f"сходство {similarity:.0%}. Можно обжаловать.",
            f"/sell/products/{version.product_id}/versions/",
        )
    else:
        change_version_status(version, S.MODERATION)
        notify(
            version.product.seller,
            f"Версия {version.tag_name} «{version.product.title}» прошла проверку и отправлена на модерацию.",
            f"/sell/products/{version.product_id}/versions/",
        )
    catalog_services.on_version_checked(version.product, rejected_auto=rejected_auto)
    return version


def mark_check_failed(version, error):
    """Проверка не удалась (битый архив): версия отклоняется автоматически с текстом ошибки."""
    version.check_error = str(error)[:1000]
    version.similarity = 0
    version.save(update_fields=["check_error", "similarity"])
    change_version_status(version, S.REJECTED_AUTO)
    catalog_services.on_version_checked(version.product, rejected_auto=True)


def appeal_version(version, user, text):
    """Продавец обжалует автоматический отказ: rejected_auto → appeal (в очередь модерации)."""
    if version.product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")
    if not text or len(text.strip()) < 10:
        raise ServiceError("Опишите, почему совпадение не является заимствованием (не короче 10 символов).")
    version.appeal_text = text.strip()
    version.save(update_fields=["appeal_text"])
    change_version_status(version, S.APPEAL)
    catalog_services.on_version_appealed(version.product)
    return version


@transaction.atomic
def approve_version(version, admin):
    """Одобрить версию: публикация в репозиторий-копию, публикация продукта, уведомления покупателям."""
    if version.status == S.APPEAL:
        change_version_status(version, S.MODERATION)
    change_version_status(version, S.APPROVED)
    version.approved_at = timezone.now()
    version.save(update_fields=["approved_at"])
    product = version.product
    had_previous = product.versions.filter(status=S.APPROVED).exclude(pk=version.pk).exists()
    publish_to_mirror(version)
    catalog_services.on_version_approved(product)
    notify(
        product.seller,
        f"Версия {version.tag_name} «{product.title}» одобрена"
        + (" и опубликована в каталоге." if not had_previous else "."),
        f"/sell/products/{product.id}/versions/",
    )
    if had_previous:
        from apps.purchases.services import notify_new_version

        notify_new_version(product, version)
    admin_log.info("admin=%s approved version=%s", admin, version.pk)
    return version


@transaction.atomic
def reject_version(version, admin, comment):
    """Отклонить версию с обязательным комментарием."""
    if not comment or not comment.strip():
        raise ServiceError("Укажите причину отклонения.")
    if version.status == S.APPEAL:
        change_version_status(version, S.MODERATION)
    change_version_status(version, S.REJECTED)
    version.admin_comment = comment.strip()
    version.save(update_fields=["admin_comment"])
    catalog_services.on_version_rejected(version.product)
    notify(
        version.product.seller,
        f"Версия {version.tag_name} «{version.product.title}» отклонена модератором: {comment.strip()}",
        f"/sell/products/{version.product_id}/versions/",
    )
    admin_log.info("admin=%s rejected version=%s comment=%s", admin, version.pk, comment)
    return version


def publish_to_mirror(version):
    """Опубликовать файлы версии в закрытый репозиторий-копию в организации платформы."""
    product = version.product
    client = get_client()
    tmp = tempfile.mkdtemp()
    try:
        extract_safe(version.archive.path, tmp)
        mirror = client.ensure_mirror_repo(product.slug)
        client.publish_version(mirror, tmp, version.tag_name, f"Версия {version.tag_name}")
    except (GitHubError, ArchiveError) as e:
        log.error("Публикация версии %s не удалась: %s", version.pk, e)
        raise ServiceError(f"Не удалось опубликовать версию в репозиторий-копию: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    catalog_services.set_mirror_repo(product, mirror)
    return mirror


def release_published_webhook(*, installation_id, repo_id, tag_name):
    """Вебхук GitHub release.published: получить релиз для продуктов из этого репозитория."""
    from apps.catalog.models import Product

    imported = []
    for product in Product.objects.filter(source_repo_id=repo_id).select_related("seller"):
        seller = product.seller
        if installation_id and seller.github_installation_id != installation_id:
            continue
        try:
            imported.append(import_release(product, seller, tag_name))
        except ServiceError as e:
            log.info("Вебхук: релиз %s продукта %s не получен: %s", tag_name, product.pk, e)
    return imported

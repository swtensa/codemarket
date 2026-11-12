"""Версии продукта: получение релизов, статусы версии (раздел 7.2 ТЗ), публикация в репозиторий-копию."""

import logging
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.archive import ArchiveError, extract_safe, inspect_zip
from app.core.errors import InvalidTransition, ServiceError
from app.core.storage import private_path, save_private
from app.integrations.github import get_client
from app.integrations.github.base import GitHubError
from app.models import Product, ProductVersion, User, VersionStatus
from app.models.base import utcnow
from app.services import catalog as catalog_services
from app.services.notifications import notify

log = logging.getLogger("codemarket")
admin_log = logging.getLogger("codemarket.admin")
S = VersionStatus

VERSION_TRANSITIONS = {
    S.CHECKING: {S.REJECTED_AUTO, S.MODERATION},
    S.REJECTED_AUTO: {S.APPEAL},
    S.APPEAL: {S.MODERATION},
    S.MODERATION: {S.APPROVED, S.REJECTED},
}


def change_version_status(db: Session, version: ProductVersion, new_status: str) -> ProductVersion:
    if new_status not in VERSION_TRANSITIONS.get(version.status, set()):
        raise InvalidTransition(f"Версия: переход {version.status} → {new_status} недопустим")
    version.status = new_status
    db.flush()
    return version


def archive_path(version: ProductVersion) -> Path:
    return private_path(version.archive)


# ---------------------------------------------------------------- чтение


def approved_versions(db: Session, product: Product) -> list[ProductVersion]:
    return list(
        db.scalars(
            select(ProductVersion)
            .where(ProductVersion.product_id == product.id, ProductVersion.status == S.APPROVED)
            .order_by(ProductVersion.approved_at.desc())
        )
    )


def current_version(db: Session, product: Product) -> ProductVersion | None:
    """Последняя одобренная версия или None."""
    return db.scalar(
        select(ProductVersion)
        .where(ProductVersion.product_id == product.id, ProductVersion.status == S.APPROVED)
        .order_by(ProductVersion.approved_at.desc())
        .limit(1)
    )


def product_versions(db: Session, product: Product) -> list[ProductVersion]:
    return list(
        db.scalars(
            select(ProductVersion)
            .where(ProductVersion.product_id == product.id)
            .order_by(ProductVersion.created_at.desc(), ProductVersion.id.desc())
        )
    )


def pending_versions_stmt():
    """Очередь модерации: версии на модерации и обжалования."""
    return (
        select(ProductVersion)
        .where(ProductVersion.status.in_([S.MODERATION, S.APPEAL]))
        .options(selectinload(ProductVersion.product).selectinload(Product.seller))
        .order_by(ProductVersion.created_at)
    )


# ---------------------------------------------------------------- релизы


def available_releases(db: Session, product: Product, user: User):
    """Релизы репозитория продавца и отметка, какие уже получены."""
    if product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")
    if not product.source_repo_full_name:
        raise ServiceError("У продукта не выбран репозиторий.")
    try:
        releases = get_client().list_releases(user.github_installation_id, product.source_repo_full_name)
    except GitHubError as e:
        raise ServiceError(str(e))
    known = set(db.scalars(select(ProductVersion.tag_name).where(ProductVersion.product_id == product.id)))
    return [{"release": r, "imported": r.tag_name in known} for r in releases]


def import_release(db: Session, product: Product, user: User, tag_name: str) -> ProductVersion:
    """Скачать zipball релиза, проверить размер и число файлов, сохранить и отправить на проверку.

    Сама проверка на заимствования выполняется в фоне (задача process_checks планировщика).
    """
    if product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")
    versions = product_versions(db, product)
    if any(v.tag_name == tag_name for v in versions):
        raise ServiceError(f"Релиз {tag_name} уже получен.")
    if any(v.status in (S.CHECKING, S.MODERATION, S.APPEAL) for v in versions):
        raise ServiceError("Предыдущая версия ещё проверяется. Дождитесь решения.")
    if product.status == "blocked":
        raise ServiceError("Продукт заблокирован.")
    client = get_client()
    try:
        releases = {
            r.tag_name: r for r in client.list_releases(user.github_installation_id, product.source_repo_full_name)
        }
    except GitHubError as e:
        raise ServiceError(str(e))
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
        rel = save_private(f"versions/{product.id}", f"{tag_name}.zip", zip_path.read_bytes())
        version = ProductVersion(
            product_id=product.id,
            tag_name=tag_name,
            commit_sha=(sha or releases[tag_name].commit_sha or "")[:40],
            size=zip_path.stat().st_size,
            files_count=files_count,
            released_at=releases[tag_name].published_at,
            status=S.CHECKING,
            archive=rel,
        )
        db.add(version)
        db.flush()
    catalog_services.on_release_submitted(db, product)
    return version


# ---------------------------------------------------------------- итоги проверки и модерации


def _versions_link(version):
    return f"/sell/products/{version.product_id}/versions/"


def apply_check_result(db: Session, version: ProductVersion, *, similarity, rejected_auto, flagged):
    version.similarity = similarity
    version.flagged = flagged
    product = version.product
    if rejected_auto:
        change_version_status(db, version, S.REJECTED_AUTO)
        notify(
            db,
            product.seller,
            f"Версия {version.tag_name} «{product.title}» отклонена автоматически: "
            f"сходство {similarity:.0%}. Можно обжаловать.",
            _versions_link(version),
        )
    else:
        change_version_status(db, version, S.MODERATION)
        notify(
            db,
            product.seller,
            f"Версия {version.tag_name} «{product.title}» прошла проверку и отправлена на модерацию.",
            _versions_link(version),
        )
    catalog_services.on_version_checked(db, product, rejected_auto=rejected_auto)
    return version


def mark_check_failed(db: Session, version: ProductVersion, error) -> None:
    """Проверка не удалась (битый архив): версия отклоняется автоматически с текстом ошибки."""
    version.check_error = str(error)[:1000]
    version.similarity = 0
    change_version_status(db, version, S.REJECTED_AUTO)
    catalog_services.on_version_checked(db, version.product, rejected_auto=True)


def appeal_version(db: Session, version: ProductVersion, user: User, text: str) -> ProductVersion:
    """Продавец обжалует автоматический отказ: rejected_auto → appeal (в очередь модерации)."""
    if version.product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")
    if not text or len(text.strip()) < 10:
        raise ServiceError("Опишите, почему совпадение не является заимствованием (не короче 10 символов).")
    version.appeal_text = text.strip()
    change_version_status(db, version, S.APPEAL)
    catalog_services.on_version_appealed(db, version.product)
    return version


def approve_version(db: Session, version: ProductVersion, admin: User) -> ProductVersion:
    """Одобрить версию: публикация в репозиторий-копию, публикация продукта, уведомления покупателям."""
    if version.status == S.APPEAL:
        change_version_status(db, version, S.MODERATION)
    change_version_status(db, version, S.APPROVED)
    version.approved_at = utcnow()
    product = version.product
    had_previous = any(v.id != version.id for v in approved_versions(db, product))
    publish_to_mirror(db, version)
    catalog_services.on_version_approved(db, product)
    notify(
        db,
        product.seller,
        f"Версия {version.tag_name} «{product.title}» одобрена"
        + (" и опубликована в каталоге." if not had_previous else "."),
        _versions_link(version),
    )
    if had_previous:
        from app.services.purchases import notify_new_version

        notify_new_version(db, product, version)
    admin_log.info("admin=%s approved version=%s", admin.username, version.id)
    return version


def reject_version(db: Session, version: ProductVersion, admin: User, comment: str) -> ProductVersion:
    """Отклонить версию с обязательным комментарием."""
    if not comment or not comment.strip():
        raise ServiceError("Укажите причину отклонения.")
    if version.status == S.APPEAL:
        change_version_status(db, version, S.MODERATION)
    change_version_status(db, version, S.REJECTED)
    version.admin_comment = comment.strip()
    catalog_services.on_version_rejected(db, version.product)
    notify(
        db,
        version.product.seller,
        f"Версия {version.tag_name} «{version.product.title}» отклонена модератором: {comment.strip()}",
        _versions_link(version),
    )
    admin_log.info("admin=%s rejected version=%s comment=%s", admin.username, version.id, comment)
    return version


def publish_to_mirror(db: Session, version: ProductVersion) -> str:
    """Опубликовать файлы версии в закрытый репозиторий-копию в организации платформы."""
    product = version.product
    client = get_client()
    tmp = tempfile.mkdtemp()
    try:
        extract_safe(archive_path(version), tmp)
        mirror = client.ensure_mirror_repo(product.slug)
        client.publish_version(mirror, tmp, version.tag_name, f"Версия {version.tag_name}")
    except (GitHubError, ArchiveError) as e:
        log.error("Публикация версии %s не удалась: %s", version.id, e)
        raise ServiceError(f"Не удалось опубликовать версию в репозиторий-копию: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    catalog_services.set_mirror_repo(db, product, mirror)
    return mirror


def release_published_webhook(db: Session, *, installation_id, repo_id, tag_name) -> list[ProductVersion]:
    """Вебхук GitHub release.published: получить релиз для продуктов из этого репозитория."""
    imported = []
    for product in db.scalars(select(Product).where(Product.source_repo_id == repo_id)):
        seller = product.seller
        if installation_id and seller.github_installation_id != installation_id:
            continue
        try:
            imported.append(import_release(db, product, seller, tag_name))
        except ServiceError as e:
            log.info("Вебхук: релиз %s продукта %s не получен: %s", tag_name, product.id, e)
    return imported

"""Панель администратора: модерация версий (споры, выплаты, пользователи, справочники, отчёты — в admin_more)."""

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import DB, StaffUser
from app.core.errors import NotFound
from app.models import Product, ProductStatus, ProductVersion, VersionStatus
from app.schemas.catalog import (
    CommentIn,
    FileView,
    ModCounts,
    QueueItem,
    SellerAdminInfo,
    TreeItem,
    VersionDetail,
)
from app.schemas.common import Ok
from app.schemas.convert import product_edit_out, version_out
from app.services import moderation as mod
from app.services import plagiarism as plag_services
from app.services import versions as version_services

router = APIRouter(prefix="/api/admin", tags=["администратор"])


@router.get("/counts", response_model=ModCounts)
def counts(db: DB, _: StaffUser):
    """Числа ожидающих задач для левого меню модерации."""
    return ModCounts(**mod.menu_counts(db))


@router.get("/versions", response_model=list[QueueItem])
def queue(db: DB, _: StaffUser):
    """Очередь модерации: версии на модерации и обжалования с коэффициентом и совпадениями."""
    items = db.scalars(version_services.pending_versions_stmt()).all()
    matches = plag_services.matches_for_versions(db, items)
    out = []
    for v in items:
        approved_before = db.scalar(
            select(func.count()).where(
                ProductVersion.product_id == v.product_id,
                ProductVersion.status == VersionStatus.APPROVED,
                ProductVersion.id != v.id,
            )
        )
        out.append(
            QueueItem(
                version=version_out(v, matches.get(v.id)),
                product_id=v.product.id,
                product_title=v.product.title,
                product_slug=v.product.slug,
                product_status=v.product.status,
                seller=v.product.seller.username,
                is_new_product=not approved_before,
            )
        )
    return out


def _version(db, pk) -> ProductVersion:
    version = db.scalar(
        select(ProductVersion)
        .where(ProductVersion.id == pk)
        .options(
            selectinload(ProductVersion.product).selectinload(Product.seller),
            selectinload(ProductVersion.product).selectinload(Product.category),
        )
    )
    if version is None:
        raise NotFound("Версия не найдена")
    return version


@router.get("/versions/{pk}", response_model=VersionDetail)
def version_detail(pk: int, db: DB, _: StaffUser):
    """Проверка версии: продукт и продавец, обжалование, совпадения, дерево файлов."""
    version = _version(db, pk)
    product = version.product
    seller = product.seller
    matches = plag_services.matches_for_versions(db, [version]).get(version.id, [])
    category = (
        f"{product.category.parent.name} / {product.category.name}"
        if product.category.parent
        else product.category.name
    )
    return VersionDetail(
        version=version_out(version, matches),
        product=product_edit_out(product),
        category=category,
        seller=SellerAdminInfo(
            id=seller.id,
            username=seller.username,
            email=seller.email,
            created_at=seller.created_at,
            products=db.scalar(select(func.count()).where(Product.seller_id == seller.id)) or 0,
            status=seller.status,
        ),
        tree=[TreeItem(**t) for t in mod.file_tree(version)],
        can_decide=version.status in (VersionStatus.MODERATION, VersionStatus.APPEAL),
        highlight_css=mod.highlight_css(),
    )


@router.get("/versions/{pk}/file", response_model=FileView)
def version_file(pk: int, path: str, db: DB, _: StaffUser):
    """Содержимое файла версии с подсветкой (HTML от Pygments)."""
    html, error = mod.render_file(_version(db, pk), path)
    return FileView(path=path, html=html, error=error)


@router.post("/versions/{pk}/approve", response_model=Ok)
def approve(pk: int, db: DB, admin: StaffUser):
    version = _version(db, pk)
    version_services.approve_version(db, version, admin)
    db.commit()
    return Ok(message=f"Версия {version.tag_name} одобрена и опубликована в репозиторий-копию.")


@router.post("/versions/{pk}/reject", response_model=Ok)
def reject(pk: int, data: CommentIn, db: DB, admin: StaffUser):
    version = _version(db, pk)
    version_services.reject_version(db, version, admin, data.comment)
    db.commit()
    return Ok(message=f"Версия {version.tag_name} отклонена.")


__all__ = ["router", "ProductStatus"]

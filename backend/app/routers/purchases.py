"""Покупки и профиль: оформление, список, страница покупки, доступ к коду, скачивание ZIP."""

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound, ServiceError
from app.integrations.github import get_client
from app.models import AccessStatus, CustomOrder, Dispute, Product, PurchaseStatus
from app.schemas.common import Ok, Page
from app.schemas.convert import dispute_short, order_row, product_ref, version_short
from app.schemas.trade import (
    BuyIn,
    BuyInfo,
    GithubLoginIn,
    PayUrl,
    PurchaseDetail,
    PurchaseRow,
    ReviewShort,
)
from app.schemas.users import ProfileIn, UserOut
from app.services import accounts as account_services
from app.services import catalog as catalog_services
from app.services import purchases as svc
from app.services import versions as version_services
from app.services.reviews import review_for_purchase

router = APIRouter(prefix="/api", tags=["покупки и профиль"])


def _product_by_slug(db, slug) -> Product:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise NotFound("Продукт не найден")
    return product


@router.get("/purchases/buy/{slug}", response_model=BuyInfo)
def buy_info(slug: str, db: DB, user: CurrentUser):
    """Страница подтверждения покупки: что покупается, что будет после оплаты, можно ли купить."""
    product = _product_by_slug(db, slug)
    existing = svc.active_purchase(db, user, product)
    error = ""
    if not existing:
        try:
            svc.check_can_buy(db, user, product)
        except ServiceError as e:
            error = e.message
    return BuyInfo(
        product=product_ref(product),
        short_description=product.short_description,
        version=version_short(version_services.current_version(db, product)),
        existing_purchase_id=existing.id if existing else None,
        error=error,
        github_login=user.github_login,
        license_version=settings.license_version,
        hold_days=settings.hold_days,
    )


@router.post("/purchases", response_model=PayUrl)
def buy(data: BuyIn, db: DB, user: CurrentUser):
    """«Оплатить»: покупка pending и платёж; ответ — адрес страницы оплаты."""
    product = _product_by_slug(db, data.slug)
    purchase, url = svc.start_purchase(
        db, user, product, github_login=data.github_login, accept_license=data.accept_license
    )
    db.commit()
    return PayUrl(url=url, purchase_id=purchase.id)


def _row(p) -> PurchaseRow:
    return PurchaseRow(
        id=p.id,
        product=product_ref(p.product),
        price=p.price,
        status=p.status,
        status_label=PurchaseStatus.label(p.status),
        access_status=p.access_status,
        access_label=AccessStatus.label(p.access_status),
        created_at=p.created_at,
        paid_at=p.paid_at,
    )


@router.get("/purchases", response_model=Page[PurchaseRow])
def purchase_list(db: DB, user: CurrentUser, page: int = 1, page_size: int = 20):
    items, total, page, pages = catalog_services.paginate(db, svc.user_purchases_stmt(user), page, page_size)
    return Page(items=[_row(p) for p in items], total=total, page=page, pages=pages)


@router.get("/purchases/{pk}", response_model=PurchaseDetail)
def purchase_detail(pk: int, db: DB, user: CurrentUser):
    """Страница покупки: статус, доступ к коду (приглашение, git clone, ZIP), версии, споры, доработки, отзыв."""
    purchase = svc.get_purchase_for(db, user, pk)
    if purchase.access_status == AccessStatus.INVITED:
        svc.refresh_access_status(db, purchase)
        db.commit()
    product = purchase.product
    versions = version_services.approved_versions(db, product)
    mirror = product.mirror_repo_full_name
    mirror_url = get_client().mirror_url(mirror) if mirror else ""
    review = review_for_purchase(db, purchase)
    dispute = db.scalar(select(Dispute).where(Dispute.purchase_id == purchase.id))
    orders = db.scalars(
        select(CustomOrder).where(CustomOrder.purchase_id == purchase.id).order_by(CustomOrder.created_at.desc())
    ).all()
    return PurchaseDetail(
        id=purchase.id,
        product=product_ref(product),
        price=purchase.price,
        commission=purchase.commission,
        status=purchase.status,
        status_label=PurchaseStatus.label(purchase.status),
        access_status=purchase.access_status,
        access_label=AccessStatus.label(purchase.access_status),
        license_version=purchase.license_version,
        created_at=purchase.created_at,
        paid_at=purchase.paid_at,
        purchased_version=purchase.version.tag_name if purchase.version else None,
        versions=[version_short(v) for v in versions],
        can_download=svc.can_download(user, purchase) and bool(versions),
        mirror_url=mirror_url,
        clone_command=f"git clone {mirror_url}.git" if mirror_url else "",
        github_login=purchase.buyer.github_login,
        dispute_days_left=svc.dispute_days_left(purchase),
        review=ReviewShort(rating=review.rating, text=review.text, created_at=review.created_at) if review else None,
        orders=[order_row(o) for o in orders],
        dispute=dispute_short(dispute),
        can_review=purchase.buyer_id == user.id and purchase.status in ("paid", "completed") and review is None,
    )


@router.post("/purchases/{pk}/access", response_model=Ok)
def get_access(pk: int, data: GithubLoginIn, db: DB, user: CurrentUser):
    """«Получить доступ»: сохранить логин GitHub (если введён) и пригласить в репозиторий-копию."""
    purchase = svc.get_purchase_for(db, user, pk)
    if purchase.buyer_id != user.id:
        raise NotFound("Покупка не найдена")
    if data.github_login.strip():
        account_services.set_github_login(db, user, data.github_login)
    svc.grant_access(db, purchase)
    db.commit()
    return Ok(message="Приглашение в репозиторий отправлено. Примите его на GitHub.")


@router.get("/purchases/{pk}/download")
def download(pk: int, db: DB, user: CurrentUser):
    """ZIP последней одобренной версии: только через проверку права (чужая покупка — 404)."""
    purchase = svc.get_purchase_for(db, user, pk)
    version = svc.download_version(db, user, purchase)
    return FileResponse(
        version_services.archive_path(version),
        media_type="application/zip",
        filename=f"{purchase.product.slug}-{version.tag_name}.zip",
    )


# ---------------------------------------------------------------- профиль


@router.get("/profile", response_model=UserOut)
def profile(user: CurrentUser):
    return user


@router.put("/profile", response_model=UserOut)
def update_profile(data: ProfileIn, db: DB, user: CurrentUser):
    account_services.update_profile(db, user, username=data.username, github_login=data.github_login)
    db.commit()
    return user

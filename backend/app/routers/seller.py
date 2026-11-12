"""Кабинет продавца: подключение GitHub, мастер продукта, скриншоты, релизы и версии, статистика."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import DB, CurrentUser, SellerUser
from app.core.errors import FieldsError, Forbidden, NotFound, ServiceError
from app.integrations.github import get_client
from app.integrations.github.base import GitHubError
from app.models import Product, ProductStatus, ProductVersion, User, VersionStatus
from app.schemas.catalog import (
    AppealIn,
    GithubCallbackIn,
    GithubConnectOut,
    ImportIn,
    MediaOut,
    ProductCreateIn,
    ProductEditOut,
    ProductIn,
    ReleaseOut,
    RepoOut,
    ReposOut,
    SellerDashboard,
    SellerProductRow,
    SellerTiles,
    VersionsPage,
)
from app.schemas.common import Ok
from app.schemas.convert import cover_url, product_edit_out, screenshots, version_out
from app.services import accounts as account_services
from app.services import catalog as svc
from app.services import plagiarism as plag_services
from app.services import reports as report_services
from app.services import versions as version_services

router = APIRouter(prefix="/api/seller", tags=["продавец"])
FAKE_INSTALLATION_BASE = 900_000_000


def own_product(db, user: User, pk: int) -> Product:
    """Свой продукт продавца; чужой — 404."""
    product = db.scalar(
        select(Product)
        .where(Product.id == pk, Product.seller_id == user.id)
        .options(selectinload(Product.screenshots), selectinload(Product.technologies), selectinload(Product.platforms))
    )
    if product is None:
        raise NotFound("Продукт не найден")
    return product


# ---------------------------------------------------------------- кабинет


@router.get("/dashboard", response_model=SellerDashboard)
def dashboard(db: DB, user: CurrentUser):
    """Продукты продавца со статусами и плитки (выручка за месяц, продажи, просмотры, рейтинг)."""
    if not user.is_seller:
        return SellerDashboard(is_seller=False, github_mode=settings.github_mode, tiles=None, products=[])
    rows = []
    products = db.scalars(
        select(Product)
        .where(Product.seller_id == user.id)
        .options(selectinload(Product.screenshots), selectinload(Product.category))
        .order_by(Product.published_at.desc().nulls_first(), Product.created_at.desc())
    ).all()
    for p in products:
        current = version_services.current_version(db, p)
        pending = db.scalar(
            select(ProductVersion.tag_name)
            .where(
                ProductVersion.product_id == p.id,
                ProductVersion.status.in_([VersionStatus.CHECKING, VersionStatus.MODERATION, VersionStatus.APPEAL]),
            )
            .limit(1)
        )
        section = p.category.parent or p.category
        rows.append(
            SellerProductRow(
                id=p.id,
                slug=p.slug,
                title=p.title,
                status=p.status,
                status_label=ProductStatus.label(p.status),
                price=p.price,
                sales_count=p.sales_count,
                category=p.category.name,
                section=section.name,
                cover=cover_url(p),
                current_version=current.tag_name if current else None,
                pending_version=pending,
            )
        )
    tiles = report_services.seller_tiles(db, user)
    return SellerDashboard(is_seller=True, github_mode=settings.github_mode, tiles=SellerTiles(**tiles), products=rows)


# ---------------------------------------------------------------- GitHub


def _state_for(user: User) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"u": user.id, "type": "gh-install", "exp": now + timedelta(hours=1)}, settings.secret_key, algorithm="HS256"
    )


@router.get("/github", response_model=GithubConnectOut)
def github_info(user: CurrentUser):
    """Страница «Подключить GitHub»: в реальном режиме — адрес установки GitHub App."""
    client = get_client()
    install_url = client.install_url(_state_for(user)) if client.mode == "real" else None
    return GithubConnectOut(mode=client.mode, install_url=install_url, connected=user.is_seller)


@router.post("/github/connect", response_model=Ok)
def github_connect_fake(db: DB, user: CurrentUser):
    """Демо-режим: подключение без GitHub (installation_id = 900 000 000 + id пользователя)."""
    if get_client().mode != "fake":
        raise ServiceError("Подключение без GitHub доступно только в демо-режиме.")
    account_services.connect_github(db, user, FAKE_INSTALLATION_BASE + user.id)
    db.commit()
    return Ok(message="GitHub подключён (демо-режим). Теперь можно создавать продукты.")


@router.post("/github/callback", response_model=Ok)
def github_callback(data: GithubCallbackIn, db: DB, user: CurrentUser):
    """GitHub вернул пользователя после установки приложения: ?installation_id=...&state=..."""
    try:
        payload = jwt.decode(data.state, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise ServiceError("Ссылка подключения устарела, попробуйте ещё раз.")
    if payload.get("type") != "gh-install" or payload.get("u") != user.id:
        raise Forbidden()
    if not data.installation_id.isdigit():
        raise ServiceError("GitHub не передал номер установки.")
    try:
        account = get_client().check_installation(int(data.installation_id))
    except GitHubError as e:
        raise ServiceError(str(e))
    account_services.connect_github(db, user, int(data.installation_id))
    db.commit()
    return Ok(message=f"GitHub подключён: {account}.")


# ---------------------------------------------------------------- мастер продукта


@router.get("/repos", response_model=ReposOut)
def repos(user: SellerUser):
    """Шаг 1 мастера: репозитории, к которым установлено приложение; нужно ли принять условия продавца."""
    try:
        items = get_client().list_repositories(user.github_installation_id)
        error = ""
    except GitHubError as e:
        items, error = [], str(e)
    return ReposOut(
        repos=[RepoOut(id=r.id, full_name=r.full_name) for r in items],
        need_terms=user.seller_terms_accepted_at is None,
        error=error,
    )


@router.post("/products", response_model=ProductEditOut, status_code=201)
def create_product(data: ProductCreateIn, db: DB, user: SellerUser):
    """Создать черновик (шаги 1–3 мастера одним запросом). Ошибки полей — в fields."""
    try:
        repos = {r.full_name: r for r in get_client().list_repositories(user.github_installation_id)}
    except GitHubError as e:
        raise ServiceError(str(e))
    if data.repo_full_name not in repos:
        raise FieldsError({"repo_full_name": "Выберите репозиторий из списка."})
    if user.seller_terms_accepted_at is None:
        if not data.accept_seller_terms:
            raise FieldsError({"accept_seller_terms": "Без согласия создать продукт нельзя."})
        account_services.accept_seller_terms(db, user)
    payload = data.model_dump(exclude={"repo_full_name", "accept_seller_terms", "technology_ids", "platform_ids"})
    payload.update(source_repo_full_name=data.repo_full_name, source_repo_id=repos[data.repo_full_name].id)
    product = svc.create_product(
        db, user, data=payload, technology_ids=data.technology_ids, platform_ids=data.platform_ids
    )
    db.commit()
    return product_edit_out(product)


@router.get("/products/{pk}", response_model=ProductEditOut)
def get_product(pk: int, db: DB, user: SellerUser):
    return product_edit_out(own_product(db, user, pk))


@router.put("/products/{pk}", response_model=ProductEditOut)
def update_product(pk: int, data: ProductIn, db: DB, user: SellerUser):
    product = own_product(db, user, pk)
    svc.update_product(
        db,
        product,
        user,
        data=data.model_dump(exclude={"technology_ids", "platform_ids"}),
        technology_ids=data.technology_ids,
        platform_ids=data.platform_ids,
    )
    db.commit()
    return product_edit_out(product)


@router.post("/products/{pk}/hide", response_model=Ok)
def hide(pk: int, db: DB, user: SellerUser):
    svc.hide_product(db, own_product(db, user, pk), user)
    db.commit()
    return Ok(message="Продукт снят с продажи. У покупателей доступ сохраняется.")


@router.post("/products/{pk}/unhide", response_model=Ok)
def unhide(pk: int, db: DB, user: SellerUser):
    svc.unhide_product(db, own_product(db, user, pk), user)
    db.commit()
    return Ok(message="Продукт снова в продаже.")


@router.delete("/products/{pk}", response_model=Ok)
def delete(pk: int, db: DB, user: SellerUser):
    svc.delete_product(db, own_product(db, user, pk), user)
    db.commit()
    return Ok(message="Продукт удалён.")


# ---------------------------------------------------------------- скриншоты и релизы


def _releases(db, product, user):
    try:
        items = version_services.available_releases(db, product, user)
        return [
            ReleaseOut(
                tag_name=r["release"].tag_name,
                name=r["release"].name,
                published_at=r["release"].published_at,
                imported=r["imported"],
            )
            for r in items
        ], ""
    except ServiceError as e:
        return [], e.message


@router.get("/products/{pk}/media", response_model=MediaOut)
def media(pk: int, db: DB, user: SellerUser):
    """Шаг 4 мастера: скриншоты и релизы для проверки."""
    product = own_product(db, user, pk)
    releases, error = _releases(db, product, user)
    return MediaOut(
        product=product_edit_out(product),
        screenshots=screenshots(product),
        max_screens=svc.MAX_SCREENSHOTS,
        releases=releases,
        release_error=error,
    )


@router.post("/products/{pk}/screenshots", response_model=MediaOut)
def upload_screenshots(pk: int, db: DB, user: SellerUser, images: list[UploadFile] = File(...)):  # noqa: B008
    product = own_product(db, user, pk)
    files = [(f.filename or "image", f.file.read()) for f in images if f.filename]
    if not files:
        raise ServiceError("Выберите файлы.")
    svc.add_screenshots(db, product, user, files)
    db.commit()
    return media(pk, db, user)


@router.delete("/products/{pk}/screenshots/{sid}", response_model=Ok)
def delete_screenshot(pk: int, sid: int, db: DB, user: SellerUser):
    svc.delete_screenshot(db, own_product(db, user, pk), user, sid)
    db.commit()
    return Ok(message="Скриншот удалён.")


@router.get("/products/{pk}/versions", response_model=VersionsPage)
def versions(pk: int, db: DB, user: SellerUser):
    """Версии продукта со статусами и совпадениями (для автоотказа), релизы для проверки."""
    product = own_product(db, user, pk)
    items = version_services.product_versions(db, product)
    matches = plag_services.matches_for_versions(db, [v for v in items if v.status == VersionStatus.REJECTED_AUTO])
    releases, error = _releases(db, product, user)
    return VersionsPage(
        product=product_edit_out(product),
        versions=[version_out(v, matches.get(v.id)) for v in items],
        releases=releases,
        release_error=error,
    )


@router.post("/products/{pk}/versions/import", response_model=Ok)
def import_release(pk: int, data: ImportIn, db: DB, user: SellerUser):
    v = version_services.import_release(db, own_product(db, user, pk), user, data.tag)
    db.commit()
    return Ok(message=f"Релиз {v.tag_name} получен и отправлен на проверку на заимствования.")


@router.post("/versions/{vid}/appeal", response_model=Ok)
def appeal(vid: int, data: AppealIn, db: DB, user: SellerUser):
    version = db.get(ProductVersion, vid)
    if version is None or version.product.seller_id != user.id:
        raise NotFound("Версия не найдена")
    version_services.appeal_version(db, version, user, data.appeal_text)
    db.commit()
    return Ok(message="Обжалование отправлено модератору.")

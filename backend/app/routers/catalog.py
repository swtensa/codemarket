"""Публичный каталог: справочники, список продуктов с фильтрами, страница продукта."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.core.deps import DB, OptionalUser, visitor_id
from app.core.errors import NotFound
from app.models import ProductStatus
from app.schemas.catalog import (
    CatalogRefs,
    CategoryOut,
    ProductCard,
    ProductDetail,
    QuestionOut,
    RefOut,
    ReviewOut,
    SectionOut,
    SellerInfo,
    SortOut,
)
from app.schemas.common import Page
from app.schemas.convert import category_out, product_card, screenshots, version_short
from app.services import catalog as svc
from app.services import orders as order_services
from app.services import purchases as purchase_services
from app.services import reviews as review_services
from app.services import versions as version_services

router = APIRouter(prefix="/api/catalog", tags=["каталог"])


@router.get("/refs", response_model=CatalogRefs)
def refs(db: DB):
    """Разделы с подкатегориями и числом продуктов, технологии, платформы, варианты сортировки."""
    side = svc.catalog_sidebar(db)
    return CatalogRefs(
        sections=[
            SectionOut(
                id=s.id,
                name=s.name,
                slug=s.slug,
                icon=s.icon,
                position=s.position,
                product_count=n,
                children=[CategoryOut.model_validate(c) for c in s.children],
            )
            for s, n in side["sections"]
        ],
        technologies=[RefOut.model_validate(t) for t in side["technologies"]],
        platforms=[RefOut.model_validate(p) for p in side["platforms"]],
        sorts=[SortOut(key=k, label=v[0]) for k, v in svc.SORTS.items()],
    )


@router.get("/products", response_model=Page[ProductCard])
def products(
    db: DB,
    q: str = "",
    section: str = "",
    category: str = "",
    price_min: str | None = None,
    price_max: str | None = None,
    tech: Annotated[list[str], Query()] = [],  # noqa: B006
    platform: Annotated[list[str], Query()] = [],  # noqa: B006
    rating: str | None = None,
    sort: str = "new",
    page: int = 1,
    page_size: int = Query(svc.PAGE_SIZE, ge=1, le=60),
):
    """Каталог: поиск, фильтры (все выбранные технологии; хотя бы одна из платформ), сортировка, страницы по 12."""
    query = svc.CatalogQuery(q, section, category, price_min, price_max, tech, platform, rating, sort)
    stmt, _applied, _sort = svc.search_catalog(db, query)
    items, total, page, pages = svc.paginate(db, stmt, page, page_size)
    return Page(items=[product_card(p) for p in items], total=total, page=page, pages=pages)


@router.get("/products/{slug}", response_model=ProductDetail)
def product_detail(slug: str, request: Request, db: DB, user: OptionalUser):
    """Страница продукта. Просмотр записывается не чаще раза в сутки на посетителя (свои не считаются)."""
    product = svc.get_public_product(db, slug, user)
    if product is None:
        raise NotFound("Продукт не найден")
    if product.status == ProductStatus.PUBLISHED:
        svc.record_view(db, product, user, visitor_id(request))
        db.commit()
    purchase = purchase_services.active_purchase(db, user, product) if user else None
    about_product, about_orders = review_services.product_reviews(db, product)
    seller_avg, seller_count = review_services.seller_rating(db, product.seller)

    def review(r):
        return ReviewOut(id=r.id, author=r.author.username, rating=r.rating, text=r.text, created_at=r.created_at)

    return ProductDetail(
        id=product.id,
        slug=product.slug,
        title=product.title,
        short_description=product.short_description,
        description=product.description,
        price=product.price,
        demo_url=product.demo_url,
        status=product.status,
        status_label=ProductStatus.label(product.status),
        rating_avg=product.rating_avg,
        rating_count=product.rating_count,
        section=category_out(product.section),
        category=category_out(product.category),
        seller=SellerInfo(
            id=product.seller.id,
            username=product.seller.username,
            rating=seller_avg,
            reviews=seller_count,
            sales=svc.seller_sales(db, product.seller_id),
        ),
        technologies=[RefOut.model_validate(t) for t in product.technologies],
        platforms=[RefOut.model_validate(p) for p in product.platforms],
        screenshots=screenshots(product),
        versions=[version_short(v) for v in version_services.approved_versions(db, product)],
        current_version=version_short(version_services.current_version(db, product)),
        product_reviews=[review(r) for r in about_product],
        order_reviews=[review(r) for r in about_orders],
        questions=[QuestionOut(**q) for q in order_services.public_questions(db, product)],
        is_owner=bool(user and user.id == product.seller_id),
        purchase_id=purchase.id if purchase else None,
    )

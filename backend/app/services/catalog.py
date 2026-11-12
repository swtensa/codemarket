"""Каталог: поиск и фильтры, просмотры, продукты продавца, статусы продукта (раздел 7.1 ТЗ)."""

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.errors import FieldsError, InvalidTransition, NotFound, ServiceError
from app.core.storage import delete_private, delete_public, save_public
from app.models import (
    PRODUCT_MAX_PRICE,
    PRODUCT_MIN_PRICE,
    Category,
    CustomOrder,
    Platform,
    Product,
    ProductStatus,
    ProductVersion,
    ProductView,
    Purchase,
    Screenshot,
    Technology,
    User,
    product_platforms,
    product_technologies,
)
from app.models.base import utcnow

admin_log = logging.getLogger("codemarket.admin")
PS = ProductStatus

PAGE_SIZE = 12
MAX_SCREENSHOTS = 8
SCREENSHOT_MAX_BYTES = 3 * 1024 * 1024
SCREENSHOT_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

SORTS = {
    "new": ("Новые", [Product.published_at.desc().nulls_last(), Product.id.desc()]),
    "cheap": ("Дешевле", [Product.price, Product.id.desc()]),
    "expensive": ("Дороже", [Product.price.desc(), Product.id.desc()]),
    "rating": ("По рейтингу", [Product.rating_avg.desc(), Product.rating_count.desc(), Product.id.desc()]),
    "popular": ("Популярные", [Product.sales_count.desc(), Product.id.desc()]),
}

PRODUCT_TRANSITIONS = {
    PS.DRAFT: {PS.CHECKING},
    PS.CHECKING: {PS.MODERATION, PS.REJECTED},
    PS.MODERATION: {PS.PUBLISHED, PS.REJECTED, PS.CHECKING},
    PS.PUBLISHED: {PS.HIDDEN, PS.BLOCKED},
    PS.HIDDEN: {PS.PUBLISHED, PS.BLOCKED},
    PS.REJECTED: {PS.CHECKING},
    PS.BLOCKED: {PS.PUBLISHED},
}


# ---------------------------------------------------------------- статусы


def change_product_status(db: Session, product: Product, new_status: str) -> Product:
    """Сменить статус продукта, проверив допустимость перехода."""
    if new_status not in PRODUCT_TRANSITIONS.get(product.status, set()):
        raise InvalidTransition(f"Продукт: переход {product.status} → {new_status} недопустим")
    product.status = new_status
    if new_status == PS.PUBLISHED and product.published_at is None:
        product.published_at = utcnow()
    db.flush()
    return product


def on_release_submitted(db, product):
    """Релиз отправлен на проверку: draft/rejected → checking. Опубликованный продукт не меняет статус."""
    if product.status in (PS.DRAFT, PS.REJECTED):
        change_product_status(db, product, PS.CHECKING)


def on_version_checked(db, product, *, rejected_auto):
    if product.status != PS.CHECKING:
        return
    change_product_status(db, product, PS.REJECTED if rejected_auto else PS.MODERATION)


def on_version_appealed(db, product):
    if product.status == PS.REJECTED:
        change_product_status(db, product, PS.CHECKING)
        change_product_status(db, product, PS.MODERATION)


def on_version_approved(db, product):
    if product.status in (PS.MODERATION, PS.CHECKING):
        if product.status == PS.CHECKING:
            change_product_status(db, product, PS.MODERATION)
        change_product_status(db, product, PS.PUBLISHED)


def on_version_rejected(db, product):
    if product.status == PS.MODERATION:
        change_product_status(db, product, PS.REJECTED)


def _check_owner(product: Product, user: User) -> None:
    if product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")


def hide_product(db, product, user):
    _check_owner(product, user)
    return change_product_status(db, product, PS.HIDDEN)


def unhide_product(db, product, user):
    _check_owner(product, user)
    if product.status != PS.HIDDEN:
        raise InvalidTransition("Вернуть в продажу можно только снятый продукт")
    return change_product_status(db, product, PS.PUBLISHED)


def block_product(db, product, *, admin, reason=""):
    change_product_status(db, product, PS.BLOCKED)
    admin_log.info("admin=%s blocked product=%s reason=%s", admin.username, product.id, reason)
    return product


def unblock_product(db, product, *, admin):
    change_product_status(db, product, PS.PUBLISHED)
    admin_log.info("admin=%s unblocked product=%s", admin.username, product.id)
    return product


# ---------------------------------------------------------------- каталог


def visible_condition():
    """Видимые в каталоге: опубликованы и продавец не заблокирован."""
    return and_(Product.status == PS.PUBLISHED, Product.seller.has(User.status == "active"))


def _to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None


@dataclass
class CatalogQuery:
    q: str = ""
    section: str = ""
    category: str = ""
    price_min: str | None = None
    price_max: str | None = None
    tech: list[str] = field(default_factory=list)
    platform: list[str] = field(default_factory=list)
    rating: str | None = None
    sort: str = "new"


def search_catalog(db: Session, query: CatalogQuery):
    """Отфильтровать и отсортировать каталог. Возвращает (select, применённые фильтры, сортировка)."""
    stmt = select(Product).where(visible_condition())
    applied: dict = {}
    q = (query.q or "").strip()
    if q:
        stmt = stmt.where(or_(Product.title.ilike(f"%{q}%"), Product.short_description.ilike(f"%{q}%")))
        applied["q"] = q
    if query.category:
        stmt = stmt.where(Product.category.has(Category.slug == query.category))
        applied["category"] = query.category
    elif query.section:
        section_ids = select(Category.id).where(Category.slug == query.section, Category.parent_id.is_(None))
        stmt = stmt.where(
            Product.category_id.in_(
                select(Category.id).where(or_(Category.slug == query.section, Category.parent_id.in_(section_ids)))
            )
        )
        applied["section"] = query.section
    pmin, pmax = _to_decimal(query.price_min), _to_decimal(query.price_max)
    if pmin is not None:
        stmt = stmt.where(Product.price >= pmin)
        applied["price_min"] = pmin
    if pmax is not None:
        stmt = stmt.where(Product.price <= pmax)
        applied["price_max"] = pmax
    techs = [t for t in query.tech if t]
    for t in techs:  # все выбранные технологии должны быть у продукта
        stmt = stmt.where(
            exists().where(
                product_technologies.c.product_id == Product.id,
                product_technologies.c.technology_id == Technology.id,
                Technology.slug == t,
            )
        )
    if techs:
        applied["tech"] = techs
    platforms = [p for p in query.platform if p]
    if platforms:  # совместим хотя бы с одной из выбранных платформ
        stmt = stmt.where(
            exists().where(
                product_platforms.c.product_id == Product.id,
                product_platforms.c.platform_id == Platform.id,
                Platform.slug.in_(platforms),
            )
        )
        applied["platform"] = platforms
    rating = _to_decimal(query.rating)
    if rating:
        stmt = stmt.where(Product.rating_avg >= rating)
        applied["rating"] = rating
    sort = query.sort if query.sort in SORTS else "new"
    stmt = stmt.order_by(*SORTS[sort][1]).options(
        selectinload(Product.category).selectinload(Category.parent),
        selectinload(Product.seller),
        selectinload(Product.technologies),
        selectinload(Product.screenshots),
    )
    return stmt, applied, sort


def paginate(db: Session, stmt, page: int, page_size: int):
    """(элементы, всего, страница, страниц) — номер страницы приводится к допустимому, как в Django Paginator."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    pages = max(1, -(-total // page_size))
    page = min(max(1, page or 1), pages)
    items = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).unique().all()
    return items, total, page, pages


def catalog_sidebar(db: Session):
    """Разделы с подкатегориями и числом продуктов, технологии, платформы."""
    counts = dict(
        db.execute(
            select(Category.parent_id, func.count(Product.id))
            .join(Product, Product.category_id == Category.id)
            .where(visible_condition())
            .group_by(Category.parent_id)
        ).all()
    )
    sections = db.scalars(
        select(Category)
        .where(Category.parent_id.is_(None))
        .order_by(Category.position, Category.name)
        .options(selectinload(Category.children))
    ).all()
    return {
        "sections": [(s, counts.get(s.id, 0)) for s in sections],
        "technologies": db.scalars(select(Technology).order_by(Technology.name)).all(),
        "platforms": db.scalars(select(Platform).order_by(Platform.name)).all(),
    }


def get_public_product(db: Session, slug: str, user: User | None) -> Product | None:
    """Продукт для страницы. Неопубликованный видят владелец и админ; снятый — ещё и купившие."""
    product = db.scalar(
        select(Product)
        .where(Product.slug == slug)
        .options(
            selectinload(Product.category).selectinload(Category.parent),
            selectinload(Product.seller),
            selectinload(Product.technologies),
            selectinload(Product.platforms),
            selectinload(Product.screenshots),
        )
    )
    if product is None:
        return None
    visible = product.status == PS.PUBLISHED and product.seller.status == "active"
    if visible or (user and (user.is_staff or user.id == product.seller_id)):
        return product
    if user and product.status in (PS.HIDDEN, PS.BLOCKED):
        from app.services.purchases import has_access

        if has_access(db, user, product):
            return product
    return None


def record_view(db: Session, product: Product, user: User | None, visitor: str) -> bool:
    """Записать просмотр: не чаще одного на посетителя в сутки, свои просмотры не считаются."""
    if user and user.id == product.seller_id:
        return False
    since = utcnow() - timedelta(days=1)
    seen = db.scalar(
        select(ProductView.id).where(
            ProductView.product_id == product.id, ProductView.session_key == visitor, ProductView.viewed_at >= since
        )
    )
    if seen:
        return False
    db.add(ProductView(product_id=product.id, session_key=visitor[:40], user_id=user.id if user else None))
    db.flush()
    return True


def seller_sales(db: Session, seller_id: int) -> int:
    return db.scalar(select(func.coalesce(func.sum(Product.sales_count), 0)).where(Product.seller_id == seller_id))


# ---------------------------------------------------------------- продукты продавца

_TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip


def _translit(text: str) -> str:
    """Транслитерация русского названия для адреса продукта (как slugify в Django)."""
    s = "".join(_TR.get(ch, ch) for ch in text.lower())
    s = re.sub(r"[^\w\s-]", "", s, flags=re.ASCII)
    return re.sub(r"[-\s]+", "-", s).strip("-_")


def unique_slug(db: Session, title: str, exclude_id: int | None = None) -> str:
    base = (_translit(title) or "product")[:120]
    slug, n = base, 2
    while db.scalar(select(Product.id).where(Product.slug == slug, Product.id != (exclude_id or 0))):
        slug = f"{base}-{n}"
        n += 1
    return slug


URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)


def _validate(data: dict) -> dict:
    """Проверки полей продукта (как full_clean модели Django)."""
    errors = {}
    title = (data.get("title") or "").strip()
    short = (data.get("short_description") or "").strip()
    desc = (data.get("description") or "").strip()
    if not title:
        errors["title"] = "Обязательное поле."
    elif len(title) > 120:
        errors["title"] = "Не больше 120 символов."
    if not short:
        errors["short_description"] = "Обязательное поле."
    elif len(short) > 200:
        errors["short_description"] = "Не больше 200 символов."
    if not desc:
        errors["description"] = "Обязательное поле."
    price = _to_decimal(data.get("price"))
    if price is None:
        errors["price"] = "Введите число."
    elif not PRODUCT_MIN_PRICE <= price <= PRODUCT_MAX_PRICE:
        errors["price"] = f"Цена — от {PRODUCT_MIN_PRICE} до {PRODUCT_MAX_PRICE:,} ₽.".replace(",", " ")
    demo = (data.get("demo_url") or "").strip()
    if demo and not demo.lower().startswith(("http://", "https://")):
        demo = "https://" + demo
    if demo and not URL_RE.match(demo):
        errors["demo_url"] = "Введите правильный адрес."
    if errors:
        raise FieldsError(errors)
    return {**data, "title": title, "short_description": short, "description": desc, "price": price, "demo_url": demo}


def _category(db: Session, category_id) -> Category:
    cat = db.get(Category, category_id) if category_id else None
    if cat is None or cat.parent_id is None:
        raise FieldsError({"category_id": "Выберите подкатегорию."})
    return cat


def create_product(db: Session, seller: User, *, data: dict, technology_ids=(), platform_ids=()) -> Product:
    """Создать черновик продукта. Требует подключённый GitHub и принятые условия продавца."""
    if not seller.is_seller:
        raise ServiceError("Сначала подключите GitHub.")
    if seller.seller_terms_accepted_at is None:
        raise ServiceError("Нужно принять условия для продавцов.")
    data = _validate(data)
    cat = _category(db, data.pop("category_id", None))
    product = Product(seller_id=seller.id, category_id=cat.id, status=PS.DRAFT, **data)
    product.slug = unique_slug(db, product.title)
    product.technologies = list(db.scalars(select(Technology).where(Technology.id.in_(technology_ids or []))))
    product.platforms = list(db.scalars(select(Platform).where(Platform.id.in_(platform_ids or []))))
    db.add(product)
    db.flush()
    return product


def update_product(db: Session, product: Product, user: User, *, data: dict, technology_ids=None, platform_ids=None):
    """Изменить описание, цену, категорию продукта."""
    _check_owner(product, user)
    data = _validate(data)
    cat = _category(db, data.pop("category_id", None))
    for k, v in data.items():
        setattr(product, k, v)
    product.category_id = cat.id
    if technology_ids is not None:
        product.technologies = list(db.scalars(select(Technology).where(Technology.id.in_(technology_ids))))
    if platform_ids is not None:
        product.platforms = list(db.scalars(select(Platform).where(Platform.id.in_(platform_ids))))
    db.flush()
    return product


def validate_screenshot(filename: str, size: int) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SCREENSHOT_EXTENSIONS:
        raise ServiceError("Допустимы только jpg, png и webp.")
    if size > SCREENSHOT_MAX_BYTES:
        raise ServiceError("Файл больше 3 МБ.")


def add_screenshot_bytes(db: Session, product: Product, filename: str, data: bytes, position: int) -> Screenshot:
    rel = save_public(f"screenshots/{product.id}", filename, data)
    shot = Screenshot(product_id=product.id, image=rel, position=position)
    db.add(shot)
    db.flush()
    return shot


def add_screenshots(db: Session, product: Product, user: User, files: list[tuple[str, bytes]]) -> list[Screenshot]:
    """Добавить скриншоты (не больше 8, jpg/png/webp, до 3 МБ)."""
    _check_owner(product, user)
    existing = db.scalar(select(func.count()).where(Screenshot.product_id == product.id)) or 0
    if existing + len(files) > MAX_SCREENSHOTS:
        raise ServiceError(f"Можно загрузить не больше {MAX_SCREENSHOTS} скриншотов.")
    for name, data in files:
        validate_screenshot(name, len(data))
    out = [add_screenshot_bytes(db, product, name, data, existing + i) for i, (name, data) in enumerate(files)]
    db.refresh(product)
    return out


def delete_screenshot(db: Session, product: Product, user: User, screenshot_id: int) -> None:
    _check_owner(product, user)
    shot = db.get(Screenshot, screenshot_id)
    if shot is None or shot.product_id != product.id:
        raise NotFound()
    delete_public(shot.image)
    db.delete(shot)
    db.flush()
    db.refresh(product)


def delete_product(db: Session, product: Product, user: User) -> None:
    """Удалить продукт. Нельзя, если у него есть покупки, вопросы или заказы — только снять с продажи."""
    _check_owner(product, user)
    from app.services.purchases import product_has_purchases

    if product_has_purchases(db, product):
        raise ServiceError("У продукта есть покупки: его можно только снять с продажи.")
    has_any = db.scalar(select(Purchase.id).where(Purchase.product_id == product.id).limit(1)) or db.scalar(
        select(CustomOrder.id).where(CustomOrder.product_id == product.id).limit(1)
    )
    if has_any:
        raise ServiceError("По продукту есть начатые покупки, вопросы или заказы: его можно только снять с продажи.")
    for shot in product.screenshots:
        delete_public(shot.image)
    for version in db.scalars(select(ProductVersion).where(ProductVersion.product_id == product.id)):
        delete_private(version.archive)
    db.delete(product)
    db.flush()


def increment_sales(db: Session, product: Product) -> None:
    db.execute(update(Product).where(Product.id == product.id).values(sales_count=Product.sales_count + 1))
    db.refresh(product)


def set_rating(db: Session, product_id: int, avg, count: int) -> None:
    db.execute(update(Product).where(Product.id == product_id).values(rating_avg=avg, rating_count=count))


def set_mirror_repo(db: Session, product: Product, full_name: str) -> None:
    if product.mirror_repo_full_name != full_name:
        product.mirror_repo_full_name = full_name
        db.flush()

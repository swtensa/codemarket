"""Сервисы каталога: поиск и фильтры, просмотры, продукты продавца, статусы продукта."""

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.utils import timezone
from django.utils.text import slugify

from apps.core.exceptions import InvalidTransition, ServiceError

from .models import Category, Platform, Product, ProductView, Screenshot, Technology

admin_log = logging.getLogger("codemarket.admin")

PAGE_SIZE = 12
MAX_SCREENSHOTS = 8
SCREENSHOT_MAX_BYTES = 3 * 1024 * 1024
SCREENSHOT_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

SORTS = {
    "new": ("Новые", ["-published_at", "-id"]),
    "cheap": ("Дешевле", ["price", "-id"]),
    "expensive": ("Дороже", ["-price", "-id"]),
    "rating": ("По рейтингу", ["-rating_avg", "-rating_count", "-id"]),
    "popular": ("Популярные", ["-sales_count", "-id"]),
}

# Допустимые переходы статусов продукта (раздел 7.1 ТЗ).
PRODUCT_TRANSITIONS = {
    Product.Status.DRAFT: {Product.Status.CHECKING},
    Product.Status.CHECKING: {Product.Status.MODERATION, Product.Status.REJECTED},
    Product.Status.MODERATION: {Product.Status.PUBLISHED, Product.Status.REJECTED, Product.Status.CHECKING},
    Product.Status.PUBLISHED: {Product.Status.HIDDEN, Product.Status.BLOCKED},
    Product.Status.HIDDEN: {Product.Status.PUBLISHED, Product.Status.BLOCKED},
    Product.Status.REJECTED: {Product.Status.CHECKING},
    Product.Status.BLOCKED: {Product.Status.PUBLISHED},
}


# ---------------------------------------------------------------- статусы


def change_product_status(product, new_status):
    """Сменить статус продукта, проверив допустимость перехода."""
    if new_status not in PRODUCT_TRANSITIONS.get(product.status, set()):
        raise InvalidTransition(f"Продукт: переход {product.status} → {new_status} недопустим")
    product.status = new_status
    fields = ["status"]
    if new_status == Product.Status.PUBLISHED and product.published_at is None:
        product.published_at = timezone.now()
        fields.append("published_at")
    product.save(update_fields=fields)
    return product


def on_release_submitted(product):
    """Продавец отправил релиз на проверку: draft/rejected → checking.

    Для уже опубликованного продукта статус не меняется: новая версия
    проверяется отдельно, а покупатели продолжают получать текущую.
    """
    if product.status in (Product.Status.DRAFT, Product.Status.REJECTED):
        change_product_status(product, Product.Status.CHECKING)


def on_version_checked(product, *, rejected_auto):
    """Итог автоматической проверки первой версии."""
    if product.status != Product.Status.CHECKING:
        return
    if rejected_auto:
        change_product_status(product, Product.Status.REJECTED)
    else:
        change_product_status(product, Product.Status.MODERATION)


def on_version_appealed(product):
    """Обжалование автоотказа отправляет продукт на модерацию."""
    if product.status == Product.Status.REJECTED:
        product.status = Product.Status.CHECKING
        change_product_status(product, Product.Status.MODERATION)


def on_version_approved(product):
    """Версия одобрена: новый продукт публикуется."""
    if product.status in (Product.Status.MODERATION, Product.Status.CHECKING):
        if product.status == Product.Status.CHECKING:
            change_product_status(product, Product.Status.MODERATION)
        change_product_status(product, Product.Status.PUBLISHED)


def on_version_rejected(product):
    """Модератор отклонил версию неопубликованного продукта."""
    if product.status == Product.Status.MODERATION:
        change_product_status(product, Product.Status.REJECTED)


def hide_product(product, user):
    """Продавец снимает продукт с продажи."""
    _check_owner(product, user)
    return change_product_status(product, Product.Status.HIDDEN)


def unhide_product(product, user):
    """Продавец возвращает продукт в продажу."""
    _check_owner(product, user)
    if product.status != Product.Status.HIDDEN:
        raise InvalidTransition("Вернуть в продажу можно только снятый продукт")
    return change_product_status(product, Product.Status.PUBLISHED)


def block_product(product, *, admin, reason=""):
    """Администратор блокирует продукт."""
    change_product_status(product, Product.Status.BLOCKED)
    admin_log.info("admin=%s blocked product=%s reason=%s", admin, product.pk, reason)
    return product


def unblock_product(product, *, admin):
    change_product_status(product, Product.Status.PUBLISHED)
    admin_log.info("admin=%s unblocked product=%s", admin, product.pk)
    return product


def _check_owner(product, user):
    if product.seller_id != user.id:
        raise ServiceError("Это не ваш продукт.")


# ---------------------------------------------------------------- каталог


def visible_products():
    """Продукты, видимые в каталоге: опубликованы и продавец не заблокирован."""
    return Product.objects.filter(status=Product.Status.PUBLISHED, seller__status="active")


def _to_decimal(value):
    try:
        return Decimal(str(value).replace(",", ".").replace(" ", "")) if value not in (None, "") else None
    except InvalidOperation:
        return None


def search_catalog(params):
    """Отфильтровать и отсортировать каталог по GET-параметрам.

    Параметры: q, section, category, price_min, price_max, tech (несколько),
    platform (несколько), rating, sort. Возвращает (queryset, применённые фильтры).
    """
    qs = visible_products()
    applied = {}

    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q))
        applied["q"] = q

    section = params.get("section")
    category = params.get("category")
    if category:
        qs = qs.filter(category__slug=category)
        applied["category"] = category
    elif section:
        qs = qs.filter(Q(category__parent__slug=section) | Q(category__slug=section))
        applied["section"] = section

    pmin, pmax = _to_decimal(params.get("price_min")), _to_decimal(params.get("price_max"))
    if pmin is not None:
        qs = qs.filter(price__gte=pmin)
        applied["price_min"] = pmin
    if pmax is not None:
        qs = qs.filter(price__lte=pmax)
        applied["price_max"] = pmax

    techs = [t for t in params.getlist("tech") if t] if hasattr(params, "getlist") else []
    for t in techs:  # все выбранные технологии должны быть у продукта
        qs = qs.filter(technologies__slug=t)
    if techs:
        applied["tech"] = techs

    platforms = [p for p in params.getlist("platform") if p] if hasattr(params, "getlist") else []
    if platforms:  # совместим хотя бы с одной из выбранных платформ
        qs = qs.filter(platforms__slug__in=platforms)
        applied["platform"] = platforms

    rating = _to_decimal(params.get("rating"))
    if rating:
        qs = qs.filter(rating_avg__gte=rating)
        applied["rating"] = rating

    if platforms or len(techs) > 1:
        qs = qs.distinct()

    sort = params.get("sort") if params.get("sort") in SORTS else "new"
    qs = qs.order_by(*SORTS[sort][1])
    qs = qs.select_related("category", "category__parent", "seller").prefetch_related(
        "technologies", Prefetch("screenshots", queryset=Screenshot.objects.order_by("position", "id"))
    )
    return qs, applied, sort


def catalog_sidebar():
    """Разделы с подкатегориями и числом продуктов, технологии, платформы."""
    counts = dict(
        visible_products()
        .values_list("category__parent_id")
        .annotate(n=Count("id"))
        .values_list("category__parent_id", "n")
    )
    sections = list(
        Category.objects.filter(parent__isnull=True).prefetch_related(
            Prefetch("children", queryset=Category.objects.order_by("position", "name"))
        )
    )
    for s in sections:
        s.product_count = counts.get(s.id, 0)
    return {
        "sections": sections,
        "technologies": Technology.objects.all(),
        "platforms": Platform.objects.all(),
    }


def get_public_product(slug, user=None):
    """Продукт для страницы продукта. Неопубликованный видят только владелец и админ."""
    product = (
        Product.objects.select_related("category", "category__parent", "seller")
        .prefetch_related("technologies", "platforms", "screenshots")
        .filter(slug=slug)
        .first()
    )
    if product is None:
        return None
    visible = product.status == Product.Status.PUBLISHED and product.seller.status == "active"
    if visible or (user and user.is_authenticated and (user.is_staff or user.id == product.seller_id)):
        return product
    if user and user.is_authenticated and product.status in (Product.Status.HIDDEN, Product.Status.BLOCKED):
        # купившие продолжают видеть страницу снятого продукта
        from apps.purchases.services import has_access

        if has_access(user, product):
            return product
    return None


def record_view(product, request):
    """Записать просмотр: не чаще одного на сессию в сутки, свои просмотры не считаются."""
    if request.user.is_authenticated and request.user.id == product.seller_id:
        return False
    if not request.session.session_key:
        request.session.save()
    key = request.session.session_key
    since = timezone.now() - timedelta(days=1)
    if ProductView.objects.filter(product=product, session_key=key, viewed_at__gte=since).exists():
        return False
    ProductView.objects.create(
        product=product, session_key=key, user=request.user if request.user.is_authenticated else None
    )
    return True


# ---------------------------------------------------------------- продукты продавца


def unique_slug(title, exclude_id=None):
    base = _translit(title) or "product"
    base = base[:120]
    slug, n = base, 2
    while Product.objects.filter(slug=slug).exclude(pk=exclude_id).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


_TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip


def _translit(text):
    """Транслитерация русского названия для адреса продукта."""
    return slugify("".join(_TR.get(ch, ch) for ch in text.lower()))


@transaction.atomic
def create_product(seller, *, data, technologies=(), platforms=()):
    """Создать черновик продукта. Требует подключённый GitHub и принятые условия продавца."""
    if not seller.is_seller:
        raise ServiceError("Сначала подключите GitHub.")
    if seller.seller_terms_accepted_at is None:
        raise ServiceError("Нужно принять условия для продавцов.")
    product = Product(seller=seller, status=Product.Status.DRAFT, **data)
    product.slug = unique_slug(product.title)
    product.full_clean(exclude=["slug"])
    product.save()
    product.technologies.set(technologies)
    product.platforms.set(platforms)
    return product


@transaction.atomic
def update_product(product, user, *, data, technologies=None, platforms=None):
    """Изменить описание, цену, категории продукта."""
    _check_owner(product, user)
    for k, v in data.items():
        setattr(product, k, v)
    product.full_clean()
    product.save()
    if technologies is not None:
        product.technologies.set(technologies)
    if platforms is not None:
        product.platforms.set(platforms)
    return product


def validate_screenshot(f):
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext not in SCREENSHOT_EXTENSIONS:
        raise ValidationError("Допустимы только jpg, png и webp.")
    if f.size > SCREENSHOT_MAX_BYTES:
        raise ValidationError("Файл больше 3 МБ.")


def add_screenshots(product, user, files):
    """Добавить скриншоты (не больше 8, jpg/png/webp, до 3 МБ)."""
    _check_owner(product, user)
    existing = product.screenshots.count()
    if existing + len(files) > MAX_SCREENSHOTS:
        raise ServiceError(f"Можно загрузить не больше {MAX_SCREENSHOTS} скриншотов.")
    created = []
    for i, f in enumerate(files):
        validate_screenshot(f)
        created.append(Screenshot.objects.create(product=product, image=f, position=existing + i))
    return created


def delete_screenshot(product, user, screenshot_id):
    _check_owner(product, user)
    shot = product.screenshots.get(pk=screenshot_id)
    shot.image.delete(save=False)
    shot.delete()


@transaction.atomic
def delete_product(product, user):
    """Удалить продукт. Нельзя, если у него есть покупки — только снять с продажи."""
    _check_owner(product, user)
    from apps.purchases.services import product_has_purchases

    if product_has_purchases(product):
        raise ServiceError("У продукта есть покупки: его можно только снять с продажи.")
    for shot in product.screenshots.all():
        shot.image.delete(save=False)
    product.delete()


def increment_sales(product):
    """Увеличить счётчик продаж (вызывает модуль покупок)."""
    Product.objects.filter(pk=product.pk).update(sales_count=F("sales_count") + 1)


def set_rating(product_id, avg, count):
    """Сохранить пересчитанный рейтинг (вызывает модуль отзывов)."""
    Product.objects.filter(pk=product_id).update(rating_avg=avg, rating_count=count)


def set_mirror_repo(product, full_name):
    """Запомнить репозиторий-копию (вызывает модуль версий)."""
    if product.mirror_repo_full_name != full_name:
        product.mirror_repo_full_name = full_name
        product.save(update_fields=["mirror_repo_full_name"])


def hide_seller_products_for_block(seller):
    """Ничего не меняет в статусах: каталог сам скрывает продукты заблокированных продавцов."""
    return visible_products().filter(seller=seller).count()


def commission_rate():
    return settings.PLATFORM_COMMISSION

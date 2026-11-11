from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

PRODUCT_MIN_PRICE = 100
PRODUCT_MAX_PRICE = 500_000


class Category(models.Model):
    """Раздел (parent пустой) или подкатегория (parent = раздел)."""

    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children", verbose_name="раздел"
    )
    name = models.CharField("название", max_length=80)
    slug = models.SlugField(unique=True, max_length=80)
    position = models.PositiveSmallIntegerField("порядок", default=0)
    icon = models.CharField("иконка Bootstrap", max_length=40, blank=True, help_text="Например, bi-window")

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "раздел / подкатегория"
        verbose_name_plural = "разделы и подкатегории"

    def __str__(self):
        return f"{self.parent.name} / {self.name}" if self.parent_id else self.name

    @property
    def is_section(self):
        return self.parent_id is None


class Technology(models.Model):
    name = models.CharField("название", max_length=50, unique=True)
    slug = models.SlugField(unique=True, max_length=50)

    class Meta:
        ordering = ["name"]
        verbose_name = "технология"
        verbose_name_plural = "технологии"

    def __str__(self):
        return self.name


class Platform(models.Model):
    name = models.CharField("название", max_length=50, unique=True)
    slug = models.SlugField(unique=True, max_length=50)

    class Meta:
        ordering = ["name"]
        verbose_name = "платформа"
        verbose_name_plural = "платформы"

    def __str__(self):
        return self.name


class Product(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        CHECKING = "checking", "Проверяется"
        MODERATION = "moderation", "На модерации"
        PUBLISHED = "published", "Опубликован"
        REJECTED = "rejected", "Отклонён"
        HIDDEN = "hidden", "Снят с продажи"
        BLOCKED = "blocked", "Заблокирован"

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="products", verbose_name="продавец"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", verbose_name="подкатегория"
    )
    title = models.CharField("название", max_length=120)
    slug = models.SlugField("адрес", unique=True, max_length=140)
    short_description = models.CharField("краткое описание", max_length=200)
    description = models.TextField("описание")
    price = models.DecimalField(
        "цена, ₽",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(PRODUCT_MIN_PRICE), MaxValueValidator(PRODUCT_MAX_PRICE)],
    )
    demo_url = models.URLField("ссылка на демо", blank=True)
    source_repo_full_name = models.CharField("репозиторий продавца", max_length=200, blank=True)
    source_repo_id = models.BigIntegerField(null=True, blank=True)
    mirror_repo_full_name = models.CharField("репозиторий-копия", max_length=200, blank=True)
    status = models.CharField("статус", max_length=12, choices=Status.choices, default=Status.DRAFT)
    rating_avg = models.DecimalField("рейтинг", max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField("число отзывов", default=0)
    sales_count = models.PositiveIntegerField("продажи", default=0)
    technologies = models.ManyToManyField(Technology, blank=True, related_name="products", verbose_name="технологии")
    platforms = models.ManyToManyField(Platform, blank=True, related_name="products", verbose_name="платформы")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "продукт"
        verbose_name_plural = "продукты"
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=PRODUCT_MIN_PRICE) & Q(price__lte=PRODUCT_MAX_PRICE),
                name="product_price_range",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-published_at"]),
            models.Index(fields=["status", "price"]),
            models.Index(fields=["status", "-rating_avg"]),
            models.Index(fields=["status", "-sales_count"]),
        ]

    def __str__(self):
        return self.title

    @property
    def section(self):
        return self.category.parent or self.category

    @property
    def cover(self):
        shots = getattr(self, "_prefetched_objects_cache", {}).get("screenshots")
        if shots is not None:
            return shots[0] if shots else None
        return self.screenshots.first()


def screenshot_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"screenshots/{instance.product_id}/{instance.position}_{instance.product_id}.{ext}"


class Screenshot(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="screenshots")
    image = models.ImageField("изображение", upload_to=screenshot_upload_to)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "скриншот"
        verbose_name_plural = "скриншоты"

    def __str__(self):
        return f"Скриншот {self.position} продукта {self.product_id}"


class ProductView(models.Model):
    """Просмотр карточки: не чаще одной записи на сессию в сутки."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    session_key = models.CharField(max_length=40)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["product", "viewed_at"]), models.Index(fields=["session_key", "product"])]
        verbose_name = "просмотр"
        verbose_name_plural = "просмотры"

    def __str__(self):
        return f"Просмотр {self.product_id} {self.viewed_at:%d.%m.%Y}"

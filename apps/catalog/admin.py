from django.contrib import admin

from .models import Category, Platform, Product, Screenshot, Technology


class SubcategoryInline(admin.TabularInline):
    model = Category
    fk_name = "parent"
    extra = 1
    fields = ["name", "slug", "position"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "slug", "position"]
    list_filter = ["parent"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [SubcategoryInline]


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


class ScreenshotInline(admin.TabularInline):
    model = Screenshot
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Аварийные правки. Обычные действия идут через страницы модерации."""

    list_display = ["title", "seller", "category", "price", "status", "sales_count", "rating_avg", "published_at"]
    list_filter = ["status", "category__parent"]
    search_fields = ["title", "slug", "seller__username"]
    raw_id_fields = ["seller"]
    filter_horizontal = ["technologies", "platforms"]
    inlines = [ScreenshotInline]

from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render

from apps.orders import services as order_services
from apps.purchases import services as purchase_services
from apps.reviews import services as review_services
from apps.versions import services as version_services

from . import services
from .models import Category, Product


def index(request):
    """Главная = каталог с поиском, фильтрами, сортировкой и пагинацией."""
    qs, applied, sort = services.search_catalog(request.GET)
    page = Paginator(qs, services.PAGE_SIZE).get_page(request.GET.get("page"))
    sidebar = services.catalog_sidebar()
    current_section = None
    if applied.get("section"):
        current_section = Category.objects.filter(slug=applied["section"], parent__isnull=True).first()
    elif applied.get("category"):
        cat = Category.objects.filter(slug=applied["category"]).select_related("parent").first()
        current_section = cat.parent if cat else None
    return render(
        request,
        "catalog/index.html",
        {
            "page_obj": page,
            "products": page.object_list,
            "total": page.paginator.count,
            "applied": applied,
            "sort": sort,
            "sorts": [(k, v[0]) for k, v in services.SORTS.items()],
            "selected_tech": request.GET.getlist("tech"),
            "selected_platform": request.GET.getlist("platform"),
            "current_section": current_section,
            "has_filters": bool(applied),
            **sidebar,
        },
    )


def product_detail(request, slug):
    product = services.get_public_product(slug, request.user)
    if product is None:
        raise Http404("Продукт не найден")
    if product.status == Product.Status.PUBLISHED:
        services.record_view(product, request)
    user = request.user
    purchase = purchase_services.active_purchase(user, product) if user.is_authenticated else None
    product_reviews, order_reviews = review_services.product_reviews(product)
    seller_avg, seller_count = review_services.seller_rating(product.seller)
    return render(
        request,
        "catalog/product_detail.html",
        {
            "product": product,
            "screenshots": list(product.screenshots.all()),
            "is_owner": user.is_authenticated and user.id == product.seller_id,
            "purchase": purchase,
            "versions": version_services.approved_versions(product),
            "current_version": version_services.current_version(product),
            "product_reviews": product_reviews,
            "order_reviews": order_reviews,
            "reviews_total": len(product_reviews) + len(order_reviews),
            "questions": order_services.public_questions(product),
            "seller_avg": seller_avg,
            "seller_count": seller_count,
            "seller_sales": sum(Product.objects.filter(seller=product.seller).values_list("sales_count", flat=True)),
        },
    )

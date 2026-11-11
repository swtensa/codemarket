from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalog.models import Product
from apps.core.exceptions import ServiceError
from apps.integrations.github import get_client
from apps.versions import services as version_services

from . import services
from .models import Purchase


@login_required
def buy(request, slug):
    """GET — страница подтверждения покупки, POST — создать покупку и перейти к оплате."""
    product = get_object_or_404(Product.objects.select_related("seller", "category"), slug=slug)
    existing = services.active_purchase(request.user, product)
    if existing:
        return redirect("me:purchase", pk=existing.pk)
    try:
        services.check_can_buy(request.user, product)
    except ServiceError as e:
        messages.error(request, str(e))
        return redirect("catalog:product", slug=slug)
    if request.method == "POST":
        try:
            _, url = services.start_purchase(
                request.user,
                product,
                github_login=request.POST.get("github_login", ""),
                accept_license=bool(request.POST.get("accept_license")),
            )
            return redirect(url)
        except ServiceError as e:
            messages.error(request, str(e))
    return render(
        request,
        "purchases/confirm.html",
        {"product": product, "version": version_services.current_version(product)},
    )


@login_required
def purchase_list(request):
    page = Paginator(services.user_purchases(request.user), 20).get_page(request.GET.get("page"))
    return render(request, "purchases/list.html", {"page_obj": page, "tab": "purchases"})


def _get(request, pk):
    try:
        return services.get_purchase_for(request.user, pk)
    except Purchase.DoesNotExist:
        raise Http404
    except PermissionError:
        raise PermissionDenied


@login_required
def purchase_detail(request, pk):
    purchase = _get(request, pk)
    if request.method == "POST" and request.POST.get("action") == "access":
        login = request.POST.get("github_login", "").strip()
        try:
            if login:
                from apps.accounts.services import set_github_login

                set_github_login(request.user, login)
                purchase.buyer.refresh_from_db()
            services.grant_access(purchase)
            messages.success(request, "Приглашение в репозиторий отправлено. Примите его на GitHub.")
        except ServiceError as e:
            messages.error(request, str(e))
        return redirect("me:purchase", pk=pk)
    if purchase.access_status == Purchase.Access.INVITED:
        services.refresh_access_status(purchase)
    versions = version_services.approved_versions(purchase.product)
    from apps.orders.services import orders_for_purchase
    from apps.reviews.services import review_for_purchase

    return render(
        request,
        "purchases/detail.html",
        {
            "purchase": purchase,
            "product": purchase.product,
            "versions": versions,
            "can_download": services.can_download(request.user, purchase) and bool(versions),
            "mirror_url": get_client().mirror_url(purchase.product.mirror_repo_full_name)
            if purchase.product.mirror_repo_full_name
            else "",
            "dispute_days_left": services.dispute_days_left(purchase),
            "review": review_for_purchase(purchase),
            "orders": orders_for_purchase(purchase),
            "tab": "purchases",
        },
    )


@login_required
def download(request, pk):
    """Скачать ZIP одобренной версии: только через проверку права, не прямой ссылкой."""
    purchase = _get(request, pk)
    try:
        version = services.download_version(request.user, purchase)
    except PermissionError:
        raise PermissionDenied
    except ServiceError as e:
        messages.error(request, str(e))
        return redirect("me:purchase", pk=pk)
    return FileResponse(
        version.archive.open("rb"),
        as_attachment=True,
        filename=f"{purchase.product.slug}-{version.tag_name}.zip",
        content_type="application/zip",
    )

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalog.models import Product
from apps.catalog.sell_views import seller_required
from apps.core.exceptions import InvalidTransition, ServiceError

from . import services
from .models import ProductVersion


@seller_required
def versions(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    items = list(services.product_versions(product))
    from apps.plagiarism.services import matches_for_versions

    matches = matches_for_versions([v for v in items if v.status == "rejected_auto"])
    for v in items:
        v.match_list = matches.get(v.id, [])
    releases, release_error = [], None
    try:
        releases = services.available_releases(product, request.user)
    except ServiceError as e:
        release_error = str(e)
    return render(
        request,
        "sell/versions.html",
        {"product": product, "versions": items, "releases": releases, "release_error": release_error},
    )


@seller_required
def import_release(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    if request.method == "POST":
        try:
            v = services.import_release(product, request.user, request.POST.get("tag", ""))
            messages.success(request, f"Релиз {v.tag_name} получен и отправлен на проверку на заимствования.")
        except ServiceError as e:
            messages.error(request, str(e))
    return redirect("sell:versions", pk=pk)


@seller_required
def appeal(request, vid):
    version = get_object_or_404(ProductVersion, pk=vid, product__seller=request.user)
    if request.method == "POST":
        try:
            services.appeal_version(version, request.user, request.POST.get("appeal_text", ""))
            messages.success(request, "Обжалование отправлено модератору.")
        except (ServiceError, InvalidTransition) as e:
            messages.error(request, str(e))
    return redirect("sell:versions", pk=version.product_id)

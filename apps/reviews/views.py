from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.exceptions import ServiceError
from apps.orders.models import CustomOrder
from apps.purchases.models import Purchase

from . import services


@login_required
def new_review(request):
    """Оставить отзыв о продукте (?purchase=) или о доработке (?order=)."""
    purchase = order = None
    if request.GET.get("purchase"):
        purchase = get_object_or_404(
            Purchase.objects.select_related("product"), pk=request.GET["purchase"], buyer=request.user
        )
        product, back = purchase.product, f"/me/purchases/{purchase.pk}/"
    else:
        order = get_object_or_404(
            CustomOrder.objects.select_related("product"), pk=request.GET.get("order") or 0, buyer=request.user
        )
        product, back = order.product, f"/orders/{order.pk}/"
    if request.method == "POST":
        try:
            data = {"rating": request.POST.get("rating"), "text": request.POST.get("text", "")}
            if purchase:
                services.create_purchase_review(request.user, purchase, **data)
            else:
                services.create_order_review(request.user, order, **data)
            messages.success(request, "Спасибо за отзыв!")
            return redirect(back)
        except ServiceError as e:
            messages.error(request, str(e))
    return render(request, "reviews/new.html", {"product": product, "purchase": purchase, "order": order, "back": back})

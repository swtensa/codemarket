from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.exceptions import InvalidTransition, ServiceError
from apps.moderation.views import mod_render, staff_required
from apps.orders.models import CustomOrder
from apps.purchases.models import Purchase
from apps.purchases.services import dispute_days_left

from . import services
from .models import Dispute


@login_required
def new_dispute(request):
    """Открыть спор по покупке (?purchase=) или по заказу (?order=)."""
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
            kwargs = {"reason_type": request.POST.get("reason_type", ""), "reason": request.POST.get("reason", "")}
            if purchase:
                services.open_purchase_dispute(request.user, purchase, **kwargs)
            else:
                services.open_order_dispute(request.user, order, **kwargs)
            messages.success(request, "Спор открыт. Администратор рассмотрит его и сообщит решение.")
            return redirect(back)
        except (ServiceError, InvalidTransition) as e:
            messages.error(request, str(e))
    return render(
        request,
        "disputes/new.html",
        {
            "purchase": purchase,
            "order": order,
            "product": product,
            "back": back,
            "reasons": [(r, Dispute.ReasonType(r).label) for r in services.BUYER_REASONS],
            "days_left": dispute_days_left(purchase) if purchase else None,
        },
    )


@staff_required
def admin_list(request):
    status = request.GET.get("status", "open")
    qs = Dispute.objects.select_related("purchase__product", "order__product", "opened_by")
    if status in ("open", "closed"):
        qs = qs.filter(status=status)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return mod_render(request, "moderation/disputes.html", {"page_obj": page, "status": status}, "disputes")


@staff_required
def admin_detail(request, pk):
    dispute = get_object_or_404(
        Dispute.objects.select_related(
            "purchase__product__seller", "purchase__buyer", "order__product__seller", "order__buyer", "opened_by"
        ),
        pk=pk,
    )
    if request.method == "POST":
        try:
            services.resolve(
                dispute,
                request.user,
                resolution=request.POST.get("resolution", ""),
                refund_amount=request.POST.get("refund_amount"),
                comment=request.POST.get("comment", ""),
            )
            messages.success(request, "Решение по спору сохранено, стороны уведомлены.")
            return redirect("moderation:disputes")
        except (ServiceError, InvalidTransition) as e:
            messages.error(request, str(e))
    return mod_render(request, "moderation/dispute.html", services.dispute_context(dispute), "disputes")

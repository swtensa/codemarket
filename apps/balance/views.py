from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from apps.core.exceptions import InvalidTransition, ServiceError
from apps.moderation.views import mod_render, staff_required

from . import services
from .models import BalanceOperation


@login_required
def index(request):
    """Баланс продавца: удержано, доступно, выведено; операции; заявка на вывод."""
    if request.method == "POST":
        try:
            services.request_payout(request.user, request.POST.get("amount", ""), request.POST.get("requisites", ""))
            messages.success(request, "Заявка на вывод создана. Администратор обработает её в ближайшее время.")
            return redirect("balance:index")
        except ServiceError as e:
            messages.error(request, str(e))
    kind = request.GET.get("kind", "")
    page = Paginator(services.operations(request.user, kind), 20).get_page(request.GET.get("page"))
    return render(
        request,
        "balance/index.html",
        {
            "balance": services.get_balance(request.user),
            "page_obj": page,
            "kind": kind,
            "kinds": [(k, BalanceOperation.Kind(k).label) for k in services.SELLER_KINDS],
            "min_payout": services.settings.MIN_PAYOUT,
            "sell_tab": "balance",
        },
    )


@staff_required
def payouts(request):
    """Заявки на вывод для администратора: «Выплачено» или «Отклонено»."""
    if request.method == "POST":
        try:
            op_id = int(request.POST.get("op", 0))
            if request.POST.get("action") == "paid":
                services.mark_payout_paid(op_id, request.user)
                messages.success(request, "Заявка отмечена выплаченной.")
            else:
                services.reject_payout(op_id, request.user, request.POST.get("reason", ""))
                messages.success(request, "Заявка отклонена, деньги вернулись продавцу в доступные.")
        except (InvalidTransition, BalanceOperation.DoesNotExist, ValueError) as e:
            messages.error(request, str(e) or "Заявка не найдена")
        return redirect("moderation:payouts")
    history = BalanceOperation.objects.filter(kind="payout").exclude(status="requested").select_related("user")
    return mod_render(
        request,
        "moderation/payouts.html",
        {"requested": services.requested_payouts(), "history": history[:30]},
        "payouts",
    )

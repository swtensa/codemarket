import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services
from .models import Payment
from .providers import FakeProvider

hook_log = logging.getLogger("codemarket.webhooks")


@csrf_exempt
@require_POST
def webhook(request):
    """Вебхук ЮKassa. Тело уведомления не считается доказательством оплаты: статус перепроверяется запросом."""
    try:
        data = json.loads(request.body)
        external_id = data["object"]["id"]
    except (ValueError, KeyError, TypeError):
        hook_log.warning("Вебхук ЮKassa: неверное тело")
        return HttpResponseBadRequest()
    hook_log.info("Вебхук ЮKassa %s %s", data.get("event"), external_id)
    services.handle_notification(external_id)
    return HttpResponse("ok")


def _target_url(payment):
    if payment.order_id:
        return f"/orders/{payment.order_id}/"
    return f"/me/purchases/{payment.purchase_id}/"


def _owner_id(payment):
    return payment.order.buyer_id if payment.order_id else payment.purchase.buyer_id


@login_required
def payment_return(request, pk):
    """Возврат покупателя со страницы оплаты: проверить статус и показать результат."""
    payment = get_object_or_404(Payment.objects.select_related("purchase", "order"), pk=pk)
    if _owner_id(payment) != request.user.id:
        raise Http404
    services.refresh_payment(payment)
    if payment.status == Payment.Status.SUCCEEDED:
        messages.success(request, "Оплата прошла.")
    elif payment.status == Payment.Status.CANCELED:
        messages.error(request, "Оплата отклонена.")
    else:
        messages.info(request, "Платёж ещё обрабатывается, обновите страницу через минуту.")
    return redirect(_target_url(payment))


@login_required
def fake_checkout(request, external_id):
    """Страница-заглушка платёжной системы (только PAYMENT_PROVIDER=fake)."""
    if settings.PAYMENT_PROVIDER != "fake":
        raise Http404
    provider = FakeProvider()
    data = provider.get(external_id)
    payment = Payment.objects.select_related("purchase", "order").filter(external_id=external_id).first()
    if data is None or payment is None or _owner_id(payment) != request.user.id:
        raise Http404
    if request.method == "POST":
        provider.set_status(external_id, "succeeded" if request.POST.get("action") == "pay" else "canceled")
        services.handle_notification(external_id)  # тот же обработчик, что у вебхука
        return redirect("payments:return", pk=payment.pk)
    return render(request, "payments/fake_checkout.html", {"data": data, "payment": payment})

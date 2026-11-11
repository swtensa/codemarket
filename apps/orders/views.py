from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.exceptions import InvalidTransition, ServiceError
from apps.purchases.models import Purchase

from . import services
from .models import CustomOrder, Message

STEPS = [
    ("new", "Новый"),
    ("offer", "Предложение"),
    ("awaiting_payment", "Оплата"),
    ("in_work", "В работе"),
    ("submitted", "Сдан"),
    ("accepted", "Принят"),
]
STEP_INDEX = {"new": 0, "offer": 1, "awaiting_payment": 2, "in_work": 3, "revision": 3, "submitted": 4, "accepted": 5}


@login_required
def new_order(request):
    """Создание заказа: «Задать вопрос», «Купить с доработкой» (со страницы продукта) или «Заказать доработку»."""
    purchase = None
    if request.GET.get("purchase"):
        purchase = get_object_or_404(Purchase, pk=request.GET["purchase"], buyer=request.user)
        product, kind = purchase.product, CustomOrder.Kind.CUSTOMIZATION
    else:
        product = get_object_or_404(Product.objects.select_related("seller"), slug=request.GET.get("product", ""))
        kind = request.GET.get("kind")
        if kind not in (CustomOrder.Kind.QUESTION, CustomOrder.Kind.WITH_PURCHASE):
            kind = CustomOrder.Kind.QUESTION
    if request.method == "POST":
        try:
            order = services.create_order(
                request.user, product, kind=kind, task=request.POST.get("task", ""), purchase=purchase
            )
            messages.success(request, "Вопрос отправлен продавцу." if kind == "question" else "Заказ создан.")
            return redirect("orders:detail", pk=order.pk)
        except ServiceError as e:
            messages.error(request, str(e))
    return render(request, "orders/new.html", {"product": product, "kind": kind, "purchase": purchase})


def _get(request, pk):
    try:
        return services.get_order_for(request.user, pk)
    except CustomOrder.DoesNotExist:
        raise Http404
    except PermissionError:
        raise PermissionDenied


@login_required
def order_detail(request, pk):
    order = _get(request, pk)
    if request.method == "POST":
        return _action(request, order)
    msgs = services.messages_after(order, request.user, 0)
    acts = services.allowed_actions(order, request.user)
    is_seller = order.product.seller_id == request.user.id
    step = STEP_INDEX.get(order.status)
    deadline_left = None
    if order.deadline and order.status in ("in_work", "revision"):
        deadline_left = order.deadline - timezone.now()
    return render(
        request,
        "orders/detail.html",
        {
            "order": order,
            "chat": msgs,
            "last_id": msgs[-1].id if msgs else 0,
            "actions": acts,
            "is_seller": is_seller,
            "is_buyer": order.buyer_id == request.user.id,
            "steps": [(code, label, i < (step or 0), i == step) for i, (code, label) in enumerate(STEPS)],
            "payment_amount": services.payment_amount(order) if order.price else None,
            "includes_product": services.includes_product(order),
            "deadline_left": deadline_left,
            "overdue": deadline_left is not None and deadline_left.total_seconds() < 0,
            "can_write": (order.buyer_id == request.user.id or is_seller) and order.status != "cancelled",
            "can_mark_result": is_seller and order.status in ("in_work", "revision"),
            "dispute": order.disputes.first(),
            "tab": "orders",
        },
    )


def _action(request, order):
    action = request.POST.get("action")
    user = request.user
    try:
        if action == "message":
            services.post_message(
                order,
                user,
                text=request.POST.get("text", ""),
                attachment=request.FILES.get("attachment"),
                is_result=bool(request.POST.get("is_result")),
            )
        elif action == "mark_result":
            services.mark_result(order, user, int(request.POST.get("message_id", 0)))
            messages.success(request, "Сообщение отмечено как результат.")
        elif action == "offer":
            services.make_offer(order, user, price=request.POST.get("price"), days=request.POST.get("days"))
            messages.success(request, "Предложение отправлено покупателю.")
        elif action == "accept_offer":
            return redirect(services.accept_offer(order, user))
        elif action == "pay":
            return redirect(services.payment_url(order, user))
        elif action == "cancel":
            services.cancel_order(order, user)
            messages.success(request, "Заказ отменён.")
        elif action == "submit":
            services.submit_result(order, user)
            messages.success(request, "Работа сдана покупателю.")
        elif action == "refuse":
            services.seller_refuse(order, user, request.POST.get("reason", ""))
            messages.success(request, "Вы отказались от заказа, покупателю будет возвращена оплата.")
        elif action == "accept":
            services.accept_result(order, user)
            messages.success(request, "Работа принята. Спасибо!")
        elif action == "revision":
            services.request_revision(order, user, request.POST.get("comment", ""))
            messages.success(request, "Заказ возвращён на доработку.")
        elif action == "cancel_overdue":
            services.cancel_overdue(order, user)
            messages.success(request, "Заказ отменён, оплата будет возвращена.")
    except (ServiceError, InvalidTransition, Message.DoesNotExist, ValueError) as e:
        messages.error(request, str(e) or "Действие недоступно")
    return redirect("orders:detail", pk=order.pk)


@login_required
def poll_messages(request, pk):
    """JSON для опроса раз в 10 секунд: новые сообщения после after."""
    order = _get(request, pk)
    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        after = 0
    msgs = services.messages_after(order, request.user, after)
    html = render_to_string("orders/_messages.html", {"chat": msgs, "user": request.user, "order": order})
    return JsonResponse({"html": html, "last_id": msgs[-1].id if msgs else after, "status": order.status})


@login_required
def attachment(request, message_id):
    """Скачать вложение: только участники заказа и администратор."""
    try:
        msg = services.attachment_for(request.user, message_id)
    except Message.DoesNotExist:
        raise Http404
    except PermissionError:
        raise PermissionDenied
    return FileResponse(msg.attachment.open("rb"), as_attachment=True, filename=msg.attachment_name)


@login_required
def buyer_list(request):
    page = Paginator(services.buyer_orders(request.user), 20).get_page(request.GET.get("page"))
    return render(request, "orders/buyer_list.html", {"page_obj": page, "tab": "orders"})


@login_required
def seller_list(request):
    qs = services.seller_orders(request.user)
    if request.GET.get("kind") == "question":
        qs = qs.filter(kind="question")
    elif request.GET.get("kind") == "orders":
        qs = qs.exclude(kind="question")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "orders/seller_list.html", {"page_obj": page, "sell_tab": "orders"})

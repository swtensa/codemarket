from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from . import services
from .models import Notification


@login_required
def notification_list(request):
    if request.method == "POST":
        n = services.mark_all_read(request.user)
        messages.success(request, f"Отмечено прочитанными: {n}")
        return redirect("notifications:list")
    page = Paginator(Notification.objects.filter(user=request.user), 20).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {"page_obj": page, "tab": "notifications"})


@login_required
def open_notification(request, pk):
    try:
        link = services.open_notification(request.user, pk)
    except Notification.DoesNotExist:
        raise Http404
    if not url_has_allowed_host_and_scheme(link, allowed_hosts={request.get_host()}):
        link = "/notifications/"
    return redirect(link)

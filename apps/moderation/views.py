"""Свои страницы администратора: модерация версий, пользователи (споры, выплаты и отчёты — в своих модулях)."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts import services as account_services
from apps.accounts.models import User
from apps.core.exceptions import InvalidTransition, ServiceError
from apps.plagiarism.services import matches_for_versions
from apps.versions import services as version_services
from apps.versions.models import ProductVersion

from . import services


def staff_required(view):
    """Только для администраторов (is_staff). Остальным — 403."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def mod_render(request, template, ctx, section):
    ctx.update(mod_section=section, mod_counts=services.menu_counts())
    return render(request, template, ctx)


@staff_required
def queue(request):
    items = list(version_services.pending_versions())
    matches = matches_for_versions(items)
    for v in items:
        v.match_list = matches.get(v.id, [])
    return mod_render(request, "moderation/queue.html", {"versions": items}, "versions")


@staff_required
def version_detail(request, pk):
    version = get_object_or_404(
        ProductVersion.objects.select_related("product", "product__seller", "product__category"), pk=pk
    )
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "approve":
                version_services.approve_version(version, request.user)
                messages.success(request, f"Версия {version.tag_name} одобрена и опубликована в репозиторий-копию.")
            elif action == "reject":
                version_services.reject_version(version, request.user, request.POST.get("comment", ""))
                messages.success(request, f"Версия {version.tag_name} отклонена.")
            return redirect("moderation:queue")
        except (ServiceError, InvalidTransition) as e:
            messages.error(request, str(e))
            return redirect("moderation:version", pk=pk)
    tree = services.file_tree(version)
    current = request.GET.get("file")
    if not current:
        current = next((p for _, _, p in tree if p), None)
    code_html, code_error = services.render_file(version, current) if current else (None, None)
    matches = matches_for_versions([version]).get(version.id, [])
    return mod_render(
        request,
        "moderation/version.html",
        {
            "version": version,
            "product": version.product,
            "tree": tree,
            "current_file": current,
            "code_html": code_html,
            "code_error": code_error,
            "highlight_css": services.highlight_css(),
            "matches": matches,
            "can_decide": version.status in ("moderation", "appeal"),
        },
        "versions",
    )


@staff_required
def users(request):
    q = request.GET.get("q", "").strip()
    qs = User.objects.all().order_by("-created_at")
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(username__icontains=q))
    if request.GET.get("status") in ("active", "blocked"):
        qs = qs.filter(status=request.GET["status"])
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return mod_render(request, "moderation/users.html", {"page_obj": page, "q": q}, "users")


@staff_required
def user_action(request, pk):
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        try:
            if request.POST.get("action") == "block":
                account_services.block_user(target, reason=request.POST.get("reason", ""), admin=request.user)
                messages.success(request, f"Пользователь {target.username} заблокирован.")
            elif request.POST.get("action") == "unblock":
                account_services.unblock_user(target, admin=request.user)
                messages.success(request, f"Пользователь {target.username} разблокирован.")
        except ServiceError as e:
            messages.error(request, str(e))
    nxt = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = ""
    return redirect(nxt or "moderation:users")

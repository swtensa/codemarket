"""Кабинет продавца: продукты, мастер создания, редактирование, скриншоты."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts import services as account_services
from apps.core.exceptions import InvalidTransition, ServiceError
from apps.integrations.github import get_client
from apps.integrations.github.base import GitHubError
from apps.reports import services as report_services

from . import services
from .forms import CategoryStepForm, InfoStepForm, ProductEditForm, RepoStepForm, ScreenshotsForm
from .models import Product

WIZARD_KEY = "product_wizard"


def seller_required(view):
    """Только для вошедших пользователей с подключённым GitHub."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_seller:
            messages.info(request, "Чтобы продавать, подключите GitHub.")
            return redirect("sell:dashboard")
        return view(request, *args, **kwargs)

    return wrapper


def _own_product(request, pk):
    return get_object_or_404(Product.objects.select_related("category"), pk=pk, seller=request.user)


@login_required
def dashboard(request):
    user = request.user
    products = (
        Product.objects.filter(seller=user).select_related("category").prefetch_related("screenshots")
        if user.is_seller
        else Product.objects.none()
    )
    return render(
        request,
        "sell/dashboard.html",
        {"products": products, "tiles": report_services.seller_tiles(user) if user.is_seller else None},
    )


@seller_required
def product_new(request):
    """Мастер создания продукта: 1) репозиторий, 2) описание и цена, 3) категории; шаг 4 — скриншоты и релиз."""
    step = request.GET.get("step", "1")
    data = request.session.get(WIZARD_KEY, {})
    user = request.user
    if step == "1":
        try:
            repos = get_client().list_repositories(user.github_installation_id)
        except GitHubError as e:
            messages.error(request, str(e))
            repos = []
        form = RepoStepForm(
            request.POST or None,
            repos=repos,
            need_terms=user.seller_terms_accepted_at is None,
            initial={"repo": data.get("repo")},
        )
        if request.method == "POST" and form.is_valid():
            if form.need_terms:
                account_services.accept_seller_terms(user)
            repo = form.repos[form.cleaned_data["repo"]]
            data.update(repo=repo.full_name, repo_id=repo.id)
            request.session[WIZARD_KEY] = data
            return redirect("/sell/products/new/?step=2")
        return render(request, "sell/product_wizard.html", {"form": form, "step": 1, "repos": repos})

    if "repo" not in data:
        return redirect("/sell/products/new/?step=1")

    if step == "2":
        form = InfoStepForm(request.POST or None, initial=data.get("info"))
        if request.method == "POST" and form.is_valid():
            info = dict(form.cleaned_data)
            info["price"] = str(info["price"])
            data["info"] = info
            request.session[WIZARD_KEY] = data
            return redirect("/sell/products/new/?step=3")
        return render(request, "sell/product_wizard.html", {"form": form, "step": 2})

    if "info" not in data:
        return redirect("/sell/products/new/?step=2")

    form = CategoryStepForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        try:
            product = services.create_product(
                user,
                data={
                    **data["info"],
                    "category": cd["category"],
                    "demo_url": cd["demo_url"],
                    "source_repo_full_name": data["repo"],
                    "source_repo_id": data["repo_id"],
                },
                technologies=cd["technologies"],
                platforms=cd["platforms"],
            )
        except (ServiceError, ValidationError) as e:
            messages.error(request, _err(e))
        else:
            request.session.pop(WIZARD_KEY, None)
            messages.success(request, "Черновик продукта создан. Добавьте скриншоты и отправьте релиз на проверку.")
            return redirect("sell:product_media", pk=product.pk)
    return render(request, "sell/product_wizard.html", {"form": form, "step": 3})


@seller_required
def product_media(request, pk):
    """Шаг 4 мастера и раздел редактирования: скриншоты и проверка релиза."""
    product = _own_product(request, pk)
    form = ScreenshotsForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        files = request.FILES.getlist("images")
        if not files:
            messages.error(request, "Выберите файлы.")
        else:
            try:
                services.add_screenshots(product, request.user, files)
                messages.success(request, "Скриншоты загружены.")
                return redirect("sell:product_media", pk=pk)
            except (ServiceError, ValidationError) as e:
                messages.error(request, _err(e))
    releases, release_error = [], None
    from apps.versions import services as version_services

    try:
        releases = version_services.available_releases(product, request.user)
    except ServiceError as e:
        release_error = str(e)
    return render(
        request,
        "sell/product_media.html",
        {
            "product": product,
            "form": form,
            "screenshots": product.screenshots.all(),
            "releases": releases,
            "release_error": release_error,
            "max_screens": services.MAX_SCREENSHOTS,
        },
    )


@seller_required
def screenshot_delete(request, pk, sid):
    product = _own_product(request, pk)
    if request.method == "POST":
        services.delete_screenshot(product, request.user, sid)
        messages.success(request, "Скриншот удалён.")
    return redirect("sell:product_media", pk=pk)


@seller_required
def product_edit(request, pk):
    product = _own_product(request, pk)
    form = ProductEditForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        try:
            services.update_product(
                product,
                request.user,
                data={k: cd[k] for k in ["title", "short_description", "description", "price", "category", "demo_url"]},
                technologies=cd["technologies"],
                platforms=cd["platforms"],
            )
            messages.success(request, "Изменения сохранены.")
            return redirect("sell:product_edit", pk=pk)
        except (ServiceError, ValidationError) as e:
            messages.error(request, _err(e))
    return render(request, "sell/product_edit.html", {"product": product, "form": form})


@seller_required
def product_action(request, pk, action):
    """Снять с продажи, вернуть в продажу, удалить."""
    product = _own_product(request, pk)
    if request.method != "POST":
        return redirect("sell:dashboard")
    try:
        if action == "hide":
            services.hide_product(product, request.user)
            messages.success(request, "Продукт снят с продажи. У покупателей доступ сохраняется.")
        elif action == "unhide":
            services.unhide_product(product, request.user)
            messages.success(request, "Продукт снова в продаже.")
        elif action == "delete":
            services.delete_product(product, request.user)
            messages.success(request, "Продукт удалён.")
    except (ServiceError, InvalidTransition) as e:
        messages.error(request, str(e))
    return redirect("sell:dashboard")


def _err(e):
    if isinstance(e, ValidationError):
        return "; ".join(e.messages)
    return str(e)

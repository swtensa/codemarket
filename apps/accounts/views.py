from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from . import services
from .forms import EmailLoginForm, ProfileForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("catalog:index")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = services.register_user(
            email=form.cleaned_data["email"],
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password1"],
        )
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        messages.success(request, "Добро пожаловать в CodeMarket!")
        return redirect("catalog:index")
    return render(request, "accounts/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    form_class = EmailLoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


def blocked(request):
    reason = request.session.pop("blocked_reason", None)
    return render(request, "accounts/blocked.html", {"reason": reason})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        services.update_profile(
            request.user, username=form.cleaned_data["username"], github_login=form.cleaned_data["github_login"]
        )
        messages.success(request, "Профиль сохранён.")
        return redirect("me:profile")
    return render(request, "accounts/profile.html", {"form": form, "tab": "profile"})


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("me:profile")

    def form_valid(self, form):
        messages.success(self.request, "Пароль изменён.")
        return super().form_valid(form)


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

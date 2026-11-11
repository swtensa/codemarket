from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User, username_validator


class RegisterForm(forms.Form):
    email = forms.EmailField(label="Email", max_length=254)
    username = forms.CharField(
        label="Имя пользователя",
        max_length=30,
        validators=[username_validator],
        help_text="3–30 символов: латинские буквы, цифры, «_».",
    )
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Не короче 8 символов, буквы и цифры.",
    )
    password2 = forms.CharField(
        label="Повтор пароля", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    accept_terms = forms.BooleanField(
        label="Принимаю пользовательское соглашение и политику обработки персональных данных",
        error_messages={"required": "Без согласия регистрация невозможна."},
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже есть.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Это имя уже занято.")
        return username

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Пароли не совпадают.")
        if p1:
            try:
                password_validation.validate_password(p1, User(email=data.get("email"), username=data.get("username")))
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return data


class EmailLoginForm(AuthenticationForm):
    """Вход по email. Заблокированному пользователю показывается причина."""

    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))

    error_messages = {
        "invalid_login": "Неверный email или пароль.",
        "inactive": "Аккаунт отключён.",
    }

    def clean(self):
        email = (self.cleaned_data.get("username") or "").strip().lower()
        password = self.cleaned_data.get("password")
        if email and password:
            candidate = User.objects.filter(email__iexact=email).first()
            if candidate and candidate.is_blocked and candidate.check_password(password):
                raise forms.ValidationError(
                    f"Аккаунт заблокирован. Причина: {candidate.block_reason or 'не указана'}",
                    code="blocked",
                )
            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "github_login"]
        labels = {"github_login": "Логин GitHub"}
        help_texts = {"github_login": "Нужен, чтобы получить доступ к купленному коду через GitHub."}

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Это имя уже занято.")
        return username

    def clean_github_login(self):
        from .validators import clean_github_login

        return clean_github_login(self.cleaned_data["github_login"])

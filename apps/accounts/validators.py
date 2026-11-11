import re

from django.core.exceptions import ValidationError

GITHUB_LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")


def clean_github_login(value):
    """Логин GitHub без «@» и пробелов; неверный формат — ValidationError."""
    login = (value or "").strip().lstrip("@")
    if login and not GITHUB_LOGIN_RE.fullmatch(login):
        raise ValidationError("Похоже, это не логин GitHub: латиница, цифры и дефис, до 39 символов.")
    return login


class LettersAndDigitsValidator:
    """Пароль должен содержать и буквы, и цифры."""

    def validate(self, password, user=None):
        if not re.search(r"[A-Za-zА-Яа-яЁё]", password) or not re.search(r"\d", password):
            raise ValidationError("Пароль должен содержать буквы и цифры.", code="password_letters_digits")

    def get_help_text(self):
        return "Пароль должен содержать буквы и цифры."

import re

from django.core.exceptions import ValidationError


class LettersAndDigitsValidator:
    """Пароль должен содержать и буквы, и цифры."""

    def validate(self, password, user=None):
        if not re.search(r"[A-Za-zА-Яа-яЁё]", password) or not re.search(r"\d", password):
            raise ValidationError("Пароль должен содержать буквы и цифры.", code="password_letters_digits")

    def get_help_text(self):
        return "Пароль должен содержать буквы и цифры."

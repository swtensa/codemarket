from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models

username_validator = RegexValidator(
    r"^[A-Za-z0-9_]{3,30}$",
    "Имя пользователя: 3–30 символов, латинские буквы, цифры и знак подчёркивания.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, username, password, **extra):
        if not email:
            raise ValueError("Нужен email")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, username=username, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, username, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, username, password, **extra)

    def create_superuser(self, email, username, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create_user(email, username, password, **extra)


class User(AbstractUser):
    """Пользователь площадки. Администратор определяется флагом is_staff."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        BLOCKED = "blocked", "Заблокирован"

    first_name = None
    last_name = None
    date_joined = None

    email = models.EmailField("email", unique=True)
    username = models.CharField("имя пользователя", max_length=30, unique=True, validators=[username_validator])
    github_login = models.CharField("логин GitHub", max_length=39, blank=True)
    github_installation_id = models.BigIntegerField("установка GitHub App", null=True, blank=True)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    block_reason = models.TextField("причина блокировки", blank=True)
    created_at = models.DateTimeField("зарегистрирован", auto_now_add=True)
    terms_accepted_at = models.DateTimeField("принято соглашение", null=True, blank=True)
    seller_terms_accepted_at = models.DateTimeField("приняты условия продавца", null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        ordering = ["-created_at"]

    def __str__(self):
        return self.username

    @property
    def is_blocked(self):
        return self.status == self.Status.BLOCKED

    @property
    def is_seller(self):
        """Раздел «Продажи» появляется после подключения GitHub."""
        return self.github_installation_id is not None

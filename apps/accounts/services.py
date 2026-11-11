"""Сервисы аккаунтов: регистрация, профиль, блокировка."""

import logging

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError

from .models import User

admin_log = logging.getLogger("codemarket.admin")


def register_user(*, email, username, password):
    """Создать пользователя и зафиксировать согласие с соглашением и политикой ПДн."""
    return User.objects.create_user(
        email=email,
        username=username,
        password=password,
        terms_accepted_at=timezone.now(),
    )


def _stored_github_login(user):
    # ModelForm уже записала новое значение в объект, поэтому старое берём из базы
    return User.objects.filter(pk=user.pk).values_list("github_login", flat=True).first() or ""


def update_profile(user, *, username, github_login):
    """Изменить имя и логин GitHub. При смене логина доступ к купленным копиям переходит на новый."""
    from apps.purchases.services import on_github_login_changed

    old_login = _stored_github_login(user)
    user.username = username
    user.github_login = github_login
    user.save(update_fields=["username", "github_login"])
    on_github_login_changed(user, old_login)
    return user


def set_github_login(user, github_login):
    """Сохранить логин GitHub (со страницы покупки). Неверный формат — ServiceError."""
    from django.core.exceptions import ValidationError

    from apps.purchases.services import on_github_login_changed

    from .validators import clean_github_login

    try:
        login = clean_github_login(github_login)
    except ValidationError as e:
        raise ServiceError(e.messages[0])
    old_login = _stored_github_login(user)
    user.github_login = login
    user.save(update_fields=["github_login"])
    on_github_login_changed(user, old_login)
    return user


def accept_seller_terms(user):
    """Зафиксировать принятие условий для продавцов (один раз)."""
    if user.seller_terms_accepted_at is None:
        user.seller_terms_accepted_at = timezone.now()
        user.save(update_fields=["seller_terms_accepted_at"])
    return user


def connect_github(user, installation_id):
    """Сохранить id установки GitHub App (токены продавца не храним)."""
    user.github_installation_id = int(installation_id)
    user.save(update_fields=["github_installation_id"])
    return user


def disconnect_github_installation(installation_id):
    """Установка удалена на стороне GitHub — забыть её."""
    return User.objects.filter(github_installation_id=installation_id).update(github_installation_id=None)


@transaction.atomic
def block_user(user, *, reason, admin):
    """Заблокировать пользователя.

    Продукты скрываются из каталога (каталог показывает только активных продавцов),
    заказы продавца обрабатываются по правилу из раздела 7.4 ТЗ.
    """
    if not reason or not reason.strip():
        raise ServiceError("Укажите причину блокировки.")
    if user.is_staff:
        raise ServiceError("Нельзя заблокировать администратора.")
    user.status = User.Status.BLOCKED
    user.block_reason = reason.strip()
    user.save(update_fields=["status", "block_reason"])

    from apps.orders.services import handle_seller_blocked

    handle_seller_blocked(user, admin=admin)
    admin_log.info("admin=%s blocked user=%s reason=%s", admin, user.pk, reason)
    return user


def unblock_user(user, *, admin):
    """Снять блокировку."""
    user.status = User.Status.ACTIVE
    user.block_reason = ""
    user.save(update_fields=["status", "block_reason"])
    admin_log.info("admin=%s unblocked user=%s", admin, user.pk)
    return user

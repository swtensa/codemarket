"""Сервисы покупок: оформление, оплата, доступ к репозиторию-копии, скачивание ZIP, статусы покупки."""

import logging
import math
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.balance import services as balance_services
from apps.catalog import services as catalog_services
from apps.catalog.models import Product
from apps.core.exceptions import InvalidTransition, ServiceError
from apps.integrations.github import get_client
from apps.integrations.github.base import GitHubError
from apps.notifications.services import notify, notify_many

from .models import Purchase

log = logging.getLogger("codemarket")
P = Purchase.Status
A = Purchase.Access

# Раздел 7.3 ТЗ
PURCHASE_TRANSITIONS = {
    P.PENDING: {P.PAID, P.CANCELLED},
    P.PAID: {P.COMPLETED, P.DISPUTE},
    P.DISPUTE: {P.PAID, P.REFUNDED, P.PARTIALLY_REFUNDED},
}
# Покупки, дающие доступ к коду
ACTIVE = [P.PAID, P.COMPLETED, P.DISPUTE, P.PARTIALLY_REFUNDED]


def change_purchase_status(purchase, new_status):
    """Сменить статус покупки с проверкой допустимости перехода."""
    if new_status not in PURCHASE_TRANSITIONS.get(purchase.status, set()):
        raise InvalidTransition(f"Покупка: переход {purchase.status} → {new_status} недопустим")
    purchase.status = new_status
    purchase.save(update_fields=["status"])
    return purchase


# ---------------------------------------------------------------- чтение


def active_purchase(user, product):
    """Действующая покупка пользователя (paid/completed/dispute/partially_refunded) или None."""
    if not user.is_authenticated:
        return None
    return Purchase.objects.filter(buyer=user, product=product, status__in=ACTIVE).first()


def has_access(user, product):
    return active_purchase(user, product) is not None


def product_has_purchases(product):
    return Purchase.objects.filter(product=product).exclude(status__in=[P.PENDING, P.CANCELLED]).exists()


def user_purchases(user):
    return (
        Purchase.objects.filter(buyer=user)
        .exclude(status=P.CANCELLED)
        .select_related("product", "product__category")
        .order_by("-created_at")
    )


def get_purchase_for(user, pk):
    """Покупка для страницы покупки: только покупатель или администратор, иначе PermissionError."""
    purchase = Purchase.objects.select_related("product", "product__seller", "version", "buyer").get(pk=pk)
    if purchase.buyer_id != user.id and not user.is_staff:
        raise PermissionError
    return purchase


# ---------------------------------------------------------------- оформление и оплата


def check_can_buy(user, product):
    """Проверка перед покупкой: продукт опубликован, покупатель не продавец, не куплено ранее."""
    if not user.is_authenticated:
        raise ServiceError("Войдите, чтобы купить продукт.")
    if product.status != Product.Status.PUBLISHED or product.seller.is_blocked:
        raise ServiceError("Продукт сейчас недоступен для покупки.")
    if product.seller_id == user.id:
        raise ServiceError("Нельзя купить собственный продукт.")
    if active_purchase(user, product):
        raise ServiceError("Вы уже купили этот продукт.")
    from apps.versions.services import current_version

    if current_version(product) is None:
        raise ServiceError("У продукта нет одобренной версии.")


@transaction.atomic
def create_purchase(user, product, *, accept_license):
    """Создать покупку pending с ценой, комиссией и версией на момент покупки (без платежа)."""
    if not accept_license:
        raise ServiceError("Нужно принять условия лицензии.")
    check_can_buy(user, product)
    from apps.versions.services import current_version

    return Purchase.objects.create(
        buyer=user,
        product=product,
        version=current_version(product),
        price=product.price,
        commission=balance_services.commission_for(product.price),
        status=P.PENDING,
        license_version=settings.LICENSE_VERSION,
    )


def start_purchase(user, product, *, github_login="", accept_license=False):
    """«Купить»: покупка pending + платёж у провайдера. Возвращает (purchase, адрес оплаты)."""
    from apps.accounts.services import set_github_login
    from apps.payments.services import create_payment, pending_payment_for

    if github_login and github_login.strip().lstrip("@") != user.github_login:
        check_can_buy(user, product)
        set_github_login(user, github_login)
    purchase = Purchase.objects.filter(buyer=user, product=product, status=P.PENDING).first()
    if purchase is not None:
        # повторное нажатие «Оплатить»: продолжить уже созданный платёж, а не создавать второй
        if not accept_license:
            raise ServiceError("Нужно принять условия лицензии.")
        check_can_buy(user, product)
        payment = pending_payment_for(purchase=purchase)
        if payment is not None:
            return purchase, payment.confirmation_url
    else:
        purchase = create_purchase(user, product, accept_license=accept_license)
    payment = create_payment(amount=purchase.price, description=f"CodeMarket: «{product.title}»", purchase=purchase)
    return purchase, payment.confirmation_url


@transaction.atomic
def on_payment_succeeded(purchase):
    """Оплата подтверждена провайдером: покупка paid, начисление продавцу (held), уведомления.

    Повторный вызов не создаёт второго начисления.
    """
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status != P.PENDING:
        if purchase.status == P.CANCELLED:
            _alert_admins(f"Оплачена отменённая покупка №{purchase.pk}: верните деньги покупателю в ЮKassa.")
        return purchase
    try:
        with transaction.atomic():
            change_purchase_status(purchase, P.PAID)
            purchase.paid_at = timezone.now()
            purchase.save(update_fields=["paid_at"])
    except IntegrityError:
        _alert_admins(f"Двойная оплата покупки №{purchase.pk}: продукт уже куплен, верните деньги в ЮKassa.")
        return purchase
    balance_services.credit_sale(purchase)
    catalog_services.increment_sales(purchase.product)
    notify(
        purchase.product.seller,
        f"Продажа: «{purchase.product.title}» за {purchase.price:.0f} ₽.",
        "/balance/",
    )
    notify(
        purchase.buyer,
        f"Оплата прошла: «{purchase.product.title}». Код доступен на странице покупки.",
        f"/me/purchases/{purchase.pk}/",
    )
    return purchase


def _alert_admins(text):
    from apps.accounts.models import User

    log.error(text)
    notify_many(User.objects.filter(is_staff=True), text, "/moderation/")


def on_payment_canceled(purchase):
    if purchase.status == P.PENDING:
        change_purchase_status(purchase, P.CANCELLED)


@transaction.atomic
def create_paid_purchase_for_order(order, price=None):
    """«Купить с доработкой»: оплата заказа включает продукт — создать оплаченную покупку и выдать доступ.

    price — оплаченная доля продукта (цена на момент создания платежа); по умолчанию текущая цена.
    """
    from apps.versions.services import current_version

    existing = active_purchase(order.buyer, order.product)
    if existing:
        return existing
    product = order.product
    price = product.price if price is None else price
    purchase = Purchase.objects.create(
        buyer=order.buyer,
        product=product,
        version=current_version(product),
        price=price,
        commission=balance_services.commission_for(price),
        status=P.PAID,
        paid_at=timezone.now(),
        license_version=settings.LICENSE_VERSION,
    )
    balance_services.credit_sale(purchase)
    catalog_services.increment_sales(product)
    return purchase


def cancel_unpaid(now=None):
    """Отменить покупки, не оплаченные за PAYMENT_TIMEOUT_MIN (перед этим перепроверить платёж)."""
    from apps.payments.services import cancel_pending, refresh_payment

    now = now or timezone.now()
    limit = now - timedelta(minutes=settings.PAYMENT_TIMEOUT_MIN)
    cancelled = 0
    for purchase in Purchase.objects.filter(status=P.PENDING, created_at__lt=limit):
        for payment in purchase.payments.filter(status="pending"):
            refresh_payment(payment)
        purchase.refresh_from_db()
        if purchase.status == P.PENDING:
            for payment in purchase.payments.filter(status="pending"):
                cancel_pending(payment)
            change_purchase_status(purchase, P.CANCELLED)
            cancelled += 1
    return cancelled


def complete_purchase(purchase):
    """Срок удержания прошёл без спора (вызывает release_funds)."""
    return change_purchase_status(purchase, P.COMPLETED)


# ---------------------------------------------------------------- доступ к коду


def can_download(user, purchase):
    return (purchase.buyer_id == user.id or user.is_staff) and purchase.status in ACTIVE


def download_version(user, purchase):
    """Архив последней одобренной версии для скачивания (через view с проверкой права)."""
    from apps.versions.services import current_version

    if not can_download(user, purchase):
        raise PermissionError
    version = current_version(purchase.product) or purchase.version
    if version is None or not version.archive:
        raise ServiceError("Архив версии недоступен.")
    return version


def grant_access(purchase):
    """Пригласить покупателя в репозиторий-копию с правом pull."""
    login = purchase.buyer.github_login
    if purchase.status not in ACTIVE:
        raise ServiceError("Покупка не оплачена.")
    if not login:
        raise ServiceError("Укажите логин GitHub.")
    mirror = purchase.product.mirror_repo_full_name
    if not mirror:
        raise ServiceError("Репозиторий-копия ещё не создан.")
    try:
        state = get_client().add_collaborator(mirror, login)
    except GitHubError as e:
        raise ServiceError(str(e))
    purchase.access_status = A.GRANTED if state == "granted" else A.INVITED
    purchase.access_granted_at = timezone.now()
    purchase.save(update_fields=["access_status", "access_granted_at"])
    return purchase


def refresh_access_status(purchase):
    """Обновить статус приглашения (принято ли на GitHub)."""
    if purchase.access_status != A.INVITED:
        return purchase
    try:
        state = get_client().invitation_status(purchase.product.mirror_repo_full_name, purchase.buyer.github_login)
    except GitHubError:
        return purchase
    if state == "granted":
        purchase.access_status = A.GRANTED
        purchase.save(update_fields=["access_status"])
    return purchase


def revoke_access(purchase):
    """Отозвать доступ к копии (возврат денег)."""
    if purchase.access_status in (A.INVITED, A.GRANTED) and purchase.buyer.github_login:
        try:
            get_client().remove_collaborator(purchase.product.mirror_repo_full_name, purchase.buyer.github_login)
        except GitHubError as e:
            log.error("Не удалось отозвать доступ покупки %s: %s", purchase.pk, e)
    purchase.access_status = A.REVOKED
    purchase.access_revoked_at = timezone.now()
    purchase.save(update_fields=["access_status", "access_revoked_at"])
    return purchase


def on_github_login_changed(user, old_login):
    """Покупатель сменил логин GitHub: отозвать приглашение старого логина, новый пригласит sync_access."""
    if not old_login or old_login == user.github_login:
        return 0
    moved = 0
    for purchase in Purchase.objects.filter(
        buyer=user, status__in=ACTIVE, access_status__in=[A.INVITED, A.GRANTED]
    ).select_related("product"):
        try:
            get_client().remove_collaborator(purchase.product.mirror_repo_full_name, old_login)
        except GitHubError as e:
            log.error("Не удалось отозвать доступ %s к покупке %s: %s", old_login, purchase.pk, e)
        purchase.access_status = A.NONE
        purchase.save(update_fields=["access_status"])
        moved += 1
    return moved


def sync_access(limit=50):
    """Фоновая задача: обновить статусы отправленных приглашений и пригласить новых покупателей с логином GitHub."""
    for purchase in Purchase.objects.filter(status__in=ACTIVE, access_status=A.INVITED).select_related(
        "product", "buyer"
    )[:limit]:
        refresh_access_status(purchase)
    invited = 0
    qs = Purchase.objects.filter(status__in=ACTIVE, access_status=A.NONE).exclude(buyer__github_login="")
    for purchase in qs.select_related("product", "buyer")[:limit]:
        try:
            grant_access(purchase)
            invited += 1
        except ServiceError as e:
            log.info("Доступ по покупке %s пока не выдан: %s", purchase.pk, e)
    return invited


def notify_new_version(product, version):
    """Новая версия купленного продукта одобрена: уведомить всех покупателей (копия уже обновлена)."""
    buyers = [p.buyer for p in Purchase.objects.filter(product=product, status__in=ACTIVE).select_related("buyer")]
    notify_many(
        buyers,
        f"Вышла версия {version.tag_name} продукта «{product.title}». Выполните git pull или скачайте ZIP.",
        f"/p/{product.slug}/",
    )
    return len(buyers)


# ---------------------------------------------------------------- споры и возвраты


def dispute_days_left(purchase):
    """Сколько дней осталось на открытие спора по покупке (0 — срок вышел)."""
    if purchase.status != P.PAID or purchase.paid_at is None:
        return 0
    seconds = (purchase.paid_at + timedelta(days=settings.HOLD_DAYS) - timezone.now()).total_seconds()
    return max(0, math.ceil(seconds / 86400))


def open_dispute(purchase):
    return change_purchase_status(purchase, P.DISPUTE)


def resolve_dispute(purchase, *, outcome, refund_amount=0):
    """Решение спора по покупке: seller → paid; refund → refunded (доступ отзывается); partial → partially_refunded."""
    if outcome == "seller":
        return change_purchase_status(purchase, P.PAID)
    if outcome == "refund":
        change_purchase_status(purchase, P.REFUNDED)
        balance_services.reverse_purchase(purchase, purchase.price)
        revoke_access(purchase)
        return purchase
    change_purchase_status(purchase, P.PARTIALLY_REFUNDED)
    balance_services.reverse_purchase(purchase, refund_amount)
    return purchase

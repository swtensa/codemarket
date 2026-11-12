"""Покупки: оформление, оплата, доступ к репозиторию-копии, скачивание ZIP, статусы (раздел 7.3 ТЗ)."""

import logging
import math
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import InvalidTransition, NotFound, ServiceError
from app.integrations.github import get_client
from app.integrations.github.base import GitHubError
from app.models import AccessStatus, Product, ProductStatus, Purchase, PurchaseStatus, User
from app.models.base import utcnow
from app.services import balance as balance_services
from app.services import catalog as catalog_services
from app.services.notifications import notify, notify_admins, notify_many

log = logging.getLogger("codemarket")
P = PurchaseStatus
A = AccessStatus

PURCHASE_TRANSITIONS = {
    P.PENDING: {P.PAID, P.CANCELLED},
    P.PAID: {P.COMPLETED, P.DISPUTE},
    P.DISPUTE: {P.PAID, P.REFUNDED, P.PARTIALLY_REFUNDED},
}
# Покупки, дающие доступ к коду
ACTIVE = [P.PAID, P.COMPLETED, P.DISPUTE, P.PARTIALLY_REFUNDED]


def change_purchase_status(db: Session, purchase: Purchase, new_status: str) -> Purchase:
    if new_status not in PURCHASE_TRANSITIONS.get(purchase.status, set()):
        raise InvalidTransition(f"Покупка: переход {purchase.status} → {new_status} недопустим")
    purchase.status = new_status
    db.flush()
    return purchase


# ---------------------------------------------------------------- чтение


def active_purchase(db: Session, user: User | None, product: Product) -> Purchase | None:
    """Действующая покупка пользователя (paid/completed/dispute/partially_refunded) или None."""
    if user is None:
        return None
    return db.scalar(
        select(Purchase)
        .where(Purchase.buyer_id == user.id, Purchase.product_id == product.id, Purchase.status.in_(ACTIVE))
        .limit(1)
    )


def has_access(db: Session, user: User, product: Product) -> bool:
    return active_purchase(db, user, product) is not None


def product_has_purchases(db: Session, product: Product) -> bool:
    return (
        db.scalar(
            select(Purchase.id)
            .where(Purchase.product_id == product.id, Purchase.status.not_in([P.PENDING, P.CANCELLED]))
            .limit(1)
        )
        is not None
    )


def user_purchases_stmt(user: User):
    return (
        select(Purchase)
        .where(Purchase.buyer_id == user.id, Purchase.status != P.CANCELLED)
        .options(selectinload(Purchase.product).selectinload(Product.screenshots))
        .order_by(Purchase.created_at.desc(), Purchase.id.desc())
    )


def get_purchase_for(db: Session, user: User, pk: int) -> Purchase:
    """Покупка для страницы покупки: только покупатель или администратор, иначе 404."""
    purchase = db.get(Purchase, pk)
    if purchase is None or (purchase.buyer_id != user.id and not user.is_staff):
        raise NotFound("Покупка не найдена")
    return purchase


# ---------------------------------------------------------------- оформление и оплата


def check_can_buy(db: Session, user: User | None, product: Product) -> None:
    """Проверка перед покупкой: продукт опубликован, покупатель не продавец, не куплено ранее."""
    from app.services.versions import current_version

    if user is None:
        raise ServiceError("Войдите, чтобы купить продукт.")
    if product.status != ProductStatus.PUBLISHED or product.seller.is_blocked:
        raise ServiceError("Продукт сейчас недоступен для покупки.")
    if product.seller_id == user.id:
        raise ServiceError("Нельзя купить собственный продукт.")
    if active_purchase(db, user, product):
        raise ServiceError("Вы уже купили этот продукт.")
    if current_version(db, product) is None:
        raise ServiceError("У продукта нет одобренной версии.")


def create_purchase(db: Session, user: User, product: Product, *, accept_license: bool) -> Purchase:
    """Создать покупку pending с ценой, комиссией и версией на момент покупки (без платежа)."""
    from app.services.versions import current_version

    if not accept_license:
        raise ServiceError("Нужно принять условия лицензии.")
    check_can_buy(db, user, product)
    purchase = Purchase(
        buyer_id=user.id,
        product_id=product.id,
        version_id=current_version(db, product).id,
        price=product.price,
        commission=balance_services.commission_for(product.price),
        status=P.PENDING,
        license_version=settings.license_version,
    )
    db.add(purchase)
    db.flush()
    return purchase


def start_purchase(db: Session, user: User, product: Product, *, github_login: str = "", accept_license=False):
    """«Купить»: покупка pending + платёж у провайдера. Возвращает (purchase, адрес оплаты)."""
    from app.services.accounts import set_github_login
    from app.services.payments import create_payment, pending_payment_for

    if github_login and github_login.strip().lstrip("@") != user.github_login:
        check_can_buy(db, user, product)
        set_github_login(db, user, github_login)
    purchase = db.scalar(
        select(Purchase).where(
            Purchase.buyer_id == user.id, Purchase.product_id == product.id, Purchase.status == P.PENDING
        )
    )
    if purchase is not None:
        # повторное нажатие «Оплатить»: продолжить уже созданный платёж, а не создавать второй
        if not accept_license:
            raise ServiceError("Нужно принять условия лицензии.")
        check_can_buy(db, user, product)
        payment = pending_payment_for(db, purchase=purchase)
        if payment is not None:
            return purchase, payment.confirmation_url
    else:
        purchase = create_purchase(db, user, product, accept_license=accept_license)
    payment = create_payment(db, amount=purchase.price, description=f"CodeMarket: «{product.title}»", purchase=purchase)
    return purchase, payment.confirmation_url


def on_payment_succeeded(db: Session, purchase: Purchase) -> Purchase:
    """Оплата подтверждена провайдером: покупка paid, начисление продавцу (held), уведомления.

    Повторный вызов не создаёт второго начисления.
    """
    db.refresh(purchase, with_for_update=True)
    if purchase.status != P.PENDING:
        if purchase.status == P.CANCELLED:
            _alert_admins(db, f"Оплачена отменённая покупка №{purchase.id}: верните деньги покупателю в ЮKassa.")
        return purchase
    try:
        with db.begin_nested():
            change_purchase_status(db, purchase, P.PAID)
            purchase.paid_at = utcnow()
            db.flush()
    except IntegrityError:
        db.refresh(purchase)
        _alert_admins(db, f"Двойная оплата покупки №{purchase.id}: продукт уже куплен, верните деньги в ЮKassa.")
        return purchase
    balance_services.credit_sale(db, purchase)
    catalog_services.increment_sales(db, purchase.product)
    notify(db, purchase.product.seller, f"Продажа: «{purchase.product.title}» за {purchase.price:.0f} ₽.", "/balance/")
    notify(
        db,
        purchase.buyer,
        f"Оплата прошла: «{purchase.product.title}». Код доступен на странице покупки.",
        f"/me/purchases/{purchase.id}/",
    )
    return purchase


def _alert_admins(db: Session, text: str) -> None:
    log.error(text)
    notify_admins(db, text, "/moderation/")


def on_payment_canceled(db: Session, purchase: Purchase) -> None:
    if purchase.status == P.PENDING:
        change_purchase_status(db, purchase, P.CANCELLED)


def create_paid_purchase_for_order(db: Session, order, price=None) -> Purchase:
    """«Купить с доработкой»: оплата заказа включает продукт — создать оплаченную покупку и выдать доступ.

    price — оплаченная доля продукта (цена на момент создания платежа); по умолчанию текущая цена.
    """
    from app.services.versions import current_version

    existing = active_purchase(db, order.buyer, order.product)
    if existing:
        return existing
    product = order.product
    price = product.price if price is None else Decimal(price)
    version = current_version(db, product)
    purchase = Purchase(
        buyer_id=order.buyer_id,
        product_id=product.id,
        version_id=version.id if version else None,
        price=price,
        commission=balance_services.commission_for(price),
        status=P.PAID,
        paid_at=utcnow(),
        license_version=settings.license_version,
    )
    db.add(purchase)
    db.flush()
    balance_services.credit_sale(db, purchase)
    catalog_services.increment_sales(db, product)
    return purchase


def cancel_unpaid(db: Session, now=None) -> int:
    """Отменить покупки, не оплаченные за PAYMENT_TIMEOUT_MIN (перед этим перепроверить платёж)."""
    from app.services.payments import cancel_pending, refresh_payment

    now = now or utcnow()
    limit = now - timedelta(minutes=settings.payment_timeout_min)
    cancelled = 0
    for purchase in db.scalars(select(Purchase).where(Purchase.status == P.PENDING, Purchase.created_at < limit)).all():
        for payment in [p for p in _payments(db, purchase) if p.status == "pending"]:
            refresh_payment(db, payment)
        db.refresh(purchase)
        if purchase.status == P.PENDING:
            for payment in [p for p in _payments(db, purchase) if p.status == "pending"]:
                cancel_pending(db, payment)
            change_purchase_status(db, purchase, P.CANCELLED)
            cancelled += 1
    return cancelled


def _payments(db: Session, purchase: Purchase):
    from app.models import Payment

    return db.scalars(select(Payment).where(Payment.purchase_id == purchase.id).order_by(Payment.id)).all()


def complete_purchase(db: Session, purchase: Purchase) -> Purchase:
    """Срок удержания прошёл без спора (вызывает release_funds)."""
    return change_purchase_status(db, purchase, P.COMPLETED)


# ---------------------------------------------------------------- доступ к коду


def can_download(user: User, purchase: Purchase) -> bool:
    return (purchase.buyer_id == user.id or user.is_staff) and purchase.status in ACTIVE


def download_version(db: Session, user: User, purchase: Purchase):
    """Архив последней одобренной версии для скачивания (через эндпоинт с проверкой права)."""
    from app.services.versions import current_version

    if not can_download(user, purchase):
        raise NotFound("Покупка не найдена")
    version = current_version(db, purchase.product) or purchase.version
    if version is None or not version.archive:
        raise ServiceError("Архив версии недоступен.")
    return version


def grant_access(db: Session, purchase: Purchase) -> Purchase:
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
    purchase.access_granted_at = utcnow()
    db.flush()
    return purchase


def refresh_access_status(db: Session, purchase: Purchase) -> Purchase:
    """Обновить статус приглашения (принято ли на GitHub)."""
    if purchase.access_status != A.INVITED:
        return purchase
    try:
        state = get_client().invitation_status(purchase.product.mirror_repo_full_name, purchase.buyer.github_login)
    except GitHubError:
        return purchase
    if state == "granted":
        purchase.access_status = A.GRANTED
        db.flush()
    return purchase


def revoke_access(db: Session, purchase: Purchase) -> Purchase:
    """Отозвать доступ к копии (возврат денег)."""
    if purchase.access_status in (A.INVITED, A.GRANTED) and purchase.buyer.github_login:
        try:
            get_client().remove_collaborator(purchase.product.mirror_repo_full_name, purchase.buyer.github_login)
        except GitHubError as e:
            log.error("Не удалось отозвать доступ покупки %s: %s", purchase.id, e)
    purchase.access_status = A.REVOKED
    purchase.access_revoked_at = utcnow()
    db.flush()
    return purchase


def on_github_login_changed(db: Session, user: User, old_login: str) -> int:
    """Покупатель сменил логин GitHub: отозвать приглашение старого логина, новый пригласит sync_access."""
    if not old_login or old_login == user.github_login:
        return 0
    moved = 0
    for purchase in db.scalars(
        select(Purchase).where(
            Purchase.buyer_id == user.id,
            Purchase.status.in_(ACTIVE),
            Purchase.access_status.in_([A.INVITED, A.GRANTED]),
        )
    ).all():
        try:
            get_client().remove_collaborator(purchase.product.mirror_repo_full_name, old_login)
        except GitHubError as e:
            log.error("Не удалось отозвать доступ %s к покупке %s: %s", old_login, purchase.id, e)
        purchase.access_status = A.NONE
        moved += 1
    db.flush()
    return moved


def sync_access(db: Session, limit: int = 50) -> int:
    """Фоновая задача: обновить статусы приглашений и пригласить новых покупателей с логином GitHub."""
    for purchase in db.scalars(
        select(Purchase).where(Purchase.status.in_(ACTIVE), Purchase.access_status == A.INVITED).limit(limit)
    ).all():
        refresh_access_status(db, purchase)
    invited = 0
    stmt = (
        select(Purchase)
        .join(User, User.id == Purchase.buyer_id)
        .where(Purchase.status.in_(ACTIVE), Purchase.access_status == A.NONE, User.github_login != "")
        .order_by(Purchase.id)
        .limit(limit)
    )
    for purchase in db.scalars(stmt).all():
        try:
            with db.begin_nested():
                grant_access(db, purchase)
            invited += 1
        except ServiceError as e:
            log.info("Доступ по покупке %s пока не выдан: %s", purchase.id, e)
    return invited


def notify_new_version(db: Session, product: Product, version) -> int:
    """Новая версия купленного продукта одобрена: уведомить всех покупателей (копия уже обновлена)."""
    buyers = [
        p.buyer
        for p in db.scalars(select(Purchase).where(Purchase.product_id == product.id, Purchase.status.in_(ACTIVE)))
    ]
    notify_many(
        db,
        buyers,
        f"Вышла версия {version.tag_name} продукта «{product.title}». Выполните git pull или скачайте ZIP.",
        f"/p/{product.slug}/",
    )
    return len(buyers)


# ---------------------------------------------------------------- споры и возвраты


def dispute_days_left(purchase: Purchase) -> int:
    """Сколько дней осталось на открытие спора по покупке (0 — срок вышел)."""
    if purchase.status != P.PAID or purchase.paid_at is None:
        return 0
    seconds = (purchase.paid_at + timedelta(days=settings.hold_days) - utcnow()).total_seconds()
    return max(0, math.ceil(seconds / 86400))


def open_dispute(db: Session, purchase: Purchase) -> Purchase:
    return change_purchase_status(db, purchase, P.DISPUTE)


def resolve_dispute(db: Session, purchase: Purchase, *, outcome: str, refund_amount=Decimal("0")) -> Purchase:
    """Решение спора: seller → paid; refund → refunded (доступ отзывается); partial → partially_refunded."""
    if outcome == "seller":
        return change_purchase_status(db, purchase, P.PAID)
    if outcome == "refund":
        change_purchase_status(db, purchase, P.REFUNDED)
        balance_services.reverse_purchase(db, purchase, purchase.price)
        revoke_access(db, purchase)
        return purchase
    change_purchase_status(db, purchase, P.PARTIALLY_REFUNDED)
    balance_services.reverse_purchase(db, purchase, refund_amount)
    return purchase

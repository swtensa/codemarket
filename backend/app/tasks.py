"""Фоновые задачи (их запускает планировщик app.scheduler, вручную — python -m app.cli <задача>).

Каждая задача открывает свою сессию БД и фиксирует изменения сама.
"""

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import CustomOrder, Message, OrderStatus
from app.models.base import utcnow

log = logging.getLogger("codemarket")
DEADLINE_NOTE = "Срок выполнения прошёл: покупатель может отменить заказ с полным возвратом оплаты доработки."


def process_checks(db: Session) -> str:
    from app.services.plagiarism import process_pending

    return f"проверено версий: {process_pending(db)}"


def send_invites(db: Session) -> str:
    from app.services.purchases import sync_access

    return f"отправлено приглашений: {sync_access(db)}"


def cancel_unpaid(db: Session) -> str:
    from app.services.purchases import cancel_unpaid as run

    return f"отменено неоплаченных покупок: {run(db)}"


def auto_accept(db: Session) -> str:
    from app.services.orders import auto_accept as run

    return f"принято автоматически заказов: {run(db)}"


def release_funds(db: Session) -> str:
    from app.services.balance import release_funds as run

    return f"переведено из удержания начислений: {run(db)}"


def check_deadlines(db: Session) -> str:
    """Срок заказа прошёл: один раз написать об этом в чат и уведомить обе стороны."""
    from app.services.notifications import notify

    done = 0
    orders = db.scalars(
        select(CustomOrder).where(
            CustomOrder.status.in_([OrderStatus.IN_WORK, OrderStatus.REVISION]), CustomOrder.deadline < utcnow()
        )
    ).all()
    for order in orders:
        already = db.scalar(
            select(Message.id).where(
                Message.order_id == order.id,
                Message.author_id.is_(None),
                Message.text == DEADLINE_NOTE,
                Message.created_at >= order.deadline,
            )
        )
        if already:
            continue
        db.add(Message(order_id=order.id, author_id=None, text=DEADLINE_NOTE, is_read=True))
        link = f"/orders/{order.id}/"
        notify(db, order.buyer, f"Срок по заказу №{order.id} прошёл. Можно отменить заказ с возвратом оплаты.", link)
        notify(db, order.product.seller, f"Срок по заказу №{order.id} прошёл. Сдайте работу как можно скорее.", link)
        done += 1
    return f"просроченных заказов отмечено: {done}"


# задача → интервал в секундах (как run_scheduler Django-версии; check_deadlines добавлена по ТЗ перехода)
JOBS: list[tuple[str, Callable[[Session], str], int]] = [
    ("process_checks", process_checks, 60),
    ("send_invites", send_invites, 60),
    ("cancel_unpaid", cancel_unpaid, 300),
    ("auto_accept", auto_accept, 600),
    ("check_deadlines", check_deadlines, 600),
    ("release_funds", release_funds, 3600),
]


def run_job(name: str, func: Callable[[Session], str]) -> str:
    """Выполнить задачу в своей транзакции; ошибка пишется в лог и не останавливает планировщик."""
    db = SessionLocal()
    try:
        result = func(db)
        db.commit()
        log.info("Задача %s: %s", name, result)
        return result
    except Exception:
        db.rollback()
        log.exception("Ошибка в задаче %s", name)
        raise
    finally:
        db.close()

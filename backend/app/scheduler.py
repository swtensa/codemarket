"""Планировщик фоновых задач (APScheduler), отдельный процесс без cron и Celery:

    python -m app.scheduler          # работать постоянно (окно PowerShell)
    python -m app.scheduler --once   # выполнить все задачи один раз и выйти

Задачи и интервалы — в app.tasks.JOBS. Ошибка одной задачи не останавливает остальные.
"""

import argparse
import contextlib
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.logging import setup_logging
from app.models.base import utcnow
from app.tasks import JOBS, run_job

log = logging.getLogger("codemarket")


def _safe(name, func):
    with contextlib.suppress(Exception):  # ошибка уже записана в лог, остальные задачи продолжают работу
        run_job(name, func)


def main() -> None:
    parser = argparse.ArgumentParser(description="Фоновые задачи CodeMarket")
    parser.add_argument("--once", action="store_true", help="выполнить все задачи один раз и выйти")
    args = parser.parse_args()
    setup_logging()
    if args.once:
        for name, func, _ in JOBS:
            _safe(name, func)
        return
    scheduler = BlockingScheduler(timezone="UTC")
    for name, func, seconds in JOBS:
        scheduler.add_job(
            _safe,
            "interval",
            seconds=seconds,
            args=[name, func],
            id=name,
            next_run_time=utcnow(),
            max_instances=1,
            coalesce=True,
        )
    print("Планировщик запущен: " + ", ".join(f"{n} ({s} с)" for n, _, s in JOBS) + ". Остановить: Ctrl+C")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Планировщик остановлен")


if __name__ == "__main__":
    main()

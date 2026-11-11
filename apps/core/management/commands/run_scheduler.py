"""Планировщик фоновых задач без cron и Celery: запускается в отдельном окне PowerShell.

    python manage.py run_scheduler

Вызывает остальные команды по их интервалам. Ошибка одной задачи не останавливает остальные.
"""

import time
import traceback

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

# команда → интервал в секундах
JOBS = [
    ("process_checks", 60),
    ("sync_access", 60),
    ("cancel_unpaid", 300),
    ("auto_accept", 600),
    ("release_funds", 3600),
]


class Command(BaseCommand):
    help = "Запускать фоновые команды по расписанию (проверка версий, доступ, автоприёмка, выплаты)"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="выполнить все задачи один раз и выйти")

    def handle(self, *args, **options):
        last = {name: 0.0 for name, _ in JOBS}
        self.stdout.write("Планировщик запущен. Остановить: Ctrl+C")
        while True:
            now = time.monotonic()
            for name, interval in JOBS:
                if options["once"] or now - last[name] >= interval:
                    close_old_connections()
                    try:
                        call_command(name, stdout=self.stdout)
                    except Exception:
                        self.stderr.write(f"Ошибка в {name}:\n{traceback.format_exc()}")
                    last[name] = time.monotonic()
            if options["once"]:
                return
            time.sleep(5)

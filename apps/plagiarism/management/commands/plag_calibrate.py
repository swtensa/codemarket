"""Калибровка проверки на заимствования на парах из fixtures/plag_pairs/.

Каждая пара — папка с подпапками a/ и b/. Команда печатает таблицу:
пара, |FA|, |FB|, общих отпечатков, S и решение при текущих порогах.
"""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.plagiarism.similarity import compare_dirs, verdict

VERDICTS = {"rejected_auto": "автоотказ", "flagged": "отметка", "ok": "норма"}


class Command(BaseCommand):
    help = "Прогнать пары из fixtures/plag_pairs и вывести таблицу коэффициентов сходства S"

    def add_arguments(self, parser):
        parser.add_argument("--k", type=int, default=settings.PLAG_K)
        parser.add_argument("--w", type=int, default=settings.PLAG_W)
        parser.add_argument("--dir", default=str(settings.BASE_DIR / "fixtures" / "plag_pairs"))

    def handle(self, *args, **opts):
        k, w = opts["k"], opts["w"]
        root = Path(opts["dir"])
        pairs = sorted(p for p in root.iterdir() if (p / "a").is_dir() and (p / "b").is_dir())
        self.stdout.write(f"k = {k}, w = {w}, гарантированная длина общего фрагмента t = {w + k - 1} токенов")
        self.stdout.write(f"Пороги: автоотказ S ≥ {settings.PLAG_REJECT}, отметка S ≥ {settings.PLAG_FLAG}\n")
        header = f"{'Пара':<34} {'|FA|':>6} {'|FB|':>6} {'общих':>6} {'S':>6}  {'решение':<10} {'время':>6}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for pair in pairs:
            t = time.monotonic()
            s, na, nb, common = compare_dirs(pair / "a", pair / "b", k, w)
            v = VERDICTS[verdict(s, settings.PLAG_REJECT, settings.PLAG_FLAG)]
            self.stdout.write(
                f"{pair.name:<34} {na:>6} {nb:>6} {common:>6} {s:>6.3f}  {v:<10} {time.monotonic() - t:>5.2f}с"
            )

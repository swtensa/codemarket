"""Команды для запуска вручную:

python -m app.cli process_checks | send_invites | cancel_unpaid | auto_accept | check_deadlines | release_funds
python -m app.cli load_refs        # справочники (разделы, технологии, платформы)
python -m app.cli plag_calibrate   # таблица коэффициентов S по парам fixtures/plag_pairs
python -m app.cli create_admin email имя пароль
python -m app.cli drop_django_tables   # удалить таблицы Django-версии (scripts/drop_django_tables.sql)
"""

import sys
import time
from pathlib import Path

from app.core.config import BASE_DIR, settings
from app.core.logging import setup_logging

VERDICTS = {"rejected_auto": "автоотказ", "flagged": "отметка", "ok": "норма"}


def plag_calibrate(k: int | None = None, w: int | None = None, root: Path | None = None, out=print) -> None:
    """Прогнать пары из fixtures/plag_pairs и вывести таблицу коэффициентов сходства S."""
    from app.plagiarism.similarity import compare_dirs, verdict

    k, w = k or settings.plag_k, w or settings.plag_w
    root = root or BASE_DIR / "fixtures" / "plag_pairs"
    pairs = sorted(p for p in root.iterdir() if (p / "a").is_dir() and (p / "b").is_dir())
    out(f"k = {k}, w = {w}, гарантированная длина общего фрагмента t = {w + k - 1} токенов")
    out(f"Пороги: автоотказ S ≥ {settings.plag_reject}, отметка S ≥ {settings.plag_flag}\n")
    header = f"{'Пара':<34} {'|FA|':>6} {'|FB|':>6} {'общих':>6} {'S':>6}  {'решение':<10} {'время':>6}"
    out(header)
    out("-" * len(header))
    for pair in pairs:
        t = time.monotonic()
        s, na, nb, common = compare_dirs(pair / "a", pair / "b", k, w)
        v = VERDICTS[verdict(s, settings.plag_reject, settings.plag_flag)]
        out(f"{pair.name:<34} {na:>6} {nb:>6} {common:>6} {s:>6.3f}  {v:<10} {time.monotonic() - t:>5.2f}с")


def main(argv: list[str]) -> int:
    setup_logging()
    if not argv:
        print(__doc__)
        return 1
    name, args = argv[0], argv[1:]
    if name == "plag_calibrate":
        plag_calibrate()
        return 0
    if name == "drop_django_tables":
        from sqlalchemy import text

        from app.core.db import engine

        sql = (BASE_DIR.parent / "scripts" / "drop_django_tables.sql").read_text(encoding="utf-8")
        with engine.begin() as conn:
            conn.execute(text(sql))
        print("Таблицы Django-версии удалены")
        return 0
    if name in ("load_refs", "create_admin"):
        from app.core.db import SessionLocal

        db = SessionLocal()
        try:
            if name == "load_refs":
                from app.services.refs import ensure_reference_data

                ensure_reference_data(db)
                print("Справочники загружены")
            else:
                from app.services.accounts import create_user

                email, username, password = args
                create_user(db, email=email, username=username, password=password, is_staff=True)
                print(f"Администратор {email} создан")
            db.commit()
        finally:
            db.close()
        return 0
    from app.tasks import JOBS, run_job

    jobs = {n: f for n, f, _ in JOBS}
    if name not in jobs:
        print(f"Неизвестная команда: {name}\n{__doc__}")
        return 1
    print(run_job(name, jobs[name]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

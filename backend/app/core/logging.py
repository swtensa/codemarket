"""Логи в backend/logs: errors, webhooks, admin_actions, integrations."""

import logging

from .config import settings

_done = False


def setup_logging() -> None:
    global _done
    if _done:
        return
    _done = True
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("{asctime} {levelname} {name}: {message}", style="{")

    def file_handler(name, level=logging.INFO):
        h = logging.FileHandler(settings.log_dir / name, encoding="utf-8")
        h.setLevel(level)
        h.setFormatter(fmt)
        return h

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root = logging.getLogger("codemarket")
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler("errors.log", logging.ERROR))
    for name, filename in [
        ("codemarket.webhooks", "webhooks.log"),
        ("codemarket.admin", "admin_actions.log"),
        ("codemarket.github", "integrations.log"),
    ]:
        logging.getLogger(name).addHandler(file_handler(filename))

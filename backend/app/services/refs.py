"""Справочники площадки: разделы, подкатегории, технологии, платформы."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Platform, Technology

SECTIONS = [
    (
        "Сайты",
        "sites",
        "bi-window",
        [
            ("Лендинг", "landing"),
            ("Интернет-магазин", "shop"),
            ("Портфолио", "portfolio"),
            ("Сайт организации", "company"),
        ],
    ),
    (
        "Модули",
        "modules",
        "bi-puzzle",
        [
            ("Калькуляторы", "calculators"),
            ("Формы", "forms"),
            ("Виджеты и слайдеры", "widgets"),
        ],
    ),
    (
        "Боты",
        "bots",
        "bi-robot",
        [
            ("Telegram-бот", "telegram-bot"),
            ("Бот для бизнеса", "business-bot"),
        ],
    ),
    (
        "Скрипты",
        "scripts",
        "bi-terminal",
        [
            ("Парсеры", "parsers"),
            ("Автоматизация", "automation"),
            ("Документы", "documents"),
        ],
    ),
]

TECHNOLOGIES = [
    ("HTML/CSS", "html-css"),
    ("JavaScript", "javascript"),
    ("TypeScript", "typescript"),
    ("Python", "python"),
    ("PHP", "php"),
    ("React", "react"),
    ("Bootstrap", "bootstrap"),
    ("Sass", "sass"),
    ("aiogram", "aiogram"),
    ("SQLite", "sqlite"),
    ("openpyxl", "openpyxl"),
    ("Node.js", "nodejs"),
]

PLATFORMS = [
    ("Любой хостинг", "any-hosting"),
    ("Tilda", "tilda"),
    ("WordPress", "wordpress"),
    ("1С-Битрикс", "bitrix"),
    ("Django", "django"),
    ("Telegram", "telegram"),
    ("Windows", "windows"),
    ("Linux", "linux"),
]


def _upsert(db, model, slug, **fields):
    obj = db.scalar(select(model).where(model.slug == slug))
    if obj is None:
        obj = model(slug=slug, **fields)
        db.add(obj)
    else:
        for k, v in fields.items():
            setattr(obj, k, v)
    db.flush()
    return obj


def ensure_reference_data(db: Session) -> None:
    """Создать справочники, если их нет (идемпотентно)."""
    for pos, (name, slug, icon, children) in enumerate(SECTIONS):
        section = _upsert(db, Category, slug, name=name, position=pos, icon=icon, parent_id=None)
        for cpos, (cname, cslug) in enumerate(children):
            _upsert(db, Category, cslug, name=cname, position=cpos, parent_id=section.id)
    for name, slug in TECHNOLOGIES:
        _upsert(db, Technology, slug, name=name)
    for name, slug in PLATFORMS:
        _upsert(db, Platform, slug, name=name)

"""Справочники площадки: разделы, подкатегории, технологии, платформы."""

from .models import Category, Platform, Technology

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


def ensure_reference_data():
    """Создать справочники, если их нет (идемпотентно)."""
    for pos, (name, slug, icon, children) in enumerate(SECTIONS):
        section, _ = Category.objects.update_or_create(
            slug=slug, defaults={"name": name, "position": pos, "icon": icon, "parent": None}
        )
        for cpos, (cname, cslug) in enumerate(children):
            Category.objects.update_or_create(slug=cslug, defaults={"name": cname, "position": cpos, "parent": section})
    for name, slug in TECHNOLOGIES:
        Technology.objects.update_or_create(slug=slug, defaults={"name": name})
    for name, slug in PLATFORMS:
        Platform.objects.update_or_create(slug=slug, defaults={"name": name})

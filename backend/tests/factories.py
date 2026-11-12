"""Фабрики тестовых данных (свои функции вместо factory-boy)."""

import itertools
from decimal import Decimal

from app.models import Category, Platform, Product, Technology, User
from app.models.base import utcnow
from app.services.accounts import create_user

PASSWORD = "secret123"
_seq = itertools.count(1)


def make_user(db, *, email=None, username=None, password=PASSWORD, **extra) -> User:
    n = next(_seq)
    extra.setdefault("terms_accepted_at", utcnow())
    return create_user(
        db, email=email or f"user{n}@test.ru", username=username or f"user_{n}", password=password, **extra
    )


def make_admin(db, **extra) -> User:
    return make_user(db, is_staff=True, **extra)


def make_seller(db, **extra) -> User:
    n = next(_seq)
    extra.setdefault("github_installation_id", 900_000_000 + n)
    extra.setdefault("seller_terms_accepted_at", utcnow())
    extra.setdefault("github_login", f"seller-{n}")
    return make_user(db, **extra)


def make_section(db, name="Сайты", slug=None, position=0, icon="bi-window") -> Category:
    c = Category(name=name, slug=slug or f"section-{next(_seq)}", position=position, icon=icon)
    db.add(c)
    db.flush()
    return c


def make_subcategory(db, parent=None, name="Лендинг", slug=None) -> Category:
    parent = parent or make_section(db)
    c = Category(name=name, slug=slug or f"sub-{next(_seq)}", parent_id=parent.id)
    db.add(c)
    db.flush()
    return c


def make_technology(db, name=None, slug=None) -> Technology:
    n = next(_seq)
    t = Technology(name=name or f"Tech {n}", slug=slug or f"tech-{n}")
    db.add(t)
    db.flush()
    return t


def make_platform(db, name=None, slug=None) -> Platform:
    n = next(_seq)
    p = Platform(name=name or f"Platform {n}", slug=slug or f"platform-{n}")
    db.add(p)
    db.flush()
    return p


def make_product(db, *, seller=None, category=None, status="published", price=Decimal("1500"), **extra) -> Product:
    n = next(_seq)
    seller = seller or make_seller(db)
    category = category or make_subcategory(db)
    extra.setdefault("title", f"Продукт {n}")
    extra.setdefault("slug", f"product-{n}")
    extra.setdefault("short_description", "Краткое описание")
    extra.setdefault("description", "Полное описание продукта")
    extra.setdefault("source_repo_full_name", f"demo-seller/repo-{n}")
    p = Product(seller_id=seller.id, category_id=category.id, status=status, price=Decimal(price), **extra)
    if status == "published" and p.published_at is None:
        p.published_at = utcnow()
    db.add(p)
    db.flush()
    db.refresh(p)
    return p

"""Роутеры API. У каждого свой префикс /api/..."""

from . import admin, auth, catalog, github, seller

ROUTERS = [auth.router, catalog.router, seller.router, admin.router, github.router]

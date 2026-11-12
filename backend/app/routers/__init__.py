"""Роутеры API. Порядок подключения не важен: у всех свой префикс /api/..."""

from . import auth

ROUTERS = [auth.router]

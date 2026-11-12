"""Роутеры API. У каждого свой префикс /api/..."""

from . import account, admin, admin_more, auth, catalog, github, orders, payments, purchases, seller

ROUTERS = [
    auth.router,
    catalog.router,
    purchases.router,
    payments.router,
    orders.router,
    account.router,
    seller.router,
    admin.router,
    admin_more.router,
    github.router,
]

"""Сервисы заказов на доработку (полностью реализуются на этапе 8)."""


def public_questions(product):
    """Публичные вопросы по продукту и первые ответы продавца."""
    return []


def handle_seller_blocked(seller, admin=None):
    """Обработать заказы заблокированного продавца (правило из 7.4)."""
    return 0


def orders_for_purchase(purchase):
    """Заказы доработки по покупке."""
    return []


def on_payment_succeeded(order):
    """Оплата заказа подтверждена (этап 8)."""
    return order

"""Сервисы покупок (полностью реализуются на этапе 7)."""


def has_access(user, product):
    """Есть ли у пользователя действующая покупка продукта."""
    return False


def product_has_purchases(product):
    """Есть ли у продукта хоть одна оплаченная покупка."""
    return False


def active_purchase(user, product):
    """Действующая покупка пользователя (paid/completed/dispute) или None."""
    return None


def notify_new_version(product, version):
    """Уведомить покупателей о новой одобренной версии."""
    return 0

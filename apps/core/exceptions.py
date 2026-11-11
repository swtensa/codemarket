class InvalidTransition(Exception):
    """Недопустимый переход статуса (бросают сервисные функции)."""


class ServiceError(Exception):
    """Нарушение бизнес-правила, текст показывается пользователю."""

"""Исключения бизнес-логики и их перевод в ответы API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ServiceError(Exception):
    """Нарушение правила, текст показывается пользователю (400)."""

    status_code = 400

    def __init__(self, message: str = "Действие недоступно", fields: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}


class InvalidTransition(ServiceError):
    """Недопустимый переход статуса (409)."""

    status_code = 409


class NotFound(ServiceError):
    """Объект не найден или чужой (404 — не раскрываем, что он существует)."""

    status_code = 404

    def __init__(self, message: str = "Не найдено"):
        super().__init__(message)


class Forbidden(ServiceError):
    status_code = 403

    def __init__(self, message: str = "Доступ запрещён"):
        super().__init__(message)


class Unauthorized(ServiceError):
    status_code = 401

    def __init__(self, message: str = "Войдите, чтобы продолжить"):
        super().__init__(message)


class FieldsError(ServiceError):
    """Ошибки отдельных полей формы (422)."""

    status_code = 422

    def __init__(self, fields: dict[str, str]):
        super().__init__(next(iter(fields.values())), fields)


_PYDANTIC_RU = {
    "missing": "Обязательное поле.",
    "string_too_short": "Слишком короткое значение.",
    "string_too_long": "Слишком длинное значение.",
    "value_error": None,
    "int_parsing": "Введите целое число.",
    "decimal_parsing": "Введите число.",
    "float_parsing": "Введите число.",
    "greater_than_equal": "Слишком маленькое значение.",
    "less_than_equal": "Слишком большое значение.",
    "url_parsing": "Введите правильный адрес.",
    "url_scheme": "Введите правильный адрес.",
    "bool_parsing": "Неверное значение.",
}


def _ru(err: dict) -> str:
    kind = err.get("type", "")
    text = _PYDANTIC_RU.get(kind)
    if text:
        return text
    msg = err.get("msg", "Неверное значение.")
    return msg.removeprefix("Value error, ").removeprefix("Assertion failed, ")


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError):
        body: dict = {"detail": exc.message}
        if exc.fields:
            body["fields"] = exc.fields
        return JSONResponse(body, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        detail = []
        for err in exc.errors():
            loc = [str(x) for x in err.get("loc", ()) if x not in ("body", "query", "path", "form")]
            name = ".".join(loc) or "__all__"
            text = _ru(err)
            fields.setdefault(name, text)
            detail.append({"loc": loc, "msg": text})
        return JSONResponse({"detail": detail, "fields": fields}, status_code=422)

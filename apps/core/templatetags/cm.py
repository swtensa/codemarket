"""Фильтры шаблонов: деньги, даты, статусы, звёзды."""

from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Цвет статуса: success / warning / danger / neutral
STATUS_TONE = {
    # продукт
    "draft": "neutral",
    "checking": "warning",
    "moderation": "warning",
    "published": "success",
    "rejected": "danger",
    "hidden": "neutral",
    "blocked": "danger",
    # версия
    "rejected_auto": "danger",
    "appeal": "warning",
    "approved": "success",
    # покупка
    "pending": "warning",
    "paid": "success",
    "completed": "success",
    "cancelled": "neutral",
    "dispute": "danger",
    "refunded": "danger",
    "partially_refunded": "danger",
    # заказ
    "new": "warning",
    "offer": "warning",
    "awaiting_payment": "warning",
    "in_work": "warning",
    "submitted": "warning",
    "revision": "warning",
    "accepted": "success",
    # баланс
    "held": "warning",
    "available": "success",
    "requested": "warning",
    # доступ
    "none": "neutral",
    "invited": "warning",
    "granted": "success",
    "revoked": "danger",
    # спор
    "open": "danger",
    "closed": "neutral",
    "active": "success",
    "succeeded": "success",
    "canceled": "neutral",
    "failed": "danger",
}


def format_money(value):
    try:
        d = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if d == d.to_integral_value():
        s = f"{int(d):,}".replace(",", " ")
    else:
        s = f"{d:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} ₽"


@register.filter
def money(value):
    """12500 → «12 500 ₽»."""
    return format_money(value)


@register.filter
def dt(value):
    """Дата и время в формате ДД.ММ.ГГГГ ЧЧ:ММ в местном поясе."""
    if not value:
        return "—"
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d.%m.%Y %H:%M")


@register.filter
def d(value):
    if not value:
        return "—"
    if hasattr(value, "tzinfo") and value.tzinfo and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d.%m.%Y")


@register.simple_tag
def status_badge(value, label=None):
    tone = STATUS_TONE.get(value, "neutral")
    icon = {"danger": "bi-exclamation-octagon", "success": "bi-check-circle", "warning": "bi-hourglass-split"}.get(
        tone, "bi-dot"
    )
    return format_html(
        '<span class="cm-status cm-status-{}"><i class="bi {}" aria-hidden="true"></i> {}</span>',
        tone,
        icon,
        label or value,
    )


@register.filter
def stars(value):
    """Пять звёзд с заполнением по рейтингу."""
    try:
        r = float(value or 0)
    except (TypeError, ValueError):
        r = 0
    parts = []
    for i in range(1, 6):
        if r >= i - 0.25:
            parts.append('<i class="bi bi-star-fill"></i>')
        elif r >= i - 0.75:
            parts.append('<i class="bi bi-star-half"></i>')
        else:
            parts.append('<i class="bi bi-star"></i>')
    return mark_safe(f'<span class="cm-stars" aria-label="Рейтинг {r:.1f} из 5">{"".join(parts)}</span>')


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Сохраняет GET-параметры фильтров, меняя только переданные."""
    q = context["request"].GET.copy()
    for k, v in kwargs.items():
        if v is None or v == "":
            q.pop(k, None)
        else:
            q[k] = v
    return q.urlencode()


@register.filter
def similarity_tone(value):
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0
    if v >= 0.7:
        return "danger"
    if v >= 0.3:
        return "warning"
    return "success"


@register.filter
def percent(value):
    try:
        return f"{float(value) * 100:.0f} %"
    except (TypeError, ValueError):
        return "—"


@register.filter
def plural_ru(n, forms):
    """{{ n|plural_ru:"отзыв,отзыва,отзывов" }}"""
    one, few, many = forms.split(",")
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.filter
def styled(bound_field):
    """Отрисовать виджет поля с классами Bootstrap и отметкой ошибки."""
    from django import forms

    w = bound_field.field.widget
    invalid = " is-invalid" if bound_field.errors else ""
    if isinstance(w, forms.CheckboxInput):
        css = "form-check-input"
    elif isinstance(w, forms.Select | forms.SelectMultiple) and not isinstance(w, forms.CheckboxSelectMultiple):
        css = "form-select"
    else:
        css = "form-control"
    attrs = {"class": (w.attrs.get("class", "") + " " + css + invalid).strip()}
    if bound_field.field.required and not isinstance(w, forms.CheckboxInput):
        attrs["aria-required"] = "true"
    return bound_field.as_widget(attrs=attrs)

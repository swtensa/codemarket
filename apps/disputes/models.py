from django.conf import settings
from django.db import models
from django.db.models import Q


class Dispute(models.Model):
    """Спор по покупке или по заказу (ровно одно из двух)."""

    class ReasonType(models.TextChoices):
        NOT_WORKING = "not_working", "Не работает"
        NOT_AS_DESCRIBED = "not_as_described", "Не соответствует описанию"
        OTHER = "other", "Другое"
        SELLER_BLOCKED = "seller_blocked", "Продавец заблокирован"

    class Status(models.TextChoices):
        OPEN = "open", "Открыт"
        CLOSED = "closed", "Закрыт"

    class Resolution(models.TextChoices):
        SELLER = "seller", "В пользу продавца"
        REFUND = "refund", "Полный возврат"
        PARTIAL = "partial", "Частичный возврат"

    purchase = models.ForeignKey(
        "purchases.Purchase", null=True, blank=True, on_delete=models.PROTECT, related_name="disputes"
    )
    order = models.ForeignKey(
        "orders.CustomOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="disputes"
    )
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason_type = models.CharField("причина", max_length=20, choices=ReasonType.choices)
    reason = models.TextField("описание проблемы")
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField("решение", max_length=10, choices=Resolution.choices, blank=True)
    refund_amount = models.DecimalField("сумма возврата", max_digits=12, decimal_places=2, default=0)
    admin_comment = models.TextField("комментарий администратора", blank=True)
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        verbose_name = "спор"
        verbose_name_plural = "споры"
        constraints = [
            models.CheckConstraint(
                condition=(Q(purchase__isnull=False) & Q(order__isnull=True))
                | (Q(purchase__isnull=True) & Q(order__isnull=False)),
                name="dispute_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=["purchase"], condition=Q(purchase__isnull=False), name="dispute_one_per_purchase"
            ),
            models.UniqueConstraint(fields=["order"], condition=Q(order__isnull=False), name="dispute_one_per_order"),
        ]

    def __str__(self):
        target = f"покупке №{self.purchase_id}" if self.purchase_id else f"заказу №{self.order_id}"
        return f"Спор по {target}"

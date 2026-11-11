from django.db import models
from django.db.models import Q


class Payment(models.Model):
    """Платёж у провайдера: за покупку продукта или за заказ доработки."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        SUCCEEDED = "succeeded", "Оплачен"
        CANCELED = "canceled", "Отменён"
        REFUNDED = "refunded", "Возвращён"
        PARTIALLY_REFUNDED = "partially_refunded", "Возвращён частично"

    purchase = models.ForeignKey(
        "purchases.Purchase", null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
    order = models.ForeignKey(
        "orders.CustomOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField("сумма", max_digits=12, decimal_places=2)
    external_id = models.CharField("id у провайдера", max_length=100, blank=True, db_index=True)
    idempotence_key = models.CharField("ключ идемпотентности", max_length=64, unique=True)
    confirmation_url = models.URLField("ссылка на оплату", max_length=500, blank=True)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    refund_amount = models.DecimalField("сумма возврата", max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "платёж"
        verbose_name_plural = "платежи"
        constraints = [
            models.CheckConstraint(
                condition=Q(purchase__isnull=False) | Q(order__isnull=False), name="payment_has_purchase_or_order"
            ),
        ]

    def __str__(self):
        return f"Платёж №{self.pk} {self.amount} ({self.status})"

from django.conf import settings
from django.db import models
from django.db.models import Q


class Purchase(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        PAID = "paid", "Оплачена"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"
        DISPUTE = "dispute", "Спор"
        REFUNDED = "refunded", "Возврат"
        PARTIALLY_REFUNDED = "partially_refunded", "Частичный возврат"

    class Access(models.TextChoices):
        NONE = "none", "Не выдан"
        INVITED = "invited", "Приглашение отправлено"
        GRANTED = "granted", "Доступ есть"
        REVOKED = "revoked", "Отозван"

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchases", verbose_name="покупатель"
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="purchases", verbose_name="продукт"
    )
    version = models.ForeignKey(
        "versions.ProductVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    price = models.DecimalField("цена", max_digits=12, decimal_places=2)
    commission = models.DecimalField("комиссия", max_digits=12, decimal_places=2)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    access_status = models.CharField("доступ", max_length=10, choices=Access.choices, default=Access.NONE)
    access_granted_at = models.DateTimeField(null=True, blank=True)
    access_revoked_at = models.DateTimeField(null=True, blank=True)
    license_version = models.CharField("версия лицензии", max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "покупка"
        verbose_name_plural = "покупки"
        constraints = [
            models.UniqueConstraint(
                fields=["buyer", "product"],
                condition=Q(status__in=["paid", "completed"]),
                name="purchase_one_active_per_buyer_product",
            ),
        ]
        indexes = [models.Index(fields=["status", "paid_at"]), models.Index(fields=["product", "status"])]

    def __str__(self):
        return f"Покупка №{self.pk}: {self.product}"

    @property
    def seller_amount(self):
        return self.price - self.commission

from django.conf import settings
from django.db import models


class BalanceOperation(models.Model):
    """Операция баланса продавца. Баланс считается только из операций (get_balance), двойного учёта нет.

    income — начисление продавцу (цена − комиссия), положительная сумма;
    commission — комиссия платформы с этой продажи (для отчётов, в баланс продавца не входит);
    refund_reversal — отмена начисления при возврате, отрицательная сумма;
    payout — вывод денег, отрицательная сумма.
    """

    class Kind(models.TextChoices):
        INCOME = "income", "Начисление"
        COMMISSION = "commission", "Комиссия платформы"
        REFUND_REVERSAL = "refund_reversal", "Отмена начисления"
        PAYOUT = "payout", "Вывод"

    class Status(models.TextChoices):
        HELD = "held", "Удержано"
        AVAILABLE = "available", "Доступно"
        REQUESTED = "requested", "Заявка на вывод"
        PAID = "paid", "Выплачено"
        CANCELLED = "cancelled", "Отменено"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="balance_operations")
    purchase = models.ForeignKey(
        "purchases.Purchase", null=True, blank=True, on_delete=models.PROTECT, related_name="balance_operations"
    )
    order = models.ForeignKey(
        "orders.CustomOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="balance_operations"
    )
    kind = models.CharField("тип", max_length=20, choices=Kind.choices)
    amount = models.DecimalField("сумма", max_digits=12, decimal_places=2)
    status = models.CharField("статус", max_length=10, choices=Status.choices)
    available_at = models.DateTimeField("доступно с", null=True, blank=True)
    requisites = models.TextField("реквизиты", blank=True)
    processed_at = models.DateTimeField("обработано", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "операция баланса"
        verbose_name_plural = "операции баланса"
        indexes = [models.Index(fields=["user", "status"]), models.Index(fields=["status", "available_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} ({self.status})"

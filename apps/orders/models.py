from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.storage import private_storage

ORDER_MIN_PRICE = 300
ORDER_MIN_DAYS = 1
ORDER_MAX_DAYS = 60


class CustomOrder(models.Model):
    """Заказ на доработку. Вопрос до покупки — тоже заказ (kind=question) без оплаты."""

    class Kind(models.TextChoices):
        QUESTION = "question", "Вопрос продавцу"
        WITH_PURCHASE = "with_purchase", "Покупка с доработкой"
        CUSTOMIZATION = "customization", "Доработка купленного продукта"

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        OFFER = "offer", "Предложение"
        AWAITING_PAYMENT = "awaiting_payment", "Ожидает оплаты"
        IN_WORK = "in_work", "В работе"
        SUBMITTED = "submitted", "Сдан"
        REVISION = "revision", "На доработке"
        ACCEPTED = "accepted", "Принят"
        CANCELLED = "cancelled", "Отменён"
        REFUNDED = "refunded", "Возврат"
        PARTIALLY_REFUNDED = "partially_refunded", "Частичный возврат"
        DISPUTE = "dispute", "Спор"

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name="покупатель"
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="orders")
    purchase = models.ForeignKey(
        "purchases.Purchase", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    kind = models.CharField("тип", max_length=20, choices=Kind.choices)
    task = models.TextField("задача")
    price = models.DecimalField("цена доработки", max_digits=12, decimal_places=2, null=True, blank=True)
    days = models.PositiveSmallIntegerField("срок, дней", null=True, blank=True)
    deadline = models.DateTimeField("крайний срок", null=True, blank=True)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.NEW)
    revisions = models.PositiveSmallIntegerField("возвратов на доработку", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "заказ на доработку"
        verbose_name_plural = "заказы на доработку"
        constraints = [
            models.CheckConstraint(
                condition=Q(price__isnull=True) | Q(price__gte=ORDER_MIN_PRICE), name="order_price_min"
            ),
            models.CheckConstraint(
                condition=Q(days__isnull=True) | Q(days__gte=ORDER_MIN_DAYS, days__lte=ORDER_MAX_DAYS),
                name="order_days_range",
            ),
        ]
        indexes = [models.Index(fields=["status", "submitted_at"]), models.Index(fields=["buyer", "kind"])]

    def __str__(self):
        return f"Заказ №{self.pk}: {self.product}"

    @property
    def seller(self):
        return self.product.seller

    @property
    def seller_id(self):
        return self.product.seller_id


def attachment_upload_to(instance, filename):
    return f"attachments/{instance.order_id}/{filename}"


class Message(models.Model):
    """Сообщение в чате заказа. author пустой — системное сообщение (смена статуса)."""

    order = models.ForeignKey(CustomOrder, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    text = models.TextField("текст", blank=True)
    attachment = models.FileField(
        "вложение", storage=private_storage, upload_to=attachment_upload_to, blank=True, max_length=300
    )
    is_result = models.BooleanField("результат", default=False)
    is_read = models.BooleanField("прочитано", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "сообщение"
        verbose_name_plural = "сообщения"

    def __str__(self):
        return (self.text or "вложение")[:50]

    @property
    def attachment_name(self):
        return self.attachment.name.rsplit("/", 1)[-1] if self.attachment else ""

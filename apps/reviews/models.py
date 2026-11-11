from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Review(models.Model):
    """Отзыв о продукте (по покупке) или о доработке (по заказу)."""

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews")
    purchase = models.ForeignKey(
        "purchases.Purchase", null=True, blank=True, on_delete=models.CASCADE, related_name="reviews"
    )
    order = models.ForeignKey(
        "orders.CustomOrder", null=True, blank=True, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField("оценка", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("текст", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "отзыв"
        verbose_name_plural = "отзывы"
        constraints = [
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_1_5"),
            models.CheckConstraint(
                condition=(Q(purchase__isnull=False) & Q(order__isnull=True))
                | (Q(purchase__isnull=True) & Q(order__isnull=False)),
                name="review_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=["purchase"], condition=Q(purchase__isnull=False), name="review_one_per_purchase"
            ),
            models.UniqueConstraint(fields=["order"], condition=Q(order__isnull=False), name="review_one_per_order"),
        ]

    def __str__(self):
        return f"{self.rating}★ от {self.author}"

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Уведомление на сайте (почта не используется)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    text = models.CharField("текст", max_length=500)
    link = models.CharField("ссылка", max_length=300, blank=True)
    is_read = models.BooleanField("прочитано", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]
        verbose_name = "уведомление"
        verbose_name_plural = "уведомления"

    def __str__(self):
        return self.text

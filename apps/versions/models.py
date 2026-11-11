from django.db import models

from apps.core.storage import private_storage


def archive_upload_to(instance, filename):
    return f"versions/{instance.product_id}/{instance.tag_name}.zip"


class ProductVersion(models.Model):
    class Status(models.TextChoices):
        CHECKING = "checking", "Проверяется"
        REJECTED_AUTO = "rejected_auto", "Отклонена автоматически"
        APPEAL = "appeal", "Обжалование"
        MODERATION = "moderation", "На модерации"
        APPROVED = "approved", "Одобрена"
        REJECTED = "rejected", "Отклонена"

    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="versions")
    tag_name = models.CharField("тег", max_length=100)
    commit_sha = models.CharField("коммит", max_length=40, blank=True)
    archive = models.FileField("архив", storage=private_storage, upload_to=archive_upload_to, max_length=300)
    size = models.PositiveBigIntegerField("размер, байт", default=0)
    files_count = models.PositiveIntegerField("файлов", default=0)
    status = models.CharField("статус", max_length=15, choices=Status.choices, default=Status.CHECKING)
    similarity = models.FloatField("коэффициент сходства", null=True, blank=True)
    flagged = models.BooleanField("отмечена", default=False)
    admin_comment = models.TextField("комментарий модератора", blank=True)
    appeal_text = models.TextField("текст обжалования", blank=True)
    check_error = models.TextField("ошибка проверки", blank=True)
    released_at = models.DateTimeField("дата релиза", null=True, blank=True)
    approved_at = models.DateTimeField("одобрена", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "версия продукта"
        verbose_name_plural = "версии продуктов"
        constraints = [models.UniqueConstraint(fields=["product", "tag_name"], name="version_unique_tag")]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.product} {self.tag_name}"

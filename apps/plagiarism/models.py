from django.db import models


class CodeFingerprint(models.Model):
    """Отпечаток (winnowing) файла версии. Индекс по hash обязателен для поиска кандидатов."""

    hash = models.BigIntegerField(db_index=True)
    version = models.ForeignKey("versions.ProductVersion", on_delete=models.CASCADE, related_name="fingerprints")
    file_path = models.CharField(max_length=500)
    position = models.PositiveIntegerField()

    class Meta:
        verbose_name = "отпечаток кода"
        verbose_name_plural = "отпечатки кода"
        indexes = [models.Index(fields=["version", "hash"])]

    def __str__(self):
        return f"{self.hash} {self.file_path}:{self.position}"


class VersionMatch(models.Model):
    """Совпадение проверяемой версии с одобренной версией другого продавца (S ≥ 0.1)."""

    version = models.ForeignKey("versions.ProductVersion", on_delete=models.CASCADE, related_name="matches")
    matched_version = models.ForeignKey("versions.ProductVersion", on_delete=models.CASCADE, related_name="+")
    similarity = models.FloatField()
    common_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-similarity"]
        verbose_name = "совпадение версий"
        verbose_name_plural = "совпадения версий"

    def __str__(self):
        return f"{self.version_id} ~ {self.matched_version_id}: {self.similarity:.2f}"

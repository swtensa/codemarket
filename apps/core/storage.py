"""Закрытое файловое хранилище (архивы версий, вложения чата).

Лежит в PRIVATE_ROOT вне MEDIA_ROOT, не раздаётся веб-сервером:
файлы отдаются только через view с проверкой права.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    @property
    def base_location(self):
        return str(settings.PRIVATE_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Закрытые файлы не имеют публичного адреса")


private_storage = PrivateStorage()

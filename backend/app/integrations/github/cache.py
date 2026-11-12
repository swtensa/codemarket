"""Кэш в памяти процесса (токены установки GitHub App живут 50 минут)."""

import time


class _Cache:
    def __init__(self):
        self._data = {}

    def get(self, key):
        item = self._data.get(key)
        if item is None or item[1] < time.monotonic():
            self._data.pop(key, None)
            return None
        return item[0]

    def set(self, key, value, ttl):
        self._data[key] = (value, time.monotonic() + ttl)


cache = _Cache()

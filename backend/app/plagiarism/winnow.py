"""Хеши k-грамм (кольцевой хеш Карпа – Рабина) и winnowing (Schleimer, Wilkerson, Aiken, 2003).

Чистые функции. Гарантия алгоритма: любой общий фрагмент длиной
не меньше t = w + k − 1 токенов даёт хотя бы один общий отпечаток.
"""

import zlib

MOD = (1 << 61) - 1  # простое число Мерсенна, хеш помещается в BigIntegerField
BASE = 1_000_003


def token_ids(tokens):
    """Перевести токены в устойчивые числа (crc32 не зависит от запуска Python)."""
    return [zlib.crc32(t.encode("utf-8")) + 1 for t in tokens]


def kgram_hashes(tokens, k):
    """Хеши всех k-грамм последовательности токенов (кольцевой хеш Карпа – Рабина).

    Возвращает список длины len(tokens) − k + 1 (пустой, если токенов меньше k).
    """
    ids = token_ids(tokens)
    n = len(ids)
    if n < k:
        return []
    high = pow(BASE, k - 1, MOD)
    h = 0
    for x in ids[:k]:
        h = (h * BASE + x) % MOD
    out = [h]
    for i in range(k, n):
        h = ((h - ids[i - k] * high) * BASE + ids[i]) % MOD
        out.append(h)
    return out


def winnow(hashes, w):
    """Отобрать отпечатки: в каждом окне из w хешей — минимальный (самый правый при равенстве).

    Один и тот же хеш на одной позиции не добавляется дважды подряд.
    Возвращает список (хеш, позиция k-граммы). Для коротких файлов (хешей меньше w)
    берётся минимальный хеш, чтобы файл тоже участвовал в сравнении.
    """
    n = len(hashes)
    if n == 0:
        return []
    if n < w:
        j = min(range(n), key=lambda i: (hashes[i], -i))
        return [(hashes[j], j)]
    result = []
    last = -1
    for start in range(n - w + 1):
        j = start
        best = hashes[start]
        for i in range(start + 1, start + w):
            if hashes[i] <= best:
                best, j = hashes[i], i
        if j != last:
            result.append((best, j))
            last = j
    return result


def fingerprint(tokens, k, w):
    """Отпечатки последовательности токенов: список (хеш, позиция)."""
    return winnow(kgram_hashes(tokens, k), w)

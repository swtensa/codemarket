"""Сравнение наборов отпечатков (чистые функции)."""

from .files import collect_source_files
from .known_libs import library_kgrams
from .tokenize import tokenize
from .winnow import fingerprint


def similarity(fa, fb):
    """S = |FA ∩ FB| / min(|FA|, |FB|). Пустой набор даёт 0."""
    fa, fb = set(fa), set(fb)
    if not fa or not fb:
        return 0.0
    return len(fa & fb) / min(len(fa), len(fb))


def fingerprint_files(files, k, w):
    """Отпечатки набора файлов: {путь: [(хеш, позиция), ...]}. k-граммы не пересекают границы файлов.

    Отпечатки кода известных библиотек (эталоны в libs/) отбрасываются; файл, в котором
    не осталось своих отпечатков, в результат не попадает.
    """
    lib = library_kgrams(k)
    out = {}
    for path, text in files:
        fps = [(h, pos) for h, pos in fingerprint(tokenize(path, text), k, w) if h not in lib]
        if fps:
            out[path] = fps
    return out


def fingerprint_dir(root, k, w):
    """Отпечатки всех проверяемых файлов папки."""
    return fingerprint_files(collect_source_files(root), k, w)


def hash_set(per_file):
    """Объединённое множество хешей по всем файлам."""
    return {h for fps in per_file.values() for h, _ in fps}


def compare_dirs(dir_a, dir_b, k, w):
    """Сравнить две папки: (S, |FA|, |FB|, общих)."""
    fa = hash_set(fingerprint_dir(dir_a, k, w))
    fb = hash_set(fingerprint_dir(dir_b, k, w))
    return similarity(fa, fb), len(fa), len(fb), len(fa & fb)


def verdict(s, reject, flag):
    """Решение по коэффициенту: rejected_auto / flagged / ok."""
    if s >= reject:
        return "rejected_auto"
    if s >= flag:
        return "flagged"
    return "ok"

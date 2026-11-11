"""Безопасная работа с zip-архивами: защита от zip-bomb и путей «../»."""

import os
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings


class ArchiveError(Exception):
    pass


MAX_RATIO = 200  # во сколько раз файл может быть больше сжатого


def _limits():
    return settings.MAX_ARCHIVE_MB * 1024 * 1024, settings.MAX_FILES


def _safe_name(name):
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
        raise ArchiveError(f"Недопустимый путь в архиве: {name}")
    return p


def inspect_zip(path):
    """Проверить архив, вернуть (число файлов, распакованный размер).

    Ошибка, если файлов больше MAX_FILES, распакованный размер больше
    MAX_ARCHIVE_MB × 4, есть пути с «..» или подозрительная степень сжатия.
    """
    max_bytes, max_files = _limits()
    if os.path.getsize(path) > max_bytes:
        raise ArchiveError(f"Архив больше {settings.MAX_ARCHIVE_MB} МБ")
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise ArchiveError("Файл не является zip-архивом") from e
    with zf:
        files = [i for i in zf.infolist() if not i.is_dir()]
        if len(files) > max_files:
            raise ArchiveError(f"В архиве больше {max_files} файлов")
        total = 0
        for i in files:
            _safe_name(i.filename)
            total += i.file_size
            if i.compress_size and i.file_size / i.compress_size > MAX_RATIO and i.file_size > 1024 * 1024:
                raise ArchiveError("Подозрительно сильное сжатие (zip-bomb)")
        if total > max_bytes * 4:
            raise ArchiveError("Распакованный архив слишком большой")
    return len(files), total


def strip_root(names):
    """GitHub кладёт всё в одну корневую папку owner-repo-sha/: найти её префикс."""
    tops = {PurePosixPath(n).parts[0] for n in names if PurePosixPath(n).parts}
    if len(tops) == 1 and all(len(PurePosixPath(n).parts) > 1 for n in names):
        return tops.pop() + "/"
    return ""


def list_files(path):
    """Пути файлов архива без корневой папки zipball."""
    with zipfile.ZipFile(path) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
    prefix = strip_root(names)
    return sorted(n[len(prefix) :] for n in names)


def read_file(path, inner_path, max_bytes=1024 * 1024):
    """Прочитать один файл архива (inner_path без корневой папки)."""
    _safe_name(inner_path)
    with zipfile.ZipFile(path) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        prefix = strip_root(names)
        info = zf.getinfo(prefix + inner_path)
        if info.file_size > max_bytes:
            raise ArchiveError("Файл слишком большой для просмотра")
        return zf.read(info)


def extract_safe(path, dest):
    """Распаковать архив в dest без корневой папки, с проверкой путей."""
    inspect_zip(path)
    dest = Path(dest).resolve()
    with zipfile.ZipFile(path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        prefix = strip_root([i.filename for i in infos])
        for info in infos:
            rel = _safe_name(info.filename[len(prefix) :])
            target = (dest / rel).resolve()
            if dest not in target.parents:
                raise ArchiveError(f"Недопустимый путь в архиве: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
    return dest

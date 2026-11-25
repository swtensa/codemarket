"""Отбор файлов архива для проверки.

Отбрасываются бинарные файлы, изображения, шрифты, служебные папки,
минифицированные файлы, файлы больше 1 МБ и известные библиотеки.
"""

import hashlib
from pathlib import Path

from . import known_libs
from .tokenize import supported_extension

MAX_FILE_BYTES = 1024 * 1024
MAX_LINE = 1000

BINARY_EXT = {
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "svg", "tiff", "psd", "ai",
    "woff", "woff2", "ttf", "otf", "eot",
    "zip", "rar", "7z", "gz", "tar", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "mp3", "mp4", "webm", "avi", "mov", "wav", "ogg",
    "exe", "dll", "so", "pyc", "class", "jar", "db", "sqlite", "sqlite3",
}  # fmt: skip


def _is_binary(data):
    if b"\0" in data[:8192]:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            data.decode("cp1251")
        except UnicodeDecodeError:
            return True
    return False


def decode(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def skip_reason(rel_path, data):
    """Причина пропуска файла или None, если файл нужно проверять."""
    parts = rel_path.split("/")
    if any(p in known_libs.SKIP_DIRS for p in parts[:-1]):
        return "служебная папка"
    name = parts[-1].lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in BINARY_EXT:
        return "бинарный файл"
    if name.endswith((".min.js", ".min.css")):
        return "минифицированный файл"
    if known_libs.is_known_lib_name(name):
        return "известная библиотека"
    if not supported_extension(name):
        return "неподдерживаемый тип"
    if len(data) > MAX_FILE_BYTES:
        return "больше 1 МБ"
    if _is_binary(data):
        return "бинарный файл"
    if known_libs.is_known_lib_hash(hashlib.sha256(data).hexdigest()):
        return "известная библиотека"
    if any(len(line) > MAX_LINE for line in decode(data).splitlines()):
        return "минифицированный файл"
    return None


def collect_source_files(root):
    """Вернуть [(относительный путь, текст)] файлов папки, которые участвуют в проверке."""
    root = Path(root)
    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if skip_reason(rel, data) is None:
            out.append((rel, decode(data)))
    return out

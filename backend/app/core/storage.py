"""Файлы: storage/public (скриншоты, раздаются по /media/) и storage/private (архивы, вложения — только через API)."""

import re
import uuid
from pathlib import Path

from .config import settings


def _clean_name(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    stem = re.sub(r"[^\w.-]+", "_", stem or ext)[:80] or "file"
    return f"{stem}.{ext.lower()}" if dot else stem


def _save(root: Path, folder: str, filename: str, data: bytes, unique: bool) -> str:
    name = _clean_name(filename)
    if unique:
        stem, dot, ext = name.rpartition(".")
        name = f"{stem or ext}_{uuid.uuid4().hex[:8]}" + (f".{ext}" if dot else "")
    rel = f"{folder.strip('/')}/{name}"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def save_public(folder: str, filename: str, data: bytes, unique: bool = True) -> str:
    return _save(settings.storage_public, folder, filename, data, unique)


def save_private(folder: str, filename: str, data: bytes, unique: bool = True) -> str:
    return _save(settings.storage_private, folder, filename, data, unique)


def public_path(rel: str) -> Path:
    return settings.storage_public / rel


def private_path(rel: str) -> Path:
    """Путь закрытого файла; выход за пределы storage/private запрещён."""
    root = settings.storage_private.resolve()
    path = (root / rel).resolve()
    if root not in path.parents:
        raise ValueError("Недопустимый путь")
    return path


def delete_public(rel: str) -> None:
    if rel:
        public_path(rel).unlink(missing_ok=True)


def delete_private(rel: str) -> None:
    if rel:
        private_path(rel).unlink(missing_ok=True)

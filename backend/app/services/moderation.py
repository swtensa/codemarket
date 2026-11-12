"""Панель администратора: счётчики меню, просмотр кода версии с подсветкой Pygments."""

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.archive import ArchiveError, list_files, read_file
from app.models import BalanceOperation, Dispute, ProductVersion, VersionStatus
from app.plagiarism.files import decode
from app.services.versions import archive_path

FORMATTER = HtmlFormatter(linenos="table", cssclass="highlight", wrapcode=True)
MAX_VIEW_BYTES = 512 * 1024


def menu_counts(db: Session) -> dict[str, int]:
    """Числа ожидающих задач для левого меню модерации."""
    return {
        "versions": db.scalar(
            select(func.count()).where(ProductVersion.status.in_([VersionStatus.MODERATION, VersionStatus.APPEAL]))
        )
        or 0,
        "disputes": db.scalar(select(func.count()).where(Dispute.status == "open")) or 0,
        "payouts": db.scalar(
            select(func.count()).where(BalanceOperation.kind == "payout", BalanceOperation.status == "requested")
        )
        or 0,
    }


def file_tree(version: ProductVersion) -> list[dict]:
    """Файлы архива версии деревом: [{depth, name, path (None у папки)}]."""
    try:
        paths = list_files(archive_path(version))
    except (ArchiveError, OSError, ValueError):
        return []
    tree, seen = [], set()
    for path in paths:
        parts = path.split("/")
        for depth in range(len(parts) - 1):
            folder = "/".join(parts[: depth + 1])
            if folder not in seen:
                seen.add(folder)
                tree.append({"depth": depth, "name": parts[depth], "path": None})
        tree.append({"depth": len(parts) - 1, "name": parts[-1], "path": path})
    return tree


def render_file(version: ProductVersion, path: str) -> tuple[str | None, str | None]:
    """Подсветить файл версии Pygments. Возвращает (html, ошибка)."""
    try:
        data = read_file(archive_path(version), path, max_bytes=MAX_VIEW_BYTES)
    except KeyError:
        return None, "Файл не найден в архиве."
    except ArchiveError as e:
        return None, str(e)
    if b"\0" in data[:8192]:
        return None, "Бинарный файл, просмотр недоступен."
    text = decode(data)
    try:
        lexer = get_lexer_for_filename(path, stripnl=False)
    except ClassNotFound:
        lexer = TextLexer()
    return highlight(text, lexer, FORMATTER), None


def highlight_css() -> str:
    return FORMATTER.get_style_defs(".highlight")

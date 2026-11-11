"""Сервисы панели администратора: счётчики меню, просмотр кода версии."""

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

from apps.core.archive import ArchiveError, list_files, read_file
from apps.plagiarism.files import decode
from apps.versions import services as version_services

FORMATTER = HtmlFormatter(linenos="table", cssclass="highlight", wrapcode=True)
MAX_VIEW_BYTES = 512 * 1024


def menu_counts():
    """Числа ожидающих задач для левого меню модерации."""
    counts = {"versions": version_services.pending_versions().count(), "disputes": 0, "payouts": 0}
    try:
        from apps.disputes.services import open_disputes

        counts["disputes"] = open_disputes().count()
    except ImportError:
        pass
    try:
        from apps.balance.services import requested_payouts

        counts["payouts"] = requested_payouts().count()
    except ImportError:
        pass
    return counts


def file_tree(version):
    """Список файлов архива версии в виде дерева: [(отступ, имя, полный путь или None для папки)]."""
    try:
        paths = list_files(version.archive.path)
    except (ArchiveError, OSError, ValueError):
        return []
    tree, seen = [], set()
    for path in paths:
        parts = path.split("/")
        for depth in range(len(parts) - 1):
            folder = "/".join(parts[: depth + 1])
            if folder not in seen:
                seen.add(folder)
                tree.append((depth, parts[depth], None))
        tree.append((len(parts) - 1, parts[-1], path))
    return tree


def render_file(version, path):
    """Подсветить файл версии Pygments. Возвращает (html, ошибка)."""
    try:
        data = read_file(version.archive.path, path, max_bytes=MAX_VIEW_BYTES)
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


def highlight_css():
    return FORMATTER.get_style_defs(".highlight")

"""Токенизация и нормализация исходного кода (Pygments, без Django).

Для языков программирования идентификаторы заменяются на ID, строки на STR,
числа на NUM, комментарии и пробелы удаляются: переименование переменных
не влияет на результат.

Для HTML и CSS имена тегов, атрибутов, классов и CSS-свойств сохраняются,
нормализуются только текст (TXT), строки (STR) и значения (NUM, VAL):
иначе любые два шаблона сайта выглядели бы одинаково.
"""

from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String, Text, Whitespace

# расширение → (имя лексера Pygments, режим)
PROGRAM = "program"
MARKUP = "markup"

LANGUAGES = {
    "py": ("python", PROGRAM),
    "js": ("javascript", PROGRAM),
    "mjs": ("javascript", PROGRAM),
    "cjs": ("javascript", PROGRAM),
    "jsx": ("jsx", PROGRAM),
    "ts": ("typescript", PROGRAM),
    "tsx": ("tsx", PROGRAM),
    "php": ("php", PROGRAM),
    "java": ("java", PROGRAM),
    "go": ("go", PROGRAM),
    "rb": ("ruby", PROGRAM),
    "cs": ("csharp", PROGRAM),
    "c": ("c", PROGRAM),
    "h": ("c", PROGRAM),
    "cpp": ("cpp", PROGRAM),
    "kt": ("kotlin", PROGRAM),
    "swift": ("swift", PROGRAM),
    "rs": ("rust", PROGRAM),
    "sql": ("sql", PROGRAM),
    "html": ("html", MARKUP),
    "htm": ("html", MARKUP),
    "vue": ("html", MARKUP),
    "twig": ("html", MARKUP),
    "css": ("css", MARKUP),
    "scss": ("scss", MARKUP),
    "sass": ("sass", MARKUP),
    "less": ("less", MARKUP),
}

_lexers = {}


def extension(filename):
    name = filename.rsplit("/", 1)[-1].lower()
    return name.rsplit(".", 1)[-1] if "." in name else ""


def supported_extension(filename):
    return extension(filename) in LANGUAGES


def _lexer(name):
    if name not in _lexers:
        _lexers[name] = get_lexer_by_name(name, stripnl=False, ensurenl=False)
    return _lexers[name]


def _is_space(ttype, value):
    return ttype in Whitespace or not value.strip()


def _program_tokens(raw):
    out = []
    for ttype, value in raw:
        if ttype in Comment or _is_space(ttype, value):
            continue
        if ttype in String:
            if not out or out[-1] != "STR":
                out.append("STR")
        elif ttype in Number:
            out.append("NUM")
        elif ttype in Name:
            out.append("ID")
        elif ttype in Keyword or ttype in Operator or ttype in Punctuation:
            out.append(value.strip())
        else:
            out.append(value.strip())
    return out


# Типы, имена которых в разметке сохраняются как есть
_KEEP_MARKUP = (Name.Tag, Name.Attribute, Name.Class, Name.Entity)


def _markup_tokens(raw):
    out = []
    last_attr = None

    def push_collapsed(tok):
        if not out or out[-1] != tok:
            out.append(tok)

    for ttype, value in raw:
        if ttype in Comment or _is_space(ttype, value):
            continue
        v = value.strip()
        if ttype in Name.Attribute:
            last_attr = v.lower()
            out.append(v.lower())
        elif any(ttype in k for k in _KEEP_MARKUP):
            out.append(v.lower())
        elif ttype in String:
            words = v.strip("\"'").split() if last_attr in ("class", "id") else []
            if words:
                out.extend(f".{w}" for w in words)  # имена классов и id сохраняются
            else:
                push_collapsed("STR")
            last_attr = None
        elif ttype in Number or ttype in Keyword.Type or ttype in Keyword.Constant or ttype in Name.Decorator:
            push_collapsed("VAL")
        elif ttype in Name.Builtin:
            push_collapsed("VAL")
        elif ttype in Keyword:
            out.append(v.lower())  # CSS-свойства, @media, ключевые слова встроенного JS
        elif ttype in Name:
            out.append("ID")  # идентификаторы встроенного JS
        elif ttype in Punctuation or ttype in Operator:
            out.append(v)
        elif ttype in Text:
            push_collapsed("TXT")  # текст страницы
        else:
            push_collapsed("VAL")
    return out


def tokenize(filename, text):
    """Нормализованные токены файла (список строк). Неподдерживаемый тип → []."""
    ext = extension(filename)
    if ext not in LANGUAGES:
        return []
    lexer_name, mode = LANGUAGES[ext]
    raw = _lexer(lexer_name).get_tokens(text)
    return _program_tokens(raw) if mode == PROGRAM else _markup_tokens(raw)

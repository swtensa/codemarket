"""Известные библиотеки и служебные файлы, которые не участвуют в проверке.

Файл исключается, если его имя подходит под один из шаблонов KNOWN_LIB_PATTERNS
или SHA-256 его содержимого есть в KNOWN_SHA256. Чтобы добавить библиотеку
по содержимому, посчитайте хеш командой
    python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" файл
и добавьте строку в KNOWN_SHA256 с комментарием.
"""

import fnmatch
from functools import lru_cache
from pathlib import Path

# Шаблоны имён файлов (без учёта регистра), сравниваются с именем файла без папок.
KNOWN_LIB_PATTERNS = [
    "bootstrap*.css",
    "bootstrap*.js",
    "bootstrap*.scss",
    "_bootstrap*.scss",
    "jquery*.js",
    "normalize*.css",
    "reset.css",
    "font-awesome*",
    "fontawesome*",
    "all.min.css",
    "swiper*",
    "slick*",
    "owl.carousel*",
    "aos*.js",
    "aos*.css",
    "animate*.css",
    "popper*.js",
    "lodash*.js",
    "moment*.js",
    "chart*.js",
    "alpine*.js",
    "vue*.js",
    "react*.js",
    "react-dom*.js",
    "axios*.js",
    "gsap*.js",
    "lightbox*",
    "fancybox*",
    "glightbox*",
    "tailwind*.css",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "composer.lock",
]

# Папки, которые пропускаются целиком.
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", ".git", "__pycache__", ".venv", "venv", ".idea", ".vscode"}

# SHA-256 содержимого известных библиотечных файлов (на случай переименования файла).
KNOWN_SHA256: set[str] = set()


def is_known_lib_name(filename):
    """Подходит ли имя файла под шаблон известной библиотеки."""
    name = filename.rsplit("/", 1)[-1].lower()
    return any(fnmatch.fnmatch(name, p) for p in KNOWN_LIB_PATTERNS)


def is_known_lib_hash(sha256_hex):
    return sha256_hex in KNOWN_SHA256


# Эталонные файлы библиотек (папка libs/). Их код часто встраивают в свои файлы — например,
# шаблоны Start Bootstrap собирают весь Bootstrap в собственный css/styles.css. Отпечатки,
# совпадающие с любой k-граммой эталона, в проверке не участвуют («общий bootstrap не даёт
# совпадения»). Чтобы добавить библиотеку, положите её несжатый файл в libs/.
LIB_DIR = Path(__file__).resolve().parent / "libs"


@lru_cache(maxsize=4)
def library_kgrams(k):
    """Множество хешей всех k-грамм эталонных библиотек."""
    from .tokenize import tokenize
    from .winnow import kgram_hashes

    hashes = set()
    for path in sorted(LIB_DIR.glob("*")):
        if path.is_file():
            hashes.update(kgram_hashes(tokenize(path.name, path.read_text(encoding="utf-8")), k))
    return frozenset(hashes)

"""Проверка на заимствования (раздел 12 ТЗ): чистые функции и работа с базой данных."""

import hashlib
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from app.cli import plag_calibrate
from app.core.config import BASE_DIR, settings
from app.core.storage import private_path
from app.models import CodeFingerprint, VersionMatch
from app.plagiarism import known_libs
from app.plagiarism.files import collect_source_files, skip_reason
from app.plagiarism.similarity import compare_dirs, fingerprint_files, similarity
from app.plagiarism.tokenize import tokenize
from app.plagiarism.winnow import fingerprint, kgram_hashes, winnow
from app.services.plagiarism import check_version, matches_for_versions, process_pending
from tests.factories import make_product, make_seller
from tests.helpers import make_checked_approved, make_version

PAIRS = BASE_DIR / "fixtures" / "plag_pairs"
SB = BASE_DIR / "fixtures" / "demo" / "startbootstrap"
K, W = 15, 16


def S(pair):
    return compare_dirs(PAIRS / pair / "a", PAIRS / pair / "b", K, W)[0]


# ------------------------------------------------------------- чистые функции


def test_identical_files_give_one():
    assert S("01_identical") == 1.0


def test_renamed_variables_at_least_09():
    assert S("02_renamed_variables") >= 0.9


def test_reordered_functions_detected():
    assert S("03_reordered_functions") >= 0.7


def test_different_projects_below_03():
    assert S("04_different_projects") < 0.3


def test_shared_bootstrap_gives_no_match():
    assert S("07_shared_bootstrap") == 0.0


def test_html_templates_with_different_markup_not_copy():
    assert S("06_html_different_markup") < 0.3


def test_html_same_markup_with_new_text_is_copy():
    assert S("05_html_same_markup_new_text") >= 0.7


def test_program_normalization_ignores_names_comments_literals():
    a = tokenize("a.py", "def total(items):\n    # сумма\n    return sum(items) + 10  # x\n")
    b = tokenize("b.py", "def summa(values):\n    return sum(values) + 99\n")
    assert a == b
    assert "ID" in a and "NUM" in a and "def" in a


def test_markup_keeps_tags_and_classes_normalizes_text():
    a = tokenize("a.html", '<div class="card big"><p>Привет</p></div>')
    b = tokenize("b.html", '<div class="card big"><p>Другой текст</p></div>')
    c = tokenize("c.html", '<section class="hero"><h2>Привет</h2></section>')
    assert a == b
    assert a != c
    assert "div" in a and ".card" in a and "TXT" in a


def test_css_keeps_properties_normalizes_values():
    a = tokenize("a.css", ".btn { color: red; margin: 0 10px; }")
    b = tokenize("b.css", ".btn { color: #fff; margin: 5px 1px; }")
    assert a == b
    assert "btn" in a and "color" in a and "margin" in a


def test_kgram_hashes_and_winnow_properties():
    tokens = [str(i % 7) for i in range(100)]
    hashes = kgram_hashes(tokens, 5)
    assert len(hashes) == 96
    fps = winnow(hashes, 4)
    positions = {p for _, p in fps}
    for start in range(len(hashes) - 4 + 1):
        assert positions & set(range(start, start + 4))
    assert kgram_hashes(tokens[:3], 5) == []
    assert winnow([], 4) == []
    assert len(winnow([5, 3, 9], 4)) == 1


def test_common_fragment_guarantee():
    """Общий фрагмент длиной t = w + k − 1 токенов обязательно даёт общий отпечаток."""
    k, w = 5, 4
    common = [f"c{i}" for i in range(w + k - 1)]
    a = [f"a{i}" for i in range(40)] + common + [f"a{i}" for i in range(40, 60)]
    b = [f"b{i}" for i in range(13)] + common + [f"b{i}" for i in range(13, 30)]
    assert {h for h, _ in fingerprint(a, k, w)} & {h for h, _ in fingerprint(b, k, w)}


def test_similarity_formula():
    assert similarity({1, 2, 3, 4}, {3, 4}) == 1.0
    assert similarity({1, 2, 3, 4}, {4, 5, 6, 7}) == 0.25
    assert similarity(set(), {1}) == 0.0


@pytest.mark.parametrize(
    "path,data,reason",
    [
        ("node_modules/x/index.js", b"var a=1;", "служебная папка"),
        ("dist/app.js", b"var a=1;", "служебная папка"),
        ("js/app.min.js", b"var a=1;", "минифицированный файл"),
        ("img/logo.png", b"\x89PNG", "бинарный файл"),
        ("fonts/a.woff2", b"wOF2", "бинарный файл"),
        ("css/bootstrap.css", b".a{}", "известная библиотека"),
        ("js/jquery-3.7.1.js", b"var a;", "известная библиотека"),
        ("js/long.js", b"var a='" + b"x" * 1200 + b"';", "минифицированный файл"),
        ("big.py", b"a=1\n" * 300_000, "больше 1 МБ"),
        ("data.bin.py", b"\x00\x01\x02", "бинарный файл"),
        ("README.md", b"# readme", "неподдерживаемый тип"),
    ],
)
def test_skip_rules(path, data, reason):
    assert skip_reason(path, data) == reason


def test_known_lib_by_sha256(tmp_path, monkeypatch):
    data = b"function lib(){ return 42; }\n"
    (tmp_path / "renamed-lib.js").write_bytes(data)
    (tmp_path / "app.js").write_text("function app(){ return 1; }\n")
    monkeypatch.setattr(known_libs, "KNOWN_SHA256", {hashlib.sha256(data).hexdigest()})
    assert [p for p, _ in collect_source_files(tmp_path)] == ["app.js"]


def test_bootstrap_itself_gives_no_fingerprints():
    css = (BASE_DIR / "app" / "plagiarism" / "libs" / "bootstrap-5.3.3.css").read_text(encoding="utf-8")
    assert fingerprint_files([("css/site.css", css)], K, W) == {}


def test_different_start_bootstrap_templates_are_not_copies():
    """В styles.css шаблонов встроен весь Bootstrap — он не должен делать разные шаблоны копиями."""
    s, *_ = compare_dirs(SB / "landing-page", SB / "freelancer", K, W)
    assert s < settings.plag_flag


def test_calibrate_prints_table():
    lines = []
    plag_calibrate(out=lines.append)
    text = "\n".join(lines)
    assert "01_identical" in text and "1.000" in text and "07_shared_bootstrap" in text


def test_check_5mb_archive_fast_enough():
    """Требование: архив 5 МБ проверяется не дольше 2 минут (здесь только алгоритм)."""
    src = (PAIRS / "04_different_projects" / "b" / "backup.py").read_text(encoding="utf-8")
    files = [(f"m{i}.py", src.replace("STATE_FILE", f"STATE_{i}")) for i in range(5 * 1024 * 1024 // len(src.encode()))]
    t = time.monotonic()
    fingerprint_files(files, K, W)
    assert time.monotonic() - t < 120


# ------------------------------------------------------------- с базой данных


def read_pair(pair, side):
    base = PAIRS / pair / side
    return {p.relative_to(base).as_posix(): p.read_text(encoding="utf-8") for p in base.rglob("*") if p.is_file()}


@pytest.fixture
def approved_original(db):
    return make_checked_approved(db, make_product(db, title="Склад оригинал"), read_pair("02_renamed_variables", "a"))


def test_copy_is_rejected_automatically(db, approved_original):
    product = make_product(db, status="checking", published_at=None)
    v = make_version(db, product, read_pair("02_renamed_variables", "b"))
    s = check_version(db, v)
    assert s >= 0.9
    assert v.status == "rejected_auto" and product.status == "rejected"
    match = db.scalar(select(VersionMatch).where(VersionMatch.version_id == v.id))
    assert match.matched_version_id == approved_original.id
    assert matches_for_versions(db, [v])[v.id][0]["files_other"] == ["inventory.py"]
    assert db.scalar(select(CodeFingerprint.id).where(CodeFingerprint.version_id == v.id).limit(1))
    assert product.seller_id and any("отклонена автоматически" in n for n in _texts(db, product.seller_id))


def _texts(db, user_id):
    from app.models import Notification

    return list(db.scalars(select(Notification.text).where(Notification.user_id == user_id)))


def test_different_code_goes_to_moderation(db, approved_original):
    product = make_product(db, status="checking", published_at=None)
    v = make_version(db, product, read_pair("04_different_projects", "b"))
    check_version(db, v)
    assert v.status == "moderation" and not v.flagged
    assert product.status == "moderation"
    assert db.scalar(select(VersionMatch.id).where(VersionMatch.version_id == v.id)) is None


def test_partial_copy_is_flagged(db, approved_original):
    product = make_product(db, status="checking", published_at=None)
    files = read_pair("04_different_projects", "b")
    original = read_pair("02_renamed_variables", "a")["inventory.py"]
    files["part.py"] = original[: len(original) // 2]
    files["extra.py"] = (
        (PAIRS / "03_reordered_functions" / "a" / "cart.js").read_text(encoding="utf-8").replace("function", "def")
    )
    v = make_version(db, product, files)
    s = check_version(db, v)
    assert 0.3 <= s < 0.7, s
    assert v.status == "moderation" and v.flagged


def test_same_seller_versions_not_compared(db, approved_original):
    product = make_product(db, seller=approved_original.product.seller)
    v = make_version(db, product, read_pair("02_renamed_variables", "b"), tag="v2")
    assert check_version(db, v) == 0.0


def test_common_code_of_six_sellers_excluded(db):
    shared = read_pair("01_identical", "a")
    for _ in range(6):
        make_checked_approved(db, make_product(db, seller=make_seller(db)), shared)
    v = make_version(db, make_product(db, status="checking", published_at=None), shared)
    assert check_version(db, v) == 0.0


def test_process_checks_and_broken_archive(db, approved_original):
    v = make_version(
        db, make_product(db, status="checking", published_at=None), read_pair("04_different_projects", "b")
    )
    broken = make_version(db, make_product(db, status="checking", published_at=None), {"a.py": "x=1"})
    Path(private_path(broken.archive)).write_bytes(b"not a zip")
    assert process_pending(db) == 2
    db.refresh(v)
    db.refresh(broken)
    assert v.status == "moderation"
    assert broken.status == "rejected_auto" and broken.check_error
    assert process_pending(db) == 0

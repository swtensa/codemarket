"""Проверка версии на заимствования: связывает чистый алгоритм (app.plagiarism) с базой данных.

Шаги: распаковать архив → отобрать файлы → токенизировать → k-граммы и winnowing →
убрать код библиотек и типовой код (≥ 6 продавцов) → найти кандидатов по индексу hash среди одобренных
версий других продавцов → S = |FA ∩ FB| / min(|FA|, |FB|) → записать совпадения S ≥ 0.1 → решение.
"""

import logging
import shutil
import tempfile
import time

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session, selectinload

from app.core.archive import extract_safe
from app.core.config import settings
from app.models import CodeFingerprint, Product, ProductVersion, VersionMatch, VersionStatus
from app.plagiarism.files import collect_source_files
from app.plagiarism.similarity import fingerprint_files, verdict
from app.services import versions as version_services

log = logging.getLogger("codemarket")
MATCH_MIN = 0.1
CHUNK = 5000
APPROVED = VersionStatus.APPROVED


def _chunks(seq, n=CHUNK):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def common_hashes(db: Session, hashes) -> set[int]:
    """Типовой код: хеши, которые есть в одобренных версиях у PLAG_COMMON_SELLERS и более продавцов."""
    common: set[int] = set()
    for part in _chunks(hashes):
        rows = db.execute(
            select(CodeFingerprint.hash)
            .join(ProductVersion, ProductVersion.id == CodeFingerprint.version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .where(CodeFingerprint.hash.in_(part), ProductVersion.status == APPROVED)
            .group_by(CodeFingerprint.hash)
            .having(func.count(func.distinct(Product.seller_id)) >= settings.plag_common_sellers)
        ).scalars()
        common |= set(rows)
    return common


def find_candidates(db: Session, hashes, seller_id: int) -> dict[int, int]:
    """Одобренные версии других продавцов с общими хешами: {version_id: число общих хешей}."""
    counts: dict[int, int] = {}
    for part in _chunks(hashes):
        rows = db.execute(
            select(CodeFingerprint.version_id, func.count(func.distinct(CodeFingerprint.hash)))
            .join(ProductVersion, ProductVersion.id == CodeFingerprint.version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .where(CodeFingerprint.hash.in_(part), ProductVersion.status == APPROVED, Product.seller_id != seller_id)
            .group_by(CodeFingerprint.version_id)
        ).all()
        for vid, n in rows:
            counts[vid] = counts.get(vid, 0) + n
    return counts


def version_hash_count(db: Session, version_id: int, exclude: set[int]) -> int:
    hashes = set(db.scalars(select(CodeFingerprint.hash).where(CodeFingerprint.version_id == version_id)))
    return len(hashes - exclude)


def check_version(db: Session, version: ProductVersion) -> float:
    """Проверить версию на заимствования и записать результат. Возвращает итоговый S."""
    started = time.monotonic()
    tmp = tempfile.mkdtemp(prefix="cm_check_")
    try:
        extract_safe(version_services.archive_path(version), tmp)
        files = collect_source_files(tmp)
        per_file = fingerprint_files(files, settings.plag_k, settings.plag_w)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    all_hashes = {h for fps in per_file.values() for h, _ in fps}
    common = common_hashes(db, all_hashes)
    fa = all_hashes - common
    seller_id = version.product.seller_id
    candidates = find_candidates(db, fa, seller_id) if fa else {}

    matches, best = [], 0.0
    for vid, shared in candidates.items():
        fb = version_hash_count(db, vid, common)
        s = min(shared / min(len(fa), fb), 1.0) if fa and fb else 0.0
        best = max(best, s)
        if s >= MATCH_MIN:
            matches.append(
                {"version_id": version.id, "matched_version_id": vid, "similarity": s, "common_count": shared}
            )

    decision = verdict(best, settings.plag_reject, settings.plag_flag)
    db.execute(delete(CodeFingerprint).where(CodeFingerprint.version_id == version.id))
    db.execute(delete(VersionMatch).where(VersionMatch.version_id == version.id))
    rows = [
        {"hash": h, "version_id": version.id, "file_path": path[:500], "position": pos}
        for path, fps in per_file.items()
        for h, pos in fps
    ]
    for part in _chunks(rows):
        db.execute(insert(CodeFingerprint), part)
    if matches:
        db.execute(insert(VersionMatch), matches)
    version_services.apply_check_result(
        db,
        version,
        similarity=round(best, 4),
        rejected_auto=decision == "rejected_auto",
        flagged=decision == "flagged",
    )
    log.info(
        "Проверка версии %s: файлов %s, отпечатков %s, S=%.3f, %s, %.1f с",
        version.id,
        len(files),
        len(all_hashes),
        best,
        decision,
        time.monotonic() - started,
    )
    return best


def process_pending(db: Session, limit: int = 10) -> int:
    """Проверить версии в статусе checking (задача планировщика process_checks). Каждая — своей транзакцией."""
    done = 0
    for _ in range(limit):
        version = db.scalar(
            select(ProductVersion)
            .where(ProductVersion.status == VersionStatus.CHECKING)
            .order_by(ProductVersion.created_at)
            .options(selectinload(ProductVersion.product))
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if version is None:
            break
        try:
            with db.begin_nested():
                check_version(db, version)
        except Exception as e:  # битый архив и т. п. — версия не должна зависнуть
            log.exception("Проверка версии %s не удалась", version.id)
            version_services.mark_check_failed(db, version, e)
        db.commit()
        done += 1
    return done


# ---------------------------------------------------------------- отчёт о совпадениях


def matched_files(db: Session, match: VersionMatch, limit: int = 10) -> tuple[list[str], list[str]]:
    """Файлы обеих версий с общими отпечатками: (файлы проверяемой, файлы совпавшей)."""
    hashes = list(set(db.scalars(select(CodeFingerprint.hash).where(CodeFingerprint.version_id == match.version_id))))
    other = db.execute(
        select(CodeFingerprint.hash, CodeFingerprint.file_path)
        .where(CodeFingerprint.version_id == match.matched_version_id, CodeFingerprint.hash.in_(hashes[:CHUNK]))
        .distinct()
    ).all()
    shared = list({h for h, _ in other})
    files_b = sorted({p for _, p in other})[:limit]
    files_a = sorted(
        set(
            db.scalars(
                select(CodeFingerprint.file_path).where(
                    CodeFingerprint.version_id == match.version_id, CodeFingerprint.hash.in_(shared[:CHUNK])
                )
            )
        )
    )[:limit]
    return files_a, files_b


def matches_for_versions(db: Session, versions) -> dict[int, list[dict]]:
    """Совпадения для списка версий: {version_id: [{similarity, common_count, product, seller, files...}]}."""
    ids = [v.id for v in versions]
    if not ids:
        return {}
    out: dict[int, list[dict]] = {}
    rows = db.scalars(
        select(VersionMatch)
        .where(VersionMatch.version_id.in_(ids))
        .order_by(VersionMatch.similarity.desc())
        .options(
            selectinload(VersionMatch.matched_version).selectinload(ProductVersion.product).selectinload(Product.seller)
        )
    ).all()
    for m in rows:
        files, files_other = matched_files(db, m)
        mv = m.matched_version
        out.setdefault(m.version_id, []).append(
            {
                "similarity": m.similarity,
                "common_count": m.common_count,
                "matched_version_id": mv.id,
                "matched_tag": mv.tag_name,
                "product_id": mv.product.id,
                "product_title": mv.product.title,
                "product_slug": mv.product.slug,
                "seller": mv.product.seller.username,
                "files": files,
                "files_other": files_other,
            }
        )
    return out

"""Проверка версии на заимствования: связывает чистый алгоритм с базой данных.

Шаги (раздел 8.5 ТЗ): распаковать архив → отобрать файлы → токенизировать →
k-граммы и winnowing → убрать типовой код (≥ 6 продавцов) → найти кандидатов
по индексу hash среди одобренных версий других продавцов → S = |FA ∩ FB| / min(|FA|, |FB|)
→ записать совпадения S ≥ 0.1 → решение (автоотказ / отметка / модерация) → сохранить отпечатки.
"""

import logging
import shutil
import tempfile
import time

from django.conf import settings
from django.db import transaction
from django.db.models import Count

from apps.core.archive import extract_safe
from apps.versions import services as version_services
from apps.versions.models import ProductVersion

from .files import collect_source_files
from .models import CodeFingerprint, VersionMatch
from .similarity import fingerprint_files, verdict

log = logging.getLogger("codemarket")

MATCH_MIN = 0.1
CHUNK = 5000


def _chunks(seq, n=CHUNK):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def common_hashes(hashes):
    """Типовой код: хеши, которые встречаются в одобренных версиях у PLAG_COMMON_SELLERS и более продавцов."""
    common = set()
    for part in _chunks(hashes):
        common |= set(
            CodeFingerprint.objects.filter(hash__in=part, version__status=ProductVersion.Status.APPROVED)
            .values("hash")
            .annotate(n=Count("version__product__seller", distinct=True))
            .filter(n__gte=settings.PLAG_COMMON_SELLERS)
            .values_list("hash", flat=True)
        )
    return common


def find_candidates(hashes, seller_id):
    """Одобренные версии других продавцов с общими хешами: {version_id: число общих хешей}."""
    counts = {}
    for part in _chunks(hashes):
        rows = (
            CodeFingerprint.objects.filter(hash__in=part, version__status=ProductVersion.Status.APPROVED)
            .exclude(version__product__seller_id=seller_id)
            .values("version_id")
            .annotate(n=Count("hash", distinct=True))
        )
        for r in rows:
            counts[r["version_id"]] = counts.get(r["version_id"], 0) + r["n"]
    return counts


def version_hash_count(version_id, exclude):
    hashes = set(CodeFingerprint.objects.filter(version_id=version_id).values_list("hash", flat=True))
    return len(hashes - exclude)


def check_version(version):
    """Проверить версию на заимствования и записать результат. Возвращает итоговый S."""
    started = time.monotonic()
    tmp = tempfile.mkdtemp(prefix="cm_check_")
    try:
        extract_safe(version.archive.path, tmp)
        files = collect_source_files(tmp)
        per_file = fingerprint_files(files, settings.PLAG_K, settings.PLAG_W)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    all_hashes = {h for fps in per_file.values() for h, _ in fps}
    common = common_hashes(all_hashes)
    fa = all_hashes - common
    seller_id = version.product.seller_id
    candidates = find_candidates(fa, seller_id) if fa else {}

    matches = []
    best = 0.0
    for vid, shared in candidates.items():
        fb = version_hash_count(vid, common)
        s = shared / min(len(fa), fb) if fa and fb else 0.0
        s = min(s, 1.0)
        best = max(best, s)
        if s >= MATCH_MIN:
            matches.append(VersionMatch(version=version, matched_version_id=vid, similarity=s, common_count=shared))

    decision = verdict(best, settings.PLAG_REJECT, settings.PLAG_FLAG)
    with transaction.atomic():
        CodeFingerprint.objects.filter(version=version).delete()
        VersionMatch.objects.filter(version=version).delete()
        CodeFingerprint.objects.bulk_create(
            [
                CodeFingerprint(hash=h, version=version, file_path=path[:500], position=pos)
                for path, fps in per_file.items()
                for h, pos in fps
            ],
            batch_size=5000,
        )
        VersionMatch.objects.bulk_create(matches)
        version_services.apply_check_result(
            version,
            similarity=round(best, 4),
            rejected_auto=decision == "rejected_auto",
            flagged=decision == "flagged",
        )
    log.info(
        "Проверка версии %s: файлов %s, отпечатков %s, S=%.3f, %s, %.1f с",
        version.pk,
        len(files),
        len(all_hashes),
        best,
        decision,
        time.monotonic() - started,
    )
    return best


def process_pending(limit=10):
    """Проверить версии в статусе checking (вызывает команда process_checks)."""
    done = 0
    for _ in range(limit):
        with transaction.atomic():
            version = (
                ProductVersion.objects.select_for_update(skip_locked=True)
                .filter(status=ProductVersion.Status.CHECKING)
                .order_by("created_at")
                .select_related("product")
                .first()
            )
            if version is None:
                break
            try:
                check_version(version)
            except Exception as e:  # битый архив и т. п. — версия не должна зависнуть
                log.exception("Проверка версии %s не удалась", version.pk)
                version_services.mark_check_failed(version, e)
        done += 1
    return done


# ---------------------------------------------------------------- отчёт о совпадениях


def matched_files(match, limit=10):
    """Файлы обеих версий, в которых есть общие отпечатки: (файлы проверяемой, файлы совпавшей)."""
    hashes = set(CodeFingerprint.objects.filter(version_id=match.version_id).values_list("hash", flat=True))
    other = (
        CodeFingerprint.objects.filter(version_id=match.matched_version_id, hash__in=list(hashes)[:CHUNK])
        .values_list("hash", "file_path")
        .distinct()
    )
    shared = {h for h, _ in other}
    files_b = sorted({p for _, p in other})[:limit]
    files_a = sorted(
        set(
            CodeFingerprint.objects.filter(version_id=match.version_id, hash__in=list(shared)[:CHUNK]).values_list(
                "file_path", flat=True
            )
        )
    )[:limit]
    return files_a, files_b


def matches_for_versions(versions):
    """Совпадения для списка версий: {version_id: [VersionMatch с атрибутами files, files_other]}."""
    ids = [v.id for v in versions]
    if not ids:
        return {}
    out = {}
    qs = VersionMatch.objects.filter(version_id__in=ids).select_related(
        "matched_version", "matched_version__product", "matched_version__product__seller"
    )
    for m in qs:
        m.files, m.files_other = matched_files(m)
        out.setdefault(m.version_id, []).append(m)
    return out

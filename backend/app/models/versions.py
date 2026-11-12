"""Версии продукта и результаты проверки на заимствования."""

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Choices, Created, OptDateTime


class VersionStatus(Choices):
    CHECKING = "checking"
    REJECTED_AUTO = "rejected_auto"
    APPEAL = "appeal"
    MODERATION = "moderation"
    APPROVED = "approved"
    REJECTED = "rejected"
    LABELS = {
        CHECKING: "Проверяется",
        REJECTED_AUTO: "Отклонена автоматически",
        APPEAL: "Обжалование",
        MODERATION: "На модерации",
        APPROVED: "Одобрена",
        REJECTED: "Отклонена",
    }


class ProductVersion(Base):
    __tablename__ = "product_versions"
    __table_args__ = (
        UniqueConstraint("product_id", "tag_name", name="uq_version_product_tag"),
        Index("ix_versions_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    tag_name: Mapped[str] = mapped_column(String(100))
    commit_sha: Mapped[str] = mapped_column(String(40), default="")
    archive: Mapped[str] = mapped_column(String(300), default="")  # путь внутри storage/private
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    files_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(15), default=VersionStatus.CHECKING)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_comment: Mapped[str] = mapped_column(Text, default="")
    appeal_text: Mapped[str] = mapped_column(Text, default="")
    check_error: Mapped[str] = mapped_column(Text, default="")
    released_at: Mapped[OptDateTime]
    approved_at: Mapped[OptDateTime]
    created_at: Mapped[Created]

    product: Mapped["Product"] = relationship()  # noqa: F821


class CodeFingerprint(Base):
    """Отпечаток (winnowing) файла версии. Индекс по hash обязателен для поиска кандидатов."""

    __tablename__ = "code_fingerprints"
    __table_args__ = (Index("ix_fingerprints_version_hash", "version_id", "hash"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hash: Mapped[int] = mapped_column(BigInteger, index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("product_versions.id", ondelete="CASCADE"))
    file_path: Mapped[str] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer)


class VersionMatch(Base):
    """Совпадение проверяемой версии с одобренной версией другого продавца (S ≥ 0.1)."""

    __tablename__ = "version_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("product_versions.id", ondelete="CASCADE"), index=True)
    matched_version_id: Mapped[int] = mapped_column(ForeignKey("product_versions.id", ondelete="CASCADE"), index=True)
    similarity: Mapped[float] = mapped_column(Float)
    common_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[Created]

    matched_version: Mapped[ProductVersion] = relationship(foreign_keys=[matched_version_id])


__all__ = ["ProductVersion", "VersionStatus", "CodeFingerprint", "VersionMatch"]

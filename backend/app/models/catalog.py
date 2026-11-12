"""Справочники и продукты каталога."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Choices, Created, Money, OptDateTime, utcnow

PRODUCT_MIN_PRICE = 100
PRODUCT_MAX_PRICE = 500_000


class Category(Base):
    """Раздел (parent пустой) или подкатегория (parent = раздел)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    icon: Mapped[str] = mapped_column(String(40), default="")

    parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent", order_by="(Category.position, Category.name)"
    )

    @property
    def is_section(self) -> bool:
        return self.parent_id is None


class Technology(Base):
    __tablename__ = "technologies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)


product_technologies = Table(
    "product_technologies",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("technology_id", ForeignKey("technologies.id", ondelete="CASCADE"), primary_key=True),
)
product_platforms = Table(
    "product_platforms",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("platform_id", ForeignKey("platforms.id", ondelete="CASCADE"), primary_key=True),
)


class ProductStatus(Choices):
    DRAFT = "draft"
    CHECKING = "checking"
    MODERATION = "moderation"
    PUBLISHED = "published"
    REJECTED = "rejected"
    HIDDEN = "hidden"
    BLOCKED = "blocked"
    LABELS = {
        DRAFT: "Черновик",
        CHECKING: "Проверяется",
        MODERATION: "На модерации",
        PUBLISHED: "Опубликован",
        REJECTED: "Отклонён",
        HIDDEN: "Снят с продажи",
        BLOCKED: "Заблокирован",
    }


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(f"price >= {PRODUCT_MIN_PRICE} AND price <= {PRODUCT_MAX_PRICE}", name="product_price_range"),
        Index("ix_products_status_published", "status", "published_at"),
        Index("ix_products_status_price", "status", "price"),
        Index("ix_products_status_rating", "status", "rating_avg"),
        Index("ix_products_status_sales", "status", "sales_count"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    short_description: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Money]
    demo_url: Mapped[str] = mapped_column(String(200), default="")
    source_repo_full_name: Mapped[str] = mapped_column(String(200), default="")
    source_repo_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mirror_repo_full_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default=ProductStatus.DRAFT)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[Created]
    published_at: Mapped[OptDateTime]

    seller: Mapped["User"] = relationship()  # noqa: F821
    category: Mapped[Category] = relationship()
    technologies: Mapped[list[Technology]] = relationship(secondary=product_technologies, order_by=Technology.name)
    platforms: Mapped[list[Platform]] = relationship(secondary=product_platforms, order_by=Platform.name)
    screenshots: Mapped[list["Screenshot"]] = relationship(
        back_populates="product", order_by="(Screenshot.position, Screenshot.id)", cascade="all, delete-orphan"
    )

    @property
    def section(self) -> Category:
        return self.category.parent or self.category

    @property
    def cover(self) -> "Screenshot | None":
        return self.screenshots[0] if self.screenshots else None


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    image: Mapped[str] = mapped_column(String(300))  # путь внутри storage/public
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[Created]

    product: Mapped[Product] = relationship(back_populates="screenshots")

    @property
    def url(self) -> str:
        return f"/media/{self.image}"


class ProductView(Base):
    """Просмотр карточки: не чаще одной записи на посетителя в сутки."""

    __tablename__ = "product_views"
    __table_args__ = (
        Index("ix_views_product_viewed", "product_id", "viewed_at"),
        Index("ix_views_session_product", "session_key", "product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_key: Mapped[str] = mapped_column(String(40))
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "Category",
    "Technology",
    "Platform",
    "Product",
    "ProductStatus",
    "Screenshot",
    "ProductView",
    "product_technologies",
    "product_platforms",
    "PRODUCT_MIN_PRICE",
    "PRODUCT_MAX_PRICE",
    "Text",
]

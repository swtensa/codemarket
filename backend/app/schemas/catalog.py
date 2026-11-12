"""Схемы каталога, кабинета продавца, версий и модерации."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from .common import Money, Schema


class CategoryOut(Schema):
    id: int
    name: str
    slug: str
    icon: str
    parent_id: int | None
    position: int


class SectionOut(BaseModel):
    id: int
    name: str
    slug: str
    icon: str
    position: int
    product_count: int
    children: list[CategoryOut]


class RefOut(Schema):
    id: int
    name: str
    slug: str


class SortOut(BaseModel):
    key: str
    label: str


class CatalogRefs(BaseModel):
    sections: list[SectionOut]
    technologies: list[RefOut]
    platforms: list[RefOut]
    sorts: list[SortOut]


class ScreenshotOut(Schema):
    id: int
    url: str
    position: int


class ProductCard(BaseModel):
    id: int
    slug: str
    title: str
    short_description: str
    price: Money
    rating_avg: Decimal
    rating_count: int
    sales_count: int
    section_name: str
    section_slug: str
    technologies: list[str]
    cover: str | None


class VersionShort(BaseModel):
    id: int
    tag_name: str
    approved_at: datetime | None


class ReviewOut(BaseModel):
    id: int
    author: str
    rating: int
    text: str
    created_at: datetime


class QuestionOut(BaseModel):
    question: str
    answer: str
    created_at: datetime


class SellerInfo(BaseModel):
    id: int
    username: str
    rating: Decimal | None
    reviews: int
    sales: int


class ProductDetail(BaseModel):
    id: int
    slug: str
    title: str
    short_description: str
    description: str
    price: Money
    demo_url: str
    status: str
    status_label: str
    rating_avg: Decimal
    rating_count: int
    section: CategoryOut
    category: CategoryOut
    seller: SellerInfo
    technologies: list[RefOut]
    platforms: list[RefOut]
    screenshots: list[ScreenshotOut]
    versions: list[VersionShort]
    current_version: VersionShort | None
    product_reviews: list[ReviewOut]
    order_reviews: list[ReviewOut]
    questions: list[QuestionOut]
    is_owner: bool
    purchase_id: int | None


# ---------------------------------------------------------------- продавец


class SellerTiles(BaseModel):
    revenue_month: Money
    sales: int
    views: int
    rating: Decimal | None


class SellerProductRow(BaseModel):
    id: int
    slug: str
    title: str
    status: str
    status_label: str
    price: Money
    sales_count: int
    category: str
    section: str
    cover: str | None
    current_version: str | None
    pending_version: str | None


class SellerDashboard(BaseModel):
    is_seller: bool
    github_mode: str
    tiles: SellerTiles | None
    products: list[SellerProductRow]


class RepoOut(BaseModel):
    id: int
    full_name: str


class ReposOut(BaseModel):
    repos: list[RepoOut]
    need_terms: bool
    error: str = ""


class ProductIn(BaseModel):
    title: str = ""
    short_description: str = ""
    description: str = ""
    price: str | int | Decimal | None = None
    category_id: int | None = None
    technology_ids: list[int] = []
    platform_ids: list[int] = []
    demo_url: str = ""


class ProductCreateIn(ProductIn):
    repo_full_name: str = ""
    accept_seller_terms: bool = False


class ProductEditOut(BaseModel):
    id: int
    slug: str
    title: str
    short_description: str
    description: str
    price: Money
    category_id: int
    technology_ids: list[int]
    platform_ids: list[int]
    demo_url: str
    status: str
    status_label: str
    source_repo_full_name: str


class ReleaseOut(BaseModel):
    tag_name: str
    name: str
    published_at: datetime | None
    imported: bool


class MediaOut(BaseModel):
    product: ProductEditOut
    screenshots: list[ScreenshotOut]
    max_screens: int
    releases: list[ReleaseOut]
    release_error: str


class MatchOut(BaseModel):
    similarity: float
    common_count: int
    matched_version_id: int
    matched_tag: str
    product_id: int
    product_title: str
    product_slug: str
    seller: str
    files: list[str]
    files_other: list[str]


class VersionOut(BaseModel):
    id: int
    tag_name: str
    status: str
    status_label: str
    similarity: float | None
    flagged: bool
    files_count: int
    size: int
    admin_comment: str
    appeal_text: str
    check_error: str
    released_at: datetime | None
    approved_at: datetime | None
    created_at: datetime
    matches: list[MatchOut] = []


class VersionsPage(BaseModel):
    product: ProductEditOut
    versions: list[VersionOut]
    releases: list[ReleaseOut]
    release_error: str


class AppealIn(BaseModel):
    appeal_text: str = ""


class ImportIn(BaseModel):
    tag: str = ""


class GithubConnectOut(BaseModel):
    mode: str
    install_url: str | None
    connected: bool


class GithubCallbackIn(BaseModel):
    installation_id: str = ""
    state: str = ""


# ---------------------------------------------------------------- модерация


class QueueItem(BaseModel):
    version: VersionOut
    product_id: int
    product_title: str
    product_slug: str
    product_status: str
    seller: str
    is_new_product: bool


class TreeItem(BaseModel):
    depth: int
    name: str
    path: str | None


class SellerAdminInfo(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    products: int
    status: str


class VersionDetail(BaseModel):
    version: VersionOut
    product: ProductEditOut
    category: str
    seller: SellerAdminInfo
    tree: list[TreeItem]
    can_decide: bool
    highlight_css: str


class FileView(BaseModel):
    path: str
    html: str | None
    error: str | None


class CommentIn(BaseModel):
    comment: str = ""


class ModCounts(BaseModel):
    versions: int
    disputes: int
    payouts: int

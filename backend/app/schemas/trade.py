"""Схемы покупок, оплаты, заказов и чата, баланса, споров, отзывов, уведомлений, отчётов, администратора."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from .catalog import VersionShort
from .common import Money

# ---------------------------------------------------------------- покупки


class ProductRef(BaseModel):
    id: int
    slug: str
    title: str
    price: Money
    cover: str | None = None
    seller: str = ""
    status: str = ""


class BuyInfo(BaseModel):
    product: ProductRef
    short_description: str
    version: VersionShort | None
    existing_purchase_id: int | None
    error: str
    github_login: str
    license_version: str
    hold_days: int


class BuyIn(BaseModel):
    slug: str
    github_login: str = ""
    accept_license: bool = False


class PayUrl(BaseModel):
    url: str
    purchase_id: int | None = None


class PurchaseRow(BaseModel):
    id: int
    product: ProductRef
    price: Money
    status: str
    status_label: str
    access_status: str
    access_label: str
    created_at: datetime
    paid_at: datetime | None


class ReviewShort(BaseModel):
    rating: int
    text: str
    created_at: datetime


class OrderRow(BaseModel):
    id: int
    kind: str
    kind_label: str
    task: str
    status: str
    status_label: str
    price: Money | None
    days: int | None
    deadline: datetime | None
    created_at: datetime
    product: ProductRef
    buyer: str = ""
    unread: int = 0


class DisputeShort(BaseModel):
    id: int
    status: str
    status_label: str
    reason_type_label: str
    resolution: str
    resolution_label: str
    refund_amount: Money
    admin_comment: str
    opened_at: datetime
    closed_at: datetime | None


class PurchaseDetail(BaseModel):
    id: int
    product: ProductRef
    price: Money
    commission: Money
    status: str
    status_label: str
    access_status: str
    access_label: str
    license_version: str
    created_at: datetime
    paid_at: datetime | None
    purchased_version: str | None
    versions: list[VersionShort]
    can_download: bool
    mirror_url: str
    clone_command: str
    github_login: str
    dispute_days_left: int
    review: ReviewShort | None
    orders: list[OrderRow]
    dispute: DisputeShort | None
    can_review: bool


class GithubLoginIn(BaseModel):
    github_login: str = ""


# ---------------------------------------------------------------- оплата


class FakeCheckout(BaseModel):
    external_id: str
    amount: Money
    description: str
    status: str
    payment_id: int


class FakeActionIn(BaseModel):
    action: str = "pay"


class PaymentResult(BaseModel):
    status: str
    message: str
    level: str
    url: str


# ---------------------------------------------------------------- заказы и чат


class OrderNewInfo(BaseModel):
    product: ProductRef
    kind: str
    kind_label: str
    purchase_id: int | None
    is_owner: bool


class OrderCreateIn(BaseModel):
    product_slug: str = ""
    purchase_id: int | None = None
    kind: str = "question"
    task: str = ""


class MessageOut(BaseModel):
    id: int
    author_id: int | None
    author: str | None
    is_mine: bool
    is_system: bool
    text: str
    attachment_name: str
    attachment_url: str | None
    is_result: bool
    created_at: datetime


class MessagesPoll(BaseModel):
    messages: list[MessageOut]
    last_id: int
    status: str


class StepOut(BaseModel):
    code: str
    label: str
    done: bool
    current: bool


class OrderDetail(BaseModel):
    id: int
    kind: str
    kind_label: str
    task: str
    status: str
    status_label: str
    price: Money | None
    days: int | None
    deadline: datetime | None
    revisions: int
    max_revisions: int
    created_at: datetime
    paid_at: datetime | None
    submitted_at: datetime | None
    product: ProductRef
    buyer: str
    seller: str
    purchase_id: int | None
    is_buyer: bool
    is_seller: bool
    actions: list[str]
    steps: list[StepOut]
    payment_amount: Money | None
    includes_product: bool
    deadline_left_seconds: int | None
    overdue: bool
    can_write: bool
    can_mark_result: bool
    dispute: DisputeShort | None
    auto_accept_days: int
    messages: list[MessageOut]
    last_id: int


class OfferIn(BaseModel):
    price: str | int | Decimal | None = None
    days: str | int | None = None


class ReasonIn(BaseModel):
    reason: str = ""


class RevisionIn(BaseModel):
    comment: str = ""


class DisputeIn(BaseModel):
    purchase_id: int | None = None
    order_id: int | None = None
    reason_type: str = ""
    reason: str = ""


# ---------------------------------------------------------------- отзывы, споры (формы)


class TargetInfo(BaseModel):
    product: ProductRef
    purchase_id: int | None
    order_id: int | None
    back: str
    days_left: int | None = None
    reasons: list[tuple[str, str]] = []


class ReviewIn(BaseModel):
    purchase_id: int | None = None
    order_id: int | None = None
    rating: int | str | None = None
    text: str = ""


# ---------------------------------------------------------------- уведомления


class NotificationOut(BaseModel):
    id: int
    text: str
    link: str
    is_read: bool
    created_at: datetime


class UnreadOut(BaseModel):
    count: int


# ---------------------------------------------------------------- баланс


class BalanceOut(BaseModel):
    held: Money
    available: Money
    withdrawn: Money
    requested: Money
    min_payout: Money
    hold_days: int
    commission_percent: int
    kinds: list[tuple[str, str]]


class OperationOut(BaseModel):
    id: int
    kind: str
    kind_label: str
    amount: Money
    status: str
    status_label: str
    created_at: datetime
    available_at: datetime | None
    processed_at: datetime | None
    purchase_id: int | None
    order_id: int | None
    title: str
    requisites: str


class PayoutIn(BaseModel):
    amount: str | int | Decimal | None = None
    requisites: str = ""


class PayoutRow(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    amount: Money
    status: str
    status_label: str
    requisites: str
    created_at: datetime
    processed_at: datetime | None
    available: Money | None = None


class PayoutsOut(BaseModel):
    requested: list[PayoutRow]
    history: list[PayoutRow]


# ---------------------------------------------------------------- споры (администратор)


class DisputeRow(BaseModel):
    id: int
    target: str
    target_url: str
    product: ProductRef
    buyer: str
    seller: str
    reason_type: str
    reason_type_label: str
    status: str
    status_label: str
    resolution_label: str
    price: Money
    opened_at: datetime


class DisputeDetail(BaseModel):
    dispute: DisputeShort
    row: DisputeRow
    reason: str
    opened_by: str
    order_id: int | None
    purchase_id: int | None
    purchase_status: str | None
    order_status: str | None
    task: str | None
    version_id: int | None
    version_tag: str | None
    chat_messages: list[MessageOut]
    results: list[MessageOut]


class ResolveIn(BaseModel):
    resolution: str = ""
    refund_amount: str | int | Decimal | None = None
    comment: str = ""


# ---------------------------------------------------------------- пользователи и справочники


class BlockIn(BaseModel):
    reason: str = ""


class CategoryIn(BaseModel):
    name: str = ""
    slug: str = ""
    parent_id: int | None = None
    position: int = 0
    icon: str = ""


class RefIn(BaseModel):
    name: str = ""
    slug: str = ""


class RefRow(BaseModel):
    id: int
    name: str
    slug: str
    products: int
    parent_id: int | None = None
    position: int = 0
    icon: str = ""
    children: int = 0


class RefsAdmin(BaseModel):
    categories: list[RefRow]
    technologies: list[RefRow]
    platforms: list[RefRow]


# ---------------------------------------------------------------- отчёты


class StatsProductRow(BaseModel):
    product_id: int
    title: str
    slug: str
    status: str
    views: int
    sales: int
    revenue: Money
    conversion: float | None
    rating: float | None


class SellerStats(BaseModel):
    date_from: str
    date_to: str
    labels: list[str]
    sales: list[int]
    revenue: list[float]
    views: list[int]
    total_views: int
    total_sales: int
    total_revenue: Money
    conversion: float | None
    rating: Decimal | None
    rating_n: int
    products: list[StatsProductRow]


class ReportRow(BaseModel):
    label: str
    users: int = 0
    products: int
    purchases: int
    orders: int
    turnover: Money
    income: Money


class AdminReport(BaseModel):
    date_from: str
    date_to: str
    by_month: list[ReportRow]
    by_section: list[ReportRow]
    totals: ReportRow
    is_empty: bool

"""Преобразование моделей в схемы ответа (общие для нескольких роутеров)."""

from app.models import Product, ProductStatus, ProductVersion, VersionStatus

from .catalog import CategoryOut, ProductCard, ProductEditOut, ScreenshotOut, VersionOut, VersionShort


def cover_url(product: Product) -> str | None:
    cover = product.cover
    return cover.url if cover else None


def product_card(p: Product) -> ProductCard:
    section = p.category.parent or p.category
    return ProductCard(
        id=p.id,
        slug=p.slug,
        title=p.title,
        short_description=p.short_description,
        price=p.price,
        rating_avg=p.rating_avg,
        rating_count=p.rating_count,
        sales_count=p.sales_count,
        section_name=section.name,
        section_slug=section.slug,
        technologies=[t.name for t in p.technologies[:3]],
        cover=cover_url(p),
    )


def category_out(c) -> CategoryOut:
    return CategoryOut.model_validate(c)


def screenshots(p: Product) -> list[ScreenshotOut]:
    return [ScreenshotOut(id=s.id, url=s.url, position=s.position) for s in p.screenshots]


def version_short(v: ProductVersion | None) -> VersionShort | None:
    if v is None:
        return None
    return VersionShort(id=v.id, tag_name=v.tag_name, approved_at=v.approved_at)


def version_out(v: ProductVersion, matches=None) -> VersionOut:
    return VersionOut(
        id=v.id,
        tag_name=v.tag_name,
        status=v.status,
        status_label=VersionStatus.label(v.status),
        similarity=v.similarity,
        flagged=v.flagged,
        files_count=v.files_count,
        size=v.size,
        admin_comment=v.admin_comment,
        appeal_text=v.appeal_text,
        check_error=v.check_error,
        released_at=v.released_at,
        approved_at=v.approved_at,
        created_at=v.created_at,
        matches=matches or [],
    )


def product_edit_out(p: Product) -> ProductEditOut:
    return ProductEditOut(
        id=p.id,
        slug=p.slug,
        title=p.title,
        short_description=p.short_description,
        description=p.description,
        price=p.price,
        category_id=p.category_id,
        technology_ids=[t.id for t in p.technologies],
        platform_ids=[x.id for x in p.platforms],
        demo_url=p.demo_url,
        status=p.status,
        status_label=ProductStatus.label(p.status),
        source_repo_full_name=p.source_repo_full_name,
    )


# ---------------------------------------------------------------- покупки, заказы, споры


def product_ref(p: Product):
    from .trade import ProductRef

    return ProductRef(
        id=p.id,
        slug=p.slug,
        title=p.title,
        price=p.price,
        cover=cover_url(p),
        seller=p.seller.username,
        status=p.status,
    )


def message_out(m, viewer):
    from .trade import MessageOut

    return MessageOut(
        id=m.id,
        author_id=m.author_id,
        author=m.author.username if m.author else None,
        is_mine=bool(viewer and m.author_id == viewer.id),
        is_system=m.author_id is None,
        text=m.text,
        attachment_name=m.attachment_name,
        attachment_url=f"/api/orders/attachments/{m.id}" if m.attachment else None,
        is_result=m.is_result,
        created_at=m.created_at,
    )


def order_row(o, unread: int = 0):
    from app.models import OrderKind, OrderStatus

    from .trade import OrderRow

    return OrderRow(
        id=o.id,
        kind=o.kind,
        kind_label=OrderKind.label(o.kind),
        task=o.task,
        status=o.status,
        status_label=OrderStatus.label(o.status),
        price=o.price,
        days=o.days,
        deadline=o.deadline,
        created_at=o.created_at,
        product=product_ref(o.product),
        buyer=o.buyer.username,
        unread=unread,
    )


def dispute_short(d):
    if d is None:
        return None
    from app.models import DisputeStatus, ReasonType, Resolution

    from .trade import DisputeShort

    return DisputeShort(
        id=d.id,
        status=d.status,
        status_label=DisputeStatus.label(d.status),
        reason_type_label=ReasonType.label(d.reason_type),
        resolution=d.resolution,
        resolution_label=Resolution.label(d.resolution) if d.resolution else "",
        refund_amount=d.refund_amount,
        admin_comment=d.admin_comment,
        opened_at=d.opened_at,
        closed_at=d.closed_at,
    )

"""Администратор: споры, выплаты, пользователи и блокировка, справочники, отчёты и Excel."""

import re
from urllib.parse import quote

from fastapi import APIRouter, Response
from sqlalchemy import func, or_, select

from app.core.deps import DB, StaffUser
from app.core.errors import FieldsError, NotFound, ServiceError
from app.models import (
    BalanceOperation,
    Category,
    DisputeStatus,
    OpStatus,
    Platform,
    Product,
    PurchaseStatus,
    ReasonType,
    Resolution,
    Technology,
    User,
    product_platforms,
    product_technologies,
)
from app.schemas.common import Ok, Page
from app.schemas.convert import dispute_short, message_out, product_ref
from app.schemas.trade import (
    AdminReport,
    BlockIn,
    CategoryIn,
    DisputeDetail,
    DisputeRow,
    PayoutRow,
    PayoutsOut,
    RefIn,
    RefRow,
    RefsAdmin,
    ReportRow,
    ResolveIn,
)
from app.schemas.users import AdminUserOut
from app.services import accounts as account_services
from app.services import balance as balance_services
from app.services import catalog as catalog_services
from app.services import disputes as dispute_services
from app.services import reports as report_services

router = APIRouter(prefix="/api/admin", tags=["администратор"])


# ---------------------------------------------------------------- споры


def _dispute_row(d) -> DisputeRow:
    if d.purchase_id:
        target, url = f"Покупка №{d.purchase_id}", f"/me/purchases/{d.purchase_id}/"
        product, buyer = d.purchase.product, d.purchase.buyer
    else:
        target, url = f"Заказ №{d.order_id}", f"/orders/{d.order_id}/"
        product, buyer = d.order.product, d.order.buyer
    return DisputeRow(
        id=d.id,
        target=target,
        target_url=url,
        product=product_ref(product),
        buyer=buyer.username,
        seller=product.seller.username,
        reason_type=d.reason_type,
        reason_type_label=ReasonType.label(d.reason_type),
        status=d.status,
        status_label=DisputeStatus.label(d.status),
        resolution_label=Resolution.label(d.resolution) if d.resolution else "",
        price=dispute_services.target_price(d),
        opened_at=d.opened_at,
    )


@router.get("/disputes", response_model=Page[DisputeRow])
def disputes(db: DB, _: StaffUser, status: str = "open", page: int = 1, page_size: int = 20):
    items, total, page, pages = catalog_services.paginate(db, dispute_services.disputes_stmt(status), page, page_size)
    return Page(items=[_dispute_row(d) for d in items], total=total, page=page, pages=pages)


@router.get("/disputes/{pk}", response_model=DisputeDetail)
def dispute_detail(pk: int, db: DB, admin: StaffUser):
    """Стороны, причина, переписка заказа, результат, ссылка на код версии."""
    d = dispute_services.get_dispute(db, pk)
    ctx = dispute_services.dispute_context(db, d)
    version = ctx["version"]
    return DisputeDetail(
        dispute=dispute_short(d),
        row=_dispute_row(d),
        reason=d.reason,
        opened_by=d.opened_by.username,
        order_id=d.order_id,
        purchase_id=d.purchase_id,
        purchase_status=PurchaseStatus.label(d.purchase.status) if d.purchase_id else None,
        order_status=d.order.status if d.order_id else None,
        task=d.order.task if d.order_id else None,
        version_id=version.id if version else None,
        version_tag=version.tag_name if version else None,
        chat_messages=[message_out(m, admin) for m in ctx["chat_messages"]],
        results=[message_out(m, admin) for m in ctx["results"]],
    )


@router.post("/disputes/{pk}/resolve", response_model=Ok)
def resolve(pk: int, data: ResolveIn, db: DB, admin: StaffUser):
    d = dispute_services.get_dispute(db, pk)
    dispute_services.resolve(
        db, d, admin, resolution=data.resolution, refund_amount=data.refund_amount, comment=data.comment
    )
    db.commit()
    return Ok(message="Решение по спору сохранено, стороны уведомлены.")


# ---------------------------------------------------------------- выплаты


def _payout_row(db, op, with_balance=False) -> PayoutRow:
    return PayoutRow(
        id=op.id,
        user_id=op.user_id,
        username=op.user.username,
        email=op.user.email,
        amount=-op.amount,
        status=op.status,
        status_label=OpStatus.label(op.status),
        requisites=op.requisites,
        created_at=op.created_at,
        processed_at=op.processed_at,
        available=balance_services.get_balance(db, op.user)["available"] if with_balance else None,
    )


@router.get("/payouts", response_model=PayoutsOut)
def payouts(db: DB, _: StaffUser):
    """Заявки на вывод и последние обработанные."""
    requested = db.scalars(balance_services.requested_payouts_stmt()).all()
    history = db.scalars(
        select(BalanceOperation)
        .where(BalanceOperation.kind == "payout", BalanceOperation.status != OpStatus.REQUESTED)
        .order_by(BalanceOperation.processed_at.desc().nulls_last(), BalanceOperation.id.desc())
        .limit(30)
    ).all()
    return PayoutsOut(
        requested=[_payout_row(db, op, with_balance=True) for op in requested],
        history=[_payout_row(db, op) for op in history],
    )


@router.post("/payouts/{pk}/paid", response_model=Ok)
def payout_paid(pk: int, db: DB, admin: StaffUser):
    balance_services.mark_payout_paid(db, pk, admin)
    db.commit()
    return Ok(message="Заявка отмечена выплаченной.")


@router.post("/payouts/{pk}/reject", response_model=Ok)
def payout_reject(pk: int, data: BlockIn, db: DB, admin: StaffUser):
    balance_services.reject_payout(db, pk, admin, data.reason.strip())
    db.commit()
    return Ok(message="Заявка отклонена, деньги вернулись продавцу в доступные.")


# ---------------------------------------------------------------- пользователи


@router.get("/users", response_model=Page[AdminUserOut])
def users(db: DB, _: StaffUser, q: str = "", status: str = "", page: int = 1, page_size: int = 20):
    """Поиск по email и имени, фильтр по статусу."""
    stmt = select(User).order_by(User.created_at.desc(), User.id.desc())
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.username.ilike(like)))
    if status in ("active", "blocked"):
        stmt = stmt.where(User.status == status)
    items, total, page, pages = catalog_services.paginate(db, stmt, page, page_size)
    return Page(items=[AdminUserOut.model_validate(u) for u in items], total=total, page=page, pages=pages)


def _user(db, pk) -> User:
    user = db.get(User, pk)
    if user is None:
        raise NotFound("Пользователь не найден")
    return user


@router.post("/users/{pk}/block", response_model=Ok)
def block(pk: int, data: BlockIn, db: DB, admin: StaffUser):
    """Заблокировать с причиной: продукты скрываются, неоплаченные заказы отменяются, оплаченные уходят в спор."""
    target = _user(db, pk)
    account_services.block_user(db, target, reason=data.reason, admin=admin)
    db.commit()
    return Ok(message=f"Пользователь {target.username} заблокирован.")


@router.post("/users/{pk}/unblock", response_model=Ok)
def unblock(pk: int, db: DB, admin: StaffUser):
    target = _user(db, pk)
    account_services.unblock_user(db, target, admin=admin)
    db.commit()
    return Ok(message=f"Пользователь {target.username} разблокирован.")


# ---------------------------------------------------------------- справочники

SLUG_RE = re.compile(r"^[a-z0-9-]{2,80}$")


def _usage(db) -> tuple[dict, dict, dict, dict]:
    by_cat = dict(db.execute(select(Product.category_id, func.count()).group_by(Product.category_id)).all())
    children = dict(
        db.execute(
            select(Category.parent_id, func.count()).where(Category.parent_id.is_not(None)).group_by(Category.parent_id)
        ).all()
    )
    by_tech = dict(
        db.execute(
            select(product_technologies.c.technology_id, func.count()).group_by(product_technologies.c.technology_id)
        ).all()
    )
    by_plat = dict(
        db.execute(
            select(product_platforms.c.platform_id, func.count()).group_by(product_platforms.c.platform_id)
        ).all()
    )
    return by_cat, children, by_tech, by_plat


@router.get("/refs", response_model=RefsAdmin)
def refs(db: DB, _: StaffUser):
    """Разделы и подкатегории, технологии, платформы с числом связанных продуктов."""
    by_cat, children, by_tech, by_plat = _usage(db)
    sections = db.scalars(select(Category).where(Category.parent_id.is_(None)).order_by(Category.position)).all()
    cats = []
    for s in sections:
        cats.append(
            RefRow(
                id=s.id,
                name=s.name,
                slug=s.slug,
                products=sum(by_cat.get(c.id, 0) for c in s.children) + by_cat.get(s.id, 0),
                parent_id=None,
                position=s.position,
                icon=s.icon,
                children=children.get(s.id, 0),
            )
        )
        cats += [
            RefRow(id=c.id, name=c.name, slug=c.slug, products=by_cat.get(c.id, 0), parent_id=s.id, position=c.position)
            for c in s.children
        ]
    techs = db.scalars(select(Technology).order_by(Technology.name)).all()
    plats = db.scalars(select(Platform).order_by(Platform.name)).all()
    return RefsAdmin(
        categories=cats,
        technologies=[RefRow(id=t.id, name=t.name, slug=t.slug, products=by_tech.get(t.id, 0)) for t in techs],
        platforms=[RefRow(id=p.id, name=p.name, slug=p.slug, products=by_plat.get(p.id, 0)) for p in plats],
    )


def _check_ref(db, model, data, obj_id=None):
    errors = {}
    name, slug = data.name.strip(), data.slug.strip().lower()
    if not name:
        errors["name"] = "Обязательное поле."
    elif len(name) > (80 if model is Category else 50):
        errors["name"] = "Слишком длинное название."
    if not SLUG_RE.match(slug):
        errors["slug"] = "Адрес: 2–80 символов, латинские строчные буквы, цифры и дефис."
    elif db.scalar(select(model.id).where(model.slug == slug, model.id != (obj_id or 0))):
        errors["slug"] = "Такой адрес уже есть."
    same_name = select(model.id).where(func.lower(model.name) == name.lower(), model.id != (obj_id or 0))
    if model is not Category and not errors.get("name") and db.scalar(same_name):
        errors["name"] = "Такое название уже есть."
    if errors:
        raise FieldsError(errors)
    return name, slug


@router.post("/refs/categories", response_model=Ok, status_code=201)
def create_category(data: CategoryIn, db: DB, _: StaffUser):
    name, slug = _check_ref(db, Category, data)
    if data.parent_id and (parent := db.get(Category, data.parent_id)) is not None and parent.parent_id is not None:
        raise FieldsError({"parent_id": "Подкатегория может быть только внутри раздела."})
    db.add(Category(name=name, slug=slug, parent_id=data.parent_id, position=data.position, icon=data.icon.strip()))
    db.commit()
    return Ok(message="Добавлено.")


@router.put("/refs/categories/{pk}", response_model=Ok)
def update_category(pk: int, data: CategoryIn, db: DB, _: StaffUser):
    cat = db.get(Category, pk)
    if cat is None:
        raise NotFound()
    cat.name, cat.slug = _check_ref(db, Category, data, pk)
    cat.position, cat.icon = data.position, data.icon.strip()
    db.commit()
    return Ok(message="Сохранено.")


def _delete(db, obj, used: int):
    if used:
        raise ServiceError("Удалить нельзя: есть связанные продукты или подкатегории.")
    db.delete(obj)
    db.commit()
    return Ok(message="Удалено.")


@router.delete("/refs/categories/{pk}", response_model=Ok)
def delete_category(pk: int, db: DB, _: StaffUser):
    cat = db.get(Category, pk)
    if cat is None:
        raise NotFound()
    by_cat, children, _t, _p = _usage(db)
    return _delete(db, cat, by_cat.get(pk, 0) + children.get(pk, 0))


def _ref_routes(model, path: str):
    @router.post(f"/refs/{path}", response_model=Ok, status_code=201, name=f"create_{path}")
    def create(data: RefIn, db: DB, _: StaffUser):
        name, slug = _check_ref(db, model, data)
        db.add(model(name=name, slug=slug))
        db.commit()
        return Ok(message="Добавлено.")

    @router.put(f"/refs/{path}/{{pk}}", response_model=Ok, name=f"update_{path}")
    def update(pk: int, data: RefIn, db: DB, _: StaffUser):
        obj = db.get(model, pk)
        if obj is None:
            raise NotFound()
        obj.name, obj.slug = _check_ref(db, model, data, pk)
        db.commit()
        return Ok(message="Сохранено.")

    @router.delete(f"/refs/{path}/{{pk}}", response_model=Ok, name=f"delete_{path}")
    def delete(pk: int, db: DB, _: StaffUser):
        obj = db.get(model, pk)
        if obj is None:
            raise NotFound()
        _cat, _ch, by_tech, by_plat = _usage(db)
        return _delete(db, obj, (by_tech if model is Technology else by_plat).get(pk, 0))


_ref_routes(Technology, "technologies")
_ref_routes(Platform, "platforms")


# ---------------------------------------------------------------- отчёты


def _report_row(r: dict) -> ReportRow:
    return ReportRow(
        label=r.get("label", "Итого"),
        users=r.get("users", 0),
        products=r["products"],
        purchases=r["purchases"],
        orders=r["orders"],
        turnover=r["turnover"],
        income=r["income"],
    )


@router.get("/reports", response_model=AdminReport)
def reports(db: DB, _: StaffUser, date_from: str | None = None, date_to: str | None = None):
    """Новые пользователи, опубликованные продукты, покупки, заказы, оборот и доход площадки (по умолчанию год)."""
    d_from, d_to = report_services.parse_period(date_from, date_to, default_days=365)
    rep = report_services.admin_report(db, d_from, d_to)
    return AdminReport(
        date_from=d_from.isoformat(),
        date_to=d_to.isoformat(),
        by_month=[_report_row(r) for r in rep["by_month"]],
        by_section=[_report_row(r) for r in rep["by_section"]],
        totals=_report_row(rep["totals"]),
        is_empty=rep["is_empty"],
    )


@router.get("/reports/excel")
def reports_excel(db: DB, _: StaffUser, date_from: str | None = None, date_to: str | None = None):
    """Выгрузка отчёта в .xlsx (листы «По месяцам» и «По разделам»)."""
    d_from, d_to = report_services.parse_period(date_from, date_to, default_days=365)
    data = report_services.admin_report_xlsx(db, d_from, d_to)
    name = f"codemarket-report-{d_from:%Y%m%d}-{d_to:%Y%m%d}.xlsx"
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"},
    )

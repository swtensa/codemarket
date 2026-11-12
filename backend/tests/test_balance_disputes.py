"""Баланс, выплаты и споры (раздел 12 ТЗ)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.core.errors import InvalidTransition, ServiceError
from app.integrations.payments import FakeProvider
from app.models import BalanceOperation, Dispute, Notification, Payment, Purchase
from app.models.base import utcnow
from app.services import balance as bal
from app.services import disputes as disp
from app.services import purchases as purchase_services
from app.services.payments import handle_notification
from tests.factories import make_admin, make_product, make_user
from tests.helpers import make_published


@pytest.fixture
def product(db):
    p = make_product(db, price=Decimal("2000"))
    make_published(db, p, {"a.py": "x = 1\n"})
    return p


@pytest.fixture
def admin(db):
    return make_admin(db)


def buy(db, product, buyer=None):
    buyer = buyer or make_user(db, github_login="gh-buyer")
    purchase, _ = purchase_services.start_purchase(db, buyer, product, accept_license=True)
    payment = db.scalar(select(Payment).where(Payment.purchase_id == purchase.id))
    FakeProvider().set_status(payment.external_id, "succeeded")
    handle_notification(db, payment.external_id)
    purchase_services.sync_access(db)
    db.refresh(purchase)
    return purchase


def later(days):
    return utcnow() + timedelta(days=days, minutes=1)


def zero_balance():
    return {"held": Decimal("0"), "available": Decimal("0"), "withdrawn": Decimal("0"), "requested": Decimal("0")}


# ------------------------------------------------------------- баланс


def test_held_becomes_available_after_hold_days(db, product):
    purchase = buy(db, product)
    seller = product.seller
    assert bal.get_balance(db, seller) == {**zero_balance(), "held": Decimal("1800.00")}
    bal.release_funds(db, now=utcnow() + timedelta(days=6))
    assert bal.get_balance(db, seller)["available"] == 0
    bal.release_funds(db, now=later(7))
    assert bal.get_balance(db, seller)["available"] == Decimal("1800.00")
    db.refresh(purchase)
    assert purchase.status == "completed"


def test_payout_more_than_available_forbidden(db, product):
    buy(db, product)
    bal.release_funds(db, now=later(7))
    seller = product.seller
    with pytest.raises(ServiceError):
        bal.request_payout(db, seller, "1900", "Карта 2200 0000 0000 0000")
    with pytest.raises(ServiceError):
        bal.request_payout(db, seller, "400", "Карта 2200 0000 0000 0000")  # меньше 500
    with pytest.raises(ServiceError):
        bal.request_payout(db, seller, "600", "")  # без реквизитов
    with pytest.raises(ServiceError):
        bal.request_payout(db, seller, "много", "Карта 2200 0000 0000 0000")
    bal.request_payout(db, seller, "1000", "Карта 2200 0000 0000 0000")
    b = bal.get_balance(db, seller)
    assert b["available"] == Decimal("800.00") and b["requested"] == Decimal("1000.00")
    with pytest.raises(ServiceError):
        bal.request_payout(db, seller, "900", "Карта 2200 0000 0000 0000")


def test_payout_paid_and_rejected(db, product, admin):
    buy(db, product)
    bal.release_funds(db, now=later(7))
    seller = product.seller
    op1 = bal.request_payout(db, seller, "1000", "Карта 2200 0000 0000 0000")
    op2 = bal.request_payout(db, seller, "500", "Карта 2200 0000 0000 0000")
    bal.mark_payout_paid(db, op1.id, admin)
    bal.reject_payout(db, op2.id, admin, "неверные реквизиты")
    b = bal.get_balance(db, seller)
    assert b["withdrawn"] == Decimal("1000.00") and b["available"] == Decimal("800.00")
    assert db.scalar(
        select(func.count()).where(Notification.user_id == seller.id, Notification.text.contains("отклонена"))
    )
    with pytest.raises(InvalidTransition):
        bal.mark_payout_paid(db, op2.id, admin)


def test_balance_api_and_payout_form(api, db, product):
    buy(db, product)
    bal.release_funds(db, now=later(7))
    api.login(product.seller)
    data = api.get("/api/balance").json()
    assert data["available"] == "1800.00" and data["min_payout"] == "500.00"
    assert [k for k, _ in data["kinds"]] == ["income", "refund_reversal", "payout"]
    resp = api.post("/api/balance/payouts", {"amount": "600", "requisites": "Карта 2200 0000 0000 0000"})
    assert resp.status_code == 201
    assert (
        api.post("/api/balance/payouts", {"amount": "400", "requisites": "Карта 2200 0000 0000 0000"}).status_code
        == 400
    )
    ops = api.get("/api/balance/operations?kind=payout").json()
    assert ops["total"] == 1 and ops["items"][0]["kind_label"] == "Вывод" and ops["items"][0]["amount"] == "-600.00"
    assert api.get("/api/balance/operations").json()["items"][-1]["title"].startswith("Покупка №")


def test_admin_payouts_api(api, db, product, admin):
    buy(db, product)
    bal.release_funds(db, now=later(7))
    op = bal.request_payout(db, product.seller, "600", "Карта 2200 0000 0000 0000")
    api.login(product.seller)
    assert api.get("/api/admin/payouts").status_code == 403
    api.login(admin)
    data = api.get("/api/admin/payouts").json()
    assert "Карта 2200" in data["requested"][0]["requisites"] and data["requested"][0]["amount"] == "600.00"
    assert api.post(f"/api/admin/payouts/{op.id}/paid").status_code == 200
    db.refresh(op)
    assert op.status == "paid"
    assert api.post(f"/api/admin/payouts/{op.id}/paid").status_code == 409
    assert api.get("/api/admin/payouts").json()["history"][0]["status"] == "paid"


# ------------------------------------------------------------- споры по покупке


def test_dispute_stops_release(db, product):
    purchase = buy(db, product)
    disp.open_purchase_dispute(
        db, purchase.buyer, purchase, reason_type="not_working", reason="Не запускается на PHP 8"
    )
    bal.release_funds(db, now=later(7))
    assert bal.get_balance(db, product.seller)["available"] == 0
    assert purchase.status == "dispute"


def test_dispute_rules(db, product):
    purchase = buy(db, product)
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(db, make_user(db), purchase, reason_type="not_working", reason="Чужая покупка тут")
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(
            db, purchase.buyer, purchase, reason_type="changed_mind", reason="Передумал покупать"
        )
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(db, purchase.buyer, purchase, reason_type="other", reason="коротко")
    db.execute(update(Purchase).where(Purchase.id == purchase.id).values(paid_at=utcnow() - timedelta(days=8)))
    db.refresh(purchase)
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(
            db, purchase.buyer, purchase, reason_type="not_working", reason="Сломалось через неделю"
        )


def test_full_refund_revokes_access_and_reverses_income(api, db, product, admin):
    purchase = buy(db, product)
    assert purchase.access_status == "invited"
    d = disp.open_purchase_dispute(
        db, purchase.buyer, purchase, reason_type="not_as_described", reason="Нет обещанной корзины"
    )
    disp.resolve(db, d, admin, resolution="refund", comment="Функции нет")
    assert purchase.status == "refunded" and purchase.access_status == "revoked"
    rev = db.scalar(
        select(BalanceOperation).where(
            BalanceOperation.purchase_id == purchase.id, BalanceOperation.kind == "refund_reversal"
        )
    )
    assert rev.amount == Decimal("-1800.00")
    bal.release_funds(db, now=later(7))
    assert bal.get_balance(db, product.seller) == zero_balance()
    payment = db.scalar(select(Payment).where(Payment.purchase_id == purchase.id))
    assert payment.status == "refunded" and payment.refund_amount == Decimal("2000")
    api.login(purchase.buyer)
    assert api.get(f"/api/purchases/{purchase.id}/download").status_code == 404
    purchase_services.check_can_buy(db, purchase.buyer, product)  # повторно купить после возврата можно


def test_partial_refund(db, product, admin):
    purchase = buy(db, product)
    d = disp.open_purchase_dispute(
        db, purchase.buyer, purchase, reason_type="other", reason="Часть функций не работает"
    )
    with pytest.raises(ServiceError):
        disp.resolve(db, d, admin, resolution="partial", refund_amount="2500")
    with pytest.raises(ServiceError):
        disp.resolve(db, d, admin, resolution="partial", refund_amount="abc")
    with pytest.raises(ServiceError):
        disp.resolve(db, d, admin, resolution="unknown")
    disp.resolve(db, d, admin, resolution="partial", refund_amount="500")
    assert purchase.status == "partially_refunded" and purchase.access_status != "revoked"
    bal.release_funds(db, now=later(7))
    assert bal.get_balance(db, product.seller)["available"] == Decimal("1350.00")  # 1800 − 500 × 0.9
    assert d.status == "closed" and d.refund_amount == Decimal("500")


def test_resolve_in_favor_of_seller(db, product, admin):
    purchase = buy(db, product)
    d = disp.open_purchase_dispute(db, purchase.buyer, purchase, reason_type="not_working", reason="Не работает вообще")
    disp.resolve(db, d, admin, resolution="seller")
    assert purchase.status == "paid"
    bal.release_funds(db, now=later(7))
    assert bal.get_balance(db, product.seller)["available"] == Decimal("1800.00")
    with pytest.raises(InvalidTransition):
        disp.resolve(db, d, admin, resolution="refund")


def test_one_dispute_per_purchase(db, product):
    purchase = buy(db, product)
    disp.open_purchase_dispute(db, purchase.buyer, purchase, reason_type="not_working", reason="Не работает вообще")
    with pytest.raises(ServiceError):
        disp.open_purchase_dispute(db, purchase.buyer, purchase, reason_type="other", reason="Ещё раз пробую")


def test_dispute_api_and_admin_pages(api, db, product, admin):
    purchase = buy(db, product)
    api.login(purchase.buyer)
    form = api.get(f"/api/disputes/new?purchase={purchase.id}").json()
    assert [r[0] for r in form["reasons"]] == ["not_working", "not_as_described", "other"] and form["days_left"] == 7
    resp = api.post(
        "/api/disputes", {"purchase_id": purchase.id, "reason_type": "not_working", "reason": "Ошибка 500 при запуске"}
    )
    assert resp.status_code == 201 and resp.json()["url"] == f"/me/purchases/{purchase.id}/"
    d = db.scalar(select(Dispute))
    assert api.get(f"/api/admin/disputes/{d.id}").status_code == 403
    api.login(admin)
    assert api.get("/api/admin/counts").json()["disputes"] == 1
    rows = api.get("/api/admin/disputes").json()
    assert rows["items"][0]["target"] == f"Покупка №{purchase.id}"
    detail = api.get(f"/api/admin/disputes/{d.id}").json()
    assert detail["reason"] == "Ошибка 500 при запуске" and detail["version_tag"] == "v1.0.0"
    assert api.post(f"/api/admin/disputes/{d.id}/resolve", {"resolution": "refund"}).status_code == 200
    db.refresh(d)
    assert d.status == "closed"
    assert api.get("/api/admin/disputes?status=closed").json()["total"] == 1


def test_other_user_cannot_open_dispute_form(api, db, product):
    purchase = buy(db, product)
    api.login(make_user(db))
    assert api.get(f"/api/disputes/new?purchase={purchase.id}").status_code == 404


# ------------------------------------------------------------- споры по заказу


def _order_in_work(db, product):
    from app.services import orders as osvc

    buyer = make_user(db)
    purchase = buy(db, product, buyer)
    order = osvc.create_order(db, buyer, product, kind="customization", task="Доработать дизайн", purchase=purchase)
    osvc.make_offer(db, order, product.seller, price=1000, days=3)
    osvc.accept_offer(db, order, buyer)
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id))
    FakeProvider().set_status(payment.external_id, "succeeded")
    handle_notification(db, payment.external_id)
    db.refresh(order)
    return order


@pytest.mark.parametrize(
    "resolution,amount,status,available",
    [
        ("seller", None, "accepted", Decimal("900.00")),
        ("refund", None, "refunded", Decimal("0")),
        ("partial", "400", "partially_refunded", Decimal("540.00")),
    ],
)
def test_order_dispute_resolutions(db, product, admin, resolution, amount, status, available):
    order = _order_in_work(db, product)
    d = disp.open_order_dispute(db, order.buyer, order, reason_type="not_working", reason="Сроки сорваны, связи нет")
    disp.resolve(db, d, admin, resolution=resolution, refund_amount=amount)
    assert order.status == status
    ops = db.scalars(
        select(BalanceOperation).where(BalanceOperation.order_id == order.id, BalanceOperation.kind == "income")
    )
    assert sum((o.amount for o in ops), Decimal("0")) == available
    ctx = disp.dispute_context(db, d)
    assert ctx["order"] is order and ctx["chat_messages"]


def test_order_dispute_via_order_api(api, db, product):
    order = _order_in_work(db, product)
    api.login(order.buyer)
    resp = api.post(f"/api/orders/{order.id}/dispute", {"reason_type": "not_working", "reason": "Работа не начата"})
    assert resp.status_code == 200
    db.refresh(order)
    assert order.status == "dispute"
    assert api.get(f"/api/orders/{order.id}").json()["dispute"]["status"] == "open"


def test_order_dispute_only_in_work_statuses(db, product):
    from app.services import orders as osvc

    buyer = make_user(db)
    order = osvc.create_order(db, buyer, product, kind="question", task="Вопрос по продукту")
    with pytest.raises(ServiceError):
        disp.open_order_dispute(db, buyer, order, reason_type="other", reason="Хочу спор по вопросу")

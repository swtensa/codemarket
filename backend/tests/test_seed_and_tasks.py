"""Демо-данные, фоновые задачи и вебхук GitHub."""

import hashlib
import hmac
import json

from sqlalchemy import func, select

from app.core.config import settings
from app.models import CustomOrder, Dispute, Product, ProductVersion, Purchase, User
from app.seed import seed
from app.tasks import JOBS
from tests.factories import make_product, make_seller


def test_seed_fills_every_screen(db):
    lines = []
    assert seed(db, out=lines.append) is True
    assert db.scalar(select(func.count()).where(Product.status == "published")) == 20
    assert set(db.scalars(select(ProductVersion.status))) >= {"approved", "appeal", "rejected_auto", "moderation"}
    statuses = set(db.scalars(select(CustomOrder.status)))
    assert statuses >= {"new", "offer", "awaiting_payment", "in_work", "submitted", "revision", "accepted",
                        "cancelled", "refunded", "dispute"}  # fmt: skip
    assert set(db.scalars(select(Purchase.status))) >= {"completed", "paid", "dispute", "refunded", "pending"}
    assert db.scalar(select(Dispute.id).where(Dispute.status == "open"))
    # настоящие шаблоны Start Bootstrap: опубликованы, автор и лицензия указаны, есть скриншоты страниц
    templates = db.scalars(select(Product).where(Product.slug.startswith("sb-"))).all()
    assert len(templates) == 4
    for p in templates:
        assert p.status == "published"
        assert "Start Bootstrap LLC" in p.description and "MIT" in p.description
        assert len(p.screenshots) >= 2
    copy = db.scalar(select(ProductVersion).join(Product).where(Product.slug == "startup-landing"))
    assert copy.status == "rejected_auto" and copy.similarity >= 0.7
    assert db.scalar(select(User).where(User.email == "buyer5@demo.ru")).github_login == ""
    assert any("demo12345" in line for line in lines)
    # повторный запуск без --reset ничего не ломает
    assert seed(db, out=lines.append) is False
    assert db.scalar(select(func.count()).where(Product.status == "published")) == 20


def test_jobs_run_on_empty_base(db):
    assert [name for name, _, _ in JOBS] == [
        "process_checks", "send_invites", "cancel_unpaid", "auto_accept", "check_deadlines", "release_funds",
    ]  # fmt: skip
    for _name, func_, seconds in JOBS:
        assert isinstance(func_(db), str) and seconds >= 60


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()


def test_github_webhook_signature_and_events(api, db, monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "s3cret")
    seller = make_seller(db, github_installation_id=777)
    repo = settings.github_fake_root / "shop"
    repo.mkdir(parents=True)
    (repo / "index.html").write_text("<p>магазин</p>", encoding="utf-8")
    product = make_product(
        db, seller=seller, status="draft", source_repo_full_name="demo-seller/shop", source_repo_id=42
    )
    body = json.dumps(
        {
            "action": "published",
            "installation": {"id": 777},
            "repository": {"id": 42},
            "release": {"tag_name": "v1.0.0"},
        }
    ).encode()
    bad = api.c.post("/api/github/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=0"})
    assert bad.status_code == 403
    resp = api.c.post(
        "/api/github/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "release"}
    )
    assert resp.status_code == 200
    assert db.scalar(select(ProductVersion).where(ProductVersion.product_id == product.id)).status == "checking"
    body = json.dumps({"action": "deleted", "installation": {"id": 777}}).encode()
    api.c.post(
        "/api/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "installation"},
    )
    db.refresh(seller)
    assert seller.github_installation_id is None


def test_spa_and_health(api):
    assert api.get("/api/health").json() == {"status": "ok"}
    assert api.get("/api/unknown").status_code == 404

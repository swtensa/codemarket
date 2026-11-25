"""Демо-данные для защиты: пользователи, справочники, 16 карточек продуктов, 4 шаблона Start Bootstrap и копия
шаблона, покупки, заказы во всех статусах, отзывы, вопросы, споры, выплаты. Всё создаётся через сервисы.

    python -m app.seed          # заполнить пустую базу
    python -m app.seed --reset  # очистить таблицы и файлы и заполнить заново
"""

import argparse
import io
import random
import re
import shutil
import zlib
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app import demo_data as D
from app.core.config import BASE_DIR, settings
from app.core.db import Base, SessionLocal
from app.core.logging import setup_logging
from app.integrations.payments import FakeProvider
from app.models import (
    BalanceOperation,
    Category,
    CustomOrder,
    Payment,
    Platform,
    ProductVersion,
    ProductView,
    Purchase,
    Technology,
    User,
)
from app.models.base import utcnow
from app.services import accounts as account_services
from app.services import catalog as catalog_services
from app.services.refs import ensure_reference_data

PALETTE = [("#293941", "#CB5152"), ("#3A4E57", "#B2BB8A"), ("#657069", "#FEF6C3"), ("#293941", "#E3B23C"),
           ("#B5444A", "#FEF6C3"), ("#3A4E57", "#E6EAD5")]  # fmt: skip
SECTION_ICON = {"sites": "</>", "modules": "{ }", "bots": "@bot", "scripts": ">_"}
SB_ROOT = BASE_DIR / "fixtures" / "demo" / "startbootstrap"
SB_SCREENS = BASE_DIR / "fixtures" / "demo" / "startbootstrap_screens"


class Seeder:
    def __init__(self, db: Session, out=print):
        self.db = db
        self.out = out
        self.now = utcnow()

    def log(self, text_):
        self.out(f"  {text_}")

    # ------------------------------------------------------------------ служебное

    @staticmethod
    def reset(db: Session, out=print) -> None:
        """Очистить 20 таблиц приложения и файлы."""
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        db.commit()
        for d in [settings.storage_public / "screenshots", settings.storage_private, settings.github_fake_root]:
            shutil.rmtree(d, ignore_errors=True)
        settings.storage_private.mkdir(parents=True, exist_ok=True)
        out("База и файлы очищены")

    def run(self) -> None:
        random.seed(42)
        ensure_reference_data(self.db)
        self.create_users()
        self.create_products()
        self.create_templates()
        self.create_copies_and_queue()
        self.create_purchases()
        self.create_orders()
        self.create_views()
        self.create_payouts()
        self.db.commit()
        self.out("Демо-данные созданы. Пароль всех пользователей: demo12345")
        self.out("Администратор: admin@demo.ru")
        self.out("Продавцы: " + ", ".join(e for _, e in D.SELLERS))
        self.out("Покупатели: " + ", ".join(e for _, e in D.BUYERS))

    # ------------------------------------------------------------------ пользователи

    def create_users(self):
        db = self.db
        self.admin = account_services.create_user(
            db, email="admin@demo.ru", username="admin", password=D.PASSWORD, is_staff=True, terms_accepted_at=self.now
        )
        self.sellers = [
            account_services.create_user(
                db,
                email=email,
                username=name,
                password=D.PASSWORD,
                terms_accepted_at=self.now,
                seller_terms_accepted_at=self.now,
                github_installation_id=900_000_000 + i + 1,
                github_login=name.replace("_", "-"),
            )
            for i, (name, email) in enumerate(D.SELLERS)
        ]
        self.buyers = [
            account_services.create_user(
                db,
                email=email,
                username=name,
                password=D.PASSWORD,
                terms_accepted_at=self.now,
                github_login=f"{name}-gh",
            )
            for name, email in D.BUYERS
        ]
        self.buyers[4].github_login = ""  # покупатель без логина GitHub — для показа кнопки «Получить доступ»
        for k, u in enumerate([*self.sellers, *self.buyers]):
            u.created_at = self.now - timedelta(days=200 - k * 15)  # регистрации растянуты на полгода
        db.flush()
        self.log(f"пользователи: 1 администратор, {len(self.sellers)} продавцов, {len(self.buyers)} покупателей")

    # ------------------------------------------------------------------ продукты

    def write_repo(self, slug, files):
        repo = Path(settings.github_fake_root) / slug
        shutil.rmtree(repo, ignore_errors=True)
        for name, code in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8", newline="\n")
        (repo / "README.md").write_text(f"# {slug}\n\nДемо-продукт CodeMarket.\n", encoding="utf-8")
        return repo

    def copy_repo(self, slug, source, renames=None):
        """Скопировать папку шаблона в fake-репозиторий; renames — переименовать классы (для копии)."""
        repo = Path(settings.github_fake_root) / slug
        shutil.rmtree(repo, ignore_errors=True)
        shutil.copytree(source, repo)
        if renames:
            pattern = re.compile(r"(?<![\w-])(" + "|".join(sorted(renames, key=len, reverse=True)) + r")(?![\w-])")
            for path in repo.rglob("*"):
                if path.suffix in (".html", ".css", ".js"):
                    text_ = path.read_text(encoding="utf-8")
                    path.write_text(pattern.sub(lambda m: renames[m.group(1)], text_), encoding="utf-8", newline="\n")
            (repo / "LICENSE").unlink(missing_ok=True)  # «автор» копии убрал упоминание оригинала
            (repo / "README.md").write_text(f"# {slug}\n\nЛендинг на Bootstrap 5.\n", encoding="utf-8")
        return repo

    def cover(self, title, section_slug, idx):
        from PIL import Image, ImageDraw, ImageFont

        bg, accent = PALETTE[idx % len(PALETTE)]
        img = Image.new("RGB", (1280, 800), bg)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 700, 1280, 800], fill=accent)
        draw.ellipse([880, -160, 1440, 400], outline=accent, width=18)

        def font(size, bold=False):
            names = (["arialbd.ttf", "segoeuib.ttf"] if bold else ["arial.ttf", "segoeui.ttf"]) + ["DejaVuSans.ttf"]
            for name in names:
                for base in ("C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", ""):
                    try:
                        return ImageFont.truetype(base + name, size)
                    except OSError:
                        continue
            return ImageFont.load_default()

        draw.text((80, 90), SECTION_ICON.get(section_slug, "</>"), font=font(110, True), fill=accent)
        lines, line = [], ""
        for w in title.split():
            if len(line + " " + w) > 20:
                lines.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        lines.append(line)
        for i, ln in enumerate(lines[:3]):
            draw.text((80, 300 + i * 92), ln, font=font(76, True), fill="#FFFFFF")
        draw.text((80, 722), "CodeMarket", font=font(40, True), fill=bg)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def make_product(self, slug, title, sub_slug, seller, price, techs, platforms, files, demo_url, idx,
                     description=None, short=None, screens=None):  # fmt: skip
        """files — словарь {путь: код} либо None (репозиторий уже скопирован); screens — файлы скриншотов."""
        db = self.db
        if isinstance(files, dict):
            self.write_repo(slug, files)
        category = db.scalar(select(Category).where(Category.slug == sub_slug))
        tech_objs = list(db.scalars(select(Technology).where(Technology.slug.in_(techs))))
        product = catalog_services.create_product(
            db,
            seller,
            data={
                "title": title,
                "short_description": short or f"{title}: готовый код, быстрый запуск и доработка от автора.",
                "description": description or D.description(title, [t.name for t in tech_objs]),
                "price": price,
                "category_id": category.id,
                "demo_url": demo_url,
                "source_repo_full_name": f"demo-seller/{slug}",
                "source_repo_id": zlib.crc32(slug.encode()),
            },
            technology_ids=[t.id for t in tech_objs],
            platform_ids=list(db.scalars(select(Platform.id).where(Platform.slug.in_(platforms)))),
        )
        product.slug = slug
        db.flush()
        if screens:
            for pos, path in enumerate(screens):
                catalog_services.add_screenshot_bytes(db, product, path.name, path.read_bytes(), pos)
        else:
            catalog_services.add_screenshot_bytes(
                db, product, "cover.png", self.cover(title, category.parent.slug, idx), 0
            )
        db.refresh(product)
        return product

    def check_and_approve(self, product, approve=True):
        from app.services import versions as versions
        from app.services.plagiarism import check_version

        v = versions.import_release(self.db, product, product.seller, "v1.0.0")
        check_version(self.db, v)
        if approve and v.status == "moderation":
            versions.approve_version(self.db, v, self.admin)
        return v

    def _backdate(self, product, version, published, version_created):
        product.published_at, product.created_at = published, published - timedelta(days=2)
        version.approved_at, version.created_at = published, version_created
        self.db.flush()

    def create_products(self):
        self.products = {}
        for idx, (slug, title, sub, seller_i, price, techs, platforms, files, demo) in enumerate(D.PRODUCTS):
            p = self.make_product(slug, title, sub, self.sellers[seller_i], price, techs, platforms, files, demo, idx)
            v = self.check_and_approve(p)
            published = self.now - timedelta(days=170 - idx * 9)  # даты — в прошлом, чтобы отчёты выглядели живыми
            self._backdate(p, v, published, published - timedelta(days=1))
            self.products[slug] = p
            self.log(f"{title}: версия {v.status}, S = {v.similarity:.2f}")

    def create_templates(self):
        """Четыре настоящих шаблона Start Bootstrap (MIT) со скриншотами страниц и копия с переименованными классами."""
        for k, (slug, title, sub, seller_i, price, techs, platforms, folder, url) in enumerate(D.TEMPLATES):
            self.copy_repo(slug, SB_ROOT / folder)
            p = self.make_product(
                slug, title, sub, self.sellers[seller_i], price, techs, platforms, None, url, 30 + k,
                description=D.template_description(title, url),
                short=f"Бесплатный шаблон {D.SB_AUTHOR} (лицензия {D.SB_LICENSE}) на Bootstrap 5, код без изменений.",
                screens=sorted(SB_SCREENS.glob(f"{folder}-*.jpg")),
            )  # fmt: skip
            v = self.check_and_approve(p)
            published = self.now - timedelta(days=32 - k * 6)
            self._backdate(p, v, published, published - timedelta(hours=6))
            p.created_at = published - timedelta(days=1)
            self.products[slug] = p
            self.log(f"{title}: версия {v.status}, S = {v.similarity:.2f}")

        slug, title, sub, seller_i, price, orig, renames = D.TEMPLATE_COPY
        o = next(t for t in D.TEMPLATES if t[0] == orig)
        self.copy_repo(slug, SB_ROOT / o[7], renames=renames)
        p = self.make_product(
            slug, title, sub, self.sellers[seller_i], price, o[5], o[6], None, "", 40,
            description=D.copy_description(title),
            short="Адаптивный лендинг на Bootstrap 5 с формой подписки и отзывами.",
            screens=sorted(SB_SCREENS.glob(f"{o[7]}-*.jpg"))[:1],
        )  # fmt: skip
        v = self.check_and_approve(p, approve=False)
        self.log(f"копия шаблона «{title}» (переименованы классы): {v.status}, S = {v.similarity:.2f}")

    def create_copies_and_queue(self):
        from app.integrations.github.fake import build_release_zip
        from app.services import versions as versions
        from app.services.plagiarism import check_version

        originals = {p[0]: p for p in D.PRODUCTS}
        for k, (slug, title, sub, seller_i, price, orig) in enumerate(D.COPIES):
            o = originals[orig]
            p = self.make_product(slug, title, sub, self.sellers[seller_i], price, o[5], o[6], o[7], "", 20 + k)
            v = self.check_and_approve(p, approve=False)
            self.log(f"копия «{title}»: {v.status}, S = {v.similarity:.2f}")
            if k == 0 and v.status == "rejected_auto":
                versions.appeal_version(
                    self.db, v, p.seller, "Код написан мной, похожа только типовая разметка лендинга."
                )
                self.log("  отправлено обжалование — версия в очереди модерации")

        # новая версия опубликованного продукта ждёт модерации
        fitness = self.products["fitness-landing"]
        repo = Path(settings.github_fake_root) / "fitness-landing"
        with open(repo / "index.html", "a", encoding="utf-8") as f:
            f.write(
                '<section class="reviews"><blockquote class="reviews__item">Лучшая студия!</blockquote></section>\n'
            )
        build_release_zip(repo, "v1.1.0")
        v2 = versions.import_release(self.db, fitness, fitness.seller, "v1.1.0")
        check_version(self.db, v2)
        # черновик без релиза
        catalog_services.create_product(
            self.db,
            self.sellers[0],
            data={
                "title": "Лендинг автосервиса (черновик)",
                "short_description": "Черновик: релиз ещё не отправлен на проверку.",
                "description": "Продукт в работе.",
                "price": 1500,
                "category_id": self.db.scalar(select(Category.id).where(Category.slug == "landing")),
                "source_repo_full_name": "demo-seller/coffee-landing",
            },
        )
        self.log("очередь модерации: обжалование и новая версия v1.1.0; один черновик")

    # ------------------------------------------------------------------ покупки

    def buy(self, buyer, slug, pay=True):
        from app.services import purchases
        from app.services.payments import handle_notification

        purchase, _ = purchases.start_purchase(self.db, buyer, self.products[slug], accept_license=True)
        if pay:
            payment = self.db.scalar(select(Payment).where(Payment.purchase_id == purchase.id))
            FakeProvider().set_status(payment.external_id, "succeeded")
            handle_notification(self.db, payment.external_id)
            self.db.refresh(purchase)
        return purchase

    def shift_purchase(self, purchase, days_ago):
        when = self.now - timedelta(days=days_ago, hours=random.randint(0, 10))
        db = self.db
        db.execute(update(Purchase).where(Purchase.id == purchase.id).values(created_at=when, paid_at=when))
        db.execute(update(Payment).where(Payment.purchase_id == purchase.id).values(created_at=when))
        db.execute(
            update(BalanceOperation)
            .where(BalanceOperation.purchase_id == purchase.id)
            .values(created_at=when, available_at=when + timedelta(days=settings.hold_days))
        )
        db.refresh(purchase)

    def create_purchases(self):
        from app.services import disputes, purchases, reviews
        from app.services.balance import release_funds

        b = self.buyers
        old = [  # (покупатель, продукт, дней назад, оценка)
            (0, "coffee-landing", 150, 5), (1, "coffee-landing", 120, 4), (2, "tg-booking-bot", 110, 5),
            (3, "price-parser", 95, 5), (0, "delivery-calculator", 80, 4), (1, "photo-portfolio", 70, 5),
            (2, "clothing-shop", 60, 4), (3, "survey-bot", 50, 3), (0, "folder-backup", 40, 5),
            (1, "dental-clinic", 35, 5), (2, "reviews-slider", 25, 4), (3, "booking-form", 20, 5),
            (4, "static-cart", 15, None), (0, "invoice-generator", 12, 4), (4, "sb-landing-page", 14, 5),
            (1, "sb-freelancer", 10, 4),
        ]  # fmt: skip
        self.completed = []
        for bi, slug, days, rating in old:
            p = self.buy(b[bi], slug)
            self.shift_purchase(p, days)
            self.completed.append((p, rating))
        release_funds(self.db)
        purchases.sync_access(self.db)
        purchases.sync_access(self.db)  # второй проход: приглашения «приняты» (fake)
        texts = {5: "Всё работает из коробки, автор быстро ответил на вопросы.", 4: "Хороший код, пришлось чуть поправить под себя.",
                 3: "В целом нормально, но документации маловато."}  # fmt: skip
        for p, rating in self.completed:
            self.db.refresh(p)
            if rating:
                reviews.create_purchase_review(self.db, p.buyer, p, rating=rating, text=texts[rating])

        self.recent = self.buy(b[4], "tg-booking-bot")  # paid, в пределах срока спора
        self.shift_purchase(self.recent, 2)
        self.buy(b[1], "reminder-bot")  # paid сегодня
        disputed = self.buy(b[2], "kindergarten-site")
        self.shift_purchase(disputed, 3)
        disputes.open_purchase_dispute(
            self.db, disputed.buyer, disputed, reason_type="not_working",
            reason="Новости не выводятся: страница пустая на PHP 8.2.",
        )  # fmt: skip
        refunded = self.buy(b[3], "fitness-landing")
        self.shift_purchase(refunded, 5)
        d = disputes.open_purchase_dispute(
            self.db, refunded.buyer, refunded, reason_type="not_as_described",
            reason="Нет обещанной онлайн-записи в календарь.",
        )  # fmt: skip
        disputes.resolve(
            self.db, d, self.admin, resolution="refund", comment="Функция заявлена в описании, но отсутствует."
        )
        self.buy(b[0], "survey-bot", pay=False)  # ожидает оплаты
        purchases.sync_access(self.db)
        self.log("покупки: завершённые, оплаченные, спор, возврат, ожидающая оплаты")

    # ------------------------------------------------------------------ заказы

    def pay_order(self, order):
        from app.services.payments import handle_notification

        payment = self.db.scalar(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()))
        FakeProvider().set_status(payment.external_id, "succeeded")
        handle_notification(self.db, payment.external_id)
        self.db.refresh(order)

    def create_orders(self):
        from app.services import orders as o
        from app.services import reviews
        from app.services.disputes import open_order_dispute

        db, b, P = self.db, self.buyers, self.products
        purchase_of = {p.product.slug: p for p, _ in self.completed}

        def custom(slug, task, price=None, days=None, accept=False, pay=False):
            pur = purchase_of[slug]
            order = o.create_order(db, pur.buyer, pur.product, kind="customization", task=task, purchase=pur)
            if price:
                o.make_offer(db, order, pur.product.seller, price=price, days=days)
            if accept:
                o.accept_offer(db, order, pur.buyer)
            if pay:
                self.pay_order(order)
            return order

        # вопросы
        q1 = o.create_order(db, b[1], P["clothing-shop"], kind="question", task="Можно подключить оплату через ЮKassa?")
        o.post_message(db, q1, P["clothing-shop"].seller, text="Да, есть готовый модуль. Сделаю за 3 дня.")
        o.create_order(
            db, b[3], P["tg-booking-bot"], kind="question", task="Бот умеет напоминать клиенту за день до записи?"
        )
        # new / offer / awaiting_payment
        custom("coffee-landing", "Добавить онлайн-меню с QR-кодом на столах")
        custom("photo-portfolio", "Подключить Instagram-ленту на главную", price=2500, days=4)
        custom("price-parser", "Добавить второй сайт-источник и график цен", price=3000, days=5, accept=True)
        # in_work
        w = custom(
            "delivery-calculator", "Добавить зоны доставки по районам Перми", price=1800, days=3, accept=True, pay=True
        )
        o.post_message(db, w, w.product.seller, text="Принял в работу, пришлите список районов.")
        # submitted
        s = custom("tg-booking-bot", "Добавить оплату записи прямо в боте", price=4000, days=7, accept=True, pay=True)
        o.post_message(
            db, s, s.product.seller, text="Готово: оплата через Telegram Payments, инструкция в README.", is_result=True
        )
        o.submit_result(db, s, s.product.seller)
        # revision
        r = custom("survey-bot", "Выгрузка ответов в Google Таблицу", price=2200, days=4, accept=True, pay=True)
        o.post_message(db, r, r.product.seller, text="Выгрузка готова, ссылка на таблицу в настройках.", is_result=True)
        o.submit_result(db, r, r.product.seller)
        o.request_revision(db, r, r.buyer, "Даты выгружаются в формате США, нужен ДД.ММ.ГГГГ")
        # accepted + отзыв о доработке
        a = custom("dental-clinic", "Добавить страницу с отзывами пациентов", price=3500, days=5, accept=True, pay=True)
        o.post_message(db, a, a.product.seller, text="Страница отзывов добавлена.", is_result=True)
        o.submit_result(db, a, a.product.seller)
        o.accept_result(db, a, a.buyer)
        reviews.create_order_review(db, a.buyer, a, rating=5, text="Сделали быстрее срока, всё аккуратно.")
        # cancelled
        c = custom("folder-backup", "Отправка архива в облако", price=1200, days=2)
        o.cancel_order(db, c, c.buyer)
        # refunded (продавец отказался)
        f = custom("booking-form", "Интеграция с amoCRM", price=5000, days=10, accept=True, pay=True)
        o.seller_refuse(db, f, f.product.seller, "Нет доступа к API amoCRM в тестовом режиме")
        # dispute
        d = custom("reviews-slider", "Сделать слайдер с видео-отзывами", price=1500, days=3, accept=True, pay=True)
        o.post_message(db, d, d.product.seller, text="Готово.", is_result=True)
        o.submit_result(db, d, d.product.seller)
        open_order_dispute(db, d.buyer, d, reason_type="not_as_described", reason="Видео не воспроизводятся на iPhone.")
        # «Купить с доработкой» в работе
        wp = o.create_order(
            db, b[4], P["invoice-generator"], kind="with_purchase", task="Добавить логотип и реквизиты моей компании"
        )
        o.make_offer(db, wp, wp.product.seller, price=900, days=2)
        o.accept_offer(db, wp, wp.buyer)
        self.pay_order(wp)
        total = db.scalar(select(text("count(*)")).select_from(CustomOrder))
        self.log(f"заказы: {total} во всех статусах")

    # ------------------------------------------------------------------ просмотры и выплаты

    def create_views(self):
        rows = []
        for slug, p in self.products.items():
            for i in range(random.randint(12, 45)):
                rows.append(
                    ProductView(
                        product_id=p.id,
                        session_key=f"demo-{slug}-{i}",
                        viewed_at=self.now - timedelta(days=random.randint(0, 175)),
                    )
                )
        self.db.add_all(rows)
        self.db.flush()
        self.log(f"просмотры карточек: {len(rows)}")

    def create_payouts(self):
        from app.services import balance as bal

        done = 0
        for i, seller in enumerate(self.sellers):
            available = bal.get_balance(self.db, seller)["available"]
            if available >= 1000:
                op = bal.request_payout(
                    self.db, seller, int(available // 2), "Карта 2200 0000 0000 0000, получатель " + seller.username
                )
                if i % 2 == 0:
                    bal.mark_payout_paid(self.db, op.id, self.admin)
                done += 1
        self.log(f"заявки на вывод: {done}")


def seed(db: Session, reset: bool = False, out=print) -> bool:
    """Заполнить базу. Возвращает False, если демо-данные уже есть и reset не задан."""
    if reset:
        Seeder.reset(db, out)
    elif db.scalar(select(User.id).where(User.email == "admin@demo.ru")):
        out("Демо-данные уже есть. Чтобы пересоздать: python -m app.seed --reset")
        return False
    Seeder(db, out).run()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Демо-данные CodeMarket")
    parser.add_argument("--reset", action="store_true", help="удалить все данные и файлы и создать заново")
    args = parser.parse_args()
    setup_logging()
    db = SessionLocal()
    try:
        seed(db, reset=args.reset)
    finally:
        db.close()


__all__ = ["seed", "Seeder", "ProductVersion"]

if __name__ == "__main__":
    main()

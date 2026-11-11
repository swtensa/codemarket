"""Демо-данные для защиты: пользователи, справочники, 16 продуктов, покупки, заказы во всех статусах,
отзывы, вопросы, спор, выплаты. Всё создаётся через сервисы (как при работе пользователей).

    python manage.py seed_demo          # заполнить пустую базу
    python manage.py seed_demo --reset  # очистить базу и файлы и заполнить заново
"""

import io
import random
import shutil
import zlib
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Category, Platform, Product, ProductView, Screenshot, Technology
from apps.catalog.refs import ensure_reference_data
from apps.core import demo_data as D

PALETTE = [("#293941", "#CB5152"), ("#3A4E57", "#B2BB8A"), ("#657069", "#FEF6C3"), ("#293941", "#E3B23C"),
           ("#B5444A", "#FEF6C3"), ("#3A4E57", "#E6EAD5")]  # fmt: skip
SECTION_ICON = {"sites": "</>", "modules": "{ }", "bots": "@bot", "scripts": ">_"}


class Command(BaseCommand):
    help = "Заполнить базу демо-данными (--reset: очистить и создать заново)"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="удалить все данные и файлы и создать заново")

    def handle(self, *args, **opts):
        if opts["reset"]:
            self.reset()
        elif User.objects.filter(email="admin@demo.ru").exists():
            self.stdout.write(self.style.WARNING("Демо-данные уже есть. Чтобы пересоздать: seed_demo --reset"))
            return
        random.seed(42)
        self.now = timezone.now()
        ensure_reference_data()
        self.create_users()
        self.create_products()
        self.create_copies_and_queue()
        self.create_purchases()
        self.create_orders()
        self.create_views()
        self.create_payouts()
        self.stdout.write(self.style.SUCCESS("Демо-данные созданы. Пароль всех пользователей: demo12345"))
        self.stdout.write("Администратор: admin@demo.ru")
        self.stdout.write("Продавцы: " + ", ".join(e for _, e in D.SELLERS))
        self.stdout.write("Покупатели: " + ", ".join(e for _, e in D.BUYERS))

    # ------------------------------------------------------------------ служебное

    def reset(self):
        call_command("flush", interactive=False, verbosity=0)
        for d in [
            Path(settings.MEDIA_ROOT) / "screenshots",
            Path(settings.PRIVATE_ROOT),
            Path(settings.GITHUB_FAKE_ROOT),
        ]:
            shutil.rmtree(d, ignore_errors=True)
        self.stdout.write("База и файлы очищены")

    def log(self, text):
        self.stdout.write(f"  {text}")

    # ------------------------------------------------------------------ пользователи

    def create_users(self):
        self.admin = User.objects.create_superuser(
            email="admin@demo.ru", username="admin", password=D.PASSWORD, terms_accepted_at=self.now
        )
        self.sellers = []
        for i, (name, email) in enumerate(D.SELLERS):
            u = User.objects.create_user(
                email=email,
                username=name,
                password=D.PASSWORD,
                terms_accepted_at=self.now,
                seller_terms_accepted_at=self.now,
                github_installation_id=900_000_000 + i + 1,
                github_login=name.replace("_", "-"),
            )
            self.sellers.append(u)
        self.buyers = [
            User.objects.create_user(
                email=email, username=name, password=D.PASSWORD, terms_accepted_at=self.now, github_login=f"{name}-gh"
            )
            for name, email in D.BUYERS
        ]
        # покупатель без логина GitHub — для показа кнопки «Получить доступ»
        self.buyers[4].github_login = ""
        self.buyers[4].save(update_fields=["github_login"])
        # даты регистрации растянуты на полгода — для отчёта администратора
        for k, u in enumerate([*self.sellers, *self.buyers]):
            User.objects.filter(pk=u.pk).update(created_at=self.now - timedelta(days=200 - k * 15))
        self.log(f"пользователи: 1 администратор, {len(self.sellers)} продавцов, {len(self.buyers)} покупателей")

    # ------------------------------------------------------------------ продукты

    def write_repo(self, slug, files):
        repo = Path(settings.GITHUB_FAKE_ROOT) / slug
        shutil.rmtree(repo, ignore_errors=True)
        for name, code in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8", newline="\n")
        (repo / "README.md").write_text(f"# {slug}\n\nДемо-продукт CodeMarket.\n", encoding="utf-8")
        return repo

    def cover(self, title, section_slug, idx):
        from PIL import Image, ImageDraw, ImageFont

        bg, accent = PALETTE[idx % len(PALETTE)]
        img = Image.new("RGB", (1280, 800), bg)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 700, 1280, 800], fill=accent)
        draw.ellipse([880, -160, 1440, 400], outline=accent, width=18)

        def font(size, bold=False):
            for name in (["arialbd.ttf", "segoeuib.ttf"] if bold else ["arial.ttf", "segoeui.ttf"]) + [
                "DejaVuSans.ttf"
            ]:
                for base in ("C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", ""):
                    try:
                        return ImageFont.truetype(base + name, size)
                    except OSError:
                        continue
            return ImageFont.load_default()

        draw.text((80, 90), SECTION_ICON.get(section_slug, "</>"), font=font(110, True), fill=accent)
        words, lines, line = title.split(), [], ""
        for w in words:
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

    def make_product(self, slug, title, sub_slug, seller, price, techs, platforms, files, demo_url, idx):
        from apps.catalog import services as catalog

        self.write_repo(slug, files)
        category = Category.objects.get(slug=sub_slug)
        tech_objs = list(Technology.objects.filter(slug__in=techs))
        product = catalog.create_product(
            seller,
            data={
                "title": title,
                "short_description": f"{title}: готовый код, быстрый запуск и доработка от автора.",
                "description": D.description(title, [t.name for t in tech_objs]),
                "price": price,
                "category": category,
                "demo_url": demo_url,
                "source_repo_full_name": f"demo-seller/{slug}",
                "source_repo_id": zlib.crc32(slug.encode()),
            },
            technologies=tech_objs,
            platforms=list(Platform.objects.filter(slug__in=platforms)),
        )
        Product.objects.filter(pk=product.pk).update(slug=slug)
        product.refresh_from_db()
        Screenshot.objects.create(
            product=product,
            position=0,
            image=ContentFile(self.cover(title, category.parent.slug, idx), name="cover.png"),
        )
        return product

    def check_and_approve(self, product, approve=True):
        from apps.plagiarism.services import check_version
        from apps.versions import services as versions

        v = versions.import_release(product, product.seller, "v1.0.0")
        check_version(v)
        v.refresh_from_db()
        if approve and v.status == "moderation":
            versions.approve_version(v, self.admin)
            v.refresh_from_db()
        return v

    def create_products(self):
        self.products = {}
        for idx, (slug, title, sub, seller_i, price, techs, platforms, files, demo) in enumerate(D.PRODUCTS):
            p = self.make_product(slug, title, sub, self.sellers[seller_i], price, techs, platforms, files, demo, idx)
            v = self.check_and_approve(p)
            p.refresh_from_db()
            # даты публикации — в прошлом, чтобы каталог и отчёты выглядели живыми
            published = self.now - timedelta(days=170 - idx * 9)
            Product.objects.filter(pk=p.pk).update(published_at=published, created_at=published - timedelta(days=2))
            v.__class__.objects.filter(pk=v.pk).update(approved_at=published, created_at=published - timedelta(days=1))
            self.products[slug] = p
            self.log(f"{title}: версия {v.status}, S = {v.similarity:.2f}")

    def create_copies_and_queue(self):
        from apps.catalog import services as catalog
        from apps.integrations.github.fake import build_release_zip
        from apps.plagiarism.services import check_version
        from apps.versions import services as versions

        originals = {p[0]: p for p in D.PRODUCTS}
        for k, (slug, title, sub, seller_i, price, orig) in enumerate(D.COPIES):
            o = originals[orig]
            p = self.make_product(slug, title, sub, self.sellers[seller_i], price, o[5], o[6], o[7], "", 20 + k)
            v = self.check_and_approve(p, approve=False)
            self.log(f"копия «{title}»: {v.status}, S = {v.similarity:.2f}")
            if k == 0 and v.status == "rejected_auto":
                versions.appeal_version(v, p.seller, "Код написан мной, похожа только типовая разметка лендинга.")
                self.log("  отправлено обжалование — версия в очереди модерации")

        # новая версия опубликованного продукта ждёт модерации
        fitness = self.products["fitness-landing"]
        repo = Path(settings.GITHUB_FAKE_ROOT) / "fitness-landing"
        with open(repo / "index.html", "a", encoding="utf-8") as f:
            f.write(
                '<section class="reviews"><blockquote class="reviews__item">Лучшая студия!</blockquote></section>\n'
            )
        build_release_zip(repo, "v1.1.0")
        v2 = versions.import_release(fitness, fitness.seller, "v1.1.0")
        check_version(v2)
        # черновик без релиза
        catalog.create_product(
            self.sellers[0],
            data={
                "title": "Лендинг автосервиса (черновик)",
                "short_description": "Черновик: релиз ещё не отправлен на проверку.",
                "description": "Продукт в работе.",
                "price": 1500,
                "category": Category.objects.get(slug="landing"),
                "source_repo_full_name": "demo-seller/coffee-landing",
            },
        )
        self.log("очередь модерации: обжалование и новая версия v1.1.0; один черновик")

    # ------------------------------------------------------------------ покупки

    def buy(self, buyer, slug, pay=True):
        from apps.payments.providers import FakeProvider
        from apps.payments.services import handle_notification
        from apps.purchases import services as purchases

        purchase, _ = purchases.start_purchase(buyer, self.products[slug], accept_license=True)
        if pay:
            payment = purchase.payments.get()
            FakeProvider().set_status(payment.external_id, "succeeded")
            handle_notification(payment.external_id)
            purchase.refresh_from_db()
        return purchase

    def shift_purchase(self, purchase, days_ago):
        from apps.balance.models import BalanceOperation
        from apps.payments.models import Payment
        from apps.purchases.models import Purchase

        when = self.now - timedelta(days=days_ago, hours=random.randint(0, 10))
        Purchase.objects.filter(pk=purchase.pk).update(created_at=when, paid_at=when)
        Payment.objects.filter(purchase=purchase).update(created_at=when)
        BalanceOperation.objects.filter(purchase=purchase).update(
            created_at=when, available_at=when + timedelta(days=settings.HOLD_DAYS)
        )
        purchase.refresh_from_db()

    def create_purchases(self):
        from apps.balance.services import release_funds
        from apps.disputes import services as disputes
        from apps.purchases import services as purchases
        from apps.reviews import services as reviews

        b = self.buyers
        old = [  # (покупатель, продукт, дней назад, оценка)
            (0, "coffee-landing", 150, 5), (1, "coffee-landing", 120, 4), (2, "tg-booking-bot", 110, 5),
            (3, "price-parser", 95, 5), (0, "delivery-calculator", 80, 4), (1, "photo-portfolio", 70, 5),
            (2, "clothing-shop", 60, 4), (3, "survey-bot", 50, 3), (0, "folder-backup", 40, 5),
            (1, "dental-clinic", 35, 5), (2, "reviews-slider", 25, 4), (3, "booking-form", 20, 5),
            (4, "static-cart", 15, None), (0, "invoice-generator", 12, 4),
        ]  # fmt: skip
        self.completed = []
        for bi, slug, days, rating in old:
            p = self.buy(b[bi], slug)
            self.shift_purchase(p, days)
            self.completed.append((p, rating))
        release_funds()
        purchases.sync_access()
        purchases.sync_access()  # второй проход: приглашения «приняты» (fake)
        texts = {5: "Всё работает из коробки, автор быстро ответил на вопросы.", 4: "Хороший код, пришлось чуть поправить под себя.",
                 3: "В целом нормально, но документации маловато."}  # fmt: skip
        for p, rating in self.completed:
            p.refresh_from_db()
            if rating:
                reviews.create_purchase_review(p.buyer, p, rating=rating, text=texts[rating])

        self.recent = self.buy(b[4], "tg-booking-bot")  # paid, в пределах срока спора
        self.shift_purchase(self.recent, 2)
        self.buy(b[1], "reminder-bot")  # paid сегодня
        disputed = self.buy(b[2], "kindergarten-site")
        self.shift_purchase(disputed, 3)
        disputes.open_purchase_dispute(
            disputed.buyer,
            disputed,
            reason_type="not_working",
            reason="Новости не выводятся: страница пустая на PHP 8.2.",
        )
        refunded = self.buy(b[3], "fitness-landing")
        self.shift_purchase(refunded, 5)
        d = disputes.open_purchase_dispute(
            refunded.buyer, refunded, reason_type="not_as_described", reason="Нет обещанной онлайн-записи в календарь."
        )
        disputes.resolve(d, self.admin, resolution="refund", comment="Функция заявлена в описании, но отсутствует.")
        self.buy(b[0], "survey-bot", pay=False)  # ожидает оплаты
        purchases.sync_access()
        self.log("покупки: завершённые, оплаченные, спор, возврат, ожидающая оплаты")

    # ------------------------------------------------------------------ заказы

    def pay_order(self, order):
        from apps.payments.models import Payment
        from apps.payments.providers import FakeProvider
        from apps.payments.services import handle_notification

        payment = Payment.objects.filter(order=order).latest("id")
        FakeProvider().set_status(payment.external_id, "succeeded")
        handle_notification(payment.external_id)
        order.refresh_from_db()

    def create_orders(self):
        from apps.orders import services as o
        from apps.orders.models import CustomOrder
        from apps.reviews import services as reviews

        b, P = self.buyers, self.products
        purchase_of = {p.product.slug: p for p, _ in self.completed}

        def custom(slug, task, price=None, days=None, accept=False, pay=False):
            pur = purchase_of[slug]
            order = o.create_order(pur.buyer, pur.product, kind="customization", task=task, purchase=pur)
            if price:
                o.make_offer(order, pur.product.seller, price=price, days=days)
            if accept:
                o.accept_offer(order, pur.buyer)
            if pay:
                self.pay_order(order)
            return order

        # вопросы
        q1 = o.create_order(b[1], P["clothing-shop"], kind="question", task="Можно подключить оплату через ЮKassa?")
        o.post_message(q1, P["clothing-shop"].seller, text="Да, есть готовый модуль. Сделаю за 3 дня.")
        o.create_order(
            b[3], P["tg-booking-bot"], kind="question", task="Бот умеет напоминать клиенту за день до записи?"
        )
        # new / offer / awaiting_payment
        custom("coffee-landing", "Добавить онлайн-меню с QR-кодом на столах")
        custom("photo-portfolio", "Подключить Instagram-ленту на главную", price=2500, days=4)
        custom("price-parser", "Добавить второй сайт-источник и график цен", price=3000, days=5, accept=True)
        # in_work
        w = custom(
            "delivery-calculator", "Добавить зоны доставки по районам Перми", price=1800, days=3, accept=True, pay=True
        )
        o.post_message(w, w.product.seller, text="Принял в работу, пришлите список районов.")
        # submitted
        s = custom("tg-booking-bot", "Добавить оплату записи прямо в боте", price=4000, days=7, accept=True, pay=True)
        o.post_message(
            s, s.product.seller, text="Готово: оплата через Telegram Payments, инструкция в README.", is_result=True
        )
        o.submit_result(s, s.product.seller)
        # revision
        r = custom("survey-bot", "Выгрузка ответов в Google Таблицу", price=2200, days=4, accept=True, pay=True)
        o.post_message(r, r.product.seller, text="Выгрузка готова, ссылка на таблицу в настройках.", is_result=True)
        o.submit_result(r, r.product.seller)
        o.request_revision(r, r.buyer, "Даты выгружаются в формате США, нужен ДД.ММ.ГГГГ")
        # accepted + отзыв о доработке
        a = custom("dental-clinic", "Добавить страницу с отзывами пациентов", price=3500, days=5, accept=True, pay=True)
        o.post_message(a, a.product.seller, text="Страница отзывов добавлена.", is_result=True)
        o.submit_result(a, a.product.seller)
        o.accept_result(a, a.buyer)
        reviews.create_order_review(a.buyer, a, rating=5, text="Сделали быстрее срока, всё аккуратно.")
        # cancelled
        c = custom("folder-backup", "Отправка архива в облако", price=1200, days=2)
        o.cancel_order(c, c.buyer)
        # refunded (продавец отказался)
        f = custom("booking-form", "Интеграция с amoCRM", price=5000, days=10, accept=True, pay=True)
        o.seller_refuse(f, f.product.seller, "Нет доступа к API amoCRM в тестовом режиме")
        # dispute
        from apps.disputes.services import open_order_dispute

        d = custom("reviews-slider", "Сделать слайдер с видео-отзывами", price=1500, days=3, accept=True, pay=True)
        o.post_message(d, d.product.seller, text="Готово.", is_result=True)
        o.submit_result(d, d.product.seller)
        open_order_dispute(d.buyer, d, reason_type="not_as_described", reason="Видео не воспроизводятся на iPhone.")
        # «Купить с доработкой» в работе
        wp = o.create_order(
            b[4], P["invoice-generator"], kind="with_purchase", task="Добавить логотип и реквизиты моей компании"
        )
        o.make_offer(wp, wp.product.seller, price=900, days=2)
        o.accept_offer(wp, wp.buyer)
        self.pay_order(wp)
        self.log(f"заказы: {CustomOrder.objects.count()} во всех статусах")

    # ------------------------------------------------------------------ просмотры и выплаты

    def create_views(self):
        rows = []
        for slug, p in self.products.items():
            n = random.randint(12, 45)
            for i in range(n):
                rows.append(ProductView(product=p, session_key=f"demo-{slug}-{i}"))
        ProductView.objects.bulk_create(rows)
        for v in ProductView.objects.all():
            ProductView.objects.filter(pk=v.pk).update(viewed_at=self.now - timedelta(days=random.randint(0, 175)))
        self.log(f"просмотры карточек: {len(rows)}")

    def create_payouts(self):
        from apps.balance import services as bal

        done = 0
        for i, seller in enumerate(self.sellers):
            available = bal.get_balance(seller)["available"]
            if available >= 1000:
                op = bal.request_payout(
                    seller, int(available // 2), "Карта 2200 0000 0000 0000, получатель " + seller.username
                )
                if i % 2 == 0:
                    bal.mark_payout_paid(op.pk, self.admin)
                done += 1
        self.log(f"заявки на вывод: {done}")

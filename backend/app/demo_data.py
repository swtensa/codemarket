"""Описание демо-продуктов для seed_demo.

По решению автора демо-продукты — только карточки: «код» каждого продукта занимает
пару-тройку строк, но у разных продуктов он разный, чтобы проверка на заимствования
давала осмысленные числа. Копии (BARISTA, SHIPPING) повторяют код оригиналов и
отклоняются автоматически.
"""

SELLERS = [
    ("webstudio", "webstudio@demo.ru"),
    ("anna_dev", "anna@demo.ru"),
    ("codecraft", "codecraft@demo.ru"),
    ("botmaster", "botmaster@demo.ru"),
    ("pyscripts", "pyscripts@demo.ru"),
]
BUYERS = [("ivan", "buyer1@demo.ru"), ("olga", "buyer2@demo.ru"), ("petr", "buyer3@demo.ru"),
          ("maria", "buyer4@demo.ru"), ("sergey", "buyer5@demo.ru")]  # fmt: skip
PASSWORD = "demo12345"

# slug, название, подкатегория, продавец, цена, технологии, платформы, файлы {путь: код}, demo_url
PRODUCTS = [
    ("coffee-landing", "Лендинг кофейни «Зерно»", "landing", 0, 1490, ["html-css", "javascript"], ["any-hosting", "tilda"],
     {"index.html": '<header class="cafe-top"><nav class="cafe-nav"><a href="#menu">Меню</a></nav></header>\n'
                    '<section id="menu" class="cafe-menu"><article class="dish"><h3>Эспрессо</h3><b class="price">150 ₽</b></article></section>\n'
                    '<footer class="cafe-footer"><address>Пермь, ул. Ленина, 10</address></footer>\n'},
     "https://example.com/demo/coffee"),
    ("fitness-landing", "Лендинг фитнес-студии «Пульс»", "landing", 0, 1990, ["html-css", "javascript"], ["any-hosting", "wordpress"],
     {"index.html": '<div class="topbar"><span class="topbar__brand">ПУЛЬС</span><button class="topbar__burger">☰</button></div>\n'
                    '<table class="timetable"><tr><td class="timetable__time">08:00</td><td class="timetable__class">Йога</td></tr></table>\n'
                    '<dialog id="signup" class="modal"><form method="dialog" class="modal__form"><input name="phone"></form></dialog>\n'},
     "https://example.com/demo/fitness"),
    ("photo-portfolio", "Портфолио фотографа", "portfolio", 1, 2490, ["html-css", "javascript"], ["any-hosting"],
     {"index.html": '<aside class="sidebar"><h1 class="name">Елена Морозова</h1><nav class="filters"><button class="filter">Свадьбы</button></nav></aside>\n'
                    '<main class="gallery"><figure class="shot"><img class="ph" alt=""><figcaption>Анна и Пётр</figcaption></figure></main>\n'
                    '<div class="lightbox" hidden><button class="lb-close">×</button><div class="lb-frame"></div></div>\n'},
     "https://example.com/demo/photo"),
    ("dental-clinic", "Сайт стоматологии «Улыбка»", "company", 0, 4900, ["html-css", "javascript", "bootstrap"], ["any-hosting", "bitrix"],
     {"index.html": '<ul class="hdr-menu"><li><a href="#services">Услуги</a></li><li><a href="#doctors">Врачи</a></li></ul>\n'
                    '<table class="price-list"><tr class="group"><th colspan="2">Терапия</th></tr><tr><td>Кариес</td><td>3 500 ₽</td></tr></table>\n'
                    '<div class="faq"><details><summary>Больно ли лечить зубы?</summary><p>Нет.</p></details></div>\n'},
     "https://example.com/demo/dental"),
    ("clothing-shop", "Интернет-магазин одежды", "shop", 1, 7900, ["html-css", "javascript", "sass"], ["any-hosting"],
     {"shop.js": "const catalog = await fetch('/api/items').then((r) => r.json());\n"
                 "const filtered = catalog.filter((item) => item.size === picked && item.price <= maxPrice);\n"
                 "grid.innerHTML = filtered.map((item) => `<div class=\"card\">${item.title}</div>`).join('');\n"},
     "https://example.com/demo/shop"),
    ("kindergarten-site", "Сайт детского сада «Солнышко»", "company", 2, 3500, ["html-css", "php"], ["wordpress", "any-hosting"],
     {"news.php": "<?php foreach ($news as $post): ?>\n"
                  "<article class=\"news-item\"><h3><?= htmlspecialchars($post['title']) ?></h3><time><?= $post['date'] ?></time></article>\n"
                  "<?php endforeach; ?>\n"},
     ""),
    ("delivery-calculator", "Калькулятор доставки на JS", "calculators", 2, 990, ["javascript"], ["any-hosting", "tilda", "wordpress"],
     {"calc.js": "function deliveryPrice(weightKg, distanceKm, express) {\n"
                 "  const base = 200 + weightKg * 35 + Math.max(0, distanceKm - 5) * 18;\n"
                 "  return Math.round(express ? base * 1.5 : base); }\n"},
     "https://example.com/demo/delivery"),
    ("booking-form", "Форма записи с валидацией", "forms", 1, 790, ["javascript", "html-css"], ["any-hosting", "tilda"],
     {"validate.js": "const rules = { phone: /^\\+7\\d{10}$/, email: /^[^@\\s]+@[^@\\s]+\\.[a-z]{2,}$/i };\n"
                     "form.addEventListener('submit', (e) => { for (const [name, re] of Object.entries(rules)) {\n"
                     "  if (!re.test(form[name].value)) { e.preventDefault(); form[name].classList.add('error'); } } });\n"},
     ""),
    ("reviews-slider", "Слайдер отзывов", "widgets", 2, 490, ["javascript", "html-css"], ["any-hosting", "wordpress"],
     {"slider.js": "let index = 0; const slides = document.querySelectorAll('.review');\n"
                   "setInterval(() => { slides[index].hidden = true; index = (index + 1) % slides.length;\n"
                   "  slides[index].hidden = false; }, 5000);\n"},
     "https://example.com/demo/slider"),
    ("static-cart", "Корзина для статичного магазина", "widgets", 1, 1290, ["javascript"], ["any-hosting"],
     {"cart.js": "const cart = JSON.parse(localStorage.getItem('cart') || '[]');\n"
                 "export function add(id, qty) { const row = cart.find((r) => r.id === id); row ? (row.qty += qty) : cart.push({ id, qty });\n"
                 "  localStorage.setItem('cart', JSON.stringify(cart)); return cart.length; }\n"},
     ""),
    ("tg-booking-bot", "Telegram-бот записи к мастеру", "telegram-bot", 3, 4500, ["python", "aiogram", "sqlite"], ["telegram", "linux"],
     {"bot.py": "@router.message(Command('book'))\n"
                "async def book(message: Message, state: FSMContext):\n"
                "    await state.set_state(Booking.service); await message.answer('Выберите услугу', reply_markup=services_kb())\n"},
     ""),
    ("survey-bot", "Бот-опросник", "business-bot", 3, 2900, ["python", "aiogram"], ["telegram"],
     {"survey.py": "QUESTIONS = ['Как вас зовут?', 'Оцените сервис от 1 до 5', 'Что улучшить?']\n"
                   "async def next_question(chat_id, step):\n"
                   "    return await bot.send_message(chat_id, QUESTIONS[step]) if step < len(QUESTIONS) else await save_answers(chat_id)\n"},
     ""),
    ("reminder-bot", "Бот напоминаний", "telegram-bot", 3, 1900, ["python", "aiogram", "sqlite"], ["telegram", "linux"],
     {"reminders.py": "while True:\n"
                      "    for chat_id, text in db.execute('SELECT chat_id, text FROM reminders WHERE at <= ?', (now(),)):\n"
                      "        await bot.send_message(chat_id, '⏰ ' + text)\n"},
     ""),
    ("price-parser", "Парсер цен в Excel", "parsers", 4, 3900, ["python", "openpyxl"], ["windows", "linux"],
     {"parser.py": "rows = [(card.select_one('.title').text, float(card.select_one('.price').text.replace(' ', '')))\n"
                   "        for card in BeautifulSoup(requests.get(URL).text, 'html.parser').select('.product')]\n"
                   "wb = Workbook(); ws = wb.active; [ws.append(r) for r in rows]; wb.save('prices.xlsx')\n"},
     ""),
    ("folder-backup", "Резервное копирование папки", "automation", 4, 1490, ["python"], ["windows", "linux"],
     {"backup.py": "stamp = datetime.now().strftime('%Y%m%d-%H%M')\n"
                   "shutil.make_archive(os.path.join(target, f'backup-{stamp}'), 'zip', source)\n"
                   "for old in sorted(glob.glob(os.path.join(target, 'backup-*.zip')))[:-keep]: os.remove(old)\n"},
     ""),
    ("invoice-generator", "Генератор счетов в PDF", "documents", 4, 2490, ["python"], ["windows", "linux", "django"],
     {"invoice.py": "pdf = canvas.Canvas(f'invoice-{number}.pdf'); pdf.setFont('DejaVu', 12)\n"
                    "for i, (name, qty, price) in enumerate(items): pdf.drawString(40, 700 - i * 18, f'{name}  {qty} × {price}')\n"
                    "pdf.drawString(40, 680 - len(items) * 18, f'Итого: {sum(q * p for _, q, p in items)} ₽'); pdf.save()\n"},
     ""),
]  # fmt: skip

# Копии для показа автоматического отклонения: slug, название, подкатегория, продавец, цена, slug оригинала
COPIES = [
    ("barista-landing", "Лендинг кафе «Бариста»", "landing", 2, 990, "coffee-landing"),
    ("shipping-calc", "Калькулятор стоимости доставки PRO", "calculators", 1, 690, "delivery-calculator"),
]


def description(title, techs):
    return (
        f"«{title}» — готовое решение, которое можно запустить за один вечер. "
        "Код аккуратно разбит на части и снабжён комментариями, поэтому его легко поменять под свой проект. "
        "Автор отвечает на вопросы и делает доработку под ваши задачи.\n\n"
        "Возможности:\n"
        "— адаптивная вёрстка и понятная структура файлов;\n"
        "— настройки вынесены в одно место;\n"
        f"— используются технологии: {', '.join(techs)};\n"
        "— бесплатные обновления всех будущих версий."
    )


# ---------------------------------------------------------------- настоящие шаблоны Start Bootstrap
#
# Четыре бесплатных шаблона Start Bootstrap (https://startbootstrap.com), автор — Start Bootstrap LLC,
# лицензия MIT. Файлы лежат в fixtures/demo/startbootstrap/<папка> без изменений (содержимое dist/,
# LICENSE и README.md оригинального репозитория), скриншоты страниц — в fixtures/demo/startbootstrap_screens.
# Все четыре шаблона публикует один продавец (веб-студия), поэтому друг с другом они не сравниваются.

SB_AUTHOR = "Start Bootstrap LLC"
SB_LICENSE = "MIT"

# slug, название, подкатегория, продавец, цена, технологии, платформы, папка шаблона, страница оригинала
TEMPLATES = [
    ("sb-landing-page", "Шаблон «Landing Page» (Start Bootstrap)", "landing", 0, 490,
     ["html-css", "bootstrap", "javascript"], ["any-hosting", "tilda"], "landing-page",
     "https://startbootstrap.com/theme/landing-page"),
    ("sb-freelancer", "Шаблон портфолио «Freelancer» (Start Bootstrap)", "portfolio", 0, 590,
     ["html-css", "bootstrap", "javascript"], ["any-hosting"], "freelancer",
     "https://startbootstrap.com/theme/freelancer"),
    ("sb-small-business", "Шаблон сайта компании «Small Business» (Start Bootstrap)", "company", 0, 390,
     ["html-css", "bootstrap"], ["any-hosting", "wordpress"], "small-business",
     "https://startbootstrap.com/template/small-business"),
    ("sb-shop-homepage", "Шаблон витрины «Shop Homepage» (Start Bootstrap)", "shop", 0, 490,
     ["html-css", "bootstrap"], ["any-hosting"], "shop-homepage",
     "https://startbootstrap.com/template/shop-homepage"),
]  # fmt: skip

# Копия шаблона Landing Page с переименованными классами блоков — для показа автоотказа (S ≈ 0,80):
# slug, название, подкатегория, продавец, цена, slug оригинала, {старый класс: новый}
TEMPLATE_COPY = (
    "startup-landing", "Лендинг для стартапа «Старт»", "landing", 2, 790, "sb-landing-page",
    {"masthead": "hero", "showcase": "gallery-block", "testimonials": "reviews", "call-to-action": "cta-banner",
     "features-icons": "benefits", "form-subscribe": "signup-form"},
)  # fmt: skip


def template_description(title, url):
    return (
        f"{title} — бесплатный шаблон на Bootstrap 5 в исходном виде.\n\n"
        f"Автор шаблона — {SB_AUTHOR}, лицензия {SB_LICENSE}. Оригинал: {url}. "
        "Файл LICENSE с уведомлением об авторских правах сохранён в репозитории, код не изменён.\n\n"
        "Что вы получаете за плату:\n"
        "— доступ к репозиторию с обновлениями;\n"
        "— ответы на вопросы по установке;\n"
        "— возможность заказать у продавца адаптацию под свой бизнес (тексты, цвета, формы)."
    )


def copy_description(title):
    return (
        f"«{title}» — современный адаптивный лендинг на Bootstrap 5: первый экран с формой подписки, "
        "преимущества, блоки с фотографиями, отзывы клиентов. Подходит для запуска продукта за один вечер."
    )

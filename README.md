# CodeMarket

Веб-приложение для продажи цифровых продуктов: шаблонов сайтов, модулей, ботов и скриптов.
Покупатель находит продукт в каталоге, оплачивает его, получает код через закрытый репозиторий GitHub
(или ZIP) и при необходимости заказывает у автора доработку. Площадка удерживает оплату доработки до
приёмки и проверяет код новых версий на заимствования (алгоритм winnowing).

Курсовая работа, НИУ ВШЭ Пермь, «Разработка информационных систем для бизнеса».
Техническое задание — [docs/TZ.md](docs/TZ.md), руководство программиста — [docs/programmer_guide.md](docs/programmer_guide.md),
руководство пользователя — [docs/user_guide.md](docs/user_guide.md), ручные тестовые сценарии — [docs/test_cases.md](docs/test_cases.md).

## Технологии

Python 3.12+ (проверено на 3.14), Django 5.2, PostgreSQL 16+ (проверено на 18), Bootstrap 5.3, Chart.js,
Pygments, openpyxl, ЮKassa (`yookassa`), GitHub App (`requests` + `PyJWT`), pytest, ruff.
Фоновые задачи — команды Django, их запускает `run_scheduler` (без Celery, Redis и cron).

## Установка (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

В `.env` задайте `SECRET_KEY` и пароль базы в `DATABASE_URL`. Тот же пароль впишите в `scripts\create_db.sql`
и создайте пользователя и базу (команда спросит пароль суперпользователя `postgres`):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f scripts\create_db.sql
```

## Запуск в демо-режиме (без интернета)

По умолчанию в `.env` включены фейковые интеграции: `PAYMENT_PROVIDER=fake` и `GITHUB_MODE=fake`.

```powershell
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Во втором окне PowerShell запустите планировщик фоновых задач (проверка версий, выдача доступа,
отмена неоплаченных покупок, автоприёмка заказов, перевод денег из удержания):

```powershell
.venv\Scripts\activate
python manage.py run_scheduler
```

Сайт: http://127.0.0.1:8000/ , панель администратора площадки: http://127.0.0.1:8000/moderation/ ,
Django admin (справочники): http://127.0.0.1:8000/admin/

`python manage.py seed_demo --reset` очищает базу и файлы и создаёт демо-данные заново.

Bootstrap, Bootstrap Icons, шрифт Manrope и Chart.js лежат в `static/vendor/` (версии и лицензии —
в `static/vendor/README.md`), поэтому сайт целиком, вместе с оформлением, работает без интернета.

## Демо-логины

Пароль у всех: `demo12345`.

| Роль | Email |
|---|---|
| Администратор | admin@demo.ru |
| Продавцы | webstudio@demo.ru, anna@demo.ru, codecraft@demo.ru, botmaster@demo.ru, pyscripts@demo.ru |
| Покупатели | buyer1@demo.ru … buyer5@demo.ru (у buyer5 нет логина GitHub) |

Демо-продукты:

* 16 карточек с «кодом» в несколько строк (так решил автор). Код у продуктов разный, а два продукта-копии
  («Лендинг кафе «Бариста»», «Калькулятор стоимости доставки PRO») отклоняются проверкой автоматически;
* 4 настоящих бесплатных шаблона [Start Bootstrap](https://startbootstrap.com) — Landing Page, Freelancer,
  Small Business, Shop Homepage (автор Start Bootstrap LLC, лицензия MIT, файл `LICENSE` сохранён).
  Файлы шаблонов — `fixtures/demo/startbootstrap/`, скриншоты страниц — `fixtures/demo/startbootstrap_screens/`;
* копия шаблона Landing Page с переименованными классами блоков («Лендинг для стартапа «Старт»», продавец
  codecraft): проверка находит сходство 0,80 и отклоняет её автоматически.

## Фоновые команды

| Команда | Что делает | Интервал в `run_scheduler` |
|---|---|---|
| `process_checks` | проверка новых версий на заимствования | 1 мин |
| `sync_access` | приглашения покупателей в репозитории-копии | 1 мин |
| `cancel_unpaid` | отмена покупок, не оплаченных за 30 минут | 5 мин |
| `auto_accept` | автоприёмка сданных заказов через 3 дня | 10 мин |
| `release_funds` | перевод денег из удержания через 7 дней | 1 ч |

Любую команду можно запустить вручную: `python manage.py process_checks`.
`python manage.py run_scheduler --once` выполняет все задачи один раз.

## Тесты и качество кода

```powershell
python -m pytest
ruff check .
ruff format .
coverage run -m pytest
coverage report
coverage html
```

Отчёт о покрытии открывается из `htmlcov\index.html`. Сейчас: 202 теста, покрытие сервисов 91 %, всего проекта 87 %.

Калибровка проверки на заимствования (таблица коэффициентов для главы 4):

```powershell
python manage.py plag_calibrate
```

## Реальные ЮKassa и GitHub

Как подключить тестовый магазин ЮKassa, GitHub App и вебхуки через туннель, описано в
[docs/programmer_guide.md](docs/programmer_guide.md), раздел 8.

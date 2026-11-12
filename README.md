# CodeMarket

Веб-приложение для продажи цифровых продуктов: шаблонов сайтов, модулей, ботов и скриптов.
Покупатель находит продукт в каталоге, оплачивает его, получает код через закрытый репозиторий GitHub
(или ZIP) и при необходимости заказывает у автора доработку. Площадка удерживает оплату доработки до
приёмки и проверяет код новых версий на заимствования (алгоритм winnowing).

Курсовая работа, НИУ ВШЭ Пермь, «Разработка информационных систем для бизнеса».
Техническое задание — [docs/TZ.md](docs/TZ.md), ТЗ перехода на FastAPI + React — [docs/TZ_fastapi_react.md](docs/TZ_fastapi_react.md),
руководство программиста (с перечнем адресов API) — [docs/programmer_guide.md](docs/programmer_guide.md),
руководство пользователя — [docs/user_guide.md](docs/user_guide.md), ручные тестовые сценарии — [docs/test_cases.md](docs/test_cases.md).

## Технологии

* Сервер (`backend/`): Python 3.12+ (проверено на 3.14), FastAPI, Uvicorn, SQLAlchemy 2, Alembic, PostgreSQL 16+
  (проверено на 18), Pydantic 2, JWT в httpOnly cookie с CSRF, APScheduler, Pygments, openpyxl,
  ЮKassa (`yookassa`), GitHub App (`requests` + `PyJWT`), pytest, ruff.
* Интерфейс (`frontend/`): React 19, TypeScript, Vite, React Router, TanStack Query, клиент API с типами из
  OpenAPI, react-hook-form + zod, Bootstrap 5, Bootstrap Icons, шрифт Manrope, Chart.js, Vitest, ESLint, Prettier.
  Всё ставится из npm, CDN не используется: сайт полностью работает без интернета.

## Установка (Windows, PowerShell)

Нужны Python 3.12+, Node.js 20+ и PostgreSQL 16+.

```powershell
# пользователь и база (спросит пароль суперпользователя postgres)
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f scripts\create_db.sql

cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # задайте SECRET_KEY и пароль базы в DATABASE_URL (как в scripts\create_db.sql)
cd ..\frontend
npm install
cd ..
```

## Запуск для защиты

```powershell
.\seed.ps1      # миграции и демо-данные (таблицы приложения очищаются и заполняются заново)
.\start.ps1     # сборка интерфейса (если нужна), миграции, сервер и планировщик в двух окнах
```

Сайт: http://127.0.0.1:8000/ , документация API: http://127.0.0.1:8000/api/docs ,
модерация: http://127.0.0.1:8000/moderation/ . `.\start.ps1 -Build` пересобирает интерфейс после изменений.

По умолчанию в `backend\.env` включены фейковые интеграции: `PAYMENT_PROVIDER=fake` (тестовая страница оплаты)
и `GITHUB_MODE=fake` (репозитории из `backend\fixtures\demo\repos`, интернет не нужен).

## Запуск для разработки

Три окна PowerShell:

```powershell
cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload     # API
cd backend; .venv\Scripts\activate; python -m app.scheduler          # фоновые задачи
cd frontend; npm run dev                                              # интерфейс: http://localhost:5173
```

После изменения API обновите типы интерфейса: `npm run gen:api` (сервер должен быть запущен).

## Демо-логины

Пароль у всех: `demo12345`.

| Роль | Email |
|---|---|
| Администратор | admin@demo.ru |
| Продавцы | webstudio@demo.ru, anna@demo.ru, codecraft@demo.ru, botmaster@demo.ru, pyscripts@demo.ru |
| Покупатели | buyer1@demo.ru … buyer5@demo.ru (у buyer5 нет логина GitHub) |

Демо-продукты: 16 карточек с «кодом» в несколько строк; 4 настоящих бесплатных шаблона
[Start Bootstrap](https://startbootstrap.com) (автор Start Bootstrap LLC, лицензия MIT, файл `LICENSE` сохранён);
две копии карточек и копия шаблона Landing Page с переименованными классами — проверка отклоняет их
автоматически (сходство 1,00 и 0,80). Заказы есть во всех статусах, есть спор, возврат и заявки на вывод.

## Фоновые задачи

| Задача | Что делает | Интервал |
|---|---|---|
| `process_checks` | проверка новых версий на заимствования | 1 мин |
| `send_invites` | приглашения покупателей в репозитории-копии | 1 мин |
| `cancel_unpaid` | отмена покупок, не оплаченных за 30 минут | 5 мин |
| `auto_accept` | автоприёмка сданных заказов через 3 дня | 10 мин |
| `check_deadlines` | отметка просроченных заказов в чате и уведомления | 10 мин |
| `release_funds` | перевод денег из удержания через 7 дней | 1 ч |

Вручную: `cd backend; python -m app.cli process_checks` (и другие имена из таблицы);
`python -m app.scheduler --once` выполняет все задачи один раз.

## Тесты и качество кода

```powershell
cd backend
python -m pytest            # тестовая база codemarket_test создаётся автоматически
coverage run -m pytest
coverage report             # покрытие backend — 91 %
ruff check .
ruff format .
python -m app.cli plag_calibrate   # таблица коэффициентов сходства для главы 4

cd ..\frontend
npm test                    # Vitest
npm run lint
npm run typecheck
```

## Реальные ЮKassa и GitHub

Как подключить тестовый магазин ЮKassa, GitHub App и вебхуки через туннель, описано в
[docs/programmer_guide.md](docs/programmer_guide.md), раздел 12.

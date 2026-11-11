# CodeMarket

Веб-приложение для продажи цифровых продуктов (готовые шаблоны сайтов, модули, боты, скрипты)
с заказом доработки у автора, проверкой кода на заимствования и выдачей кода через GitHub.

Курсовая работа, НИУ ВШЭ Пермь, «Разработка информационных систем для бизнеса».
Техническое задание: [docs/TZ.md](docs/TZ.md).

## Требования

- Windows 10/11, PowerShell
- Python 3.12+ (проверено на 3.14)
- PostgreSQL 16+ (проверено на 18)

## Установка

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # затем указать пароль БД и SECRET_KEY
```

Создать пользователя и базу (команда спросит пароль суперпользователя `postgres`):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f scripts\create_db.sql
```

Пароль в `scripts\create_db.sql` должен совпадать с паролем в `DATABASE_URL` из `.env`.

## Запуск

```powershell
python manage.py migrate
python manage.py runserver
```

Сайт: http://127.0.0.1:8000/

## Тесты и проверка кода

```powershell
python -m pytest
ruff check .
ruff format .
```

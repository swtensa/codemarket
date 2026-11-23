# CodeMarket

Площадка для продажи готового кода: шаблонов сайтов, модулей, ботов и скриптов. Покупатель оплачивает продукт,
получает код через закрытый репозиторий GitHub или ZIP и может заказать у автора доработку. Новые версии
проверяются на заимствования (алгоритм winnowing).

Курсовая работа, НИУ ВШЭ Пермь. Документация — в папке [docs](docs).

**Стек:** FastAPI, SQLAlchemy, PostgreSQL, React, TypeScript, Bootstrap.

## Установка

Нужны Python 3.12+, Node.js 20+ и PostgreSQL 16+.

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f scripts\create_db.sql

cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # задайте SECRET_KEY и пароль базы
cd ..\frontend
npm install
```

## Запуск

```powershell
.\seed.ps1      # демо-данные
.\start.ps1     # сервер и фоновые задачи
```

Сайт: http://127.0.0.1:8000/ . Оплата и GitHub по умолчанию работают в демо-режиме, интернет не нужен.

Демо-логины (пароль `demo12345`): администратор `admin@demo.ru`, продавец `webstudio@demo.ru`,
покупатель `buyer1@demo.ru`.

## Тесты

```powershell
cd backend; python -m pytest
cd frontend; npm test
```

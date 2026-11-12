-- Создание пользователя и базы CodeMarket. Пароль должен совпадать с DATABASE_URL в backend.env
CREATE ROLE codemarket LOGIN PASSWORD 'codemarket_password' CREATEDB;
CREATE DATABASE codemarket OWNER codemarket ENCODING 'UTF8';

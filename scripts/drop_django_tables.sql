-- Удаление таблиц Django-версии CodeMarket из базы codemarket (после перехода на FastAPI).
-- Таблицы новой версии (users, products, purchases, ... и alembic_version) не затрагиваются.
-- Запуск: python -m app.cli drop_django_tables  (из папки backend, пароль берётся из backend\.env)
--     или: psql -U codemarket -h localhost -d codemarket -f scripts\drop_django_tables.sql
DROP TABLE IF EXISTS
    plagiarism_codefingerprint,
    plagiarism_versionmatch,
    reviews_review,
    disputes_dispute,
    balance_balanceoperation,
    payments_payment,
    orders_message,
    orders_customorder,
    purchases_purchase,
    versions_productversion,
    notifications_notification,
    catalog_productview,
    catalog_screenshot,
    catalog_product_technologies,
    catalog_product_platforms,
    catalog_product,
    catalog_technology,
    catalog_platform,
    catalog_category,
    accounts_user_groups,
    accounts_user_user_permissions,
    django_admin_log,
    accounts_user,
    auth_group_permissions,
    auth_permission,
    auth_group,
    django_content_type,
    django_session,
    django_migrations
CASCADE;

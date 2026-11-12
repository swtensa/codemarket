# Демо-данные CodeMarket: применить миграции, очистить таблицы и файлы приложения и заполнить заново.
#   .\seed.ps1            — пересоздать демо-данные (таблицы приложения очищаются!)
#   .\seed.ps1 -Keep      — заполнить только пустую базу, ничего не удаляя
param([switch]$Keep)

$ErrorActionPreference = 'Stop'
$backend = Join-Path $PSScriptRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host 'Нет окружения backend\.venv. Выполните установку из README.' -ForegroundColor Red
    exit 1
}

Push-Location $backend
& $python -m alembic upgrade head
if ($Keep) { & $python -m app.seed } else { & $python -m app.seed --reset }
Pop-Location
Write-Host 'Готово. Пароль всех демо-пользователей: demo12345' -ForegroundColor Green

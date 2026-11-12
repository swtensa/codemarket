# Запуск CodeMarket для защиты (без Vite): сервер FastAPI и планировщик в двух окнах PowerShell.
#   .\start.ps1          — собрать интерфейс, если он ещё не собран, применить миграции и запустить
#   .\start.ps1 -Build   — пересобрать интерфейс принудительно
# Сайт: http://127.0.0.1:8000/  Документация API: http://127.0.0.1:8000/api/docs
param([switch]$Build)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host 'Нет окружения backend\.venv. Выполните установку из README (раздел «Установка»).' -ForegroundColor Red
    exit 1
}

if ($Build -or -not (Test-Path (Join-Path $frontend 'dist\index.html'))) {
    Write-Host 'Сборка интерфейса (npm run build)...' -ForegroundColor Cyan
    Push-Location $frontend
    if (-not (Test-Path 'node_modules')) { npm install }
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host 'Сборка не удалась' -ForegroundColor Red; exit 1 }
    Pop-Location
}

Write-Host 'Миграции базы данных (alembic upgrade head)...' -ForegroundColor Cyan
Push-Location $backend
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host 'Миграции не применились: проверьте DATABASE_URL в backend\.env' -ForegroundColor Red; exit 1 }
Pop-Location

$server = "Set-Location -LiteralPath '$backend'; `$host.UI.RawUI.WindowTitle = 'CodeMarket: сервер'; & '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
$scheduler = "Set-Location -LiteralPath '$backend'; `$host.UI.RawUI.WindowTitle = 'CodeMarket: фоновые задачи'; & '$python' -m app.scheduler"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $server
Start-Process powershell -ArgumentList '-NoExit', '-Command', $scheduler

Write-Host 'Сервер и планировщик запущены в отдельных окнах. Остановить — Ctrl+C в каждом окне.' -ForegroundColor Green
Start-Sleep -Seconds 4
Start-Process 'http://127.0.0.1:8000/'

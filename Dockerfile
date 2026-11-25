# ---------- Этап 1: сборка интерфейса React ----------
FROM node:22-slim AS frontend
WORKDIR /app/frontend

# Сначала только списки зависимостей: если они не менялись,
# Docker берёт установленные пакеты из кэша
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Остальной код интерфейса и сборка в папку dist
COPY frontend/ ./
RUN npm run build


# ---------- Этап 2: сервер на Python ----------
FROM python:3.12-slim

# Логи пишутся сразу, без буфера; .pyc-файлы не создаются
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# Зависимости отдельным слоем, чтобы при изменении кода не ставить их заново
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

# Код сервера
COPY backend/ ./

# Готовый интерфейс из первого этапа: сервер ищет его в ../frontend/dist
COPY --from=frontend /app/frontend/dist /app/frontend/dist

EXPOSE 8000

# По умолчанию запускается веб-сервер; 0.0.0.0 — чтобы сайт был виден снаружи контейнера
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

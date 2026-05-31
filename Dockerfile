FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Moscow

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

# worker-class gthread + threads: блокирующий iiko/OLAP-вызов больше не занимает
#   весь воркер целиком (другие запросы обслуживаются другими потоками воркера).
# --timeout 180: запас под retry-бюджет OLAP (2 попытки × 60с + backoff).
# --max-requests + jitter: периодический рециклинг воркеров против накопления
#   per-worker кэшей/истории (anti-leak на длинном аптайме).
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:10000", \
     "--worker-class", "gthread", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "180", \
     "--max-requests", "800", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

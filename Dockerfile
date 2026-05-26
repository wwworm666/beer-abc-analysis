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

CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:10000", \
     "--timeout", "120", \
     "--workers", "2", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

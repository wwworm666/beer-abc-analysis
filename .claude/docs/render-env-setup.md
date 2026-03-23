# Render Environment Variables Setup

## Проблема

После удаления `.env` из git (по соображениям безопасности), деплой на Render падает с ошибкой:
```
Error: Не удалось подключиться к iiko API
```

## Причина

Приложение не может найти переменные окружения `IIKO_SERVER`, `IIKO_PORT`, `IIKO_LOGIN`, `IIKO_PASSWORD`.

## Решение

### 1. Открыть Render Dashboard

1. Перейти на https://dashboard.render.com
2. Выбрать сервис `beer-abc-analysis` (или как он называется)
3. Перейти в раздел **Environment**

### 2. Добавить переменные окружения

Добавить следующие переменные:

| Key | Value |
|-----|-------|
| `IIKO_SERVER` | `first-federation.iiko.it` |
| `IIKO_PORT` | `443` |
| `IIKO_LOGIN` | `claude544` |
| `IIKO_PASSWORD` | `ApiPass2024!` |

### 3. Сохранить и передеплоить

1. Нажать **Save Changes**
2. Render автоматически передеплоит приложение
3. Подождать 2-3 минуты

### 4. Проверить

Открыть приложение и проверить что:
- Dashboard загружается
- API подключается к iiko
- Данные отображаются

## Важно

**Никогда не коммитить .env в git!**

- `.env` содержит секретные данные (пароли, API ключи)
- `.env` добавлен в `.gitignore`
- Для примера используется `.env.example` с placeholder-значениями
- На production (Render) переменные задаются через Dashboard

## Альтернатива: Render.yaml

Можно создать `render.yaml` для автоматической настройки:

```yaml
services:
  - type: web
    name: beer-abc-analysis
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app
    envVars:
      - key: IIKO_SERVER
        sync: false  # не синхронизировать с git
      - key: IIKO_PORT
        value: 443
      - key: IIKO_LOGIN
        sync: false
      - key: IIKO_PASSWORD
        sync: false
```

Но секретные значения всё равно нужно задавать вручную через Dashboard.

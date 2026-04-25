# stocks.md — Остатки товаров

## Что это

Flask Blueprint `stocks_bp` — API остатков товаров. Четыре группы данных: краны (taplist), кухня (kitchen), фасовка (bottles), маркировка ЧЗ (chz). Все endpoints доступны через `routes/stocks.py`.

## Файлы

- `routes/stocks.py` — все endpoints, Blueprint `stocks_bp`
- `chz_test/debug/chz_stock.json` — кеш ЧЗ (обновляется через `POST /api/chz/refresh`)
- `remote_exec.py` — SSH-утилита для запуска `chz.py` на бар-ПК и скачивания результата

## Как работает

### GET /api/stocks/taplist

Возвращает остатки пива на кранах по данным iiko OLAP.

Параметры: `bar` (bar1..bar4 | Общая), `date_from`, `date_to`.

Формат ответа: `{items: [{beer, taps, stock, avg_consumption, days_left, stock_level}]}`.

`stock_level` — расчётный уровень запаса:
- `critical` — days_left < 3
- `low` — days_left < 7
- `ok` — days_left >= 7

### GET /api/stocks/kitchen

Остатки кухни из iiko. Аналогичная структура.

### GET /api/stocks/bottles

Остатки фасованного пива из iiko. Аналогичная структура.

### GET /api/stocks/chz

Прямой вызов ЧЗ API (`chz.get_chz_stock()`). Работает только на сервере с установленным CryptoPro CSP. На production-деплое (Render) всегда возвращает 503. Для production использовать `GET /api/chz/stock`.

Поле `near_expiry_codes` — суммарное количество кодов маркировки с датой годности в диапазоне [сегодня, +30 дней).

### GET /api/chz/stock

Читает кеш из `chz_test/debug/chz_stock.json`. Не требует бар-ПК или CryptoPro.

Ответ: `{items: [...], updated_at: ISO8601}`.

Возвращает 404 если кеш не найден, 500 если кеш повреждён или обновляется.

### POST /api/chz/refresh

Запускает `remote_exec.py run stock` в фоне (SSH на бар-ПК, запуск `chz.py stock`, скачивание `chz_stock.json`).

Требует: переменная окружения `REMOTE_PASS`.

Возвращает 409 если обновление уже выполняется (один параллельный процесс разрешён).

Ответ: `{status: "started"}` или `{status: "already_running"}`.

## Changelog

- 2026-04-22: Добавлены `GET /api/chz/stock` и `POST /api/chz/refresh` — кеш-слой для ЧЗ данных
- 2026-04-05: Добавлен `GET /api/stocks/chz` — прямой вызов ЧЗ API (работает только с CryptoPro)

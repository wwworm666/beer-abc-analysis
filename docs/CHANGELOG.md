# Changelog

### 2026-04-21 — CHZ stock integration: Task 4 — run stock on bar-PC

**Изменено:**
- `remote_exec.py` — добавлен параметр `timeout` в `run_cmd` (передаётся в `exec_command`)
- `remote_exec.py` — добавлена специальная команда `run stock`: обновляет токен, запускает `chz.py stock` с timeout=600, скачивает `chz_stock.json` в `chz_test/debug/`
- `remote_exec.py` — исправлена кодировка вывода: теперь `sys.stdout.buffer.write` с UTF-8 вместо `print` (избегает cp1251 ошибок)
- `chz_test/debug/chz_stock.json` — обновлён: 30 GTIN, 29 с датами годности

**Почему:**
- Без timeout=600 долгие SSH-команды обрывались по таймауту paramiko
- run stock нужен как единая команда для обновления кеша (токен + сбор + скачивание)

**Файлы:**
- `remote_exec.py`
- `chz_test/debug/chz_stock.json`

### 2026-04-11 — ЧЗ остатки: название + количество + срок годности

**Новое:**
- `chz.py stock` — CLI команда для получения остатков пива в формате "название — количество — срок годности"
- `get_product_names(gtins)` — запрос к `/api/v4/true-api/product/info` для получения названий по GTIN
- `get_chz_stock()` — объединяет коды со статусом INTRODUCED с названиями продуктов
- `/api/stocks/chz` — Flask endpoint для дашборда

**Как работает:**
1. `cises/search` получает все коды маркировки за период
2. Фильтруются только коды со статусом `INTRODUCED` (в обороте = на складе)
3. Группировка по GTIN, подсчёт количества
4. `product/info` получает названия, бренды, объёмы по GTIN
5. Результат: GTIN + название + количество + сроки годности

**Файлы:**
- `chz_test/chz.py` — добавлены `get_product_names()`, `get_chz_stock()`, `print_stock_report()`, команда `stock`
- `routes/stocks.py` — добавлен endpoint `/api/stocks/chz`

### 2026-04-08 — Beer Menu Card Creator

**Что создано:**
- Веб-конструктор A4-карточек пивного меню с live-превью
- Два режима экспорта PNG: client (html2canvas) и server (Playwright)
- CRUD API для управления позициями, загрузка логотипов
- Фиксированный дизайн (PT Serif, corner accents, dividers), не ломающийся при любом контенте

**Файлы:**
- `routes/menu.py` — Blueprint с API и Playwright-рендером
- `templates/menu.html` — страница конструктора
- `templates/menu_card.html` — standalone шаблон карточки
- `static/menu/logos/` — папка для логотипов
- `data/menu_items.json` — хранилище позиций
- `docs/menu-card.md` — документация модуля

### 2026-04-07 — Исследование подключения к бар-10 и бар-ПК

**Что сделано:**
- Подключились к бар-10 (100.98.149.104) через RDP: `1` / `qwe123`
- SSH на бар-10 НЕ работает (порт 22 не отвечает)
- Сертификат КриптоПро на бар-10 просрочен (12.12.2025), владелец: Тюменева О.И.
- Носитель сертификата: Jacarta (USB токен, нельзя экспортировать)
- Тестировали 5+ вариантов SSH-логина на бар-ПК (100.98.149.108) — только sshuser работает
- sshuser НЕ в группе Администраторы, нет прав на повышение (`runas`, `net localgroup /add` — Access Denied)
- cryptcp требует доступ к хранилищу ключей Администратора
- Подпись через cryptcp не проходит валидацию на сервере (NOT_VALID_GOST_SIGNATURE)

**Файлы:**
- `docs/CONNECTIVITY.md` — полный статус подключения ко всем устройствам
- `.claude/INDEX.md` — добавлена ссылка на CONNECTIVITY.md

### 2026-04-05 — Удалённый доступ к бар-ПК

**Что сделано:**
- Настроен Tailscale сеть + OpenSSH Server + paramiko
- Создан `sshuser` учётка, SSH-ключ
- Утилита `remote_exec.py` для удалённого выполнения команд

**Файлы:**
- `docs/remote-sync.md`

### 2026-04-05 — Честный ЗНАК

**Что сделано:**
- Чистка chz_test, единый скрипт chz.py
- Получены сроки годности пива (v4 API, 8500+ записей)

**Файлы:**
- `docs/changelog/CHZ_INTEGRATION.md`
- `chz_test/chz.py`

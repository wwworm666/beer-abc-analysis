# Changelog

### 2026-04-22 — CHZ stock integration: code review pass 3 — bug fixes and doc updates

**Изменено:**
- `routes/stocks.py` — `near_expiry_codes`: исправлена логика подсчёта — ранее считались и уже просроченные коды (`days < 0`). Теперь только коды с `0 <= days < 30`.
- `routes/stocks.py` — `GET /api/chz/stock`: `getmtime()` перенесён внутрь `try/except` — ранее при удалении файла между `.exists()` и `getmtime()` возникал необработанный `FileNotFoundError` (TOCTOU race).
- `routes/stocks.py` — удалён мёртвый блок `if amount == 0: pass` в `get_taplist_stocks`.
- `remote_exec.py` — проверка `REMOTE_PASS` перенесена из уровня модуля в `connect()` — импорт модуля больше не выбрасывает исключение.
- `remote_exec.py` — `cd` заменён на `cd /d` во всех командах `run stock` и `run` — без `/d` `cmd.exe` не меняет диск.
- `docs/remote-sync.md` — обновлены учётные данные (Администратор / REMOTE_PASS env), Python путь, состояние бар-ПК; добавлена команда `run stock`.
- `docs/changelog/CHZ_INTEGRATION.md` — обновлён пункт 7: описан дефолтный лимит 180 дней в `get_chz_stock`.
- `chz_test/README.md` — добавлена секция команды `stock`.
- `README.md` — добавлены `GET /api/chz/stock` и `POST /api/chz/refresh` в список API; `REMOTE_PASS`/`REMOTE_USER` добавлены в список env vars.

**Почему:**
- `days < 30` без проверки `>= 0` ошибочно включало давно просроченные коды в `near_expiry_codes`.
- TOCTOU гонка на файле кеша могла вызвать 500 при параллельном refresh.
- `cd` без `/d` не меняет диск в Windows cmd.exe при смене драйва.

**Файлы:**
- `remote_exec.py`, `routes/stocks.py`, `README.md`, `docs/remote-sync.md`, `docs/changelog/CHZ_INTEGRATION.md`, `chz_test/README.md`

### 2026-04-21 — CHZ stock integration: code review pass 2 — security and reliability fixes

**Изменено:**
- `remote_exec.py` — удалён захардкоженный пароль `"Krem2026"` как дефолт в `REMOTE_PASS`; теперь переменная обязательна, без неё бросается `EnvironmentError`
- `remote_exec.py` — `run_cmd`: добавлен `try/finally` для гарантированного закрытия SSH-клиента; добавлен перехват `socket.timeout` с понятным `TimeoutError`
- `remote_exec.py` — `push`, `pull`: добавлены `try/finally` для SFTP и SSH-клиентов, исключающие утечки соединений при исключениях
- `routes/stocks.py` — `GET /api/chz/stock`: при отсутствии кеша возвращает 404 (было 200)
- `routes/stocks.py` — `POST /api/chz/refresh`: `Popen` обёрнут в `try/except OSError`, возвращает 500 при ошибке запуска
- `routes/stocks.py` — `near_expiry` переименован в `near_expiry_codes` и теперь считает количество кодов (было количество GTIN); семантика согласована с `total_codes`

**Почему:**
- Хранение пароля в исходном коде — критическая уязвимость
- Утечки SSH-сессий при сетевых сбоях накапливались на бар-ПК
- `near_expiry=1` рядом с `total_codes=50` вводило в заблуждение

**Файлы:**
- `remote_exec.py`
- `routes/stocks.py`

### 2026-04-21 — CHZ stock integration: Task 5 — add Flask cache endpoints

**Изменено:**
- `routes/stocks.py` — добавлен `GET /api/chz/stock`: читает `chz_test/debug/chz_stock.json` с диска, возвращает `{items, updated_at}`. При отсутствии файла — `{items:[], error:'no data'}`. При повреждённом JSON — 500 с `error:'cache corrupted or updating'`
- `routes/stocks.py` — добавлен `POST /api/chz/refresh`: запускает `remote_exec.py run stock` через `subprocess.Popen` (неблокирующий), возвращает `{status:'started'}`

**Почему:**
- `/api/stocks/chz` вызывает CHZ API напрямую, требует CryptoPro на сервере (недоступно на Render)
- Новые endpoints используют кеш-файл, обновляемый с бар-ПК по запросу

**Файлы:**
- `routes/stocks.py`

### 2026-04-21 — CHZ stock integration: Task 6 — verify result

**Проверено:**
- `chz_test/debug/chz_stock.json` содержит 30 GTIN, 16 с product_group=BEER, все 30 с непустыми expiration_dates
- `routes/stocks.py` проходит `python -m py_compile` без ошибок
- Оба endpoint `/api/chz/stock` и `/api/chz/refresh` присутствуют в коде

**Файлы:**
- `chz_test/debug/chz_stock.json`
- `routes/stocks.py`
- `docs/plans/chz-stock-integration.md`

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

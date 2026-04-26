# Changelog

### 2026-04-26 — Полная автоматизация выгрузки ЧЗ через dispenser API

**До:** пользователь руками выгружал CSV из ЛК ЧЗ (3 группы: beer/water/milk),
клал в `chz_test/debug/pg*_csv/`, запускал `chz.py csv`. Без ручного действия
данные устаревали (на момент диагностики CSV был 2-недельной давности).

**Теперь:** один POST-запрос → весь цикл автоматически на бар-ПК.

**Как работает:**
1. На бар-ПК `chz.py csv-auto` для каждой группы (beer/water/nabeer):
   - `POST /api/v3/true-api/dispenser/tasks` — создать задание `FILTERED_CIS_REPORT`
   - `GET /api/v3/true-api/dispenser/tasks/{id}` — опрашивать статус до COMPLETED
   - `GET /api/v3/true-api/dispenser/results` — получить resultId
   - `GET /api/v3/true-api/dispenser/results/{id}/file` — скачать ZIP
   - Распаковать ZIP, сохранить CSV в `chz_test/debug/pg{code}_csv/auto-*.csv`
2. После всех групп — `parse_chz_csv()` → перестроить `chz_stock.json`
3. Flask тянет JSON через SSH/SFTP

**productGroupCode:**
- 15 = BEER
- 13 = WATER
- 22 = NABEER (безалкогольное на пивной основе) — **новая группа**, в ручных
  выгрузках её не было

**Изменения:**
- `chz_test/chz.py` — добавлены: `dispenser_create_task`, `dispenser_poll`,
  `dispenser_get_result_id`, `dispenser_download`, `export_csv_via_dispenser`,
  CLI команда `csv-auto`. Парсер теперь умеет читать UTF-8 / cp1251 и
  распаковывать ZIP-ответы dispenser API.
- `remote_exec.py` — добавлен спец-режим `run csv-auto`: token refresh →
  csv-auto на бар-ПК → pull `chz_stock.json` локально.
- `routes/stocks.py` — `POST /api/chz/refresh` теперь дёргает `csv-auto`
  вместо устаревшего `stock`. Новый эндпоинт `GET /api/chz/refresh/status`
  для опроса прогресса (running, exit_code, log_tail, cache_updated_at).
- `templates/stocks.html` — кнопка «Обновить данные ЧЗ» во вкладке Сроки
  годности с polling-индикатором; после успеха таблица перезагружается.
- `core/chz_scheduler.py` (новый) — daemon-thread дёргает refresh раз в
  сутки (по умолчанию 03:00, env CHZ_REFRESH_HOUR / CHZ_REFRESH_MINUTE).
- `app.py` — стартует scheduler при запуске Flask, если `REMOTE_PASS` в env.

**Match rate с фрешем через dispenser:**

| Бар | До (CSV 12.04) | После (API 26.04) |
|---|---|---|
| Большой В.О | 82 | 96 |
| Лиговский | 52 | 76 |
| Кременчугская | 78 | 80 |
| Варшавская | 58 | 65 |
| Общая | 202 | 228 |

**Эксплуатация:**
- Флешем по кнопке: открыть Stocks → Сроки годности → «Обновить данные ЧЗ»
- Авторефреш: `REMOTE_PASS=xxx py app.py` → каждый день в 03:00
- Лог: `chz_test/debug/refresh.log` (truncate перед каждым refresh)
- Лимит ЧЗ: 10 заданий в сутки на одну товарную группу — для нас 1/день более чем достаточно

**На будущее:**
- Если в `chz.py` в DISPENSER_GROUPS добавить ещё группы (например milk
  если бар начнёт продавать молоко) — сразу подхватится.
- На бар-ПК нет апдейтера: новые версии `chz.py` пушит `remote_exec.py push`.

---

### 2026-04-26 — Обновление iiko XML-номенклатуры → +146% матчей с ЧЗ

**Диагностика match rate.** Из 366 позиций фасовки (Общая):
- 80 матчились с ЧЗ
- 141 «нет в XML iiko» — товар есть в OLAP-кэше, в XML-номенклатуре нет
- 144 «есть баркод, нет в ЧЗ» — баркод корректный, но GTIN отсутствует в выгрузке ЛК
- 1 без баркода вообще

**Корень:** `data/cache/nomenclature__products.xml` от 26.12.2025, не обновлялся
4 месяца. Среди 141 «не в XML» — 99 от поставщика «БЕЗ ИМЕНИ ОРГАНИЗ…»,
16 от ИП Степанов и др. — новые товары, появившиеся в продажах после 26.12.

**Решение:** скачали свежую XML через `/products` iiko API. Результат:
- 7866 → 8362 товаров (+496)
- 3953 → 4302 с баркодом (+349)
- 4295 → 4743 уникальных GTIN в карте

**Эффект на match rate:**

| Бар | Было | Стало |
|---|---|---|
| Большой В.О | 30 | 82 |
| Лиговский | 19 | 52 |
| Кременчугская | 33 | 78 |
| Варшавская | 23 | 58 |
| Общая | 82 | 202 |

Срочных <30д было 0-1, теперь 6 на юрлицо.

**На будущее:** XML-кэш надо периодически обновлять. Вариант — добавить
TTL в `core/iiko_barcodes.py` или endpoint `POST /api/iiko/refresh-xml`.

---

### 2026-04-26 — Точная привязка партий ЧЗ к конкретному бару через КПП

**Проблема предыдущей итерации:**
Эвристика «брать последние партии по дате производства под iiko-остаток» врала
при размазывании одного SKU по нескольким барам — одни и те же партии могли
показаться в разных барах. Пользователь это сразу заметил.

**Находка:** в **локальной документации ЧЗ** (`chz_test/чз/docs.crpt22.ru.html`,
str. 2743) описан CSV-формат `FILTERED_CIS_REPORT` — ровно тот же отчёт,
который выгружается из ЛК. У него 35 колонок, две из которых критичны:
- `kpp` — КПП места осуществления деятельности (МОД), где числится CIS
- `fiasId` — ФИАС-идентификатор адреса МОД

**Эти колонки уже есть в выгруженных CSV у пользователя**, просто игнорировались
старым парсером. Распределение по 3016 строкам:
- KPP 784201001 — 1043 кода (Кременчугская)
- KPP 780145001 — 738 кодов (Большой В.О.)
- KPP 781045001 — 710 кодов (Варшавская)
- KPP 781645001 — 343 кода (Лиговский)

**Маппинг бар↔КПП получен через `GET /api/v3/true-api/mods/list`** (новая
команда `python chz.py mods` — добавлена в [chz_test/chz.py](chz_test/chz.py)).
Ответ сохранён в `chz_test/debug/mods.json` с адресами всех 4 МОД.

**Изменено:**
- `chz_test/chz.py:parse_chz_csv` — извлекает `kpp` и `fiasId` из CSV,
  агрегирует по `(gtin, kpp, prod_date, exp_date)`. Каждый GTIN теперь имеет
  поле `by_kpp: [{kpp, fiasId, count, batches: [{prod, exp, count}]}, ...]`.
- `chz_test/chz.py` — новая CLI команда `mods` для запроса справочника МОД.
- `routes/stocks.py:get_bottles_with_expiry` — добавлен `bar_kpp_map`
  (bar1..bar4 → КПП), для конкретного бара берёт партии **только** из
  его слота `by_kpp[kpp]`. Эвристика «обрезаем под iiko-сток» удалена —
  данные точные, показываем все партии, которые числятся за этим баром.
  Добавлено поле `bar_chz_count` (коды на КПП этого бара) рядом с
  `chz_total_count` (по всему юрлицу).
- `templates/stocks.html` — UI показывает предупреждение «⚠ В ЧЗ за этим
  баром N кодов, в iiko M — касса не RETIRE'ит» когда `bar_chz_count > stock`,
  и второе строкой «по всему юрлицу: K кодов» если SKU размазан по 2+ барам.
- `remote_exec.py` — `mods` добавлено в `ALLOWED_SUBCMDS`.

**Результат на 2026-04-26:**
- Большой пр. В.О: 160 позиций / 30 с CHZ-привязкой
- Лиговский: 115 / 19
- Кременчугская: 158 / 33
- Варшавская: 116 / 23
- Общая (юрлицо): 366 / 82

Точные партии, не эвристика. Когда `bar_chz_count >> stock` — это явный сигнал
что касса этого бара не RETIRE'ит при продажах (cash доминирующий источник
ошибки учёта).

---

### 2026-04-25 — Стыковка iiko-фасовки со сроками годности из ЧЗ

**Контекст:**
Остатки фасовки в iiko (`/api/stocks/bottles`) и сроки годности в ЧЗ
(`/api/chz/stock`) лежали в разных витринах. Бар-менеджеру нужно было одним
взглядом видеть, что физически есть на полке его бара и что из этого скоро
протухнет.

**Решение:** новый эндпоинт `GET /api/stocks/expiry?bar=<bar>` и вкладка
«Сроки годности» в `templates/stocks.html`. Стыковка по `barcode (iiko)`
↔ `gtin (ЧЗ)` через нормализацию к 14 цифрам (`zfill(14)`).

**Изменено:**
- `core/iiko_barcodes.py` (новый) — `parse_barcodes_from_xml()` и
  `get_barcode_map()`. Парсит существующий `data/cache/nomenclature__products.xml`,
  строит `{gtin14: [product_id, ...]}` с in-memory кэшем (инвалидация по mtime).
  OLAP-номенклатура `nomenclature_full.json` баркодов не содержит, поэтому
  пришлось завести отдельный загрузчик из XML.
- `routes/stocks.py` — добавлен `GET /api/stocks/expiry`. Повторяет логику
  `/api/stocks/bottles` (фильтр по `FASOVKA_GROUP_ID`, баланс по складу,
  средние продажи за 30 дней) и обогащает позиции полями `gtins`,
  `expiration_dates`, `production_dates`, `nearest_expiry`, `days_to_expiry`,
  `has_chz_data`. Сортировка: срочные (<30д) сверху, без CHZ-данных в конце.
- `templates/stocks.html` — новая вкладка «Сроки годности» с таблицей по
  поставщикам, цветовой подсветкой (красный <30д, жёлтый <90д, серый без ЧЗ),
  блоком статистики (всего / с ЧЗ / срочных), отображением даты последнего
  обновления кэша ЧЗ.

**Результат (на 2026-04-25):**
- Бар «Лиговский»: 116 позиций фасовки, 31 сматчилась с ЧЗ.
- Все 4 бара (`bar=Общая`): 367 позиций, 82 сматчилось.
- Покрытие GTIN-баркод: 4295 GTIN из XML iiko, 155 из 541 ЧЗ-GTIN сматчены
  (29%) — остальные либо устаревшие позиции в ЧЗ (бар не делает RETIRE),
  либо товары без занесённого баркода в iiko.
- Сортировка проверена на реальных данных: просроченные (-135д) первыми,
  затем по nearest_expiry asc, без ЧЗ-данных — в конце.

**Что НЕ менялось:**
- `chz_test/chz.py` — парсер CSV-экспорта из прошлой сессии работает.
- `routes/stocks.py:get_bottles_stocks` — shape ответа сохранён, существующая
  вкладка «Фасовка» не сломана.
- `core/olap_reports.py` — баркоды добавлены не туда (отдельный модуль),
  чтобы не ломать существующий disk-cache `nomenclature_full.json`.

---

### 2026-04-25 — CHZ stock: переход с API search на CSV-парсер (РАБОЧЕЕ РЕШЕНИЕ)

**Контекст проблемы:**
API `/cises/search` возвращал только 30 GTIN / 173 кода для ИНВЕСТАГРО, тогда как
в реальности у бара 540+ позиций. Расследование показало:
1. API режет страницы до 100 записей (игнорирует `limit=1000`) — пагинация рвалась
   из-за условия `len(items) < limit`.
2. Без фильтра по дате API возвращает 79,000+ INTRODUCED кодов — историческое
   накопление за все годы (бар не делает RETIRE при продажах).
3. CSV-экспорт через ЛК ЧЗ применяет фильтры `participantInn + packageType=UNIT`
   и возвращает реальный текущий склад.

**Решение:** парсить CSV-экспорты из ЛК ЧЗ вместо использования API search.

**Изменено:**
- `chz_test/chz.py` — добавлена функция `parse_chz_csv()`. Читает все
  `chz_test/debug/pg*_csv/*.csv`, фильтрует по `status=INTRODUCED + packageType=UNIT
  + ownerInn=INN_ORG`, агрегирует по GTIN.
- `chz_test/chz.py` — добавлена CLI-команда `python chz.py csv` для построения
  `chz_stock.json` из CSV-экспортов.
- `chz_test/chz.py:298` — `limit = 100` (был 1000) — это реальный потолок API.
- `chz_test/chz.py:267` — `delay_between_pages=0` (был 1) — задержка не нужна.
- `chz_test/chz.py:496-500` — убран дефолтный фильтр по дате 180 дней (он отрезал
  валидный сток с long-shelf-life продуктами).
- `chz_test/test_filters.py` — диагностический скрипт для тестирования параметров
  фильтра API (ownerInn vs participantInn vs packageType).

**Результат:**
- Было: 30 GTIN, 173 кода (через API)
- Стало: 541 GTIN, 2878 кодов (через CSV) — увеличение в 18 раз

**Workflow для пользователя:**
1. Скачать CSV-экспорт из ЛК ЧЗ для нужных групп (beer/nabeer/water/etc.)
2. Распакованные папки положить в `chz_test/debug/pg*_csv/`
3. Запустить `python chz_test/chz.py csv`
4. Данные доступны через `GET /api/chz/stock`

**Замечание:** 203 из 541 GTIN имеют просроченные expiration_dates (2024 год) —
это коды, которые бар не закрыл RETIRE-операцией. Это проблема учёта на стороне
бара, не нашего парсера.

**Файлы:** `chz_test/chz.py`, `chz_test/test_filters.py`, `chz_test/debug/chz_stock.json`

---

### 2026-04-25 — CHZ stock integration: code review pass 4 — bug fixes and docs

**Изменено:**
- `routes/stocks.py:647` — `GET /api/chz/stock`: добавлен HTTP 404 при отсутствии кеша (ранее возвращался 200, что противоречило документации в README и plan).
- `routes/stocks.py:660-676` — `POST /api/chz/refresh`: `_refresh_proc` теперь используется как guard — при уже запущенном refresh возвращает 409 вместо запуска параллельного SSH-процесса. Popen-результат присваивается в модульную переменную.
- `chz_test/chz.py:703-705` — удалён дублирующий default для `date_from` из `main()` — он уже есть в `get_chz_stock()` (добавлен в этой ветке). Два одинаковых defaults = риск расхождения при будущих изменениях.
- `docs/stocks.md` — создан (требование CLAUDE.md: документ на каждый модуль).
- `docs/plans/chz-stock-integration.md` — добавлен статус DONE (2026-04-22).

**Почему:**
- Несоответствие 200 vs 404 нарушало API-контракт, описанный в README.
- Параллельные refreshes создавали два SSH-процесса, записывающих в один файл одновременно.
- `date_from` default в двух местах означал, что изменение периода в одном месте тихо не применится к другому.

**Файлы:** `routes/stocks.py`, `chz_test/chz.py`, `docs/stocks.md`, `docs/plans/chz-stock-integration.md`

---

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

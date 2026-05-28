# Open-check Telegram bot

## Что это

Отдельный Telegram-бот (не KULT Taplist), который **ежедневно в 14:59 МСК** проверяет в iiko, открыта ли касса в каждом из 4 баров KULT:

- **Все 4 открыты** → одно сообщение в групповой чат.
- **Хоть один закрыт** → ЛС каждому из админов со списком закрытых баров.
- **iiko недоступен** → ЛС каждому админу с текстом ошибки (отдельный формат, не путаем с «все закрыты»).

Хендлеров команд у бота нет — только outbound-отправка. Поэтому webhook регистрировать не нужно.

## Файлы

| Файл | Что делает |
|---|---|
| [core/open_check_bot.py](../core/open_check_bot.py) | Логика проверки, форматирование, отправка (sync, через `requests`) |
| [core/open_check_telegram.py](../core/open_check_telegram.py) | Telegram HTTP API + интерактивное меню (inline-кнопки) + webhook-хелперы |
| [core/open_check_subscribers.py](../core/open_check_subscribers.py) | Хранилище подписанных чатов (`data/open_check_subscribers.json` + portalocker) |
| [core/open_check_scheduler.py](../core/open_check_scheduler.py) | Daemon-thread, ежедневный запуск в 14:59 МСК, защита от двойного срабатывания |
| [routes/open_check.py](../routes/open_check.py) | `run-now` (ручной триггер) + webhook-эндпоинты бота |
| [app.py](../app.py) | Стартует шедулер рядом с CHZ |
| [render.yaml](../render.yaml) | env vars нового бота |

## Меню подключения чатов (интерактив)

Чтобы не вписывать chat_id руками, бот принимает команды и показывает меню.

**Как пользоваться:**
1. Личный чат: написать боту `/start`. Группа: добавить бота и написать `/start@kultura_open_bot`.
2. Появятся кнопки: «Сюда слать: все открыто», «Сюда слать: тревоги», «Подключить оба типа», «Отключить этот чат», «Статус».
3. Нажатие подписывает **текущий** чат на выбранный тип. Подписки хранятся в `data/open_check_subscribers.json`.

**Кто в итоге получает уведомления** (`send_report`):
- «Все открыто» → `TELEGRAM_GROUP_CHAT_ID` (env) + подписчики `positive` (меню).
- Тревоги/ошибки → `TELEGRAM_ALARM_CHAT_IDS` (env) + подписчики `alarm` (меню).
- Списки объединяются и дедуплицируются. То есть env и меню работают вместе.

**Webhook (нужен для интерактива):**
- `POST /telegram/openbot/webhook` — точка входа Telegram. Проверяет секрет в заголовке `X-Telegram-Bot-Api-Secret-Token` (выводится из токена, отдельная env не нужна).
- `GET /telegram/openbot/setup-webhook` — зарегистрировать webhook у Telegram (вызвать **один раз** после деплоя). Также ставит командное меню `/start`, `/status`.
- `GET /telegram/openbot/webhook-info` — диагностика.
- `POST /telegram/openbot/delete-webhook` — снять webhook.

Реализация на чистом `requests` (без aiogram, без async) — бот простой, синхронный путь надёжнее и тестируется локально.

## Как работает

### 1. Источник данных «бар открыт»

Используется готовый `IikoAPI.get_cash_shifts(date_from, date_to, status='OPEN')` ([core/iiko_api.py:215-269](../core/iiko_api.py#L215-L269)). Запрашивается диапазон **yesterday..today** — ночная смена, открытая вчера и ещё не закрытая, имеет `openDate=вчера`; без `yesterday` она потерялась бы.

`pointOfSaleId` маппится в имя точки через `get_groups_with_pos()` ([core/iiko_api.py:271-310](../core/iiko_api.py#L271-L310)), а имя точки → ключ бара через `BAR_NAME_MAPPING` + `normalize_bar_name` из [core/employee_plans.py:19-55](../core/employee_plans.py#L19-L55).

**Важно:** в кассовых сменах iiko имена точек НЕ совпадают с OLAP `Store.Name`. В сменах «Кременчугская» называется **«Пивная культура»**, плюс есть 5-я точка **«Планерная»** (`planernaya`, не входит в 4 канонических бара). Поэтому используется `BAR_NAME_MAPPING` (он построен под имена из смен), а НЕ `venues_config.IIKO_NAME_TO_KEY` (тот под OLAP-имена и «Пивную культуру» не знает — иначе Кременчугская ложно числилась бы закрытой каждый день).

Бар считается открытым, если в выдаче есть смена этого `pointOfSaleId` с `_parse_iso_datetime(openDate) <= check_dt`. `_parse_iso_datetime` уже отдаёт МСК naive ([core/iiko_api.py:198-209](../core/iiko_api.py#L198-L209)) — без таймзонных приключений. Открытая «Планерная» попадает в `other_open` (только в лог), на статус 4 баров не влияет.

### 2. Матрица результата → действие

| Состояние | Куда | Формат |
|---|---|---|
| `closed_keys == []` | Получатели «всё открыто» | `Open-check` + построчно `<код> — <время>` |
| `closed_keys != []` | Получатели тревог | `Open-check ALARM` + `Закрыты: …` + открытые с временем |
| `iiko_error=True` | Получатели тревог | `Open-check ERROR` + причина |

Сокращённые имена баров (`BAR_SHORT_NAMES` в open_check_bot.py): ВО, Лиг, Крем, Варш.
Время — старт самой свежей открытой кассовой смены бара (`open_times`).

Примеры:
```
Open-check 14:59 МСК
Все 4 бара открыты:
ВО — 14:30
Лиг — 13:58
Крем — 14:26
Варш — 13:26
```
```
Open-check ALARM 14:59 МСК
Закрыты: Крем, Варш
Открыты:
ВО — 14:30
Лиг — 13:58
```

`other_open` (открытая 5-я точка «Планерная») и `unknown_pos` (имя POS, которое вообще не маппится) выводятся только в лог, в сообщения не идут.

### 3. Расписание

`core/open_check_scheduler.py` повторяет паттерн `core/chz_scheduler.py` (daemon-thread, `_seconds_until_next_run`, `time.sleep`), но с тремя отличиями:

1. **Явный МСК**: `datetime.now(MOSCOW_TZ)` вместо локального — на Render контейнер UTC.
2. **Lock-файл** в `data/.open_check_lock_YYYY-MM-DD`, atomic test-and-set через `os.open(O_CREAT | O_EXCL)`. Под `gunicorn --workers 2` оба воркера импортят app и запускают шедулер; в 14:59 первый берёт lock, второй ловит `FileExistsError` и тихо выходит.
3. **Гейт по env**: без `TELEGRAM_OPEN_CHECK_BOT_TOKEN` шедулер не стартует (аналог `REMOTE_PASS` в CHZ).

Старые lock-файлы (>2 дней) убираются при `start_scheduler()`.

### 4. Конфигурация (env vars)

| Env | Назначение |
|---|---|
| `TELEGRAM_OPEN_CHECK_BOT_TOKEN` | Токен бота из @BotFather (новый, не KULT Taplist). Без него шедулер не стартует. |
| `TELEGRAM_GROUP_CHAT_ID` | Numeric chat_id группового чата. Туда уходит позитивный отчёт. |
| `TELEGRAM_ALARM_CHAT_IDS` | Comma-separated numeric chat_id'ы админов. Туда уходят алармы и ошибки. |
| `OPEN_CHECK_HOUR` | Час срабатывания МСК (default 14). |
| `OPEN_CHECK_MINUTE` | Минута срабатывания МСК (default 59). |
| `OPEN_CHECK_DRY_RUN` | `1` → все сообщения шлёт первому `TELEGRAM_ALARM_CHAT_IDS` с префиксом `[DRY-RUN]`, в группу не пишет. |
| `REMOTE_PASS` | Используется существующий env. Защищает `POST /api/admin/open-check/run-now`. |

### 5. Получение chat_id

Бот не отвечает на сообщения, поэтому стандартный подход:
- Пользователь пишет любое сообщение боту @userinfobot и копирует свой numeric chat_id → в `TELEGRAM_ALARM_CHAT_IDS`.
- Группа: бот добавляется в группу, потом курлим `https://api.telegram.org/bot<TOKEN>/getUpdates` — там видно `chat.id` с минусом (отрицательное число для групп) → в `TELEGRAM_GROUP_CHAT_ID`.

### 6. Тестирование

**Локально:**
```
TELEGRAM_OPEN_CHECK_BOT_TOKEN=<test_token> \
TELEGRAM_GROUP_CHAT_ID=<my_chat_id> \
TELEGRAM_ALARM_CHAT_IDS=<my_chat_id> \
OPEN_CHECK_DRY_RUN=1 \
python -c "from core.open_check_bot import run_check; import json; print(json.dumps(run_check(), indent=2, default=str))"
```

**На проде:**
```
curl -X POST "https://beerkultura.ru/api/admin/open-check/run-now" \
  -H "X-Remote-Pass: $REMOTE_PASS"
```

Эндпоинт возвращает JSON-результат с состоянием 4 баров и отчётом об отправке.

## Деталь реализации: без aiogram

Изначально отправка шла через aiogram, но бот простой (отчёт + меню), поэтому весь open-check переведён на синхронный `requests` напрямую к Telegram Bot API ([core/open_check_telegram.py](../core/open_check_telegram.py)). `send_report` синхронный, `run_check` без `asyncio`. Плюсы: нет async-плумбинга, нет утечки `aiohttp.ClientSession`, работает и тестируется в окружении без aiogram.

## Changelog

### 2026-05-18 — Open-check telegram bot

**Что:**
- Новый бот, ежедневная проверка открытых смен в 4 барах KULT в 14:59 МСК.
- Позитив → группа; алармы и ошибки iiko → ЛС админам.
- Atomic file lock для защиты от double-fire под `gunicorn --workers 2`.
- DRY-RUN режим для проверки логики без шума в чате.

**Почему:**
- Ручной мониторинг открытия касс — операционная рутина, легко автоматизируется через уже доступный `iiko cashshifts` API.
- Существующий KULT Taplist бот не тронут (отдельный токен, отдельный файл) — у него скомпрометированный токен в коде, и задачи разные.

**Файлы:**
- `core/open_check_bot.py`, `core/open_check_scheduler.py`, `routes/open_check.py` — новые.
- `routes/__init__.py`, `app.py`, `render.yaml` — правки на интеграцию.
- `docs/open-check-bot.md` (этот файл), `docs/CHANGELOG.md`, `.claude/INDEX.md` — документация.

**Техдолг (отдельная задача):**
- `core/chz_scheduler.py` тоже двоит под `--workers 2`. Текущий CHZ refresh идемпотентен, поэтому не критично, но паттерн с lock-файлом стоит туда же добавить.

# Open-check Telegram bot

## Что это

Отдельный Telegram-бот (не KULT Taplist), который **ежедневно в 14:59 МСК** проверяет в iiko, открыта ли касса в каждом из 4 баров KULT:

- **Все 4 открыты** → одно сообщение в групповой чат.
- **Хоть один закрыт** → ЛС каждому из админов со списком закрытых баров.
- **iiko недоступен** → ЛС каждому админу с текстом ошибки (отдельный формат, не путаем с «все закрыты»).

Помимо ежедневного авто-оповещения, бот интерактивный: человек открывает бота, жмёт одну кнопку «Подписаться» — и его чат начинает получать уведомления. Команды `/start` (меню подписки), `/status` (статус баров сейчас) и переключение подписки забираются через **long-polling** (`getUpdates`), а не через webhook: входящие соединения от Telegram до сервера блокируются на магистрали (см. раздел «Блокировки»). Получатели = env-чаты ПЛЮС самоподписавшиеся.

## Файлы

| Файл | Что делает |
|---|---|
| [core/open_check_bot.py](../core/open_check_bot.py) | Логика проверки, форматирование, отправка (sync, через `requests`) |
| [core/open_check_telegram.py](../core/open_check_telegram.py) | Telegram HTTP API + меню подписки (кнопка) + команды `/start` `/status` `/temp` + webhook-хелперы |
| [core/open_check_subscribers.py](../core/open_check_subscribers.py) | Хранилище самоподписавшихся чатов (`open_check_subscribers.json`, единый список + portalocker) |
| [core/open_check_polling.py](../core/open_check_polling.py) | Long-polling getUpdates (входящие команды/кнопки; webhook не доставляется из-за блокировок) |
| [core/open_check_scheduler.py](../core/open_check_scheduler.py) | Daemon-thread, ежедневный запуск в 14:59 МСК, защита от двойного срабатывания |
| [routes/open_check.py](../routes/open_check.py) | `run-now` (ручной триггер) + webhook-эндпоинты бота |
| [app.py](../app.py) | Стартует шедулер рядом с CHZ |
| [render.yaml](../render.yaml) | env vars нового бота |

## Меню подписки и команды

Самоподписка в одно нажатие (раньше было 5 кнопок positive/alarm/both/off/status —
упрощено по запросу владельца до одного переключателя):

1. Человек открывает бота → `/start`. В группе: `/start@kultura_open_bot`.
2. Бот показывает короткое описание, «Уведомления приходят в этот чат: да/нет», «ID этого чата» и кнопки:
   - **Подписаться на уведомления** / **Отписаться от уведомлений** — переключатель (callback `oc_on` / `oc_off`).
   - **Статус баров сейчас** — живой опрос iiko (callback `oc_status`), то же что команда `/status`.
   - **Температура в барах** — живой опрос термометров Tuya (callback `oc_temp`), то же что команда `/temp`.
3. Подписавшийся чат получает **все** типы уведомлений (и «все открыты», и тревоги, и ошибки iiko). Раздельного выбора нет.

Команды (дублируют кнопки для тех, кто любит текст): `/status`, `/temp` (`/temperature`, `/t`), `/subscribe`, `/unsubscribe` (`/stop`).

`/temp` опрашивает термометры по 4 барам через Tuya Cloud и отвечает короткой сводкой
(те же данные, что страница [/temperature](temperature.md)): `ВО — 24.0 C, влажность 62%`
и т.д.; бар вне нормы (холодно/тепло/жарко) или без данных помечается жирным. Формат и
окраска по диапазонам — общие со страницей. Реализация: `_live_temperature_text()` в
[core/open_check_telegram.py](../core/open_check_telegram.py), показания —
[core/tuya_temperature.py](../core/tuya_temperature.py).

Подписки хранятся в `open_check_subscribers.json` (единый список `{"chats":[...]}`,
[core/open_check_subscribers.py](../core/open_check_subscribers.py)). Старый формат
`{"positive":[],"alarm":[]}` читается с миграцией на лету — существующие подписчики не теряются.

**Кому уходят авто-оповещения** (`send_report`) — env ПЛЮС самоподписавшиеся, объединяются и дедуплицируются:
- «Все открыто» → `TELEGRAM_GROUP_CHAT_ID` + подписчики.
- Тревоги/ошибки → `TELEGRAM_ALARM_CHAT_IDS` (comma-separated) + подписчики.

**Доставка команд: long-polling (основной режим).**
`core/open_check_polling.py` — daemon-thread, стартует из app.py. Снимает webhook
(не сбрасывая очередь) и крутит `getUpdates(timeout=25)` → `handle_update()`.
Singleton под `gunicorn --workers 2`: эксклюзивный flock (portalocker) на
`data/.open_check_polling.lock` живёт, пока жив процесс; второй воркер лок не
получает и тихо выходит, replacement-воркер подхватывает. Отключение:
`OPEN_CHECK_POLLING=0`.

**Webhook (выключен, оставлен как fallback):**
- `POST /telegram/openbot/webhook` — точка входа Telegram. Проверяет секрет в заголовке `X-Telegram-Bot-Api-Secret-Token` (выводится из токена, отдельная env не нужна).
- `GET /telegram/openbot/setup-webhook` — зарегистрировать webhook у Telegram. Также ставит командное меню `/start`, `/status`, `/temp`. **Не вызывать при включённом polling** — polling снимет webhook обратно при первом 409.
- `GET /telegram/openbot/webhook-info` — диагностика (`getWebhookInfo`).
- `POST /telegram/openbot/delete-webhook` — снять webhook.

Webhook не работает, пока ТСПУ блокирует входящие соединения от Telegram
(см. «Блокировки»). Если когда-нибудь домен переедет за Cloudflare-прокси —
можно выставить `OPEN_CHECK_POLLING=0` и вернуть setup-webhook.

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
| `closed_keys == []` | Получатели «всё открыто» | `Все 4 бара открыты — HH:MM МСК` + построчно `<код> — <время>` |
| `closed_keys != []` | Получатели тревог | `!!! ALARM !!!` + `ЗАКРЫТ(Ы) — …` (обе строки жирным) + открытые с временем |
| `iiko_error=True` | Получатели тревог | `!!! ОШИБКА: iiko недоступен !!!` (жирным) + причина |

Сокращённые имена баров (`BAR_SHORT_NAMES` в open_check_bot.py): ВО, Лиг, Крем, Варш.
Время — старт самой свежей открытой кассовой смены бара (`open_times`).
Тревога и ошибка шлются с `parse_mode=HTML` (жирные заголовки, `send_message(..., html=True)`);
динамический текст ошибок iiko экранируется `html.escape`. ЗАКРЫТ/ЗАКРЫТЫ — по числу баров.
Первая строка сообщения видна в пуш-уведомлении и списке чатов, поэтому тревога начинается с ALARM.

Примеры:
```
Все 4 бара открыты — 14:59 МСК
ВО — 14:30
Лиг — 13:58
Крем — 14:26
Варш — 13:26
```
```
<b>!!! ALARM !!!</b>
<b>ЗАКРЫТЫ — Крем, Варш</b>
Проверка 14:59 МСК
Открыты:
ВО — 14:30
Лиг — 13:58
```
```
<b>!!! ОШИБКА: iiko недоступен !!!</b>
Проверка 14:59 МСК не выполнена
Причина: auth_failed
```

Ответ на команду `/status` (`format_status_reply`) — спокойный тон, по запросу пользователя, без «ALARM»; закрытые помечены жирным:
```
Статус на 15:30 МСК
ВО — открыт (14:30)
Лиг — открыт (13:58)
<b>Крем — закрыт</b>
Варш — открыт (13:26)
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

Проще всего — написать боту `/start`: он ответит строкой «ID этого чата: …». Альтернативы:
- Пользователь пишет любое сообщение боту @userinfobot и копирует свой numeric chat_id → в `TELEGRAM_ALARM_CHAT_IDS`.
- Группа: добавить бота в группу и написать `/start@kultura_open_bot` — в ответе будет `chat.id` с минусом (отрицательное число для групп) → в `TELEGRAM_GROUP_CHAT_ID`.

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

## Блокировки: связь сервер ↔ Telegram

Инцидент 2026-06-12: бот перестал отвечать на команды, исходящая отправка
тоже отвалилась после 14:59. Диагностика показала:

- **Исходящие**: системный DNS отдаёт для `api.telegram.org` адрес
  `149.154.166.110` — он заблокирован на магистрали (ТСПУ) для датацентровых
  сетей (таймаут со всех проверенных российских ДЦ, из Европы доступен).
  Соседний `149.154.167.220` из того же пула при этом доступен. До инцидента
  DNS отдавал «живой» IP — бот работал, пока выдача не переключилась.
- **Входящие**: SYN-пакеты от подсетей Telegram (`149.154.160.0/20`,
  `91.108.4.0/22`) вообще не доходят до сервера (tcpdump 150с — ноль пакетов
  при активных ретраях доставки webhook). Локальный файрвол чист (fail2ban
  только sshd, iptables без блоков) — режется до сервера, локально не лечится.

**Решение:**
1. Исходящие — пин IP в `docker-compose.yml` → `extra_hosts:
   "api.telegram.org:149.154.167.220"` (контейнер в `network_mode: host`,
   но `/etc/hosts` у него свой, extra_hosts работает).
2. Входящие — long-polling вместо webhook (`core/open_check_polling.py`):
   команды забираются исходящими `getUpdates`, входящая связь не нужна.
3. Самолечение при блокировке запиненного IP — `api_call` в
   `core/open_check_telegram.py` при сбое основного пути автоматически
   пробует запасные адреса: TLS к голому IP с SNI и проверкой сертификата
   на имя api.telegram.org + заголовок `Host`. Кандидаты: кэш последнего
   живого → статический `_FALLBACK_IPS` → текущие A-записи через DoH
   (dns.google / cloudflare-dns.com — мимо системного DNS). После сбоя
   основного пути 5 минут (`_PRIMARY_COOLDOWN`) запросы идут сразу через
   запасной, потом основной пробуется снова. В логах переключение видно
   по `TG: переключился на запасной IP ...`.

**Если бот замолчал совсем** (значит, недоступны и запиненный, и все
запасные IP) — найти живой адрес и обновить пин + `_FALLBACK_IPS`:

```
ssh root@139.100.200.92
# кандидаты — A-записи api.telegram.org из разных ротаций и соседние подсети:
for ip in 149.154.167.220 149.154.166.110 149.154.167.99 149.154.165.120; do
  printf '%s: ' $ip; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 https://$ip/ || echo timeout
done
```

Живой IP прописать в `extra_hosts` в docker-compose.yml (и первым в
`_FALLBACK_IPS`), передеплоить. Диагностика доставки со стороны Telegram:
`GET /telegram/openbot/webhook-info` (при включённом polling должен
показывать пустой `url`).

## Деталь реализации: без aiogram

Изначально отправка шла через aiogram, но бот простой, поэтому весь open-check переведён на синхронный `requests` напрямую к Telegram Bot API ([core/open_check_telegram.py](../core/open_check_telegram.py)). `send_report` синхронный, `run_check` без `asyncio`. Плюсы: нет async-плумбинга, нет утечки `aiohttp.ClientSession`, работает и тестируется в окружении без aiogram.

## Changelog

### 2026-07-11 — Кнопка «Возможная инкассация» (/cash)

Кнопка в меню + команда `/cash` (`/incass`, `/касса`, `/инкассация`): сколько
наличных можно забрать с каждого бара по **последней сданной кассе** (наличные в
сейфе на конец смены — ручной пересчёт бармена из графика, **без iiko**).

- Инкассируем всё сверх минимума на размен `CASH_CHANGE_FLOAT_RUB = 5000 ₽` — в
  каждом баре остаётся размен. Формула: `к инкассации = max(0, наличные − 5000)`.
  Чистая функция `collectable_kop` (тест `test_collectable_math`).
- Данные — `ShiftsManager.get_latest_cash_by_location()`: самая свежая смена с
  непустым `cash_end_kop` по каждой точке (тест `test_latest_cash_by_location`).
  Показывается дата кассы (свежесть) и «нет данных», если бар кассу не сдавал.
- Формат — блок на бар (жирное имя + «забрать N ₽», деталь «в сейфе / касса от»
  отдельной строкой, пустая строка между барами — чтобы цифры не слипались, html),
  снизу жирный итог к инкассации по сети.
- Файлы: `core/open_check_telegram.py` (кнопка/callback `oc_cash`, команда,
  `_live_cash_collection_text`), `core/shifts_manager.py`.

### 2026-06-29 — Команда /temp: температура баров из бота

- Добавлена команда `/temp` (алиасы `/temperature`, `/t`) и кнопка «Температура в барах»
  в меню — живой опрос термометров Tuya по 4 барам, короткая сводка (температура +
  влажность; бар вне нормы холодно/тепло/жарко или без данных — жирным). Те же показания,
  что страница [/temperature](temperature.md).
- `set_my_commands` теперь регистрирует `/temp`; добавлены `_live_temperature_text()`,
  кнопка/коллбэк `oc_temp`, ветка команды в `handle_update`.
- Файлы: `core/open_check_telegram.py`. Опирается на `core/tuya_temperature.py`.
- **Тревога по высокой температуре** переиспользует чаты тревог этого бота: если в баре
  выше 26 C, фоновый опрос температуры шлёт аларм в `_alarm_recipients()` (как о закрытом
  баре). Логика и антиспам — в `core/temperature_alarm.py`, см. [temperature.md](temperature.md).

### 2026-06-17 — Ложное «ЗАКРЫТ — Варш»: дробные секунды iiko + Python 3.10

**Problem:** бот слал «ЗАКРЫТ — Варш» при открытой смене Варшавской; локально
(Python 3.14) всё верно, на проде (контейнер, Python 3.10) — «закрыт».

**Root cause:** `openDate` Варшавской был `2026-06-17T13:42:51.45` (2 цифры
дробной секунды). `datetime.fromisoformat` в Python 3.10 требует ровно 3/6 цифр →
`ValueError` → `_parse_iso_datetime` возвращал `None` → смена молча отбрасывалась
в `check_bars_state`. Остальные бары имели 3-значную дробь. Полный разбор —
[docs/lessons.md](lessons.md).

**Что:**
- **Фикс (корень):** `IikoAPI._parse_iso_datetime` нормализует дробную часть
  секунд до 6 цифр перед парсингом — работает на всех версиях Python.
- **Защита (заодно):** в `check_bars_state` добавлен резерв
  `pointOfSaleId -> venue_key` (`_SEED_POS_MAP` + learned-кэш
  `open_check_pos_map.json`) на случай неполной выдачи `/corporation/groups`:
  смена с неизвестным `pos_id` логируется и берётся из резерва, а не теряется молча.

**Файлы:** `core/iiko_api.py`, `core/open_check_bot.py`; `docs/lessons.md`,
`docs/open-check-bot.md`, `docs/CHANGELOG.md`.

### 2026-06-17 — Самоподписка одной кнопкой (упрощённая, вместо удалённых подписок)

Откат к самоподписке после правки 2026-06-16: владелец уточнил, что человек должен
**сам** подписываться, открыв бота. Но не «простыня» из 5 кнопок, а один переключатель.

**Что:**
- Возвращён `core/open_check_subscribers.py`, но упрощён: единый список `{"chats":[...]}`
  вместо раздельных `positive`/`alarm`. Подписчик получает все типы уведомлений.
  Старый формат читается с миграцией на лету (существующие подписчики не теряются).
- В `open_check_telegram.py` вернулись `_menu_keyboard` (одна кнопка-переключатель
  подписки + «Статус баров сейчас»), `answer_callback`, `edit_message_text`,
  обработка `callback_query` (`_handle_callback`). Команды: `/start` (меню),
  `/status`, `/subscribe`, `/unsubscribe`/`/stop`.
- `_positive_recipients` / `_alarm_recipients` снова подмешивают `subs.get_recipients()`.
- `allowed_updates` (polling и `set_webhook`) опять включает `callback_query`.

**Почему:** самоподписка нужна (новый человек подключается сам), а сложность была
в выборе типов уведомлений — его и убрали. Теперь: открыл бота → одна кнопка → готово.

**Hardening (по адверсариальному ревью):**
- `_read` логирует битый JSON и сохраняет `.corrupt`-копию (не теряем подписчиков молча);
  невалидные chat_id (None/дробные/мусор) отбрасываются с логом.
- `_handle_callback` отвечает рано при отсутствии callback id (кнопка не «зависает»),
  меню рисуется по уже известному состоянию (без повторного чтения файла).
- `_poll_loop` прогоняет исключения через `_scrub` (в URL requests есть токен бота).
- Read-путь (`get_recipients`/`is_subscribed`) намеренно без лока — атомарная запись
  делает чтение безопасным, а критичный `send_report` не зависит от захвата лока.

**Файлы:** `core/open_check_subscribers.py` (заново), `core/open_check_bot.py`,
`core/open_check_telegram.py`, `core/open_check_polling.py`, `routes/open_check.py`.

### 2026-06-16 — Упрощение: только авто-оповещения + /status, подписки убраны (отменено 2026-06-17)

**Что:**
- Убраны inline-меню и система подписок: удалён `core/open_check_subscribers.py`,
  из `open_check_telegram.py` убраны `_menu_keyboard`, `answer_callback`,
  `edit_message_text` и вся обработка `callback_query`.
- Получатели авто-оповещений теперь только из env (`TELEGRAM_GROUP_CHAT_ID`,
  `TELEGRAM_ALARM_CHAT_IDS`) — `_positive_recipients` / `_alarm_recipients`
  больше не подмешивают подписчиков.
- `/status` переосмыслен: вместо «что получает этот чат» теперь опрашивает iiko
  и присылает статус 4 баров на текущий момент (`format_status_reply` в
  open_check_bot.py). `/start` — короткая справка + ID чата.
- `set_my_commands` вызывается при старте polling; `allowed_updates` сужен до
  `["message"]` (callback больше не нужен).

**Почему:** по запросу владельца — меню/подписки оказались лишней сложностью.
Боту нужны ровно две функции: всегда слать оповещения и отдавать статус по запросу.

**Файлы:** `core/open_check_bot.py`, `core/open_check_telegram.py`,
`core/open_check_polling.py`, `routes/open_check.py`; удалён
`core/open_check_subscribers.py`.

### 2026-06-13 — Новые шаблоны сообщений: без «Open-check», заметная тревога

**Что:** позитив — «Все 4 бара открыты — HH:MM МСК»; тревога — жирные
`!!! ALARM !!!` и `ЗАКРЫТ(Ы) — <бары>` (HTML parse_mode); ошибка iiko —
жирный заголовок + экранированная причина. По запросу владельца.

### 2026-06-13 — Автоперебор запасных IP api.telegram.org

**Что:** `api_call` при сбое основного пути (запиненного IP) сам пробует
запасные адреса (SNI-коннект по голому IP + DoH-резолв), кэширует живой,
держит 5-минутный кулдаун на основной путь. Ручная смена пина нужна теперь
только если заблокируют все адреса разом.

**Почему:** запиненный IP — единственная точка отказа после фикса 2026-06-12;
прецедент блокировки соседнего адреса уже был.

### 2026-06-12 — Long-polling вместо webhook, пин IP api.telegram.org

**Что:**
- `core/open_check_polling.py` — getUpdates-цикл в daemon-thread, singleton
  через flock; webhook снят (без сброса очереди недоставленных команд).
- `docker-compose.yml` — `extra_hosts: api.telegram.org:149.154.167.220`.
- Раздел «Блокировки» в этом доке.

**Почему:** ТСПУ режет входящие соединения от Telegram до сервера (webhook
мёртв), а DNS стал отдавать заблокированный IP для api.telegram.org
(исходящие мертвы). Подробности и инструкция по смене IP — раздел «Блокировки».

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

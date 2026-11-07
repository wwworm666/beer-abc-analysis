# Боты Telegram: какие есть, где работают, кто через кого пишет

## Что это

Карта всех ботов проекта на одной странице: что каждый делает, где работает, как получает
сообщения, где его токен и **кто через какого бота пишет**. Составлена 2026-11-07 по коду (у
каждого утверждения — файл), потому что по памяти и по старым документам картина
путалась: «модуль импортирует `core/open_check_telegram.py`» ещё не значит «пишет от
open-check бота» — этот модуль общий для всех ботов сайта (см. «Главная ловушка»).

Подробности каждого бота — в его документе; здесь — как они связаны.

**Имена** (решение владельца 2026-11-07): **kultura.os** — сайт (beerkultura.ru);
**kultura.research** — ИИ-бот для анализа через MCP (@MCPkulturabot); **kultura.pulse** — бот
опозданий (открыты ли кассы), инкассации, температуры и отзывов (@kultura_open_bot, в коде —
open-check). У гостевого бота @kult_taplist_bot своего имени нет. Имя и описания каждый из двух
названных ботов ставит себе сам при запуске (раздел 3 и 4) — в @BotFather их не правят.

| Бот | Для кого | Где работает | Код | Токен (имя, не значение) | Сообщения получает | Обновляется |
|---|---|---|---|---|---|---|
| **@MCPkulturabot**, имя в чатах **kultura.research** | владелец и администраторы сайта | **отдельный сервер в Амстердаме**, служба systemd `kultura-bot` | `kultura_bot/` | на странице «Доступ агентов» (`mcp.db`), запасной — `TELEGRAM_MCP_BOT_TOKEN` | long polling напрямую | сам: таймер раз в 2 минуты забирает `main` с GitHub |
| **@kultura_open_bot**, имя в чатах **kultura.pulse** (в коде — open-check, «kulturaopenclosed») | команда: статус касс, тревоги, отзывы | **сервер сайта** (Selectel, Россия), контейнер `beer-app`, поток внутри сайта | `core/open_check_*.py` | `TELEGRAM_OPEN_CHECK_BOT_TOKEN` в `.env` сайта | long polling через обход блокировок | вместе с сайтом (выкладка после тестов) |
| **@kult_taplist_bot** (гостевой) | гости баров | **сервер сайта**, тот же контейнер `beer-app` | `core/taplist_polling.py` | `TELEGRAM_BOT_TOKEN` в `.env` сайта | long polling через обход блокировок | вместе с сайтом |

Серверов два: kultura.research — в Амстердаме, open-check и гостевой — оба на сервере сайта в
России. Четвёртый токен, `TELEGRAM_CONTENT_BOT_TOKEN`, — необязательный «бот каналов» для
постов контент-плана: задан — посты в каналы баров идут от него, не задан — от гостевого бота
(раздел 5). Какой задан на проде, видно на странице контент-плана, «Каналы и отправка» (имя
бота каналов; `token_source` в `GET /api/content-plan/channels`).

### Кто через какого бота пишет

| Что уходит | От какого бота | Кому | Когда | Код |
|---|---|---|---|---|
| Ответы на вопросы, отчёты, меню, справка | kultura.research | тому, кто спросил (подключённый администратор) | на каждый вопрос | `kultura_bot/engine/` |
| Графики и выжимки отчётов kultura.research | kultura.research — но шлёт **сайт**, токеном этого бота | в чат вопроса | когда модель вызывает `common_chart_send` / `common_report_send` | `kultura_bot/charts/send.py` |
| Сводка «открыты ли кассы» | open-check | «все открыты» — `TELEGRAM_GROUP_CHAT_ID` + подписчики; «закрыт» или iiko не ответил — `TELEGRAM_ALARM_CHAT_IDS` + подписчики | 14:59 МСК; недоставленное — досылка раз в 5 минут до конца дня | `core/open_check_bot.py`, `open_check_scheduler.py`, `open_check_pending.py` |
| Новые отзывы с Яндекс Карт | open-check | только подписчики | после каждой проверки отзывов: раз в 3 часа и полный проход в 08:30 МСК | `core/review_notify.py`, `core/yandex_reviews_scheduler.py` |
| Новые отзывы из гостевого бота | open-check (не гостевой!) | только подписчики | сразу после отзыва, пропущенные — подбор раз в 10 минут | `core/taplist_polling.py` -> `core/review_notify.py` |
| Сторож отзывов: «не обновлялись больше суток», «на Картах больше, чем у нас» и «снова в порядке» | open-check | подписчики | проверка раз в 15 минут | `core/yandex_reviews_watchdog.py` |
| Температура: «ЖАРКО» (выше 26 °C), «ХОЛОДНО» (ниже 19 °C) | open-check | `TELEGRAM_ALARM_CHAT_IDS` + подписчики | раз в `TUYA_POLL_MINUTES`, одно сообщение на пересечение порога; с 01:00 до 15:00 МСК молчит | `core/temperature_alarm.py`, `core/temperature_scheduler.py` |
| «Приёмка ждёт разбора» (бухгалтерии) | open-check | только `RECEIVING_NOTIFY_CHAT_IDS` (подписчики не получают) | когда в закрытой приёмке есть новые, похожие или восстановленные позиции | `core/receiving_notify.py` |
| Фиды Яндекса не обновились | open-check | `TELEGRAM_ALARM_CHAT_IDS` + подписчики | не чаще раза в день: снимок в 05:00 МСК не снялся или с ошибкой | `core/yml_scheduler.py` |
| Сообщение владельцу от ИИ-агента | open-check | чат отчётов агентов (`notify_chat_id`, выбирается на «Доступ агентов») | MCP-инструмент `common_notify_owner`, не больше 30 в сутки | `core/mcp/tools/common.py` |
| Сторож kultura.research: бот молчит, Claude не отвечает, бот в ошибке, «снова отвечает» | open-check — чтобы дошло, даже если упал сам kultura.research | `notify_chat_id` | проверка раз в минуту, напоминание раз в 6 часов | `kultura_bot/watchdog.py` |
| Краны, подписка, отзывы — ответы гостю | гостевой | гостю | на команды и кнопки | `core/taplist_polling.py` |
| Рассылки гостям (площадка «Бот» контент-плана) | гостевой — **только** он | подписчики гостевого бота (все, по бару, «были за 30 дней», «пропали 60 дней») | по расписанию контент-плана или кнопкой «Отправить сейчас» | `core/content_publisher.py`, `core/content_channels.py` |
| Ответ бара на отзыв гостя из бота | гостевой | этому гостю | кнопка «Отправить гостю в Telegram» на «Отзывы» или MCP `content_review_send_reply` | `routes/reviews.py` |
| Посты в каналы баров, проверка канала, «Проверка связи с сайтом», напоминания об Instagram | бот каналов `TELEGRAM_CONTENT_BOT_TOKEN`, если задан, иначе гостевой | каналы баров, владелец | по расписанию контент-плана | `core/content_channels.py` (`channel_bot_token`), `core/content_publisher.py` |

### Главная ловушка

`core/open_check_telegram.py` — не только open-check бот, а общий для сайта транспорт к
Telegram с обходом блокировок (`api_call`, `api_call_files`). Им пользуются все три бота, когда
пишет сервер сайта. Если вызвать `api_call` **без токена**, сообщение молча уйдёт **от open-check
бота** (`core/open_check_telegram.py`, `_token()`); `send_message`, `answer_callback`,
`edit_message_text` токена не принимают вовсе и всегда пишут от open-check. Поэтому каждый вызов
от имени другого бота передаёт свой токен и заранее проверяет, что он не пустой
(`core/content_publisher.py`, `routes/reviews.py`, `kultura_bot/charts/send.py`,
`routes/tg_miniapp.py`, `core/taplist_polling.py`).

Гостю может писать только гостевой бот: гость запускал его, другой бот получит от Telegram 403, и
отправщик пометил бы гостя «заблокировал бота» (`core/content_channels.py`, `guest_bot_token`).

## Файлы

**kultura.research (@MCPkulturabot)** — подробно в [kultura-bot.md](kultura-bot.md):

| Файл | Роль |
|---|---|
| `kultura_bot/engine/` | сам бот на сервере в Амстердаме: приём сообщений, Claude, инструменты сайта по MCP, ответы |
| `kultura_bot/settings.py`, `prompts/`, `agents/`, `assets/` | все несекретные настройки, инструкции, агенты, аватарка |
| `kultura_bot/deploy/` | установка одной командой и самообновление (`install.sh`, `update.sh`, службы systemd) |
| `kultura_bot/credentials.py`, `access.py`, `store.py`, `site_api.py`, `journal.py`, `watchdog.py` | сторона сайта: секреты, привязки Telegram, приём отчётов, журнал, сторож |
| `kultura_bot/charts/` | графики и отчёты: рисует и шлёт сайт ([tg-miniapp.md](tg-miniapp.md)) |
| `routes/bot_api.py`, `routes/mcp.py`, `routes/bot_journal.py`, `routes/tg_miniapp.py` | API для сервера бота, раздел «Бот» на «Доступ агентов», журнал, мини-приложение |

**open-check (@kultura_open_bot)** — подробно в [open-check-bot.md](open-check-bot.md):

| Файл | Роль |
|---|---|
| `core/open_check_telegram.py` | транспорт к Telegram с обходом блокировок (общий для сайта), меню, команды и кнопки бота |
| `core/open_check_polling.py` | приём сообщений: long polling в одном воркере (замок `data/.open_check_polling.lock`) |
| `core/open_check_scheduler.py` | проверка в 14:59, догоняющий прогон после перезапуска, досылка |
| `core/open_check_bot.py` | проверка касс в iiko, тексты, получатели, отправка с повтором |
| `core/open_check_subscribers.py`, `core/open_check_pending.py` | подписчики, очередь досылки |
| `routes/open_check.py` | ручной прогон `POST /api/admin/open-check/run-now`, запасной webhook (не работает, раздел 7) |

**Гостевой (@kult_taplist_bot)** — подробно в [guides/TELEGRAM_BOT_GUIDE.md](guides/TELEGRAM_BOT_GUIDE.md):

| Файл | Роль |
|---|---|
| `core/taplist_polling.py` | весь бот: long polling в одном воркере (замок `data/.taplist_polling.lock`), меню, краны, подписка, отзывы |
| `core/taplist_post.py`, `core/untappd_registry.py` | текст кранов: название со ссылкой на Untappd, стиль, крепость |
| `core/guest_subscribers.py` | подписчики и шаг диалога (SQLite `guest_subscribers.db`) |
| `core/guest_reviews.py` | отзывы гостей (`guest_reviews.json`, источник `bot`) |
| `core/content_channels.py`, `core/content_publisher.py`, `core/content_publisher_scheduler.py` | рассылки гостям и посты в каналы: какой бот пишет, расписание |
| `telegram_webhook.py`, `telegram_bot.py` (корень репозитория) | **наследие**, раздел 7 |

**Сервер сайта:** `Dockerfile`, `docker-compose.yml`, `.github/workflows/deploy.yml`,
`scripts/deploy/beer-deploy.sh`, `app.py` (`_start_background_jobs`), [guides/deploy.md](guides/deploy.md).

## Как работает

### 1. Сервер сайта (Selectel, Россия): open-check и гостевой

**Выкладка:** push в `main` -> GitHub Actions гоняет тесты -> только после них SSH с ограниченным
ключом и командой `deploy <коммит>` -> на сервере `scripts/deploy/beer-deploy.sh` (на сервере —
`/usr/local/sbin/beer-deploy`): fast-forward в `/opt/beer`, сборка образа, пересоздание контейнера
`app`, проверка `/login`, при сбое — откат (`.github/workflows/deploy.yml`,
`scripts/deploy/beer-deploy.sh`).

**Контейнеры:** `beer-app` (gunicorn) и `beer-caddy` (HTTPS), оба `network_mode: host`. Данные —
тома на хосте: `/srv/kultura` -> `/kultura` (базы и JSON: подписчики, отзывы, `mcp.db`),
`/srv/beer/data` -> `/app/data` (замки, служебные файлы) (`docker-compose.yml`).

**Потоки ботов внутри сайта.** gunicorn — 2 воркера по 4 потока, без `--preload` (`Dockerfile`), поэтому
`_start_background_jobs()` из `app.py` выполняется в **каждом** воркере; `BEER_SCHEDULERS=0`
выключает всё. Двойной работы нет:

| Поток | Сколько | Почему не дважды |
|---|---|---|
| приём сообщений open-check | один | flock `data/.open_check_polling.lock`; второй воркер выходит, сменщик берёт замок при старте |
| приём сообщений гостевого | один | flock `data/.taplist_polling.lock` |
| проверка в 14:59 и досылка | в обоих | дневной замок `.open_check_lock_<дата>` (`O_CREAT \| O_EXCL`), досылка — с захватом записи |
| публикации контент-плана | один | flock `data/.content_publisher.lock` |
| сторож kultura.research | в обоих | одна строка `bot_watchdog` в `mcp.db`: сообщение отправляет тот воркер, чей `UPDATE` прошёл |

Выключатели по отдельности: `OPEN_CHECK_POLLING=0`, `TAPLIST_POLLING=0`, `CONTENT_PUBLISH=0`.

**Сеть.** Входящие от Telegram до сервера режет ТСПУ — webhook не доходит, поэтому оба бота сами
забирают сообщения (`getUpdates`, ожидание 25 с). Исходящие: `api.telegram.org` прибит к живому
адресу в `docker-compose.yml` (`extra_hosts`); не отвечает — `api_call` пробует запасные адреса с
SNI и проверкой сертификата, затем адреса из DoH; после сбоя 300 с ходит сразу запасным путём, на
соединение — 3 попытки (`core/open_check_telegram.py`). Этим путём идут **все** вызовы Telegram с
сервера сайта: open-check, гостевой, контент-план, графики kultura.research, сторож, ответы на отзывы.

**Секреты:** `/opt/beer/.env` на сервере сайта — `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_OPEN_CHECK_BOT_TOKEN`, `TELEGRAM_GROUP_CHAT_ID`, `TELEGRAM_ALARM_CHAT_IDS`,
необязательный `TELEGRAM_CONTENT_BOT_TOKEN`, запасные `TELEGRAM_MCP_BOT_TOKEN` и
`KULTURA_BOT_ANTHROPIC_KEY` ([guides/deploy.md](guides/deploy.md), `.env.example`).

### 2. Сервер в Амстердаме: kultura.research

Почему отдельно: API Anthropic (Claude) из России недоступен; на сервер сайта ничего, что зовёт
Claude, не ставится (`.claude/CLAUDE.md`).

**Установка** — один раз командой со страницы «Доступ агентов» («Команда установки»,
`kultura_bot/deploy/install.sh`): пользователь `kultura-bot`, частичный клон одной папки
`kultura_bot/` в `/opt/kultura-bot/repo`, `/opt/kultura-bot/venv`, `/etc/kultura-bot.env` (ключ
сервера бота и адрес сайта, права 600), службы `kultura-bot` (`python -m kultura_bot`,
`Restart=always`, данные — `/var/lib/kultura-bot`) и `kultura-bot-update.timer`.

**Самообновление:** таймер раз в 2 минуты запускает `update.sh`: забирает `main`; поменялось
что-то в `kultura_bot/` — обновляет код, зависимости, службы и перезапускает бота. **Результат
тестов не ждёт** (раздел 7). Та же папка входит и в образ сайта: сторона сайта (`credentials`,
`site_api`, `watchdog`, `charts`) выходит обычной выкладкой сайта.

**Связь с сайтом:** по HTTPS с ключом сервера бота (статический MCP-токен): данные —
инструменты сайта по MCP (`/mcp`); настройки и учёт — `/api/bot/*` (`routes/bot_api.py`):
`config` (токен Telegram, ключ Anthropic, пауза; раз в 30 с), `link`, `actor/<id>`, `report`
(состояние и расход раз в минуту), `note`, `replied`, `chat-format`, `rich-demo`, `journal`,
`journal/feedback`. В Telegram сервер ходит напрямую, без обхода.

**Секреты:** токен Telegram и ключ Anthropic — только на «Доступ агентов» (в `mcp.db` на сервере
сайта), сервер бота берёт их у сайта; у него самого — только ключ сервера (`/etc/kultura-bot.env`).

### 3. kultura.research (@MCPkulturabot)

ИИ-помощник владельца на Claude: отвечает обычными словами по данным сайта (около 250
инструментов MCP — те же расчёты, что у страниц).

- **Доступ:** только администратор сайта, подключивший свой Telegram одноразовой ссылкой
  («Подключить мой Telegram» на «Доступ агентов» -> `/start <код>`). В группе — если к боту
  обратились (`@`, ответ на его сообщение, команда `/…@бот`). Остальным — «Это закрытый бот».
- **Меню** (`settings.MENU`): `/sales` (продажи и планы), `/stock` (остатки, заказы и краны),
  `/staff` (смены и зарплаты), `/content` (контент и отзывы) — готовые вопросы кнопками;
  `/report` (отчёт страницей), `/new` (новый диалог), `/help`. Вне меню: `/rich` (вид ответов),
  `/start`.
- **Что умеет:** ответы с цифрами и «Как считается»; агенты (Аналитик, Зарплаты и график, Контент)
  для больших задач; отчёт страницей в мини-приложении; графики с кнопкой «Открыть
  интерактивно»; фото и PDF в вопросе; продолжение прошлой работы ответом на сообщение бота;
  кнопки следующего шага; богатые сообщения (`/rich`).
- **Учёт:** журнал вопросов и ответов на сайте (`/admin/bot/journal`, только администраторы),
  оценка реакцией под ответом; дневной предел $15 на человека и $2 на вопрос; сторож пишет владельцу,
  если бот замолчал.
- **Профиль:** имя kultura.research (до 2026-11-07 было kultura.os — это имя сайта), описания, аватарка и меню — в `settings.py`; сервер бота ставит их
  сам при запуске и удаляет старые меню, которые Telegram показывал вместо общего.

### 4. kultura.pulse — open-check (@kultura_open_bot)

- **Имя и описания** (`core/open_check_telegram.py`: `BOT_NAME` = `kultura.pulse`,
  `BOT_SHORT_DESCRIPTION`, `BOT_DESCRIPTION`) ставит сайт при старте приёма сообщений
  (`sync_profile` из `core/open_check_polling.py`), только если в Telegram другое. Аватарку — нет
  (её ставят в @BotFather).

- **Команды и кнопки** (`core/open_check_telegram.py`, `handle_update`): `/start` (`/menu`,
  `/help`) — описание, «подписан: да/нет», ID чата и кнопки:
  - «Подписаться / Отписаться» (`/subscribe`, `/unsubscribe`, `/stop`) — сразу на все уведомления;
  - «Статус баров сейчас» (`/status`) — живой запрос в iiko: по 4 барам «открыт (ЧЧ:ММ)» или
    «закрыт»;
  - «Температура в барах» (`/temp`, `/temperature`, `/t`, `/температура`) — датчики Tuya,
    вне нормы — жирным;
  - «Возможная инкассация» (`/cash`, `/incass`, `/инкассация`, `/касса`) — сколько забрать из
    сейфа по последней сданной кассе из графика: вниз до тысячи (сейф − 5 000 ₽ на размен);
  - «Последние отзывы» (`/reviews`, `/отзывы`) — пять свежих с Яндекс Карт и из гостевого бота и
    сколько ждут ответа.
  В Telegram зарегистрированы 5 команд: start, status, temp, cash, reviews. На прочий текст бот
  не отвечает.
- **Рассылки** — таблица «Кто через какого бота пишет» выше. Два списка получателей
  (`core/open_check_bot.py`): «позитив» — `TELEGRAM_GROUP_CHAT_ID` + подписчики, «тревоги» —
  `TELEGRAM_ALARM_CHAT_IDS` + подписчики. Подписчик получает всё: и «все открыты», и тревоги.
- **Данные** (`/kultura` на проде): `open_check_subscribers.json` (подписчики, только на
  сервере), `open_check_pending.json` (очередь досылки на день), `open_check_pos_map.json`
  (касса -> бар); замки — в `data/`.
- **Настройки:** `TELEGRAM_OPEN_CHECK_BOT_TOKEN` (без него нет ни проверки, ни приёма, ни
  рассылок), `TELEGRAM_GROUP_CHAT_ID`, `TELEGRAM_ALARM_CHAT_IDS`, `OPEN_CHECK_HOUR` /
  `OPEN_CHECK_MINUTE`, `OPEN_CHECK_DRY_RUN` (каждое сообщение — только первому из своего списка
  получателей, с пометкой `[DRY-RUN]`), `OPEN_CHECK_POLLING`; для рассылок —
  `RECEIVING_NOTIFY_CHAT_IDS`, `YANDEX_REVIEWS_NOTIFY`, `TUYA_ALARM_*`, `TUYA_POLL_MINUTES`.
- **Ручной прогон проверки:** `POST /api/admin/open-check/run-now` (администратор) или
  MCP `staff_open_check_run_now`.

### 5. Гостевой (@kult_taplist_bot)

- **Команды** (`core/taplist_polling.py`, `_COMMANDS`): `/start`, `/help`, `/taplist` — кнопки
  четырёх баров и «Все бары»; `/taplist1`–`/taplist4`, `/taplistall` — краны бара: «{кран}.
  {пивоварня и название} — {стиль}, {крепость}%», название — ссылка на Untappd (данные — файл
  кранов `taps_data.json`, реестр Untappd, `resources/taplist_post_names.json`).
- **Подписка на новости** (`/subscribe`, только в личке): согласие с версией текста -> выбор баров
  -> телефон кнопкой или «Пропустить». `/stop` — отписка в любой момент, стирает телефон и в
  отзывах.
- **Отзыв** (`/review`, только в личке): бар -> оценка 1–5 -> текст или «без текста»; не больше 3 в
  сутки с чата. Отзыв ложится в «Отзывы» сайта, владельцу о нём сообщает **open-check** бот.
- Кнопки подписки и отзыва в меню бота и команды `/subscribe`, `/review` в списке — только когда
  на странице контент-плана включено «Кнопки подписки и отзывов в боте» (`bot.signup`, по
  умолчанию выключено).
- **Ссылки для QR:** `t.me/kult_taplist_bot?start=subscribe`, `?start=review`, `?start=review_<бар>`.
- **В группах** — только краны.
- **Что шлёт сайт:** рассылки гостям, ответ бара на отзыв, а если не задан
  `TELEGRAM_CONTENT_BOT_TOKEN` — и посты в каналы баров (таблица выше). Рассылки и посты
  включаются на `/content-plan`, «Каналы и отправка» (`enabled`, `bot.enabled`).
- **Данные** (`/kultura` на проде): `guest_subscribers.db` (подписчики, согласие, телефон, шаг
  диалога), `guest_reviews.json`, `content_channels.json` (выключатели и имя бота),
  `content_plan.json` (ход рассылок).

### 6. Как понять, что бот жив

| Бот | Где смотреть |
|---|---|
| kultura.research | строка состояния на «Доступ агентов» (отчёта нет 3 минуты — «давно не отзывался»); сторож пишет в чат отчётов агентов; на сервере бота — `systemctl status kultura-bot`, `journalctl -u kultura-bot -f`, `journalctl -u kultura-bot-update -n 50` |
| open-check, гостевой | страницы состояния нет — только журнал контейнера: `docker logs beer-app` (или `docker compose logs app`); искать `[OPEN-CHECK-POLL] polling стартовал`, `[TAPLIST-POLL] polling стартовал`, `TG: переключился на запасной IP`. `GET /telegram/openbot/webhook-info`: пустой адрес — значит, работает приём сообщений сам |

### 7. Известные проблемы (на 2026-11-07)

1. **У open-check бота нет списка допуска.** Любой, кто найдёт бота, может смотреть `/status`,
   `/temp`, `/reviews`, `/cash` (сколько наличных забрать из сейфа) и подписаться на все
   уведомления — проверки доступа в `handle_update` нет. Решить владельцу: кого пускать
   (например, как kultura.research — только подключённых администраторов).
2. **Запасной webhook open-check не сработает:** `/telegram/openbot/webhook` не входит в
   `PUBLIC_ENDPOINTS` (`core/auth_guard.py`), запрос Telegram без входа получит отказ. Работает
   только приём сообщений самим ботом.
3. **`/telegram/setup-webhook` (гостевой) — для любого вошедшего, не только администратора:**
   ставит webhook с `drop_pending_updates=True` — накопленные сообщения гостей теряются, потом
   приём сообщений снимает webhook. Не вызывать.
4. **Наследие гостевого бота:** `telegram_webhook.py` загружается при каждом старте сайта
   (`extensions.py`) и обслуживает `/telegram/webhook`, но умеет только краны (без подписки и
   отзывов); `telegram_bot.py` нигде не запускается и с сайта данные уже не получит (маршрут
   кранов закрыт входом).
5. **kultura.research обновляется без тестов:** сервер в Амстердаме забирает `main` раз в 2 минуты, не
   дожидаясь CI, — сломанный `main` дойдёт до бота раньше, чем тесты его поймают (сайт
   выкладывается только после тестов).
6. **Нет внешнего наблюдения за сервером сайта.** Сторож kultura.research шлёт через open-check бота из
   того же контейнера: упал `beer-app` — молчат оба бота сайта и сторож.
7. **`render.yaml` — наследие** (сайт давно на Selectel). Если сервис на Render ещё жив и смотрит
   на репозиторий, он запустит те же приёмы сообщений с теми же токенами — Telegram будет
   отдавать сообщения то туда, то сюда (409). Проверить в панели Render и удалить сервис.
8. **409 молча:** приёмы сообщений сайта считают любой ответ 409 спором с webhook и повторяют;
   чужая программа на том же токене видна только по строкам `TG getUpdates -> …` в журнале.

### Что сломается при неверной правке

- Вызвать `api_call` без токена от имени гостевого бота или kultura.research — сообщение уйдёт от
  open-check бота (и получатель его не поймёт).
- Писать гостю не гостевым ботом — Telegram ответит 403, отправщик пометит гостя
  «заблокировал бота».
- Убрать замки приёма сообщений или запустить бот с тем же токеном ещё где-то (Render,
  компьютер для разработки) — 409, потерянные и двойные ответы.
- Поставить на сервер сайта что-то, что зовёт Claude, — из России API Anthropic недоступен.
- Путать ботов в документах — так появилась эта страница.

## Changelog

- **2026-11-07 (2)** — имена: kultura.os — сайт, kultura.research — @MCPkulturabot (было
  kultura.os), kultura.pulse — @kultura_open_bot (имя и описания ставит сайт, `sync_profile`).

- **2026-11-07** — страница создана по коду (все три бота, серверы, кто через кого пишет,
  известные проблемы). Заодно поправлены расхождения в [open-check-bot.md](open-check-bot.md),
  [guides/TELEGRAM_BOT_GUIDE.md](guides/TELEGRAM_BOT_GUIDE.md), [overview.md](overview.md),
  [lessons.md](lessons.md) и текст `/start` open-check бота; из `lessons.md` убрано начало старого
  токена.

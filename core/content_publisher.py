"""
Отправка утверждённых публикаций контент-плана: Telegram-каналы баров (сам),
Instagram (напоминание владельцу), рассылка гостям через гостевого бота.

## Что это

Утверждённое размещение (status 'approved') в своё время уходит в площадку — если
владелец подключил её в «Каналы и отправка» (core/content_channels.py) и включил
отправку. Не подключено — всё как раньше: «Время вышло, выход не отмечен», выход
отмечают вручную. Отправщик вызывается раз в минуту (core/content_publisher_scheduler.py)
и кнопкой «Отправить сейчас» (POST /api/content-plan/publish-now).

## Файлы

| Файл | Роль |
|------|------|
| `core/content_publisher.py` | этот модуль: что пора отправлять, отправка, проверка канала, тестовое сообщение |
| `core/content_publisher_scheduler.py` | фоновый поток: publish_due раз в минуту, один процесс на все воркеры |
| `core/content_channels.py` | настройки каналов, выключатели, подписчики бота |
| `core/content_plan.py` | план; все изменения — `ContentPlanStore.delivery_update` под его блокировкой |
| `core/open_check_telegram.py` | транспорт: api_call (JSON) и api_call_files (файлы), обход блокировок ТСПУ |
| `tests/test_content_publisher.py` | тесты с поддельным транспортом (в настоящий Telegram — ничего) |

## Как работает

### Что пора отправлять (publish_due)

Время — Москва, с точностью до минуты (как весь контент-план). Для каждого
размещения status 'approved' с датой и временем:

    пост   = дата+время размещения
    начало = пост; у Instagram — пост минус reminder_minutes_before
    пора   = max(начало, delivery.retry_at) <= сейчас
             («Отправить сейчас» и продолжение рассылки — retry_at <= сейчас)
    поздно = max(пост, retry_at) <= сейчас − GRACE_MINUTES (120)

«Поздно» и «раньше подключения» — от времени ПОСТА, не напоминания (проверка
2026-09-28: Instagram, утверждённый днём при «напоминать за 720 минут», оставался
без напоминания). Время напоминания прошло, а пост впереди — напоминание сразу.

- поздно: Telegram и бот — failed «Время выхода прошло, пока сервер не работал:
  проверьте и отправьте повторно» (пост не выходит с опозданием молча — решает
  владелец, кнопка «Повторить» отправит сразу); рассылка, которая уже кому-то
  дошла, — остановка «дошло N из M»; Instagram — напоминание не шлётся,
  delivery.state 'reminder_late' (один раз).
- Площадка не подключена (канал бара не проверен, нет чата напоминаний или он
  совпадает с каналом бара, рассылки выключены) — пропуск: размещение остаётся
  «Время вышло», как до подключения.
- Время поста раньше подключения площадки (content_channels.since_for) и это не
  повтор — пропуск: накопленный до подключения хвост отмечают вручную, отправщик
  его не выпускает и не помечает ошибкой.
- Главный выключатель выключен — ничего не отправляется: все, кому пора, — в
  skipped. Нет токена бота — то же.
- Instagram: напоминание для этого времени поста уже было (delivery.reminded_for =
  время поста) — пропуск; пост перенесли — напоминание взводится заново.
- Рассылка бота, которая вышла, но дошла не всем, после «Повторить неудавшимся»
  (retry_failed: status 'published', delivery.state 'queued') — тоже в очереди.

Порядок в проходе: сначала посты каналов и напоминания, потом рассылки с бюджетом
MAILING_BUDGET_SEC (40 с) на проход; рассылка, не уложившаяся в бюджет, сохраняет
прогресс и продолжается в следующем проходе (delivery.continuation, без дублей —
по sent_to). Журнал: 'delivery_progress'.

### Идемпотентность

Перед вызовом Telegram размещение под блокировкой хранилища помечается
delivery = {state: 'sending', attempt_id, started_at, heartbeat_at}; второй
отправщик такое размещение не возьмёт, правки плана получают 409 (SENDING_CONFLICT:
текст, файлы, сдвиг, размещение). После — published (published_at, published_by
'бот', delivery.chat, delivery.message_ids) или failed (failed_error — понятным
русским текстом). Итог пишется, только если попытка своя (attempt_id совпадает);
попытку потеряли (размещение изменили или удалили) — строка в журнал материала с
тем, что ушло (_lost).

«Отправляется» дольше SENDING_STALE_MINUTES (10) без отметки heartbeat_at —
процесс умер посреди отправки. Такое размещение НЕ отправляется повторно
(пост мог уже выйти): failed «Статус отправки неизвестен: проверьте канал; если
поста нет — «Повторить»». У рассылки получатели последней пачки (pending) — в
unknown_to: им повтор не шлёт. Отправляет только планировщик (один на сервер); свою
ещё идущую попытку (_ACTIVE_ATTEMPTS) он зависшей не считает.

### Ответы Telegram

- ok — отправлено; соединение не установилось (запрос точно не ушёл) — повторяет
  транспорт (core/open_check_telegram: 3 попытки, запасные адреса);
- отправка идёт с safe_resend=True: после ReadTimeout, обрыва посреди соединения
  или ответа не-JSON запрос мог дойти — транспорт НЕ шлёт его запасным путём
  (проверка 2026-09-28: 2–4 копии поста в канале);
- нет ответа, запрос мог дойти (None, last_outcome 'unknown') — «Telegram не
  ответил (нет связи): пост мог не выйти — проверьте канал; если поста нет —
  «Повторить»»; в рассылке — статус неизвестен (unknown_to), повтор не шлётся;
- нет ответа, но все пути отказали до отправки (last_outcome 'not_sent') —
  NOT_SENT_TEXT; в рассылке — failed_to, «Повторить неудавшимся» безопасен;
- 429 — повтор один раз через retry_after секунд, если ждать не дольше
  RETRY_AFTER_MAX_SEC (60 с); иначе ошибка. В рассылке 429 не ждётся: продолжение
  в следующем проходе;
- 5xx — failed «Telegram временно не отвечает (ошибка N)» без повтора;
- 403 в рассылке — гость заблокировал бота: guest_subscribers.mark_blocked(chat_id);
- прочие 4xx — failed с переводом частых описаний («канал не найден», «у бота нет
  права публиковать» …) и исходным текстом Telegram в скобках.

### Что отправляется

Текст и файлы — из снимка утверждения (approved_snapshot: что утвердил владелец).
У материала с актуальными данными (kind 'live') шаблон собирается в момент
отправки: render_live(источник, бар, шаблон, дата размещения, площадка, есть ли
файлы); стоп-правило (ok False) — failed «Публикация остановлена: <проблемы>».
До отправки проверяются пределы площадки (4096 без файлов, 1024 подпись с
файлами; Instagram 2200; Telegram и бот — в единицах UTF-16, эмодзи — 2:
content_plan.text_units), число файлов (до 10), наличие файлов на диске и их
общий размер (UPLOAD_TOTAL_MAX = 50 МБ на одно сообщение: предел загрузки файла
ботом; больше одним запросом не шлём — память сервера и таймаут).

- Telegram-канал бара: без файлов — sendMessage (без parse_mode, предпросмотр
  ссылок включён); 1 файл — sendPhoto / sendVideo с подписью; 2..10 — sendMediaGroup
  (подпись у первого). Живой таплист несёт ссылки на Untappd — сущности text_link
  (render_live, entities): у текста — entities, у подписи — caption_entities;
  такой текст уходит без предпросмотра ссылки (иначе под постом — карточка первого
  пива). Рассылка бота шлёт те же сущности. Файлы — multipart с диска
  (content_media). Загруженный файл Telegram возвращает с file_id — следующие чаты
  за тот же проход получают его по file_id без повторной загрузки (4 бара — одна
  загрузка).
- Instagram — ручной канал. В момент выхода минус reminder_minutes_before в чат
  напоминаний уходят: заголовок «Instagram: пора выложить — «<название>», <дата
  время>» со ссылкой на карточку https://beerkultura.ru/content-plan?open=<id>;
  текст подписи отдельным сообщением (удобно скопировать); фото и видео альбомом.
  Размещение остаётся approved, delivery.state 'reminded' (reminded_at,
  reminded_for — время поста) — напоминание одно на время поста; «вышло» владелец
  отмечает сам. Сбой — 'reminder_failed' без автоповтора (повторить — «Отправить
  сейчас»). Чат напоминаний совпал с каналом бара — не шлётся (заметка ушла бы
  подписчикам канала).
- Рассылка бота — ТОЛЬКО гостевым ботом @kult_taplist_bot (TELEGRAM_BOT_TOKEN,
  guest_transport): гость запускал его; отдельный бот контента писать гостю не может
  (403 пометил бы всех «заблокировал»). Посты, проверка канала, тест и напоминание
  об Instagram — бот каналов (TELEGRAM_CONTENT_BOT_TOKEN, иначе тот же гостевой).
  file_id у каждого бота свой — кэш раздельный.
  Получатели — core/guest_subscribers.recipients(сегмент, бар) на
  момент первого запуска (список хранится: M не меняется); каждому — то же
  сообщение, не чаще BOT_RATE_PER_SEC = 25 сообщений в секунду (лимит Telegram
  ~30/с на бота, запас на ответы бота гостям; альбом из k файлов — k сообщений).
  Прогресс пишется после каждой пачки из BOT_BATCH = 25 (sent_to, failed_to,
  blocked, pending, heartbeat_at): сбой посреди рассылки не шлёт повторно тем,
  кому ушло. Повтор (retry / retry_failed) шлёт только тем, кому не дошло и кто
  всё ещё подписан (отписавшиеся — unsubscribed, им не шлём). Три обрыва связи
  подряд (NETWORK_ABORT_AFTER) — рассылка останавливается, остальные — в failed_to.
  Перед каждой пачкой настройки перечитываются: выключены отправка или рассылки —
  стоп; пауза и отмена ставят delivery.stop_requested — стоп перед следующей пачкой;
  между проходами отправку выключали и включали — стоп (switch_marks). Остановка —
  content_plan.stop_mailing: не получившие — в failed_to, кому-то дошло — published
  «partial», никому — 'stopped'.
  Итог: published, delivery.stats {total, sent, failed, blocked, unsubscribed,
  unknown}; sent < total — подпись «дошло N из M» и действие retry_failed. Не дошло
  никому — failed; в аудитории никого — failed «В аудитории нет ни одного
  подписчика». Рассылки выключены (bot.enabled false) — ничего не шлётся.

Журнал плана: 'auto_publish' (вышло), 'auto_failed' (ошибка, остановка, потерянная
попытка), 'reminder' (напоминание об Instagram), 'delivery_progress' (рассылка
продолжится в следующем проходе), 'publish_now' («Отправить сейчас», подпись — кто
нажал).

### «Отправить сейчас» (publish_now)

Только утверждённое; отправка должна быть включена, площадка подключена, бот
настроен, планировщик работает (CONTENT_PUBLISH не '0'), иначе 409 с причиной.
Только ставит в очередь (delivery.state 'queued', retry_at = сейчас, send_now):
отправляет планировщик в ближайший проход, ответ — «Уйдёт в течение минуты».
Раньше отправка шла в веб-запросе, рассылка — потоком в веб-воркере (перезапуск
воркера рвал её, два потока — 50 сообщений в секунду). {дата} у живых материалов —
сегодняшняя дата (данные — на сейчас).

### Проверка канала и тестовое сообщение

check_channel: getMe -> getChat -> getChatMember(бот). can_post: у канала —
создатель или администратор с правом «Публикация сообщений» (can_post_messages);
у группы — участник, администратор или создатель; личный чат — нет
(PRIVATE_CHAT_TEXT). Результат сохраняется у бара (content_channels.save_check),
кроме сбоя связи (нет ответа, 429, 5xx): saved=false, прежняя проверка остаётся.
send_test: sendMessage «Проверка связи с сайтом» в канал бара — сообщение видят
подписчики канала, его можно удалить.

### Чего нет

Правка вышедшего поста в канале (editMessageText) — вне объёма: исправление —
новый пост, старый удаляют руками.

## Changelog

- 2026-09-28 — модуль создан: отправка в Telegram-каналы баров, напоминание об
  Instagram, рассылка гостям через бота, «Отправить сейчас», проверка канала.
- 2026-09-28 — исправления по независимой проверке: safe_resend (без дублей при
  сбое связи), 409 на правки во время отправки и журнал потерянной попытки, время
  поста для «поздно» у Instagram и reminded_for, сбой проверки канала не
  сохраняется, остановка идущей рассылки, бюджет рассылок и продолжение, «Отправить
  сейчас» — только очередь, _ACTIVE_ATTEMPTS, длина в UTF-16, личный чат и
  совпадение чата напоминаний с каналом (docs/content-plan.md, Changelog).
"""

import copy
import json
import os
import secrets
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from core import content_channels as channels_mod
from core import content_media, msk_time
from core import content_plan as cp

GRACE_MINUTES = cp.DELIVERY_GRACE_MINUTES              # 120 — см. core/content_plan.py
SENDING_STALE_MINUTES = cp.SENDING_STALE_MINUTES       # 10 — см. core/content_plan.py
# Лимит Telegram — около 30 сообщений в секунду на бота; 25 — запас на ответы бота
# гостям (таплист, подписка), которые идут тем же ботом в это же время.
BOT_RATE_PER_SEC = 25
# Пачка рассылки: прогресс пишется после каждых 25 получателей (≈ 1 секунда при
# 25/с). Меньше — лишние записи плана (файл перезаписывается целиком), больше —
# больше получателей с неизвестным статусом, если процесс умрёт посреди пачки.
BOT_BATCH = 25
# Бюджет рассылок на один проход (проход — раз в минуту): 40 с. Посты каналов и
# напоминания идут первыми; рассылка, не уложившаяся в бюджет, сохраняет прогресс и
# продолжается в следующем проходе (без дублей — по sent_to). Так тысяча гостей с
# альбомом (≈ 7 минут отправки) не задерживает пост канала на 16:05 (проверка
# 2026-09-28). 40 из 60 с — запас на посты, запись плана и медленную сеть.
MAILING_BUDGET_SEC = 40
# 429: ждём retry_after один раз, если не дольше минуты; дольше (Telegram просит
# часы при флуде) — ошибка: держать поток отправщика часами нельзя. В рассылке 429
# не ждём вовсе: рассылка продолжается в следующем проходе.
RETRY_AFTER_MAX_SEC = 60
# Три обрыва связи подряд в рассылке — Telegram недоступен: дальше не ждём по
# ~45 с на каждого получателя (обход блокировок), остальные — в failed_to.
NETWORK_ABORT_AFTER = 3
# Предел файлов одного сообщения: 50 МБ — предел загрузки файла ботом (Bot API);
# больше одним запросом не шлём — память сервера и таймаут загрузки.
UPLOAD_TOTAL_MAX = 50 * 1024 * 1024
# Таймаут ответа на JSON-вызов: sendMessage и sendMediaGroup по file_id отвечают
# за секунды; 20 с — с запасом на медленный запасной путь.
CALL_TIMEOUT = 20
SITE = 'https://beerkultura.ru'
PUBLISHED_BY = cp.PUBLISHED_BY_BOT

GRACE_TEXT = 'Время выхода прошло, пока сервер не работал: проверьте и отправьте повторно'
STALE_TEXT = 'Статус отправки неизвестен: проверьте канал; если поста нет — «Повторить»'
NO_ANSWER_TEXT = ('Telegram не ответил (нет связи): пост мог не выйти — проверьте канал; '
                  'если поста нет — «Повторить»')
NOT_SENT_TEXT = 'Telegram недоступен (нет соединения): сообщение не отправлено — «Повторить» отправит его'
NO_TOKEN_TEXT = ('Бот не настроен: на сервере нет токена TELEGRAM_CONTENT_BOT_TOKEN или '
                 'TELEGRAM_BOT_TOKEN')
GUEST_NO_TOKEN_TEXT = ('Гостевой бот не настроен: на сервере нет TELEGRAM_BOT_TOKEN — рассылки гостям '
                       'идут только через @kult_taplist_bot')
DISABLED_TEXT = 'Отправка публикаций выключена: включите её в «Каналы и отправка»'
SCHEDULER_OFF_TEXT = ('Отправка отключена на сервере (CONTENT_PUBLISH=0): «Отправить сейчас» не сработает — '
                      'отметьте выход вручную')
EMPTY_AUDIENCE_TEXT = 'В аудитории нет ни одного подписчика — рассылка не отправлена'
PUBLISH_NOW_TEXT = 'Уйдёт в течение минуты'

# Частые описания ошибок Telegram -> понятный текст (исходное — в скобках).
KNOWN_ERRORS = (
    ('chat not found', 'канал или чат не найден: проверьте адрес'),
    ('not enough rights', 'у бота нет права публиковать'),
    ('need administrator rights', 'бот не администратор канала'),
    ('have no rights to send', 'у бота нет права публиковать'),
    ('bot is not a member', 'бот не состоит в канале'),
    ('bot was kicked', 'бота удалили из канала'),
    ('bot was blocked by the user', 'гость заблокировал бота'),
    ('user is deactivated', 'аккаунт получателя удалён'),
    ('message is too long', 'текст длиннее, чем принимает Telegram'),
    ('caption is too long', 'подпись длиннее, чем принимает Telegram'),
    ('wrong file', 'Telegram не принял файл'),
    ('unauthorized', 'Telegram не принял токен бота'),
)

# Попытки, которые сейчас выполняет ЭТОТ процесс: проход отправщика не считает свою
# же отправку «зависшей» (отправляет только поток планировщика, он один на сервер).
_ACTIVE_ATTEMPTS = set()
_ACTIVE_GUARD = threading.Lock()


# ---------------------------------------------------------------------------
# Транспорт
# ---------------------------------------------------------------------------

class TelegramTransport:
    """Настоящий Telegram через core/open_check_telegram (обход блокировок ТСПУ).

    call(method, payload) -> JSON Telegram или None; upload(method, fields, files)
    — то же с файлами (files: [(поле, имя, байты, mime)]). Тесты передают свою
    подделку с теми же двумя методами — в настоящий Telegram ничего не уходит.

    Отправка (send*) идёт с safe_resend=True: после ReadTimeout и других сбоев, при
    которых запрос мог дойти, транспорт НЕ шлёт его запасным путём (проверка
    2026-09-28: 2–4 копии поста в канале). last_outcome после None: 'not_sent' —
    запрос точно не ушёл (повтор безопасен), 'unknown' — мог уйти. Чтение (getMe,
    getChat, getChatMember) повторять безопасно — без ключа, как раньше."""

    def __init__(self, token: str):
        if not token:
            raise ValueError('Нет токена бота')
        self.token = token
        self.last_outcome = None

    def call(self, method: str, payload: Optional[dict] = None):
        from core.open_check_telegram import api_call
        outcome: List[str] = []
        result = api_call(method, payload or {}, timeout=CALL_TIMEOUT, token=self.token,
                          safe_resend=method.startswith('send'), outcome=outcome)
        self.last_outcome = outcome[0] if result is None and outcome else None
        return result

    def upload(self, method: str, fields: dict, files: list):
        from core.open_check_telegram import api_call_files
        outcome: List[str] = []
        result = api_call_files(method, fields, files, token=self.token, safe_resend=True, outcome=outcome)
        self.last_outcome = outcome[0] if result is None and outcome else None
        return result


def default_transport() -> Optional[TelegramTransport]:
    """Бот каналов (посты, проверка, тест, напоминание об Instagram) или None."""
    token, _source = channels_mod.channel_bot_token()
    return TelegramTransport(token) if token else None


def default_guest_transport() -> Optional[TelegramTransport]:
    """Гостевой бот @kult_taplist_bot (рассылки гостям) или None. Только
    TELEGRAM_BOT_TOKEN: бот контента писать гостям не может (см. content_channels)."""
    token, _source = channels_mod.guest_bot_token()
    return TelegramTransport(token) if token else None


def human_error(code, description: str) -> str:
    """Ошибка Telegram понятным текстом (исходное описание — в скобках)."""
    desc = str(description or '').strip() or 'нет описания'
    shown = code if isinstance(code, int) else '?'
    if isinstance(code, int) and code >= 500:
        return f'Telegram временно не отвечает (ошибка {shown}): {desc}'
    low = desc.lower()
    for needle, text in KNOWN_ERRORS:
        if needle in low:
            return f'{text} (Telegram: {desc})'
    return f'Telegram отклонил запрос (ошибка {shown}): {desc}'


def classify(resp, transport=None) -> Tuple[str, object, str]:
    """Ответ Telegram -> (вид, result, текст ошибки): вид 'ok' | 'forbidden' (403) |
    'error' | 'network' (ответа нет — запрос мог дойти) | 'not_sent' (ответа нет, но
    транспорт знает, что запрос не ушёл: last_outcome 'not_sent')."""
    if not isinstance(resp, dict):
        if getattr(transport, 'last_outcome', None) == 'not_sent':
            return 'not_sent', None, NOT_SENT_TEXT
        return 'network', None, NO_ANSWER_TEXT
    if resp.get('ok'):
        return 'ok', resp.get('result'), ''
    code = resp.get('error_code')
    if code == 403:
        return 'forbidden', None, human_error(code, resp.get('description'))
    return 'error', None, human_error(code, resp.get('description'))


def _retry_after(resp: dict) -> Optional[int]:
    params = resp.get('parameters') if isinstance(resp.get('parameters'), dict) else {}
    value = params.get('retry_after')
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


class RateLimiter:
    """Не чаще per_sec «сообщений» в секунду: перед отправкой ждёт, пока пройдёт
    интервал после предыдущей (units — сколько сообщений займёт отправка)."""

    def __init__(self, per_sec: float, clock: Callable[[], float], sleep: Callable[[float], None]):
        self.interval = 1.0 / per_sec
        self.clock = clock
        self.sleep = sleep
        self._next: Optional[float] = None

    def wait(self, units: int = 1) -> None:
        now = self.clock()
        if self._next is not None and now < self._next:
            self.sleep(self._next - now)
            now = self._next
        self._next = now + self.interval * max(1, units)


# ---------------------------------------------------------------------------
# Проход отправщика
# ---------------------------------------------------------------------------

def _new_report() -> dict:
    return {'sent': 0, 'failed': 0, 'skipped': 0, 'details': []}


def _detail(report: dict, material: dict, placement: dict, result: str, text: str = '') -> None:
    """Строка отчёта. result: sent | reminded | failed | stale | skipped | queued."""
    if result in ('sent', 'reminded'):
        report['sent'] += 1
    elif result in ('failed', 'stale'):
        report['failed'] += 1
    elif result == 'skipped':
        report['skipped'] += 1
    report['details'].append({'placement_id': placement.get('id'), 'material_id': material.get('id'),
                              'title': material.get('title'), 'channel': placement.get('channel'),
                              'bar': placement.get('bar'), 'result': result, 'text': text})


class _Run:
    """Контекст одного прохода: хранилища, настройки, транспорты, кэш file_id, темп,
    бюджет времени рассылок.

    transport — бот каналов (посты, напоминание об Instagram); guest_transport —
    гостевой бот (рассылки). file_id у каждого бота свой (file_id одного бота другой
    не примет), поэтому кэш — отдельно по транспорту."""

    def __init__(self, store, channels, settings: dict, transport, now: datetime,
                 sleep: Optional[Callable] = None, clock: Optional[Callable] = None, guest_transport=None):
        self.store = store
        self.channels = channels
        self.settings = settings
        self.transport = transport
        self.guest_transport = guest_transport
        self.now = now
        self.now_str = cp.fmt_stamp(now)
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self.rate = RateLimiter(BOT_RATE_PER_SEC, self.clock, self.sleep)
        self.mailing_deadline: Optional[float] = None
        self._file_ids: Dict[int, Dict[str, str]] = {}

    def file_ids(self, transport) -> Dict[str, str]:
        """Кэш file_id этого бота на проход: {имя файла: file_id}."""
        return self._file_ids.setdefault(id(transport), {})

    def mailing_time_left(self) -> bool:
        """Остался ли бюджет рассылок этого прохода (MAILING_BUDGET_SEC)."""
        if self.mailing_deadline is None:
            self.mailing_deadline = self.clock() + MAILING_BUDGET_SEC
        return self.clock() < self.mailing_deadline

    def request(self, method: str, payload: Optional[dict] = None, fields: Optional[dict] = None,
                files: Optional[list] = None, transport=None, on_rate: str = 'wait') -> Tuple[str, object, str]:
        """Вызов Telegram с разбором ответа. transport — какой бот (по умолчанию бот
        каналов). 429: on_rate='wait' — один повтор через retry_after (не дольше 60 с);
        on_rate='return' (рассылка) — сразу ('rate', retry_after, текст): рассылка
        продолжится в следующем проходе, а не ждёт, держа посты каналов."""
        bot = transport or self.transport
        for attempt in (1, 2):
            if files:
                resp = bot.upload(method, fields or {}, files)
            else:
                resp = bot.call(method, payload or {})
            if isinstance(resp, dict) and resp.get('error_code') == 429:
                wait = _retry_after(resp)
                if on_rate == 'return':
                    return 'rate', wait, f'Telegram просит подождать {wait} с'
                if attempt == 1:
                    if wait is not None and wait <= RETRY_AFTER_MAX_SEC:
                        self.sleep(wait)
                        continue
                    return 'error', None, (f'Telegram просит подождать {wait} с — слишком долго; '
                                           'отправьте повторно позже')
            return classify(resp, bot)
        return 'error', None, 'Telegram ограничил частоту отправки'   # сюда не доходит


def _read(item: dict) -> bytes:
    with open(item['path'], 'rb') as f:
        return f.read()


def _file_id(message, kind: str) -> Optional[str]:
    """file_id загруженного файла из ответа Telegram (фото — самый крупный размер)."""
    if not isinstance(message, dict):
        return None
    if kind == 'image':
        photos = message.get('photo') or []
        return photos[-1].get('file_id') if photos and isinstance(photos[-1], dict) else None
    video = message.get('video')
    return video.get('file_id') if isinstance(video, dict) else None


def _message_ids(result) -> List[int]:
    if isinstance(result, list):
        return [m.get('message_id') for m in result if isinstance(m, dict) and m.get('message_id') is not None]
    if isinstance(result, dict) and result.get('message_id') is not None:
        return [result['message_id']]
    return []


def send_post(run: _Run, chat_id, text: str, media: List[dict], caption: bool = True,
              transport=None, on_rate: str = 'wait',
              entities: Optional[List[dict]] = None) -> Tuple[str, List[int], str]:
    """Одно сообщение в чат: текст (sendMessage), 1 файл (sendPhoto / sendVideo) или
    2..10 (sendMediaGroup, подпись у первого). caption=False — файлы без подписи.
    transport — какой бот (по умолчанию бот каналов; рассылка — гостевой).
    entities — ссылки в тексте (таплист: названия -> Untappd), offset и length в
    единицах UTF-16; у текста — entities, у подписи — caption_entities. Текст со
    ссылками уходит без предпросмотра ссылки: иначе под постом встала бы карточка
    первого пива. Без entities — как раньше: без parse_mode, предпросмотр включён.
    -> (вид, message_ids, текст ошибки); у вида 'rate' второй элемент — retry_after."""
    bot = transport or run.transport
    known = run.file_ids(bot)

    def req(method, **kw):
        return run.request(method, transport=bot, on_rate=on_rate, **kw)

    def done(kind, result, error):
        if kind == 'rate':
            return kind, result, error
        return kind, _message_ids(result) if kind == 'ok' else [], error

    entities = list(entities or [])
    if not media:
        payload = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': bool(entities)}
        if entities:
            payload['entities'] = entities
        return done(*req('sendMessage', payload=payload))
    caption_text = text if caption and text and text.strip() else ''
    caption_entities = entities if caption_text else []
    if len(media) == 1:
        item = media[0]
        method, field = ('sendVideo', 'video') if item['kind'] == 'video' else ('sendPhoto', 'photo')
        cached = known.get(item['name'])
        if cached:
            payload = {'chat_id': chat_id, field: cached}
            if caption_text:
                payload['caption'] = caption_text
            if caption_entities:
                payload['caption_entities'] = caption_entities
            kind, result, error = req(method, payload=payload)
        else:
            fields = {'chat_id': str(chat_id)}
            if caption_text:
                fields['caption'] = caption_text
            if caption_entities:
                fields['caption_entities'] = json.dumps(caption_entities, ensure_ascii=False)
            kind, result, error = req(method, fields=fields,
                                      files=[(field, item['filename'], _read(item), item['mime'])])
            if kind == 'ok':
                file_id = _file_id(result, item['kind'])
                if file_id:
                    known[item['name']] = file_id
        return done(kind, result, error)
    entries, files = [], []
    for index, item in enumerate(media):
        cached = known.get(item['name'])
        if cached:
            ref = cached
        else:
            attach = f'file{index}'
            files.append((attach, item['filename'], _read(item), item['mime']))
            ref = 'attach://' + attach
        entry = {'type': 'video' if item['kind'] == 'video' else 'photo', 'media': ref}
        if index == 0 and caption_text:
            entry['caption'] = caption_text
            if caption_entities:
                entry['caption_entities'] = caption_entities
        entries.append(entry)
    if files:
        kind, result, error = req('sendMediaGroup', fields={
            'chat_id': str(chat_id), 'media': json.dumps(entries, ensure_ascii=False)}, files=files)
    else:
        kind, result, error = req('sendMediaGroup', payload={'chat_id': chat_id, 'media': entries})
    if kind == 'ok' and isinstance(result, list):
        for item, message in zip(media, result):
            file_id = _file_id(message, item['kind'])
            if file_id:
                known[item['name']] = file_id
    return done(kind, result, error)


def build_post(run: _Run, material: dict, placement: dict, pub_date: Optional[str]) -> dict:
    """Что отправить: {text, entities, media: [{name, kind, path, filename, mime, size}], problems}.

    Текст и файлы — из снимка утверждения; у live — шаблон, собранный сейчас
    (render_live), и entities — ссылки на Untappd в таплисте (у готовой
    публикации — пусто). problems — почему отправлять нельзя (стоп-правило,
    длина, файлы); непустой список — отправка не делается. Длина — как считает
    площадка (content_plan.text_units: Telegram и бот — единицы UTF-16, эмодзи — 2)."""
    snapshot = placement.get('approved_snapshot')
    if isinstance(snapshot, dict):
        text = '' if snapshot.get('text') is None else str(snapshot.get('text'))
        names: List[str] = []
        for name in snapshot.get('media') or []:
            if content_media.is_valid_name(name) and name not in names:
                names.append(name)
    else:
        text, names = cp.effective_text(material, placement), cp.effective_media(material, placement)
    channel = placement['channel']
    problems: List[str] = []
    entities: List[dict] = []
    if material.get('kind') == 'live':
        live = cp.render_live(material.get('live_source'), placement.get('bar'), text, pub_date=pub_date,
                              now=run.now, channel=channel, has_media=bool(names))
        # Стоп-правило: ok False — отправлять нельзя (файлы всё равно собираются:
        # напоминанию об Instagram они нужны, чтобы показать, что именно стоит).
        problems.extend(p['text'] for p in live['problems'])
        text, entities = live['text'], live.get('entities') or []
    else:
        limit = cp.text_limit_for(channel, bool(names))
        if cp.text_units(text, channel) > limit:
            problems.append(f'текст длиннее {limit} знаков')
    media_max = cp.CHANNELS[channel]['media_max']
    if len(names) > media_max:
        problems.append(f'больше {media_max} файлов')
    if not text.strip() and not names:
        problems.append('нечего отправлять: нет ни текста, ни файлов')
    known = {item['name']: item for item in material.get('media') or []}
    media, total = [], 0
    for name in names:
        original = (known.get(name) or {}).get('original_name') or name
        path = run.store.media.path(name)
        if not path or not os.path.isfile(path):
            problems.append(f'файл «{original}» не найден на диске')
            continue
        size = os.path.getsize(path)
        total += size
        # Имя в запросе — наше латинское имя файла (cp_…): кириллица в имени части
        # multipart кодируется по-разному, а подписчикам канала имя фото не видно.
        media.append({'name': name, 'kind': content_media.kind_of(name), 'path': path, 'filename': name,
                      'mime': content_media.mimetype_of(name), 'size': size})
    if total > UPLOAD_TOTAL_MAX:
        problems.append(f'файлы вместе больше {UPLOAD_TOTAL_MAX // (1024 * 1024)} МБ — уберите часть видео')
    return {'text': text, 'entities': entities, 'media': media, 'problems': problems}


def route_reason(settings: dict, placement: dict) -> Optional[str]:
    """Почему площадку размещения нельзя отправить (своя настройка) или None."""
    channel = placement.get('channel')
    if channel == 'telegram':
        return channels_mod.telegram_bar_reason((settings.get('telegram') or {}).get(placement.get('bar')))
    if channel == 'instagram':
        if not (settings.get('instagram') or {}).get('reminder_chat'):
            return 'не указан чат для напоминаний'
        conflict = channels_mod.reminder_conflict(settings)
        if conflict:
            return f'чат для напоминаний совпадает с каналом бара {channels_mod.bar_short(conflict)}'
        return None
    if channel == 'bot':
        return None if (settings.get('bot') or {}).get('enabled') else 'рассылки гостям выключены'
    return 'неизвестная площадка'


# ---------------------------------------------------------------------------
# Изменения плана (всё через delivery_update)
# ---------------------------------------------------------------------------

def _claim(run: _Run, placement_id: str, attempt: str):
    """Пометить размещение «отправляется». -> (материал, размещение) копиями или
    None — взять нельзя (уже отправляется, не утверждено, чужая очередь)."""
    holder: Dict[str, dict] = {}

    def fn(material, placement, now_str):
        delivery = cp.delivery_of(placement)
        if delivery.get('state') == 'sending':
            return None
        if placement['status'] == 'published':
            if placement.get('channel') != 'bot' or delivery.get('state') != 'queued':
                return None
        elif placement['status'] != 'approved':
            return None
        placement['delivery'] = dict(delivery, state='sending', attempt_id=attempt, started_at=now_str,
                                     heartbeat_at=now_str, error=None)
        holder['material'] = copy.deepcopy(material)
        holder['placement'] = copy.deepcopy(placement)
        return 'save'

    try:
        if not run.store.delivery_update(placement_id, fn):
            return None
    except cp.ContentPlanNotFound:          # удалили между чтением плана и отметкой
        return None
    with _ACTIVE_GUARD:
        _ACTIVE_ATTEMPTS.add(attempt)
    return holder['material'], holder['placement']


def _lost(run: _Run, material: dict, placement: dict, text: str) -> None:
    """Попытку потеряли (размещение изменили или удалили во время отправки): итог в
    размещение записать нельзя — пишем строку в журнал материала, чтобы было видно,
    что ушло (проверка 2026-09-28)."""
    print(f'[CONTENT-PUBLISH] {placement.get("id")}: {text}')
    try:
        run.store.log_event(material.get('id'), placement.get('id'), 'auto_failed', PUBLISHED_BY, text)
    except Exception as e:  # noqa: BLE001 — журнал не должен ронять проход
        print(f'[CONTENT-PUBLISH] журнал не записан: {e!r}')


def _finish(run: _Run, material: dict, placement: dict, attempt: str, apply: Callable, action: str,
            text: str, lost: Optional[str] = None):
    """Записать итог своей попытки (attempt_id совпадает). -> материал (API) или None.
    Попытка не найдена (размещение изменили или удалили) — строка в журнал (lost)."""
    def fn(_material, target, now_str):
        delivery = cp.delivery_of(target)
        if delivery.get('attempt_id') != attempt:
            return None
        apply(_material, target, delivery, now_str)
        return action, PUBLISHED_BY, text

    try:
        result = run.store.delivery_update(placement['id'], fn, view=True)
    except cp.ContentPlanNotFound:
        result = None
    if result is None:
        _lost(run, material, placement, lost or (f'{cp.placement_label(placement)}: итог отправки не записан — '
                                                 f'размещение изменили или удалили во время отправки ({text})'))
    return result


def _progress(run: _Run, placement_id: str, attempt: str, updates: dict) -> Optional[dict]:
    """Прогресс рассылки (без журнала) и отметка heartbeat_at. -> свежая delivery
    (в ней может быть stop_requested) или None — попытка больше не наша: стоп."""
    holder: Dict[str, dict] = {}

    def fn(_material, placement, now_str):
        delivery = cp.delivery_of(placement)
        if delivery.get('attempt_id') != attempt or delivery.get('state') != 'sending':
            return None
        placement['delivery'] = dict(delivery, heartbeat_at=now_str, **updates)
        holder['delivery'] = copy.deepcopy(placement['delivery'])
        return 'save'

    try:
        if not run.store.delivery_update(placement_id, fn):
            return None
    except cp.ContentPlanNotFound:
        return None
    return holder['delivery']


def _fail(run: _Run, material: dict, placement: dict, attempt: str, error: str, report: dict,
          result: str = 'failed') -> None:
    label = cp.placement_label(placement)

    def apply(_material, target, delivery, now_str):
        target['status'] = 'failed'
        target['failed_error'] = error
        target['delivery'] = dict(delivery, state='failed', finished_at=now_str, error=error, send_now=None)

    _finish(run, material, placement, attempt, apply, 'auto_failed', f'Ошибка отправки: {label}: {error}')
    _detail(report, material, placement, result, error)


# ---------------------------------------------------------------------------
# Площадки
# ---------------------------------------------------------------------------

def _send_telegram(run: _Run, material: dict, placement: dict, attempt: str, pub_date: Optional[str],
                   report: dict) -> None:
    cfg = (run.settings.get('telegram') or {}).get(placement.get('bar')) or {}
    chat = cfg.get('chat')
    check = cfg.get('check') or {}
    post = build_post(run, material, placement, pub_date)
    if post['problems']:
        _fail(run, material, placement, attempt, 'Публикация остановлена: ' + '; '.join(post['problems']), report)
        return
    kind, ids, error = send_post(run, chat, post['text'], post['media'], entities=post['entities'])
    if kind != 'ok':
        _fail(run, material, placement, attempt, error, report)
        return
    label = cp.placement_label(placement)

    def apply(_material, target, delivery, now_str):
        target['status'] = 'published'
        target['published_at'], target['published_by'] = now_str, PUBLISHED_BY
        target['failed_error'] = None
        target['delivery'] = dict(delivery, state='sent', finished_at=now_str, chat=chat, send_now=None,
                                  chat_username=check.get('chat_username'), message_ids=ids, error=None)

    _finish(run, material, placement, attempt, apply, 'auto_publish', f'Вышло автоматически: {label} ({chat})',
            lost=f'Пост вышел в канале {chat} (сообщение {ids[0] if ids else "?"}), но размещение изменили во '
                 f'время отправки — отметьте выход вручную: {label}')
    _detail(report, material, placement, 'sent', chat)


def _when_text(placement: dict) -> str:
    when = cp.fmt_date_ru(placement['date']) if placement.get('date') else 'без даты'
    return when + (' ' + placement['time'] if placement.get('time') else '')


def _send_reminder(run: _Run, material: dict, placement: dict, attempt: str, pub_date: Optional[str],
                   report: dict) -> None:
    chat = (run.settings.get('instagram') or {}).get('reminder_chat')
    post_at = cp.placement_datetime(placement)
    label = cp.placement_label(placement)
    conflict = channels_mod.reminder_conflict(run.settings)
    errors: List[str] = []
    ids: List[int] = []
    if conflict:
        # Чат напоминаний совпал с каналом бара (например, проверка вернула тот же id):
        # служебная заметка ушла бы подписчикам канала — не шлём вовсе.
        errors.append(f'чат для напоминаний совпадает с каналом бара {channels_mod.bar_short(conflict)}')
    post = build_post(run, material, placement, pub_date)
    if not errors:
        header = (f'Instagram: пора выложить — «{material.get("title")}», {_when_text(placement)}\n'
                  f'Карточка: {SITE}/content-plan?open={material["id"]}\n'
                  'Выложите пост вручную и отметьте «Вышло» в карточке.')
        kind, result, error = run.request('sendMessage', payload={'chat_id': chat, 'text': header,
                                                                  'disable_web_page_preview': True})
        if kind == 'ok':
            ids += _message_ids(result)
            if post['problems']:
                body = 'Текст не собран — публиковать нельзя: ' + '; '.join(post['problems'])
            else:
                body = post['text']
            if body.strip():
                kind, result, error = run.request('sendMessage', payload={'chat_id': chat, 'text': body,
                                                                          'disable_web_page_preview': True})
                if kind == 'ok':
                    ids += _message_ids(result)
                else:
                    errors.append(error)
            if post['media'] and not errors:
                kind, album_ids, error = send_post(run, chat, '', post['media'], caption=False)
                if kind == 'ok':
                    ids += album_ids
                else:
                    errors.append(error)
        else:
            errors.append(error)
    if errors:
        message = 'Напоминание не отправлено: ' + errors[0]

        def apply_failed(_material, target, delivery, now_str):
            target['delivery'] = dict(delivery, state='reminder_failed', finished_at=now_str, chat=chat,
                                      message_ids=ids, error=errors[0], reminded_for=post_at, send_now=None)

        _finish(run, material, placement, attempt, apply_failed, 'reminder', f'{message}: {label}')
        _detail(report, material, placement, 'failed', message)
        return

    def apply(_material, target, delivery, now_str):
        target['delivery'] = dict(delivery, state='reminded', finished_at=now_str, reminded_at=now_str, chat=chat,
                                  message_ids=ids, error=None, reminded_for=post_at, send_now=None,
                                  problems=post['problems'] or None)

    _finish(run, material, placement, attempt, apply, 'reminder', f'Напоминание об Instagram отправлено: {label}')
    _detail(report, material, placement, 'reminded', chat)


def _switch_marks(settings: dict) -> list:
    """Отметки выключателей: когда в последний раз включали отправку и рассылки.
    Включение ставит новую отметку, поэтому «выключили и включили снова» меняет их,
    даже если всё случилось в одну минуту."""
    return [settings.get('enabled_at'), (settings.get('bot') or {}).get('enabled_at')]


def _mailing_stop_reason(run: _Run, delivery: dict) -> Tuple[Optional[str], str, Optional[list]]:
    """Остановить ли рассылку перед следующей пачкой: (причина или None, статус,
    если не дошло никому, отметки выключателей). Настройки перечитываются каждый
    раз — выключатель действует на идущую рассылку (проверка 2026-09-28: выключили
    всё на 11-м из 200, а ушло ещё 189). Продолжение рассылки (continuation) хранит
    отметки на момент паузы между проходами (switch_marks): отметки другие —
    отправку между проходами выключали и включили снова, выключение — «стоп»."""
    stop = delivery.get('stop_requested')
    if isinstance(stop, dict) and stop.get('action') in cp.MAILING_STOP_WORDS:
        action = stop['action']
        return cp.MAILING_STOP_WORDS[action], ('paused' if action == 'pause' else 'cancelled'), None
    try:
        settings = run.channels.load()
    except channels_mod.ContentChannelsUnavailable:
        return 'настройки отправки не читаются', 'failed', None
    if not settings.get('enabled'):
        return 'отправка публикаций выключена', 'failed', None
    if not (settings.get('bot') or {}).get('enabled'):
        return 'рассылки гостям выключены', 'failed', None
    marks = _switch_marks(settings)
    stored = delivery.get('switch_marks')
    if delivery.get('continuation') and isinstance(stored, list) and stored != marks:
        return 'отправку выключали во время рассылки', 'failed', None
    return None, 'failed', marks


def _send_bot(run: _Run, material: dict, placement: dict, attempt: str, pub_date: Optional[str],
              report: dict) -> None:
    """Рассылка гостям (правила — в докстроке модуля, «Рассылка бота»)."""
    pid = placement['id']
    first_run = placement['status'] == 'approved'
    delivery = cp.delivery_of(placement)
    label = cp.placement_label(placement)
    continuation = bool(delivery.get('continuation'))
    post = build_post(run, material, placement, pub_date)
    if post['problems']:
        _bot_stop(run, material, placement, attempt, 'Рассылка остановлена: ' + '; '.join(post['problems']),
                  first_run, report)
        return
    segment = (placement.get('audience') or {}).get('segment')
    bar = None if placement.get('bar') in (None, cp.BAR_ALL) else placement.get('bar')
    try:
        current = channels_mod.recipients(segment, bar)
    except Exception as e:  # noqa: BLE001 — без списка получателей рассылки нет
        _bot_stop(run, material, placement, attempt, f'Не удалось прочитать подписчиков бота: {e}', first_run, report)
        return
    originals = {str(c): c for c in current}
    stored = delivery.get('recipients')
    if not isinstance(stored, list):
        stored = [str(c) for c in current]
    stored = [str(c) for c in stored]
    sent_to = [str(c) for c in delivery.get('sent_to') or []]
    blocked = [str(c) for c in delivery.get('blocked') or []]
    unknown = [str(c) for c in delivery.get('unknown_to') or []]
    # Продолжение той же рассылки (бюджет прохода, 429): прежние неудачи не повторяются
    # сами — только по «Повторить неудавшимся». Новый запуск и повтор — повторяются.
    failed: Dict[str, str] = {str(c): 'не дошло' for c in delivery.get('failed_to') or []} if continuation else {}
    done = set(sent_to) | set(blocked) | set(unknown) | set(failed)
    targets = [c for c in stored if c not in done and c in originals]
    unsubscribed = [c for c in stored if c not in done and c not in originals]
    if not stored:
        _bot_stop(run, material, placement, attempt, EMPTY_AUDIENCE_TEXT, first_run, report)
        return

    def stats() -> dict:
        return {'total': len(stored), 'sent': len(sent_to), 'failed': len(failed), 'blocked': len(blocked),
                'unsubscribed': len(unsubscribed), 'unknown': len(unknown)}

    def lost():
        _lost(run, material, placement, f'Рассылка остановлена: размещение изменили; дошло {len(sent_to)} '
                                        f'({label})')

    if _progress(run, pid, attempt, {'recipients': stored, 'pending': [], 'failed_to': list(failed),
                                     'stats': stats()}) is None:
        lost()
        return
    network_in_row = 0
    stop_reason, none_status, yield_reason, marks = None, 'failed', None, None
    index = 0
    while index < len(targets):
        batch = targets[index:index + BOT_BATCH]
        fresh = _progress(run, pid, attempt, {'pending': batch, 'stats': stats()})
        if fresh is None:
            lost()
            return
        stop_reason, none_status, marks = _mailing_stop_reason(run, fresh)
        if stop_reason:
            break
        if not run.mailing_time_left():
            yield_reason = 'budget'
            break
        attempted = 0
        for chat in batch:
            if network_in_row >= NETWORK_ABORT_AFTER:
                failed[chat] = 'не отправлено: нет связи с Telegram'
                attempted += 1
                continue
            if not run.mailing_time_left():
                yield_reason = 'budget'
                break
            run.rate.wait(max(1, len(post['media'])))
            try:
                kind, extra, error = send_post(run, originals.get(chat, chat), post['text'], post['media'],
                                               transport=run.guest_transport, on_rate='return',
                                               entities=post['entities'])
            except Exception as e:  # noqa: BLE001 — сбой на одном госте не останавливает рассылку
                # Сообщение могло уйти до сбоя: статус неизвестен, повтор ему не шлём.
                print(f'[CONTENT-PUBLISH] рассылка {pid}, чат {chat}: сбой {e!r}')
                unknown.append(chat)
                attempted += 1
                continue
            if kind == 'rate':
                yield_reason = 'rate'       # этому гостю не ушло (429) — возьмём в следующем проходе
                break
            attempted += 1
            if kind == 'ok':
                sent_to.append(chat)
                network_in_row = 0
            elif kind == 'forbidden':
                blocked.append(chat)
                channels_mod.mark_blocked(originals.get(chat, chat))
                network_in_row = 0
            elif kind == 'network':
                # Ответа нет, запрос мог дойти: статус неизвестен, повтор не шлём.
                unknown.append(chat)
                network_in_row += 1
            elif kind == 'not_sent':
                failed[chat] = error        # точно не ушло: «Повторить неудавшимся» безопасен
                network_in_row += 1
            else:
                failed[chat] = error
                network_in_row = 0
        index += attempted
        if _progress(run, pid, attempt, {'pending': [], 'sent_to': sent_to, 'blocked': blocked,
                                         'failed_to': list(failed), 'unknown_to': unknown,
                                         'stats': stats()}) is None:
            lost()
            return
        if yield_reason:
            break

    if stop_reason:
        def apply_stop(_material, target, current, now_str):
            target['delivery'] = dict(current, sent_to=sent_to, blocked=blocked, unknown_to=unknown,
                                      failed_to=list(failed), pending=[])
            cp.stop_mailing(target, stop_reason, now_str, none_status)

        _finish(run, material, placement, attempt, apply_stop, 'auto_failed',
                f'Рассылка остановлена ({stop_reason}): дошло {len(sent_to)} из {len(stored)}: {label}')
        _detail(report, material, placement, 'failed' if not sent_to else 'sent',
                f'остановлена ({stop_reason}): дошло {len(sent_to)} из {len(stored)}')
        return

    if yield_reason:
        # Не уложились в бюджет прохода или Telegram просит подождать: прогресс сохранён,
        # рассылка встаёт в очередь и продолжится в следующем проходе (не раньше минуты).
        def apply_yield(_material, target, current, now_str):
            target['delivery'] = dict(current, state='queued', retry_at=now_str, queued_at=now_str,
                                      continuation=True, switch_marks=marks, pending=[], stats=stats())

        _finish(run, material, placement, attempt, apply_yield, 'delivery_progress',
                f'Рассылка продолжится в следующем проходе: дошло {len(sent_to)} из {len(stored)}: {label}')
        _detail(report, material, placement, 'queued',
                f'продолжится в следующем проходе ({"бюджет прохода" if yield_reason == "budget" else "429"}): '
                f'дошло {len(sent_to)} из {len(stored)}')
        return

    final = stats()
    first_error = next((text for text in failed.values() if text != 'не дошло'), None) or \
        next(iter(failed.values()), None)
    notes = []
    if failed:
        notes.append(f'Не дошло {len(failed)}: {first_error}')
    if unknown:
        notes.append(f'у {len(unknown)} статус неизвестен — повтор им не шлётся')
    error = '; '.join(notes) or None
    if not sent_to and first_run:
        message = 'Рассылка не дошла ни одному подписчику' + (f': {first_error}' if first_error else '')

        def apply_failed(_material, target, current, now_str):
            target['status'] = 'failed'
            target['failed_error'] = message
            target['delivery'] = dict(current, state='failed', finished_at=now_str, stats=final, error=message,
                                      pending=[], continuation=None, send_now=None, stop_requested=None)

        _finish(run, material, placement, attempt, apply_failed, 'auto_failed', f'Ошибка отправки: {label}: {message}')
        _detail(report, material, placement, 'failed', message)
        return

    def apply(_material, target, current, now_str):
        target['status'] = 'published'
        if not target.get('published_at'):
            target['published_at'], target['published_by'] = now_str, PUBLISHED_BY
        target['failed_error'] = None
        target['delivery'] = dict(current, state='partial' if failed else 'sent', finished_at=now_str,
                                  stats=final, error=error, pending=[], continuation=None, send_now=None,
                                  stop_requested=None)

    text = f'Рассылка: дошло {final["sent"]} из {final["total"]}: {label}'
    _finish(run, material, placement, attempt, apply, 'auto_publish', text)
    _detail(report, material, placement, 'sent', f'дошло {final["sent"]} из {final["total"]}')


def _bot_stop(run: _Run, material: dict, placement: dict, attempt: str, message: str, first_run: bool,
              report: dict) -> None:
    """Рассылка не началась (стоп-правило, нет подписчиков, сбой чтения): первый
    запуск — failed; повтор неудавшимся — статус остаётся published, ошибка — в delivery."""
    if first_run:
        _fail(run, material, placement, attempt, message, report)
        return
    label = cp.placement_label(placement)

    def apply(_material, target, delivery, now_str):
        target['delivery'] = dict(delivery, state='partial', finished_at=now_str, error=message,
                                  continuation=None, send_now=None)

    _finish(run, material, placement, attempt, apply, 'auto_failed', f'Повтор рассылки не выполнен: {label}: {message}')
    _detail(report, material, placement, 'failed', message)


SENDERS = {'telegram': _send_telegram, 'instagram': _send_reminder, 'bot': _send_bot}


def _send(run: _Run, material: dict, placement: dict, attempt: str, pub_date: Optional[str], report: dict) -> None:
    """Отправить уже помеченное «отправляется» размещение. Неожиданный сбой —
    итог «статус неизвестен» (пост мог уйти — повтор без проверки дал бы дубль)."""
    try:
        SENDERS[placement['channel']](run, material, placement, attempt, pub_date, report)
    except Exception as e:  # noqa: BLE001 — сбой одного размещения не останавливает проход
        print(f'[CONTENT-PUBLISH] {placement.get("id")}: сбой отправки {e!r}')
        label = cp.placement_label(placement)

        def apply(_material, target, delivery, now_str):
            _interrupt_delivery(target, delivery, now_str, label)

        _finish(run, material, placement, attempt, apply, 'auto_failed', f'Сбой отправки (статус неизвестен): {label}')
        _detail(report, material, placement, 'failed', STALE_TEXT)
    finally:
        with _ACTIVE_GUARD:
            _ACTIVE_ATTEMPTS.discard(attempt)


# ---------------------------------------------------------------------------
# Зависшие и опоздавшие
# ---------------------------------------------------------------------------

def _interrupt_delivery(target: dict, delivery: dict, now_str: str, label: str) -> tuple:
    """Отправка прервалась (процесс умер или сбой): итог без повторной отправки.

    Instagram — reminder_failed «статус неизвестен». Рассылка бота: получатели
    последней пачки (pending) — unknown_to (им повтор не шлёт: могли получить);
    те, до кого очередь не дошла, — в failed_to (повтор безопасен); кому-то
    дошло — published «дошло N из M», никому — failed. Прочее — failed
    STALE_TEXT. Меняет target на месте. -> (action, by, text) для журнала."""
    channel = target.get('channel')
    if channel == 'instagram':
        target['delivery'] = dict(delivery, state='reminder_failed', finished_at=now_str, send_now=None,
                                  reminded_for=cp.placement_datetime(target),
                                  error='статус напоминания неизвестен: проверьте чат')
        return 'reminder', PUBLISHED_BY, f'Напоминание об Instagram: статус неизвестен (отправка прервалась): {label}'
    if channel == 'bot' and isinstance(delivery.get('recipients'), list):
        recipients = [str(c) for c in delivery['recipients']]
        sent = [str(c) for c in delivery.get('sent_to') or []]
        blocked = [str(c) for c in delivery.get('blocked') or []]
        unknown = [str(c) for c in delivery.get('unknown_to') or []]
        unknown += [str(c) for c in delivery.get('pending') or [] if str(c) not in unknown and str(c) not in sent]
        failed = [str(c) for c in delivery.get('failed_to') or []]
        accounted = set(sent) | set(blocked) | set(unknown) | set(failed)
        failed += [c for c in recipients if c not in accounted]
        stats = dict(delivery.get('stats') or {}, total=len(recipients), sent=len(sent), failed=len(failed),
                     blocked=len(blocked), unknown=len(unknown))
        message = f'Рассылка прервалась: дошло {len(sent)} из {len(recipients)}; у {len(unknown)} статус неизвестен'
        fields = dict(finished_at=now_str, unknown_to=unknown, failed_to=failed, pending=[], stats=stats,
                      error=message, continuation=None, send_now=None, stop_requested=None)
        if sent or target['status'] == 'published':
            target['status'] = 'published'
            if not target.get('published_at'):
                target['published_at'], target['published_by'] = now_str, PUBLISHED_BY
            target['delivery'] = dict(delivery, state='partial', **fields)
            return 'auto_failed', PUBLISHED_BY, f'{message}: {label}'
        target['status'] = 'failed'
        target['failed_error'] = message
        target['delivery'] = dict(delivery, state='failed', **fields)
        return 'auto_failed', PUBLISHED_BY, f'Ошибка отправки: {label}: {message}'
    if target['status'] == 'approved':
        target['status'] = 'failed'
        target['failed_error'] = STALE_TEXT
    target['delivery'] = dict(delivery, state='failed', finished_at=now_str, error=STALE_TEXT, send_now=None)
    return 'auto_failed', PUBLISHED_BY, f'Ошибка отправки: {label}: {STALE_TEXT}'


def _resolve_stale(run: _Run, material: dict, placement: dict, report: dict) -> None:
    """«Отправляется» дольше SENDING_STALE_MINUTES: не отправлять повторно (пост мог
    уйти), а поставить ошибку «статус неизвестен» (`_interrupt_delivery`). Своя
    попытка этого процесса зависшей не считается (_ACTIVE_ATTEMPTS)."""
    label = cp.placement_label(placement)

    def fn(_material, target, now_str):
        delivery = cp.delivery_of(target)
        if delivery.get('state') != 'sending' or cp.in_flight(target, now_str):
            return None
        with _ACTIVE_GUARD:
            if delivery.get('attempt_id') in _ACTIVE_ATTEMPTS:
                return None
        return _interrupt_delivery(target, delivery, now_str, label)

    try:
        changed = run.store.delivery_update(placement['id'], fn)
    except cp.ContentPlanNotFound:
        return
    if changed:
        _detail(report, material, placement, 'stale', STALE_TEXT)


def _mark_late(run: _Run, material: dict, placement: dict, report: dict) -> None:
    """Опоздание больше GRACE_MINUTES (от времени поста или повтора): Telegram и бот —
    ошибка «время выхода прошло» (решение владельцу), у рассылки, которая уже
    кому-то дошла, — остановка «дошло N из M»; Instagram — напоминание не шлётся
    (reminder_late для этого времени поста)."""
    label = cp.placement_label(placement)
    channel = placement.get('channel')
    outcome: Dict[str, str] = {}

    def fn(_material, target, now_str):
        delivery = cp.delivery_of(target)
        if delivery.get('state') == 'sending':
            return None
        if channel == 'instagram':
            if target['status'] != 'approved' or cp.reminder_is_current(target):
                return None
            target['delivery'] = dict(delivery, state='reminder_late', finished_at=now_str, send_now=None,
                                      reminded_for=cp.placement_datetime(target),
                                      error='время прошло, пока сервер не работал')
            outcome['result'] = 'skipped'
            return 'reminder', PUBLISHED_BY, f'Напоминание об Instagram не отправлено: время прошло: {label}'
        if channel == 'bot' and (delivery.get('sent_to') or target['status'] == 'published'):
            if target['status'] not in ('approved', 'published'):
                return None
            stats = cp.stop_mailing(target, 'время прошло, пока отправка не работала', now_str)
            outcome['result'] = 'failed'
            return 'auto_failed', PUBLISHED_BY, (f'Рассылка не завершена — время прошло, пока отправка не '
                                                 f'работала: дошло {stats["sent"]} из {stats["total"]}: {label}')
        if target['status'] != 'approved':
            return None
        target['status'] = 'failed'
        target['failed_error'] = GRACE_TEXT
        target['delivery'] = dict(delivery, state='failed', finished_at=now_str, error=GRACE_TEXT, send_now=None)
        outcome['result'] = 'failed'
        return 'auto_failed', PUBLISHED_BY, f'Ошибка отправки: {label}: {GRACE_TEXT}'

    try:
        changed = run.store.delivery_update(placement['id'], fn)
    except cp.ContentPlanNotFound:
        return
    if changed:
        _detail(report, material, placement, outcome.get('result', 'failed'),
                'напоминание опоздало больше чем на 2 часа' if channel == 'instagram' else GRACE_TEXT)


# ---------------------------------------------------------------------------
# Главный вход
# ---------------------------------------------------------------------------

def _remind_at(settings: dict, post_at: str) -> str:
    """Когда напоминать об Instagram: время поста минус reminder_minutes_before."""
    minutes = int((settings.get('instagram') or {}).get('reminder_minutes_before') or 0)
    return cp.minus_minutes(post_at, minutes) if minutes else post_at


def _collect(run: _Run, data: dict) -> Tuple[List[tuple], List[dict]]:
    """-> (зависшие [(материал, размещение)], пора [{material, placement, effective,
    retry_at, post_at}]). effective — когда пора: время поста (у Instagram — время
    напоминания), не раньше retry_at; «Отправить сейчас» и продолжение рассылки —
    retry_at. Порядок: сначала посты каналов и напоминания, потом рассылки."""
    stale, due = [], []
    for material in data['materials'].values():
        for placement in material['placements']:
            status = placement.get('status')
            channel = placement.get('channel')
            delivery = cp.delivery_of(placement)
            state = delivery.get('state')
            if state == 'sending':
                if not cp.in_flight(placement, run.now_str):
                    stale.append((material, placement))
                continue
            if status == 'published':
                if channel != 'bot' or state != 'queued':
                    continue
            elif status != 'approved':
                continue
            if status == 'approved' and state in ('sent', 'partial'):
                continue        # уже ушло (защита от дубля при необычных данных)
            post_at = cp.placement_datetime(placement)
            if post_at is None:
                continue
            if channel == 'instagram' and cp.reminder_is_current(placement):
                continue        # напоминание для этого времени поста уже было
            retry_at = delivery.get('retry_at') if state == 'queued' else None
            if retry_at and (delivery.get('send_now') or delivery.get('continuation')):
                effective = retry_at
            else:
                start = _remind_at(run.settings, post_at) if channel == 'instagram' else post_at
                effective = max(start, retry_at or '')
            if effective > run.now_str:
                continue
            due.append({'material': material, 'placement': placement, 'effective': effective,
                        'retry_at': retry_at, 'post_at': post_at})
    order = {'telegram': 0, 'instagram': 1, 'bot': 2}
    due.sort(key=lambda item: (item['placement']['channel'] == 'bot', item['effective'],
                               order.get(item['placement']['channel'], 9), item['placement']['id']))
    return stale, due


def publish_due(now: Optional[datetime] = None, transport=None, store=None, channels=None,
                sleep: Optional[Callable] = None, clock: Optional[Callable] = None,
                guest_transport=None) -> dict:
    """Отправить всё, чему пора (правила — в докстроке модуля).

    now — момент выбора «пора» (по умолчанию — часы хранилища плана); отметки
    времени в плане — по часам хранилища. transport — бот каналов, guest_transport —
    гостевой бот (рассылки). Оба None — настоящие боты с токенами из окружения
    (планировщик); передан хоть один (тесты) — второй НЕ создаётся сам: без него его
    площадки пропускаются, в настоящий Telegram из теста ничего не уйдёт.
    sleep / clock — для темпа рассылки, 429 и бюджета прохода (тесты — без
    настоящих пауз). -> {sent, failed, skipped, details: [{placement_id,
    material_id, title, channel, bar, result, text}], enabled}."""
    store = store or cp.get_content_plan_store()
    channels = channels or channels_mod.get_channels_store()
    settings = channels.load()
    moment = now if isinstance(now, datetime) else store.now()
    if moment.tzinfo is not None:
        moment = moment.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
    moment = moment.replace(second=0, microsecond=0)
    report = _new_report()
    report['enabled'] = bool(settings.get('enabled'))
    run = _Run(store, channels, settings, transport, moment, sleep, clock, guest_transport)
    stale, due = _collect(run, store.snapshot_data())
    for material, placement in stale:
        _resolve_stale(run, material, placement, report)
    if not settings.get('enabled'):
        for item in due:
            _detail(report, item['material'], item['placement'], 'skipped', 'Отправка выключена владельцем')
        return report
    if run.transport is None and run.guest_transport is None:
        run.transport, run.guest_transport = default_transport(), default_guest_transport()
    if run.transport is None and run.guest_transport is None:
        for item in due:
            _detail(report, item['material'], item['placement'], 'skipped', NO_TOKEN_TEXT)
        return report
    cutoff = cp.minus_minutes(run.now_str, GRACE_MINUTES)
    for item in due:
        material, placement = item['material'], item['placement']
        retry_at, post_at = item['retry_at'], item['post_at']
        channel = placement.get('channel')
        reason = route_reason(settings, placement)
        if reason:
            _detail(report, material, placement, 'skipped', f'Площадка не подключена: {reason}')
            continue
        if (run.guest_transport if channel == 'bot' else run.transport) is None:
            _detail(report, material, placement, 'skipped',
                    GUEST_NO_TOKEN_TEXT if channel == 'bot' else NO_TOKEN_TEXT)
            continue
        # «Раньше подключения» и «опоздало» — от времени ПОСТА (у Instagram — не от
        # времени напоминания: иначе пост, утверждённый днём, оставался без напоминания).
        since = channels_mod.since_for(settings, channel, placement.get('bar'))
        if not retry_at and post_at < since:
            _detail(report, material, placement, 'skipped',
                    'Время выхода раньше подключения отправки — отметьте выход вручную')
            continue
        if max(post_at, retry_at or '') <= cutoff:
            _mark_late(run, material, placement, report)
            continue
        if channel == 'bot' and not run.mailing_time_left():
            _detail(report, material, placement, 'skipped', 'Рассылка начнётся в следующем проходе (бюджет прохода)')
            continue
        attempt = secrets.token_hex(6)
        claimed = _claim(run, placement['id'], attempt)
        if not claimed:
            _detail(report, material, placement, 'skipped', 'Уже отправляется или изменилось')
            continue
        fresh_material, fresh_placement = claimed
        send_now = bool(cp.delivery_of(placement).get('send_now'))
        pub_date = store.today() if send_now else fresh_placement.get('date')
        _send(run, fresh_material, fresh_placement, attempt, pub_date, report)
    return report


def publish_now(placement_id: str, user: Optional[dict], *, store=None, channels=None, transport=None,
                guest_transport=None) -> dict:
    """«Отправить сейчас»: утверждённое размещение встаёт в очередь отправки, его
    отправит планировщик в ближайший проход (в течение минуты).

    Раньше отправка шла прямо в веб-запросе (рассылка — потоком в веб-воркере):
    перезапуск воркера рвал её, два потока слали 50 сообщений в секунду, а долгая
    загрузка могла быть признана «зависшей» (проверка 2026-09-28). Теперь отправляет
    только планировщик — он один на сервер и сам себя зависшим не считает.

    transport / guest_transport — есть ли бот каналов и гостевой бот (маршрут
    передаёт настоящие; здесь они только проверяются, никуда не шлют).
    -> {placement, material, queued: True, message}. Ошибки: ContentPlanNotFound
    (404), ContentPlanConflict (409: не утверждено, уже отправляется, отправка
    выключена, бот не настроен, площадка не подключена, CONTENT_PUBLISH=0)."""
    store = store or cp.get_content_plan_store()
    channels = channels or channels_mod.get_channels_store()
    settings = channels.load()
    _material, placement = store.get_placement_raw(placement_id)
    now_str = store.now_str()
    status = placement['status']
    if status != 'approved':
        raise cp.ContentPlanConflict('Отправить сейчас можно только утверждённую публикацию '
                                     f'(сейчас: {cp.STATUS_NAMES.get(status, status)})')
    if cp.delivery_of(placement).get('state') == 'sending' and cp.in_flight(placement, now_str):
        raise cp.ContentPlanConflict(cp.SENDING_CONFLICT)
    if not settings.get('enabled'):
        raise cp.ContentPlanConflict(DISABLED_TEXT)
    from core import content_publisher_scheduler
    if content_publisher_scheduler.disabled():
        raise cp.ContentPlanConflict(SCHEDULER_OFF_TEXT)
    if placement['channel'] == 'bot' and guest_transport is None:
        raise cp.ContentPlanConflict(GUEST_NO_TOKEN_TEXT)
    if placement['channel'] != 'bot' and transport is None:
        raise cp.ContentPlanConflict(NO_TOKEN_TEXT)
    reason = route_reason(settings, placement)
    if reason:
        raise cp.ContentPlanConflict(f'Площадка не подключена: {reason}')
    by = cp.actor_label(user)

    def fn(_m, target, stamp):
        if target['status'] != 'approved':
            raise cp.ContentPlanConflict('Отправить сейчас можно только утверждённую публикацию '
                                         f'(сейчас: {cp.STATUS_NAMES.get(target["status"], target["status"])})')
        delivery = cp.delivery_of(target)
        if delivery.get('state') == 'sending' and cp.in_flight(target, stamp):
            raise cp.ContentPlanConflict(cp.SENDING_CONFLICT)
        target['delivery'] = dict(delivery, state='queued', retry_at=stamp, queued_at=stamp, send_now=True,
                                  error=None, continuation=None, stop_requested=None)
        return 'publish_now', by, f'Отправить сейчас: {cp.placement_label(target)} — уйдёт в течение минуты'

    material_view = store.delivery_update(placement_id, fn, view=True)
    placement_view = next((p for p in material_view['placements'] if p['id'] == placement_id), None)
    return {'placement': placement_view, 'material': material_view, 'queued': True, 'message': PUBLISH_NOW_TEXT}


# ---------------------------------------------------------------------------
# Проверка канала и тестовое сообщение
# ---------------------------------------------------------------------------

def _bar_chat(channels, bar: str) -> Tuple[dict, str]:
    if bar not in cp.BAR_KEYS:
        raise ValueError(f'Неизвестный бар «{bar}»')
    settings = channels.load()
    chat = ((settings.get('telegram') or {}).get(bar) or {}).get('chat') or ''
    if not chat:
        raise ValueError(f'Сначала укажите канал бара {channels_mod.bar_short(bar)}')
    return settings, chat


CHECK_NO_ANSWER_TEXT = 'Нет связи с Telegram — повторите проверку через минуту'
CHECK_TRANSIENT_TEXT = 'Telegram временно недоступен — прежняя проверка не изменилась, повторите через минуту'
TEST_NO_ANSWER_TEXT = ('Telegram не ответил (нет связи): тестовое сообщение могло прийти — '
                       'посмотрите в канал')
PRIVATE_CHAT_TEXT = 'Это личный чат, а не канал: укажите @канал бара или id канала (-100…)'


def check_channel(bar: str, user: Optional[dict], *, transport, channels=None) -> dict:
    """Проверить канал бара: getMe -> getChat -> getChatMember(бот).
    -> {check, saved, channels (настройки)}.

    Результат сохраняется у бара, КРОМЕ сбоя связи (нет ответа, 429, 5xx): тогда
    saved=false и прежняя проверка остаётся — случайный сбой не выключает рабочий
    канал (проверка 2026-09-28). Канал бара — только канал или группа: личный чат
    отклоняется (can_post=false)."""
    channels = channels or channels_mod.get_channels_store()
    _settings, chat = _bar_chat(channels, bar)
    if transport is None:
        return {'check': {'ok': False, 'can_post': False, 'error': NO_TOKEN_TEXT, 'chat': chat}, 'saved': False,
                'channels': channels.load()}

    def call(method, payload=None):
        resp = transport.call(method, payload or {})
        kind, result, error = classify(resp, transport)
        code = resp.get('error_code') if isinstance(resp, dict) else None
        transient = kind in ('network', 'not_sent') or code == 429 or (isinstance(code, int) and code >= 500)
        return kind, result, (CHECK_NO_ANSWER_TEXT if kind in ('network', 'not_sent') else error), transient

    def unsaved(error):
        return {'check': {'ok': False, 'can_post': False, 'error': error or CHECK_TRANSIENT_TEXT, 'chat': chat,
                          'transient': True},
                'saved': False, 'channels': channels.load()}

    check = {'ok': False, 'can_post': False, 'error': None, 'chat_title': None, 'chat_type': None,
             'chat_username': None, 'bot_username': None, 'chat_id': None}
    kind, me, error, transient = call('getMe')
    if transient:
        return unsaved(error)
    if kind != 'ok' or not isinstance(me, dict):
        check['error'] = error or 'Telegram не ответил на getMe'
        settings = channels.save_check(bar, chat, check, user)
        return {'check': dict(check, chat=chat), 'saved': True, 'channels': settings}
    check['bot_username'] = me.get('username')
    identity = {'username': me.get('username'), 'token_hash': channels_mod.token_hash(getattr(transport, 'token', None))}
    kind, info, error, transient = call('getChat', {'chat_id': chat})
    if transient:
        return unsaved(error)
    if kind != 'ok' or not isinstance(info, dict):
        check['error'] = (error or 'канал не найден') + ' — для закрытого канала укажите числовой id, бот должен быть в канале'
        settings = channels.save_check(bar, chat, check, user, identity=identity)
        return {'check': dict(check, chat=chat), 'saved': True, 'channels': settings}
    check.update({'ok': True, 'chat_title': info.get('title') or info.get('first_name'),
                  'chat_type': info.get('type'), 'chat_username': info.get('username'), 'chat_id': info.get('id')})
    if info.get('type') not in ('channel', 'supergroup', 'group'):
        check['can_post'] = False
        check['error'] = PRIVATE_CHAT_TEXT
    else:
        kind, member, error, transient = call('getChatMember', {'chat_id': chat, 'user_id': me.get('id')})
        if transient:
            return unsaved(error)
        status = member.get('status') if isinstance(member, dict) else None
        if info.get('type') == 'channel':
            can_post = status == 'creator' or (status == 'administrator' and bool(member.get('can_post_messages')))
        else:
            can_post = status in ('creator', 'administrator', 'member') or (
                status == 'restricted' and bool((member or {}).get('can_send_messages')))
        check['can_post'] = bool(can_post)
        if not can_post:
            if kind != 'ok':
                check['error'] = error or 'не удалось узнать права бота'
            elif status in ('left', 'kicked', None):
                check['error'] = 'Бот не состоит в канале: добавьте его администратором с правом «Публикация сообщений»'
            else:
                check['error'] = 'У бота нет права «Публикация сообщений»: дайте его в настройках администраторов канала'
    settings = channels.save_check(bar, chat, check, user, identity=identity)
    return {'check': dict(check, chat=chat), 'saved': True, 'channels': settings}


def send_test(bar: str, user: Optional[dict], *, transport, channels=None) -> dict:
    """Тестовое сообщение «Проверка связи с сайтом» в канал бара.
    -> {ok, message_id, error, chat}. Сообщение видят подписчики канала."""
    channels = channels or channels_mod.get_channels_store()
    _settings, chat = _bar_chat(channels, bar)
    if transport is None:
        return {'ok': False, 'message_id': None, 'error': NO_TOKEN_TEXT, 'chat': chat}
    kind, result, error = classify(transport.call('sendMessage', {
        'chat_id': chat, 'text': channels_mod.TEST_MESSAGE_TEXT, 'disable_web_page_preview': True}), transport)
    if kind == 'network':
        error = TEST_NO_ANSWER_TEXT
    ok = kind == 'ok'
    ids = _message_ids(result) if ok else []
    channels.note(f'Тестовое сообщение в канал {channels_mod.bar_short(bar)} ({chat}): '
                  + ('доставлено' if ok else error), user)
    return {'ok': ok, 'message_id': ids[0] if ids else None, 'error': None if ok else error, 'chat': chat}


# ---------------------------------------------------------------------------
# Скачать для Instagram (zip)
# ---------------------------------------------------------------------------

# До 16 МБ архив собирается в памяти, больше — во временном файле: у материала до
# 20 файлов по 10–50 МБ, держать сотни мегабайт в памяти воркера нельзя.
ZIP_SPOOL_BYTES = 16 * 1024 * 1024
_BAD_NAME_CHARS = set('<>:"/\\|?*')


def _safe_filename(name, fallback: str) -> str:
    """Имя файла в архиве: без пути, управляющих символов и запрещённых в Windows знаков."""
    base = os.path.basename(str(name or '').replace('\\', '/')).strip()
    base = ''.join(ch for ch in base if ch >= ' ' and ch not in _BAD_NAME_CHARS)
    return base[:120] or fallback


def build_material_zip(store, material: dict):
    """Архив для ручного размещения (Instagram): по текстовому файлу на каждое
    неотменённое размещение (только текст подписи — удобно скопировать), файлы
    материала в папке files (и файлы из снимков вышедших размещений) и опись
    opis.txt: какое размещение, когда, какой текст и какие файлы.

    Текст — как в карточке: у вышедших и ошибочных — снимок утверждения, иначе
    итоговый текст. У материала с актуальными данными таплист подставляется на
    момент скачивания (в публикации — на момент выхода); если данных нет — в
    файле шаблон, в описи — причина. -> файловый объект (позиция 0)."""
    now = store.now()
    known = {item['name']: item for item in material.get('media') or []}
    placements = [p for p in material.get('placements') or [] if p.get('status') != 'cancelled']
    placements.sort(key=lambda p: (p.get('date') or '9999', p.get('time') or '', p['id']))
    contents = [(p,) + tuple(cp.placement_content(material, p)) for p in placements]
    names: List[str] = [item['name'] for item in material.get('media') or []]
    for _p, _text, media, _source in contents:
        for name in media:
            if name not in names:
                names.append(name)
    manifest = [f'Материал: «{material.get("title")}»',
                f'Скачано: {cp.fmt_date_ru(now.date())} {now.strftime("%H:%M")} (МСК)',
                'Тексты — по файлу на размещение: в файле только текст подписи, его удобно скопировать.',
                'Фото и видео — в папке files.', '']
    archive = tempfile.SpooledTemporaryFile(max_size=ZIP_SPOOL_BYTES)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        arc_names: Dict[str, str] = {}
        missing: List[str] = []
        for index, name in enumerate(names, 1):
            original = (known.get(name) or {}).get('original_name') or name
            ext = content_media.ext_of(name) or 'bin'
            filename = _safe_filename(original, name)
            if '.' not in filename:
                filename += '.' + ext
            arc = f'files/{index:02d}_{filename}'
            path = store.media.path(name)
            if path and os.path.isfile(path):
                zf.write(path, arc, compress_type=zipfile.ZIP_STORED)   # фото и видео уже сжаты
                arc_names[name] = arc
            else:
                missing.append(f'Файл «{original}» не найден на диске — в архив не вошёл.')
        if missing:
            manifest.extend(missing + [''])
        for index, (placement, text, media, _source) in enumerate(contents, 1):
            note = ''
            if material.get('kind') == 'live':
                live = cp.render_live(material.get('live_source'), placement.get('bar'), text,
                                      pub_date=placement.get('date'), now=now, channel=placement.get('channel'),
                                      has_media=bool(media))
                if live['ok']:
                    text = live['text']
                    note = f'    таплист — на момент скачивания ({live["data_at"].replace("T", " ")}); в публикации — на момент выхода'
                else:
                    note = '    данные не собраны, в файле шаблон: ' + '; '.join(p['text'] for p in live['problems'])
            day = placement.get('date') or 'bez-daty'
            hhmm = (placement.get('time') or '').replace(':', '')
            arc = f'{index:02d}_{placement.get("channel")}_{placement.get("bar")}_{day}' + (f'_{hhmm}' if hhmm else '') + '.txt'
            zf.writestr(arc, text or '')
            status = cp.STATUS_NAMES.get(placement.get('status'), placement.get('status'))
            files = ', '.join(arc_names[n] for n in media if n in arc_names) or 'без файлов'
            manifest.append(f'{index:02d}. {cp.placement_label(placement)} — {status}')
            manifest.append(f'    текст: {arc}')
            manifest.append(f'    файлы: {files}')
            if note:
                manifest.append(note)
        if not contents:
            manifest.append('Размещений нет: в архиве только файлы материала.')
        zf.writestr('opis.txt', '\n'.join(manifest) + '\n')
    archive.seek(0)
    return archive

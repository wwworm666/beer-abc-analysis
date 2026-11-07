"""Сторож бота kultura.research (@MCPkulturabot) на сайте: бот замолчал или не может ответить — сообщение владельцу.

## Что это

Подготовка к выпуску в прод (решение владельца 2026-11-06, «подумай, что ещё нужно предусмотреть»):
раньше о том, что бот не работает, владелец узнавал, только когда бот не отвечал на вопрос или
открыв страницу «Доступ агентов». Теперь сайт раз в CHECK_EVERY_S смотрит отчёты сервера бота
(kultura_bot/store.get_status, их сервер присылает раз в минуту) и пишет владельцу в чат отчётов
агентов (страница «Доступ агентов», настройка notify_chat_id) — тем же ботом open-check, что и
common_notify_owner: если упал сам @MCPkulturabot, сообщение всё равно дойдёт.

## Когда пишет

| Беда | Когда | Текст |
|---|---|---|
| сервер бота молчит | отчёта нет дольше settings.WATCHDOG_SILENT_MINUTES | «не присылает отчёт с ЧЧ:ММ МСК» |
| Claude не отвечает | в отчёте ошибка Claude (ключ, оплата, доступ) | текст ошибки |
| бот в ошибке | состояние error или conflict держится дольше STATE_AFTER_S | что пишет сервер бота |

Одно сообщение на беду; если она держится, напоминание раз в settings.WATCHDOG_REMIND_HOURS часов;
кончилась — «снова отвечает». Бот на паузе, без токена или ключа, сервер бота не установлен —
молчит: это решение владельца, а не беда.

## Два воркера gunicorn

Поток сторожа есть в каждом воркере. Кто пишет — решает одна строка bot_watchdog в mcp.db:
UPDATE … WHERE (проверка «ещё не отправлено») меняет строку только у одного воркера, второй видит
rowcount 0 и молчит. Отправка не удалась — отметка снимается, попробует следующая проверка.
"""
import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

log = logging.getLogger(__name__)

CHECK_EVERY_S = 60
STATE_AFTER_S = 5 * 60              # error / conflict дольше — пишем (короткий сбой связи — не беда)
SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS bot_watchdog (
        id       INTEGER PRIMARY KEY CHECK (id = 1),
        kind     TEXT NOT NULL DEFAULT '',
        since_ts REAL NOT NULL DEFAULT 0,
        sent_ts  REAL NOT NULL DEFAULT 0,
        text     TEXT NOT NULL DEFAULT ''
    )''',
)
RECOVERED_TEXT = 'Бот kultura.research (@MCPkulturabot) снова отвечает.'

_started = False
_start_lock = threading.Lock()


def _ensure() -> None:
    from core.mcp import db
    db.ensure_schema('bot_watchdog', SCHEMA)
    with db.write() as conn:
        conn.execute('INSERT OR IGNORE INTO bot_watchdog (id) VALUES (1)')


def _hhmm(ts: float) -> str:
    from core import msk_time
    return datetime.fromtimestamp(ts, msk_time.MOSCOW_TZ).strftime('%d.%m %H:%M')


def problem(status: Dict[str, Any], *, configured: bool, now: float) -> Tuple[str, str]:
    """(вид беды, текст) или ('', '') — всё хорошо или сторожить нечего."""
    from kultura_bot import settings
    if not configured:
        return '', ''
    at_ts = float(status.get('at_ts') or 0)
    silent_s = max(1, int(settings.WATCHDOG_SILENT_MINUTES)) * 60
    if at_ts and now - at_ts > silent_s:
        return 'silent', (f'Бот kultura.research (@MCPkulturabot) не отвечает: сервер в Амстердаме не присылает отчёт с '
                          f'{_hhmm(at_ts)} МСК. Вопросы в Telegram сейчас остаются без ответа. Что проверить: '
                          f'включён ли сервер и служба kultura-bot (journalctl -u kultura-bot), страница '
                          f'{settings.ADMIN_PAGE_URL}, раздел «Бот».')
    claude_error = str(status.get('claude_error') or '').strip()
    if claude_error:
        return 'claude', f'Бот kultura.research (@MCPkulturabot) не может ответить: {claude_error}'
    state = status.get('state')
    if state in ('error', 'conflict'):
        detail = str(status.get('detail') or state)
        return 'state', f'Бот kultura.research (@MCPkulturabot): {detail}'
    return '', ''


def _configured() -> bool:
    """Сторожить есть что: токен, ключ, не пауза, сервер бота установлен (выпущен его ключ)."""
    from kultura_bot import credentials, site_api
    return bool(credentials.bot_token() and credentials.anthropic_key() and not credentials.paused()
                and site_api.engine_token_id())


def _send(text: str) -> bool:
    """Сообщение владельцу. Чат отчётов агентов не выбран — только журнал сайта и True: повторять раз в
    минуту некуда, а «отправлено» не даст сторожу засорять журнал той же строкой."""
    from core.mcp import settings as mcp_settings
    chat_id = str(mcp_settings.get('notify_chat_id') or '').strip()
    if not chat_id:
        log.warning('[BOT-WATCHDOG] некому писать: чат отчётов агентов не выбран на «Доступ агентов» — %s', text)
        return True
    from core.open_check_telegram import send_message
    return bool(send_message(chat_id, text))


def check_once(now: Optional[float] = None, *, status: Optional[Dict[str, Any]] = None,
               configured: Optional[bool] = None, send: Optional[Callable[[str], bool]] = None) -> str:
    """Одна проверка. Вернуть, что сделано: 'alert', 'remind', 'recovered' или '' (тесты подставляют
    время, состояние и отправку)."""
    from core.mcp import db
    from kultura_bot import settings, store
    if not settings.WATCHDOG:
        return ''
    now = time.time() if now is None else now
    status = store.get_status() if status is None else status
    configured = _configured() if configured is None else configured
    send = send or _send
    kind, text = problem(status, configured=configured, now=now)
    _ensure()
    with db.write() as conn:
        row = dict(conn.execute('SELECT * FROM bot_watchdog WHERE id = 1').fetchone())
        if kind != row['kind']:
            # Беда сменилась (или кончилась): новая — с этой секунды; кончилась после сообщения — «снова отвечает».
            recovered = not kind and row['kind'] and row['sent_ts'] > 0
            conn.execute('UPDATE bot_watchdog SET kind = ?, since_ts = ?, sent_ts = 0, text = ? WHERE id = 1',
                         (kind, now, text))
            row = {'kind': kind, 'since_ts': now, 'sent_ts': 0, 'text': text}
            if recovered:
                claimed = 'recovered'
            else:
                claimed = ''
        else:
            claimed = ''
        if kind and not claimed:
            due_after = STATE_AFTER_S if kind == 'state' else 0
            remind_s = max(1, int(settings.WATCHDOG_REMIND_HOURS)) * 3600
            if row['sent_ts'] == 0 and now - row['since_ts'] >= due_after:
                claimed = 'alert'
            elif row['sent_ts'] > 0 and now - row['sent_ts'] >= remind_s:
                claimed = 'remind'
            if claimed:
                previous = row['sent_ts']
                changed = conn.execute('UPDATE bot_watchdog SET sent_ts = ? WHERE id = 1 AND kind = ? AND sent_ts = ?',
                                       (now, kind, previous)).rowcount
                if not changed:
                    claimed = ''
    if not claimed:
        return ''
    message = RECOVERED_TEXT if claimed == 'recovered' else (
        text if claimed == 'alert' else f'Напоминание: {text}')
    try:
        ok = send(message)
    except Exception as exc:  # noqa: BLE001 — сторож не роняет сайт
        log.warning('[BOT-WATCHDOG] сообщение не ушло: %s', exc)
        ok = False
    if not ok and claimed != 'recovered':
        with db.write() as conn:                     # не ушло — попробует следующая проверка
            conn.execute('UPDATE bot_watchdog SET sent_ts = ? WHERE id = 1 AND kind = ? AND sent_ts = ?',
                         (0 if claimed == 'alert' else now - max(1, int(settings.WATCHDOG_REMIND_HOURS)) * 3600,
                          kind, now))
        return ''
    log.info('[BOT-WATCHDOG] %s: %s', claimed, message)
    return claimed if ok else ''


def _loop() -> None:
    time.sleep(CHECK_EVERY_S)                        # сайт только поднялся — дать серверу бота отчитаться
    while True:
        try:
            check_once()
        except Exception:  # noqa: BLE001
            log.exception('[BOT-WATCHDOG] проверка не прошла')
        time.sleep(CHECK_EVERY_S)


def start_watchdog() -> None:
    global _started
    from kultura_bot import settings
    with _start_lock:
        if _started or not settings.WATCHDOG:
            return
        _started = True
    threading.Thread(target=_loop, name='kultura-bot-watchdog', daemon=True).start()

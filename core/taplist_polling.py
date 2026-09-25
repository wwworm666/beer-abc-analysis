"""Long-polling команд @kult_taplist_bot.

Webhook после отзыва токена Telegram сбрасывает, а входящие соединения от
Telegram до сервера режет ТСПУ. Ответы через aiogram из Flask обрывались по
таймауту даже когда сообщение уже дошло. Поэтому бот сам забирает апдейты и
сам отвечает через тот же HTTP-клиент, что и бот открытия: запасной IP, если
api.telegram.org не открывается.

Один процесс на gunicorn --workers 2: flock на data/.taplist_polling.lock.
Пока webhook зарегистрирован, getUpdates отвечает 409 — webhook снимается
без drop_pending_updates.

Отключение: TAPLIST_POLLING=0.
"""
import json
import os
import threading
import time

import portalocker

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.taplist_polling.lock')
MAPPING_PATH = os.path.join(_BASE_DIR, 'data', 'beer_info_mapping.json')

POLL_TIMEOUT = 25
HTTP_TIMEOUT = POLL_TIMEOUT + 15

BAR_NAMES = {
    'bar1': 'Большой пр. В.О',
    'bar2': 'Лиговский',
    'bar3': 'Кременчугская',
    'bar4': 'Варшавская',
}

_COMMANDS = [
    {"command": "start", "description": "Кнопки баров"},
    {"command": "taplist", "description": "Выбрать бар"},
    {"command": "taplist1", "description": "Большой пр. В.О"},
    {"command": "taplist2", "description": "Лиговский"},
    {"command": "taplist3", "description": "Кременчугская"},
    {"command": "taplist4", "description": "Варшавская"},
    {"command": "taplistall", "description": "Все бары"},
    {"command": "help", "description": "Кнопки баров"},
]

_started = False
_thread_lock = threading.Lock()
_lock_handle = None


class WebhookConflict(Exception):
    """Telegram отклонил getUpdates, потому что на боте висит webhook."""


def _polling_disabled() -> bool:
    return os.environ.get('TAPLIST_POLLING', '1').lower() in ('0', 'false', 'off', 'no')


def command_name(text) -> str:
    if not text:
        return ''
    token = str(text).strip().split()[0]
    if not token.startswith('/'):
        return ''
    return token[1:].split('@', 1)[0].lower()


def bar_keyboard() -> dict:
    rows = [
        [{"text": name, "callback_data": "taplist_" + bar_id}]
        for bar_id, name in BAR_NAMES.items()
    ]
    rows.append([{"text": "Все бары", "callback_data": "taplist_all"}])
    return {"inline_keyboard": rows}


def plan_update(update) -> list:
    """Что ответить на один апдейт. Сеть и краны сюда не входят.

    Элементы: {"op": "ack", "callback_id"}, {"op": "menu", "chat_id"},
    {"op": "taplist", "chat_id", "bar_id"} (bar_id None — все бары).
    """
    callback = (update or {}).get('callback_query')
    if callback:
        actions = []
        if callback.get('id'):
            actions.append({"op": "ack", "callback_id": callback.get('id')})
        data = callback.get('data') or ''
        chat_id = ((callback.get('message') or {}).get('chat') or {}).get('id')
        if chat_id and data.startswith('taplist_'):
            bar_id = data.replace('taplist_', '', 1)
            actions.append({
                "op": "taplist",
                "chat_id": chat_id,
                "bar_id": None if bar_id == 'all' else bar_id,
            })
        return actions

    message = (update or {}).get('message') or {}
    chat_id = (message.get('chat') or {}).get('id')
    if not chat_id:
        return []
    cmd = command_name(message.get('text') or '')
    if cmd in ('start', 'help', 'taplist'):
        return [{"op": "menu", "chat_id": chat_id}]
    if cmd in ('taplist1', 'taplist2', 'taplist3', 'taplist4'):
        return [{"op": "taplist", "chat_id": chat_id, "bar_id": "bar" + cmd[-1]}]
    if cmd == 'taplistall':
        return [{"op": "taplist", "chat_id": chat_id, "bar_id": None}]
    if cmd:
        return [{"op": "menu", "chat_id": chat_id}]
    return []


def label_bars(data):
    """Подменить внутренние «Бар 1» на имена точек из меню бота."""
    for row in (data or {}).get('taplist') or []:
        name = BAR_NAMES.get(row.get('bar_id'))
        if name:
            row['bar'] = name
    return data


def consume_batch(data, offset, feed, on_error=None):
    """Разобрать один ответ getUpdates.

    offset двигается даже если feed упал: один битый апдейт не должен
    застрять в очереди навсегда. 409 — WebhookConflict, offset не меняется.
    Не-ok ответ (кроме 409) возвращает прежний offset.
    """
    if not data or not data.get('ok'):
        if data and data.get('error_code') == 409:
            raise WebhookConflict(data.get('description') or 'webhook is active')
        return offset
    for upd in data.get('result') or []:
        offset = int(upd['update_id']) + 1
        try:
            feed(upd)
        except Exception as exc:
            if on_error is None:
                raise
            on_error(exc)
    return offset


def _taps_path() -> str:
    if os.path.isdir('/kultura'):
        return '/kultura/taps_data.json'
    return os.path.join(_BASE_DIR, 'data', 'taps_data.json')


def _load_mapping() -> dict:
    if not os.path.exists(MAPPING_PATH):
        return {}
    with open(MAPPING_PATH, encoding='utf-8') as handle:
        return json.load(handle)


def _render_taplist(bar_id, manager, mapping) -> str:
    import telegram_webhook as tw
    data = label_bars(tw.get_taplist_data(bar_id, manager, mapping))
    text = tw.format_taplist_message(data, bar_id)
    if not text or 'Нет активных' in text or 'Нет данных' in text:
        title = BAR_NAMES.get(bar_id, 'Бар')
        return f"{title}: нет активных кранов"
    return text


def _execute(actions, token, manager, mapping) -> None:
    from core.open_check_telegram import api_call
    from core.taps_manager import TapsManager

    for action in actions:
        op = action.get('op')
        if op == 'ack':
            api_call('answerCallbackQuery', {'callback_query_id': action['callback_id']}, timeout=10, token=token)
            continue
        if op == 'menu':
            _send(token, action['chat_id'], 'Нажми бар:', bar_keyboard())
            continue
        if op != 'taplist':
            continue
        # Краны читаем с диска на каждый запрос: страница кранов пишет файл,
        # а этот процесс живёт сутками.
        manager = TapsManager(data_file=_taps_path())
        bar_id = action.get('bar_id')
        targets = list(BAR_NAMES) if bar_id is None else [bar_id]
        for bid in targets:
            _send(token, action['chat_id'], _render_taplist(bid, manager, mapping))


def _send(token, chat_id, text, markup=None) -> None:
    from core.open_check_telegram import api_call
    payload = {
        "chat_id": chat_id,
        "text": text or "Нет данных",
        "disable_web_page_preview": True,
    }
    if '<' in (text or ''):
        payload['parse_mode'] = 'HTML'
    if markup is not None:
        payload['reply_markup'] = markup
    data = api_call('sendMessage', payload, timeout=20, token=token)
    if not data or not data.get('ok'):
        print(f"[TAPLIST-POLL] send fail chat={chat_id} {(data or {}).get('error_code')} {(data or {}).get('description')}")


def _poll_loop() -> None:
    from core.open_check_telegram import _scrub, api_call

    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    mapping = _load_mapping()
    print(f"[TAPLIST-POLL] справочник пива: {len(mapping)}")
    api_call('deleteWebhook', {'drop_pending_updates': False}, token=token)
    api_call('setMyCommands', {'commands': _COMMANDS}, token=token)

    me = api_call('getMe', token=token)
    if me and me.get('ok'):
        print(f"[TAPLIST-POLL] polling стартовал, бот @{me['result'].get('username')}")
    else:
        desc = (me or {}).get('description') or 'нет ответа'
        print(f"[TAPLIST-POLL] getMe не подтвердил токен ({desc}) — polling продолжит пытаться")

    offset = None
    while True:
        try:
            payload = {
                'timeout': POLL_TIMEOUT,
                'allowed_updates': ['message', 'callback_query'],
            }
            if offset is not None:
                payload['offset'] = offset
            data = api_call('getUpdates', payload, timeout=HTTP_TIMEOUT, token=token)
            if data and data.get('error_code') == 401:
                print('[TAPLIST-POLL] Telegram отклонил токен. Проверьте TELEGRAM_BOT_TOKEN и перезапустите приложение.')
                time.sleep(60)
                continue
            try:
                def feed(upd, token=token, mapping=mapping):
                    _execute(plan_update(upd), token, None, mapping)

                def on_error(exc, token=token):
                    print(f"[TAPLIST-POLL] update failed: {_scrub(exc, token)}")

                offset = consume_batch(data, offset, feed, on_error)
            except WebhookConflict:
                api_call('deleteWebhook', {'drop_pending_updates': False}, token=token)
                time.sleep(2)
                continue
            if not data or not data.get('ok'):
                time.sleep(5)
        except Exception as exc:
            print(f"[TAPLIST-POLL] исключение в цикле: {_scrub(exc, token)}")
            time.sleep(10)


def start_polling() -> None:
    """Запустить daemon-поток polling'а. Идемпотентно; лок отдаёт его одному процессу."""
    global _started, _lock_handle
    with _thread_lock:
        if _started:
            return
        if not os.environ.get('TELEGRAM_BOT_TOKEN'):
            print('[TAPLIST-POLL] TELEGRAM_BOT_TOKEN не задан — polling отключён')
            return
        if _polling_disabled():
            print('[TAPLIST-POLL] TAPLIST_POLLING=0 — polling отключён')
            return

        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        handle = open(LOCK_PATH, 'a')
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            handle.close()
            print('[TAPLIST-POLL] лок занят другим воркером — в этом процессе polling не нужен')
            return

        _lock_handle = handle
        thread = threading.Thread(target=_poll_loop, name='taplist-polling', daemon=True)
        thread.start()
        _started = True

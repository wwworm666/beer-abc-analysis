"""Telegram-слой open-check бота: HTTP-вызовы и обработка команд/меню.

Реализовано на чистом requests (без aiogram) — бот простой, синхронный requests
надёжнее и тестируется локально без лишних зависимостей.

Бот делает две вещи:
- авто-оповещения (см. core/open_check_bot.py) шлются на чаты из env и на тех,
  кто сам подписался кнопкой в боте (core/open_check_subscribers.py);
- отвечает на команды /start (меню: подписаться/отписаться + статус) и /status
  (опросить iiko и показать статус 4 баров прямо сейчас).

Меню простое: одна кнопка-переключатель подписки + «Статус баров сейчас».
Подписчик получает все типы уведомлений (раздельный выбор positive/alarm убран).

Содержит:
- низкоуровневые вызовы Telegram Bot API (send_message, editMessageText, ...);
- регистрацию webhook (set_webhook / delete_webhook / get_webhook_info);
- обработку входящих апдейтов (handle_update) — команды + callback подписки.
"""
import hashlib
import logging
import os
import time

import requests

log = logging.getLogger("open-check-tg")

_API_HOST = "api.telegram.org"
_API = f"https://{_API_HOST}"

# --- запасной путь при блокировке основного IP ------------------------------
# Основной путь — имя api.telegram.org, запиненное на живой IP в
# docker-compose.yml (extra_hosts). Если заблокируют и его, api_call
# автоматически пробует запасные адреса: TLS к голому IP с SNI и проверкой
# сертификата на имя api.telegram.org (_SNIAdapter) + заголовок Host.
# Кандидаты: кэш последнего живого -> статический список -> текущие A-записи
# через DoH (мимо системного DNS, который может отдавать заблокированный IP).
# После сбоя основного пути _PRIMARY_COOLDOWN секунд ходим сразу через
# запасной, чтобы getUpdates-цикл не ждал таймаут на каждом вызове.
# Гонки потоков (polling + шедулер) на этих глобалах безвредны: худший
# случай — лишний перебор кандидатов.
_FALLBACK_IPS = ["149.154.167.220", "149.154.166.110"]
_DOH_URLS = (
    "https://dns.google/resolve?name=api.telegram.org&type=A",
    "https://cloudflare-dns.com/dns-query?name=api.telegram.org&type=A",
)
_PRIMARY_COOLDOWN = 300  # секунд
_primary_dead_until = 0.0
_working_ip = None


class _SNIAdapter(requests.adapters.HTTPAdapter):
    """TLS к голому IP с SNI и проверкой сертификата на имя api.telegram.org."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["server_hostname"] = _API_HOST
        kwargs["assert_hostname"] = _API_HOST
        return super().init_poolmanager(*args, **kwargs)


def _doh_resolve() -> list:
    """Текущие A-записи api.telegram.org через DNS-over-HTTPS. Best-effort."""
    for url in _DOH_URLS:
        try:
            r = requests.get(url, headers={"accept": "application/dns-json"}, timeout=4)
            answers = r.json().get("Answer") or []
            ips = [a["data"] for a in answers if a.get("type") == 1]
            if ips:
                return ips
        except Exception:
            continue
    return []


def _iter_candidate_ips():
    """Запасные IP в порядке перспективности; DoH дёргается только если
    статический список не помог (ленивый генератор)."""
    seen = set()
    head = ([_working_ip] if _working_ip else []) + _FALLBACK_IPS
    for ip in head:
        if ip not in seen:
            seen.add(ip)
            yield ip
    for ip in _doh_resolve():
        if ip not in seen:
            seen.add(ip)
            yield ip


def _post_via_ip(ip: str, method: str, token: str, payload: dict, timeout) -> dict:
    """POST к Bot API по голому IP (SNI + Host = api.telegram.org)."""
    s = requests.Session()
    s.mount("https://", _SNIAdapter())
    try:
        r = s.post(f"https://{ip}/bot{token}/{method}", json=payload or {},
                   headers={"Host": _API_HOST}, timeout=timeout)
        return r.json()
    finally:
        s.close()


def _token():
    return os.environ.get("TELEGRAM_OPEN_CHECK_BOT_TOKEN")


def _scrub(e) -> str:
    """Убрать токен из текста перед логированием: исключения requests
    содержат полный URL вида /bot<token>/<method>."""
    s = str(e)
    t = _token()
    return s.replace(t, "<TOKEN>") if t else s


def webhook_secret() -> str:
    """Секрет для проверки входящих webhook-запросов (заголовок Telegram).

    Выводится из токена — отдельная env не нужна. Telegram присылает его в
    X-Telegram-Bot-Api-Secret-Token, мы сверяем.
    """
    return hashlib.sha256(("ocwh:" + (_token() or "")).encode()).hexdigest()[:40]


def api_call(method: str, payload: dict = None, timeout: int = 8):
    # timeout=8 (было 20): webhook-хендлер вызывает api_call синхронно, а воркеров
    # всего 2 — долгий ответ Telegram не должен надолго занимать воркер.
    # timeout трактуется как read-timeout; на connect всегда 5с — заблокированный
    # IP отваливается на connect, и длинный read-timeout getUpdates его не ждёт.
    global _primary_dead_until, _working_ip
    token = _token()
    if not token:
        log.error("TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан")
        return None

    if time.time() >= _primary_dead_until:
        try:
            r = requests.post(f"{_API}/bot{token}/{method}", json=payload or {},
                              timeout=(5, timeout))
            data = r.json()
            if not data.get("ok"):
                log.warning("TG %s -> %s", method, data.get("description"))
            return data
        except Exception as e:
            _primary_dead_until = time.time() + _PRIMARY_COOLDOWN
            log.warning("TG %s: основной путь не работает (%s) — пробуем запасные IP",
                        method, _scrub(e))

    for ip in _iter_candidate_ips():
        try:
            data = _post_via_ip(ip, method, token, payload, (5, timeout))
        except Exception as e:
            log.warning("TG %s via %s failed: %s", method, ip, _scrub(e))
            continue
        if _working_ip != ip:
            log.warning("TG: переключился на запасной IP %s", ip)
            _working_ip = ip
        if not data.get("ok"):
            log.warning("TG %s -> %s", method, data.get("description"))
        return data

    log.warning("TG %s failed: все пути исчерпаны (основной + %d запасных)",
                method, len(_FALLBACK_IPS))
    return None


def send_message(chat_id, text: str, reply_markup: dict = None, html: bool = False) -> bool:
    # html=True — для отчётов open-check (<b> в тревоге/ошибке); меню и прочие
    # сообщения шлются плоским текстом, чтобы не экранировать всё подряд.
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if html:
        payload["parse_mode"] = "HTML"
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    data = api_call("sendMessage", payload)
    return bool(data and data.get("ok"))


def answer_callback(callback_id: str, text: str = None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    return api_call("answerCallbackQuery", payload)


def edit_message_text(chat_id, message_id, text: str, reply_markup: dict = None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
               "disable_web_page_preview": True}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return api_call("editMessageText", payload)


def set_webhook(url: str):
    return api_call("setWebhook", {
        "url": url,
        "secret_token": webhook_secret(),
        "drop_pending_updates": True,
        "allowed_updates": ["message", "callback_query"],
    })


def delete_webhook():
    return api_call("deleteWebhook", {"drop_pending_updates": True})


def get_webhook_info():
    return api_call("getWebhookInfo")


def set_my_commands():
    return api_call("setMyCommands", {"commands": [
        {"command": "start", "description": "Подписка и меню"},
        {"command": "status", "description": "Статус баров сейчас"},
    ]})


# ---------------------------------------------------------------- меню/команды

def _menu_keyboard(subscribed: bool) -> dict:
    """Простое меню: одна кнопка подписки-переключателя + статус.
    Раньше было 5 кнопок (positive/alarm/both/off/status) — упрощено."""
    toggle = ({"text": "Отписаться от уведомлений", "callback_data": "oc_off"} if subscribed
              else {"text": "Подписаться на уведомления", "callback_data": "oc_on"})
    return {"inline_keyboard": [
        [toggle],
        [{"text": "Статус баров сейчас", "callback_data": "oc_status"}],
    ]}


def _start_text(chat_id, subscribed: bool) -> str:
    state = "да" if subscribed else "нет"
    return (
        "Бот мониторинга открытия баров KULT.\n"
        "Раз в день в 14:59 МСК присылает сводку: все бары открыты или какой-то закрыт.\n\n"
        f"Уведомления приходят в этот чат: {state}\n"
        f"ID этого чата: {chat_id}\n\n"
        "Кнопкой ниже можно подписаться или отписаться. "
        "«Статус баров сейчас» — проверить вручную в любой момент."
    )


def _live_status_text() -> str:
    """Опросить iiko прямо сейчас и собрать ответ на /status."""
    from core.open_check_bot import check_bars_state, format_status_reply, now_msk
    dt = now_msk()
    return format_status_reply(check_bars_state(dt), dt)


def _send_menu(chat_id, subs) -> None:
    sub = subs.is_subscribed(chat_id)
    send_message(chat_id, _start_text(chat_id, sub), reply_markup=_menu_keyboard(sub))


def _handle_callback(cq: dict, subs) -> None:
    cq_id = cq.get("id")
    if not cq_id:
        return  # малформед-апдейт без callback id — подтверждать нечем
    data = cq.get("data")
    message = cq.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    if chat_id is None:
        answer_callback(cq_id)
        return

    if data == "oc_status":
        answer_callback(cq_id, "Проверяю...")
        send_message(chat_id, _live_status_text(), html=True)
        return

    # subscribed = состояние ПОСЛЕ переключения (не перечитываем файл повторно).
    if data == "oc_on":
        subs.subscribe(chat_id)
        subscribed, note = True, "Подписка оформлена"
    elif data == "oc_off":
        subs.unsubscribe(chat_id)
        subscribed, note = False, "Подписка отключена"
    else:
        answer_callback(cq_id)
        return

    answer_callback(cq_id, note)
    if message_id is not None:
        edit_message_text(chat_id, message_id, _start_text(chat_id, subscribed),
                          reply_markup=_menu_keyboard(subscribed))


def handle_update(update: dict) -> None:
    """Обработать один апдейт. Команды: /start (меню+подписка), /status, /subscribe,
    /unsubscribe. Подписка переключается кнопкой (callback_query)."""
    from core import open_check_subscribers as subs

    cq = update.get("callback_query")
    if cq:
        _handle_callback(cq, subs)
        return

    msg = update.get("message")
    if not msg:
        return
    text = (msg.get("text") or "").strip()
    chat_id = msg.get("chat", {}).get("id")
    if not text or chat_id is None:
        return
    cmd = text.split("@")[0].split()[0]
    if cmd in ("/start", "/menu", "/help"):
        _send_menu(chat_id, subs)
    elif cmd == "/status":
        # html=True: format_status_reply помечает закрытые бары <b>…</b>
        send_message(chat_id, _live_status_text(), html=True)
    elif cmd == "/subscribe":
        subs.subscribe(chat_id)
        send_message(chat_id, "Подписка оформлена. Уведомления будут приходить в этот чат.")
    elif cmd in ("/unsubscribe", "/stop"):
        subs.unsubscribe(chat_id)
        send_message(chat_id, "Подписка отключена. Уведомления больше не приходят.")

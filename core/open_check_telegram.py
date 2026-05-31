"""Telegram-слой open-check бота: HTTP-вызовы и интерактивное меню.

Реализовано на чистом requests (без aiogram) — бот простой (меню + подписка),
синхронный requests надёжнее и тестируется локально без лишних зависимостей.

Содержит:
- низкоуровневые вызовы Telegram Bot API (send_message, editMessageText, ...);
- регистрацию webhook (set_webhook / delete_webhook / get_webhook_info);
- обработку входящих апдейтов (handle_update) — меню с inline-кнопками для
  подключения текущего чата к уведомлениям (см. core/open_check_subscribers.py).
"""
import hashlib
import logging
import os

import requests

log = logging.getLogger("open-check-tg")

_API = "https://api.telegram.org"


def _token():
    return os.environ.get("TELEGRAM_OPEN_CHECK_BOT_TOKEN")


def webhook_secret() -> str:
    """Секрет для проверки входящих webhook-запросов (заголовок Telegram).

    Выводится из токена — отдельная env не нужна. Telegram присылает его в
    X-Telegram-Bot-Api-Secret-Token, мы сверяем.
    """
    return hashlib.sha256(("ocwh:" + (_token() or "")).encode()).hexdigest()[:40]


def api_call(method: str, payload: dict = None, timeout: int = 8):
    # timeout=8 (было 20): webhook-хендлер вызывает api_call синхронно, а воркеров
    # всего 2 — долгий ответ Telegram не должен надолго занимать воркер.
    token = _token()
    if not token:
        log.error("TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан")
        return None
    try:
        r = requests.post(f"{_API}/bot{token}/{method}", json=payload or {}, timeout=timeout)
        data = r.json()
        if not data.get("ok"):
            log.warning("TG %s -> %s", method, data.get("description"))
        return data
    except Exception as e:
        log.warning("TG %s failed: %s", method, e)
        return None


def send_message(chat_id, text: str, reply_markup: dict = None) -> bool:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
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
        {"command": "start", "description": "Меню подключения чата"},
        {"command": "status", "description": "Что получает этот чат"},
    ]})


# ---------------------------------------------------------------- меню

def _menu_keyboard() -> dict:
    return {"inline_keyboard": [
        [{"text": "Сюда слать: все открыто", "callback_data": "oc_pos"}],
        [{"text": "Сюда слать: тревоги", "callback_data": "oc_alarm"}],
        [{"text": "Подключить оба типа", "callback_data": "oc_both"}],
        [{"text": "Отключить этот чат", "callback_data": "oc_off"}],
        [{"text": "Статус", "callback_data": "oc_status"}],
    ]}


def _status_text(chat_id, st: dict) -> str:
    pos = "да" if st.get("positive") else "нет"
    al = "да" if st.get("alarm") else "нет"
    return (
        "Open-check бот.\n"
        f"ID этого чата: {chat_id}\n\n"
        "Сейчас этот чат получает:\n"
        f"- Все открыто (14:59): {pos}\n"
        f"- Тревоги (бар закрыт): {al}\n\n"
        "Выберите, что присылать в этот чат:"
    )


def handle_update(update: dict) -> None:
    """Обработать один webhook-апдейт от Telegram."""
    from core import open_check_subscribers as subs

    msg = update.get("message")
    cq = update.get("callback_query")

    if msg:
        text = (msg.get("text") or "").strip()
        chat_id = msg.get("chat", {}).get("id")
        cmd = text.split("@")[0].split()[0] if text else ""
        if cmd in ("/start", "/menu"):
            send_message(chat_id, _status_text(chat_id, subs.status(chat_id)),
                         reply_markup=_menu_keyboard())
        elif cmd == "/status":
            send_message(chat_id, _status_text(chat_id, subs.status(chat_id)),
                         reply_markup=_menu_keyboard())
        return

    if cq:
        data = cq.get("data")
        cq_id = cq.get("id")
        message = cq.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        note = None
        if data == "oc_pos":
            subs.subscribe(chat_id, ["positive"]); note = "Подключено: все открыто"
        elif data == "oc_alarm":
            subs.subscribe(chat_id, ["alarm"]); note = "Подключено: тревоги"
        elif data == "oc_both":
            subs.subscribe(chat_id, ["positive", "alarm"]); note = "Подключено: оба типа"
        elif data == "oc_off":
            subs.unsubscribe(chat_id); note = "Этот чат отключен"
        elif data == "oc_status":
            note = "Обновлено"

        answer_callback(cq_id, note)
        if chat_id is not None and message_id is not None:
            edit_message_text(chat_id, message_id,
                              _status_text(chat_id, subs.status(chat_id)),
                              reply_markup=_menu_keyboard())
        return

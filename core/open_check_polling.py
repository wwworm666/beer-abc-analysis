"""Long-polling вместо webhook для меню open-check бота.

Зачем: входящие соединения от Telegram (подсети 149.154.160.0/20,
91.108.4.0/22) до сервера блокируются на магистрали (ТСПУ) — webhook-апдейты
не доставляются, getWebhookInfo показывает "Connection timed out".
Исходящие запросы работают (api.telegram.org пинится на доступный IP через
extra_hosts в docker-compose.yml), поэтому команды бота сервер забирает сам
через getUpdates. Подробности: docs/open-check-bot.md, раздел "Блокировки".

Singleton под gunicorn --workers 2: оба воркера импортят app.py и зовут
start_polling(), но поллить должен ровно один процесс — второй параллельный
getUpdates получил бы 409 Conflict. Эксклюзивный flock (portalocker) на
data/.open_check_polling.lock держится всё время жизни процесса; воркер,
не получивший лок, тихо выходит. При смерти процесса ОС снимает flock
автоматически (в отличие от O_CREAT|O_EXCL-файла — нет проблемы протухшего
лока), и replacement-воркер gunicorn подхватывает polling при старте.

Webhook и getUpdates взаимоисключающи на стороне Telegram: пока webhook
зарегистрирован, getUpdates отвечает 409. Поэтому при старте (и при 409 в
цикле) webhook снимается БЕЗ drop_pending_updates — накопленные недоставленные
команды приходят через getUpdates и бот на них отвечает.

Отключение: OPEN_CHECK_POLLING=0 (например, если домен уехал за Cloudflare и
webhook снова доставляется — тогда вернуть setup-webhook).
"""
import os
import threading
import time

import portalocker

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.open_check_polling.lock')

# getUpdates держит соединение до POLL_TIMEOUT секунд (long poll);
# HTTP-таймаут должен быть больше, иначе requests оборвёт ожидание.
POLL_TIMEOUT = 25
HTTP_TIMEOUT = POLL_TIMEOUT + 10

_started = False
_thread_lock = threading.Lock()
_lock_handle = None  # держим файл открытым, пока жив процесс — иначе flock снимется


def _polling_disabled() -> bool:
    return os.environ.get('OPEN_CHECK_POLLING', '1').lower() in ('0', 'false', 'off', 'no')


def _poll_loop() -> None:
    from core import open_check_telegram as tg

    # Снять webhook, сохранив очередь недоставленных апдейтов.
    tg.api_call("deleteWebhook", {"drop_pending_updates": False})
    # Обновить список команд в меню Telegram (/status, /start).
    tg.set_my_commands()

    me = tg.api_call("getMe")
    if me and me.get("ok"):
        print(f"[OPEN-CHECK-POLL] polling стартовал, бот @{me['result'].get('username')}")
    else:
        print("[OPEN-CHECK-POLL] getMe не ответил — polling продолжит пытаться")

    offset = None
    while True:
        try:
            payload = {"timeout": POLL_TIMEOUT,
                       "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                payload["offset"] = offset
            data = tg.api_call("getUpdates", payload, timeout=HTTP_TIMEOUT)
            if not data or not data.get("ok"):
                if data and data.get("error_code") == 409:
                    # Кто-то снова зарегистрировал webhook — снимаем и продолжаем.
                    tg.api_call("deleteWebhook", {"drop_pending_updates": False})
                time.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    tg.handle_update(upd)
                except Exception as e:
                    # _scrub: исключения requests содержат URL с токеном бота
                    print(f"[OPEN-CHECK-POLL] handle_update failed: {tg._scrub(e)}")
        except Exception as e:
            print(f"[OPEN-CHECK-POLL] исключение в цикле: {tg._scrub(e)}")
            time.sleep(10)


def start_polling() -> None:
    """Запустить daemon-поток polling'а. Идемпотентно; лок отдаёт его одному процессу."""
    global _started, _lock_handle
    with _thread_lock:
        if _started:
            return
        if not os.environ.get("TELEGRAM_OPEN_CHECK_BOT_TOKEN"):
            print("[OPEN-CHECK-POLL] TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан — polling отключён")
            return
        if _polling_disabled():
            print("[OPEN-CHECK-POLL] OPEN_CHECK_POLLING=0 — polling отключён")
            return

        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        f = open(LOCK_PATH, 'a')
        try:
            portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            f.close()
            print("[OPEN-CHECK-POLL] лок занят другим воркером — в этом процессе polling не нужен")
            return

        _lock_handle = f
        t = threading.Thread(target=_poll_loop, name="open-check-polling", daemon=True)
        t.start()
        _started = True

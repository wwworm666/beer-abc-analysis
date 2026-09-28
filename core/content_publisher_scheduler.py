"""Фоновая отправка публикаций контент-плана: раз в минуту — publish_due.

## Что это

Поток, который каждую минуту зовёт core/content_publisher.publish_due: утверждённые
публикации уходят в Telegram-каналы баров, напоминания об Instagram — владельцу,
рассылки — гостям (правила — в докстроке core/content_publisher.py). Что и куда
отправлять, решают настройки «Каналы и отправка» (core/content_channels.py): пока
владелец не включил отправку, проход ничего не шлёт.

## Файлы

| Файл | Роль |
|------|------|
| `core/content_publisher_scheduler.py` | этот модуль: поток и блокировка «один процесс» |
| `core/content_publisher.py` | один проход отправки |
| `app.py` | зовёт start_scheduler() при старте (вызов добавляет оркестратор) |

## Как работает

- Такт — начало каждой минуты + TICK_OFFSET_SEC (1 с): пост на 16:00 уходит в
  16:00:01, а не «когда-нибудь в течение минуты».
- Один процесс на все воркеры gunicorn: flock на data/.content_publisher.lock (как
  core/taplist_polling.py). Второй воркер лок не получает и поток не заводит.
  Защита от дубля есть и без лока (отметка «отправляется» под блокировкой плана),
  лок экономит лишние проходы.
- start_scheduler() идемпотентен. Молча (одна строка в лог) не стартует:
  без токена бота (TELEGRAM_CONTENT_BOT_TOKEN / TELEGRAM_BOT_TOKEN) и при
  CONTENT_PUBLISH=0 (выключить совсем).
- Сбой прохода (битый файл плана или настроек — 503-случаи) пишется в лог, поток
  живёт дальше; в лог — только проходы, где что-то отправлено или упало.

## Changelog

- 2026-09-28 — модуль создан.
"""
import os
import threading
import time
from typing import Callable, Optional

import portalocker

from core import msk_time

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.content_publisher.lock')
# Секунда после начала минуты: часы хранилища считают минуту целиком, поэтому
# проход в hh:mm:01 видит публикации на hh:mm как «пора».
TICK_OFFSET_SEC = 1

_started = False
_thread_lock = threading.Lock()
_lock_handle = None


def disabled() -> bool:
    """CONTENT_PUBLISH=0 (false/off/no) — отправку не запускать вовсе."""
    return os.environ.get('CONTENT_PUBLISH', '1').strip().lower() in ('0', 'false', 'off', 'no')


def seconds_to_next_tick(now=None) -> float:
    """Секунд до следующего такта (начало минуты + TICK_OFFSET_SEC)."""
    moment = now or msk_time.now()
    passed = moment.second + moment.microsecond / 1_000_000
    wait = 60 - passed + TICK_OFFSET_SEC
    return wait if wait > 0 else 1.0


def run_once() -> dict:
    """Один проход отправки (настоящий Telegram, токен из окружения)."""
    from core.content_publisher import publish_due
    report = publish_due()
    if report.get('sent') or report.get('failed'):
        lines = [f'{d["result"]}: {d["title"]} ({d["channel"]}, {d["bar"]}) {d["text"]}'
                 for d in report['details'] if d['result'] != 'skipped']
        print('[CONTENT-PUBLISH] ' + '; '.join(lines))
    return report


def _loop() -> None:
    while True:
        time.sleep(seconds_to_next_tick())
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 — поток отправки не должен умирать
            print(f'[CONTENT-PUBLISH] проход не выполнен: {e!r}')


def _start_thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name='content-publisher', daemon=True).start()


def start_scheduler(lock_path: Optional[str] = None) -> bool:
    """Запустить поток отправки. Идемпотентно. -> True, если поток работает в
    этом процессе (запущен сейчас или раньше). Не стартует без токена бота, при
    CONTENT_PUBLISH=0 и если лок уже держит другой воркер."""
    global _started, _lock_handle
    with _thread_lock:
        if _started:
            return True
        if disabled():
            print('[CONTENT-PUBLISH] CONTENT_PUBLISH=0 — отправка публикаций отключена')
            return False
        from core.content_channels import channel_bot_token
        token, source = channel_bot_token()     # без него нет и гостевого (тот же TELEGRAM_BOT_TOKEN)
        if not token:
            print('[CONTENT-PUBLISH] бот не настроен (нет TELEGRAM_CONTENT_BOT_TOKEN и TELEGRAM_BOT_TOKEN) — '
                  'отправка публикаций отключена')
            return False
        path = lock_path or LOCK_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handle = open(path, 'a')
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            handle.close()
            print('[CONTENT-PUBLISH] лок занят другим воркером — в этом процессе отправка не нужна')
            return False
        _lock_handle = handle
        _start_thread(_loop)
        _started = True
        print(f'[CONTENT-PUBLISH] отправка публикаций запущена (бот: {source}); '
              'шлёт только то, что владелец включил в «Каналы и отправка»')
        return True

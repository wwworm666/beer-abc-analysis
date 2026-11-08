"""Журнал вопросов и ответов бота: запись о каждой работе (решение владельца 2026-11-06).

## Что это

Владелец спросил «мы храним все запросы и ответы?» — нет: сервер бота держал только текущий
разговор чата. Решение: полный журнал, «подготовим к выпуску в прод» — чтобы разбирать, где бот
ошибается, сколько стоят ответы и кто чем пользуется.

Запись — одна на вопрос (работу), с любым концом: ответ, ошибка, «Остановить», предел:

    uid, job_id          своя метка записи (uuid4) и номер вопроса в базе сервера бота
    asked_at, finished_at, seconds, waited   когда пришёл, когда кончился, сколько шла работа и ждала очереди
    chat_id, chat_type, tg_user_id, login, name   где и кто спросил (администратор сайта)
    mode, source         answer | report; message | button (кнопка следующего шага) | menu (вопрос из
                         меню раздела: /sales, /stock, /staff, /content)
    fast, fast_steps     спросили «/fast …» (быстрый режим, с 2026-11-08 только по команде); сколько
                         запросов к модели на самом деле прошло в нём (остальные — на обычной скорости)
    question             текст вопроса (до QUESTION_MAX)
    files                что приложили: [{kind: image|document, mime}] — сами файлы не хранятся
    reply_to             ответ на сообщение бота: {message_id} — какую работу продолжали
    answer               что увидел человек: ответ модели (Markdown, с «Как считается») или текст ошибки
    cards                графики и отчёты, ушедшие картинкой или страницей: инструмент, id, заголовок, подпись
    messages             message_id всех сообщений ответа — по ним реакция человека находит запись
    format               rich | plain — каким видом ушёл ответ
    status, error        done | error | stopped | budget; причина (до ERROR_MAX)
    notes                пометки разговора: max_rounds, question_budget, refusal, …
    cost_usd, steps, tool_calls   расход (бот и агенты вместе), запросов к модели, вызовов инструментов
    calls                вызовы инструментов по порядку: имя, аргументы (до ARGS_MAX), секунды, ok,
                         начало ошибки, agent — вызов агента (до CALLS_MAX)
    model                модель из настроек

Сервер бота кладёт запись в свою базу (store.outbox_*) и сразу отправляет её сайту
(POST /api/bot/journal) пачками; сайт не ответил — запись ждёт и уходит со следующей попыткой
(service.flush_journal, не чаще раза в FLUSH_RETRY_S). Хранит и показывает журнал сайт
(kultura_bot/journal.py, страница /admin/bot/journal): он в России и уже держит данные сети.

Кода сайта модуль не импортирует.
"""
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from kultura_bot import settings

QUESTION_MAX = 8000
ANSWER_MAX = 40000
ERROR_MAX = 500
ARGS_MAX = 300
CALLS_MAX = 200
CARD_TEXT_MAX = 4000


def _iso(ts: float) -> str:
    from kultura_bot.engine.store import MSK
    return datetime.fromtimestamp(ts, MSK).isoformat(timespec='seconds')


def args_preview(args: Any) -> str:
    """Аргументы вызова коротко: JSON до ARGS_MAX знаков (длинные тексты — обрезаны)."""
    try:
        text = json.dumps(args if args is not None else {}, ensure_ascii=False, separators=(',', ':'))
    except (TypeError, ValueError):
        text = str(args)
    return text if len(text) <= ARGS_MAX else text[:ARGS_MAX - 1] + '…'


def start(job: Dict[str, Any], chat_id: str, job_id: int) -> Dict[str, Any]:
    """Начало записи: что спросили, где, кем (кто — уточняется, когда сайт подтвердит права)."""
    message = job.get('message') or {}
    author = message.get('from') or {}
    files: List[Dict[str, str]] = []
    if message.get('photo'):
        files.append({'kind': 'image', 'mime': 'image/jpeg'})
    document = message.get('document') or {}
    if document:
        files.append({'kind': 'document', 'mime': str(document.get('mime_type') or '')[:80]})
    replied = message.get('reply_to_message') or {}
    actor = job.get('actor') or {}
    asked = float(job.get('asked_ts') or time.time())
    return {
        'uid': uuid.uuid4().hex,
        'job_id': int(job_id),
        'asked_ts': asked,
        'chat_id': str(chat_id),
        'chat_type': str((message.get('chat') or {}).get('type') or job.get('chat_type') or ''),
        'tg_user_id': str(author.get('id') or actor.get('tg_user_id') or ''),
        'login': str(actor.get('login') or ''),
        'name': str(actor.get('display_name') or ''),
        'mode': 'report' if job.get('mode') == 'report' else 'answer',
        'source': str(job.get('source') or 'message'),
        'fast': bool(job.get('fast')),
        'question': str(job.get('text') or '')[:QUESTION_MAX],
        'files': files,
        'reply_to': {'message_id': replied['message_id']} if replied.get('message_id') else None,
    }


def finish(entry: Dict[str, Any], *, status: str, error: str = '', shown: str = '', ctx: Any = None,
           tracker: Any = None, spend: Any = None, result: Any = None, started_ts: Optional[float] = None,
           now: Optional[float] = None) -> Dict[str, Any]:
    """Запись целиком (JSON для сайта) — из того, что накопила работа."""
    now = time.time() if now is None else now
    record = {k: v for k, v in entry.items() if k != 'asked_ts'}
    asked = entry.get('asked_ts') or now
    started = started_ts if started_ts is not None else asked
    delivered = dict(getattr(ctx, 'delivered', None) or {})
    cards = [dict(c) for c in (getattr(ctx, 'cards', None) or [])]
    answer = (getattr(result, 'text', '') or '') if status == 'done' else ''
    if not answer and shown:
        answer = shown
    messages = list(delivered.get('message_ids') or [])
    for card in cards:
        if card.get('message_id') and card['message_id'] not in messages:
            messages.append(card['message_id'])
    record.update({
        'asked_at': _iso(asked),
        'finished_at': _iso(now),
        'seconds': round(max(now - started, 0.0), 1),
        'waited': round(max(started - asked, 0.0), 1),
        'answer': answer[:ANSWER_MAX],
        'cards': cards,
        'messages': [int(m) for m in messages if isinstance(m, int)],
        'format': str(delivered.get('format') or ''),
        'status': status,
        'error': str(error or '')[:ERROR_MAX],
        'notes': list(getattr(result, 'notes', None) or []),
        'cost_usd': round(float(getattr(spend, 'usd', 0.0) or 0.0), 4),
        'steps': int(getattr(spend, 'steps', 0) or 0),
        'fast_steps': int(getattr(spend, 'fast_steps', 0) or 0),
        'tool_calls': int(getattr(tracker, 'tool_calls', 0) or 0),
        'calls': list(getattr(ctx, 'calls', None) or [])[:CALLS_MAX],
        'model': settings.MODEL,
    })
    return record

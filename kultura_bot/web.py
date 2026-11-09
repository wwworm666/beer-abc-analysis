"""Вопросы боту kultura.research со страницы сайта (решение владельца 2026-11-09).

## Что это

Владелец: «нужно дублировать функционал бота на сайт: страница, которая также позволяет задать
вопрос и получить либо краткий ответ, либо ресерч; весь бриф, все графики — всё сохраняется».
Страница /research (routes/research.py) — те же ответы, что в Telegram: обычный вопрос — короткий
ответ, Research — отчёт страницей; графики, «Как считается», кнопки следующего шага, строка цены.

## Как устроено (сайт к Claude не обращается)

Сайт стоит в России, API Anthropic оттуда недоступен (.claude/CLAUDE.md). Поэтому страница только
кладёт вопрос в очередь — таблица bot_web_questions в mcp.db, — а отвечает тот же сервер бота в
Амстердаме, что и в Telegram, тем же кодом (kultura_bot/engine/service.answer: те же инструкции,
инструменты сайта, агенты, пределы расхода):

    страница  POST /api/research/ask                     -> вопрос queued
    сервер    GET  /api/bot/web/next                     -> вопрос taken (берёт, когда есть свободное место)
    сервер    POST /api/bot/web/<id>/beat {progress}     -> running; в ответ — нажали ли «Остановить»
    сервер    POST /api/bot/web/<id>/card {tool, args}   -> график или отчёт ложится в вопрос (не в Telegram)
    сервер    POST /api/bot/web/<id>/finish {...}        -> done | error | stopped | budget
    страница  GET  /api/research/questions/<id>          раз в 2 секунды, пока вопрос не готов

Беседа (thread) — диалог бота: у сервера бота это чат «web:<id беседы>» (своя история, как у чата
Telegram; простой дольше DIALOG_IDLE_MINUTES — разговор начинается заново, а прошлые вопросы беседы
сервер получает отсюда кратко, history). В одной беседе вопросы идут по одному; у человека — не
больше ACTIVE_MAX вопросов в работе сразу. Сервер бота молчит дольше STALE_S — вопрос закрывается
ошибкой «сервер бота перестал отвечать» (перезапуск, обрыв связи).

## Что хранится — навсегда (решение владельца: «всё сохраняется»)

Вопрос, ответ (Markdown), «Как считается», кнопки следующего шага, пометки, расход и карточки:
график — описанием целиком (kultura_bot/charts/spec.normalize), отчёт — телом целиком
(reports.normalize_report). Поэтому старый ответ рисуется со всеми графиками и через год, хотя
у графиков и отчётов Telegram срок — 90 дней. Отчёт к тому же сохраняется в tg_reports — пока он
там (90 дней), у карточки есть отдельная страница /tg/report/<id> и ссылка для браузера.
Удалить можно только беседу целиком — кнопкой на странице. Каждый человек видит только свои беседы.

Кода сервера бота модуль не импортирует, кроме общих функций разметки (kultura_bot/engine/
formatting.py — их уже использует сайт для подписей и отчётов).
"""
import json
import re
import secrets
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core import msk_time
from core.mcp import db

MODES = ('answer', 'report')                       # answer — краткий ответ, report — Research (отчёт страницей)
ACTIVE = ('queued', 'taken', 'running')
FINAL = ('done', 'error', 'stopped', 'budget')
QUESTION_MAX = 8000                                # знаков вопроса (как у журнала бота)
ANSWER_MAX = 40000
HOW_MAX = 20000
NOTICE_MAX = 500
SHOWN_MAX = 2000                                   # текст ошибки, остановки, предела — что увидел человек
ERROR_MAX = 500
PROGRESS_MAX = 600
ASK_MAX = 6                                        # кнопок следующего шага у ответа
ASK_TEXT_MAX = 64
CAPTION_MAX = 4000                                 # Markdown подписи графика
CARD_HOW_MAX = 6000
CARDS_MAX = 12                                     # графиков и отчётов в одном ответе
ACTIVE_MAX = 3                                     # вопросов в работе у человека сразу
STALE_S = 5 * 60                                   # сервер бота не отзывался — вопрос закрывается ошибкой
THREADS_LIMIT = 60                                 # бесед в списке страницы
HISTORY_QUESTIONS = 6                              # прошлых вопросов беседы — серверу бота, если диалог начат заново
HISTORY_ANSWER_MAX = 3000
ID_RE = re.compile(r'[qt][A-Za-z0-9_-]{16}')       # q… — вопрос, t… — беседа (token_urlsafe(12))
CHART_TOOL = 'common_chart_send'
REPORT_TOOL = 'common_report_send'

STALE_TEXT = 'Сервер бота перестал отвечать (перезапуск или обрыв связи) — задайте вопрос ещё раз.'
STOPPED_TEXT = 'Остановлено.'
NO_ACCESS_TEXT = 'Нет доступа: вопросы боту — только администраторам сайта.'

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS bot_web_questions (
        id          TEXT PRIMARY KEY,
        thread_id   TEXT NOT NULL,
        user_id     INTEGER NOT NULL,
        login       TEXT NOT NULL,
        name        TEXT NOT NULL,
        question    TEXT NOT NULL,
        mode        TEXT NOT NULL,
        fast        INTEGER NOT NULL DEFAULT 0,
        status      TEXT NOT NULL,
        progress    TEXT NOT NULL DEFAULT '',
        answer      TEXT NOT NULL DEFAULT '',
        how         TEXT NOT NULL DEFAULT '',
        notice      TEXT NOT NULL DEFAULT '',
        ask         TEXT NOT NULL DEFAULT '[]',
        cards       TEXT NOT NULL DEFAULT '[]',
        shown       TEXT NOT NULL DEFAULT '',
        error       TEXT NOT NULL DEFAULT '',
        cost_usd    REAL NOT NULL DEFAULT 0,
        steps       INTEGER NOT NULL DEFAULT 0,
        fast_steps  INTEGER NOT NULL DEFAULT 0,
        asked_ts    INTEGER NOT NULL,
        taken_ts    INTEGER,
        beat_ts     INTEGER,
        finished_ts INTEGER,
        stop        INTEGER NOT NULL DEFAULT 0
    )''',
    'CREATE INDEX IF NOT EXISTS idx_bot_web_user ON bot_web_questions(user_id, asked_ts)',
    'CREATE INDEX IF NOT EXISTS idx_bot_web_thread ON bot_web_questions(thread_id, asked_ts)',
    'CREATE INDEX IF NOT EXISTS idx_bot_web_status ON bot_web_questions(status, asked_ts)',
)

TextFilter = Callable[[str], str]


class WebError(ValueError):
    """Вопрос или вызов не прошли проверку: текст — для человека (страница) или сервера бота."""


def _ensure() -> None:
    db.ensure_schema('bot_web_questions', SCHEMA)


def new_id(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(12)


def valid_id(value: Any, prefix: str) -> bool:
    return isinstance(value, str) and value[:1] == prefix and bool(ID_RE.fullmatch(value))


def chat_id(thread_id: str) -> str:
    """Чат сервера бота для беседы: свой диалог, как у чата Telegram."""
    return 'web:' + thread_id


def _iso(ts: Optional[float]) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, msk_time.MOSCOW_TZ).isoformat(timespec='seconds')


def _row(row) -> Dict[str, Any]:
    out = dict(row)
    for key in ('ask', 'cards'):
        try:
            value = json.loads(out.get(key) or '[]')
        except ValueError:
            value = []
        out[key] = value if isinstance(value, list) else []
    return out


# ------------------------------------------------------------------ страница: вопрос, беседы

def ask(user: Dict[str, Any], question: Any, *, mode: Any = 'answer', fast: Any = False,
        thread_id: Any = None, now: Optional[float] = None) -> Dict[str, Any]:
    """Новый вопрос в очередь. thread_id — продолжить свою беседу, без него — новая беседа."""
    text = str(question if question is not None else '').strip()
    if not text:
        raise WebError('Напишите вопрос')
    if len(text) > QUESTION_MAX:
        raise WebError(f'Вопрос длиннее {QUESTION_MAX} знаков — сократите его')
    if mode not in MODES:
        raise WebError('mode — answer (ответ) или report (Research)')
    if thread_id not in (None, '') and not valid_id(thread_id, 't'):
        raise WebError('Нет такой беседы')
    now = time.time() if now is None else now
    _ensure()
    qid = new_id('q')
    with db.write() as conn:
        if thread_id:
            own = conn.execute('SELECT 1 FROM bot_web_questions WHERE thread_id = ? AND user_id = ? LIMIT 1',
                               (thread_id, int(user['id']))).fetchone()
            if own is None:
                raise WebError('Нет такой беседы')
            busy = conn.execute(f'SELECT COUNT(*) FROM bot_web_questions WHERE thread_id = ? AND status IN '
                                f'({",".join("?" * len(ACTIVE))})', (thread_id, *ACTIVE)).fetchone()[0]
            if busy:
                raise WebError('В этой беседе бот ещё отвечает — дождитесь ответа или остановите его')
        else:
            thread_id = new_id('t')
        active = conn.execute(f'SELECT COUNT(*) FROM bot_web_questions WHERE user_id = ? AND status IN '
                              f'({",".join("?" * len(ACTIVE))})', (int(user['id']), *ACTIVE)).fetchone()[0]
        if active >= ACTIVE_MAX:
            raise WebError(f'Уже идут {active} вопроса — дождитесь ответа хотя бы на один')
        conn.execute('INSERT INTO bot_web_questions (id, thread_id, user_id, login, name, question, mode, fast, '
                     'status, asked_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (qid, thread_id, int(user['id']), str(user.get('login') or ''),
                      str(user.get('display_name') or user.get('login') or ''), text, mode, 1 if fast else 0,
                      'queued', int(now)))
    return get(int(user['id']), qid)


def get(user_id: int, qid: str) -> Optional[Dict[str, Any]]:
    """Вопрос человека — видом для страницы (или None: чужой, удалён, нет такого)."""
    if not valid_id(qid, 'q'):
        return None
    _ensure()
    expire_stale()
    with db.read() as conn:
        row = conn.execute('SELECT * FROM bot_web_questions WHERE id = ? AND user_id = ?',
                           (qid, int(user_id))).fetchone()
    return view(_row(row)) if row else None


def threads(user_id: int, limit: int = THREADS_LIMIT) -> List[Dict[str, Any]]:
    """Беседы человека, свежие сверху: заголовок — первый вопрос, сколько вопросов, идёт ли ответ."""
    _ensure()
    expire_stale()
    with db.read() as conn:
        rows = conn.execute(
            f'''SELECT thread_id, MIN(asked_ts) AS started_ts, MAX(asked_ts) AS last_ts, COUNT(*) AS questions,
                       SUM(status IN ({",".join("?" * len(ACTIVE))})) AS active,
                       SUM(mode = 'report') AS reports, MAX(rowid) AS last_row
                FROM bot_web_questions WHERE user_id = ? GROUP BY thread_id
                ORDER BY last_ts DESC, last_row DESC LIMIT ?''',
            (*ACTIVE, int(user_id), int(limit))).fetchall()
        out = []
        for row in rows:
            first = conn.execute('SELECT question FROM bot_web_questions WHERE thread_id = ? ORDER BY asked_ts, '
                                 'rowid LIMIT 1', (row['thread_id'],)).fetchone()
            title = ' '.join(str(first['question'] if first else '').split())
            out.append({'id': row['thread_id'], 'title': title[:120], 'questions': int(row['questions']),
                        'reports': int(row['reports'] or 0), 'active': bool(row['active']),
                        'started_at': _iso(row['started_ts']), 'last_at': _iso(row['last_ts'])})
    return out


def thread(user_id: int, thread_id: str) -> Optional[Dict[str, Any]]:
    """Беседа целиком: вопросы по порядку с ответами, графиками и отчётами."""
    if not valid_id(thread_id, 't'):
        return None
    _ensure()
    expire_stale()
    with db.read() as conn:
        rows = conn.execute('SELECT * FROM bot_web_questions WHERE thread_id = ? AND user_id = ? '
                            'ORDER BY asked_ts, rowid', (thread_id, int(user_id))).fetchall()
    if not rows:
        return None
    return {'id': thread_id, 'questions': [view(_row(r)) for r in rows]}


def stop(user_id: int, qid: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """«Остановить»: вопрос в очереди — сразу закрыт; в работе — сервер бота узнает при следующем
    отчёте о ходе работы (раз в несколько секунд) и остановится, как в Telegram."""
    if not valid_id(qid, 'q'):
        return None
    now = time.time() if now is None else now
    _ensure()
    with db.write() as conn:
        row = conn.execute('SELECT status FROM bot_web_questions WHERE id = ? AND user_id = ?',
                           (qid, int(user_id))).fetchone()
        if row is None:
            return None
        if row['status'] == 'queued':
            conn.execute("UPDATE bot_web_questions SET status = 'stopped', shown = ?, error = 'stopped', "
                         "finished_ts = ?, progress = '' WHERE id = ?", (STOPPED_TEXT, int(now), qid))
        elif row['status'] in ('taken', 'running'):
            conn.execute('UPDATE bot_web_questions SET stop = 1 WHERE id = ?', (qid,))
    return get(user_id, qid)


def delete_thread(user_id: int, thread_id: str) -> bool:
    """Удалить беседу целиком (кнопка на странице). Идущий в ней ответ сервер бота доведёт до конца,
    но сохранить его будет некуда."""
    if not valid_id(thread_id, 't'):
        return False
    _ensure()
    with db.write() as conn:
        return conn.execute('DELETE FROM bot_web_questions WHERE thread_id = ? AND user_id = ?',
                            (thread_id, int(user_id))).rowcount > 0


_expired_at = 0.0                                  # последняя проверка молчания — не чаще EXPIRE_EVERY_S
EXPIRE_EVERY_S = 10


def expire_stale(now: Optional[float] = None, force: bool = False) -> int:
    """Вопросы, по которым сервер бота молчит дольше STALE_S, — ошибкой: страница не ждёт вечно.
    Страница опрашивает вопрос раз в 2 секунды — проверка не чаще раза в EXPIRE_EVERY_S."""
    global _expired_at
    now = time.time() if now is None else now
    if not force and 0 <= now - _expired_at < EXPIRE_EVERY_S:
        return 0
    _expired_at = now
    _ensure()
    with db.write() as conn:
        return conn.execute("UPDATE bot_web_questions SET status = 'error', error = 'stale', shown = ?, "
                            "progress = '', finished_ts = ? WHERE status IN ('taken', 'running') AND "
                            "COALESCE(beat_ts, taken_ts, asked_ts) < ?",
                            (STALE_TEXT, int(now), int(now - STALE_S))).rowcount


# ------------------------------------------------------------------ вид для страницы

def cost_line(usd: float, steps: int, fast_steps: int = 0) -> str:
    """Та же строка цены, что в Telegram (kultura_bot/engine/service.cost_line)."""
    fast = f'; в быстром режиме — {fast_steps}, цена ×2' if fast_steps else ''
    return f'Ответ обошёлся в ${usd:.2f} (запросов к модели: {steps}{fast}).'


def _card_view(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from kultura_bot.charts import reports
    from kultura_bot.engine import formatting
    if card.get('kind') == 'chart' and isinstance(card.get('spec'), dict):
        return {'kind': 'chart', 'id': card.get('id'), 'spec': card['spec'],
                'caption_html': formatting.to_html(card.get('caption') or ''),
                'how_html': formatting.to_html(card['how']) if card.get('how') else '',
                'ask': list(card.get('ask') or [])}
    if card.get('kind') == 'report' and isinstance(card.get('body'), dict):
        record = {'id': card.get('id') or '', 'body': card['body'], 'created_at': card.get('created_at') or ''}
        alive = bool(card.get('id')) and reports.get(card['id']) is not None
        return {'kind': 'report', 'id': card.get('id'), 'view': reports.view(record),
                'page': f'/tg/report/{card["id"]}' if alive else None, 'ask': list(card.get('ask') or [])}
    return None


def view(row: Dict[str, Any]) -> Dict[str, Any]:
    """Строка таблицы -> то, что рисует страница: Markdown переведён в HTML (только своя разметка)."""
    from kultura_bot.engine import formatting
    active = row['status'] in ACTIVE
    cards = [c for c in (_card_view(card) for card in row['cards']) if c is not None]
    done = row['status'] in FINAL
    return {
        'id': row['id'], 'thread_id': row['thread_id'], 'question': row['question'], 'mode': row['mode'],
        'fast': bool(row['fast']), 'status': row['status'], 'active': active,
        'asked_at': _iso(row['asked_ts']), 'finished_at': _iso(row.get('finished_ts')),
        'progress': row['progress'] if active else '', 'stopping': bool(row['stop']) and active,
        'answer_html': formatting.to_html(row['answer']) if row['answer'] else '',
        'how_html': formatting.to_html(row['how']) if row['how'] else '',
        'notice': row['notice'], 'ask': row['ask'], 'cards': cards, 'shown': row['shown'],
        'cost': ({'usd': round(float(row['cost_usd']), 4), 'steps': int(row['steps']),
                  'fast_steps': int(row['fast_steps']),
                  'line': cost_line(float(row['cost_usd']), int(row['steps']), int(row['fast_steps']))}
                 if done and int(row['steps']) else None),
    }


# ------------------------------------------------------------------ сервер бота

def _history(conn, thread_id: str, before_ts: int) -> List[Dict[str, Any]]:
    """Прошлые ответы беседы коротко — серверу бота, если его диалог начат заново (простой, новые
    инструкции): иначе продолжение беседы на сайте потеряло бы смысл."""
    rows = conn.execute("SELECT * FROM bot_web_questions WHERE thread_id = ? AND asked_ts <= ? AND status = 'done' "
                        'ORDER BY asked_ts DESC, rowid DESC LIMIT ?',
                        (thread_id, int(before_ts), HISTORY_QUESTIONS)).fetchall()
    from kultura_bot.charts import reports as report_store
    out = []
    items = [_row(row) for row in reversed(rows)]
    for index, item in enumerate(items):
        answer = item['answer'][:HISTORY_ANSWER_MAX]
        cards = [c for c in item['cards'] if c.get('kind') == 'report' and isinstance(c.get('body'), dict)]
        charts = [c for c in item['cards'] if c.get('kind') == 'chart']
        entry = {'question': item['question'], 'mode': item['mode'], 'answer': answer,
                 'reports': [{'title': c['body'].get('title', ''),
                              'summary': str(c['body'].get('summary', ''))[:HISTORY_ANSWER_MAX]} for c in cards],
                 'charts': [{'title': str((c.get('spec') or {}).get('title') or ''),
                             'caption': str(c.get('caption') or '')[:1000]} for c in charts]}
        if cards and index == len(items) - 1:
            # Последний отчёт беседы — целиком текстом (как ответ на отчёт в Telegram): «добавь октябрь»
            # к нему — новая версия отчёта, а не сбор с нуля.
            last = cards[-1]
            text = report_store.report_context({'id': last.get('id') or '', 'body': last['body'],
                                                'created_at': last.get('created_at') or ''})
            entry['report_text'] = text[:report_store.REPLY_CONTEXT_MAX]
        out.append(entry)
    return out


def _is_admin(user_id: int) -> Optional[Dict[str, Any]]:
    from core.auth_manager import get_auth_manager
    try:
        user = get_auth_manager().get_by_id(int(user_id))
    except Exception:  # noqa: BLE001 — база пользователей недоступна: вопрос подождёт
        return None
    return user if user and user.get('active') and user.get('is_admin') else None


def claim(now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Следующий вопрос серверу бота (самый старый, из беседы, где сейчас ничего не идёт) -> taken.
    Права спросившего — ещё раз: пока вопрос ждал, админство могли снять."""
    now = time.time() if now is None else now
    _ensure()
    expire_stale(now, force=True)
    for _attempt in range(5):
        with db.read() as conn:
            row = conn.execute(
                f'''SELECT * FROM bot_web_questions q WHERE status = 'queued' AND stop = 0 AND NOT EXISTS (
                        SELECT 1 FROM bot_web_questions r WHERE r.thread_id = q.thread_id
                        AND r.status IN ('taken', 'running'))
                    ORDER BY asked_ts, rowid LIMIT 1''').fetchone()
        if row is None:
            return None
        user = _is_admin(row['user_id'])
        with db.write() as conn:
            if user is None:
                conn.execute("UPDATE bot_web_questions SET status = 'error', error = 'no access', shown = ?, "
                             "finished_ts = ? WHERE id = ? AND status = 'queued'", (NO_ACCESS_TEXT, int(now), row['id']))
                continue
            taken = conn.execute("UPDATE bot_web_questions SET status = 'taken', taken_ts = ?, beat_ts = ? "
                                 "WHERE id = ? AND status = 'queued' AND stop = 0",
                                 (int(now), int(now), row['id'])).rowcount
            if not taken:
                continue                                 # «Остановить» или другой поток успели раньше
            history = _history(conn, row['thread_id'], row['asked_ts'])
        return {
            'id': row['id'], 'thread_id': row['thread_id'], 'chat_id': chat_id(row['thread_id']),
            'question': row['question'], 'mode': row['mode'], 'fast': bool(row['fast']),
            'asked_at': _iso(row['asked_ts']), 'asked_ts': int(row['asked_ts']),
            'actor': {'user_id': int(user['id']), 'login': str(user.get('login') or row['login']),
                      'display_name': str(user.get('display_name') or user.get('login') or row['name'])},
            'history': history,
        }
    return None


def _engine_row(conn, qid: str):
    if not valid_id(qid, 'q'):
        raise WebError('id вопроса — q и 16 знаков')
    row = conn.execute('SELECT * FROM bot_web_questions WHERE id = ?', (qid,)).fetchone()
    if row is None:
        raise WebError('Вопроса нет: беседу удалили')
    return row


def beat(qid: str, progress: Any, now: Optional[float] = None) -> Dict[str, Any]:
    """Сервер бота работает над вопросом: строка хода работы -> страница. Ответ: {stop} — нажали
    «Остановить» или вопрос уже закрыт (удалён, закрыт по молчанию) — дальше работать незачем."""
    now = time.time() if now is None else now
    _ensure()
    with db.write() as conn:
        try:
            row = _engine_row(conn, qid)
        except WebError:
            return {'stop': True, 'gone': True}
        if row['status'] not in ('taken', 'running'):
            return {'stop': True, 'gone': True}
        conn.execute("UPDATE bot_web_questions SET status = 'running', beat_ts = ?, progress = ? WHERE id = ?",
                     (int(now), str(progress or '')[:PROGRESS_MAX], qid))
        return {'stop': bool(row['stop']), 'gone': False}


def _ask_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = ' '.join(str(item or '').split())[:ASK_TEXT_MAX]
        if text and text not in out:
            out.append(text)
    return out[:ASK_MAX]


def _markdown(value: Any, limit: int, where: str) -> str:
    if value is None:
        return ''
    if not isinstance(value, str):
        raise WebError(f'{where} — текст')
    if len(value) > limit:
        raise WebError(f'{where} длиннее {limit} знаков')
    return value


def _tool_result(payload: Any, is_error: bool = False) -> Dict[str, Any]:
    """Ответ в виде ответа инструмента MCP — сервер бота отдаёт его модели как есть."""
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {'content': [{'type': 'text', 'text': text}], 'isError': bool(is_error)}


def add_card(qid: str, tool: str, args: Any, *, token_id: str = '', text_filter: Optional[TextFilter] = None,
             page_filter: Optional[TextFilter] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """График (common_chart_send) или отчёт (common_report_send) вопроса с сайта: проверка — та же, что у
    отправки в Telegram (spec.normalize, reports.normalize_report), но в Telegram ничего не уходит —
    карточка ложится в вопрос и рисуется страницей. Вернуть ответ инструмента: ошибку проверки модель
    исправит, как в Telegram. Пределы картинки Telegram (подпись до 1024 знаков) здесь не действуют."""
    from kultura_bot import links, settings
    from kultura_bot.charts import reports, spec as chart_spec
    from kultura_bot.engine import formatting
    if tool not in (CHART_TOOL, REPORT_TOOL):
        raise WebError(f'tool — {CHART_TOOL} или {REPORT_TOOL}')
    if not isinstance(args, dict):
        raise WebError('args — объект JSON')
    now = time.time() if now is None else now
    _ensure()
    with db.read() as conn:
        row = _row(_engine_row(conn, qid))
    if row['status'] not in ('taken', 'running'):
        return _tool_result('Вопрос уже закрыт (остановлен или удалён) — отправлять некуда.', True)
    if len(row['cards']) >= CARDS_MAX:
        return _tool_result(f'Не больше {CARDS_MAX} графиков и отчётов в одном ответе.', True)
    created = _iso(now)
    try:
        if tool == CHART_TOOL:
            try:
                spec = chart_spec.normalize(args.get('chart'), text_filter=text_filter)
            except chart_spec.ChartSpecError as exc:
                return _tool_result(f'Описание графика: {exc}', True)
            caption = _markdown(args.get('caption'), CAPTION_MAX, 'caption')
            how = _markdown(args.get('how'), CARD_HOW_MAX, 'how')
            if text_filter is not None and caption:
                caption = text_filter(caption)
            if page_filter is not None and how:
                how = page_filter(how)
            caption, cut_how = formatting.split_how(caption)
            caption, ask = formatting.split_buttons(caption)
            how = '\n\n'.join(part for part in (how, cut_how) if part and part.strip())
            card = {'kind': 'chart', 'id': new_id('c'), 'spec': spec, 'caption': caption or spec['title'],
                    'how': how, 'ask': _ask_list(ask), 'created_at': created}
            result = {'chart_id': card['id'], 'format': 'web',
                      'shown': 'на странице вопроса на сайте (kultura.research): интерактивно, с подписью'}
        else:
            try:
                body = reports.normalize_report(args.get('report'), text_filter=text_filter, page_filter=page_filter)
            except reports.ReportError as exc:
                return _tool_result(f'Отчёт: {exc}', True)
            summary, cut_how = formatting.split_how(body['summary'])
            if cut_how:
                body['summary'] = summary or body['title']
                extra = page_filter(cut_how) if page_filter else cut_how
                body['how'] = '\n\n'.join(part for part in (body['how'], extra) if part and part.strip())
            summary, ask = formatting.split_buttons(body['summary'])
            if ask:
                body['summary'] = summary or body['title']
            try:
                record = reports.create(body, chat_id=chat_id(row['thread_id']), token_id=token_id,
                                        daily_limit=settings.REPORT_DAILY_LIMIT)
            except reports.ReportLimitError as exc:
                return _tool_result(f'Лимит: не больше {settings.REPORT_DAILY_LIMIT} записок и отчётов в сутки — '
                                    f'сегодня уже {exc.used}.', True)
            card = {'kind': 'report', 'id': record['id'], 'body': body, 'ask': _ask_list(ask), 'created_at': created}
            result = {'report_id': record['id'], 'url': links.site_page(record['id']), 'format': 'web',
                      'sections': len(body['sections']), 'shown': 'на странице вопроса на сайте (kultura.research)'}
    except WebError as exc:
        return _tool_result(str(exc), True)
    with db.write() as conn:
        fresh = conn.execute('SELECT cards FROM bot_web_questions WHERE id = ?', (qid,)).fetchone()
        if fresh is None:
            return _tool_result('Вопрос удалён — отправлять некуда.', True)
        cards = _row({'cards': fresh['cards'], 'ask': '[]'})['cards']
        cards.append(card)
        conn.execute('UPDATE bot_web_questions SET cards = ?, beat_ts = ? WHERE id = ?',
                     (json.dumps(cards, ensure_ascii=False, separators=(',', ':')), int(now), qid))
    return _tool_result(result)


def _number(value: Any, cast=float, high: float = 1e9):
    try:
        number = cast(value)
    except (TypeError, ValueError):
        return cast(0)
    if number != number:                          # NaN
        return cast(0)
    return cast(min(max(number, 0), high))


def finish(qid: str, data: Any, now: Optional[float] = None) -> Dict[str, Any]:
    """Итог вопроса от сервера бота: ответ (Markdown), «Как считается», пометка, кнопки следующего шага,
    что увидел человек при ошибке, расход. Вопрос, закрытый по молчанию (stale), принимает итог —
    настоящий ответ важнее ошибки ожидания."""
    if not isinstance(data, dict):
        raise WebError('Итог — объект JSON')
    status = str(data.get('status') or '')
    if status not in FINAL:
        raise WebError(f'status — один из {list(FINAL)}')
    now = time.time() if now is None else now
    _ensure()
    with db.write() as conn:
        row = _engine_row(conn, qid)
        if row['status'] in FINAL and row['error'] != 'stale':
            return {'ok': False, 'status': row['status']}
        conn.execute(
            'UPDATE bot_web_questions SET status = ?, answer = ?, how = ?, notice = ?, ask = ?, shown = ?, error = ?, '
            "cost_usd = ?, steps = ?, fast_steps = ?, finished_ts = ?, progress = '' WHERE id = ?",
            (status, str(data.get('answer') or '')[:ANSWER_MAX], str(data.get('how') or '')[:HOW_MAX],
             str(data.get('notice') or '')[:NOTICE_MAX],
             json.dumps(_ask_list(data.get('ask')), ensure_ascii=False),
             str(data.get('shown') or '')[:SHOWN_MAX], str(data.get('error') or '')[:ERROR_MAX],
             _number(data.get('cost_usd'), float, 10_000), _number(data.get('steps'), int, 100_000),
             _number(data.get('fast_steps'), int, 100_000), int(now), qid))
    return {'ok': True, 'status': status}


def engine_state(now: Optional[float] = None) -> Dict[str, Any]:
    """Отвечает ли сейчас сервер бота — для строки над полем вопроса: на паузе, не на связи, нет ключа."""
    from kultura_bot import credentials, site_api, store
    now = time.time() if now is None else now
    if credentials.paused():
        return {'ok': False, 'text': 'Бот на паузе (страница «Доступ агентов»): вопрос подождёт в очереди.'}
    if not credentials.anthropic_key():
        return {'ok': False, 'text': 'Нет ключа Claude API (страница «Доступ агентов»): вопрос подождёт в очереди.'}
    status = store.get_status()
    at_ts = float(status.get('at_ts') or 0)
    if status.get('state') in (None, 'stopped') or not at_ts or now - at_ts > site_api.STALE_AFTER_S:
        return {'ok': False, 'text': 'Сервер бота не на связи: вопрос подождёт в очереди и уйдёт, когда он вернётся.'}
    return {'ok': True, 'text': ''}

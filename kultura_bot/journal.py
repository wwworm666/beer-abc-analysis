"""Журнал вопросов и ответов бота @MCPkulturabot на сайте (mcp.db), решение владельца 2026-11-06.

## Что это

«Мы храним все запросы и ответы?» — «Да, давай подготовим к выпуску в прод»: каждый вопрос боту,
его ответ, кто спросил, расход, вызовы инструментов, ошибки и реакция человека — чтобы разбирать,
где бот ошибается. Запись собирает сервер бота (kultura_bot/engine/journal.py) и присылает
пачками (POST /api/bot/journal); здесь она хранится JOURNAL_KEEP_DAYS дней и показывается
администраторам на странице /admin/bot/journal (routes/bot_journal.py) и агентам владельца
инструментом common_bot_journal.

## Таблицы

    bot_journal           запись на вопрос: uid (PK, uuid4 сервера бота), asked_at / asked_ts (когда
                          пришёл, МСК и unix), чат и кто спросил (chat_id, chat_type, tg_user_id,
                          login, name), mode, source, status, question, answer, cost_usd, seconds,
                          steps, tool_calls, format, rating (good | bad | other | ''), feedback
                          (JSON: tg_user_id -> {reactions, at}), search (вопрос и ответ в нижнем
                          регистре — поиск по-русски без учёта регистра), payload (запись целиком,
                          JSON), received_ts
    bot_journal_messages  chat_id + message_id (PK) -> uid: по реакции на сообщение бота найти запись

Сервер бота шлёт ту же запись повторно, если не дождался ответа сайта, — по uid она заменяется,
оценка (feedback, rating) сохраняется. Записи старше JOURNAL_KEEP_DAYS удаляются при каждом приёме.

## Оценка реакцией

Человек ставит реакцию под сообщением бота (Telegram присылает её серверу бота, тот — сюда):
хоть одна плохая (палец вниз, гнев, слёзы, тошнота, клоун, зевота…) — rating «bad»; иначе
хоть одна хорошая (палец вверх, сердце, огонь, аплодисменты…) — «good»; иначе «other». Наборы
— BAD_REACTIONS и GOOD_REACTIONS (кодами Unicode: в коде проекта эмодзи не пишем).
"""
import csv
import io
import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core import msk_time
from core.mcp import db

STATUSES = ('done', 'error', 'stopped', 'budget')
STATUS_FILTERS = STATUSES + ('problems',)        # problems — всё, кроме done
RATINGS = ('good', 'bad', 'other')
MODES = ('answer', 'report')
SOURCES = ('message', 'button', 'menu', 'web')   # menu — вопрос кнопкой из меню раздела (2026-11-06);
#                                                 web — вопрос со страницы сайта /research (2026-11-09)
FORMATS = ('', 'rich', 'plain', 'web')
UID_RE = re.compile(r'[0-9a-f]{32}')
CHAT_RE = re.compile(r'-?\d{1,21}|web:t[A-Za-z0-9_-]{16}')     # web:<беседа> — вопросы со страницы сайта

BATCH_MAX = 50              # записей в одном запросе сервера бота
QUESTION_MAX = 8000
ANSWER_MAX = 40000
PAYLOAD_MAX = 200_000       # запись целиком (JSON); больше — без списка вызовов и карточек
SEARCH_MAX = 50_000
LIST_MAX = 200              # строк в одной выдаче списка
CSV_MAX = 5000
PREVIEW = 300

# Реакции (Telegram ReactionTypeEmoji). Вариант-селектор U+FE0F отбрасывается перед сравнением.
GOOD_REACTIONS = frozenset({
    '\U0001F44D',   # палец вверх
    '❤',       # сердце
    '\U0001F525',   # огонь
    '\U0001F44F',   # аплодисменты
    '\U0001F44C',   # «окей»
    '\U0001F64F',   # спасибо
    '\U0001F389',   # хлопушка
    '\U0001F929',   # звёзды в глазах
    '\U0001F60D',   # влюблённые глаза
    '\U0001F970',   # сердечки
    '\U0001F4AF',   # сто
    '\U0001F3C6',   # кубок
    '⚡',       # молния
    '\U0001F91D',   # рукопожатие
})
BAD_REACTIONS = frozenset({
    '\U0001F44E',   # палец вниз
    '\U0001F92C',   # ругательство
    '\U0001F621',   # гнев
    '\U0001F622',   # слеза
    '\U0001F62D',   # рыдание
    '\U0001F92E',   # тошнота
    '\U0001F4A9',   # куча
    '\U0001F921',   # клоун
    '\U0001F971',   # зевота
    '\U0001F612',   # недовольство
})

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS bot_journal (
        uid         TEXT PRIMARY KEY,
        asked_at    TEXT NOT NULL,
        asked_ts    INTEGER NOT NULL,
        chat_id     TEXT NOT NULL,
        chat_type   TEXT NOT NULL DEFAULT '',
        tg_user_id  TEXT NOT NULL DEFAULT '',
        login       TEXT NOT NULL DEFAULT '',
        name        TEXT NOT NULL DEFAULT '',
        mode        TEXT NOT NULL DEFAULT 'answer',
        source      TEXT NOT NULL DEFAULT 'message',
        status      TEXT NOT NULL,
        question    TEXT NOT NULL DEFAULT '',
        answer      TEXT NOT NULL DEFAULT '',
        cost_usd    REAL NOT NULL DEFAULT 0,
        seconds     REAL NOT NULL DEFAULT 0,
        steps       INTEGER NOT NULL DEFAULT 0,
        tool_calls  INTEGER NOT NULL DEFAULT 0,
        format      TEXT NOT NULL DEFAULT '',
        rating      TEXT NOT NULL DEFAULT '',
        feedback    TEXT NOT NULL DEFAULT '{}',
        search      TEXT NOT NULL DEFAULT '',
        payload     TEXT NOT NULL,
        received_ts INTEGER NOT NULL
    )''',
    'CREATE INDEX IF NOT EXISTS idx_bot_journal_asked ON bot_journal(asked_ts)',
    'CREATE INDEX IF NOT EXISTS idx_bot_journal_login ON bot_journal(login, asked_ts)',
    '''CREATE TABLE IF NOT EXISTS bot_journal_messages (
        chat_id    TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        uid        TEXT NOT NULL,
        PRIMARY KEY (chat_id, message_id)
    )''',
    'CREATE INDEX IF NOT EXISTS idx_bot_journal_messages_uid ON bot_journal_messages(uid)',
)


class JournalError(ValueError):
    """Запись или фильтр не прошли проверку: текст — для сервера бота или страницы."""


def _ensure() -> None:
    db.ensure_schema('bot_journal', SCHEMA)


def keep_days() -> int:
    from kultura_bot import settings
    return max(1, int(settings.JOURNAL_KEEP_DAYS))


# ------------------------------------------------------------------ приём записей

def _text(value: Any, limit: int) -> str:
    return str(value if value is not None else '')[:limit]


def _number(value: Any, cast=float, low: float = 0, high: float = 1e9):
    try:
        number = cast(value)
    except (TypeError, ValueError):
        return cast(0)
    if number != number:                          # NaN
        return cast(0)
    return cast(min(max(number, low), high))


def _asked_ts(value: Any) -> Tuple[str, int]:
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise JournalError('asked_at: нужна дата ISO 8601') from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=msk_time.MOSCOW_TZ)
    return moment.isoformat(timespec='seconds'), int(moment.timestamp())


def normalize(raw: Any) -> Dict[str, Any]:
    """Запись сервера бота -> строка таблицы. Ошибка — JournalError (запись отвергается, остальные — нет)."""
    if not isinstance(raw, dict):
        raise JournalError('запись — объект JSON')
    uid = str(raw.get('uid') or '')
    if not UID_RE.fullmatch(uid):
        raise JournalError('uid — 32 шестнадцатеричных знака')
    chat_id = str(raw.get('chat_id') or '')
    if not CHAT_RE.fullmatch(chat_id):
        raise JournalError('chat_id — число')
    status = str(raw.get('status') or '')
    if status not in STATUSES:
        raise JournalError(f'status — один из {list(STATUSES)}')
    asked_at, asked_ts = _asked_ts(raw.get('asked_at'))
    question = _text(raw.get('question'), QUESTION_MAX)
    answer = _text(raw.get('answer'), ANSWER_MAX)
    payload = dict(raw, question=question, answer=answer)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > PAYLOAD_MAX:
        payload['calls'] = payload.get('calls', [])[:20] if isinstance(payload.get('calls'), list) else []
        payload['cards'] = []
        payload['trimmed'] = True
        text = json.dumps(payload, ensure_ascii=False)[:PAYLOAD_MAX]
        try:
            json.loads(text)
        except ValueError:
            text = json.dumps({k: payload[k] for k in payload if k not in ('calls', 'cards', 'answer')} |
                              {'answer': answer[:5000], 'trimmed': True}, ensure_ascii=False)
    messages = [m for m in raw.get('messages') or [] if isinstance(m, int) and not isinstance(m, bool) and m > 0]
    return {
        'uid': uid, 'asked_at': asked_at, 'asked_ts': asked_ts, 'chat_id': chat_id,
        'chat_type': _text(raw.get('chat_type'), 20), 'tg_user_id': _text(raw.get('tg_user_id'), 21),
        'login': _text(raw.get('login'), 64), 'name': _text(raw.get('name'), 120),
        'mode': raw.get('mode') if raw.get('mode') in MODES else 'answer',
        'source': raw.get('source') if raw.get('source') in SOURCES else 'message',
        'status': status, 'question': question, 'answer': answer,
        'cost_usd': _number(raw.get('cost_usd'), float, 0, 10_000),
        'seconds': _number(raw.get('seconds'), float, 0, 86_400),
        'steps': _number(raw.get('steps'), int, 0, 100_000),
        'tool_calls': _number(raw.get('tool_calls'), int, 0, 100_000),
        'format': raw.get('format') if raw.get('format') in FORMATS else '',
        'search': f'{question}\n{answer}'.casefold()[:SEARCH_MAX],
        'payload': text, 'messages': messages[:50],
    }


def save(records: Any, now: Optional[float] = None) -> Dict[str, Any]:
    """Пачка записей сервера бота -> {saved: [uid], rejected: [{uid, error}]}. Оценка у повторно
    присланной записи сохраняется; старше JOURNAL_KEEP_DAYS — удаляются."""
    if not isinstance(records, list):
        raise JournalError('records — список')
    if len(records) > BATCH_MAX:
        raise JournalError(f'не больше {BATCH_MAX} записей за раз')
    now = time.time() if now is None else now
    rows, rejected = [], []
    for raw in records:
        try:
            rows.append(normalize(raw))
        except JournalError as exc:
            uid = raw.get('uid') if isinstance(raw, dict) else None
            rejected.append({'uid': str(uid or '')[:40], 'error': str(exc)})
    _ensure()
    columns = ('uid', 'asked_at', 'asked_ts', 'chat_id', 'chat_type', 'tg_user_id', 'login', 'name', 'mode',
               'source', 'status', 'question', 'answer', 'cost_usd', 'seconds', 'steps', 'tool_calls', 'format',
               'search', 'payload')
    updates = ', '.join(f'{c} = excluded.{c}' for c in columns if c != 'uid')
    with db.write() as conn:
        for row in rows:
            conn.execute(f'INSERT INTO bot_journal ({", ".join(columns)}, received_ts) '
                         f'VALUES ({", ".join("?" for _ in columns)}, ?) '
                         f'ON CONFLICT(uid) DO UPDATE SET {updates}, received_ts = excluded.received_ts',
                         tuple(row[c] for c in columns) + (int(now),))
            for message_id in row['messages']:
                conn.execute('INSERT OR REPLACE INTO bot_journal_messages (chat_id, message_id, uid) VALUES (?, ?, ?)',
                             (row['chat_id'], message_id, row['uid']))
        cutoff = int(now) - keep_days() * 86400
        old = [r['uid'] for r in conn.execute('SELECT uid FROM bot_journal WHERE asked_ts < ?', (cutoff,))]
        for uid in old:
            conn.execute('DELETE FROM bot_journal_messages WHERE uid = ?', (uid,))
        conn.execute('DELETE FROM bot_journal WHERE asked_ts < ?', (cutoff,))
    return {'saved': [r['uid'] for r in rows], 'rejected': rejected}


# ------------------------------------------------------------------ оценка реакцией

def _clean(emoji: str) -> str:
    return str(emoji or '').replace('️', '')


def rating_of(feedback: Dict[str, Any]) -> str:
    reactions = [_clean(r) for item in feedback.values() if isinstance(item, dict)
                 for r in item.get('reactions') or []]
    if any(r in BAD_REACTIONS for r in reactions):
        return 'bad'
    if any(r in GOOD_REACTIONS for r in reactions):
        return 'good'
    return 'other' if reactions else ''


def set_feedback(chat_id: str, message_id: int, tg_user_id: str, reactions: Any,
                 now: Optional[float] = None) -> bool:
    """Реакция на сообщение бота -> оценка записи. False — сообщение не из журнала (или срок вышел)."""
    if not CHAT_RE.fullmatch(str(chat_id or '')) or not isinstance(message_id, int) or isinstance(message_id, bool):
        raise JournalError('chat_id и message_id — числа')
    if not isinstance(reactions, list):
        raise JournalError('reactions — список')
    reactions = [str(r)[:16] for r in reactions if isinstance(r, str) and r][:10]
    _ensure()
    with db.write() as conn:
        row = conn.execute('SELECT j.uid, j.feedback FROM bot_journal_messages m JOIN bot_journal j ON j.uid = m.uid '
                           'WHERE m.chat_id = ? AND m.message_id = ?', (str(chat_id), int(message_id))).fetchone()
        if row is None:
            return False
        try:
            feedback = json.loads(row['feedback'] or '{}')
        except ValueError:
            feedback = {}
        if not isinstance(feedback, dict):
            feedback = {}
        key = str(tg_user_id or '')[:21] or 'anon'
        if reactions:
            moment = msk_time.now() if now is None else datetime.fromtimestamp(now, msk_time.MOSCOW_TZ)
            feedback[key] = {'reactions': reactions, 'at': moment.isoformat(timespec='seconds')}
        else:
            feedback.pop(key, None)
        conn.execute('UPDATE bot_journal SET feedback = ?, rating = ? WHERE uid = ?',
                     (json.dumps(feedback, ensure_ascii=False), rating_of(feedback), row['uid']))
    return True


# ------------------------------------------------------------------ выборка для страницы и агента

def _filters(args: Dict[str, Any], now: Optional[float] = None,
             only_login: Optional[str] = None) -> Tuple[str, List[Any], Dict[str, Any]]:
    """Фильтры страницы и агента -> (WHERE, параметры, что применено). Неверное — JournalError.
    only_login — чьи записи вообще можно видеть (свои: решение владельца 2026-11-09 «история у каждого
    своя»); фильтр login его не расширяет."""
    now = time.time() if now is None else now
    try:
        days = int(args.get('days') or 30)
    except (TypeError, ValueError):
        raise JournalError('days — число дней') from None
    days = min(max(days, 1), 3650)
    where, params = ['asked_ts >= ?'], [int(now) - days * 86400]
    applied: Dict[str, Any] = {'days': days}
    login = str(args.get('login') or '').strip()
    if only_login is not None:
        where.append("login = ? AND login != ''")          # без логина — ничего: записи без логина ничьи
        params.append(str(only_login)[:64])
        applied['login'] = str(only_login)[:64]
    elif login:
        where.append('login = ?')
        params.append(login[:64])
        applied['login'] = login[:64]
    status = str(args.get('status') or '').strip()
    if status:
        if status not in STATUS_FILTERS:
            raise JournalError(f'status — один из {list(STATUS_FILTERS)}')
        if status == 'problems':
            where.append("status != 'done'")
        else:
            where.append('status = ?')
            params.append(status)
        applied['status'] = status
    rating = str(args.get('rating') or '').strip()
    if rating:
        if rating not in RATINGS:
            raise JournalError(f'rating — один из {list(RATINGS)}')
        where.append('rating = ?')
        params.append(rating)
        applied['rating'] = rating
    query = str(args.get('q') or '').strip()
    if query:
        needle = query.casefold()[:200].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        where.append("search LIKE ? ESCAPE '\\'")
        params.append(f'%{needle}%')
        applied['q'] = query[:200]
    return ' AND '.join(where), params, applied


def _summary(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        payload = json.loads(row['payload'])
    except ValueError:
        payload = {}
    try:
        feedback = json.loads(row['feedback'] or '{}')
    except ValueError:
        feedback = {}
    calls = payload.get('calls') if isinstance(payload.get('calls'), list) else []
    return {
        'uid': row['uid'], 'asked_at': row['asked_at'], 'login': row['login'], 'name': row['name'],
        'chat_type': row['chat_type'], 'mode': row['mode'], 'source': row['source'], 'status': row['status'],
        'question': row['question'][:PREVIEW], 'answer': row['answer'][:PREVIEW],
        'cost_usd': round(row['cost_usd'], 4), 'seconds': row['seconds'], 'steps': row['steps'],
        'tool_calls': row['tool_calls'], 'format': row['format'], 'rating': row['rating'],
        'reactions': sorted({r for item in feedback.values() if isinstance(item, dict)
                             for r in item.get('reactions') or []}),
        'cards': len(payload.get('cards') or []) if isinstance(payload.get('cards'), list) else 0,
        'failed_calls': sum(1 for c in calls if isinstance(c, dict) and not c.get('ok')),
        'error': str(payload.get('error') or '')[:PREVIEW],
    }


def query(args: Optional[Dict[str, Any]] = None, now: Optional[float] = None,
          only_login: Optional[str] = None) -> Dict[str, Any]:
    """Список записей (новые сверху) с итогами за выбранное и списком людей для фильтра.
    only_login — только записи этого человека (и в списке людей — только он)."""
    args = args or {}
    where, params, applied = _filters(args, now, only_login)
    try:
        limit = min(max(int(args.get('limit') or 50), 1), LIST_MAX)
        offset = max(int(args.get('offset') or 0), 0)
    except (TypeError, ValueError):
        raise JournalError('limit и offset — числа') from None
    _ensure()
    with db.read() as conn:
        rows = [dict(r) for r in conn.execute(
            f'SELECT * FROM bot_journal WHERE {where} ORDER BY asked_ts DESC, uid LIMIT ? OFFSET ?',
            params + [limit, offset])]
        totals = dict(conn.execute(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS cost, COALESCE(AVG(seconds), 0) AS seconds, "
            f"SUM(status = 'done') AS done, SUM(status = 'error') AS errors, SUM(status = 'stopped') AS stopped, "
            f"SUM(status = 'budget') AS budget, SUM(rating = 'bad') AS bad, SUM(rating = 'good') AS good "
            f"FROM bot_journal WHERE {where}", params).fetchone())
        own = '' if only_login is None else ' AND login = ?'
        people = [dict(r) for r in conn.execute(
            'SELECT login, MAX(name) AS name, COUNT(*) AS n FROM bot_journal WHERE asked_ts >= ? AND login != \'\''
            f'{own} GROUP BY login ORDER BY n DESC', (params[0],) + (() if only_login is None else (str(only_login),)))]
    stats = {
        'count': int(totals['n'] or 0), 'done': int(totals['done'] or 0), 'errors': int(totals['errors'] or 0),
        'stopped': int(totals['stopped'] or 0), 'budget': int(totals['budget'] or 0),
        'bad': int(totals['bad'] or 0), 'good': int(totals['good'] or 0),
        'cost_usd': round(float(totals['cost'] or 0), 2), 'avg_seconds': round(float(totals['seconds'] or 0), 1),
    }
    return {'filters': applied, 'stats': stats, 'people': people, 'keep_days': keep_days(),
            'limit': limit, 'offset': offset, 'items': [_summary(r) for r in rows]}


def get(uid: str, only_login: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Запись целиком: всё, что прислал сервер бота, и оценки людей. only_login — только своя
    (чужая — как будто её нет)."""
    if not UID_RE.fullmatch(str(uid or '')):
        return None
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT * FROM bot_journal WHERE uid = ?', (uid,)).fetchone()
    if row is None or (only_login is not None and row['login'] != str(only_login)):
        return None
    row = dict(row)
    try:
        record = json.loads(row['payload'])
    except ValueError:
        record = {}
    try:
        feedback = json.loads(row['feedback'] or '{}')
    except ValueError:
        feedback = {}
    # Проверенные поля — из колонок: в payload они такие, как прислал сервер бота.
    record.update(uid=row['uid'], asked_at=row['asked_at'], login=row['login'], name=row['name'],
                  status=row['status'], mode=row['mode'], source=row['source'], format=row['format'],
                  rating=row['rating'], feedback=feedback)
    return record


def delete(uid: str, only_login: Optional[str] = None) -> bool:
    if not UID_RE.fullmatch(str(uid or '')):
        return False
    _ensure()
    with db.write() as conn:
        if only_login is not None:
            row = conn.execute('SELECT login FROM bot_journal WHERE uid = ?', (uid,)).fetchone()
            if row is None or row['login'] != str(only_login):
                return False
        conn.execute('DELETE FROM bot_journal_messages WHERE uid = ?', (uid,))
        return conn.execute('DELETE FROM bot_journal WHERE uid = ?', (uid,)).rowcount > 0


CSV_COLUMNS = (('asked_at', 'Когда'), ('login', 'Логин'), ('name', 'Кто'), ('chat_type', 'Чат'), ('mode', 'Вид'),
               ('status', 'Итог'), ('question', 'Вопрос'), ('answer', 'Ответ'), ('cost_usd', 'Расход, $'),
               ('seconds', 'Секунд'), ('steps', 'Запросов к модели'), ('tool_calls', 'Вызовов инструментов'),
               ('format', 'Оформление'), ('rating', 'Оценка'))


def csv_text(args: Optional[Dict[str, Any]] = None, now: Optional[float] = None,
             only_login: Optional[str] = None) -> str:
    """Выгрузка выбранного (до CSV_MAX строк) для таблицы: точка с запятой, UTF-8 с BOM — Excel откроет."""
    where, params, _ = _filters(args or {}, now, only_login)
    _ensure()
    with db.read() as conn:
        rows = [dict(r) for r in conn.execute(
            f'SELECT * FROM bot_journal WHERE {where} ORDER BY asked_ts DESC LIMIT ?', params + [CSV_MAX])]
    out = io.StringIO()
    writer = csv.writer(out, delimiter=';')
    writer.writerow([title for _, title in CSV_COLUMNS])
    for row in rows:
        writer.writerow([('%.4f' % row[key]).replace('.', ',') if key == 'cost_usd' else row[key]
                         for key, _ in CSV_COLUMNS])
    return '﻿' + out.getvalue()

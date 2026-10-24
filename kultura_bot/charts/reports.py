"""Отчёты и записки «Как считается»: проверка, хранилище, вид для страницы.

## Что это

Решение владельца 2026-10-24: обычный вопрос — один пузырь в Telegram, большой —
полноценный разбор на странице. Пояснение расчёта (формулы, окна дат, источник) не
занимает места в сообщении: оно живёт на той же странице, а в сообщении — ссылка.

Два вида записей, одна таблица tg_reports в mcp.db:

    note    записка «Как считается» к одному ответу: заголовок и текст (Markdown бота).
            Пишут её сервер бота (POST /api/bot/note — блок «>> Как считается» из ответа
            модели) и common_chart_send (аргумент how).
    report  отчёт (common_report_send): заголовок, выжимка для пузыря в Telegram, разделы
            (текст, график, таблица, «Как считается» раздела), общее «Как считается»,
            источник и время данных.

Открывают их мини-приложение (/tg/chart?id=<id>, initData + участие в чате, как у
графиков) и страница сайта /tg/report/<id> (обычный вход сайта) — routes/tg_miniapp.py.
Куда ведёт кнопка или ссылка — kultura_bot/links.py.

## Формат отчёта (вход агента)

    title     заголовок — вывод с числом, до TITLE_MAX
    summary   выжимка для Telegram (Markdown бота): лид с числом, 2–4 строки, что дальше;
              в чате это подпись к обложке или текст сообщения (предел — при отправке)
    sections  1..SECTIONS_MAX разделов: {heading, text, chart, table, how}
              heading  заголовок раздела
              text     Markdown бота: абзацы, **жирный**, пункты, цитаты «> »
              chart    описание графика — тот же формат, что у common_chart_send
                       (kultura_bot/charts/spec.normalize); первый график — обложка в чате
              table    {columns: [строка | {label, align}], rows: [[ячейки]], note}
                       ячейка — строка, число или null; число выравнивается вправо
              how      «Как считается» раздела (Markdown), на странице — свёрнуто
    how       общее «Как считается» (Markdown), на странице — свёрнуто внизу
    source    источник данных: «iiko», «iiko · планы сайта»
    data_at   время данных ISO 8601; без пояса — МСК; по умолчанию — время отправки

Тексты хранятся Markdown-ом бота (источник истины) и переводятся в HTML при чтении
(kultura_bot/engine/formatting.to_html — тот же перевод, что у сообщений бота: всё
экранируется, разметка только своя).

## Хранилище

id — «rep_» и 22 шестнадцатеричных знака (secrets.token_hex(11): 88 бит; вместе с
проверкой участия в чате перебором не открыть). Длина и приставка отличают его от id
графика (22 знака token_urlsafe), поэтому мини-приложение одно. Срок — TTL_DAYS = 90 дней,
как у графиков; просроченные удаляются при каждой новой записи и не отдаются.
"""
import json
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core import msk_time
from core.mcp import db
from kultura_bot.charts import spec as chart_spec
from kultura_bot.links import REPORT_ID_RE

KINDS = ('note', 'report')
TTL_DAYS = 90
ID_HEX_BYTES = 11                  # token_hex(11) — 22 знака

TITLE_MAX = 120
SUMMARY_MAX = 3000                 # Markdown выжимки; видимый текст проверяет отправка (подпись ≤ 1024)
HEADING_MAX = 120
TEXT_MAX = 8000                    # текст раздела
HOW_MAX = 6000                     # «Как считается» раздела, отчёта или записки
SOURCE_MAX = 60
SECTIONS_MAX = 20
CHARTS_MAX = 8                     # графиков в отчёте: каждый — ECharts на странице телефона
TABLE_COLS_MAX = 12
TABLE_ROWS_MAX = 300
CELL_MAX = 200
TABLE_NOTE_MAX = 300
BODY_MAX_BYTES = 400_000           # канонический JSON записи

TextFilter = Callable[[str], str]


class ReportError(ValueError):
    """Отчёт или записка не прошли проверку: текст называет поле и что не так."""


class ReportLimitError(Exception):
    """Суточный предел записей исчерпан."""

    def __init__(self, used: int):
        super().__init__(used)
        self.used = used


# ------------------------------------------------------------------ проверка

def _markdown(value: Any, where: str, limit: int, *, required: bool = False,
              text_filter: Optional[TextFilter] = None) -> str:
    """Markdown бота: строки сохраняются, хвостовые пробелы и лишние пустые строки — нет."""
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ReportError(f'{where}: нужна строка')
    lines = [line.rstrip() for line in value.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
    text = '\n'.join(lines).strip('\n')
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    if text_filter is not None and text:
        text = text_filter(text)
    if required and not text.strip():
        raise ReportError(f'{where}: обязательное поле')
    if len(text) > limit:
        raise ReportError(f'{where}: длиннее {limit} символов')
    return text


def _line(value: Any, where: str, limit: int, *, required: bool = False,
          text_filter: Optional[TextFilter] = None) -> str:
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ReportError(f'{where}: нужна строка')
    text = ' '.join(value.split())
    if text_filter is not None and text:
        text = text_filter(text)
    if required and not text:
        raise ReportError(f'{where}: обязательное поле')
    if len(text) > limit:
        raise ReportError(f'{where}: длиннее {limit} символов')
    return text


def _cell(value: Any, where: str, text_filter: Optional[TextFilter]) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ReportError(f'{where}: ячейка — строка, число или null')
    if isinstance(value, (int, float)):
        if value != value or value in (float('inf'), float('-inf')):
            raise ReportError(f'{where}: число не конечное')
        if abs(value) > chart_spec.VALUE_ABS_MAX:
            raise ReportError(f'{where}: число больше {chart_spec.VALUE_ABS_MAX:g} — проверьте единицы')
        return value
    if isinstance(value, str):
        return _line(value, where, CELL_MAX, text_filter=text_filter)
    raise ReportError(f'{where}: ячейка — строка, число или null')


def _table(raw: Any, where: str, text_filter: Optional[TextFilter]) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ReportError(f'{where}: нужен объект {{columns, rows}}')
    unknown = sorted(set(raw) - {'columns', 'rows', 'note'})
    if unknown:
        raise ReportError(f'{where}: неизвестные поля: {", ".join(unknown)}')
    columns_raw, rows_raw = raw.get('columns'), raw.get('rows')
    if not isinstance(columns_raw, list) or not 1 <= len(columns_raw) <= TABLE_COLS_MAX:
        raise ReportError(f'{where}.columns: список от 1 до {TABLE_COLS_MAX} колонок')
    columns = []
    for n, col in enumerate(columns_raw):
        cw = f'{where}.columns[{n}]'
        if isinstance(col, str):
            col = {'label': col}
        if not isinstance(col, dict) or set(col) - {'label', 'align'}:
            raise ReportError(f'{cw}: строка или {{label, align}}')
        align = col.get('align')
        if align not in (None, 'left', 'right'):
            raise ReportError(f'{cw}.align: left или right')
        columns.append({'label': _line(col.get('label'), cw + '.label', CELL_MAX, required=True,
                                       text_filter=text_filter), 'align': align})
    if not isinstance(rows_raw, list) or not 1 <= len(rows_raw) <= TABLE_ROWS_MAX:
        raise ReportError(f'{where}.rows: список от 1 до {TABLE_ROWS_MAX} строк')
    rows = []
    for r, row in enumerate(rows_raw):
        if not isinstance(row, list) or len(row) != len(columns):
            raise ReportError(f'{where}.rows[{r}]: список из {len(columns)} ячеек (по числу колонок)')
        rows.append([_cell(v, f'{where}.rows[{r}][{c}]', text_filter) for c, v in enumerate(row)])
    for c, col in enumerate(columns):
        if col['align'] is None:
            numeric = [row[c] for row in rows if row[c] is not None]
            col['align'] = 'right' if numeric and all(isinstance(v, (int, float)) for v in numeric) else 'left'
    return {'columns': columns, 'rows': rows,
            'note': _line(raw.get('note'), where + '.note', TABLE_NOTE_MAX, text_filter=text_filter)}


def _data_at(value: Any, now: datetime) -> str:
    try:
        return chart_spec._data_at(value, now)
    except chart_spec.ChartSpecError as exc:
        raise ReportError(str(exc)) from None


def normalize_report(raw: Any, *, text_filter: Optional[TextFilter] = None,
                     page_filter: Optional[TextFilter] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Проверить отчёт и привести к каноническому виду (его и храним). Ошибка — ReportError.

    text_filter — для того, что уходит в Telegram (выжимка): там голый домен становится
    ссылкой. page_filter — для текстов страницы (заголовок, разделы, «Как считается»): там
    ссылкой становится только явный адрес, а имена полей вроде metrics.avg_rating должны
    остаться как есть."""
    if not isinstance(raw, dict):
        raise ReportError('отчёт: нужен объект')
    unknown = sorted(set(raw) - {'title', 'summary', 'sections', 'how', 'source', 'data_at'})
    if unknown:
        raise ReportError(f'неизвестные поля отчёта: {", ".join(unknown)}')
    now = now or msk_time.now()
    sections_raw = raw.get('sections')
    if not isinstance(sections_raw, list) or not 1 <= len(sections_raw) <= SECTIONS_MAX:
        raise ReportError(f'sections: список от 1 до {SECTIONS_MAX} разделов')
    sections: List[Dict[str, Any]] = []
    charts = 0
    for n, sec in enumerate(sections_raw):
        where = f'sections[{n}]'
        if not isinstance(sec, dict):
            raise ReportError(f'{where}: нужен объект {{heading, text, chart, table, how}}')
        unknown = sorted(set(sec) - {'heading', 'text', 'chart', 'table', 'how'})
        if unknown:
            raise ReportError(f'{where}: неизвестные поля: {", ".join(unknown)}')
        chart = None
        if sec.get('chart') is not None:
            charts += 1
            if charts > CHARTS_MAX:
                raise ReportError(f'не больше {CHARTS_MAX} графиков в отчёте')
            try:
                chart = chart_spec.normalize(sec['chart'], text_filter=page_filter, now=now)
            except chart_spec.ChartSpecError as exc:
                raise ReportError(f'{where}.chart: {exc}') from None
        item = {
            'heading': _line(sec.get('heading'), where + '.heading', HEADING_MAX, required=True,
                             text_filter=page_filter),
            'text': _markdown(sec.get('text'), where + '.text', TEXT_MAX, text_filter=page_filter),
            'chart': chart,
            'table': _table(sec.get('table'), where + '.table', page_filter),
            'how': _markdown(sec.get('how'), where + '.how', HOW_MAX, text_filter=page_filter),
        }
        if not (item['text'] or item['chart'] or item['table']):
            raise ReportError(f'{where}: нужен хотя бы text, chart или table')
        sections.append(item)
    body = {
        'kind': 'report',
        'title': _line(raw.get('title'), 'title', TITLE_MAX, required=True, text_filter=page_filter),
        'summary': _markdown(raw.get('summary'), 'summary', SUMMARY_MAX, required=True, text_filter=text_filter),
        'sections': sections,
        'how': _markdown(raw.get('how'), 'how', HOW_MAX, text_filter=page_filter),
        'source': _line(raw.get('source'), 'source', SOURCE_MAX, required=True, text_filter=page_filter),
        'data_at': _data_at(raw.get('data_at'), now),
    }
    _check_size(body)
    return body


def normalize_note(text: Any, *, title: Any = None, page_filter: Optional[TextFilter] = None,
                   now: Optional[datetime] = None) -> Dict[str, Any]:
    """Записка «Как считается»: заголовок (по умолчанию «Как считается») и текст."""
    now = now or msk_time.now()
    body = {
        'kind': 'note',
        'title': _line(title if title not in (None, '') else 'Как считается', 'title', TITLE_MAX,
                       text_filter=page_filter) or 'Как считается',
        'text': _markdown(text, 'text', HOW_MAX, required=True, text_filter=page_filter),
        'data_at': now.isoformat(timespec='seconds'),
    }
    _check_size(body)
    return body


def _check_size(body: Dict[str, Any]) -> None:
    size = len(json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    if size > BODY_MAX_BYTES:
        raise ReportError(f'запись больше {BODY_MAX_BYTES // 1000} КБ ({size // 1000} КБ): сократите таблицы и тексты')


# ------------------------------------------------------------------ вид для страницы

def view(record: Dict[str, Any]) -> Dict[str, Any]:
    """Запись -> то, что рисует страница: Markdown переведён в HTML (только своя разметка)."""
    from kultura_bot.engine import formatting
    body = record['body']
    html = formatting.to_html
    out: Dict[str, Any] = {'id': record['id'], 'kind': body['kind'], 'title': body['title'],
                           'data_at': body.get('data_at'), 'created_at': record['created_at']}
    if body['kind'] == 'note':
        out['how_html'] = html(body['text'])
        return out
    out.update({
        'summary_html': html(body['summary']),
        'sections': [{'heading': s['heading'], 'html': html(s['text']) if s['text'] else '',
                      'chart': s['chart'], 'table': s['table'],
                      'how_html': html(s['how']) if s['how'] else ''} for s in body['sections']],
        'how_html': html(body['how']) if body['how'] else '',
        'source': body['source'],
    })
    return out


def cover_chart(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Обложка отчёта в чате — первый график (или None)."""
    for section in body.get('sections') or []:
        if section.get('chart'):
            return section['chart']
    return None


# ------------------------------------------------------------------ хранилище

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS tg_reports (
        id          TEXT PRIMARY KEY,           -- rep_ + secrets.token_hex(11)
        kind        TEXT NOT NULL,              -- note | report
        body        TEXT NOT NULL,              -- канонический JSON (normalize_*)
        created_at  TEXT NOT NULL,              -- МСК ISO
        created_ts  INTEGER NOT NULL,
        expires_ts  INTEGER NOT NULL,
        day         TEXT NOT NULL,              -- МСК YYYY-MM-DD (суточный предел)
        chat_id     TEXT NOT NULL DEFAULT '',
        message_id  INTEGER,
        token_id    TEXT NOT NULL DEFAULT '',   -- кто записал: подключение MCP или ключ сервера бота
        sent        INTEGER NOT NULL DEFAULT 0  -- 1 — Telegram подтвердил отправку (у отчётов)
    )''',
    'CREATE INDEX IF NOT EXISTS idx_tg_reports_expires ON tg_reports(expires_ts)',
    'CREATE INDEX IF NOT EXISTS idx_tg_reports_day ON tg_reports(day)',
)


def _ensure() -> None:
    db.ensure_schema('tg_reports', SCHEMA)


def new_id() -> str:
    return 'rep_' + secrets.token_hex(ID_HEX_BYTES)


def valid_id(report_id: Any) -> bool:
    return isinstance(report_id, str) and bool(REPORT_ID_RE.fullmatch(report_id))


def create(body: Dict[str, Any], *, chat_id: str = '', token_id: str = '', now: Optional[datetime] = None,
           daily_limit: Optional[int] = None) -> Dict[str, Any]:
    """Сохранить запись. Вернуть {id, expires_at, used_today}. Предел — под одним write-локом."""
    if body.get('kind') not in KINDS:
        raise ReportError('kind — note или report')
    _ensure()
    now = now or msk_time.now()
    now_ts = int(now.timestamp())
    expires = now + timedelta(days=TTL_DAYS)
    day = now.date().isoformat()
    report_id = new_id()
    with db.write() as conn:
        conn.execute('DELETE FROM tg_reports WHERE expires_ts <= ?', (now_ts,))
        used = conn.execute('SELECT COUNT(*) AS n FROM tg_reports WHERE day=?', (day,)).fetchone()['n']
        if daily_limit is not None and used >= daily_limit:
            raise ReportLimitError(used)
        conn.execute('INSERT INTO tg_reports (id, kind, body, created_at, created_ts, expires_ts, day, chat_id, '
                     'token_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (report_id, body['kind'], json.dumps(body, ensure_ascii=False, separators=(',', ':')),
                      now.isoformat(timespec='seconds'), now_ts, int(expires.timestamp()), day,
                      str(chat_id or ''), token_id or ''))
    return {'id': report_id, 'expires_at': expires.isoformat(timespec='seconds'), 'used_today': used + 1}


def get(report_id: str, now_ts: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Запись или None (нет такого id, неверный формат или срок истёк)."""
    if not valid_id(report_id):
        return None
    _ensure()
    now_ts = int(now_ts if now_ts is not None else time.time())
    with db.read() as conn:
        row = conn.execute('SELECT * FROM tg_reports WHERE id=? AND expires_ts > ?', (report_id, now_ts)).fetchone()
    if row is None:
        return None
    record = dict(row)
    record['body'] = json.loads(record['body'])
    return record


def mark_sent(report_id: str, message_id: Optional[int]) -> None:
    _ensure()
    with db.write() as conn:
        conn.execute('UPDATE tg_reports SET sent=1, message_id=? WHERE id=?', (message_id, report_id))


def delete(report_id: str) -> None:
    _ensure()
    with db.write() as conn:
        conn.execute('DELETE FROM tg_reports WHERE id=?', (report_id,))

"""Графики бота @MCPkulturabot: описание графика, проверка и хранилище.

## Что это

Бот и агенты MCP присылают описание графика (нейтральный JSON), сервис рисует по нему
PNG (kultura_bot/charts/png.py), отправляет картинку в Telegram (kultura_bot/charts/send.py)
и хранит описание под непредсказуемым id. Кнопка «Открыть интерактивно» под
картинкой открывает мини-приложение /tg/chart (routes/tg_miniapp.py), которое
рисует тот же график на ECharts по тому же описанию. Один формат — одна картинка
и одна интерактивная версия: разойтись им негде.

## Формат описания (вход агента)

    kind        rating | periods | stack | days
                rating  — рейтинг полосами (одна серия value; фильтр по группам)
                periods — два периода столбиками (серии current и base)
                stack   — стек по частям (серии part, строка = категория)
                days    — ряд по дням (категории — даты YYYY-MM-DD, зум по периоду)
    title       заголовок, до 120 символов (обязательно)
    subtitle    период и бар: «2–13 сен к 19–30 авг 2026 · Все»
    note        одна строка пояснения под заголовком
    unit        единица значений как они переданы: «₽», «л», «порций» (обязательно)
    unit_forms  три формы единицы для чисел 1, 2, 5: ["порция", "порции", "порций"] —
                подпись «2 порции», а не «2 порций»; без них единица не склоняется
    scale       1 | 1000 | 1000000 — делитель для подписей и оси («тыс. ₽»);
                точные значения в подсказке и таблице не делятся. По умолчанию — см.
                default_scale
    decimals    0..3 — знаков после запятой у точных значений; по умолчанию — см.
                default_decimals
    additive    можно ли складывать значения категорий (итоги, доли). false — для
                средних, цен, долей; по умолчанию true
    categories  подписи: строка или {label, short, tag, note, color}
                short — короткая подпись на оси (до 2 строк через \\n), tag — группа
                для фильтра рейтинга («кран»), note — пояснение в подсказке,
                color — плашка цвета у подписи (ключ бара: bolshoy, ...)
    series      [{name, role, data, color}] — data той же длины, что categories;
                число или null («нет данных»)
    groups      только rating: [{label, tags}] — кнопки фильтра «Кран / Фасовка»
    base_category  подпись категории — точки отсчёта («до ивента»): в подсказке
                разница к ней (rating, stack)
    source      источник данных: «iiko» (обязательно)
    data_at     время данных ISO 8601; без пояса — МСК; по умолчанию — время отправки

## Хранилище

Таблица tg_charts в mcp.db (core/mcp/db.py: WAL, атомарные записи из двух
воркеров). id = secrets.token_urlsafe(16): 22 символа из [A-Za-z0-9_-], 128 бит
случайности — перебором не угадать; те же символы допускает start_param Telegram.
Срок хранения CHART_TTL_DAYS = 90 дней от отправки; просроченные строки удаляются
при каждой новой записи (purge_expired) и не отдаются (get).
"""
import json
import math
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core import msk_time
from core.mcp import db

FORMAT_VERSION = 1

KINDS = ('rating', 'periods', 'stack', 'days')
ROLES = ('value', 'current', 'base', 'part')
# Ключи цвета (static/tg_chart/charts.js, COLOR_TOKEN): акцент, база, нейтральные, две
# части стека и четыре бара сети (ключи заведений, как в common_bars_reference).
COLORS = ('accent', 'base', 'greige', 'other', 'part_dark', 'part_light',
          'bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya')
SCALES = (1, 1000, 1000000)

TITLE_MAX = 120
SUBTITLE_MAX = 160
NOTE_MAX = 300
UNIT_MAX = 24
SOURCE_MAX = 60
LABEL_MAX = 80
SHORT_MAX = 24            # одна строка короткой подписи; строк не больше SHORT_LINES
SHORT_LINES = 2
TAG_MAX = 24
CATEGORY_NOTE_MAX = 200
SERIES_NAME_MAX = 60
GROUP_LABEL_MAX = 24
GROUPS_MAX = 6
DECIMALS_MAX = 3
VALUE_ABS_MAX = 1e12      # больше — почти наверняка ошибка единиц (копейки вместо рублей)

# Сколько категорий помещается в карточку шириной 430 px (kultura_bot/charts/png.py):
# рейтинг и стек — строки по 40–56 px (60 строк ~ 2,5 тыс. px: Telegram хранит фото до
# 2560 px по длинной стороне, длиннее карточка в чате станет мелкой); два периода —
# столбики, 12 пар — ~15 px на столбик; ряд по дням — тонкие столбики, остальное — зумом.
CATEGORIES_MAX = {'rating': 60, 'periods': 12, 'stack': 40, 'days': 400}
SERIES_RANGE = {'rating': (1, 1), 'periods': (2, 2), 'stack': (1, 8), 'days': (1, 6)}

CHART_TTL_DAYS = 90
CHART_ID_BYTES = 16       # token_urlsafe(16) -> 22 символа
CHART_ID_RE = re.compile(r'[A-Za-z0-9_-]{16,64}')       # сверка — fullmatch

_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')

TextFilter = Callable[[str], str]


class ChartSpecError(ValueError):
    """Описание графика не прошло проверку: текст называет поле и что не так."""


class ChartLimitError(Exception):
    """Суточный предел отправок графиков исчерпан."""

    def __init__(self, used: int):
        super().__init__(used)
        self.used = used


# ------------------------------------------------------------------ проверка описания

def _text(value: Any, where: str, limit: int, *, required: bool = False, keep_newlines: bool = False,
          text_filter: Optional[TextFilter] = None) -> str:
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ChartSpecError(f'{where}: нужна строка')
    if keep_newlines:
        lines = [' '.join(line.split()) for line in value.replace('\r', '').split('\n')]
        text = '\n'.join(line for line in lines if line)
    else:
        text = ' '.join(value.split())
    if text_filter is not None and text:
        text = text_filter(text)
    if required and not text:
        raise ChartSpecError(f'{where}: обязательное поле')
    if len(text) > limit:
        raise ChartSpecError(f'{where}: длиннее {limit} символов')
    return text


def _number(value: Any, where: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChartSpecError(f'{where}: нужно число или null')
    if not math.isfinite(value):
        raise ChartSpecError(f'{where}: число должно быть конечным')
    if abs(value) > VALUE_ABS_MAX:
        raise ChartSpecError(f'{where}: по модулю больше {VALUE_ABS_MAX:.0e} — проверьте единицы')
    # Целое остаётся целым (252 -> 252), дробное — без хвоста двоичной арифметики
    # (406.70000000000005 -> 406.7): 6 знаков точнее любой единицы этого сервиса.
    if isinstance(value, int) or float(value).is_integer():
        return int(value)
    return round(float(value), 6)


def _decimals_of(value: float) -> int:
    text = repr(value)
    if 'e' in text or '.' not in text:
        return 0
    return len(text.split('.', 1)[1].rstrip('0'))


def default_decimals(values: List[float]) -> int:
    """Знаков после запятой, если агент их не задал: столько, сколько есть в данных,
    но не больше 2 (406.7 -> 1, 0.33 -> 2, 534120 -> 0)."""
    return min(2, max((_decimals_of(v) for v in values if v is not None), default=0))


def default_scale(unit: str, values: List[float]) -> int:
    """Делитель подписей, если агент его не задал: рубли от 100 000 по модулю
    подписываются в тысячах («тыс. ₽»), от 100 000 000 — в миллионах. Иначе 1.
    Почему с 100 000: шестизначные суммы на столбике не помещаются, а «534»
    с осью «тыс. ₽» читается сразу."""
    if unit.strip() != '₽':
        return 1
    peak = max((abs(v) for v in values if v is not None), default=0)
    if peak >= 100_000_000:
        return 1_000_000
    if peak >= 100_000:
        return 1000
    return 1


def _category(raw: Any, where: str, kind: str, text_filter: Optional[TextFilter]) -> Dict[str, Any]:
    if isinstance(raw, str):
        raw = {'label': raw}
    if not isinstance(raw, dict):
        raise ChartSpecError(f'{where}: нужна строка или объект {{label, ...}}')
    unknown = sorted(set(raw) - {'label', 'short', 'tag', 'note', 'color'})
    if unknown:
        raise ChartSpecError(f'{where}: лишние поля {unknown}')
    item: Dict[str, Any] = {'label': _text(raw.get('label'), where + '.label', LABEL_MAX, required=True,
                                           text_filter=text_filter)}
    if kind == 'days':
        if not _DATE_RE.fullmatch(item['label']):
            raise ChartSpecError(f'{where}.label: для ряда по дням нужна дата YYYY-MM-DD')
        try:
            datetime.strptime(item['label'], '%Y-%m-%d')
        except ValueError:
            raise ChartSpecError(f'{where}.label: такой даты нет ({item["label"]})') from None
    short = _text(raw.get('short'), where + '.short', SHORT_MAX * SHORT_LINES + 1, keep_newlines=True,
                  text_filter=text_filter)
    if short:
        lines = short.split('\n')
        if len(lines) > SHORT_LINES or any(len(line) > SHORT_MAX for line in lines):
            raise ChartSpecError(f'{where}.short: не больше {SHORT_LINES} строк по {SHORT_MAX} символов')
        item['short'] = short
    tag = _text(raw.get('tag'), where + '.tag', TAG_MAX, text_filter=text_filter)
    if tag:
        item['tag'] = tag
    note = _text(raw.get('note'), where + '.note', CATEGORY_NOTE_MAX, text_filter=text_filter)
    if note:
        item['note'] = note
    color = raw.get('color')
    if color is not None:
        if color not in COLORS:
            raise ChartSpecError(f'{where}.color: один из {list(COLORS)}')
        item['color'] = color
    return item


def _series(raw: Any, where: str, size: int, text_filter: Optional[TextFilter]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ChartSpecError(f'{where}: нужен объект {{name, role, data}}')
    unknown = sorted(set(raw) - {'name', 'role', 'data', 'color'})
    if unknown:
        raise ChartSpecError(f'{where}: лишние поля {unknown}')
    role = raw.get('role')
    if role not in ROLES:
        raise ChartSpecError(f'{where}.role: один из {list(ROLES)}')
    data = raw.get('data')
    if not isinstance(data, list):
        raise ChartSpecError(f'{where}.data: нужен список чисел')
    if len(data) != size:
        raise ChartSpecError(f'{where}.data: {len(data)} значений, а категорий {size}')
    item = {'name': _text(raw.get('name'), where + '.name', SERIES_NAME_MAX, required=True,
                          text_filter=text_filter),
            'role': role,
            'data': [_number(v, f'{where}.data[{i}]') for i, v in enumerate(data)]}
    color = raw.get('color')
    if color is not None:
        if color not in COLORS:
            raise ChartSpecError(f'{where}.color: один из {list(COLORS)}')
        item['color'] = color
    return item


def _check_roles(kind: str, series: List[Dict[str, Any]]) -> None:
    roles = [s['role'] for s in series]
    low, high = SERIES_RANGE[kind]
    if not low <= len(series) <= high:
        count = str(low) if low == high else f'от {low} до {high}'
        raise ChartSpecError(f'series: для вида {kind} нужно {count}, получено {len(series)}')
    if kind == 'rating' and roles != ['value']:
        raise ChartSpecError('series: у рейтинга одна серия с role=value')
    if kind == 'periods' and sorted(roles) != ['base', 'current']:
        raise ChartSpecError('series: у двух периодов серии role=current (текущий) и role=base (сравнение)')
    if kind == 'stack' and set(roles) != {'part'}:
        raise ChartSpecError('series: у стека все серии role=part')
    if kind == 'days':
        if 'part' in roles and set(roles) != {'part'}:
            raise ChartSpecError('series: у ряда по дням либо все серии role=part (стек), либо ни одной')
        if roles.count('current') > 1 or roles.count('base') > 1:
            raise ChartSpecError('series: role=current и role=base — не больше чем по одной')
    if kind in ('rating', 'stack'):
        for s_index, s in enumerate(series):
            for i, v in enumerate(s['data']):
                if v is not None and v < 0:
                    raise ChartSpecError(f'series[{s_index}].data[{i}]: у вида {kind} значения не меньше 0')
    if kind == 'rating' and any(v is None for v in series[0]['data']):
        raise ChartSpecError('series[0].data: у рейтинга нужны все значения (null нельзя)')


def _data_at(value: Any, now: datetime) -> str:
    if value in (None, ''):
        return now.isoformat(timespec='seconds')
    if not isinstance(value, str):
        raise ChartSpecError('data_at: нужна строка ISO 8601, например 2026-09-14T00:58:00+03:00')
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ChartSpecError('data_at: нужна строка ISO 8601, например 2026-09-14T00:58:00+03:00') from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=msk_time.MOSCOW_TZ)
    return moment.astimezone(msk_time.MOSCOW_TZ).isoformat(timespec='seconds')


def normalize(raw: Any, *, text_filter: Optional[TextFilter] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Проверить описание графика и привести к каноническому виду (его и храним).

    text_filter — функция над каждой строкой (MCP передаёт вырезание чужих ссылок,
    как у сообщения владельцу). Ошибка — ChartSpecError с именем поля.
    """
    if not isinstance(raw, dict):
        raise ChartSpecError('описание графика: нужен объект')
    allowed = {'kind', 'title', 'subtitle', 'note', 'unit', 'unit_forms', 'scale', 'decimals', 'additive',
               'categories', 'series', 'groups', 'base_category', 'source', 'data_at'}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ChartSpecError(f'лишние поля {unknown}')
    kind = raw.get('kind')
    if kind not in KINDS:
        raise ChartSpecError(f'kind: один из {list(KINDS)}')
    now = now or msk_time.now()
    spec: Dict[str, Any] = {
        'v': FORMAT_VERSION,
        'kind': kind,
        'title': _text(raw.get('title'), 'title', TITLE_MAX, required=True, text_filter=text_filter),
        'subtitle': _text(raw.get('subtitle'), 'subtitle', SUBTITLE_MAX, text_filter=text_filter),
        'note': _text(raw.get('note'), 'note', NOTE_MAX, text_filter=text_filter),
        'unit': _text(raw.get('unit'), 'unit', UNIT_MAX, required=True, text_filter=text_filter),
        'source': _text(raw.get('source'), 'source', SOURCE_MAX, required=True, text_filter=text_filter),
    }
    forms = raw.get('unit_forms')
    spec['unit_forms'] = []
    if forms not in (None, []):
        if not isinstance(forms, list) or len(forms) != 3:
            raise ChartSpecError('unit_forms: три формы для 1, 2 и 5 — ["порция", "порции", "порций"]')
        spec['unit_forms'] = [_text(f, f'unit_forms[{i}]', UNIT_MAX, required=True, text_filter=text_filter)
                              for i, f in enumerate(forms)]

    categories = raw.get('categories')
    if not isinstance(categories, list) or not categories:
        raise ChartSpecError('categories: нужен непустой список')
    if len(categories) > CATEGORIES_MAX[kind]:
        raise ChartSpecError(f'categories: для вида {kind} не больше {CATEGORIES_MAX[kind]}, получено '
                             f'{len(categories)} — сузьте выборку или возьмите первые')
    spec['categories'] = [_category(c, f'categories[{i}]', kind, text_filter) for i, c in enumerate(categories)]
    labels = [c['label'] for c in spec['categories']]
    # Один сорт может стоять в рейтинге дважды — на кране и в бутылке: тогда их
    # различает метка (tag). Пара «подпись + метка» у каждой категории своя.
    keys = [(c['label'], c.get('tag', '')) for c in spec['categories']]
    if len(set(keys)) != len(keys):
        raise ChartSpecError('categories: подписи повторяются — у каждой категории своя (или своя метка tag)')
    if kind == 'days' and any(a >= b for a, b in zip(labels, labels[1:])):
        raise ChartSpecError('categories: даты ряда по дням идут по возрастанию без повторов')

    series = raw.get('series')
    if not isinstance(series, list) or not series:
        raise ChartSpecError('series: нужен непустой список')
    spec['series'] = [_series(s, f'series[{i}]', len(labels), text_filter) for i, s in enumerate(series)]
    _check_roles(kind, spec['series'])
    for i, s in enumerate(spec['series']):
        s['key'] = f's{i}'

    values = [v for s in spec['series'] for v in s['data'] if v is not None]
    scale = raw.get('scale')
    if scale is None:
        scale = default_scale(spec['unit'], values)
    elif isinstance(scale, bool) or scale not in SCALES:
        raise ChartSpecError(f'scale: одно из {list(SCALES)}')
    spec['scale'] = int(scale)
    decimals = raw.get('decimals')
    if decimals is None:
        decimals = default_decimals(values)
    elif isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= DECIMALS_MAX:
        raise ChartSpecError(f'decimals: целое от 0 до {DECIMALS_MAX}')
    spec['decimals'] = int(decimals)
    additive = raw.get('additive', True)
    if not isinstance(additive, bool):
        raise ChartSpecError('additive: true или false')
    spec['additive'] = additive

    groups = raw.get('groups')
    spec['groups'] = []
    if groups not in (None, []):
        if kind != 'rating':
            raise ChartSpecError('groups: только у рейтинга (kind=rating)')
        if not isinstance(groups, list) or len(groups) > GROUPS_MAX:
            raise ChartSpecError(f'groups: список до {GROUPS_MAX} групп')
        tags = {c.get('tag') for c in spec['categories'] if c.get('tag')}
        for i, g in enumerate(groups):
            where = f'groups[{i}]'
            if not isinstance(g, dict) or sorted(set(g) - {'label', 'tags'}):
                raise ChartSpecError(f'{where}: нужен объект {{label, tags}}')
            label = _text(g.get('label'), where + '.label', GROUP_LABEL_MAX, required=True, text_filter=text_filter)
            g_tags = g.get('tags')
            if not isinstance(g_tags, list) or not g_tags:
                raise ChartSpecError(f'{where}.tags: непустой список меток из categories[].tag')
            clean = [_text(t, f'{where}.tags', TAG_MAX, required=True, text_filter=text_filter) for t in g_tags]
            missing = [t for t in clean if t not in tags]
            if missing:
                raise ChartSpecError(f'{where}.tags: нет категорий с метками {missing}')
            spec['groups'].append({'key': f'g{i}', 'label': label, 'tags': clean})

    base_category = raw.get('base_category')
    spec['base_category'] = None
    if base_category not in (None, ''):
        if kind not in ('rating', 'stack'):
            raise ChartSpecError('base_category: только у rating и stack (у двух периодов база — серия base)')
        if labels.count(base_category) != 1:
            raise ChartSpecError('base_category: подпись ровно одной из categories')
        spec['base_category'] = labels.index(base_category)

    spec['data_at'] = _data_at(raw.get('data_at'), now)
    return spec


# ------------------------------------------------------------------ хранилище

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS tg_charts (
        id          TEXT PRIMARY KEY,           -- secrets.token_urlsafe(16)
        spec        TEXT NOT NULL,              -- канонический JSON описания (normalize)
        created_at  TEXT NOT NULL,              -- МСК ISO
        created_ts  INTEGER NOT NULL,           -- unix-время создания
        expires_ts  INTEGER NOT NULL,           -- unix-время, после которого не отдаём
        day         TEXT NOT NULL,              -- МСК YYYY-MM-DD (суточный предел отправок)
        chat_id     TEXT NOT NULL DEFAULT '',
        message_id  INTEGER,
        token_id    TEXT NOT NULL DEFAULT '',   -- подключение MCP, которое отправило
        sent        INTEGER NOT NULL DEFAULT 0  -- 1 — Telegram подтвердил отправку
    )''',
    'CREATE INDEX IF NOT EXISTS idx_tg_charts_expires ON tg_charts(expires_ts)',
    'CREATE INDEX IF NOT EXISTS idx_tg_charts_day ON tg_charts(day)',
)


def _ensure() -> None:
    db.ensure_schema('tg_charts', SCHEMA)


def new_chart_id() -> str:
    return secrets.token_urlsafe(CHART_ID_BYTES)


def valid_chart_id(chart_id: Any) -> bool:
    return isinstance(chart_id, str) and bool(CHART_ID_RE.fullmatch(chart_id))


def purge_expired(conn, now_ts: Optional[float] = None) -> int:
    now_ts = int(now_ts if now_ts is not None else time.time())
    return conn.execute('DELETE FROM tg_charts WHERE expires_ts <= ?', (now_ts,)).rowcount


def create(spec: Dict[str, Any], *, chat_id: str = '', token_id: str = '', now: Optional[datetime] = None,
           daily_limit: Optional[int] = None) -> Dict[str, Any]:
    """Сохранить описание (до отправки: кнопке нужен id). Вернуть {id, expires_at, used_today}.

    daily_limit — суточный предел записей (МСК) на все подключения; проверка и запись
    под одним write-локом, поэтому два воркера не проскочат предел вместе.
    """
    _ensure()
    now = now or msk_time.now()
    now_ts = int(now.timestamp())
    expires = now + timedelta(days=CHART_TTL_DAYS)
    day = now.date().isoformat()
    chart_id = new_chart_id()
    with db.write() as conn:
        purge_expired(conn, now_ts)
        used = conn.execute('SELECT COUNT(*) AS n FROM tg_charts WHERE day=?', (day,)).fetchone()['n']
        if daily_limit is not None and used >= daily_limit:
            raise ChartLimitError(used)
        conn.execute('INSERT INTO tg_charts (id, spec, created_at, created_ts, expires_ts, day, chat_id, token_id) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                     (chart_id, json.dumps(spec, ensure_ascii=False, separators=(',', ':')),
                      now.isoformat(timespec='seconds'), now_ts, int(expires.timestamp()), day,
                      str(chat_id or ''), token_id or ''))
    return {'id': chart_id, 'expires_at': expires.isoformat(timespec='seconds'), 'used_today': used + 1}


def get(chart_id: str, now_ts: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Запись графика или None (нет такого id, неверный формат или срок истёк)."""
    if not valid_chart_id(chart_id):
        return None
    _ensure()
    now_ts = int(now_ts if now_ts is not None else time.time())
    with db.read() as conn:
        row = conn.execute('SELECT * FROM tg_charts WHERE id=? AND expires_ts > ?', (chart_id, now_ts)).fetchone()
    if row is None:
        return None
    record = dict(row)
    record['spec'] = json.loads(record['spec'])
    return record


def mark_sent(chart_id: str, message_id: Optional[int]) -> None:
    _ensure()
    with db.write() as conn:
        conn.execute('UPDATE tg_charts SET sent=1, message_id=? WHERE id=?', (message_id, chart_id))


def delete(chart_id: str) -> None:
    _ensure()
    with db.write() as conn:
        conn.execute('DELETE FROM tg_charts WHERE id=?', (chart_id,))

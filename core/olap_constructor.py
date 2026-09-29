"""Конструктор OLAP-отчётов (/explorer): заявка -> запросы iiko -> сводная таблица.

Что это
    Перенос конструктора OLAP-отчётов iikoOffice в сервис. Заявка (ReportSpec) — это
    ровно то, что пользователь собирает в iikoOffice: тип отчёта, поля в строках и
    столбцах, показатели, фильтры и период. Модуль проверяет заявку по каталогу полей
    (core/olap_catalog.py), собирает тела запросов POST /v2/reports/olap, выполняет их
    (core/olap_client.py) и раскладывает ответ в сводную таблицу с итогами — как грид
    iikoOffice — или в плоский список строк (для ИИ-агентов и выгрузки).

Правила сборки запроса (olap_body)
    1. Период — всегда фильтр DateRange по полю периода типа отчёта (DATE_FIELD):
       from = первый день, to = последний день + 1 (граница iiko исключающая, а
       пользователь выбирает дни включительно). Относительные периоды iiko
       (CURRENT_WEEK и т.п.) не используются: даты считает сервис (resolve_period),
       по рабочим суткам бара (до 06:00 МСК), и показывает их в ответе явно.
    2. Удалённые позиции и заказы. Если в заявке нет своего фильтра по полям
       DeletedWithWriteoff / OrderDeleted и не сказано include_deleted=true, в отчёт по
       продажам и доставкам добавляется фильтр «не удалено» (DELETION_GUARDS) — так
       работает шаблон OLAP-отчёта iikoOffice и все отчёты сервиса. Страница
       конструктора всегда шлёт include_deleted=true и показывает эти фильтры
       обычными фишками: их видно и можно снять.
    3. Строки и столбцы уходят в iiko одним списком groupByRowFields, а раскладка по
       столбцам делается здесь. Так ответ iiko всегда плоский и одинаково читается.
    4. Сортировка, топ-N и условия на показатели в iiko не отправляются — в теле
       OLAP-запроса их нет (docs/iiko-api/olap-otchety-v2.md), это делает модуль.

Итоги (build_pivot)
    У показателя kind 'sum' (core/olap_catalog.py) итог группы = сумма её строк —
    считается здесь, точно. У kind 'server' (уникальные чеки, средние, проценты,
    длительности) сумма строк неверна, поэтому итоги берутся из iiko: запрос с
    buildSummary=true возвращает summary — блоки [ключи, значения], где ключи —
    ПРЕФИКС полей группировки в порядке запроса (документация iiko, «Что в ответе»).
    Префикс даёт не все нужные итоги, отсюда план запросов:

        нет показателей 'server'  -> 1 запрос (строки + столбцы), без summary;
        нет столбцов              -> 1 запрос (строки), summary: итоги групп строк;
        нет строк                 -> 1 запрос (столбцы), summary: общий итог;
        есть и строки, и столбцы  -> 2 запроса одной сессией, параллельно:
            'cells' (столбцы + строки): ячейки, итоги столбцов и итоги групп строк
                                        внутри каждого столбца;
            'rows'  (только строки):    колонка «Итого» — итоги строк и групп по всем
                                        столбцам и общий итог.

    Если iiko не вернул нужный блок summary, в итоговой ячейке показателя 'server'
    стоит прочерк (null) и в warnings — пояснение; сумму строк вместо неё не
    подставляем никогда. Сверка: общий итог iiko по показателям 'sum' сравнивается с
    суммой строк; расхождение больше копейки — предупреждение (значит, разбор summary
    разошёлся с форматом iiko).

Пределы (почему такие)
    PIVOT_MAX_LEAVES = 20 000 строк и PIVOT_MAX_CELLS = 400 000 ячеек — больше браузер
    рисует с заметной задержкой, а читать такую таблицу глазами нельзя; для больших
    отчётов есть выгрузка в Excel (EXPORT_MAX_ROWS = 200 000 строк данных).
    RECOMMENDED_FIELDS = 7 — рекомендация iiko по нагрузке («не более 7 полей»,
    ogranicheniya-i-rekomendatsii.md): не запрет, а предупреждение в ответе.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core import msk_time
from core.olap_catalog import (DATE_FIELD, REPORT_TYPE_TITLES, REPORT_TYPES, Catalog, Field,
                               get_catalog)
from core.olap_client import IikoError, fetch_olap, open_session

MAX_ROW_FIELDS = 8
MAX_COLUMN_FIELDS = 4
MAX_MEASURES = 12
MAX_FILTERS = 30
MAX_FILTER_VALUES = 500
RECOMMENDED_FIELDS = 7
PIVOT_MAX_LEAVES = 20000
PIVOT_MAX_CELLS = 400000
FLAT_DEFAULT_LIMIT = 200
FLAT_MAX_LIMIT = 5000
EXPORT_MAX_ROWS = 200000
EXPORT_PIVOT_MAX_LEAVES = 50000
VALUES_MAX = 2000
PRESETS_TTL_S = 600
ROUND_DIGITS = 6          # числа в ответе — до 6 знаков: убирает хвосты 0.30000000000000004

FORMATS = ('flat', 'pivot')
FILTER_OPS = ('in', 'not_in', 'range', 'date_range')
HAVING_OPS = ('>', '>=', '<', '<=', '=', '!=')
SORT_ORDERS = ('asc', 'desc')

PERIOD_PRESETS: Tuple[str, ...] = (
    'yesterday', 'today', 'this_week', 'last_week', 'this_month', 'last_month',
    'last_7_days', 'last_30_days', 'this_year', 'last_year',
)
PERIOD_TITLES: Dict[str, str] = {
    'yesterday': 'Вчера', 'today': 'Сегодня', 'this_week': 'Эта неделя',
    'last_week': 'Прошлая неделя', 'this_month': 'Этот месяц', 'last_month': 'Прошлый месяц',
    'last_7_days': 'Последние 7 дней', 'last_30_days': 'Последние 30 дней',
    'this_year': 'Этот год', 'last_year': 'Прошлый год',
}
# periodType сохранённого отчёта iikoOffice -> пресет сервиса (CUSTOM — явные даты).
IIKO_PERIOD_TYPES: Dict[str, str] = {
    'TODAY': 'today', 'YESTERDAY': 'yesterday', 'CURRENT_WEEK': 'this_week',
    'LAST_WEEK': 'last_week', 'CURRENT_MONTH': 'this_month', 'LAST_MONTH': 'last_month',
    'CURRENT_YEAR': 'this_year', 'LAST_YEAR': 'last_year',
}
GUARDED_TYPES = ('SALES', 'DELIVERIES')
DELETION_GUARDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ('DeletedWithWriteoff', ('NOT_DELETED',)),
    ('OrderDeleted', ('NOT_DELETED',)),
)
# Показатель для запроса «какие значения есть у поля» (списки фильтров): самый лёгкий
# из доступных. Сам показатель в ответ не идёт.
VALUES_MEASURES: Dict[str, Tuple[str, ...]] = {
    'SALES': ('DishAmountInt', 'DishSumInt', 'UniqOrderId'),
    'DELIVERIES': ('DishAmountInt', 'DishSumInt', 'UniqOrderId'),
    'TRANSACTIONS': ('Amount', 'Amount.In', 'Sum.ResignedSum'),
    'STOCK': ('Amount',),
}


class ConstructorError(ValueError):
    """Ошибка заявки: status — HTTP-код ответа маршрута, code — машинный код для страницы."""

    def __init__(self, message: str, status: int = 400, code: str = 'bad_request',
                 extra: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.extra = extra or {}


# ---------------------------------------------------------------- период

def resolve_period(preset: str, today: Optional[date] = None) -> Tuple[date, date]:
    """Пресет периода -> (первый день, последний день), оба включительно.

    «Сегодня» — рабочий день бара (сутки до 06:00 МСК, core/msk_time.business_today).
    Неделя — понедельник..воскресенье. «Последние 7/30 дней» — закрытые дни до
    вчера включительно: незакрытый сегодняшний день не смешивается с полными.
    """
    today = today or msk_time.business_today()
    if preset == 'today':
        return today, today
    if preset == 'yesterday':
        day = today - timedelta(days=1)
        return day, day
    monday = today - timedelta(days=today.weekday())
    if preset == 'this_week':
        return monday, today
    if preset == 'last_week':
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if preset == 'this_month':
        return today.replace(day=1), today
    if preset == 'last_month':
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    if preset == 'last_7_days':
        return today - timedelta(days=7), today - timedelta(days=1)
    if preset == 'last_30_days':
        return today - timedelta(days=30), today - timedelta(days=1)
    if preset == 'this_year':
        return date(today.year, 1, 1), today
    if preset == 'last_year':
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    raise ConstructorError('Неизвестный период «' + str(preset) + '». Варианты: ' +
                           ', '.join(PERIOD_PRESETS) + '.')


def period_table(today: Optional[date] = None) -> List[dict]:
    """Все пресеты с датами на сегодня — для подписей на странице."""
    out = []
    for preset in PERIOD_PRESETS:
        start, end = resolve_period(preset, today)
        out.append({'id': preset, 'title': PERIOD_TITLES[preset],
                    'date_from': start.isoformat(), 'date_to': end.isoformat()})
    return out


def _parse_day(raw, name: str) -> date:
    try:
        return datetime.strptime(str(raw).strip()[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ConstructorError(name + ': нужна дата в формате YYYY-MM-DD, получено «' +
                               str(raw) + '».')


def _parse_period(payload: dict) -> Tuple[date, date, Optional[str]]:
    preset = payload.get('period')
    if preset not in (None, ''):
        start, end = resolve_period(str(preset))
        return start, end, str(preset)
    if not payload.get('date_from') or not payload.get('date_to'):
        raise ConstructorError('Нужен период: date_from и date_to (YYYY-MM-DD, включительно) '
                               'или period (' + ', '.join(PERIOD_PRESETS) + ').')
    start = _parse_day(payload.get('date_from'), 'date_from')
    end = _parse_day(payload.get('date_to'), 'date_to')
    if end < start:
        raise ConstructorError('Конец периода раньше начала: ' + start.isoformat() + ' — ' +
                               end.isoformat() + '.')
    return start, end, None


# ---------------------------------------------------------------- заявка

@dataclass
class FilterSpec:
    field: str
    op: str
    values: List[Any] = field(default_factory=list)
    low: Any = None
    high: Any = None
    include_low: bool = True
    include_high: bool = True

    def compile(self) -> dict:
        if self.op in ('in', 'not_in'):
            return {'filterType': 'IncludeValues' if self.op == 'in' else 'ExcludeValues',
                    'values': list(self.values)}
        if self.op == 'range':
            return {'filterType': 'Range', 'from': self.low, 'to': self.high,
                    'includeLow': self.include_low, 'includeHigh': self.include_high}
        return {'filterType': 'DateRange', 'periodType': 'CUSTOM', 'from': self.low,
                'to': self.high, 'includeLow': self.include_low,
                'includeHigh': self.include_high}

    def to_json(self) -> dict:
        out = {'field': self.field, 'op': self.op}
        if self.op in ('in', 'not_in'):
            out['values'] = list(self.values)
        else:
            out.update({'from': self.low, 'to': self.high, 'include_low': self.include_low,
                        'include_high': self.include_high})
        return out


@dataclass
class ReportSpec:
    report_type: str
    rows: List[str]
    columns: List[str]
    measures: List[str]
    filters: List[FilterSpec]
    include_deleted: bool
    date_from: date
    date_to: date
    period: Optional[str] = None

    @property
    def dims(self) -> List[str]:
        return self.rows + self.columns

    def guards(self) -> List[FilterSpec]:
        """Фильтры «не удалено», которые добавятся автоматически (правило 2)."""
        if self.include_deleted or self.report_type not in GUARDED_TYPES:
            return []
        own = {f.field for f in self.filters}
        return [FilterSpec(fid, 'in', list(values)) for fid, values in DELETION_GUARDS
                if fid not in own]

    def config(self) -> dict:
        """Заявка в том виде, в каком её хранят сохранённые отчёты."""
        period = ({'preset': self.period} if self.period else
                  {'from': self.date_from.isoformat(), 'to': self.date_to.isoformat()})
        return {'report_type': self.report_type, 'rows': list(self.rows),
                'columns': list(self.columns), 'measures': list(self.measures),
                'filters': [f.to_json() for f in self.filters],
                'include_deleted': self.include_deleted, 'period': period}


def parse_report_type(payload: dict) -> str:
    value = str(payload.get('report_type') or 'SALES').strip().upper()
    if value not in REPORT_TYPES:
        raise ConstructorError('report_type: один из ' + ', '.join(REPORT_TYPES) + '.')
    return value


def _str_list(payload: dict, key: str, limit: int) -> List[str]:
    raw = payload.get(key) or []
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise ConstructorError(key + ': нужен список id полей (строк).')
    items = [item.strip() for item in raw]
    if len(items) > limit:
        raise ConstructorError(key + ': не больше ' + str(limit) + ' полей.')
    if len(set(items)) != len(items):
        raise ConstructorError(key + ': поле указано дважды.')
    return items


def _field_or_error(catalog: Catalog, fid: str, where: str) -> Field:
    item = catalog.get(fid)
    if item is None:
        raise ConstructorError(where + ': в каталоге «' + REPORT_TYPE_TITLES[catalog.report_type] +
                               '» нет поля «' + fid + '». Найдите id в каталоге полей.',
                               code='unknown_field', extra={'field': fid})
    if item.blocked:
        raise ConstructorError(where + ': поле «' + item.name + '» недоступно. ' + item.blocked,
                               code='blocked_field', extra={'field': fid})
    return item


def _enum_code(item: Field, value) -> Any:
    """Для перечислений принимаем и код, и русское название — в iiko уходит код."""
    if value is None or not item.enum:
        return value
    text = str(value)
    for code, label in item.enum:
        if text == code:
            return code
    folded = text.casefold()
    for code, label in item.enum:
        if folded == label.casefold():
            return code
    return text


def _number(raw, where: str) -> float:
    if isinstance(raw, bool) or raw is None:
        raise ConstructorError(where + ': нужно число.')
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ConstructorError(where + ': нужно число, получено «' + str(raw) + '».')
    if not math.isfinite(value):
        raise ConstructorError(where + ': нужно конечное число.')
    return int(value) if value.is_integer() else value


_DATETIME_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?')


def _datetime_value(raw, where: str, whole_unit: bool = False) -> str:
    """Граница фильтра date_range в формате iiko YYYY-MM-DDTHH:MM:SS.sss.

    whole_unit — верхняя граница «включительно»: без времени она покрывает весь день
    (до 23:59:59.999), без секунд — всю минуту (до ЧЧ:ММ:59.999). Иначе «до 22-го»
    включало бы только полночь 22-го, а «до 23:59» теряло бы последнюю минуту.
    """
    match = _DATETIME_RE.match(str(raw or '').strip())
    if not match:
        raise ConstructorError(where + ': нужна дата YYYY-MM-DD или дата и время '
                               'YYYY-MM-DDTHH:MM, получено «' + str(raw) + '».')
    day = match.group(1)
    _parse_day(day, where)
    hours, minutes, seconds = match.group(2) or '00', match.group(3) or '00', match.group(4) or '00'
    if int(hours) > 23 or int(minutes) > 59 or int(seconds) > 59:
        raise ConstructorError(where + ': неверное время «' + str(raw) + '».')
    if whole_unit and match.group(2) is None:
        return day + 'T23:59:59.999'
    if whole_unit and match.group(4) is None:
        return day + 'T' + hours + ':' + minutes + ':59.999'
    return day + 'T' + hours + ':' + minutes + ':' + seconds + '.000'


def _parse_filters(payload: dict, catalog: Catalog) -> List[FilterSpec]:
    raw = payload.get('filters') or []
    if not isinstance(raw, list):
        raise ConstructorError('filters: нужен список фильтров.')
    if len(raw) > MAX_FILTERS:
        raise ConstructorError('filters: не больше ' + str(MAX_FILTERS) + ' фильтров.')
    out: List[FilterSpec] = []
    seen = set()
    for index, item in enumerate(raw):
        where = 'filters[' + str(index) + ']'
        if not isinstance(item, dict):
            raise ConstructorError(where + ': нужен объект {field, op, …}.')
        fid = str(item.get('field') or '').strip()
        spec_field = _field_or_error(catalog, fid, where)
        if fid in seen:
            raise ConstructorError(where + ': второй фильтр по полю «' + spec_field.name +
                                   '» — объедините значения в один.')
        seen.add(fid)
        if not spec_field.filter_op:
            raise ConstructorError(where + ': по полю «' + spec_field.name + '» фильтр нельзя. ' +
                                   (spec_field.filter_note or ''))
        op = str(item.get('op') or '').strip()
        allowed = {'values': ('in', 'not_in'), 'range': ('range',),
                   'date_range': ('date_range',)}[spec_field.filter_op]
        if op not in allowed:
            raise ConstructorError(where + ': у поля «' + spec_field.name + '» фильтр ' +
                                   ' или '.join(allowed) + ', а не «' + op + '».')
        if op in ('in', 'not_in'):
            values = item.get('values')
            if not isinstance(values, list) or not values:
                raise ConstructorError(where + ': values — непустой список значений.')
            if len(values) > MAX_FILTER_VALUES:
                raise ConstructorError(where + ': не больше ' + str(MAX_FILTER_VALUES) +
                                       ' значений.')
            clean = []
            for value in values:
                if value is not None and not isinstance(value, (str, int, float)):
                    raise ConstructorError(where + ': значения — строки, числа или null (пусто).')
                if isinstance(value, bool):
                    raise ConstructorError(where + ': значения — строки, числа или null (пусто).')
                code = _enum_code(spec_field, value)
                clean.append(code if code is None else str(code) if not isinstance(code, str) else code)
            out.append(FilterSpec(fid, op, clean))
            continue
        include_low = item.get('include_low', True)
        include_high = item.get('include_high', True)
        if not isinstance(include_low, bool) or not isinstance(include_high, bool):
            raise ConstructorError(where + ': include_low и include_high — true или false.')
        if op == 'range':
            low = _number(item.get('from'), where + '.from')
            high = _number(item.get('to'), where + '.to')
        else:
            low = _datetime_value(item.get('from'), where + '.from')
            high = _datetime_value(item.get('to'), where + '.to', whole_unit=include_high)
        if high < low:
            raise ConstructorError(where + ': «до» меньше «от».')
        out.append(FilterSpec(fid, op, [], low, high, include_low, include_high))
    return out


def parse_spec(payload: dict, catalog: Catalog) -> ReportSpec:
    """Проверить заявку по каталогу. Ошибка — ConstructorError с понятным текстом."""
    rows = _str_list(payload, 'rows', MAX_ROW_FIELDS)
    columns = _str_list(payload, 'columns', MAX_COLUMN_FIELDS)
    measures = _str_list(payload, 'measures', MAX_MEASURES)
    if not rows and not columns:
        raise ConstructorError('Добавьте хотя бы одно поле в строки или столбцы.', code='no_dims')
    if not measures:
        raise ConstructorError('Добавьте хотя бы один показатель.', code='no_measures')
    both = set(rows) & set(columns)
    if both:
        raise ConstructorError('Поле «' + sorted(both)[0] + '» и в строках, и в столбцах.')
    for fid in rows + columns:
        item = _field_or_error(catalog, fid, 'rows' if fid in rows else 'columns')
        if not item.group:
            raise ConstructorError('Поле «' + item.name + '» — показатель, в строки и столбцы '
                                   'его поставить нельзя.', code='not_groupable',
                                   extra={'field': fid})
    for fid in measures:
        item = _field_or_error(catalog, fid, 'measures')
        if not item.agg:
            raise ConstructorError('Поле «' + item.name + '» не считается как показатель — '
                                   'поставьте его в строки или столбцы.', code='not_aggregatable',
                                   extra={'field': fid})
        if fid in rows or fid in columns:
            raise ConstructorError('Поле «' + item.name + '» уже стоит в строках или столбцах: '
                                   'в одном отчёте iiko не отдаёт его и разрезом, и показателем.',
                                   code='dim_and_measure', extra={'field': fid})
    include_deleted = payload.get('include_deleted', False)
    if not isinstance(include_deleted, bool):
        raise ConstructorError('include_deleted — true или false.')
    start, end, preset = _parse_period(payload)
    return ReportSpec(catalog.report_type, rows, columns, measures,
                      _parse_filters(payload, catalog), include_deleted, start, end, preset)


# ---------------------------------------------------------------- тело запроса и план

def olap_body(spec: ReportSpec, group_fields: Sequence[str], summary: bool) -> dict:
    """Тело POST /v2/reports/olap (правила 1–3 в докстринге модуля)."""
    filters: Dict[str, dict] = {
        DATE_FIELD[spec.report_type]: {
            'filterType': 'DateRange', 'periodType': 'CUSTOM',
            'from': spec.date_from.isoformat(),
            'to': (spec.date_to + timedelta(days=1)).isoformat(),
        },
    }
    for item in spec.filters + spec.guards():
        filters[item.field] = item.compile()
    return {
        'reportType': spec.report_type,
        'buildSummary': 'true' if summary else 'false',
        'groupByRowFields': list(group_fields),
        'groupByColFields': [],
        'aggregateFields': list(spec.measures),
        'filters': filters,
    }


def _kinds(spec: ReportSpec, catalog: Catalog) -> List[str]:
    return [catalog.get(fid).kind or 'server' for fid in spec.measures]


def plan(spec: ReportSpec, catalog: Catalog, fmt: str) -> List[Tuple[str, List[str], bool]]:
    """[(имя, поля группировки, summary)] — см. «Итоги» в докстринге модуля."""
    server = any(kind != 'sum' for kind in _kinds(spec, catalog))
    if fmt == 'flat':
        return [('main', spec.dims, server)]
    if not server:
        return [('main', spec.dims, False)]
    if not spec.columns:
        return [('main', list(spec.rows), True)]
    if not spec.rows:
        return [('main', list(spec.columns), True)]
    return [('cells', spec.columns + spec.rows, True), ('rows', list(spec.rows), True)]


PURPOSE = {
    'main': 'данные отчёта',
    'cells': 'ячейки, итоги столбцов и групп внутри столбцов',
    'rows': 'колонка «Итого» по строкам и общий итог',
}


# ---------------------------------------------------------------- значения и сортировка

def norm_key(value) -> Any:
    """Значение разреза как ключ: объекты — строкой JSON, числа и строки как есть."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def to_number(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    try:
        number = float(str(value).replace(',', '.'))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def measure_value(value, kind: Optional[str]):
    """Значение показателя из ответа iiko.

    Суммируемые (kind 'sum') — только числа. У остальных iiko изредка отдаёт не число
    (время последней сервисной печати — строка даты): такое значение идёт как есть и
    никогда не складывается.
    """
    number = to_number(value)
    if number is not None or kind == 'sum':
        return number
    if value is None or value == '':
        return None
    return str(value)


def _round(value):
    if isinstance(value, float):
        value = round(value, ROUND_DIGITS)
        return int(value) if value.is_integer() else value
    return value


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a + b


_NATURAL_RE = re.compile(r'(\d+)')
EMPTY_LABEL = '(пусто)'               # null: у строки нет значения поля
BLANK_LABEL = '(пустая строка)'       # "": значение есть, но пустое — iiko отдаёт оба вида


def _natural(text: str) -> tuple:
    # isdecimal, а не isdigit: «²» и «①» — цифры для isdigit, но int() их не читает.
    return tuple((0, int(part)) if part.isdecimal() else (1, part.casefold())
                 for part in _NATURAL_RE.split(text) if part != '')


def is_empty(value) -> bool:
    """Пустое значение разреза: null или пустая строка."""
    return value is None or value == ''


def sort_key(value, item: Optional[Field] = None) -> tuple:
    """Порядок значений разреза: числа по величине, текст «естественно» (2 < 10);
    пустая строка и пусто (null) — в конце, в этом порядке."""
    if value is None:
        return (3,)
    if value == '':
        return (2,)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, value)
    label = item.enum_label(value) if item is not None else None
    return (1, _natural(label or str(value)))


def display_value(value, item: Optional[Field]) -> str:
    """Подпись значения для людей (фильтры в «Как считается», выгрузка)."""
    if value is None:
        return EMPTY_LABEL
    if value == '':
        return BLANK_LABEL
    if item is not None:
        label = item.enum_label(value)
        if label:
            return label
        if item.type == 'DATE' and isinstance(value, str) and len(value) >= 10:
            return value[8:10] + '.' + value[5:7] + '.' + value[0:4]
    return str(value)


# ---------------------------------------------------------------- summary

def summary_index(summary, order: Sequence[str]) -> Dict[Tuple[int, tuple], dict]:
    """Блоки summary -> {(длина префикса, значения префикса): итоги}.

    Берутся только блоки, чьи ключи — ровно префикс order (так их описывает
    документация iiko); полный набор полей — это те же строки data, он не нужен.
    """
    index: Dict[Tuple[int, tuple], dict] = {}
    if not isinstance(summary, list):
        return index
    for block in summary:
        if not isinstance(block, (list, tuple)) or len(block) != 2:
            continue
        keys, values = block
        if not isinstance(keys, dict) or not isinstance(values, dict):
            continue
        length = len(keys)
        if length >= len(order) or set(keys) != set(order[:length]):
            continue
        index[(length, tuple(norm_key(keys.get(fid)) for fid in order[:length]))] = values
    return index


# ---------------------------------------------------------------- сводная таблица

def _field_json(item: Field) -> dict:
    out = {'id': item.id, 'name': item.name, 'type': item.type}
    if item.kind:
        out['kind'] = item.kind
    if item.enum:
        out['enum'] = [list(pair) for pair in item.enum]
    if item.hint:
        out['hint'] = item.hint
    return out


def build_pivot(spec: ReportSpec, catalog: Catalog, results: Dict[str, dict],
                max_leaves: int = PIVOT_MAX_LEAVES, max_cells: int = PIVOT_MAX_CELLS) -> dict:
    """Ответы iiko -> дерево строк с ячейками по столбцам и итогами (см. «Итоги»)."""
    rows_f, cols_f, meas = spec.rows, spec.columns, spec.measures
    kinds = _kinds(spec, catalog)
    count = len(meas)
    main = results.get('cells') or results['main']
    warnings: List[str] = []

    leaves: Dict[tuple, Dict[tuple, list]] = {}
    col_set = set()
    duplicate = False
    for row in main.get('data') or []:
        rk = tuple(norm_key(row.get(fid)) for fid in rows_f)
        ck = tuple(norm_key(row.get(fid)) for fid in cols_f)
        values = [measure_value(row.get(fid), kinds[i]) for i, fid in enumerate(meas)]
        col_set.add(ck)
        cell = leaves.setdefault(rk, {})
        if ck in cell:
            duplicate = True
            previous = cell[ck]
            cell[ck] = [_add(previous[i], values[i]) if kinds[i] == 'sum' else previous[i]
                        for i in range(count)]
        else:
            cell[ck] = values
    if len(leaves) > max_leaves:
        raise ConstructorError(
            'В отчёте ' + '{:,}'.format(len(leaves)).replace(',', ' ') + ' строк — больше, чем '
            'можно показать (' + '{:,}'.format(max_leaves).replace(',', ' ') + '). Сузьте период, '
            'уберите поле из строк или выгрузите отчёт в Excel.', code='too_many_rows',
            extra={'rows': len(leaves), 'limit': max_leaves})
    col_items = [catalog.get(fid) for fid in cols_f]
    row_items = [catalog.get(fid) for fid in rows_f]
    col_keys = sorted(col_set, key=lambda ck: tuple(sort_key(v, col_items[i])
                                                    for i, v in enumerate(ck))) if cols_f else []
    if cols_f and len(col_keys) * max(1, len(leaves)) > max_cells:
        raise ConstructorError(
            'Таблица выйдет ' + str(len(leaves)) + ' строк × ' + str(len(col_keys)) + ' столбцов — '
            'слишком много ячеек. Перенесите поле из столбцов в строки, сузьте период или '
            'выгрузите отчёт в Excel.', code='too_many_cells',
            extra={'rows': len(leaves), 'columns': len(col_keys)})

    if 'cells' in results:
        cells_idx = summary_index(results['cells'].get('summary'), cols_f + rows_f)
        rows_idx = summary_index(results['rows'].get('summary'), rows_f)
        rows_data = {}
        for row in results['rows'].get('data') or []:
            rows_data[tuple(norm_key(row.get(fid)) for fid in rows_f)] = \
                [measure_value(row.get(fid), kinds[i]) for i, fid in enumerate(meas)]
    elif not rows_f:
        cells_idx = summary_index(main.get('summary'), cols_f)
        rows_idx = cells_idx
        rows_data = {}
    else:
        cells_idx = {}
        rows_idx = summary_index(main.get('summary'), rows_f)
        rows_data = {}
    missing = set()

    def server_values(block: Optional[dict], target: list) -> None:
        for i in range(count):
            if kinds[i] == 'sum':
                continue
            value = measure_value(block.get(meas[i]), kinds[i]) if block else None
            if value is None and block is None:
                missing.add(i)
            target[i] = value

    def leaf_values(node: dict, rk: tuple) -> None:
        cells = leaves.get(rk, {})
        if cols_f:
            node['c'] = [cells.get(ck) for ck in col_keys]
        total = [None] * count
        for i in range(count):
            if kinds[i] == 'sum':
                for values in cells.values():
                    total[i] = _add(total[i], values[i])
            elif cols_f and rows_f:
                row_total = rows_data.get(rk)
                if row_total is None:
                    missing.add(i)
                else:
                    total[i] = row_total[i]
            elif cols_f:
                pass
            else:
                values = cells.get(())
                total[i] = values[i] if values else None
        if cols_f and not rows_f and cells:
            server_values(rows_idx.get((0, ())), total)
        node['t'] = total

    def group_values(node: dict, depth: int, path: tuple) -> None:
        children = node['ch']
        if cols_f:
            cells = []
            for col, ck in enumerate(col_keys):
                child_cells = [child['c'][col] for child in children
                               if child['c'][col] is not None]
                if not child_cells:
                    # В этом столбце у группы нет ни одной строки — «нет данных», а не
                    # «iiko не вернул итог»: блока summary для пустой пары и не бывает.
                    cells.append(None)
                    continue
                values = [None] * count
                for i in range(count):
                    if kinds[i] == 'sum':
                        for child_cell in child_cells:
                            values[i] = _add(values[i], child_cell[i])
                server_values(cells_idx.get((len(cols_f) + depth, ck + path)), values)
                cells.append(values)
            node['c'] = cells
        total = [None] * count
        for i in range(count):
            if kinds[i] == 'sum':
                for child in children:
                    total[i] = _add(total[i], child['t'][i])
        if children:
            server_values(rows_idx.get((depth, path)), total)
        node['t'] = total

    root: dict = {}
    if not rows_f:
        leaf_values(root, ())
    else:
        root['ch'] = []
        nodes = {(): root}
        ordered = sorted(leaves, key=lambda rk: tuple(sort_key(v, row_items[i])
                                                      for i, v in enumerate(rk)))
        for rk in ordered:
            for depth in range(1, len(rows_f) + 1):
                path = rk[:depth]
                if path in nodes:
                    continue
                node = {'k': rk[depth - 1]}
                if depth < len(rows_f):
                    node['ch'] = []
                nodes[path[:-1]]['ch'].append(node)
                nodes[path] = node
        # Снизу вверх: сначала листья, потом группы от глубоких к корню.
        for rk in ordered:
            leaf_values(nodes[rk], rk)
        group_paths = sorted((path for path in nodes if len(path) < len(rows_f)),
                             key=len, reverse=True)
        for path in group_paths:
            group_values(nodes[path], len(path), path)

    if duplicate:
        warnings.append('iiko вернул повторяющиеся строки: суммы сложены, итоги iiko взяты '
                        'из первой строки.')
    for i in sorted(missing):
        warnings.append('Итоги по «' + catalog.get(meas[i]).name + '» iiko не вернул — в строках '
                        'итогов прочерк (сумма строк для этого показателя была бы неверной).')
    grand_block = rows_idx.get((0, ())) if rows_f or not cols_f else cells_idx.get((0, ()))
    if grand_block:
        for i in range(count):
            if kinds[i] != 'sum':
                continue
            iiko_total = to_number(grand_block.get(meas[i]))
            local = root['t'][i]
            if iiko_total is not None and local is not None and \
                    abs(iiko_total - local) > max(0.01, abs(iiko_total) * 1e-9):
                warnings.append('Итог iiko по «' + catalog.get(meas[i]).name + '» (' +
                                str(_round(iiko_total)) + ') не совпал с суммой строк (' +
                                str(_round(local)) + ').')
    _round_tree(root)
    if len(spec.dims) > RECOMMENDED_FIELDS:
        warnings.append('Полей в строках и столбцах больше ' + str(RECOMMENDED_FIELDS) +
                        ' — iiko советует не больше, отчёт может строиться дольше.')
    return {
        'format': 'pivot',
        'fields': {'rows': [_field_json(item) for item in row_items],
                   'columns': [_field_json(item) for item in col_items],
                   'measures': [_field_json(catalog.get(fid)) for fid in meas]},
        'columns': [list(ck) for ck in col_keys],
        'tree': root,
        'leaf_count': len(leaves) if rows_f else 0,
        'warnings': warnings,
    }


def _round_tree(node: dict) -> None:
    stack = [node]
    while stack:
        current = stack.pop()
        if 't' in current:
            current['t'] = [_round(v) for v in current['t']]
        if current.get('c') is not None:
            current['c'] = [None if cell is None else [_round(v) for v in cell]
                            for cell in current['c']]
        stack.extend(current.get('ch') or [])


# ---------------------------------------------------------------- плоский список

@dataclass
class FlatOptions:
    sort: Optional[str] = None
    order: str = 'desc'
    limit: int = FLAT_DEFAULT_LIMIT
    having: List[Tuple[str, str, float]] = field(default_factory=list)


def parse_flat_options(payload: dict, spec: ReportSpec) -> FlatOptions:
    options = FlatOptions()
    sort = payload.get('sort')
    if sort not in (None, ''):
        if sort not in spec.dims and sort not in spec.measures:
            raise ConstructorError('sort: поле из rows, columns или measures, а не «' +
                                   str(sort) + '».')
        options.sort = sort
        options.order = 'desc' if sort in spec.measures else 'asc'
    order = payload.get('order')
    if order not in (None, ''):
        if order not in SORT_ORDERS:
            raise ConstructorError('order: asc или desc.')
        options.order = order
    limit = payload.get('limit')
    if limit not in (None, ''):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= FLAT_MAX_LIMIT:
            raise ConstructorError('limit: целое от 1 до ' + str(FLAT_MAX_LIMIT) + '.')
        options.limit = limit
    having = payload.get('having') or []
    if not isinstance(having, list) or len(having) > 5:
        raise ConstructorError('having: список до 5 условий {measure, op, value}.')
    for index, cond in enumerate(having):
        where = 'having[' + str(index) + ']'
        if not isinstance(cond, dict):
            raise ConstructorError(where + ': нужен объект {measure, op, value}.')
        measure = cond.get('measure')
        if measure not in spec.measures:
            raise ConstructorError(where + ': measure — один из показателей отчёта.')
        op = cond.get('op')
        if op not in HAVING_OPS:
            raise ConstructorError(where + ': op — один из ' + ' '.join(HAVING_OPS) + '.')
        options.having.append((measure, op, _number(cond.get('value'), where + '.value')))
    return options


def _compare(value, op: str, target: float) -> bool:
    if value is None or isinstance(value, str):
        return False
    return {'>': value > target, '>=': value >= target, '<': value < target,
            '<=': value <= target, '=': value == target, '!=': value != target}[op]


def build_flat(spec: ReportSpec, catalog: Catalog, result: dict, options: FlatOptions) -> dict:
    """Ответ iiko -> список строк (разрезы, затем показатели) с итогами по всем строкам."""
    dims, meas = spec.dims, spec.measures
    kinds = _kinds(spec, catalog)
    dim_items = [catalog.get(fid) for fid in dims]
    rows = []
    for row in result.get('data') or []:
        rows.append([norm_key(row.get(fid)) for fid in dims] +
                    [measure_value(row.get(fid), kinds[i]) for i, fid in enumerate(meas)])
    grand = summary_index(result.get('summary'), dims).get((0, ()))
    totals = {}
    for i, fid in enumerate(meas):
        if kinds[i] == 'sum':
            total = None
            for row in rows:
                total = _add(total, row[len(dims) + i])
            totals[fid] = _round(total)
        else:
            totals[fid] = _round(measure_value(grand.get(fid), kinds[i])) if grand else None
    matched = rows
    for measure, op, target in options.having:
        position = len(dims) + meas.index(measure)
        matched = [row for row in matched if _compare(row[position], op, target)]
    if options.sort:
        if options.sort in meas:
            position = len(dims) + meas.index(options.sort)
            present = [row for row in matched if isinstance(row[position], (int, float))]
            empty = [row for row in matched if not isinstance(row[position], (int, float))]
            present.sort(key=lambda row: row[position], reverse=options.order == 'desc')
            matched = present + empty
        else:
            # Пустые значения — в конце и при обратном порядке, как у показателей.
            position = dims.index(options.sort)
            present = [row for row in matched if not is_empty(row[position])]
            empty = [row for row in matched if is_empty(row[position])]
            present.sort(key=lambda row: sort_key(row[position], dim_items[position]),
                         reverse=options.order == 'desc')
            empty.sort(key=lambda row: sort_key(row[position], dim_items[position]))
            matched = present + empty
    else:
        matched = sorted(matched, key=lambda row: tuple(sort_key(row[i], dim_items[i])
                                                        for i in range(len(dims))))
    limited = matched[:options.limit]
    out_rows = []
    for row in limited:
        values = []
        for i, value in enumerate(row):
            if i < len(dims):
                label = dim_items[i].enum_label(value)
                values.append(label if label else value)
            else:
                values.append(_round(value))
        out_rows.append(values)
    missing = [catalog.get(fid).name for i, fid in enumerate(meas)
               if kinds[i] != 'sum' and totals[fid] is None and rows]
    warnings = ['Итог по «' + name + '» iiko не вернул.' for name in missing]
    return {
        'format': 'flat',
        'columns': ([dict(_field_json(item), role='dim') for item in dim_items] +
                    [dict(_field_json(catalog.get(fid)), role='measure') for fid in meas]),
        'rows': out_rows,
        'row_count': len(rows),
        'matched': len(matched),
        'returned': len(out_rows),
        'truncated': len(matched) > len(out_rows),
        'totals': totals,
        'warnings': warnings,
    }


# ---------------------------------------------------------------- исполнение

def describe_filter(item: FilterSpec, catalog: Catalog, automatic: bool = False) -> str:
    """«Со склада: Лиговский, Варшавская» — фильтр словами для «Как считается»."""
    spec_field = catalog.get(item.field)
    name = spec_field.name if spec_field else item.field
    if item.op in ('in', 'not_in'):
        shown = [display_value(value, spec_field) for value in item.values[:12]]
        text = ', '.join(shown) + (' и ещё ' + str(len(item.values) - 12)
                                   if len(item.values) > 12 else '')
        text = name + ': ' + ('кроме ' if item.op == 'not_in' else '') + text
    else:
        low = ('от ' if item.include_low else 'больше ') + str(item.low)
        high = ('до ' if item.include_high else 'меньше ') + str(item.high)
        text = name + ': ' + low + ' ' + high
    return text + (' (автоматически)' if automatic else '')


def execute(payload: dict, fmt: str) -> Tuple[ReportSpec, Catalog, List[tuple], List[dict], Dict[str, dict]]:
    """Заявка -> (заявка, каталог, план, тела запросов, ответы iiko по именам плана)."""
    report_type = parse_report_type(payload)
    catalog = get_catalog(report_type)
    spec = parse_spec(payload, catalog)
    steps = plan(spec, catalog, fmt)
    bodies = [olap_body(spec, group_fields, summary) for _name, group_fields, summary in steps]
    answers = fetch_olap(bodies)
    return spec, catalog, steps, bodies, {name: answer for (name, _g, _s), answer
                                          in zip(steps, answers)}


def report_meta(spec: ReportSpec, catalog: Catalog, steps, bodies, answers) -> dict:
    kinds = _kinds(spec, catalog)
    # Ответы серии всегда из одного похода в iiko (core/olap_client.py, «КЭШ ОТВЕТОВ»);
    # на всякий случай «данные на» — по самому старому, «из кэша» — если хоть один.
    fetched = sorted({answer.get('fetched_at') for answer in answers.values()
                      if answer.get('fetched_at')})
    meta = {
        'report_type': spec.report_type,
        'title': REPORT_TYPE_TITLES[spec.report_type],
        'date_field': catalog.date_field,
        'date_field_name': (catalog.get(catalog.date_field).name
                            if catalog.get(catalog.date_field) else catalog.date_field),
        'date_from': spec.date_from.isoformat(),
        'date_to': spec.date_to.isoformat(),
        'date_to_exclusive': (spec.date_to + timedelta(days=1)).isoformat(),
        'period': spec.period,
        'period_title': PERIOD_TITLES.get(spec.period) if spec.period else None,
        'include_deleted': spec.include_deleted,
        'filters': [describe_filter(item, catalog) for item in spec.filters] +
                   [describe_filter(item, catalog, automatic=True) for item in spec.guards()],
        'totals': {'sum': [fid for i, fid in enumerate(spec.measures) if kinds[i] == 'sum'],
                   'server': [fid for i, fid in enumerate(spec.measures) if kinds[i] != 'sum']},
        'requests': [{'name': name, 'purpose': PURPOSE[name], 'body': body}
                     for (name, _g, _s), body in zip(steps, bodies)],
        'fetched_at': fetched[0] if fetched else None,
        'cached': any(answer.get('cached') for answer in answers.values()),
        'catalog_source': catalog.source,
        'config': spec.config(),
        'generated_at': msk_time.now().strftime('%Y-%m-%d %H:%M'),
    }
    if catalog.source != 'live':
        meta['catalog_note'] = ('Каталог полей из запасной копии (' + catalog.source + ', ' +
                                catalog.fetched_at + '): iiko не отдал живой список полей.')
    return meta


def run_report(payload: dict) -> dict:
    """Построить отчёт: format 'pivot' (сводная для страницы) или 'flat' (список строк)."""
    fmt = str(payload.get('format') or 'flat')
    if fmt not in FORMATS:
        raise ConstructorError('format: flat или pivot.')
    if fmt == 'flat':
        # Опции списка проверяются до похода в iiko: ошибка в sort не должна стоить запроса.
        report_type = parse_report_type(payload)
        parse_flat_options(payload, parse_spec(payload, get_catalog(report_type)))
    spec, catalog, steps, bodies, answers = execute(payload, fmt)
    if fmt == 'pivot':
        out = build_pivot(spec, catalog, answers)
    else:
        out = build_flat(spec, catalog, answers['main'], parse_flat_options(payload, spec))
    out['meta'] = report_meta(spec, catalog, steps, bodies, answers)
    return out


# ---------------------------------------------------------------- значения поля

def field_values(report_type: str, field_id: str, payload: dict, q: str = '',
                 limit: int = VALUES_MAX) -> dict:
    """Значения поля за период — для списка галочек в фильтре.

    Лёгкий запрос: одна группировка по полю и самый дешёвый показатель. Фильтр
    «не удалено» не ставится — в списке должны быть и значения удалённых позиций.
    У перечислений к найденным кодам добавляются все известные коды с русскими
    названиями (их можно выбрать, даже если за период их не было).
    """
    catalog = get_catalog(report_type)
    item = _field_or_error(catalog, field_id, 'field')
    if not item.group:
        raise ConstructorError('У поля «' + item.name + '» нет списка значений: это показатель.')
    start, end, preset = _parse_period(payload)
    measure = next((fid for fid in VALUES_MEASURES[report_type]
                    if catalog.get(fid) and catalog.get(fid).agg and not catalog.get(fid).blocked),
                   None)
    if measure is None:
        raise ConstructorError('Не нашлось показателя для списка значений.', status=502)
    body = {
        'reportType': report_type, 'buildSummary': 'false', 'groupByRowFields': [field_id],
        'groupByColFields': [], 'aggregateFields': [measure],
        'filters': {DATE_FIELD[report_type]: {
            'filterType': 'DateRange', 'periodType': 'CUSTOM', 'from': start.isoformat(),
            'to': (end + timedelta(days=1)).isoformat()}},
    }
    answer = fetch_olap([body])[0]
    found = set()
    has_empty = False
    for row in answer.get('data') or []:
        value = norm_key(row.get(field_id))
        if value is None:
            has_empty = True        # null — отдельная галочка «(пусто)» на странице
        else:
            found.add(value)        # пустая строка — обычное значение «(пустая строка)»
    if item.enum:
        found |= {code for code, _label in item.enum}
    values = sorted(found, key=lambda v: sort_key(v, item))
    query = (q or '').strip().casefold()
    out = []
    for value in values:
        label = BLANK_LABEL if value == '' else item.enum_label(value) or str(value)
        if query and query not in label.casefold() and query not in str(value).casefold():
            continue
        out.append({'value': value, 'label': label})
    return {
        'report_type': report_type, 'field': field_id, 'name': item.name, 'type': item.type,
        'date_from': start.isoformat(), 'date_to': end.isoformat(),
        'values': out[:limit], 'total': len(out), 'truncated': len(out) > limit,
        'has_empty': has_empty, 'fetched_at': answer.get('fetched_at'),
    }


# ---------------------------------------------------------------- отчёты iikoOffice

_presets_cache: Dict[str, Any] = {'stamp': 0.0, 'data': None}
_presets_lock = threading.Lock()


def _preset_period(flt: dict) -> Tuple[Optional[dict], Optional[str]]:
    period_type = str(flt.get('periodType') or 'CUSTOM').upper()
    if period_type in IIKO_PERIOD_TYPES:
        return {'preset': IIKO_PERIOD_TYPES[period_type]}, None
    if period_type == 'CUSTOM':
        try:
            start = _parse_day(flt.get('from'), 'from')
            end = _parse_day(flt.get('to'), 'to')
        except ConstructorError:
            return None, 'период отчёта не распознан — выберите его сами'
        if not flt.get('includeHigh', False):
            end = end - timedelta(days=1)
        if end < start:
            end = start
        return {'from': start.isoformat(), 'to': end.isoformat()}, None
    return None, 'период «' + period_type + '» не переносится — выберите его сами'


def convert_preset(preset: dict) -> dict:
    """Сохранённый отчёт iikoOffice -> конфигурация конструктора (фильтры — как есть)."""
    report_type = str(preset.get('reportType') or '').upper()
    date_field = DATE_FIELD.get(report_type)
    filters, notes, period = [], [], None
    for fid, flt in (preset.get('filters') or {}).items():
        if not isinstance(flt, dict):
            continue
        kind = flt.get('filterType')
        if kind in ('IncludeValues', 'ExcludeValues'):
            filters.append({'field': fid, 'op': 'in' if kind == 'IncludeValues' else 'not_in',
                            'values': list(flt.get('values') or [])})
        elif kind == 'Range':
            filters.append({'field': fid, 'op': 'range', 'from': flt.get('from'),
                            'to': flt.get('to'), 'include_low': bool(flt.get('includeLow', True)),
                            'include_high': bool(flt.get('includeHigh', False))})
        elif kind == 'DateRange' and fid == date_field:
            period, note = _preset_period(flt)
            if note:
                notes.append(note)
        elif kind == 'DateRange':
            filters.append({'field': fid, 'op': 'date_range', 'from': flt.get('from'),
                            'to': flt.get('to'), 'include_low': bool(flt.get('includeLow', True)),
                            'include_high': bool(flt.get('includeHigh', False))})
        else:
            notes.append('фильтр по «' + str(fid) + '» (' + str(kind) + ') не перенесён')
    supported = report_type in REPORT_TYPES
    if not supported:
        notes.append('тип отчёта «' + report_type + '» конструктор не строит')
    return {
        'id': str(preset.get('id') or ''),
        'name': str(preset.get('name') or 'Без названия'),
        'report_type': report_type,
        'supported': supported,
        'config': {
            'report_type': report_type,
            'rows': [str(x) for x in preset.get('groupByRowFields') or []],
            'columns': [str(x) for x in preset.get('groupByColFields') or []],
            'measures': [str(x) for x in preset.get('aggregateFields') or []],
            'filters': filters,
            # Фильтры отчёта iikoOffice переносятся ровно как есть: если в нём нет
            # фильтра удалённых, iikoOffice их показывает — и конструктор тоже.
            'include_deleted': True,
            'period': period,
        },
        'notes': notes,
    }


def iiko_presets(refresh: bool = False) -> dict:
    """Отчёты, сохранённые в iikoOffice (GET /v2/reports/olap/presets), кэш PRESETS_TTL_S."""
    with _presets_lock:
        if not refresh and _presets_cache['data'] is not None and \
                time.time() - _presets_cache['stamp'] < PRESETS_TTL_S:
            return _presets_cache['data']
    with open_session() as session:
        raw = session.get_json('/v2/reports/olap/presets')
    if not isinstance(raw, list):
        raise IikoError('iiko вернул список сохранённых отчётов не в том формате.', 502)
    presets = [convert_preset(item) for item in raw if isinstance(item, dict)]
    presets.sort(key=lambda p: (not p['supported'], p['report_type'], p['name'].casefold()))
    data = {'presets': presets, 'fetched_at': msk_time.now().strftime('%Y-%m-%d %H:%M')}
    with _presets_lock:
        _presets_cache.update(stamp=time.time(), data=data)
    return data


def reset_presets_cache() -> None:
    with _presets_lock:
        _presets_cache.update(stamp=0.0, data=None)

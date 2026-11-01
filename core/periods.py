"""Периоды по стандарту сайта (docs/period-standard.md) — одна модель для всех страниц.

Период — это date_from и date_to, обе даты ВКЛЮЧИТЕЛЬНО, в учётных днях бара (рабочие
сутки до 06:00 МСК, core/msk_time.business_today). Шаг (день, неделя, месяц, квартал, год)
определяется по границам: 1–31 октября — месяц, понедельник–воскресенье — неделя; иначе —
свой период (custom). Неделя — ISO, с понедельника.

Три даты страницы (page_config):
- today — текущий учётный день;
- last_full_day — последний ПОЛНЫЙ день данных: у живых данных iiko — вчера, у витрины с
  ночной загрузкой — min(последний день с чеками, вчера);
- max_date — последний день, который можно выбрать: у живых данных — сегодня (неполный день
  уже виден), у витрины — last_full_day.

Состояние периода: complete — весь не позже last_full_day; partial — начался не позже
max_date, а кончается позже last_full_day («идёт»); future — начинается позже max_date.

Правила открытия страницы (стандарт, раздел 3): last_closed — последний закрытый период
шага (отчёты), current — период, где лежит max_date (рабочие страницы), last_days — последние
N полных дней (ABC/XYZ).

Подписи — те же, что у static/js/shared/period/period_core.js: обе стороны проверяются
одним набором примеров (tests/fixtures/period_labels.json).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from core import msk_time

STEPS = ('day', 'week', 'month', 'quarter', 'year')
CUSTOM = 'custom'

MONTHS_NOMINATIVE = ('январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август',
                     'сентябрь', 'октябрь', 'ноябрь', 'декабрь')
MONTHS_GENITIVE = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
                   'сентября', 'октября', 'ноября', 'декабря')
MONTHS_SHORT = ('янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек')
QUARTER_ROMAN = ('I', 'II', 'III', 'IV')
# Тире диапазона — короткое с пробелами («26 окт – 1 ноя 2026»), одно на сайт.
DASH = ' – '


class PeriodError(ValueError):
    """Неверный период в запросе — текст для ответа 400."""


@dataclass(frozen=True)
class Period:
    step: str
    start: date
    end: date

    @property
    def key(self):
        """'YYYY-MM-DD_YYYY-MM-DD' — как ключи /api/weeks и комментариев дашборда."""
        return self.start.isoformat() + '_' + self.end.isoformat()

    @property
    def days(self):
        return (self.end - self.start).days + 1

    def title(self):
        return period_title(self.step, self.start, self.end)

    def state(self, last_full_day, max_date=None):
        """complete / partial / future относительно последнего полного дня данных."""
        return period_state(self, last_full_day, max_date)

    def to_meta(self, last_full_day, max_date=None):
        """Описание для ответа API (meta.period): страница берёт подписи отсюда."""
        state = self.state(last_full_day, max_date)
        return {
            'key': self.key, 'step': self.step,
            'date_from': self.start.isoformat(), 'date_to': self.end.isoformat(),
            'title': self.title(), 'sub': period_sub(self, last_full_day, max_date),
            'short': period_short(self.step, self.start, self.end),
            'state': state, 'cutoff': cutoff_of(self, last_full_day, max_date),
        }


# ---------------------------------------------------------------- построение

def _month_end(year, month):
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def period_for(step, anchor):
    """Период шага, где лежит anchor (date). Неизвестный шаг — один день."""
    if step == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        return Period('week', start, start + timedelta(days=6))
    if step == 'month':
        return Period('month', anchor.replace(day=1), _month_end(anchor.year, anchor.month))
    if step == 'quarter':
        first = (anchor.month - 1) // 3 * 3 + 1
        return Period('quarter', date(anchor.year, first, 1), _month_end(anchor.year, first + 2))
    if step == 'year':
        return Period('year', date(anchor.year, 1, 1), date(anchor.year, 12, 31))
    return Period('day', anchor, anchor)


def detect_step(start, end):
    """Шаг по натуральным границам или CUSTOM."""
    for step in STEPS:
        p = period_for(step, start)
        if p.start == start and p.end == end:
            return step
    return CUSTOM


def from_bounds(start, end):
    """Период по границам: шаг определяется сам, порядок дат нормализуется."""
    if start > end:
        start, end = end, start
    return Period(detect_step(start, end), start, end)


def shift(period, n):
    """Сдвиг на n периодов своего шага; свой период — на собственную длину."""
    if period.step == 'day':
        return period_for('day', period.start + timedelta(days=n))
    if period.step == 'week':
        return period_for('week', period.start + timedelta(days=7 * n))
    if period.step in ('month', 'quarter'):
        months = n * (3 if period.step == 'quarter' else 1)
        index = period.start.year * 12 + period.start.month - 1 + months
        return period_for(period.step, date(index // 12, index % 12 + 1, 1))
    if period.step == 'year':
        return period_for('year', date(period.start.year + n, 1, 1))
    delta = timedelta(days=period.days * n)
    return Period(CUSTOM, period.start + delta, period.end + delta)


def last_closed(step, last_full_day):
    """Последний закрытый период шага: целиком не позже последнего полного дня."""
    p = period_for(step, last_full_day)
    return p if p.end <= last_full_day else period_for(step, p.start - timedelta(days=1))


def current(step, max_date):
    """Текущий период шага — где лежит последний доступный день (у живых данных — сегодня)."""
    return period_for(step, max_date)


def last_days(n, last_full_day):
    """Последние n полных дней: ровно n дат, последняя — последний полный день."""
    return from_bounds(last_full_day - timedelta(days=n - 1), last_full_day)


# ---------------------------------------------------------------- состояние

def period_state(period, last_full_day, max_date=None):
    max_date = max_date or last_full_day
    if period.start > max_date:
        return 'future'
    if period.end <= last_full_day:
        return 'complete'
    return 'partial'


def cutoff_of(period, last_full_day, max_date=None):
    """По какой день в периоде есть данные (ISO) или None у будущего."""
    max_date = max_date or last_full_day
    if period.start > max_date:
        return None
    return min(period.end, max_date).isoformat()


# ---------------------------------------------------------------- подписи

def _range_title(start, end):
    if start.year == end.year:
        if start.month == end.month:
            return (str(start.day) + DASH + str(end.day) + ' ' + MONTHS_SHORT[start.month - 1]
                    + ' ' + str(start.year))
        return (str(start.day) + ' ' + MONTHS_SHORT[start.month - 1] + DASH + str(end.day) + ' '
                + MONTHS_SHORT[end.month - 1] + ' ' + str(end.year))
    return (str(start.day) + ' ' + MONTHS_SHORT[start.month - 1] + ' ' + str(start.year) + DASH
            + str(end.day) + ' ' + MONTHS_SHORT[end.month - 1] + ' ' + str(end.year))


def period_title(step, start, end):
    """Название периода — всегда с годом: «Октябрь 2026», «26 окт – 1 ноя 2026»."""
    if step == 'day':
        return str(start.day) + ' ' + MONTHS_GENITIVE[start.month - 1] + ' ' + str(start.year)
    if step == 'month':
        return MONTHS_NOMINATIVE[start.month - 1].capitalize() + ' ' + str(start.year)
    if step == 'quarter':
        return QUARTER_ROMAN[(start.month - 1) // 3] + ' квартал ' + str(start.year)
    if step == 'year':
        return str(start.year)
    return _range_title(start, end)


def period_short(step, start, end):
    """Короткое название для заголовков карточек: «окт 26», «26.10–01.11»."""
    if step == 'day':
        return start.strftime('%d.%m')
    if step == 'month':
        return MONTHS_SHORT[start.month - 1] + ' ' + start.strftime('%y')
    if step == 'quarter':
        return QUARTER_ROMAN[(start.month - 1) // 3] + ' кв ' + start.strftime('%y')
    if step == 'year':
        return str(start.year)
    return start.strftime('%d.%m') + '–' + end.strftime('%d.%m')


def plural_days(n):
    abs_n = abs(n) % 100
    last = abs_n % 10
    if 10 < abs_n < 20:
        return 'дней'
    if last == 1:
        return 'день'
    if 2 <= last <= 4:
        return 'дня'
    return 'дней'


def period_sub(period, last_full_day, max_date=None):
    """Вторая строка: номер недели или длина своего периода и «идёт, по ДД.ММ»."""
    parts = []
    if period.step == 'week':
        parts.append('неделя ' + str(period.start.isocalendar()[1]))
    elif period.step == CUSTOM:
        parts.append(str(period.days) + ' ' + plural_days(period.days))
    state = period_state(period, last_full_day, max_date)
    if state == 'partial':
        parts.append('идёт, по ' + date.fromisoformat(
            cutoff_of(period, last_full_day, max_date)).strftime('%d.%m'))
    elif state == 'future':
        parts.append('ещё не начался')
    return ' · '.join(parts)


# ---------------------------------------------------------------- запрос и страница

def _parse_iso(raw, name):
    try:
        return date.fromisoformat(str(raw).strip())
    except (TypeError, ValueError):
        raise PeriodError(name + ' — дата YYYY-MM-DD, получено: ' + str(raw)[:40])


def parse_period(args, default=None):
    """Период из параметров запроса: date_from и date_to (включительно); иначе default.

    Синоним: key / period_key = 'YYYY-MM-DD_YYYY-MM-DD' (ключ /api/weeks). Неверные даты
    или одна из двух — PeriodError (ответ 400). Порядок дат нормализуется.
    """
    raw_from, raw_to = args.get('date_from'), args.get('date_to')
    if not raw_from and not raw_to:
        key = args.get('key') or args.get('period_key')
        if key:
            parts = str(key).split('_')
            if len(parts) != 2:
                raise PeriodError('key — YYYY-MM-DD_YYYY-MM-DD, получено: ' + str(key)[:40])
            raw_from, raw_to = parts
    if not raw_from and not raw_to:
        return default
    if not raw_from or not raw_to:
        raise PeriodError('Нужны обе даты: date_from и date_to')
    return from_bounds(_parse_iso(raw_from, 'date_from'), _parse_iso(raw_to, 'date_to'))


def page_config(live=True, last_full_day=None, data_start=None, today=None):
    """Даты для страницы (window.*_PERIOD): today, last_full_day, max_date, data_start.

    live=True — живые данные iiko: сегодняшний неполный день виден, последний полный — вчера.
    live=False — витрина с ночной загрузкой: передайте last_full_day (min(последний день с
    данными, вчера)); выбрать можно только по него.
    """
    today = today or msk_time.business_today()
    yesterday = today - timedelta(days=1)
    full = min(last_full_day, yesterday) if last_full_day else yesterday
    return {
        'today': today.isoformat(),
        'last_full_day': full.isoformat(),
        'max_date': (today if live else full).isoformat(),
        'data_start': data_start.isoformat() if data_start else None,
    }

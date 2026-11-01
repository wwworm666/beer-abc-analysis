"""Старые ссылки «?month=YYYY-MM» на страницах, перешедших на полосу «Бар и период».

Что это: контент-план и отзывы (план единого виджета, этап 5 —
docs/planning/period-widget-rollout.md) берут месяц и период из общей полосы сайта
(core/scope.py), а период в адресе — ?date_from=&date_to= (стандарт периодов, раздел 6).
Ссылки, которые уже разосланы и живут вне сайта (бот, Telegram, закладки, агент контента),
несут ?month=YYYY-MM. Маршрут страницы отвечает на них 302 на тот же адрес, где month заменён
датами этого месяца: полоса рисуется сервером сразу на нём, а остальные параметры (?open=,
?state=, ?status=, ?origin=…) сохраняются.

Правило (month_link_query):
    ?month=2026-10&open=m1                 -> ?open=m1&date_from=2026-10-01&date_to=2026-10-31
    ?month=2026-10&date_from=…&date_to=…   -> month убирается: период из ссылки главнее
    ?month=мусор                           -> month убирается: страница откроется по общему выбору
    ?month=all (keep=('all',) у отзывов)   -> без перевода: это показ «за всё время», его
                                              понимает страница (static/js/guest_hub/reviews.js)
    без month                              -> None: переводить нечего
Месяц — календарный, обе даты включительно (core/periods.period_for).
"""
import re
from datetime import date
from urllib.parse import urlencode

from core import periods

MONTH_RE = re.compile(r'^(\d{4})-(0[1-9]|1[0-2])$')


def _pairs(args):
    """Все пары (ключ, значение) параметров: у MultiDict запроса — с повторами."""
    try:
        return list(args.items(multi=True))
    except TypeError:          # обычный dict (тесты)
        return list(args.items())


def month_link_query(args, keep=()):
    """Строка запроса для 302 со старой ссылки или None, если переводить нечего.

    args — request.args; keep — значения month, которые страница понимает сама (у отзывов —
    'all'). Пустая строка — после перевода параметров не осталось (адрес без «?»).
    """
    raw = args.get('month')
    if raw is None:
        return None
    raw = str(raw).strip()
    if raw in keep:
        return None
    pairs = [(k, v) for k, v in _pairs(args) if k != 'month']
    match = MONTH_RE.match(raw)
    if match and not (args.get('date_from') or args.get('date_to')):
        month = periods.period_for('month', date(int(match.group(1)), int(match.group(2)), 1))
        pairs += [('date_from', month.start.isoformat()), ('date_to', month.end.isoformat())]
    return urlencode(pairs)


def redirect_target(path, args, keep=()):
    """Адрес для 302 (путь + новая строка запроса) или None."""
    query = month_link_query(args, keep)
    if query is None:
        return None
    return path + ('?' + query if query else '')

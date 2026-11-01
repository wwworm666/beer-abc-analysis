"""Общий выбор бара и периода на весь сайт — полоса «Бар и период».

План единого виджета: docs/planning/period-widget-rollout.md (разделы 3.5–3.6); стандарт
периодов — docs/period-standard.md. Решения владельца 2026-11-01:
- бар и период — один выбор на весь сайт: выбрал на любой странице — все открываются с ним;
- период помнится час, у каждого пользователя свой (Р1); бар — пока не сменишь;
- без выбора — текущий период шага страницы (Р2): сегодня, эта неделя или этот месяц;
- страница «только месяц» показывает месяц выбранного периода (Р3, periods.month_of) и пишет
  это в полосе, но общий выбор не меняет (показ — не выбор).

Хранение — cookie браузера (не только память страницы: сервер сразу рисует полосу с выбором —
без мигания и с ровной анимацией перехода между страницами):
- kultura_period = '<номер пользователя>:<YYYY-MM-DD>_<YYYY-MM-DD>', срок PERIOD_TTL_SECONDS;
  срок продлевается при каждом открытии страницы с полосой (static/js/shared/period/scope.js);
- kultura_bar = '<номер пользователя>:<ключ бара|all>', срок BAR_TTL_SECONDS;
- kultura_bar_single = '<номер пользователя>:<ключ бара>' — последний бар, выбранный на странице
  «по одному бару» (склад, кран бара, фиды): её показывает такая страница, когда на сайте выбраны
  все бары (ответ Р4), с подписью в полосе.
Номер пользователя в значении: на общем компьютере чужой выбор не подхватывается.

Порядок источников при открытии страницы: ссылка (?date_from=&date_to=&bar=) → выбор из
cookie → правило страницы (page_default).

Шаблон страницы объявляет полосу до общего меню:
    {% set strip = kultura_strip(mode='report', step='week') %}
    {% include 'shared/nav.html' %}
shared/nav.html рисует templates/shared/scope_strip.html, если strip задан.
"""

from datetime import date
from urllib.parse import unquote

from flask import request

from core import periods
from core.venues_config import ALL_BARS_HINT, ALL_BARS_LABEL, SITE_BARS, bar_key, site_bar

COOKIE_PERIOD = 'kultura_period'
COOKIE_BAR = 'kultura_bar'
COOKIE_BAR_SINGLE = 'kultura_bar_single'
# Период помнится час (ответ владельца Р1, 2026-11-01); срок продлевается при открытии страницы.
PERIOD_TTL_SECONDS = 3600
# Бар — пока не сменишь: год, чтобы браузер не выбросил cookie раньше.
BAR_TTL_SECONDS = 365 * 24 * 3600

# report — ровно выбранный период; monthly — месяц выбранного периода; now — «на сейчас».
MODES = ('report', 'monthly', 'now')
DEFAULT_STEPS = ['day', 'week', 'month', 'year', 'custom']
# Правило открытия по шагу страницы (ответ Р2): текущий период шага; last30 — ABC/XYZ
# (XYZ нужно не меньше трёх недель); last_closed_month — ежемесячный отчёт (только закрытые).
PAGE_STEPS = ('day', 'week', 'month', 'year', 'last30', 'last_closed_month')


def _owned(raw, user_id):
    """Значение cookie '<номер>:<значение>' этого пользователя или None (чужое, пустое, мусор).

    Страница пишет значение через encodeURIComponent (двоеточие приходит как %3A) — раскодируем.
    """
    if not raw or user_id is None:
        return None
    owner, sep, value = unquote(str(raw)).partition(':')
    if not sep or owner != str(user_id) or not value:
        return None
    return value


def read_bar(cookies, user_id):
    """Бар из cookie: ключ, '' — вся сеть, None — выбора нет или он чужой."""
    value = _owned(cookies.get(COOKIE_BAR), user_id)
    return None if value is None else bar_key(value)


def read_bar_single(cookies, user_id):
    """Последний бар страниц «по одному бару» (ответ Р4): ключ или None (не выбирали, чужой)."""
    value = _owned(cookies.get(COOKIE_BAR_SINGLE), user_id)
    key = None if value is None else bar_key(value)
    return key or None


def bars_client():
    """Таблица баров для страницы: ключ, имя, короткое имя, имя iiko, bar1…bar4."""
    return [{'key': b['key'], 'name': b['name'], 'short': b['short'], 'iiko_name': b['iiko_name'],
             'bar_id': b['bar_id']} for b in SITE_BARS]


def read_period(cookies, user_id):
    """Период из cookie или None (нет, чужой, истёк — браузер его уже выбросил, неверный)."""
    value = _owned(cookies.get(COOKIE_PERIOD), user_id)
    if value is None:
        return None
    try:
        return periods.parse_period({'key': value})
    except periods.PeriodError:
        return None


def page_default(step, clock):
    """Период страницы без выбора (ответ Р2): текущий период шага по последнему доступному дню."""
    max_date = date.fromisoformat(clock['max_date'])
    last_full = date.fromisoformat(clock['last_full_day'])
    if step == 'last30':
        return periods.last_days(30, last_full)
    if step == 'last_closed_month':
        return periods.last_closed('month', last_full)
    return periods.current(step if step in periods.STEPS else 'week', max_date)


def resolve(args, cookies, user_id, mode='report', step='week', clock=None, allow_future=False):
    """Что показать: бар, выбранный период, показанный период, подпись и ошибка ссылки.

    -> {'bar', 'bar_source', 'chosen', 'chosen_source', 'default', 'period', 'note', 'url_error'}
    chosen — общий выбор (ссылка или cookie) или None; period — то, что показывает страница:
    у помесячной — месяц выбранного (periods.month_of), у «на сейчас» — None.
    """
    clock = clock or periods.page_config()
    bar, bar_source = '', 'default'
    if args.get('bar') is not None and bar_key(args.get('bar')) is not None:
        bar, bar_source = bar_key(args.get('bar')), 'url'
    else:
        saved = read_bar(cookies, user_id)
        if saved is not None:
            bar, bar_source = saved, 'choice'

    chosen, chosen_source, url_error = None, None, None
    try:
        from_url = periods.parse_period(args)
    except periods.PeriodError as exc:
        from_url, url_error = None, 'Период из ссылки не распознан (' + str(exc) + ')'
    if from_url is not None:
        if not allow_future and from_url.start > date.fromisoformat(clock['max_date']):
            url_error = 'Период из ссылки ещё не начался'
        else:
            chosen, chosen_source = from_url, 'url'
    if chosen is None:
        saved_period = read_period(cookies, user_id)
        if saved_period is not None:
            chosen, chosen_source = saved_period, 'choice'

    default = page_default(step, clock)
    shown, note = chosen or default, ''
    if mode == 'monthly':
        shown = periods.month_of(shown) if shown.step != 'month' else shown
        if chosen is not None and chosen.step != 'month':
            note = 'по месяцам — показан ' + periods.period_title('month', shown.start, shown.end).lower()
    elif mode == 'now':
        shown = None
    if url_error:
        note = (url_error + ' — показан ' + (periods.period_title(shown.step, shown.start, shown.end)
                                              if shown else 'текущий период')).strip()
    return {'bar': bar, 'bar_source': bar_source, 'chosen': chosen, 'chosen_source': chosen_source,
            'default': default, 'period': shown, 'note': note, 'url_error': url_error}


def _bar_options(bar_mode):
    options = [] if bar_mode == 'single' else [{'key': '', 'name': ALL_BARS_LABEL, 'hint': ALL_BARS_HINT}]
    return options + [{'key': b['key'], 'name': b['name'], 'hint': b['short']} for b in SITE_BARS]


def _period_dict(p):
    return None if p is None else {'start': p.start.isoformat(), 'end': p.end.isoformat(), 'step': p.step}


def build_strip(user_id, args, cookies, mode='report', step='week', live=True, last_full_day=None,
                data_start=None, steps=None, bar_mode='all', allow_future=False, max_days=None,
                max_reason=None, freshness=None, bar_label=None, bar_hint=None):
    """Полоса страницы: подписи для первой отрисовки сервером и настройки для страницы (client).

    bar_mode: all — «Все бары» и бары; single — только один бар (склад, кран бара, фиды): при
    «Все бары» на сайте показан последний бар таких страниц (cookie kultura_bar_single, иначе
    первый бар) с подписью в полосе — ответ Р4; none — страница на бары не делится (бар в полосе
    серый; подпись — bar_label / bar_hint, по умолчанию «Все бары · вся сеть»). Даты — строки ISO
    или date.
    """
    if mode not in MODES:
        raise ValueError('mode — одно из: ' + ', '.join(MODES))
    as_date = lambda v: date.fromisoformat(v) if isinstance(v, str) else v  # noqa: E731
    clock = periods.page_config(live=live, last_full_day=as_date(last_full_day), data_start=as_date(data_start))
    res = resolve(args, cookies, user_id, mode=mode, step=step, clock=clock, allow_future=allow_future)
    steps = list(steps or (['month'] if mode == 'monthly' else DEFAULT_STEPS))
    bar, bar_note = res['bar'], ''
    if bar_mode == 'single' and not bar:
        bar = read_bar_single(cookies, user_id) or SITE_BARS[0]['key']
        bar_note = 'по одному бару: показан ' + site_bar(bar)['name']
    if bar_mode == 'none':
        bar_name = bar_label or ALL_BARS_LABEL
        bar_hint = ALL_BARS_HINT if bar_hint is None else bar_hint
        bar_short = bar_name
    else:
        row = site_bar(bar)
        bar_name, bar_hint = (row['name'], row['short']) if row else (ALL_BARS_LABEL, ALL_BARS_HINT)
        # На телефоне бар — коротким именем (ВО, Лиг, Крем, Вар), вся сеть — «Все бары» (Р6).
        bar_short = row['short'] if row else ALL_BARS_LABEL
    note = ' · '.join(x for x in (res['note'], bar_note) if x)
    shown = res['period']
    last_full = date.fromisoformat(clock['last_full_day'])
    max_date = date.fromisoformat(clock['max_date'])
    title = periods.period_title(shown.step, shown.start, shown.end) if shown else 'Сейчас'
    sub = periods.period_sub(shown, last_full, max_date) if shown else 'данные на сейчас'
    # Полоса на телефоне (до 480 px): название и вторая строка — короткие, чтобы не обрезались
    # (periods.period_title_compact, period_sub_compact; страница — period_core.js).
    title_c = periods.period_title_compact(shown.step, shown.start, shown.end) if shown else title
    sub_c = periods.period_sub_compact(sub)
    client = {
        'user': user_id, 'mode': mode, 'step': step, 'clock': clock, 'steps': steps,
        'allowFuture': bool(allow_future), 'maxDays': max_days, 'maxReason': max_reason,
        'freshness': freshness,
        'bar': bar, 'globalBar': res['bar'], 'barMode': bar_mode, 'barSource': res['bar_source'],
        'barNote': bar_note, 'bars': bars_client(),
        'allLabel': ALL_BARS_LABEL, 'allHint': ALL_BARS_HINT,
        'period': _period_dict(shown), 'chosen': _period_dict(res['chosen']),
        'chosenSource': res['chosen_source'], 'default': _period_dict(res['default']),
        'note': note,
        'cookies': {'period': COOKIE_PERIOD, 'bar': COOKIE_BAR, 'barSingle': COOKIE_BAR_SINGLE},
        'ttl': {'period': PERIOD_TTL_SECONDS, 'bar': BAR_TTL_SECONDS},
    }
    return {
        'mode': mode, 'bar': bar, 'bar_mode': bar_mode, 'bar_name': bar_name, 'bar_hint': bar_hint,
        'bar_options': _bar_options(bar_mode), 'title': title, 'sub': sub,
        'bar_short': bar_short, 'title_c': title_c, 'sub_c': sub_c,
        'partial': bool(shown) and periods.period_state(shown, last_full, max_date) == 'partial',
        'note': note, 'client': client,
    }


def _current_user_id():
    from core.auth_guard import current_user   # без цикла импорта при старте
    user = current_user()
    return user.get('id') if user else None


def scope_base(user_id):
    """Настройки общего выбора для страниц без полосы (static/js/shared/period/scope.js)."""
    return {
        'user': user_id,
        'bars': bars_client(),
        'cookies': {'period': COOKIE_PERIOD, 'bar': COOKIE_BAR, 'barSingle': COOKIE_BAR_SINGLE},
        'ttl': {'period': PERIOD_TTL_SECONDS, 'bar': BAR_TTL_SECONDS},
    }


def _inject():
    import extensions   # APP_VERSION выставляет app.py при старте

    def kultura_strip(**opts):
        return build_strip(_current_user_id(), request.args, request.cookies, **opts)
    return {'kultura_strip': kultura_strip, 'kultura_scope': scope_base(_current_user_id()),
            'kultura_static_version': getattr(extensions, 'APP_VERSION', '') or ''}


def init_scope(app):
    """Шаблонам — kultura_strip(...) (полоса страницы) и kultura_scope (настройки scope.js)."""
    app.context_processor(_inject)

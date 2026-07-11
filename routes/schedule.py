import re
import sqlite3
from flask import Blueprint, request, jsonify, Response
from datetime import datetime, timedelta, date
from extensions import shifts_mgr, notes_manager
from core.auth_guard import current_user
from core.iiko_api import IikoAPI
from core.daily_plans_generator import DailyPlansGenerator
from core.calendar_ics import build_calendar
from core.schedule_plans import (
    build_month_plans,
    compute_month_summary,
    compute_employees_load,
    match_iiko_hours,
    SHIFT_NORM,
    PLAN_FORMULA_TEXT,
)

schedule_bp = Blueprint('schedule', __name__)

# Плановое время начала смены: 'HH:MM' (24ч). NULL = стандартная смена.
START_TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def _validate_start_time(value):
    """None или 'HH:MM'. Возвращает (ok, normalized)."""
    if value in (None, ''):
        return True, None
    if isinstance(value, str) and START_TIME_RE.match(value):
        return True, value
    return False, None


# Валидация входных дат/месяцев. Кривой ввод -> 400 (а не необработанный 500 и не
# рецидив iiko-бага datepicker, который упирался в неверный формат). ISO 'YYYY-MM-DD'.
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _valid_month(year, month):
    """Осмысленные год (2000..2100) и месяц (1..12)."""
    return 2000 <= year <= 2100 and 1 <= month <= 12


def _valid_date_str(date_str):
    """True, если строка — корректная ISO-дата 'YYYY-MM-DD' (и существует)."""
    if not isinstance(date_str, str) or not DATE_RE.match(date_str):
        return False
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def _today_iso():
    """Сегодня в ISO — дата для журнала у изменений без собственной даты
    (ставка, реестр): так запись попадает в историю текущего месяца."""
    return date.today().isoformat()


def _fmt_rate(v):
    """Ставка для строки журнала: целое без копеек, иначе с двумя знаками."""
    if v is None:
        return '—'
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{v:.0f}" if v == int(v) else f"{v:.2f}"


# ==================== Журнал изменений графика ====================
# Кто что менял в графике. Автор — текущий пользователь сессии (current_user,
# появился вместе с авторизацией). Журналирование — «лучшая попытка»: его сбой
# не должен валить саму операцию со сменой, поэтому _audit() глотает исключения.

def _fmt_dm(date_str):
    """ISO 'YYYY-MM-DD' -> 'DD.MM' для строки журнала."""
    try:
        return datetime.strptime(str(date_str)[:10], '%Y-%m-%d').strftime('%d.%m')
    except (ValueError, TypeError):
        return date_str or ''


def _fmt_hhmm(minutes):
    """Минуты -> 'Ч:ММ' для строки журнала."""
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return '?'
    return f"{m // 60}:{m % 60:02d}"


# Касса на смене (v7): ручной ввод бармена, без iiko. Деньги приходят в РУБЛЯХ,
# хранятся в КОПЕЙКАХ (INTEGER — точно). Потолок против опечаток — 1 млн ₽.
CASH_MAX_RUB = 1_000_000


def _rub_to_kop(value):
    """Рубли (число или null/'') -> копейки INTEGER. (ok, kop_or_None).

    None/'' -> (True, None): поле не заполнено. 0 допустимо («не было»).
    Отрицательное, не-число или сверх потолка -> (False, None).
    """
    if value in (None, ''):
        return True, None
    try:
        rub = float(value)
    except (TypeError, ValueError):
        return False, None
    if rub < 0 or rub > CASH_MAX_RUB:
        return False, None
    return True, int(round(rub * 100))


def _fmt_kop(kop):
    """Копейки -> строка рублей для журнала: '15 340' или '350.50 ₽'-часть."""
    if kop is None:
        return '—'
    rub = kop / 100.0
    s = f"{rub:,.0f}" if kop % 100 == 0 else f"{rub:,.2f}"
    return s.replace(',', ' ')


def _audit(action, summary, entity_date=None, employee_name=None):
    """Записать действие текущего пользователя в журнал графика (best-effort)."""
    try:
        u = current_user() or {}
        shifts_mgr.log_audit(
            action=action,
            summary=summary,
            actor_login=u.get('login'),
            actor_name=u.get('display_name') or u.get('login') or 'неизвестно',
            entity_date=entity_date,
            employee_name=employee_name,
        )
    except Exception as e:
        print(f"[SCHEDULE AUDIT WARNING] журнал не записан ({action}): {e}")


@schedule_bp.route('/api/schedule/employees', methods=['GET'])
def schedule_get_employees():
    """Реестр сотрудников графика (быстро, из shifts.db, без похода в iiko).

    Имена из исторических смен подмешиваются автоматически. Пополнение
    из iiko — отдельным POST /api/schedule/employees/sync.
    """
    include_inactive = request.args.get('all') == '1'
    return jsonify(shifts_mgr.get_schedule_employees(include_inactive=include_inactive))


@schedule_bp.route('/api/schedule/employees/sync', methods=['POST'])
def schedule_sync_employees():
    """Синхронизация реестра с iiko по стабильному id (справочник /employees).

    Переименование сотрудника в iiko подхватывается автоматически (имя смен и
    реестра обновляется по id), дубли не плодятся. Body (опц.):
    {"overrides": {"старое_имя_смены": "iiko_id_или_текущее_имя"}} — разовая
    ручная привязка наследия, где имя изменилось так, что авто-сопоставление
    по строке невозможно.
    """
    data = request.get_json(silent=True) or {}
    overrides = data.get('overrides') or {}
    iiko = IikoAPI()
    if not iiko.authenticate():
        return jsonify({'error': 'iiko недоступен'}), 503
    try:
        emps = iiko.get_employees() or []
    finally:
        iiko.logout()
    pairs = [(e.get('id'), e.get('name')) for e in emps if e.get('id') and e.get('name')]
    if not pairs:
        # get_employees() при ошибке iiko (HTTP != 200, таймаут, битый XML) возвращает [],
        # неотличимый от пустого справочника. Синк с pairs=[] удалил бы legacy-строки
        # реестра (шаг чистки в sync_employees), поэтому пустой ответ — всегда отказ.
        return jsonify({'error': 'iiko вернул пустой справочник сотрудников — синхронизация отменена'}), 503
    report = shifts_mgr.sync_employees(pairs, overrides=overrides)
    report['total_from_iiko'] = len(pairs)
    _audit('employees_sync',
           f"Синхронизация сотрудников из iiko: добавлено {report['added']}, "
           f"обновлено {report['updated']}, привязано смен {report['shifts_backfilled']}, "
           f"убрано дублей {report['legacy_removed']}")
    return jsonify(report)


@schedule_bp.route('/api/schedule/employee/<emp_id>', methods=['PUT'])
def schedule_update_employee(emp_id):
    """Обновить сотрудника в реестре по стабильному iiko_id: short_label, active,
    sort_order. Имя приходит из iiko (синк), здесь не редактируется."""
    data = request.get_json(silent=True) or {}
    # снимок до изменения — для журнала (защита от саботажа держится на истории)
    before = next((e for e in shifts_mgr.get_schedule_employees(include_inactive=True)
                   if str(e.get('id')) == str(emp_id)), None)
    ok = shifts_mgr.update_schedule_employee(
        iiko_id=emp_id,
        short_label=data.get('short_label'),
        active=data.get('active'),
        sort_order=data.get('sort_order'),
    )
    if not ok:
        return jsonify({'error': 'Сотрудник не найден'}), 404
    name = (before or {}).get('name') or emp_id
    parts = []
    if data.get('short_label') is not None:
        parts.append(f"метка «{(before or {}).get('short_label') or '—'}»"
                     f" -> «{(data.get('short_label') or '').strip() or '—'}»")
    if data.get('active') is not None:
        parts.append('показан в сетке' if data.get('active') else 'скрыт из сетки')
    if data.get('sort_order') is not None:
        parts.append(f"порядок -> {data.get('sort_order')}")
    _audit('employee_update',
           f"Реестр: {name} — " + ('; '.join(parts) if parts else 'изменён'),
           entity_date=_today_iso(), employee_name=name)
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/roles', methods=['GET'])
def schedule_get_roles():
    """Список ролей (включая rate_per_hour — ставку за час для расчёта ЗП)."""
    return jsonify(shifts_mgr.get_roles())


@schedule_bp.route('/api/schedule/role/<int:role_id>/rate', methods=['PUT'])
def schedule_set_role_rate(role_id):
    """Ставка за час для роли (расчёт ЗП). Body: {"rate_per_hour": число >= 0}."""
    data = request.get_json(silent=True) or {}
    try:
        rate = float(data.get('rate_per_hour'))
    except (TypeError, ValueError):
        return jsonify({'error': 'rate_per_hour должен быть числом'}), 400
    if rate < 0:
        return jsonify({'error': 'rate_per_hour не может быть отрицательным'}), 400
    # снимок до изменения — ставка напрямую влияет на ЗП, изменение обязано остаться в истории
    role = next((r for r in shifts_mgr.get_roles() if r['id'] == role_id), None)
    if not shifts_mgr.set_role_rate(role_id, rate):
        return jsonify({'error': 'Роль не найдена'}), 404
    role_name = (role or {}).get('name') or f"роль #{role_id}"
    _audit('role_rate',
           f"Ставка «{role_name}»: {_fmt_rate((role or {}).get('rate_per_hour'))}"
           f" -> {_fmt_rate(rate)} ₽/ч",
           entity_date=_today_iso())
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/hours-by-role', methods=['GET'])
def schedule_hours_by_role():
    """Часы по ролям и оплата за период (для страницы ЗП).

    Часы — из графика (fact_minutes), единственный источник часов оплаты;
    оплата = часы × ставка роли. Query: date_from, date_to (включительно).
    """
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    if not date_from or not date_to:
        return jsonify({'error': 'date_from и date_to обязательны'}), 400
    return jsonify({
        'rates': shifts_mgr.get_roles(),
        'employees': shifts_mgr.get_hours_by_role_for_period(date_from, date_to),
    })


@schedule_bp.route('/api/schedule/locations', methods=['GET'])
def schedule_get_locations():
    """Список точек."""
    return jsonify(shifts_mgr.get_locations())


@schedule_bp.route('/api/schedule/<int:year>/<int:month>', methods=['GET'])
def schedule_get_month(year, month):
    """Получить все смены за месяц."""
    if not _valid_month(year, month):
        return jsonify({'error': 'Некорректный год или месяц'}), 400
    return jsonify(shifts_mgr.get_shifts_for_month(year, month))


@schedule_bp.route('/api/schedule/shift', methods=['POST'])
def schedule_create_shift():
    """Создать смену. start_time 'HH:MM' — плановое начало (опционально)."""
    data = request.get_json(silent=True) or {}
    if not _valid_date_str(data.get('date')):
        return jsonify({'error': 'date обязателен в формате YYYY-MM-DD'}), 400
    if not (data.get('employee_name') or '').strip():
        return jsonify({'error': 'employee_name обязателен'}), 400
    try:
        location_id = int(data['location_id'])
        role_id = int(data['role_id'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'location_id и role_id обязательны (целые)'}), 400
    ok, start_time = _validate_start_time(data.get('start_time'))
    if not ok:
        return jsonify({'error': 'start_time должен быть в формате HH:MM'}), 400
    try:
        shift_id = shifts_mgr.create_shift(
            date_str=data['date'],
            employee_name=data['employee_name'],
            location_id=location_id,
            role_id=role_id,
            notes=data.get('notes'),
            start_time=start_time,
            employee_id=data.get('employee_id'),
        )
    except sqlite3.IntegrityError:
        # FK включён: несуществующая точка/роль -> понятная 400 вместо 500
        return jsonify({'error': 'Точка или роль не найдена'}), 400
    sh = shifts_mgr.get_shift(shift_id)
    if sh:
        time_part = f", с {sh['start_time']}" if sh.get('start_time') else ""
        _audit('shift_create',
               f"Добавлена смена: {sh['employee_name']} — {sh['role_name']}{time_part}"
               f" в {sh['location_short']}, {_fmt_dm(sh['date'])}",
               entity_date=sh['date'], employee_name=sh['employee_name'])
    return jsonify({'id': shift_id})


@schedule_bp.route('/api/schedule/shift/<int:shift_id>', methods=['PUT'])
def schedule_update_shift(shift_id):
    """Обновить смену (роль, плановое время и т.д.)."""
    data = request.get_json(silent=True) or {}
    # Факт часов меняется ТОЛЬКО через /fact (там проверка 0..1440). Здесь его не
    # принимаем, чтобы битые минуты (строка/отрицательное/огромное) не уходили в ЗП
    # в обход валидации.
    data.pop('fact_minutes', None)
    if 'start_time' in data:
        ok, start_time = _validate_start_time(data.get('start_time'))
        if not ok:
            return jsonify({'error': 'start_time должен быть в формате HH:MM'}), 400
        data['start_time'] = start_time
    if 'date' in data and not _valid_date_str(data.get('date')):
        return jsonify({'error': 'date должен быть в формате YYYY-MM-DD'}), 400
    for key in ('location_id', 'role_id'):
        if key in data:
            try:
                data[key] = int(data[key])
            except (TypeError, ValueError):
                return jsonify({'error': f'{key} должен быть целым'}), 400
    before = shifts_mgr.get_shift(shift_id)
    try:
        shifts_mgr.update_shift(shift_id, **data)
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Точка или роль не найдена'}), 400
    after = shifts_mgr.get_shift(shift_id)
    if after:
        parts = []
        if before:
            if before.get('role_name') != after.get('role_name'):
                parts.append(f"роль {before['role_name']} -> {after['role_name']}")
            if (before.get('start_time') or None) != (after.get('start_time') or None):
                parts.append(f"время {before.get('start_time') or 'день'}"
                             f" -> {after.get('start_time') or 'день'}")
        detail = '; '.join(parts) if parts else 'без изменений'
        _audit('shift_update',
               f"Изменена смена: {after['employee_name']}, {_fmt_dm(after['date'])} ({detail})",
               entity_date=after['date'], employee_name=after['employee_name'])
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/shift/<int:shift_id>/fact', methods=['PUT'])
def schedule_set_shift_fact(shift_id):
    """Записать факт отработанных минут (вводится барменом в конце смены).

    Body: {"fact_minutes": int 0..1440} либо {"fact_minutes": null} для очистки.
    """
    data = request.get_json() or {}
    fact = data.get('fact_minutes')
    if fact is not None:
        try:
            fact = int(fact)
        except (TypeError, ValueError):
            return jsonify({'error': 'fact_minutes должен быть целым числом минут'}), 400
        if not (0 <= fact <= 1440):
            return jsonify({'error': 'fact_minutes должен быть в диапазоне 0..1440'}), 400
    updated = shifts_mgr.set_shift_fact(shift_id, fact)
    if not updated:
        return jsonify({'error': 'Смена не найдена'}), 404
    sh = shifts_mgr.get_shift(shift_id)
    if sh:
        if fact is None:
            _audit('fact_clear',
                   f"Очищен факт часов: {sh['employee_name']}, {_fmt_dm(sh['date'])}",
                   entity_date=sh['date'], employee_name=sh['employee_name'])
        else:
            _audit('fact_set',
                   f"Проставлен факт часов: {sh['employee_name']} — {_fmt_hhmm(fact)}"
                   f" за {_fmt_dm(sh['date'])}",
                   entity_date=sh['date'], employee_name=sh['employee_name'])
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/shift/<int:shift_id>/cash', methods=['PUT'])
def schedule_set_shift_cash(shift_id):
    """Записать кассу смены — ручной ввод бармена в конце смены (без iiko).

    Body в РУБЛЯХ (число или null): {cash_expense, cash_collection, cash_end,
    cash_expense_note}. Хранится в копейках. 0 = «трат/инкассации не было»,
    null = поле не заполнено. Все три null -> очистка кассы смены. Заполняет,
    как правило, дневная смена (замена бумажного чеклиста кассовой дисциплины).
    Часы (fact) не трогаются — касса и часы независимы.
    """
    data = request.get_json() or {}
    ok_e, exp = _rub_to_kop(data.get('cash_expense'))
    ok_c, col = _rub_to_kop(data.get('cash_collection'))
    ok_k, end = _rub_to_kop(data.get('cash_end'))
    if not (ok_e and ok_c and ok_k):
        return jsonify({'error': f'Суммы кассы — число от 0 до {CASH_MAX_RUB} ₽'}), 400
    note = data.get('cash_expense_note')
    if note is not None and not isinstance(note, str):
        return jsonify({'error': 'cash_expense_note должен быть строкой'}), 400

    updated = shifts_mgr.set_shift_cash(shift_id, exp, col, end, note)
    if not updated:
        return jsonify({'error': 'Смена не найдена'}), 404

    sh = shifts_mgr.get_shift(shift_id)
    if sh:
        if exp is None and col is None and end is None:
            _audit('cash_clear',
                   f"Очищена касса: {sh['employee_name']}, {_fmt_dm(sh['date'])}",
                   entity_date=sh['date'], employee_name=sh['employee_name'])
        else:
            # Заметку «на что» в журнал не пишем (низкая ценность, как текст пожеланий).
            _audit('cash_set',
                   f"Касса ({sh['employee_name']}, {_fmt_dm(sh['date'])}): "
                   f"траты {_fmt_kop(exp)}, инкассация {_fmt_kop(col)}, "
                   f"на конец {_fmt_kop(end)} ₽",
                   entity_date=sh['date'], employee_name=sh['employee_name'])
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/shift/<int:shift_id>', methods=['DELETE'])
def schedule_delete_shift(shift_id):
    """Удалить смену."""
    sh = shifts_mgr.get_shift(shift_id)  # снимок до удаления — для журнала
    shifts_mgr.delete_shift(shift_id)
    if sh:
        _audit('shift_delete',
               f"Удалена смена: {sh['employee_name']} — {sh['role_name']}"
               f" в {sh['location_short']}, {_fmt_dm(sh['date'])}",
               entity_date=sh['date'], employee_name=sh['employee_name'])
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/dayoff', methods=['GET'])
def schedule_get_dayoffs():
    """Пожелания выходных с фильтрацией."""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    employee_name = request.args.get('employee_name')
    return jsonify(shifts_mgr.get_day_off_requests(
        employee_name=employee_name,
        date_from=date_from,
        date_to=date_to
    ))


@schedule_bp.route('/api/schedule/dayoff', methods=['POST'])
def schedule_create_dayoff():
    """Создать пожелание выходного."""
    data = request.get_json(silent=True) or {}
    if not (data.get('employee_name') or '').strip():
        return jsonify({'error': 'employee_name обязателен'}), 400
    if not _valid_date_str(data.get('date_from')) or not _valid_date_str(data.get('date_to')):
        return jsonify({'error': 'date_from и date_to обязательны в формате YYYY-MM-DD'}), 400
    if data['date_from'] > data['date_to']:
        return jsonify({'error': 'date_from позже date_to'}), 400
    req_id = shifts_mgr.create_day_off_request(
        employee_name=data['employee_name'],
        date_from=data['date_from'],
        date_to=data['date_to'],
        reason=data.get('reason')
    )
    _audit('dayoff_create',
           f"Добавлено пожелание выходного: {data['employee_name']},"
           f" {_fmt_dm(data['date_from'])}-{_fmt_dm(data['date_to'])}",
           entity_date=data['date_from'], employee_name=data['employee_name'])
    return jsonify({'id': req_id})


@schedule_bp.route('/api/schedule/dayoff/<int:request_id>', methods=['DELETE'])
def schedule_delete_dayoff(request_id):
    """Удалить пожелание выходного."""
    req = shifts_mgr.get_day_off_request(request_id)  # снимок до удаления
    shifts_mgr.delete_day_off_request(request_id)
    if req:
        _audit('dayoff_delete',
               f"Удалено пожелание выходного: {req['employee_name']},"
               f" {_fmt_dm(req['date_from'])}-{_fmt_dm(req['date_to'])}",
               entity_date=req['date_from'], employee_name=req['employee_name'])
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/audit/<int:year>/<int:month>', methods=['GET'])
def schedule_get_audit(year, month):
    """Журнал изменений графика за месяц (новые сверху). Кто что менял —
    автор берётся из сессии в момент изменения."""
    limit = request.args.get('limit', 200, type=int)
    return jsonify(shifts_mgr.get_audit(year, month, limit=limit))


@schedule_bp.route('/schedule/cal.ics', methods=['GET'])
def schedule_calendar_ics():
    """Личный график сотрудника в формате iCalendar (.ics) — разовая выгрузка.

    Отдаёт смены ТЕКУЩЕГО пользователя (привязка аккаунта к сотруднику —
    users.employee_iiko_id; смены ищутся по shifts.employee_id). За логином
    (не публичный эндпоинт). Окно: месяц назад .. полгода вперёд — недавняя
    история + всё запланированное. Аккаунт без привязки -> пустой календарь.
    Подписки нет (статичный файл): поменялся график -> скачать заново.
    """
    user = current_user() or {}
    iiko_id = user.get('employee_iiko_id')
    name = user.get('display_name') or 'сотрудник'
    today = datetime.now().date()
    date_from = (today - timedelta(days=31)).isoformat()
    date_to = (today + timedelta(days=183)).isoformat()
    shifts = shifts_mgr.get_shifts_for_employee(iiko_id, date_from, date_to)
    ics = build_calendar(name, shifts, dtstamp=datetime.now())
    return Response(
        ics,
        content_type='text/calendar; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename="grafik-smen.ics"',
            'Cache-Control': 'no-store',
        },
    )


def _fetch_month_fact_olap(year, month):
    """Факт выручки по дням и точкам из iiko OLAP — тот же источник и кэш,
    что «Факт» на дашборде (cached_olap: TTL 10 мин + single-flight).

    Returns:
        {date_str: {venue_key: revenue}} или None, если iiko недоступен
        (тогда вызывающий код падает на сохранённый daily_revenue).
    """
    from extensions import cached_olap, venues_manager
    from core.olap_reports import OlapReports

    first_day = f"{year}-{month:02d}-01"
    if month == 12:
        next_month_first = f"{year + 1}-01-01"
    else:
        next_month_first = f"{year}-{month + 1:02d}-01"

    def _fetch():
        olap = OlapReports()
        if not olap.connect():
            return None
        try:
            return olap.get_store_daily_revenue(first_day, next_month_first)
        finally:
            olap.disconnect()

    stores_daily = cached_olap(f"schedule_fact_{year}-{month:02d}", _fetch)
    if not stores_daily:
        return None

    month_prefix = f"{year}-{month:02d}-"
    by_day = {}
    for store_name, days in stores_daily.items():
        venue_key = venues_manager.get_key_by_iiko_name(store_name)
        if not venue_key:
            continue
        for date_str, revenue in days.items():
            if not date_str.startswith(month_prefix):
                continue
            day_map = by_day.setdefault(date_str, {})
            day_map[venue_key] = day_map.get(venue_key, 0.0) + revenue
    return by_day


def _month_inputs(year, month):
    """Общие входные данные планов/сводки месяца."""
    locations = shifts_mgr.get_locations()
    daily_plans = DailyPlansGenerator().load_daily_plans()
    manual_rows = shifts_mgr.get_revenue_for_month(year, month)
    olap_fact = _fetch_month_fact_olap(year, month)
    return locations, build_month_plans(year, month, locations, daily_plans,
                                        manual_rows, olap_fact=olap_fact)


@schedule_bp.route('/api/schedule/plans/<int:year>/<int:month>', methods=['GET'])
def schedule_get_plans(year, month):
    """План/факт по дням месяца. План — read-only из daily_plans (веса дней);
    фоллбэк — замороженный ручной plan_revenue (source='manual')."""
    if not _valid_month(year, month):
        return jsonify({'error': 'Некорректный год или месяц'}), 400
    _, month_plans = _month_inputs(year, month)
    return jsonify({'days': month_plans, 'plan_formula': PLAN_FORMULA_TEXT})


def _fetch_month_iiko_hours(year, month):
    """Расчётные часы по сотрудникам из кассовых смен iiko за месяц.

    Тот же источник, что «N ч (авт)» на странице расчёта ЗП:
    IikoAPI.get_employee_metrics_from_shifts -> total_hours
    (закрытие кассовой смены минус открытие, ключ responsibleUserId).
    Кэш 10 минут (cached_olap). Возвращает {ФИО_iiko: часы} или None.
    """
    from extensions import cached_olap

    first_day = f"{year}-{month:02d}-01"
    if month == 12:
        next_month_first = f"{year + 1}-01-01"
    else:
        next_month_first = f"{year}-{month + 1:02d}-01"

    def _fetch():
        iiko = IikoAPI()
        if not iiko.authenticate():
            return None
        try:
            id_to_name = {e['id']: e['name']
                          for e in (iiko.get_employees() or []) if e.get('id')}
            metrics = iiko.get_employee_metrics_from_shifts(first_day, next_month_first)
            hours_by_name = {}
            for emp_id, m in (metrics or {}).items():
                name = id_to_name.get(emp_id)
                if name:
                    hours_by_name[name] = hours_by_name.get(name, 0.0) + (m.get('total_hours') or 0.0)
            # Обёртка, чтобы пустой месяц тоже кэшировался (cached_olap не кэширует falsy)
            return {'hours_by_iiko_name': hours_by_name}
        finally:
            iiko.logout()

    data = cached_olap(f"schedule_iiko_hours_{year}-{month:02d}", _fetch)
    return data.get('hours_by_iiko_name') if data else None


@schedule_bp.route('/api/schedule/summary/<int:year>/<int:month>', methods=['GET'])
def schedule_get_summary(year, month):
    """Сводка месяца: план/факт/средняя/ожидаемая/выполнение % + нагрузка людей."""
    if not _valid_month(year, month):
        return jsonify({'error': 'Некорректный год или месяц'}), 400
    locations, month_plans = _month_inputs(year, month)
    summary = compute_month_summary(month_plans, locations)
    shifts = shifts_mgr.get_shifts_for_month(year, month)
    load = compute_employees_load(shifts, datetime.now().strftime('%Y-%m-%d'))

    summary['employees_load'] = load
    summary['shift_norm'] = SHIFT_NORM  # норма смен в месяц — ориентир в «Нагрузке»
    return jsonify(summary)


@schedule_bp.route('/api/schedule/widgets/<int:year>/<int:month>', methods=['GET'])
def schedule_get_widgets(year, month):
    """Данные виджета «Нагрузка» для редактора И просмотра — money-free и без iiko
    (смены/норма/подряд/без факта). На странице просмотра у барменов финансов нет,
    поэтому здесь рублей нет вовсе. Денежный виджет «План/Факт по дням» живёт
    только в редакторе и строится на фронте из уже загруженного /plans."""
    if not _valid_month(year, month):
        return jsonify({'error': 'Некорректный год или месяц'}), 400
    shifts = shifts_mgr.get_shifts_for_month(year, month)
    load = compute_employees_load(shifts, datetime.now().strftime('%Y-%m-%d'))
    return jsonify({
        'employees_load': load,
        'shift_norm': SHIFT_NORM,
    })


@schedule_bp.route('/api/schedule/revenue/<date_str>', methods=['GET'])
def schedule_get_revenue(date_str):
    """Выручка по всем точкам за день."""
    if not _valid_date_str(date_str):
        return jsonify({'error': 'Некорректная дата (YYYY-MM-DD)'}), 400
    return jsonify(shifts_mgr.get_revenue_for_day(date_str))


@schedule_bp.route('/api/schedule/revenue/<date_str>/<int:location_id>', methods=['PUT'])
def schedule_update_revenue(date_str, location_id):
    """Обновить факт выручки.

    Ручной ввод ПЛАНА заморожен (2026-06): план дня считается из весов
    (см. /api/schedule/plans). plan_revenue в body игнорируется.
    """
    if not _valid_date_str(date_str):
        return jsonify({'error': 'Некорректная дата (YYYY-MM-DD)'}), 400
    data = request.get_json(silent=True) or {}
    if 'plan_revenue' in data:
        print(f"[SCHEDULE] plan_revenue в PUT revenue игнорируется (план заморожен): {date_str}")
    fact = data.get('fact_revenue')
    shifts_mgr.update_revenue(
        date_str=date_str,
        location_id=location_id,
        fact_revenue=fact
    )
    # деньги — в историю (защита от саботажа держится на журнале)
    loc = next((l for l in shifts_mgr.get_locations() if l['id'] == location_id), None)
    loc_name = (loc or {}).get('short_name') or (loc or {}).get('name') or f"точка #{location_id}"
    _audit('revenue_set',
           f"Факт выручки {_fmt_dm(date_str)} ({loc_name}): "
           + (f"{_fmt_rate(fact)} ₽" if fact is not None else 'очищен'),
           entity_date=date_str)
    return jsonify({'ok': True})


def _aggregate_cash_shifts_by_day(cash_shifts, locations):
    """Сгруппировать кассовые смены iiko: {date: {location_name: revenue}}.

    Выручка кассовой смены = cashOrders + cardOrders (как в дневном синке).
    Дата — openDate кассовой смены (первые 10 символов ISO).
    Маппинг точки — по вхождению имени/short_name локации в pointOfSale.
    """
    by_day = {}
    for shift in cash_shifts or []:
        open_date = (shift.get('openDate') or '')[:10]
        if not open_date:
            continue
        point_of_sale = shift.get('pointOfSale', '')
        revenue = (shift.get('payOrders', {}).get('cashOrders', 0) or 0) + \
                  (shift.get('payOrders', {}).get('cardOrders', 0) or 0)

        for loc in locations:
            if loc['name'].lower() in point_of_sale.lower() or \
               loc['short_name'].lower() in point_of_sale.lower():
                day_map = by_day.setdefault(open_date, {})
                day_map[loc['name']] = day_map.get(loc['name'], 0) + revenue
                # Одна кассовая смена = одна точка: без break выручка задвоилась бы,
                # если pointOfSale содержит подстроки двух локаций (short_name «ВО» и т.п.).
                break
    return by_day


@schedule_bp.route('/api/schedule/revenue/sync/<date_str>', methods=['POST'])
def schedule_sync_revenue(date_str):
    """Синхронизировать фактическую выручку из iiko за дату."""
    if not _valid_date_str(date_str):
        return jsonify({'error': 'Некорректная дата (YYYY-MM-DD)'}), 400
    iiko = None
    try:
        iiko = IikoAPI()
        if not iiko.authenticate():
            # Без проверки get_cash_shifts вернул бы [] и синк отчитался бы
            # 200 «обновлено точек 0», маскируя недоступность iiko.
            return jsonify({'error': 'iiko недоступен'}), 503

        # Получаем кассовые смены за дату
        date_to = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        cash_shifts = iiko.get_cash_shifts(date_str, date_to)

        by_day = _aggregate_cash_shifts_by_day(cash_shifts, shifts_mgr.get_locations())
        revenue_by_location = by_day.get(date_str, {})

        updated = shifts_mgr.sync_revenue_from_iiko(date_str, revenue_by_location)
        # синк перезаписывает факт — фиксируем, кто его запускал
        _audit('revenue_sync',
               f"Синхронизация факта выручки из iiko за {_fmt_dm(date_str)}: обновлено точек {updated}",
               entity_date=date_str)
        return jsonify({'updated': updated, 'revenue': revenue_by_location})

    except Exception as e:
        print(f"[SCHEDULE SYNC ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Синхронизация выручки не удалась'}), 500
    finally:
        # Освобождаем слот лицензии iiko в любом случае (иначе утечка слотов).
        if iiko is not None:
            iiko.logout()


@schedule_bp.route('/api/schedule/revenue/sync-month/<int:year>/<int:month>', methods=['POST'])
def schedule_sync_revenue_month(year, month):
    """Синхронизировать факт выручки из iiko за весь месяц одним запросом.

    Нужно для сводки месяца («Ожидаемая», «Выполнение %») — днями синкать
    месяц было бы 30 запросов к iiko.
    """
    if not _valid_month(year, month):
        return jsonify({'error': 'Некорректный год или месяц'}), 400
    iiko = None
    try:
        first_day = f"{year}-{month:02d}-01"
        if month == 12:
            next_month_first = f"{year + 1}-01-01"
        else:
            next_month_first = f"{year}-{month + 1:02d}-01"

        iiko = IikoAPI()
        if not iiko.authenticate():
            return jsonify({'error': 'iiko недоступен'}), 503
        cash_shifts = iiko.get_cash_shifts(first_day, next_month_first)

        by_day = _aggregate_cash_shifts_by_day(cash_shifts, shifts_mgr.get_locations())

        updated_days = 0
        updated_rows = 0
        month_prefix = f"{year}-{month:02d}-"
        for date_str, revenue_map in sorted(by_day.items()):
            if not date_str.startswith(month_prefix):
                continue
            updated_rows += shifts_mgr.sync_revenue_from_iiko(date_str, revenue_map)
            updated_days += 1

        _audit('revenue_sync_month',
               f"Синхронизация факта выручки из iiko за {int(month):02d}.{year}:"
               f" дней {updated_days}, строк {updated_rows}",
               entity_date=f"{year}-{int(month):02d}-01")
        return jsonify({'updated_days': updated_days, 'updated_rows': updated_rows})

    except Exception as e:
        print(f"[SCHEDULE SYNC MONTH ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Синхронизация выручки не удалась'}), 500
    finally:
        if iiko is not None:
            iiko.logout()


@schedule_bp.route('/api/schedule/wishes', methods=['GET'])
def schedule_get_wishes():
    """Получить все пожелания."""
    return jsonify(shifts_mgr.get_wishes())


@schedule_bp.route('/api/schedule/wishes', methods=['POST'])
def schedule_save_wish():
    """Сохранить пожелание сотрудника."""
    data = request.get_json(silent=True) or {}
    if not (data.get('employee_name') or '').strip():
        return jsonify({'error': 'employee_name обязателен'}), 400
    shifts_mgr.save_wish(
        employee_name=data['employee_name'],
        text=data.get('text', '')
    )
    return jsonify({'ok': True})


# ============================================
# Meeting Notes API
# ============================================

@schedule_bp.route('/api/meeting-notes', methods=['GET'])
def get_meeting_note():
    """Получить заметку для бара и периода."""
    venue = request.args.get('venue', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    if not venue or not date_from or not date_to:
        return jsonify({'text': ''})
    note = notes_manager.get(venue, date_from, date_to)
    return jsonify({'text': note['text'] if note else ''})


@schedule_bp.route('/api/meeting-notes', methods=['POST'])
def save_meeting_note():
    """Сохранить заметку."""
    data = request.json
    venue = data.get('venue', '')
    date_from = data.get('date_from', '')
    date_to = data.get('date_to', '')
    text = data.get('text', '')
    if not venue or not date_from or not date_to:
        return jsonify({'error': 'venue, date_from, date_to required'}), 400
    notes_manager.save(venue, date_from, date_to, text)
    return jsonify({'ok': True})


@schedule_bp.route('/api/meeting-notes/history', methods=['GET'])
def meeting_notes_history():
    """Список заметок для бара (все периоды, новые первые)."""
    venue = request.args.get('venue', '')
    if not venue:
        return jsonify([])
    limit = request.args.get('limit', 10, type=int)
    notes = notes_manager.list_by_venue(venue, limit=limit)
    return jsonify(notes)

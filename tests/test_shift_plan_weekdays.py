"""Сводка план/факт смен по дням недели (core/shift_plan_weekdays.py, POST /api/shift-plan-weekdays).

Числа в ожиданиях посчитаны вручную по формулам из докстроки модуля.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import shift_plan_weekdays as spw  # noqa: E402


def _day(date, venue, plan, revenue):
    over = revenue - plan if plan > 0 else 0
    bonus = 1000 + over * 0.05 if over > 0 else 0
    return {'date': date, 'venue': venue, 'plan': plan, 'revenue': revenue, 'day_bonus': bonus}


# Октябрь 2026: пт — 2, 9, 16; сб — 3, 10, 17; пн 5, вт 6, ср 7, чт 8, вс 11.
EMPLOYEES = [
    {'name': 'Анна Смирнова', 'employee_id': 'a', 'days': [
        _day('2026-10-02', 'ligovskiy', 50000, 45000),     # пт
        _day('2026-10-03', 'ligovskiy', 50000, 45000),     # сб
        _day('2026-10-05', 'ligovskiy', 25000, 30000),     # пн
        _day('2026-10-06', 'ligovskiy', 25000, 30000),     # вт
        _day('2026-10-11', 'ligovskiy', 25000, 30000),     # вс
    ]},
    {'name': 'Борис Иванов', 'employee_id': 'b', 'days': [
        _day('2026-10-07', 'ligovskiy', 25000, 25000),     # ср: ровно план — премии нет
        _day('2026-10-09', 'ligovskiy', 50000, 40000),     # пт
        _day('2026-10-10', 'ligovskiy', 50000, 40000),     # сб
        _day('2026-10-16', 'ligovskiy', 50000, 40000),     # пт
        _day('2026-10-17', 'ligovskiy', 50000, 40000),     # сб
    ]},
    {'name': 'Вера Котова', 'employee_id': 'c', 'days': [
        _day('2026-10-05', 'kremenchugskaya', 30000, 33000),
        _day('2026-10-06', 'kremenchugskaya', 30000, 33000),
        _day('2026-10-08', 'planernaya', 0, 10000),         # точка без плана
    ]},
]


def _summary(**kwargs):
    return spw.summarize(EMPLOYEES, '2026-10-01', '2026-10-31', **kwargs)


def _person(summary, employee_id):
    return next(p for p in summary['employees'] if p['employee_id'] == employee_id)


# ---------------------------------------------------------------- аргументы

def test_parse_period():
    assert spw.parse_period('2025-11-01', '2026-10-31') == ('2025-11-01', '2026-10-31')
    assert spw.parse_period('2026-01-01', '2027-02-04')                  # 400 дней — можно
    for bad in (('2026-10-31', '2026-10-01'), ('2026-10', '2026-10-31'), (None, '2026-10-31'),
                ('2026-01-01', '2027-02-05')):                           # 401 день
        with pytest.raises(ValueError):
            spw.parse_period(*bad)


def test_parse_weekend_and_venue():
    assert spw.parse_weekend(None) == (4, 5)
    assert spw.parse_weekend([6, 5, 5]) == (5, 6)
    for bad in ([], [7], [True], ['5'], list(range(7)), 5):
        with pytest.raises(ValueError):
            spw.parse_weekend(bad)
    assert spw.parse_venue(None) == 'all'
    assert spw.parse_venue('bolshoy') == 'bolshoy'
    with pytest.raises(ValueError):
        spw.parse_venue('Лиговский')


# ---------------------------------------------------------------- сводка

def test_network_groups_and_weekdays():
    out = _summary()
    net = out['network']
    assert net['weekend'] == {'shifts': 6, 'plan': 300000, 'revenue': 250000, 'percent': 83.3,
                              'met': 0, 'bonus': 0}
    # Будни: Анна 3 x (25 000 -> 30 000), Борис 25 000 -> 25 000, Вера 2 x (30 000 -> 33 000).
    assert net['weekdays'] == {'shifts': 6, 'plan': 160000, 'revenue': 181000, 'percent': 113.1,
                               'met': 5, 'bonus': 6050}
    assert net['total']['shifts'] == 12 and net['total']['percent'] == 93.7
    assert net['weekend_share'] == 50.0
    assert [d['day'] for d in net['by_weekday']] == list(spw.WEEKDAY_NAMES)
    # Пятницы: Анна 45 000, Борис 40 000 + 40 000 — 125 000 при плане 3 x 50 000.
    assert net['by_weekday'][4] == {'day': 'пт', 'shifts': 3, 'plan': 150000, 'revenue': 125000,
                                    'percent': 83.3, 'met': 0, 'bonus': 0}
    assert out['groups'] == {'weekend': [4, 5], 'weekend_names': 'пт, сб',
                             'weekdays': [0, 1, 2, 3, 6], 'weekdays_names': 'пн, вт, ср, чт, вс'}
    assert out['no_plan'] == {'shifts': 1, 'revenue': 10000}
    assert out['months'][0]['month'] == '2026-10'
    assert out['months'][0]['total'] == net['total']


def test_venues_in_site_order_with_names():
    out = _summary()
    assert [(v['venue_key'], v['name']) for v in out['venues']] == [
        ('ligovskiy', 'Лиговский'), ('kremenchugskaya', 'Кременчугская')]
    lig = out['venues'][0]
    assert lig['weekdays']['percent'] == 115.0 and lig['weekend']['percent'] == 83.3


def test_norm_compares_with_colleagues_in_same_cells():
    out = _summary()
    anna = _person(out, 'a')
    # Пт/сб: коллеги 160 000 / 200 000 = 0,8 -> ожидаемо 80 000; будни: 25 000 / 25 000 = 1,0 ->
    # 75 000. Ожидаемо 155 000 из плана 175 000, факт 180 000.
    assert anna['norm'] == {'percent': 88.6, 'fact_percent': 102.9, 'diff': 14.3,
                            'weekend_diff': 10.0, 'weekdays_diff': 20.0, 'coverage': 100.0,
                            'expected_revenue': 155000}
    boris = _person(out, 'b')
    # Пт/сб: у Анны 90 000 / 100 000 = 0,9 -> 180 000; будни: 90 000 / 75 000 = 1,2 -> 30 000.
    assert boris['norm'] == {'percent': 93.3, 'fact_percent': 82.2, 'diff': -11.1,
                             'weekend_diff': -10.0, 'weekdays_diff': -20.0, 'coverage': 100.0,
                             'expected_revenue': 210000}


def test_alone_in_cell_has_no_norm_and_no_plan_is_separate():
    vera = _person(_summary(), 'c')
    assert vera['norm'] is None                       # на Кременчугской в октябре — одна
    assert vera['total'] == {'shifts': 2, 'plan': 60000, 'revenue': 66000, 'percent': 110.0,
                             'met': 2, 'bonus': 2300}
    assert vera['no_plan'] == {'shifts': 1, 'revenue': 10000}
    assert vera['venues'] == ['kremenchugskaya']
    assert vera['weekend_share'] == 0.0


def test_partial_coverage():
    employees = EMPLOYEES + [{'name': 'Глеб Орлов', 'employee_id': 'd', 'days': [
        _day('2026-10-12', 'kremenchugskaya', 30000, 27000),   # пн: рядом Вера — есть норма
        _day('2026-10-23', 'kremenchugskaya', 60000, 66000),   # пт: в пт/сб там один Глеб
    ]}]
    gleb = _person(spw.summarize(employees, '2026-10-01', '2026-10-31'), 'd')
    # Будни: у Веры 66 000 / 60 000 = 1,1 -> ожидаемо 33 000 при факте 27 000 на плане 30 000.
    assert gleb['norm']['coverage'] == round(30000 / 90000 * 100, 1)
    assert gleb['norm']['percent'] == 110.0 and gleb['norm']['fact_percent'] == 90.0
    assert gleb['norm']['diff'] == -20.0 and gleb['norm']['weekend_diff'] is None


def test_people_have_slim_weekdays_sorted_by_shifts():
    out = _summary()
    assert [p['employee_id'] for p in out['employees']] == ['a', 'b', 'c']
    anna = _person(out, 'a')
    assert anna['by_weekday'] == [
        {'day': 'пн', 'shifts': 1, 'percent': 120.0, 'met': 1},
        {'day': 'вт', 'shifts': 1, 'percent': 120.0, 'met': 1},
        {'day': 'пт', 'shifts': 1, 'percent': 90.0, 'met': 0},
        {'day': 'сб', 'shifts': 1, 'percent': 90.0, 'met': 0},
        {'day': 'вс', 'shifts': 1, 'percent': 120.0, 'met': 1}]
    assert anna['weekend_share'] == 40.0
    assert 'no_plan' not in anna


def test_custom_weekend_and_venue_filter():
    anna = _person(_summary(weekend_days=(5, 6)), 'a')
    # Сб 45 000 / 50 000 и вс 30 000 / 25 000: 75 000 / 75 000.
    assert anna['weekend']['percent'] == 100.0 and anna['weekend']['shifts'] == 2
    only = _summary(venue_key='kremenchugskaya')
    assert [p['employee_id'] for p in only['employees']] == ['c']
    assert only['venue_key'] == 'kremenchugskaya'
    assert only['no_plan'] == {'shifts': 0, 'revenue': 0}   # точка без плана — другой бар
    assert [v['venue_key'] for v in only['venues']] == ['kremenchugskaya']


def test_year_answer_fits_mcp_limit():
    """Год, 30 человек на 4 барах: ответ меньше предела MCP (core/mcp/bridge.RESULT_TEXT_LIMIT)."""
    import json
    from datetime import date, timedelta
    from core.mcp.bridge import RESULT_TEXT_LIMIT
    venues = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']
    people = [{'name': 'Сотрудник Номер%02d' % i, 'employee_id': '%08d-0000-0000-0000-000000000000' % i,
               'days': []} for i in range(30)]
    day = date(2025, 11, 1)
    while day <= date(2026, 10, 31):
        for v_index, venue in enumerate(venues):
            person = people[(day.toordinal() + v_index * 7) % 30]
            person['days'].append(_day(day.isoformat(), venue, 61234.56, 58765.43))
        day += timedelta(days=1)
    text = json.dumps(spw.summarize(people, '2025-11-01', '2026-10-31'), ensure_ascii=False,
                      separators=(',', ':'))
    assert len(text) < RESULT_TEXT_LIMIT * 0.75, len(text)


# ---------------------------------------------------------------- маршрут

class _FakeIiko:
    """Кассовые смены вместо iiko: тот же формат, что get_employee_metrics_from_shifts."""

    SHIFTS = {
        'e1': {'2026-10-02': ('Лиговский', 45000), '2026-10-05': ('Лиговский', 30000)},
        'e2': {'2026-10-09': ('Лиговский', 40000), '2026-10-07': ('Пивная культура', 31000)},
    }

    def authenticate(self):
        return True

    def logout(self):
        pass

    def get_employees(self):
        return [{'id': 'e1', 'name': 'Анна Смирнова'}, {'id': 'e2', 'name': 'Борис Иванов'}]

    def get_employee_metrics_from_shifts(self, date_from, date_to):
        self.period = (date_from, date_to)
        out = {}
        for emp_id, days in self.SHIFTS.items():
            out[emp_id] = {'shift_locations': {d: loc for d, (loc, _) in days.items()},
                           'shift_revenues': {d: rev for d, (_, rev) in days.items()},
                           'shift_times': {}, 'shifts_count': len(days), 'late_count': 0,
                           'late_dates': [], 'total_hours': 0.0}
        return out


def _patch_iiko(monkeypatch):
    """Расчёт премий без iiko и без базы графика: кассовые смены — _FakeIiko, планы — словарь."""
    import routes.employee as emp
    plans = {('2026-10-02', 'ligovskiy'): 50000, ('2026-10-05', 'ligovskiy'): 25000,
             ('2026-10-09', 'ligovskiy'): 50000, ('2026-10-07', 'kremenchugskaya'): 30000}
    calls = []
    fake = _FakeIiko()

    def make_iiko():
        calls.append('iiko')
        return fake

    monkeypatch.setattr(emp, 'IikoAPI', make_iiko)
    monkeypatch.setattr(emp, 'EMPLOYEES_CACHE', {'data': None, 'timestamp': 0})
    monkeypatch.setattr(emp, 'get_daily_plan_for_date', lambda d, v: plans.get((d, v), 0.0))
    monkeypatch.setattr(emp, '_cash_filled_day_keys', lambda *a: None)
    monkeypatch.setattr(emp, '_manual_handover_penalties', lambda *a: ({}, {}))
    return calls, fake


@pytest.fixture
def client(monkeypatch):
    from flask import Flask
    import routes
    calls, fake = _patch_iiko(monkeypatch)
    app = Flask('shift_plan_weekdays_test')
    routes.register_blueprints(app)
    test_client = app.test_client()
    test_client.calls = calls
    test_client.fake = fake
    return test_client


def test_route_uses_bonus_calculation(client):
    resp = client.post('/api/shift-plan-weekdays',
                       json={'date_from': '2026-10-01', 'date_to': '2026-10-31'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert client.fake.period == ('2026-10-01', '2026-10-31')
    assert data['network']['weekend'] == {'shifts': 2, 'plan': 100000, 'revenue': 85000,
                                          'percent': 85.0, 'met': 0, 'bonus': 0}
    assert data['network']['weekdays']['met'] == 2
    venues = {v['venue_key']: v['total']['shifts'] for v in data['venues']}
    assert venues == {'ligovskiy': 3, 'kremenchugskaya': 1}     # «Пивная культура» = Кременчугская
    anna = next(p for p in data['employees'] if p['name'] == 'Анна Смирнова')
    assert anna['employee_id'] == 'e1' and anna['venues'] == ['ligovskiy']


def test_bonus_days_carry_venue(client):
    resp = client.post('/api/bonus-calculate', json={'date_from': '2026-10-01', 'date_to': '2026-10-31'})
    days = {d['date']: d['venue'] for e in resp.get_json()['employees'] for d in e['days']}
    assert days == {'2026-10-02': 'ligovskiy', '2026-10-05': 'ligovskiy',
                    '2026-10-09': 'ligovskiy', '2026-10-07': 'kremenchugskaya'}


def test_route_validates_before_iiko(client):
    for body in ({'date_from': '2026-10-31', 'date_to': '2026-10-01'},
                 {'date_from': '2025-01-01', 'date_to': '2026-10-31'},
                 {'date_from': '2026-10-01', 'date_to': '2026-10-31', 'weekend_days': [9]},
                 {'date_from': '2026-10-01', 'date_to': '2026-10-31', 'venue_key': 'Лиговский'}):
        resp = client.post('/api/shift-plan-weekdays', json=body)
        assert resp.status_code == 400 and resp.get_json()['error'], body
    assert client.calls == []


def test_route_no_shifts_is_404(client, monkeypatch):
    monkeypatch.setattr(_FakeIiko, 'SHIFTS', {})
    resp = client.post('/api/shift-plan-weekdays',
                       json={'date_from': '2026-10-01', 'date_to': '2026-10-31'})
    assert resp.status_code == 404
    assert 'Нет кассовых смен' in resp.get_json()['error']


def test_tool_matches_module_limits():
    from core.mcp.tools import staff
    spec = next(t for t in staff.TOOLS if t.name == 'staff_shift_plan_weekdays')
    props = spec.input_schema['properties']
    assert tuple(props['venue_key']['enum']) == spw.VENUE_CHOICES
    assert str(spw.MAX_DAYS) in spec.description
    assert props['weekend_days']['items'] == {'type': 'integer', 'minimum': 0, 'maximum': 6}
    assert spec.heavy and spec.read_only and spec.path == '/api/shift-plan-weekdays'


def test_tool_through_mcp_bridge_behind_auth_gate(monkeypatch):
    """Как зовёт бот: мост MCP с настоящим гейтом входа; расчёт премий внутри — вложенный запрос."""
    from tests import test_mcp_bridge as tmb
    from core.mcp.tools import staff
    import routes.employee as emp
    _patch_iiko(monkeypatch)

    class EnvWithEmployee(tmb.Env):
        @staticmethod
        def _app():
            app = tmb.Env._app()
            app.register_blueprint(emp.employee_bp)
            return app

    spec = next(t for t in staff.TOOLS if t.name == 'staff_shift_plan_weekdays')
    body = {'date_from': '2026-10-01', 'date_to': '2026-10-31', 'weekend_days': [4, 5]}
    with EnvWithEmployee() as env:
        result = env.run(spec, body, connector='staff')
        direct = env.client.post('/api/shift-plan-weekdays', json=body)
    assert direct.status_code == 200 and not result.is_error, result.text_value
    # Тяжёлое чтение: первая строка — «Данные на ЧЧ:ММ МСК (кэш до 5 минут)», дальше JSON маршрута.
    first, rest = result.text_value.split('\n', 1)
    assert first.startswith('Данные на ') and 'кэш до' in first
    import json
    assert json.loads(rest) == direct.get_json()
    assert json.loads(rest)['network']['total']['shifts'] == 4

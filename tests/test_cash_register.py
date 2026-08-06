"""
Тесты кассового регистра — раздел «Касса за месяц» на странице ЗП.

Что проверяем:
  * разбор сумм (₽ -> копейки) — одно правило для бармена и бухгалтера;
  * сборку строк и ПРОБЕЛЫ («касса не сдана»): условие обязано совпадать с тем,
    которое снимает премию за передачу смены (routes/employee.py);
  * что штраф находится по стабильному id после переименования в iiko;
  * эндпоинты: правка без окна 72 ч только администратору, штраф тем же
    запросом, возврат премии другим сотрудникам смены — сообщением.
"""

import pytest
from flask import Flask

from core.cash_register import (
    CASH_MAX_RUB, PROBLEM_NO_CASH, PROBLEM_NO_NOTE, PROBLEM_NO_SHIFT,
    build_register, fmt_kop, index_penalties, is_evening, rub_to_kop)
from core.shifts_manager import ShiftsManager


RULE_FROM = '2026-07-11'   # HANDOVER_CASH_RULE_FROM
TODAY = '2026-08-01'


# ==================== Суммы: рубли <-> копейки ====================

def test_rub_to_kop_basics():
    assert rub_to_kop(None) == (True, None)      # поле не заполнено
    assert rub_to_kop('') == (True, None)
    assert rub_to_kop(0) == (True, 0)            # «не было» — это НЕ пусто
    assert rub_to_kop(350.5) == (True, 35050)
    assert rub_to_kop(15340.25) == (True, 1534025)


def test_rub_to_kop_rejects_garbage():
    assert rub_to_kop(-1) == (False, None)
    assert rub_to_kop(CASH_MAX_RUB + 1) == (False, None)
    assert rub_to_kop('abc') == (False, None)
    assert rub_to_kop(float('nan')) == (False, None)
    assert rub_to_kop(float('inf')) == (False, None)


def test_rub_to_kop_accepts_excel_style_strings():
    """Бухгалтер копирует сумму из русского Excel: «15 340,25»."""
    assert rub_to_kop('350,50') == (True, 35050)
    assert rub_to_kop('15 340,25') == (True, 1534025)
    assert rub_to_kop(' 1 000 ') == (True, 100000)   # неразрывные пробелы
    assert rub_to_kop('   ') == (True, None)


def test_fmt_kop():
    assert fmt_kop(None) == '—'
    assert fmt_kop(1534025) == '15 340.25'
    assert fmt_kop(500000) == '5 000'
    assert fmt_kop(0) == '0'


# ==================== День/вечер ====================

def test_is_evening_mirrors_frontend():
    """Зеркало S.isEvening: роль «второй …» или старт >= 18:00."""
    assert is_evening('второй бармен', None) is True
    assert is_evening('Второй Бармен', '12:00') is True
    assert is_evening('бармен', '18:00') is True
    assert is_evening('бармен', '17:59') is False
    assert is_evening('бармен', None) is False


# ==================== Индекс штрафов ====================

def test_index_penalties_id_wins_and_name_only_without_id():
    by_id, by_name = index_penalties([
        {'date': '2026-07-16', 'employee_id': 'guid-1', 'employee_name': 'Алексей Стажер',
         'note': 'забыта трата'},
        {'date': '2026-07-20', 'employee_id': None, 'employee_name': 'Без Идишника',
         'note': None},
    ])
    assert by_id == {'guid-1': {'2026-07-16': 'забыта трата'}}
    # строка С id по имени не индексируется — иначе штраф уехал бы однофамильцу
    assert by_name == {'без идишника': {'2026-07-20': None}}


# ==================== Сборка регистра ====================

def _shift(sid, date, loc=1, name='Егор Бобриков', emp_id='guid-1', role='бармен',
           start=None, exp=None, note=None, col=None, end=None):
    return {
        'id': sid, 'date': date, 'employee_name': name, 'employee_id': emp_id,
        'start_time': start, 'location_id': loc, 'location_name': 'Кременчугская',
        'location_short': 'Крем', 'role_name': role,
        'cash_expense_kop': exp, 'cash_expense_note': note,
        'cash_collection_kop': col, 'cash_end_kop': end,
    }


def _reg(shifts, penalties=()):
    return build_register(shifts, list(penalties), today=TODAY, rule_from=RULE_FROM)


def test_gap_is_flagged_for_past_day_shift_without_cash():
    reg = _reg([_shift(1, '2026-07-20')])
    assert reg['rows'][0]['problems'] == [PROBLEM_NO_CASH]
    assert reg['rows'][0]['cash_expected'] is True
    assert reg['totals']['problems'] == 1


def test_no_gap_before_rule_date():
    """До 11.07.2026 кассовой дисциплины не было — пробелом не считаем."""
    reg = _reg([_shift(1, '2026-07-05')])
    assert reg['rows'][0]['problems'] == []
    assert reg['rows'][0]['cash_expected'] is False


def test_no_gap_for_today_and_future():
    """Кассу сдают в конце смены: сегодня и завтра — ещё не пробел."""
    reg = _reg([_shift(1, TODAY), _shift(2, '2026-08-10')])
    assert [r['problems'] for r in reg['rows']] == [[], []]


def test_no_gap_when_evening_shift_closed_the_day():
    """День закрыт, если кассу внёс кто угодно на этой точке — как в расчёте."""
    reg = _reg([
        _shift(1, '2026-07-20', start='10:00'),
        _shift(2, '2026-07-20', start='18:00', name='Дарья Коновцова',
               emp_id='guid-2', end=1500000),
    ])
    assert all(not r['problems'] for r in reg['rows'])
    assert all(r['day_closed'] for r in reg['rows'])


def test_gap_shown_once_for_two_day_shifts():
    """Два дневных бармена в дне — предупреждение на первой смене, не на обеих."""
    reg = _reg([
        _shift(1, '2026-07-20', start='10:00'),
        _shift(2, '2026-07-20', start='12:00', name='Роман Юреня', emp_id='guid-2'),
    ])
    flagged = [r['shift_id'] for r in reg['rows'] if r['problems']]
    assert flagged == [1]


def test_evening_shift_never_gets_cash_gap():
    reg = _reg([_shift(1, '2026-07-20', role='второй бармен')])
    assert reg['rows'][0]['problems'] == []


def test_expense_without_note_is_a_problem():
    rows = _reg([
        _shift(1, '2026-07-20', exp=35050, end=1500000),
        _shift(2, '2026-07-21', exp=35050, note='лёд', end=1500000),
        _shift(3, '2026-07-22', exp=0, end=1500000),          # трат не было
    ])['rows']
    assert rows[0]['problems'] == [PROBLEM_NO_NOTE]
    assert rows[1]['problems'] == []
    assert rows[2]['problems'] == []


def test_penalty_found_by_id_after_rename():
    """Сотрудника переименовали в iiko — штраф ищется по id, не по имени."""
    reg = _reg([_shift(1, '2026-07-16', name='Алексей Марченко', emp_id='guid-1',
                       end=1500000)],
               [{'date': '2026-07-16', 'employee_id': 'guid-1',
                 'employee_name': 'Алексей Стажер', 'note': 'забыта трата'}])
    row = reg['rows'][0]
    assert row['penalized'] is True
    assert row['penalty_note'] == 'забыта трата'
    assert reg['totals']['penalties'] == 1


def test_penalty_by_name_only_for_rows_without_id():
    """Штраф с чужим id к сотруднику не липнет, штраф без id находится по имени."""
    other = _reg([_shift(1, '2026-07-16', name='Тёзка Тёзкин', emp_id='guid-me',
                         end=1500000)],
                 [{'date': '2026-07-16', 'employee_id': 'guid-other',
                   'employee_name': 'Тёзка Тёзкин', 'note': 'чужой'}])
    shift_row = next(r for r in other['rows'] if r['shift_id'] == 1)
    assert shift_row['penalized'] is False
    # но и не проглатываем: чужой штраф видно отдельной строкой без смены
    assert [r['problems'] for r in other['rows'] if r['shift_id'] is None] \
        == [[PROBLEM_NO_SHIFT]]

    legacy = _reg([_shift(1, '2026-07-16', name='Без Айди', emp_id=None, end=1500000)],
                  [{'date': '2026-07-16', 'employee_id': None,
                    'employee_name': 'без айди', 'note': 'свой'}])
    assert legacy['rows'][0]['penalized'] is True
    assert len(legacy['rows']) == 1


def test_penalty_without_shift_becomes_its_own_row():
    """Штраф, не легший ни на одну смену, показывается строкой без смены.

    Реальный случай прода 26.07.2026: штраф стоял на дне, которого нет в графике
    (дни на странице ЗП берутся из кассовых смен iiko) — регистр показывал 9
    штрафов из 10. Молча терять нельзя: регистр перестаёт сходиться с расчётом.
    """
    reg = _reg([_shift(1, '2026-07-20', end=1500000)],
               [{'date': '2026-07-26', 'employee_id': 'guid-нет-смены',
                 'employee_name': 'Егор Верещагин', 'note': 'пропущена трата'}])
    orphan = [r for r in reg['rows'] if r['shift_id'] is None]
    assert len(orphan) == 1
    assert orphan[0]['problems'] == [PROBLEM_NO_SHIFT]
    assert orphan[0]['penalized'] is True
    assert orphan[0]['penalty_note'] == 'пропущена трата'
    assert orphan[0]['location_id'] is None      # точки нет -> в фильтр не попадёт
    # штрафы периода сходятся с БД, «смен» считаем только настоящие
    assert reg['totals']['penalties'] == 1
    assert reg['totals']['shifts'] == 1


def test_penalty_matched_by_shift_makes_no_orphan_row():
    reg = _reg([_shift(1, '2026-07-20', end=1500000)],
               [{'date': '2026-07-20', 'employee_id': 'guid-1',
                 'employee_name': 'Егор Бобриков', 'note': None}])
    assert all(r['shift_id'] is not None for r in reg['rows'])
    assert len(reg['rows']) == 1


def test_totals_and_locations():
    reg = _reg([
        _shift(1, '2026-07-20', loc=1, exp=35050, note='лёд', col=2000000, end=1534025),
        _shift(2, '2026-07-21', loc=2, exp=None, col=0, end=300000),
    ])
    # точки в ответе — только те, что есть в периоде
    assert [l['id'] for l in reg['locations']] == [1, 2]
    t = reg['totals']
    assert t['shifts'] == 2 and t['with_cash'] == 2
    assert t['expense_kop'] == 35050
    assert t['collection_kop'] == 2000000


def test_rows_sorted_by_date():
    reg = _reg([_shift(2, '2026-07-25', end=1), _shift(1, '2026-07-20', end=1)])
    assert [r['date'] for r in reg['rows']] == ['2026-07-20', '2026-07-25']


# ==================== Эндпоинты ====================

@pytest.fixture
def api(tmp_path, monkeypatch):
    """Приложение с одним блюпринтом ЗП, временной БД и подменённым юзером.

    Возвращает (client, mgr, set_user): set_user(is_admin) переключает права.
    """
    import core.auth_guard as guard
    import routes.salary as salary

    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    monkeypatch.setattr(salary, 'shifts_mgr', mgr)

    user = {'login': 'owner', 'display_name': 'Владелец', 'is_admin': True}
    monkeypatch.setattr(guard, '_load_user', lambda: user)
    monkeypatch.setattr(salary, 'current_user', lambda: user)

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'
    app.register_blueprint(salary.salary_bp)

    def set_admin(flag):
        user['is_admin'] = flag

    return app.test_client(), mgr, set_admin


def _make_shift(mgr, date_str='2026-07-20', name='Егор Бобриков', emp_id='guid-1',
                role_idx=0):
    loc = mgr.get_locations()[0]
    role = mgr.get_roles()[role_idx]
    return mgr.create_shift(date_str, name, loc['id'], role['id'], employee_id=emp_id)


def test_register_endpoint_lists_gap(api):
    client, mgr, _ = api
    _make_shift(mgr)
    r = client.get('/api/salary/cash-register?date_from=2026-07-01&date_to=2026-07-31')
    assert r.status_code == 200
    data = r.get_json()
    assert data['can_edit'] is True
    assert data['rule_from'] == RULE_FROM
    assert [row['problems'] for row in data['rows']] == [[PROBLEM_NO_CASH]]


def test_register_endpoint_validates_period(api):
    client, _, _ = api
    assert client.get('/api/salary/cash-register').status_code == 400
    assert client.get('/api/salary/cash-register?date_from=2026-07-31'
                      '&date_to=2026-07-01').status_code == 400
    assert client.get('/api/salary/cash-register?date_from=2020-01-01'
                      '&date_to=2026-12-31').status_code == 400   # период-переросток


def test_admin_fills_cash_late_and_penalty_lands(api):
    """Главный сценарий: касса внесена задним числом -> премия остаётся снятой."""
    client, mgr, _ = api
    sid = _make_shift(mgr)
    r = client.put(f'/api/salary/cash-register/shift/{sid}', json={
        'cash_expense': '350,50', 'cash_expense_note': 'лёд',
        'cash_collection': 0, 'cash_end': 15340.25,
        'penalize': True, 'penalty_note': 'касса не сдана, внесена задним числом',
    })
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['cash_changed'] is True and body['penalty_changed'] is True

    sh = mgr.get_shift(sid)
    assert (sh['cash_expense_kop'], sh['cash_expense_note']) == (35050, 'лёд')
    assert (sh['cash_collection_kop'], sh['cash_end_kop']) == (0, 1534025)

    pens = mgr.get_handover_penalties('2026-07-01', '2026-07-31')
    assert len(pens) == 1
    assert pens[0]['employee_id'] == 'guid-1'          # ключ штрафа — id, не имя
    assert pens[0]['note'] == 'касса не сдана, внесена задним числом'

    # оба действия в журнале графика — правка задним числом обязана быть видна
    actions = {a['action'] for a in mgr.get_audit(2026, 7)}
    assert {'cash_admin_set', 'handover_penalty'} <= actions


def test_ignores_edit_window(api):
    """Окно 72 ч регистр не касается: смысл раздела — внести старое."""
    client, mgr, _ = api
    sid = _make_shift(mgr, '2026-01-15')
    r = client.put(f'/api/salary/cash-register/shift/{sid}',
                   json={'cash_end': 1000})
    assert r.status_code == 200
    assert mgr.get_shift(sid)['cash_end_kop'] == 100000


def test_non_admin_cannot_edit(api):
    client, mgr, set_admin = api
    sid = _make_shift(mgr)
    set_admin(False)
    r = client.put(f'/api/salary/cash-register/shift/{sid}', json={'cash_end': 1000})
    assert r.status_code == 403
    assert mgr.get_shift(sid)['cash_end_kop'] is None
    # смотреть регистр можно всем, только без правки
    data = client.get('/api/salary/cash-register?date_from=2026-07-01'
                      '&date_to=2026-07-31').get_json()
    assert data['can_edit'] is False


def test_penalty_untouched_when_field_absent(api):
    """Без поля penalize штраф не появляется: правка кассы и штраф независимы."""
    client, mgr, _ = api
    sid = _make_shift(mgr)
    client.put(f'/api/salary/cash-register/shift/{sid}', json={'cash_end': 1000})
    assert mgr.get_handover_penalties('2026-07-01', '2026-07-31') == []


def test_penalize_false_removes_penalty(api):
    client, mgr, _ = api
    sid = _make_shift(mgr)
    mgr.set_handover_penalty('2026-07-20', 'Егор Бобриков', True, 'старый',
                             employee_id='guid-1')
    r = client.put(f'/api/salary/cash-register/shift/{sid}',
                   json={'cash_end': 1000, 'penalize': False})
    assert r.status_code == 200 and r.get_json()['penalty_changed'] is True
    assert mgr.get_handover_penalties('2026-07-01', '2026-07-31') == []


def test_reports_whose_premium_came_back(api):
    """Закрытие пробела возвращает премию остальным на точке — говорим об этом."""
    client, mgr, _ = api
    loc = mgr.get_locations()[0]
    roles = mgr.get_roles()
    day = mgr.create_shift('2026-07-20', 'Егор Бобриков', loc['id'], roles[0]['id'],
                           employee_id='guid-1')
    mgr.create_shift('2026-07-20', 'Дарья Коновцова', loc['id'], roles[-1]['id'],
                     employee_id='guid-2')
    body = client.put(f'/api/salary/cash-register/shift/{day}',
                      json={'cash_end': 1000, 'penalize': True}).get_json()
    assert body['premium_restored_for'] == ['Дарья Коновцова']

    # день уже закрыт — повторная правка никому премию не «возвращает»
    body2 = client.put(f'/api/salary/cash-register/shift/{day}',
                       json={'cash_end': 2000}).get_json()
    assert body2['premium_restored_for'] == []


def test_bad_amount_is_rejected(api):
    client, mgr, _ = api
    sid = _make_shift(mgr)
    r = client.put(f'/api/salary/cash-register/shift/{sid}',
                   json={'cash_end': CASH_MAX_RUB + 1})
    assert r.status_code == 400
    assert mgr.get_shift(sid)['cash_end_kop'] is None
    assert client.put('/api/salary/cash-register/shift/999999',
                      json={'cash_end': 1}).status_code == 404


def test_audit_summary_lists_only_changed_fields():
    """В журнале — что именно стало другим, а не «касса переписана»."""
    from routes.salary import _cash_diff_summary
    sh = {'cash_expense_kop': 100, 'cash_collection_kop': 0,
          'cash_end_kop': 500, 'cash_expense_note': 'лёд'}
    assert _cash_diff_summary(sh, 100, 0, 500, 'лёд') == []
    changes = _cash_diff_summary(sh, 100, 200, 500, 'лёд')
    assert len(changes) == 1 and 'инкассация' in changes[0]

"""
Тесты резолвера личности `/me` (core/me_identity.py).

Совместимы с pytest, но pytest локально может быть не установлен, поэтому файл
self-runnable: `py -3 tests/test_me_identity.py`.

Главное, что проверяется: резолвер НИКОГДА не отдаёт строку другого человека.
Всё остальное — производные от этого правила: строгое имя, отказ при двойной
привязке, явные статусы вместо нулей.

Функции модуля чистые (ни Flask, ни сети, ни БД), поэтому моков здесь нет —
данные собираются литералами.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.me_identity import (  # noqa: E402
    SNAPSHOT_SCHEMA, resolve_me, strict_same_name, norm_name, is_name_unique,
    find_in_registry,
)

ID_A = '4b83e5be-aaaa'
ID_B = '4b83e5be-bbbb'
ID_C = '4b83e5be-cccc'


def _user(iiko_id, login='roman', name='Юреня Роман'):
    return {'id': 1, 'login': login, 'display_name': name, 'short_label': 'ЮР',
            'employee_iiko_id': iiko_id, 'is_admin': False, 'active': True}


def _emp(iiko_id, name, active=True, in_registry=True):
    return {'id': iiko_id, 'name': name, 'short_label': None,
            'active': active, 'sort_order': 0, 'in_registry': in_registry}


def _row(iiko_id, name, *, hours_trust='id', total=1000.0, excluded=None,
         metrics_status='ok', kpi_status='ok'):
    return {
        'employee_id': iiko_id,
        'name_iiko': name, 'name_olap': name, 'name_schedule': name,
        'metrics': {'status': metrics_status, 'total_revenue': 100.0},
        'kpi': {'status': kpi_status, 'total_premium': 500.0},
        'hours': {'trust': hours_trust, 'total_hours': 97.0, 'total_pay': 29100.0,
                  'employee_name': name},
        'money': {'total': total, 'excluded_components': excluded or []},
    }


def _snap(rows, *, schema=SNAPSHOT_SCHEMA, unlinked=None):
    return {
        '_schema': schema, '_month': '2026-08',
        '_refreshed_at': '2026-08-13T07:42:11+03:00',
        'employees': {r['employee_id']: r for r in rows},
        'unlinked_hours': unlinked or [],
    }


# --- правило имён ---

def test_strict_name_rejects_one_word_subset():
    """Прямая противоположность _names_match из core/salary_payload.py, где
    хватает одного общего слова. Одного слова здесь не хватает никогда."""
    assert strict_same_name('Юреня', 'Юреня Иван') is False
    assert strict_same_name('Юреня Иван', 'Юреня') is False
    assert strict_same_name('Юреня', 'Юреня') is False       # одно слово с обеих сторон
    assert strict_same_name('Юреня Роман', 'Роман Юреня') is True   # порядок не важен
    assert strict_same_name('юреня роман', 'Юреня Роман') is True   # регистр не важен
    assert strict_same_name('Юреня Роман', 'Юреня Иван') is False
    assert strict_same_name('', 'Юреня Роман') is False
    assert strict_same_name(None, None) is False


def test_norm_name_and_uniqueness():
    assert norm_name('  Юреня   Роман ') == 'роман юреня'
    names = ['Юреня Роман', 'Иванов Иван', 'Иван Иванов']
    assert is_name_unique('Юреня Роман', names) is True
    assert is_name_unique('Роман Юреня', names) is True      # та же нормальная форма
    assert is_name_unique('Иванов Иван', names) is False     # два раза в списке
    assert is_name_unique('', names) is False


def test_find_in_registry_by_id_only():
    reg = [_emp(ID_A, 'Юреня Роман'), _emp(None, 'Без id')]
    assert find_in_registry(reg, ID_A)['name'] == 'Юреня Роман'
    assert find_in_registry(reg, ID_B) is None
    assert find_in_registry(reg, None) is None
    assert find_in_registry([], ID_A) is None


# --- отказы вместо чужих и вместо нулей ---

def test_not_linked_is_explicit_status():
    r = resolve_me(_user(None), _snap([_row(ID_A, 'Юреня Роман')]), month='2026-08')
    assert r['status'] == 'not_linked'
    assert r['row'] is None
    assert 'Аккаунты' in r['message']
    # пустая строка и пробелы — то же самое, что отсутствие привязки
    assert resolve_me(_user('   '), {}, month='2026-08')['status'] == 'not_linked'


def test_unknown_employee_id():
    r = resolve_me(_user(ID_C), _snap([_row(ID_A, 'Юреня Роман')]),
                   month='2026-08', registry=[_emp(ID_A, 'Юреня Роман')])
    assert r['status'] == 'unknown_employee'
    assert r['row'] is None
    assert ID_C in r['message']


def test_empty_registry_does_not_claim_unknown():
    """Пустой реестр = недоступна shifts.db, а не «сотрудника не существует»."""
    r = resolve_me(_user(ID_A), _snap([_row(ID_A, 'Юреня Роман')]),
                   month='2026-08', registry=[])
    assert r['status'] == 'ok', r


def test_two_accounts_one_employee_refuses_money():
    """Дубль привязки: деньги не показываются, оба логина названы."""
    linked = [{'login': 'roman', 'active': True}, {'login': 'roman2', 'active': True}]
    r = resolve_me(_user(ID_A), _snap([_row(ID_A, 'Юреня Роман')]), month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')], linked_users=linked)
    assert r['status'] == 'ambiguous_link'
    assert r['row'] is None
    assert 'roman' in r['message'] and 'roman2' in r['message']


def test_inactive_duplicate_account_does_not_block():
    """Выключенный аккаунт-дубль войти не может, поэтому не повод скрывать деньги."""
    linked = [{'login': 'roman', 'active': True}, {'login': 'roman_old', 'active': False}]
    r = resolve_me(_user(ID_A), _snap([_row(ID_A, 'Юреня Роман')]), month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')], linked_users=linked)
    assert r['status'] == 'ok', r


def test_never_returns_other_persons_row():
    """Однофамильцы: каждый id получает ровно свою строку, чужую — никогда."""
    snap = _snap([_row(ID_A, 'Юреня Роман', total=111.0),
                  _row(ID_B, 'Юреня Иван', total=222.0)])
    reg = [_emp(ID_A, 'Юреня Роман'), _emp(ID_B, 'Юреня Иван')]
    a = resolve_me(_user(ID_A), snap, month='2026-08', registry=reg)
    b = resolve_me(_user(ID_B, login='ivan', name='Юреня Иван'), snap,
                   month='2026-08', registry=reg)
    assert a['status'] == 'ok' and a['row']['money']['total'] == 111.0
    assert b['status'] == 'ok' and b['row']['money']['total'] == 222.0
    # id, которого в снимке нет, НЕ ищется по имени, даже если имя совпадает
    c = resolve_me(_user(ID_C, name='Юреня Роман'), snap, month='2026-08',
                   registry=reg + [_emp(ID_C, 'Юреня Роман')])
    assert c['status'] == 'not_in_snapshot'
    assert c['row'] is None


def test_missing_snapshot_is_not_error():
    r = resolve_me(_user(ID_A), {}, month='2026-08', registry=[_emp(ID_A, 'Юреня Роман')])
    assert r['status'] == 'no_snapshot'
    assert r['row'] is None
    assert r['employee_name'] == 'Юреня Роман'   # имя из реестра всё равно известно


def test_schema_mismatch_hides_money():
    snap = _snap([_row(ID_A, 'Юреня Роман')], schema=SNAPSHOT_SCHEMA + 1)
    r = resolve_me(_user(ID_A), snap, month='2026-08', registry=[_emp(ID_A, 'Юреня Роман')])
    assert r['status'] == 'schema_mismatch'
    assert r['row'] is None


def test_status_order_link_problems_first():
    """Проблема привязки важнее отсутствия снимка: сначала чиним привязку."""
    linked = [{'login': 'a', 'active': True}, {'login': 'b', 'active': True}]
    r = resolve_me(_user(ID_A), {}, month='2026-08', linked_users=linked)
    assert r['status'] == 'ambiguous_link'


# --- issues: расщеплённые часы и недостоверные суммы ---

def test_hours_matched_by_name_is_warned_not_hidden():
    row = _row(ID_A, 'Юреня Роман', hours_trust='name_strict')
    r = resolve_me(_user(ID_A), _snap([row]), month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')])
    assert r['status'] == 'ok'
    codes = [i['code'] for i in r['issues']]
    assert 'hours_matched_by_name' in codes
    assert [i['severity'] for i in r['issues'] if i['code'] == 'hours_matched_by_name'] == ['warn']


def test_unsafe_hours_are_error_with_excluded_components():
    row = _row(ID_A, 'Юреня Роман', hours_trust='unsafe',
               excluded=['hours_pay', 'taxi'])
    r = resolve_me(_user(ID_A), _snap([row]), month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')])
    issue = [i for i in r['issues'] if i['code'] == 'hours_attribution_unsafe'][0]
    assert issue['severity'] == 'error'
    assert issue['detail']['excluded_components'] == ['hours_pay', 'taxi']
    assert 'НЕ включены' in issue['message']


def test_split_hours_reports_missing_amount():
    """Осиротевшая строка часов с тем же полным именем — явный дефицит с суммой."""
    orphan = {'employee_name': 'Юреня Роман', 'total_hours': 16.0,
              'total_pay': 4800.0, 'day_shifts': 2}
    snap = _snap([_row(ID_A, 'Юреня Роман')], unlinked=[orphan])
    r = resolve_me(_user(ID_A), snap, month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')])
    assert r['status'] == 'ok'
    issue = [i for i in r['issues'] if i['code'] == 'hours_unlinked_shifts'][0]
    assert issue['detail']['hours'] == 16.0
    assert issue['detail']['pay'] == 4800.0
    assert issue['detail']['certain'] is True
    assert '16' in issue['message'] and '4800' in issue['message'].replace(' ', '')


def test_orphan_with_one_word_name_is_not_mine():
    """«Юреня» без id не приклеивается к «Юреня Роман» — это и есть R3."""
    orphan = {'employee_name': 'Юреня', 'total_hours': 16.0, 'total_pay': 4800.0}
    snap = _snap([_row(ID_A, 'Юреня Роман')], unlinked=[orphan])
    r = resolve_me(_user(ID_A), snap, month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')])
    assert [i['code'] for i in r['issues']] == []


def test_homonym_registry_marks_orphan_ambiguous():
    """При полном тёзке в реестре принадлежность часов не утверждается."""
    orphan = {'employee_name': 'Иванов Иван', 'total_hours': 8.0, 'total_pay': 2400.0}
    snap = _snap([_row(ID_A, 'Иванов Иван')], unlinked=[orphan])
    reg = [_emp(ID_A, 'Иванов Иван'), _emp(ID_B, 'Иван Иванов')]
    r = resolve_me(_user(ID_A, name='Иванов Иван'), snap, month='2026-08', registry=reg)
    issue = [i for i in r['issues'] if i['code'] == 'hours_unlinked_shifts'][0]
    assert issue['detail']['certain'] is False
    assert 'тёзка' in issue['message']


def test_metrics_and_kpi_statuses_become_issues():
    row = _row(ID_A, 'Юреня Роман', metrics_status='no_olap_name', kpi_status='no_data')
    r = resolve_me(_user(ID_A), _snap([row]), month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')])
    codes = [i['code'] for i in r['issues']]
    assert 'metrics_unavailable' in codes
    assert 'kpi_unavailable' in codes
    kpi_issue = [i for i in r['issues'] if i['code'] == 'kpi_unavailable'][0]
    assert 'Цели месяца' in kpi_issue['message']


def test_clean_row_has_no_issues():
    r = resolve_me(_user(ID_A), _snap([_row(ID_A, 'Юреня Роман')]), month='2026-08',
                   registry=[_emp(ID_A, 'Юреня Роман')])
    assert r['issues'] == []


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            import traceback
            print(f'FAIL {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())

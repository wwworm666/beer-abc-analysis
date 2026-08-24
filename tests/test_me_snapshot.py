"""
Тесты сборщика снимка личного кабинета (core/me_snapshot.py).

Self-runnable: `py -3 tests/test_me_snapshot.py`.

Главный тест здесь — `test_money_total_matches_salary_page_formula`: итог на /me
обязан совпадать с формулой страницы расчёта ЗП (`recalcEmployeeTotals` в
templates/bonus.html). Расхождение означает, что кабинет разошёлся с тем, по чему
владелец платит, и человек увидит одну сумму, а получит другую.

Остальное — про честность отказов: сбой источника не обнуляет уже собранный
снимок, пустой OLAP даёт нули, а недостоверные часы исключаются из итога.

Моков iiko нет: источники подменяются атрибутами модуля (тот же приём, что в
tests/test_salary_payload.py), каталог снимков — временный.
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.me_snapshot as ms  # noqa: E402
from core.me_identity import (SNAPSHOT_SCHEMA, is_name_unique,  # noqa: E402
                              norm_name, strict_same_name)

ID_A = 'guid-aaaa'
ID_B = 'guid-bbbb'


# ==================== фикстуры данных ====================

def _bonus_row(emp_id, name, *, day_plan=17420.0, handover=6000.0, penalty=750.0,
               late=2, shifts=14, plan=1180000.0, revenue=1284310.0):
    return {
        'name': name, 'employee_id': emp_id,
        'plan_revenue': plan, 'total_revenue': revenue, 'plan_percent': 108.8,
        'overperformance': 128400.0,
        'bonus': day_plan, 'shifts_count': shifts, 'late_count': late,
        'penalty': penalty, 'net': day_plan - penalty,
        'shift_handover_bonus': handover, 'shift_handover_unpaid_days': 1,
        'shift_handover_manual_days': 1, 'shift_handover_base_days': 14,
        'shift_handover_paid_days': 12, 'total_hours': 144.1,
        'days': [
            {'date': '2026-08-04', 'overperformance': 5000.0, 'is_late': True},
            {'date': '2026-08-05', 'overperformance': 0.0, 'is_late': False},
            {'date': '2026-08-11', 'overperformance': 3000.0, 'is_late': True},
        ],
    }


def _kpi_row(emp_id, name, *, koef=0.93, total=13120.0):
    return {
        'employee_name': name, 'employee_id': emp_id,
        'total_shifts': 14, 'koef': koef,
        'shifts_per_location': {'Варшавская': 9, 'Лиговский': 5},
        'kpi_count': 3, 'base_per_kpi': 5000, 'kpi_pool': 15000,
        'kpis': {
            'kpi1': {'name': 'Доля кухни (%)', 'metric': 'kitchen_share',
                     'fact': 18.1, 'target': 18.0, 'min': 13.0,
                     'ratio': 1.02, 'capped_ratio': 1.02,
                     'intermediate_premium': 5100.0},
            'kpi2': {'name': 'Доля розлива (%)', 'metric': 'draft_share',
                     'fact': 61.2, 'target': 58.0, 'min': 52.0,
                     'ratio': 1.53, 'capped_ratio': 1.53,
                     'intermediate_premium': 7650.0},
        },
        'total_premium': total,
    }


def _hours_row(emp_id, name, *, pay=29100.0, day_shifts=12, hours=97.0):
    return {
        'employee_name': name, 'employee_id': emp_id,
        'total_hours': hours, 'total_pay': pay, 'total_minutes': int(hours * 60),
        'day_shifts': day_shifts, 'shifts_with_fact': 13, 'shifts_without_fact': 1,
        'roles': [{'role_id': 1, 'role_name': 'бармен', 'rate_per_hour': 300,
                   'minutes': int(hours * 60), 'hours': hours, 'pay': pay}],
    }


def _olap_all(name):
    """Минимальный набор шести отчётов, где сотрудник присутствует.

    `aggregated` — свёрнутый словарь {имя: метрики}, как отдаёт
    get_employee_aggregated_metrics; остальные — сырые {'data': [...]}.
    """
    return {
        'aggregated': {name: {'UniqOrderId.OrdersCount': 812,
                              'DishDiscountSumInt': 1284310.0,
                              'DiscountSum': 41220.0, 'DishAmountInt': 900}},
        'draft': {'data': []}, 'bottles': {'data': []}, 'kitchen': {'data': []},
        'cancelled': {'data': []}, 'loyalty': {name: 11},
    }


def _kpi_data():
    return {
        'kpi_config': {'kpi1': {'metric': 'kitchen_share', 'name': 'Доля кухни (%)'},
                       'kpi2': {'metric': 'draft_share', 'name': 'Доля розлива (%)'}},
        'defaults': {'norm_shifts': 15, 'kpi_pool': 15000, 'base_premium': 5000,
                     'max_ratio': 2},
    }


def _assemble(bonus, kpi, hours, *, olap=None, kpi_data=None, status=None):
    return ms._assemble(
        '2026-08', '2026-08-01', '2026-08-31',
        bonus, kpi, hours,
        [{'name': 'бармен', 'rate_per_hour': 300, 'sort_order': 0}],
        kpi_data if kpi_data is not None else _kpi_data(),
        olap if olap is not None else {},
        status or {'bonus': 'ok', 'kpi': 'ok', 'hours': 'ok', 'olap_metrics': 'ok'},
        'test', norm_fn=norm_name)


def _tmp_dir():
    path = tempfile.mkdtemp(prefix='me_snap_t_')
    orig = ms.snapshot_dir
    ms.snapshot_dir = lambda: path

    def restore():
        ms.snapshot_dir = orig
        shutil.rmtree(path, ignore_errors=True)
    return path, restore


# ==================== ГЛАВНОЕ: деньги ====================

def test_money_total_matches_salary_page_formula():
    """Итог = формула recalcEmployeeTotals (templates/bonus.html:906).

        total = часы×ставка + такси + передача смены + дневной план
                + KPI − штраф за опоздания

    Числа посчитаны руками: 29100 + 12×700 + 6000 + 17420 + 13120 − 750 = 73290.
    """
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                     [_kpi_row(ID_A, 'Юреня Роман')],
                     [_hours_row(ID_A, 'Юреня Роман')])
    money = snap['employees'][ID_A]['money']
    assert money['hours_pay'] == 29100.0
    assert money['taxi']['sum'] == 8400.0          # 12 дневных смен × 700
    assert money['handover']['sum'] == 6000.0
    assert money['day_plan']['sum'] == 17420.0
    assert money['kpi']['sum'] == 13120.0
    assert money['late']['sum'] == 750.0
    assert money['total'] == 73290.0, money['total']
    # и то же значение, посчитанное независимо от разложения
    expected = (money['hours_pay'] + money['taxi']['sum'] + money['handover']['sum']
                + money['day_plan']['sum'] + money['kpi']['sum'] - money['late']['sum'])
    assert money['total'] == round(expected, 2)


def test_money_excludes_excel_only_rows():
    """В деньгах нет строк, которые владелец ведёт в Excel, и нет 10 500."""
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                     [_kpi_row(ID_A, 'Юреня Роман')],
                     [_hours_row(ID_A, 'Юреня Роман')])
    money = snap['employees'][ID_A]['money']
    for forbidden in ('vacation', 'extra_income', 'deduction_inventory',
                      'deduction_other', 'bridges', 'taxi_official', 'adjustments'):
        assert forbidden not in money, forbidden
    # зачёт официального такси (15 смен × 700 = 10 500) в кабинет не приходит
    assert money['total'] != 73290.0 - 10500
    assert money['taxi']['day_shifts'] == 12       # факт, а не фикс 15


def test_money_day_plan_and_late_breakdown():
    """Разложение премии и вычета: человек видит, из чего сложилось."""
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                     [_kpi_row(ID_A, 'Юреня Роман')],
                     [_hours_row(ID_A, 'Юреня Роман')])
    money = snap['employees'][ID_A]['money']
    assert money['day_plan']['days_paid'] == 2      # два дня с перевыполнением > 0
    assert money['day_plan']['base_per_day'] == 1000
    assert money['day_plan']['over_share'] == 0.05
    assert money['late']['dates'] == ['2026-08-04', '2026-08-11']
    assert money['late']['step'] == 250
    assert money['handover']['paid_days'] == 12 and money['handover']['base_days'] == 14
    # массив дней целиком в снимок не пишем — только производные счётчики
    assert 'days' not in snap['employees'][ID_A]


def test_no_bonus_source_gives_hours_only_month():
    """Начало месяца: продаж нет — премии нулевые, часы и такси из графика."""
    snap = _assemble([], [], [_hours_row(ID_A, 'Юреня Роман')])
    money = snap['employees'][ID_A]['money']
    assert money['handover']['sum'] == 0 and money['day_plan']['sum'] == 0
    assert money['kpi']['sum'] == 0 and money['late']['sum'] == 0
    assert money['total'] == 29100.0 + 8400.0
    assert snap['employees'][ID_A]['kpi']['status'] == 'no_data'


# ==================== ключ снимка и осиротевшие часы ====================

def test_snapshot_keys_by_employee_id():
    """Ключ employees — стабильный id (регрессия на потерю id в payload ЗП)."""
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                     [_kpi_row(ID_A, 'Юреня Роман')],
                     [_hours_row(ID_A, 'Юреня Роман')])
    assert list(snap['employees'].keys()) == [ID_A]
    assert snap['employees'][ID_A]['employee_id'] == ID_A


def test_unlinked_hours_separated_from_employees():
    """Строка часов без id не попадает в employees — только в unlinked_hours."""
    snap = _assemble([], [], [_hours_row(None, 'Юреня', pay=4800.0, day_shifts=2,
                                        hours=16.0)])
    assert snap['employees'] == {}
    assert len(snap['unlinked_hours']) == 1
    orphan = snap['unlinked_hours'][0]
    assert orphan['employee_name'] == 'Юреня'
    assert orphan['total_hours'] == 16.0 and orphan['total_pay'] == 4800.0


def test_split_hours_id_row_kept_orphan_listed():
    """Расщепление часов: строка по id в итоге, безымянная — отдельно.

    Две строки НЕ складываем: страница /salary, по которой платят, их тоже не
    складывает. Показать сумму больше выплаты хуже, чем назвать дефицит.
    """
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                     [_kpi_row(ID_A, 'Юреня Роман')],
                     [_hours_row(ID_A, 'Юреня Роман', pay=29100.0, day_shifts=12),
                      _hours_row(None, 'Юреня', pay=4800.0, day_shifts=2, hours=16.0)])
    assert snap['employees'][ID_A]['money']['hours_pay'] == 29100.0
    assert len(snap['unlinked_hours']) == 1
    assert snap['unlinked_hours'][0]['total_pay'] == 4800.0


# ==================== вердикт доверия к часам ====================

def test_hours_trust_verdicts():
    reg = ['Юреня Роман', 'Иванов Иван', 'Иван Иванов']
    kw = {'registry_names': reg, 'strict_fn': strict_same_name,
          'unique_fn': is_name_unique}
    # по стабильному id — доверяем
    assert ms.hours_trust(_hours_row(ID_A, 'Юреня Роман'), ID_A,
                          ['Юреня Роман'], **kw) == 'id'
    # id нет, полное имя совпало и в реестре единственное
    assert ms.hours_trust(_hours_row(None, 'Юреня Роман'), ID_A,
                          ['Юреня Роман'], **kw) == 'name_strict'
    # id нет, имя из одного слова — подмножество не связывает
    assert ms.hours_trust(_hours_row(None, 'Юреня'), ID_A,
                          ['Юреня Роман'], **kw) == 'unsafe'
    # id есть, но чужой
    assert ms.hours_trust(_hours_row(ID_B, 'Юреня Роман'), ID_A,
                          ['Юреня Роман'], **kw) == 'unsafe'
    # полный тёзка в реестре — принадлежность не утверждаем
    assert ms.hours_trust(_hours_row(None, 'Иванов Иван'), ID_A,
                          ['Иванов Иван'], **kw) == 'unsafe'
    # часов нет вовсе
    assert ms.hours_trust(None, ID_A, ['Юреня Роман'], **kw) == 'unsafe'


def _salary_page_total(bonus_row, kpi_row, hours_row):
    """Формула страницы ЗП — `recalcEmployeeTotals` в templates/bonus.html.

    Переписана здесь дословно и НЕ через `_money_for`: тест обязан ловить
    расхождение кабинета с тем, по чему реально платят, а не сверять кабинет
    сам с собой. При правке bonus.html правится и эта функция.
    """
    b, k, h = bonus_row or {}, kpi_row or {}, hours_row or {}
    hours_pay = h.get('total_pay') or 0
    taxi_pay = (h.get('day_shifts') or 0) * ms.TAXI_RATE_PER_SHIFT
    base = ((b.get('bonus') or 0) + (b.get('shift_handover_bonus') or 0)
            - (b.get('penalty') or 0) + (k.get('total_premium') or 0))
    return base + hours_pay + taxi_pay


def test_me_total_matches_salary_page_formula():
    """ИНВАРИАНТ: итог /me равен итогу /salary за тот же период.

    Проверяется на КАЖДОМ вердикте привязки часов: вердикт влияет только на
    предупреждение, но не на деньги. До 24.08.2026 при 'unsafe' кабинет
    показывал на 37 500 руб. меньше (29 100 часов + 8 400 такси).
    """
    b = _bonus_row(ID_A, 'Юреня Роман')
    k = _kpi_row(ID_A, 'Юреня Роман')
    h = _hours_row(None, 'Юреня')
    expected = _salary_page_total(b, k, h)
    # 17420 + 6000 - 750 + 13120 + 29100 + 12 x 700
    assert expected == 73290.0, expected
    for trust in ('id', 'name_strict', 'unsafe'):
        assert ms._money_for(b, k, h, trust)['total'] == expected, trust


def test_unsafe_hours_are_flagged_but_still_paid():
    """Недостоверная привязка — предупреждение, а не вычет из итога."""
    money = ms._money_for(_bonus_row(ID_A, 'Юреня Роман'),
                          _kpi_row(ID_A, 'Юреня Роман'),
                          _hours_row(None, 'Юреня'), 'unsafe')
    assert money['untrusted_components'] == ['hours_pay', 'taxi']
    assert 'excluded_components' not in money, 'старое поле-ловушка вернулось'
    assert money['hours_pay'] == 29100.0
    assert money['taxi']['sum'] == 8400.0
    # обе суммы внутри итога, а не рядом с ним
    assert money['total'] == 73290.0, money['total']


def test_trusted_hours_have_no_warning():
    money = ms._money_for(_bonus_row(ID_A, 'Юреня Роман'),
                          _kpi_row(ID_A, 'Юреня Роман'),
                          _hours_row(ID_A, 'Юреня Роман'), 'id')
    assert money['untrusted_components'] == []


def test_legacy_snapshot_total_is_healed_on_read():
    """Снимок замороженного месяца чинится при чтении, а не пересчётом.

    Файл июля после 7 августа уже не пересобрать (`months_to_build`), поэтому
    вычтенные часы и такси возвращаются в итог на лету.
    """
    legacy = {
        '_schema': 1,
        'employees': {
            ID_A: {'money': {'total': 35790.0, 'hours_pay': 29100.0,
                             'taxi': {'sum': 8400.0, 'day_shifts': 12},
                             'excluded_components': ['hours_pay', 'taxi']}},
            ID_B: {'money': {'total': 73290.0, 'hours_pay': 29100.0,
                             'taxi': {'sum': 8400.0, 'day_shifts': 12},
                             'excluded_components': []}},
        },
    }
    healed = ms._heal_legacy_money(legacy)
    a = healed['employees'][ID_A]['money']
    assert a['total'] == 73290.0, a['total']
    assert a['untrusted_components'] == ['hours_pay', 'taxi']
    assert 'excluded_components' not in a
    # у доверенной строки итог не трогаем — вычета там и не было
    b = healed['employees'][ID_B]['money']
    assert b['total'] == 73290.0
    assert b['untrusted_components'] == []


def test_heal_is_idempotent_on_new_snapshots():
    """Новый снимок через чинилку проходит без изменений."""
    money = ms._money_for(_bonus_row(ID_A, 'Юреня Роман'),
                          _kpi_row(ID_A, 'Юреня Роман'),
                          _hours_row(None, 'Юреня'), 'unsafe')
    snap = {'employees': {ID_A: {'money': dict(money)}}}
    assert ms._heal_legacy_money(snap)['employees'][ID_A]['money'] == money


# ==================== сопоставление имени с OLAP ====================

def test_olap_name_resolution_requires_unique_candidate():
    r = lambda n, names: ms.resolve_olap_name(n, names, norm_fn=norm_name)
    # точное совпадение
    assert r('Юреня Роман', ['Юреня Роман', 'Иванов Иван']) == 'Юреня Роман'
    # порядок слов другой
    assert r('Артемий Новаев', ['Новаев Артемий']) == 'Новаев Артемий'
    # подмножество при единственном кандидате
    assert r('Роман Юреня', ['Юреня Роман Сергеевич']) == 'Юреня Роман Сергеевич'
    # два супермножества — отказ, а не первое совпадение
    assert r('Иван Иванов', ['Иван Иванов Петрович', 'Иван Иванов Сергеевич']) is None
    # одно слово не связывает
    assert r('Юреня', ['Юреня Роман']) is None
    assert r('', ['Юреня Роман']) is None


def test_metrics_status_when_name_not_resolved():
    """Имя не сопоставлено -> статус, а не нули: ноль читается как «плохо работал»."""
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')], [], [],
                     olap={'aggregated': {'Кто-то Другой': {}}, 'loyalty': {}})
    assert snap['employees'][ID_A]['metrics'] == {'status': 'no_olap_name'}


def test_metrics_computed_when_name_resolved():
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')], [], [],
                     olap=_olap_all('Юреня Роман'))
    m = snap['employees'][ID_A]['metrics']
    assert m['status'] == 'ok'
    assert m['total_checks'] == 812
    assert m['shifts_count'] == 14           # из расчёта премий, не пересчитано
    assert m['loyalty_cards_count'] == 11


# ==================== KPI ====================

def test_kpi_items_have_formula_inputs():
    """У каждого KPI есть факт, цель, минимум, множитель и премия."""
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                     [_kpi_row(ID_A, 'Юреня Роман')],
                     [_hours_row(ID_A, 'Юреня Роман')])
    kpi = snap['employees'][ID_A]['kpi']
    assert kpi['status'] == 'ok' and kpi['koef'] == 0.93
    assert [i['key'] for i in kpi['items']] == ['kpi1', 'kpi2']
    first = kpi['items'][0]
    for field in ('fact', 'target', 'min', 'ratio', 'intermediate_premium', 'premium'):
        assert field in first, field
    # премия одного KPI = промежуточная × коэффициент смен
    assert first['premium'] == round(5100.0 * 0.93, 2)
    assert snap['kpi_meta']['base_per_kpi'] == 5000
    assert snap['kpi_meta']['keys'] == ['kpi1', 'kpi2']


def test_kpi_no_targets_is_not_error():
    """Нет KPI-целей на месяц: статус no_data, остальное посчитано."""
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')], [],
                     [_hours_row(ID_A, 'Юреня Роман')], kpi_data={})
    emp = snap['employees'][ID_A]
    assert emp['kpi']['status'] == 'no_data' and emp['kpi']['items'] == []
    assert emp['money']['kpi']['sum'] == 0
    assert emp['money']['total'] > 0


# ==================== запись и устойчивость ====================

def test_write_and_read_roundtrip():
    path, restore = _tmp_dir()
    try:
        snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                         [_kpi_row(ID_A, 'Юреня Роман')],
                         [_hours_row(ID_A, 'Юреня Роман')])
        ms._write_month('2026-08', snap)
        back = ms.read_month('2026-08')
        assert back['_schema'] == SNAPSHOT_SCHEMA
        assert back['employees'][ID_A]['money']['total'] == 73290.0
        meta = ms.snapshot_meta(back)
        assert meta['status'] == 'ok' and meta['refreshed_at']
        # временный файл после атомарной записи не остаётся
        assert not os.path.exists(ms.month_path('2026-08') + '.tmp')
    finally:
        restore()


def test_source_error_does_not_wipe_snapshot():
    """Сбой источника: прежний файл цел, ошибка в refresh_state.

    Инвариант «всё или ничего»: смешивать свежие часы с позавчерашней
    KPI-премией нельзя — итог не сойдётся ни с одной датой.
    """
    path, restore = _tmp_dir()
    orig_call = ms._call_source
    try:
        good = _assemble([_bonus_row(ID_A, 'Юреня Роман')],
                         [_kpi_row(ID_A, 'Юреня Роман')],
                         [_hours_row(ID_A, 'Юреня Роман')])
        ms._write_month('2026-08', good)
        before = ms.read_month('2026-08')

        ms._call_source = lambda app, view, df, dt: ({}, 'error')
        report = ms.build_month(None, '2026-08', tag='test')
        assert report['written'] is False
        assert 'sboyn' in (report['error'] or '')

        after = ms.read_month('2026-08')
        assert after['_refreshed_at'] == before['_refreshed_at']
        assert after['employees'][ID_A]['money']['total'] == 73290.0
    finally:
        ms._call_source = orig_call
        restore()


def test_build_month_rejects_bad_month():
    report = ms.build_month(None, '2026-13')
    assert report['written'] is False and 'mesyac' in report['error']


def test_refresh_state_merges_fields():
    path, restore = _tmp_dir()
    try:
        ms.write_refresh_state(last_started_at='A', tag='nightly')
        ms.write_refresh_state(last_finished_at='B')
        state = ms.read_refresh_state()
        assert state['last_started_at'] == 'A'      # прежнее поле не затёрто
        assert state['last_finished_at'] == 'B'
        assert state['tag'] == 'nightly'
    finally:
        restore()


def test_read_month_survives_broken_file():
    path, restore = _tmp_dir()
    try:
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'month__2026-08.json'), 'w', encoding='utf-8') as f:
            f.write('[not a dict]')
        assert ms.read_month('2026-08') == {}
        with open(os.path.join(path, 'month__2026-08.json'), 'w', encoding='utf-8') as f:
            f.write('{oops')
        assert ms.read_month('2026-08') == {}
        assert ms.read_month('2026-13') == {}
        assert ms.snapshot_meta({})['status'] == 'missing'
    finally:
        restore()


def test_snapshot_carries_rates_and_norms():
    """Тарифы и нормы едут в снимке — фронт не должен их хардкодить."""
    snap = _assemble([_bonus_row(ID_A, 'Юреня Роман')], [], [])
    assert snap['rates']['taxi_per_shift'] == 700
    assert snap['rates']['handover_per_day'] == 500
    assert snap['rates']['day_plan_base'] == 1000
    assert snap['rates']['late_penalty_step'] == 250
    assert snap['norms'] == {'shift_norm': 15, 'hours_norm': 113}
    assert snap['_source_status']['bonus'] == 'ok'


def test_months_to_build_prev_until_day():
    from datetime import date
    assert ms.months_to_build(date(2026, 8, 3), 7) == ['2026-08', '2026-07']
    assert ms.months_to_build(date(2026, 8, 9), 7) == ['2026-08']
    assert ms.months_to_build(date(2026, 1, 2), 7) == ['2026-01', '2025-12']


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

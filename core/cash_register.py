"""
Кассовый регистр за период — блок «Касса за месяц» на странице графика
(/schedule).

## Что это

Одна таблица со ВСЕМИ сменами периода и их кассой: траты, инкассация, наличные
на конец, комментарий «на что». Раньше блок был read-only и показывал только
сданные кассы; регистр показывает ещё и ПРОБЕЛЫ — дни, за которые кассу не
сдали. Их и надо находить: пробел автоматом снимает премию «передача смены»
(500 ₽), а трата, забытая барменом и всплывшая в чате, должна попасть в таблицу
бухгалтерии.

Модуль — чистая сборка: на входе смены/точки/штрафы (уже прочитанные из
shifts.db), на выходе строки с флагами. Ни БД, ни Flask — поэтому проверяется
тестами целиком (`tests/test_cash_register.py`).

## Проблемы строки (`problems`)

- `no_cash` — «касса не сдана». Дата прошла, дата >= `HANDOVER_CASH_RULE_FROM`,
  смена дневная и первая в дне на своей точке, и НИ ОДНА смена этой точки за этот
  день не имеет `cash_end_kop`. Ровно это условие обнуляет премию за передачу
  смены (`routes/employee.py::_cash_filled_day_keys`), поэтому флаг = «здесь
  премия не начислена».
- `no_note` — трата > 0 без комментария «на что»: бухгалтеру нечего провести.
- `no_shift` — штраф периода, не легший ни на одну смену графика (строка без
  смены). Значит, человек работал, а смену в график не внесли — иначе штраф был
  бы в регистре невидим, и регистр перестал бы сходиться с расчётом ЗП.

Чего в проблемах СОЗНАТЕЛЬНО нет: «не внесена инкассация». Инкассацию забирает
владелец при визите, а не бармен каждую смену — наличные копятся в сейфе, и
`cash_collection_kop = 0` при полном сейфе законно (см. `collectable_kop` в
`core/open_check_telegram.py`, там же считается «сколько можно забрать»). На
проде за июль-август 2026 не было НИ ОДНОЙ смены со сданной кассой и NULL в
инкассации — флаг не находил бы ничего, кроме шума.

## Файлы

- `core/cash_register.py` — этот модуль (сборка строк, ₽ <-> копейки).
- `routes/schedule.py` — `GET /api/schedule/cash-register/<год>/<месяц>` (чтение —
  всем), `PUT /api/schedule/cash-register/shift/<id>` (правка — только
  администратору, без окна 72 ч).
- `static/js/schedule/view.js` — блок «Касса за месяц»: пять видов, фильтр по
  точке, поиск, правка строки, штраф, выгрузка CSV.
- `templates/schedule.html`, `static/schedule/schedule.css` — разметка и стили.

## Changelog

- 2026-08-07 (2) — регистр переехал в блок «Касса за месяц» на странице графика:
  владелец имел в виду существующий блок, а не новый раздел на странице ЗП.
- 2026-08-07 — модуль создан.
"""

from typing import Dict, List, Optional, Tuple


# Деньги в кассе приходят из UI в РУБЛЯХ, хранятся в КОПЕЙКАХ (INTEGER — точно,
# без float-дребезга). Потолок против опечатки «лишний нуль» — 1 млн ₽.
# Единственное место правила: routes/schedule.py и routes/salary.py импортируют
# отсюда, чтобы бармен и бухгалтер не разошлись в допустимых значениях.
CASH_MAX_RUB = 1_000_000

# Проблемы строки регистра. Значения уходят на фронт как есть — подписи в
# PROBLEM_LABELS, чтобы текст был один и в CSV, и в таблице.
PROBLEM_NO_CASH = 'no_cash'
PROBLEM_NO_NOTE = 'no_note'
PROBLEM_NO_SHIFT = 'no_shift'

PROBLEM_LABELS = {
    PROBLEM_NO_CASH: 'касса не сдана',
    PROBLEM_NO_NOTE: 'трата без комментария',
    PROBLEM_NO_SHIFT: 'штраф без смены в графике',
}


def rub_to_kop(value) -> Tuple[bool, Optional[int]]:
    """Рубли (число, строка или null/'') -> копейки INTEGER. (ok, kop_or_None).

    None/'' -> (True, None): поле не заполнено. 0 допустимо («не было»).
    Отрицательное, не-число или сверх потолка -> (False, None).
    Строка с запятой-десятичной («350,50») принимается: бухгалтер копирует суммы
    из русского Excel, где разделитель — запятая.
    """
    if value in (None, ''):
        return True, None
    if isinstance(value, str):
        # Пробелы-разделители тысяч (обычный и неразрывный) и запятая-десятичная:
        # так сумма выглядит при копировании из русского Excel.
        value = value.replace(' ', '').replace(' ', '').strip().replace(',', '.')
        if not value:
            return True, None
    try:
        rub = float(value)
    except (TypeError, ValueError):
        return False, None
    if rub != rub:  # NaN: json.loads принимает литерал NaN, сравнения его пропускают
        return False, None
    if rub < 0 or rub > CASH_MAX_RUB:
        return False, None
    return True, int(round(rub * 100))


def fmt_kop(kop) -> str:
    """Копейки -> строка рублей для журнала: '15 340', '350.50', '—' для None."""
    if kop is None:
        return '—'
    rub = kop / 100.0
    s = f"{rub:,.0f}" if kop % 100 == 0 else f"{rub:,.2f}"
    return s.replace(',', ' ')


def is_evening(role_name, start_time) -> bool:
    """Вечерняя ли смена: роль «второй …» или старт >= 18:00.

    Зеркало `S.isEvening` из `static/js/schedule/screens.js` (там же порог 18:00
    и подстрока «втор»): день/вечер должны сегментироваться одинаково на всех
    экранах, иначе смена 16:00 то дневная, то вечерняя. Кассу сдаёт ДНЕВНАЯ
    смена — от этого зависит, у кого регистр ищет пробел.
    """
    if role_name and 'втор' in str(role_name).lower():
        return True
    return bool(start_time and str(start_time) >= '18:00')


def index_penalties(penalties) -> Tuple[Dict, Dict]:
    """Ручные штрафы кассы -> ({id: {дата: note}}, {имя_lower: {дата: note}}).

    Два индекса, потому что имя — снимок: после переименования сотрудника в iiko
    («Алексей Стажер» -> «Алексей Марченко») штраф, записанный под старым именем,
    по имени уже не найдётся. Приоритет — `employee_id` (v10); по имени
    индексируются ТОЛЬКО строки без id, иначе штраф, привязанный к одному
    человеку, применился бы и к его однофамильцу с другим id (потребители берут
    объединение индексов).

    Используют `routes/employee.py::_manual_handover_penalties` (расчёт премии) и
    регистр кассы — правило сопоставления обязано быть одно.
    """
    by_id, by_name = {}, {}
    for p in penalties or []:
        emp_id = (p.get('employee_id') or '').strip()
        if emp_id:
            by_id.setdefault(emp_id, {})[p['date']] = p.get('note')
        else:
            by_name.setdefault(
                (p.get('employee_name') or '').strip().lower(),
                {})[p['date']] = p.get('note')
    return by_id, by_name


def _penalty_for(by_id, by_name, employee_id, employee_name, date_str):
    """(penalized, note, ключ_совпадения) для смены.

    Сначала id, потом имя — как в расчёте ЗП. Третий элемент — ('id'|'name', key,
    date) найденной строки штрафа или None: по нему build_register понимает, какие
    штрафы НЕ легли ни на одну смену.
    """
    key = (employee_id or '').strip()
    if key and key in by_id and date_str in by_id[key]:
        return True, by_id[key][date_str], ('id', key, date_str)
    name = (employee_name or '').strip().lower()
    if name in by_name and date_str in by_name[name]:
        return True, by_name[name][date_str], ('name', name, date_str)
    return False, None, None


def _orphan_penalty_rows(penalties, by_id, by_name, matched) -> List[Dict]:
    """Строки для штрафов, не легших ни на одну смену периода.

    Так бывает: штраф ставится со страницы ЗП, где дни берутся из кассовых смен
    iiko, а регистр строится по графику — если смену в график не внесли, штраф
    оказался бы невидим (на проде 26.07.2026: 10 штрафов в БД, 9 строк в
    регистре). Молча терять штраф нельзя: регистр перестал бы сходиться с
    расчётом. Такая строка — сама по себе сигнал «в графике нет смены, а человек
    работал», поэтому помечается проблемой `no_shift`; править кассу в ней нечего
    (`shift_id = None`), только снять штраф на карточке сотрудника.
    """
    out = []
    for p in penalties or []:
        date_str = p.get('date') or ''
        emp_id = (p.get('employee_id') or '').strip()
        key = ('id', emp_id, date_str) if emp_id \
            else ('name', (p.get('employee_name') or '').strip().lower(), date_str)
        if key in matched:
            continue
        matched.add(key)                      # дубли штрафов не размножаем
        out.append({
            'shift_id': None, 'date': date_str,
            'location_id': None, 'location_short': '', 'location_name': '',
            'employee_id': p.get('employee_id'),
            'employee_name': p.get('employee_name') or '',
            'role_name': '', 'evening': False,
            'expense_kop': None, 'expense_note': None,
            'collection_kop': None, 'end_kop': None,
            'has_cash': False, 'day_closed': False, 'cash_expected': False,
            'problems': [PROBLEM_NO_SHIFT],
            'penalized': True, 'penalty_note': p.get('note'),
        })
    return out


def build_register(shifts, penalties, today, rule_from) -> Dict:
    """Собрать регистр кассы: строки по сменам + флаги проблем + итоги.

    Аргументы:
      shifts    — смены периода (как отдаёт `ShiftsManager.get_shifts_for_period`);
      penalties — ручные штрафы кассы периода (`get_handover_penalties`);
      today     — ISO-дата «сегодня»: смена сегодня и будущая не пробел (кассу
                  сдают в конце смены), параметр — чтобы тесты были
                  детерминированными;
      rule_from — ISO-дата, с которой действует правило «нет кассы — нет премии»
                  (`routes/employee.py::HANDOVER_CASH_RULE_FROM`). Дни до неё
                  пробелами не считаются: кассовой дисциплины тогда не было.

    Возвращает {'rows': [...], 'totals': {...}, 'locations': [...]}.
    Строки — по возрастанию даты, внутри дня по точке и времени начала.
    """
    rows = []
    by_id, by_name = index_penalties(penalties)
    # Ключи штрафов, легших хотя бы на одну смену. Остальные добавим строками
    # без смены: регистр обязан показывать ВСЕ штрафы периода.
    matched = set()

    # Точка «закрыта по кассе» за день, если ХОТЬ ОДНА её смена этого дня имеет
    # cash_end — то же условие, что снимает премию (_cash_filled_day_keys).
    # Обычно кассу сдаёт дневная смена, но если её внёс вечерний бармен — день
    # всё равно закрыт, и пробела нет.
    closed = {(s.get('location_id'), s.get('date'))
              for s in shifts if s.get('cash_end_kop') is not None}

    # Ответственная за кассу смена дня: первая дневная (по времени старта, затем
    # по id — порядок создания). Пробел показываем только на ней, иначе день с
    # двумя дневными барменами дал бы два одинаковых предупреждения.
    responsible = {}
    for s in shifts:
        if is_evening(s.get('role_name'), s.get('start_time')):
            continue
        key = (s.get('location_id'), s.get('date'))
        cur = responsible.get(key)
        rank = (s.get('start_time') or '', s.get('id') or 0)
        if cur is None or rank < cur[0]:
            responsible[key] = (rank, s.get('id'))

    for s in shifts:
        date_str = s.get('date') or ''
        loc_key = (s.get('location_id'), date_str)
        evening = is_evening(s.get('role_name'), s.get('start_time'))
        expense = s.get('cash_expense_kop')
        note = (s.get('cash_expense_note') or '').strip()
        has_cash = any(s.get(f) is not None for f in
                       ('cash_expense_kop', 'cash_collection_kop', 'cash_end_kop'))
        is_responsible = responsible.get(loc_key, (None, None))[1] == s.get('id')

        problems = []
        # Пробел кассы: дата прошла, правило уже действует, точка за день не
        # закрыта — и это ответственная смена дня.
        cash_expected = (not evening and is_responsible
                         and date_str < today and date_str >= rule_from)
        if cash_expected and loc_key not in closed:
            problems.append(PROBLEM_NO_CASH)
        if (expense or 0) > 0 and not note:
            problems.append(PROBLEM_NO_NOTE)

        penalized, penalty_note, pkey = _penalty_for(
            by_id, by_name, s.get('employee_id'), s.get('employee_name'), date_str)
        if pkey:
            matched.add(pkey)

        rows.append({
            'shift_id': s.get('id'),
            'date': date_str,
            'location_id': s.get('location_id'),
            'location_short': s.get('location_short') or s.get('location_name') or '',
            'location_name': s.get('location_name') or '',
            'employee_id': s.get('employee_id'),
            'employee_name': s.get('employee_name') or '',
            'role_name': s.get('role_name') or '',
            'evening': evening,
            'expense_kop': expense,
            'expense_note': note or None,
            'collection_kop': s.get('cash_collection_kop'),
            'end_kop': s.get('cash_end_kop'),
            'has_cash': has_cash,
            # день точки закрыт по кассе — премия за передачу смены не режется
            'day_closed': loc_key in closed,
            'cash_expected': cash_expected,
            'problems': problems,
            'penalized': penalized,
            'penalty_note': penalty_note,
        })

    rows.extend(_orphan_penalty_rows(penalties, by_id, by_name, matched))
    rows.sort(key=lambda r: (r['date'], r['location_short'], r['role_name'],
                             r['shift_id'] or 0))

    totals = {
        'shifts': sum(1 for r in rows if r['shift_id'] is not None),
        'with_cash': sum(1 for r in rows if r['has_cash']),
        'expense_kop': sum(r['expense_kop'] or 0 for r in rows),
        'collection_kop': sum(r['collection_kop'] or 0 for r in rows),
        'problems': sum(1 for r in rows if r['problems']),
        'penalties': sum(1 for r in rows if r['penalized']),
    }

    # Точки — в порядке id (как в графике), только те, что есть в периоде.
    # Строки-сироты точки не имеют (location_id = None) — в фильтр не попадают.
    seen, locations = set(), []
    for r in sorted(rows, key=lambda r: (r['location_id'] or 0)):
        if r['location_id'] is None or r['location_id'] in seen:
            continue
        seen.add(r['location_id'])
        locations.append({'id': r['location_id'], 'short': r['location_short'],
                          'name': r['location_name']})

    return {'rows': rows, 'totals': totals, 'locations': locations}

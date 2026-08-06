"""
Раскладка таблицы ЗП — ЕДИНЫЙ источник строк, формул и оформления.

## Что это

Модуль строит абстрактный лист (`Sheet`) из payload страницы /salary: строки,
ячейки (числа / формулы Excel), заливки, начертания, форматы чисел. Сам ничего
не рендерит — рендереры разные:

- `core/salary_export.py` -> .xlsx (openpyxl),
- `core/salary_gsheet.py` -> Google Таблица (Sheets API).

Так сделано, чтобы два экспорта не разъехались: формула, тариф или цвет
меняются здесь, и оба формата меняются вместе. Если в раскладке появится
строка — её увидят оба рендерера без правок в них.

## Формат листа (таблица бухгалтерии «Новая таблица (3).xlsx»)

    A Показатель | B Хозяин цифры | C Дедлайн готовности | D Проверить |
    E Тариф | F.. по столбцу на сотрудника | последний столбец ИТОГО

Строка 1 пустая, шапка в строке 2, данные с 3-й. При 2 ролях и 3 KPI — строки
3..23 (в эталоне было 3..22: добавлена своя база премии за передачу смены,
см. ниже).

Порядок строк: часы по ролям, «Количество смен», «Оплаченных дней передачи
смены», оплата по ролям, «Отпуск», премия за передачу, премия за дневной план,
KPI (N строк), «Доп доход», блок такси (4 строки), вычеты (3), ИТОГО БАРМЕН.
Счётчики стоят ДО блока начислений намеренно: ИТОГО суммирует непрерывный
диапазон «оплата..доп доход», и счётчик дней внутри него уехал бы в деньги.

## Формулы

Формулой пишется всё, что ВЫВОДИТСЯ из других строк листа; первичные величины
(часы, смены, дневной план, KPI, вычеты) — числа, они посчитаны сервером и в
листе не выводимы.

    Ставка по часам      =F3*$E$7          часы x тариф
    Премия за передачу   =F6*$E$10         оплаченные дни x тариф
    Такси расчет.        =F5*$E$16         дневные смены графика x тариф
    Такси разница        =F16+F17-F18      расчёт + мосты - оф.
    ИТОГО БАРМЕН         =SUM(F7:F15)-F20-F21-F22+F19
    Колонка ИТОГО        =SUM(F7:N7)

Номера строк здесь — для 2 ролей и 3 KPI; в коде они вычисляются, а не зашиты.

Две сверки, чтобы формула не соврала (формула ставится ТОЛЬКО если
воспроизводит сумму страницы, иначе пишется число — экспорт обязан совпадать с
расчётом):

- *оплата*: страница считает из неокруглённых часов (`minutes/60 x ставка`), а
  в ячейку часов идёт округление до сотых — на длинном месяце «часы x тариф»
  расходится со страницей на рубль;
- *премия за передачу смены*: формула ставится, только если
  «оплаченные дни x тариф» в точности равно премии страницы.

## Почему у премии за передачу смены СВОЯ строка базы

Премия считается по ДНЯМ смен минус дни без сданной кассы и дни с ручным
штрафом (`routes/employee.py:_handover_premium`), а «Количество смен» — это
дневные смены графика, база такси. Это разные числа. Пока премия была формулой
от «Количества смен», разницу приходилось гасить константой, и в файле
появлялся вычет «-2000» там, где штрафов на 2 500, плюс фантомные «-500» у
тех, у кого штрафов нет вовсе (жалоба владельца 2026-08-06). Теперь база своя,
и вычетов-заглушек в листе не бывает.

## Changelog

- 2026-08-06 — добавлена строка «Оплаченных дней передачи смены»; премия
  считается формулой от неё, а не от «Количества смен» с константой.
- 2026-08-01 — выделен из `core/salary_export.py` под второй рендерер
  (Google Таблицы); поведение .xlsx не менялось.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

# Ключ алфавитного порядка колонок. Живёт в salary_payload (там же сортируется
# мёрж для страницы), обратной зависимости нет — цикла импорта не возникает.
from core.salary_payload import name_sort_key

# --- Геометрия листа ------------------------------------------------------
HEADER_ROW = 2
FIRST_DATA_ROW = 3
FIRST_EMP_COL = 6                      # F — первый сотрудник (A..E — метаданные)

# --- Тарифы и правила -----------------------------------------------------
# Тариф такси за полноценную ДНЕВНУЮ смену — из эталонной таблицы бухгалтерии
# (колонка «Тариф» строки «Такси за смены расчет.»). Единственное место
# значения: страница ЗП получает его через /api/schedule/hours-by-role
# (расчёт = day_shifts x тариф), здесь пишется в ячейку тарифа, а строка
# считается формулой «смены x тариф» — правка тарифа в файле пересчитает всё.
TAXI_RATE_PER_SHIFT = 700

# «Такси за смены оф.» — официально такси всегда оплачивается за фиксированные
# 15 смен (15 x 700 = 10 500, правило владельца). В ЗП идёт разница:
# расчёт + мосты - оф. (доплата или удержание); «мосты» — ручная надбавка
# бухгалтера. Если дневных смен за период нет, оф. не начисляется (иначе у
# сотрудника «только вечера» появилось бы удержание 10 500). Число
# фиксированное, поэтому пишется значением, а не формулой от тарифа — как в
# эталоне (там 10 500 проставлено руками).
TAXI_OFFICIAL_SHIFTS = 15

# Служебные тарифы страницы ЗП (дублируют константы бэкенда только для показа
# в колонке «Тариф»; сами суммы приходят уже посчитанными):
# 500 — премия за передачу смены (routes/employee.py), 1000 — база премии
# за дневной план (routes/employee.py).
HANDOVER_RATE = 500
DAY_PLAN_RATE = 1000

# --- Оформление (снято с ячеек эталонной таблицы бухгалтерии) -------------
FONT_NAME = 'PT Serif'
FONT_SIZE = 8

FILL_HEADER = 'FFF2CC'      # шапка и ИТОГО БАРМЕН
FILL_YELLOW = 'FFFF00'      # смены и блок такси
FILL_GREEN = '00FF00'       # «2-й в смене», хозяин цифры РЮ
FILL_KPI = 'D9EAD3'         # блок KPI целиком
FILL_RED_LABEL = 'CC0000'   # подписи вычетов
FILL_RED_DATA = 'F4CCCC'    # данные вычетов
FILL_TOTAL = 'FFF2CC'

FMT_MONEY = '#,##0'
FMT_MONEY_2 = '#,##0.00'
FMT_SHIFTS = '0'
FMT_HOURS = 'General'       # часы бывают дробными (97.5) — General не рисует хвост у целых

# Ширины колонок: A/сотрудники/ИТОГО — из эталона, B..E — подобраны под
# заголовки (в эталоне оставлены по умолчанию)
WIDTH_LABEL = 26.5
WIDTH_META = (10, 11, 9, 8)
WIDTH_EMP = 9.5
WIDTH_TOTAL = 11.13

# Метаданные процессов (кто владеет цифрой, дедлайн, кто проверяет) — из
# эталонной таблицы бухгалтерии. Чисто справочные колонки B/C/D.
_META = {
    'pay': ('УПР', '05 число', 'УПР'),
    'handover': ('РЮ', '05 число', 'УПР'),
    'day_plan': ('УПР', '05 число', 'УПР'),
    'kpi': ('УПР', '05 число', 'УПР'),
    'extra_income': ('РЮ', '10 число', 'ИШ'),
    'taxi': ('НК', '5 число', 'УПР'),
    'ded_inventory': ('РЮ', '10 число', 'ИШ'),
    'ded_discipline': ('РЮ', '05 число', 'ИШ'),
    'ded_other': ('РЮ', '10 число', 'ИШ'),
}

_MONTH_NAMES = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']

HEADERS = ['Показатель', 'Хозяин цифры', 'Дедлайн готовности', 'Проверить', 'Тариф']


class Formula(str):
    """Маркер намеренной формулы.

    Обычная строка с ведущим «=» (например имя сотрудника «=Иванов» — опечатка
    или подделка) должна попасть в лист ТЕКСТОМ, иначе уйдёт живой формулой.
    Формулы, которые ставит раскладка, помечаются этим типом; рендереры пишут
    формулой только их (см. formula injection в обоих рендерерах).
    """


@dataclass
class Row:
    """Строка листа: подпись, метаданные, тариф, ячейки по сотрудникам."""
    key: str
    label: str
    number: int                                  # номер строки на листе (1-based)
    cells: List[Any] = field(default_factory=list)   # число / Formula / None
    total: Any = None                            # ячейка колонки ИТОГО
    meta: Tuple[str, str, str] = ('', '', '')
    tariff: Any = None
    fmt: str = FMT_MONEY
    label_fill: Optional[str] = None
    data_fill: Optional[str] = None
    meta_fill: Optional[str] = None
    owner_fill: Optional[str] = None
    label_bold: bool = False
    label_italic: bool = False


@dataclass
class Sheet:
    """Готовая раскладка: всё, что нужно рендереру, и ничего лишнего."""
    month: str
    title: str                                   # имя листа, «июль2026»
    employees: List[str]
    rows: List[Row]
    n_emp: int
    first_emp_col: int = FIRST_EMP_COL
    total_col: int = FIRST_EMP_COL

    @property
    def emp_cols(self) -> List[int]:
        return [self.first_emp_col + i for i in range(self.n_emp)]

    @property
    def last_row(self) -> int:
        return self.rows[-1].number if self.rows else HEADER_ROW


def col_letter(idx: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA (без зависимости от openpyxl)."""
    name = ''
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def month_title(month: str) -> str:
    """'2026-07' -> 'июль 2026'."""
    try:
        y, m = month.split('-')
        return f"{_MONTH_NAMES[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return month


def sheet_title(month: str) -> str:
    """'2026-07' -> 'июль2026' — имя листа в стиле таблицы бухгалтерии."""
    return month_title(month).replace(' ', '') or 'ЗП'


def auto_sheet_title(month: str) -> str:
    """'2026-07' -> 'Июль_2026_Автоматическая'.

    Вкладка ночной выгрузки в таблицу бухгалтерии. Отдельная от ручной
    «июль2026» намеренно: ночная задача переписывает свою вкладку целиком, и
    будь она общей — стирала бы «мосты», отпуск, доп доход и вычеты, которые
    бухгалтер вносит руками (решение владельца 2026-08-01).
    """
    try:
        y, m = month.split('-')
        return f"{_MONTH_NAMES[int(m) - 1].capitalize()}_{y}_Автоматическая"
    except (ValueError, IndexError):
        return f"{month}_Автоматическая"


def build_sheet(payload: dict) -> Sheet:
    """Собрать раскладку листа из payload страницы /salary.

    Контракт payload — докстрока `core/salary_export.py`.
    """
    month = payload.get('month') or ''
    roles = payload.get('roles') or []
    kpi_names = payload.get('kpi_names') or []
    base_per_kpi = payload.get('base_per_kpi') or 0
    # Порядок колонок задаёт СЕРВЕР, а не порядок в payload. Клиенту тут верить
    # нельзя: страница, открытая до деплоя алфавитной сортировки, прислала
    # старый порядок «по сумме ЗП», и кнопка «Обновить Google» откатила вкладку
    # июля (прод 2026-08-07, журнал salary_gsheet_export 21:54 UTC). Сортировка
    # здесь одна на все три пути записи — .xlsx, кнопка, ночная выгрузка.
    # sorted() стабильна: полные тёзки сохраняют порядок мёржа.
    employees = sorted(payload.get('employees') or [],
                       key=lambda e: name_sort_key(e.get('name')))

    n_emp = len(employees)
    emp_cols = [FIRST_EMP_COL + i for i in range(n_emp)]
    emp_letters = [col_letter(c) for c in emp_cols]
    total_col = FIRST_EMP_COL + n_emp
    last_emp_letter = emp_letters[-1] if emp_letters else None

    rows: List[Row] = []
    counter = {'row': FIRST_DATA_ROW}

    def add(key, label, values=None, sum_total=True, **kw):
        """Добавить строку. values — список ИЛИ функция (номер строки) -> список
        (нужна формулам, которые ссылаются на собственную строку, например
        «часы x $E$<своя строка>»)."""
        r = counter['row']
        counter['row'] += 1
        cells = values(r) if callable(values) else (values or [None] * n_emp)
        fmt = kw.get('fmt', FMT_MONEY)
        # Нули не показываем (как в эталоне), кроме KPI — там печатается 0.00
        cells = [None if (c == 0 and fmt != FMT_MONEY_2 and not isinstance(c, Formula))
                 else c for c in cells]
        total = None
        if n_emp and sum_total:
            total = Formula(f"=SUM({emp_letters[0]}{r}:{last_emp_letter}{r})")
        row = Row(key=key, label=label, number=r, cells=cells, total=total, **kw)
        rows.append(row)
        return r

    def emp_vals(getter):
        return [getter(e) for e in employees]

    adj = lambda e, cat: (e.get('adjustments') or {}).get(cat) or 0

    # --- Часы по ролям (числа: первичные данные, из листа не выводятся) ---
    hours_labels = ['Часы', 'Часы 2-й в смене']
    hours_rows = []
    for idx, role in enumerate(roles):
        label = hours_labels[idx] if idx < len(hours_labels) else f"Часы — {role['name']}"
        hours_rows.append(add(
            'hours', label,
            emp_vals(lambda e, rn=role['name']: (e.get('hours_by_role') or {}).get(rn) or 0),
            label_italic=True, fmt=FMT_HOURS))

    shifts_row = add('shifts', 'Количество смен',
                     emp_vals(lambda e: e.get('shifts_count') or 0),
                     sum_total=False, label_fill=FILL_YELLOW, label_italic=True,
                     fmt=FMT_SHIFTS)

    # База премии за передачу смены — СВОЯ строка, а не «Количество смен»:
    # премия считается по ДНЯМ кассовых смен iiko, а «Количество смен» — это
    # дневные смены графика (база такси), и числа не совпадают. Пока премия была
    # формулой от чужой базы, разницу приходилось гасить константой: в файле
    # появлялся вычет «-2000» там, где штрафов на 2500, и фантомные «-500» у
    # тех, у кого штрафов нет вовсе (жалоба владельца 2026-08-06).
    # Стоит ВЫШЕ блока начислений (как «Часы» и «Количество смен»), иначе
    # счётчик дней попал бы в диапазон SUM строки ИТОГО БАРМЕН.
    paid_days_row = add(
        'handover_paid', 'Оплаченных дней передачи смены',
        emp_vals(lambda e: e.get('handover_paid_days') or 0),
        sum_total=False, label_italic=True, fmt=FMT_SHIFTS)

    # --- Оплата по ролям: формула «часы x тариф» ---
    def pay_cell(e, role_name, rate, r, letter, h_row):
        hours = (e.get('hours_by_role') or {}).get(role_name) or 0
        pay = (e.get('pay_by_role') or {}).get(role_name)
        if pay is None or round(hours * (rate or 0), 2) == round(pay, 2):
            return Formula(f"={letter}{h_row}*$E${r}")
        return pay      # округление разошлось — пишем сумму страницы

    pay_labels = ['Ставка по часам', 'Ставка 2-й в смене']
    pay_rows = []
    for idx, role in enumerate(roles):
        label = pay_labels[idx] if idx < len(pay_labels) else f"Оплата — {role['name']}"
        pay_rows.append(add(
            'pay', label,
            lambda r, hr=hours_rows[idx], rn=role['name'], rt=role.get('rate'): [
                pay_cell(e, rn, rt, r, emp_letters[i], hr)
                for i, e in enumerate(employees)],
            meta=_META['pay'] if idx == 0 else ('', '', ''),
            tariff=role.get('rate'),
            label_fill=FILL_GREEN if idx == 1 else None))

    add('vacation', 'Отпуск', emp_vals(lambda e: adj(e, 'vacation')))

    # --- Премия за передачу смены ---
    def handover_cell(e, r, letter):
        """Формула «оплаченные дни x тариф»; число — если она не сходится.

        Не оплачиваются дни без сданной кассы и дни с ручным штрафом (правило
        владельца), поэтому база строки — уже оплаченные дни, а не все смены.
        """
        paid = e.get('handover_paid_days')
        bonus = e.get('handover_bonus') or 0
        if paid and round(paid * HANDOVER_RATE, 2) == round(bonus, 2):
            return Formula(f"={letter}{paid_days_row}*$E${r}")
        return bonus

    add('handover', 'Премия за приемку-передачу смены',
        lambda r: [handover_cell(e, r, emp_letters[i]) for i, e in enumerate(employees)],
        meta=_META['handover'], tariff=HANDOVER_RATE,
        label_bold=True, owner_fill=FILL_GREEN)

    add('day_plan', 'Премия за дневной план',
        emp_vals(lambda e: e.get('day_plan_bonus') or 0),
        meta=_META['day_plan'], tariff=DAY_PLAN_RATE)

    for k_idx, k_name in enumerate(kpi_names):
        add('kpi', f"KPI {k_idx + 1} — {k_name}",
            emp_vals(lambda e, i=k_idx: (e.get('kpi_premiums') or [])[i]
                     if i < len(e.get('kpi_premiums') or []) else 0),
            meta=_META['kpi'], tariff=base_per_kpi,
            label_fill=FILL_KPI, label_bold=True,
            meta_fill=FILL_KPI, data_fill=FILL_KPI, fmt=FMT_MONEY_2)

    extra_income_row = add('extra_income', 'Доп доход',
                           emp_vals(lambda e: adj(e, 'extra_income')),
                           meta=_META['extra_income'], label_bold=True)

    # --- Такси ---
    # расчёт — формула «смены x тариф»; оф. — фикс 15 смен (число, как в
    # эталоне); мосты — единственная ручная строка бухгалтера; разница —
    # формула, поэтому вписанные мосты сразу меняют разницу и ИТОГО БАРМЕН.
    taxi_calc_row = add(
        'taxi_calc', 'Такси за смены расчет.',
        lambda r: [Formula(f"={L}{shifts_row}*$E${r}") for L in emp_letters],
        meta=_META['taxi'], tariff=TAXI_RATE_PER_SHIFT,
        label_fill=FILL_YELLOW, label_bold=True)
    bridges_row = add('bridges', 'мосты', None,
                      label_fill=FILL_YELLOW, label_bold=True)
    official_row = add(
        'taxi_official', 'Такси за смены оф.',
        emp_vals(lambda e: TAXI_OFFICIAL_SHIFTS * TAXI_RATE_PER_SHIFT
                 if (e.get('shifts_count') or 0) > 0 else 0),
        meta=_META['taxi'], label_fill=FILL_YELLOW, label_bold=True)
    taxi_diff_row = add(
        'taxi_diff', 'Такси разница: доплата/удержание',
        [Formula(f"={L}{taxi_calc_row}+{L}{bridges_row}-{L}{official_row}")
         for L in emp_letters],
        meta=_META['taxi'], label_fill=FILL_YELLOW, label_bold=True)

    # --- Вычеты ---
    ded_rows = [
        add('ded_inventory', 'Вычет инвент',
            emp_vals(lambda e: adj(e, 'deduction_inventory')),
            meta=_META['ded_inventory'], label_fill=FILL_RED_LABEL, label_bold=True,
            meta_fill=FILL_RED_DATA, data_fill=FILL_RED_DATA),
        # Дисциплина = авто-штраф за опоздания (страница ЗП) + ручной вычет
        add('ded_discipline', 'Вычет дисциплина',
            emp_vals(lambda e: (e.get('late_penalty') or 0)
                     + adj(e, 'deduction_discipline')),
            meta=_META['ded_discipline'], label_fill=FILL_RED_LABEL, label_bold=True,
            meta_fill=FILL_RED_DATA, data_fill=FILL_RED_DATA),
        add('ded_other', 'Доп вычет', emp_vals(lambda e: adj(e, 'deduction_other')),
            meta=_META['ded_other'], label_fill=FILL_RED_LABEL, label_bold=True,
            meta_fill=FILL_RED_DATA, data_fill=FILL_RED_DATA),
    ]

    # --- ИТОГО БАРМЕН ---
    # Непрерывный блок «оплата..доп доход» + такси-разница - вычеты (часы,
    # смены, такси-расчёт и оф. в итог не входят). Форма формулы — как в
    # таблице бухгалтерии: =SUM(F6:F14)-F19-F20-F21+F18
    def total_cells(r):
        if not pay_rows:
            return [None] * n_emp
        return [Formula(f"=SUM({L}{pay_rows[0]}:{L}{extra_income_row})"
                        + ''.join(f"-{L}{d}" for d in ded_rows)
                        + f"+{L}{taxi_diff_row}") for L in emp_letters]

    add('total', 'ИТОГО БАРМЕН', total_cells,
        label_fill=FILL_TOTAL, label_bold=True, meta_fill=FILL_TOTAL,
        data_fill=FILL_TOTAL)

    return Sheet(month=month, title=sheet_title(month),
                 employees=[e.get('name', '') for e in employees],
                 rows=rows, n_emp=n_emp,
                 first_emp_col=FIRST_EMP_COL, total_col=total_col)

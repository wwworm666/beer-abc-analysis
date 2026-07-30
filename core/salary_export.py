"""
Экспорт расчёта ЗП (/salary) в Excel — формат эталонной таблицы владельца.

Строит книгу openpyxl из payload, который присылает фронтенд страницы /salary
(уже посчитанные и смёрженные данные — экспорт бит-в-бит совпадает со
страницей). Структура листа повторяет таблицу владельца:

    A Показатель | B Хозяин цифры | C Дедлайн готовности | D Проверить |
    E Тариф | F.. по столбцу на сотрудника | последний столбец ИТОГО

Строки: часы по ролям, количество смен, оплата по ролям, отпуск, премия за
передачу смены, премия за дневной план, KPI 1..N, доп доход, такси
(расчёт/мосты/официально/разница), вычеты (инвент/дисциплина/доп),
ИТОГО БАРМЕН.

Такси и «ИТОГО БАРМЕН» пишутся ФОРМУЛАМИ Excel — менеджер дозаполняет
«мосты» и «такси оф.» прямо в файле, и итоги пересчитываются сами.

Payload (все суммы в рублях, уже рассчитаны страницей):
    {
      "month": "YYYY-MM",
      "kpi_names": ["Доля кухни (%)", ...],      # показатели месяца, по порядку
      "base_per_kpi": 5000,                       # тариф KPI = фонд / кол-во KPI
      "roles": [{"name": "бармен", "rate": 300}, ...],  # порядок = порядок строк
      "employees": [{
          "name": str,
          "hours_by_role": {role_name: часы},
          "pay_by_role": {role_name: оплата},
          "shifts_count": int,                    # смены из графика за период
          "handover_bonus": float,                # премия за передачу смены
          "day_plan_bonus": float,                # премия за дневной план
          "kpi_premiums": [float, ...],           # по каждому KPI, уже с koef
          "late_penalty": float,                  # авто-штраф за опоздания
          "adjustments": {категория: сумма}       # SALARY_ADJUSTMENT_CATEGORIES
      }, ...]
    }
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Тариф такси за смену — из эталонной таблицы владельца (колонка «Тариф»
# строки «Такси за смены расчет.»). Пишется в ячейку тарифа, а строка
# считается формулой «смены x тариф» — правка тарифа в файле пересчитает всё.
TAXI_RATE_PER_SHIFT = 700

# Служебные тарифы страницы ЗП (дублируют константы бэкенда только для показа
# в колонке «Тариф»; сами суммы приходят уже посчитанными):
# 500 — премия за передачу смены (routes/employee.py), 1000 — база премии
# за дневной план (routes/employee.py).
HANDOVER_RATE = 500
DAY_PLAN_RATE = 1000

# Метаданные процессов (кто владеет цифрой, дедлайн, кто проверяет) — из
# эталонной таблицы владельца. Чисто справочные колонки B/C/D.
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

# Заливки — приближение к цветам эталонной таблицы
_FILL_HEADER = PatternFill('solid', fgColor='FCE4B8')
_FILL_YELLOW = PatternFill('solid', fgColor='FFFF00')
_FILL_GREEN = PatternFill('solid', fgColor='92D050')
_FILL_KPI = PatternFill('solid', fgColor='E2EFDA')
_FILL_RED_LABEL = PatternFill('solid', fgColor='C00000')
_FILL_RED_DATA = PatternFill('solid', fgColor='FADBD8')
_FILL_TOTAL = PatternFill('solid', fgColor='FDE9D9')

_THIN = Side(style='thin', color='BFBFBF')
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FMT_MONEY = '#,##0'
_FMT_MONEY_2 = '#,##0.00'
_FMT_HOURS = 'General'  # часы бывают дробными (97.5) — General не рисует хвост у целых


def month_title(month: str) -> str:
    """'2026-07' -> 'июль 2026' (для заголовка листа)."""
    try:
        y, m = month.split('-')
        return f"{_MONTH_NAMES[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return month


def build_salary_workbook(payload: dict) -> Workbook:
    """Собрать книгу Excel из payload страницы /salary (контракт в докстроке модуля)."""
    month = payload.get('month') or ''
    roles = payload.get('roles') or []
    kpi_names = payload.get('kpi_names') or []
    base_per_kpi = payload.get('base_per_kpi') or 0
    employees = payload.get('employees') or []

    wb = Workbook()
    ws = wb.active
    ws.title = f"ЗП {month}" if month else 'ЗП'

    n_emp = len(employees)
    first_emp_col = 6                      # F — первый сотрудник (A..E — метаданные)
    total_col = first_emp_col + n_emp      # последний столбец — ИТОГО
    emp_cols = [first_emp_col + i for i in range(n_emp)]

    def put(row, col, value, fill=None, font=None, fmt=None, align=None,
            is_formula=False):
        cell = ws.cell(row=row, column=col, value=value)
        # openpyxl типизирует любую строку с ведущим «=» как формулу: имя
        # сотрудника вида «=Иванов» (опечатка или крафт) ушло бы в файл живой
        # формулой. Только явно помеченные ячейки остаются формулами.
        if isinstance(value, str) and value.startswith('=') and not is_formula:
            cell.data_type = 's'
        cell.border = _BORDER
        if fill:
            cell.fill = fill
        if font:
            cell.font = font
        if fmt:
            cell.number_format = fmt
        if align:
            cell.alignment = align
        return cell

    # --- Строка 1: заголовок (месяц) ---
    put(1, 1, f"Расчёт ЗП — {month_title(month)}", font=Font(bold=True, size=12))

    # --- Строка 2: шапка ---
    header_font = Font(bold=True, italic=True)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    headers = ['Показатель', 'Хозяин цифры', 'Дедлайн готовности', 'Проверить', 'Тариф']
    for i, h in enumerate(headers, start=1):
        put(2, i, h, fill=_FILL_HEADER, font=header_font, align=center)
    for i, emp in enumerate(employees):
        put(2, first_emp_col + i, emp.get('name', ''), fill=_FILL_HEADER,
            font=header_font, align=center)
    put(2, total_col, 'ИТОГО', fill=_FILL_HEADER, font=header_font, align=center)

    # --- Данные: строки добавляются последовательно, номера запоминаем ---
    row = 3

    def data_row(label, values, meta=None, tariff=None, label_fill=None,
                 label_font=None, data_fill=None, fmt=_FMT_MONEY,
                 formula=None, sum_total=True):
        """Одна строка таблицы. values — список по сотрудникам (None = пусто);
        formula(col_letter, row) — формула вместо значений; ИТОГО = SUM по строке."""
        nonlocal row
        r = row
        put(r, 1, label, fill=label_fill, font=label_font)
        owner, deadline, checker = meta or ('', '', '')
        put(r, 2, owner or None, fill=_FILL_GREEN if owner == 'РЮ' else None, align=center)
        put(r, 3, deadline or None, font=Font(italic=True), align=center)
        put(r, 4, checker or None, align=center)
        put(r, 5, tariff, font=Font(italic=True), fmt=_FMT_MONEY, align=center)
        for i, col in enumerate(emp_cols):
            letter = get_column_letter(col)
            if formula is not None:
                put(r, col, formula(letter, r), fill=data_fill, fmt=fmt,
                    is_formula=True)
            else:
                v = values[i] if values else None
                put(r, col, v if v not in (None, 0) or fmt == _FMT_MONEY_2 else None,
                    fill=data_fill, fmt=fmt)
        if n_emp and sum_total:
            first_l = get_column_letter(first_emp_col)
            last_l = get_column_letter(total_col - 1)
            put(r, total_col, f"=SUM({first_l}{r}:{last_l}{r})",
                fill=_FILL_TOTAL, font=Font(bold=True), fmt=fmt, is_formula=True)
        else:
            put(r, total_col, None, fill=_FILL_TOTAL)
        row += 1
        return r

    def emp_vals(getter):
        return [getter(e) for e in employees]

    adj = lambda e, cat: (e.get('adjustments') or {}).get(cat) or 0

    # Часы по ролям (первая роль — «Часы», вторая — «Часы 2-й в смене», как в эталоне)
    hours_labels = ['Часы', 'Часы 2-й в смене']
    for idx, role in enumerate(roles):
        label = hours_labels[idx] if idx < len(hours_labels) else f"Часы — {role['name']}"
        data_row(label,
                 emp_vals(lambda e, rn=role['name']: (e.get('hours_by_role') or {}).get(rn) or 0),
                 label_font=Font(italic=True), fmt=_FMT_HOURS)

    shifts_row = data_row('Количество смен',
                          emp_vals(lambda e: e.get('shifts_count') or 0),
                          label_fill=_FILL_YELLOW, label_font=Font(italic=True),
                          fmt='0', sum_total=False)

    # Оплата по ролям (часы x ставка — суммы уже посчитаны страницей)
    pay_labels = ['Ставка по часам', 'Ставка 2-й в смене']
    pay_rows = []
    for idx, role in enumerate(roles):
        label = pay_labels[idx] if idx < len(pay_labels) else f"Оплата — {role['name']}"
        pay_rows.append(data_row(
            label,
            emp_vals(lambda e, rn=role['name']: (e.get('pay_by_role') or {}).get(rn) or 0),
            meta=_META['pay'] if idx == 0 else None,
            tariff=role.get('rate'),
            label_fill=_FILL_GREEN if idx == 1 else None))

    vacation_row = data_row('Отпуск', emp_vals(lambda e: adj(e, 'vacation')),
                            label_font=Font(bold=True))

    handover_row = data_row('Премия за приемку-передачу смены',
                            emp_vals(lambda e: e.get('handover_bonus') or 0),
                            meta=_META['handover'], tariff=HANDOVER_RATE,
                            label_font=Font(bold=True))

    day_plan_row = data_row('Премия за дневной план',
                            emp_vals(lambda e: e.get('day_plan_bonus') or 0),
                            meta=_META['day_plan'], tariff=DAY_PLAN_RATE)

    kpi_rows = []
    for k_idx, k_name in enumerate(kpi_names):
        kpi_rows.append(data_row(
            f"KPI {k_idx + 1} — {k_name}",
            emp_vals(lambda e, i=k_idx: (e.get('kpi_premiums') or [0] * len(kpi_names))[i]
                     if i < len(e.get('kpi_premiums') or []) else 0),
            meta=_META['kpi'], tariff=base_per_kpi,
            data_fill=_FILL_KPI, fmt=_FMT_MONEY_2))

    extra_income_row = data_row('Доп доход', emp_vals(lambda e: adj(e, 'extra_income')),
                                meta=_META['extra_income'])

    # Такси: «расчёт» — формула смены x тариф; «мосты» и «оф.» дозаполняются в
    # файле; «разница» — формула, пересчитывается при заполнении.
    taxi_calc_row = data_row('Такси за смены расчет.', None,
                             meta=_META['taxi'], tariff=TAXI_RATE_PER_SHIFT,
                             label_fill=_FILL_YELLOW,
                             formula=lambda L, r, sr=shifts_row: f"={L}{sr}*$E{r}")
    mosty_row = data_row('мосты', None, label_fill=_FILL_YELLOW)
    taxi_official_row = data_row('Такси за смены оф.', None, meta=_META['taxi'])
    taxi_diff_row = data_row(
        'Такси разница: доплата/удержание', None,
        meta=_META['taxi'], label_fill=_FILL_YELLOW,
        formula=lambda L, r, a=taxi_calc_row, b=mosty_row, c=taxi_official_row:
            f"={L}{a}+{L}{b}-{L}{c}")

    red_label_font = Font(bold=True, color='FFFFFF')
    ded_inventory_row = data_row(
        'Вычет инвент', emp_vals(lambda e: adj(e, 'deduction_inventory')),
        meta=_META['ded_inventory'],
        label_fill=_FILL_RED_LABEL, label_font=red_label_font, data_fill=_FILL_RED_DATA)
    # Дисциплина = авто-штраф за опоздания (страница ЗП) + ручной вычет
    ded_discipline_row = data_row(
        'Вычет дисциплина',
        emp_vals(lambda e: (e.get('late_penalty') or 0) + adj(e, 'deduction_discipline')),
        meta=_META['ded_discipline'],
        label_fill=_FILL_RED_LABEL, label_font=red_label_font, data_fill=_FILL_RED_DATA)
    ded_other_row = data_row(
        'Доп вычет', emp_vals(lambda e: adj(e, 'deduction_other')),
        meta=_META['ded_other'],
        label_fill=_FILL_RED_LABEL, label_font=red_label_font, data_fill=_FILL_RED_DATA)

    # ИТОГО БАРМЕН = оплата по ролям + отпуск + премии + KPI + доп доход +
    # такси-разница - вычеты (часы/смены/такси-расчёт в итог не входят)
    plus_rows = pay_rows + [vacation_row, handover_row, day_plan_row] + kpi_rows + \
        [extra_income_row, taxi_diff_row]
    minus_rows = [ded_inventory_row, ded_discipline_row, ded_other_row]

    def total_formula(L):
        plus = '+'.join(f"{L}{r}" for r in plus_rows)
        minus = ''.join(f"-{L}{r}" for r in minus_rows)
        return f"={plus}{minus}"

    total_row = row
    put(total_row, 1, 'ИТОГО БАРМЕН', fill=_FILL_TOTAL, font=Font(bold=True))
    for col in range(2, first_emp_col):
        put(total_row, col, None, fill=_FILL_TOTAL)
    for col in emp_cols:
        put(total_row, col, total_formula(get_column_letter(col)),
            fill=_FILL_TOTAL, font=Font(bold=True), fmt=_FMT_MONEY, is_formula=True)
    if n_emp:
        put(total_row, total_col,
            f"=SUM({get_column_letter(first_emp_col)}{total_row}:"
            f"{get_column_letter(total_col - 1)}{total_row})",
            fill=_FILL_TOTAL, font=Font(bold=True), fmt=_FMT_MONEY, is_formula=True)
    else:
        put(total_row, total_col, None, fill=_FILL_TOTAL)

    # --- Оформление листа ---
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 9
    for col in emp_cols + [total_col]:
        ws.column_dimensions[get_column_letter(col)].width = 12
    ws.freeze_panes = ws.cell(row=3, column=first_emp_col)

    return wb

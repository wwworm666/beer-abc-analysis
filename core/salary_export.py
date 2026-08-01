"""
Экспорт расчёта ЗП (/salary) в Excel — формат эталонной таблицы бухгалтерии.

Строит книгу openpyxl из payload, который присылает фронтенд страницы /salary
(уже посчитанные и смёрженные данные — экспорт совпадает со страницей).
Структура листа повторяет таблицу бухгалтерии:

    A Показатель | B Хозяин цифры | C Дедлайн готовности | D Проверить |
    E Тариф | F.. по столбцу на сотрудника | последний столбец ИТОГО

Строки: часы по ролям, количество смен, оплата по ролям, отпуск, премия за
передачу смены, премия за дневной план, KPI 1..N, доп доход, такси
(расчёт/мосты/официально/разница), вычеты (инвент/дисциплина/доп),
ИТОГО БАРМЕН.

ФОРМУЛЫ (с 2026-08-01, требование владельца — файл должен вести себя как
таблица бухгалтерии: правишь часы/тариф/мосты — пересчитывается всё):

    Ставка по часам      =F3*$E$6          часы x тариф
    Премия за передачу   =F5*$E$9-500      смены x тариф - неоплаченные дни
    Такси расчет.        =F5*$E$15         смены x тариф
    Такси разница        =F15+F16-F17      расчёт + мосты - оф.
    ИТОГО БАРМЕН         =SUM(F6:F14)-F19-F20-F21+F18
    Колонка ИТОГО        =SUM(F6:N6)

Формулами пишется только то, что ВЫВОДИТСЯ из других строк листа. Первичные
величины (часы, смены, дневной план, KPI, вычеты) — числа: они посчитаны
сервером и в файле не выводимы.

ВАЖНО про формулы: openpyxl не пишет кэш вычисленных значений, поэтому
просмотрщики, которые сами не считают (предпросмотр Google Drive, защищённый
режим Excel), показывают формульные ячейки пустыми — жалоба владельца
2026-07-31, из-за неё формулы временно убирали. Смягчение: у книги выставлен
`fullCalcOnLoad` — Excel/LibreOffice/Google Sheets пересчитывают лист при
ОТКРЫТИИ файла, и значения появляются. В предпросмотре без открытия
формульные ячейки по-прежнему могут быть пустыми — это цена живых формул.

Строка «Премия за передачу смены» становится формулой ТОЛЬКО если она сходится
с «Количеством смен» листа (разница кратна тарифу): премия считается по
кассовым сменам iiko, а «Количество смен» — дневные смены графика, и эти числа
совпадают не всегда. Не сошлось — пишется числом (см. _handover_cell).

Payload (все суммы в рублях, уже рассчитаны страницей):
    {
      "month": "YYYY-MM",
      "kpi_names": ["Доля кухни (%)", ...],      # показатели месяца, по порядку
      "base_per_kpi": 5000,                       # тариф KPI = фонд / кол-во KPI
      "roles": [{"name": "бармен", "rate": 300}, ...],  # порядок = порядок строк
      "employees": [{
          "name": str,
          "hours_by_role": {role_name: часы},
          "pay_by_role": {role_name: оплата},     # для сверки; в файл идёт формула
          "shifts_count": int,                    # дневные смены графика за период
          "handover_bonus": float,                # премия за передачу смены
          "day_plan_bonus": float,                # премия за дневной план
          "kpi_premiums": [float, ...],           # по каждому KPI, уже с koef
          "late_penalty": float,                  # авто-штраф за опоздания
          "adjustments": {категория: сумма}       # vacation/extra_income/deduction_*;
                                                  # с 2026-07-31 фронт шлёт {} —
                                                  # эти строки заполняются в Excel
      }, ...]
    }
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Тариф такси за полноценную ДНЕВНУЮ смену — из эталонной таблицы бухгалтерии
# (колонка «Тариф» строки «Такси за смены расчет.»). Единственное место
# значения: страница ЗП получает его через /api/schedule/hours-by-role
# (расчёт = day_shifts x тариф), в экспорте пишется в ячейку тарифа, а
# строка считается формулой «смены x тариф» — правка тарифа в файле
# пересчитает всё.
TAXI_RATE_PER_SHIFT = 700

# «Такси за смены оф.» — официально такси всегда оплачивается за фиксированные
# 15 смен (15 x 700 = 10 500, правило владельца). В ЗП идёт разница:
# расчёт + мосты - оф. (доплата или удержание); «мосты» — ручная надбавка
# бухгалтера в Excel. Если дневных смен за период нет, оф. не начисляется
# (иначе у сотрудника «только вечера» появилось бы удержание 10 500).
# Число фиксированное, поэтому пишется значением, а не формулой от тарифа —
# как в эталоне (там 10 500 проставлено руками).
TAXI_OFFICIAL_SHIFTS = 15

# Служебные тарифы страницы ЗП (дублируют константы бэкенда только для показа
# в колонке «Тариф»; сами суммы приходят уже посчитанными):
# 500 — премия за передачу смены (routes/employee.py), 1000 — база премии
# за дневной план (routes/employee.py).
HANDOVER_RATE = 500
DAY_PLAN_RATE = 1000

# Шрифт эталонной таблицы бухгалтерии — PT Serif 8 пт во всех ячейках
# (проверено по «Новая таблица (3).xlsx»). Меняется только здесь.
FONT_NAME = 'PT Serif'
FONT_SIZE = 8

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

# Заливки — цвета эталонной таблицы бухгалтерии (сняты из её ячеек)
_FILL_HEADER = PatternFill('solid', fgColor='FFF2CC')   # шапка и ИТОГО БАРМЕН
_FILL_YELLOW = PatternFill('solid', fgColor='FFFF00')   # смены и блок такси
_FILL_GREEN = PatternFill('solid', fgColor='00FF00')    # «2-й в смене», хозяин РЮ
_FILL_KPI = PatternFill('solid', fgColor='D9EAD3')      # блок KPI целиком
_FILL_RED_LABEL = PatternFill('solid', fgColor='CC0000')  # подписи вычетов
_FILL_RED_DATA = PatternFill('solid', fgColor='F4CCCC')   # данные вычетов
_FILL_TOTAL = PatternFill('solid', fgColor='FFF2CC')

_THIN = Side(style='thin', color='BFBFBF')
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FMT_MONEY = '#,##0'
_FMT_MONEY_2 = '#,##0.00'
_FMT_HOURS = 'General'  # часы бывают дробными (97.5) — General не рисует хвост у целых


class _Formula(str):
    """Маркер намеренной формулы Excel.

    Обычная строка с ведущим «=» (например имя сотрудника «=Иванов» —
    опечатка или подделка) принудительно пишется текстом, иначе она ушла бы в
    файл живой формулой. Формулы, которые ставит сам модуль, помечаются этим
    типом и проходят как формулы.
    """


def _font(bold=False, italic=False, color=None):
    """Шрифт эталона (PT Serif 8) с нужными начертаниями."""
    return Font(name=FONT_NAME, size=FONT_SIZE, bold=bold, italic=italic, color=color)


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


def build_salary_workbook(payload: dict) -> Workbook:
    """Собрать книгу Excel из payload страницы /salary (контракт в докстроке модуля)."""
    month = payload.get('month') or ''
    roles = payload.get('roles') or []
    kpi_names = payload.get('kpi_names') or []
    base_per_kpi = payload.get('base_per_kpi') or 0
    employees = payload.get('employees') or []

    wb = Workbook()
    # Формулы в файле живые, но openpyxl не пишет их вычисленные значения:
    # без этого флага лист открылся бы с пустыми формульными ячейками.
    wb.calculation.fullCalcOnLoad = True
    # Шрифт по умолчанию — для ячеек, которых модуль не касается (приватный
    # API openpyxl, поэтому под try: без него файл всё равно корректен —
    # каждая записанная ячейка получает шрифт явно).
    try:
        wb._named_styles['Normal'].font = _font()
    except Exception:
        pass

    ws = wb.active
    ws.title = sheet_title(month)

    n_emp = len(employees)
    first_emp_col = 6                      # F — первый сотрудник (A..E — метаданные)
    total_col = first_emp_col + n_emp      # последний столбец — ИТОГО
    emp_cols = [first_emp_col + i for i in range(n_emp)]
    emp_letters = [get_column_letter(c) for c in emp_cols]
    last_emp_letter = emp_letters[-1] if emp_letters else None

    def put(row, col, value, fill=None, font=None, fmt=None, align=None):
        cell = ws.cell(row=row, column=col, value=value)
        # openpyxl типизирует любую строку с ведущим «=» как формулу: имя
        # сотрудника вида «=Иванов» ушло бы в файл живой формулой. Формулы
        # модуля помечены _Formula, всё остальное с «=» — принудительно текст.
        if isinstance(value, str) and value.startswith('=') and not isinstance(value, _Formula):
            cell.data_type = 's'
        cell.border = _BORDER
        cell.font = font or _font()
        if fill:
            cell.fill = fill
        if fmt:
            cell.number_format = fmt
        if align:
            cell.alignment = align
        return cell

    center = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # --- Строка 1 пустая, строка 2 — шапка (как в таблице бухгалтерии) ---
    put(2, 1, 'Показатель', font=_font(italic=True), align=center)
    for i, h in enumerate(['Хозяин цифры', 'Дедлайн готовности', 'Проверить', 'Тариф'],
                          start=2):
        put(2, i, h, font=_font(bold=True, italic=True), align=center)
    for i, emp in enumerate(employees):
        put(2, first_emp_col + i, emp.get('name', ''), fill=_FILL_HEADER,
            font=_font(bold=True), align=center)
    put(2, total_col, 'ИТОГО', fill=_FILL_HEADER, font=_font(bold=True), align=center)

    # --- Данные: строки добавляются последовательно, номера запоминаем ---
    row = 3

    def data_row(label, values=None, meta=None, tariff=None, label_fill=None,
                 label_font=None, data_fill=None, meta_fill=None, owner_fill=None,
                 fmt=_FMT_MONEY, sum_total=True):
        """Одна строка таблицы.

        values — список по сотрудникам ИЛИ функция (номер_строки) -> список
        (нужна формулам, которые ссылаются на собственную строку, например
        «часы x $E$<своя строка>»). Элемент: число, None (пусто) или _Formula.
        ИТОГО по строке — формула SUM по колонкам сотрудников.
        """
        nonlocal row
        r = row
        row += 1
        if callable(values):
            values = values(r)
        put(r, 1, label, fill=label_fill, font=label_font or _font())
        owner, deadline, checker = meta or ('', '', '')
        put(r, 2, owner or None, fill=owner_fill or meta_fill, align=center)
        put(r, 3, deadline or None, fill=meta_fill, font=_font(italic=True), align=center)
        put(r, 4, checker or None, fill=meta_fill, align=center)
        put(r, 5, tariff, fill=meta_fill, font=_font(italic=True),
            fmt=_FMT_MONEY, align=center)
        for i, col in enumerate(emp_cols):
            v = values[i] if values else None
            # Нули не показываем (как в эталоне), но KPI-строки печатают 0.00
            if v == 0 and fmt != _FMT_MONEY_2 and not isinstance(v, _Formula):
                v = None
            put(r, col, v, fill=data_fill, fmt=fmt)
        total = None
        if n_emp and sum_total:
            total = _Formula(f"=SUM({emp_letters[0]}{r}:{last_emp_letter}{r})")
        put(r, total_col, total, fill=_FILL_TOTAL, font=_font(bold=True), fmt=fmt)
        return r

    def emp_vals(getter):
        return [getter(e) for e in employees]

    adj = lambda e, cat: (e.get('adjustments') or {}).get(cat) or 0

    # Часы по ролям (первая роль — «Часы», вторая — «Часы 2-й в смене», как в
    # эталоне) — числа: первичные данные, из листа не выводятся
    hours_labels = ['Часы', 'Часы 2-й в смене']
    hours_rows = []
    for idx, role in enumerate(roles):
        label = hours_labels[idx] if idx < len(hours_labels) else f"Часы — {role['name']}"
        hours_rows.append(data_row(
            label,
            emp_vals(lambda e, rn=role['name']: (e.get('hours_by_role') or {}).get(rn) or 0),
            label_font=_font(italic=True), fmt=_FMT_HOURS))

    shifts_row = data_row('Количество смен',
                          emp_vals(lambda e: e.get('shifts_count') or 0),
                          label_fill=_FILL_YELLOW, label_font=_font(italic=True),
                          fmt='0', sum_total=False)

    # Оплата по ролям — ФОРМУЛА «часы x тариф»: правка часов или ставки в
    # файле пересчитывает оплату, ИТОГО и итог сотрудника
    def _pay_cell(e, role_name, rate, r, letter, h_row):
        """Оплата роли: формула, если она воспроизводит сумму страницы.

        Страница считает оплату из НЕокруглённых часов (minutes/60 x ставка),
        а в ячейку часов идёт значение, округлённое до сотых — на длинном
        месяце формула «часы x тариф» может разойтись со страницей на рубль.
        Разошлась — пишем сумму страницы числом (экспорт обязан совпадать с
        расчётом), иначе живую формулу.
        """
        hours = (e.get('hours_by_role') or {}).get(role_name) or 0
        pay = (e.get('pay_by_role') or {}).get(role_name)
        if pay is None or round(hours * (rate or 0), 2) == round(pay, 2):
            return _Formula(f"={letter}{h_row}*$E${r}")
        return pay

    pay_labels = ['Ставка по часам', 'Ставка 2-й в смене']
    pay_rows = []
    for idx, role in enumerate(roles):
        label = pay_labels[idx] if idx < len(pay_labels) else f"Оплата — {role['name']}"
        h_row = hours_rows[idx]
        rate = role.get('rate')
        pay_rows.append(data_row(
            label,
            lambda r, hr=h_row, rn=role['name'], rt=rate: [
                _pay_cell(e, rn, rt, r, emp_letters[i], hr)
                for i, e in enumerate(employees)],
            meta=_META['pay'] if idx == 0 else None,
            tariff=rate,
            label_fill=_FILL_GREEN if idx == 1 else None))

    vacation_row = data_row('Отпуск', emp_vals(lambda e: adj(e, 'vacation')))

    def _handover_cell(e, r, letter):
        """Премия за передачу смены: формула, если сходится с «Кол-вом смен».

        Премия считается по кассовым сменам iiko минус дни без кассы и ручные
        штрафы, а строка «Количество смен» — это дневные смены графика. Когда
        разница кратна тарифу (обычный случай), пишем формулу в стиле эталона
        «=F5*$E$9-500»; когда нет — премию числом, чтобы файл не показал
        сумму, отличную от расчёта страницы.
        """
        shifts = e.get('shifts_count') or 0
        bonus = e.get('handover_bonus') or 0
        unpaid = shifts * HANDOVER_RATE - bonus
        if shifts and unpaid >= 0 and float(unpaid).is_integer() \
                and int(unpaid) % HANDOVER_RATE == 0:
            formula = f"={letter}{shifts_row}*$E${r}"
            if unpaid:
                formula += f"-{int(unpaid)}"
            return _Formula(formula)
        return bonus

    handover_row = data_row(
        'Премия за приемку-передачу смены',
        lambda r: [_handover_cell(e, r, emp_letters[i]) for i, e in enumerate(employees)],
        meta=_META['handover'], tariff=HANDOVER_RATE,
        label_font=_font(bold=True), owner_fill=_FILL_GREEN)

    day_plan_row = data_row('Премия за дневной план',
                            emp_vals(lambda e: e.get('day_plan_bonus') or 0),
                            meta=_META['day_plan'], tariff=DAY_PLAN_RATE)

    kpi_rows = []
    for k_idx, k_name in enumerate(kpi_names):
        kpi_rows.append(data_row(
            f"KPI {k_idx + 1} — {k_name}",
            emp_vals(lambda e, i=k_idx: (e.get('kpi_premiums') or [])[i]
                     if i < len(e.get('kpi_premiums') or []) else 0),
            meta=_META['kpi'], tariff=base_per_kpi,
            label_fill=_FILL_KPI, label_font=_font(bold=True),
            meta_fill=_FILL_KPI, data_fill=_FILL_KPI, fmt=_FMT_MONEY_2))

    extra_income_row = data_row('Доп доход', emp_vals(lambda e: adj(e, 'extra_income')),
                                meta=_META['extra_income'], label_font=_font(bold=True))

    # --- Такси ---
    # расчёт — формула «смены x тариф»; оф. — фикс 15 смен (число, как в
    # эталоне); мосты — единственная ручная строка бухгалтера; разница —
    # формула, поэтому вписанные мосты сразу меняют разницу и ИТОГО БАРМЕН.
    taxi_calc_row = data_row(
        'Такси за смены расчет.',
        lambda r: [_Formula(f"={L}{shifts_row}*$E${r}") for L in emp_letters],
        meta=_META['taxi'], tariff=TAXI_RATE_PER_SHIFT,
        label_fill=_FILL_YELLOW, label_font=_font(bold=True))
    bridges_row = data_row('мосты', None,
                           label_fill=_FILL_YELLOW, label_font=_font(bold=True))
    official_row = data_row(
        'Такси за смены оф.',
        emp_vals(lambda e: TAXI_OFFICIAL_SHIFTS * TAXI_RATE_PER_SHIFT
                 if (e.get('shifts_count') or 0) > 0 else 0),
        meta=_META['taxi'], label_fill=_FILL_YELLOW, label_font=_font(bold=True))
    taxi_diff_row = data_row(
        'Такси разница: доплата/удержание',
        [_Formula(f"={L}{taxi_calc_row}+{L}{bridges_row}-{L}{official_row}")
         for L in emp_letters],
        meta=_META['taxi'], label_fill=_FILL_YELLOW, label_font=_font(bold=True))

    # --- Вычеты ---
    red_label_font = _font(bold=True, color='FFFFFF')
    ded_rows = []
    ded_rows.append(data_row(
        'Вычет инвент', emp_vals(lambda e: adj(e, 'deduction_inventory')),
        meta=_META['ded_inventory'], label_fill=_FILL_RED_LABEL,
        label_font=red_label_font, meta_fill=_FILL_RED_DATA, data_fill=_FILL_RED_DATA))
    # Дисциплина = авто-штраф за опоздания (страница ЗП) + ручной вычет
    ded_rows.append(data_row(
        'Вычет дисциплина',
        emp_vals(lambda e: (e.get('late_penalty') or 0) + adj(e, 'deduction_discipline')),
        meta=_META['ded_discipline'], label_fill=_FILL_RED_LABEL,
        label_font=red_label_font, meta_fill=_FILL_RED_DATA, data_fill=_FILL_RED_DATA))
    ded_rows.append(data_row(
        'Доп вычет', emp_vals(lambda e: adj(e, 'deduction_other')),
        meta=_META['ded_other'], label_fill=_FILL_RED_LABEL,
        label_font=red_label_font, meta_fill=_FILL_RED_DATA, data_fill=_FILL_RED_DATA))

    # ИТОГО БАРМЕН = непрерывный блок «оплата..доп доход» + такси-разница -
    # вычеты (часы/смены/такси-расчёт/оф. в итог не входят). Формула той же
    # формы, что в таблице бухгалтерии: =SUM(F6:F14)-F19-F20-F21+F18
    total_row = row
    put(total_row, 1, 'ИТОГО БАРМЕН', fill=_FILL_TOTAL, font=_font(bold=True))
    for col in range(2, first_emp_col):
        put(total_row, col, None, fill=_FILL_TOTAL)
    if pay_rows:
        block_start, block_end = pay_rows[0], extra_income_row
        for i, col in enumerate(emp_cols):
            L = emp_letters[i]
            formula = (f"=SUM({L}{block_start}:{L}{block_end})"
                       + ''.join(f"-{L}{d}" for d in ded_rows)
                       + f"+{L}{taxi_diff_row}")
            put(total_row, col, _Formula(formula), fill=_FILL_TOTAL,
                font=_font(bold=True), fmt=_FMT_MONEY)
    else:
        for col in emp_cols:
            put(total_row, col, None, fill=_FILL_TOTAL, font=_font(bold=True))
    put(total_row, total_col,
        _Formula(f"=SUM({emp_letters[0]}{total_row}:{last_emp_letter}{total_row})")
        if n_emp else None,
        fill=_FILL_TOTAL, font=_font(bold=True), fmt=_FMT_MONEY)

    # --- Оформление листа (ширины — как в таблице бухгалтерии) ---
    ws.column_dimensions['A'].width = 26.5
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 11
    ws.column_dimensions['D'].width = 9
    ws.column_dimensions['E'].width = 8
    for col in emp_cols:
        ws.column_dimensions[get_column_letter(col)].width = 9.5
    ws.column_dimensions[get_column_letter(total_col)].width = 11.13
    ws.freeze_panes = ws.cell(row=3, column=first_emp_col)

    return wb

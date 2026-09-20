"""Проверки расчёта ABC/XYZ фасовки (core/packaging_analysis.py).

    python tests/test_packaging_analysis.py

Главное, что здесь фиксируется — ИНВАРИАНТЫ СВЕДЕНИЯ в разрез «Общая». Прежний
расчёт ломался именно на них, причём молча: выручка сети оказывалась МЕНЬШЕ суммы
баров (позиции с незаполненным стилем выбрасывал groupby с dropna=True), наценка
бралась максимумом по барам, а XYZ считался по разбросу МЕЖДУ БАРАМИ вместо
недель. Ни одна из этих поломок не давала исключения — только неверные буквы.
Поэтому тесты сверяют суммы с сырыми строками, а не с самими собой.

Данные: data/beer_report.json — реальный ответ OLAP (4 бара, 30 дней) плюс
синтетические наборы там, где нужно проверить поведение на краю.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.abc_thresholds import (  # noqa: E402
    MARKUP_A_MIN,
    MIN_XYZ_WEEKS,
    UNCATEGORIZED,
    XYZ_X_MAX_CV,
    XYZ_Y_MAX_CV,
)
from core.packaging_analysis import PackagingAnalysis  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                       'data', 'beer_report.json')

passed = 0
failed = 0


def _run(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f'  ok  {name}')
    except Exception as exc:  # noqa: BLE001 — тестовый раннер печатает любую причину
        failed += 1
        print(f'FAIL  {name}')
        print(f'      {type(exc).__name__}: {exc}')


def load_rows():
    with open(FIXTURE, 'r', encoding='utf-8') as handle:
        return json.load(handle)['data']


def fixture_period(rows):
    days = sorted({str(r['OpenDate.Typed'])[:10] for r in rows})
    return days[0], days[-1]


def build_total():
    rows = load_rows()
    date_from, date_to = fixture_period(rows)
    return rows, PackagingAnalysis(rows, date_from, date_to).build(None)


def row(bar, dish, day, qty, revenue, cost, style='Лагер (Ф)', country='Россия'):
    """Строка OLAP для синтетических наборов."""
    return {
        'Store.Name': bar,
        'DishName': dish,
        'DishGroup.ThirdParent': style,
        'DishForeignName': country,
        'OpenDate.Typed': day,
        'DishAmountInt': qty,
        'DishDiscountSumInt': revenue,
        'ProductCostBase.ProductCost': cost,
    }


# ==================== инварианты сведения ====================

def test_total_keeps_every_rouble():
    """Выручка и штуки разреза «Общая» равны сумме сырых строк.

    Ровно здесь ломался прежний расчёт: позиции с пустым стилем выпадали, и
    «Общая» показывала меньше денег, чем сумма баров.
    """
    rows, block = build_total()
    raw_revenue = sum(float(r.get('DishDiscountSumInt') or 0) for r in rows)
    raw_qty = sum(float(r.get('DishAmountInt') or 0) for r in rows)
    assert abs(block['totals']['revenue'] - raw_revenue) < 0.01, \
        f"выручка {block['totals']['revenue']:.2f} против сырых {raw_revenue:.2f}"
    assert abs(block['totals']['qty'] - raw_qty) < 0.01, \
        f"штуки {block['totals']['qty']:.2f} против сырых {raw_qty:.2f}"


def test_total_equals_sum_of_bars():
    """Сумма разрезов по барам сходится с разрезом «Общая».

    Это и есть «свести в тотал»: сеть не теряет и не выдумывает ни рубля.
    """
    rows, total = build_total()
    date_from, date_to = fixture_period(rows)
    bars = sorted({str(r['Store.Name']).strip() for r in rows})
    per_bar = 0.0
    per_bar_qty = 0.0
    for bar in bars:
        block = PackagingAnalysis(rows, date_from, date_to).build(bar)
        per_bar += block['totals']['revenue']
        per_bar_qty += block['totals']['qty']
    assert abs(total['totals']['revenue'] - per_bar) < 0.01, \
        f"«Общая» {total['totals']['revenue']:.2f} против суммы баров {per_bar:.2f}"
    assert abs(total['totals']['qty'] - per_bar_qty) < 0.01


def test_positions_and_categories_reconcile():
    """Позиции и категории складываются в тот же итог, что показан в сводке."""
    _, block = build_total()
    total = block['totals']['revenue']
    by_positions = sum(p['TotalRevenue'] for p in block['positions'])
    by_categories = sum(c['TotalRevenue'] for c in block['categories'])
    assert abs(by_positions - total) < 0.01, 'позиции не складываются в итог'
    assert abs(by_categories - total) < 0.01, 'категории не складываются в итог'
    shares = sum(p['RevenueSharePercent'] for p in block['positions'])
    assert abs(shares - 100.0) < 0.01, f'доли позиций дают {shares:.4f}%, а не 100%'


def test_beers_count_is_unique_positions():
    """«Позиций» в категории — уникальные фасовки, а не строки.

    Прежний счётчик считал пары (бар, фасовка) и в сетевом разрезе завышал
    количество на 45%: «Хели (Ф)» показывала 23 позиции вместо 7.
    """
    _, block = build_total()
    by_categories = sum(c['BeersCount'] for c in block['categories'])
    assert by_categories == block['totals']['sku'], \
        f"сумма BeersCount {by_categories} против SKU {block['totals']['sku']}"
    names = {p['Beer'] for p in block['positions']}
    assert len(names) == block['totals']['sku'], 'позиции повторяются'


def test_all_categories_present():
    """Показаны ВСЕ категории разреза, включая позиции без стиля.

    Урезание до топ-10 жило на фронте, но проверять надо и здесь: сервер обязан
    отдавать полный список, иначе «все категории» физически неоткуда взять.
    """
    rows, block = build_total()
    expected = set()
    for r in rows:
        style = str(r.get('DishGroup.ThirdParent') or '').strip()
        expected.add(style if style else UNCATEGORIZED)
    got = {c['Category'] for c in block['categories']}
    assert got == expected, f'разошлись категории: {expected ^ got}'
    assert UNCATEGORIZED in got, 'позиции без стиля потерялись'


def test_categories_sorted_and_cumulative_reaches_100():
    """Категории отсортированы по выручке, накопленный процент доходит до 100."""
    _, block = build_total()
    revenues = [c['TotalRevenue'] for c in block['categories']]
    assert revenues == sorted(revenues, reverse=True), 'категории не по убыванию выручки'
    assert abs(block['categories'][-1]['CumulativePercent'] - 100.0) < 0.01, \
        'накопленный процент не доходит до 100'


# ==================== экономика ====================

def test_markup_is_weighted_not_max():
    """Наценка сети считается от сумм, а не берётся максимумом по барам.

    Бар с копеечной себестоимостью и огромной наценкой не должен задавать
    наценку всей сети: раньше 'max' по барам поднимал позицию в корзину
    «звёзды», хотя по факту продаж она едва окупалась.
    """
    rows = [
        # Много продаж с наценкой 5%: 10 000 себестоимости, 10 500 выручки.
        row('Бар А', 'Пиво', '2026-01-05', 100, 10500, 10000),
        # Одна продажа с наценкой 300%: 100 себестоимости, 400 выручки.
        row('Бар Б', 'Пиво', '2026-01-05', 1, 400, 100),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    # (10900 - 10100) / 10100 = 7,92%
    assert abs(item['MarkupPercent'] - 7.9207920792) < 0.001, \
        f"наценка {item['MarkupPercent']:.4f}% вместо взвешенной 7,92%"
    assert item['ABC_Markup'] == 'C', 'наценка ниже 100% должна давать C'
    assert abs(block['totals']['markup_percent'] - 7.9207920792) < 0.001


def test_markup_undefined_when_no_cost():
    """Нулевая себестоимость — наценка не определена, а не C.

    Раньше такая позиция молча получала C и уезжала в корзину «поднять
    наценку», хотя наценку у неё просто не из чего посчитать.
    """
    rows = [row('Бар А', 'Пиво', '2026-01-05', 5, 1000, 0)]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    assert item['MarkupPercent'] is None, 'наценка выдумана из нулевой себестоимости'
    assert item['ABC_Markup'] is None, 'буква наценки выдумана'
    assert item['ABC_Bucket'] == 'check', 'без себестоимости позиция должна попасть в «Сверить учёт»'
    assert item['ABC_Combined'].endswith('?'), 'в коде нет отметки о нехватке данных'


def test_markup_threshold_boundary():
    """Ровно 120% наценки — это A, граница включающая."""
    rows = [row('Бар А', 'Пиво', '2026-01-05', 10, 2200, 1000)]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    assert abs(item['MarkupPercent'] - MARKUP_A_MIN * 100) < 1e-9
    assert item['ABC_Markup'] == 'A', 'порог наценки перестал быть включающим'


def test_cost_per_unit_is_average_not_max():
    """Себестоимость единицы — от сумм, а не максимум по барам."""
    rows = [
        row('Бар А', 'Пиво', '2026-01-05', 10, 2000, 1000),   # 100 за штуку
        row('Бар Б', 'Пиво', '2026-01-05', 10, 2000, 2000),   # 200 за штуку
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    assert abs(item['CostPerUnit'] - 150.0) < 1e-9, \
        f"себестоимость единицы {item['CostPerUnit']} вместо 150"


# ==================== XYZ ====================

def test_xyz_measures_weeks_not_bars():
    """XYZ меряет недели, а не разброс между барами.

    Позиция продаётся ровно по 10 штук каждую неделю, но в одном баре сильно
    больше, чем в другом. Прежний расчёт брал std по барам и выдавал Z; честный
    недельный ряд ровный, поэтому буква X.
    """
    rows = []
    for week in range(4):
        day = f'2026-01-{5 + week * 7:02d}'
        rows.append(row('Бар А', 'Пиво', day, 9, 900, 400))
        rows.append(row('Бар Б', 'Пиво', day, 1, 100, 45))
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    assert item['BarsPresent'] == 2, 'разбивка по барам потерялась'
    assert item['WeeksWithSales'] == 4
    assert abs(item['CoefficientOfVariation']) < 1e-9, \
        f"ровный недельный ряд дал CV {item['CoefficientOfVariation']}"
    assert item['XYZ_Category'] == 'X', 'ровный спрос должен быть X'


def test_single_sale_gets_no_letter():
    """Позиция, проданная один раз, буквы не получает.

    Прежний расчёт выбрасывал недели без продаж и на единственной продаже давал
    CV = 0%, то есть букву X — «идеально стабильный спрос». Это был худший из
    дефектов: редкая позиция выглядела надёжнее флагмана.
    """
    rows = [row('Бар А', 'Пиво', '2026-01-05', 1, 100, 45)]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    assert item['XYZ_Category'] is None, 'разовая продажа получила букву XYZ'
    assert item['CoefficientOfVariation'] is None
    assert item['XYZ_Reason'] == 'weeks'
    assert item['WeeksWithSales'] == 1


def test_short_period_has_no_xyz_at_all():
    """На периоде короче трёх полных недель XYZ не считается ни у кого."""
    rows = [row('Бар А', 'Пиво', '2026-01-05', 3, 300, 100),
            row('Бар А', 'Пиво', '2026-01-12', 3, 300, 100)]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-01-18').build(None)
    assert block['period']['weeks'] == 2
    assert block['xyz_available'] is False
    assert block['min_xyz_weeks'] == MIN_XYZ_WEEKS
    assert all(p['XYZ_Category'] is None for p in block['positions'])
    assert all(p['XYZ_Reason'] == 'period' for p in block['positions'])


def test_xyz_thresholds_match_documented_bounds():
    """Границы XYZ включающие: ровно 30% — ещё X, ровно 60% — ещё Y."""
    from core.abc_thresholds import xyz_letter
    assert xyz_letter(XYZ_X_MAX_CV) == 'X'
    assert xyz_letter(XYZ_X_MAX_CV + 0.001) == 'Y'
    assert xyz_letter(XYZ_Y_MAX_CV) == 'Y'
    assert xyz_letter(XYZ_Y_MAX_CV + 0.001) == 'Z'
    assert xyz_letter(None) is None


def test_week_window_is_anchored_to_the_end():
    """Недельное окно прижато к КОНЦУ периода, а не к началу.

    Ни один пресет страницы не делится на 7 нацело, поэтому кусок периода
    всегда остаётся вне недель. При якоре к началу за бортом оказывались самые
    СВЕЖИЕ дни, и позиция, заведённая на последней неделе, получала «продавалась
    0 недель из 4» рядом со своей же выручкой.
    """
    # 30 дней -> 4 недели (28 дней), 2 дня остаются снаружи.
    rows = [row('Бар А', 'Пиво', '2026-01-30', 5, 500, 200)]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-03').build(None)
    period = block['period']
    assert period['days'] == 30 and period['weeks'] == 4
    assert period['weeks_to'] == '2026-02-03', 'окно не кончается вместе с периодом'
    assert period['weeks_from'] == '2026-01-07', 'окно не прижато к концу'
    # Продажа 30 января попадает в окно, а не выбрасывается как хвост.
    item = block['positions'][0]
    assert item['WeeksWithSales'] == 1, 'свежая продажа выпала из недель'
    assert item['QtyOutsideWeeks'] == 0


def test_sales_outside_window_are_counted_and_flagged():
    """Продажи вне недельного окна попадают в итоги и помечены отдельно.

    Деньги терять нельзя, но и молчать нельзя: без QtyOutsideWeeks страница
    печатала «0 недель с продажами» под выручкой позиции и выглядела сломанной.
    """
    rows = [row('Бар А', 'Пиво', '2026-01-05', 7, 700, 300)]   # первый день, вне окна
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-03').build(None)
    item = block['positions'][0]
    assert item['TotalQty'] == 7, 'штуки вне окна потерялись из итога'
    assert block['totals']['revenue'] == 700, 'выручка вне окна потерялась из итога'
    assert item['WeeksWithSales'] == 0
    assert item['QtyOutsideWeeks'] == 7, 'продажи вне окна ничем не помечены'
    assert sum(item['WeeklyQty']) == 0


def test_abc_bases_are_reported_so_the_formula_reproduces():
    """Базы долей отдаются отдельно от итогов — иначе формула в карточке врёт.

    ABC считается от суммы ПОЛОЖИТЕЛЬНЫХ значений, а totals.margin включает
    убыточные позиции. Подставив totals.margin в знаменатель, страница печатала
    деление, которое не даёт показанный процент.
    """
    rows = [
        row('Бар А', 'Прибыльное', '2026-01-05', 10, 3000, 1000),
        row('Бар А', 'Убыточное', '2026-01-05', 10, 500, 900),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    totals = block['totals']
    assert totals['margin'] == 1600, totals['margin']           # 2000 + (-400)
    assert totals['margin_abc_base'] == 2000, 'база маржи включила убыток'
    assert totals['margin'] != totals['margin_abc_base'], 'тест ничего не доказывает'
    good = next(p for p in block['positions'] if p['Beer'] == 'Прибыльное')
    # Ровно то деление, которое печатает карточка.
    assert abs(good['TotalMargin'] / totals['margin_abc_base'] * 100
               - good['MarginSharePercent']) < 1e-9
    assert abs(good['TotalRevenue'] / totals['revenue_abc_base'] * 100
               - good['RevenueSharePercent']) < 1e-9
    assert abs(good['TotalRevenue'] / good['RevenueBaseInCategory'] * 100
               - good['RevenueShareInCategoryPercent']) < 1e-9


def test_category_and_country_follow_the_money():
    """При переклассификации в номенклатуре побеждает вариант с большей выручкой.

    Раньше бралась первая встреченная строка OLAP, то есть результат зависел от
    того, как iiko отсортировал ответ.
    """
    rows = [
        row('Бар А', 'Пиво', '2026-01-05', 1, 100, 40, 'Старый стиль (Ф)', ''),
        row('Бар А', 'Пиво', '2026-01-12', 20, 9000, 4000, 'Новый стиль (Ф)', 'Бельгия'),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    assert item['Category'] == 'Новый стиль (Ф)', item['Category']
    # Пустая страна в первой строке не должна навсегда фиксировать прочерк.
    assert item['Country'] == 'Бельгия', item['Country']
    assert item['TotalRevenue'] == 9100, 'деньги при склейке потерялись'
    # Порядок строк на результат не влияет.
    other = PackagingAnalysis(list(reversed(rows)), '2026-01-05', '2026-02-01').build(None)
    assert other['positions'][0]['Category'] == item['Category']
    assert other['positions'][0]['Country'] == item['Country']


def test_by_bar_order_is_deterministic():
    """При равной выручке бары идут по алфавиту, а не по порядку строк OLAP."""
    rows = [
        row('Яблочный', 'Пиво', '2026-01-05', 5, 1000, 400),
        row('Абрикосовый', 'Пиво', '2026-01-05', 5, 1000, 400),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    bars = [b['Bar'] for b in block['positions'][0]['ByBar']]
    assert bars == ['Абрикосовый', 'Яблочный'], bars
    other = PackagingAnalysis(list(reversed(rows)), '2026-01-05', '2026-02-01').build(None)
    assert [b['Bar'] for b in other['positions'][0]['ByBar']] == bars


def test_inverted_period_is_rejected():
    """Перевёрнутый период — ошибка, а не отрицательное число дней в ответе."""
    try:
        PackagingAnalysis([], '2026-02-01', '2026-01-05')
    except ValueError as exc:
        assert 'позже' in str(exc), str(exc)
    else:
        raise AssertionError('перевёрнутый период принят без ошибки')


def test_weekly_series_covers_whole_period():
    """Недельный ряд отдаётся целиком, включая недели без продаж.

    Карточка рисует по нему столбики: пустые недели объясняют, почему буквы
    может не быть, и прятать их нельзя.
    """
    rows = [row('Бар А', 'Пиво', '2026-01-05', 5, 500, 200),
            row('Бар А', 'Пиво', '2026-01-19', 5, 500, 200)]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    item = block['positions'][0]
    assert item['WeeklyQty'] == [5.0, 0.0, 5.0, 0.0], \
        f"недельный ряд {item['WeeklyQty']}"
    assert len(item['WeeklyQty']) == block['period']['weeks']


# ==================== ABC и корзины ====================

def test_abc_revenue_follows_pareto():
    """Первая буква — накопленная доля выручки, а не просто место в списке."""
    rows = [
        row('Бар А', 'Флагман', '2026-01-05', 100, 80000, 30000),
        row('Бар А', 'Середняк', '2026-01-05', 20, 15000, 6000),
        row('Бар А', 'Хвост', '2026-01-05', 5, 5000, 2000),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    letters = {p['Beer']: p['ABC_Revenue'] for p in block['positions']}
    assert letters == {'Флагман': 'A', 'Середняк': 'B', 'Хвост': 'C'}, letters


def test_dominant_position_is_always_a():
    """Позиция, которая одна даёт больше 80% выручки, получает A.

    При наивной проверке «накоплено <= 80» единственный флагман получал B,
    хотя он и есть вся выручка. Буква считается по накопленному ДО позиции,
    поэтому первая строка списка всегда A.
    """
    rows = [
        row('Бар А', 'Флагман', '2026-01-05', 100, 90000, 40000),
        row('Бар А', 'Прочее', '2026-01-05', 10, 10000, 4000),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    top = block['positions'][0]
    assert top['Beer'] == 'Флагман'
    assert top['ABC_Revenue'] == 'A', f"флагман получил {top['ABC_Revenue']}"
    assert abs(top['RevenueCumulativePercent'] - 90.0) < 0.01, \
        'накопленный процент должен включать саму позицию'


def test_two_abc_scales_are_both_reported():
    """Буква по выручке считается от двух баз, и обе приезжают в ответ.

    Внутрикатегорийная и общеассортиментная шкалы расходятся у каждой пятой
    позиции. Раньше на экране под одинаковым значком A/B/C жили обе, и это
    выглядело ошибкой расчёта.
    """
    rows = [
        row('Бар А', 'Большой лагер', '2026-01-05', 100, 90000, 40000, 'Лагер (Ф)'),
        row('Бар А', 'Малый лагер', '2026-01-05', 5, 2000, 900, 'Лагер (Ф)'),
        row('Бар А', 'Единственный стаут', '2026-01-05', 6, 8000, 3000, 'Стаут (Ф)'),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    stout = next(p for p in block['positions'] if p['Beer'] == 'Единственный стаут')
    # В своей категории он один, значит первые 80% выручки категории — это он.
    assert stout['ABC_Revenue_InCategory'] == 'A'
    assert abs(stout['RevenueShareInCategoryPercent'] - 100.0) < 0.01
    # По всему ассортименту он второй и в первые 80% уже не попадает.
    assert stout['ABC_Revenue'] == 'B', stout['ABC_Revenue']


def test_bucket_decisions_follow_rules_and_cover_everything():
    """Группа решения воспроизводится из полей позиции правилами
    core/abc_buckets.py; каждая позиция ровно в одной группе, карточки с сервера."""
    from core.abc_buckets import BUCKETS, decide_bucket
    _, block = build_total()
    for item in block['positions']:
        share = None if item['MarkupPercent'] is None else item['MarkupPercent'] / 100
        expected = decide_bucket(item['ABC_Revenue'], share, item['TotalQty'],
                                 item['WeeksInPeriod'], item['WeeklyQty'],
                                 item['QtyOutsideWeeks'])
        assert item['ABC_Bucket'] == expected, \
            f"{item['Beer']}: {item['ABC_Bucket']}, ждали {expected}"
        assert item['ABC_Bucket'] in BUCKETS
    assert sum(block['bucket_stats'].values()) == len(block['positions'])
    cards = block['buckets']
    assert [c['key'] for c in cards] == [k for k, _ in sorted(BUCKETS.items(), key=lambda kv: kv[1]['order'])]
    assert sum(c['count'] for c in cards) == len(block['positions'])
    assert abs(sum(c['revenue_share_percent'] for c in cards) - 100.0) < 1e-6
    for card in cards:
        assert card['rule'] and card['hint'] and card['action']


def test_combined_code_is_revenue_markup_demand():
    """Трёхбуквенный код — выручка, наценка, спрос. Маржа отдельным полем."""
    _, block = build_total()
    for item in block['positions'][:50]:
        expected = '{}{}{}'.format(
            item['ABC_Revenue'],
            item['ABC_Markup'] or '?',
            item['XYZ_Category'] or '?',
        )
        assert item['ABC_Combined'] == expected, item['ABC_Combined']
        assert item['ABC_Margin'] in ('A', 'B', 'C'), 'маржа должна оставаться полем'


# ==================== разрезы и край ====================

def test_bar_scope_is_labelled_and_filtered():
    """Разрез одного бара помечен в ответе и не содержит чужих строк."""
    rows = [
        row('Бар А', 'Пиво А', '2026-01-05', 5, 500, 200),
        row('Бар Б', 'Пиво Б', '2026-01-05', 5, 500, 200),
    ]
    block = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build('Бар А')
    assert block['scope'] == 'bar'
    assert block['bar_label'] == 'Бар А'
    assert [p['Beer'] for p in block['positions']] == ['Пиво А']
    total = PackagingAnalysis(rows, '2026-01-05', '2026-02-01').build(None)
    assert total['scope'] == 'total'
    assert total['bar_label'] == 'Общая'
    assert total['bars_in_scope'] == ['Бар А', 'Бар Б']


def test_empty_rows_do_not_crash():
    """Пустой ответ iiko не роняет расчёт и не выдумывает итогов."""
    block = PackagingAnalysis([], '2026-01-05', '2026-02-01').build(None)
    assert block['positions'] == []
    assert block['categories'] == []
    assert block['totals']['revenue'] == 0
    assert block['totals']['markup_percent'] is None


def test_deterministic_between_runs():
    """Одни и те же данные дают один и тот же ответ.

    Требование .claude/CLAUDE.md пункт 1. Сортировки с тай-брейком по имени
    нужны именно для этого: без них позиции с равной выручкой меняли буквы от
    запуска к запуску.
    """
    rows = load_rows()
    date_from, date_to = fixture_period(rows)
    first = PackagingAnalysis(rows, date_from, date_to).build(None)
    second = PackagingAnalysis(rows, date_from, date_to).build(None)
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
        json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_response_is_json_serialisable():
    """Ответ уходит через jsonify — в нём не должно быть несериализуемых типов."""
    _, block = build_total()
    json.dumps(block, ensure_ascii=False)


if __name__ == '__main__':
    print('ABC/XYZ фасовки — расчёт\n')
    _run('«Общая» не теряет ни рубля сырых строк', test_total_keeps_every_rouble)
    _run('«Общая» равна сумме разрезов по барам', test_total_equals_sum_of_bars)
    _run('позиции и категории складываются в итог', test_positions_and_categories_reconcile)
    _run('счётчик позиций в категории — уникальные фасовки', test_beers_count_is_unique_positions)
    _run('показаны все категории, включая «Без категории (Ф)»', test_all_categories_present)
    _run('категории отсортированы, накопленный доходит до 100%',
         test_categories_sorted_and_cumulative_reaches_100)
    _run('наценка сети взвешенная, а не максимум по барам', test_markup_is_weighted_not_max)
    _run('без себестоимости наценки нет, а не C', test_markup_undefined_when_no_cost)
    _run('порог наценки 120% включающий', test_markup_threshold_boundary)
    _run('себестоимость единицы от сумм, а не максимум', test_cost_per_unit_is_average_not_max)
    _run('XYZ меряет недели, а не разброс между барами', test_xyz_measures_weeks_not_bars)
    _run('разовая продажа буквы XYZ не получает', test_single_sale_gets_no_letter)
    _run('на коротком периоде XYZ не считается ни у кого', test_short_period_has_no_xyz_at_all)
    _run('границы XYZ включающие', test_xyz_thresholds_match_documented_bounds)
    _run('недельное окно прижато к концу периода', test_week_window_is_anchored_to_the_end)
    _run('продажи вне окна попадают в итог и помечены',
         test_sales_outside_window_are_counted_and_flagged)
    _run('базы долей отдаются, формула воспроизводится',
         test_abc_bases_are_reported_so_the_formula_reproduces)
    _run('категория и страна выбираются по выручке', test_category_and_country_follow_the_money)
    _run('порядок баров детерминирован', test_by_bar_order_is_deterministic)
    _run('перевёрнутый период отвергается', test_inverted_period_is_rejected)
    _run('недельный ряд отдаётся целиком', test_weekly_series_covers_whole_period)
    _run('первая буква следует Парето', test_abc_revenue_follows_pareto)
    _run('доминирующая позиция всегда A', test_dominant_position_is_always_a)
    _run('обе шкалы буквы по выручке приезжают в ответ', test_two_abc_scales_are_both_reported)
    _run('группы решений по правилам, все позиции покрыты', test_bucket_decisions_follow_rules_and_cover_everything)
    _run('код — выручка, наценка, спрос', test_combined_code_is_revenue_markup_demand)
    _run('разрез бара помечен и отфильтрован', test_bar_scope_is_labelled_and_filtered)
    _run('пустой ответ не роняет расчёт', test_empty_rows_do_not_crash)
    _run('расчёт детерминирован', test_deterministic_between_runs)
    _run('ответ сериализуется в JSON', test_response_is_json_serialisable)
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)

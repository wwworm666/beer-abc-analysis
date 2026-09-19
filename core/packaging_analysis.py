"""ABC/XYZ анализ фасовки: один расчёт на всю страницу /packaging.

Что это
-------
Считает ОДИН ответ для страницы: сводка, все категории (стили), все фасовки,
корзины действий. Разрез — либо один бар, либо «Общая» (все бары сведены в одну
сеть). Страница из этого ответа рисует все секции без дополнительных запросов,
так же как /draft из ответа /api/draft-kegs.

Почему не pandas
----------------
Прежний расчёт (core/abc_analysis.py + core/category_analysis.py + ветки в
routes/analysis.py) жил на pandas и накопил на этом четыре молчаливых дефекта:
`groupby` с умолчанием `dropna=True` выбрасывал позиции с незаполненным стилем
(15,3% выручки), `fillna(..., inplace=True)` на срезе перестал срабатывать на
pandas 3, агрегаты `'max'` подменяли сетевую наценку максимумом по барам, а
коэффициент вариации считался по строкам разных БАРОВ вместо недель. Здесь всё
на обычных словарях и списках: что написано, то и происходит, и результат не
зависит от версии pandas.

Сведение в «Общую»
------------------
Аддитивные величины (количество, выручка, себестоимость, маржа) складываются по
барам. Неаддитивные (наценка, себестоимость единицы, доли, буквы ABC/XYZ)
ПЕРЕСЧИТЫВАЮТСЯ от сумм и никогда не усредняются по барам — среднее коэффициентов
не равно коэффициенту суммы. Формулы: docs/abc-xyz-analysis.md.

Файлы
-----
- core/abc_thresholds.py — пороги и подписи
- core/abc_buckets.py — 6 корзин действий по паре (выручка, наценка)
- routes/analysis.py — эндпоинт /api/packaging
"""

from datetime import date, datetime

from core.abc_buckets import get_bucket_key
from core.abc_thresholds import (
    MIN_XYZ_WEEKS,
    TOTAL_LABEL,
    UNCATEGORIZED,
    WEEK_DAYS,
    abc_letter_by_cumulative,
    markup_letter,
    xyz_letter,
)


def _num(value):
    """Число из ответа OLAP: None и мусор -> 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_day(value):
    """'YYYY-MM-DD' -> date. None, если распознать нельзя."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    text = str(value)[:10].replace('.', '-')
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


def _text(value, fallback=''):
    """Строка без обрамляющих пробелов. Пустая строка и None -> fallback."""
    if value is None:
        return fallback
    cleaned = str(value).strip()
    return cleaned if cleaned else fallback


def _cv_percent(values):
    """Коэффициент вариации в процентах. None, если считать не на чем.

    Стандартное отклонение ВЫБОРОЧНОЕ (делитель n-1) — та же статистика, что на
    /draft, чтобы буквы двух страниц были сопоставимы.
    """
    points = [float(v) for v in values]
    if len(points) < 2:
        return None
    mean = sum(points) / len(points)
    if mean <= 0:
        return None
    variance = sum((p - mean) ** 2 for p in points) / (len(points) - 1)
    return (variance ** 0.5) / mean * 100


def _markup_share(revenue, cost):
    """Наценка как доля: (выручка - себестоимость) / себестоимость. 1.2 = 120%.

    None при нулевой или отрицательной себестоимости: позиция без оприходования
    или сторно. Раньше такие случаи молча получали букву C и уезжали в корзину
    «поднять наценку», хотя наценка у них просто не определена.
    """
    if cost is None or cost <= 0:
        return None
    return (revenue - cost) / cost


def _assign_abc_by_cumulative(rows, value_key, letter_key, share_key, cum_key, base=None):
    """Проставить букву ABC по накопленной доле значения value_key.

    rows меняются на месте. База — сумма ПОЛОЖИТЕЛЬНЫХ значений: возврат с
    отрицательной выручкой не должен увеличивать целое, долей которого он якобы
    является. Сортировка стабильная, тай-брейк по имени позиции, поэтому при
    одинаковых суммах порядок и буквы воспроизводятся от запуска к запуску.
    """
    total = base if base is not None else sum(max(_num(r.get(value_key)), 0.0) for r in rows)
    ordered = sorted(
        rows,
        key=lambda r: (-max(_num(r.get(value_key)), 0.0), _text(r.get('Beer') or r.get('Category'))),
    )
    cumulative = 0.0
    for row in ordered:
        value = max(_num(row.get(value_key)), 0.0)
        share = (value / total * 100) if total > 0 else 0.0
        # Буква — по накопленному ДО этой позиции, а сам cum_key показывает
        # накопленное ВМЕСТЕ с ней: в интерфейсе нужно именно второе, иначе
        # последняя строка таблицы не доходила бы до 100%.
        row[letter_key] = abc_letter_by_cumulative(cumulative) if total > 0 else 'C'
        cumulative += share
        row[share_key] = share
        row[cum_key] = min(cumulative, 100.0)
    return ordered


class PackagingAnalysis:
    """Расчёт страницы фасовки по сырым строкам OLAP-отчёта продаж.

    rows — список строк iiko (Store.Name, DishName, DishGroup.ThirdParent,
    DishForeignName, OpenDate.Typed, DishAmountInt, DishDiscountSumInt,
    ProductCostBase.ProductCost). Даты периода ВКЛЮЧИТЕЛЬНЫЕ.
    """

    def __init__(self, rows, date_from, date_to):
        self.rows = rows or []
        self.date_from = _parse_day(date_from)
        self.date_to = _parse_day(date_to)
        if not self.date_from or not self.date_to:
            raise ValueError('date_from/date_to обязательны и должны быть YYYY-MM-DD')
        self.period_days = (self.date_to - self.date_from).days + 1
        # Полных 7-дневных корзин в периоде — база для XYZ. Хвост короче недели
        # в расчёт не идёт: неполная неделя даёт заниженный объём и фиктивный
        # разброс, из-за которого ровная позиция получала бы Z.
        self.weeks_in_period = self.period_days // WEEK_DAYS

    # ---------- недельные корзины ----------

    def _bucket_index(self, day):
        """Номер 7-дневной корзины от начала периода. None — вне периода или хвост."""
        if not day:
            return None
        offset = (day - self.date_from).days
        if offset < 0:
            return None
        index = offset // WEEK_DAYS
        return index if index < self.weeks_in_period else None

    # ---------- сбор ----------

    def _collect(self, bar_name):
        """Свернуть строки OLAP в позиции разреза.

        Ключ позиции — название фасовки (DishName). В разрезе «Общая» бары
        складываются в одну позицию, поэтому ключ НЕ включает бар: иначе одно и
        то же пиво заняло бы в списке четыре строки, а доли считались бы от
        завышенной базы.
        """
        positions = {}
        for row in self.rows:
            bar = _text(row.get('Store.Name'))
            if bar_name and bar != bar_name:
                continue
            name = _text(row.get('DishName'))
            if not name:
                continue

            item = positions.get(name)
            if item is None:
                item = {
                    'Beer': name,
                    # Пустой стиль получает подпись, а не None: иначе позиция
                    # выпадала из группировки и терялась из анализа целиком.
                    'Category': _text(row.get('DishGroup.ThirdParent'), UNCATEGORIZED),
                    'Country': _text(row.get('DishForeignName'), '—'),
                    'TotalQty': 0.0,
                    'TotalRevenue': 0.0,
                    'TotalCost': 0.0,
                    '_weeks': {},
                    '_bars': {},
                }
                positions[name] = item

            qty = _num(row.get('DishAmountInt'))
            revenue = _num(row.get('DishDiscountSumInt'))
            cost = _num(row.get('ProductCostBase.ProductCost'))

            item['TotalQty'] += qty
            item['TotalRevenue'] += revenue
            item['TotalCost'] += cost

            bucket = self._bucket_index(_parse_day(row.get('OpenDate.Typed')))
            if bucket is not None:
                item['_weeks'][bucket] = item['_weeks'].get(bucket, 0.0) + qty

            by_bar = item['_bars'].get(bar)
            if by_bar is None:
                by_bar = {'Bar': bar, 'Qty': 0.0, 'Revenue': 0.0, 'Cost': 0.0}
                item['_bars'][bar] = by_bar
            by_bar['Qty'] += qty
            by_bar['Revenue'] += revenue
            by_bar['Cost'] += cost

        return positions

    # ---------- XYZ ----------

    def _apply_xyz(self, item):
        """Проставить XYZ по недельным продажам позиции.

        Что именно измеряем: насколько ровно позиция продавалась В ТЕ НЕДЕЛИ,
        КОГДА ОНА БЫЛА В ПРОДАЖЕ. Недели без продаж в расчёт не берутся, и это
        та же методика, что на /draft, по той же причине: фасовка ротируется
        ещё сильнее разлива (450 SKU за месяц, у большинства единичные продажи),
        и если считать пустые недели нулями, «нестабильный спрос» получает
        вообще всё — на живых данных при нулевом заполнении 80% ассортимента
        уезжало в Z, и буква переставала что-либо различать.

        Буква не выдумывается. Нужно минимум MIN_XYZ_WEEKS недель С ПРОДАЖАМИ,
        иначе категории нет — прочерк, а не Z. Это и чинит главный дефект
        прежнего расчёта: позиция, проданная один раз, получала CV = 0% и букву
        X, то есть «идеально стабильный спрос». Теперь она не получает буквы
        вовсе, а длительность присутствия видна отдельными полями
        WeeksWithSales и WeeksInPeriod.
        """
        weeks = item.pop('_weeks', {})
        # Ряд по всем неделям периода — для столбиков в карточке. Показать
        # пустые недели важно: именно они объясняют, почему буквы может не быть.
        item['WeeklyQty'] = [weeks.get(index, 0.0) for index in range(self.weeks_in_period)]
        active = [value for value in weeks.values() if value > 0]
        item['WeeksWithSales'] = len(active)
        item['WeeksInPeriod'] = self.weeks_in_period
        item['XYZ_Category'] = None
        item['CoefficientOfVariation'] = None

        if self.weeks_in_period < MIN_XYZ_WEEKS:
            item['XYZ_Reason'] = 'period'
            return
        if len(active) < MIN_XYZ_WEEKS:
            item['XYZ_Reason'] = 'weeks'
            return

        cv = _cv_percent(active)
        if cv is None:
            item['XYZ_Reason'] = 'no_sales'
            return

        item['CoefficientOfVariation'] = cv
        item['XYZ_Category'] = xyz_letter(cv)
        item['XYZ_Reason'] = ''

    # ---------- сборка ответа ----------

    def build(self, bar_name=None):
        """Собрать блок ответа для разреза.

        bar_name=None или '' — сведение всех баров в «Общую».
        """
        positions = self._collect(bar_name)

        for item in positions.values():
            item['TotalMargin'] = item['TotalRevenue'] - item['TotalCost']
            item['MarkupPercent'] = self._as_percent(
                _markup_share(item['TotalRevenue'], item['TotalCost'])
            )
            item['CostPerUnit'] = (
                item['TotalCost'] / item['TotalQty'] if item['TotalQty'] > 0 else 0.0
            )
            item['PricePerUnit'] = (
                item['TotalRevenue'] / item['TotalQty'] if item['TotalQty'] > 0 else 0.0
            )
            self._apply_xyz(item)

            bars = sorted(item.pop('_bars').values(), key=lambda b: -b['Revenue'])
            for entry in bars:
                entry['Margin'] = entry['Revenue'] - entry['Cost']
                entry['SharePercent'] = (
                    entry['Revenue'] / item['TotalRevenue'] * 100
                    if item['TotalRevenue'] > 0 else 0.0
                )
            item['ByBar'] = bars
            item['BarsPresent'] = len(bars)

        rows = list(positions.values())

        # Первая буква — по всему ассортименту разреза.
        _assign_abc_by_cumulative(
            rows, 'TotalRevenue', 'ABC_Revenue', 'RevenueSharePercent', 'RevenueCumulativePercent'
        )
        # Отдельное поле для сортировки: маржа в рублях. В трёхбуквенный код не
        # входит — там третья буква это XYZ, спрос.
        _assign_abc_by_cumulative(
            rows, 'TotalMargin', 'ABC_Margin', 'MarginSharePercent', 'MarginCumulativePercent'
        )

        for item in rows:
            item['ABC_Markup'] = markup_letter(
                _markup_share(item['TotalRevenue'], item['TotalCost'])
            )
            item['ABC_Bucket'] = (
                get_bucket_key(item['ABC_Revenue'], item['ABC_Markup'])
                if item['ABC_Markup'] else None
            )
            item['ABC_Combined'] = '{}{}{}'.format(
                item['ABC_Revenue'],
                item['ABC_Markup'] or '?',
                item['XYZ_Category'] or '?',
            )

        categories = self._build_categories(rows)
        # Вторая шкала первой буквы: место позиции ВНУТРИ своей категории.
        # Обе базы верные, но разные, и на одном экране под одинаковым значком
        # A/B/C они расходились у каждой пятой позиции. Теперь обе посчитаны
        # явно и подписаны в карточке.
        for category in categories:
            members = [r for r in rows if r['Category'] == category['Category']]
            _assign_abc_by_cumulative(
                members, 'TotalRevenue', 'ABC_Revenue_InCategory',
                'RevenueShareInCategoryPercent', 'RevenueCumulativeInCategoryPercent',
            )

        rows.sort(key=lambda r: (-r['TotalRevenue'], r['Beer']))
        for index, item in enumerate(rows):
            item['Id'] = index

        for category in categories:
            category['PositionIds'] = [r['Id'] for r in rows if r['Category'] == category['Category']]

        return {
            'scope': 'bar' if bar_name else 'total',
            'bar_label': bar_name or TOTAL_LABEL,
            'bars_in_scope': self._bars_in_scope(rows),
            'period': {
                'from': self.date_from.isoformat(),
                'to': self.date_to.isoformat(),
                'days': self.period_days,
                'weeks': self.weeks_in_period,
            },
            'totals': self._build_totals(rows, categories),
            'bucket_stats': self._count(rows, 'ABC_Bucket'),
            'abc_stats': self._count(rows, 'ABC_Combined'),
            'xyz_stats': self._count(rows, 'XYZ_Category'),
            'categories': categories,
            'positions': rows,
            'xyz_available': self.weeks_in_period >= MIN_XYZ_WEEKS,
            'min_xyz_weeks': MIN_XYZ_WEEKS,
        }

    # ---------- части ответа ----------

    @staticmethod
    def _as_percent(share):
        """Долю (1.2) в проценты (120.0). None остаётся None."""
        return None if share is None else share * 100

    @staticmethod
    def _count(rows, key):
        """Сколько позиций в каждом значении поля. None-значения не считаем."""
        stats = {}
        for row in rows:
            value = row.get(key)
            if not value:
                continue
            stats[value] = stats.get(value, 0) + 1
        return stats

    @staticmethod
    def _bars_in_scope(rows):
        """Бары, встретившиеся в разрезе — по алфавиту, для подписи сводки."""
        bars = set()
        for row in rows:
            for entry in row['ByBar']:
                bars.add(entry['Bar'])
        return sorted(bars)

    def _build_categories(self, rows):
        """Сводка по ВСЕМ категориям разреза, без урезаний.

        Категорий столько, сколько встретилось в данных: страница показывает их
        все. Раньше сервер отдавал все, а страница рисовала первые десять, и на
        одном экране таблица и карточки говорили разное.
        """
        buckets = {}
        for row in rows:
            name = row['Category']
            entry = buckets.get(name)
            if entry is None:
                entry = {
                    'Category': name,
                    'BeersCount': 0,
                    'TotalQty': 0.0,
                    'TotalRevenue': 0.0,
                    'TotalCost': 0.0,
                    'abc_stats': {},
                    'xyz_stats': {},
                    'bucket_stats': {},
                }
                buckets[name] = entry
            # Уникальные фасовки, а не строки: в сетевом разрезе позиция уже
            # сведена по барам, поэтому счётчик совпадает с длиной списка.
            entry['BeersCount'] += 1
            entry['TotalQty'] += row['TotalQty']
            entry['TotalRevenue'] += row['TotalRevenue']
            entry['TotalCost'] += row['TotalCost']
            for field, stat in (('ABC_Combined', 'abc_stats'),
                                ('XYZ_Category', 'xyz_stats'),
                                ('ABC_Bucket', 'bucket_stats')):
                value = row.get(field)
                if value:
                    entry[stat][value] = entry[stat].get(value, 0) + 1

        categories = list(buckets.values())
        for entry in categories:
            entry['TotalMargin'] = entry['TotalRevenue'] - entry['TotalCost']
            # Наценка категории — от сумм, а не среднее наценок позиций: среднее
            # даёт вес дешёвой позиции наравне с флагманом и меняло букву.
            entry['MarkupPercent'] = self._as_percent(
                _markup_share(entry['TotalRevenue'], entry['TotalCost'])
            )
            entry['ABC_Markup'] = markup_letter(
                _markup_share(entry['TotalRevenue'], entry['TotalCost'])
            )

        _assign_abc_by_cumulative(
            categories, 'TotalRevenue', 'ABC_Category',
            'RevenueSharePercent', 'CumulativePercent',
        )
        categories.sort(key=lambda c: (-c['TotalRevenue'], c['Category']))
        return categories

    def _build_totals(self, rows, categories):
        """Итоги разреза. Считаются от тех же строк, что показаны в таблицах."""
        revenue = sum(r['TotalRevenue'] for r in rows)
        cost = sum(r['TotalCost'] for r in rows)
        qty = sum(r['TotalQty'] for r in rows)
        return {
            'revenue': revenue,
            'cost': cost,
            'margin': revenue - cost,
            'qty': qty,
            'markup_percent': self._as_percent(_markup_share(revenue, cost)),
            'sku': len(rows),
            'categories': len(categories),
            'price_per_unit': revenue / qty if qty > 0 else 0.0,
        }

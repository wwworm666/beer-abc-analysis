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
- core/abc_buckets.py — решения по ассортименту (6 групп с защитой от малых выборок)
- routes/analysis.py — эндпоинт /api/packaging
"""

from datetime import date, datetime, timedelta

from core.abc_buckets import bucket_cards, decide_bucket
from core.packaging_losses import build_losses_block
from core.abc_thresholds import (
    MIN_XYZ_WEEKS,
    TOTAL_LABEL,
    UNCATEGORIZED,
    WEEK_DAYS,
    abc_code,
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


def _pick_by_revenue(weighted, fallback):
    """Вариант с наибольшей выручкой; при равенстве — первый по алфавиту.

    weighted: {значение: выручка}. Пустой словарь -> fallback.
    """
    if not weighted:
        return fallback
    return sorted(weighted.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


def _assign_abc_by_cumulative(rows, value_key, letter_key, share_key, cum_key, base=None):
    """Проставить букву ABC по накопленной доле значения value_key.

    rows меняются на месте. ВОЗВРАЩАЕТ базу, от которой считались доли — она
    нужна интерфейсу: карточка печатает формулу с подстановкой чисел, и если
    показать в знаменателе другое число, деление не даст написанного результата.

    База — сумма ПОЛОЖИТЕЛЬНЫХ значений: возврат с отрицательной выручкой не
    должен увеличивать целое, долей которого он якобы является. Именно поэтому
    база НЕ равна `totals.revenue` / `totals.margin`, где отрицательные значения
    учтены, и подставлять их в формулу нельзя.

    Сортировка стабильная, тай-брейк по имени позиции, поэтому при одинаковых
    суммах порядок и буквы воспроизводятся от запуска к запуску.
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
    return total


class PackagingAnalysis:
    """Расчёт страницы фасовки по сырым строкам OLAP-отчёта продаж.

    rows — список строк iiko (Store.Name, DishName, DishGroup.ThirdParent,
    DishForeignName, OpenDate.Typed, DishAmountInt, DishDiscountSumInt,
    ProductCostBase.ProductCost). Даты периода ВКЛЮЧИТЕЛЬНЫЕ.
    """

    def __init__(self, rows, date_from, date_to, transactions=None):
        self.rows = rows or []
        # Проводки склада (OLAP TRANSACTIONS по «Напитки Фасовка») — для баланса
        # и потерь. Необязательны: без них блок losses состоит из нулей, а
        # таблицы и буквы считаются как раньше.
        self.transactions = transactions or []
        self.date_from = _parse_day(date_from)
        self.date_to = _parse_day(date_to)
        if not self.date_from or not self.date_to:
            raise ValueError('date_from/date_to обязательны и должны быть YYYY-MM-DD')
        if self.date_from > self.date_to:
            # Иначе период уходит в ответ отрицательным, а недель в нём «минус
            # две»: страница показывает бессмыслицу вместо ошибки.
            raise ValueError('date_from позже date_to')
        self.period_days = (self.date_to - self.date_from).days + 1
        # Полных 7-дневных корзин в периоде — база для XYZ. Хвост короче недели
        # в расчёт не идёт: неполная неделя даёт заниженный объём и фиктивный
        # разброс, из-за которого ровная позиция получала бы Z.
        self.weeks_in_period = self.period_days // WEEK_DAYS
        # Окно недель прижато к КОНЦУ периода, а не к началу. Ни один пресет
        # страницы не делится на 7 нацело (30 дней = 4 недели + 2 дня, 90 = 12 + 6,
        # 180 = 25 + 5), поэтому неполный кусок неизбежен — вопрос только в том,
        # какой. При якоре к началу за бортом оставались САМЫЕ СВЕЖИЕ дни, и
        # позиция, заведённая на последней неделе, получала «продавалась 0 недель
        # из 4» и график из нулей рядом со своей же выручкой. XYZ отвечает на
        # вопрос «насколько ровен спрос СЕЙЧАС», поэтому окно держится за конец
        # периода, а отбрасываются самые старые дни.
        #
        # Выбор якоря не отменяет того, что часть продаж остаётся вне окна.
        # Поэтому границы окна уходят в ответ (period.weeks_from/weeks_to), а у
        # позиции есть QtyOutsideWeeks — страница обязана сказать об этом вслух,
        # а не печатать голый ноль.
        if self.weeks_in_period:
            self.weeks_to = self.date_to
            self.weeks_from = self.date_to - timedelta(
                days=self.weeks_in_period * WEEK_DAYS - 1
            )
        else:
            self.weeks_from = None
            self.weeks_to = None

    # ---------- недельные корзины ----------

    def _bucket_index(self, day):
        """Номер 7-дневной корзины внутри недельного окна. None — вне окна."""
        if not day or not self.weeks_from:
            return None
        offset = (day - self.weeks_from).days
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
                    'TotalQty': 0.0,
                    'TotalRevenue': 0.0,
                    'TotalCost': 0.0,
                    '_weeks': {},
                    '_bars': {},
                    # Стиль и страна копятся с выручкой, а не берутся из первой
                    # встреченной строки: позицию могли переклассифицировать в
                    # номенклатуре внутри периода, и тогда «первая строка» —
                    # это просто порядок выгрузки OLAP, то есть результат
                    # зависел бы от того, как iiko отсортировал ответ.
                    '_categories': {},
                    '_countries': {},
                    # GUID блюда из продаж (DishId) — связка с проводками склада.
                    # Копится с выручкой по тому же правилу, что стиль и страна.
                    '_ids': {},
                }
                positions[name] = item

            qty = _num(row.get('DishAmountInt'))
            revenue = _num(row.get('DishDiscountSumInt'))
            cost = _num(row.get('ProductCostBase.ProductCost'))

            # Пустой стиль получает подпись, а не None: иначе позиция выпадала
            # из группировки и терялась из анализа целиком.
            category = _text(row.get('DishGroup.ThirdParent'), UNCATEGORIZED)
            item['_categories'][category] = item['_categories'].get(category, 0.0) + revenue
            country = _text(row.get('DishForeignName'))
            if country:
                item['_countries'][country] = item['_countries'].get(country, 0.0) + revenue
            dish_id = _text(row.get('DishId'))
            if dish_id:
                item['_ids'][dish_id] = item['_ids'].get(dish_id, 0.0) + revenue

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
        вообще всё: на живых данных при нулевом заполнении букву получили бы 438
        позиций из 450, и 414 из них (92% ассортимента) оказались бы в Z — буква
        перестала бы что-либо различать.

        Буква не выдумывается. Нужно минимум MIN_XYZ_WEEKS недель С ПРОДАЖАМИ,
        иначе категории нет — прочерк, а не Z. Это и чинит главный дефект
        прежнего расчёта: позиция, проданная один раз, получала CV = 0% и букву
        X, то есть «идеально стабильный спрос». Теперь она не получает буквы
        вовсе, а длительность присутствия видна отдельными полями
        WeeksWithSales и WeeksInPeriod.
        """
        weeks = item.pop('_weeks', {})
        # Ряд по всем неделям окна — для столбиков в карточке. Показать пустые
        # недели важно: именно они объясняют, почему буквы может не быть.
        item['WeeklyQty'] = [weeks.get(index, 0.0) for index in range(self.weeks_in_period)]
        # Штуки, проданные в периоде, но ВНЕ недельного окна (хвост короче
        # недели). Без этого поля страница печатала бы «0 недель с продажами»
        # у позиции, чья выручка показана строкой выше, и выглядела бы сломанной.
        item['QtyOutsideWeeks'] = item['TotalQty'] - sum(item['WeeklyQty'])
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
            # Побеждает вариант с наибольшей выручкой, при равенстве — первый по
            # алфавиту. Детерминировано и осмысленно: позиция числится там, где
            # на неё пришлись деньги, а не там, куда её случайно записали одной
            # строкой.
            item['Category'] = _pick_by_revenue(item.pop('_categories'), UNCATEGORIZED)
            item['Country'] = _pick_by_revenue(item.pop('_countries'), '—')
            ids = item.pop('_ids')
            item['DishId'] = _pick_by_revenue(ids, None)
            # Все GUID, встреченные под этим названием (перезаведённая карточка
            # даёт второй) — чтобы проводки по любому из них нашли позицию.
            item['DishIds'] = sorted(ids)
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

            # Тай-брейк по имени бара: без него порядок при равной выручке
            # определялся порядком строк OLAP и мог меняться между запусками.
            bars = sorted(item.pop('_bars').values(), key=lambda b: (-b['Revenue'], b['Bar']))
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
        revenue_base = _assign_abc_by_cumulative(
            rows, 'TotalRevenue', 'ABC_Revenue', 'RevenueSharePercent', 'RevenueCumulativePercent'
        )
        # Отдельное поле для сортировки: маржа в рублях. В трёхбуквенный код не
        # входит — там третья буква это XYZ, спрос.
        margin_base = _assign_abc_by_cumulative(
            rows, 'TotalMargin', 'ABC_Margin', 'MarginSharePercent', 'MarginCumulativePercent'
        )

        for item in rows:
            item['ABC_Markup'] = markup_letter(
                _markup_share(item['TotalRevenue'], item['TotalCost'])
            )
            # Группа решения — по правилам с защитой от малых выборок, а не по
            # паре букв: см. core/abc_buckets.py. Без себестоимости — «сверить
            # учёт», а не пропуск: раньше такие позиции не попадали никуда.
            item['ABC_Bucket'] = decide_bucket(
                item['ABC_Revenue'],
                _markup_share(item['TotalRevenue'], item['TotalCost']),
                item['TotalQty'],
                item['WeeksInPeriod'],
                item['WeeklyQty'],
                item['QtyOutsideWeeks'],
            )
            # Код один на обе страницы: core/abc_thresholds.py, abc_code.
            item['ABC_Combined'] = abc_code(
                item['ABC_Revenue'], item['ABC_Markup'], item['XYZ_Category'],
            )

        categories = self._build_categories(rows)
        total_qty = sum(r['TotalQty'] for r in rows)
        self._assign_qty_share(rows, total_qty)
        self._assign_qty_share(categories, total_qty)
        # Вторая шкала первой буквы: место позиции ВНУТРИ своей категории.
        # Обе базы верные, но разные, и на одном экране под одинаковым значком
        # A/B/C они расходились у каждой пятой позиции. Теперь обе посчитаны
        # явно и подписаны в карточке.
        for category in categories:
            members = [r for r in rows if r['Category'] == category['Category']]
            base = _assign_abc_by_cumulative(
                members, 'TotalRevenue', 'ABC_Revenue_InCategory',
                'RevenueShareInCategoryPercent', 'RevenueCumulativeInCategoryPercent',
            )
            category['RevenueAbcBase'] = base
            for member in members:
                member['RevenueBaseInCategory'] = base

        rows.sort(key=lambda r: (-r['TotalRevenue'], r['Beer']))
        for index, item in enumerate(rows):
            item['Id'] = index

        for category in categories:
            category['PositionIds'] = [r['Id'] for r in rows if r['Category'] == category['Category']]

        totals = self._build_totals(rows, categories, revenue_base, margin_base)
        # Баланс и потери по проводкам склада; заодно проставляет позициям поля
        # движений (SoldQtyStock, WriteoffQty, InventoryNetQty, LossQty).
        losses = build_losses_block(self.transactions, bar_name, rows, totals['qty'])

        return {
            'scope': 'bar' if bar_name else 'total',
            'bar_label': bar_name or TOTAL_LABEL,
            'bars_in_scope': self._bars_in_scope(rows),
            'period': {
                'from': self.date_from.isoformat(),
                'to': self.date_to.isoformat(),
                'days': self.period_days,
                'weeks': self.weeks_in_period,
                # Границы недельного окна: какие именно дни попали в XYZ.
                # Без них «30 дн. · 4 полные недели» читается как «весь период
                # покрыт», хотя два дня остались снаружи.
                'weeks_from': self.weeks_from.isoformat() if self.weeks_from else None,
                'weeks_to': self.weeks_to.isoformat() if self.weeks_to else None,
            },
            'totals': totals,
            'losses': losses,
            # Карточки решений: счётчики, доли и правила словами — с сервера.
            'buckets': bucket_cards(rows, self.period_days, 'pieces'),
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
    def _assign_qty_share(rows, total_qty):
        """Доля штук позиции или категории в штуках всего разреза.

        Та же формула, что доля литров на /draft: количество / сумма количеств
        разреза × 100. Считается от сумм, отдельно для позиций и для категорий.
        """
        for row in rows:
            qty = row.get('TotalQty') or 0.0
            row['QtySharePercent'] = (qty / total_qty * 100) if total_qty > 0 else 0.0

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

        # База долей категорий нужна карточке категории для формулы «выручка /
        # база = доля». Она НЕ равна базе позиций (revenue_abc_base): возврат,
        # ставший отдельной позицией, в базе позиций обнулён, а в категории он
        # уменьшает её выручку. Раньше карточка делила на базу позиций, и деление
        # не давало напечатанный процент.
        self.category_revenue_base = _assign_abc_by_cumulative(
            categories, 'TotalRevenue', 'ABC_Category',
            'RevenueSharePercent', 'CumulativePercent',
        )
        categories.sort(key=lambda c: (-c['TotalRevenue'], c['Category']))
        return categories

    def _build_totals(self, rows, categories, revenue_base, margin_base):
        """Итоги разреза. Считаются от тех же строк, что показаны в таблицах.

        revenue_base / margin_base — базы, от которых считались доли ABC (суммы
        только ПОЛОЖИТЕЛЬНЫХ значений). Они отдаются отдельно от revenue/margin
        именно потому, что при наличии возвратов это разные числа, а карточка
        печатает формулу с подстановкой: в знаменателе должна стоять та база,
        от которой доля действительно посчитана.
        """
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
            'revenue_abc_base': revenue_base,
            'margin_abc_base': margin_base,
            'category_revenue_abc_base': getattr(self, 'category_revenue_base', 0.0),
        }

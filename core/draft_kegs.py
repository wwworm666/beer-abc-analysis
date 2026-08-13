# -*- coding: utf-8 -*-
"""Проливы разливного по кегам: литры из проводок iiko, деньги из отчёта по продажам.

Зачем модуль
------------
Старый расчёт (core/draft_analysis.py) получал литры перемножением количества порций на
объём, вытащенный регексом из названия блюда («ФестХаус Хеллес (0,5)» -> 0,5 л). Здесь
литры берутся оттуда, где их считает сам iiko: проводка списания кега по техкарте при
продаже. Сверка на живых данных 2026-08-13 показала совпадение обоих способов
(755,61 л за неделю 04-10.08, по каждому бару отдельно; 0,019% расхождения на 3,5 месяцах),
поэтому переход не меняет цифру, но убирает зависимость от дисциплины названий.

Строка расчёта = КЕГ (товар со склада), а не сорт по названию блюда. За 3,5 месяца в базе
74 сорта против 75 кегов, то есть таблица по составу строк остаётся прежней, но ключ теперь
тот же объект, который закупается и инвентаризуется.

Формулы (все — от сумм, без средних по средним)
----------------------------------------------
    Литры продано          = сумма Amount.Out проводок SESSION_WRITEOFF (ЕИ «л»)
    Литры списано актами    = сумма Amount.Out проводок WRITEOFF
    Недостача инвентаризации = сумма Amount.Out минус Amount.In проводок INVENTORY_CORRECTION
    Приход                  = сумма Amount.In проводок INVOICE
    Баланс кега             = приход + перемещения(приход) - продано - списано
                              - недостача - перемещения(расход)
    Доля по литрам, %       = литры позиции / литры всех позиций разреза * 100
    Выручка, себестоимость  = суммы из продаж, отнесённые к кегу через техкарту
    Наценка, %              = (выручка - себестоимость) / себестоимость * 100
    Маржа                   = выручка - себестоимость
    Цена за литр            = выручка / литры
    Средний объём порции    = литры / порции
    Литров в неделю         = литры / (дней в периоде / 7)
    CV (для XYZ)            = стандартное отклонение / среднее по неделям, В КОТОРЫЕ БЫЛИ
                              продажи, * 100; недели считаются 7-дневными окнами от начала
                              периода, берутся только полные окна, нужно минимум 3 активных
    XYZ                     = X при CV <= 30%, Y при CV <= 60%, Z свыше; при меньше чем
                              3 активных неделях категория не присваивается

Разрез по барменам (вкладка «По барменам» той же страницы)
---------------------------------------------------------
Автора в проводках нет, поэтому литры на человека раскладываются из продаж и нормируются
на факт списания кега:

    объём порции         = норма закладки кега на 1 порцию из техкарты iiko
    raw(строка продажи)  = порций * объём порции
    factor(кег)          = литры кега по проводкам / сумма raw по этому кегу
    литры(строка)        = raw(строка) * factor(кег)

Отсюда сумма литров по барменам равна сумме по кегам — две вкладки не могут показать
разные литры за один период. Деньги делятся между кегами тем же _keg_shares, что и на
вкладке кегов, поэтому выручка тоже сходится.

Что здесь сознательно иначе, чем в старом расчёте (дефекты аудита 2026-08-13)
----------------------------------------------------------------------------
1. XYZ не выдумывается. Корзины — 7-дневные окна ОТ НАЧАЛА ПЕРИОДА, а не календарные
   недели; берутся только полные окна; при меньше чем 3 окнах категория не присваивается
   (раньше на периоде «прошлая неделя» у всех позиций CV выходил 100 и X/Y/Z раздавались
   по порядку сортировки).
2. Доля в выручке — своя доля позиции. Накопленный процент для порогов ABC отдаётся
   отдельным полем RevenueCumulativePercent и в подписи «% от выручки» не участвует.
3. Наценка — от сумм за период, а не среднее арифметическое построчных процентов
   (расхождение доходило до 44 п.п.).
4. Литров в неделю — по длине выбранного периода, а не по числу календарных недель,
   в которые он попал (7-дневный период, начавшийся не с понедельника, занижал вдвое).
5. CV считается по недельным итогам разреза; разброс между барами в него не попадает.
6. Порции не обрезаются до целого: DishAmountInt у розлива бывает дробным.

Файлы
-----
core/olap_reports.py — get_draft_writeoff_report (проводки), get_draft_sales_by_dish
(продажи с DishId), get_dish_ingredient_map (техкарты, связка блюдо->кег по GUID).
routes/analysis.py — эндпоинт /api/draft-kegs. templates/draft.html — страница.
"""

from datetime import date, datetime, timedelta


LITER_UNIT = 'л'

# Типы проводок iiko, проверены на живых данных (docs/draft.md).
TT_SOLD = 'SESSION_WRITEOFF'        # списание кега при продаже через кассу
TT_WRITEOFF = 'WRITEOFF'            # акты списания (в т.ч. «удалено со списанием»)
TT_INVENTORY = 'INVENTORY_CORRECTION'  # расхождения инвентаризаций
TT_INVOICE = 'INVOICE'              # приход по накладным
TT_TRANSFER = 'TRANSFER'            # перемещения между барами

WEEK_DAYS = 7

# Подпись строки, когда в продаже не указан автор (AuthUser пуст). Такие строки НЕ
# выбрасываются: их литры есть в проводках, и без строки сумма по барменам разошлась бы
# с суммой по кегам.
UNKNOWN_BARTENDER = 'Не указан'

# Минимум недель с продажами, при котором вообще имеет смысл говорить о стабильности.
# На двух точках коэффициент вариации формально считается, но ничего не означает.
MIN_XYZ_WEEKS = 3

# Границы XYZ по коэффициенту вариации недельных проливов, в процентах.
# Пороги АБСОЛЮТНЫЕ, а не перцентильные: при перцентилях позиция с идеально ровными
# продажами получала Z только потому, что рядом кто-то ровнее, а единственная позиция
# в разрезе — всегда Z. Значения выведены из живых данных за 14 недель (2026-05-01..08-12,
# 57 кегов с 3+ активными неделями): CV от 10% до 102%, медиана 56%, у флагмана
# «ФестХаус Хеллес» 13%, у ротационного хвоста 90-102%. Порог 30/60 даёт X=14%, Y=51%,
# Z=35% позиций и читается словами: до 30% — недельный объём предсказуем, свыше 60% —
# может отличаться больше чем в полтора раза.
XYZ_X_MAX_CV = 30.0
XYZ_Y_MAX_CV = 60.0


def _num(value):
    """Число из ответа OLAP: None и мусор -> 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_day(value):
    """'YYYY-MM-DD' -> date. Возвращает None, если распознать нельзя."""
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


def _cv_percent(values):
    """Коэффициент вариации в процентах по выборке. None, если считать не на чем.

    Используется выборочное стандартное отклонение (делитель n-1) — та же
    статистика, что даёт pandas .std() в старом расчёте, чтобы числа между
    страницами были сопоставимы.
    """
    points = [float(v) for v in values]
    if len(points) < 2:
        return None
    mean = sum(points) / len(points)
    if mean <= 0:
        return None
    variance = sum((p - mean) ** 2 for p in points) / (len(points) - 1)
    return (variance ** 0.5) / mean * 100


def _abc_by_cumulative(rows, value_key, letter_key, cum_key):
    """ABC по накопленной доле: A до 80%, B до 95%, остальное C.

    Классический порог Парето. Строки сортируются по значению убыв., накопленный
    процент пишется в cum_key — он нужен и для буквы, и для прозрачности в UI.
    """
    total = sum(max(_num(r.get(value_key)), 0) for r in rows)
    ordered = sorted(rows, key=lambda r: _num(r.get(value_key)), reverse=True)
    cumulative = 0.0
    for row in ordered:
        cumulative += max(_num(row.get(value_key)), 0)
        percent = (cumulative / total * 100) if total > 0 else 0.0
        row[cum_key] = percent
        row[letter_key] = 'A' if percent <= 80 else ('B' if percent <= 95 else 'C')


def _abc_by_percentile(rows, value_key, letter_key):
    """ABC по перцентилям: верхняя треть A, средняя B, нижняя C.

    Для наценки и маржи порог Парето не подходит (это не доли целого), поэтому
    делим ранжированный список на три равные части. Позиции с неизвестным
    значением (None) получают C и в ранжировании не участвуют.
    """
    known = [r for r in rows if r.get(value_key) is not None]
    unknown = [r for r in rows if r.get(value_key) is None]
    for row in unknown:
        row[letter_key] = 'C'
    if not known:
        return
    ordered = sorted(known, key=lambda r: _num(r.get(value_key)), reverse=True)
    total = len(ordered)
    for index, row in enumerate(ordered):
        rank = (index + 1) / total * 100
        row[letter_key] = 'A' if rank <= 100 / 3 else ('B' if rank <= 200 / 3 else 'C')


class DraftKegAnalysis:
    """Свод проливов по кегам за период.

    transactions: строки get_draft_writeoff_report()['data']
    sales:        строки get_draft_sales_by_dish()['data']
    dish_map:     {dish_guid: [[ingredient_guid, amount], ...]} из get_dish_ingredient_map()
    date_from/date_to: границы ВЫБРАННОГО пользователем периода, обе ВКЛЮЧИТЕЛЬНО
                  (эксклюзивная граница нужна только запросам к iiko)
    """

    def __init__(self, transactions, sales, dish_map, date_from, date_to):
        self.transactions = transactions or []
        self.sales = sales or []
        self.dish_map = dish_map or {}
        self.date_from = _parse_day(date_from)
        self.date_to = _parse_day(date_to)
        if not self.date_from or not self.date_to:
            raise ValueError('date_from/date_to обязательны и должны быть YYYY-MM-DD')
        self.period_days = (self.date_to - self.date_from).days + 1
        # Полных 7-дневных корзин в периоде — база для XYZ.
        self.full_buckets = self.period_days // WEEK_DAYS
        self.unmapped_dishes = []   # блюда, которым не нашёлся кег: диагностика в ответе
        self.bartender_notes = {}   # как разложились литры по барменам: тоже диагностика
        self._keg_names = {}        # product_id -> название кега из проводок

    # ---------- разбор проводок ----------

    def _liter_rows(self):
        """Проводки только по кегам в литрах.

        Фильтр по группе «Напитки Розлив» уже стоит в запросе; здесь остаётся отсечь
        позиции в других единицах (в группе попадаются товары в шт) и служебные счета.
        Корреспондирующие счета («Расход продуктов», «Недостача инвентаризации»,
        «Задолженность перед поставщиками») отсекаются сами: в их строках и приход,
        и расход нулевые, поэтому в агрегаты они ничего не приносят.
        """
        for row in self.transactions:
            if row.get('Product.MeasureUnit') != LITER_UNIT:
                continue
            product_id = row.get('Product.Id')
            if not product_id:
                continue
            self._keg_names.setdefault(product_id, row.get('Product.Name') or product_id)
            yield row

    def _bucket_index(self, day):
        """Номер 7-дневной корзины от начала периода. None — день вне периода
        или попал в незавершённый хвост."""
        if not day:
            return None
        offset = (day - self.date_from).days
        if offset < 0:
            return None
        index = offset // WEEK_DAYS
        if index >= self.full_buckets:
            return None
        return index

    def collect_kegs(self, bar_name=None):
        """Агрегаты по кегам. Возвращает {(bar, keg_id): {...}}.

        bar_name сужает разрез до одного склада; None — все склады как есть
        (список баров не захардкожен, берётся из данных).
        """
        kegs = {}
        for row in self._liter_rows():
            bar = row.get('Account.Name')
            if bar_name and bar != bar_name:
                continue
            keg_id = row.get('Product.Id')
            entry = kegs.get((bar, keg_id))
            if entry is None:
                entry = kegs[(bar, keg_id)] = {
                    'bar': bar,
                    'keg_id': keg_id,
                    'keg_name': self._keg_names.get(keg_id, keg_id),
                    'sold': 0.0,
                    'writeoff': 0.0,
                    'inventory_out': 0.0,
                    'inventory_in': 0.0,
                    'invoice_in': 0.0,
                    'transfer_in': 0.0,
                    'transfer_out': 0.0,
                    'sold_cost': 0.0,
                    'buckets': {},
                }
            out = _num(row.get('Amount.Out'))
            inc = _num(row.get('Amount.In'))
            kind = row.get('TransactionType')

            if kind == TT_SOLD:
                entry['sold'] += out
                entry['sold_cost'] += _num(row.get('Sum.Outgoing'))
                bucket = self._bucket_index(_parse_day(row.get('DateTime.DateTyped')))
                if bucket is not None:
                    entry['buckets'][bucket] = entry['buckets'].get(bucket, 0.0) + out
            elif kind == TT_WRITEOFF:
                entry['writeoff'] += out
            elif kind == TT_INVENTORY:
                entry['inventory_out'] += out
                entry['inventory_in'] += inc
            elif kind == TT_INVOICE:
                entry['invoice_in'] += inc
            elif kind == TT_TRANSFER:
                entry['transfer_in'] += inc
                entry['transfer_out'] += out
        return kegs

    # ---------- разбор продаж ----------

    def _dish_to_kegs(self, keg_ids):
        """{dish_guid: [keg_guid, ...]} — только ингредиенты, которые реально кеги.

        Кег определяется не по названию и не по единице измерения из номенклатуры, а по
        участию в проводках разливного (keg_ids). Так связка не зависит от полноты
        номенклатуры и сама отбрасывает посуду из техкарты (ПЭТ-бутылки у литровых
        позиций «с собой»).
        """
        result = {}
        for dish_id, items in self.dish_map.items():
            found = []
            for item in items or []:
                if not item:
                    continue
                product_id = item[0] if isinstance(item, (list, tuple)) else item.get('productId')
                if product_id in keg_ids and product_id not in found:
                    found.append(product_id)
            if found:
                result[dish_id] = found
        return result

    def _keg_shares(self, kegs, bar, targets):
        """Как делить строку продажи между кегами: [(keg_id, доля), ...].

        Один кег к одному блюду — доля 1. Несколько (следствие смены техкарты внутри
        периода) — пропорционально литрам этих кегов в том же баре, а если литров нет,
        поровну. Общий делитель для денег и для литров по барменам: иначе на двух
        вкладках одна и та же продажа разошлась бы по кегам по-разному.
        """
        if len(targets) == 1:
            return [(targets[0], 1.0)]
        weights = [max(kegs.get((bar, keg_id), {}).get('sold', 0.0), 0.0)
                   for keg_id in targets]
        total_weight = sum(weights)
        if total_weight > 0:
            return [(keg_id, weight / total_weight)
                    for keg_id, weight in zip(targets, weights) if weight > 0]
        even = 1.0 / len(targets)
        return [(keg_id, even) for keg_id in targets]

    def collect_money(self, kegs, bar_name=None):
        """Разложить выручку/себестоимость/порции продаж по кегам.

        Одному кегу соответствует несколько блюд (размеры 0,25/0,4/0,5/1,0 и версии
        «с собой») — они складываются. Обратная ситуация в базе не встречается, но если
        блюдо ведёт на несколько кегов (следствие смены техкарты внутри периода), его
        деньги делятся между ними пропорционально литрам этих кегов в том же баре.
        """
        keg_ids = {keg_id for (_bar, keg_id) in kegs}
        dish_to_kegs = self._dish_to_kegs(keg_ids)
        unmapped = {}

        for row in self.sales:
            bar = row.get('Store.Name')
            if bar_name and bar != bar_name:
                continue
            dish_id = row.get('DishId')
            targets = dish_to_kegs.get(dish_id)
            revenue = _num(row.get('DishDiscountSumInt'))
            cost = _num(row.get('ProductCostBase.ProductCost'))
            portions = _num(row.get('DishAmountInt'))

            if not targets:
                # Блюдо продано, но кега для него нет: нет техкарты, либо кег не двигался
                # в периоде. Литры такого блюда в проводках всё равно отсутствуют,
                # поэтому деньги никуда не относим — только показываем в диагностике.
                name = row.get('DishName') or dish_id
                stat = unmapped.setdefault(name, {'DishName': name, 'Revenue': 0.0,
                                                  'Portions': 0.0})
                stat['Revenue'] += revenue
                stat['Portions'] += portions
                continue

            for keg_id, share in self._keg_shares(kegs, bar, targets):
                entry = kegs.get((bar, keg_id))
                if entry is None:
                    # Продажи есть, а движения кега на этом складе нет — так бывает,
                    # если списание попало в соседний учётный день на границе периода.
                    entry = kegs[(bar, keg_id)] = {
                        'bar': bar, 'keg_id': keg_id,
                        'keg_name': self._keg_names.get(keg_id, keg_id),
                        'sold': 0.0, 'writeoff': 0.0,
                        'inventory_out': 0.0, 'inventory_in': 0.0, 'invoice_in': 0.0,
                        'transfer_in': 0.0, 'transfer_out': 0.0, 'sold_cost': 0.0,
                        'buckets': {},
                    }
                entry['revenue'] = entry.get('revenue', 0.0) + revenue * share
                entry['cost'] = entry.get('cost', 0.0) + cost * share
                entry['portions'] = entry.get('portions', 0.0) + portions * share

        self.unmapped_dishes = sorted(unmapped.values(),
                                      key=lambda s: -s['Revenue'])
        return kegs

    # ---------- разрез по барменам ----------

    def _dish_volumes(self, keg_ids):
        """{(dish_guid, keg_guid): литров на порцию} из техкарт.

        Норма закладки кега на одну порцию блюда — то самое число, которым iiko считает
        списание. Берётся только для ингредиентов, которые реально кеги (keg_ids).
        """
        volumes = {}
        for dish_id, items in self.dish_map.items():
            for item in items or []:
                if not item:
                    continue
                if isinstance(item, (list, tuple)):
                    product_id = item[0]
                    amount = _num(item[1]) if len(item) > 1 else 0.0
                else:
                    product_id = item.get('productId')
                    amount = _num(item.get('amount'))
                if product_id not in keg_ids or amount <= 0:
                    continue
                key = (dish_id, product_id)
                volumes[key] = volumes.get(key, 0.0) + amount
        return volumes

    def collect_bartenders(self, kegs, bar_name=None):
        """Литры, порции и деньги по барменам. Возвращает список строк, готовых в JSON.

        Литры: в проводках автора нет (склад x кег x день x тип), поэтому объём порции
        берётся из техкарты, а результат НОРМИРУЕТСЯ на факт списания кега:

            raw(строка)   = порций * норма закладки кега на порцию
            factor(кег)   = литры кега по проводкам / сумма raw по этому кегу
            литры(строка) = raw(строка) * factor(кег)

        Нормировка нужна потому, что техкарта и факт списания расходятся: в документе
        может стоять коэффициент списания, техкарта могла смениться внутри периода,
        iiko округляет. Без неё сумма по барменам не совпала бы с суммой по кегам, и
        две вкладки одной страницы показывали бы разные литры за один период.

        Если ни у одного блюда кега нет нормы (например, у карты только строки размеров),
        литры кега делятся между барменами пропорционально порциям — это записывается
        в диагностику, а не прячется.

        Бармен — поле AuthUser («Авторизовал», кто пробил позицию). Пустое значение
        становится строкой UNKNOWN_BARTENDER и НЕ выбрасывается: выброшенные строки
        порвали бы тождество с литрами по кегам.
        """
        keg_ids = {keg_id for (_bar, keg_id) in kegs}
        dish_to_kegs = self._dish_to_kegs(keg_ids)
        volumes = self._dish_volumes(keg_ids)

        cells = {}          # (bar, keg_id, бармен) -> сырые литры, порции, деньги
        raw_by_keg = {}     # (bar, keg_id) -> сумма сырых литров
        portions_by_keg = {}
        no_volume = {}      # блюда, для которых нормы не нашлось

        for row in self.sales:
            bar = row.get('Store.Name')
            if bar_name and bar != bar_name:
                continue
            dish_id = row.get('DishId')
            targets = dish_to_kegs.get(dish_id)
            if not targets:
                # Блюдо без кега уже перечислено в unmapped_dishes (collect_money);
                # литров у него в проводках тоже нет, относить нечего.
                continue
            person = (row.get('AuthUser') or '').strip() or UNKNOWN_BARTENDER
            revenue = _num(row.get('DishDiscountSumInt'))
            cost = _num(row.get('ProductCostBase.ProductCost'))
            portions = _num(row.get('DishAmountInt'))

            for keg_id, share in self._keg_shares(kegs, bar, targets):
                volume = volumes.get((dish_id, keg_id), 0.0)
                keg_portions = portions * share
                raw = keg_portions * volume
                cell = cells.get((bar, keg_id, person))
                if cell is None:
                    cell = cells[(bar, keg_id, person)] = {
                        'raw': 0.0, 'portions': 0.0, 'revenue': 0.0, 'cost': 0.0,
                    }
                cell['raw'] += raw
                cell['portions'] += keg_portions
                cell['revenue'] += revenue * share
                cell['cost'] += cost * share
                raw_by_keg[(bar, keg_id)] = raw_by_keg.get((bar, keg_id), 0.0) + raw
                portions_by_keg[(bar, keg_id)] = (
                    portions_by_keg.get((bar, keg_id), 0.0) + keg_portions)
                if volume <= 0 and keg_portions > 0:
                    name = row.get('DishName') or dish_id
                    stat = no_volume.setdefault(name, {'DishName': name, 'Portions': 0.0})
                    stat['Portions'] += keg_portions

        # Нормировка на факт списания и раскладка по людям.
        people = {}
        kegs_scaled = 0
        max_deviation = 0.0
        assigned_liters = 0.0
        for (bar, keg_id, person), cell in cells.items():
            keg_entry = kegs.get((bar, keg_id)) or {}
            sold = _num(keg_entry.get('sold'))
            raw_total = raw_by_keg.get((bar, keg_id), 0.0)
            portions_total = portions_by_keg.get((bar, keg_id), 0.0)

            if raw_total > 0:
                liters = cell['raw'] * (sold / raw_total)
            elif portions_total > 0:
                # Норм нет ни у одного блюда кега: делим по порциям.
                liters = sold * (cell['portions'] / portions_total)
            else:
                liters = 0.0

            entry = people.get(person)
            if entry is None:
                entry = people[person] = {
                    'name': person, 'liters': 0.0, 'portions': 0.0,
                    'revenue': 0.0, 'cost': 0.0, 'kegs': {},
                }
            entry['liters'] += liters
            entry['portions'] += cell['portions']
            entry['revenue'] += cell['revenue']
            entry['cost'] += cell['cost']
            keg_name = keg_entry.get('keg_name') or self._keg_names.get(keg_id, keg_id)
            keg_stat = entry['kegs'].get(keg_id)
            if keg_stat is None:
                keg_stat = entry['kegs'][keg_id] = {
                    'KegName': keg_name, 'Liters': 0.0, 'Portions': 0.0, 'Revenue': 0.0,
                }
            keg_stat['Liters'] += liters
            keg_stat['Portions'] += cell['portions']
            keg_stat['Revenue'] += cell['revenue']
            assigned_liters += liters

        for (bar, keg_id), raw_total in raw_by_keg.items():
            if raw_total <= 0:
                continue
            sold = _num((kegs.get((bar, keg_id)) or {}).get('sold'))
            if sold <= 0:
                continue
            deviation = abs(sold / raw_total - 1) * 100
            if deviation > 1.0:
                kegs_scaled += 1
            max_deviation = max(max_deviation, deviation)

        rows = [self._format_bartender(entry) for entry in people.values()]
        total_liters = sum(r['TotalLiters'] for r in rows)
        total_revenue = sum(r['TotalRevenue'] for r in rows)
        for row in rows:
            row['LitersSharePercent'] = (row['TotalLiters'] / total_liters * 100
                                         if total_liters > 0 else 0.0)
            row['RevenueSharePercent'] = (row['TotalRevenue'] / total_revenue * 100
                                          if total_revenue > 0 else 0.0)
        rows.sort(key=lambda r: r['TotalLiters'], reverse=True)

        self.bartender_notes = {
            'dishes_without_volume': sorted(no_volume.values(),
                                            key=lambda s: -s['Portions'])[:10],
            'kegs_scaled': kegs_scaled,
            'max_factor_deviation_percent': max_deviation,
            'assigned_liters': assigned_liters,
        }
        return rows

    def _format_bartender(self, entry):
        """Одна строка таблицы барменов."""
        liters = entry['liters']
        revenue = entry['revenue']
        cost = entry['cost']
        portions = entry['portions']
        kegs = sorted(entry['kegs'].values(), key=lambda k: -k['Liters'])
        for keg in kegs:
            keg['SharePercent'] = (keg['Liters'] / liters * 100) if liters > 0 else 0.0
        return {
            'Bartender': entry['name'],
            'TotalLiters': liters,
            'TotalPortions': portions,
            'TotalRevenue': revenue,
            'TotalCost': cost,
            'TotalMargin': revenue - cost,
            'MarkupPercent': ((revenue - cost) / cost * 100) if cost > 0 else None,
            'PricePerLiter': revenue / liters if liters > 0 else 0.0,
            'AvgPortionLiters': liters / portions if portions > 0 else 0.0,
            'KegsCount': len(kegs),
            'LitersSharePercent': 0.0,
            'RevenueSharePercent': 0.0,
            'kegs': kegs,
        }

    # ---------- сборка ответа ----------

    def build(self, bar_name=None):
        """Готовый блок ответа для одного разреза (бар или «Общая»)."""
        kegs = self.collect_kegs(bar_name)
        kegs = self.collect_money(kegs, bar_name)
        bartenders = self.collect_bartenders(kegs, bar_name)

        # Схлопываем бары, если разрез сводный: ключ строки — кег.
        merged = {}
        for entry in kegs.values():
            key = entry['keg_id']
            target = merged.get(key)
            if target is None:
                target = merged[key] = dict(entry)
                target['buckets'] = dict(entry['buckets'])
                continue
            for field in ('sold', 'writeoff', 'inventory_out', 'inventory_in',
                          'invoice_in', 'transfer_in', 'transfer_out', 'sold_cost',
                          'revenue', 'cost', 'portions'):
                if field in entry:
                    target[field] = target.get(field, 0.0) + entry.get(field, 0.0)
            for bucket, liters in entry['buckets'].items():
                target['buckets'][bucket] = target['buckets'].get(bucket, 0.0) + liters

        rows = [self._format_keg(entry) for entry in merged.values()
                if entry['sold'] > 0 or entry.get('revenue')]
        total_liters = sum(r['TotalLiters'] for r in rows)

        for row in rows:
            row['LitersSharePercent'] = (row['TotalLiters'] / total_liters * 100
                                         if total_liters > 0 else 0.0)

        total_revenue = sum(r['TotalRevenue'] for r in rows)
        for row in rows:
            row['RevenueSharePercent'] = (row['TotalRevenue'] / total_revenue * 100
                                          if total_revenue > 0 else 0.0)

        _abc_by_cumulative(rows, 'TotalRevenue', 'ABC_Revenue', 'RevenueCumulativePercent')
        _abc_by_percentile(rows, 'MarkupPercent', 'ABC_Markup')
        _abc_by_percentile(rows, 'TotalMargin', 'ABC_Margin')
        self._assign_xyz(rows)
        for row in rows:
            row['ABC_Combined'] = row['ABC_Revenue'] + row['ABC_Markup'] + row['ABC_Margin']
            if row['XYZ_Category']:
                row['ABCXYZ_Combined'] = f"{row['ABC_Combined']}-{row['XYZ_Category']}"

        rows.sort(key=lambda r: r['TotalLiters'], reverse=True)

        total_portions = sum(r['TotalPortions'] for r in rows)
        total_cost = sum(r['TotalCost'] for r in rows)
        return {
            'period': {
                'from': self.date_from.isoformat(),
                'to': self.date_to.isoformat(),
                'days': self.period_days,
                'weeks': self.period_days / WEEK_DAYS,
            },
            'total_liters': total_liters,
            'total_portions': total_portions,
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'total_margin': total_revenue - total_cost,
            'total_kegs': len(rows),
            'avg_price_per_liter': total_revenue / total_liters if total_liters > 0 else 0.0,
            'avg_portion_liters': total_liters / total_portions if total_portions > 0 else 0.0,
            'markup_percent': ((total_revenue - total_cost) / total_cost * 100
                               if total_cost > 0 else None),
            'xyz_buckets': self.full_buckets,
            'xyz_available': self.full_buckets >= MIN_XYZ_WEEKS,
            'losses': self._build_losses(merged, total_liters),
            'unmapped_dishes': self.unmapped_dishes[:10],
            'kegs': rows,
            'total_bartenders': len(bartenders),
            'bartenders': bartenders,
            # Литры, которые не удалось отнести ни к одному бармену: продажа кега есть в
            # проводках, а строки продаж под неё нет (граница учётного дня). В норме ноль,
            # поэтому показывается только когда не ноль.
            'bartender_notes': dict(self.bartender_notes,
                                    unassigned_liters=total_liters
                                    - self.bartender_notes.get('assigned_liters', 0.0)),
        }

    def _format_keg(self, entry):
        """Одна строка таблицы: только посчитанные значения, без «примерно»."""
        liters = entry['sold']
        revenue = entry.get('revenue', 0.0)
        cost = entry.get('cost', 0.0)
        portions = entry.get('portions', 0.0)
        weeks = self.period_days / WEEK_DAYS
        return {
            'KegId': entry['keg_id'],
            'KegName': entry['keg_name'],
            'Bar': entry['bar'],
            'TotalLiters': liters,
            'TotalPortions': portions,
            'TotalRevenue': revenue,
            'TotalCost': cost,
            # Считаем всегда: у бесплатного пролива выручка нулевая, а себестоимость
            # есть, и маржа обязана показать минус, а не ноль.
            'TotalMargin': revenue - cost,
            'MarkupPercent': ((revenue - cost) / cost * 100) if cost > 0 else None,
            'PricePerLiter': revenue / liters if liters > 0 else 0.0,
            'AvgPortionLiters': liters / portions if portions > 0 else 0.0,
            'AvgLitersPerWeek': liters / weeks if weeks > 0 else 0.0,
            # Недели с продажами и всего полных недель в периоде: показывают, сколько
            # позиция реально стояла на кране. Без этой пары CV нельзя читать —
            # ротационная позиция и постоянная выглядели бы одинаково.
            'WeeksWithSales': len([index for index, value in entry['buckets'].items()
                                   if index < self.full_buckets and value > 0]),
            'WeeksInPeriod': self.full_buckets,
            'WriteoffLiters': entry['writeoff'],
            'InventoryNetLiters': entry['inventory_out'] - entry['inventory_in'],
            'XYZ_Category': None,
            'CoefficientOfVariation': None,
            '_buckets': entry['buckets'],
        }

    def _assign_xyz(self, rows):
        """XYZ по стабильности недельных проливов.

        Что именно измеряем: насколько ровно позиция продавалась В ТЕ НЕДЕЛИ, КОГДА
        СТОЯЛА НА КРАНЕ. Недели без продаж в расчёт не берутся — на кранах постоянная
        ротация (из 71 кега за 3,5 месяца только 12 продавались все 14 недель), и если
        считать пустые недели нулями, то каждая сезонная позиция получает «нестабильный
        спрос» просто за короткий срок на кране. Длительность присутствия — отдельный
        факт, он отдаётся полями WeeksWithSales и WeeksInPeriod.

        Меньше MIN_XYZ_WEEKS активных недель — категории нет (прочерк в интерфейсе).
        Это честнее выдуманного бейджа: именно на этом раньше ломался расчёт, когда на
        недельном периоде у всех позиций CV выходил 100 и X/Y/Z раздавались по порядку
        сортировки.
        """
        for row in rows:
            row['XYZ_Category'] = None
            row['CoefficientOfVariation'] = None
            row['WeeksInPeriod'] = self.full_buckets
        if self.full_buckets < MIN_XYZ_WEEKS:
            return

        for row in rows:
            active = [liters for index, liters in row['_buckets'].items()
                      if index < self.full_buckets and liters > 0]
            if len(active) < MIN_XYZ_WEEKS:
                continue
            cv = _cv_percent(active)
            if cv is None:
                continue
            row['CoefficientOfVariation'] = cv
            row['XYZ_Category'] = ('X' if cv <= XYZ_X_MAX_CV
                                   else ('Y' if cv <= XYZ_Y_MAX_CV else 'Z'))

    def _build_losses(self, merged, total_liters):
        """Баланс кегов за период: приход, расход и то, что не продано.

        Недостача инвентаризации — это нетто (расход минус излишки). Она включает и
        настоящие потери (пена, промывка линий, недолив в кеге), и недокрут остатка кега
        на кране в момент пересчёта, поэтому подаётся как факт расхождения, а не как
        готовая цифра воровства.
        """
        sold = sum(e['sold'] for e in merged.values())
        writeoff = sum(e['writeoff'] for e in merged.values())
        inventory_out = sum(e['inventory_out'] for e in merged.values())
        inventory_in = sum(e['inventory_in'] for e in merged.values())
        invoice_in = sum(e['invoice_in'] for e in merged.values())
        transfer_in = sum(e['transfer_in'] for e in merged.values())
        transfer_out = sum(e['transfer_out'] for e in merged.values())
        inventory_net = inventory_out - inventory_in

        by_keg = [{
            'KegName': e['keg_name'],
            'WriteoffLiters': e['writeoff'],
            'InventoryNetLiters': e['inventory_out'] - e['inventory_in'],
            'SoldLiters': e['sold'],
        } for e in merged.values()
            if e['writeoff'] > 0 or abs(e['inventory_out'] - e['inventory_in']) > 0]
        by_keg.sort(key=lambda k: -(k['WriteoffLiters'] + abs(k['InventoryNetLiters'])))

        return {
            'invoice_in': invoice_in,
            'transfer_in': transfer_in,
            'sold': sold,
            'writeoff': writeoff,
            'inventory_out': inventory_out,
            'inventory_in': inventory_in,
            'inventory_net': inventory_net,
            'transfer_out': transfer_out,
            'balance': (invoice_in + transfer_in
                        - sold - writeoff - inventory_net - transfer_out),
            'writeoff_percent_of_sold': (writeoff / sold * 100) if sold > 0 else 0.0,
            'inventory_percent_of_sold': (inventory_net / sold * 100) if sold > 0 else 0.0,
            'by_keg': by_keg[:15],
        }


def strip_service_fields(block):
    """Убрать из строк служебные поля перед отдачей в JSON (корзины XYZ)."""
    for row in block.get('kegs', []):
        row.pop('_buckets', None)
    return block

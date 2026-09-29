"""Каталог полей OLAP iiko для конструктора отчётов (/explorer).

Что это
    Список всех полей, из которых конструктор собирает отчёт, — тот же, что видит
    iikoOffice в «OLAP-отчёте»: GET /v2/reports/olap/columns?reportType=… Для каждого
    поля iiko отдаёт id (FieldName), русское имя из iikoOffice, тип, три флага (можно ли
    группировать, агрегировать, фильтровать) и категории (tags) — те же, что в правом
    верхнем углу конструктора iikoOffice. Здесь каталог дополняется тем, чего iiko не
    отдаёт, но без чего конструктор посчитал бы неверно или положил бы сервер:

    - kind показателя — как считать итоги (раздел «Итоги» ниже);
    - blocked — поле видно, но недоступно, с причиной (тяжёлые остатки, доли от
      раскладки таблицы, составные значения);
    - filter_op — какой фильтр у поля (список значений, диапазон, диапазон дат) или
      почему фильтра нет;
    - enum — русские названия кодов перечислений (/columns их не отдаёт; таблицы — из
      docs/iiko-api/kody-bazovykh-tipov.md);
    - группы для панели полей: «Часто используемые», категории iiko в удобном
      порядке, служебные идентификаторы — в конце.

Откуда берётся каталог (get_catalog)
    1. Память процесса, если моложе CATALOG_TTL_S (6 часов: каталог меняется только
       с обновлением iiko).
    2. Живой iiko. Удачный ответ на проде сохраняется на постоянный диск
       (/kultura/olap_columns_<ТИП>.json) — запасная копия на время, когда iiko недоступен.
    3. Запасные копии: сначала с диска, затем снимки в репозитории
       (resources/olap_all_fields.json — продажи, resources/olap_transactions_fields.json
       — проводки, resources/olap_stock_fields.json — контроль хранения). Снимки лежат
       в resources/, а не в data/: в проде /app/data перекрыт диском сервера, и файлы
       data/ из образа не видны, а релиз с изменениями в data/ скрипт выкладки не
       выпускает (docs/guides/deploy.md). В ответе source говорит, откуда каталог:
       'live' | 'disk' | 'repo'.
    После неудачи живого запроса iiko не опрашивается LIVE_RETRY_S секунд — страница
    не должна ждать таймаут на каждом открытии, пока сервер лежит.

Итоги (kind показателя)
    'sum'    — обычная сумма по строкам (выручка, количество, себестоимость, приход и
               расход). Итог группы = сложение её строк; это точно и не требует от iiko
               ничего сверх данных.
    'server' — всё остальное: уникальные чеки и заказы, средние, проценты, длительности,
               время. Сложение строк для них ДАЁТ НЕВЕРНОЕ число (чек с пивом и едой попал
               бы в итог дважды), поэтому итоги таких показателей берутся из iiko —
               buildSummary, как их считает сам iikoOffice (core/olap_constructor.py).
    Список 'sum' — явный (SUM_MEASURES): неизвестный новый показатель по умолчанию
    'server', то есть в худшем случае итог придёт из iiko, но никогда не будет
    неверной суммой.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core import msk_time
from core.olap_client import IikoError, open_session

REPORT_TYPES: Tuple[str, ...] = ('SALES', 'TRANSACTIONS', 'DELIVERIES', 'STOCK')
REPORT_TYPE_TITLES: Dict[str, str] = {
    'SALES': 'Продажи',
    'TRANSACTIONS': 'Проводки',
    'DELIVERIES': 'Доставка',
    'STOCK': 'Контроль хранения',
}
REPORT_TYPE_HINTS: Dict[str, str] = {
    'SALES': 'OLAP-отчёт по продажам: чеки, блюда, оплаты, скидки, сотрудники',
    'TRANSACTIONS': 'OLAP-отчёт по проводкам: склад и деньги — приход, расход, списания',
    'DELIVERIES': 'OLAP-отчёт по доставкам (у сети доставки нет)',
    'STOCK': 'Контроль хранения: просрочка на момент продажи',
}
# Поле периода: по нему конструктор всегда ставит фильтр дат (с iiko 5.5 фильтр по дате
# обязателен в каждом OLAP-запросе, docs/iiko-api/olap-otchety-v2.md). Для продаж и
# доставок — учётный день заказа, для проводок — учётный день проводки
# (так советует документация iiko), для контроля хранения — дата события.
DATE_FIELD: Dict[str, str] = {
    'SALES': 'OpenDate.Typed',
    'DELIVERIES': 'OpenDate.Typed',
    'TRANSACTIONS': 'DateTime.DateTyped',
    'STOCK': 'EventDate',
}

# Снимки каталога в образе: файл в resources/ и дата снимка. Дата — из истории файла,
# а не время изменения: в образе это время выкладки.
RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'resources')
REPO_SNAPSHOTS: Dict[str, Tuple[str, str]] = {
    'SALES': ('olap_all_fields.json', '2025-10-18'),
    'TRANSACTIONS': ('olap_transactions_fields.json', '2026-09-20'),
    'STOCK': ('olap_stock_fields.json', '2025-10-18'),
}
DISK_SNAPSHOT = 'olap_columns_{}.json'
CATALOG_TTL_S = 6 * 3600
LIVE_RETRY_S = 60

# ---------------------------------------------------------------- коды перечислений

TRANSACTION_TYPES = {
    'OPENING_BALANCE': 'Начальный баланс', 'CUSTOM': 'Ручная проводка',
    'CASH': 'Продажа за наличные', 'PREPAY_CLOSED': 'Продажа с предоплатой',
    'PREPAY': 'Предоплата', 'PREPAY_RETURN': 'Возврат предоплаты',
    'PREPAY_CLOSED_RETURN': 'Возврат продажи с предоплатой', 'DISCOUNT': 'Скидка',
    'CARD': 'Выручка по картам', 'CREDIT': 'Выручка в кредит', 'PAYIN': 'Внесенная сумма',
    'PAYOUT': 'Изъятая сумма', 'PAY_COLLECTION': 'Снятая выручка',
    'CASH_CORRECTION': 'Коррекция по кассе', 'INVENTORY_CORRECTION': 'Инвентаризация',
    'STORE_COST_CORRECTION': 'Коррекция себестоимости', 'CASH_SURPLUS': 'Излишек по кассе',
    'CASH_SHORTAGE': 'Недостача по кассе', 'PENALTY': 'Штраф', 'BONUS': 'Премия',
    'INVOICE': 'Накладная', 'NDS_INCOMING': 'НДС входящий', 'NDS_SALES': 'НДС с продаж',
    'SALES_REVENUE': 'Выручка от реализации', 'OUTGOING_INVOICE': 'Расходная накладная',
    'OUTGOING_INVOICE_REVENUE': 'Выручка расходной накладной',
    'RETURNED_INVOICE': 'Возвратная накладная',
    'RETURNED_INVOICE_REVENUE': 'Выручка возвратной накладной', 'WRITEOFF': 'Списание',
    'SESSION_WRITEOFF': 'Реализация товаров', 'TRANSFER': 'Внутреннее перемещение',
    'TRANSFORMATION': 'Акт переработки', 'TARIFF_HOUR': 'Почасовая оплата',
    'ON_THE_HOUSE': 'Оплата заказа за счет заведения', 'ADVANCE': 'Аванс по зарплате',
    'INCOMING_SERVICE': 'Получение услуг', 'OUTGOING_SERVICE': 'Оказание услуг',
    'INCOMING_SERVICE_PAYMENT': 'Оплата получения услуг',
    'OUTGOING_SERVICE_PAYMENT': 'Оплата оказания услуг',
    'IMPORTED_BANK_STATEMENT': 'Загрузка банковской выписки',
    'CLOSE_AT_EMPLOYEE_EXPENSE': 'Закрытие стола за счет сотрудника',
    'INCENTIVE_PAYMENT': 'Мотивация', 'TARIFF_PERCENT': 'Процент с продаж',
    'SESSION_ACCEPTANCE': 'Принятие смены', 'EMPLOYEE_CASH_PAYMENT': 'Выдача наличных сотрудникам',
    'EMPLOYEE_PAYMENT': 'Начисление оклада', 'INVOICE_PAYMENT': 'Оплата накладной',
    'OUTGOING_DOCUMENT_PAYMENT': 'Принятие оплаты исходящего документа',
    'OUTGOING_SALES_DOCUMENT_PAYMENT': 'Принятие оплаты акта реализации',
    'PRODUCTION': 'Акт приготовления', 'SALES_RETURN_PAYMENT': 'Оплата приема возврата',
    'SALES_RETURN_WRITEOFF': 'Возврат товаров', 'DISASSEMBLE': 'Акт разбора',
}
DOCUMENT_TYPES = {
    'INCOMING_INVOICE': 'Приходная накладная', 'INCOMING_INVENTORY': 'Инвентаризация',
    'INCOMING_SERVICE': 'Акт приема услуг', 'OUTGOING_SERVICE': 'Акт оказания услуг',
    'WRITEOFF_DOCUMENT': 'Акт списания', 'SALES_DOCUMENT': 'Акт реализации',
    'SESSION_ACCEPTANCE': 'Принятие смены', 'INTERNAL_TRANSFER': 'Внутреннее перемещение',
    'OUTGOING_INVOICE': 'Расходная накладная', 'RETURNED_INVOICE': 'Возвратная накладная',
    'PRODUCTION_DOCUMENT': 'Акт приготовления', 'TRANSFORMATION_DOCUMENT': 'Акт переработки',
    'PRODUCTION_ORDER': 'Заказ в производство', 'CONSOLIDATED_ORDER': 'Консолидированный заказ',
    'PREPARED_REGISTER': 'Ведомость полуфабрикатов',
    'MENU_CHANGE': 'Приказ об изменении прейскуранта', 'PRODUCT_REPLACEMENT': 'Замена товаров',
    'SALES_RETURN_DOCUMENT': 'Акт приема возврата', 'DISASSEMBLE_DOCUMENT': 'Акт разбора',
    'PAYROLL': 'Платёжная ведомость', 'INCOMING_CASH_ORDER': 'Приходный кассовый ордер',
    'OUTGOING_CASH_ORDER': 'Расходный кассовый ордер',
}
ACCOUNT_TYPES = {
    'CASH': 'Денежные средства', 'ACCOUNTS_RECEIVABLE': 'Задолженность покупателей',
    'DEBTS_OF_EMPLOYEES': 'Задолженность сотрудников', 'CURRENT_ASSET': 'Текущие активы',
    'OTHER_CURRENT_ASSET': 'Основные средства', 'INVENTORY_ASSETS': 'Складские запасы',
    'EMPLOYEES_LIABILITY': 'Расчеты с сотрудниками', 'ACCOUNTS_PAYABLE': 'Расчеты с поставщиками',
    'CLIENTS_LIABILITY': 'Расчеты с гостями', 'OTHER_CURRENT_LIABILITY': 'Прочие текущие обязательства',
    'LONG_TERM_LIABILITY': 'Долгосрочные обязательства',
    'COST_OF_GOODS_SOLD': 'Прямые издержки (себестоимость)', 'INCOME': 'Доходы',
    'EXPENSES': 'Расходы', 'OTHER_INCOME': 'Прочие доходы', 'OTHER_EXPENSES': 'Прочие расходы',
}
ACCOUNT_GROUPS = {'ASSETS': 'Активы', 'LIABILITIES': 'Обязательства', 'EQUITY': 'Капитал',
                  'INCOME_EXPENSES': 'Доходы/Расходы'}
COUNTERAGENT_TYPES = {'NONE': 'Нет', 'COUNTERAGENT': 'Все', 'EMPLOYEE': 'Сотрудник',
                      'SUPPLIER': 'Поставщик', 'CLIENT': 'Гость',
                      'INTERNAL_SUPPLIER': 'Внутренний поставщик'}
PRODUCT_TYPES = {'GOODS': 'Товар', 'DISH': 'Блюдо', 'PREPARED': 'Заготовка', 'SERVICE': 'Услуга',
                 'MODIFIER': 'Модификатор', 'OUTER': 'Внешние товары', 'PETROL': 'Топливо',
                 'RATE': 'Тариф'}
CASHFLOW_TYPES = {'OPERATIONAL': 'Операционная деятельность',
                  'INVESTMENT': 'Инвестиционная деятельность', 'FINANCE': 'Финансовая деятельность'}
CASHFLOW_FLAG = {'CASH_FLOW': 'Участвует в ДДС', 'NOT_CASH_FLOW': 'Не участвует в ДДС'}
STORE_OR_ACCOUNT = {'STORE': 'Склад', 'ACCOUNT': 'Счет'}
ALCOHOL_TYPES = {'STRONG': 'Крепкие', 'BEER': 'Пиво'}
SIDES = {'DEBIT': 'Дебет', 'CREDIT': 'Кредит'}
DELETION_TYPES = {'NOT_DELETED': 'Не удалено', 'DELETED_WITH_WRITEOFF': 'Удалено со списанием',
                  'DELETED_WITHOUT_WRITEOFF': 'Удалено без списания'}
# В справочнике iiko — «Заказ не удален» / «Заказ удален»; у поля «Заказ удален» это
# читалось бы тавтологией («Заказ удален: Заказ не удален»), поэтому коротко.
ORDER_DELETED = {'NOT_DELETED': 'Не удален', 'DELETED': 'Удален'}
DELIVERY_FLAG = {'DELIVERY_ORDER': 'Доставка', 'ORDER_WITHOUT_DELIVERY': 'Не доставка'}
DISH_TYPES = {'DISH': 'Блюдо', 'GOOD': 'Товар', 'MODIFIER': 'Модификатор'}
OPERATION_TYPES = {'STORNED': 'Сторнирование', 'PREPAY': 'Предоплата',
                   'PREPAY_RETURN': 'Возврат предоплаты', 'NO_PAYMENT': '(без оплаты)',
                   'PAYMENT': 'Оплата'}
PAY_GROUPS = {'CASH': 'Оплата наличными', 'CARD': 'Банковские карты', 'WRITEOFF': 'Без выручки',
              'NON_CASH': 'Безналичный расчет'}
FISCAL = {'FISCAL': 'Фискальный', 'NOT_FISCAL': 'Не фискальный'}
DELIVERY_SERVICE = {'PICKUP': 'Самовывоз', 'COURIER': 'Курьер'}

# Поле -> таблица кодов. Перечисления без таблицы (VAT.SplitVat, OrderServiceType,
# Delivery.IsAsap, Event.Type) показываются кодами iiko как есть.
ENUM_LABELS: Dict[str, Dict[str, str]] = {
    'TransactionType': TRANSACTION_TYPES,
    'NonCashPaymentType.DocumentType': DOCUMENT_TYPES,
    'Account.Type': ACCOUNT_TYPES, 'Contr-Account.Type': ACCOUNT_TYPES,
    'Account.Group': ACCOUNT_GROUPS, 'Contr-Account.Group': ACCOUNT_GROUPS,
    'Account.CounteragentType': COUNTERAGENT_TYPES,
    'Product.Type': PRODUCT_TYPES, 'Contr-Product.Type': PRODUCT_TYPES,
    'CashFlowCategory.Type': CASHFLOW_TYPES,
    'Account.IsCashFlowAccount': CASHFLOW_FLAG,
    'Account.StoreOrAccount': STORE_OR_ACCOUNT,
    'Product.AlcoholClass.Type': ALCOHOL_TYPES, 'Contr-Product.AlcoholClass.Type': ALCOHOL_TYPES,
    'TransactionSide': SIDES,
    'DeletedWithWriteoff': DELETION_TYPES,
    'OrderDeleted': ORDER_DELETED,
    'Delivery.IsDelivery': DELIVERY_FLAG,
    'Banquet': {'TRUE': 'Банкет', 'FALSE': 'Не банкет'},
    'Storned': {'TRUE': 'Возврат чека', 'FALSE': 'Не возврат'},
    'DishType': DISH_TYPES,
    'OperationType': OPERATION_TYPES,
    'PayTypes.Group': PAY_GROUPS,
    'PayTypes.IsPrintCheque': FISCAL,
    'Delivery.ServiceType': DELIVERY_SERVICE,
}

# ---------------------------------------------------------------- показатели и запреты

# Показатели, итог которых — обычная сумма строк (kind 'sum'). Остальные — 'server'.
SUM_MEASURES = frozenset((
    # продажи и доставки
    'DishDiscountSumInt', 'DishDiscountSumInt.withoutVAT', 'DishSumInt', 'DiscountSum',
    'discountWithoutVAT', 'fullSum', 'sumAfterDiscountWithoutVAT', 'IncreaseSum', 'VAT.Sum',
    'DishReturnSum', 'DishReturnSum.withoutVAT', 'DishAmountInt', 'PayableAmountInt',
    'ProductCostBase.ProductCost', 'ProductCostBase.Profit',
    'ItemSaleEventDiscountType.DiscountAmount', 'ItemSaleEventDiscountType.ComboAmount',
    'IncentiveSumBase.Sum',
    # проводки
    'Amount', 'Amount.In', 'Amount.Out', 'Amount.StoreInOutTyped', 'Contr-Amount',
    'Sum.ResignedSum', 'Sum.Incoming', 'Sum.Outgoing',
))

HEAVY_REASON = ('Тяжёлый запрос: iiko суммирует проводки за всё время работы и советует '
                'запускать его ночью. Текущие остатки — на странице «Остатки».')
LAYOUT_REASON = ('Доля от итога зависит от раскладки таблицы iikoOffice; в конструкторе её '
                 'показывает переключатель «Доли» над таблицей.')
OBJECT_REASON = 'Составное значение (объект): iiko отдаёт его не числом и не строкой.'
BLOCKED: Dict[str, str] = {
    'StartBalance.Amount': HEAVY_REASON, 'StartBalance.Money': HEAVY_REASON,
    'FinalBalance.Amount': HEAVY_REASON, 'FinalBalance.Money': HEAVY_REASON,
    'PercentOfSummary.ByCol': LAYOUT_REASON, 'PercentOfSummary.ByRow': LAYOUT_REASON,
    'Sum.PartOfSummaryByCol': LAYOUT_REASON, 'Sum.PartOfSummaryByRow': LAYOUT_REASON,
}

# ---------------------------------------------------------------- подсказки и группы

# Короткая подпись после имени поля: как оно связано с остальным сервисом.
FIELD_HINTS: Dict[str, str] = {
    'Store.Name': 'бар — так во всех отчётах сервиса',
    'OpenDate.Typed': 'учётный день',
    'DateTime.DateTyped': 'учётный день',
    'DishDiscountSumInt': 'выручка — так на дашборде',
    'UniqOrderId': 'чеки',
    'UniqOrderId.OrdersCount': 'заказы',
    'AuthUser': 'сотрудник — так в KPI и ЗП',
    'WaiterName': 'пусто для продаж через стойку',
    'DishAmountInt': 'порции, не литры',
    'OrderNum': 'номер чека, не счётчик',
    'Account.Name': 'склад или счёт (бар — его склад)',
    'Contr-Account.Name': 'корреспондирующий счёт (у списаний — счёт списания)',
    'Amount.Out': 'в единицах товара (у кег — литры)',
    'Amount.In': 'в единицах товара (у кег — литры)',
}

FAVORITES: Dict[str, Tuple[str, ...]] = {
    'SALES': (
        'OpenDate.Typed', 'DayOfWeekOpen', 'HourOpen', 'WeekInYearOpen', 'Mounth', 'Store.Name',
        'DishGroup.TopParent', 'DishGroup.SecondParent', 'DishGroup.ThirdParent', 'DishName',
        'AuthUser', 'PayTypes', 'OrderDiscount.Type', 'DeletedWithWriteoff', 'RemovalType',
        'WriteoffReason', 'DishDiscountSumInt', 'DishSumInt', 'DiscountSum', 'DishAmountInt',
        'UniqOrderId', 'DishDiscountSumInt.average', 'GuestNum', 'ProductCostBase.ProductCost',
        'ProductCostBase.MarkUp',
    ),
    'TRANSACTIONS': (
        'DateTime.DateTyped', 'DateTime.Month', 'Account.Name', 'Contr-Account.Name',
        'Product.TopParent', 'Product.SecondParent', 'Product.Name', 'Product.MeasureUnit',
        'TransactionType', 'Document', 'Comment', 'Counteragent.Name', 'Amount.In', 'Amount.Out',
        'Sum.Incoming', 'Sum.Outgoing', 'Sum.ResignedSum', 'Amount',
    ),
    'STOCK': (
        'EventDate', 'Department', 'StoreFrom', 'ProductName', 'ProductCategory', 'User',
        'Event.Type', 'Amount', 'ProductExpirationDuration', 'ProductCostBase.ProductCost',
    ),
}
FAVORITES['DELIVERIES'] = FAVORITES['SALES'] + ('Delivery.ServiceType', 'Delivery.Courier',
                                                'Delivery.Delay')

TAG_ORDER: Dict[str, Tuple[str, ...]] = {
    'SALES': ('Время', 'Организация', 'Блюда', 'Заказ', 'Оплата', 'Скидки/надбавки', 'Сотрудники',
              'Гости', 'Себестоимость', 'НДС', 'Бонусы', 'Приготовление', 'Временные интервалы',
              'Корпорация', 'Счета', 'Доставка', 'Клиент доставки', 'Отзывы клиентов'),
    'TRANSACTIONS': ('Дата и время', 'Транзакция', 'Счета', 'Номенклатура', 'Корреспондент', 'ОСВ',
                     'Финансы', 'P&L', 'Движение денежных средств', 'Корпорация', 'Организация',
                     'Алкоголь', 'Оплата'),
    'STOCK': (),
}
TAG_ORDER['DELIVERIES'] = ('Доставка', 'Клиент доставки', 'Отзывы клиентов') + tuple(
    t for t in TAG_ORDER['SALES'] if t not in ('Доставка', 'Клиент доставки', 'Отзывы клиентов'))

FAVORITES_TITLE = 'Часто используемые'
ID_GROUP_TITLE = 'Идентификаторы (ID)'
OTHER_GROUP_TITLE = 'Прочие поля'
ID_TYPES = ('ID', 'ID_STRING')
VALUE_FILTER_TYPES = ('ENUM', 'STRING', 'ID', 'ID_STRING')
RANGE_FILTER_TYPES = ('INTEGER', 'AMOUNT', 'MONEY', 'PERCENT')
DATE_FILTER_TYPES = ('DATE', 'DATETIME')


@dataclass
class Field:
    id: str
    name: str
    type: str
    group: bool
    agg: bool
    filter: bool
    tags: Tuple[str, ...] = ()
    blocked: Optional[str] = None
    kind: Optional[str] = None
    filter_op: Optional[str] = None
    filter_note: Optional[str] = None
    enum: Optional[Tuple[Tuple[str, str], ...]] = None
    hint: Optional[str] = None

    def enum_label(self, code) -> Optional[str]:
        if code is None or not self.enum:
            return None
        for key, label in self.enum:
            if key == code:
                return label
        return None

    def to_json(self, compact: bool = False) -> dict:
        out = {'id': self.id, 'name': self.name, 'type': self.type, 'group': self.group,
               'agg': self.agg, 'filter_op': self.filter_op}
        if self.kind:
            out['kind'] = self.kind
        if self.blocked:
            out['blocked'] = self.blocked
        if self.hint:
            out['hint'] = self.hint
        if not compact:
            out['tags'] = list(self.tags)
            if self.filter_note:
                out['filter_note'] = self.filter_note
            if self.enum:
                out['enum'] = [list(pair) for pair in self.enum]
        return out


@dataclass
class Catalog:
    report_type: str
    fields: List[Field]
    source: str
    fetched_at: str
    live_error: Optional[str] = None
    by_id: Dict[str, Field] = field(default_factory=dict)

    def __post_init__(self):
        self.by_id = {f.id: f for f in self.fields}

    def get(self, field_id: str) -> Optional[Field]:
        return self.by_id.get(field_id)

    @property
    def date_field(self) -> str:
        return DATE_FIELD[self.report_type]

    def groups(self) -> List[dict]:
        """Группы панели полей: избранное, категории iiko по TAG_ORDER, прочие, ID."""
        out = []
        favorites = [fid for fid in FAVORITES.get(self.report_type, ()) if fid in self.by_id]
        if favorites:
            out.append({'title': FAVORITES_TITLE, 'ids': favorites})
        by_tag: Dict[str, List[str]] = {}
        ids, others = [], []
        for item in self.fields:
            if item.type in ID_TYPES:
                ids.append(item.id)
                continue
            if not item.tags:
                others.append(item.id)
                continue
            for tag in item.tags:
                by_tag.setdefault(tag, []).append(item.id)
        order = list(TAG_ORDER.get(self.report_type, ()))
        order += sorted(tag for tag in by_tag if tag not in order)
        for tag in order:
            if by_tag.get(tag):
                out.append({'title': tag, 'ids': by_tag[tag]})
        if others:
            out.append({'title': OTHER_GROUP_TITLE, 'ids': others})
        if ids:
            out.append({'title': ID_GROUP_TITLE, 'ids': ids})
        return out

    def to_json(self, q: str = '', tag: str = '', compact: bool = False) -> dict:
        selected = self.fields
        query = (q or '').strip().casefold()
        if query:
            selected = [f for f in selected if query in f.id.casefold() or
                        query in f.name.casefold() or
                        any(query in t.casefold() for t in f.tags)]
        if tag:
            selected = [f for f in selected if tag in f.tags]
        out = {
            'report_type': self.report_type,
            'title': REPORT_TYPE_TITLES[self.report_type],
            'date_field': self.date_field,
            'source': self.source,
            'fetched_at': self.fetched_at,
            'field_count': len(self.fields),
            'fields': [f.to_json(compact=compact) for f in selected],
        }
        if self.live_error:
            out['live_error'] = self.live_error
        if not query and not tag and not compact:
            out['groups'] = self.groups()
        return out


def _filter_op(ftype: str, group: bool, filt: bool, is_date_field: bool) -> Tuple[Optional[str], Optional[str]]:
    """Какой фильтр у поля и, если его нет, почему."""
    if is_date_field:
        return None, 'Это поле периода: его задаёт выбор периода отчёта.'
    if not filt:
        return None, 'iiko не разрешает фильтр по этому полю.'
    if ftype in VALUE_FILTER_TYPES:
        return 'values', None
    if ftype in DATE_FILTER_TYPES:
        return 'date_range', None
    if ftype in RANGE_FILTER_TYPES:
        if group:
            return 'range', None
        # Итоговые показатели iiko на сервере не фильтрует: фильтр по DiscountSum
        # отвечал HTTP 400 «Filtering is not allowed» (проверено 2026-06-17).
        return None, 'Показатель: условия на итоговые суммы iiko не фильтрует.'
    return None, 'У поля этого типа нет фильтра.'


def normalize(raw: dict, report_type: str) -> List[Field]:
    """Ответ /v2/reports/olap/columns -> список Field, отсортированный по русскому имени."""
    if not isinstance(raw, dict) or not raw:
        raise IikoError('Каталог полей iiko пуст или не в том формате.', 502)
    date_field = DATE_FIELD[report_type]
    fields = []
    for fid, info in raw.items():
        if not isinstance(info, dict):
            continue
        ftype = str(info.get('type') or 'STRING')
        group = bool(info.get('groupingAllowed'))
        agg = bool(info.get('aggregationAllowed'))
        filt = bool(info.get('filteringAllowed'))
        blocked = BLOCKED.get(fid)
        if ftype == 'OBJECT':
            blocked = OBJECT_REASON
        op, note = _filter_op(ftype, group, filt, fid == date_field)
        labels = ENUM_LABELS.get(fid) if ftype == 'ENUM' else None
        fields.append(Field(
            id=str(fid),
            name=str(info.get('name') or fid),
            type=ftype,
            group=group,
            agg=agg,
            filter=filt,
            tags=tuple(str(t) for t in (info.get('tags') or [])),
            blocked=blocked,
            kind=('sum' if fid in SUM_MEASURES else 'server') if agg else None,
            filter_op=op if not blocked else None,
            filter_note=note if not blocked else None,
            enum=tuple(labels.items()) if labels else None,
            hint=FIELD_HINTS.get(fid),
        ))
    fields.sort(key=lambda f: (f.name.casefold(), f.id))
    return fields


# ---------------------------------------------------------------- загрузка

_memory: Dict[str, Catalog] = {}
_memory_stamp: Dict[str, float] = {}
_live_failed_at: Dict[str, float] = {}
_lock = threading.Lock()


def _read_json(path: str):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _disk_path(report_type: str) -> Optional[str]:
    """Запасная копия живого каталога на постоянном диске (только в проде)."""
    from core.storage_paths import RENDER_DISK_DIR, is_persistent_storage_active
    if not is_persistent_storage_active():
        return None
    return os.path.join(RENDER_DISK_DIR, DISK_SNAPSHOT.format(report_type))


def _repo_path(report_type: str) -> Optional[str]:
    snapshot = REPO_SNAPSHOTS.get(report_type)
    return os.path.join(RESOURCES_DIR, snapshot[0]) if snapshot else None


def _save_disk(report_type: str, raw: dict) -> None:
    path = _disk_path(report_type)
    if not path:
        return
    try:
        from core.json_store import atomic_write_json
        atomic_write_json(path, raw)
    except OSError as error:
        print('[OLAP-CATALOG] не удалось сохранить копию каталога ' + report_type + ': ' + str(error))


def _fallback(report_type: str, live_error: str) -> Catalog:
    for source, path in (('disk', _disk_path(report_type)), ('repo', _repo_path(report_type))):
        if not path or not os.path.exists(path):
            continue
        raw = _read_json(path)
        if isinstance(raw, dict) and raw:
            if source == 'repo':
                stamp = REPO_SNAPSHOTS[report_type][1]
            else:
                stamp = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path)))
            return Catalog(report_type, normalize(raw, report_type), source, stamp, live_error)
    raise IikoError('Каталог полей «' + REPORT_TYPE_TITLES[report_type] + '» недоступен: iiko не '
                    'ответил (' + live_error + '), а запасной копии нет.', 502)


def get_catalog(report_type: str, refresh: bool = False) -> Catalog:
    """Каталог полей типа отчёта (см. докстринг модуля, «Откуда берётся каталог»)."""
    if report_type not in REPORT_TYPES:
        raise ValueError('Тип отчёта: ' + ', '.join(REPORT_TYPES) + '.')
    now = time.time()
    with _lock:
        cached = _memory.get(report_type)
        if cached is not None and not refresh and now - _memory_stamp[report_type] < CATALOG_TTL_S:
            return cached
        failed_at = _live_failed_at.get(report_type)
    if failed_at is not None and not refresh and now - failed_at < LIVE_RETRY_S:
        if cached is not None:
            return cached
        return _fallback(report_type, 'iiko недавно не ответил')
    try:
        with open_session() as session:
            raw = session.get_json('/v2/reports/olap/columns', {'reportType': report_type})
        catalog = Catalog(report_type, normalize(raw, report_type), 'live',
                          msk_time.now().strftime('%Y-%m-%d %H:%M'))
    except IikoError as error:
        with _lock:
            _live_failed_at[report_type] = time.time()
        if cached is not None:
            return cached
        return _fallback(report_type, error.message)
    _save_disk(report_type, raw)
    with _lock:
        _memory[report_type] = catalog
        _memory_stamp[report_type] = time.time()
        _live_failed_at.pop(report_type, None)
    return catalog


def reset_cache() -> None:
    """Тесты: забыть каталоги и неудачи."""
    with _lock:
        _memory.clear()
        _memory_stamp.clear()
        _live_failed_at.clear()

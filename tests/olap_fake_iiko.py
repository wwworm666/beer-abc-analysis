"""Поддельный iiko для тестов конструктора OLAP (core/olap_constructor.py и соседи).

Ведёт себя как iiko Server на уровне, нужном конструктору:
- GET /v2/reports/olap/columns — каталог из снимков в data/ (как у живого сервера);
- GET /v2/reports/olap/presets — список PRESETS;
- POST /v2/reports/olap — настоящая группировка «фактов» (строк позиций чеков) по
  groupByRowFields с фильтрами IncludeValues / ExcludeValues / Range / DateRange
  (to исключающий, как у iiko) и агрегатами: суммы — сложением, UniqOrderId —
  числом уникальных чеков, DishDiscountSumInt.average — выручка / чеки. При
  buildSummary='true' возвращает summary блоками [ключи префикса, итоги] для каждого
  префикса полей группировки, от пустого (общий итог) до полного — как в документации
  iiko (olap-otchety-v2.md, «Что в ответе»).

Итоги считаются по фактам, а не сложением строк, поэтому тесты ловят ошибку «чеки
сложены по категориям»: у одного чека пиво и еда, в итоге он должен посчитаться один раз.
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Позиции чеков: чек, бар, дата, группа, блюдо, сумма со скидкой, количество, удалено.
FACTS = [
    {'UniqOrderId.Id': 'o1', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-21',
     'DishGroup.TopParent': 'Напитки Розлив', 'DishName': 'IPA 0,5',
     'DishDiscountSumInt': 400.0, 'DishSumInt': 400.0, 'DishAmountInt': 1.0,
     'DeletedWithWriteoff': 'NOT_DELETED', 'OrderDeleted': 'NOT_DELETED'},
    {'UniqOrderId.Id': 'o1', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-21',
     'DishGroup.TopParent': 'ЕДА', 'DishName': 'Гренки',
     'DishDiscountSumInt': 300.0, 'DishSumInt': 300.0, 'DishAmountInt': 1.0,
     'DeletedWithWriteoff': 'NOT_DELETED', 'OrderDeleted': 'NOT_DELETED'},
    {'UniqOrderId.Id': 'o2', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-21',
     'DishGroup.TopParent': 'Напитки Розлив', 'DishName': 'IPA 0,5',
     'DishDiscountSumInt': 400.0, 'DishSumInt': 400.0, 'DishAmountInt': 1.0,
     'DeletedWithWriteoff': 'NOT_DELETED', 'OrderDeleted': 'NOT_DELETED'},
    {'UniqOrderId.Id': 'o3', 'Store.Name': 'Варшавская', 'OpenDate.Typed': '2026-09-22',
     'DishGroup.TopParent': 'Напитки Фасовка', 'DishName': 'Bottle',
     'DishDiscountSumInt': 250.0, 'DishSumInt': 300.0, 'DishAmountInt': 2.0,
     'DeletedWithWriteoff': 'NOT_DELETED', 'OrderDeleted': 'NOT_DELETED'},
    {'UniqOrderId.Id': 'o3', 'Store.Name': 'Варшавская', 'OpenDate.Typed': '2026-09-22',
     'DishGroup.TopParent': 'ЕДА', 'DishName': 'Гренки',
     'DishDiscountSumInt': 300.0, 'DishSumInt': 300.0, 'DishAmountInt': 1.0,
     'DeletedWithWriteoff': 'NOT_DELETED', 'OrderDeleted': 'NOT_DELETED'},
    {'UniqOrderId.Id': 'o4', 'Store.Name': 'Варшавская', 'OpenDate.Typed': '2026-09-22',
     'DishGroup.TopParent': 'ЕДА', 'DishName': 'Суп',
     'DishDiscountSumInt': 500.0, 'DishSumInt': 500.0, 'DishAmountInt': 1.0,
     'DeletedWithWriteoff': 'DELETED_WITH_WRITEOFF', 'OrderDeleted': 'NOT_DELETED'},
    {'UniqOrderId.Id': 'o5', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-23',
     'DishGroup.TopParent': 'Напитки Розлив', 'DishName': 'Stout 0,5',
     'DishDiscountSumInt': 450.0, 'DishSumInt': 450.0, 'DishAmountInt': 1.0,
     'DeletedWithWriteoff': 'NOT_DELETED', 'OrderDeleted': 'NOT_DELETED'},
    # Позиция без группы (null в разрезе) — проверка «(пусто)».
    {'UniqOrderId.Id': 'o6', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-23',
     'DishGroup.TopParent': None, 'DishName': 'Сбор',
     'DishDiscountSumInt': 50.0, 'DishSumInt': 50.0, 'DishAmountInt': 1.0,
     'DeletedWithWriteoff': 'NOT_DELETED', 'OrderDeleted': 'NOT_DELETED'},
]

PRESETS = [
    {'id': 'p-1', 'name': 'Продажи по барам за прошлый месяц', 'reportType': 'SALES',
     'groupByRowFields': ['Store.Name'], 'groupByColFields': ['DishGroup.TopParent'],
     'aggregateFields': ['DishDiscountSumInt'],
     'filters': {
         'OpenDate.Typed': {'filterType': 'DateRange', 'periodType': 'LAST_MONTH',
                            'from': '2026-01-01T00:00:00.000'},
         'DeletedWithWriteoff': {'filterType': 'IncludeValues', 'values': ['NOT_DELETED']},
         'SessionNum': {'filterType': 'Range', 'from': 1, 'to': 9, 'includeHigh': True},
         'Weird': {'filterType': 'Unknown'},
     }},
    {'id': 'p-2', 'name': 'Своя дата', 'reportType': 'SALES',
     'groupByRowFields': ['DishName'], 'aggregateFields': ['DishAmountInt'],
     'filters': {'OpenDate.Typed': {'filterType': 'DateRange', 'periodType': 'CUSTOM',
                                    'from': '2025-03-01T00:00:00.000',
                                    'to': '2025-04-01T00:00:00.000'}}},
    {'id': 'p-3', 'name': 'Контроль хранения', 'reportType': 'STOCK',
     'groupByRowFields': ['ProductName'], 'aggregateFields': ['Amount'], 'filters': {}},
    {'id': 'p-4', 'name': 'Чужой тип', 'reportType': 'SOMETHING',
     'groupByRowFields': [], 'aggregateFields': [], 'filters': {}},
]

SNAPSHOTS = {'SALES': 'olap_all_fields.json', 'TRANSACTIONS': 'olap_transactions_fields.json',
             'STOCK': 'olap_stock_fields.json'}


def load_snapshot(report_type):
    with open(os.path.join(REPO, 'data', SNAPSHOTS[report_type]), encoding='utf-8') as handle:
        return json.load(handle)


def _passes(fact, field, flt):
    value = fact.get(field)
    kind = flt.get('filterType')
    if kind == 'IncludeValues':
        return value in flt['values']
    if kind == 'ExcludeValues':
        return value not in flt['values']
    if kind == 'Range':
        low, high = flt['from'], flt['to']
        ok_low = value >= low if flt.get('includeLow', True) else value > low
        ok_high = value <= high if flt.get('includeHigh', False) else value < high
        return ok_low and ok_high
    if kind == 'DateRange':
        low, high = str(flt['from'])[:10], str(flt['to'])[:10]
        day = str(value)[:10]
        ok_low = day >= low if flt.get('includeLow', True) else day > low
        ok_high = day <= high if flt.get('includeHigh', False) else day < high
        return ok_low and ok_high
    raise AssertionError('фильтр не поддержан подделкой: ' + str(kind))


def _aggregate(facts, measures):
    out = {}
    orders = {f['UniqOrderId.Id'] for f in facts}
    for measure in measures:
        if measure == 'UniqOrderId':
            out[measure] = len(orders)
        elif measure == 'DishDiscountSumInt.average':
            total = sum(f['DishDiscountSumInt'] for f in facts)
            out[measure] = total / len(orders) if orders else None
        else:
            out[measure] = sum(f.get(measure) or 0 for f in facts)
    return out


def olap(body, facts=None):
    """Ответ «iiko» на тело OLAP-запроса."""
    facts = FACTS if facts is None else facts
    selected = [f for f in facts
                if all(_passes(f, field, flt) for field, flt in body['filters'].items())]
    fields = list(body['groupByRowFields']) + list(body.get('groupByColFields') or [])
    measures = body['aggregateFields']
    groups = {}
    for fact in selected:
        groups.setdefault(tuple(fact.get(f) for f in fields), []).append(fact)
    data = []
    for key, items in groups.items():
        row = dict(zip(fields, key))
        row.update(_aggregate(items, measures))
        data.append(row)
    summary = []
    if str(body.get('buildSummary')).lower() == 'true':
        for length in range(0, len(fields) + 1):
            prefixes = {}
            for fact in selected:
                prefixes.setdefault(tuple(fact.get(f) for f in fields[:length]), []).append(fact)
            for key, items in prefixes.items():
                summary.append([dict(zip(fields[:length], key)), _aggregate(items, measures)])
    return {'data': data, 'summary': summary}


class FakeSession:
    """Сессия iiko для core.olap_client.set_session_factory(lambda: FakeSession(...))."""

    log = []

    def __init__(self, facts=None, fail_columns=False, olap_error=None):
        self.facts = facts
        self.fail_columns = fail_columns
        self.olap_error = olap_error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post_olap(self, body):
        FakeSession.log.append(('POST', body))
        if self.olap_error is not None:
            raise self.olap_error
        return olap(body, self.facts)

    def get_json(self, path, params=None):
        FakeSession.log.append(('GET', path, params))
        if path.endswith('/columns'):
            if self.fail_columns:
                from core.olap_client import IikoError
                raise IikoError('нет связи', 502)
            return load_snapshot(params['reportType'])
        if path.endswith('/presets'):
            return PRESETS
        raise AssertionError('путь не поддержан подделкой: ' + path)

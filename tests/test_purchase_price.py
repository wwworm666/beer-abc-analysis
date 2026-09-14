"""
Тесты цены единицы для суммы заказа (core/purchase_price.py).

Self-runnable: `py -3 tests/test_purchase_price.py` (совместимо с pytest).

Модуль чистый: сеть не нужна. Проверяется порядок источников (накладная →
себестоимость остатка → нет цены), выбор самой поздней накладной с суммированием
строк одного дня, пропуск нулевых и битых строк, округление до копеек и один
прогон на реальном кэше storeOperations: цена по накладной у всех товаров положительна.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.purchase_price import (SOURCE_INVOICE, SOURCE_STOCK, invoice_prices, line_sum,  # noqa: E402
                                 resolve_prices, stock_prices)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS_CACHE = os.path.join(ROOT, 'data', 'cache', 'store_operations_report.json')

P1, P2, P3 = 'p1', 'p2', 'p3'
STORE_A, STORE_B = 'store-a', 'store-b'


def _inv(product, amount, total, op_date, store=STORE_A, incoming='true', doc='INCOMING_INVOICE'):
    """Строка storeOperations как в iiko: числа строками с девятью знаками."""
    return {'product': product, 'primaryStore': store, 'amount': f'{amount:.9f}', 'sum': f'{total:.9f}',
            'incoming': incoming, 'documentType': doc, 'date': op_date}


class InvoicePriceTests(unittest.TestCase):
    def test_latest_invoice_wins_and_same_day_lines_are_summed(self):
        ops = [
            _inv(P1, 10, 1000, '01.10.2025'),                    # старая: 100 ₽
            _inv(P1, 4, 480, '20.10.2025', store=STORE_A),        # два склада в один день:
            _inv(P1, 6, 660, '20.10.2025', store=STORE_B),        # (480 + 660) / 10 = 114 ₽
            _inv(P1, 2, 300, '15.10.2025'),                       # между ними: не последняя
        ]
        prices = invoice_prices(ops)
        self.assertEqual(prices[P1]['price'], 114.0)
        self.assertEqual(prices[P1]['source'], SOURCE_INVOICE)
        self.assertEqual(prices[P1]['date'].isoformat(), '2025-10-20')

    def test_skips_non_invoice_zero_and_broken_lines(self):
        ops = [
            _inv(P1, 5, 500, '10.10.2025', doc='INTERNAL_TRANSFER'),        # перемещение — не цена
            _inv(P1, 5, 0, '12.10.2025'),                                   # бонусная строка
            _inv(P1, 0, 500, '12.10.2025'),                                 # нулевое количество
            _inv(P1, 5, 500, '', ),                                         # без даты
            _inv(P1, -5, -500, '13.10.2025', incoming='false'),             # возврат поставщику
            {'product': P1, 'amount': 'abc', 'sum': '10', 'incoming': 'true',
             'documentType': 'INCOMING_INVOICE', 'date': '14.10.2025'},     # мусор в amount
            _inv(P1, 3, 330.333, '11.10.2025'),                             # единственная годная
        ]
        prices = invoice_prices(ops)
        self.assertEqual(prices[P1]['price'], 110.11)                       # 330.333 / 3 до копеек
        self.assertEqual(prices[P1]['date'].isoformat(), '2025-10-11')
        self.assertEqual(invoice_prices([_inv(P1, 1, 1, '10.10.2025')], product_ids=[P2]), {})


class StockPriceTests(unittest.TestCase):
    def test_stock_cost_is_network_wide_and_ignores_empty_or_negative(self):
        balances = [
            {'store': STORE_A, 'product': P1, 'amount': 0, 'sum': 0},
            {'store': STORE_B, 'product': P1, 'amount': 4, 'sum': 1000},
            {'store': STORE_A, 'product': P2, 'amount': -1, 'sum': -50},      # отрицательный остаток
            {'store': STORE_A, 'product': P3, 'amount': 2, 'sum': 0},         # без стоимости
        ]
        prices = stock_prices(balances)
        self.assertEqual(prices[P1], {'price': 250.0, 'source': SOURCE_STOCK, 'date': None})
        self.assertNotIn(P2, prices)
        self.assertNotIn(P3, prices)


class ResolveTests(unittest.TestCase):
    def test_invoice_beats_stock_then_stock_then_none(self):
        ops = [_inv(P1, 10, 1200, '20.10.2025')]
        balances = [{'store': STORE_A, 'product': P1, 'amount': 3, 'sum': 450},
                    {'store': STORE_A, 'product': P2, 'amount': 3, 'sum': 450}]
        prices = resolve_prices(ops, balances, [P1, P2, P3])
        self.assertEqual(prices[P1], {'price': 120.0, 'source': SOURCE_INVOICE, 'date': '2025-10-20'})
        self.assertEqual(prices[P2], {'price': 150.0, 'source': SOURCE_STOCK, 'date': None})
        self.assertIsNone(prices[P3])

    def test_line_sum_rounds_to_kopecks_and_none_without_price(self):
        self.assertEqual(line_sum(110.11, 3), 330.33)
        self.assertEqual(line_sum(0.1, 3), 0.3)
        self.assertIsNone(line_sum(None, 3))
        self.assertEqual(line_sum(10, float('nan')), 0.0)


class RealCacheTests(unittest.TestCase):
    def test_real_store_operations_give_positive_invoice_prices(self):
        if not os.path.exists(OPS_CACHE):
            raise unittest.SkipTest('нет data/cache/store_operations_report.json')
        with open(OPS_CACHE, encoding='utf-8') as f:
            ops = json.load(f)
        prices = invoice_prices(ops)
        self.assertGreater(len(prices), 200)
        self.assertTrue(all(p['price'] > 0 for p in prices.values()))
        # Товар из накладной обязан получить цену, и не старее самой этой накладной
        sample = next(r for r in ops if r.get('documentType') == 'INCOMING_INVOICE')
        pid = sample['product']
        self.assertIn(pid, prices)
        self.assertGreaterEqual(prices[pid]['date'].isoformat(),
                                '-'.join(reversed(sample['date'].split('.'))))
        # Себестоимость остатка как запасной источник даёт цену и без накладных
        balances = [{'store': STORE_A, 'product': pid, 'amount': 2, 'sum': 500}]
        fallback = resolve_prices([], balances, [pid])
        self.assertEqual(fallback[pid], {'price': 250.0, 'source': SOURCE_STOCK, 'date': None})


if __name__ == '__main__':
    unittest.main()

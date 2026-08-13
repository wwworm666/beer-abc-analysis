# -*- coding: utf-8 -*-
"""Юнит-тесты расчёта проливов по кегам (core/draft_kegs.py).

Запуск:
    py -3 -m pytest tests/test_draft_kegs.py -q
    py -3 tests/test_draft_kegs.py        (без pytest)

Данные синтетические, но формы строк дословно повторяют ответы iiko, проверенные
на живых данных 2026-08-13 (см. docs/draft.md).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.draft_kegs import (
    DraftKegAnalysis,
    MIN_XYZ_WEEKS,
    XYZ_X_MAX_CV,
    XYZ_Y_MAX_CV,
    _cv_percent,
    strip_service_fields,
)

KEG_A = 'keg-aaaa'
KEG_B = 'keg-bbbb'
DISH_A_05 = 'dish-a05'
DISH_A_10 = 'dish-a10'
DISH_B_05 = 'dish-b05'
PET_BOTTLE = 'pet-1l'


def trans(bar, keg_id, day, kind, out=0.0, inc=0.0, cost=0.0, name=None, unit='л'):
    """Строка ответа get_draft_writeoff_report()."""
    return {
        'Account.Name': bar,
        'Product.Id': keg_id,
        'Product.Name': name or f'КЕГ {keg_id}',
        'Product.MeasureUnit': unit,
        'DateTime.DateTyped': day,
        'TransactionType': kind,
        'Amount.Out': out,
        'Amount.In': inc,
        'Sum.Outgoing': cost,
    }


def sale(bar, dish_id, day, portions, revenue, cost, name=None):
    """Строка ответа get_draft_sales_by_dish()."""
    return {
        'Store.Name': bar,
        'DishId': dish_id,
        'DishName': name or dish_id,
        'OpenDate.Typed': day,
        'DishAmountInt': portions,
        'DishDiscountSumInt': revenue,
        'ProductCostBase.ProductCost': cost,
    }


# Техкарта: у литровой позиции кроме кега лежит ПЭТ-бутылка — она не кег и должна
# отсеиваться, потому что её нет среди Product.Id из проводок.
DISH_MAP = {
    DISH_A_05: [[KEG_A, 0.5]],
    DISH_A_10: [[KEG_A, 1.0], [PET_BOTTLE, 1.0]],
    DISH_B_05: [[KEG_B, 0.5]],
}


class TestLiters:
    """Литры берутся только из проводок продажи."""

    def test_sold_liters_from_session_writeoff(self):
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Лиговский', KEG_A, '2026-08-05', 'SESSION_WRITEOFF', out=5.5),
        ]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_liters'] == 15.5, block['total_liters']
        assert block['total_kegs'] == 1

    def test_other_transaction_types_not_counted_as_sold(self):
        """Списания, инвентаризация, приход и перемещения в проливы не попадают."""
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Лиговский', KEG_A, '2026-08-04', 'WRITEOFF', out=2.0),
            trans('Лиговский', KEG_A, '2026-08-04', 'INVENTORY_CORRECTION', out=3.0),
            trans('Лиговский', KEG_A, '2026-08-04', 'INVOICE', inc=30.0),
            trans('Лиговский', KEG_A, '2026-08-04', 'TRANSFER', out=1.0, inc=1.0),
        ]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_liters'] == 10.0
        losses = block['losses']
        assert losses['writeoff'] == 2.0
        assert losses['inventory_net'] == 3.0
        assert losses['invoice_in'] == 30.0
        assert losses['transfer_in'] == 1.0 and losses['transfer_out'] == 1.0

    def test_non_liter_units_ignored(self):
        """В группе «Напитки Розлив» бывают товары в штуках — они не проливы."""
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Лиговский', 'sht-1', '2026-08-04', 'SESSION_WRITEOFF', out=99.0, unit='шт'),
        ]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_liters'] == 10.0

    def test_service_accounts_contribute_nothing(self):
        """У корреспондирующих счетов приход и расход нулевые (проверено на 3,5 мес)."""
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Расход продуктов', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=0.0),
        ]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_liters'] == 10.0
        assert block['total_kegs'] == 1


class TestBarMerge:
    """Сведение баров и фильтр по бару."""

    def _rows(self):
        return [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Варшавская', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=6.0),
            trans('Варшавская', KEG_B, '2026-08-04', 'SESSION_WRITEOFF', out=4.0),
        ]

    def test_all_bars_merge_into_one_row_per_keg(self):
        block = DraftKegAnalysis(self._rows(), [], DISH_MAP,
                                 '2026-08-04', '2026-08-10').build()
        assert block['total_liters'] == 20.0
        assert block['total_kegs'] == 2
        by_name = {k['KegId']: k for k in block['kegs']}
        assert by_name[KEG_A]['TotalLiters'] == 16.0

    def test_single_bar_filter(self):
        block = DraftKegAnalysis(self._rows(), [], DISH_MAP,
                                 '2026-08-04', '2026-08-10').build('Варшавская')
        assert block['total_liters'] == 10.0
        assert block['total_kegs'] == 2

    def test_liters_share_sums_to_100(self):
        block = DraftKegAnalysis(self._rows(), [], DISH_MAP,
                                 '2026-08-04', '2026-08-10').build()
        total = sum(k['LitersSharePercent'] for k in block['kegs'])
        assert abs(total - 100.0) < 1e-9, total


class TestMoney:
    """Деньги приходят из продаж и ложатся на кег через техкарту."""

    def _analysis(self):
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
        ]
        sales = [
            # 20 порций по 0,5 = 10 л; выручка 10000, себестоимость 2500
            sale('Лиговский', DISH_A_05, '2026-08-04', 20, 10000.0, 2500.0),
        ]
        return DraftKegAnalysis(rows, sales, DISH_MAP, '2026-08-04', '2026-08-10')

    def test_revenue_and_portions_attached_to_keg(self):
        block = self._analysis().build()
        keg = block['kegs'][0]
        assert keg['TotalRevenue'] == 10000.0
        assert keg['TotalPortions'] == 20
        assert keg['TotalCost'] == 2500.0

    def test_markup_from_sums_not_mean_of_rows(self):
        """Наценка = (выручка - с/с) / с/с. Дефект аудита 03."""
        block = self._analysis().build()
        keg = block['kegs'][0]
        assert abs(keg['MarkupPercent'] - 300.0) < 1e-9, keg['MarkupPercent']
        assert abs(block['markup_percent'] - 300.0) < 1e-9

    def test_markup_unknown_when_cost_zero(self):
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0)]
        sales = [sale('Лиговский', DISH_A_05, '2026-08-04', 20, 10000.0, 0.0)]
        block = DraftKegAnalysis(rows, sales, DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['kegs'][0]['MarkupPercent'] is None
        # Позиция с неизвестной наценкой не должна ломать ABC
        assert block['kegs'][0]['ABC_Markup'] == 'C'

    def test_price_per_liter_and_avg_portion(self):
        block = self._analysis().build()
        keg = block['kegs'][0]
        assert keg['PricePerLiter'] == 1000.0
        assert keg['AvgPortionLiters'] == 0.5
        assert block['avg_price_per_liter'] == 1000.0
        assert block['avg_portion_liters'] == 0.5

    def test_fractional_portions_preserved(self):
        """DishAmountInt у розлива бывает дробным (0,33). Дефект аудита 10."""
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=0.33)]
        sales = [sale('Лиговский', DISH_A_05, '2026-08-04', 0.33, 200.0, 50.0)]
        block = DraftKegAnalysis(rows, sales, DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_portions'] == 0.33, block['total_portions']

    def test_pet_bottle_item_not_treated_as_keg(self):
        """У литровой позиции в техкарте есть ПЭТ-бутылка: она не кег."""
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=2.0)]
        sales = [sale('Лиговский', DISH_A_10, '2026-08-04', 2, 3000.0, 700.0)]
        block = DraftKegAnalysis(rows, sales, DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_kegs'] == 1
        assert block['kegs'][0]['KegId'] == KEG_A
        assert block['kegs'][0]['TotalRevenue'] == 3000.0

    def test_dish_without_keg_goes_to_diagnostics(self):
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0)]
        sales = [
            sale('Лиговский', DISH_A_05, '2026-08-04', 20, 10000.0, 2500.0),
            sale('Лиговский', 'dish-unknown', '2026-08-04', 3, 900.0, 200.0, name='Сет'),
        ]
        block = DraftKegAnalysis(rows, sales, DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_revenue'] == 10000.0
        assert len(block['unmapped_dishes']) == 1
        assert block['unmapped_dishes'][0]['DishName'] == 'Сет'
        assert block['unmapped_dishes'][0]['Revenue'] == 900.0

    def test_dish_on_two_kegs_split_proportionally_to_liters(self):
        """Страховка на случай смены техкарты внутри периода."""
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=30.0),
            trans('Лиговский', KEG_B, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
        ]
        dish_map = {'dish-mixed': [[KEG_A, 0.5], [KEG_B, 0.5]]}
        sales = [sale('Лиговский', 'dish-mixed', '2026-08-04', 80, 40000.0, 10000.0)]
        block = DraftKegAnalysis(rows, sales, dish_map, '2026-08-04', '2026-08-10').build()
        by_id = {k['KegId']: k for k in block['kegs']}
        assert abs(by_id[KEG_A]['TotalRevenue'] - 30000.0) < 1e-9
        assert abs(by_id[KEG_B]['TotalRevenue'] - 10000.0) < 1e-9
        assert abs(block['total_revenue'] - 40000.0) < 1e-9


class TestRevenueShareAndABC:
    """Своя доля выручки vs накопленный процент. Дефект аудита 02."""

    def _block(self):
        rows, sales, dish_map = [], [], {}
        # Три кега с выручкой 800 / 150 / 50 -> A / B / C по накопленной доле
        for index, (keg, revenue) in enumerate(
                [('keg-1', 800.0), ('keg-2', 150.0), ('keg-3', 50.0)]):
            dish = f'dish-{index}'
            rows.append(trans('Лиговский', keg, '2026-08-04', 'SESSION_WRITEOFF',
                              out=revenue / 100))
            sales.append(sale('Лиговский', dish, '2026-08-04', 10, revenue, revenue / 4))
            dish_map[dish] = [[keg, 0.5]]
        return DraftKegAnalysis(rows, sales, dish_map, '2026-08-04', '2026-08-10').build()

    def test_own_share_sums_to_100(self):
        block = self._block()
        total = sum(k['RevenueSharePercent'] for k in block['kegs'])
        assert abs(total - 100.0) < 1e-9, total

    def test_own_share_is_not_cumulative(self):
        block = self._block()
        top = max(block['kegs'], key=lambda k: k['TotalRevenue'])
        assert abs(top['RevenueSharePercent'] - 80.0) < 1e-9
        assert abs(top['RevenueCumulativePercent'] - 80.0) < 1e-9
        last = min(block['kegs'], key=lambda k: k['TotalRevenue'])
        assert abs(last['RevenueSharePercent'] - 5.0) < 1e-9
        assert abs(last['RevenueCumulativePercent'] - 100.0) < 1e-9

    def test_abc_letters_by_pareto(self):
        block = self._block()
        letters = {k['TotalRevenue']: k['ABC_Revenue'] for k in block['kegs']}
        assert letters[800.0] == 'A'
        assert letters[150.0] == 'B'
        assert letters[50.0] == 'C'

    def test_abc_combined_is_three_letters(self):
        block = self._block()
        for keg in block['kegs']:
            assert len(keg['ABC_Combined']) == 3, keg['ABC_Combined']


class TestXYZ:
    """XYZ считается только при достатке недель. Дефекты аудита 01, 04, 05."""

    @staticmethod
    def _rows_for_weeks(weekly_liters, bar='Лиговский', keg=KEG_A, start_day=4):
        """Продажи по одной на каждую неделю периода, начиная с 2026-08-04."""
        from datetime import date, timedelta
        rows = []
        base = date(2026, 8, start_day)
        for index, liters in enumerate(weekly_liters):
            day = (base + timedelta(days=index * 7)).isoformat()
            rows.append(trans(bar, keg, day, 'SESSION_WRITEOFF', out=liters))
        return rows

    def test_no_xyz_on_single_week(self):
        """Период по умолчанию — одна неделя: категорию не присваиваем."""
        rows = self._rows_for_weeks([10.0])
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['xyz_available'] is False
        assert block['xyz_buckets'] == 1
        assert block['kegs'][0]['XYZ_Category'] is None
        assert block['kegs'][0]['CoefficientOfVariation'] is None

    def test_no_xyz_on_two_weeks(self):
        rows = self._rows_for_weeks([10.0, 12.0])
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-17').build()
        assert block['xyz_buckets'] == 2
        assert block['xyz_available'] is False
        assert block['kegs'][0]['XYZ_Category'] is None

    def test_xyz_from_three_weeks(self):
        rows = self._rows_for_weeks([10.0, 12.0, 11.0])
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-24').build()
        assert block['xyz_buckets'] == MIN_XYZ_WEEKS
        assert block['xyz_available'] is True
        keg = block['kegs'][0]
        assert keg['XYZ_Category'] == 'X'
        assert keg['CoefficientOfVariation'] is not None

    def test_single_position_is_not_forced_to_z(self):
        """Одна позиция в разрезе с ровными продажами — это X, а не Z.

        Так ломались перцентили: при единственной строке ранг всегда 100%.
        """
        rows = self._rows_for_weeks([10.0, 10.0, 10.0])
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-24').build()
        assert block['total_kegs'] == 1
        assert block['kegs'][0]['CoefficientOfVariation'] == 0.0
        assert block['kegs'][0]['XYZ_Category'] == 'X'

    def test_thresholds_are_absolute_not_relative(self):
        """Категория зависит только от своего CV, а не от соседей по таблице."""
        alone = DraftKegAnalysis(self._rows_for_weeks([10.0, 14.0, 6.0]), [], DISH_MAP,
                                 '2026-08-04', '2026-08-24').build()['kegs'][0]
        rows = self._rows_for_weeks([10.0, 14.0, 6.0], keg='keg-same')
        rows += self._rows_for_weeks([10.0, 10.0, 10.0], keg='keg-flat')
        rows += self._rows_for_weeks([20.0, 1.0, 1.0], keg='keg-spiky')
        together = {k['KegId']: k for k in DraftKegAnalysis(
            rows, [], DISH_MAP, '2026-08-04', '2026-08-24').build()['kegs']}
        assert together['keg-same']['XYZ_Category'] == alone['XYZ_Category']
        assert abs(together['keg-same']['CoefficientOfVariation']
                   - alone['CoefficientOfVariation']) < 1e-9

    def test_stable_beats_unstable(self):
        """Ровные продажи получают X, рваные — Z, середина — Y."""
        rows = []
        rows += self._rows_for_weeks([10.0, 10.0, 10.0], keg='keg-stable')
        rows += self._rows_for_weeks([20.0, 1.0, 1.0], keg='keg-spiky')
        rows += self._rows_for_weeks([10.0, 15.0, 5.0], keg='keg-middle')
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-24').build()
        cats = {k['KegId']: (k['XYZ_Category'], round(k['CoefficientOfVariation'], 1))
                for k in block['kegs']}
        assert cats['keg-stable'][0] == 'X', cats
        assert cats['keg-spiky'][0] == 'Z', cats
        assert cats['keg-middle'][0] == 'Y', cats
        assert cats['keg-stable'][1] <= XYZ_X_MAX_CV
        assert cats['keg-spiky'][1] > XYZ_Y_MAX_CV

    def test_weeks_without_sales_excluded_from_cv(self):
        """Недели, когда кега не было на кране, в CV не входят.

        Ротация кранов иначе делала бы Z каждую сезонную позицию: за 3,5 месяца из
        71 кега все 14 недель продавались только 12.
        """
        rows = self._rows_for_weeks([10.0, 10.0, 10.0], keg='keg-short')
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-09-14').build()
        keg = block['kegs'][0]
        assert block['xyz_buckets'] == 6
        assert keg['WeeksWithSales'] == 3
        assert keg['WeeksInPeriod'] == 6
        assert keg['CoefficientOfVariation'] == 0.0
        assert keg['XYZ_Category'] == 'X'

    def test_too_few_active_weeks_gives_no_category(self):
        """Две недели на кране — статистики нет, ставим прочерк."""
        rows = self._rows_for_weeks([10.0, 10.0], keg='keg-two')
        rows += self._rows_for_weeks([5.0, 5.0, 5.0], keg='keg-three')
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-09-14').build()
        by_id = {k['KegId']: k for k in block['kegs']}
        assert by_id['keg-two']['XYZ_Category'] is None
        assert by_id['keg-two']['CoefficientOfVariation'] is None
        assert by_id['keg-two']['WeeksWithSales'] == 2
        assert by_id['keg-three']['XYZ_Category'] == 'X'

    def test_cv_ignores_partial_tail_week(self):
        """Огрызок недели в CV не попадает: 10 дней -> одна полная корзина."""
        rows = self._rows_for_weeks([10.0, 3.0])
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-13').build()
        assert block['xyz_buckets'] == 1
        assert block['kegs'][0]['XYZ_Category'] is None

    def test_cv_is_bar_independent(self):
        """Разброс между барами не должен влиять на CV. Дефект аудита 05."""
        rows = []
        for bar, split in (('Лиговский', 8.0), ('Варшавская', 2.0)):
            rows += self._rows_for_weeks([split, split, split], bar=bar)
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-24').build()
        keg = block['kegs'][0]
        assert keg['TotalLiters'] == 30.0
        assert keg['CoefficientOfVariation'] == 0.0, keg['CoefficientOfVariation']
        assert keg['XYZ_Category'] == 'X'


class TestWeeklyRate:
    """Литров в неделю — по длине периода. Дефект аудита 04."""

    def test_seven_day_period_is_one_week(self):
        """7 дней со вторника раньше давали 2 календарные недели и деление вдвое."""
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=243.03)]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['period']['days'] == 7
        assert block['period']['weeks'] == 1.0
        assert abs(block['kegs'][0]['AvgLitersPerWeek'] - 243.03) < 1e-9

    def test_fourteen_day_period_halves_the_rate(self):
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=200.0)]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-17').build()
        assert block['period']['days'] == 14
        assert abs(block['kegs'][0]['AvgLitersPerWeek'] - 100.0) < 1e-9


class TestLosses:
    """Баланс кегов и доли потерь."""

    def _block(self):
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'INVOICE', inc=100.0),
            trans('Лиговский', KEG_A, '2026-08-05', 'SESSION_WRITEOFF', out=60.0),
            trans('Лиговский', KEG_A, '2026-08-05', 'WRITEOFF', out=3.0),
            trans('Лиговский', KEG_A, '2026-08-06', 'INVENTORY_CORRECTION', out=8.0, inc=2.0),
            trans('Лиговский', KEG_A, '2026-08-07', 'TRANSFER', out=5.0, inc=1.0),
        ]
        return DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()

    def test_balance_formula(self):
        losses = self._block()['losses']
        assert losses['inventory_net'] == 6.0
        # 100 + 1 - 60 - 3 - 6 - 5 = 27
        assert abs(losses['balance'] - 27.0) < 1e-9, losses['balance']

    def test_loss_shares_of_sold(self):
        losses = self._block()['losses']
        assert abs(losses['writeoff_percent_of_sold'] - 5.0) < 1e-9
        assert abs(losses['inventory_percent_of_sold'] - 10.0) < 1e-9

    def test_by_keg_lists_only_kegs_with_losses(self):
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Лиговский', KEG_B, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Лиговский', KEG_B, '2026-08-04', 'WRITEOFF', out=1.0),
        ]
        losses = DraftKegAnalysis(rows, [], DISH_MAP,
                                 '2026-08-04', '2026-08-10').build()['losses']
        assert [k['KegName'] for k in losses['by_keg']] == [f'КЕГ {KEG_B}']

    def test_keg_with_losses_but_no_sales_not_in_main_table(self):
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
            trans('Лиговский', KEG_B, '2026-08-04', 'WRITEOFF', out=4.0),
        ]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert [k['KegId'] for k in block['kegs']] == [KEG_A]
        assert block['losses']['writeoff'] == 4.0


class TestEdgeCases:
    def test_empty_input(self):
        block = DraftKegAnalysis([], [], {}, '2026-08-04', '2026-08-10').build()
        assert block['total_liters'] == 0
        assert block['kegs'] == []
        assert block['markup_percent'] is None
        assert block['avg_price_per_liter'] == 0.0

    def test_none_amounts_are_zero(self):
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=None)]
        rows[0]['Amount.Out'] = None
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert block['total_liters'] == 0

    def test_bad_dates_rejected(self):
        try:
            DraftKegAnalysis([], [], {}, 'не дата', '2026-08-10')
        except ValueError:
            return
        raise AssertionError('ожидали ValueError на неразобранной дате')

    def test_service_fields_stripped(self):
        rows = [trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=1.0)]
        block = strip_service_fields(
            DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build())
        assert '_buckets' not in block['kegs'][0]

    def test_sorted_by_liters_desc(self):
        rows = [
            trans('Лиговский', KEG_A, '2026-08-04', 'SESSION_WRITEOFF', out=5.0),
            trans('Лиговский', KEG_B, '2026-08-04', 'SESSION_WRITEOFF', out=15.0),
        ]
        block = DraftKegAnalysis(rows, [], DISH_MAP, '2026-08-04', '2026-08-10').build()
        assert [k['KegId'] for k in block['kegs']] == [KEG_B, KEG_A]

    def test_cv_helper(self):
        assert _cv_percent([10, 10, 10]) == 0.0
        assert _cv_percent([10]) is None
        assert _cv_percent([0, 0]) is None
        assert abs(_cv_percent([8, 12]) - 28.284271247461902) < 1e-9


def run_tests():
    """Прогон без pytest."""
    import traceback
    passed = failed = 0
    errors = []
    for name, obj in sorted(globals().items()):
        if not (name.startswith('Test') and isinstance(obj, type)):
            continue
        print(f"\n{name}")
        for method_name in sorted(dir(obj)):
            if not method_name.startswith('test_'):
                continue
            instance = obj()
            if hasattr(instance, 'setup_method'):
                instance.setup_method(method_name)
            try:
                getattr(instance, method_name)()
                print(f"  [OK] {method_name}")
                passed += 1
            except Exception:
                print(f"  [FAIL] {method_name}")
                print('       ' + traceback.format_exc().strip().splitlines()[-1])
                failed += 1
                errors.append((f'{name}.{method_name}', traceback.format_exc()))

    print(f"\n{'=' * 60}\nRESULTS: {passed} passed, {failed} failed\n{'=' * 60}")
    for name, tb in errors:
        print(f"\n--- {name} ---\n{tb}")
    return failed == 0


if __name__ == '__main__':
    sys.exit(0 if run_tests() else 1)

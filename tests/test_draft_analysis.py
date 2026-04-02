# -*- coding: utf-8 -*-
"""
Unit-тесты для модуля анализа разливного пива (draft_analysis.py)

Запуск:
    python -m pytest tests/test_draft_analysis.py -v

Или без pytest:
    python tests/test_draft_analysis.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from core.draft_analysis import DraftAnalysis


class TestExtractBeerInfo:
    """Тесты функции extract_beer_info()"""

    def setup_method(self):
        """Создание экземпляра анализатора для тестов"""
        self.analyzer = DraftAnalysis(pd.DataFrame())

    def test_fractional_liters_comma(self):
        """Формат: дробные литры с запятой (0,5)"""
        name, volume = self.analyzer.extract_beer_info("FestHaus Helles (0,5)")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "helles" in name.lower(), f"Expected 'helles' in '{name}'"

    def test_fractional_liters_dot(self):
        """Формат: дробные литры с точкой (0.5)"""
        name, volume = self.analyzer.extract_beer_info("FestHaus Helles (0.5)")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "helles" in name.lower(), f"Expected 'helles' in '{name}'"

    def test_whole_liters(self):
        """Формат: целые литры (2)"""
        name, volume = self.analyzer.extract_beer_info("Beer (2)")
        assert volume == 2.0, f"Expected 2.0, got {volume}"
        assert "beer" in name.lower(), f"Expected 'beer' in '{name}'"

    def test_milliliters(self):
        """Формат: миллилитры (500мл)"""
        name, volume = self.analyzer.extract_beer_info("Beer (500ml)")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "beer" in name.lower(), f"Expected 'beer' in '{name}'"

    def test_milliliters_english(self):
        """Формат: миллилитры на английском (500ml)"""
        name, volume = self.analyzer.extract_beer_info("Import Beer (500ml)")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "beer" in name.lower(), f"Expected 'beer' in '{name}'"

    def test_liters_with_letter(self):
        """Формат: литры с буквой (0.5л)"""
        name, volume = self.analyzer.extract_beer_info("Beer (0.5l)")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "beer" in name.lower(), f"Expected 'beer' in '{name}'"

    def test_with_takeaway(self):
        """Формат: с указанием "с собой" """
        name, volume = self.analyzer.extract_beer_info("Oktoberfest (1.0) take away")
        assert volume == 1.0, f"Expected 1.0, got {volume}"
        assert "oktoberfest" in name.lower(), f"Expected 'oktoberfest' in '{name}'"
        assert "take away" not in name.lower(), f"Expected 'take away' removed from '{name}'"

    def test_no_brackets_liters(self):
        """Формат: БЕЗ скобок - литры (Пиво 0.5л)"""
        name, volume = self.analyzer.extract_beer_info("Beer 0.5l")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "beer" in name.lower(), f"Expected 'beer' in '{name}'"

    def test_no_brackets_milliliters(self):
        """Формат: БЕЗ скобок - миллилитры (Пиво 500мл)"""
        name, volume = self.analyzer.extract_beer_info("FestHaus 500ml")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "fest" in name.lower(), f"Expected 'fest' in '{name}'"

    def test_no_brackets_with_space(self):
        """Формат: БЕЗ скобок с пробелом (0,5 л)"""
        name, volume = self.analyzer.extract_beer_info("Beer 0.5 l")
        assert volume == 0.5, f"Expected 0.5, got {volume}"
        assert "beer" in name.lower(), f"Expected 'beer' in '{name}'"

    def test_unrecognized_uses_heuristic(self):
        """Не распознано → эвристика (не 0.0!)"""
        name, volume = self.analyzer.extract_beer_info("Unknown Beer")
        assert volume == 0.5, f"Expected 0.5 (heuristic), got {volume}"

    def test_unrecognized_with_05_in_name(self):
        """Эвристика: ищем "0.5" в названии"""
        name, volume = self.analyzer.extract_beer_info("Light Beer 0.5")
        assert volume == 0.5, f"Expected 0.5, got {volume}"

    def test_unrecognized_with_500_in_name(self):
        """Эвристика: ищем "500" в названии"""
        name, volume = self.analyzer.extract_beer_info("Dark Beer 500")
        assert volume == 0.5, f"Expected 0.5, got {volume}"

    def test_double_spaces(self):
        """Двойные пробелы в названии"""
        name, volume = self.analyzer.extract_beer_info("FestHaus  Helles (0.5)")
        assert "  " not in name, f"Expected double spaces removed, got '{name}'"

    def test_hyphen_in_name(self):
        """Дефис в названии"""
        name, volume = self.analyzer.extract_beer_info("FestHaus-Helles (0.5)")
        assert "helles" in name.lower(), f"Expected 'helles' in '{name}'"

    def test_quarter_liter(self):
        """Объем 0.25л"""
        name, volume = self.analyzer.extract_beer_info("Black Ship (0.25)")
        assert volume == 0.25, f"Expected 0.25, got {volume}"
        assert "ship" in name.lower(), f"Expected 'ship' in '{name}'"

    def test_one_liter(self):
        """Объем 1.0л"""
        name, volume = self.analyzer.extract_beer_info("FestHaus Weizen (1.0)")
        assert volume == 1.0, f"Expected 1.0, got {volume}"
        assert "weizen" in name.lower(), f"Expected 'weizen' in '{name}'"


class TestPrepareDraftData:
    """Тесты функции prepare_draft_data()"""

    def setup_method(self):
        """Создание тестовых данных"""
        self.test_df = pd.DataFrame({
            'DishName': [
                'ФестХаус Хеллес (0,5)',
                'ФестХаус  Хеллес (0,5)',  # двойной пробел
                'Блек Шип (0,25)',
                'Пиво (500мл)',
                'Неизвестное пиво',  # эвристика
            ],
            'DishAmountInt': [10, 5, 20, 100, 50],
            'Store.Name': ['Бар1'] * 5,
            'OpenDate.Typed': ['2024-01-01'] * 5,
        })

    def test_two_step_normalization(self):
        """Двухэтапная нормализация: BeerNameOriginal и BeerNameNorm"""
        analyzer = DraftAnalysis(self.test_df.copy())
        prepared = analyzer.prepare_draft_data()
        assert 'BeerNameOriginal' in prepared.columns
        assert 'BeerNameNorm' in prepared.columns

    def test_beer_name_original_preserves_case(self):
        """BeerNameOriginal сохраняет регистр для маппинга"""
        analyzer = DraftAnalysis(self.test_df.copy())
        prepared = analyzer.prepare_draft_data()
        # Оригинальное название должно сохранять регистр (не все lowercase)
        assert prepared['BeerNameOriginal'].iloc[0] != prepared['BeerNameNorm'].iloc[0]

    def test_beer_name_norm_lowercase(self):
        """BeerNameNorm: lowercase для группировки"""
        analyzer = DraftAnalysis(self.test_df.copy())
        prepared = analyzer.prepare_draft_data()
        assert all(prepared['BeerNameNorm'] == prepared['BeerNameNorm'].str.lower())

    def test_normalization_double_spaces_removed(self):
        """Нормализация: двойные пробелы удалены"""
        analyzer = DraftAnalysis(self.test_df.copy())
        prepared = analyzer.prepare_draft_data()
        assert '  ' not in ' '.join(prepared['BeerNameNorm'])

    def test_no_data_loss_on_unrecognized(self):
        """НЕТ потери данных для нераспознанных названий"""
        analyzer = DraftAnalysis(self.test_df.copy())
        prepared = analyzer.prepare_draft_data()
        # Все 5 записей должны остаться (эвристика вместо удаления)
        assert len(prepared) == 5

    def test_volume_calculation(self):
        """Расчет VolumeInLiters"""
        analyzer = DraftAnalysis(self.test_df.copy())
        prepared = analyzer.prepare_draft_data()
        # Проверка для первой записи: 10 порций * 0.5л = 5л
        first_row = prepared.iloc[0]
        assert first_row['VolumeInLiters'] == 10 * 0.5

    def test_week_column_added(self):
        """Колонка Week добавлена"""
        analyzer = DraftAnalysis(self.test_df.copy())
        prepared = analyzer.prepare_draft_data()
        assert 'Week' in prepared.columns


class TestBeerSharePercent:
    """Тесты корректности расчета BeerSharePercent"""

    def setup_method(self):
        """Создание тестовых данных для нескольких баров"""
        self.test_df = pd.DataFrame({
            'DishName': [
                'Пиво А (0,5)', 'Пиво Б (0,5)', 'Пиво В (0,5)',
                'Пиво Г (0,5)', 'Пиво Д (0,5)',
            ],
            'DishAmountInt': [100, 50, 50, 80, 20],  # 200л для Бар1, 100л для Бар2
            'Store.Name': ['Бар1', 'Бар1', 'Бар1', 'Бар2', 'Бар2'],
            'OpenDate.Typed': ['2024-01-01'] * 5,
        })

    def test_beer_share_percent_single_bar(self):
        """BeerSharePercent для одного бара = 100% в сумме"""
        analyzer = DraftAnalysis(self.test_df.copy())
        summary = analyzer.get_beer_summary(bar_name='Бар1')
        total_percent = summary['BeerSharePercent'].sum()
        assert 99.9 <= total_percent <= 100.1, f"Сумма процентов = {total_percent}"

    def test_beer_share_percent_values(self):
        """BeerSharePercent: правильные значения для Бар1"""
        analyzer = DraftAnalysis(self.test_df.copy())
        summary = analyzer.get_beer_summary(bar_name='Бар1')

        # Пиво А: 100 * 0.5 = 50л из 200л = 50%
        # Используем BeerNameNorm для поиска (lowercase)
        пиво_а = summary[summary['BeerNameNorm'] == 'пиво а']
        if len(пиво_а) > 0:
            assert 49.9 <= пиво_а['BeerSharePercent'].values[0] <= 50.1
        else:
            # Альтернативно: ищем по оригинальному названию
            пиво_а = summary[summary['BeerName'].str.lower() == 'пиво а']
            assert 49.9 <= пиво_а['BeerSharePercent'].values[0] <= 50.1


class TestCleanBeerName:
    """Тесты функции _clean_beer_name()"""

    def setup_method(self):
        self.analyzer = DraftAnalysis(pd.DataFrame())

    def test_removes_s_soboy(self):
        """Удаление "с собой" """
        result = self.analyzer._clean_beer_name("ФестХаус (0,5) с собой")
        assert "с собой" not in result

    def test_removes_to_go(self):
        """Удаление "to go" """
        result = self.analyzer._clean_beer_name("Beer (0.5) to go")
        assert "to go" not in result

    def test_removes_take_away(self):
        """Удаление "take away" """
        result = self.analyzer._clean_beer_name("Beer (0.5) take away")
        assert "take away" not in result

    def test_removes_double_spaces(self):
        """Удаление двойных пробелов"""
        result = self.analyzer._clean_beer_name("ФестХаус  Хеллес")
        assert "  " not in result


def run_tests():
    """Запуск тестов без pytest"""
    import traceback

    test_classes = [
        TestExtractBeerInfo,
        TestPrepareDraftData,
        TestBeerSharePercent,
        TestCleanBeerName,
    ]

    passed = 0
    failed = 0
    errors = []

    for test_class in test_classes:
        instance = test_class()
        print(f"\n{'='*60}")
        print(f"Tests: {test_class.__name__}")
        print(f"{'='*60}")

        for method_name in dir(instance):
            if method_name.startswith('test_'):
                try:
                    # Вызов setup_method если есть
                    if hasattr(instance, 'setup_method'):
                        instance.setup_method()

                    # Вызов теста
                    method = getattr(instance, method_name)
                    method()
                    print(f"  [PASS] {method_name}")
                    passed += 1

                except AssertionError as e:
                    print(f"  [FAIL] {method_name}: {str(e).encode('utf-8', errors='replace').decode('cp1251', errors='replace')}")
                    failed += 1
                    errors.append((method_name, str(e)))

                except Exception as e:
                    error_msg = traceback.format_exc().encode('utf-8', errors='replace').decode('cp1251', errors='replace')
                    print(f"  [ERROR] {method_name}: {error_msg}")
                    failed += 1
                    errors.append((method_name, error_msg))

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    if errors:
        print("\nERRORS:")
        for name, error in errors:
            print(f"  - {name}: {error[:100]}...")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

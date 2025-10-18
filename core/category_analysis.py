import pandas as pd
import numpy as np

class CategoryAnalysis:
    """Класс для ABC/XYZ анализа по категориям (стилям) пива"""

    def __init__(self, aggregated_data, original_dataframe=None):
        """
        aggregated_data: DataFrame с агрегированными данными (из BeerDataProcessor.aggregate_by_beer_and_bar)
        original_dataframe: DataFrame с исходными данными для XYZ анализа (опционально)
        """
        self.data = aggregated_data.copy()

        # Заменяем пустые (NaN/None) значения Style на "Без категории (Ф)"
        self.data['Style'] = self.data['Style'].fillna('Без категории (Ф)')

        self.original_df = original_dataframe.copy() if original_dataframe is not None else None

    def get_categories(self, bar_name=None):
        """
        Получить список всех категорий (стилей) пива

        bar_name: если указан, фильтрует по бару
        Возвращает: list уникальных стилей
        """
        df = self.data.copy()

        if bar_name:
            df = df[df['Bar'] == bar_name]

        # Получаем уникальные стили (теперь пустые значения уже заменены на "Без категории (Ф)")
        # Сортируем по количеству фасовок в категории (от большего к меньшему)
        category_counts = df['Style'].value_counts()
        categories = list(category_counts.index)

        return categories

    def analyze_category(self, category_name, bar_name=None):
        """
        Провести ABC анализ для конкретной категории

        category_name: название стиля пива
        bar_name: если указан, фильтрует по бару

        Возвращает: dict с результатами анализа
        """
        df = self.data.copy()

        # Фильтруем по категории
        df = df[df['Style'] == category_name]

        # Фильтруем по бару если указан
        if bar_name:
            df = df[df['Bar'] == bar_name]

        if len(df) == 0:
            return None

        # Рассчитываем ABC категории для каждой метрики
        df = df.copy()

        # 1-я буква: ABC по выручке
        df['ABC_Revenue'] = self._calculate_abc_category(
            df['TotalRevenue'],
            ascending=False
        )

        # 2-я буква: ABC по % наценки
        df['ABC_Markup'] = self._calculate_abc_category(
            df['AvgMarkupPercent'],
            ascending=False
        )

        # 3-я буква: ABC по марже в рублях
        df['ABC_Margin'] = self._calculate_abc_category(
            df['TotalMargin'],
            ascending=False
        )

        # Объединяем три буквы
        df['ABC_Combined'] = (
            df['ABC_Revenue'] +
            df['ABC_Markup'] +
            df['ABC_Margin']
        )

        # Статистика по ABC
        abc_stats = df['ABC_Combined'].value_counts().to_dict()

        # Общие показатели
        total_revenue = float(df['TotalRevenue'].sum())
        total_qty = float(df['TotalQty'].sum())
        total_margin = float(df['TotalMargin'].sum())
        avg_markup = float(df['AvgMarkupPercent'].mean())

        return {
            'category': category_name,
            'bar': bar_name,
            'total_beers': int(len(df)),
            'total_revenue': total_revenue,
            'total_qty': total_qty,
            'total_margin': total_margin,
            'avg_markup_percent': avg_markup,
            'abc_stats': abc_stats,
            'beers': df.to_dict('records')
        }

    def analyze_all_categories(self, bar_name=None):
        """
        Провести анализ для всех категорий

        bar_name: если указан, фильтрует по бару

        Возвращает: dict {category_name: analysis_result}
        """
        categories = self.get_categories(bar_name)
        results = {}

        print(f"\n{'='*60}")
        print(f"ABC АНАЛИЗ ПО КАТЕГОРИЯМ ПИВА")
        if bar_name:
            print(f"   Бар: {bar_name}")
        print(f"{'='*60}")

        for category in categories:
            print(f"\nАнализ категории: {category}")
            result = self.analyze_category(category, bar_name)

            if result:
                results[category] = result
                print(f"   Фасовок: {result['total_beers']}")
                print(f"   Выручка: {result['total_revenue']:,.0f} руб")
                print(f"   Топ-3 ABC: {list(result['abc_stats'].keys())[:3]}")

        print(f"\n{'='*60}")
        print(f"Проанализировано категорий: {len(results)}")

        return results

    def get_category_summary(self, bar_name=None):
        """
        Получить краткую сводку по всем категориям

        bar_name: если указан, фильтрует по бару

        Возвращает: DataFrame с сводкой по категориям
        """
        df = self.data.copy()

        if bar_name:
            df = df[df['Bar'] == bar_name]

        # Группируем по стилю
        summary = df.groupby('Style').agg({
            'Beer': 'count',              # Количество фасовок
            'TotalQty': 'sum',            # Общее количество
            'TotalRevenue': 'sum',        # Общая выручка
            'TotalMargin': 'sum',         # Общая маржа
            'AvgMarkupPercent': 'mean'    # Средняя наценка
        }).reset_index()

        # Переименуем столбцы
        summary.columns = [
            'Category', 'BeersCount', 'TotalQty',
            'TotalRevenue', 'TotalMargin', 'AvgMarkupPercent'
        ]

        # Сортируем по выручке
        summary = summary.sort_values('TotalRevenue', ascending=False)

        # Добавляем процент от общей выручки
        total_revenue = summary['TotalRevenue'].sum()
        summary['RevenuePercent'] = (summary['TotalRevenue'] / total_revenue * 100).round(2)

        # Добавляем накопительный процент
        summary['CumulativePercent'] = summary['RevenuePercent'].cumsum().round(2)

        # Определяем ABC категорию для самой категории
        summary['ABC_Category'] = 'C'
        summary.loc[summary['CumulativePercent'] <= 80, 'ABC_Category'] = 'A'
        summary.loc[
            (summary['CumulativePercent'] > 80) & (summary['CumulativePercent'] <= 95),
            'ABC_Category'
        ] = 'B'

        return summary

    def _calculate_abc_category(self, series, ascending=False):
        """
        Рассчитать ABC категорию для серии значений

        series: pandas Series с числовыми значениями
        ascending: True если меньше = лучше

        Возвращает: Series с категориями A, B, C
        """
        # Сортируем по значению
        sorted_series = series.sort_values(ascending=ascending)

        # Вычисляем накопленный процент
        cumsum = sorted_series.cumsum()
        total = sorted_series.sum()

        if total == 0:
            return pd.Series('C', index=series.index)

        cumulative_percent = (cumsum / total) * 100

        # Присваиваем категории
        categories = pd.Series('C', index=series.index)

        # A = первые 80% от суммы
        categories[cumulative_percent <= 80] = 'A'
        # B = следующие 15% (от 80% до 95%)
        categories[(cumulative_percent > 80) & (cumulative_percent <= 95)] = 'B'
        # C = последние 5% (от 95% до 100%)
        categories[cumulative_percent > 95] = 'C'

        return categories

    def add_xyz_to_category_analysis(self, category_result, xyz_analyzer, bar_name):
        """
        Добавить XYZ анализ к результатам анализа категории

        category_result: результат из analyze_category()
        xyz_analyzer: экземпляр XYZAnalysis
        bar_name: название бара

        Возвращает: обновленный category_result с XYZ данными
        """
        if not category_result or not xyz_analyzer or not bar_name:
            return category_result

        # Получаем XYZ анализ для бара
        xyz_df = xyz_analyzer.perform_xyz_analysis_by_bar(bar_name)

        if xyz_df.empty:
            return category_result

        # Добавляем XYZ данные к каждому пиву
        beers_with_xyz = []
        xyz_stats = {}

        for beer in category_result['beers']:
            beer_name = beer['Beer']
            xyz_row = xyz_df[xyz_df['Beer'] == beer_name]

            if not xyz_row.empty:
                beer['XYZ_Category'] = xyz_row.iloc[0]['XYZ_Category']
                beer['CoefficientOfVariation'] = xyz_row.iloc[0]['CoefficientOfVariation']
                beer['ABCXYZ_Combined'] = beer['ABC_Combined'] + '-' + beer['XYZ_Category']

                # Собираем статистику
                xyz_cat = beer['XYZ_Category']
                xyz_stats[xyz_cat] = xyz_stats.get(xyz_cat, 0) + 1
            else:
                beer['XYZ_Category'] = 'Z'
                beer['CoefficientOfVariation'] = 100
                beer['ABCXYZ_Combined'] = beer['ABC_Combined'] + '-Z'
                xyz_stats['Z'] = xyz_stats.get('Z', 0) + 1

            beers_with_xyz.append(beer)

        category_result['beers'] = beers_with_xyz
        category_result['xyz_stats'] = xyz_stats

        return category_result


# Тестовый запуск
if __name__ == "__main__":
    import json
    from data_processor import BeerDataProcessor

    print("=== Тест анализа по категориям ===\n")

    # Загружаем данные
    with open("beer_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # Обрабатываем
    processor = BeerDataProcessor(data)

    if processor.prepare_dataframe():
        # Агрегируем данные
        agg_data = processor.aggregate_by_beer_and_bar()

        # Создаем анализатор категорий
        cat_analyzer = CategoryAnalysis(agg_data)

        # Получаем сводку по категориям
        print("\nСВОДКА ПО КАТЕГОРИЯМ (все бары):")
        print("="*80)
        summary = cat_analyzer.get_category_summary()
        print(summary.to_string(index=False))

        # Анализ по одному бару
        bar_name = "Большой пр. В.О"
        print(f"\n\nАНАЛИЗ КАТЕГОРИЙ ДЛЯ БАРА: {bar_name}")
        print("="*80)

        results = cat_analyzer.analyze_all_categories(bar_name)

        # Выводим топ-3 категории по выручке
        print(f"\n\nТОП-3 КАТЕГОРИИ ПО ВЫРУЧКЕ ({bar_name}):")
        print("="*80)

        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1]['total_revenue'],
            reverse=True
        )[:3]

        for i, (cat_name, cat_data) in enumerate(sorted_results, 1):
            print(f"\n{i}. {cat_name}")
            print(f"   Выручка: {cat_data['total_revenue']:,.0f} руб")
            print(f"   Фасовок: {cat_data['total_beers']}")
            print(f"   Средняя наценка: {cat_data['avg_markup_percent']*100:.1f}%")
            print(f"   ABC распределение: {cat_data['abc_stats']}")

        # Сохраняем сводку
        summary.to_csv("category_summary.csv", index=False, encoding='utf-8-sig')
        print("\n\nСводка сохранена в: category_summary.csv")

import pandas as pd
import numpy as np

class ABCAnalysis:
    """Класс для ABC анализа (3 буквы)"""
    
    def __init__(self, aggregated_data):
        """
        aggregated_data: DataFrame с агрегированными данными
        Колонки: Bar, Beer, Style, Country, TotalQty, TotalRevenue, TotalCost, AvgMarkupPercent, TotalMargin
        """
        self.data = aggregated_data.copy()
    
    def calculate_abc_category(self, series, ascending=False):
        """
        Рассчитать ABC категорию для серии значений
        
        series: pandas Series с числовыми значениями
        ascending: True если меньше = лучше (для процентов наценки наоборот)
        
        Возвращает: Series с категориями A, B, C
        """
        # Сортируем по значению
        sorted_series = series.sort_values(ascending=ascending)
        
        # Вычисляем накопленный процент
        cumsum = sorted_series.cumsum()
        total = sorted_series.sum()
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
    
    def perform_abc_analysis_by_bar(self, bar_name):
        """
        Выполнить ABC анализ для конкретного бара
        
        Возвращает DataFrame с добавленными столбцами:
        - ABC_Revenue (по выручке)
        - ABC_Markup (по % наценки)
        - ABC_Margin (по марже в рублях)
        - ABC_Combined (три буквы вместе, например "ACA")
        """
        # Фильтруем данные по бару
        bar_data = self.data[self.data['Bar'] == bar_name].copy()
        
        if len(bar_data) == 0:
            print(f"⚠️  Нет данных для бара: {bar_name}")
            return pd.DataFrame()
        
        print(f"\n🔍 ABC анализ для бара: {bar_name}")
        print(f"   Фасовок: {len(bar_data)}")
        
        # 1-я буква: ABC по выручке (больше = лучше, ascending=False)
        bar_data['ABC_Revenue'] = self.calculate_abc_category(
            bar_data['TotalRevenue'], 
            ascending=False
        )
        
        # 2-я буква: ABC по % наценки (больше = лучше, ascending=False)
        bar_data['ABC_Markup'] = self.calculate_abc_category(
            bar_data['AvgMarkupPercent'], 
            ascending=False
        )
        
        # 3-я буква: ABC по марже в рублях (больше = лучше, ascending=False)
        bar_data['ABC_Margin'] = self.calculate_abc_category(
            bar_data['TotalMargin'], 
            ascending=False
        )
        
        # Объединяем три буквы
        bar_data['ABC_Combined'] = (
            bar_data['ABC_Revenue'] + 
            bar_data['ABC_Markup'] + 
            bar_data['ABC_Margin']
        )
        
        # Статистика
        print(f"\n   📊 Распределение по категориям:")
        print(f"      1-я буква (Выручка):")
        print(f"         A: {(bar_data['ABC_Revenue'] == 'A').sum()} шт")
        print(f"         B: {(bar_data['ABC_Revenue'] == 'B').sum()} шт")
        print(f"         C: {(bar_data['ABC_Revenue'] == 'C').sum()} шт")
        
        print(f"\n      2-я буква (% Наценки):")
        print(f"         A: {(bar_data['ABC_Markup'] == 'A').sum()} шт")
        print(f"         B: {(bar_data['ABC_Markup'] == 'B').sum()} шт")
        print(f"         C: {(bar_data['ABC_Markup'] == 'C').sum()} шт")
        
        print(f"\n      3-я буква (Маржа руб):")
        print(f"         A: {(bar_data['ABC_Margin'] == 'A').sum()} шт")
        print(f"         B: {(bar_data['ABC_Margin'] == 'B').sum()} шт")
        print(f"         C: {(bar_data['ABC_Margin'] == 'C').sum()} шт")
        
        # Топ комбинации
        print(f"\n   🏆 Топ-10 комбинаций ABC:")
        top_combinations = bar_data['ABC_Combined'].value_counts().head(10)
        for combo, count in top_combinations.items():
            print(f"      {combo}: {count} фасовок")
        
        return bar_data
    
    def perform_full_analysis(self):
        """
        Выполнить ABC анализ для всех баров
        
        Возвращает: dict {bar_name: DataFrame}
        """
        bars = self.data['Bar'].unique()
        results = {}
        
        print("=" * 60)
        print("🍺 ABC АНАЛИЗ ПО ВСЕМ БАРАМ")
        print("=" * 60)
        
        for bar in bars:
            results[bar] = self.perform_abc_analysis_by_bar(bar)
        
        print("\n" + "=" * 60)
        
        return results


# Тестовый запуск
if __name__ == "__main__":
    print("🧪 Тест ABC анализа\n")
    
    # Загружаем агрегированные данные
    agg_data = pd.read_csv("aggregated_beer_data.csv", encoding='utf-8-sig')
    
    print(f"📊 Загружено {len(agg_data)} записей")
    
    # Создаем анализатор
    analyzer = ABCAnalysis(agg_data)
    
    # Выполняем полный анализ
    results = analyzer.perform_full_analysis()
    
    # Сохраняем результаты для каждого бара
    for bar_name, bar_result in results.items():
        if not bar_result.empty:
            # Убираем недопустимые символы из имени файла
            safe_name = bar_name.replace(" ", "_").replace(".", "")
            filename = f"abc_analysis_{safe_name}.csv"
            bar_result.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"\n💾 Результаты для {bar_name} сохранены в: {filename}")
    
    # Общая статистика по всем барам
    print("\n" + "=" * 60)
    print("📈 ОБЩАЯ СТАТИСТИКА ПО КАТЕГОРИЯМ AAA, ACA и т.д.")
    print("=" * 60)
    
    all_results = pd.concat(results.values(), ignore_index=True)
    
    print("\nТоп-20 комбинаций ABC по всем барам:")
    top_all = all_results['ABC_Combined'].value_counts().head(20)
    for i, (combo, count) in enumerate(top_all.items(), 1):
        print(f"{i:2d}. {combo}: {count:3d} фасовок")
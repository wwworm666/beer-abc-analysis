import pandas as pd
import numpy as np
from collections import defaultdict

class XYZAnalysis:
    """Класс для XYZ анализа (вариация продаж по неделям)"""
    
    def __init__(self, dataframe):
        """
        dataframe: DataFrame с данными (должен содержать YearWeek, DishName, DishAmountInt)
        """
        self.df = dataframe.copy()
    
    def calculate_coefficient_of_variation(self, weekly_sales):
        """
        Вычислить коэффициент вариации
        
        weekly_sales: список продаж по неделям
        Возвращает: коэффициент вариации в процентах
        """
        if len(weekly_sales) < 2:
            return 100  # Если меньше 2 недель - считаем нестабильным
        
        sales_array = np.array(weekly_sales)
        
        # Убираем нулевые значения для более точного расчета
        non_zero_sales = sales_array[sales_array > 0]
        
        if len(non_zero_sales) == 0:
            return 100
        
        mean = np.mean(non_zero_sales)
        
        if mean == 0:
            return 100
        
        std = np.std(non_zero_sales)
        cv = (std / mean) * 100
        
        return cv
    
    def categorize_xyz(self, cv):
        """
        Определить XYZ категорию на основе коэффициента вариации
        
        cv: коэффициент вариации в процентах
        """
        if cv < 10:
            return 'X'  # Стабильный спрос
        elif cv < 25:
            return 'Y'  # Средняя вариация
        else:
            return 'Z'  # Нестабильный спрос
    
    def perform_xyz_analysis_by_bar(self, bar_name, min_weeks=2):
        """
        Выполнить XYZ анализ для конкретного бара
        
        bar_name: название бара
        min_weeks: минимальное количество недель для анализа
        
        Возвращает: DataFrame с XYZ категориями
        """
        # Фильтруем по бару
        bar_data = self.df[self.df['Store.Name'] == bar_name].copy()
        
        if len(bar_data) == 0:
            print(f"⚠️  Нет данных для бара: {bar_name}")
            return pd.DataFrame()
        
        print(f"\n🔍 XYZ анализ для бара: {bar_name}")
        
        # Группируем по фасовке и неделе
        weekly_sales = bar_data.groupby(['DishName', 'YearWeek'])['DishAmountInt'].sum().reset_index()
        
        # Для каждой фасовки считаем вариацию
        results = []
        
        for beer in bar_data['DishName'].unique():
            beer_weekly = weekly_sales[weekly_sales['DishName'] == beer]
            
            # Количество недель с продажами
            weeks_with_sales = len(beer_weekly)
            
            if weeks_with_sales < min_weeks:
                # Если продавалось меньше минимума недель - пропускаем
                continue
            
            # Список продаж по неделям
            sales_list = beer_weekly['DishAmountInt'].tolist()
            
            # Вычисляем коэффициент вариации
            cv = self.calculate_coefficient_of_variation(sales_list)
            
            # Определяем категорию
            xyz_category = self.categorize_xyz(cv)
            
            results.append({
                'Beer': beer,
                'WeeksCount': weeks_with_sales,
                'CoefficientOfVariation': cv,
                'XYZ_Category': xyz_category
            })
        
        result_df = pd.DataFrame(results)
        
        if not result_df.empty:
            print(f"   Проанализировано фасовок: {len(result_df)}")
            print(f"\n   📊 Распределение XYZ:")
            print(f"      X (стабильный): {(result_df['XYZ_Category'] == 'X').sum()} шт")
            print(f"      Y (средний): {(result_df['XYZ_Category'] == 'Y').sum()} шт")
            print(f"      Z (нестабильный): {(result_df['XYZ_Category'] == 'Z').sum()} шт")
        
        return result_df
    
    def get_weekly_sales_chart_data(self, bar_name, beer_name):
        """
        Получить данные для графика продаж по неделям
        
        Возвращает: dict с неделями и продажами
        """
        bar_data = self.df[
            (self.df['Store.Name'] == bar_name) & 
            (self.df['DishName'] == beer_name)
        ].copy()
        
        if bar_data.empty:
            return None
        
        # Группируем по неделям
        weekly = bar_data.groupby('YearWeek')['DishAmountInt'].sum().sort_index()
        
        return {
            'weeks': weekly.index.tolist(),
            'sales': weekly.values.tolist()
        }


# Тестовый запуск
if __name__ == "__main__":
    import json
    from data_processor import BeerDataProcessor
    
    print("🧪 Тест XYZ анализа\n")
    
    # Загружаем данные
    with open("beer_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Обрабатываем
    processor = BeerDataProcessor(data)
    
    if processor.prepare_dataframe():
        # XYZ анализ
        analyzer = XYZAnalysis(processor.df)
        
        # Анализ для одного бара
        xyz_result = analyzer.perform_xyz_analysis_by_bar("Большой пр. В.О")
        
        if not xyz_result.empty:
            print("\n📊 Топ-10 самых стабильных (X):")
            stable = xyz_result[xyz_result['XYZ_Category'] == 'X'].sort_values('CoefficientOfVariation').head(10)
            for i, row in stable.iterrows():
                print(f"   {row['Beer'][:50]}: CV = {row['CoefficientOfVariation']:.1f}%")
            
            print("\n📊 Топ-10 самых нестабильных (Z):")
            unstable = xyz_result[xyz_result['XYZ_Category'] == 'Z'].sort_values('CoefficientOfVariation', ascending=False).head(10)
            for i, row in unstable.iterrows():
                print(f"   {row['Beer'][:50]}: CV = {row['CoefficientOfVariation']:.1f}%")
            
            # Сохраняем
            xyz_result.to_csv("xyz_analysis_test.csv", index=False, encoding='utf-8-sig')
            print("\n💾 Результаты сохранены в: xyz_analysis_test.csv")
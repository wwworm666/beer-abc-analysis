import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

class BeerDataProcessor:
    """Класс для обработки данных по пиву из OLAP отчета"""
    
    # Список баров
    BARS = [
        "Большой пр. В.О",
        "Лиговский", 
        "Кременчугская",
        "Варшавская"
    ]
    
    def __init__(self, olap_data):
        """
        olap_data: данные из OLAP отчета (dict с ключом 'data')
        """
        self.raw_data = olap_data.get('data', [])
        self.df = None
        
    def prepare_dataframe(self):
        """Преобразовать данные в pandas DataFrame и подготовить"""
        print("📊 Подготовка данных...")
        
        # Создаем DataFrame
        self.df = pd.DataFrame(self.raw_data)
        
        if self.df.empty:
            print("❌ Нет данных для анализа")
            return False
        
        print(f"✅ Загружено {len(self.df)} записей")
        
        # Преобразуем типы данных
        self.df['DishAmountInt'] = pd.to_numeric(self.df['DishAmountInt'], errors='coerce')
        self.df['DishDiscountSumInt'] = pd.to_numeric(self.df['DishDiscountSumInt'], errors='coerce')
        self.df['ProductCostBase.ProductCost'] = pd.to_numeric(self.df['ProductCostBase.ProductCost'], errors='coerce')
        self.df['ProductCostBase.MarkUp'] = pd.to_numeric(self.df['ProductCostBase.MarkUp'], errors='coerce')
        
        # Преобразуем дату
        self.df['OpenDate.Typed'] = pd.to_datetime(self.df['OpenDate.Typed'])
        
        # Добавляем вычисляемые поля
        self.df['Margin'] = self.df['DishDiscountSumInt'] - self.df['ProductCostBase.ProductCost']
        
        # Добавляем номер недели
        self.df['WeekNum'] = self.df['OpenDate.Typed'].dt.isocalendar().week
        self.df['Year'] = self.df['OpenDate.Typed'].dt.year
        self.df['YearWeek'] = self.df['Year'].astype(str) + '-W' + self.df['WeekNum'].astype(str).str.zfill(2)
        
        print(f"📅 Период данных: {self.df['OpenDate.Typed'].min()} - {self.df['OpenDate.Typed'].max()}")
        print(f"🍺 Уникальных фасовок: {self.df['DishName'].nunique()}")
        print(f"🏪 Баров в данных: {self.df['Store.Name'].nunique()}")
        
        return True
    
    def aggregate_by_beer_and_bar(self):
        """
        Агрегировать данные по фасовке и бару
        Возвращает DataFrame с суммарными показателями
        """
        print("\n🔄 Агрегация данных по фасовке и бару...")
        
        agg_data = self.df.groupby(['Store.Name', 'DishName', 'DishGroup.ThirdParent', 'DishForeignName']).agg({
            'DishAmountInt': 'sum',                    # Общее количество
            'DishDiscountSumInt': 'sum',               # Общая выручка
            'ProductCostBase.ProductCost': 'sum',      # Общая себестоимость
            'ProductCostBase.MarkUp': 'mean',          # Средняя наценка %
            'Margin': 'sum'                            # Общая маржа
        }).reset_index()
        
        # Переименуем столбцы для ясности
        agg_data.columns = [
            'Bar', 'Beer', 'Style', 'Country',
            'TotalQty', 'TotalRevenue', 'TotalCost', 
            'AvgMarkupPercent', 'TotalMargin'
        ]
        
        print(f"✅ Агрегировано: {len(agg_data)} уникальных пар (бар + фасовка)")
        
        return agg_data
    
    def get_weekly_sales(self, bar_name=None):
        """
        Получить продажи по неделям для каждой фасовки
        
        bar_name: если указан, фильтруем по бару
        Возвращает: dict {beer_name: {week: qty}}
        """
        df = self.df.copy()
        
        if bar_name:
            df = df[df['Store.Name'] == bar_name]
        
        # Группируем по фасовке и неделе
        weekly = df.groupby(['DishName', 'YearWeek'])['DishAmountInt'].sum().reset_index()
        
        # Преобразуем в словарь
        result = defaultdict(dict)
        for _, row in weekly.iterrows():
            beer = row['DishName']
            week = row['YearWeek']
            qty = row['DishAmountInt']
            result[beer][week] = qty
        
        return dict(result)
    
    def get_bar_statistics(self):
        """Получить статистику по каждому бару"""
        print("\n📈 Статистика по барам:")
        print("=" * 60)
        
        for bar in self.BARS:
            bar_data = self.df[self.df['Store.Name'] == bar]
            if len(bar_data) == 0:
                print(f"\n🏪 {bar}: НЕТ ДАННЫХ")
                continue
            
            total_revenue = bar_data['DishDiscountSumInt'].sum()
            total_qty = bar_data['DishAmountInt'].sum()
            unique_beers = bar_data['DishName'].nunique()
            
            print(f"\n🏪 {bar}:")
            print(f"   Выручка: {total_revenue:,.0f} руб")
            print(f"   Продано: {total_qty:,.0f} шт")
            print(f"   Уникальных фасовок: {unique_beers}")
        
        print("=" * 60)


# Тестовый запуск
if __name__ == "__main__":
    import json
    
    print("🧪 Тест обработки данных\n")
    
    # Загружаем данные из файла
    with open("beer_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Создаем процессор
    processor = BeerDataProcessor(data)
    
    # Подготавливаем данные
    if processor.prepare_dataframe():
        # Статистика по барам
        processor.get_bar_statistics()
        
        # Агрегация
        agg_data = processor.aggregate_by_beer_and_bar()
        
        print(f"\n📊 Первые 5 записей агрегированных данных:")
        print(agg_data.head())
        
        # Сохраним агрегированные данные
        agg_data.to_csv("aggregated_beer_data.csv", index=False, encoding='utf-8-sig')
        print("\n💾 Агрегированные данные сохранены в: aggregated_beer_data.csv")
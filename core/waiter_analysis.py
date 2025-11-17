"""
Модуль для анализа продаж разливного пива по официантам
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class WaiterAnalysis:
    """Класс для анализа продаж разливного пива по официантам"""

    def __init__(self, df):
        """
        df: pandas DataFrame с данными OLAP отчета
        Ожидаемые колонки:
        - DishName: название позиции (например, "ФестХаус Хеллес (0,5)")
        - DishAmountInt: количество проданных порций
        - OpenDate.Typed: дата продажи
        - Store.Name: название бара
        - WaiterName: имя официанта блюда
        - DishDiscountSumInt: выручка
        - ProductCostBase.ProductCost: себестоимость
        - ProductCostBase.MarkUp: наценка %
        """
        self.df = df.copy()

        # Проверяем наличие поля WaiterName
        if 'WaiterName' not in self.df.columns:
            self.df['WaiterName'] = 'Неизвестно'

        # Заполняем пустые значения
        self.df['WaiterName'].fillna('Неизвестно', inplace=True)

        # Фильтруем системных пользователей
        system_users = [
            'Пользователь для централизованной доставки',
            'Системный пользователь',
            'Неизвестно'
        ]
        self.df = self.df[~self.df['WaiterName'].isin(system_users)]

    def extract_beer_info(self, dish_name):
        """
        Извлекает название пива и объем порции из DishName

        Примеры:
        "ФестХаус Хеллес (0,5)" -> ("ФестХаус Хеллес", 0.5)
        "Блек Шип (0,25)" -> ("Блек Шип", 0.25)
        "ХБ Октоберфест (1,0) с собой" -> ("ХБ Октоберфест", 1.0)
        "Пиво (2)" -> ("Пиво", 2.0)
        "Пиво (500мл)" -> ("Пиво", 0.5)
        """
        # Паттерн 1: дробные числа в литрах (0,5 или 0.5)
        pattern_liters = r'\((\d+[,\.]\d+)\s*(?:л|l)?\)'
        match = re.search(pattern_liters, dish_name.strip(), re.IGNORECASE)

        if match:
            volume_str = match.group(1).replace(',', '.')
            volume = float(volume_str)
            beer_name = dish_name[:match.start()].strip()
            return beer_name, volume

        # Паттерн 2: целые числа в литрах (2)
        pattern_whole_liters = r'\((\d+)\s*(?:л|l)?\)'
        match = re.search(pattern_whole_liters, dish_name.strip(), re.IGNORECASE)

        if match:
            volume = float(match.group(1))
            beer_name = dish_name[:match.start()].strip()
            return beer_name, volume

        # Паттерн 3: миллилитры (500мл, 500ml)
        pattern_ml = r'\((\d+)\s*(?:мл|ml)\)'
        match = re.search(pattern_ml, dish_name.strip(), re.IGNORECASE)

        if match:
            volume_ml = float(match.group(1))
            volume = volume_ml / 1000  # Конвертируем в литры
            beer_name = dish_name[:match.start()].strip()
            return beer_name, volume

        # Если ничего не нашли
        return dish_name, 0.0

    def prepare_waiter_data(self):
        """Подготовка данных для анализа по официантам"""
        # Извлекаем название пива и объем порции
        beer_info = self.df['DishName'].apply(self.extract_beer_info)
        self.df['BeerName'] = beer_info.apply(lambda x: x[0])
        self.df['PortionVolume'] = beer_info.apply(lambda x: x[1])

        # НОРМАЛИЗАЦИЯ: убираем лишние пробелы и приводим к единому регистру
        # Это критично для правильной группировки!
        # Пример: "ФестХаус  Хеллес" (два пробела) → "фестхаус хеллес"
        self.df['BeerName'] = self.df['BeerName'].str.strip().str.replace(r'\s+', ' ', regex=True).str.lower()

        # Фильтруем записи с нулевым объёмом (не удалось распарсить)
        zero_volume_count = (self.df['PortionVolume'] == 0).sum()
        if zero_volume_count > 0:
            print(f"[WARNING] Isklyucheno {zero_volume_count} zapisey s nulevym obyomom (ne udalos rasparsit)")
        self.df = self.df[self.df['PortionVolume'] > 0]

        # Вычисляем объем в литрах
        self.df['VolumeInLiters'] = self.df['DishAmountInt'] * self.df['PortionVolume']

        # Вычисляем маржу
        if 'DishDiscountSumInt' in self.df.columns and 'ProductCostBase.ProductCost' in self.df.columns:
            self.df['Margin'] = self.df['DishDiscountSumInt'] - self.df['ProductCostBase.ProductCost']

        return self.df

    def get_waiter_summary(self, bar_name=None):
        """
        Сводка по каждому официанту за весь период

        Возвращает DataFrame с колонками:
        - WaiterName: имя официанта
        - Bar: бар (если указан)
        - TotalLiters: общий объем пролитого пива в литрах
        - TotalPortions: количество порций
        - TotalRevenue: выручка
        - TotalCost: себестоимость
        - TotalMargin: маржа
        - AvgMarkupPercent: средняя наценка %
        - Kegs30L: примерное количество кег 30л
        - Kegs50L: примерное количество кег 50л
        - UniqueBeers: количество уникальных сортов пива
        """
        df = self.prepare_waiter_data()

        # Фильтруем по бару если указан
        if bar_name:
            df = df[df['Store.Name'] == bar_name]

        # Группируем по официанту
        group_cols = ['WaiterName']
        if not bar_name:
            group_cols.append('Store.Name')

        agg_dict = {
            'VolumeInLiters': 'sum',
            'DishAmountInt': 'sum',
            'BeerName': 'nunique'
        }

        # Добавляем финансовые поля
        if 'DishDiscountSumInt' in df.columns:
            agg_dict['DishDiscountSumInt'] = 'sum'
        if 'ProductCostBase.ProductCost' in df.columns:
            agg_dict['ProductCostBase.ProductCost'] = 'sum'
        if 'ProductCostBase.MarkUp' in df.columns:
            agg_dict['ProductCostBase.MarkUp'] = 'mean'
        if 'Margin' in df.columns:
            agg_dict['Margin'] = 'sum'

        summary = df.groupby(group_cols).agg(agg_dict).reset_index()

        # Переименовываем колонки
        col_mapping = {
            'VolumeInLiters': 'TotalLiters',
            'DishAmountInt': 'TotalPortions',
            'BeerName': 'UniqueBeers',
            'DishDiscountSumInt': 'TotalRevenue',
            'ProductCostBase.ProductCost': 'TotalCost',
            'ProductCostBase.MarkUp': 'AvgMarkupPercent',
            'Margin': 'TotalMargin'
        }

        if not bar_name:
            col_mapping['Store.Name'] = 'Bar'

        summary = summary.rename(columns=col_mapping)

        # Добавляем бар если не было группировки по бару
        if bar_name:
            summary['Bar'] = bar_name

        # Примерное количество кег
        summary['Kegs30L'] = (summary['TotalLiters'] / 30).round(2)
        summary['Kegs50L'] = (summary['TotalLiters'] / 50).round(2)

        # Сортируем по объему (по убыванию)
        summary = summary.sort_values('TotalLiters', ascending=False)

        return summary

    def get_waiter_beer_details(self, waiter_name, bar_name=None):
        """
        Детальная информация о том, какое пиво пролил конкретный официант

        Возвращает DataFrame с колонками:
        - BeerName: название пива
        - TotalLiters: объем в литрах
        - TotalPortions: количество порций
        - TotalRevenue: выручка
        - TotalMargin: маржа
        - AvgMarkupPercent: средняя наценка %
        """
        df = self.prepare_waiter_data()

        # Фильтруем по официанту
        df = df[df['WaiterName'] == waiter_name]

        # Фильтруем по бару если указан
        if bar_name:
            df = df[df['Store.Name'] == bar_name]

        if df.empty:
            return pd.DataFrame()

        # Группируем по пиву
        agg_dict = {
            'VolumeInLiters': 'sum',
            'DishAmountInt': 'sum'
        }

        if 'DishDiscountSumInt' in df.columns:
            agg_dict['DishDiscountSumInt'] = 'sum'
        if 'ProductCostBase.ProductCost' in df.columns:
            agg_dict['ProductCostBase.ProductCost'] = 'sum'
        if 'ProductCostBase.MarkUp' in df.columns:
            agg_dict['ProductCostBase.MarkUp'] = 'mean'
        if 'Margin' in df.columns:
            agg_dict['Margin'] = 'sum'

        details = df.groupby('BeerName').agg(agg_dict).reset_index()

        # Переименовываем колонки
        col_mapping = {
            'VolumeInLiters': 'TotalLiters',
            'DishAmountInt': 'TotalPortions',
            'DishDiscountSumInt': 'TotalRevenue',
            'ProductCostBase.ProductCost': 'TotalCost',
            'ProductCostBase.MarkUp': 'AvgMarkupPercent',
            'Margin': 'TotalMargin'
        }

        details = details.rename(columns=col_mapping)

        # Сортируем по объему
        details = details.sort_values('TotalLiters', ascending=False)

        return details

    def get_top_waiters(self, bar_name=None, top_n=10):
        """Топ-N официантов по объему пролитого пива"""
        summary = self.get_waiter_summary(bar_name)
        return summary.head(top_n)

    def get_waiter_daily_performance(self, waiter_name, bar_name=None):
        """
        Производительность официанта по дням

        Возвращает DataFrame с колонками:
        - Date: дата
        - TotalLiters: объем за день
        - TotalPortions: количество порций
        - TotalRevenue: выручка
        - TotalMargin: маржа
        """
        df = self.prepare_waiter_data()

        # Фильтруем по официанту
        df = df[df['WaiterName'] == waiter_name]

        # Фильтруем по бару если указан
        if bar_name:
            df = df[df['Store.Name'] == bar_name]

        if df.empty:
            return pd.DataFrame()

        # Конвертируем дату
        df['Date'] = pd.to_datetime(df['OpenDate.Typed'])

        # Группируем по дате
        agg_dict = {
            'VolumeInLiters': 'sum',
            'DishAmountInt': 'sum'
        }

        if 'DishDiscountSumInt' in df.columns:
            agg_dict['DishDiscountSumInt'] = 'sum'
        if 'Margin' in df.columns:
            agg_dict['Margin'] = 'sum'

        daily = df.groupby('Date').agg(agg_dict).reset_index()

        # Переименовываем колонки
        col_mapping = {
            'VolumeInLiters': 'TotalLiters',
            'DishAmountInt': 'TotalPortions',
            'DishDiscountSumInt': 'TotalRevenue',
            'Margin': 'TotalMargin'
        }

        daily = daily.rename(columns=col_mapping)

        # Сортируем по дате
        daily = daily.sort_values('Date')

        return daily

    def format_summary_for_display(self, summary_df):
        """Форматирование сводки для отображения в JSON"""
        records = []

        for _, row in summary_df.iterrows():
            record = {
                'WaiterName': row['WaiterName'],
                'Bar': row['Bar'] if 'Bar' in row else '',
                'TotalLiters': float(row['TotalLiters']),
                'TotalPortions': int(row['TotalPortions']),
                'UniqueBeers': int(row['UniqueBeers']),
                'Kegs30L': float(row['Kegs30L']),
                'Kegs50L': float(row['Kegs50L'])
            }

            # Добавляем финансовые поля если есть
            if 'TotalRevenue' in row:
                record['TotalRevenue'] = float(row['TotalRevenue'])
            if 'TotalCost' in row:
                record['TotalCost'] = float(row['TotalCost'])
            if 'AvgMarkupPercent' in row:
                record['AvgMarkupPercent'] = float(row['AvgMarkupPercent'])
            if 'TotalMargin' in row:
                record['TotalMargin'] = float(row['TotalMargin'])

            records.append(record)

        return records

    def format_beer_details_for_display(self, details_df):
        """Форматирование детализации по пиву для отображения в JSON"""
        records = []

        for _, row in details_df.iterrows():
            record = {
                'BeerName': row['BeerName'],
                'TotalLiters': float(row['TotalLiters']),
                'TotalPortions': int(row['TotalPortions'])
            }

            # Добавляем финансовые поля если есть
            if 'TotalRevenue' in row:
                record['TotalRevenue'] = float(row['TotalRevenue'])
            if 'TotalCost' in row:
                record['TotalCost'] = float(row['TotalCost'])
            if 'AvgMarkupPercent' in row:
                record['AvgMarkupPercent'] = float(row['AvgMarkupPercent'])
            if 'TotalMargin' in row:
                record['TotalMargin'] = float(row['TotalMargin'])

            records.append(record)

        return records


# Тестовый запуск
if __name__ == "__main__":
    print("\n[TEST] Testiruem analiz po oficiantam\n")

    from datetime import datetime, timedelta
    from olap_reports import OlapReports

    # Подключаемся к API
    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Ne udalos podklyuchitsya k API")
        exit()

    # Получаем данные за последние 30 дней (московское время)
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_moscow = datetime.now(moscow_tz)
    date_to = now_moscow.strftime("%Y-%m-%d")
    date_from = (now_moscow - timedelta(days=30)).strftime("%Y-%m-%d")

    print(f"[INFO] Zaprashivaem dannye razlivnogo piva s oficiantami za {date_from} - {date_to}")
    report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to)
    olap.disconnect()

    if not report_data or not report_data.get('data'):
        print("[ERROR] Net dannykh")
        exit()

    # Преобразуем в DataFrame
    df = pd.DataFrame(report_data['data'])

    # Преобразуем типы
    df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
    df['DishDiscountSumInt'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce')
    df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce')
    df['ProductCostBase.MarkUp'] = pd.to_numeric(df['ProductCostBase.MarkUp'], errors='coerce')

    print(f"[INFO] Vsego zapisey: {len(df)}")

    # Создаем анализатор
    waiter_analyzer = WaiterAnalysis(df)

    # Получаем сводку по официантам
    summary = waiter_analyzer.get_waiter_summary()

    print(f"\n[INFO] Vsego oficiantov: {len(summary)}")
    print("\n[TOP 10] Oficianty po obyomu proliva:\n")

    top10 = summary.head(10)
    for i, row in top10.iterrows():
        print(f"{row['WaiterName']:30s} | {row['TotalLiters']:8.1f}L | ~{row['Kegs30L']:.1f} keg 30L | {row['Bar']}")

    # Детализация по первому официанту
    if len(top10) > 0:
        top_waiter = top10.iloc[0]['WaiterName']
        top_bar = top10.iloc[0]['Bar']
        print(f"\n[DETAILS] Chto prolil {top_waiter} v bare {top_bar}:\n")

        details = waiter_analyzer.get_waiter_beer_details(top_waiter, top_bar)
        for i, row in details.head(5).iterrows():
            print(f"  {row['BeerName']:40s} | {row['TotalLiters']:6.1f}L | {row['TotalPortions']:3d} porciy")

    # Сохраняем результаты
    summary.to_csv('waiter_analysis_summary.csv', index=False, encoding='utf-8-sig')
    print("\n[SAVE] Svodka sokhranena v waiter_analysis_summary.csv")
    print("[OK] Test zavershen!")

"""
Модуль для анализа продаж разливного пива
Агрегирует объемы по кегам в литрах
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class DraftAnalysis:
    """Класс для анализа продаж разливного пива"""

    def __init__(self, df):
        """
        df: pandas DataFrame с данными OLAP отчета
        Ожидаемые колонки:
        - DishName: название позиции (например, "ФестХаус Хеллес (0,5)")
        - DishAmountInt: количество проданных порций
        - OpenDate: дата продажи
        - Store.Name: название бара
        - DishGroup.TopParent: группа ("Напитки Розлив")
        """
        self.df = df.copy()

    def _clean_beer_name(self, name: str) -> str:
        """
        Очистка названия пива от лишних символов и слов

        Удаляет:
        - "с собой", "to go", "take away"
        - Лишние пробелы, дефисы в начале/конце
        """
        name = name.strip()
        # Удаляем "с собой" и аналоги
        name = re.sub(r'\s*(с\s+собой|to\s+go|take\s+away)\s*$', '', name, flags=re.IGNORECASE)
        # Удаляем лишние пробелы
        name = re.sub(r'\s+', ' ', name)
        # Удаляем дефисы в начале/конце
        name = name.strip('- ')
        return name

    def _estimate_volume(self, dish_name: str) -> float:
        """
        Эвристика для оценки объема порции если не удалось распарсить

        Логика:
        - Если в названии есть "0.5" или "0,5" → 0.5л
        - Если есть "1.0" или "1,0" → 1.0л
        - Если есть "500" (без мл) → 0.5л
        - Если есть "1000" или "1л" → 1.0л
        - Иначе → 0.5л (стандартная порция)
        """
        name_lower = dish_name.lower()

        # Ищем явные указания объема в тексте
        if re.search(r'0[,\.]5', name_lower):
            return 0.5
        if re.search(r'1[,\.]0', name_lower) or re.search(r'\b1л\b', name_lower):
            return 1.0
        if re.search(r'\b500\b', name_lower):
            return 0.5
        if re.search(r'\b1000\b', name_lower):
            return 1.0

        # Стандартная порция по умолчанию
        return 0.5

    def extract_beer_info(self, dish_name: str) -> tuple[str, float]:
        """
        Извлекает название пива и объем порции из DishName

        Поддерживаемые форматы:
        - "ФестХаус Хеллес (0,5)" → ("фестхаус хеллес", 0.5)
        - "Блек Шип (0,25)" → ("блек шип", 0.25)
        - "ФестХаус Вайцен (1,0)" → ("фестхаус вайцен", 1.0)
        - "ХБ Октоберфест (1,0) с собой" → ("хб октоберфест", 1.0)
        - "Пиво (2)" → ("пиво", 2.0)
        - "Пиво (500мл)" → ("пиво", 0.5)
        - "Пиво 0.5л" → ("пиво", 0.5) [НОВЫЙ: без скобок]
        - "ФестХаус 500мл с собой" → ("фестхаус", 0.5) [НОВЫЙ]
        - "Пиво 0,5 л" → ("пиво", 0.5) [НОВЫЙ: пробел перед единицей]

        Возвращает:
        - (название_пива, объем_в_литрах)
        - Если не распознано → (очищенное_название, 0.0)
        """
        original = dish_name.strip()

        # Паттерн 1: дробные числа в скобках (0,5 или 0.5)
        pattern_liters = r'\((\d+[,\.]\d+)\s*(?:л|l)?\)'
        match = re.search(pattern_liters, original, re.IGNORECASE)

        if match:
            volume_str = match.group(1).replace(',', '.')
            volume = float(volume_str)
            beer_name = original[:match.start()].strip()
            return self._clean_beer_name(beer_name), volume

        # Паттерн 2: целые числа в скобках (2)
        pattern_whole_liters = r'\((\d+)\s*(?:л|l)?\)'
        match = re.search(pattern_whole_liters, original, re.IGNORECASE)

        if match:
            volume = float(match.group(1))
            beer_name = original[:match.start()].strip()
            return self._clean_beer_name(beer_name), volume

        # Паттерн 3: миллилитры в скобках (500мл, 500ml)
        pattern_ml = r'\((\d+)\s*(?:мл|ml)\)'
        match = re.search(pattern_ml, original, re.IGNORECASE)

        if match:
            volume_ml = float(match.group(1))
            volume = volume_ml / 1000  # Конвертируем в литры
            beer_name = original[:match.start()].strip()
            return self._clean_beer_name(beer_name), volume

        # ПАТТЕРН 4: НОВЫЙ - дробные литры без скобок (Пиво 0.5л)
        pattern_liters_no_brackets = r'(\d+[,\.]\d+)\s*(?:л|l)(?:\s|$|с)'
        match = re.search(pattern_liters_no_brackets, original, re.IGNORECASE)

        if match:
            volume_str = match.group(1).replace(',', '.')
            volume = float(volume_str)
            beer_name = original[:match.start()].strip()
            return self._clean_beer_name(beer_name), volume

        # ПАТТЕРН 5: НОВЫЙ - миллилитры без скобок (Пиво 500мл)
        pattern_ml_no_brackets = r'(\d+)\s*(?:мл|ml)(?:\s|$|с)'
        match = re.search(pattern_ml_no_brackets, original, re.IGNORECASE)

        if match:
            volume_ml = float(match.group(1))
            volume = volume_ml / 1000  # Конвертируем в литры
            beer_name = original[:match.start()].strip()
            return self._clean_beer_name(beer_name), volume

        # НЕ РАСПОЗНАНО: применяем эвристику вместо возврата 0.0
        # Это предотвращает потерю данных
        estimated_volume = self._estimate_volume(original)
        return self._clean_beer_name(original), estimated_volume

    def prepare_draft_data(self, preserve_original_for_mapping=True):
        """
        Подготовка данных для анализа разливного пива

        preserve_original_for_mapping: если True, сохраняем оригинальный регистр
                                       для маппинга с dish_to_keg_mapping.json
        """
        # Этап 1: Извлекаем BeerName и PortionVolume
        beer_info = self.df['DishName'].apply(self.extract_beer_info)
        self.df['BeerName'] = beer_info.apply(lambda x: x[0])
        self.df['PortionVolume'] = beer_info.apply(lambda x: x[1])

        # Этап 2: Сохраняем оригинальное название для маппинга (если нужно)
        if preserve_original_for_mapping:
            self.df['BeerNameOriginal'] = self.df['BeerName'].str.strip()

        # Этап 3: Создаем нормализованную версию для группировки
        # Двухэтапная нормализация:
        # - BeerNameOriginal: сохраняет регистр для маппинга с dish_to_keg_mapping.json
        # - BeerNameNorm: lowercase для группировки одинаковых позиций
        self.df['BeerNameNorm'] = (
            self.df['BeerName']
            .str.strip()
            .str.replace(r'\s+', ' ', regex=True)
            .str.lower()
        )

        # Этап 4: Обработка записей с нулевым объемом — ЭВРИСТИКА вместо удаления
        zero_volume_mask = self.df['PortionVolume'] == 0
        zero_volume_count = zero_volume_mask.sum()

        if zero_volume_count > 0:
            print(f"[WARNING] Naideno {zero_volume_count} zapisey s neraspoznannym obyomom")
            print(f"[INFO] Primyayem evristiku dlya vosstanovleniya...")

            # Применяем эвристику вместо удаления
            self.df.loc[zero_volume_mask, 'PortionVolume'] = (
                self.df.loc[zero_volume_mask, 'DishName']
                .apply(self._estimate_volume)
            )

            recovered = (self.df.loc[zero_volume_mask, 'PortionVolume'] > 0).sum()
            print(f"[OK] Vosstanovleno {recovered} zapisey, {(zero_volume_count - recovered)} udaleno")

            # Теперь удаляем только те, где эвристика не помогла
            self.df = self.df[self.df['PortionVolume'] > 0]

        # Этап 5: Расчет литров
        self.df['VolumeInLiters'] = self.df['DishAmountInt'] * self.df['PortionVolume']

        # Этап 6: Недели
        if 'OpenDate.Typed' in self.df.columns:
            self.df['Week'] = pd.to_datetime(self.df['OpenDate.Typed']).dt.to_period('W')
        elif 'OpenDate' in self.df.columns:
            self.df['Week'] = pd.to_datetime(self.df['OpenDate']).dt.to_period('W')

        return self.df

    def get_weekly_draft_sales(self, bar_name=None):
        """
        Получить объемы продаж разливного пива по неделям

        Возвращает DataFrame с колонками:
        - BeerName: название пива (оригинальный регистр, для отображения)
        - BeerNameNorm: нормализованное название (для группировки)
        - Week: неделя
        - Bar: название бара
        - TotalLiters: общий объем в литрах
        - TotalPortions: количество порций
        - AvgPortionSize: средний объем порции
        """
        df = self.prepare_draft_data()

        # Фильтруем по бару если указан
        if bar_name:
            df = df[df['Store.Name'] == bar_name]

        # Группируем по нормализованному имени пива, неделе и бару
        grouped = df.groupby(['BeerNameNorm', 'Week', 'Store.Name']).agg({
            'VolumeInLiters': 'sum',
            'DishAmountInt': 'sum',
            'PortionVolume': 'mean',
            'BeerNameOriginal': 'first'  # Берем первое оригинальное название для отображения
        }).reset_index()

        grouped.columns = [
            'BeerNameNorm', 'Week', 'Bar',
            'TotalLiters', 'TotalPortions', 'AvgPortionSize',
            'BeerName'  # Оригинальное название для отображения
        ]

        # Сортируем по объему (по убыванию)
        grouped = grouped.sort_values('TotalLiters', ascending=False)

        return grouped

    def get_beer_summary(self, bar_name=None, include_financials=False):
        """
        Сводка по каждому пиву за весь период

        Возвращает DataFrame с колонками:
        - BeerName: название пива (оригинальный регистр, для отображения)
        - BeerNameNorm: нормализованное название (для группировки)
        - Bar: бар
        - TotalLiters: общий объем в литрах
        - TotalPortions: количество порций
        - WeeksActive: количество недель с продажами
        - AvgLitersPerWeek: средний объем за неделю
        - BeerSharePercent: доля пива от общего объема в % (рассчитывается ДЛЯ КАЖДОГО бара отдельно)
        - Kegs30L: примерное количество кег 30л
        - Kegs50L: примерное количество кег 50л
        - (опционально) TotalRevenue, TotalCost, AvgMarkupPercent, TotalMargin

        ВАЖНО: BeerSharePercent рассчитывается ПОСЛЕ фильтрации по бару,
               поэтому сумма процентов для каждого бара = 100%
        """
        df = self.prepare_draft_data()

        # Фильтруем по бару если указан
        if bar_name:
            df = df[df['Store.Name'] == bar_name]

        # Группируем для объемов — используем BeerNameNorm для группировки
        agg_dict = {
            'VolumeInLiters': 'sum',
            'DishAmountInt': 'sum',
            'PortionVolume': 'mean',
            'Week': 'nunique',
            'BeerNameOriginal': 'first'  # Сохраняем оригинальное название
        }

        # Добавляем финансовые данные если нужно
        if include_financials:
            if 'DishDiscountSumInt' in df.columns:
                agg_dict['DishDiscountSumInt'] = 'sum'
            if 'ProductCostBase.ProductCost' in df.columns:
                agg_dict['ProductCostBase.ProductCost'] = 'sum'
            if 'ProductCostBase.MarkUp' in df.columns:
                agg_dict['ProductCostBase.MarkUp'] = 'mean'
            if 'Margin' in df.columns:
                agg_dict['Margin'] = 'sum'

        # Группировка по нормализованному имени и бару
        summary = df.groupby(['BeerNameNorm', 'Store.Name']).agg(agg_dict).reset_index()

        # Переименовываем колонки
        col_mapping = {
            'BeerNameNorm': 'BeerNameNorm',  # Оставляем как есть
            'Store.Name': 'Bar',
            'VolumeInLiters': 'TotalLiters',
            'DishAmountInt': 'TotalPortions',
            'PortionVolume': 'AvgPortionSize',
            'Week': 'WeeksActive',
            'BeerNameOriginal': 'BeerName'  # Оригинальное название для отображения
        }

        if include_financials:
            col_mapping.update({
                'DishDiscountSumInt': 'TotalRevenue',
                'ProductCostBase.ProductCost': 'TotalCost',
                'ProductCostBase.MarkUp': 'AvgMarkupPercent',
                'Margin': 'TotalMargin'
            })

        summary = summary.rename(columns=col_mapping)

        # Вычисляем средний объем за неделю
        summary['AvgLitersPerWeek'] = summary['TotalLiters'] / summary['WeeksActive']

        # Вычисляем долю пива в % от общего объема
        # ВАЖНО: Считаем ДЛЯ КАЖДОГО бара отдельно, поэтому сумма = 100%
        for bar in summary['Bar'].unique():
            bar_mask = summary['Bar'] == bar
            bar_total = summary.loc[bar_mask, 'TotalLiters'].sum()

            if bar_total > 0:
                summary.loc[bar_mask, 'BeerSharePercent'] = (
                    summary.loc[bar_mask, 'TotalLiters'] / bar_total * 100
                )
            else:
                summary.loc[bar_mask, 'BeerSharePercent'] = 0.0

        # Примерное количество кег (30л и 50л)
        summary['Kegs30L'] = (summary['TotalLiters'] / 30).round(2)
        summary['Kegs50L'] = (summary['TotalLiters'] / 50).round(2)

        # Сортируем по объему (по убыванию)
        summary = summary.sort_values('TotalLiters', ascending=False)

        return summary

    def get_top_draft_beers(self, bar_name=None, top_n=10):
        """Топ-N разливного пива по объему продаж"""
        summary = self.get_beer_summary(bar_name)
        return summary.head(top_n)

    def get_weekly_chart_data(self, beer_name, bar_name=None):
        """
        Данные для графика продаж по неделям (в литрах)

        Возвращает словарь:
        {
            'weeks': ['2024-W01', '2024-W02', ...],
            'liters': [120.5, 145.2, ...]
        }
        """
        weekly = self.get_weekly_draft_sales(bar_name)
        beer_data = weekly[weekly['BeerName'] == beer_name].copy()

        if beer_data.empty:
            return None

        # Сортируем по неделям
        beer_data = beer_data.sort_values('Week')

        return {
            'weeks': [str(w) for w in beer_data['Week'].tolist()],
            'liters': beer_data['TotalLiters'].tolist(),
            'portions': beer_data['TotalPortions'].tolist()
        }

    def calculate_xyz_for_summary(self, bar_name=None):
        """
        Рассчитать XYZ категорию для каждого пива по процентилям (как ABC)

        X: топ 33% (наименьший CV - самые стабильные)
        Y: средние 33%
        Z: нижние 33% (наибольший CV - самые нестабильные)

        Возвращает DataFrame с колонками BeerName, XYZ_Category, CoefficientOfVariation
        """
        weekly = self.get_weekly_draft_sales(bar_name)

        # Группируем по пиву и рассчитываем коэффициент вариации
        xyz_data = []

        for beer_name in weekly['BeerName'].unique():
            beer_weekly = weekly[beer_name == weekly['BeerName']]

            if len(beer_weekly) < 2:
                # Если меньше 2 недель, CV = 100 (будет Z)
                xyz_data.append({
                    'BeerName': beer_name,
                    'CoefficientOfVariation': 100.0
                })
                continue

            # Рассчитываем коэффициент вариации
            mean_val = beer_weekly['TotalLiters'].mean()
            std_val = beer_weekly['TotalLiters'].std()

            if mean_val > 0:
                cv = (std_val / mean_val) * 100
            else:
                cv = 100.0

            xyz_data.append({
                'BeerName': beer_name,
                'CoefficientOfVariation': cv
            })

        df_xyz = pd.DataFrame(xyz_data)

        if df_xyz.empty:
            return df_xyz

        # Сортируем по CV (по возрастанию - чем меньше, тем стабильнее)
        df_xyz = df_xyz.sort_values('CoefficientOfVariation', ascending=True).reset_index(drop=True)

        # Присваиваем категории по процентилям (как в ABC)
        df_xyz['XYZ_Rank'] = (df_xyz.index + 1) / len(df_xyz) * 100

        def assign_xyz_category(rank):
            if rank <= 33.33:
                return 'X'  # Топ 33% - самые стабильные (наименьший CV)
            elif rank <= 66.66:
                return 'Y'  # Средние 33%
            else:
                return 'Z'  # Нижние 33% - самые нестабильные (наибольший CV)

        df_xyz['XYZ_Category'] = df_xyz['XYZ_Rank'].apply(assign_xyz_category)

        return df_xyz[['BeerName', 'XYZ_Category', 'CoefficientOfVariation']]

    def format_summary_for_display(self, summary_df):
        """Форматирование сводки для отображения в JSON"""
        records = []

        for _, row in summary_df.iterrows():
            record = {
                'BeerName': row['BeerName'],
                'Bar': row['Bar'],
                'TotalLiters': float(row['TotalLiters']),
                'TotalPortions': int(row['TotalPortions']),
                'WeeksActive': int(row['WeeksActive']),
                'AvgLitersPerWeek': float(row['AvgLitersPerWeek']),
                'BeerSharePercent': float(row['BeerSharePercent']) if 'BeerSharePercent' in row else 0.0,
                'Kegs30L': float(row['Kegs30L']),
                'Kegs50L': float(row['Kegs50L'])
            }

            # Добавляем финансовые поля если есть
            if 'TotalRevenue' in row:
                record['TotalRevenue'] = float(row['TotalRevenue'])
                # Цена за литр = выручка / литры
                total_liters = float(row['TotalLiters'])
                record['PricePerLiter'] = float(row['TotalRevenue']) / total_liters if total_liters > 0 else 0.0
            if 'TotalCost' in row:
                record['TotalCost'] = float(row['TotalCost'])
            if 'AvgMarkupPercent' in row:
                record['AvgMarkupPercent'] = float(row['AvgMarkupPercent'])
            if 'TotalMargin' in row:
                record['TotalMargin'] = float(row['TotalMargin'])
            if 'ABC_Combined' in row:
                record['ABC_Combined'] = str(row['ABC_Combined'])
            if 'ABC_Revenue' in row:
                record['ABC_Revenue'] = str(row['ABC_Revenue'])
            if 'ABC_Markup' in row:
                record['ABC_Markup'] = str(row['ABC_Markup'])
            if 'ABC_Margin' in row:
                record['ABC_Margin'] = str(row['ABC_Margin'])
            if 'RevenuePercent' in row:
                record['RevenuePercent'] = float(row['RevenuePercent'])

            # Добавляем XYZ поля если есть
            if 'XYZ_Category' in row:
                record['XYZ_Category'] = str(row['XYZ_Category'])
            if 'CoefficientOfVariation' in row:
                record['CoefficientOfVariation'] = float(row['CoefficientOfVariation'])
            if 'ABCXYZ_Combined' in row:
                record['ABCXYZ_Combined'] = str(row['ABCXYZ_Combined'])

            records.append(record)

        return records


# Тестовый запуск
if __name__ == "__main__":
    print("\n[TEST] Testiruem analiz razlivnogo piva\n")

    # Загружаем тестовые данные ИЗ СПЕЦИАЛЬНОГО ЗАПРОСА для разливного
    # (нужно сначала получить данные через get_draft_sales_report)
    import json
    from datetime import datetime, timedelta
    from core.olap_reports import OlapReports

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

    print(f"[INFO] Zaprashivaem dannye razlivnogo piva za {date_from} - {date_to}")
    report_data = olap.get_draft_sales_report(date_from, date_to)
    olap.disconnect()

    if not report_data or not report_data.get('data'):
        print("[ERROR] Net dannykh")
        exit()

    # Преобразуем в DataFrame
    df = pd.DataFrame(report_data['data'])

    # Преобразуем типы
    df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
    df['OpenDate'] = pd.to_datetime(df['OpenDate.Typed'])

    print(f"[INFO] Vsego zapisey razlivnogo piva: {len(df)}")

    # Создаем анализатор
    draft_analyzer = DraftAnalysis(df)

    # Получаем сводку
    summary = draft_analyzer.get_beer_summary()

    print(f"\n[INFO] Vsego unikalnykh razlivnykh piv: {len(summary)}")
    print("\n[TOP 10] Samye populyarnye razlivnye piva:\n")

    top10 = summary.head(10)
    for i, row in top10.iterrows():
        print(f"{row['BeerName']:40s} | {row['TotalLiters']:8.1f}L | ~{row['Kegs30L']:.1f} keg 30L | {row['Bar']}")

    # Пример графика для ФестХаус
    print("\n[CHART] Nedelnye prodazhi FestHaus Helles:\n")
    chart = draft_analyzer.get_weekly_chart_data('ФестХаус Хеллес')
    if chart:
        for week, liters in zip(chart['weeks'][:5], chart['liters'][:5]):
            print(f"  {week}: {liters:.1f}L")

    # Сохраняем результаты
    summary.to_csv('draft_beer_summary.csv', index=False, encoding='utf-8-sig')
    print("\n[SAVE] Svodka sokhranena v draft_beer_summary.csv")
    print("[OK] Test zavershen!")

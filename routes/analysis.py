from flask import Blueprint, request, jsonify
import pandas as pd
import json
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.data_processor import BeerDataProcessor
from core.abc_analysis import ABCAnalysis
from core.xyz_analysis import XYZAnalysis
from core.category_analysis import CategoryAnalysis
from core.draft_analysis import DraftAnalysis
from core.waiter_analysis import WaiterAnalysis
from extensions import BARS

analysis_bp = Blueprint('analysis', __name__)


@analysis_bp.route('/api/analyze', methods=['POST'])
def analyze():
    """API endpoint для запуска анализа"""
    try:
        data = request.json
        bar_name = data.get('bar')
        days = int(data.get('days', 30))

        print(f"\n[ANALIZ] Zapusk analiza...")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")
        print(f"   Period: {days} dney")

            # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            # Запрашиваем данные
            date_to_obj = datetime.now()
            date_from = (date_to_obj - timedelta(days=days)).strftime("%Y-%m-%d")
            date_to = (date_to_obj + timedelta(days=1)).strftime("%Y-%m-%d")  # OLAP exclusive

            report_data = olap.get_beer_sales_report(date_from, date_to, bar_name)
        finally:
            olap.disconnect()

        if not report_data or not report_data.get('data'):
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

        # Обрабатываем данные
        processor = BeerDataProcessor(report_data)
        if not processor.prepare_dataframe():
            return jsonify({'error': 'Ошибка обработки данных'}), 500

        agg_data = processor.aggregate_by_beer_and_bar()

        # ABC анализ
        abc_analyzer = ABCAnalysis(agg_data)

        # XYZ анализ
        xyz_analyzer = XYZAnalysis(processor.df)

        if bar_name:
            # Анализ для одного бара
            abc_result = abc_analyzer.perform_abc_analysis_by_bar(bar_name)
            xyz_result = xyz_analyzer.perform_xyz_analysis_by_bar(bar_name)

            # Объединяем ABC и XYZ
            if not abc_result.empty and not xyz_result.empty:
                combined = abc_result.merge(
                    xyz_result[['Beer', 'XYZ_Category', 'CoefficientOfVariation']],
                    on='Beer',
                    how='left'
                )
                # Заполняем пустые XYZ как Z (нестабильные)
                combined['XYZ_Category'].fillna('Z', inplace=True)
                combined['CoefficientOfVariation'].fillna(100, inplace=True)

                # Полная категория ABC-XYZ
                combined['ABCXYZ_Combined'] = combined['ABC_Combined'] + '-' + combined['XYZ_Category']

                results = {bar_name: combined}
            else:
                results = {bar_name: abc_result}
        else:
            # Анализ для всех баров - объединяем в единую сводку
            abc_results = abc_analyzer.perform_full_analysis()

            # Объединяем все данные из всех баров
            all_bars_data = []
            for bar, abc_df in abc_results.items():
                if not abc_df.empty:
                    # Добавляем колонку с названием бара
                    abc_df_copy = abc_df.copy()
                    abc_df_copy['Bar'] = bar

                    # Добавляем XYZ данные для этого бара
                    xyz_df = xyz_analyzer.perform_xyz_analysis_by_bar(bar)
                    if not xyz_df.empty:
                        abc_df_copy = abc_df_copy.merge(
                            xyz_df[['Beer', 'XYZ_Category', 'CoefficientOfVariation']],
                            on='Beer',
                            how='left'
                        )
                        abc_df_copy['XYZ_Category'].fillna('Z', inplace=True)
                        abc_df_copy['CoefficientOfVariation'].fillna(100, inplace=True)
                        abc_df_copy['ABCXYZ_Combined'] = abc_df_copy['ABC_Combined'] + '-' + abc_df_copy['XYZ_Category']

                    all_bars_data.append(abc_df_copy)

            # Создаём единый DataFrame со всеми данными
            if all_bars_data:
                combined_all = pd.concat(all_bars_data, ignore_index=True)

                # Агрегируем данные по пиву, объединяя все бары
                # Группируем по Beer, Style, Country и агрегируем метрики
                aggregated = combined_all.groupby(['Beer', 'Style', 'Country']).agg({
                    'TotalQty': 'sum',
                    'TotalRevenue': 'sum',
                    'TotalCost': 'sum',
                    'TotalMargin': 'sum',
                    'CostPerUnit': 'max',  # Берём актуальную себестоимость единицы
                    'AvgMarkupPercent': 'max',  # Берём максимальную наценку по всем барам
                }).reset_index()

                # Пересчитываем ABC категории на основе агрегированных данных
                # Создаем временный экземпляр для использования методов
                abc_temp = ABCAnalysis(pd.DataFrame())

                # 1-я буква: ABC по выручке
                aggregated['ABC_Revenue'] = abc_temp.calculate_abc_category(
                    aggregated['TotalRevenue'],
                    ascending=False
                )

                # 2-я буква: ABC по % наценки (фиксированные пороги)
                aggregated['ABC_Markup'] = abc_temp.calculate_markup_category(
                    aggregated['AvgMarkupPercent']
                )

                # 3-я буква: ABC по марже
                aggregated['ABC_Margin'] = abc_temp.calculate_abc_category(
                    aggregated['TotalMargin'],
                    ascending=False
                )

                # Комбинированная категория
                aggregated['ABC_Combined'] = (
                    aggregated['ABC_Revenue'] +
                    aggregated['ABC_Markup'] +
                    aggregated['ABC_Margin']
                )

                # Добавляем XYZ анализ на основе агрегированных данных
                # Для этого нужно пересчитать вариацию по всем барам
                xyz_all = []
                for beer in aggregated['Beer'].unique():
                    beer_data = combined_all[combined_all['Beer'] == beer]
                    if len(beer_data) > 1:
                        cv = beer_data['TotalQty'].std() / beer_data['TotalQty'].mean() * 100 if beer_data['TotalQty'].mean() > 0 else 100
                    else:
                        cv = 100

                    # Категоризация XYZ
                    if cv < 10:
                        xyz_cat = 'X'
                    elif cv < 25:
                        xyz_cat = 'Y'
                    else:
                        xyz_cat = 'Z'

                    xyz_all.append({
                        'Beer': beer,
                        'CoefficientOfVariation': cv,
                        'XYZ_Category': xyz_cat
                    })

                xyz_df_all = pd.DataFrame(xyz_all)
                aggregated = aggregated.merge(xyz_df_all, on='Beer', how='left')
                aggregated['XYZ_Category'].fillna('Z', inplace=True)
                aggregated['CoefficientOfVariation'].fillna(100, inplace=True)
                aggregated['ABCXYZ_Combined'] = aggregated['ABC_Combined'] + '-' + aggregated['XYZ_Category']

                results = {"Общая": aggregated}
            else:
                results = {}

        # Формируем ответ
        response_data = {}

        for bar, df in results.items():
            if df.empty:
                continue

            # Конвертируем в JSON-friendly формат
            records = df.to_dict('records')

            # Статистика по ABC категориям
            abc_stats = df['ABC_Combined'].value_counts().to_dict()

            # Статистика по XYZ категориям
            xyz_stats = {}
            if 'XYZ_Category' in df.columns:
                xyz_stats = df['XYZ_Category'].value_counts().to_dict()

            # Статистика по ABCXYZ комбинациям
            abcxyz_stats = {}
            if 'ABCXYZ_Combined' in df.columns:
                abcxyz_stats = df['ABCXYZ_Combined'].value_counts().to_dict()

            # Топ и худшие фасовки
            top_beers = df.nlargest(10, 'TotalRevenue')[
                ['Beer', 'TotalRevenue', 'ABC_Combined'] +
                (['XYZ_Category'] if 'XYZ_Category' in df.columns else [])
            ].to_dict('records')

            worst_beers = df.nsmallest(10, 'TotalRevenue')[
                ['Beer', 'TotalRevenue', 'ABC_Combined'] +
                (['XYZ_Category'] if 'XYZ_Category' in df.columns else [])
            ].to_dict('records')

            response_data[bar] = {
                'records': records,
                'abc_stats': abc_stats,
                'xyz_stats': xyz_stats,
                'abcxyz_stats': abcxyz_stats,
                'top_beers': top_beers,
                'worst_beers': worst_beers,
                'total_beers': len(df),
                'total_revenue': float(df['TotalRevenue'].sum()),
                'total_qty': float(df['TotalQty'].sum())
            }

        return jsonify(response_data)

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/analyze: {e}")
        import traceback
        traceback.print_exc()
        error_detail = f"{type(e).__name__}: {str(e)}"
        return jsonify({'error': error_detail}), 500

@analysis_bp.route('/api/weekly-chart/<bar_name>/<beer_name>', methods=['GET'])
def get_weekly_chart(bar_name, beer_name):
    """API endpoint для получения данных графика по неделям"""
    try:
        # Загружаем последний отчет из кеша (в реальности нужно запросить заново)
        # Для простоты используем сохраненные данные
        import os
        if not os.path.exists('beer_report.json'):
            return jsonify({'error': 'Нет данных'}), 404

        with open('beer_report.json', 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        processor = BeerDataProcessor(report_data)
        if not processor.prepare_dataframe():
            return jsonify({'error': 'Ошибка обработки'}), 500

        xyz_analyzer = XYZAnalysis(processor.df)
        chart_data = xyz_analyzer.get_weekly_sales_chart_data(bar_name, beer_name)

        if not chart_data:
            return jsonify({'error': 'Нет данных для графика'}), 404

        return jsonify(chart_data)

    except Exception as e:
        print(f"❌ Ошибка графика: {e}")
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/api/categories', methods=['POST'])
def analyze_categories():
    """API endpoint для анализа по категориям пива"""
    try:
        data = request.json
        bar_name = data.get('bar')
        days = int(data.get('days', 30))

        print(f"\n[CATEGORY] Zapusk analiza po kategoriyam...")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")
        print(f"   Period: {days} dney")

        # Подключаемся к iiko API
        print("   [1/8] Podklyuchenie k iiko API...")
        olap = OlapReports()
        if not olap.connect():
            print("   [ERROR] Ne udalos podklyuchitsya k iiko API")
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500
        print("   [OK] Podklyucheno k iiko API")

        try:
            # Запрашиваем данные
            print("   [2/8] Zapros dannykh iz OLAP...")
            date_to_obj = datetime.now()
            date_from = (date_to_obj - timedelta(days=days)).strftime("%Y-%m-%d")
            date_to = (date_to_obj + timedelta(days=1)).strftime("%Y-%m-%d")  # OLAP exclusive

            report_data = olap.get_beer_sales_report(date_from, date_to, bar_name)

            if not report_data or not report_data.get('data'):
                print(f"   [ERROR] Net dannykh za period {date_from} - {date_to}")
                return jsonify({'error': 'Нет данных за выбранный период'}), 404
        finally:
            olap.disconnect()

        print(f"   [OK] Polucheno {len(report_data.get('data', []))} zapisey")

        # Обрабатываем данные
        print("   [3/8] Obrabotka dannykh...")
        processor = BeerDataProcessor(report_data)
        if not processor.prepare_dataframe():
            print("   [ERROR] Oshibka obrabotki dannykh")
            return jsonify({'error': 'Ошибка обработки данных'}), 500

        print("   [OK] Dannye obrabotany")

        print("   [4/8] Agregaciya dannykh...")
        agg_data = processor.aggregate_by_beer_and_bar()
        print(f"   [OK] Agregirovano {len(agg_data)} zapisey")

        # Создаем анализатор категорий
        print("   [5/8] Sozdanie analizatora kategoriy...")
        cat_analyzer = CategoryAnalysis(agg_data, processor.df)

        # Проверка null значений после создания
        null_count_after = cat_analyzer.data['Style'].isna().sum()
        uncategorized_count = (cat_analyzer.data['Style'] == 'Bez kategorii (F)').sum()
        print(f"   [STATS] Pustykh Style posle sozdaniya CategoryAnalysis: {null_count_after}")
        print(f"   [STATS] Fasovok v kategorii 'Bez kategorii (F)': {uncategorized_count}")
        print("   [OK] Analizator kategoriy sozdan")

        # XYZ анализатор для добавления данных о стабильности
        print("   [6/8] Sozdanie XYZ analizatora...")
        xyz_analyzer = XYZAnalysis(processor.df)
        print("   [OK] XYZ analizator sozdan")

        # Получаем сводку по категориям
        print("   [7/8] Poluchenie svodki po kategoriyam...")
        summary = cat_analyzer.get_category_summary(bar_name)
        print(f"   [OK] Svodka poluchena: {len(summary)} kategoriy")

        # Получаем детальный анализ для всех категорий
        print("   [8/8] Detalniy analiz kategoriy...")
        category_results = {}

        if bar_name:
            # Для одного бара
            categories = cat_analyzer.get_categories(bar_name)
            print(f"   [STATS] Naydeno kategoriy dlya bara '{bar_name}': {len(categories)}")

            for i, category in enumerate(categories, 1):
                print(f"      [{i}/{len(categories)}] Analiz kategorii: {category}")
                result = cat_analyzer.analyze_category(category, bar_name)
                if result:
                    # Добавляем XYZ данные
                    result = cat_analyzer.add_xyz_to_category_analysis(
                        result, xyz_analyzer, bar_name
                    )
                    category_results[category] = result
                    print(f"         [OK] {result['total_beers']} fasovok")
                else:
                    print(f"         [WARN] Net dannykh dlya kategorii")
        else:
            # Для всех баров - группируем по барам
            print(f"   [STATS] Analiz dlya vsekh barov: {', '.join(BARS)}")
            for bar in BARS:
                bar_results = {}
                categories = cat_analyzer.get_categories(bar)
                print(f"      Bar '{bar}': {len(categories)} kategoriy")

                for category in categories:
                    result = cat_analyzer.analyze_category(category, bar)
                    if result:
                        result = cat_analyzer.add_xyz_to_category_analysis(
                            result, xyz_analyzer, bar
                        )
                        bar_results[category] = result

                if bar_results:
                    category_results[bar] = bar_results
                    print(f"         [OK] {len(bar_results)} kategoriy obrabotano")

        print(f"   [OK] Analiz zavershen")
        print(f"   [STATS] Vsego kategoriy v rezultate: {len(category_results)}")

        # Формируем ответ
        response_data = {
            'summary': summary.to_dict('records'),
            'categories': category_results
        }

        print(f"   [OK] Otvet sformirovan i otpravlyaetsya klientu")
        return jsonify(response_data)

    except Exception as e:
        print(f"[ERROR] Oshibka analiza kategoriy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/api/draft-analyze', methods=['POST'])
def analyze_draft():
    """API endpoint для анализа разливного пива"""
    try:
        data = request.json
        bar_name = data.get('bar')
        days = int(data.get('days', 30))
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        print(f"\n[DRAFT] Zapusk analiza razlivnogo piva...")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")

        # Обработка дат: если переданы конкретные даты, используем их, иначе вычисляем
        if not date_from or not date_to:
            date_to_obj = datetime.now()
            date_from = (date_to_obj - timedelta(days=days)).strftime("%Y-%m-%d")
            date_to = date_to_obj.strftime("%Y-%m-%d")
            print(f"   Period: {days} dney (computed: {date_from} - {date_to})")
        else:
            print(f"   Period: {date_from} - {date_to}")

        # OLAP to-дата exclusive → +1 день
        olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            report_data = olap.get_draft_sales_report(date_from, olap_date_to, bar_name)

            if not report_data or not report_data.get('data'):
                return jsonify({'error': 'Нет данных за выбранный период'}), 404
        finally:
            olap.disconnect()

        # Преобразуем в DataFrame
        df = pd.DataFrame(report_data['data'])
        df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
        df['DishDiscountSumInt'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce')
        df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce')
        df['ProductCostBase.MarkUp'] = pd.to_numeric(df['ProductCostBase.MarkUp'], errors='coerce')
        df['OpenDate'] = pd.to_datetime(df['OpenDate.Typed'])

        # Добавляем вычисляемые поля
        df['Margin'] = df['DishDiscountSumInt'] - df['ProductCostBase.ProductCost']

        # Создаем анализатор разливного
        draft_analyzer = DraftAnalysis(df)

        if bar_name:
            # Анализ для одного бара с финансами
            summary = draft_analyzer.get_beer_summary(bar_name, include_financials=True)

            # Применяем ABC анализ (3 буквы: выручка + наценка + маржа)
            if 'TotalRevenue' in summary.columns:
                # 1. ABC по выручке (A)
                summary_sorted = summary.sort_values('TotalRevenue', ascending=False).copy()
                summary_sorted['CumulativeRevenue'] = summary_sorted['TotalRevenue'].cumsum()
                total_revenue = summary_sorted['TotalRevenue'].sum()
                summary_sorted['RevenuePercent'] = (summary_sorted['CumulativeRevenue'] / total_revenue * 100)

                def assign_abc_revenue(pct):
                    if pct <= 80:
                        return 'A'
                    elif pct <= 95:
                        return 'B'
                    else:
                        return 'C'

                summary_sorted['ABC_Revenue'] = summary_sorted['RevenuePercent'].apply(assign_abc_revenue)

                # 2. ABC по наценке (B)
                markup_sorted = summary_sorted.sort_values('AvgMarkupPercent', ascending=False).copy()
                markup_sorted = markup_sorted.reset_index(drop=True)
                markup_sorted['MarkupRank'] = (markup_sorted.index + 1) / len(markup_sorted) * 100

                def assign_abc_markup(rank):
                    if rank <= 33.33:
                        return 'A'
                    elif rank <= 66.66:
                        return 'B'
                    else:
                        return 'C'

                markup_sorted['ABC_Markup'] = markup_sorted['MarkupRank'].apply(assign_abc_markup)
                summary_sorted = summary_sorted.merge(markup_sorted[['BeerName', 'ABC_Markup']], on='BeerName', how='left')

                # 3. ABC по марже (C)
                margin_sorted = summary_sorted.sort_values('TotalMargin', ascending=False).copy()
                margin_sorted = margin_sorted.reset_index(drop=True)
                margin_sorted['MarginRank'] = (margin_sorted.index + 1) / len(margin_sorted) * 100

                def assign_abc_margin(rank):
                    if rank <= 33.33:
                        return 'A'
                    elif rank <= 66.66:
                        return 'B'
                    else:
                        return 'C'

                margin_sorted['ABC_Margin'] = margin_sorted['MarginRank'].apply(assign_abc_margin)
                summary_sorted = summary_sorted.merge(margin_sorted[['BeerName', 'ABC_Margin']], on='BeerName', how='left')

                # Объединяем в 3-буквенный код
                summary_sorted['ABC_Combined'] = summary_sorted['ABC_Revenue'] + summary_sorted['ABC_Markup'] + summary_sorted['ABC_Margin']

                summary = summary_sorted

            # Применяем XYZ анализ
            xyz_df = draft_analyzer.calculate_xyz_for_summary(bar_name)
            if not xyz_df.empty:
                summary = summary.merge(
                    xyz_df[['BeerName', 'XYZ_Category', 'CoefficientOfVariation']],
                    on='BeerName',
                    how='left'
                )
                # Заполняем пустые XYZ как Z (нестабильные)
                summary['XYZ_Category'].fillna('Z', inplace=True)
                summary['CoefficientOfVariation'].fillna(100.0, inplace=True)

                # Полная категория ABC-XYZ (если есть ABC)
                if 'ABC_Combined' in summary.columns:
                    summary['ABCXYZ_Combined'] = summary['ABC_Combined'] + '-' + summary['XYZ_Category']

            # Сортируем по объёму (литры) от большего к меньшему
            summary = summary.sort_values('TotalLiters', ascending=False)

            beers = draft_analyzer.format_summary_for_display(summary)

            response_data = {
                bar_name: {
                    'total_liters': float(summary['TotalLiters'].sum()),
                    'total_portions': int(summary['TotalPortions'].sum()),
                    'total_beers': len(summary),
                    'kegs_30l': float(summary['TotalLiters'].sum() / 30),
                    'kegs_50l': float(summary['TotalLiters'].sum() / 50),
                    'total_revenue': float(summary['TotalRevenue'].sum()) if 'TotalRevenue' in summary.columns else 0,
                    'beers': beers
                }
            }
        else:
            # Анализ для всех баров - объединяем с ABC/XYZ для каждого
            all_bars_data = []

            for bar in BARS:
                bar_summary = draft_analyzer.get_beer_summary(bar, include_financials=True)
                if bar_summary.empty:
                    continue

                # Применяем ABC анализ для этого бара
                if 'TotalRevenue' in bar_summary.columns:
                    # 1. ABC по выручке
                    summary_sorted = bar_summary.sort_values('TotalRevenue', ascending=False).copy()
                    summary_sorted['CumulativeRevenue'] = summary_sorted['TotalRevenue'].cumsum()
                    total_revenue = summary_sorted['TotalRevenue'].sum()
                    summary_sorted['RevenuePercent'] = (summary_sorted['CumulativeRevenue'] / total_revenue * 100)

                    def assign_abc_revenue(pct):
                        if pct <= 80:
                            return 'A'
                        elif pct <= 95:
                            return 'B'
                        else:
                            return 'C'

                    summary_sorted['ABC_Revenue'] = summary_sorted['RevenuePercent'].apply(assign_abc_revenue)

                    # 2. ABC по наценке
                    markup_sorted = summary_sorted.sort_values('AvgMarkupPercent', ascending=False).copy()
                    markup_sorted = markup_sorted.reset_index(drop=True)
                    markup_sorted['MarkupRank'] = (markup_sorted.index + 1) / len(markup_sorted) * 100

                    def assign_abc_markup(rank):
                        if rank <= 33.33:
                            return 'A'
                        elif rank <= 66.66:
                            return 'B'
                        else:
                            return 'C'

                    markup_sorted['ABC_Markup'] = markup_sorted['MarkupRank'].apply(assign_abc_markup)
                    summary_sorted = summary_sorted.merge(markup_sorted[['BeerName', 'ABC_Markup']], on='BeerName', how='left')

                    # 3. ABC по марже
                    margin_sorted = summary_sorted.sort_values('TotalMargin', ascending=False).copy()
                    margin_sorted = margin_sorted.reset_index(drop=True)
                    margin_sorted['MarginRank'] = (margin_sorted.index + 1) / len(margin_sorted) * 100

                    def assign_abc_margin(rank):
                        if rank <= 33.33:
                            return 'A'
                        elif rank <= 66.66:
                            return 'B'
                        else:
                            return 'C'

                    margin_sorted['ABC_Margin'] = margin_sorted['MarginRank'].apply(assign_abc_margin)
                    summary_sorted = summary_sorted.merge(margin_sorted[['BeerName', 'ABC_Margin']], on='BeerName', how='left')

                    # Объединяем в 3-буквенный код
                    summary_sorted['ABC_Combined'] = summary_sorted['ABC_Revenue'] + summary_sorted['ABC_Markup'] + summary_sorted['ABC_Margin']

                    bar_summary = summary_sorted

                # Применяем XYZ анализ для этого бара
                xyz_df = draft_analyzer.calculate_xyz_for_summary(bar)
                if not xyz_df.empty:
                    bar_summary = bar_summary.merge(
                        xyz_df[['BeerName', 'XYZ_Category', 'CoefficientOfVariation']],
                        on='BeerName',
                        how='left'
                    )
                    bar_summary['XYZ_Category'].fillna('Z', inplace=True)
                    bar_summary['CoefficientOfVariation'].fillna(100.0, inplace=True)

                    if 'ABC_Combined' in bar_summary.columns:
                        bar_summary['ABCXYZ_Combined'] = bar_summary['ABC_Combined'] + '-' + bar_summary['XYZ_Category']

                # Сортируем по объёму (литры) от большего к меньшему
                bar_summary = bar_summary.sort_values('TotalLiters', ascending=False)

                all_bars_data.append(bar_summary)

            # Объединяем все бары
            if all_bars_data:
                combined_data = pd.concat(all_bars_data, ignore_index=True)

                # Агрегируем по названию пива (объединяем одинаковые сорта из разных баров)
                agg_dict = {
                    'TotalLiters': 'sum',
                    'TotalPortions': 'sum',
                    'WeeksActive': 'max',
                    'AvgPortionSize': 'mean',
                    'Kegs30L': 'sum',
                    'Kegs50L': 'sum'
                }

                if 'TotalRevenue' in combined_data.columns:
                    agg_dict['TotalRevenue'] = 'sum'
                    agg_dict['TotalCost'] = 'sum'
                    agg_dict['AvgMarkupPercent'] = 'mean'
                    agg_dict['TotalMargin'] = 'sum'

                # Группируем по BeerName
                aggregated = combined_data.groupby('BeerName', as_index=False).agg(agg_dict)

                # Пересчитываем AvgLitersPerWeek
                aggregated['AvgLitersPerWeek'] = aggregated['TotalLiters'] / aggregated['WeeksActive']

                # Пересчитываем BeerSharePercent после агрегации
                total_liters = aggregated['TotalLiters'].sum()
                if total_liters > 0:
                    aggregated['BeerSharePercent'] = (aggregated['TotalLiters'] / total_liters * 100)
                else:
                    aggregated['BeerSharePercent'] = 0.0

                # Добавляем Bar = "Общая"
                aggregated['Bar'] = 'Общая'

                # Применяем ABC анализ к агрегированным данным
                if 'TotalRevenue' in aggregated.columns:
                    # 1. ABC по выручке
                    abc_sorted = aggregated.sort_values('TotalRevenue', ascending=False).copy()
                    abc_sorted['CumulativeRevenue'] = abc_sorted['TotalRevenue'].cumsum()
                    total_revenue = abc_sorted['TotalRevenue'].sum()
                    abc_sorted['RevenuePercent'] = (abc_sorted['CumulativeRevenue'] / total_revenue * 100)

                    def assign_abc_revenue(pct):
                        if pct <= 80:
                            return 'A'
                        elif pct <= 95:
                            return 'B'
                        else:
                            return 'C'

                    abc_sorted['ABC_Revenue'] = abc_sorted['RevenuePercent'].apply(assign_abc_revenue)

                    # 2. ABC по наценке
                    markup_sorted = abc_sorted.sort_values('AvgMarkupPercent', ascending=False).copy()
                    markup_sorted = markup_sorted.reset_index(drop=True)
                    markup_sorted['MarkupRank'] = (markup_sorted.index + 1) / len(markup_sorted) * 100

                    def assign_abc_markup(rank):
                        if rank <= 33.33:
                            return 'A'
                        elif rank <= 66.66:
                            return 'B'
                        else:
                            return 'C'

                    markup_sorted['ABC_Markup'] = markup_sorted['MarkupRank'].apply(assign_abc_markup)
                    abc_sorted = abc_sorted.merge(markup_sorted[['BeerName', 'ABC_Markup']], on='BeerName', how='left')

                    # 3. ABC по марже
                    margin_sorted = abc_sorted.sort_values('TotalMargin', ascending=False).copy()
                    margin_sorted = margin_sorted.reset_index(drop=True)
                    margin_sorted['MarginRank'] = (margin_sorted.index + 1) / len(margin_sorted) * 100

                    def assign_abc_margin(rank):
                        if rank <= 33.33:
                            return 'A'
                        elif rank <= 66.66:
                            return 'B'
                        else:
                            return 'C'

                    margin_sorted['ABC_Margin'] = margin_sorted['MarginRank'].apply(assign_abc_margin)
                    abc_sorted = abc_sorted.merge(margin_sorted[['BeerName', 'ABC_Margin']], on='BeerName', how='left')

                    # Объединяем в 3-буквенный код
                    abc_sorted['ABC_Combined'] = abc_sorted['ABC_Revenue'] + abc_sorted['ABC_Markup'] + abc_sorted['ABC_Margin']

                    aggregated = abc_sorted

                # Применяем XYZ анализ к агрегированным данным (без bar_name - по всем барам)
                xyz_df = draft_analyzer.calculate_xyz_for_summary(None)
                if not xyz_df.empty:
                    aggregated = aggregated.merge(
                        xyz_df[['BeerName', 'XYZ_Category', 'CoefficientOfVariation']],
                        on='BeerName',
                        how='left'
                    )
                    aggregated['XYZ_Category'].fillna('Z', inplace=True)
                    aggregated['CoefficientOfVariation'].fillna(100.0, inplace=True)

                    if 'ABC_Combined' in aggregated.columns:
                        aggregated['ABCXYZ_Combined'] = aggregated['ABC_Combined'] + '-' + aggregated['XYZ_Category']

                # Сортируем по объёму (литры) от большего к меньшему
                aggregated = aggregated.sort_values('TotalLiters', ascending=False)

                beers = draft_analyzer.format_summary_for_display(aggregated)

                response_data = {
                    "Общая": {
                        'total_liters': float(aggregated['TotalLiters'].sum()),
                        'total_portions': int(aggregated['TotalPortions'].sum()),
                        'total_beers': len(aggregated),
                        'kegs_30l': float(aggregated['TotalLiters'].sum() / 30),
                        'kegs_50l': float(aggregated['TotalLiters'].sum() / 50),
                        'total_revenue': float(aggregated['TotalRevenue'].sum()) if 'TotalRevenue' in aggregated.columns else 0,
                        'beers': beers
                    }
                }
            else:
                response_data = {}

        return jsonify(response_data)

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/draft-analyze: {e}")
        import traceback
        traceback.print_exc()
        error_detail = f"{type(e).__name__}: {str(e)}"
        return jsonify({'error': error_detail}), 500

@analysis_bp.route('/api/waiter-analyze', methods=['POST'])
def analyze_waiters():
    """API endpoint для анализа продаж разливного пива по официантам"""
    try:
        data = request.json
        bar_name = data.get('bar')
        days = int(data.get('days', 30))
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        print(f"\n[WAITER] Zapusk analiza po oficiantam...")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")

        # Обработка дат: если переданы конкретные даты, используем их, иначе вычисляем
        if not date_from or not date_to:
            date_to_obj = datetime.now()
            date_from = (date_to_obj - timedelta(days=days)).strftime("%Y-%m-%d")
            date_to = date_to_obj.strftime("%Y-%m-%d")
            print(f"   Period: {days} dney (computed: {date_from} - {date_to})")
        else:
            print(f"   Period: {date_from} - {date_to}")

        # OLAP to-дата exclusive → +1 день
        olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            # Запрашиваем данные разливного с официантами
            report_data = olap.get_draft_sales_by_waiter_report(date_from, olap_date_to, bar_name)

            if not report_data or not report_data.get('data'):
                return jsonify({'error': 'Нет данных за выбранный период'}), 404
        finally:
            olap.disconnect()

        # Преобразуем в DataFrame
        df = pd.DataFrame(report_data['data'])
        df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
        df['DishDiscountSumInt'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce')
        df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce')
        df['ProductCostBase.MarkUp'] = pd.to_numeric(df['ProductCostBase.MarkUp'], errors='coerce')

        print(f"[INFO] Vsego zapisey: {len(df)}")

        # Создаем анализатор по официантам
        waiter_analyzer = WaiterAnalysis(df)

        # Получаем сводку по официантам
        summary = waiter_analyzer.get_waiter_summary(bar_name)

        if summary.empty:
            return jsonify({'error': 'Нет данных об официантах'}), 404

        print(f"[INFO] Vsego oficiantov: {len(summary)}")

        # Форматируем результат
        waiters = waiter_analyzer.format_summary_for_display(summary)

        # Для каждого официанта получаем детали о том, какое пиво он пролил
        for waiter_record in waiters:
            waiter_name = waiter_record['WaiterName']
            # Передаём bar_name из запроса (None = все бары суммируются, иначе конкретный бар)
            beer_details = waiter_analyzer.get_waiter_beer_details(waiter_name, bar_name)
            if not beer_details.empty:
                beer_details_formatted = waiter_analyzer.format_beer_details_for_display(beer_details)
                waiter_record['beers'] = beer_details_formatted  # Все сорта
            else:
                waiter_record['beers'] = []

        response_data = {
            'total_waiters': len(summary),
            'total_liters': float(summary['TotalLiters'].sum()),
            'total_portions': int(summary['TotalPortions'].sum()),
            'total_revenue': float(summary['TotalRevenue'].sum()) if 'TotalRevenue' in summary.columns else 0,
            'total_margin': float(summary['TotalMargin'].sum()) if 'TotalMargin' in summary.columns else 0,
            'waiters': waiters
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/waiter-analyze: {e}")
        import traceback
        traceback.print_exc()
        error_detail = f"{type(e).__name__}: {str(e)}"
        return jsonify({'error': error_detail}), 500


# ============= API для анализа скидок =============

@analysis_bp.route('/api/discount-names', methods=['GET'])
def get_discount_names():
    """Лёгкий API — список названий скидок за последний год"""
    try:
        date_to = datetime.now()
        date_from = date_to - timedelta(days=365)
        olap_date_to = (date_to + timedelta(days=1)).strftime('%Y-%m-%d')
        date_from_str = date_from.strftime('%Y-%m-%d')

        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            result = olap.get_discount_names(date_from_str, olap_date_to)
        finally:
            olap.disconnect()

        if not result or not result.get('data'):
            return jsonify({'names': []})

        names = sorted(set(
            r.get('ItemSaleEventDiscountType', '') for r in result['data']
            if r.get('ItemSaleEventDiscountType')
        ))

        return jsonify({'names': names})

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/discount-names: {e}")
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/api/discount-analyze', methods=['POST'])
def analyze_discounts():
    """API endpoint для анализа скидок — один OLAP, агрегация в Python"""
    try:
        data = request.json
        bar_name = data.get('bar')
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if not date_from or not date_to:
            return jsonify({'error': 'Укажите период'}), 400

        print(f"\n[DISCOUNT] Zapusk analiza skidok...")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")
        print(f"   Period: {date_from} - {date_to}")

        # OLAP to-дата exclusive → +1 день
        olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            report_data = olap.get_discount_report(date_from, olap_date_to, bar_name)

            if not report_data or not report_data.get('data'):
                return jsonify({'error': 'Нет данных за выбранный период'}), 404
        finally:
            olap.disconnect()

        rows = report_data['data']
        print(f"[INFO] Vsego zapisey: {len(rows)}")

        # Извлекаем уникальные названия скидок
        discount_names = sorted(set(
            r.get('ItemSaleEventDiscountType', '') for r in rows
            if r.get('ItemSaleEventDiscountType')
        ))

        # Агрегируем данные по каждому гостю для каждой скидки
        # Структура: { discount_name: { card_number: { name, visits, sum_with_discount, discount_sum, dishes } } }
        discounts_data = {}

        for row in rows:
            discount_name = row.get('ItemSaleEventDiscountType', '')
            if not discount_name:
                continue

            card_number = row.get('Delivery.CustomerCardNumber', '') or 'Без карты'
            customer_name = row.get('Delivery.CustomerName', '') or ''
            order_num = row.get('OrderNum', '')
            dish_name = row.get('DishName', '')
            store_name = row.get('Store.Name', '')
            sum_with_discount = float(row.get('DishDiscountSumInt', 0) or 0)
            discount_sum = float(row.get('DiscountSum', 0) or 0)

            if discount_name not in discounts_data:
                discounts_data[discount_name] = {}

            guests = discounts_data[discount_name]
            if card_number not in guests:
                guests[card_number] = {
                    'card_number': card_number,
                    'customer_name': customer_name,
                    'orders': set(),
                    'sum_with_discount': 0,
                    'discount_sum': 0,
                    'dishes': [],
                    'stores': set()
                }

            guest = guests[card_number]
            if order_num:
                guest['orders'].add(order_num)
            guest['sum_with_discount'] += sum_with_discount
            guest['discount_sum'] += discount_sum
            if dish_name:
                guest['dishes'].append({
                    'name': dish_name,
                    'sum_with_discount': sum_with_discount,
                    'discount_sum': discount_sum,
                    'store': store_name,
                    'order_num': order_num
                })
            if store_name:
                guest['stores'].add(store_name)

        # Агрегируем сводку по барам для каждой скидки
        stores_summary = {}
        for row in rows:
            discount_name = row.get('ItemSaleEventDiscountType', '')
            if not discount_name:
                continue
            store_name = row.get('Store.Name', '') or 'Неизвестно'
            order_num = row.get('OrderNum', '')
            card_number = row.get('Delivery.CustomerCardNumber', '')
            sum_with_discount = float(row.get('DishDiscountSumInt', 0) or 0)
            discount_sum = float(row.get('DiscountSum', 0) or 0)

            if discount_name not in stores_summary:
                stores_summary[discount_name] = {}
            if store_name not in stores_summary[discount_name]:
                stores_summary[discount_name][store_name] = {
                    'orders': set(),
                    'cards': set(),
                    'sum_with_discount': 0,
                    'discount_sum': 0
                }

            s = stores_summary[discount_name][store_name]
            if order_num:
                s['orders'].add(order_num)
            if card_number:
                s['cards'].add(card_number)
            s['sum_with_discount'] += sum_with_discount
            s['discount_sum'] += discount_sum

        # Преобразуем сводку по барам в сериализуемый формат
        stores_result = {}
        for disc_name, stores in stores_summary.items():
            store_list = []
            for store_name, s in stores.items():
                store_list.append({
                    'store': store_name,
                    'orders_count': len(s['orders']),
                    'guests_count': len(s['cards']),
                    'sum_with_discount': round(s['sum_with_discount'], 2),
                    'discount_sum': round(s['discount_sum'], 2)
                })
            store_list.sort(key=lambda x: x['discount_sum'], reverse=True)
            stores_result[disc_name] = store_list

        # Преобразуем гостей в сериализуемый формат
        result = {}
        for disc_name, guests in discounts_data.items():
            guest_list = []
            for card, g in guests.items():
                guest_list.append({
                    'card_number': g['card_number'],
                    'customer_name': g['customer_name'],
                    'visits': len(g['orders']),
                    'sum_with_discount': round(g['sum_with_discount'], 2),
                    'discount_sum': round(g['discount_sum'], 2),
                    'stores': sorted(g['stores']),
                    'dishes': g['dishes']
                })
            guest_list.sort(key=lambda x: x['visits'], reverse=True)
            result[disc_name] = guest_list

        return jsonify({
            'discount_names': discount_names,
            'discounts': result,
            'stores_summary': stores_result,
            'total_rows': len(rows)
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/discount-analyze: {e}")
        import traceback
        traceback.print_exc()
        error_detail = f"{type(e).__name__}: {str(e)}"
        return jsonify({'error': error_detail}), 500

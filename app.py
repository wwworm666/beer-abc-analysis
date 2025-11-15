from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.data_processor import BeerDataProcessor
from core.abc_analysis import ABCAnalysis
from core.xyz_analysis import XYZAnalysis
from core.category_analysis import CategoryAnalysis
from core.draft_analysis import DraftAnalysis
from core.waiter_analysis import WaiterAnalysis
from core.taps_manager import TapsManager

app = Flask(__name__)

# Инициализируем менеджер кранов
# Если на Render (есть диск /kultura), используем его для постоянного хранения
# Иначе используем локальную папку data/
TAPS_DATA_PATH = os.environ.get('TAPS_DATA_PATH', 'data/taps_data.json')
if os.path.exists('/kultura'):
    TAPS_DATA_PATH = '/kultura/taps_data.json'
    print(f"[INFO] Используется Render Disk: {TAPS_DATA_PATH}")
else:
    print(f"[INFO] Используется локальный путь: {TAPS_DATA_PATH}")

taps_manager = TapsManager(data_file=TAPS_DATA_PATH)

# Список баров
BARS = [
    "Большой пр. В.О",
    "Лиговский",
    "Кременчугская",
    "Варшавская"
]

@app.route('/')
def index():
    """Главная страница - фасовка"""
    return render_template('index.html', bars=BARS)

@app.route('/draft')
def draft():
    """Страница разливного пива"""
    return render_template('draft.html', bars=BARS)

@app.route('/waiters')
def waiters():
    """Страница анализа по официантам"""
    return render_template('waiters.html', bars=BARS)

@app.route('/taps')
def taps():
    """Главная страница управления кранами - выбор бара"""
    return render_template('taps_main.html')

@app.route('/stocks')
def stocks():
    """Страница управления стоками и формирования заказов"""
    return render_template('stocks.html', bars=BARS)

@app.route('/taps/<bar_id>')
def taps_bar(bar_id):
    """Страница управления кранами конкретного бара"""
    bars_config = {
        'bar1': {'name': 'Большой пр. В.О', 'taps': 24},
        'bar2': {'name': 'Лиговский', 'taps': 12},
        'bar3': {'name': 'Кременчугская', 'taps': 12},
        'bar4': {'name': 'Варшавская', 'taps': 12}
    }

    if bar_id not in bars_config:
        return "Бар не найден", 404

    bar_info = bars_config[bar_id]
    return render_template('taps_bar.html',
                         bar_id=bar_id,
                         bar_name=bar_info['name'],
                         tap_count=bar_info['taps'])

@app.route('/api/test', methods=['GET', 'POST'])
def test_endpoint():
    """Тестовый endpoint"""
    print("[TEST] Test endpoint called!")
    return jsonify({'status': 'ok', 'message': 'Test successful'})

@app.route('/api/connection-status', methods=['GET'])
def connection_status():
    """API endpoint для проверки подключения к iiko API"""
    try:
        olap = OlapReports()
        is_connected = olap.connect()
        if is_connected:
            olap.disconnect()
            return jsonify({
                'status': 'connected',
                'message': 'Подключение к iiko API успешно'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Не удалось подключиться к iiko API'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка подключения: {str(e)}'
        }), 500

@app.route('/api/analyze', methods=['POST'])
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
        
        # Запрашиваем данные
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        report_data = olap.get_beer_sales_report(date_from, date_to, bar_name)
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
                results = {"Общая": combined_all}
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
@app.route('/api/weekly-chart/<bar_name>/<beer_name>', methods=['GET'])
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

@app.route('/api/categories', methods=['POST'])
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

        # Запрашиваем данные
        print("   [2/8] Zapros dannykh iz OLAP...")
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        report_data = olap.get_beer_sales_report(date_from, date_to, bar_name)
        olap.disconnect()

        if not report_data or not report_data.get('data'):
            print(f"   [ERROR] Net dannykh za period {date_from} - {date_to}")
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

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

@app.route('/api/draft-analyze', methods=['POST'])
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
            # Вычисляем даты на основе дней
            date_to = datetime.now().strftime("%Y-%m-%d")
            date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            print(f"   Period: {days} dney (computed: {date_from} - {date_to})")
        else:
            print(f"   Period: {date_from} - {date_to}")

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
        olap.disconnect()

        if not report_data or not report_data.get('data'):
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

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

@app.route('/api/waiter-analyze', methods=['POST'])
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
            # Вычисляем даты на основе дней
            date_to = datetime.now().strftime("%Y-%m-%d")
            date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            print(f"   Period: {days} dney (computed: {date_from} - {date_to})")
        else:
            print(f"   Period: {date_from} - {date_to}")

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        # Запрашиваем данные разливного с официантами
        report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to, bar_name)
        olap.disconnect()

        if not report_data or not report_data.get('data'):
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

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
            waiter_bar = waiter_record['Bar'] if bar_name else None

            # Получаем детали по пиву
            beer_details = waiter_analyzer.get_waiter_beer_details(waiter_name, waiter_bar)
            if not beer_details.empty:
                beer_details_formatted = waiter_analyzer.format_beer_details_for_display(beer_details)
                waiter_record['beers'] = beer_details_formatted[:10]  # Топ-10 сортов
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

# ============= API для управления пивными кранами =============

@app.route('/api/taps/bars', methods=['GET'])
def get_bars_list():
    """Получить список всех баров"""
    try:
        bars = taps_manager.get_bars()
        return jsonify(bars)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/bars: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/<bar_id>', methods=['GET'])
def get_bar_taps(bar_id):
    """Получить состояние кранов конкретного бара"""
    try:
        result = taps_manager.get_bar_taps(bar_id)
        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/<bar_id>/start', methods=['POST'])
def start_tap(bar_id):
    """Подключить кегу (начать работу крана)"""
    try:
        data = request.json
        tap_number = data.get('tap_number')
        beer_name = data.get('beer_name')
        keg_id = data.get('keg_id')

        if not all([tap_number, beer_name, keg_id]):
            return jsonify({'error': 'Требуются: tap_number, beer_name, keg_id'}), 400

        result = taps_manager.start_tap(bar_id, int(tap_number), beer_name, keg_id)

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/start: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/<bar_id>/stop', methods=['POST'])
def stop_tap(bar_id):
    """Остановить кран (кега закончилась)"""
    try:
        data = request.json
        tap_number = data.get('tap_number')

        if not tap_number:
            return jsonify({'error': 'Требуется: tap_number'}), 400

        result = taps_manager.stop_tap(bar_id, int(tap_number))

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/stop: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/<bar_id>/replace', methods=['POST'])
def replace_tap(bar_id):
    """Заменить кегу (смена сорта пива)"""
    try:
        data = request.json
        tap_number = data.get('tap_number')
        beer_name = data.get('beer_name')
        keg_id = data.get('keg_id')

        if not all([tap_number, beer_name, keg_id]):
            return jsonify({'error': 'Требуются: tap_number, beer_name, keg_id'}), 400

        result = taps_manager.replace_tap(bar_id, int(tap_number), beer_name, keg_id)

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/replace: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/<bar_id>/<int:tap_number>/history', methods=['GET'])
def get_tap_history(bar_id, tap_number):
    """Получить историю действий крана"""
    try:
        limit = request.args.get('limit', 50, type=int)
        result = taps_manager.get_tap_history(bar_id, tap_number, limit)

        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/{tap_number}/history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/events/all', methods=['GET'])
def get_all_events():
    """Получить все события"""
    try:
        bar_id = request.args.get('bar_id', None)
        limit = request.args.get('limit', 100, type=int)

        events = taps_manager.get_all_events(bar_id, limit)
        return jsonify({'events': events})
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/events/all: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/statistics', methods=['GET'])
def get_statistics():
    """Получить статистику по кранам"""
    try:
        bar_id = request.args.get('bar_id', None)
        result = taps_manager.get_statistics(bar_id)

        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/statistics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/export-taplist', methods=['GET'])
def export_taplist():
    """Экспортировать текущий таплист в CSV формате"""
    try:
        from io import StringIO
        import csv

        # Опциональный параметр bar_id для фильтрации по конкретному бару
        bar_id_filter = request.args.get('bar_id', None)

        # Получаем список всех баров
        bars = taps_manager.get_bars()

        # Фильтруем по конкретному бару, если указан
        if bar_id_filter:
            bars = [bar for bar in bars if bar['bar_id'] == bar_id_filter]

        # Создаём CSV в памяти
        output = StringIO()
        writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_MINIMAL)

        # Заголовок
        writer.writerow(['Бар', 'Номер крана', 'Название пива'])

        # Собираем данные по всем барам (или по одному, если bar_id_filter указан)
        for bar in bars:
            bar_id = bar['bar_id']
            bar_name = bar['name']

            # Получаем краны бара
            bar_data = taps_manager.get_bar_taps(bar_id)
            if 'error' in bar_data:
                continue

            # Добавляем все краны (активные и пустые)
            for tap in bar_data.get('taps', []):
                beer_name = tap['current_beer'] if tap['current_beer'] else '(пусто)'
                writer.writerow([
                    bar_name,
                    tap['tap_number'],
                    beer_name
                ])

        # Готовим ответ
        output.seek(0)
        csv_content = output.getvalue()
        output.close()

        # Формируем имя файла
        if bar_id_filter and bars:
            # Используем bar_id вместо имени для безопасности
            filename = f"taplist_{bar_id_filter}.csv"
        else:
            filename = "taplist.csv"

        # Создаём response с правильными заголовками
        from flask import make_response
        from urllib.parse import quote
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        # Используем RFC 5987 для корректной работы с кириллицей
        response.headers['Content-Disposition'] = f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"

        return response

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/export-taplist: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/taps/<bar_id>/stats', methods=['GET'])
def get_bar_stats(bar_id):
    """Получить краткую статистику для карточки бара"""
    try:
        result = taps_manager.get_bar_taps(bar_id)
        if 'error' in result:
            return jsonify({'active': 0, 'empty': 12}), 200

        taps = result.get('taps', [])
        active = len([t for t in taps if t.get('status') == 'active'])
        total = result.get('total_taps', 12)
        empty = total - len([t for t in taps if t.get('status') in ['active', 'replacing']])

        return jsonify({
            'active': active,
            'empty': empty,
            'total': total
        })
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/stats: {e}")
        return jsonify({'active': 0, 'empty': 12}), 200

@app.route('/api/beers/draft', methods=['GET'])
def get_draft_beers():
    """Получить список разливного пива из номенклатуры"""
    try:
        # Читаем файл с номенклатурой
        import os
        products_file = os.path.join('data', 'all_products.json')

        if not os.path.exists(products_file):
            # Если файла нет, возвращаем пустой список
            return jsonify({'beers': []})

        with open(products_file, 'r', encoding='utf-8') as f:
            products = json.load(f)

        # Фильтруем только разливное пиво
        # Разливное обычно содержит "кег", "KEG", "30L", "50L" в названии
        draft_beers = []
        seen_names = set()

        for product in products:
            name = product.get('name', '')
            # Ищем признаки разливного пива
            if any(keyword in name.upper() for keyword in ['КЕГ', 'KEG', '30L', '50L', 'DRAFT']):
                # Убираем дубликаты по названию
                clean_name = name.strip()
                if clean_name and clean_name not in seen_names:
                    draft_beers.append({
                        'id': product.get('id'),
                        'name': clean_name,
                        'num': product.get('num')
                    })
                    seen_names.add(clean_name)

        # Сортируем по названию
        draft_beers.sort(key=lambda x: x['name'])

        return jsonify({'beers': draft_beers})
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/beers/draft: {e}")
        return jsonify({'beers': []}), 200

@app.route('/api/update-nomenclature', methods=['POST'])
def update_nomenclature():
    """Обновить список продуктов из iiko"""
    try:
        import requests
        import xml.etree.ElementTree as ET
        from core.iiko_api import IikoAPI

        print("[INFO] Начинаем обновление номенклатуры...")

        # Подключаемся к iiko
        api = IikoAPI()
        if not api.authenticate():
            print("[ERROR] Не удалось авторизоваться в iiko")
            return jsonify({'success': False, 'error': 'Authentication failed'}), 500

        # Получаем список продуктов
        url = f"{api.base_url}/products"
        params = {"key": api.token}

        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            api.logout()
            print(f"[ERROR] Ошибка получения продуктов: {response.status_code}")
            return jsonify({'success': False, 'error': f'API error: {response.status_code}'}), 500

        # Парсим XML
        root = ET.fromstring(response.content)
        products = []

        for product in root.findall('.//productDto'):
            product_id = product.find('id').text if product.find('id') is not None else None
            name = product.find('name').text if product.find('name') is not None else None
            parent_id = product.find('parentId').text if product.find('parentId') is not None else None
            num = product.find('num').text if product.find('num') is not None else None

            products.append({
                'id': product_id,
                'name': name,
                'parent_id': parent_id,
                'num': num
            })

        # Сохраняем в файл
        products_file = os.path.join('data', 'all_products.json')
        with open(products_file, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)

        api.logout()

        print(f"[OK] Обновлено продуктов: {len(products)}")
        return jsonify({'success': True, 'count': len(products)})

    except Exception as e:
        print(f"[ERROR] Ошибка при обновлении номенклатуры: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stocks/taplist', methods=['GET'])
def get_taplist_stocks():
    """API endpoint для получения остатков КЕГ из iiko API (только активные на кранах)"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Получаем список активных кег из taps_manager
        bar_id_map = {
            'Большой пр. В.О': 'bar1',
            'Лиговский': 'bar2',
            'Кременчугская': 'bar3',
            'Варшавская': 'bar4',
            'Общая': None  # Для "Общая" покажем все бары
        }

        # Маппинг баров на склады iiko (store_id)
        store_id_map = {
            'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',  # Большой пр. В.О
            'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',  # Лиговский
            'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',  # Кременчугская
            'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',  # Варшавская
        }

        # Собираем список активных кег со всех кранов с номерами кранов
        active_beers = set()
        beer_to_taps = {}  # { beer_name: [tap_numbers] }

        import re

        if bar == 'Общая':
            # Для "Общая" собираем со всех баров
            for bar_id in ['bar1', 'bar2', 'bar3', 'bar4']:
                result = taps_manager.get_bar_taps(bar_id)
                if 'taps' in result:
                    for tap in result['taps']:
                        if tap.get('status') == 'active' and tap.get('current_beer'):
                            beer_name = tap['current_beer']
                            tap_number = tap.get('tap_number', '?')
                            # Обрабатываем название так же, как из остатков
                            beer_name = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r'^Кег\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',?\s*\d+\s*л.*', '', beer_name)
                            beer_name = re.sub(r'\s+л\s*$', '', beer_name)
                            beer_name = re.sub(r',?\s*кег.*', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',\s*$', '', beer_name)
                            beer_name = beer_name.strip()
                            active_beers.add(beer_name)
                            if beer_name not in beer_to_taps:
                                beer_to_taps[beer_name] = []
                            beer_to_taps[beer_name].append(tap_number)
        else:
            bar_id = bar_id_map.get(bar)
            if bar_id:
                result = taps_manager.get_bar_taps(bar_id)
                if 'taps' in result:
                    for tap in result['taps']:
                        if tap.get('status') == 'active' and tap.get('current_beer'):
                            beer_name = tap['current_beer']
                            tap_number = tap.get('tap_number', '?')
                            # Обрабатываем название так же, как из остатков
                            beer_name = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r'^Кег\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',?\s*\d+\s*л.*', '', beer_name)
                            beer_name = re.sub(r'\s+л\s*$', '', beer_name)
                            beer_name = re.sub(r',?\s*кег.*', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',\s*$', '', beer_name)
                            beer_name = beer_name.strip()
                            active_beers.add(beer_name)
                            if beer_name not in beer_to_taps:
                                beer_to_taps[beer_name] = []
                            beer_to_taps[beer_name].append(tap_number)

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        # Получаем номенклатуру для маппинга GUID -> информация о товаре
        nomenclature = olap.get_nomenclature()
        if not nomenclature:
            olap.disconnect()
            return jsonify({'error': 'Не удалось получить номенклатуру'}), 500

        # Получаем РЕАЛЬНЫЕ остатки на складах (текущее время)
        from datetime import datetime
        current_time = datetime.now()
        print(f"[DEBUG] Текущее время сервера: {current_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

        balances = olap.get_store_balances()
        if not balances:
            olap.disconnect()
            return jsonify({'error': 'Не удалось получить остатки'}), 500

        print(f"[DEBUG] Получено {len(balances)} записей остатков", flush=True)

        olap.disconnect()

        # Определяем склад для фильтрации
        target_store_id = None
        if bar != 'Общая':
            bar_id = bar_id_map.get(bar)
            if bar_id:
                target_store_id = store_id_map.get(bar_id)

        # Обрабатываем остатки кег (GOODS в литрах)
        beer_stocks = {}

        for balance in balances:
            product_id = balance.get('product')
            amount = balance.get('amount', 0)
            store_id = balance.get('store')

            # Фильтруем по складу конкретного бара (если не "Общая")
            if target_store_id and store_id != target_store_id:
                continue

            # НЕ пропускаем отрицательные остатки - они важны для контроля!
            # Пропускаем только нулевые, если кега не активна
            if amount == 0:
                # Пропустим потом при проверке на активность
                pass

            # Получаем информацию о товаре из номенклатуры
            product_info = nomenclature.get(product_id)
            if not product_info:
                continue

            # Берем только GOODS (кеги - это товары, а не блюда!)
            if product_info.get('type') != 'GOODS':
                continue

            # Берем только литры (кеги измеряются в литрах)
            if product_info.get('mainUnit') != 'л':
                continue

            product_name = product_info.get('name', product_id)

            # Убираем "Кег" и объёмы из названия для агрегации
            import re
            base_name = product_name
            base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
            # Убираем объемы: ", 20 л", "20 л", или просто " л" в конце
            base_name = re.sub(r',?\s*\d+\s*л.*', '', base_name)
            base_name = re.sub(r'\s+л\s*$', '', base_name)  # Убираем " л" в конце если осталось
            base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
            base_name = re.sub(r',\s*$', '', base_name)  # Убираем запятую в конце
            base_name = base_name.strip()

            # ФИЛЬТР: Показываем только кеги, которые стоят на кранах
            # Названия идентичны в iiko и на кранах, поэтому только точное сравнение
            if active_beers:
                is_active = base_name in active_beers

                # Если кега не активна, пропускаем
                if not is_active:
                    continue

            category = product_info.get('category', 'Разливное')

            if base_name not in beer_stocks:
                beer_stocks[base_name] = {
                    'remaining_liters': 0,
                    'category': category,
                    'on_tap': base_name in active_beers if active_beers else False
                }

            # Суммируем остатки по базовому названию
            beer_stocks[base_name]['remaining_liters'] += amount

        # Добавляем активные краны, которых нет в остатках (с нулевым остатком)
        for active_beer in active_beers:
            if active_beer not in beer_stocks:
                beer_stocks[active_beer] = {
                    'remaining_liters': 0,
                    'category': 'Разливное',
                    'on_tap': True
                }

        # Формируем итоговый список
        taps_data = []
        total_liters = 0
        low_stock_count = 0
        negative_stock_count = 0
        active_taps_count = len(active_beers)

        for beer_name, beer_data in beer_stocks.items():
            remaining_liters = beer_data['remaining_liters']

            # НЕ пропускаем активные краны даже с нулевым или отрицательным остатком
            # (чтобы видеть какие кеги нужно пополнить)
            if remaining_liters == 0 and not beer_data.get('on_tap', False):
                continue

            total_liters += remaining_liters if remaining_liters > 0 else 0

            # Определяем уровень остатка
            if remaining_liters < 0:
                stock_level = 'negative'
                negative_stock_count += 1
                low_stock_count += 1
            elif remaining_liters < 10:
                stock_level = 'low'
                low_stock_count += 1
            elif remaining_liters < 25:
                stock_level = 'medium'
            else:
                stock_level = 'high'

            # Получаем номера кранов для этого пива
            tap_numbers = beer_to_taps.get(beer_name, [])
            tap_numbers_str = ', '.join(map(str, sorted(tap_numbers))) if tap_numbers else '—'

            taps_data.append({
                'beer_name': beer_name,
                'category': beer_data['category'],
                'remaining_liters': round(remaining_liters, 1),
                'stock_level': stock_level,
                'on_tap': beer_data.get('on_tap', False),
                'tap_numbers': tap_numbers_str,
                'taps_count': len(tap_numbers)
            })

        # Сортируем по остатку (от меньшего к большему - что заканчивается сверху)
        taps_data.sort(key=lambda x: x['remaining_liters'])

        return jsonify({
            'total_items': len(taps_data),
            'total_liters': round(total_liters, 1),
            'low_stock_count': low_stock_count,
            'negative_stock_count': negative_stock_count,
            'active_taps_count': active_taps_count,
            'taps': taps_data
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/taplist: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/kitchen', methods=['GET'])
def get_kitchen_stocks():
    """API endpoint для получения товаров с остатками"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        # Получаем складские операции за последние 30 дней
        # API требует формат DD.MM.YYYY
        date_to_obj = datetime.now()
        date_from_obj = datetime.now() - timedelta(days=30)
        date_to = date_to_obj.strftime("%d.%m.%Y")
        date_from = date_from_obj.strftime("%d.%m.%Y")

        # Получаем номенклатуру товаров (GUID -> название)
        nomenclature = olap.get_nomenclature()

        if not nomenclature:
            olap.disconnect()
            return jsonify({'error': 'Не удалось получить номенклатуру товаров'}), 500

        # Получаем отчет по складским операциям с товарами
        bar_name = bar if bar != 'Общая' else None
        store_data = olap.get_store_operations_report(date_from, date_to, bar_name)

        if not store_data:
            olap.disconnect()
            return jsonify({'error': 'Не удалось получить данные о товарах'}), 500

        # Обрабатываем данные о товарах
        products_dict = {}

        for record in store_data:
            product_id = record.get('product')
            if not product_id:
                continue

            # Получаем информацию о товаре из номенклатуры
            product_info = nomenclature.get(product_id)
            if not product_info:
                continue  # Товар не найден в номенклатуре

            # Фильтруем товары: исключаем пиво и напитки
            # Пропускаем DISH (блюда - это разливное пиво)
            if product_info.get('type') == 'DISH':
                continue

            # Используем белый список категорий для еды/продуктов
            # Остальное (пиво, напитки) исключаем
            category = product_info.get('category', '') or ''

            # Белый список - только эти категории попадают в стоки
            food_categories = [
                'Метро', 'ООО "Май"', 'ООО "КВГ"', 'ГС Маркет',
                'ИП Тихомиров', 'ООО "Кулинарпродторг"',
                'ИП Новиков', 'ООО МП Арсенал', 'Лента',
                'ООО "МП-Арсенал АО"', 'Криспи',
                'ООО "ВУРСТХАУСМАНУФАКТУР"', 'ООО "Арбореал"'
            ]

            # Если категория не указана или не в белом списке - пропускаем
            if not category or not any(food_cat in category for food_cat in food_categories):
                continue

            # Дополнительно фильтруем по названию (на случай если категория не указана)
            product_name = product_info.get('name', product_id)
            if any(keyword in product_name.lower() for keyword in ['пиво', 'beer', 'ipa', 'лагер', 'эль', 'стаут']):
                continue

            if product_id not in products_dict:
                products_dict[product_id] = {
                    'id': product_id,
                    'name': product_name,
                    'category': category or 'Товары',
                    'incoming': 0,
                    'outgoing': 0,
                    'operations_count': 0
                }

            # Учитываем приход и расход
            amount = float(record.get('amount', 0) or 0)
            is_incoming = record.get('incoming', 'false') == 'true'

            products_dict[product_id]['operations_count'] += 1

            if is_incoming:
                products_dict[product_id]['incoming'] += amount
            else:
                products_dict[product_id]['outgoing'] += abs(amount)

        # Формируем список товаров с остатками
        items = []
        for product_id, product_data in products_dict.items():
            # Рассчитываем текущий остаток
            current_stock = product_data['incoming'] - product_data['outgoing']

            # Рассчитываем средний расход в день
            days_in_period = 30
            avg_consumption = product_data['outgoing'] / days_in_period if days_in_period > 0 else 0

            # Определяем уровень остатков (сколько дней хватит)
            if avg_consumption > 0:
                days_left = current_stock / avg_consumption
                if days_left < 3:
                    stock_level = 'low'
                elif days_left < 7:
                    stock_level = 'medium'
                else:
                    stock_level = 'high'
            else:
                stock_level = 'high'

            items.append({
                'category': product_data['category'],
                'name': product_data['name'],
                'stock': round(current_stock, 1),
                'avg_sales': round(avg_consumption, 2),
                'stock_level': stock_level
            })

        olap.disconnect()

        # Сортируем по категориям и названиям
        items.sort(key=lambda x: (x['category'], x['name']))

        low_stock_count = len([item for item in items if item['stock_level'] == 'low'])

        return jsonify({
            'total_items': len(items),
            'low_stock_count': low_stock_count,
            'items': items
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/kitchen: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/bottles', methods=['GET'])
def get_bottles_stocks():
    """API endpoint для получения фасованного пива с остатками"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        # Получаем складские операции за последние 30 дней
        date_to_obj = datetime.now()
        date_from_obj = datetime.now() - timedelta(days=30)
        date_to = date_to_obj.strftime("%d.%m.%Y")
        date_from = date_from_obj.strftime("%d.%m.%Y")

        # Получаем номенклатуру товаров
        nomenclature = olap.get_nomenclature()

        if not nomenclature:
            olap.disconnect()
            return jsonify({'error': 'Не удалось получить номенклатуру товаров'}), 500

        # Получаем отчет по складским операциям
        bar_name = bar if bar != 'Общая' else None
        store_data = olap.get_store_operations_report(date_from, date_to, bar_name)

        if not store_data:
            olap.disconnect()
            return jsonify({'error': 'Не удалось получить данные о товарах'}), 500

        # Обрабатываем данные о фасовке
        products_dict = {}
        checked_products = 0
        matched_products = 0

        for record in store_data:
            product_id = record.get('product')
            if not product_id:
                continue

            # Получаем информацию о товаре из номенклатуры
            product_info = nomenclature.get(product_id)
            if not product_info:
                continue

            checked_products += 1

            # Фильтруем фасованное пиво: тип GOODS + единица измерения "шт" + в названии есть пиво/beer
            product_type = product_info.get('type')
            product_unit = product_info.get('mainUnit')
            product_name = product_info.get('name', product_id)
            product_name_lower = product_name.lower()

            # Проверяем: тип GOODS, единица "шт", и в названии есть пивные слова
            if product_type != 'GOODS':
                continue

            if product_unit != 'шт':
                continue

            # Проверяем что это пиво
            beer_keywords = ['пив', 'beer', 'ipa', 'лагер', 'эль', 'стаут', 'портер', 'ales']
            if not any(keyword in product_name_lower for keyword in beer_keywords):
                continue

            matched_products += 1
            supplier = product_info.get('category', 'Без поставщика')

            # Отладочный вывод
            if matched_products <= 5:
                print(f"[DEBUG] Найдена фасовка: {product_name}, категория: {supplier}")

            if product_id not in products_dict:
                products_dict[product_id] = {
                    'id': product_id,
                    'name': product_name,
                    'category': supplier,
                    'incoming': 0,
                    'outgoing': 0,
                    'operations_count': 0
                }

            # Учитываем приход и расход
            amount = float(record.get('amount', 0) or 0)
            is_incoming = record.get('incoming', 'false') == 'true'

            products_dict[product_id]['operations_count'] += 1

            if is_incoming:
                products_dict[product_id]['incoming'] += amount
            else:
                products_dict[product_id]['outgoing'] += abs(amount)

        # Формируем список товаров с остатками
        items = []
        for product_id, product_data in products_dict.items():
            # Рассчитываем текущий остаток
            current_stock = product_data['incoming'] - product_data['outgoing']

            # Рассчитываем средний расход в день
            days_in_period = 30
            avg_consumption = product_data['outgoing'] / days_in_period if days_in_period > 0 else 0

            # Определяем уровень остатков (сколько дней хватит)
            if avg_consumption > 0:
                days_left = current_stock / avg_consumption
                if days_left < 3:
                    stock_level = 'low'
                elif days_left < 7:
                    stock_level = 'medium'
                else:
                    stock_level = 'high'
            else:
                stock_level = 'high'

            items.append({
                'category': product_data['category'],
                'name': product_data['name'],
                'stock': round(current_stock, 1),
                'avg_sales': round(avg_consumption, 2),
                'stock_level': stock_level
            })

        olap.disconnect()

        # Сортируем по категориям и названиям
        items.sort(key=lambda x: (x['category'], x['name']))

        low_stock_count = len([item for item in items if item['stock_level'] == 'low'])

        # Отладочная информация
        print(f"\n[BOTTLES DEBUG]")
        print(f"   Проверено товаров: {checked_products}")
        print(f"   Найдено фасовки: {matched_products}")
        print(f"   Итого позиций: {len(items)}")
        print(f"   Требуют пополнения: {low_stock_count}")

        return jsonify({
            'total_items': len(items),
            'low_stock_count': low_stock_count,
            'items': items
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/bottles: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("BEER ABC/XYZ ANALYSIS")
    print("="*60)
    print("\nZapusk veb-servera...")
    print("Otkroyte v brauzere: http://localhost:5000")
    print("\nDlya ostanovki nazhmite Ctrl+C\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
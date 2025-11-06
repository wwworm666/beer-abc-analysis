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
    """API endpoint для получения таплиста с остатками"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Получаем данные о кранах из TapsManager
        bar_id_map = {
            'Большой пр. В.О': 'bar1',
            'Лиговский': 'bar2',
            'Кременчугская': 'bar3',
            'Варшавская': 'bar4'
        }

        bar_id = bar_id_map.get(bar)
        if not bar_id:
            return jsonify({'error': 'Неверное название бара'}), 400

        result = taps_manager.get_bar_taps(bar_id)
        if 'error' in result:
            return jsonify({'error': result['error']}), 404

        taps = result.get('taps', [])

        # Формируем данные с уровнями остатков
        taps_data = []
        total_liters = 0
        active_taps = 0
        low_stock_count = 0

        for tap in taps:
            if tap.get('status') == 'active':
                active_taps += 1
                # Предполагаем, что в среднем осталось 25л из 50л кеги
                # В реальности нужно получать данные из iiko о фактическом остатке
                remaining_liters = 25.0
                total_liters += remaining_liters

                # Определяем уровень остатка (простая логика)
                if remaining_liters < 10:
                    stock_level = 'low'
                    low_stock_count += 1
                elif remaining_liters < 25:
                    stock_level = 'medium'
                else:
                    stock_level = 'high'

                taps_data.append({
                    'tap_number': tap['tap_number'],
                    'beer_name': tap['current_beer'],
                    'remaining_liters': remaining_liters,
                    'stock_level': stock_level
                })

        return jsonify({
            'active_taps': active_taps,
            'total_liters': total_liters,
            'low_stock_count': low_stock_count,
            'taps': taps_data
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/taplist: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/kitchen', methods=['GET'])
def get_kitchen_stocks():
    """API endpoint для получения меню кухни с остатками"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        # Получаем данные о продажах за последние 30 дней для расчета средних продаж
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Здесь должен быть запрос к iiko для получения остатков на складе
        # Для примера создадим mock данные

        items = []
        categories = ['Закуски', 'Горячее', 'Салаты', 'Десерты']

        # Mock данные - в реальности нужен запрос к iiko
        import random
        for i, category in enumerate(categories):
            for j in range(5):
                stock = random.randint(0, 50)
                avg_sales = random.uniform(2, 10)

                if stock < 5:
                    stock_level = 'low'
                elif stock < 20:
                    stock_level = 'medium'
                else:
                    stock_level = 'high'

                items.append({
                    'category': category,
                    'name': f'{category} блюдо {j+1}',
                    'stock': stock,
                    'avg_sales': avg_sales,
                    'stock_level': stock_level
                })

        olap.disconnect()

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

if __name__ == '__main__':
    print("\n" + "="*60)
    print("BEER ABC/XYZ ANALYSIS")
    print("="*60)
    print("\nZapusk veb-servera...")
    print("Otkroyte v brauzere: http://localhost:5000")
    print("\nDlya ostanovki nazhmite Ctrl+C\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
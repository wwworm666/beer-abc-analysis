from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
from datetime import datetime, timedelta
from olap_reports import OlapReports
from data_processor import BeerDataProcessor
from abc_analysis import ABCAnalysis
from xyz_analysis import XYZAnalysis
from category_analysis import CategoryAnalysis

app = Flask(__name__)

# Список баров
BARS = [
    "Большой пр. В.О",
    "Лиговский",
    "Кременчугская",
    "Варшавская"
]

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html', bars=BARS)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """API endpoint для запуска анализа"""
    try:
        data = request.json
        bar_name = data.get('bar')
        days = int(data.get('days', 30))
        
        print(f"\n🔄 Запуск анализа...")
        print(f"   Бар: {bar_name if bar_name else 'ВСЕ'}")
        print(f"   Период: {days} дней")
        
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
            # Анализ для всех баров
            abc_results = abc_analyzer.perform_full_analysis()
            results = {}
            
            for bar, abc_df in abc_results.items():
                xyz_df = xyz_analyzer.perform_xyz_analysis_by_bar(bar)
                
                if not abc_df.empty and not xyz_df.empty:
                    combined = abc_df.merge(
                        xyz_df[['Beer', 'XYZ_Category', 'CoefficientOfVariation']], 
                        on='Beer', 
                        how='left'
                    )
                    combined['XYZ_Category'].fillna('Z', inplace=True)
                    combined['CoefficientOfVariation'].fillna(100, inplace=True)
                    combined['ABCXYZ_Combined'] = combined['ABC_Combined'] + '-' + combined['XYZ_Category']
                    results[bar] = combined
                else:
                    results[bar] = abc_df
        
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
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
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

        print(f"\n🔄 Запуск анализа по категориям...")
        print(f"   Бар: {bar_name if bar_name else 'ВСЕ'}")
        print(f"   Период: {days} дней")

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

        # Создаем анализатор категорий
        cat_analyzer = CategoryAnalysis(agg_data, processor.df)

        # XYZ анализатор для добавления данных о стабильности
        xyz_analyzer = XYZAnalysis(processor.df)

        # Получаем сводку по категориям
        summary = cat_analyzer.get_category_summary(bar_name)

        # Получаем детальный анализ для всех категорий
        category_results = {}

        if bar_name:
            # Для одного бара
            categories = cat_analyzer.get_categories(bar_name)

            for category in categories:
                result = cat_analyzer.analyze_category(category, bar_name)
                if result:
                    # Добавляем XYZ данные
                    result = cat_analyzer.add_xyz_to_category_analysis(
                        result, xyz_analyzer, bar_name
                    )
                    category_results[category] = result
        else:
            # Для всех баров - группируем по барам
            for bar in BARS:
                bar_results = {}
                categories = cat_analyzer.get_categories(bar)

                for category in categories:
                    result = cat_analyzer.analyze_category(category, bar)
                    if result:
                        result = cat_analyzer.add_xyz_to_category_analysis(
                            result, xyz_analyzer, bar
                        )
                        bar_results[category] = result

                if bar_results:
                    category_results[bar] = bar_results

        # Формируем ответ
        response_data = {
            'summary': summary.to_dict('records'),
            'categories': category_results
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Ошибка анализа категорий: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🍺 BEER ABC/XYZ ANALYSIS")
    print("="*60)
    print("\n🌐 Запуск веб-сервера...")
    print("📍 Откройте в браузере: http://localhost:5000")
    print("\n⚠️  Для остановки нажмите Ctrl+C\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
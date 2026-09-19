from flask import Blueprint, request, jsonify
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from core.olap_reports import OlapReports
from core.packaging_analysis import PackagingAnalysis
from core.draft_analysis import DraftAnalysis
from core.draft_kegs import DraftKegAnalysis, strip_service_fields
from core.draft_loader import load_draft_kegs
from core.revenue_metrics import RevenueMetricsCalculator
from extensions import BARS, cached_olap

analysis_bp = Blueprint('analysis', __name__)


@analysis_bp.route('/api/packaging', methods=['POST'])
def analyze_packaging():
    """ABC/XYZ анализ фасовки: вся страница /packaging одним ответом.

    Тело запроса: {bar, date_from, date_to} либо {bar, days}. Пустой bar — разрез
    «Общая»: все бары сведены в одну сеть. Даты ВКЛЮЧИТЕЛЬНЫЕ, к iiko уходит
    date_to + 1 день (правая граница DateRange эксклюзивная).

    Ответ — блок из core/packaging_analysis.py: сводка, ВСЕ категории, ВСЕ
    фасовки, корзины действий. Страница рисует из него все секции без
    дополнительных запросов — тот же приём, что у /api/draft-kegs.

    Заменил собой /api/analyze и /api/categories (удалены 2026-09-19). Старая пара
    считала одно и то же двумя разными способами и расходилась сама с собой:
    «Общая» в /api/analyze теряла позиции с незаполненным стилем (15,3% выручки),
    брала наценку сети как максимум по барам и считала XYZ по разбросу МЕЖДУ
    БАРАМИ вместо недель, а /api/categories сводного разреза не умел вовсе —
    отдавал четыре отдельных блока по барам. Разбор: docs/abc-xyz-analysis.md.
    """
    try:
        # silent=True: кривой JSON — ошибка клиента, а не наша. Без него Flask
        # бросает BadRequest, и запрос уходил в общий except как HTTP 500.
        data = request.get_json(silent=True) or {}
        bar_name = data.get('bar') or None
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        print(f"\n[PACKAGING] Zapusk analiza fasovki...")
        print(f"   Bar: {bar_name if bar_name else 'VSE (Obschaya)'}")

        if not date_from or not date_to:
            # days разбирается только здесь: при явно переданных датах это поле
            # не используется, и мусор в нём не должен ронять валидный запрос.
            try:
                days = int(data.get('days', 30))
            except (TypeError, ValueError):
                return jsonify({'error': 'Поле days должно быть числом'}), 400
            # Московский день, а не UTC: иначе на UTC-хосте после 21:00 «сегодня»
            # уезжает на сутки назад (тот же дефолт, что у /api/draft-kegs).
            today = datetime.now(ZoneInfo('Europe/Moscow')).date()
            date_to = today.strftime('%Y-%m-%d')
            date_from = (today - timedelta(days=days)).strftime('%Y-%m-%d')
            print(f"   Period: {days} dney (computed: {date_from} - {date_to})")
        else:
            print(f"   Period: {date_from} - {date_to}")

        try:
            olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d')
                            + timedelta(days=1)).strftime('%Y-%m-%d')
            if datetime.strptime(date_from, '%Y-%m-%d') > datetime.strptime(date_to, '%Y-%m-%d'):
                return jsonify({'error': 'Начало периода позже конца'}), 400
        except ValueError:
            return jsonify({'error': 'Даты должны быть в формате YYYY-MM-DD'}), 400

        # Кэш по бару и периоду: страница пересчитывает разрезы часто, а отчёт
        # iiko за тот же период не меняется. Ключ включает бар, потому что
        # сервер фильтрует выборку на стороне iiko.
        cache_key = f"packaging:{bar_name or 'ALL'}:{date_from}:{olap_date_to}"

        def fetch():
            olap = OlapReports()
            if not olap.connect():
                return None
            try:
                return olap.get_beer_sales_report(date_from, olap_date_to, bar_name)
            finally:
                olap.disconnect()

        report_data = cached_olap(cache_key, fetch)

        if not report_data:
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 502
        if not report_data.get('data'):
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

        analyzer = PackagingAnalysis(report_data['data'], date_from, date_to)
        block = analyzer.build(bar_name)

        if not block['positions']:
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

        totals = block['totals']
        print(f"   [OK] SKU: {totals['sku']}, kategoriy: {totals['categories']}, "
              f"vyruchka: {totals['revenue']:.2f}, "
              f"XYZ: {'da' if block['xyz_available'] else 'net (nuzhno 3 nedeli)'}")

        return jsonify(block)

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/packaging: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


# Эндпоинтов /api/analyze, /api/categories и /api/weekly-chart больше нет
# (удалены 2026-09-19). Первые два заменил /api/packaging — см. его докстроку.
# /api/weekly-chart не работал никогда: он читал файл beer_report.json из корня
# репозитория, который создаётся только ручным запуском core/olap_reports.py и в
# продакшене не появляется, поэтому клик по иконке графика всегда отдавал 404.
# График недельных продаж теперь не нужен отдельным запросом: недельный ряд уже
# посчитан внутри /api/packaging и показывается в карточке позиции.

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

        # OLAP to-дата EXCLUSIVE → добавляем 1 день для включения последнего дня
        # Это корректно работает даже на границе месяца/года
        date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
        olap_date_to_dt = date_to_dt + timedelta(days=1)
        olap_date_to = olap_date_to_dt.strftime('%Y-%m-%d')
        print(f"   OLAP Period: {date_from} - {olap_date_to} (to-date exclusive, +1 day added)")

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

@analysis_bp.route('/api/draft-kegs', methods=['POST'])
def analyze_draft_kegs():
    """Проливы по кегам: литры из проводок iiko, деньги из отчёта по продажам.

    Заменяет /api/draft-analyze как источник данных страницы /draft. Старый эндпоинт
    оставлен рабочим: он считает литры из названий блюд и нужен для сверки двух
    расчётов (tests/test_draft_kegs.py, docs/draft.md).

    Тело запроса: {bar, date_from, date_to} либо {bar, days}. Даты — ВКЛЮЧИТЕЛЬНО,
    к iiko уходит date_to + 1 день (правая граница DateRange эксклюзивная).
    """
    try:
        data = request.json or {}
        bar_name = data.get('bar') or None
        days = int(data.get('days', 30))
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        print(f"\n[DRAFT KEGS] Zapusk analiza prolivov po kegam...")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")

        if not date_from or not date_to:
            # Тот же дефолт, что у остальных страниц: московский день, иначе на
            # UTC-хосте после 21:00 «сегодня» уезжает на сутки назад.
            today = datetime.now(ZoneInfo('Europe/Moscow')).date()
            date_to = today.strftime('%Y-%m-%d')
            date_from = (today - timedelta(days=days)).strftime('%Y-%m-%d')
            print(f"   Period: {days} dney (computed: {date_from} - {date_to})")
        else:
            print(f"   Period: {date_from} - {date_to}")

        # Три запроса к iiko и ключ кэша живут в core/draft_loader.py (с 2026-09-04):
        # тот же загрузчик кормит вкладку «Литры» в карточках розлива дашборда, и при
        # совпадении бара и периода оба экрана читают одну запись кэша.
        raw = load_draft_kegs(bar_name, date_from, date_to)
        if not raw:
            return jsonify({'error': 'Не удалось получить данные из iiko API'}), 502

        analyzer = DraftKegAnalysis(
            transactions=raw['transactions'],
            sales=raw['sales'],
            dish_map=raw['dish_map'],
            date_from=date_from,
            date_to=date_to,
        )
        block = strip_service_fields(analyzer.build(bar_name))
        block['generated_at'] = raw.get('fetched_at')

        if not block['kegs'] and block['losses']['invoice_in'] == 0:
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

        print(f"   [OK] Kegov: {block['total_kegs']}, litrov: {block['total_liters']:.2f}, "
              f"barmenov: {block['total_bartenders']}, "
              f"XYZ: {'da' if block['xyz_available'] else 'net (nuzhno 3 nedeli)'}")
        notes = block['bartender_notes']
        if abs(notes.get('unassigned_liters', 0.0)) > 0.01:
            print(f"   [WARN] Litrov bez barmena: {notes['unassigned_liters']:.2f}")
        if notes.get('dishes_without_volume'):
            print(f"   [WARN] Blyud bez normy zakladki: {len(notes['dishes_without_volume'])} "
                  f"(pervoe: {notes['dishes_without_volume'][0]['DishName']})")
        if block['unmapped_dishes']:
            print(f"   [WARN] Blyud bez kega: {len(block['unmapped_dishes'])} "
                  f"(pervoe: {block['unmapped_dishes'][0]['DishName']})")

        return jsonify({bar_name or 'Общая': block})

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/draft-kegs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


# Эндпоинта /api/waiter-analyze больше нет: разрез по барменам считается в
# /api/draft-kegs из тех же данных, что и разрез по кегам (core/draft_kegs.py,
# collect_bartenders). Прежний расчёт брал объём порции регексом из названия блюда и
# молча выбрасывал позиции, где объёма в названии не нашлось. Сверка перед удалением
# (2026-08-13): по каждому бармену расхождение не больше 0,16% на 3,5 месяцах, при этом
# новая сумма по барменам совпадает с суммой по кегам до 0,000000 л. Страница /waiters
# отдаёт 301 на /draft#bartenders (routes/pages.py). Док: docs/draft.md.


# ============= API для анализа скидок =============

# Служебное имя ведра «все акции вместе» в ответе /api/discount-analyze.
# Нужно потому, что тип скидки — измерение ПОЗИЦИИ чека: один чек может лежать в
# множествах двух акций сразу, и сложить их количества на клиенте нельзя.
# В discount_names не попадает (список собирается из значений строк OLAP).
ALL_BUCKET = '__all__'


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
        # Структура: { discount_name: { card_number: { name, visits, visit_dates, sum_with_discount, discount_sum, dishes } } }
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
            visit_date = row.get('OpenDate.Typed', '')  # Дата визита для RFM-анализа
            sum_with_discount = float(row.get('DishDiscountSumInt', 0) or 0)
            discount_sum = float(row.get('DiscountSum', 0) or 0)

            # Каждая строка идёт в ДВА ведра: своей акции и сводное ALL_BUCKET.
            # Сводное нельзя собрать на клиенте сложением: тип скидки — измерение
            # ПОЗИЦИИ, поэтому один чек, где пиво по одной акции, а еда по другой,
            # лежит в множествах обеих акций. Сложение len(set) дало бы два чека
            # вместо одного — завышенный счётчик чеков и заниженный средний чек.
            for bucket in (discount_name, ALL_BUCKET):
                guests = discounts_data.setdefault(bucket, {})
                guest = guests.get(card_number)
                if guest is None:
                    guest = guests[card_number] = {
                        'card_number': card_number,
                        'customer_name': customer_name,
                        'orders': set(),
                        'visit_dates': set(),   # уникальные даты визитов
                        'sum_with_discount': 0,
                        'discount_sum': 0,
                        'dishes': [],
                        'stores': set()
                    }
                if order_num:
                    # Ключ чека — «дата + бар + номер», как во всём проекте
                    # (docs/guests.md). Раньше ключом был один OrderNum:
                    # одинаковый номер в разные дни склеивался в один чек, число
                    # чеков занижалось, а средний чек завышался (регресс
                    # зафиксирован в tests/test_logic_audit_regressions).
                    guest['orders'].add((visit_date, store_name, order_num))
                if visit_date:
                    guest['visit_dates'].add(visit_date)
                guest['sum_with_discount'] += sum_with_discount
                guest['discount_sum'] += discount_sum
                # Позиции — только в ведре конкретной акции. В сводном они не
                # нужны (клиент склеивает их сам, там дублей нет: у строки ровно
                # один тип скидки), а дублировать их значит удвоить размер ответа.
                if dish_name and bucket != ALL_BUCKET:
                    guest['dishes'].append({
                        'name': dish_name,
                        'sum_with_discount': sum_with_discount,
                        'discount_sum': discount_sum,
                        'store': store_name,
                        'order_num': order_num,
                        'date': visit_date
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

            # Оба ведра, по той же причине, что у гостей: множества чеков и карт
            # разных акций пересекаются, складывать их len() нельзя.
            for bucket in (discount_name, ALL_BUCKET):
                per_store = stores_summary.setdefault(bucket, {})
                s = per_store.get(store_name)
                if s is None:
                    s = per_store[store_name] = {
                        'orders': set(),
                        'cards': set(),
                        'sum_with_discount': 0,
                        'discount_sum': 0
                    }
                if order_num:
                    # Тот же ключ чека, что у гостя: дата + бар + номер. Бар здесь
                    # один (группировка по нему), но дата обязательна — без неё
                    # одинаковый номер чека в разные дни давал один чек.
                    s['orders'].add((row.get('OpenDate.Typed', ''), store_name, order_num))
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

        # Преобразуем гостей в сериализуемый формат с RFM-метриками
        from datetime import datetime as dt
        period_end = dt.strptime(date_to, '%Y-%m-%d')
        period_start = dt.strptime(date_from, '%Y-%m-%d')
        period_days = (period_end - period_start).days + 1

        result = {}
        for disc_name, guests in discounts_data.items():
            guest_list = []
            for card, g in guests.items():
                visit_dates = sorted(g['visit_dates']) if g['visit_dates'] else []
                total_visits = len(visit_dates)

                # RFM-метрики
                last_visit = visit_dates[-1] if visit_dates else None
                first_visit = visit_dates[0] if visit_dates else None

                # Recency: дней с последнего визита
                recency_days = None
                if last_visit:
                    last_visit_dt = dt.strptime(last_visit, '%Y-%m-%d')
                    recency_days = (period_end - last_visit_dt).days

                # Frequency: визитов в неделю
                frequency_per_week = None
                if total_visits > 0 and period_days > 0:
                    frequency_per_week = round(total_visits / period_days * 7, 2)

                # Активный период (дни между первым и последним визитом)
                active_days = None
                if first_visit and last_visit and first_visit != last_visit:
                    first_dt = dt.strptime(first_visit, '%Y-%m-%d')
                    last_dt = dt.strptime(last_visit, '%Y-%m-%d')
                    active_days = (last_dt - first_dt).days + 1

                # Средний чек = выручка / ЧЕКИ (единое определение проекта,
                # docs/guests.md и GUEST_FORMULAS.avg_check). Раньше делилось на
                # число визитов, из-за чего два чека за один вечер давали
                # завышенный «средний чек».
                orders_count = len(g['orders'])
                avg_check = (round(g['sum_with_discount'] / orders_count, 0)
                             if orders_count > 0 else 0)

                guest_list.append({
                    'card_number': g['card_number'],
                    'customer_name': g['customer_name'],
                    'visits': total_visits,
                    'orders': orders_count,
                    'visit_dates': visit_dates,  # Список дат для timeline
                    'last_visit': last_visit,
                    'first_visit': first_visit,
                    'recency_days': recency_days,
                    'frequency_per_week': frequency_per_week,
                    'active_days': active_days,
                    'avg_check': int(avg_check),
                    'sum_with_discount': round(g['sum_with_discount'], 2),
                    'discount_sum': round(g['discount_sum'], 2),
                    'stores': sorted(g['stores']),
                    'dishes': g['dishes']
                })

            # Сортировка по recency (сначала самые «свежие»). Нельзя писать
            # `x['recency_days'] or 999`: ноль тоже falsy, и гость, купивший в
            # последний день периода, уезжал В КОНЕЦ списка вместо начала.
            guest_list.sort(key=lambda x: (x['recency_days'] is None,
                                           x['recency_days']
                                           if x['recency_days'] is not None else 0))
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


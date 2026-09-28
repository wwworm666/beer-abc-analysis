from flask import Blueprint, request, jsonify
import time
import json
import os
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.dashboard_analysis import DashboardMetrics
from core.dashboard_details import (
    build_card_details, section_draft_liters, section_taps,
    METRIC_IDS, LAZY_SECTIONS, LAZY_ONLY_METRICS
)
from core.draft_loader import load_draft_kegs
from core.draft_kegs import DraftKegAnalysis, strip_service_fields
from core.daily_plans_generator import DailyPlansGenerator
from core.plans_manager import (
    PeriodCommentsStore, PeriodCommentsUnavailable, PERIOD_KEY_RE,
    validate_comment_period_key, validate_comment_text, validate_comment_venue,
)
from core.weeks_generator import WeeksGenerator
from core import monthly_report, msk_time
from core.auth_guard import current_user
from extensions import (
    venues_manager, plans_manager, notes_manager, taps_manager,
    comparison_calculator, trends_analyzer, export_manager,
    day_weight_overrides_manager,
    DASHBOARD_OLAP_CACHE, DASHBOARD_OLAP_CACHE_TTL, cached_olap
)

dashboard_bp = Blueprint('dashboard', __name__)

# venue_key дашборда -> id бара в TapsManager. Константа уровня модуля: нужна и
# карточке «Активность кранов», и секции «Краны» в деталях карточки. Та же
# таблица продублирована во фронте (analytics.js, ссылка «Открыть краны»).
VENUE_TO_BAR_MAPPING = {
    'bolshoy': 'bar1',
    'ligovskiy': 'bar2',
    'kremenchugskaya': 'bar3',
    'varshavskaya': 'bar4',
    'all': None  # все бары
}


def _taps_bar_names():
    """{bar_id: название бара для экрана} - краны в TapsManager зовутся «Бар 1»."""
    names = {}
    for venue_key, bar_id in VENUE_TO_BAR_MAPPING.items():
        venue = venues_manager.get_venue(venue_key) if bar_id else None
        if venue:
            names[bar_id] = venue.get('name') or bar_id
    return names


def load_dashboard_sales(venue_key, date_from, date_to):
    """
    Единый OLAP-запрос «Аналитики» из общего кэша (10 мин, single-flight).

    Один вход для всех, кто показывает цифры этого экрана: карточки
    (/api/dashboard-analytics), вкладка «Выручка» (/api/revenue-metrics) и
    разбивка карточки по сотрудникам (/api/employee-metrics-breakdown в
    routes/employee.py). Ключ кэша один, поэтому карточка и её разбивка
    считаются из одного и того же ответа iiko. До 2026-09-04 разбивка ходила
    в iiko отдельно и без кэша, и на открытом периоде обгоняла карточку.

    Args:
        venue_key: ключ заведения; '' и None равны 'all'
        date_from, date_to: 'YYYY-MM-DD', обе даты инклюзивно (как на экране);
                            сдвиг +1 день для iiko (exclusive end) делается здесь

    Returns:
        dict {'data': [...]} - пустой период даёт {'data': []} и кэшируется;
        None - сбой iiko, не кэшируется.
    """
    venue_key = venue_key or 'all'
    bar_name = venues_manager.get_iiko_name(venue_key) if venue_key != 'all' else None
    date_to_inclusive = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    cache_key = f"{venue_key}_{date_from}_{date_to_inclusive}"

    def _fetch_all_sales():
        olap = OlapReports()
        if not olap.connect():
            print("   [ERROR] Не удалось подключиться к iiko API")
            return None
        try:
            print(f"   [OLAP] Комплексный запрос: {bar_name or 'ВСЕ'}, {date_from} - {date_to_inclusive}")
            start_time = time.time()
            data = olap.get_all_sales_report(date_from, date_to_inclusive, bar_name)
            if data is None:
                # Сбой iiko: наверх идёт None, такой результат НЕ кэшируется.
                return None
            print(f"   [OK] Комплексный запрос выполнен за {time.time() - start_time:.2f}s")
            # Пустой период (закрытый день, будущая дата) — это ВАЛИДНЫЙ ответ:
            # возвращаем {'data': []}, чтобы он попал в кэш и метрики стали нулями.
            # Раньше пустой ответ приравнивался к ошибке -> 500 и повторный поход
            # в iiko на каждое нажатие стрелки. См. docs/lessons.md.
            return data if data.get('data') else {'data': []}
        finally:
            olap.disconnect()

    return cached_olap(cache_key, _fetch_all_sales)


# Ключи ответа «Аналитики»: snake_case расчёта (DashboardMetrics.calculate_metrics)
# -> camelCase экрана (static/js/dashboard/core/config.js: actualKey = planKey).
# Один словарь на всех: карточки (/api/dashboard-analytics), «Выручка»
# (/api/revenue-metrics), сравнение периодов и выгрузки Excel/PDF. До 2026-09-28
# у каждого маршрута была своя копия, и выгрузки брали сырые ключи — отсюда наценка
# «Факт» дробью (2.24) против плана в процентах (200) и нулевая активность кранов.
DASHBOARD_FRONTEND_KEYS = {
    'total_revenue': 'revenue',
    'total_checks': 'checks',
    'avg_check': 'averageCheck',
    'draft_share': 'draftShare',
    'bottles_share': 'packagedShare',
    'kitchen_share': 'kitchenShare',
    'draft_revenue': 'revenueDraft',
    'bottles_revenue': 'revenuePackaged',
    'kitchen_revenue': 'revenueKitchen',
    'avg_markup': 'markupPercent',
    'total_margin': 'profit',
    'draft_markup': 'markupDraft',
    'bottles_markup': 'markupPackaged',
    'tap_activity': 'tapActivity',
    'kitchen_markup': 'markupKitchen',
    'loyalty_points_written_off': 'loyaltyWriteoffs',
    # Лояльность: чеки с картой / без карты (группа «Лояльность» на дашборде)
    'card_checks': 'cardChecks',
    'nocard_checks': 'nocardChecks',
    'card_checks_share': 'cardChecksShare',
    'card_revenue': 'cardRevenue',
    'nocard_revenue': 'nocardRevenue'
}

# Наценка в расчёте — дробь (2.2448 = 224.48 %), в планах и на экране — проценты.
# Множитель 100 применяется ровно к этим ключам и ровно здесь.
MARKUP_FRONTEND_KEYS = ('markupPercent', 'markupDraft', 'markupPackaged', 'markupKitchen')


def map_dashboard_metrics(metrics):
    """Метрики расчёта -> ключи и единицы экрана (наценки ×100); лишние ключи отбрасываются."""
    mapped = {}
    for old_key, new_key in DASHBOARD_FRONTEND_KEYS.items():
        if old_key in metrics:
            value = metrics[old_key]
            if new_key in MARKUP_FRONTEND_KEYS:
                value = value * 100
            mapped[new_key] = value
    return mapped


class DashboardDataUnavailable(RuntimeError):
    """iiko не ответил: у маршрута это 500, как у /api/dashboard-analytics."""


def dashboard_page_metrics(venue_key, date_from, date_to):
    """Метрики «Аналитики» ровно как на экране: (сырые метрики, метрики экрана).

    Шаги те же, что у /api/dashboard-analytics: единый OLAP-запрос из общего кэша
    (load_dashboard_sales, 10 мин), DashboardMetrics.calculate_metrics, активность
    кранов за период по журналу кранов (TapsManager.calculate_tap_activity_for_period),
    map_dashboard_metrics. Пустой период даёт нули, а не ошибку.

    Args:
        venue_key: ключ заведения; '' и None равны 'all'
        date_from, date_to: 'YYYY-MM-DD', обе даты включительно

    Raises:
        DashboardDataUnavailable: сбой iiko (не кэшируется).
    """
    venue_key = venue_key or 'all'
    all_sales_data = load_dashboard_sales(venue_key, date_from, date_to)
    if all_sales_data is None:
        raise DashboardDataUnavailable('Не удалось получить данные из OLAP')
    metrics = DashboardMetrics().calculate_metrics(all_sales_data)
    metrics['tap_activity'] = taps_manager.calculate_tap_activity_for_period(
        VENUE_TO_BAR_MAPPING.get(venue_key), date_from, date_to)
    return metrics, map_dashboard_metrics(metrics)


def _parse_iso_date(value):
    """'YYYY-MM-DD' -> date или None (кривой ввод маршрут превращает в 400)."""
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


@dashboard_bp.route('/api/dashboard-analytics', methods=['POST'])
def dashboard_analytics():
    """API endpoint для получения всех метрик дашборда из сырых OLAP данных"""
    try:
        data = request.json
        venue_key = data.get('bar')  # ключ заведения (kremenchugskaya, bolshoy, etc)
        date_from = data.get('date_from')  # YYYY-MM-DD
        date_to = data.get('date_to')      # YYYY-MM-DD

        if not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры date_from и date_to'}), 400

        print(f"\n[DASHBOARD] Запуск анализа дашборда...")
        print(f"   Venue key: {venue_key}")
        print(f"   Period (requested): {date_from} - {date_to}")

        # 1. ВСЕ данные ОДНИМ запросом из общего кэша (single-flight внутри воркера).
        # Тот же загрузчик кормит вкладку «Выручка» и разбивку карточек по сотрудникам.
        all_sales_data = load_dashboard_sales(venue_key, date_from, date_to)

        if all_sales_data is None:
            return jsonify({'error': 'Не удалось получить данные из OLAP'}), 500

        # 2. Создаем калькулятор метрик и рассчитываем из СЫРЫХ данных
        print("   [2/5] Расчет метрик из сырых OLAP данных...")
        calculator = DashboardMetrics()

        # Считаем метрики из единого отчета
        metrics = calculator.calculate_metrics(all_sales_data)
        table_data = calculator.get_table_data(metrics)

        print(f"   [OK] Метрики рассчитаны успешно!")

        # 3. Добавляем метрику активности кранов за период
        print("   [3/5] Расчет активности кранов...")

        # Преобразуем venue_key в bar_id для TapsManager (константа уровня модуля)
        bar_id_for_taps = VENUE_TO_BAR_MAPPING.get(venue_key)
        print(f"   [DEBUG] venue_key={venue_key} -> bar_id_for_taps={bar_id_for_taps}")

        tap_activity = taps_manager.calculate_tap_activity_for_period(bar_id_for_taps, date_from, date_to)
        metrics['tap_activity'] = tap_activity
        print(f"   [OK] Активность кранов: {tap_activity}%")

        # Ключи и единицы экрана (camelCase, наценка ×100) — общий словарь
        # DASHBOARD_FRONTEND_KEYS: те же числа берут сравнение периодов и выгрузки.
        mapped_metrics = map_dashboard_metrics(metrics)

        # Формируем ответ с преобразованными ключами
        response = {
            **mapped_metrics,
            'table_data': table_data
        }

        return jsonify(response)

    except Exception as e:
        print(f"[ERROR] Ошибка в /api/dashboard-analytics: {e}")
        import traceback
        traceback.print_exc()
        error_detail = f"{type(e).__name__}: {str(e)}"
        return jsonify({'error': error_detail}), 500


@dashboard_bp.route('/api/dashboard-card-details', methods=['POST'])
def dashboard_card_details():
    """
    Детали одной карточки дашборда: секции-вкладки раскрытой карточки (2026-09-04).

    Тело: {venue_key, date_from, date_to, metric, section?}. Даты включительно,
    как у /api/employee-metrics-breakdown; venue_key '' и None = 'all'.

    Без section - все секции метрики из строк единого OLAP-запроса, взятого из
    того же кэша, что и карточка (load_dashboard_sales, TTL 10 мин): новых
    обращений к iiko нет, итог каждой секции равен карточке по построению
    (core/dashboard_details.py). Ленивые секции приходят заглушкой lazy=true.

    С section='draft_liters' - топ кегов по литрам из тех же данных, что
    страница /draft (core/draft_loader.py, общий ключ кэша draft_kegs_*);
    с section='taps' - краны с простоем из data/taps_data.json.

    Коды: 400 без дат / при неизвестной метрике или секции; 500 при сбое iiko
    (как у соседей, не кэшируется); 502 если не удалось загрузить данные /draft.
    Пустой период - 200 с пустыми rows.
    """
    try:
        data = request.get_json(silent=True) or {}
        venue_key = data.get('venue_key') or 'all'
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        metric = data.get('metric')
        section_id = data.get('section')

        if not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры: date_from, date_to'}), 400
        if metric not in METRIC_IDS:
            return jsonify({'error': f'Неизвестная метрика: {metric}'}), 400
        period = {'from': date_from, 'to': date_to}

        if section_id:
            if section_id not in LAZY_SECTIONS:
                return jsonify({'error': f'Неизвестная секция: {section_id}'}), 400
            print(f"\n[CARD DETAILS] Lenivaya sekciya {section_id}: {venue_key}, {date_from} - {date_to}")
            if section_id == 'draft_liters':
                bar_name = venues_manager.get_iiko_name(venue_key) if venue_key != 'all' else None
                raw = load_draft_kegs(bar_name, date_from, date_to)
                if not raw:
                    return jsonify({'error': 'Не удалось получить данные проливов из iiko'}), 502
                analyzer = DraftKegAnalysis(
                    transactions=raw['transactions'], sales=raw['sales'],
                    dish_map=raw['dish_map'], date_from=date_from, date_to=date_to,
                )
                block = strip_service_fields(analyzer.build(bar_name))
                block['generated_at'] = raw.get('fetched_at')
                section = section_draft_liters(block)
            else:
                bar_id = VENUE_TO_BAR_MAPPING.get(venue_key)
                detail = taps_manager.tap_activity_by_tap(bar_id, date_from, date_to)
                section = section_taps(detail, bar_names=_taps_bar_names(),
                                       link_href=f'/taps/{bar_id}' if bar_id else '/taps')
            return jsonify({'metric': metric, 'venue': venue_key, 'period': period, 'section': section})

        print(f"\n[CARD DETAILS] Detali kartochki {metric}: {venue_key}, {date_from} - {date_to}")
        if metric in LAZY_ONLY_METRICS:
            # У кранов все секции ленивые: заглушкам строки не нужны, в iiko не ходим -
            # иначе недоступный iiko прятал бы локальные данные кранов.
            all_sales_data = {'data': []}
        else:
            all_sales_data = load_dashboard_sales(venue_key, date_from, date_to)
            if all_sales_data is None:
                return jsonify({'error': 'Не удалось получить данные из OLAP'}), 500

        # План по дням нужен только выручке; файл читается один раз на запрос.
        daily_plans = DailyPlansGenerator().load_daily_plans() if metric == 'revenue' else None
        sections = build_card_details(metric, all_sales_data, venue_key, date_from, date_to, daily_plans)
        errors = sum(1 for s in sections if s.get('error'))
        print(f"[OK] Detali {metric}: {len(sections)} sekciy" + (f", oshibok: {errors}" if errors else ''))
        return jsonify({'metric': metric, 'venue': venue_key, 'period': period, 'sections': sections})

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/dashboard-card-details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


# ============================================================================
# MONTHLY REPORT API - Месячный отчёт (вкладка дашборда, помесячная динамика)
# ============================================================================

# «Текущие» год и месяц месячного отчёта (значения по умолчанию и год пересчёта
# force/full) — по Москве (core/msk_time): прод-контейнер живёт в UTC, и с 00:00 до
# 03:00 МСК наивный datetime.now() давал прошлые сутки — в ночь на 1-е число
# «текущим» был прошлый месяц, в новогоднюю ночь — прошлый год (с 2026-09-28).

def _parse_years_arg(years_arg):
    """'2026,2025' -> [2026, 2025] (уник., убыв., максимум 3). Пусто -> текущий год (МСК)."""
    if years_arg:
        years = [int(y) for y in years_arg.split(',') if y.strip().isdigit()]
    else:
        years = [msk_time.today().year]
    if not years:
        years = [msk_time.today().year]
    return sorted(set(years), reverse=True)[:3]


def _maybe_refresh(block, venue):
    """Ручной пересчёт через query-параметры (UI-кнопки «Обновить» больше нет —
    данные обновляются автоматически ночным шедулером при закрытии месяца):
    - force=1 — досчитать недостающие закрытые месяцы текущего года;
    - full=1  — глубокий пересчёт всего текущего года (для ретро-правок в iiko).
    Прошлые годы заморожены и не трогаются. Возвращает True если был пересчёт."""
    force = request.args.get('force', '') in ('1', 'true', 'yes')
    full = request.args.get('full', '') in ('1', 'true', 'yes')
    if not (force or full):
        return False
    monthly_report.refresh_block(block, venue, msk_time.today().year, force=full)
    return True


@dashboard_bp.route('/api/monthly-report', methods=['GET'])
def monthly_report_core():
    """Core-блок месячного отчёта: выручка/наценка/доли/маржа/чеки/баллы/локал-импорт
    помесячно за указанные годы (years=2026,2025 для наложения год-к-году).
    Читается из витрины (диск). force=1 — пересчитать текущий месяц."""
    try:
        venue = request.args.get('venue', 'all') or 'all'
        years = _parse_years_arg(request.args.get('years', ''))
        _maybe_refresh('core', venue)
        return jsonify(monthly_report.get_core(venue, years))
    except Exception as e:
        print(f"[ERROR] /api/monthly-report: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


@dashboard_bp.route('/api/monthly-report/loyalty', methods=['GET'])
def monthly_report_loyalty():
    """Лояльность помесячно за год: новые гости + выручка по картам/без карт."""
    try:
        venue = request.args.get('venue', 'all') or 'all'
        year = int(request.args.get('year', msk_time.today().year))
        _maybe_refresh('loyalty', venue)
        return jsonify(monthly_report.get_loyalty(venue, year))
    except Exception as e:
        print(f"[ERROR] /api/monthly-report/loyalty: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


@dashboard_bp.route('/api/monthly-report/draft-liters', methods=['GET'])
def monthly_report_draft_liters():
    """Проливы розлива в литрах по стилям, помесячно за год."""
    try:
        venue = request.args.get('venue', 'all') or 'all'
        year = int(request.args.get('year', msk_time.today().year))
        _maybe_refresh('liters', venue)
        return jsonify(monthly_report.get_draft_liters(venue, year))
    except Exception as e:
        print(f"[ERROR] /api/monthly-report/draft-liters: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


@dashboard_bp.route('/api/monthly-report/top-guests', methods=['GET'])
def monthly_report_top_guests():
    """ТОП гостей по тратам за конкретный месяц (свой селектор месяца)."""
    try:
        venue = request.args.get('venue', 'all') or 'all'
        today = msk_time.today()
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))
        _maybe_refresh('topguests', venue)
        return jsonify(monthly_report.get_top_guests(venue, year, month))
    except Exception as e:
        print(f"[ERROR] /api/monthly-report/top-guests: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


# ============================================================================
# DASHBOARD PLANS API - Управление плановыми показателями
# ============================================================================

@dashboard_bp.route('/api/venues')
def get_venues():
    """Получить список всех заведений для селектора"""
    try:
        print("\n[VENUES API] Запрос списка заведений...")
        venues = venues_manager.get_all_for_dropdown()
        print(f"[VENUES API] Возвращаю {len(venues)} заведений")
        return jsonify({'venues': venues})
    except Exception as e:
        print(f"[VENUES API ERROR] Ошибка при получении списка заведений: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/weeks')
def get_weeks():
    """Получить список всех недель для текущего года (год и текущая неделя — по Москве)"""
    try:
        print("\n[WEEKS API] Генерация недель для текущего года...")
        current_year = msk_time.today().year
        weeks = WeeksGenerator.generate_weeks_for_year(current_year)
        current_week = WeeksGenerator.get_current_week()
        print(f"[WEEKS API] Сгенерировано недель: {len(weeks)}")
        print(f"[WEEKS API] Текущая неделя: {current_week['label']}")
        return jsonify({
            'weeks': weeks,
            'current_week': current_week
        })
    except Exception as e:
        print(f"[WEEKS API ERROR] Ошибка при генерации недель: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/plans/<venue_key>/<period_key>')
def get_plan_with_venue(venue_key, period_key):
    """Получить план за конкретное заведение и период.

    «Общее» (all/total/пусто) за месячный ключ YYYY-MM возвращается как агрегат —
    сумма баров (calculate_plan_for_period за полный месяц), а не отдельная запись all_*.
    """
    try:
        print(f"\n[PLANS API] Запрос плана для заведения: {venue_key}, период: {period_key}")

        is_month = len(period_key) == 7 and period_key[4] == '-'
        if venue_key in ('all', 'total', '') and is_month:
            y, m = int(period_key[:4]), int(period_key[5:7])
            mstart = f"{period_key}-01"
            mnext = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
            mend = (mnext - timedelta(days=1)).strftime('%Y-%m-%d')
            plan = plans_manager.calculate_plan_for_period('', mstart, mend)
            if plan:
                print(f"[PLANS API] Агрегат «Общее» рассчитан: выручка={plan.get('revenue', 0):.0f}")
                return jsonify(plan)
            return jsonify({'error': 'Plan not found'}), 404

        composite_key = f"{venue_key}_{period_key}"
        print(f"[PLANS API] Составной ключ: {composite_key}")
        plan = plans_manager.get_plan(composite_key)
        if plan:
            print(f"[PLANS API] План найден")
            return jsonify(plan)
        else:
            print(f"[PLANS API] План НЕ найден")
            return jsonify({'error': 'Plan not found'}), 404
    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка при получении плана: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/plans/calculate/<venue_key>/<start_date>/<end_date>')
def calculate_plan_for_period(venue_key, start_date, end_date):
    """Рассчитать план для произвольного периода на основе месячных планов"""
    try:
        print(f"\n[PLANS API] Расчёт плана для {venue_key}, период: {start_date} - {end_date}")
        venue = '' if venue_key in ('', 'total', 'общая', 'all') else venue_key
        plan = plans_manager.calculate_plan_for_period(venue, start_date, end_date)
        if plan:
            print(f"[PLANS API] План рассчитан: выручка={plan.get('revenue', 0):.0f}")
            return jsonify(plan)
        else:
            print(f"[PLANS API] Не удалось рассчитать план")
            return jsonify({'error': 'No monthly plans found for this period'}), 404
    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка при расчёте плана: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/plans', methods=['GET'])
def get_all_plans():
    """Получить все планы (для функции копирования)"""
    try:
        print("\n[PLANS API] Запрос всех планов...")
        all_plans = plans_manager.get_all_plans()
        periods = plans_manager.get_periods_with_plans()
        print(f"[PLANS API] Загружено планов: {len(all_plans)}")
        return jsonify({
            'plans': all_plans,
            'periods': periods
        })
    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка при получении планов: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/plans/<venue_key>/<period_key>', methods=['POST'])
def save_plan_with_venue(venue_key, period_key):
    """Сохранить или обновить план для конкретного заведения и периода"""
    try:
        request_data = request.json

        if not request_data:
            return jsonify({'error': 'No data provided'}), 400

        print(f"\n[PLANS API] Сохранение плана для заведения: {venue_key}, период: {period_key}")
        print(f"[PLANS API] Данные: {list(request_data.keys())}")

        composite_key = f"{venue_key}_{period_key}"
        print(f"[PLANS API] Составной ключ: {composite_key}")

        success = plans_manager.save_plan_with_regeneration(composite_key, request_data)

        if success:
            print(f"[PLANS API] План успешно сохранен")
            return jsonify({
                'success': True,
                'message': 'Plan saved successfully',
                'period': period_key,
                'venue': venue_key
            })
        else:
            return jsonify({'error': 'Failed to save plan'}), 500

    except ValueError as e:
        print(f"[PLANS API VALIDATION ERROR] {e}")
        return jsonify({'error': f'Validation error: {str(e)}'}), 400

    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка при сохранении плана: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/plans/<venue_key>/<period_key>', methods=['DELETE'])
def delete_plan_with_venue(venue_key, period_key):
    """Удалить план за конкретное заведение и период"""
    try:
        print(f"\n[PLANS API] Удаление плана для заведения: {venue_key}, период: {period_key}")
        composite_key = f"{venue_key}_{period_key}"
        print(f"[PLANS API] Составной ключ: {composite_key}")
        success = plans_manager.delete_plan(composite_key)
        if success:
            print(f"[PLANS API] План удален")
            # Подчистить override весов и обнулить «призрачные» дневные значения
            # удалённой точки в daily_plans.json, затем пересобрать агрегат 'all'.
            try:
                if len(period_key) == 7:
                    y, m = int(period_key[:4]), int(period_key[5:7])
                    removed = day_weight_overrides_manager.delete_venue_month(venue_key, y, m)
                    from core.daily_plans_generator import (
                        regenerate_daily_plan_for_venue_month,
                        regenerate_all_aggregate_for_month,
                    )
                    # После удаления revenue плана нет -> compute_daily_plan вернёт 0.0
                    # для всех дней точки (чистит призраков); внутри пересчитывается агрегат.
                    regenerate_daily_plan_for_venue_month(venue_key, y, m)
                    regenerate_all_aggregate_for_month(y, m)
                    if removed:
                        print(f"[PLANS API] Удалено override весов: {removed}")
            except Exception as cleanup_err:
                print(f"[PLANS API WARN] Не удалось подчистить daily/override: {cleanup_err}")
            return jsonify({
                'success': True,
                'message': 'Plan deleted successfully'
            })
        else:
            return jsonify({'error': 'Plan not found'}), 404
    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка при удалении плана: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


REAL_VENUES = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']


def _daily_breakdown_payload(venue_key: str, year: int, month: int) -> dict:
    """Собрать подневную разбивку плана для страницы «Планы по дням».

    Для конкретной точки — month_breakdown с её override.
    Для 'all'/'total'/'' — сумма дневных планов реальных точек (агрегат, без правки).
    """
    from core.day_weights import month_breakdown, month_weight as compute_month_weight

    is_aggregate = venue_key in ('all', 'total', 'общая', '')

    if not is_aggregate:
        mp = plans_manager.get_monthly_plan(venue_key, year, month)
        monthly_revenue = float(mp.get('revenue', 0.0)) if mp else 0.0
        overrides = day_weight_overrides_manager.get_for_venue_month(venue_key, year, month)
        days = month_breakdown(year, month, monthly_revenue, overrides)
        mw = compute_month_weight(year, month, overrides)
        daily_sum = round(sum(d['daily_plan'] for d in days), 2)
        tolerance = 1.0
        return {
            'venue': venue_key,
            'year': year,
            'month': month,
            'editable': True,
            'monthly_revenue': round(monthly_revenue, 2),
            'month_weight': mw,
            'days': days,
            'daily_sum': daily_sum,
            'tolerance': tolerance,
            'sum_check': abs(daily_sum - monthly_revenue) <= tolerance,
        }

    # Агрегат 'all' = сумма дневных планов реальных точек (каждая со своими override)
    per_venue_days = {}
    monthly_revenue = 0.0
    venues_with_plan = 0
    for v in REAL_VENUES:
        mp = plans_manager.get_monthly_plan(v, year, month)
        rev = float(mp.get('revenue', 0.0)) if mp else 0.0
        if rev > 0:
            venues_with_plan += 1
        monthly_revenue += rev
        ov = day_weight_overrides_manager.get_for_venue_month(v, year, month)
        per_venue_days[v] = month_breakdown(year, month, rev, ov)

    template = per_venue_days[REAL_VENUES[0]]
    days = []
    for idx, ref in enumerate(template):
        daily = round(sum(per_venue_days[v][idx]['daily_plan'] for v in REAL_VENUES), 2)
        any_override = any(per_venue_days[v][idx]['is_override'] for v in REAL_VENUES)
        days.append({
            'date': ref['date'],
            'weekday': ref['weekday'],
            'weekday_name': ref['weekday_name'],
            'weight': None,  # для агрегата вес отдельного дня не определён
            'is_override': any_override,
            'daily_plan': daily,
        })
    daily_sum = round(sum(d['daily_plan'] for d in days), 2)
    tolerance = max(1.0, venues_with_plan * 1.0)
    return {
        'venue': 'all',
        'year': year,
        'month': month,
        'editable': False,
        'monthly_revenue': round(monthly_revenue, 2),
        'month_weight': None,
        'days': days,
        'daily_sum': daily_sum,
        'tolerance': tolerance,
        'sum_check': abs(daily_sum - monthly_revenue) <= tolerance,
    }


@dashboard_bp.route('/api/plans/daily/<venue_key>/<int:year>/<int:month>')
def get_daily_breakdown(venue_key, year, month):
    """Подневная разбивка месячного плана для страницы «Планы по дням»."""
    try:
        payload = _daily_breakdown_payload(venue_key, year, month)
        return jsonify(payload)
    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка подневной разбивки: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/plans/daily/<venue_key>/<int:year>/<int:month>', methods=['POST'])
def set_day_weight(venue_key, year, month):
    """Задать override веса дня (праздник = N, закрытый день = 0)."""
    try:
        data = request.json or {}
        date_str = data.get('date')
        weight = data.get('weight')
        if not date_str or weight is None:
            return jsonify({'error': 'Требуются поля date и weight'}), 400

        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        if d.year != year or d.month != month:
            return jsonify({'error': 'Дата не принадлежит указанному месяцу'}), 400

        day_weight_overrides_manager.set_override(venue_key, date_str, float(weight))
        return jsonify(_daily_breakdown_payload(venue_key, year, month))

    except ValueError as e:
        return jsonify({'error': f'Validation error: {str(e)}'}), 400
    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка установки веса дня: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/plans/daily/<venue_key>/<int:year>/<int:month>/<date_str>', methods=['DELETE'])
def reset_day_weight(venue_key, year, month, date_str):
    """Сбросить override веса дня к значению по умолчанию. Идемпотентно."""
    try:
        day_weight_overrides_manager.delete_override(venue_key, date_str)
        return jsonify(_daily_breakdown_payload(venue_key, year, month))
    except ValueError as e:
        return jsonify({'error': f'Validation error: {str(e)}'}), 400
    except Exception as e:
        print(f"[PLANS API ERROR] Ошибка сброса веса дня: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/storage/diagnose')
def storage_diagnose():
    """
    Диагностика хранилища планов: куда реально пишет приложение и работает ли persistence.

    Используется для подтверждения, что Render Disk примонтирован и приложение его видит.
    Не требует авторизации (информационный endpoint без чувствительных данных).
    """
    from core.storage_paths import (
        RENDER_DISK_DIR, LOCAL_DATA_DIR, get_data_path, is_persistent_storage_active
    )

    persistent = is_persistent_storage_active()
    plans_path = get_data_path('plansdashboard.json', seed_from_local=False)
    daily_path = get_data_path('daily_plans.json', seed_from_local=False)

    def _file_info(path):
        if not os.path.exists(path):
            return {'exists': False}
        try:
            stat = os.stat(path)
            info = {
                'exists': True,
                'path': path,
                'size_bytes': stat.st_size,
                'mtime': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'writable': os.access(path, os.W_OK),
            }
            if path.endswith('.json'):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'plans' in data:
                        info['keys_count'] = len(data['plans'])
                        info['sample_keys'] = sorted(data['plans'].keys())[:5]
                    elif isinstance(data, dict):
                        info['keys_count'] = len(data)
                except Exception as e:
                    info['parse_error'] = str(e)
            return info
        except Exception as e:
            return {'exists': True, 'path': path, 'stat_error': str(e)}

    return jsonify({
        'persistent_storage_active': persistent,
        'render_disk_dir': RENDER_DISK_DIR,
        'render_disk_exists': os.path.exists(RENDER_DISK_DIR),
        'local_data_dir': LOCAL_DATA_DIR,
        'plansdashboard': _file_info(plans_path),
        'daily_plans': _file_info(daily_path),
        'env_persistent_data_dir': os.environ.get('PERSISTENT_DATA_DIR'),
        'pid': os.getpid(),
        'cwd': os.getcwd(),
    })


@dashboard_bp.route('/api/plans/export', methods=['GET'])
def plans_export():
    """
    Экспорт всех планов одним flat-листом xlsx.

    Возвращает xlsx со строками `<period> × <venue>` и 16 метриками в столбцах.
    Источник данных — plansdashboard.json (через plans_manager.get_all_plans()).
    Сортировка: Period ASC, Venue ASC.
    """
    try:
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        all_plans = plans_manager.get_all_plans()
        if not all_plans:
            return jsonify({'error': 'Нет планов для экспорта'}), 404

        venue_names = {
            'bolshoy': 'Большой пр. В.О',
            'ligovskiy': 'Лиговский',
            'kremenchugskaya': 'Кременчугская',
            'varshavskaya': 'Варшавская',
            'all': 'Все заведения',
        }

        metric_keys = list(plans_manager.PLAN_SCHEMA.keys())
        metric_labels = {
            'revenue': 'Выручка (₽)',
            'checks': 'Чеки (шт)',
            'averageCheck': 'Средний чек (₽)',
            'draftShare': 'Доля розлива (%)',
            'packagedShare': 'Доля фасовки (%)',
            'kitchenShare': 'Доля кухни (%)',
            'revenueDraft': 'Выручка розлив (₽)',
            'revenuePackaged': 'Выручка фасовка (₽)',
            'revenueKitchen': 'Выручка кухня (₽)',
            'markupPercent': 'Наценка (%)',
            'profit': 'Прибыль (₽)',
            'markupDraft': 'Наценка розлив (%)',
            'markupPackaged': 'Наценка фасовка (%)',
            'markupKitchen': 'Наценка кухня (%)',
            'loyaltyWriteoffs': 'Списания баллов (₽)',
            'tapActivity': 'Активность кранов (%)',
            # План доли чеков с картой (2026-09-05): у старых месяцев подставлен дефолт
            # PLAN_DEFAULTS через get_all_plans, поэтому колонка всегда заполнена.
            'cardChecksShare': 'Доля чеков с картой (%)',
        }

        rows = []
        for key, plan in all_plans.items():
            # Ключ формата venue_YYYY-MM
            parts = key.rsplit('_', 1)
            if len(parts) != 2 or len(parts[1]) != 7:
                continue
            venue_key, period = parts
            rows.append((period, venue_key, plan))

        rows.sort(key=lambda r: (r[0], r[1]))

        wb = Workbook()
        ws = wb.active
        ws.title = 'All Plans'

        headers = ['Период', 'Заведение'] + [metric_labels.get(k, k) for k in metric_keys]
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color='CCE5FF', end_color='CCE5FF', fill_type='solid')
            cell.alignment = Alignment(horizontal='center')
        ws.freeze_panes = 'A2'

        for period, venue_key, plan in rows:
            row_values = [period, venue_names.get(venue_key, venue_key)]
            for metric_key in metric_keys:
                value = plan.get(metric_key)
                row_values.append(round(value, 2) if isinstance(value, (int, float)) else '')
            ws.append(row_values)

        col_widths = [12, 22] + [20] * len(metric_keys)
        for idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = width

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"plans_export_{msk_time.today().strftime('%Y-%m-%d')}.xlsx"
        print(f"[PLANS EXPORT] Сгенерирован xlsx: {len(rows)} строк, файл {filename}")

        return output.getvalue(), 200, {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': f'attachment; filename={filename}'
        }

    except Exception as e:
        print(f"[PLANS EXPORT ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# Хранилище комментариев к периодам создаётся при первом обращении (а не при импорте
# модуля): так импорт blueprint'а в тестах и в стенде не трогает файлы данных, а
# тесты подменяют _comments_store своим экземпляром во временной папке.
_comments_store = None


def _period_comments():
    """Хранилище комментариев; старые комментарии переносятся из файла планов."""
    global _comments_store
    if _comments_store is None:
        _comments_store = PeriodCommentsStore(legacy_plans_file=plans_manager.data_file)
    return _comments_store


def _comment_author():
    """Кто сохранил: логин; через MCP — «<логин> · агент» (как в контент-плане)."""
    try:
        user = current_user()
    except Exception:  # вне сессии (голый Flask в тестах) — автор неизвестен
        user = None
    if not user:
        return None
    name = user.get('login') or user.get('display_name')
    if user.get('via_mcp'):
        name = (name or 'владелец') + ' · агент'
    return name


@dashboard_bp.route('/api/comments/<venue_key>/<period_key>', methods=['GET'])
def get_comment(venue_key, period_key):
    """Комментарий («анализ») к периоду дашборда для заведения.

    Ответ 200: {comment: текст или null, venue_key, period_key, updated_at,
    updated_by, legacy}. legacy=true — старый общий комментарий (сохранён до
    2026-09-28, когда заведение не учитывалось): виден у любого заведения, пока у
    заведения нет своего. 400 — неизвестное заведение или пустой/длинный ключ
    периода; 503 — файл комментариев повреждён. Правила хранения —
    core/plans_manager.PeriodCommentsStore.
    """
    try:
        validate_comment_venue(venue_key)
        validate_comment_period_key(period_key, for_write=False)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    try:
        found = _period_comments().get(venue_key, period_key)
    except PeriodCommentsUnavailable as e:
        print(f"[COMMENTS API ERROR] {e}")
        return jsonify({'error': str(e)}), 503
    if found is None:
        return jsonify({'comment': None, 'venue_key': venue_key, 'period_key': period_key,
                        'updated_at': None, 'updated_by': None, 'legacy': False})
    return jsonify(found)


@dashboard_bp.route('/api/comments/<venue_key>/<period_key>', methods=['POST'])
def save_comment(venue_key, period_key):
    """Сохранить комментарий к периоду дашборда для заведения.

    Тело: {"comment": "текст"} — строка до 10 000 знаков, пробелы по краям
    обрезаются; пустая строка очищает комментарий заведения. Ключ периода — только
    'YYYY-MM-DD_YYYY-MM-DD' (формат дашборда), заведение — 'all' или ключ бара.
    Комментарий хранится отдельно от планов (period_comments.json) и полей плана
    не проверяет — до 2026-09-28 он писался в файл планов, и любое сохранение
    отвечало 500 «Missing required field: revenue».

    Ответ 200: {success: true, message, comment, venue_key, period_key, updated_at,
    updated_by, legacy: false}; 400 — неверный ключ, заведение или текст;
    503 — файл комментариев повреждён (не перезаписывается).
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Тело запроса — JSON-объект {"comment": "текст"}'}), 400
    try:
        validate_comment_venue(venue_key)
        validate_comment_period_key(period_key, for_write=True)
        text = validate_comment_text(data.get('comment', ''))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    try:
        saved = _period_comments().save(venue_key, period_key, text, author=_comment_author())
    except PeriodCommentsUnavailable as e:
        print(f"[COMMENTS API ERROR] {e}")
        return jsonify({'error': str(e)}), 503
    print(f"[COMMENTS API] Комментарий сохранён: {venue_key} / {period_key}, {len(text)} знаков")
    return jsonify(dict(saved, success=True,
                        message='Comment saved successfully' if text else 'Comment cleared'))


# ========== COMPARISON, TRENDS & EXPORT APIs ==========

def _period_from_key(period_key):
    """'YYYY-MM-DD_YYYY-MM-DD' -> ('YYYY-MM-DD', 'YYYY-MM-DD') или None.

    Даты обязаны существовать, начало — не позже конца.
    """
    match = PERIOD_KEY_RE.match(period_key) if isinstance(period_key, str) else None
    if not match:
        return None
    start, end = _parse_iso_date(match.group(1)), _parse_iso_date(match.group(2))
    if start is None or end is None or start > end:
        return None
    return start.isoformat(), end.isoformat()


@dashboard_bp.route('/api/comparison/periods', methods=['POST'])
def compare_periods():
    """Сравнение двух периодов по всем метрикам «Аналитики» (с 2026-09-28 — честный расчёт).

    Тело: {venue_key: 'all' | ключ бара (пусто = 'all'), period1_key, period2_key},
    ключи периодов — 'YYYY-MM-DD_YYYY-MM-DD' (как key у /api/weeks).

    Числа каждого периода — ровно карточки «Аналитики» за эти даты
    (get_dashboard_analytics_data: общий кэш OLAP, наценка в процентах, активность
    кранов). Сравнение — core/comparison_calculator.py, соглашение вкладки
    «Сравнение»: период 2 — база («было»), Δ = период 1 − период 2,
    Δ% = Δ / период 2 × 100 (база 0 — null), у метрик в процентах Δ в п.п.

    Страница сюда не ходит: вкладка «Сравнение» считает то же самое в браузере из
    двух запросов /api/dashboard-analytics. Маршрут нужен ИИ-агентам (MCP
    analytics_compare_periods) — один вызов вместо двух и арифметики в модели.
    До 2026-09-28 здесь была заглушка с пустым сравнением.

    Ответ 200: {success, venue_key, base: 'period2', period1: {key, date_from,
    date_to, metrics}, period2: {...}, comparison: {метрика: {label, unit, period1,
    period2, diff, diff_unit, diff_percent, trend, budget, better}}, top_changes,
    insights, formula}. 400 — неверный бар или ключ периода; 500 — сбой iiko.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Тело запроса — JSON-объект {venue_key, period1_key, '
                                 'period2_key}'}), 400
    venue_key = data.get('venue_key') or 'all'
    if venue_key not in VENUE_TO_BAR_MAPPING:
        return jsonify({'error': 'Неизвестное заведение: ' + str(venue_key)[:40] + '. Ключи: '
                                 + ', '.join(VENUE_TO_BAR_MAPPING)}), 400
    periods = {}
    for field in ('period1_key', 'period2_key'):
        bounds = _period_from_key(data.get(field))
        if bounds is None:
            return jsonify({'error': field + ' — ключ периода YYYY-MM-DD_YYYY-MM-DD '
                                             '(начало не позже конца), получено: '
                                             + str(data.get(field))[:40]}), 400
        periods[field] = bounds
    try:
        result = {'success': True, 'venue_key': venue_key, 'base': 'period2'}
        metrics = {}
        for field, name in (('period1_key', 'period1'), ('period2_key', 'period2')):
            date_from, date_to = periods[field]
            metrics[name] = get_dashboard_analytics_data(venue_key, date_from, date_to)
            result[name] = {'key': data[field], 'date_from': date_from, 'date_to': date_to,
                            'metrics': metrics[name]}
        result.update(comparison_calculator.summary(metrics['period1'], metrics['period2']))
        return jsonify(result)
    except DashboardDataUnavailable as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(f"[ERROR] /api/comparison/periods: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {str(e)}"}), 500


def get_dashboard_analytics_data(bar, date_from, date_to):
    """Метрики «Аналитики» за период ровно как на экране — для выгрузок и сравнения.

    Ключи и единицы — как в ответе /api/dashboard-analytics без table_data:
    camelCase, наценки в процентах (224.48, а не 2.2448), tapActivity по журналу
    кранов; данные из того же кэша OLAP (load_dashboard_sales), поэтому выгрузка
    совпадает с экраном за те же даты. Пустой период — нули (как на экране).

    До 2026-09-28 функция ходила в iiko отдельно и без кэша, возвращала сырые
    ключи расчёта (наценка дробью) без активности кранов и падала на пустом периоде.

    Args:
        bar: ключ заведения; '' и None равны 'all'
        date_from, date_to: 'YYYY-MM-DD', обе даты включительно

    Raises:
        DashboardDataUnavailable: сбой iiko.
    """
    _raw, page_metrics = dashboard_page_metrics(bar, date_from, date_to)
    return page_metrics


@dashboard_bp.route('/api/revenue-metrics', methods=['POST'])
def revenue_metrics():
    """
    API для вкладки 'Выручка' — 4 ключевые метрики + таблица по барам
    Использует тот же OLAP запрос что и дашборд
    """
    try:
        data = request.json
        venue_key = data.get('bar')
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры date_from и date_to'}), 400

        print(f"\n[REVENUE-METRICS] Zapros metrik...")
        print(f"   Bar: {venue_key if venue_key else 'OBSSHAYA'}")
        print(f"   Period: {date_from} - {date_to}")

        # Те же данные, что у dashboard_analytics (вся выручка, не только напитки),
        # из общего кэша: вкладки делят один ответ iiko, а не ходят за ним по разу.
        all_sales_data = load_dashboard_sales(venue_key, date_from, date_to)

        if all_sales_data is None:
            return jsonify({'error': 'Не удалось получить данные из OLAP'}), 500

        # Считаем метрики из сырых OLAP данных; ключи экрана — общий словарь
        # DASHBOARD_FRONTEND_KEYS (как у dashboard_analytics).
        calculator = DashboardMetrics()
        metrics = calculator.calculate_metrics(all_sales_data)
        mapped = map_dashboard_metrics(metrics)

        # 'revenue' = вся выручка после маппинга
        actual_revenue = mapped.get('revenue', 0)

        # ---- Границы ПОЛНОГО периода, к которому относятся план и прогноз ----
        # date_from/date_to — это диапазон, за который есть ФАКТ (для текущего месяца
        # он обрезан по сегодня). period_from/period_to — весь выбранный период целиком.
        # Разделение нужно, чтобы «Ожидаемая» экстраполировалась до конца периода,
        # а «% выполнения» считался от плана за весь период.
        #
        # Старые открытые вкладки period_from/period_to не присылают — тогда полным
        # периодом считается календарный месяц date_from, как было до 2026-08-11.
        # На месячном периоде обе ветки дают одинаковые числа.
        _pdt = datetime.strptime(date_from, '%Y-%m-%d')
        period_from = data.get('period_from')
        period_to = data.get('period_to')

        if not period_from or not period_to:
            _mnext = datetime(_pdt.year + 1, 1, 1) if _pdt.month == 12 else datetime(_pdt.year, _pdt.month + 1, 1)
            period_from = _pdt.replace(day=1).strftime('%Y-%m-%d')
            period_to = (_mnext - timedelta(days=1)).strftime('%Y-%m-%d')

        period_start = datetime.strptime(period_from, '%Y-%m-%d')
        period_end = datetime.strptime(period_to, '%Y-%m-%d')

        # План за ВЕСЬ период. «Общее» (all/пусто) = сумма баров; для конкретного бара
        # calculate_plan_for_period делит месячные планы пропорционально взвешенным
        # дням (пт/сб = 2.0, core/day_weights.py). На полном месяце это ровно месячный
        # план — прежнее поведение get_monthly_plan сохраняется.
        _venue_for_plan = '' if (not venue_key or venue_key in ('all', 'total')) else venue_key
        period_plan = plans_manager.calculate_plan_for_period(_venue_for_plan, period_from, period_to) or {}
        plan_revenue = period_plan.get('revenue', 0.0)

        # ---- Метрики ----
        start = datetime.strptime(date_from, '%Y-%m-%d')
        end = datetime.strptime(date_to, '%Y-%m-%d')
        total_days = (end - start).days + 1          # дней с фактом (для средней)
        period_days = (period_end - period_start).days + 1  # дней во всём периоде

        # Средняя в день = факт / дни с фактом
        average_daily = actual_revenue / total_days if total_days > 0 else 0

        # Ожидаемая = факт + линейная экстраполяция средней на остаток периода.
        # Период закончился (или данных на весь период уже есть) -> ожидаемая = факт.
        # «Сегодня» — по Москве (core/msk_time): прод-контейнер живёт в UTC, и с 00:00
        # до 03:00 МСК наивный datetime.now() давал вчерашнюю дату — в первую ночь
        # после конца периода он ещё считался идущим, и «Ожидаемая» экстраполировалась.
        today_dt = datetime.combine(msk_time.today(), datetime.min.time())
        period_finished = today_dt > period_end or total_days >= period_days

        if not period_finished and total_days > 0:
            expected = average_daily * period_days
        else:
            expected = actual_revenue

        # % выполнения = факт / план за весь период
        completion = (actual_revenue / plan_revenue * 100) if plan_revenue > 0 else 0

        result = {
            'current': round(actual_revenue, 2),
            'plan': round(plan_revenue, 2),
            'expected': round(expected, 2),
            'average': round(average_daily, 2),
            'period_days': total_days,
            # days_in_month — историческое имя поля: число дней во ВСЁМ выбранном
            # периоде (на месячной гранулярности это по-прежнему дни месяца).
            'days_in_month': period_days,
            'completion_percent': round(completion, 1)
        }

        print(f"   [OK] Metriki rasschitany: current={result['current']}, plan={result['plan']}")
        return jsonify(result)

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/revenue-metrics: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# Кэш для widget API (5 минут)
WIDGET_CACHE = {}
WIDGET_CACHE_TTL = 300  # 5 минут


@dashboard_bp.route('/api/widget/revenue', methods=['GET'])
def widget_revenue():
    """
    API для PWA виджета — 5 баров с процентами выполнения
    ОПТИМИЗАЦИЯ: ОДИН OLAP запрос на все бары вместо пяти
    """
    try:
        # Проверяем кэш
        now = time.time()
        cache_key = 'widget_revenue'

        if cache_key in WIDGET_CACHE:
            cached_entry = WIDGET_CACHE[cache_key]
            if (now - cached_entry['timestamp']) < WIDGET_CACHE_TTL:
                print(f"[WIDGET] Using cached data")
                return jsonify(cached_entry['data'])

        print(f"\n[WIDGET] Generatsiya dannykh dlya vidzheta (ODIN OLAP zapros)...")

        # Период: с 1-го числа по сегодня. «Сегодня» — по Москве (core/msk_time):
        # прод-контейнер живёт в UTC, и с 00:00 до 03:00 МСК наивный datetime.now()
        # давал вчера — а в ночь на 1-е число показывал процент ПРОШЛОГО месяца.
        today = msk_time.today()
        month_start = today.replace(day=1)
        date_from = month_start.strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
        date_to_inclusive = (today + timedelta(days=1)).strftime('%Y-%m-%d')

        print(f"   Period: {date_from} - {date_to}")

        # ОДИН OLAP запрос на ВСЕ бары сразу (без фильтра по Store.Name)
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        print(f"   [1/3] Zapros OLAP na VSE barы...")
        all_sales_data = olap.get_all_sales_report(date_from, date_to_inclusive, None)  # None = все бары
        olap.disconnect()

        if not all_sales_data or not all_sales_data.get('data'):
            print(f"   [WARN] Net dannykh iz OLAP")
            return jsonify([
                {'bar': '', 'name': 'Общая', 'completion': 0.0},
                {'bar': 'bolshoy', 'name': 'Большой пр. В.О', 'completion': 0.0},
                {'bar': 'ligovskiy', 'name': 'Лиговский', 'completion': 0.0},
                {'bar': 'kremenchugskaya', 'name': 'Кременчугская', 'completion': 0.0},
                {'bar': 'varshavskaya', 'name': 'Варшавская', 'completion': 0.0}
            ])

        # Группируем данные по барам (Store.Name)
        print(f"   [2/3] Gruppировка dannykh po barам...")
        from collections import defaultdict
        bar_data = defaultdict(list)

        for record in all_sales_data.get('data', []):
            store_name = record.get('Store.Name', '')
            if store_name:
                bar_data[store_name].append(record)

        # Маппинг названий баров из iiko в ключи
        iiko_to_key = {
            'Большой пр. В.О': 'bolshoy',
            'Лиговский': 'ligovskiy',
            'Кременчугская': 'kremenchugskaya',
            'Варшавская': 'varshavskaya'
        }

        # Читаем планы один раз
        print(f"   [3/3] Rasschёт metrik...")
        plans_file = plans_manager.data_file
        try:
            with open(plans_file, 'r', encoding='utf-8') as f:
                plans_data = json.load(f)
            plans = plans_data.get('plans', {})
        except:
            plans = {}

        results = []
        total_revenue = 0.0
        total_plan = 0.0

        # Порядок баров
        bars_order = [
            ('', 'Общая'),
            ('bolshoy', 'Большой пр. В.О'),
            ('ligovskiy', 'Лиговский'),
            ('kremenchugskaya', 'Кременчугская'),
            ('varshavskaya', 'Варшавская')
        ]

        for bar_key, bar_name_iiko in bars_order:
            if bar_key == '':
                # Общая = сумма по всем барам
                actual_revenue = 0.0
                plan_revenue = 0.0

                for iiko_name, records in bar_data.items():
                    calculator = DashboardMetrics()
                    metrics = calculator.calculate_metrics({'data': records})

                    frontend_mapping = {
                        'total_revenue': 'revenue',
                        'avg_check': 'averageCheck',
                        'total_margin': 'profit',
                    }
                    mapped = {}
                    for old_key, new_key in frontend_mapping.items():
                        if old_key in metrics:
                            value = metrics[old_key]
                            if new_key in ['averageCheck']:
                                value = value * 100
                            mapped[new_key] = value

                    bar_revenue = mapped.get('revenue', 0)
                    actual_revenue += bar_revenue

                    # План по этому бару
                    bar_key_tmp = iiko_to_key.get(iiko_name, '')
                    month_key = f"{bar_key_tmp if bar_key_tmp else 'all'}_{month_start.strftime('%Y-%m')}"
                    month_plan = plans.get(month_key, {})
                    plan_revenue += month_plan.get('revenue', 0.0)

                total_revenue = actual_revenue
                total_plan = plan_revenue
                completion = (actual_revenue / plan_revenue * 100) if plan_revenue > 0 else 0

            else:
                # Конкретный бар
                iiko_name = bar_name_iiko
                records = bar_data.get(iiko_name, [])

                if records:
                    calculator = DashboardMetrics()
                    metrics = calculator.calculate_metrics({'data': records})

                    frontend_mapping = {
                        'total_revenue': 'revenue',
                        'avg_check': 'averageCheck',
                        'total_margin': 'profit',
                    }
                    mapped = {}
                    for old_key, new_key in frontend_mapping.items():
                        if old_key in metrics:
                            value = metrics[old_key]
                            if new_key in ['averageCheck']:
                                value = value * 100
                            mapped[new_key] = value

                    actual_revenue = mapped.get('revenue', 0)
                else:
                    actual_revenue = 0.0

                # План
                month_key = f"{bar_key}_{month_start.strftime('%Y-%m')}"
                month_plan = plans.get(month_key, {})
                plan_revenue = month_plan.get('revenue', 0.0)

                completion = (actual_revenue / plan_revenue * 100) if plan_revenue > 0 else 0

            results.append({
                'bar': bar_key,
                'name': bar_name_iiko,
                'completion': round(completion, 1)
            })
            print(f"   {bar_name_iiko}: {completion:.1f}% (выручка={actual_revenue:.0f}, план={plan_revenue:.0f})")

        # Кэшируем результат
        WIDGET_CACHE[cache_key] = {
            'data': results,
            'timestamp': now
        }

        print(f"   [OK] Widget data generated (1 OLAP zamiesto 5)")
        return jsonify(results)

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/widget/revenue: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/export/text', methods=['POST'])
def export_text():
    """API для экспорта в текстовый формат"""
    try:
        data = request.json
        venue_name = data.get('venue_name', 'Unknown')
        period = data.get('period', {})
        comparison = data.get('comparison', {})
        insights = data.get('insights', [])

        text_report = export_manager.prepare_text_report(
            venue_name,
            period,
            comparison,
            insights
        )

        return jsonify({
            'success': True,
            'text': text_report
        })

    except Exception as e:
        print(f"[ERROR] /api/export/text: {e}")
        return jsonify({'error': str(e)}), 500


def _export_request():
    """Тело выгрузки дашборда: (bar, date_from, date_to, None) или (None, None, None, ответ 400).

    bar — 'all' или ключ бара ('' и отсутствие = 'all'); даты 'YYYY-MM-DD'
    включительно, начало не позже конца. До 2026-09-28 кривые даты давали 500.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, None, None, (jsonify({'error': 'Тело запроса — JSON-объект '
                                                    '{bar, date_from, date_to}'}), 400)
    bar = data.get('bar') or 'all'
    if bar not in VENUE_TO_BAR_MAPPING:
        return None, None, None, (jsonify({'error': 'Неизвестное заведение: ' + str(bar)[:40]
                                                    + '. Ключи: ' + ', '.join(VENUE_TO_BAR_MAPPING)}),
                                  400)
    start, end = _parse_iso_date(data.get('date_from')), _parse_iso_date(data.get('date_to'))
    if start is None or end is None or start > end:
        return None, None, None, (jsonify({'error': 'Нужны date_from и date_to в формате '
                                                    'YYYY-MM-DD, начало не позже конца'}), 400)
    return bar, start.isoformat(), end.isoformat(), None


def _export_venue_name(bar):
    """Название заведения для заголовка выгрузки (как в селекторе дашборда)."""
    venue = venues_manager.get_venue(bar)
    return (venue or {}).get('full_name') or (venue or {}).get('name') or bar


def _fmt_export(value, unit=''):
    """Число для PDF/HTML: 2 знака и разделитель тысяч; None — «—»."""
    if value is None:
        return '—'
    text = f"{value:,.2f}"
    return text + (' ' + unit if unit else '')


# Цвета светофора HTML-выгрузки — как на экране: выполнено / почти / не выполнено /
# плана нет (нейтральный серый вместо красного 0 %).
_EXPORT_STATUS_COLORS = {'ok': '#4CAF50', 'warn': '#FFC107', 'bad': '#F44336', 'none': '#9E9E9E'}


@dashboard_bp.route('/api/export/excel', methods=['POST'])
def export_excel():
    """Выгрузка дашборда в Excel (xlsx): «Метрика | План | Факт» за период.

    Тело: {bar: 'all' | ключ бара, date_from, date_to} — даты включительно, как у
    карточек. Факт — get_dashboard_analytics_data: ровно карточки «Аналитики» за
    эти даты (тот же кэш OLAP, наценки и доли в процентах, активность кранов по
    журналу кранов). План — plans_manager.calculate_plan_for_period за те же даты
    (его же экран берёт через /api/plans/calculate). Строки и правила —
    core/export_manager.ExportManager.dashboard_rows; метрика без плана — пустая
    ячейка «План» (на экране «План не задан»). Пустой период — нули, как на экране.

    До 2026-09-28 факт брался отдельным запросом без кэша и в сырых единицах:
    наценка дробью (2.24) против плана в процентах (200), активность кранов 0,
    пустой период — 500. CSV-фолбэк без openpyxl убран: openpyxl — обязательная
    зависимость (requirements.txt), а фолбэк писал текст в байтовый буфер и падал.

    Коды: 400 — неверный бар или даты; 500 — сбой iiko.
    """
    bar, date_from, date_to, error = _export_request()
    if error:
        return error
    try:
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill

        print(f"\n[EXPORT EXCEL] Генерация Excel: {bar} / {date_from} - {date_to}")
        fact = get_dashboard_analytics_data(bar, date_from, date_to)
        plan = plans_manager.calculate_plan_for_period(bar, date_from, date_to) or {}
        rows = export_manager.dashboard_rows(plan, fact)
        venue_name = _export_venue_name(bar)

        wb = Workbook()
        ws = wb.active
        ws.title = "Дашборд"

        ws.merge_cells('A1:C1')
        ws['A1'] = f"{venue_name} | {date_from} - {date_to}"
        ws['A1'].font = Font(size=14, bold=True)
        ws['A1'].alignment = Alignment(horizontal='center')
        ws['A2'] = ('Факт — как карточки «Аналитики» за эти даты; план — доля месячных '
                    'планов по взвешенным дням. Доли, наценки и активность кранов — в '
                    'процентах; пустой план — план не задан.')

        for col, header in enumerate(['Метрика', 'План', 'Факт'], 1):
            cell = ws.cell(row=4, column=col, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")

        for offset, row in enumerate(rows):
            line = 5 + offset
            ws.cell(row=line, column=1, value=f"{row['label']} ({row['unit']})")
            ws.cell(row=line, column=2,
                    value=round(row['plan'], 2) if row['plan'] is not None else None)
            ws.cell(row=line, column=3, value=round(row['fact'], 2))

        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 18

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        print(f"[EXPORT EXCEL] Excel файл сгенерирован: {len(rows)} строк")
        return output.getvalue(), 200, {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': f'attachment; filename=dashboard_{bar}_{date_from}_{date_to}.xlsx'
        }

    except DashboardDataUnavailable as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(f"[ERROR] /api/export/excel: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/export/pdf', methods=['POST'])
def export_pdf():
    """Выгрузка дашборда в PDF: «Метрика | План | Факт | % плана | Разница».

    Тело, факт, план и строки — как у export_excel (одна функция
    ExportManager.dashboard_rows); % плана = факт / план × 100, разница = факт −
    план, у метрики без плана — «—». Светофор HTML-варианта — как на экране: у
    бюджетных метрик (списания баллов) план — потолок, статус от зеркального
    процента (core.plans_manager.plan_score).

    reportlab в requirements.txt нет, поэтому на проде отдаётся HTML-страница
    (Content-Type text/html, файл .html) — её печатают в PDF из браузера; ветка
    reportlab работает, только если библиотеку поставить.

    Коды: 400 — неверный бар или даты; 500 — сбой iiko.
    """
    bar, date_from, date_to, error = _export_request()
    if error:
        return error
    try:
        from io import BytesIO
        from html import escape

        print(f"\n[EXPORT PDF] Генерация PDF: {bar} / {date_from} - {date_to}")
        fact = get_dashboard_analytics_data(bar, date_from, date_to)
        plan = plans_manager.calculate_plan_for_period(bar, date_from, date_to) or {}
        rows = export_manager.dashboard_rows(plan, fact)
        venue_name = _export_venue_name(bar)

        # Пробуем использовать reportlab если установлен
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

            output = BytesIO()
            doc = SimpleDocTemplate(output, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = [
                Paragraph(f"<b>Дашборд - {escape(venue_name)}</b>", styles['Title']),
                Spacer(1, 12),
                Paragraph(f"Период: {date_from} - {date_to}", styles['Normal']),
                Spacer(1, 20),
            ]

            data_table = [['Метрика', 'План', 'Факт', '% плана', 'Разница']]
            for row in rows:
                data_table.append([
                    f"{row['label']} ({row['unit']})",
                    _fmt_export(row['plan']),
                    _fmt_export(row['fact']),
                    f"{row['percent']:.1f}%" if row['percent'] is not None else '—',
                    _fmt_export(row['diff']),
                ])

            table = Table(data_table)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            doc.build(elements)
            output.seek(0)

            print(f"[EXPORT PDF] PDF файл сгенерирован (reportlab)")
            return output.getvalue(), 200, {
                'Content-Type': 'application/pdf',
                'Content-Disposition': f'attachment; filename=dashboard_{bar}_{date_from}_{date_to}.pdf'
            }

        except ImportError:
            # reportlab нет (так на проде) — HTML-страница с теми же строками
            print("[EXPORT PDF] reportlab не установлен, используем HTML")

        cards = []
        for row in rows:
            color = _EXPORT_STATUS_COLORS[row['status']]
            has_plan = row['plan'] is not None
            # Бюджетная метрика: план — потолок («Бюджет», «Использовано»).
            plan_label = 'Бюджет' if row['budget'] else 'План'
            progress_label = 'Использовано' if row['budget'] else 'Выполнение'
            plan_text = _fmt_export(row['plan'], row['unit']) if has_plan else 'не задан'
            percent = row['percent'] if row['percent'] is not None else 0
            percent_text = f"{percent:.1f}%" if has_plan else '—'

            cards.append(f"""
                <div class="metric-card">
                    <div class="metric-name">{escape(row['label'])}</div>
                    <div class="metric-values">
                        <div class="value-row">
                            <span class="label">{plan_label}:</span>
                            <span class="value">{plan_text}</span>
                        </div>
                        <div class="value-row">
                            <span class="label">Факт:</span>
                            <span class="value" style="color: {color}; font-weight: bold;">{_fmt_export(row['fact'], row['unit'])}</span>
                        </div>
                        <div class="value-row progress-row">
                            <span class="label">{progress_label}:</span>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: {min(max(percent, 0), 100)}%; background: {color};"></div>
                                <span class="progress-text">{percent_text}</span>
                            </div>
                        </div>
                    </div>
                </div>
                """)

        html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Дашборд - {escape(venue_name)}</title>
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        padding: 30px;
                        min-height: 100vh;
                    }}
                    .container {{
                        max-width: 1200px;
                        margin: 0 auto;
                        background: white;
                        border-radius: 20px;
                        padding: 40px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    }}
                    .header {{
                        text-align: center;
                        margin-bottom: 40px;
                        padding-bottom: 20px;
                        border-bottom: 3px solid #667eea;
                    }}
                    h1 {{
                        color: #333;
                        font-size: 32px;
                        margin-bottom: 10px;
                    }}
                    .period {{
                        color: #666;
                        font-size: 16px;
                    }}
                    .note {{
                        color: #666;
                        font-size: 13px;
                        margin-top: 8px;
                    }}
                    .metrics-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                        gap: 20px;
                    }}
                    .metric-card {{
                        background: #f8f9fa;
                        border-radius: 12px;
                        padding: 20px;
                        transition: transform 0.2s, box-shadow 0.2s;
                    }}
                    .metric-card:hover {{
                        transform: translateY(-5px);
                        box-shadow: 0 8px 16px rgba(0,0,0,0.1);
                    }}
                    .metric-name {{
                        font-size: 18px;
                        font-weight: 600;
                        color: #333;
                        margin-bottom: 15px;
                    }}
                    .metric-values {{
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                    }}
                    .value-row {{
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        padding: 8px 0;
                    }}
                    .label {{
                        color: #666;
                        font-size: 14px;
                    }}
                    .value {{
                        font-size: 16px;
                        color: #333;
                    }}
                    .progress-row {{
                        flex-direction: column;
                        align-items: stretch;
                        gap: 5px;
                        margin-top: 5px;
                    }}
                    .progress-bar {{
                        width: 100%;
                        height: 24px;
                        background: #e0e0e0;
                        border-radius: 12px;
                        position: relative;
                        overflow: hidden;
                    }}
                    .progress-fill {{
                        height: 100%;
                        border-radius: 12px;
                        transition: width 0.3s ease;
                    }}
                    .progress-text {{
                        position: absolute;
                        top: 50%;
                        left: 50%;
                        transform: translate(-50%, -50%);
                        font-size: 12px;
                        font-weight: 600;
                        color: #333;
                    }}
                    @media print {{
                        body {{ background: white; padding: 0; }}
                        .container {{ box-shadow: none; }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{escape(venue_name)}</h1>
                        <div class="period">{date_from} - {date_to}</div>
                        <div class="note">Факт — как карточки «Аналитики» за эти даты; план — доля месячных планов по взвешенным дням; доли, наценки и активность кранов — в процентах.</div>
                    </div>
                    <div class="metrics-grid">
                        {''.join(cards)}
                    </div>
                </div>
            </body>
            </html>
            """

        print(f"[EXPORT PDF] HTML файл сгенерирован (fallback)")
        return html_content.encode('utf-8'), 200, {
            'Content-Type': 'text/html; charset=utf-8',
            'Content-Disposition': f'attachment; filename=dashboard_{bar}_{date_from}_{date_to}.html'
        }

    except DashboardDataUnavailable as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(f"[ERROR] /api/export/pdf: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

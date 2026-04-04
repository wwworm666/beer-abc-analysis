from flask import Blueprint, request, jsonify
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.olap_reports import OlapReports
from core.iiko_api import IikoAPI
from core.employee_analysis import EmployeeMetricsCalculator, get_employees_from_waiter_data
from core.employee_plans import get_employee_plan_by_shifts
from core.daily_plans_generator import get_daily_plan_for_date, regenerate_daily_plans
from core.kpi_calculator import KpiCalculator, KpiTargetsReader, clear_kpi_cache, AVAILABLE_METRICS
from extensions import EMPLOYEES_CACHE, EMPLOYEES_CACHE_TTL

employee_bp = Blueprint('employee', __name__)


@employee_bp.route('/api/employees', methods=['GET'])
def get_employees_list():
    """Получить список всех сотрудников для dropdown"""
    try:
        # Используем данные о продажах за последние 30 дней чтобы получить актуальный список сотрудников
        date_to_obj = datetime.now()
        date_from = (date_to_obj - timedelta(days=30)).strftime("%Y-%m-%d")
        date_to = (date_to_obj + timedelta(days=1)).strftime("%Y-%m-%d")  # OLAP exclusive

        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            # Получаем данные разливного с официантами (там точно есть WaiterName)
            report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to, None)
        finally:
            olap.disconnect()

        if not report_data:
            return jsonify({'employees': []})

        # Извлекаем уникальные имена сотрудников
        employees = get_employees_from_waiter_data(report_data)

        return jsonify({'employees': employees})

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/employees: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/employee-analytics', methods=['POST'])
def employee_analytics():
    """API endpoint для детальной аналитики по одному сотруднику"""
    try:
        data = request.json
        employee_name = data.get('employee_name')
        bar_name = data.get('bar')  # None для всех баров
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if not employee_name or not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры: employee_name, date_from, date_to'}), 400

        print(f"\n[EMPLOYEE] Analiz sotrudnika: {employee_name}")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")
        print(f"   Period: {date_from} - {date_to}")

        # OLAP трактует to-дату как exclusive → добавляем +1 день чтобы включить весь последний день
        # (бар работает до 2-4 ночи, чеки после полуночи попадают на следующий календарный день)
        olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        # 1. Получаем данные через OLAP (ПАРАЛЛЕЛЬНО для скорости)
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            # Запускаем все OLAP запросы параллельно
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {
                    executor.submit(olap.get_employee_aggregated_metrics, date_from, olap_date_to, bar_name): 'aggregated',
                    executor.submit(olap.get_draft_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'draft',
                    executor.submit(olap.get_bottles_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'bottles',
                    executor.submit(olap.get_kitchen_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'kitchen',
                    executor.submit(olap.get_cancelled_orders_by_waiter, date_from, olap_date_to, bar_name): 'cancelled',
                    executor.submit(olap.get_new_loyalty_cards_by_waiter, date_from, olap_date_to, bar_name): 'loyalty_cards',
                }

                results = {}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        results[key] = future.result()
                    except Exception as e:
                        print(f"   [ERROR] OLAP {key}: {e}")
                        results[key] = None

            aggregated_data = results.get('aggregated')
            draft_data = results.get('draft')
            bottles_data = results.get('bottles')
            kitchen_data = results.get('kitchen')
            cancelled_data = results.get('cancelled')
            loyalty_cards_data = results.get('loyalty_cards', {})
        finally:
            olap.disconnect()

        # 2. Данные из кассовых смен (сотрудник, локация, выручка, часы - всё из одного API)
        shifts_count = 0
        shift_locations = {}
        shifts_revenue = 0.0
        total_hours = 0.0
        late_count = 0
        try:
            # Проверяем кэш сотрудников
            now = time.time()
            if EMPLOYEES_CACHE['data'] and (now - EMPLOYEES_CACHE['timestamp']) < EMPLOYEES_CACHE_TTL:
                employees_list = EMPLOYEES_CACHE['data']
                print(f"   [CACHE] Using cached employees list ({len(employees_list)} employees)")
            else:
                # Загружаем свежий список
                iiko_emp = IikoAPI()
                if iiko_emp.authenticate():
                    try:
                        employees_list = iiko_emp.get_employees()
                        EMPLOYEES_CACHE['data'] = employees_list
                        EMPLOYEES_CACHE['timestamp'] = now
                        print(f"   [CACHE] Loaded fresh employees list ({len(employees_list)} employees)")
                    finally:
                        iiko_emp.logout()
                else:
                    employees_list = []

            # Ищем ID сотрудника (с нормализацией имени)
            def normalize_name(name):
                if not name:
                    return set()
                return set(name.lower().strip().split())

            employee_id = None
            employee_name_normalized = normalize_name(employee_name)
            for emp in employees_list:
                iiko_name = emp.get('name')
                if not iiko_name:
                    continue
                # Сначала точное совпадение
                if iiko_name == employee_name:
                    employee_id = emp.get('id')
                    break
                iiko_normalized = normalize_name(iiko_name)
                # Потом нормализованное (те же слова в любом порядке)
                if iiko_normalized == employee_name_normalized:
                    employee_id = emp.get('id')
                    print(f"   [MATCH] '{employee_name}' -> '{iiko_name}' (exact set)")
                    break
                # OLAP даёт "Имя Отчество", iiko — "Фамилия Имя Отчество"
                if employee_name_normalized and employee_name_normalized.issubset(iiko_normalized) and len(employee_name_normalized) >= 2:
                    employee_id = emp.get('id')
                    print(f"   [MATCH] '{employee_name}' -> '{iiko_name}' (subset)")
                    break

            # Получаем метрики из кассовых смен (unified метод)
            if employee_id:
                print(f"   Found employee_id: {employee_id}")
                iiko = IikoAPI()
                if iiko.authenticate():
                    try:
                        all_metrics = iiko.get_employee_metrics_from_shifts(date_from, date_to)
                        emp_metrics = all_metrics.get(employee_id, {})
                        shifts_count = emp_metrics.get('shifts_count', 0)
                        shift_locations = emp_metrics.get('shift_locations', {})
                        shifts_revenue = emp_metrics.get('total_revenue', 0.0)
                        total_hours = emp_metrics.get('total_hours', 0.0)
                        late_count = emp_metrics.get('late_count', 0)
                        print(f"   Loaded {shifts_count} cash shifts, {total_hours:.1f} hours, revenue: {shifts_revenue:.0f}, late: {late_count}")
                    finally:
                        iiko.logout()
            else:
                print(f"   [WARN] Employee ID not found for: {employee_name}")
        except Exception as shift_error:
            print(f"   [WARN] Error getting cash shifts: {shift_error}")

        # 3. Рассчитываем план на основе кассовых смен
        plan_revenue = get_employee_plan_by_shifts(shift_locations)
        print(f"   Plan calculated from {len(shift_locations)} cash shifts: {plan_revenue:.0f}")

        # 4. Рассчитываем все метрики (используем OLAP для консистентности с dashboard)
        # Кассовые смены используем только для смен/часов/опозданий/локаций/плана
        calculator = EmployeeMetricsCalculator()
        metrics = calculator.calculate(
            employee_name=employee_name,
            aggregated_data=aggregated_data,
            draft_data=draft_data,
            bottles_data=bottles_data,
            kitchen_data=kitchen_data,
            cancelled_data=cancelled_data,
            plan_revenue=plan_revenue,
            date_from=date_from,
            date_to=date_to,
            shifts_count_override=shifts_count,
            total_hours_override=total_hours,
            late_count_override=late_count,
            loyalty_cards_count=loyalty_cards_data.get(employee_name, 0),
            total_revenue_override=None  # Используем OLAP выручку для консистентности
        )

        return jsonify(metrics)

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/employee-analytics: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/employee-compare', methods=['POST'])
def employee_compare():
    """API endpoint для сравнения нескольких сотрудников"""
    try:
        data = request.json
        employee_names = data.get('employee_names', [])
        bar_name = data.get('bar')
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if not employee_names or not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры: employee_names, date_from, date_to'}), 400

        if len(employee_names) < 2:
            return jsonify({'error': 'Выберите минимум 2 сотрудников для сравнения'}), 400

        print(f"\n[COMPARE] Sravnenie sotrudnikov: {len(employee_names)} chelovek")
        print(f"   Bar: {bar_name if bar_name else 'VSE'}")
        print(f"   Period: {date_from} - {date_to}")

        # OLAP трактует to-дату как exclusive → +1 день
        olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        # Загружаем данные ОДИН раз для всех (оптимизация)
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {
                    executor.submit(olap.get_employee_aggregated_metrics, date_from, olap_date_to, bar_name): 'aggregated',
                    executor.submit(olap.get_draft_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'draft',
                    executor.submit(olap.get_bottles_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'bottles',
                    executor.submit(olap.get_kitchen_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'kitchen',
                    executor.submit(olap.get_cancelled_orders_by_waiter, date_from, olap_date_to, bar_name): 'cancelled',
                    executor.submit(olap.get_new_loyalty_cards_by_waiter, date_from, olap_date_to, bar_name): 'loyalty_cards',
                }

                all_data = {}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        all_data[key] = future.result()
                    except Exception as e:
                        print(f"   [ERROR] OLAP {key}: {e}")
                        all_data[key] = None
        finally:
            olap.disconnect()

        # Получаем список сотрудников и метрики из кассовых смен ОДНИМ запросом (оптимизация)
        now = time.time()
        all_employee_metrics = {}

        iiko = IikoAPI()
        if iiko.authenticate():
            try:
                # Список сотрудников (с кэшем)
                if EMPLOYEES_CACHE['data'] and (now - EMPLOYEES_CACHE['timestamp']) < EMPLOYEES_CACHE_TTL:
                    employees_list = EMPLOYEES_CACHE['data']
                    print(f"   [CACHE] Using cached employees ({len(employees_list)})")
                else:
                    employees_list = iiko.get_employees()
                    EMPLOYEES_CACHE['data'] = employees_list
                    EMPLOYEES_CACHE['timestamp'] = now
                    print(f"   [CACHE] Fresh employees loaded ({len(employees_list)})")

                # Получаем метрики из кассовых смен для ВСЕХ сотрудников (unified метод)
                all_employee_metrics = iiko.get_employee_metrics_from_shifts(date_from, date_to)
                print(f"   [SHIFTS] Loaded metrics for {len(all_employee_metrics)} employees from cash shifts")
            finally:
                iiko.logout()
        else:
            employees_list = []
            all_employee_metrics = {}
            print("   [ERROR] Failed to authenticate to iiko")

        # Хелпер для нормализации имен (игнорируем порядок слов)
        def normalize_name(name):
            if not name:
                return set()
            return set(name.lower().strip().split())

        # Создаём маппинг employee_id -> employee для быстрого поиска
        emp_id_to_name = {emp.get('id'): emp.get('name') for emp in employees_list}

        # DEBUG: показываем имена для сопоставления
        print(f"   [DEBUG] OLAP names to compare: {employee_names}")
        iiko_names = [emp.get('name') for emp in employees_list]
        print(f"   [DEBUG] iiko employee names: {iiko_names[:10]}...")  # первые 10

        # Рассчитываем метрики для каждого сотрудника
        calculator = EmployeeMetricsCalculator()
        results = []

        for emp_name in employee_names:
            # Находим ID сотрудника с нормализацией имени
            employee_id = None
            emp_name_normalized = normalize_name(emp_name)

            for emp in employees_list:
                iiko_name = emp.get('name')
                if not iiko_name:
                    continue
                # Сначала пробуем точное совпадение
                if iiko_name == emp_name:
                    employee_id = emp.get('id')
                    break
                iiko_normalized = normalize_name(iiko_name)
                # Потом пробуем нормализованное (те же слова в любом порядке)
                if iiko_normalized == emp_name_normalized:
                    employee_id = emp.get('id')
                    print(f"   [MATCH] '{emp_name}' -> '{iiko_name}' (exact set)")
                    break
                # OLAP даёт "Имя Отчество", iiko — "Фамилия Имя Отчество"
                # Проверяем что OLAP-имя является подмножеством iiko-имени
                if emp_name_normalized and emp_name_normalized.issubset(iiko_normalized) and len(emp_name_normalized) >= 2:
                    employee_id = emp.get('id')
                    print(f"   [MATCH] '{emp_name}' -> '{iiko_name}' (subset)")
                    break

            # Получаем метрики из кассовых смен по employee_id
            emp_metrics = {}
            shifts_count = 0
            shift_locations = {}
            total_hours = 0.0
            late_count = 0
            cash_revenue = 0.0
            if employee_id:
                emp_metrics = all_employee_metrics.get(employee_id, {})
                shifts_count = emp_metrics.get('shifts_count', 0)
                shift_locations = emp_metrics.get('shift_locations', {})
                total_hours = emp_metrics.get('total_hours', 0.0)
                late_count = emp_metrics.get('late_count', 0)
                cash_revenue = emp_metrics.get('total_revenue', 0.0)
                print(f"   [SHIFTS] {emp_name}: {shifts_count} shifts, {total_hours:.1f}h, revenue: {cash_revenue:.0f}, late: {late_count} (employee_id: {employee_id[:8]}...)")
            else:
                print(f"   [WARNING] {emp_name}: employee_id NOT FOUND in iiko!")

            # Рассчитываем план на основе кассовых смен
            plan_revenue = get_employee_plan_by_shifts(shift_locations)

            # Рассчитываем метрики (используем OLAP для консистентности с dashboard)
            # Кассовые смены используем только для смен/часов/опозданий/локаций
            loyalty_cards_data = all_data.get('loyalty_cards', {})
            metrics = calculator.calculate(
                employee_name=emp_name,
                aggregated_data=all_data.get('aggregated'),
                draft_data=all_data.get('draft'),
                bottles_data=all_data.get('bottles'),
                kitchen_data=all_data.get('kitchen'),
                cancelled_data=all_data.get('cancelled'),
                plan_revenue=plan_revenue,
                date_from=date_from,
                date_to=date_to,
                shifts_count_override=shifts_count,
                total_hours_override=total_hours,
                late_count_override=late_count,
                loyalty_cards_count=loyalty_cards_data.get(emp_name, 0),
                total_revenue_override=None  # Используем OLAP выручку для консистентности
            )

            results.append({
                'name': emp_name,
                **metrics
            })

        print(f"[OK] Sravnenie zaversheno dlya {len(results)} sotrudnikov")

        return jsonify({
            'employees': results,
            'period': {'from': date_from, 'to': date_to}
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/employee-compare: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/bonus-calculate', methods=['POST'])
def bonus_calculate():
    """
    API endpoint для расчёта бонусов всех сотрудников.

    Формула (считается ПО ДНЯМ):
    - На каждый рабочий день: если выручка сотрудника > плана ТТ → перевыполнение
    - Суммируются только положительные дни
    - Бонус = 1 000 + (сумма дневных перевыполнений × 5%)
    - Если суммарное перевыполнение = 0 → бонус = 0
    """
    try:
        data = request.json
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры: date_from, date_to'}), 400

        started_at = time.perf_counter()

        def bonus_log(message):
            elapsed = time.perf_counter() - started_at
            print(f"[BONUS][{elapsed:7.2f}s] {message}", flush=True)

        bonus_log(f"Raschyot bonusov za period: {date_from} - {date_to}")

        # 1. iiko: кассовые смены — выручка, локация, дата (единый источник)
        now = time.time()
        all_employee_metrics = {}

        iiko = IikoAPI()
        if iiko.authenticate():
            try:
                if EMPLOYEES_CACHE['data'] and (now - EMPLOYEES_CACHE['timestamp']) < EMPLOYEES_CACHE_TTL:
                    employees_list = EMPLOYEES_CACHE['data']
                    print(f"   [CACHE] Using cached employees ({len(employees_list)})")
                else:
                    employees_list = iiko.get_employees()
                    EMPLOYEES_CACHE['data'] = employees_list
                    EMPLOYEES_CACHE['timestamp'] = now
                    print(f"   [CACHE] Fresh employees loaded ({len(employees_list)})")

                all_employee_metrics = iiko.get_employee_metrics_from_shifts(date_from, date_to)
                print(f"   [SHIFTS] Loaded metrics for {len(all_employee_metrics)} employees")
            finally:
                iiko.logout()
        else:
            employees_list = []
            print("   [ERROR] Failed to authenticate to iiko")

        bonus_log(f"Stage shifts complete: employees={len(all_employee_metrics)}")

        if not all_employee_metrics:
            return jsonify({'error': 'Нет данных за выбранный период'}), 404

        # 2. Подготовка: планы ТТ из daily_plans.json (рассчитываются автоматически из месячных планов)
        # Формула: пт/сб = 2x, остальные дни = 1x
        from core.employee_plans import normalize_bar_name, BAR_NAME_MAPPING

        # Маппинг employee_id -> имя
        emp_id_to_name = {emp.get('id'): emp.get('name') for emp in employees_list}

        system_users = EmployeeMetricsCalculator.SYSTEM_USERS + ['']

        # 3. Расчёт по дням для каждого сотрудника (данные из кассовых смен)
        results = []
        total_bonus = 0.0
        total_penalty = 0
        total_net = 0.0

        for emp_id, emp_metrics in all_employee_metrics.items():
            emp_name = emp_id_to_name.get(emp_id, '')
            if not emp_name or emp_name in system_users:
                continue

            shift_locations = emp_metrics.get('shift_locations', {})
            shift_revenues = emp_metrics.get('shift_revenues', {})
            shift_times = emp_metrics.get('shift_times', {})
            shifts_count = emp_metrics.get('shifts_count', 0)
            late_count = emp_metrics.get('late_count', 0)
            late_dates_set = set(emp_metrics.get('late_dates', []))

            # Считаем по дням
            total_revenue = 0.0
            total_plan = 0.0
            total_overperformance = 0.0
            days_detail = []

            for date_str in sorted(set(list(shift_locations.keys()) + list(shift_revenues.keys()))):
                day_revenue = shift_revenues.get(date_str, 0.0)
                total_revenue += day_revenue

                # План на этот день из daily_plans.json (автоматический расчёт пт/сб = 2x)
                location = shift_locations.get(date_str, '')
                day_plan = 0.0
                if location:
                    normalized = normalize_bar_name(location)
                    mapped_name = BAR_NAME_MAPPING.get(normalized, location)
                    # Получаем план из daily_plans.json
                    day_plan = get_daily_plan_for_date(date_str, mapped_name)

                total_plan += day_plan

                # Перевыполнение: только положительная разница
                day_over = max(0, day_revenue - day_plan) if day_plan > 0 else 0
                total_overperformance += day_over

                # Бонус за смену: 1000 + перевыполнение × 5% (только если план выполнен)
                day_bonus = (1000 + day_over * 0.05) if day_over > 0 else 0

                # Время открытия/закрытия смены
                times = shift_times.get(date_str, {})
                open_time = times.get('open', '')
                close_time = times.get('close', '')

                days_detail.append({
                    'date': date_str,
                    'revenue': round(day_revenue, 2),
                    'plan': round(day_plan, 2),
                    'overperformance': round(day_over, 2),
                    'day_bonus': round(day_bonus, 2),
                    'is_late': date_str in late_dates_set,
                    'open_time': open_time,
                    'close_time': close_time
                })

            # Формула бонуса: 1000 за каждую успешную смену + 5% от перевыполнения
            plan_percent = (total_revenue / total_plan * 100) if total_plan > 0 else 0
            bonus = sum(d['day_bonus'] for d in days_detail)

            # Штраф за опоздания: прогрессивная шкала 250, 500, 750...
            penalty = 250 * late_count * (late_count + 1) // 2
            net = max(0, bonus - penalty)

            total_bonus += bonus
            total_penalty += penalty
            total_net += net

            # Сортируем дни по дате
            days_detail.sort(key=lambda x: x['date'])

            # Часы работы из кассовых смен
            total_hours = emp_metrics.get('total_hours', 0.0)

            # Премия за передачу смены: 500 ₽ × количество смен
            shift_handover_bonus = shifts_count * 500

            results.append({
                'name': emp_name,
                'plan_revenue': round(total_plan, 2),
                'total_revenue': round(total_revenue, 2),
                'plan_percent': round(plan_percent, 1),
                'overperformance': round(total_overperformance, 2),
                'bonus': round(bonus, 2),
                'shifts_count': shifts_count,
                'late_count': late_count,
                'penalty': penalty,
                'net': round(net, 2),
                'shift_handover_bonus': shift_handover_bonus,
                'total_hours': round(total_hours, 1),
                'days': days_detail
            })

        bonus_log(f"Stage calculation complete: result_employees={len(results)}")

        # Сортируем: сначала с наибольшей итоговой суммой
        results.sort(key=lambda x: x['net'], reverse=True)

        print(f"[OK] Bonus calculated for {len(results)} employees, total bonus: {total_bonus:.0f}, penalty: {total_penalty}, net: {total_net:.0f}")

        return jsonify({
            'employees': results,
            'total_bonus': round(total_bonus, 2),
            'total_penalty': total_penalty,
            'total_net': round(total_net, 2),
            'period': {'from': date_from, 'to': date_to}
        })

    except Exception as e:
        try:
            bonus_log(f"FAILED: {e}")
        except Exception:
            pass
        print(f"[ERROR] Oshibka v /api/bonus-calculate: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _find_employee_in_olap(data_dict, emp_name):
    """
    Найти данные сотрудника в OLAP результатах (exact match + fuzzy по словам).
    Обрабатывает случаи вроде "Артемий Новаев" vs "Новаев Артемий".
    """
    if not data_dict:
        return None
    if emp_name in data_dict:
        return data_dict[emp_name]
    emp_words = set(emp_name.lower().split())
    for name, data in data_dict.items():
        name_words = set(name.lower().split())
        if emp_words == name_words or (len(emp_words) >= 2 and emp_words.issubset(name_words)):
            return data
    return None


def _build_kpi_metrics(emp_name, kpi_olap, shifts_count, total_hours):
    """
    Собрать метрики для KPI из OLAP данных.

    Формирует dict с теми же ключами, что и EmployeeMetricsCalculator.calculate(),
    но из 2 лёгких OLAP запросов вместо 4 тяжёлых.

    Источники:
      summary  -> total_checks, total_revenue, discount_sum
      categories -> draft/bottles/kitchen revenue, markup
      shifts (параметры) -> revenue_per_shift, revenue_per_hour
    """
    summary = _find_employee_in_olap(kpi_olap['summary'], emp_name)
    cat_rows = _find_employee_in_olap(kpi_olap['categories'], emp_name) or []

    total_checks = summary.get('total_checks', 0) if summary else 0
    total_revenue = summary.get('total_revenue', 0) if summary else 0
    discount_sum = summary.get('discount_sum', 0) if summary else 0

    # Разбивка по категориям
    draft_revenue = 0.0
    bottles_revenue = 0.0
    kitchen_revenue = 0.0
    total_cost = 0.0
    total_weighted_markup = 0.0

    for row in cat_rows:
        cat = row['category']
        rev = row['revenue']
        cost = row['cost']
        markup = row['markup']

        if cat == 'Напитки Розлив':
            draft_revenue += rev
        elif cat == 'Напитки Фасовка':
            bottles_revenue += rev
        else:
            kitchen_revenue += rev

        if cost > 0:
            total_weighted_markup += markup * cost
            total_cost += cost

    # Доли категорий (%)
    draft_share = (draft_revenue / total_revenue * 100) if total_revenue > 0 else 0
    bottles_share = (bottles_revenue / total_revenue * 100) if total_revenue > 0 else 0
    kitchen_share = (kitchen_revenue / total_revenue * 100) if total_revenue > 0 else 0

    # Производные метрики
    avg_check = (total_revenue / total_checks) if total_checks > 0 else 0
    revenue_per_shift = (total_revenue / shifts_count) if shifts_count > 0 else 0
    revenue_per_hour = (total_revenue / total_hours) if total_hours > 0 else 0
    avg_markup = ((total_weighted_markup / total_cost) * 100) if total_cost > 0 else 0
    gross = total_revenue + discount_sum
    discount_percent = (discount_sum / gross * 100) if gross > 0 else 0

    return {
        'total_revenue': round(total_revenue, 2),
        'draft_share': round(draft_share, 2),
        'bottles_share': round(bottles_share, 2),
        'kitchen_share': round(kitchen_share, 2),
        'draft_revenue': round(draft_revenue, 2),
        'bottles_revenue': round(bottles_revenue, 2),
        'kitchen_revenue': round(kitchen_revenue, 2),
        'avg_check': round(avg_check, 2),
        'total_checks': total_checks,
        'revenue_per_shift': round(revenue_per_shift, 2),
        'revenue_per_hour': round(revenue_per_hour, 2),
        'avg_markup': round(avg_markup, 2),
        'discount_sum': round(discount_sum, 2),
        'discount_percent': round(discount_percent, 2),
        'cancelled_count': 0,
    }


@employee_bp.route('/api/kpi-calculate', methods=['POST'])
def kpi_calculate():
    """
    API endpoint для расчёта KPI-бонусов всех сотрудников.

    Формула:
    - ratio = (Факт - Мін) / (Цель - Мін), capped [0, 2]
    - Премия_kpi = ratio × Смен × (5000 / 15)
    - Цели взвешены по сменам на точках
    """
    try:
        data = request.json
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры: date_from, date_to'}), 400

        month = date_from[:7]  # "YYYY-MM"
        started_at = time.perf_counter()

        def kpi_log(message):
            elapsed = time.perf_counter() - started_at
            print(f"[KPI][{elapsed:7.2f}s] {message}", flush=True)

        kpi_log(f"Raschyot KPI-bonusov za period: {date_from} - {date_to}, month: {month}")

        # 1. Проверяем наличие целей за месяц
        clear_kpi_cache()
        kpi_calc = KpiCalculator()
        month_targets = kpi_calc.reader.get_targets_for_month(month)
        kpi_log(f"Stage targets loaded: locations={len(month_targets)}")
        if not month_targets:
            return jsonify({'error': f'Нет KPI-целей за месяц {month}. Настройте цели во вкладке "Настройка целей".'}), 404

        # 2. iiko: список сотрудников + кассовые смены
        now = time.time()
        all_employee_metrics = {}

        iiko = IikoAPI()
        if iiko.authenticate():
            try:
                if EMPLOYEES_CACHE['data'] and (now - EMPLOYEES_CACHE['timestamp']) < EMPLOYEES_CACHE_TTL:
                    employees_list = EMPLOYEES_CACHE['data']
                    print(f"   [CACHE] Using cached employees ({len(employees_list)})")
                else:
                    employees_list = iiko.get_employees()
                    EMPLOYEES_CACHE['data'] = employees_list
                    EMPLOYEES_CACHE['timestamp'] = now
                    print(f"   [CACHE] Fresh employees loaded ({len(employees_list)})")

                all_employee_metrics = iiko.get_employee_metrics_from_shifts(date_from, date_to)
                print(f"   [SHIFTS] Loaded metrics for {len(all_employee_metrics)} employees")
            finally:
                iiko.logout()
        else:
            employees_list = []
            print("   [ERROR] Failed to authenticate to iiko")

        kpi_log(f"Stage shifts complete: employees={len(all_employee_metrics)}")

        if not all_employee_metrics:
            return jsonify({'error': 'Нет данных о сменах за выбранный период'}), 404

        # 3. OLAP: 2 легковесных запроса вместо 4 тяжёлых
        # Старый подход: 4 параллельных запроса с группировкой по DishName × Store × Date
        #   → тысячи строк, ~60 секунд
        # Новый подход: 2 запроса с агрегацией на сервере
        #   → ~200 строк, ~5-10 секунд
        olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko OLAP'}), 500

        try:
            kpi_log("Stage OLAP started (2 lightweight queries)")
            kpi_olap = olap.get_kpi_olap_data(date_from, olap_date_to)
        finally:
            olap.disconnect()

        kpi_log("Stage OLAP complete")

        if kpi_olap is None:
            return jsonify({'error': 'OLAP не вернул данные (таймаут или ошибка). Попробуйте ещё раз или уменьшите период.'}), 500

        # 4. Маппинг employee_id -> имя
        emp_id_to_name = {emp.get('id'): emp.get('name') for emp in employees_list}
        system_users = EmployeeMetricsCalculator.SYSTEM_USERS + ['']

        # 5. Расчёт KPI для каждого сотрудника
        results = []
        total_premium = 0.0
        processed_employees = 0

        for emp_id, emp_shifts in all_employee_metrics.items():
            emp_name = emp_id_to_name.get(emp_id, '')
            if not emp_name or emp_name in system_users:
                continue

            shift_locations = emp_shifts.get('shift_locations', {})
            shifts_count = emp_shifts.get('shifts_count', 0)
            total_hours = emp_shifts.get('total_hours', 0.0)

            if shifts_count == 0:
                continue

            # Собираем метрики из OLAP данных + смен (без EmployeeMetricsCalculator)
            metrics = _build_kpi_metrics(
                emp_name, kpi_olap, shifts_count, total_hours
            )

            # Рассчитываем KPI-бонус
            kpi_result = kpi_calc.calculate_employee(
                employee_name=emp_name,
                metrics=metrics,
                shift_locations=shift_locations,
                month=month,
            )

            if kpi_result:
                kpi_result['total_hours'] = round(total_hours, 1)
                results.append(kpi_result)
                total_premium += kpi_result['total_premium']

            processed_employees += 1
            if processed_employees == 1 or processed_employees % 3 == 0:
                kpi_log(
                    f"Stage employee loop: processed={processed_employees}, "
                    f"results={len(results)}, current={emp_name}"
                )

        # Сортируем по убыванию премии
        results.sort(key=lambda x: x['total_premium'], reverse=True)

        defaults = kpi_calc.reader.get_defaults()
        kpi_config = kpi_calc.reader.get_kpi_config_for_month(month)

        # kpi_names из конфига месяца
        kpi_names = {k: v.get('name', k) for k, v in kpi_config.items()}

        kpi_log(f"Stage final complete: results={len(results)}, total_premium={total_premium:.0f}")
        print(f"[OK] KPI calculated for {len(results)} employees, total premium: {total_premium:.0f}")

        return jsonify({
            'employees': results,
            'total_premium': round(total_premium, 2),
            'employee_count': len(results),
            'avg_premium': round(total_premium / len(results), 2) if results else 0,
            'period': {'from': date_from, 'to': date_to},
            'month': month,
            'defaults': defaults,
            'kpi_names': kpi_names,
            'kpi_config': kpi_config,
            'month_targets': month_targets,
            'available_metrics': AVAILABLE_METRICS,
        })

    except Exception as e:
        try:
            kpi_log(f"FAILED: {e}")
        except Exception:
            pass
        print(f"[ERROR] Oshibka v /api/kpi-calculate: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/kpi-targets', methods=['GET'])
def kpi_targets_get():
    """Получить текущие KPI-цели для редактора."""
    try:
        clear_kpi_cache()
        reader = KpiTargetsReader()
        data = reader.get_all_data()
        data['available_metrics'] = AVAILABLE_METRICS
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/kpi-targets', methods=['POST'])
def kpi_targets_save():
    """Сохранить KPI-цели."""
    try:
        new_data = request.json
        if not new_data or 'months' not in new_data:
            return jsonify({'error': 'Неверный формат данных'}), 400

        clear_kpi_cache()
        reader = KpiTargetsReader()
        reader.save_targets(new_data)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/employee-metrics-breakdown', methods=['POST'])
def employee_metrics_breakdown():
    """
    API endpoint для получения разбивки метрик по сотрудникам.
    Используется для раскрытия карточек на дашборде.
    """
    try:
        data = request.json
        venue_key = data.get('venue_key', 'all')
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        if not date_from or not date_to:
            return jsonify({'error': 'Требуются параметры: date_from, date_to'}), 400

        print(f"\n[BREAKDOWN] Razbiyka metrik po sotrudnikam")
        print(f"   Venue: {venue_key}, Period: {date_from} - {date_to}")

        # Маппинг venue_key -> bar_name для iiko
        venue_to_bar = {
            'bolshoy': 'Большой пр. В.О',
            'ligovskiy': 'Лиговский',
            'kremenchugskaya': 'Кременчугская',
            'varshavskaya': 'Варшавская',
            'all': None
        }
        bar_name = venue_to_bar.get(venue_key)

        # Загружаем данные OLAP для всех сотрудников
        # OLAP to-дата exclusive → +1 день
        olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(olap.get_employee_aggregated_metrics, date_from, olap_date_to, bar_name): 'aggregated',
                    executor.submit(olap.get_draft_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'draft',
                    executor.submit(olap.get_bottles_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'bottles',
                    executor.submit(olap.get_kitchen_sales_by_waiter_report, date_from, olap_date_to, bar_name): 'kitchen',
                }

                all_data = {}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        all_data[key] = future.result()
                    except Exception as e:
                        print(f"   [ERROR] OLAP {key}: {e}")
                        all_data[key] = None
        finally:
            olap.disconnect()

        # Собираем метрики по сотрудникам
        # aggregated - это dict {name: {metrics}}, draft/bottles/kitchen - OLAP ответы {'data': [...]}
        aggregated = all_data.get('aggregated') or {}
        draft_raw = all_data.get('draft') or {}
        bottles_raw = all_data.get('bottles') or {}
        kitchen_raw = all_data.get('kitchen') or {}
        draft = draft_raw.get('data', []) if isinstance(draft_raw, dict) else []
        bottles = bottles_raw.get('data', []) if isinstance(bottles_raw, dict) else []
        kitchen = kitchen_raw.get('data', []) if isinstance(kitchen_raw, dict) else []

        # Строим breakdown для каждой метрики
        employees_data = {}

        # Из aggregated получаем выручку, чеки (это dict с ключами = имена)
        if isinstance(aggregated, dict):
            for name, metrics in aggregated.items():
                if not name or name == 'Итого':
                    continue
                employees_data[name] = {
                    'name': name,
                    'revenue': float(metrics.get('DishDiscountSumInt', 0) or 0),
                    'checks': int(metrics.get('UniqOrderId.OrdersCount', 0) or 0),
                    'loyaltyWriteoffs': float(metrics.get('DiscountSum', 0) or 0),
                    'draft_revenue': 0, 'draft_cost': 0,
                    'bottles_revenue': 0, 'bottles_cost': 0,
                    'kitchen_revenue': 0, 'kitchen_cost': 0
                }

        # Добавляем выручку и себестоимость по категориям из OLAP данных
        for category, cat_key, cost_key in [
            (draft, 'draft', 'draft'),
            (bottles, 'bottles', 'bottles'),
            (kitchen, 'kitchen', 'kitchen')
        ]:
            for row in category:
                if isinstance(row, dict):
                    name = row.get('WaiterName') or row.get('Waiter') or row.get('waiter')
                    if name and name != 'Итого' and name in employees_data:
                        employees_data[name][f'{cat_key}_revenue'] += float(row.get('DishDiscountSumInt', 0) or 0)
                        employees_data[name][f'{cat_key}_cost'] += float(row.get('ProductCostBase.ProductCost', 0) or 0)

        # Рассчитываем производные метрики
        result = []
        for name, data in employees_data.items():
            total_revenue = data['revenue']
            checks = data['checks']

            # Средний чек
            avg_check = total_revenue / checks if checks > 0 else 0

            # Доли
            draft_share = (data['draft_revenue'] / total_revenue * 100) if total_revenue > 0 else 0
            bottles_share = (data['bottles_revenue'] / total_revenue * 100) if total_revenue > 0 else 0
            kitchen_share = (data['kitchen_revenue'] / total_revenue * 100) if total_revenue > 0 else 0

            # Себестоимость и прибыль
            total_cost = data['draft_cost'] + data['bottles_cost'] + data['kitchen_cost']
            profit = total_revenue - total_cost

            # Наценки по категориям: (выручка / себестоимость - 1) * 100
            markup_draft = ((data['draft_revenue'] / data['draft_cost'] - 1) * 100) if data['draft_cost'] > 0 else 0
            markup_packaged = ((data['bottles_revenue'] / data['bottles_cost'] - 1) * 100) if data['bottles_cost'] > 0 else 0
            markup_kitchen = ((data['kitchen_revenue'] / data['kitchen_cost'] - 1) * 100) if data['kitchen_cost'] > 0 else 0
            markup_percent = ((total_revenue / total_cost - 1) * 100) if total_cost > 0 else 0

            result.append({
                'name': name,
                'revenue': round(total_revenue, 0),
                'checks': checks,
                'averageCheck': round(avg_check, 0),
                'draftShare': round(draft_share, 1),
                'packagedShare': round(bottles_share, 1),
                'kitchenShare': round(kitchen_share, 1),
                'revenueDraft': round(data['draft_revenue'], 0),
                'revenuePackaged': round(data['bottles_revenue'], 0),
                'revenueKitchen': round(data['kitchen_revenue'], 0),
                'profit': round(profit, 0),
                'markupPercent': round(markup_percent, 1),
                'markupDraft': round(markup_draft, 1),
                'markupPackaged': round(markup_packaged, 1),
                'markupKitchen': round(markup_kitchen, 1),
                'loyaltyWriteoffs': round(data['loyaltyWriteoffs'], 0)
            })

        # Сортируем по выручке
        result.sort(key=lambda x: x['revenue'], reverse=True)

        print(f"[OK] Razbiyka: {len(result)} sotrudnikov")

        return jsonify({
            'employees': result,
            'period': {'from': date_from, 'to': date_to},
            'venue': venue_key
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/employee-metrics-breakdown: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

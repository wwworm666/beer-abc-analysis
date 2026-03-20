from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from extensions import shifts_mgr, notes_manager
from core.iiko_api import IikoAPI

schedule_bp = Blueprint('schedule', __name__)


@schedule_bp.route('/api/schedule/employees', methods=['GET'])
def schedule_get_employees():
    """Список сотрудников — переиспользуем /api/employees."""
    from routes.employee import get_employees_list
    result = get_employees_list()
    data = result.get_json()
    # /api/employees возвращает {employees: [...]}, нам нужен [{name: ...}]
    names = data.get('employees', []) if isinstance(data, dict) else []
    return jsonify([{'name': n} for n in names])


@schedule_bp.route('/api/schedule/roles', methods=['GET'])
def schedule_get_roles():
    """Список ролей."""
    return jsonify(shifts_mgr.get_roles())


@schedule_bp.route('/api/schedule/locations', methods=['GET'])
def schedule_get_locations():
    """Список точек."""
    return jsonify(shifts_mgr.get_locations())


@schedule_bp.route('/api/schedule/<int:year>/<int:month>', methods=['GET'])
def schedule_get_month(year, month):
    """Получить все смены за месяц."""
    return jsonify(shifts_mgr.get_shifts_for_month(year, month))


@schedule_bp.route('/api/schedule/shift', methods=['POST'])
def schedule_create_shift():
    """Создать смену."""
    data = request.get_json()
    shift_id = shifts_mgr.create_shift(
        date_str=data['date'],
        employee_name=data['employee_name'],
        location_id=data['location_id'],
        role_id=data['role_id'],
        notes=data.get('notes')
    )
    return jsonify({'id': shift_id})


@schedule_bp.route('/api/schedule/shift/<int:shift_id>', methods=['PUT'])
def schedule_update_shift(shift_id):
    """Обновить смену."""
    data = request.get_json()
    shifts_mgr.update_shift(shift_id, **data)
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/shift/<int:shift_id>', methods=['DELETE'])
def schedule_delete_shift(shift_id):
    """Удалить смену."""
    shifts_mgr.delete_shift(shift_id)
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/dayoff', methods=['GET'])
def schedule_get_dayoffs():
    """Пожелания выходных с фильтрацией."""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    employee_name = request.args.get('employee_name')
    return jsonify(shifts_mgr.get_day_off_requests(
        employee_name=employee_name,
        date_from=date_from,
        date_to=date_to
    ))


@schedule_bp.route('/api/schedule/dayoff', methods=['POST'])
def schedule_create_dayoff():
    """Создать пожелание выходного."""
    data = request.get_json()
    req_id = shifts_mgr.create_day_off_request(
        employee_name=data['employee_name'],
        date_from=data['date_from'],
        date_to=data['date_to'],
        reason=data.get('reason')
    )
    return jsonify({'id': req_id})


@schedule_bp.route('/api/schedule/dayoff/<int:request_id>', methods=['DELETE'])
def schedule_delete_dayoff(request_id):
    """Удалить пожелание выходного."""
    shifts_mgr.delete_day_off_request(request_id)
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/revenue/<date_str>', methods=['GET'])
def schedule_get_revenue(date_str):
    """Выручка по всем точкам за день."""
    return jsonify(shifts_mgr.get_revenue_for_day(date_str))


@schedule_bp.route('/api/schedule/revenue/<date_str>/<int:location_id>', methods=['PUT'])
def schedule_update_revenue(date_str, location_id):
    """Обновить план/факт выручки."""
    data = request.get_json()
    shifts_mgr.update_revenue(
        date_str=date_str,
        location_id=location_id,
        plan_revenue=data.get('plan_revenue'),
        fact_revenue=data.get('fact_revenue')
    )
    return jsonify({'ok': True})


@schedule_bp.route('/api/schedule/revenue/sync/<date_str>', methods=['POST'])
def schedule_sync_revenue(date_str):
    """Синхронизировать фактическую выручку из iiko за дату."""
    try:
        iiko = IikoAPI()
        iiko.authenticate()

        # Получаем кассовые смены за дату
        date_to = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        cash_shifts = iiko.get_cash_shifts(date_str, date_to)

        # Собираем выручку по точкам
        revenue_by_location = {}
        if cash_shifts:
            for shift in cash_shifts:
                point_of_sale = shift.get('pointOfSale', '')
                revenue = (shift.get('payOrders', {}).get('cashOrders', 0) or 0) + \
                          (shift.get('payOrders', {}).get('cardOrders', 0) or 0)

                # Маппинг имён точек продаж на locations в shifts.db
                for loc in shifts_mgr.get_locations():
                    if loc['name'].lower() in point_of_sale.lower() or \
                       loc['short_name'].lower() in point_of_sale.lower():
                        loc_name = loc['name']
                        revenue_by_location[loc_name] = revenue_by_location.get(loc_name, 0) + revenue

        updated = shifts_mgr.sync_revenue_from_iiko(date_str, revenue_by_location)
        return jsonify({'updated': updated, 'revenue': revenue_by_location})

    except Exception as e:
        print(f"[SCHEDULE SYNC ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@schedule_bp.route('/api/schedule/wishes', methods=['GET'])
def schedule_get_wishes():
    """Получить все пожелания."""
    return jsonify(shifts_mgr.get_wishes())


@schedule_bp.route('/api/schedule/wishes', methods=['POST'])
def schedule_save_wish():
    """Сохранить пожелание сотрудника."""
    data = request.get_json()
    shifts_mgr.save_wish(
        employee_name=data['employee_name'],
        text=data.get('text', '')
    )
    return jsonify({'ok': True})


# ============================================
# Meeting Notes API
# ============================================

@schedule_bp.route('/api/meeting-notes', methods=['GET'])
def get_meeting_note():
    """Получить заметку для бара и периода."""
    venue = request.args.get('venue', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    if not venue or not date_from or not date_to:
        return jsonify({'text': ''})
    note = notes_manager.get(venue, date_from, date_to)
    return jsonify({'text': note['text'] if note else ''})


@schedule_bp.route('/api/meeting-notes', methods=['POST'])
def save_meeting_note():
    """Сохранить заметку."""
    data = request.json
    venue = data.get('venue', '')
    date_from = data.get('date_from', '')
    date_to = data.get('date_to', '')
    text = data.get('text', '')
    if not venue or not date_from or not date_to:
        return jsonify({'error': 'venue, date_from, date_to required'}), 400
    notes_manager.save(venue, date_from, date_to, text)
    return jsonify({'ok': True})


@schedule_bp.route('/api/meeting-notes/history', methods=['GET'])
def meeting_notes_history():
    """Список заметок для бара (все периоды, новые первые)."""
    venue = request.args.get('venue', '')
    if not venue:
        return jsonify([])
    limit = request.args.get('limit', 10, type=int)
    notes = notes_manager.list_by_venue(venue, limit=limit)
    return jsonify(notes)

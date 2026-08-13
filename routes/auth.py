"""
Маршруты авторизации: вход, выход, первичная настройка и управление аккаунтами.

- /login            — форма входа (логин+пароль). Если аккаунтов ещё нет —
                      редирект на /setup (создание первого владельца).
- /setup            — первичная настройка: создать первого владельца (admin).
                      Работает только пока в системе нет ни одного аккаунта.
- /logout           — выход.
- /admin/users      — страница управления аккаунтами (только админ).
- /api/auth/users*  — API управления аккаунтами (только админ).
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for, jsonify, abort,
)

from core.auth_manager import get_auth_manager
from core.auth_guard import login_user, logout_user, current_user, admin_required

auth_bp = Blueprint('auth', __name__)


def _safe_next(nxt: str) -> str:
    """Защита от open-redirect: разрешаем только локальные пути (/...), не //, не схему."""
    if not nxt or not isinstance(nxt, str):
        return '/'
    if not nxt.startswith('/') or nxt.startswith('//') or '://' in nxt:
        return '/'
    return nxt


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    mgr = get_auth_manager()
    # Пока нет ни одного аккаунта — уводим на первичную настройку.
    if mgr.count_users() == 0:
        return redirect(url_for('auth.setup'))

    nxt = _safe_next(request.values.get('next', '/'))

    # Уже залогинен — на запрошенную страницу.
    if current_user():
        return redirect(nxt)

    if request.method == 'POST':
        login_value = (request.form.get('login') or '').strip()
        password = request.form.get('password') or ''
        user = mgr.verify_credentials(login_value, password)
        if user:
            login_user(user)
            return redirect(nxt)
        return render_template('login.html', mode='login', next=nxt,
                               error='Неверный логин или пароль'), 401

    return render_template('login.html', mode='login', next=nxt, error=None)


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """Первичная настройка: создать первого владельца. Доступна только пока
    нет ни одного аккаунта (иначе — на обычный вход)."""
    mgr = get_auth_manager()
    if mgr.count_users() > 0:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        login_value = (request.form.get('login') or '').strip()
        display_name = (request.form.get('display_name') or '').strip()
        password = request.form.get('password') or ''
        password2 = request.form.get('password2') or ''
        if password != password2:
            return render_template('login.html', mode='setup', next='/',
                                   error='Пароли не совпадают'), 400
        try:
            mgr.create_first_owner(login=login_value, display_name=display_name,
                                   password=password)
        except ValueError as e:
            # Среди ошибок и «Аккаунты уже существуют» (проиграл гонку first-run).
            return render_template('login.html', mode='setup', next='/',
                                   error=str(e)), 400
        user = mgr.verify_credentials(login_value, password)
        if user:
            login_user(user)
        return redirect('/')

    return render_template('login.html', mode='setup', next='/', error=None)


@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


# --- Управление аккаунтами (только админ) ---

def _schedule_employees():
    """Реестр сотрудников графика, best-effort (пустой список, если БД недоступна)."""
    try:
        from core.shifts_manager import get_shifts_manager
        return get_shifts_manager().get_schedule_employees(include_inactive=True)
    except Exception:
        return []


def _norm_emp_name(name):
    """Множество слов имени в нижнем регистре — для поиска тёзок в реестре."""
    return ' '.join(sorted((name or '').lower().split()))


@auth_bp.route('/admin/users')
@admin_required
def admin_users():
    mgr = get_auth_manager()
    # Реестр сотрудников графика: имена — для подсказки display_name, пары
    # {id, name} (только с устойчивым iiko_id) — для привязки аккаунта к сотруднику.
    emps = _schedule_employees()
    registry = [e['name'] for e in emps]

    # Метка опции в списке привязки. Одно имя на двух карточках iiko —
    # реальный случай (под него есть HandoverPenaltyConflict), а в списке из
    # одних имён админ такие опции не различит и привяжет аккаунт не к тому
    # человеку. Тёзкам дописываем хвост id; неактивных и отсутствующих в
    # реестре помечаем словами. Шум добавляется только там, где без него
    # ошибка неизбежна.
    with_id = [e for e in emps if e.get('id')]
    name_counts = {}
    for e in with_id:
        key = _norm_emp_name(e.get('name'))
        name_counts[key] = name_counts.get(key, 0) + 1

    employees = []
    for e in with_id:
        label = e['name']
        if name_counts.get(_norm_emp_name(e.get('name')), 0) > 1:
            label += f" · id ...{str(e['id'])[-6:]}"
        if not e.get('in_registry', True):
            label += ' (не в реестре)'
        if not e.get('active', True):
            label += ' (скрыт)'
        employees.append({'id': e['id'], 'name': e['name'], 'label': label})

    return render_template('admin_users.html',
                           users=mgr.list_users(),
                           registry_names=registry,
                           employees=employees,
                           duplicate_links=mgr.find_duplicate_employee_links())


@auth_bp.route('/api/auth/users', methods=['GET'])
@admin_required
def api_list_users():
    return jsonify(get_auth_manager().list_users())


@auth_bp.route('/api/auth/users', methods=['POST'])
@admin_required
def api_create_user():
    data = request.get_json() or {}
    try:
        uid = get_auth_manager().create_user(
            login=data.get('login', ''),
            display_name=data.get('display_name', ''),
            password=data.get('password', ''),
            is_admin=bool(data.get('is_admin')),
            short_label=data.get('short_label', ''),
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'id': uid})


@auth_bp.route('/api/auth/users/<int:user_id>/profile', methods=['POST'])
@admin_required
def api_update_profile(user_id):
    """Изменить имя и/или сокращение аккаунта (сокращение вводится вручную)."""
    data = request.get_json() or {}
    try:
        get_auth_manager().update_profile(
            user_id,
            display_name=data.get('display_name'),
            short_label=data.get('short_label'),
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@auth_bp.route('/api/auth/users/<int:user_id>/employee', methods=['POST'])
@admin_required
def api_set_employee(user_id):
    """Привязать аккаунт к сотруднику графика по iiko_id (пусто = отвязать).

    Существование сотрудника проверяется ЗДЕСЬ, а не в AuthManager: менеджер
    работает только с auth.db, и тащить в него shifts.db значило бы связать две
    независимые базы. По этой привязке личная страница отдаёт человеку его
    зарплату, поэтому id из ниоткуда принимать нельзя — список в форме
    фильтрованный, но эндпоинт принимает что угодно.
    Уникальность привязки (один сотрудник = один аккаунт) проверяет менеджер.

    Реестр пуст (график недоступен) -> проверку пропускаем: недоступность
    shifts.db не должна лишать админа возможности управлять аккаунтами.
    """
    data = request.get_json() or {}
    emp_id = (data.get('employee_iiko_id') or '').strip()
    if emp_id:
        known = {str(e['id']) for e in _schedule_employees() if e.get('id')}
        if known and emp_id not in known:
            return jsonify({'error': 'Сотрудник с таким идентификатором не найден '
                                     'в реестре графика'}), 400
    try:
        get_auth_manager().set_employee_link(user_id, emp_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@auth_bp.route('/api/auth/users/<int:user_id>/password', methods=['POST'])
@admin_required
def api_reset_password(user_id):
    data = request.get_json() or {}
    try:
        get_auth_manager().set_password(user_id, data.get('password', ''))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@auth_bp.route('/api/auth/users/<int:user_id>/active', methods=['POST'])
@admin_required
def api_set_active(user_id):
    data = request.get_json() or {}
    try:
        get_auth_manager().set_active(user_id, bool(data.get('active')))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@auth_bp.route('/api/auth/users/<int:user_id>/admin', methods=['POST'])
@admin_required
def api_set_admin(user_id):
    data = request.get_json() or {}
    try:
        get_auth_manager().set_admin(user_id, bool(data.get('is_admin')))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@auth_bp.route('/api/auth/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    try:
        get_auth_manager().delete_user(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})

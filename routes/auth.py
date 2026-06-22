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

@auth_bp.route('/admin/users')
@admin_required
def admin_users():
    mgr = get_auth_manager()
    # Имена из реестра графика — для подсказки display_name (связь «кто менял»).
    try:
        from core.shifts_manager import get_shifts_manager
        registry = [e['name'] for e in get_shifts_manager().get_schedule_employees(include_inactive=True)]
    except Exception:
        registry = []
    return render_template('admin_users.html',
                           users=mgr.list_users(),
                           registry_names=registry)


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
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'id': uid})


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

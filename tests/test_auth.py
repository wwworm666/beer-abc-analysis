"""
Тесты авторизации. Совместимы с pytest, но pytest локально не установлен,
поэтому файл self-runnable: `py -3 tests/test_auth.py` прогоняет все test_*-функции
и печатает PASS/FAIL (ненулевой код выхода при падении).

Покрывает: хэш/проверку паролей, валидации, защиту последнего админа,
глобальный гейт (аноним -> redirect/401), first-run setup, полный цикл входа,
admin-only доступ и стабильность SECRET_KEY.
"""

import os
import sys
import tempfile

# repo root в путь (запуск из корня: py -3 tests/test_auth.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Локальный прогон по http: Secure-cookie выключаем, иначе test client их не сохранит.
os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask, jsonify  # noqa: E402
import core.auth_manager as am  # noqa: E402
from core.auth_guard import init_auth, admin_required  # noqa: E402
from routes.auth import auth_bp  # noqa: E402
import config  # noqa: E402

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')


def _fresh_manager():
    """Свежий AuthManager на временной БД, подставленный как синглтон."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)  # пусть менеджер создаст с нуля
    mgr = am.AuthManager(db_path=path)
    am._auth_manager = mgr
    return mgr


def _make_app():
    app = Flask('test_auth', template_folder=TEMPLATES, static_folder=STATIC)
    app.register_blueprint(auth_bp)

    @app.route('/secret')
    def secret():
        return 'секрет'

    @app.route('/api/ping')
    def api_ping():
        return jsonify({'pong': True})

    @app.route('/admin-only')
    @admin_required
    def admin_only():
        return 'только админ'

    init_auth(app)
    return app


# --- auth_manager ---

def test_password_hashing_and_verify():
    mgr = _fresh_manager()
    uid = mgr.create_user('ivan', 'Иван Петров', 'secret12', is_admin=False)
    assert uid > 0
    assert mgr.verify_credentials('ivan', 'secret12')['login'] == 'ivan'
    assert mgr.verify_credentials('IVAN', 'secret12') is not None, 'логин регистронезависим'
    assert mgr.verify_credentials('ivan', 'wrong') is None
    assert mgr.verify_credentials('nobody', 'secret12') is None
    # пароль не хранится в открытом виде
    with mgr._get_connection() as conn:
        h = conn.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()[0]
    assert 'secret12' not in h


def test_inactive_user_cannot_login():
    mgr = _fresh_manager()
    admin = mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True)
    uid = mgr.create_user('bob', 'Боб', 'bobpass12')
    mgr.set_active(uid, False)
    assert mgr.verify_credentials('bob', 'bobpass12') is None


def test_create_validations():
    mgr = _fresh_manager()
    raised = 0
    for bad in [('a', 'name', 'longenough'),        # логин короткий
                ('ok', 'name', '12'),                # пароль короткий
                ('bad login', 'name', 'longenough')]:  # пробел в логине
        try:
            mgr.create_user(*bad)
        except ValueError:
            raised += 1
    assert raised == 3, f'ожидали 3 ошибки валидации, получили {raised}'
    mgr.create_user('dup', 'X', 'passpass')
    try:
        mgr.create_user('dup', 'Y', 'passpass')
        assert False, 'дубликат логина должен падать'
    except ValueError:
        pass


def test_create_first_owner_guard():
    mgr = _fresh_manager()
    uid = mgr.create_first_owner('owner', 'Владелец', 'ownerpass')
    assert mgr.get_by_id(uid)['is_admin'] is True
    # пока есть хоть один аккаунт — повторное создание владельца запрещено
    try:
        mgr.create_first_owner('other', 'Другой', 'otherpass')
        assert False, 'create_first_owner должен падать при непустой системе'
    except ValueError:
        pass
    assert mgr.count_users() == 1


def test_min_password_len_enforced():
    mgr = _fresh_manager()
    for bad in (lambda: mgr.create_user('shorty', 'S', '1234567'),       # 7 < 8
                lambda: mgr.create_first_owner('own', 'O', 'short12')):    # 7 < 8
        try:
            bad()
            assert False, 'пароль короче 8 должен отклоняться'
        except ValueError:
            pass


def test_last_admin_protected():
    mgr = _fresh_manager()
    a = mgr.create_user('admin1', 'A1', 'passpass', is_admin=True)
    # единственный админ — нельзя ни выключить, ни разжаловать, ни удалить
    for fn in (lambda: mgr.set_active(a, False),
               lambda: mgr.set_admin(a, False),
               lambda: mgr.delete_user(a)):
        try:
            fn()
            assert False, 'операция с последним админом должна падать'
        except ValueError:
            pass
    # со вторым админом — разжаловать первого уже можно
    mgr.create_user('admin2', 'A2', 'passpass', is_admin=True)
    mgr.set_admin(a, False)  # не должно падать
    assert mgr.get_by_id(a)['is_admin'] is False


# --- гейт и потоки входа ---

def test_gate_blocks_anonymous():
    _fresh_manager().create_user('usr', 'U', 'passpass')  # есть юзеры -> /login не редиректит на setup
    app = _make_app()
    c = app.test_client()
    r = c.get('/secret')
    assert r.status_code == 302 and '/login' in r.headers['Location'], r.status_code
    r = c.get('/api/ping')
    assert r.status_code == 401, r.status_code
    assert r.get_json().get('auth_required') is True


def test_first_run_setup_flow():
    _fresh_manager()  # 0 пользователей
    app = _make_app()
    c = app.test_client()
    # /login при пустой системе уводит на /setup
    r = c.get('/login')
    assert r.status_code == 302 and '/setup' in r.headers['Location']
    r = c.get('/setup')
    assert r.status_code == 200 and 'Создать' in r.get_data(as_text=True)
    # создаём владельца -> залогинены -> защищённая страница доступна
    r = c.post('/setup', data={'login': 'owner', 'display_name': 'Хозяин',
                               'password': 'ownerpass', 'password2': 'ownerpass'})
    assert r.status_code == 302
    r = c.get('/secret')
    assert r.status_code == 200 and 'секрет' in r.get_data(as_text=True)
    # setup больше недоступен (есть аккаунты)
    assert c.get('/setup').status_code == 302
    assert am.get_auth_manager().count_users() == 1


def test_login_logout_flow():
    mgr = _fresh_manager()
    mgr.create_user('ivan', 'Иван', 'secret12')
    app = _make_app()
    c = app.test_client()
    # неверный пароль
    r = c.post('/login', data={'login': 'ivan', 'password': 'nope'})
    assert r.status_code == 401
    # верный
    r = c.post('/login', data={'login': 'ivan', 'password': 'secret12'})
    assert r.status_code == 302
    assert c.get('/secret').status_code == 200
    # выход
    assert c.get('/logout').status_code == 302
    assert c.get('/secret').status_code == 302  # снова под гейтом


def test_admin_only_access():
    mgr = _fresh_manager()
    mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True)
    mgr.create_user('bob', 'Боб', 'bobpass12', is_admin=False)
    app = _make_app()

    # обычный пользователь -> 403 на admin-only и на /admin/users
    c = app.test_client()
    c.post('/login', data={'login': 'bob', 'password': 'bobpass12'})
    assert c.get('/admin-only').status_code == 403
    assert c.get('/admin/users').status_code == 403
    assert c.post('/api/auth/users',
                  json={'login': 'x', 'display_name': 'X', 'password': 'passpass'}).status_code == 403

    # админ -> 200/доступ
    c2 = app.test_client()
    c2.post('/login', data={'login': 'owner', 'password': 'ownerpass'})
    assert c2.get('/admin-only').status_code == 200
    assert c2.get('/admin/users').status_code == 200
    assert c2.post('/api/auth/users',
                   json={'login': 'new', 'display_name': 'Новый', 'password': 'passpass'}).status_code == 200
    assert mgr.get_by_login('new') is not None


def test_open_redirect_blocked():
    mgr = _fresh_manager()
    mgr.create_user('ivan', 'Иван', 'secret12')
    app = _make_app()
    c = app.test_client()
    r = c.post('/login?next=https://evil.example/phish',
               data={'login': 'ivan', 'password': 'secret12'})
    assert r.status_code == 302
    assert r.headers['Location'] in ('/', 'http://localhost/'), r.headers['Location']


def test_secret_key_stable_and_env_override():
    # без env: два вызова дают один и тот же персистентный ключ
    saved = os.environ.pop('SECRET_KEY', None)
    try:
        k1 = config.get_secret_key()
        k2 = config.get_secret_key()
        assert k1 == k2 and len(k1) >= 32
        # env override имеет приоритет
        os.environ['SECRET_KEY'] = 'fixed-key-value'
        assert config.get_secret_key() == b'fixed-key-value'
    finally:
        os.environ.pop('SECRET_KEY', None)
        if saved is not None:
            os.environ['SECRET_KEY'] = saved


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            import traceback
            print(f'FAIL {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())

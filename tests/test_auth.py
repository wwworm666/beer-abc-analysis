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
    for bad in (lambda: mgr.create_user('shorty', 'S', '123'),       # 3 < 4
                lambda: mgr.create_first_owner('own', 'O', 'ab')):    # 2 < 4
        try:
            bad()
            assert False, 'пароль короче 4 должен отклоняться'
        except ValueError:
            pass
    # 4 символов достаточно
    uid = mgr.create_user('okuser', 'OK', '1234')
    assert mgr.get_by_id(uid) is not None


def test_short_label_stored_and_editable():
    mgr = _fresh_manager()
    uid = mgr.create_user('an', 'Антон Николаев', 'passpass', short_label='АН')
    assert mgr.get_by_id(uid)['short_label'] == 'АН'
    # сокращение НЕ авто-генерируется: без передачи остаётся пустым
    uid2 = mgr.create_user('iv', 'Иван Петров', 'passpass')
    assert mgr.get_by_id(uid2)['short_label'] == ''
    # правится отдельно (имя и/или сокращение)
    mgr.update_profile(uid, display_name='Антон Н.', short_label='Ан')
    u = mgr.get_by_id(uid)
    assert u['display_name'] == 'Антон Н.' and u['short_label'] == 'Ан'


def test_update_profile_and_set_password_reject_missing():
    mgr = _fresh_manager()
    mgr.create_user('owner', 'Владелец', 'passpass', is_admin=True)
    for bad in (lambda: mgr.update_profile(9999, display_name='X'),
                lambda: mgr.set_password(9999, 'newpass')):
        try:
            bad()
            assert False, 'операция с несуществующим id должна падать'
        except ValueError:
            pass


def test_migration_adds_short_label_to_v1_db():
    import sqlite3 as _sq
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)
    # старая схема v1 — без short_label
    conn = _sq.connect(path)
    conn.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
        password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, last_login_at TEXT)""")
    conn.execute("""INSERT INTO users (login, display_name, password_hash, is_admin, active, created_at)
                    VALUES ('old', 'Старый', 'x', 1, 1, '2026-01-01')""")
    conn.commit()
    conn.close()
    mgr = am.AuthManager(db_path=path)  # должен добавить колонку, не потеряв данные
    u = mgr.get_by_login('old')
    assert u is not None and u['short_label'] == ''


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


def test_employee_link_set_and_clear():
    mgr = _fresh_manager()
    uid = mgr.create_user('ivan', 'Иван Петров', 'passpass')
    assert mgr.get_by_id(uid)['employee_iiko_id'] is None
    mgr.set_employee_link(uid, 'iiko-guid-123')
    assert mgr.get_by_id(uid)['employee_iiko_id'] == 'iiko-guid-123'
    # пустое значение -> отвязка (NULL)
    mgr.set_employee_link(uid, '   ')
    assert mgr.get_by_id(uid)['employee_iiko_id'] is None
    # несуществующий пользователь
    try:
        mgr.set_employee_link(99999, 'x')
        assert False, 'привязка несуществующего id должна падать'
    except ValueError:
        pass


def test_migration_adds_employee_link_to_v2_db():
    import sqlite3 as _sq
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)
    # схема v2 — со short_label, но без employee_iiko_id
    conn = _sq.connect(path)
    conn.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
        short_label TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, last_login_at TEXT)""")
    conn.execute("PRAGMA user_version=2")
    conn.execute("""INSERT INTO users (login, display_name, password_hash, is_admin, active, created_at)
                    VALUES ('old', 'Старый', 'x', 1, 1, '2026-01-01')""")
    conn.commit()
    conn.close()
    mgr = am.AuthManager(db_path=path)  # должен добавить колонку, не потеряв данные
    u = mgr.get_by_login('old')
    assert u is not None and u['employee_iiko_id'] is None


def _fake_registry(pairs):
    """Подменить реестр сотрудников графика на список (id, name).

    Реестр подставляется ЯВНО, а не берётся из локальной shifts.db: иначе тест
    зависит от содержимого чужой базы — при пустом реестре валидация эндпоинта
    пропускает любой id, при непустом отклоняет выдуманный.
    """
    import routes.auth as ra
    orig = ra._schedule_employees
    ra._schedule_employees = lambda: [{'id': i, 'name': n, 'active': True,
                                       'in_registry': True} for i, n in pairs]

    def restore():
        ra._schedule_employees = orig
    return restore


def test_admin_set_employee_endpoint():
    mgr = _fresh_manager()
    mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True)
    bob = mgr.create_user('bob', 'Боб', 'bobpass12')
    app = _make_app()
    restore = _fake_registry([('guid-9', 'Иван Петров')])
    try:
        # админ привязывает сотрудника к аккаунту
        c = app.test_client()
        c.post('/login', data={'login': 'owner', 'password': 'ownerpass'})
        r = c.post('/api/auth/users/%d/employee' % bob, json={'employee_iiko_id': 'guid-9'})
        assert r.status_code == 200, (r.status_code, r.get_json())
        assert mgr.get_by_id(bob)['employee_iiko_id'] == 'guid-9'
        # обычному пользователю эндпоинт запрещён
        c2 = app.test_client()
        c2.post('/login', data={'login': 'bob', 'password': 'bobpass12'})
        assert c2.post('/api/auth/users/%d/employee' % bob,
                       json={'employee_iiko_id': 'guid-9'}).status_code == 403
    finally:
        restore()


# --- один сотрудник = один аккаунт (иначе кто-то видит чужую зарплату) ---

def test_employee_link_rejects_duplicate():
    """Второй аккаунт на того же сотрудника отклоняется, первый цел."""
    mgr = _fresh_manager()
    a = mgr.create_user('anna', 'Анна', 'passpass')
    b = mgr.create_user('boris', 'Борис', 'passpass')
    mgr.set_employee_link(a, 'guid-X')
    try:
        mgr.set_employee_link(b, 'guid-X')
        assert False, 'дубль привязки должен отклоняться'
    except ValueError as e:
        assert 'anna' in str(e), str(e)
    assert mgr.get_by_id(a)['employee_iiko_id'] == 'guid-X'
    assert mgr.get_by_id(b)['employee_iiko_id'] is None


def test_employee_link_relink_same_user_ok():
    """Повторная привязка того же аккаунта к тому же сотруднику идемпотентна."""
    mgr = _fresh_manager()
    uid = mgr.create_user('anna', 'Анна', 'passpass')
    mgr.set_employee_link(uid, 'guid-X')
    mgr.set_employee_link(uid, 'guid-X')  # не должно падать на собственной привязке
    assert mgr.get_by_id(uid)['employee_iiko_id'] == 'guid-X'


def test_employee_unlink_always_allowed():
    """Отвязка проверок не проходит — снять привязку можно всегда."""
    mgr = _fresh_manager()
    a = mgr.create_user('anna', 'Анна', 'passpass')
    b = mgr.create_user('boris', 'Борис', 'passpass')
    mgr.set_employee_link(a, 'guid-X')
    mgr.set_employee_link(a, '')          # отвязали
    mgr.set_employee_link(b, 'guid-X')    # теперь сотрудник свободен
    assert mgr.get_by_id(a)['employee_iiko_id'] is None
    assert mgr.get_by_id(b)['employee_iiko_id'] == 'guid-X'


def test_list_users_by_employee_id():
    mgr = _fresh_manager()
    a = mgr.create_user('anna', 'Анна', 'passpass')
    mgr.create_user('boris', 'Борис', 'passpass')
    mgr.set_employee_link(a, 'guid-X')
    found = mgr.list_users_by_employee_id('guid-X')
    assert [u['login'] for u in found] == ['anna'], found
    assert mgr.list_users_by_employee_id('guid-NONE') == []
    assert mgr.list_users_by_employee_id('') == []
    assert mgr.list_users_by_employee_id(None) == []


def test_find_duplicate_employee_links():
    """Дубль-наследие (вставлен напрямую SQL, минуя проверку) обнаруживается."""
    import sqlite3 as _sq
    mgr = _fresh_manager()
    a = mgr.create_user('anna', 'Анна', 'passpass')
    b = mgr.create_user('boris', 'Борис', 'passpass')
    mgr.set_employee_link(a, 'guid-X')
    assert mgr.find_duplicate_employee_links() == []
    # как будто привязка появилась до появления проверки
    conn = _sq.connect(mgr.db_path)
    conn.execute("UPDATE users SET employee_iiko_id='guid-X' WHERE id=?", (b,))
    conn.commit()
    conn.close()
    dups = mgr.find_duplicate_employee_links()
    assert len(dups) == 1, dups
    assert dups[0]['employee_iiko_id'] == 'guid-X'
    assert sorted(dups[0]['logins']) == ['anna', 'boris'], dups
    # и старт на такой БД не падает (диагностика в _init_database)
    assert am.AuthManager(db_path=mgr.db_path).count_users() == 2


def test_admin_set_employee_rejects_unknown_id():
    """Эндпоинт не принимает id, которого нет в реестре графика."""
    mgr = _fresh_manager()
    mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True)
    bob = mgr.create_user('bob', 'Боб', 'bobpass12')
    app = _make_app()
    c = app.test_client()
    c.post('/login', data={'login': 'owner', 'password': 'ownerpass'})

    restore = _fake_registry([('guid-known', 'Иван Петров')])
    try:
        r = c.post('/api/auth/users/%d/employee' % bob, json={'employee_iiko_id': 'guid-ghost'})
        assert r.status_code == 400, r.status_code
        assert mgr.get_by_id(bob)['employee_iiko_id'] is None
        r = c.post('/api/auth/users/%d/employee' % bob, json={'employee_iiko_id': 'guid-known'})
        assert r.status_code == 200, r.get_json()
        assert mgr.get_by_id(bob)['employee_iiko_id'] == 'guid-known'
    finally:
        restore()


def test_admin_set_employee_duplicate_returns_400():
    """Дубль через эндпоинт — 400 с внятным текстом, а не 500."""
    mgr = _fresh_manager()
    mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True)
    a = mgr.create_user('anna', 'Анна', 'passpass')
    b = mgr.create_user('boris', 'Борис', 'passpass')
    mgr.set_employee_link(a, 'guid-X')
    app = _make_app()
    restore = _fake_registry([('guid-X', 'Иван Петров')])
    try:
        c = app.test_client()
        c.post('/login', data={'login': 'owner', 'password': 'ownerpass'})
        r = c.post('/api/auth/users/%d/employee' % b, json={'employee_iiko_id': 'guid-X'})
        assert r.status_code == 400, r.status_code
        assert 'anna' in (r.get_json() or {}).get('error', '')
    finally:
        restore()


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

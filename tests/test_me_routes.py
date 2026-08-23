"""
Тесты эндпоинтов личной страницы `/me` (routes/me.py).

Self-runnable: `py -3 tests/test_me_routes.py`.

Проверяем главное: чужие данные получить нельзя (параметра сотрудника нет),
отсутствие снимка и привязки — это 200 со статусом, а не 500 и не нули, и файл
снимка от другой версии не роняет страницу.

Моков iiko нет: снимок подкладывается файлом в временный каталог, привязка
аккаунта ставится через AuthManager на временной БД. Тот же приём подмены
атрибутов модуля, что в tests/test_salary_payload.py.
"""

import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import core.auth_manager as am  # noqa: E402
import core.me_snapshot as ms  # noqa: E402
import routes.me as rm  # noqa: E402
from core.auth_guard import init_auth  # noqa: E402
from core.me_identity import SNAPSHOT_SCHEMA  # noqa: E402
from routes.auth import auth_bp  # noqa: E402
from routes.me import me_bp  # noqa: E402

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')

ID_A = 'guid-aaaa'
ID_B = 'guid-bbbb'


def _fresh_manager():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)
    mgr = am.AuthManager(db_path=path)
    am._auth_manager = mgr
    return mgr


def _make_app():
    app = Flask('test_me', template_folder=TEMPLATES, static_folder=STATIC)
    app.jinja_env.globals['app_version'] = 'test'
    app.register_blueprint(auth_bp)
    app.register_blueprint(me_bp)
    init_auth(app)
    return app


def _tmp_snapshot_dir():
    """Подменить каталог снимков на временный. Возвращает (путь, восстановитель)."""
    path = tempfile.mkdtemp(prefix='me_snap_')
    orig = ms.snapshot_dir
    ms.snapshot_dir = lambda: path

    def restore():
        ms.snapshot_dir = orig
        shutil.rmtree(path, ignore_errors=True)
    return path, restore


def _fake_registry(pairs):
    """Подменить реестр сотрудников графика на список (id, name)."""
    orig = rm._registry
    rm._registry = lambda: [{'id': i, 'name': n, 'active': True, 'in_registry': True}
                            for i, n in pairs]
    return lambda: setattr(rm, '_registry', orig)


def _write_snapshot(dir_path, month, rows, *, schema=SNAPSHOT_SCHEMA, extra=None):
    data = {
        '_schema': schema,
        '_month': month,
        '_refreshed_at': '2026-08-13T07:42:11+03:00',
        '_refreshed_by': 'test',
        '_source_status': {'bonus': 'ok', 'kpi': 'ok', 'hours': 'ok', 'olap_metrics': 'ok'},
        'norms': {'shift_norm': 15, 'hours_norm': 113},
        'employees': {r['employee_id']: r for r in rows},
        'unlinked_hours': [],
    }
    data.update(extra or {})
    with open(os.path.join(dir_path, f'month__{month}.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def _row(emp_id, name, total):
    return {
        'employee_id': emp_id, 'name_iiko': name, 'name_olap': name,
        'name_schedule': name,
        'metrics': {'status': 'ok', 'total_revenue': total * 10},
        'kpi': {'status': 'ok', 'total_premium': 500.0},
        'hours': {'trust': 'id', 'total_hours': 97.0, 'total_pay': 29100.0},
        'money': {'total': total, 'excluded_components': []},
    }


def _login(app, login, password):
    c = app.test_client()
    c.post('/login', data={'login': login, 'password': password})
    return c


# --- гейт и валидация ---

def test_api_me_requires_login():
    _fresh_manager().create_user('usr', 'U', 'passpass')
    app = _make_app()
    r = app.test_client().get('/api/me')
    assert r.status_code == 401, r.status_code
    assert (r.get_json() or {}).get('auth_required') is True


def test_api_me_month_validation():
    mgr = _fresh_manager()
    mgr.create_user('usr', 'U', 'passpass')
    c = _login(_make_app(), 'usr', 'passpass')
    assert c.get('/api/me?month=2026-13').status_code == 400
    assert c.get('/api/me?month=2026-8').status_code == 400
    assert c.get('/api/me?month=nonsense').status_code == 400
    assert c.get('/api/me').status_code == 200


def test_root_leads_to_me_page():
    """«Я» — главная: `/` ведёт на `/me`, дашборд остаётся на `/dashboard`.

    Код именно 302: 301 браузеры кэшируют бессрочно, и вернуть главную назад
    было бы нельзя без чистки кэша у каждого.
    """
    from routes.pages import pages_bp
    mgr = _fresh_manager()
    mgr.create_user('usr', 'U', 'passpass')
    app = _make_app()
    app.register_blueprint(pages_bp)
    c = _login(app, 'usr', 'passpass')
    r = c.get('/')
    assert r.status_code == 302, r.status_code
    assert r.headers['Location'].endswith('/me'), r.headers['Location']
    rules = {str(rule.rule) for rule in app.url_map.iter_rules()}
    assert '/dashboard' in rules


def test_me_page_renders_for_unlinked_account():
    """Страница обязана открываться и без привязки: объяснение, а не 500."""
    mgr = _fresh_manager()
    mgr.create_user('usr', 'Бармен Без Привязки', 'passpass')
    c = _login(_make_app(), 'usr', 'passpass')
    r = c.get('/me')
    assert r.status_code == 200, r.status_code
    body = r.data.decode('utf-8')
    assert 'myShifts' in body            # хост личного экрана смен на месте
    assert 'factModal' in body           # модалка закрытия смены на месте
    d = c.get('/api/me').get_json()
    assert d['identity']['status'] == 'not_linked'
    assert d['money'] is None and d['kpi'] is None and d['metrics'] is None
    assert 'Аккаунты' in d['identity']['message']


# --- чужие данные получить нельзя ---

def test_api_me_has_no_employee_parameter():
    """Любые параметры про сотрудника игнорируются: ответ тот же."""
    mgr = _fresh_manager()
    uid = mgr.create_user('anna', 'Анна Смирнова', 'passpass')
    mgr.set_employee_link(uid, ID_A)
    path, restore_dir = _tmp_snapshot_dir()
    restore_reg = _fake_registry([(ID_A, 'Анна Смирнова'), (ID_B, 'Борис Петров')])
    try:
        _write_snapshot(path, ms.current_month(),
                        [_row(ID_A, 'Анна Смирнова', 111.0),
                         _row(ID_B, 'Борис Петров', 222.0)])
        c = _login(_make_app(), 'anna', 'passpass')
        plain = c.get('/api/me').get_json()
        spoofed = c.get('/api/me?employee_id=%s&employee_iiko_id=%s&user_id=2'
                        % (ID_B, ID_B)).get_json()
        assert plain['money']['total'] == 111.0
        assert spoofed == plain, 'параметры запроса не должны влиять на выдачу'
    finally:
        restore_reg()
        restore_dir()


def test_api_me_ambiguous_link_hides_money():
    """Два активных аккаунта на одного сотрудника: денег не показываем никому."""
    mgr = _fresh_manager()
    a = mgr.create_user('anna', 'Анна Смирнова', 'passpass')
    b = mgr.create_user('anna2', 'Анна Смирнова', 'passpass')
    mgr.set_employee_link(a, ID_A)
    # дубль как наследие прода — напрямую в БД, минуя проверку уникальности
    import sqlite3
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("UPDATE users SET employee_iiko_id=? WHERE id=?", (ID_A, b))
    conn.commit()
    conn.close()

    path, restore_dir = _tmp_snapshot_dir()
    restore_reg = _fake_registry([(ID_A, 'Анна Смирнова')])
    try:
        _write_snapshot(path, ms.current_month(), [_row(ID_A, 'Анна Смирнова', 111.0)])
        d = _login(_make_app(), 'anna', 'passpass').get('/api/me').get_json()
        assert d['identity']['status'] == 'ambiguous_link'
        assert d['money'] is None
        assert 'anna2' in d['identity']['message']
    finally:
        restore_reg()
        restore_dir()


def test_api_me_ok_path_returns_my_row():
    mgr = _fresh_manager()
    uid = mgr.create_user('anna', 'Анна Смирнова', 'passpass')
    mgr.set_employee_link(uid, ID_A)
    path, restore_dir = _tmp_snapshot_dir()
    restore_reg = _fake_registry([(ID_A, 'Анна Смирнова')])
    try:
        month = ms.current_month()
        _write_snapshot(path, month, [_row(ID_A, 'Анна Смирнова', 73290.0)])
        d = _login(_make_app(), 'anna', 'passpass').get('/api/me').get_json()
        assert d['identity']['status'] == 'ok', d['identity']
        assert d['money']['total'] == 73290.0
        assert d['snapshot']['status'] == 'ok'
        assert d['snapshot']['refreshed_at'] == '2026-08-13T07:42:11+03:00'
        assert d['month'] == month
        assert month in d['months_available']
        assert d['notes']['accrued_to_date']
    finally:
        restore_reg()
        restore_dir()


# --- устойчивость к чужим и старым файлам ---

def test_api_me_tolerates_old_snapshot_file():
    """Файл без новых необязательных ключей -> 200 с дефолтами, без KeyError.

    У людей неделями живут открытые вкладки, а на томе — файл предыдущей
    версии: чтение обязано быть терпимым к отсутствию полей.
    """
    mgr = _fresh_manager()
    uid = mgr.create_user('anna', 'Анна Смирнова', 'passpass')
    mgr.set_employee_link(uid, ID_A)
    path, restore_dir = _tmp_snapshot_dir()
    restore_reg = _fake_registry([(ID_A, 'Анна Смирнова')])
    try:
        month = ms.current_month()
        skinny = {
            '_schema': SNAPSHOT_SCHEMA,
            '_refreshed_at': '2026-08-13T07:42:11+03:00',
            'employees': {ID_A: {'employee_id': ID_A, 'money': {'total': 5.0}}},
        }
        with open(os.path.join(path, f'month__{month}.json'), 'w', encoding='utf-8') as f:
            json.dump(skinny, f, ensure_ascii=False)
        d = _login(_make_app(), 'anna', 'passpass').get('/api/me').get_json()
        assert d['identity']['status'] == 'ok', d['identity']
        assert d['money']['total'] == 5.0
        assert d['norms'] == {'shift_norm': 15, 'hours_norm': 113}   # дефолт с бэка
        assert d['metrics'] is None and d['kpi'] is None             # полей нет — не выдумываем
    finally:
        restore_reg()
        restore_dir()


def test_api_me_schema_mismatch_hides_money():
    mgr = _fresh_manager()
    uid = mgr.create_user('anna', 'Анна Смирнова', 'passpass')
    mgr.set_employee_link(uid, ID_A)
    path, restore_dir = _tmp_snapshot_dir()
    restore_reg = _fake_registry([(ID_A, 'Анна Смирнова')])
    try:
        _write_snapshot(path, ms.current_month(), [_row(ID_A, 'Анна Смирнова', 111.0)],
                        schema=SNAPSHOT_SCHEMA + 1)
        d = _login(_make_app(), 'anna', 'passpass').get('/api/me').get_json()
        assert d['snapshot']['status'] == 'schema_mismatch'
        assert d['identity']['status'] == 'schema_mismatch'
        assert d['money'] is None
    finally:
        restore_reg()
        restore_dir()


def test_api_me_broken_json_is_not_500():
    mgr = _fresh_manager()
    uid = mgr.create_user('anna', 'Анна Смирнова', 'passpass')
    mgr.set_employee_link(uid, ID_A)
    path, restore_dir = _tmp_snapshot_dir()
    restore_reg = _fake_registry([(ID_A, 'Анна Смирнова')])
    try:
        with open(os.path.join(path, f'month__{ms.current_month()}.json'), 'w',
                  encoding='utf-8') as f:
            f.write('{"_schema": 1, "employees": {oops')
        r = _login(_make_app(), 'anna', 'passpass').get('/api/me')
        assert r.status_code == 200
        d = r.get_json()
        assert d['snapshot']['status'] == 'missing'
        assert d['money'] is None
    finally:
        restore_reg()
        restore_dir()


# --- кнопка «Обновить»: лок, кулдаун, аудит ---

def _no_iiko():
    """Убрать креды iiko и вернуть восстановитель."""
    import config
    saved = (config.IIKO_LOGIN, config.IIKO_PASSWORD)
    config.IIKO_LOGIN, config.IIKO_PASSWORD = '', ''

    def restore():
        config.IIKO_LOGIN, config.IIKO_PASSWORD = saved
    return restore


def _with_iiko():
    import config
    saved = (config.IIKO_LOGIN, config.IIKO_PASSWORD)
    config.IIKO_LOGIN, config.IIKO_PASSWORD = 'test-login', 'test-pass'

    def restore():
        config.IIKO_LOGIN, config.IIKO_PASSWORD = saved
    return restore


def _fake_build():
    """Подменить сборку на мгновенную заглушку. Возвращает (счётчик, восстановитель)."""
    calls = []
    orig = ms.build_month
    ms.build_month = lambda app, month, tag='x': (
        calls.append((month, tag))
        or {'month': month, 'written': True, 'employees': 1,
            'source_status': {}, 'error': None, 'seconds': 0.0})

    def restore():
        ms.build_month = orig
    return calls, restore


def test_refresh_requires_iiko_config():
    """Без кредов iiko — 503, и лок не создаётся (кулдаун не съеден)."""
    mgr = _fresh_manager()
    mgr.create_user('usr', 'U', 'passpass')
    path, restore_dir = _tmp_snapshot_dir()
    restore_iiko = _no_iiko()
    try:
        c = _login(_make_app(), 'usr', 'passpass')
        r = c.post('/api/me/refresh')
        assert r.status_code == 503, r.status_code
        assert not os.path.exists(ms.REFRESH_LOCK)
    finally:
        restore_iiko()
        restore_dir()


def test_refresh_starts_and_is_audited():
    mgr = _fresh_manager()
    mgr.create_user('anna', 'Анна', 'passpass')
    path, restore_dir = _tmp_snapshot_dir()
    restore_iiko = _with_iiko()
    calls, restore_build = _fake_build()
    audited = []
    orig_audit = rm._audit
    rm._audit = lambda action, summary: audited.append((action, summary))
    try:
        ms._release_refresh_lock()
        c = _login(_make_app(), 'anna', 'passpass')
        r = c.post('/api/me/refresh')
        assert r.status_code == 202, (r.status_code, r.get_json())
        assert r.get_json()['started'] is True
        _wait_idle()
        assert calls, 'сборка не вызвана'
        assert audited and audited[0][0] == 'me_snapshot_refresh'
        # лок снят в finally
        assert not os.path.exists(ms.REFRESH_LOCK)
    finally:
        rm._audit = orig_audit
        restore_build()
        restore_iiko()
        ms.write_refresh_state(last_started_at=None)
        restore_dir()


def test_refresh_cooldown_409_with_retry_after():
    """Повторное нажатие в пределах кулдауна: 409 и сборка НЕ вызвана."""
    mgr = _fresh_manager()
    mgr.create_user('anna', 'Анна', 'passpass')
    path, restore_dir = _tmp_snapshot_dir()
    restore_iiko = _with_iiko()
    calls, restore_build = _fake_build()
    try:
        from core.msk_time import now as msk_now
        ms._release_refresh_lock()
        ms.write_refresh_state(last_started_at=msk_now().isoformat(timespec='seconds'))
        c = _login(_make_app(), 'anna', 'passpass')
        r = c.post('/api/me/refresh')
        assert r.status_code == 409, r.status_code
        d = r.get_json()
        assert d['reason'] == 'cooldown' and d['retry_after_sec'] > 0
        assert not calls, 'при кулдауне сборка запускаться не должна'
    finally:
        restore_build()
        restore_iiko()
        restore_dir()


def test_refresh_cross_worker_lock_409_and_stale_reclaim():
    """Живой лок другого воркера -> 409; брошенный (старый mtime) -> снимается."""
    mgr = _fresh_manager()
    mgr.create_user('anna', 'Анна', 'passpass')
    path, restore_dir = _tmp_snapshot_dir()
    restore_iiko = _with_iiko()
    calls, restore_build = _fake_build()
    try:
        ms.write_refresh_state(last_started_at=None)
        os.makedirs(ms.LOCK_DIR, exist_ok=True)
        with open(ms.REFRESH_LOCK, 'w') as f:
            f.write('99999\n')            # как будто прогон в другом воркере
        c = _login(_make_app(), 'anna', 'passpass')
        r = c.post('/api/me/refresh')
        assert r.status_code == 409, r.status_code
        assert r.get_json()['reason'] == 'already_running'
        assert not calls

        # состарим лок за порог — он должен быть снят, прогон стартует
        old = time.time() - ms.STALE_LOCK_SEC - 60
        os.utime(ms.REFRESH_LOCK, (old, old))
        r = c.post('/api/me/refresh')
        assert r.status_code == 202, (r.status_code, r.get_json())
        _wait_idle()
        assert calls
    finally:
        restore_build()
        restore_iiko()
        ms._release_refresh_lock()
        ms.write_refresh_state(last_started_at=None)
        restore_dir()


def test_refresh_status_reports_months_and_cooldown():
    mgr = _fresh_manager()
    mgr.create_user('anna', 'Анна', 'passpass')
    path, restore_dir = _tmp_snapshot_dir()
    try:
        month = ms.current_month()
        _write_snapshot(path, month, [_row(ID_A, 'Анна', 1.0)])
        c = _login(_make_app(), 'anna', 'passpass')
        d = c.get('/api/me/refresh-status').get_json()
        assert month in d['months']
        assert d['months'][month]['refreshed_at'] == '2026-08-13T07:42:11+03:00'
        assert 'cooldown_left_sec' in d and 'progress' in d
    finally:
        restore_dir()


def _wait_idle(timeout=5.0):
    """Дождаться завершения фонового прогона (поток demon, тест не должен гадать)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not ms.get_progress().get('running'):
            return True
        time.sleep(0.05)
    raise AssertionError('fonovy progon ne zavershilsya')


def test_available_months_always_has_current():
    path, restore_dir = _tmp_snapshot_dir()
    try:
        assert ms.available_months() == [ms.current_month()]
        _write_snapshot(path, '2026-07', [])
        months = ms.available_months()
        assert months[0] == ms.current_month()
        assert '2026-07' in months
    finally:
        restore_dir()


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

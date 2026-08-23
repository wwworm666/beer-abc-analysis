"""
Тесты приёмки бара («Как принял бар?») — core/bar_acceptance.py,
core/bar_photo_store.py, routes/cleanliness.py, схема v11 shifts.db.

Что проверяем, в порядке важности:
  * ЧУЖУЮ смену отметить нельзя — ни обычному аккаунту, ни администратору:
    ценность журнала в том, что каждая строка это свидетельство от первого лица;
  * отвечает только ОТКРЫВАЮЩАЯ смена точки, и правило то же самое, по которому
    кассовый регистр выбирает ответственного за кассу;
  * окно «только в день смены» держит сервер, а не фронт;
  * «Плохо» без фото не проходит, «Чисто» с текстом или фото — тоже;
  * имя файла фото — единственный допуск к диску (обход каталога невозможен);
  * пробел `not_marked` появляется только у прошедших дней после даты отсечки;
  * миграция v10 -> v11 аддитивна и данные не теряет.
"""

import io
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

import pytest  # noqa: E402
from flask import Flask  # noqa: E402

import core.auth_manager as am  # noqa: E402
import core.bar_photo_store as photos  # noqa: E402
import routes.cleanliness as rc  # noqa: E402
from core.auth_guard import init_auth  # noqa: E402
from core.bar_acceptance import (NOTE_MAX_LEN, PROBLEM_NOT_MARKED, STATUS_BAD,
                                 STATUS_CLEAN, STATUS_ISSUES, build_journal,
                                 can_answer, normalize_note, validate)  # noqa: E402
from core.cash_register import opening_shifts  # noqa: E402
from core.shifts_manager import ShiftsManager  # noqa: E402
from routes.auth import auth_bp  # noqa: E402
from routes.cleanliness import cleanliness_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'templates')
STATIC = os.path.join(ROOT, 'static')

TODAY = '2026-08-20'
YESTERDAY = '2026-08-19'
RULE_FROM = '2026-08-01'

ID_ME = 'guid-me'
ID_OTHER = 'guid-other'

# Самый маленький валидный JPEG-заголовок: сигнатуру проверяет bar_photo_store,
# декодировать картинку никто не пытается (Pillow в образе нет).
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 64
NOT_JPEG = b'PNG\r\n' + b'\x00' * 64


# ==================== Чистые правила ====================

def test_normalize_note_makes_one_line():
    assert normalize_note('  краны   не\n промыты  ') == 'краны не промыты'
    assert normalize_note(None) == ''


def test_clean_requires_nothing_and_rejects_extras():
    ok, err, out = validate(STATUS_CLEAN, '', False)
    assert ok and out == {'status': STATUS_CLEAN, 'note': None}
    # «Чисто» с комментарием — это уже «Замечания», иначе смысл ответа теряется
    assert validate(STATUS_CLEAN, 'вообще-то липкая стойка', False)[0] is False
    assert validate(STATUS_CLEAN, '', True)[0] is False


def test_issues_requires_note_photo_optional():
    assert validate(STATUS_ISSUES, 'стойка липкая', False)[0] is True
    assert validate(STATUS_ISSUES, 'стойка липкая', True)[0] is True
    assert validate(STATUS_ISSUES, '   ', False)[0] is False


def test_bad_requires_note_and_photo():
    assert validate(STATUS_BAD, 'краны не промыты', False)[0] is False
    assert validate(STATUS_BAD, 'краны не промыты', True)[0] is True
    assert validate(STATUS_BAD, '', True)[0] is False


def test_note_length_capped():
    assert validate(STATUS_ISSUES, 'а' * NOTE_MAX_LEN, False)[0] is True
    assert validate(STATUS_ISSUES, 'а' * (NOTE_MAX_LEN + 1), False)[0] is False


def test_unknown_status_rejected():
    assert validate('perfect', '', False)[0] is False
    assert validate(None, '', False)[0] is False


def test_answer_window_is_the_shift_day_only():
    assert can_answer(TODAY, TODAY)[0] is True
    assert can_answer(YESTERDAY, TODAY)[0] is False      # вчера уже закрыто
    assert can_answer('2026-08-21', TODAY)[0] is False   # завтра ещё рано
    assert can_answer(None, TODAY)[0] is False


# ==================== Кто открывающий ====================

def _shift(sid, date, loc, name, emp_id, start, role='бармен'):
    return {'id': sid, 'date': date, 'location_id': loc, 'location_name': 'Точка',
            'location_short': 'Т' + str(loc), 'employee_name': name,
            'employee_id': emp_id, 'start_time': start, 'role_name': role}


def test_opening_shift_is_first_day_shift():
    """Открывающая — самая ранняя дневная. Вечерняя не участвует, второй дневной
    бармен вопроса не получает: одна приёмка на (точку, день)."""
    shifts = [
        _shift(1, TODAY, 1, 'Второй Дневной', 'g2', '14:00'),
        _shift(2, TODAY, 1, 'Открывающий', ID_ME, '10:00'),
        _shift(3, TODAY, 1, 'Вечерний', 'g3', '18:00', role='второй бармен'),
    ]
    assert opening_shifts(shifts) == {(1, TODAY): 2}


def test_opening_shift_tie_broken_by_id():
    """Одинаковое время старта -> порядок создания. Иначе «кто отвечает»
    зависело бы от порядка строк в выборке."""
    shifts = [_shift(7, TODAY, 1, 'Б', 'g1', '10:00'),
              _shift(3, TODAY, 1, 'А', 'g2', '10:00')]
    assert opening_shifts(shifts) == {(1, TODAY): 3}


# ==================== Журнал ====================

def _acc(shift_id, status, note=None, photo=None, created='2026-08-19T09:12:00',
         updated=None):
    return {'shift_id': shift_id, 'status': status, 'note': note, 'photo': photo,
            'created_at': created, 'updated_at': updated or created,
            'author_name': 'Бармен'}


def test_journal_one_row_per_opening_shift():
    shifts = [
        _shift(1, YESTERDAY, 1, 'Открывающий', ID_ME, '10:00'),
        _shift(2, YESTERDAY, 1, 'Вечерний', 'g3', '18:00', role='второй бармен'),
        _shift(3, YESTERDAY, 2, 'Другая точка', ID_OTHER, '11:00'),
    ]
    j = build_journal(shifts, [], today=TODAY, rule_from=RULE_FROM)
    assert [r['shift_id'] for r in j['rows']] == [1, 3]
    assert j['totals']['shifts'] == 2
    assert len(j['locations']) == 2


def test_journal_marks_gap_only_for_past_days_after_rule():
    shifts = [
        _shift(1, '2026-07-15', 1, 'До правила', ID_ME, '10:00'),   # до RULE_FROM
        _shift(2, YESTERDAY, 1, 'Вчера', ID_ME, '10:00'),           # пробел
        _shift(3, TODAY, 1, 'Сегодня', ID_ME, '10:00'),             # ещё успеет
    ]
    j = build_journal(shifts, [], today=TODAY, rule_from=RULE_FROM)
    gaps = {r['shift_id']: PROBLEM_NOT_MARKED in r['problems'] for r in j['rows']}
    assert gaps == {1: False, 2: True, 3: False}
    assert j['totals'][PROBLEM_NOT_MARKED] == 1


def test_journal_counts_answers_and_marks_edited():
    shifts = [_shift(1, YESTERDAY, 1, 'А', ID_ME, '10:00'),
              _shift(2, YESTERDAY, 2, 'Б', ID_OTHER, '10:00')]
    accs = [_acc(1, STATUS_CLEAN),
            _acc(2, STATUS_BAD, 'краны не промыты', 'p.jpg',
                 created='2026-08-19T09:00:00', updated='2026-08-19T09:30:00')]
    j = build_journal(shifts, accs, today=TODAY, rule_from=RULE_FROM)
    by_id = {r['shift_id']: r for r in j['rows']}
    assert by_id[1]['status'] == STATUS_CLEAN and by_id[1]['edited'] is False
    assert by_id[2]['edited'] is True and by_id[2]['photo'] == 'p.jpg'
    assert j['totals']['answered'] == 2
    assert j['totals']['with_photo'] == 1
    assert j['totals'][PROBLEM_NOT_MARKED] == 0
    # «Плохо» — не проблема журнала, а его нормальная работа
    assert by_id[2]['problems'] == []


# ==================== Хранение фото ====================

def test_photo_name_is_the_only_way_to_the_disk():
    assert photos.is_valid_name('2026-08-20_17_deadbeef.jpg')
    for bad in ('../../etc/passwd', '2026-08-20_17_deadbeef.jpg/../x',
                'x.jpg', '2026-08-20_17_DEADBEEF.jpg', '', None,
                '2026-08-20_17_deadbeef.png'):
        assert not photos.is_valid_name(bad), bad
        assert photos.photo_path(bad) is None


def test_photo_check_rejects_non_jpeg_and_oversize():
    assert photos.check(JPEG) == (True, None)
    assert photos.check(NOT_JPEG)[0] is False
    assert photos.check(b'')[0] is False
    assert photos.check(JPEG + b'\x00' * photos.MAX_PHOTO_BYTES)[0] is False


def test_photo_save_and_delete(tmp_path):
    orig = photos.photo_dir
    photos.photo_dir = lambda: str(tmp_path)
    try:
        ok, name = photos.save(JPEG, '2026-08-20', 17)
        assert ok and photos.is_valid_name(name)
        assert photos.exists(name)
        # Временного файла после записи не остаётся
        assert [f for f in os.listdir(str(tmp_path)) if f.endswith('.tmp')] == []
        assert photos.delete(name) is True
        assert not photos.exists(name)
    finally:
        photos.photo_dir = orig


# ==================== Схема v11 ====================

def test_fresh_db_has_acceptance_table(tmp_path):
    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    with sqlite3.connect(mgr.db_path) as conn:
        assert (conn.execute('PRAGMA user_version').fetchone()[0]
                == ShiftsManager.SCHEMA_VERSION)
        cols = {r[1] for r in conn.execute('PRAGMA table_info(bar_acceptance)')}
    assert {'shift_id', 'status', 'note', 'photo', 'created_at', 'updated_at'} <= cols


def test_acceptance_upsert_keeps_created_at(tmp_path):
    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    loc, role = mgr.get_locations()[0], mgr.get_roles()[0]
    sid = mgr.create_shift(TODAY, 'Бармен', loc['id'], role['id'],
                           start_time='10:00', employee_id=ID_ME)
    first = mgr.set_bar_acceptance(
        sid, date=TODAY, location_id=loc['id'], employee_id=ID_ME,
        employee_name='Бармен', status=STATUS_ISSUES, note='пыль',
        photo=None, author_login='u', author_name='U')
    second = mgr.set_bar_acceptance(
        sid, date=TODAY, location_id=loc['id'], employee_id=ID_ME,
        employee_name='Бармен', status=STATUS_CLEAN, note=None,
        photo=None, author_login='u', author_name='U')
    assert second['created_at'] == first['created_at']   # первый ответ датирован своим временем
    assert second['updated_at'] != second['created_at']  # но видно, что переписан
    assert second['status'] == STATUS_CLEAN
    assert len(mgr.get_bar_acceptances_for_period(TODAY, TODAY)) == 1


def test_acceptance_timestamp_is_moscow(tmp_path):
    """Отметка ПОКАЗЫВАЕТСЯ («принял в 09:12»), а в прод-образе нет tzdata и
    наивное время там UTC. Значит смещение обязано быть в самой строке."""
    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    loc, role = mgr.get_locations()[0], mgr.get_roles()[0]
    sid = mgr.create_shift(TODAY, 'Бармен', loc['id'], role['id'],
                           start_time='10:00', employee_id=ID_ME)
    row = mgr.set_bar_acceptance(sid, date=TODAY, location_id=loc['id'],
                                 employee_id=ID_ME, employee_name='Бармен',
                                 status=STATUS_CLEAN, note=None, photo=None,
                                 author_login='u', author_name='U')
    assert row['created_at'].endswith('+03:00'), row['created_at']


def test_acceptance_dies_with_its_shift(tmp_path):
    """Смена удалена -> приёмка тоже: журнал строится по сменам, осиротевшая
    строка была бы невидима, но занимала бы место."""
    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    loc, role = mgr.get_locations()[0], mgr.get_roles()[0]
    sid = mgr.create_shift(TODAY, 'Бармен', loc['id'], role['id'],
                           start_time='10:00', employee_id=ID_ME)
    mgr.set_bar_acceptance(sid, date=TODAY, location_id=loc['id'], employee_id=ID_ME,
                           employee_name='Бармен', status=STATUS_CLEAN, note=None,
                           photo=None, author_login='u', author_name='U')
    mgr.delete_shift(sid)
    assert mgr.get_bar_acceptance(sid) is None


def test_v10_migration_preserves_shifts(tmp_path):
    """Миграция v10 -> v11 аддитивна: смены целы, таблица приёмок появилась."""
    db = str(tmp_path / 'shifts.db')
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, short_name TEXT NOT NULL, venue_key TEXT)''')
    cur.execute('''CREATE TABLE roles (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, short_name TEXT, color TEXT,
        sort_order INTEGER DEFAULT 0, rate_per_hour REAL NOT NULL DEFAULT 300)''')
    cur.execute('''CREATE TABLE shifts (id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, employee_name TEXT NOT NULL, location_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL, notes TEXT, start_time TEXT, fact_minutes INTEGER,
        employee_id TEXT, cash_expense_kop INTEGER, cash_expense_note TEXT,
        cash_collection_kop INTEGER, cash_end_kop INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute("INSERT INTO locations (name, short_name) VALUES ('Варшавская', 'Варш')")
    cur.execute("INSERT INTO roles (name, short_name, sort_order) VALUES ('бармен', 'Б', 1)")
    cur.execute("INSERT INTO shifts (date, employee_name, location_id, role_id, "
                "fact_minutes, cash_end_kop) VALUES ('2026-08-05', 'Старый', 1, 1, 600, 1534025)")
    cur.execute('PRAGMA user_version = 10')
    conn.commit()
    conn.close()

    mgr = ShiftsManager(db_path=db)   # триггерит миграцию v10 -> v11

    shifts = mgr.get_shifts_for_month(2026, 8)
    assert len(shifts) == 1
    assert shifts[0]['employee_name'] == 'Старый'
    assert shifts[0]['fact_minutes'] == 600
    assert shifts[0]['cash_end_kop'] == 1534025
    assert mgr.get_bar_acceptances_for_period('2026-08-01', '2026-08-31') == []


# ==================== Эндпоинты ====================

@pytest.fixture
def env(tmp_path):
    """Приложение + временные БД + временный каталог фото + фиксированное «сегодня»."""
    fd, auth_db = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(auth_db)
    auth = am.AuthManager(db_path=auth_db)
    am._auth_manager = auth

    shifts = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    photo_dir = tempfile.mkdtemp(prefix='bar_photos_')

    orig = (rc.shifts_mgr, rc._today, photos.photo_dir)
    rc.shifts_mgr = shifts
    rc._today = lambda: TODAY
    photos.photo_dir = lambda: photo_dir

    app = Flask('test_cleanliness', template_folder=TEMPLATES, static_folder=STATIC)
    app.jinja_env.globals['app_version'] = 'test'
    app.register_blueprint(auth_bp)
    app.register_blueprint(cleanliness_bp)
    init_auth(app)

    loc, role = shifts.get_locations()[0], shifts.get_roles()[0]
    yield {'app': app, 'auth': auth, 'shifts': shifts, 'photo_dir': photo_dir,
           'loc': loc, 'role': role}

    rc.shifts_mgr, rc._today, photos.photo_dir = orig
    shutil.rmtree(photo_dir, ignore_errors=True)
    try:
        os.unlink(auth_db)
    except OSError:
        pass


def _user(env, login, name, emp_id, is_admin=False):
    uid = env['auth'].create_user(login, name, 'passpass', is_admin=is_admin)
    if isinstance(uid, dict):
        uid = uid.get('id')
    if emp_id:
        env['auth'].set_employee_link(uid, emp_id)
    c = env['app'].test_client()
    r = c.post('/login', data={'login': login, 'password': 'passpass'})
    assert r.status_code in (200, 302), r.status_code
    return c


def _shift_row(env, date=TODAY, emp_id=ID_ME, name='Бармен', start='10:00',
               location_id=None):
    return env['shifts'].create_shift(
        date, name, location_id or env['loc']['id'], env['role']['id'],
        start_time=start, employee_id=emp_id)


def _post(client, shift_id, **fields):
    data = {k: v for k, v in fields.items() if v is not None}
    return client.post('/api/cleanliness/shift/' + str(shift_id),
                       data=data, content_type='multipart/form-data')


def _photo_field(content=JPEG):
    return (io.BytesIO(content), 'photo.jpg')


# --- гейт ---

def test_endpoints_require_login(env):
    c = env['app'].test_client()
    assert c.get('/api/cleanliness/today').status_code == 401
    assert c.get('/api/cleanliness/month/2026/8').status_code == 401
    assert c.post('/api/cleanliness/shift/1').status_code == 401


# --- «моя приёмка сегодня» ---

def test_today_without_link_is_a_status_not_an_error(env):
    c = _user(env, 'nolink', 'Без Привязки', None)
    r = c.get('/api/cleanliness/today')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'not_linked'
    assert r.get_json()['items'] == []


def test_today_returns_only_my_opening_shift(env):
    _shift_row(env, emp_id=ID_OTHER, name='Открывающий', start='09:00')
    mine = _shift_row(env, emp_id=ID_ME, name='Я', start='14:00')
    c = _user(env, 'me', 'Я', ID_ME)
    # я в этот день второй дневной — вопрос не мой
    assert c.get('/api/cleanliness/today').get_json()['status'] == 'no_shift'

    env['shifts'].delete_shift(mine)
    other_loc = env['shifts'].get_locations()[1]
    _shift_row(env, emp_id=ID_ME, name='Я', start='10:00', location_id=other_loc['id'])
    data = c.get('/api/cleanliness/today').get_json()
    assert data['status'] == 'ok'
    assert len(data['items']) == 1
    assert data['items'][0]['acceptance'] is None


def test_today_never_leaks_someone_elses_shift(env):
    """Идентификатор сотрудника в запросе не принимается: подставленные
    параметры игнорируются, ответ строится только по сессии."""
    _shift_row(env, emp_id=ID_OTHER, name='Чужой', start='10:00')
    c = _user(env, 'me', 'Я', ID_ME)
    r = c.get('/api/cleanliness/today?employee_id=' + ID_OTHER)
    assert r.get_json()['status'] == 'no_shift'


# --- запись ответа ---

def test_clean_answer_saved(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    r = _post(c, sid, status='clean')
    assert r.status_code == 200, r.get_json()
    acc = env['shifts'].get_bar_acceptance(sid)
    assert acc['status'] == 'clean' and acc['note'] is None and acc['photo'] is None
    assert acc['author_login'] == 'me'


def test_issues_requires_text(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    assert _post(c, sid, status='issues').status_code == 400
    r = _post(c, sid, status='issues', note='  стойка   липкая ')
    assert r.status_code == 200
    assert env['shifts'].get_bar_acceptance(sid)['note'] == 'стойка липкая'


def test_bad_without_photo_rejected_and_nothing_written(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    r = _post(c, sid, status='bad', note='краны не промыты')
    assert r.status_code == 400
    assert env['shifts'].get_bar_acceptance(sid) is None
    assert os.listdir(env['photo_dir']) == []


def test_bad_with_photo_saved(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    r = _post(c, sid, status='bad', note='краны не промыты', photo=_photo_field())
    assert r.status_code == 200, r.get_json()
    acc = env['shifts'].get_bar_acceptance(sid)
    assert acc['status'] == 'bad'
    assert photos.is_valid_name(acc['photo'])
    assert os.path.isfile(os.path.join(env['photo_dir'], acc['photo']))


def test_non_jpeg_rejected_without_writing_anything(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    r = _post(c, sid, status='bad', note='грязь',
              photo=(io.BytesIO(NOT_JPEG), 'photo.jpg'))
    assert r.status_code == 400
    assert env['shifts'].get_bar_acceptance(sid) is None
    assert os.listdir(env['photo_dir']) == []


def test_rewrite_drops_the_orphaned_photo(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    _post(c, sid, status='bad', note='грязь', photo=_photo_field())
    old = env['shifts'].get_bar_acceptance(sid)['photo']
    _post(c, sid, status='clean')
    assert env['shifts'].get_bar_acceptance(sid)['photo'] is None
    assert not os.path.exists(os.path.join(env['photo_dir'], old))


def test_keep_photo_lets_you_fix_a_typo(env):
    """Правка текста не должна требовать переснимать фотографию."""
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    _post(c, sid, status='bad', note='краны нипромыты', photo=_photo_field())
    old = env['shifts'].get_bar_acceptance(sid)['photo']
    r = _post(c, sid, status='bad', note='краны не промыты', keep_photo='1')
    assert r.status_code == 200, r.get_json()
    acc = env['shifts'].get_bar_acceptance(sid)
    assert acc['photo'] == old and acc['note'] == 'краны не промыты'
    assert os.path.isfile(os.path.join(env['photo_dir'], old))


# --- права и окно ---

def test_cannot_answer_for_someone_else(env):
    sid = _shift_row(env, emp_id=ID_OTHER, name='Коллега')
    c = _user(env, 'me', 'Я', ID_ME)
    r = _post(c, sid, status='clean')
    assert r.status_code == 403
    assert env['shifts'].get_bar_acceptance(sid) is None


def test_admin_cannot_answer_for_someone_else_either(env):
    """У администратора исключения НЕТ: каждая строка журнала — свидетельство
    от первого лица, иначе журнал вырождается в пересказ."""
    sid = _shift_row(env, emp_id=ID_OTHER, name='Коллега')
    c = _user(env, 'boss', 'Владелец', 'guid-boss', is_admin=True)
    assert _post(c, sid, status='clean').status_code == 403


def test_unlinked_account_cannot_answer(env):
    sid = _shift_row(env, emp_id=None, name='Безымянный')
    c = _user(env, 'nolink', 'Без Привязки', None)
    assert _post(c, sid, status='clean').status_code == 403


def test_cannot_answer_for_another_day(env):
    past = _shift_row(env, date=YESTERDAY)
    future = _shift_row(env, date='2026-08-21')
    c = _user(env, 'me', 'Я', ID_ME)
    assert _post(c, past, status='clean').status_code == 403
    assert _post(c, future, status='clean').status_code == 403


def test_only_opening_shift_can_answer(env):
    _shift_row(env, emp_id=ID_OTHER, name='Открывающий', start='09:00')
    mine = _shift_row(env, emp_id=ID_ME, name='Я', start='14:00')
    c = _user(env, 'me', 'Я', ID_ME)
    r = _post(c, mine, status='clean')
    assert r.status_code == 400
    assert 'открывающая' in (r.get_json().get('error') or '').lower()


def test_missing_shift_is_404(env):
    c = _user(env, 'me', 'Я', ID_ME)
    assert _post(c, 999999, status='clean').status_code == 404


# --- журнал и фото ---

def test_month_journal_lists_rows(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    _post(c, sid, status='issues', note='пыль на полке')
    data = c.get('/api/cleanliness/month/2026/8').get_json()
    assert data['totals']['answered'] == 1
    assert data['rows'][0]['note'] == 'пыль на полке'
    assert data['rows'][0]['status_label'] == 'Замечания'
    assert data['status_labels']['bad'] == 'Плохо'


def test_month_validates_period(env):
    c = _user(env, 'me', 'Я', ID_ME)
    assert c.get('/api/cleanliness/month/2026/13').status_code == 400
    assert c.get('/api/cleanliness/month/1999/5').status_code == 400


def test_photo_route_rejects_traversal_and_unknown(env):
    c = _user(env, 'me', 'Я', ID_ME)
    assert c.get('/api/cleanliness/photo/..%2F..%2Fapp.py').status_code == 404
    assert c.get('/api/cleanliness/photo/whatever.jpg').status_code == 404
    assert c.get('/api/cleanliness/photo/2026-08-20_1_deadbeef.jpg').status_code == 404


def test_photo_route_serves_the_saved_file(env):
    sid = _shift_row(env)
    c = _user(env, 'me', 'Я', ID_ME)
    _post(c, sid, status='bad', note='грязь', photo=_photo_field())
    name = env['shifts'].get_bar_acceptance(sid)['photo']
    r = c.get('/api/cleanliness/photo/' + name)
    assert r.status_code == 200
    assert r.mimetype == 'image/jpeg'
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.data.startswith(b'\xff\xd8\xff')


def test_page_renders(env):
    c = _user(env, 'me', 'Я', ID_ME)
    assert c.get('/cleanliness').status_code == 200


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))

"""Тесты подписчиков гостевого бота (core/guest_subscribers.py). Сети нет.

Базы — во временной папке: guest_subscribers.db и маленькая витрина guests.db (та же
схема, что у core/guest_store). Часы подменяются (детерминированно).
Что проверяется:
- канон телефона совпадает с guest_id витрины (normalize_guest_id), в том числе лишняя 7;
- выбор баров: проверка, порядок, «все четыре = все бары», маска кнопок, переключение;
- согласие: запись версии и времени, повторное «Согласен» его не переписывает, после
  отписки — новое согласие;
- отписка стирает телефон и связку с гостем; блокировка и разблокировка;
- телефон — только у подписанного; связка с гостем по guest_id, guests.phone, псевдониму;
- сегменты bot_all / bot_bar / bot_recent_30 / bot_lapsed_60 на границах 29/30 и 59/60
  дней, фильтр бара, заблокированные и отписавшиеся не попадают, без телефона — не в
  сегментах по визитам;
- витрины нет или она битая — сегменты по визитам пустые, файл не создаётся;
- stats, API модуля для отправителя, ошибки аргументов;
- сегменты совпадают с аудиториями контент-плана.
"""
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import guest_subscribers as gs  # noqa: E402
from core import msk_time  # noqa: E402
from core.guest_store import GuestStore  # noqa: E402
from core.guest_sync import normalize_guest_id  # noqa: E402

TODAY = date(2026, 9, 28)


class Clock:
    """Подменяемые часы (aware МСК)."""

    def __init__(self, value=None):
        self.value = value or datetime(2026, 9, 28, 12, 0, tzinfo=msk_time.MOSCOW_TZ)

    def __call__(self):
        return self.value

    def move(self, **delta):
        self.value = self.value + timedelta(**delta)


def _guests_db(folder, guests=(), aliases=()):
    """Витрина гостей с нужными строками: guests — (guest_id, phone, last_visit_date)."""
    path = os.path.join(str(folder), 'guests.db')
    GuestStore(path)      # схема — как у настоящей витрины
    conn = sqlite3.connect(path)
    try:
        conn.executemany("INSERT INTO guests (guest_id, phone, last_visit_date, updated_at) "
                         "VALUES (?, ?, ?, '2026-09-28T05:10:00')", list(guests))
        conn.executemany('INSERT INTO guest_aliases (alias, guest_id) VALUES (?, ?)', list(aliases))
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return gs.SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=str(tmp_path / 'no_guests.db'),
                              clock=clock)


def _days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


# ----------------------------------------------------------------- чистые функции

def test_phone_canon_matches_guest_base():
    for raw in ('+7 (999) 123-45-67', '89991234567', '79991234567', '9991234567', '779991234567',
                '+79991234567'):
        assert gs.canon_phone(raw) == '79991234567' == normalize_guest_id(''.join(c for c in raw if c.isdigit()))
    assert gs.canon_phone('12345') == '' and gs.canon_phone(None) == '' and gs.canon_phone('abc') == ''
    assert gs.phone_display('79991234567') == '+79991234567' and gs.phone_display('') == ''


def test_bars_normalize_mask_toggle():
    assert gs.normalize_bars(None) == [] and gs.normalize_bars([]) == []
    assert gs.normalize_bars(['varshavskaya', 'bolshoy', 'bolshoy']) == ['bolshoy', 'varshavskaya']
    assert gs.normalize_bars(list(gs.BAR_KEYS)) == []                 # все четыре = все бары
    with pytest.raises(ValueError):
        gs.normalize_bars(['nope'])
    with pytest.raises(ValueError):
        gs.normalize_bars('bolshoy')
    assert gs.bars_to_mask([]) == 0 and gs.bars_to_mask(['ligovskiy', 'varshavskaya']) == 0b1010
    assert gs.mask_to_bars(0b1010) == ['ligovskiy', 'varshavskaya'] and gs.mask_to_bars(15) == []
    for bad in (-1, 16, 'x', '1e1', True):
        with pytest.raises(ValueError):
            gs.mask_to_bars(bad)
    assert gs.toggle_bar([], 'ligovskiy') == ['ligovskiy']
    assert gs.toggle_bar(['ligovskiy'], 'ligovskiy') == []           # снят последний -> все бары
    assert gs.toggle_bar(['bolshoy', 'ligovskiy', 'kremenchugskaya'], 'varshavskaya') == []
    assert gs.bars_label([]) == 'все бары' and gs.bars_label(['varshavskaya', 'bolshoy']) == 'Большой пр. В.О, Варшавская'
    assert gs.wants_bar([], 'bolshoy') and gs.wants_bar(['bolshoy'], 'bolshoy') and not gs.wants_bar(['bolshoy'], 'ligovskiy')


def test_visit_boundaries_match_docstring_examples():
    # Докстринг: сегодня 28.09 — «за 30 дней» визиты с 30.08 по 28.09; «60 и больше» — 30.07 и раньше.
    assert gs.visit_matches('bot_recent_30', '2026-09-28', TODAY)
    assert gs.visit_matches('bot_recent_30', '2026-08-30', TODAY)
    assert not gs.visit_matches('bot_recent_30', '2026-08-29', TODAY)
    assert not gs.visit_matches('bot_lapsed_60', '2026-07-31', TODAY)
    assert gs.visit_matches('bot_lapsed_60', '2026-07-30', TODAY)
    assert gs.visit_matches('bot_recent_30', '2026-09-29', TODAY)     # дата «из будущего» — недавний
    assert not gs.visit_matches('bot_recent_30', None, TODAY) and not gs.visit_matches('bot_lapsed_60', 'x', TODAY)


def test_segments_match_content_plan_audiences():
    from core.content_plan import AUDIENCES
    assert tuple(a['key'] for a in AUDIENCES) == gs.SEGMENTS
    assert set(gs.SEGMENT_RULES) == set(gs.SEGMENTS)


def test_consent_text_is_versioned_and_plain():
    text = gs.CONSENT_TEXTS[gs.CONSENT_VERSION]
    assert text == gs.CONSENT_TEXT
    assert '«Согласен»' in text and '/stop' in text and 'телефон' in text
    assert not any(ord(ch) > 0xFFFF for ch in text) and '<' not in text


# ----------------------------------------------------------------- хранилище

def test_schema_and_wal(store):
    conn = sqlite3.connect(store.db_path)
    try:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == gs.SCHEMA_VERSION
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        cols = {r[1] for r in conn.execute('PRAGMA table_info(subscribers)')}
    finally:
        conn.close()
    assert cols == {'chat_id', 'user_id', 'username', 'first_name', 'bars', 'subscribed', 'consent_at',
                    'consent_text_version', 'unsubscribed_at', 'blocked_at', 'phone', 'guest_id',
                    'created_at', 'updated_at', 'last_seen_at'}


def test_subscribe_records_consent_once(store, clock):
    row = store.subscribe(501, user_id=501, username='@anna', first_name='Анна')
    assert row['subscribed'] is True and row['bars'] == [] and row['username'] == 'anna'
    assert row['consent_at'] == '2026-09-28T12:00:00' and row['consent_text_version'] == gs.CONSENT_VERSION
    clock.move(minutes=5)
    again = store.subscribe(501, user_id=501, username=None, first_name='Анна')
    assert again['consent_at'] == '2026-09-28T12:00:00'               # согласие не переписано
    assert again['username'] is None and again['last_seen_at'] == '2026-09-28T12:05:00'
    assert store.is_subscribed(501) and not store.is_subscribed(502)
    with pytest.raises(ValueError):
        store.subscribe('abc')
    with pytest.raises(ValueError):
        store.subscribe(503, consent_version='1999-01-01')


def test_unsubscribe_clears_phone_and_resubscribe_is_new_consent(tmp_path, clock):
    guests = _guests_db(tmp_path, guests=[('79990000001', '79990000001', _days_ago(3))])
    s = gs.SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=guests, clock=clock)
    s.subscribe(501, first_name='Анна')
    assert s.set_bars(501, ['ligovskiy'])
    assert s.set_phone(501, '+7 999 000-00-01') == {'phone': '79990000001', 'guest_id': '79990000001',
                                                    'last_visit_date': _days_ago(3)}
    clock.move(hours=1)
    assert s.unsubscribe(501) is True and s.unsubscribe(501) is False
    row = s.get(501)
    assert row['subscribed'] is False and row['phone'] is None and row['guest_id'] is None
    assert row['unsubscribed_at'] == '2026-09-28T13:00:00' and row['bars'] == ['ligovskiy']
    assert row['consent_at'] == '2026-09-28T12:00:00'                # запись о прежнем согласии осталась
    clock.move(hours=1)
    back = s.subscribe(501, first_name='Анна')
    assert back['subscribed'] and back['consent_at'] == '2026-09-28T14:00:00' and back['unsubscribed_at'] is None
    assert back['bars'] == ['ligovskiy']                              # прежний выбор предлагается снова


def test_bars_and_phone_only_for_subscribed(store):
    assert store.set_bars(700, ['bolshoy']) is False                  # строки нет — не создаём
    assert store.set_phone(700, '+79990000001') is None
    assert store.get(700) is None
    store.subscribe(700, first_name='Олег')
    with pytest.raises(ValueError):
        store.set_bars(700, ['nope'])
    with pytest.raises(ValueError):
        store.set_phone(700, '123')
    assert store.set_bars(700, list(gs.BAR_KEYS)) and store.get(700)['bars'] == []
    res = store.set_phone(700, '89990000001')
    assert res == {'phone': '79990000001', 'guest_id': None, 'last_visit_date': None}   # витрины нет


def test_blocked_and_touch(store, clock):
    store.subscribe(801, first_name='Ира')
    assert store.mark_blocked(999) is False and store.get(999) is None   # чужих строк не создаём
    assert store.mark_blocked(801) is True and store.mark_blocked(801) is False
    assert store.recipients('bot_all') == [] and store.stats()['blocked'] == 1
    assert store.touch(801, user_id=801, username='ira', first_name='Ира') is True
    assert store.get(801)['blocked_at'] is None and store.get(801)['username'] == 'ira'
    assert [r['chat_id'] for r in store.recipients('bot_all')] == [801]
    store.mark_blocked(801)
    assert store.mark_unblocked(801) is True and store.mark_unblocked(801) is False
    assert store.touch(12345) is False


def test_guest_link_by_id_phone_and_alias(tmp_path, clock):
    guests = _guests_db(tmp_path, guests=[
        ('79990000001', '79990000001', '2026-09-01'),       # guest_id = телефон
        ('100777', '79990000002', '2026-08-01'),            # гость по пластиковой карте, телефон в поле phone
        ('100888', '79990000002', '2026-09-10'),            # тот же телефон, визит позже -> он
        ('79990000009', '79990000009', '2026-05-05'),
    ], aliases=[('79990000003', '79990000009')])
    s = gs.SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=guests, clock=clock)
    assert s.find_guest('+7 999 000 00 01') == {'guest_id': '79990000001', 'last_visit_date': '2026-09-01'}
    assert s.find_guest('8 999 000 00 02') == {'guest_id': '100888', 'last_visit_date': '2026-09-10'}
    assert s.find_guest('79990000003') == {'guest_id': '79990000009', 'last_visit_date': '2026-05-05'}
    assert s.find_guest('79990000004') is None and s.find_guest('') is None


def _population(tmp_path, clock):
    """Подписчики с визитами на границах сегментов (сегодня 28.09.2026)."""
    guests = _guests_db(tmp_path, guests=[
        ('79990000001', '79990000001', _days_ago(0)),
        ('79990000002', '79990000002', _days_ago(29)),
        ('79990000003', '79990000003', _days_ago(30)),
        ('79990000004', '79990000004', _days_ago(59)),
        ('79990000005', '79990000005', _days_ago(60)),
        ('100555', '79990000008', _days_ago(10)),            # найдётся по guests.phone
        ('79990000010', '79990000010', _days_ago(90)),       # найдётся по псевдониму
        ('79990000011', '79990000011', _days_ago(1)),        # заблокирует бота
        ('79990000012', '79990000012', _days_ago(1)),        # отпишется
    ], aliases=[('79990000009', '79990000010')])
    s = gs.SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=guests, clock=clock)
    plan = [  # chat_id, phone, bars
        (1, '79990000001', ['bolshoy']),
        (2, '79990000002', []),
        (3, '79990000003', ['ligovskiy']),
        (4, '79990000004', []),
        (5, '79990000005', ['bolshoy', 'ligovskiy']),
        (6, None, ['bolshoy']),                               # без телефона
        (7, '79990000007', []),                               # телефон есть, гостя нет
        (8, '79990000008', ['varshavskaya']),
        (9, '79990000009', []),
        (11, '79990000011', []),
        (12, '79990000012', []),
    ]
    for chat_id, phone, bars in plan:
        s.subscribe(chat_id, first_name='Гость %d' % chat_id)
        s.set_bars(chat_id, bars)
        if phone:
            s.set_phone(chat_id, phone)
    s.mark_blocked(11)
    s.unsubscribe(12)
    return s


def _ids(rows):
    return [r['chat_id'] for r in rows]


def test_segments(tmp_path, clock):
    s = _population(tmp_path, clock)
    assert _ids(s.recipients('bot_all')) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert _ids(s.recipients('bot_all', 'all')) == _ids(s.recipients('bot_all', '')) == _ids(s.recipients('bot_all'))
    assert _ids(s.recipients('bot_bar', 'bolshoy')) == [1, 2, 4, 5, 6, 7, 9]      # отметили бар или «Все бары»
    assert _ids(s.recipients('bot_bar', 'varshavskaya')) == [2, 4, 7, 8, 9]
    recent = s.recipients('bot_recent_30', today=TODAY)
    assert _ids(recent) == [1, 2, 8]
    assert {r['chat_id']: r['last_visit_date'] for r in recent} == {1: _days_ago(0), 2: _days_ago(29),
                                                                    8: _days_ago(10)}
    assert _ids(s.recipients('bot_lapsed_60', today=TODAY)) == [5, 9]
    assert _ids(s.recipients('bot_recent_30', 'ligovskiy', today=TODAY)) == [2]  # бар сужает любой сегмент
    assert s.audience_size('bot_lapsed_60', 'bolshoy', today=TODAY) == 2
    assert s.recipients('bot_all')[0] == {'chat_id': 1, 'username': None, 'first_name': 'Гость 1',
                                          'bars': ['bolshoy'], 'guest_id': '79990000001',
                                          'last_visit_date': None}
    # «Сегодня» по часам хранилища (28.09 МСК)
    assert _ids(s.recipients('bot_recent_30')) == [1, 2, 8]


def test_first_purchase_after_subscription_is_seen(tmp_path, clock):
    path = _guests_db(tmp_path)
    s = gs.SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=path, clock=clock)
    s.subscribe(1, first_name='А')
    assert s.set_phone(1, '79990000001')['guest_id'] is None
    assert s.recipients('bot_recent_30') == []
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO guests (guest_id, phone, last_visit_date, updated_at) "
                 "VALUES ('79990000001', '79990000001', '2026-09-27', 'x')")
    conn.commit()
    conn.close()
    assert _ids(s.recipients('bot_recent_30')) == [1]                 # гость ищется при каждом расчёте


def test_missing_or_broken_guest_base(tmp_path, clock):
    missing = str(tmp_path / 'absent' / 'guests.db')
    s = gs.SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=missing, clock=clock)
    s.subscribe(1, first_name='А')
    s.set_phone(1, '79990000001')
    assert s.recipients('bot_recent_30') == [] and s.recipients('bot_lapsed_60') == []
    assert not os.path.exists(missing)                                 # витрину не создаём
    broken = tmp_path / 'broken.db'
    broken.write_bytes(b'this is not a database' * 100)
    s2 = gs.SubscriberStore(str(tmp_path / 'subs2.db'), guests_db_path=str(broken), clock=clock)
    s2.subscribe(1, first_name='А')
    assert s2.set_phone(1, '79990000001')['guest_id'] is None
    assert s2.recipients('bot_lapsed_60') == []


def test_argument_errors(store):
    for bad in ('', 'bot', None, 'BOT_ALL'):
        with pytest.raises(ValueError):
            store.recipients(bad)
    with pytest.raises(ValueError):
        store.recipients('bot_bar')                                    # без бара
    with pytest.raises(ValueError):
        store.recipients('bot_bar', 'all')
    with pytest.raises(ValueError):
        store.audience_size('bot_all', 'nope')


def test_stats(tmp_path, clock):
    s = _population(tmp_path, clock)
    st = s.stats()
    assert st == {'total': 11, 'subscribed': 9, 'with_phone': 8, 'linked': 7, 'all_bars': 4,
                  'by_bar': {'bolshoy': 7, 'ligovskiy': 6, 'kremenchugskaya': 4, 'varshavskaya': 5},
                  'unsubscribed': 1, 'blocked': 1, 'consent_version': gs.CONSENT_VERSION}
    assert st['by_bar']['bolshoy'] == s.audience_size('bot_bar', 'bolshoy')
    assert set(gs.STATS_RULES) == set(st) - {'consent_version'}


def test_module_api_for_publisher(tmp_path, clock):
    previous = gs.set_store(None)
    try:
        s = gs.get_store(db_path=str(tmp_path / 'm.db'), guests_db_path=str(tmp_path / 'none.db'), clock=clock)
        assert gs.get_store() is s
        s.subscribe(42, first_name='Гость')
        assert gs.audience_size('bot_all') == 1 and _ids(gs.recipients('bot_all')) == [42]
        assert gs.mark_blocked(42) is True and gs.audience_size('bot_all') == 0
        assert gs.stats()['blocked'] == 1
    finally:
        gs.set_store(previous)


# ----------------------------------------------------------------- проверка 2026-09-28

def test_foreign_phone_kept_as_is_and_not_linked(tmp_path, clock):
    """П. 5: зарубежный номер не превращается в чужой +7 (армянский 37477123456 давал
    казахстанский +77477123456 и привязку к чужой карте гостя)."""
    cases = {
        '37477123456': '+37477123456',          # Армения без плюса
        '+375 29 123-45-67': '+375291234567',   # Беларусь
        '998901234567': '+998901234567',        # Узбекистан
        '380671234567': '+380671234567',        # Украина
        '+49 151 23456789': '+4915123456789',   # Германия
        '+84 912 345 678': '+84912345678',      # Вьетнам: 11 цифр с 8 — но с плюсом
    }
    for raw, canon in cases.items():
        assert gs.canon_phone(raw) == canon, raw
        assert not gs.is_russian_phone(canon) and gs.phone_display(canon) == canon
    # Российские формы — как канон витрины (normalize_guest_id).
    for raw in ('9991234567', '89991234567', '79991234567', '779991234567', '+7 999 123-45-67'):
        assert gs.canon_phone(raw) == '79991234567' and gs.is_russian_phone('79991234567'), raw
    # Контакт Telegram — всегда с кодом страны: «84912345678» — Вьетнам, не российская «8…».
    assert gs.canon_phone('84912345678', international=True) == '+84912345678'
    assert gs.canon_phone('79991234567', international=True) == '79991234567'
    assert gs.canon_phone('1234567') == '' and gs.canon_phone('1' * 16) == ''
    # Витрина: казахстанский гость с каноном 77477123456 — армянский номер к нему не привяжется.
    guests = _guests_db(tmp_path, guests=[('77477123456', '77477123456', _days_ago(3))])
    s = gs.SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=guests, clock=clock)
    s.subscribe(1, first_name='А')
    saved = s.set_phone(1, '37477123456', international=True)
    assert saved == {'phone': '+37477123456', 'guest_id': None, 'last_visit_date': None}
    assert s.find_guest('+37477123456') is None
    assert s.recipients('bot_recent_30') == [] and s.recipients('bot_lapsed_60') == []
    assert s.get(1)['phone'] == '+37477123456'


def test_touch_only_updates_subscribed(store):
    """П. 3: об отписавшемся новые данные (имя, ник, время) не копим."""
    store.subscribe(900, user_id=900, username='old', first_name='Старое')
    store.unsubscribe(900)
    before = store.get(900)
    assert store.touch(900, user_id=900, username='new', first_name='Новое') is False
    after = store.get(900)
    assert (after['username'], after['first_name'], after['last_seen_at']) == \
        (before['username'], before['first_name'], before['last_seen_at'])
    store.subscribe(900, first_name='Снова')
    assert store.touch(900, user_id=900, username='new', first_name='Новое') is True
    assert store.get(900)['username'] == 'new'


def test_dialog_state_in_database(tmp_path, clock):
    """П. 6: шаг диалога бота хранится в базе и переживает новый экземпляр хранилища
    (перезапуск воркера); чистка старых записей."""
    path = str(tmp_path / 'subs.db')
    s = gs.SubscriberStore(path, guests_db_path=str(tmp_path / 'none.db'), clock=clock)
    s.dialog_set(555, {'flow': 'review_text', 'bar': 'ligovskiy', 'rating': 2, 'prompt_message_id': 41}, 1000.5)
    again = gs.SubscriberStore(path, guests_db_path=str(tmp_path / 'none.db'), clock=clock)
    assert again.dialog_get(555) == ({'flow': 'review_text', 'bar': 'ligovskiy', 'rating': 2,
                                      'prompt_message_id': 41}, 1000.5)
    assert again.dialog_get(1) is None
    s.dialog_set(556, {'flow': 'sub_phone'}, 10.0)
    assert again.dialog_sweep(500.0) == 1 and again.dialog_get(556) is None and again.dialog_get(555)
    again.dialog_clear(555)
    assert s.dialog_get(555) is None


def test_schema_upgrade_from_v1(tmp_path, clock):
    """База версии 1 (без таблицы dialogs) обновляется до 2, подписчики сохраняются."""
    path = str(tmp_path / 'old.db')
    conn = sqlite3.connect(path)
    for sql in gs._SCHEMA_SQL:
        conn.execute(sql)
    conn.execute("INSERT INTO subscribers (chat_id, subscribed, bars, created_at, updated_at) "
                 "VALUES (7, 1, '[]', 'x', 'x')")
    conn.execute('PRAGMA user_version = 1')
    conn.commit()
    conn.close()
    s = gs.SubscriberStore(path, guests_db_path=str(tmp_path / 'none.db'), clock=clock)
    assert s.is_subscribed(7)
    s.dialog_set(7, {'flow': 'consent'}, 1.0)
    conn = sqlite3.connect(path)
    try:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
    finally:
        conn.close()


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль должен разбираться грамматикой 3.10 (без PEP 701 и т.п.)."""
    import ast
    src = open(gs.__file__, encoding='utf-8').read()
    ast.parse(src, feature_version=(3, 10))

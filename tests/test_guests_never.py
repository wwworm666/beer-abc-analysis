# -*- coding: utf-8 -*-
"""Тесты вкладки «Не купившие» (§15) и починенных когорт (§2).

Сети и прода не касаются: витрина создаётся во временном файле, ответ Orderia
подставляется структурой. Запуск: py -3 -m pytest tests/test_guests_never.py -q
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import guest_analytics as ga           # noqa: E402
from core import guest_sync                       # noqa: E402
from core.guest_store import GuestStore           # noqa: E402


def orderia_row(oid, card, phone, last_date, name='Иван', lastname='',
                telegram='123', balance='20000'):
    """Запись в формате ответа never.php: все значения — строки."""
    return {'id': oid, 'cardnum': card, 'name': name, 'lastname': lastname,
            'phone': phone, 'balance': balance, 'check_sum': '0',
            'check_count': '0', 'last_date': last_date + ' 20:00:00',
            'telegram': telegram, 'coeff_calc': '5',
            'dated': last_date + ' 23:00:00'}


class NeverCardsBase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.unlink(self.db_path)
        self.store = GuestStore(self.db_path)

    def tearDown(self):
        for suffix in ('', '-wal', '-shm', '.backup_v1'):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    def add_buyer(self, guest_id, card, first, last, orders=1, revenue=1000.0):
        """Гость-покупатель прямо в витрину (минуя ETL из iiko)."""
        with self.store.conn() as conn:
            conn.execute(
                "INSERT INTO guests (guest_id, name, phone, card_number, "
                "registration_date, registration_source, first_order_date, "
                "first_order_store, last_visit_date, updated_at) "
                "VALUES (?, 'Гость', ?, ?, ?, 'iiko', ?, 'bolshoy', ?, '2026-01-01')",
                (guest_id, guest_id, card, first, first, last))
            for i in range(orders):
                conn.execute(
                    "INSERT INTO receipts (open_date, store, order_num, guest_id, "
                    "revenue, discount, full_sum) VALUES (?, 'bolshoy', ?, ?, ?, 0, ?)",
                    (first if i == 0 else last, str(i), guest_id,
                     revenue / orders, revenue / orders))
            conn.commit()


class TestSchemaMigration(NeverCardsBase):
    def test_fresh_db_gets_v2_tables(self):
        """Свежая база создаётся сразу в v2: таблицы v1 И never_cards."""
        with self.store.conn() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(version, 2)
        self.assertIn('guests', tables)
        self.assertIn('never_cards', tables)
        self.assertIn('never_sync', tables)

    def test_v1_database_migrates_and_keeps_data(self):
        """Старая база v1 доезжает до v2, данные на месте, бэкап создан."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE guests (guest_id TEXT PRIMARY KEY, name TEXT, phone TEXT,"
            " card_number TEXT, registration_date TEXT,"
            " registration_source TEXT NOT NULL DEFAULT 'iiko', first_order_date TEXT,"
            " first_order_store TEXT, last_visit_date TEXT, updated_at TEXT NOT NULL);"
            "CREATE TABLE receipts (open_date TEXT NOT NULL, store TEXT NOT NULL,"
            " order_num TEXT NOT NULL, guest_id TEXT NOT NULL, revenue REAL NOT NULL,"
            " discount REAL NOT NULL, full_sum REAL,"
            " PRIMARY KEY (open_date, store, order_num, guest_id));"
            "CREATE TABLE receipt_items (open_date TEXT, store TEXT, order_num TEXT,"
            " guest_id TEXT, dish_name TEXT, amount REAL, revenue REAL);"
            "CREATE TABLE guest_aliases (alias TEXT PRIMARY KEY, guest_id TEXT NOT NULL);"
            "CREATE TABLE sync_state (month TEXT PRIMARY KEY, status TEXT NOT NULL,"
            " receipts INTEGER, items INTEGER, synced_at TEXT,"
            " frozen INTEGER NOT NULL DEFAULT 0);"
            "INSERT INTO guests VALUES ('79001', 'Ста', '79001', '2000001',"
            " '2025-01-01', 'iiko', '2025-01-01', 'bolshoy', '2025-01-01', '2025-01-01');")
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        try:
            store = GuestStore(path)
            with store.conn() as c:
                self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(
                    c.execute("SELECT COUNT(*) FROM guests").fetchone()[0], 1)
                c.execute("SELECT COUNT(*) FROM never_cards")  # не бросает
            self.assertTrue(os.path.exists(path + '.backup_v1'),
                            'перед миграцией должен появиться бэкап')
        finally:
            for suffix in ('', '-wal', '-shm', '.backup_v1'):
                try:
                    os.unlink(path + suffix)
                except OSError:
                    pass


class TestTransform(unittest.TestCase):
    def test_key_is_source_id_not_cardnum(self):
        """cardnum в Orderia не уникален — ключом должен быть id."""
        rows = guest_sync.transform_never_cards([
            orderia_row('2647', '2002639', '79112365853', '2025-04-03'),
            orderia_row('2648', '2002639', '79992128676', '2025-04-03'),
            orderia_row('2649', '2002639', '79112365853', '2025-04-03'),
        ])
        self.assertEqual(len(rows), 3, 'три записи с одним номером карты не схлопываются')
        self.assertEqual({r['source_id'] for r in rows}, {'2647', '2648', '2649'})

    def test_registration_date_from_last_date_not_dated(self):
        """dated врёт (бэкфилл и сдвиг на 3 часа) — берём last_date."""
        row = guest_sync.transform_never_cards(
            [orderia_row('1', '2001', '79990001122', '2026-03-27')])[0]
        self.assertEqual(row['registered_at'], '2026-03-27')

    def test_phone_canon_matches_guest_id_rule(self):
        """Канонизация должна совпадать с normalize_guest_id, иначе сшивки нет."""
        for raw in ('79997313052', '+79997313052', '779997313052'):
            row = guest_sync.transform_never_cards(
                [orderia_row('1', '2001', raw, '2026-01-01')])[0]
            self.assertEqual(row['phone_canon'], '79997313052', raw)

    def test_junk_phone_flagged(self):
        """'7om/catalog' и бинарный мусор — не телефоны."""
        rows = guest_sync.transform_never_cards([
            orderia_row('1', '2001', '7om/catalog', '2026-01-01'),
            orderia_row('2', '2002', '7r_j\x1d931CJp', '2026-01-01'),
            orderia_row('3', '2003', '38268847632', '2026-01-01'),   # Черногория
        ])
        by_id = {r['source_id']: r for r in rows}
        self.assertEqual(by_id['1']['phone_valid'], 0)
        self.assertEqual(by_id['2']['phone_valid'], 0)
        self.assertEqual(by_id['3']['phone_valid'], 1, 'зарубежный номер настоящий')

    def test_balance_parsed_to_int(self):
        row = guest_sync.transform_never_cards(
            [orderia_row('1', '2001', '79990001122', '2026-01-01', balance='40000')])[0]
        self.assertEqual(row['balance'], 40000)


class TestStoreReplace(NeverCardsBase):
    def test_replace_is_full_not_upsert(self):
        """Карта, исчезнувшая из ответа (человек купил), исчезает из витрины."""
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('1', '2001', '79990001122', '2026-01-01'),
            orderia_row('2', '2002', '79990002233', '2026-01-02'),
        ]))
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('2', '2002', '79990002233', '2026-01-02'),
        ]))
        with self.store.conn() as conn:
            ids = {r[0] for r in conn.execute("SELECT source_id FROM never_cards")}
        self.assertEqual(ids, {'2'})
        self.assertEqual(self.store.never_sync_state()['total'], 1)

    def test_error_does_not_wipe_snapshot(self):
        """Сетевая ошибка не должна обнулять сохранённый список."""
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('1', '2001', '79990001122', '2026-01-01')]))
        self.store.mark_never_sync_error('Orderia ne otvetila')
        with self.store.conn() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM never_cards").fetchone()[0], 1)
        state = self.store.never_sync_state()
        self.assertEqual(state['status'], 'error')
        self.assertIsNotNone(state['error'])


class TestNeverBuyersReport(NeverCardsBase):
    def _report(self, anchor='2026-05-15', **kw):
        period = ga.resolve_period('month', anchor)
        meta = ga.build_meta(self.store, period)
        return ga.never_buyers(self.store, period, meta, **kw)

    def test_confirmed_excludes_buyers_found_by_card(self):
        """Тот же номер карты с чеками в iiko — ложное срабатывание."""
        self.add_buyer('79112365853', '2002639', '2025-04-03', '2026-06-18',
                       orders=53, revenue=52594.0)
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('2647', '2002639', '79112365853', '2025-04-03'),
            orderia_row('9001', '2009001', '79990009999', '2026-05-02'),
        ]))
        d = self._report()
        self.assertEqual(d['totals']['reported'], 2)
        self.assertEqual(d['totals']['confirmed'], 1)
        self.assertEqual(d['totals']['false_positives'], 1)
        self.assertEqual(d['totals']['fp_same_card'], 1)
        self.assertEqual(d['totals']['fp_revenue'], 52594)

    def test_second_card_of_known_phone_is_other_card(self):
        """Телефон знаком витрине, но покупки по другой карте."""
        self.add_buyer('79218649847', '2001711', '2024-03-16', '2026-07-18',
                       orders=82, revenue=105367.0)
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('1712', '20017111', '79218649847', '2024-03-16'),
        ]))
        d = self._report()
        self.assertEqual(d['totals']['confirmed'], 0)
        self.assertEqual(d['totals']['fp_other_card'], 1)
        self.assertEqual(d['false_positives'][0]['iiko_card'], '2001711')

    def test_junk_rows_excluded_from_confirmed(self):
        """Болванки сканера не считаются живыми людьми."""
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('1', '2001', '79990001122', '2026-05-02'),
            orderia_row('2', '2002', '7om/catalog', '2026-05-03'),
            orderia_row('3', '2003', '79990003344', '2026-05-04',
                        name='Jane', lastname='Doe', telegram=''),
        ]))
        d = self._report()
        self.assertEqual(d['totals']['reported'], 3)
        self.assertEqual(d['totals']['junk'], 2)
        self.assertEqual(d['totals']['confirmed'], 1)

    def test_conversion_uses_never_buyers_as_denominator(self):
        """Знаменатель конверсии = купившие + подтверждённые некупившие."""
        # Трое зарегистрировались в мае: один купил, двое нет.
        self.add_buyer('79001110011', '2005001', '2026-05-10', '2026-05-10')
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('1', '2005002', '79001110022', '2026-05-11'),
            orderia_row('2', '2005003', '79001110033', '2026-05-12'),
        ]))
        d = self._report()
        self.assertEqual(d['period']['bought'], 1)
        self.assertEqual(d['period']['never'], 2)
        self.assertEqual(d['period']['registered_total'], 3)
        self.assertAlmostEqual(d['period']['conversion_pct'], 33.3, places=1)

    def test_conversion_unavailable_before_orderia_coverage(self):
        """До начала данных Orderia конверсия не считается, а не показывает 100%."""
        self.add_buyer('79001110011', '2005001', '2023-05-10', '2023-05-10')
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('1', '2005002', '79001110022', '2026-05-11'),
        ]))
        d = self._report(anchor='2023-05-15')
        self.assertFalse(d['period']['conversion_available'])
        self.assertIsNone(d['period']['conversion_pct'])

    def test_duplicate_cardnum_does_not_drag_strangers(self):
        """Неуникальный номер карты нельзя использовать как ключ сшивки.

        В Orderia номер 2002639 выдан трём записям — двум разным людям. Привязка
        по номеру подтянула бы к покупателю чужие карты и посчитала бы его
        выручку трижды (реальный дефект, пойманный на проде 2026-08-12).
        """
        self.add_buyer('79992128676', '2002639', '2025-04-03', '2026-06-18',
                       orders=53, revenue=52594.0)
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('2647', '2002639', '79112365853', '2025-04-03'),  # чужой
            orderia_row('2648', '2002639', '79992128676', '2025-04-03'),  # покупатель
            orderia_row('2649', '2002639', '79112365853', '2025-04-03'),  # чужой
        ]))
        d = self._report()
        self.assertEqual(d['totals']['false_positives'], 1,
                         'ложное срабатывание только у того, чей телефон в витрине')
        self.assertEqual(d['totals']['confirmed'], 2)
        self.assertEqual(d['totals']['fp_revenue'], 52594,
                         'выручка не должна множиться на число карт')

    def test_revenue_counted_once_per_guest(self):
        """Две разные карты одного человека — выручка считается один раз."""
        self.add_buyer('79218649847', '2001711', '2024-03-16', '2026-07-18',
                       orders=82, revenue=105367.0)
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('1', '20017111', '79218649847', '2024-03-16'),
            orderia_row('2', '2003999', '79218649847', '2026-01-10'),
        ]))
        d = self._report()
        self.assertEqual(d['totals']['false_positives'], 2)
        self.assertEqual(d['totals']['fp_guests'], 1)
        self.assertEqual(d['totals']['fp_revenue'], 105367)

    def test_csv_list_contains_only_confirmed(self):
        self.add_buyer('79112365853', '2002639', '2025-04-03', '2026-06-18')
        self.store.replace_never_cards(guest_sync.transform_never_cards([
            orderia_row('2647', '2002639', '79112365853', '2025-04-03'),
            orderia_row('9001', '2009001', '79990009999', '2026-05-02'),
            orderia_row('9002', '2009002', '7om/catalog', '2026-05-02'),
        ]))
        d = self._report(include_list=True)
        self.assertEqual([g['card_number'] for g in d['guests']], ['2009001'])


class TestCohortFixes(NeverCardsBase):
    def test_no_tautological_first_order_column(self):
        """Колонки order1_pct больше нет: она всегда была 100%."""
        self.add_buyer('79001110011', '2005001', '2026-01-10', '2026-01-10')
        period = ga.resolve_period('month', '2026-05-15')
        meta = ga.build_meta(self.store, period)
        d = ga.lifecycle_cohorts(self.store, period, meta)
        self.assertTrue(d['cohorts'])
        self.assertNotIn('order1_pct', d['cohorts'][0])

    def test_active_is_bounded_by_asof(self):
        """Визит ПОСЛЕ даты среза не делает гостя активным на срез."""
        # Зарегистрировался и купил в январе, следующий визит — в августе.
        self.add_buyer('79001110011', '2005001', '2026-01-10', '2026-08-10',
                       orders=2, revenue=2000.0)
        # Срез — конец марта: августовский визит учитываться не должен.
        period = ga.resolve_period('month', '2026-03-15')
        meta = ga.build_meta(self.store, period)
        d = ga.lifecycle_cohorts(self.store, period, meta)
        jan = next(c for c in d['cohorts'] if c['cohort'] == '2026-01')
        self.assertEqual(jan['active_pct'], 0.0,
                         'последний визит на 31.03 — 10.01, это больше 30 дней')


class TestMskBoundary(unittest.TestCase):
    def test_period_default_uses_moscow_date(self):
        """Период по умолчанию берётся от московской даты, а не от UTC."""
        from core import msk_time
        period = ga.resolve_period('month', None)
        self.assertEqual(period['p_start'], msk_time.today().replace(day=1))

    def test_moscow_offset_is_three_hours(self):
        from datetime import timezone

        from core import msk_time
        utc_now = ga.datetime.now(timezone.utc)
        delta = msk_time.now().utcoffset().total_seconds()
        self.assertEqual(delta, 3 * 3600)
        # И «московская дата» действительно может отличаться от UTC-даты.
        self.assertEqual(msk_time.today(),
                         (utc_now + ga.timedelta(hours=3)).date())


if __name__ == '__main__':
    unittest.main(verbosity=2)

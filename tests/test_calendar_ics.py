# -*- coding: utf-8 -*-
"""Тесты генератора iCalendar (.ics) личного графика — core/calendar_ics.py.

Генератор детерминирован (кроме DTSTAMP, который передаём фиксированным), поэтому
проверяем структуру и правила RFC 5545 на синтетических сменах.
Запуск: py -3 tests/test_calendar_ics.py  (или pytest tests/test_calendar_ics.py)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.calendar_ics import build_calendar  # noqa: E402

STAMP = datetime(2026, 6, 26, 10, 0, 0)


def _events(ics):
    """Разбить .ics на блоки VEVENT (список словарей prop->value)."""
    out, cur = [], None
    for line in ics.split("\r\n"):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            out.append(cur); cur = None
        elif cur is not None and ":" in line:
            k, v = line.split(":", 1)
            cur[k] = v
    return out


def test_envelope_and_crlf():
    ics = build_calendar("Роман Юреня", [], dtstamp=STAMP)
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.rstrip("\r\n").endswith("END:VCALENDAR")
    assert "VERSION:2.0" in ics
    assert "\r\n" in ics and "\n\n" not in ics.replace("\r\n", "\n")
    assert "X-WR-TIMEZONE:Europe/Moscow" in ics
    assert "BEGIN:VEVENT" not in ics  # пустой список смен -> без событий


def test_day_shift_default_1400_and_fact_duration():
    shifts = [{
        "id": 7, "date": "2026-06-28", "start_time": None, "fact_minutes": 600,
        "location_name": "Варшавская", "role_id": 1, "role_name": "бармен",
    }]
    ev = _events(build_calendar("РЮ", shifts, dtstamp=STAMP))[0]
    assert ev["UID"] == "shift-7@kultura-schedule"
    assert ev["DTSTART"] == "20260628T140000"          # день -> 14:00
    assert ev["DTEND"] == "20260629T000000"            # +600 мин = 10ч -> 00:00
    assert ev["SUMMARY"] == "Варшавская"
    assert ev["LOCATION"] == "Варшавская"
    assert "факт" in ev["DESCRIPTION"]


def test_evening_shift_uses_start_time():
    shifts = [{
        "id": 9, "date": "2026-06-26", "start_time": "18:00", "fact_minutes": None,
        "location_name": "Лиговский", "role_id": 2, "role_name": "второй бармен",
    }]
    ev = _events(build_calendar("РЮ", shifts, dtstamp=STAMP))[0]
    assert ev["DTSTART"] == "20260626T180000"          # вечер -> 18:00
    assert ev["DTEND"] == "20260626T230000"            # план role 2 = 300 мин -> 23:00
    assert "по плану" in ev["DESCRIPTION"]
    assert "с 18:00" in ev["DESCRIPTION"]


def test_escaping_special_chars():
    shifts = [{
        "id": 1, "date": "2026-06-01", "start_time": None, "fact_minutes": None,
        "location_name": "Большой пр. В.О; зал, 2", "role_id": 1, "role_name": "бармен",
    }]
    ev = _events(build_calendar("РЮ", shifts, dtstamp=STAMP))[0]
    # ; и , должны быть экранированы в значении свойства
    assert ev["SUMMARY"] == "Большой пр. В.О\\; зал\\, 2"


def test_dtstamp_passthrough_and_count():
    shifts = [
        {"id": i, "date": "2026-06-%02d" % i, "start_time": None, "fact_minutes": 540,
         "location_name": "Крем", "role_id": 1, "role_name": "бармен"}
        for i in range(1, 6)
    ]
    ics = build_calendar("РЮ", shifts, dtstamp=STAMP)
    evs = _events(ics)
    assert len(evs) == 5
    assert all(e["DTSTAMP"] == "20260626T100000Z" for e in evs)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print("ALL %d TESTS PASSED" % len(fns))

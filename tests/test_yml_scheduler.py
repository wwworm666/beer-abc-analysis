"""Расписание снимка фидов: 05:00 МСК, без сети."""
from datetime import datetime
from zoneinfo import ZoneInfo

from core.yml_scheduler import MOSCOW, needs_refresh, next_refresh_at, parse_updated_at


def test_next_run_is_today_before_five_and_tomorrow_after():
    morning = datetime(2026, 9, 26, 4, 15, tzinfo=MOSCOW)
    assert next_refresh_at(morning) == datetime(2026, 9, 26, 5, 0, tzinfo=MOSCOW)
    after = datetime(2026, 9, 26, 5, 0, tzinfo=MOSCOW)
    assert next_refresh_at(after) == datetime(2026, 9, 27, 5, 0, tzinfo=MOSCOW)


def test_catch_up_only_after_five_when_snapshot_is_older():
    today_noon = datetime(2026, 9, 26, 12, 0, tzinfo=MOSCOW)
    yesterday = datetime(2026, 9, 25, 5, 0, tzinfo=MOSCOW)
    assert needs_refresh(today_noon, None) is True
    assert needs_refresh(today_noon, yesterday) is True
    assert needs_refresh(today_noon, datetime(2026, 9, 26, 5, 0, 1, tzinfo=MOSCOW)) is False
    assert needs_refresh(datetime(2026, 9, 26, 4, 0, tzinfo=MOSCOW), None) is False


def test_naive_stamp_is_read_as_moscow():
    parsed = parse_updated_at('2026-09-26T05:00:00')
    assert parsed == datetime(2026, 9, 26, 5, 0, tzinfo=ZoneInfo('Europe/Moscow'))

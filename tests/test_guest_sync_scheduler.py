# -*- coding: utf-8 -*-
"""Время ночного синка гостей (core/guest_sync_scheduler.py).

Шедулер живёт по наивному времени контейнера — в проде это UTC, и 05:10 = 08:10 МСК.
Так устроена вся ночная цепочка (docs/me.md, «Ночной прогон»): месячный отчёт 04:30,
гости 05:10, снимок /me 05:40. Тесты держат порядок цепочки и вторую подпись по Москве
в логе — без неё 05:10 читалось как «5 утра по Москве» (так и было написано в доке).

Запуск: py -3 -m pytest tests/test_guest_sync_scheduler.py -q
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import guest_sync_scheduler as gs   # noqa: E402


def test_container_utc_time_is_signed_in_moscow_time():
    assert gs._as_msk(datetime(2026, 10, 28, 5, 10, tzinfo=timezone.utc)) == '08:10'
    assert gs._as_msk(datetime(2026, 10, 27, 22, 30, tzinfo=timezone.utc)) == '01:30'


def test_guests_sync_stays_inside_the_night_chain():
    """Гости — после месячного отчёта и до снимка /me, все в одном времени контейнера."""
    from core import me_snapshot_scheduler as me
    from core import monthly_report_scheduler as monthly
    if any(name in os.environ for name in ('GUESTS_SYNC_HOUR', 'GUESTS_SYNC_MINUTE',
                                           'MONTHLY_REPORT_HOUR', 'MONTHLY_REPORT_MINUTE',
                                           'ME_SNAPSHOT_HOUR', 'ME_SNAPSHOT_MINUTE')):
        pytest.skip('время переопределено окружением — порядок задаёт тот, кто его задал')
    assert (monthly.REFRESH_HOUR, monthly.REFRESH_MINUTE) < (gs.REFRESH_HOUR, gs.REFRESH_MINUTE)
    assert (gs.REFRESH_HOUR, gs.REFRESH_MINUTE) < (me.SNAP_HOUR, me.SNAP_MINUTE)
    assert (gs.REFRESH_HOUR, gs.REFRESH_MINUTE) == (5, 10), \
        'время контейнера, 08:10 МСК — не «поправлять» на Москву (docs/me.md)'

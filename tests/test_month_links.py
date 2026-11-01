"""Старые ссылки «?month=YYYY-MM» на страницах, перешедших на полосу «Бар и период»
(core/month_links.py): контент-план и отзывы отвечают на них 302 с датами месяца.

Self-runnable: `py -3 tests/test_month_links.py` (совместимо с pytest).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.datastructures import MultiDict  # noqa: E402

from core.month_links import month_link_query, redirect_target  # noqa: E402


def test_month_becomes_dates_of_that_month():
    assert month_link_query(MultiDict([('month', '2026-10'), ('open', 'm1')])) == \
        'open=m1&date_from=2026-10-01&date_to=2026-10-31'
    assert month_link_query(MultiDict([('month', '2024-02')])) == 'date_from=2024-02-01&date_to=2024-02-29'
    assert month_link_query(MultiDict([('month', '2026-12')])) == 'date_from=2026-12-01&date_to=2026-12-31'
    assert month_link_query(MultiDict([('month', ' 2026-11 ')])) == 'date_from=2026-11-01&date_to=2026-11-30'


def test_nothing_to_convert_or_kept_values():
    assert month_link_query(MultiDict([('open', 'm1')])) is None              # без month — без перевода
    assert month_link_query(MultiDict([('month', 'all')]), keep=('all',)) is None
    assert month_link_query({'month': 'all'}, keep=('all',)) is None          # обычный dict тоже


def test_bad_month_or_period_in_link_drops_month():
    assert month_link_query(MultiDict([('month', '2026-13'), ('state', 'failed')])) == 'state=failed'
    assert month_link_query(MultiDict([('month', 'all')])) == ''              # 'all' не задан как понятный
    # Период из ссылки главнее старого месяца.
    assert month_link_query(MultiDict([('month', '2026-10'), ('date_from', '2026-09-01'),
                                       ('date_to', '2026-09-30')])) == 'date_from=2026-09-01&date_to=2026-09-30'


def test_repeated_params_and_target():
    args = MultiDict([('month', '2026-10'), ('tag', 'a'), ('tag', 'b')])
    assert month_link_query(args) == 'tag=a&tag=b&date_from=2026-10-01&date_to=2026-10-31'
    assert redirect_target('/reviews', MultiDict([('month', 'oops')])) == '/reviews'
    assert redirect_target('/reviews', MultiDict([('status', 'new')])) is None


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)

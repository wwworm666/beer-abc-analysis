# -*- coding: utf-8 -*-
"""Пересчёт производных полей в tests/fixtures/draft_kegs_sample.json.

    python3 tests/fixtures/refresh_draft_sample.py

Фикстура — ответ /api/draft-kegs, снятый с боевого iiko за неделю 03-09.08.2026
(сырых проводок и продаж в репозитории нет). Когда меняются правила букв или
групп решений, здесь пересчитываются ТОЛЬКО производные поля кегов — теми же
функциями, что в core/draft_kegs.py: буквы ABC, ряд по неделям, группа решения,
карточки групп. Литры, деньги, бармены и баланс остаются как сняты.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.abc_buckets import bucket_cards, decide_bucket  # noqa: E402
from core.abc_thresholds import KEG_MARKUP_A_MIN, KEG_MARKUP_B_MIN, markup_letter  # noqa: E402
from core.draft_kegs import _abc_by_cumulative, _abc_by_percentile, _count_by  # noqa: E402

TARGET = os.path.join(ROOT, 'tests', 'fixtures', 'draft_kegs_sample.json')


def refresh(block):
    rows = block['kegs']
    weeks = int(block['period']['days']) // 7
    _abc_by_cumulative(rows, 'TotalRevenue', 'ABC_Revenue', 'RevenueCumulativePercent')
    for row in rows:
        share = None if row['MarkupPercent'] is None else row['MarkupPercent'] / 100
        row['ABC_Markup'] = markup_letter(share, KEG_MARKUP_A_MIN, KEG_MARKUP_B_MIN)
    _abc_by_percentile(rows, 'TotalMargin', 'ABC_Margin')
    for row in rows:
        row['WeeksInPeriod'] = weeks
        # Недельного ряда в снятом ответе нет; на одной полной неделе он равен
        # литрам периода (окно прижато к концу периода и покрывает его целиком).
        if weeks == 1:
            row['WeeklyLiters'] = [row['TotalLiters']] if row['TotalLiters'] > 0 else [0.0]
            row['LitersOutsideWeeks'] = 0.0
        else:
            row.setdefault('WeeklyLiters', [])
            row.setdefault('LitersOutsideWeeks', row['TotalLiters'] - sum(row['WeeklyLiters']))
        row['ABC_Combined'] = row['ABC_Revenue'] + (row['ABC_Markup'] or '?') + row['ABC_Margin']
        share = None if row['MarkupPercent'] is None else row['MarkupPercent'] / 100
        row['ABC_Bucket'] = decide_bucket(row['ABC_Revenue'], share, row['TotalPortions'],
                                          row['WeeksInPeriod'], row['WeeklyLiters'],
                                          row['LitersOutsideWeeks'],
                                          KEG_MARKUP_A_MIN, KEG_MARKUP_B_MIN)
    block['buckets'] = bucket_cards(rows, int(block['period']['days']), 'portions',
                                    KEG_MARKUP_A_MIN, KEG_MARKUP_B_MIN)
    block['bucket_stats'] = _count_by(rows, 'ABC_Bucket')


def main():
    with open(TARGET, encoding='utf-8') as f:
        raw = f.read()
    payload = json.loads(raw)
    for block in payload.values():
        refresh(block)
    pretty = '\n' in raw.strip()[:200]
    with open(TARGET, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2 if pretty else None)
        if pretty:
            f.write('\n')
    for bar, block in payload.items():
        print(bar, 'kegs', len(block['kegs']), 'buckets', {c['key']: c['count'] for c in block['buckets']},
              'markup letters', _count_by(block['kegs'], 'ABC_Markup'))


if __name__ == '__main__':
    main()

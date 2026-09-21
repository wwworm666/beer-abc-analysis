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

import re  # noqa: E402

from core.abc_buckets import bucket_cards, decide_bucket  # noqa: E402
from core.abc_thresholds import (  # noqa: E402
    KEG_MARKUP_A_MIN,
    KEG_MARKUP_B_MIN,
    UNCATEGORIZED_KEGS,
    markup_letter,
)
from core.draft_kegs import (  # noqa: E402
    DraftKegAnalysis,
    _abc_by_cumulative,
    _abc_by_percentile,
    _count_by,
    _format_bars,
)

TARGET = os.path.join(ROOT, 'tests', 'fixtures', 'draft_kegs_sample.json')
NOMENCLATURE = os.path.join(ROOT, 'data', 'cache', 'nomenclature_full.json')

# Бары сети: разрез по барам в снятом ответе не сохранён, и его приходится
# восстанавливать синтетикой (см. split_by_bars).
BARS = ['Лиговский', 'Варшавская', 'Кременчугская', 'Большой пр. В.О']


def keg_styles():
    """{название кега без «КЕГ» и объёма: стиль} по дереву номенклатуры.

    Стиль у кега своей группой не задан, он лежит на блюде-порции. В боевом
    расчёте связка идёт по GUID техкарты, здесь техкарт нет, поэтому сорт
    сопоставляется по названию — только для фикстуры.
    """
    with open(NOMENCLATURE, encoding='utf-8') as f:
        nom = json.load(f)

    def chain(pid):
        names, seen = [], set()
        while pid and pid in nom and pid not in seen:
            seen.add(pid)
            names.append(nom[pid].get('name'))
            pid = nom[pid].get('parentId')
        return list(reversed(names))

    styles = {}
    for item in nom.values():
        if item.get('type') != 'DISH':
            continue
        path = chain(item.get('parentId'))
        if len(path) >= 3 and path[0] == 'Напитки Розлив':
            styles.setdefault((item.get('name') or '').strip().lower(), path[2])
    return styles


def sort_name(keg_name):
    """«КЕГ ФестХаус Хеллес 20 л» -> «фестхаус хеллес»."""
    name = re.sub(r'^КЕГ\s+', '', keg_name or '', flags=re.I)
    name = re.sub(r'\s*\d+([,.]\d+)?\s*л\.?\s*$', '', name, flags=re.I)
    return re.sub(r'[,\s]+$', '', name).strip().lower()


def pick_style(keg_name, styles):
    core_name = sort_name(keg_name)
    if not core_name:
        return UNCATEGORIZED_KEGS
    exact = styles.get(core_name)
    if exact:
        return exact
    for dish_name, style in sorted(styles.items()):
        if dish_name.startswith(core_name) or core_name in dish_name:
            return style
    return UNCATEGORIZED_KEGS


def split_by_bars(row, index):
    """Разрез кега по барам. СИНТЕТИКА: в снятом ответе его нет.

    Правило детерминированное: каждый третий кег делится между двумя барами
    как 70/30, остальные целиком в одном. Нужен, чтобы отрисовка секции «ПО
    БАРАМ» вообще проверялась; бизнес-смысл проверяют юнит-тесты на сырых
    строках (tests/test_draft_kegs.py).
    """
    liters, revenue, cost = row['TotalLiters'], row['TotalRevenue'], row['TotalCost']
    portions = row['TotalPortions']
    first = BARS[index % len(BARS)]
    if index % 3 == 0:
        second = BARS[(index + 1) % len(BARS)]
        bars = [
            {'Bar': first, 'Liters': liters * 0.7, 'Portions': portions * 0.7,
             'Revenue': revenue * 0.7, 'Cost': cost * 0.7},
            {'Bar': second, 'Liters': liters * 0.3, 'Portions': portions * 0.3,
             'Revenue': revenue * 0.3, 'Cost': cost * 0.3},
        ]
    else:
        bars = [{'Bar': first, 'Liters': liters, 'Portions': portions,
                 'Revenue': revenue, 'Cost': cost}]
    return _format_bars(bars, liters, revenue)


def refresh(block):
    rows = block['kegs']
    weeks = int(block['period']['days']) // 7
    styles = keg_styles()
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
    for index, row in enumerate(rows):
        row['Category'] = pick_style(row['KegName'], styles)
        row['ByBar'] = split_by_bars(row, index)
        row['BarsPresent'] = len(row['ByBar'])
    analysis = DraftKegAnalysis([], [], {}, block['period']['from'], block['period']['to'])
    categories = analysis._build_categories(rows)
    block['categories'] = categories
    block['total_categories'] = len(categories)
    block['buckets'] = bucket_cards(rows, int(block['period']['days']), 'portions',
                                    KEG_MARKUP_A_MIN, KEG_MARKUP_B_MIN)
    block['bucket_stats'] = _count_by(rows, 'ABC_Bucket')
    block['abc_stats'] = _count_by(rows, 'ABC_Combined')
    block['xyz_stats'] = _count_by(rows, 'XYZ_Category')


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
        print(bar, 'kegs', len(block['kegs']),
              'categories', block['total_categories'],
              'buckets', {c['key']: c['count'] for c in block['buckets']},
              'markup letters', _count_by(block['kegs'], 'ABC_Markup'))
        for cat in block['categories'][:5]:
            print(f"   {cat['Category']:26} кегов {cat['KegsCount']:2} "
                  f"литров {cat['TotalLiters']:7.1f} доля {cat['RevenueSharePercent']:5.1f}%")


if __name__ == '__main__':
    main()

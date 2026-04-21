# -*- coding: utf-8 -*-
"""Проверить все группы продуктов ЧЗ и посчитать коды в обороте"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chz import get_all_cises

groups = ['beer', 'nabeer', 'water', 'softdrinks', 'conserv', 'seafood', 'milk', 'grocery', 'vegetableoil']

for g in groups:
    print(f"\n--- {g} ---")
    try:
        items = get_all_cises(product_group=g, date_from='2024-01-01')
        statuses = {}
        for i in items:
            s = i.get('status', '?')
            statuses[s] = statuses.get(s, 0) + 1
        gtins = set(i.get('gtin') for i in items)
        print(f"  Всего кодов: {len(items)}")
        print(f"  Статусы: {statuses}")
        print(f"  Уникальных GTIN: {len(gtins)}")
    except Exception as e:
        print(f"  Ошибка: {e}")

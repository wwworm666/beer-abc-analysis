# -*- coding: utf-8 -*-
"""Список «нет в ЧЗ» — для отправки барменам.

По каждому бару отдельно, плюс сводный лист. Включает колонку для
заполнения реального GTIN после сканирования бутылки приложением
«Честный знак».
"""
import os
import sys
import csv
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)
from core.iiko_barcodes import _normalize_gtin

BARS = ["Большой пр. В.О", "Лиговский", "Кременчугская", "Варшавская"]

# Поставщики которых НЕ включаем в список бармен-сверки.
# СПБ-Премиум возит только импорт со сроком розлива до 01.12.2025 —
# поштучный учёт по этим бутылкам в ЧЗ не ведётся (объёмно-сортовой
# метод старого режима). Их «нет в ЧЗ» легитимно, проверять баркоды
# в iiko бессмысленно — всё равно ЧЗ не пропустит сканирование.
EXCLUDE_SUPPLIERS = {"СПБ-Премиум"}


def load_suggestions():
    """barcode_fixes_suggested.csv → {iiko_name: (suggested_gtin, score)}"""
    path = os.path.join(REPO_DIR, 'chz_test', 'debug', 'barcode_fixes_suggested.csv')
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f, delimiter=';'))
    for r in rows[1:]:
        if len(r) < 9:
            continue
        # iiko: Поставщик, iiko: Название, iiko: Остаток, iiko: Текущий баркод,
        # Предлагаемый GTIN из ЧЗ, ЧЗ: Бренд, ЧЗ: Название, ЧЗ: Кол-во кодов, Score
        name, sg, brand, score = r[1], r[4], r[5], r[8]
        try:
            sc = int(score)
        except ValueError:
            sc = 0
        out[name.strip()] = (sg, brand, sc)
    return out


def main():
    suggestions = load_suggestions()
    print(f"Загружено {len(suggestions)} предложений GTIN")

    # iiko XML → name → barcodes
    tree = ET.parse(os.path.join(REPO_DIR, 'data', 'cache', 'nomenclature__products.xml'))
    iiko_by_name = {}
    for p in tree.getroot().findall('productDto'):
        nm = p.find('name')
        if nm is not None and nm.text:
            bcs = []
            for bc in p.findall('.//barcode'):
                if bc.text:
                    bcs.append(bc.text.strip())
            iiko_by_name[nm.text.strip()] = bcs

    rows_for_csv = []
    for bar in BARS:
        url = 'http://127.0.0.1:5000/api/stocks/expiry?bar=' + urllib.parse.quote(bar)
        try:
            data = json.loads(urllib.request.urlopen(url, timeout=60).read())
        except Exception as e:
            print(f"[ERR] {bar}: {e}")
            continue
        unmatched = [
            it for it in data['items']
            if not it['has_chz_data']
            and it.get('category', '?') not in EXCLUDE_SUPPLIERS
        ]
        print(f"  {bar}: {len(unmatched)} позиций без ЧЗ (после исключения {EXCLUDE_SUPPLIERS})")
        for it in unmatched:
            name = it['name'].strip()
            iiko_bcs = iiko_by_name.get(name, [])
            sg = suggestions.get(name)
            sg_gtin = sg[0] if sg else ''
            sg_brand = sg[1] if sg else ''
            sg_score = sg[2] if sg else 0
            confidence = ''
            if sg_score >= 4:
                confidence = 'Точный'
            elif sg_score == 3:
                confidence = 'Уверенный'
            elif sg_score == 2:
                confidence = 'Требует проверки'
            rows_for_csv.append({
                'bar': bar,
                'supplier': it.get('category', '?'),
                'name': name,
                'stock': it.get('stock', 0),
                'current_barcode': ', '.join(iiko_bcs) if iiko_bcs else '(нет в карточке)',
                'suggested_gtin': sg_gtin,
                'suggested_chz_brand': sg_brand,
                'confidence': confidence,
            })

    # Один CSV со всеми барами, разделённый шапками-разделителями
    out_file = os.path.join(REPO_DIR, 'chz_test', 'debug', 'для_барменов_проверка_баркодов.csv')
    with open(out_file, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow([
            'Бар',
            'Поставщик',
            'Товар',
            'Остаток (шт)',
            'Текущий баркод в iiko',
            'Предлагаемый GTIN (из ЧЗ)',
            'ЧЗ-название (что значит предложение)',
            'Уверенность',
            'Реальный GTIN с DataMatrix',
            'Заметки бармена',
        ])
        # Группируем по бару, сортируем по поставщику + названию
        rows_for_csv.sort(key=lambda r: (r['bar'], r['supplier'], r['name']))
        prev_bar = None
        for r in rows_for_csv:
            if r['bar'] != prev_bar:
                # пустая разделительная строка между барами
                if prev_bar is not None:
                    w.writerow([])
                prev_bar = r['bar']
            w.writerow([
                r['bar'],
                r['supplier'],
                r['name'],
                r['stock'],
                r['current_barcode'],
                r['suggested_gtin'],
                r['suggested_chz_brand'],
                r['confidence'],
                '',  # Реальный GTIN — пусто, бармен заполнит
                '',  # Заметки — пусто
            ])

    print(f"\nСохранено: {out_file}")
    print(f"Всего строк: {len(rows_for_csv)}")
    # Сводка по барам и по уверенности
    from collections import Counter
    by_bar = Counter(r['bar'] for r in rows_for_csv)
    by_conf = Counter(r['confidence'] or 'Нет предложения' for r in rows_for_csv)
    print('\nПо барам:')
    for bar, n in by_bar.most_common():
        print(f'  {bar}: {n}')
    print('\nПо уверенности предложения GTIN:')
    for c, n in by_conf.most_common():
        print(f'  {c}: {n}')


if __name__ == '__main__':
    main()

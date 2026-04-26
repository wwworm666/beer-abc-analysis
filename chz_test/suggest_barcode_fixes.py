# -*- coding: utf-8 -*-
"""Подбор GTIN из ЧЗ к iiko-товарам где баркод не сматчился.

Для каждого товара фасовки на полке (iiko) у которого баркод
не нашёлся в chz_stock.json — ищет по бренду/названию ближайший
кандидат в ЧЗ-данных.

Алгоритм:
1. Берёт /api/stocks/expiry?bar=Общая, фильтрует has_chz_data=false
2. Для каждой позиции выбирает ключевые слова из имени iiko
3. Сравнивает с brand/name в chz_stock.json (только товары которые
   ещё не сматчены другим iiko-товаром)
4. Выдаёт CSV с предлагаемыми парами + score соответствия
"""
import os
import sys
import json
import csv
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

from core.iiko_barcodes import _normalize_gtin


def normalize_text(s):
    """Нижний регистр, убираем спец-символы, оставляем только слова длиннее 2."""
    s = s.lower()
    s = re.sub(r'[^\w\s]', ' ', s)
    return [w for w in s.split() if len(w) >= 3 and not w.isdigit()]


def score_match(iiko_words, chz_text):
    """Сколько iiko-слов нашлось в chz-тексте."""
    chz_low = chz_text.lower()
    return sum(1 for w in iiko_words if w in chz_low)


def main():
    url = 'http://127.0.0.1:5000/api/stocks/expiry?bar=' + urllib.parse.quote('Общая')
    data = json.loads(urllib.request.urlopen(url, timeout=60).read())
    unmatched = [it for it in data['items'] if not it['has_chz_data']]
    print(f"Несматченных в iiko фасовке: {len(unmatched)}")

    # Загружаем ЧЗ
    chz = json.load(open(os.path.join(REPO_DIR, 'chz_test', 'debug', 'chz_stock.json'), encoding='utf-8'))

    # Какие GTIN уже сматчены другими iiko-товарами — не предлагаем их повторно
    used_gtins = set()
    for it in data['items']:
        if it['has_chz_data']:
            for g in it.get('gtins', []):
                used_gtins.add(g.zfill(14))

    # iiko XML (для обогащения, если что)
    tree = ET.parse(os.path.join(REPO_DIR, 'data', 'cache', 'nomenclature__products.xml'))
    iiko_xml_by_name = {}
    for p in tree.getroot().findall('productDto'):
        nm = p.find('name')
        if nm is not None and nm.text:
            iiko_xml_by_name[nm.text.strip()] = p

    suggestions = []
    for it in unmatched:
        iiko_name = it['name']
        iiko_words = normalize_text(iiko_name)
        if not iiko_words:
            continue

        # Подбираем кандидатов
        scored = []
        for x in chz:
            gtin = x['gtin'].zfill(14)
            if gtin in used_gtins:
                continue
            chz_text = (x.get('name') or '') + ' ' + (x.get('brand') or '')
            sc = score_match(iiko_words, chz_text)
            if sc >= 2:  # минимум 2 общих слова
                scored.append((sc, x))
        scored.sort(key=lambda s: -s[0])

        if scored:
            best_sc, best = scored[0]
            iiko_xml = iiko_xml_by_name.get(iiko_name.strip())
            iiko_bcs = []
            if iiko_xml is not None:
                for bc in iiko_xml.findall('.//barcode'):
                    if bc.text:
                        iiko_bcs.append(bc.text.strip())
            suggestions.append({
                'iiko_name': iiko_name,
                'iiko_category': it.get('category', '?'),
                'iiko_stock': it.get('stock', 0),
                'iiko_barcodes': ', '.join(iiko_bcs),
                'suggested_gtin': best['gtin'],
                'chz_brand': best.get('brand', ''),
                'chz_name': best.get('name', ''),
                'chz_count': best['count'],
                'match_score': best_sc,
            })

    # Сохраняем CSV
    out_file = os.path.join(REPO_DIR, 'chz_test', 'debug', 'barcode_fixes_suggested.csv')
    with open(out_file, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['iiko: Поставщик', 'iiko: Название', 'iiko: Остаток',
                    'iiko: Текущий баркод', 'Предлагаемый GTIN из ЧЗ',
                    'ЧЗ: Бренд', 'ЧЗ: Название', 'ЧЗ: Кол-во кодов', 'Score'])
        suggestions.sort(key=lambda s: -s['match_score'])
        for s in suggestions:
            w.writerow([
                s['iiko_category'], s['iiko_name'], s['iiko_stock'],
                s['iiko_barcodes'], s['suggested_gtin'],
                s['chz_brand'], s['chz_name'], s['chz_count'], s['match_score'],
            ])

    print(f"Сохранено {len(suggestions)} предложений в {out_file}")
    print(f"Из них score >= 4 (высокая уверенность): {sum(1 for s in suggestions if s['match_score'] >= 4)}")


if __name__ == '__main__':
    main()

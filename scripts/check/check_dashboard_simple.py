# -*- coding: utf-8 -*-
"""Проверка дашборда без спецсимволов"""
import requests
import json

TEST_PERIOD = {'date_from': '2025-11-17', 'date_to': '2025-11-23'}

EXPECTED_KREM = {
    'checks': 161,
    'averageCheck': 1652.94,
    'revenue': 266123.0,
    'loyaltyWriteoffs': 10657.0
}

BARS = [
    ('kremenchugskaya', 'Кременчугская'),
    ('bolshoy', 'Большой'),
    ('ligovskiy', 'Лиговский'),
    ('varshavskaya', 'Варшавская'),
    ('all', 'Общая')
]

print("="*80)
print("ПРОВЕРКА ДАШБОРДА")
print("="*80)

errors = []
warnings = []
all_metrics = {}

# 1. Проверка метрик для всех баров
print("\n1. ФАКТИЧЕСКИЕ МЕТРИКИ:")
for bar_key, bar_name in BARS:
    resp = requests.post('http://localhost:5000/api/dashboard-analytics',
                        json={'bar': bar_key, **TEST_PERIOD})

    if resp.status_code != 200:
        errors.append(f"[ERROR] {bar_name}: HTTP {resp.status_code}")
        continue

    data = resp.json()
    all_metrics[bar_key] = data

    print(f"\n{bar_name}:")
    print(f"  Выручка: {data.get('revenue', 0):,.0f}")
    print(f"  Чеки: {data.get('checks', 0)}")
    print(f"  Средний чек: {data.get('averageCheck', 0):,.2f}")
    print(f"  Списания баллов: {data.get('loyaltyWriteoffs', 0):,.2f}")
    print(f"  Прибыль: {data.get('profit', 0):,.2f}")

# 2. Проверка эталонных значений
print("\n2. ПРОВЕРКА ЭТАЛОННЫХ ЗНАЧЕНИЙ (Кременчугская):")
if 'kremenchugskaya' in all_metrics:
    kd = all_metrics['kremenchugskaya']

    if abs(kd.get('checks', 0) - EXPECTED_KREM['checks']) == 0:
        print("  [OK] Чеки: {} (правильно)".format(kd.get('checks')))
    else:
        errors.append("[ERROR] Чеки: {} != {}".format(kd.get('checks'), EXPECTED_KREM['checks']))
        print("  [ERROR] Чеки: {} (ожидалось {})".format(kd.get('checks'), EXPECTED_KREM['checks']))

    avg_diff = abs(kd.get('averageCheck', 0) - EXPECTED_KREM['averageCheck'])
    if avg_diff < 10:
        print("  [OK] Средний чек: {:.2f} (правильно)".format(kd.get('averageCheck')))
    else:
        warnings.append("[WARN] Средний чек: {:.2f} != {:.2f}".format(kd.get('averageCheck'), EXPECTED_KREM['averageCheck']))

    loyalty_diff = abs(kd.get('loyaltyWriteoffs', 0) - EXPECTED_KREM['loyaltyWriteoffs'])
    if loyalty_diff < 1:
        print("  [OK] Списания баллов: {:.2f} (правильно)".format(kd.get('loyaltyWriteoffs')))
    else:
        errors.append("[ERROR] Списания: {:.2f} != {}".format(kd.get('loyaltyWriteoffs'), EXPECTED_KREM['loyaltyWriteoffs']))

# 3. Проверка сумм
print("\n3. ПРОВЕРКА СУММИРОВАНИЯ:")
if 'all' in all_metrics:
    total = all_metrics['all']

    sums = {'revenue': 0, 'checks': 0, 'loyaltyWriteoffs': 0, 'profit': 0}
    for bk, _ in BARS[:-1]:
        if bk in all_metrics:
            bd = all_metrics[bk]
            sums['revenue'] += bd.get('revenue', 0)
            sums['checks'] += bd.get('checks', 0)
            sums['loyaltyWriteoffs'] += bd.get('loyaltyWriteoffs', 0)
            sums['profit'] += bd.get('profit', 0)

    for metric in sums:
        calc = sums[metric]
        actual = total.get(metric, 0)
        diff = abs(calc - actual)

        if diff < 0.01:
            print("  [OK] {}: сумма {:.2f} = общая {:.2f}".format(metric, calc, actual))
        else:
            errors.append("[ERROR] {}: сумма {:.2f} != {:.2f}".format(metric, calc, actual))
            print("  [ERROR] {}: сумма {:.2f} != общая {:.2f}".format(metric, calc, actual))

# 4. Проверка долей
print("\n4. ПРОВЕРКА ДОЛЕЙ:")
for bar_key, bar_name in BARS:
    if bar_key not in all_metrics:
        continue

    data = all_metrics[bar_key]
    total_share = data.get('draftShare', 0) + data.get('packagedShare', 0) + data.get('kitchenShare', 0)

    if abs(total_share - 100) < 0.1:
        print("  [OK] {}: доли = 100%".format(bar_name))
    else:
        warnings.append("[WARN] {}: доли = {:.2f}%".format(bar_name, total_share))
        print("  [WARN] {}: доли = {:.2f}%".format(bar_name, total_share))

# 5. Проверка планов
print("\n5. ПРОВЕРКА ПЛАНОВ:")
resp = requests.post('http://localhost:5000/api/get-plan',
                     json={'bar': 'kremenchugskaya', 'week': TEST_PERIOD['date_from']})

if resp.status_code == 200:
    plan = resp.json()
    if 'loyaltyWriteoffs' in plan:
        print("  [OK] План содержит loyaltyWriteoffs: {:.2f}".format(plan['loyaltyWriteoffs']))
    else:
        errors.append("[ERROR] План не содержит loyaltyWriteoffs")
        print("  [ERROR] План не содержит loyaltyWriteoffs")
else:
    warnings.append("[WARN] Не удалось получить план: HTTP {}".format(resp.status_code))

# ИТОГ
print("\n" + "="*80)
print("ИТОГ:")
print("  Критических ошибок: {}".format(len(errors)))
print("  Предупреждений: {}".format(len(warnings)))

if errors:
    print("\nКРИТИЧЕСКИЕ ОШИБКИ:")
    for e in errors:
        print("  " + e)

if warnings:
    print("\nПРЕДУПРЕЖДЕНИЯ:")
    for w in warnings:
        print("  " + w)

if not errors and not warnings:
    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")

print("="*80)

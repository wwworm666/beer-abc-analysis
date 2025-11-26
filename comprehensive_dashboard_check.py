"""
Комплексная проверка дашборда на ошибки
Проверяет все метрики, планы, консистентность данных
"""
import requests
import json

# Период для проверки (Кременчугская 17.11-23.11 - известные эталонные значения)
TEST_PERIOD = {
    'date_from': '2025-11-17',
    'date_to': '2025-11-23'
}

# Эталонные значения для Кременчугская 17.11-23.11
EXPECTED_KREMENCHUGSKAYA = {
    'checks': 161,
    'averageCheck': 1652.94,  # примерно
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
print("КОМПЛЕКСНАЯ ПРОВЕРКА ДАШБОРДА")
print("="*80)
print(f"\nПериод проверки: {TEST_PERIOD['date_from']} - {TEST_PERIOD['date_to']}\n")

# =======================
# 1. ПРОВЕРКА МЕТРИК ФАКТ
# =======================
print("\n" + "="*80)
print("1. ПРОВЕРКА ФАКТИЧЕСКИХ МЕТРИК")
print("="*80)

all_metrics = {}
errors = []
warnings = []

for bar_key, bar_name in BARS:
    print(f"\n{bar_name} ({bar_key}):")
    print("-" * 40)

    response = requests.post('http://localhost:5000/api/dashboard-analytics', json={
        'bar': bar_key,
        **TEST_PERIOD
    })

    if response.status_code != 200:
        errors.append(f"❌ {bar_name}: HTTP {response.status_code}")
        print(f"  ❌ Ошибка HTTP {response.status_code}")
        continue

    data = response.json()
    all_metrics[bar_key] = data

    # Проверка обязательных полей
    required_fields = [
        'revenue', 'checks', 'averageCheck',
        'draftShare', 'packagedShare', 'kitchenShare',
        'revenueDraft', 'revenuePackaged', 'revenueKitchen',
        'markupPercent', 'profit',
        'markupDraft', 'markupPackaged', 'markupKitchen',
        'loyaltyWriteoffs'
    ]

    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        errors.append(f"❌ {bar_name}: Отсутствуют поля: {missing_fields}")
        print(f"  ❌ Отсутствуют поля: {missing_fields}")

    # Выводим основные метрики
    print(f"  Выручка: {data.get('revenue', 0):,.2f} ₽")
    print(f"  Чеки: {data.get('checks', 0)}")
    print(f"  Средний чек: {data.get('averageCheck', 0):,.2f} ₽")
    print(f"  Списания баллов: {data.get('loyaltyWriteoffs', 0):,.2f} ₽")
    print(f"  Прибыль: {data.get('profit', 0):,.2f} ₽")
    print(f"  Наценка: {data.get('markupPercent', 0):.2f}%")

    # Проверка None значений
    none_fields = [field for field in required_fields if data.get(field) is None]
    if none_fields:
        errors.append(f"❌ {bar_name}: Поля со значением None: {none_fields}")
        print(f"  ❌ None значения: {none_fields}")

    # Проверка математики: средний чек = выручка / чеки
    if data.get('checks') and data.get('checks') > 0:
        calculated_avg = data.get('revenue', 0) / data.get('checks')
        actual_avg = data.get('averageCheck', 0)
        diff = abs(calculated_avg - actual_avg)

        if diff > 0.01:  # допуск 1 копейка
            warnings.append(f"⚠️  {bar_name}: Средний чек не сходится: {calculated_avg:.2f} vs {actual_avg:.2f}")
            print(f"  ⚠️  Средний чек: рассчитано {calculated_avg:.2f}, в данных {actual_avg:.2f}")

# Проверка эталонных значений для Кременчугская
print("\n" + "-"*80)
print("ПРОВЕРКА ЭТАЛОННЫХ ЗНАЧЕНИЙ (Кременчугская 17.11-23.11):")
print("-"*80)

if 'kremenchugskaya' in all_metrics:
    krem_data = all_metrics['kremenchugskaya']

    checks_diff = abs(krem_data.get('checks', 0) - EXPECTED_KREMENCHUGSKAYA['checks'])
    if checks_diff > 0:
        errors.append(f"❌ Кременчугская: Чеки {krem_data.get('checks')} != {EXPECTED_KREMENCHUGSKAYA['checks']}")
        print(f"  ❌ Чеки: {krem_data.get('checks')} (ожидалось {EXPECTED_KREMENCHUGSKAYA['checks']})")
    else:
        print(f"  ✅ Чеки: {krem_data.get('checks')} (правильно)")

    avg_diff = abs(krem_data.get('averageCheck', 0) - EXPECTED_KREMENCHUGSKAYA['averageCheck'])
    if avg_diff > 10:  # допуск 10 рублей
        warnings.append(f"⚠️  Кременчугская: Средний чек {krem_data.get('averageCheck'):.2f} != {EXPECTED_KREMENCHUGSKAYA['averageCheck']:.2f}")
        print(f"  ⚠️  Средний чек: {krem_data.get('averageCheck'):.2f} (ожидалось ~{EXPECTED_KREMENCHUGSKAYA['averageCheck']:.2f})")
    else:
        print(f"  ✅ Средний чек: {krem_data.get('averageCheck'):.2f} (правильно)")

    loyalty_diff = abs(krem_data.get('loyaltyWriteoffs', 0) - EXPECTED_KREMENCHUGSKAYA['loyaltyWriteoffs'])
    if loyalty_diff > 1:  # допуск 1 рубль
        errors.append(f"❌ Кременчугская: Списания {krem_data.get('loyaltyWriteoffs'):.2f} != {EXPECTED_KREMENCHUGSKAYA['loyaltyWriteoffs']}")
        print(f"  ❌ Списания баллов: {krem_data.get('loyaltyWriteoffs'):.2f} (ожидалось {EXPECTED_KREMENCHUGSKAYA['loyaltyWriteoffs']})")
    else:
        print(f"  ✅ Списания баллов: {krem_data.get('loyaltyWriteoffs'):.2f} (правильно)")

# =======================
# 2. ПРОВЕРКА СУММИРОВАНИЯ
# =======================
print("\n" + "="*80)
print("2. ПРОВЕРКА КОНСИСТЕНТНОСТИ (сумма по барам = общая)")
print("="*80)

if 'all' in all_metrics:
    total_data = all_metrics['all']

    # Суммируем по барам
    bars_sum = {
        'revenue': 0,
        'checks': 0,
        'loyaltyWriteoffs': 0,
        'profit': 0
    }

    for bar_key, _ in BARS[:-1]:  # Все кроме "all"
        if bar_key in all_metrics:
            bar_data = all_metrics[bar_key]
            bars_sum['revenue'] += bar_data.get('revenue', 0)
            bars_sum['checks'] += bar_data.get('checks', 0)
            bars_sum['loyaltyWriteoffs'] += bar_data.get('loyaltyWriteoffs', 0)
            bars_sum['profit'] += bar_data.get('profit', 0)

    # Проверяем суммы
    for metric in bars_sum:
        calculated = bars_sum[metric]
        actual = total_data.get(metric, 0)
        diff = abs(calculated - actual)

        if diff > 0.01:  # допуск для округления
            errors.append(f"❌ Общая/{metric}: сумма {calculated:.2f} != {actual:.2f}")
            print(f"  ❌ {metric}: сумма по барам {calculated:.2f} != общая {actual:.2f}")
        else:
            print(f"  ✅ {metric}: сумма по барам {calculated:.2f} = общая {actual:.2f}")

# =======================
# 3. ПРОВЕРКА ДОЛЕЙ
# =======================
print("\n" + "="*80)
print("3. ПРОВЕРКА ДОЛЕЙ КАТЕГОРИЙ")
print("="*80)

for bar_key, bar_name in BARS:
    if bar_key not in all_metrics:
        continue

    data = all_metrics[bar_key]
    draft = data.get('draftShare', 0)
    packaged = data.get('packagedShare', 0)
    kitchen = data.get('kitchenShare', 0)
    total_share = draft + packaged + kitchen

    if abs(total_share - 100) > 0.1:  # должно быть ровно 100%
        warnings.append(f"⚠️  {bar_name}: Доли не равны 100%: {total_share:.2f}%")
        print(f"  ⚠️  {bar_name}: Доли = {total_share:.2f}% (розлив {draft}% + фасовка {packaged}% + кухня {kitchen}%)")
    else:
        print(f"  ✅ {bar_name}: Доли = 100% (розлив {draft}% + фасовка {packaged}% + кухня {kitchen}%)")

# =======================
# 4. ПРОВЕРКА ПЛАНОВ
# =======================
print("\n" + "="*80)
print("4. ПРОВЕРКА ПЛАНОВ")
print("="*80)

# Запрашиваем планы для текущего периода
response = requests.post('http://localhost:5000/api/get-plan', json={
    'bar': 'kremenchugskaya',
    'week': TEST_PERIOD['date_from']
})

if response.status_code == 200:
    plan_data = response.json()

    required_plan_fields = [
        'revenue', 'checks', 'averageCheck',
        'draftShare', 'packagedShare', 'kitchenShare',
        'markupPercent', 'profit',
        'loyaltyWriteoffs'  # Проверяем что есть в планах
    ]

    missing_plan_fields = [field for field in required_plan_fields if field not in plan_data]
    if missing_plan_fields:
        errors.append(f"❌ План: Отсутствуют поля: {missing_plan_fields}")
        print(f"  ❌ Отсутствуют поля в плане: {missing_plan_fields}")
    else:
        print(f"  ✅ Все обязательные поля присутствуют в плане")

    if 'loyaltyWriteoffs' in plan_data:
        print(f"  ✅ План списаний баллов: {plan_data['loyaltyWriteoffs']:,.2f} ₽")
    else:
        errors.append(f"❌ План: Отсутствует loyaltyWriteoffs")
        print(f"  ❌ План: Отсутствует loyaltyWriteoffs")
else:
    warnings.append(f"⚠️  Не удалось получить план: HTTP {response.status_code}")
    print(f"  ⚠️  Не удалось получить план: HTTP {response.status_code}")

# =======================
# ИТОГОВЫЙ ОТЧЕТ
# =======================
print("\n" + "="*80)
print("ИТОГОВЫЙ ОТЧЕТ")
print("="*80)

print(f"\nПроверено баров: {len([k for k in all_metrics if k != 'all'])}")
print(f"Критических ошибок: {len(errors)}")
print(f"Предупреждений: {len(warnings)}")

if errors:
    print("\n❌ КРИТИЧЕСКИЕ ОШИБКИ:")
    for error in errors:
        print(f"  {error}")

if warnings:
    print("\n⚠️  ПРЕДУПРЕЖДЕНИЯ:")
    for warning in warnings:
        print(f"  {warning}")

if not errors and not warnings:
    print("\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
    print("   Дашборд работает корректно, ошибок не обнаружено.")

print("\n" + "="*80)

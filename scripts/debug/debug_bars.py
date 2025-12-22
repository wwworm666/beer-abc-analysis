"""Проверка подсчёта уникальных чеков по дате+времени"""
from core.olap_reports import OlapReports
from collections import defaultdict

olap = OlapReports()

if olap.connect():
    # Получаем все данные
    draft = olap.get_draft_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    bottles = olap.get_beer_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    kitchen = olap.get_kitchen_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    
    all_records = []
    if draft and 'data' in draft:
        all_records.extend(draft['data'])
    if bottles and 'data' in bottles:
        all_records.extend(bottles['data'])
    if kitchen and 'data' in kitchen:
        all_records.extend(kitchen['data'])
    
    print(f"Всего записей: {len(all_records)}")
    
    # Способ 1: Суммирование UniqOrderId (текущий, неправильный)
    total_sum = sum(r.get('UniqOrderId', 0) for r in all_records)
    print(f"\nСпособ 1 (сумма UniqOrderId): {total_sum} чеков")
    
    # Способ 2: Уникальные даты
    unique_dates = set()
    for r in all_records:
        date = r.get('OpenDate.Typed')
        if date:
            unique_dates.add(date)
    print(f"\nСпособ 2 (уникальные даты): {len(unique_dates)} уникальных дат")
    print(f"Даты: {sorted(unique_dates)}")
    
    # Способ 3: Максимальное значение UniqOrderId по дате (предположение что это номер чека)
    max_by_date = defaultdict(int)
    for r in all_records:
        date = r.get('OpenDate.Typed')
        uniq_id = r.get('UniqOrderId', 0)
        if date and uniq_id:
            max_by_date[date] = max(max_by_date[date], uniq_id)
    
    total_by_max = sum(max_by_date.values())
    print(f"\nСпособ 3 (сумма максимумов по датам): {total_by_max} чеков")
    for date in sorted(max_by_date.keys()):
        print(f"  {date}: макс {max_by_date[date]}")
    
    olap.disconnect()

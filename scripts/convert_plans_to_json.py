# -*- coding: utf-8 -*-
"""
Скрипт для конвертации Excel планов ТТ в JSON формат.
Запуск: python scripts/convert_plans_to_json.py

Формат Excel:
- Колонка 0: номер дня
- Колонки 1-4: план по каждому бару

Формат JSON:
{
  "2026-01-05": {
    "Кременчугская": 33270,
    "Варшавская": 23220
  }
}
"""
import pandas as pd
import json
import os

# Колонки баров в Excel
BARS = {
    1: 'Кременчугская',
    2: 'Варшавская',
    3: 'Большой пр В.О.',
    4: 'Лиговский',
}

# Строки где начинаются месяцы
MONTH_ROWS = {
    0: (12, 2025),   # Декабрь 2025
    37: (11, 2025),  # Ноябрь 2025
    73: (10, 2025),  # Октябрь 2025
    111: (1, 2026),  # Январь 2026
}


def convert_excel_to_json(excel_path: str, output_path: str):
    """Конвертирует Excel файл планов в JSON."""

    df = pd.read_excel(excel_path, header=None)

    plans = {}  # {date: {bar: plan}}

    current_month = None
    current_year = None

    for idx, row in df.iterrows():
        # Проверяем, начинается ли новый месяц
        if idx in MONTH_ROWS:
            current_month, current_year = MONTH_ROWS[idx]
            continue

        if current_month is None:
            continue

        # Получаем номер дня
        day = row[0]
        if pd.isna(day) or not isinstance(day, (int, float)):
            continue
        day = int(day)

        # Формируем дату
        date_str = f'{current_year}-{current_month:02d}-{day:02d}'
        plans[date_str] = {}

        # Читаем план по каждому бару
        for col, bar_name in BARS.items():
            plan = row[col] if pd.notna(row[col]) else 0
            if isinstance(plan, (int, float)) and plan > 0:
                plans[date_str][bar_name] = int(plan)

    # Формируем итоговый JSON
    result = {
        'metadata': {
            'source': os.path.basename(excel_path),
            'bars': list(BARS.values()),
            'description': 'План выручки по торговым точкам на каждый день'
        },
        'plans': {date: plans[date] for date in sorted(plans.keys()) if plans[date]}
    }

    # Сохраняем
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'Сохранено {len(result["plans"])} дней в {output_path}')
    return result


if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base_dir, 'план для сайта.xlsx')
    output_path = os.path.join(base_dir, 'data', 'bar_plans.json')

    result = convert_excel_to_json(excel_path, output_path)

    # Показываем пример
    print('\nПример данных:')
    for date in list(result['plans'].keys())[:3]:
        print(f'{date}: {result["plans"][date]}')

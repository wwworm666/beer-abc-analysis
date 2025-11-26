# -*- coding: utf-8 -*-
"""
Тестирование функций экспорта (Excel и PDF)
"""
import requests
import os
from datetime import datetime

BASE_URL = 'http://localhost:5000'
TEST_BAR = 'kremenchugskaya'
TEST_DATE_FROM = '2025-11-17'
TEST_DATE_TO = '2025-11-23'

print("="*80)
print("ТЕСТИРОВАНИЕ ЭКСПОРТА")
print("="*80)
print(f"\nБар: {TEST_BAR}")
print(f"Период: {TEST_DATE_FROM} - {TEST_DATE_TO}\n")

# Создаём папку для результатов
output_dir = 'test_exports'
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
    print(f"Создана папка: {output_dir}\n")

# ==========================================
# 1. ТЕСТ ЭКСПОРТА В EXCEL
# ==========================================
print("-"*80)
print("1. ТЕСТ: Экспорт в Excel")
print("-"*80)

try:
    response = requests.post(f'{BASE_URL}/api/export/excel', json={
        'bar': TEST_BAR,
        'date_from': TEST_DATE_FROM,
        'date_to': TEST_DATE_TO
    }, timeout=10)

    print(f"Статус ответа: HTTP {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"Размер файла: {len(response.content)} байт")

    if response.status_code == 200:
        # Сохраняем файл
        filename = f"{output_dir}/test_export_{TEST_BAR}_{TEST_DATE_FROM}.xlsx"
        with open(filename, 'wb') as f:
            f.write(response.content)

        print(f"[OK] УСПЕХ: Файл сохранён: {filename}")

        # Проверяем размер файла
        file_size = os.path.getsize(filename)
        if file_size > 1000:  # Минимум 1 KB
            print(f"[OK] Размер файла корректный: {file_size} байт")
        else:
            print(f"[WARN] ВНИМАНИЕ: Файл слишком маленький: {file_size} байт")
    else:
        print(f"[ERROR] ОШИБКА: HTTP {response.status_code}")
        print(f"Ответ сервера: {response.text[:500]}")

except Exception as e:
    print(f"[ERROR] ОШИБКА: {e}")

# ==========================================
# 2. ТЕСТ ЭКСПОРТА В PDF
# ==========================================
print("\n" + "-"*80)
print("2. ТЕСТ: Экспорт в PDF")
print("-"*80)

try:
    response = requests.post(f'{BASE_URL}/api/export/pdf', json={
        'bar': TEST_BAR,
        'date_from': TEST_DATE_FROM,
        'date_to': TEST_DATE_TO
    }, timeout=10)

    print(f"Статус ответа: HTTP {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"Размер файла: {len(response.content)} байт")

    if response.status_code == 200:
        # Определяем расширение по Content-Type
        content_type = response.headers.get('Content-Type', '')
        extension = '.pdf' if 'pdf' in content_type else '.html'

        # Сохраняем файл
        filename = f"{output_dir}/test_export_{TEST_BAR}_{TEST_DATE_FROM}{extension}"
        with open(filename, 'wb') as f:
            f.write(response.content)

        print(f"[OK] УСПЕХ: Файл сохранён: {filename}")

        # Проверяем размер файла
        file_size = os.path.getsize(filename)
        if file_size > 1000:  # Минимум 1 KB
            print(f"[OK] Размер файла корректный: {file_size} байт")
        else:
            print(f"[WARN] ВНИМАНИЕ: Файл слишком маленький: {file_size} байт")

        # Если это HTML, показываем начало
        if extension == '.html':
            print("\nПервые 200 символов HTML:")
            print(response.text[:200])
    else:
        print(f"[ERROR] ОШИБКА: HTTP {response.status_code}")
        print(f"Ответ сервера: {response.text[:500]}")

except Exception as e:
    print(f"[ERROR] ОШИБКА: {e}")

# ==========================================
# 3. ПРОВЕРКА ДАННЫХ
# ==========================================
print("\n" + "-"*80)
print("3. ПРОВЕРКА ДАННЫХ: Получение метрик")
print("-"*80)

try:
    response = requests.post(f'{BASE_URL}/api/dashboard-analytics', json={
        'bar': TEST_BAR,
        'date_from': TEST_DATE_FROM,
        'date_to': TEST_DATE_TO
    }, timeout=10)

    if response.status_code == 200:
        data = response.json()

        print("Основные метрики (факт):")
        print(f"  Выручка: {data.get('total_revenue', 0):,.2f} ₽")
        print(f"  Чеки: {data.get('total_checks', 0)}")
        print(f"  Средний чек: {data.get('avg_check', 0):,.2f} ₽")
        print(f"  Списания баллов: {data.get('loyalty_points_written_off', 0):,.2f} ₽")
        print(f"  Прибыль: {data.get('total_margin', 0):,.2f} ₽")
        print(f"  Наценка: {data.get('avg_markup', 0)*100:.2f}%")

        # Проверяем, что все ключи присутствуют
        required_keys = [
            'total_revenue', 'total_checks', 'avg_check',
            'loyalty_points_written_off', 'total_margin', 'avg_markup',
            'draft_share', 'bottles_share', 'kitchen_share'
        ]

        missing = [k for k in required_keys if k not in data]
        if missing:
            print(f"\n[WARN] Отсутствующие ключи: {missing}")
        else:
            print("\n[OK] Все необходимые ключи присутствуют")
    else:
        print(f"[ERROR] ОШИБКА: HTTP {response.status_code}")

except Exception as e:
    print(f"[ERROR] ОШИБКА: {e}")

# ==========================================
# ИТОГ
# ==========================================
print("\n" + "="*80)
print("ИТОГ ТЕСТИРОВАНИЯ")
print("="*80)
print(f"\nФайлы сохранены в папке: {output_dir}")
print("Откройте файлы, чтобы проверить их содержимое.\n")
print("="*80)

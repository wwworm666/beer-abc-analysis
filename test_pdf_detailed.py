# -*- coding: utf-8 -*-
"""Детальное тестирование PDF экспорта"""
import requests
import sys

BASE_URL = 'http://localhost:5000'
TEST_BAR = 'kremenchugskaya'
TEST_DATE_FROM = '2025-11-17'
TEST_DATE_TO = '2025-11-23'

print("="*80)
print("ДЕТАЛЬНЫЙ ТЕСТ PDF ЭКСПОРТА")
print("="*80)

try:
    print(f"\nОтправка запроса:")
    print(f"  URL: {BASE_URL}/api/export/pdf")
    print(f"  Бар: {TEST_BAR}")
    print(f"  Период: {TEST_DATE_FROM} - {TEST_DATE_TO}\n")

    response = requests.post(f'{BASE_URL}/api/export/pdf', json={
        'bar': TEST_BAR,
        'date_from': TEST_DATE_FROM,
        'date_to': TEST_DATE_TO
    }, timeout=30)

    print(f"Ответ сервера:")
    print(f"  Статус: HTTP {response.status_code}")
    print(f"  Причина: {response.reason}")
    print(f"\nЗаголовки ответа:")
    for key, value in response.headers.items():
        print(f"  {key}: {value}")

    print(f"\nРазмер контента: {len(response.content)} байт")

    # Проверяем начало контента
    first_bytes = response.content[:100]
    print(f"\nПервые 100 байт (hex): {first_bytes.hex()}")
    print(f"Первые 100 байт (text): {first_bytes[:100]}")

    # Определяем тип файла
    if first_bytes.startswith(b'%PDF'):
        print("\n[OK] Это настоящий PDF файл")
        file_ext = '.pdf'
    elif first_bytes.startswith(b'<!DOCTYPE') or first_bytes.startswith(b'<html'):
        print("\n[INFO] Это HTML файл (fallback)")
        file_ext = '.html'
    elif first_bytes.startswith(b'PK'):
        print("\n[ERROR] Это ZIP/Excel файл! Неправильный формат!")
        file_ext = '.xlsx'
    else:
        print("\n[WARN] Неизвестный формат файла")
        file_ext = '.bin'

    # Сохраняем файл
    filename = f"test_exports/pdf_detailed_test{file_ext}"
    with open(filename, 'wb') as f:
        f.write(response.content)

    print(f"\nФайл сохранён: {filename}")
    print(f"Расширение: {file_ext}")

    # Если это HTML, покажем начало
    if file_ext == '.html':
        print("\nНачало HTML (первые 500 символов):")
        print(response.text[:500])

except Exception as e:
    print(f"\n[ERROR] Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)

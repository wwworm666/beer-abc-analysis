"""Отладка данных Кременчугская 17.11-23.11"""
import requests
import json

# Запрашиваем данные
response = requests.post('http://localhost:5000/api/dashboard-analytics', json={
    'bar': 'kremenchugskaya',
    'date_from': '2025-11-17',
    'date_to': '2025-11-23'
})

if response.status_code == 200:
    data = response.json()
    print("Данные API для Кременчугская 17.11-23.11:")
    print(f"  Чеки (checks): {data.get('checks')}")
    print(f"  Средний чек (averageCheck): {data.get('averageCheck')}")
    print(f"  Выручка (revenue): {data.get('revenue')}")
    print()
    print("Расчет среднего чека:")
    if data.get('checks') and data.get('revenue'):
        avg = data.get('revenue') / data.get('checks')
        print(f"  revenue / checks = {data.get('revenue')} / {data.get('checks')} = {avg:.2f}")
else:
    print(f"Ошибка: {response.status_code}")
    print(response.text)

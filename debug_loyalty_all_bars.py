"""Проверка метрики списания баллов для всех баров 17.11-23.11"""
import requests

bars = [
    ('kremenchugskaya', 'Кременчугская'),
    ('bolshoy', 'Большой'),
    ('ligovskiy', 'Лиговский'),
    ('varshavskaya', 'Варшавская'),
    ('all', 'Общая')
]

print("Списания баллов (loyaltyWriteoffs) для всех баров 17.11-23.11:\n")

for bar_key, bar_name in bars:
    response = requests.post('http://localhost:5000/api/dashboard-analytics', json={
        'bar': bar_key,
        'date_from': '2025-11-17',
        'date_to': '2025-11-23'
    })

    if response.status_code == 200:
        data = response.json()
        loyalty = data.get('loyaltyWriteoffs', 0)
        print(f"  {bar_name:15s}: {loyalty:10.2f}")
    else:
        print(f"  {bar_name:15s}: Ошибка {response.status_code}")

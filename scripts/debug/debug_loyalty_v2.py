"""Проверка метрики списания баллов для Кременчугская 17.11-23.11"""
import requests

response = requests.post('http://localhost:5000/api/dashboard-analytics', json={
    'bar': 'kremenchugskaya',
    'date_from': '2025-11-17',
    'date_to': '2025-11-23'
})

if response.status_code == 200:
    data = response.json()
    print("Метрики для Кременчугская 17.11-23.11:")
    print(f"  loyaltyWriteoffs: {data.get('loyaltyWriteoffs')}")
    print(f"  Ожидаемое значение: 10657.00")
else:
    print(f"Ошибка: {response.status_code}")
    print(response.text)

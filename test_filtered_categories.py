"""
Проверка каких категорий товары остались после фильтрации
"""
import requests
import json

response = requests.get("http://localhost:5000/api/stocks/kitchen?bar=Общая", timeout=120)

if response.status_code == 200:
    data = response.json()
    items = data.get('items', [])

    # Группируем по категориям
    categories = {}
    for item in items:
        cat = item.get('category', 'Unknown')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item['name'])

    print(f"Vsego tovarov: {len(items)}\n")
    print("Kategorii tovarov:\n")
    for cat, products in sorted(categories.items(), key=lambda x: -len(x[1])):
        print(f"{cat}: {len(products)} tovarov")
        # Покажем первые 3 товара из категории
        for i, name in enumerate(products[:3], 1):
            print(f"  {i}. {name}")
        if len(products) > 3:
            print(f"  ... i eshe {len(products) - 3}")
        print()
else:
    print(f"Error: {response.status_code}")

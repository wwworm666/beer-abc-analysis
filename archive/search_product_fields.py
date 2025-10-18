"""
Поиск полей связанных с товарами/продуктами/ингредиентами в OLAP
"""

import json

# Читаем файл с полями
with open("olap_all_fields.json", "r", encoding="utf-8") as f:
    fields = json.load(f)

print("="*80)
print("ПОИСК ПОЛЕЙ СВЯЗАННЫХ С ТОВАРАМИ/ИНГРЕДИЕНТАМИ/КЕГАМИ")
print("="*80)

# Ключевые слова для поиска
keywords = ['product', 'товар', 'ingredient', 'ингредиент', 'состав',
            'рецепт', 'recipe', 'tech', 'карта', 'кег', 'keg', 'бочка']

found_fields = []

for field_key, field_data in fields.items():
    field_name = field_data.get('name', '').lower()
    field_key_lower = field_key.lower()

    # Проверяем ключевое слово в названии поля или ключе
    if any(keyword in field_name or keyword in field_key_lower for keyword in keywords):
        found_fields.append((field_key, field_data))

print(f"\nНайдено полей: {len(found_fields)}\n")

for field_key, field_data in found_fields:
    print(f"{field_key}")
    print(f"  Название: {field_data.get('name')}")
    print(f"  Тип: {field_data.get('type')}")
    print(f"  Группировка: {field_data.get('groupingAllowed')}")
    print(f"  Фильтрация: {field_data.get('filteringAllowed')}")
    print(f"  Агрегация: {field_data.get('aggregationAllowed')}")
    if 'tags' in field_data:
        print(f"  Теги: {', '.join(field_data['tags'])}")
    print()

print("="*80)
print("ПОЛЯ СВЯЗАННЫЕ С СЕБЕСТОИМОСТЬЮ (ProductCost*):")
print("="*80)

for field_key, field_data in fields.items():
    if 'productcost' in field_key.lower():
        print(f"\n{field_key}")
        print(f"  Название: {field_data.get('name')}")
        print(f"  Тип: {field_data.get('type')}")
        print(f"  Описание: Это поле рассчитывается через техкарты/рецепты")

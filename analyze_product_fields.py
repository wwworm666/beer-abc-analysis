# -*- coding: utf-8 -*-
import json
from collections import defaultdict

# Загружаем данные
with open("olap_fields_SALES.json", "r", encoding="utf-8") as f:
    fields = json.load(f)

# Категоризируем поля
categories = {
    "Основная информация о блюде": [],
    "Группы и категории": [],
    "Размеры и фасовки": [],
    "Цены и финансы": [],
    "Себестоимость и наценка": [],
    "Количество и продажи": [],
    "Идентификаторы": [],
    "Коды": [],
    "Пользовательские свойства и теги": [],
    "Состав и комбо": [],
    "Время приготовления": [],
    "Прочее": []
}

for field_key, field_data in fields.items():
    tags = field_data.get("tags", [])
    name = field_data.get("name", "")
    field_type = field_data.get("type", "")

    # Пропускаем поля, не связанные с блюдами
    if "Блюда" not in tags and "Себестоимость" not in tags:
        continue

    field_info = {
        "key": field_key,
        "name": name,
        "type": field_type,
        "agg": field_data.get("aggregationAllowed", False),
        "group": field_data.get("groupingAllowed", False),
        "filter": field_data.get("filteringAllowed", False)
    }

    # Основная информация
    if field_key in ["DishName", "DishFullName", "DishForeignName", "DishMeasureUnit", "DishType"]:
        categories["Основная информация о блюде"].append(field_info)
    # Группы и категории
    elif "Group" in field_key or "Category" in field_key or "Hierarchy" in field_key:
        categories["Группы и категории"].append(field_info)
    # Размеры
    elif "Size" in field_key:
        categories["Размеры и фасовки"].append(field_info)
    # Идентификаторы
    elif field_key.endswith(".Id") or field_key == "DishId":
        categories["Идентификаторы"].append(field_info)
    # Коды
    elif "Code" in field_key or "Num" in field_key:
        categories["Коды"].append(field_info)
    # Себестоимость и наценка
    elif "ProductCost" in field_key or "MarkUp" in field_key or "Profit" in field_key:
        categories["Себестоимость и наценка"].append(field_info)
    # Количество и суммы
    elif "Amount" in field_key or "Sum" in field_key or "Price" in field_key or "Discount" in field_key:
        categories["Цены и финансы"].append(field_info)
    # Теги и свойства
    elif "Tag" in field_key or "Tags" in field_key:
        categories["Пользовательские свойства и теги"].append(field_info)
    # Комбо
    elif "Combo" in field_key or "SoldWith" in field_key:
        categories["Состав и комбо"].append(field_info)
    # Приготовление
    elif "Cooking" in field_key or "ServicePrint" in field_key:
        categories["Время приготовления"].append(field_info)
    # Остальное
    else:
        categories["Прочее"].append(field_info)

# Вывод результатов
print("=" * 80)
print("ДОСТУПНЫЕ ПОЛЯ ТОВАРА/БЛЮДА В iiko OLAP API (SALES)")
print("=" * 80)
print()

total_fields = 0
for category, fields_list in categories.items():
    if not fields_list:
        continue

    print(f"\n[{category}] ({len(fields_list)} полей)")
    print("-" * 80)

    for field in sorted(fields_list, key=lambda x: x["name"]):
        flags = []
        if field["agg"]:
            flags.append("AGG")
        if field["group"]:
            flags.append("GROUP")
        if field["filter"]:
            flags.append("FILTER")

        flags_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {field['name']}")
        print(f"    API: {field['key']}")
        print(f"    Тип: {field['type']}{flags_str}")
        print()

        total_fields += 1

print("=" * 80)
print(f"ИТОГО: {total_fields} полей, связанных с товаром/блюдом")
print("=" * 80)
print()
print("Легенда:")
print("  AGG    - поддерживает агрегацию (суммирование)")
print("  GROUP  - поддерживает группировку")
print("  FILTER - поддерживает фильтрацию")

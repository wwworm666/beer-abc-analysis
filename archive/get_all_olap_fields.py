"""
Получаем список ВСЕХ доступных полей OLAP API
Используем endpoint /v2/reports/olap/columns
"""

from iiko_api import IikoAPI
import requests
import json

print("="*80)
print("POLUCHAEM VSE DOSTUPNYE POLYA OLAP API")
print("="*80)

# Подключаемся
api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya k API")
    exit()

# Запрашиваем список полей для SALES отчёта
url = f"{api.base_url}/v2/reports/olap/columns"
params = {
    "key": api.token,
    "reportType": "SALES"
}

print("\nZaprashivaem dostupnye polya dlya reportType=SALES...\n")

try:
    response = requests.get(url, params=params)

    if response.status_code == 200:
        fields_data = response.json()

        # Сохраняем полный список
        with open("olap_all_fields.json", "w", encoding="utf-8") as f:
            json.dump(fields_data, f, indent=2, ensure_ascii=False)

        print(f"[OK] Polucheno poley: {len(fields_data)}")
        print("[SAVED] olap_all_fields.json\n")

        # Ищем поля связанные с продуктами/ингредиентами/товарами
        print("="*80)
        print("POLYA SVYAZANNYE S PRODUKTAMI/INGREDIENTAMI:")
        print("="*80)

        interesting_keywords = ['product', 'ingredient', 'keg', 'товар', 'ингредиент', 'кег', 'бочка']

        for field in fields_data:
            field_name = field.get('name', '').lower()
            field_caption = field.get('caption', '').lower()

            # Проверяем название и описание поля
            if any(keyword in field_name or keyword in field_caption for keyword in interesting_keywords):
                print(f"\n{field.get('name')}")
                print(f"  Caption: {field.get('caption')}")
                print(f"  Type: {field.get('type')}")
                print(f"  Grouping: {field.get('groupingAllowed')}")
                print(f"  Filtering: {field.get('filteringAllowed')}")
                print(f"  Aggregation: {field.get('aggregationAllowed')}")

        print("\n" + "="*80)
        print("POLYA SVYAZANNYE S DISH (dlya sravneniya):")
        print("="*80)

        dish_fields = [f for f in fields_data if 'dish' in f.get('name', '').lower()]
        for field in dish_fields[:10]:  # Показываем первые 10
            print(f"\n{field.get('name')}")
            print(f"  Caption: {field.get('caption')}")

    else:
        print(f"[ERROR] Status: {response.status_code}")
        print(f"Response: {response.text}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

api.logout()

print("\n" + "="*80)
print("GOTOVO! Prover'te olap_all_fields.json")
print("="*80)

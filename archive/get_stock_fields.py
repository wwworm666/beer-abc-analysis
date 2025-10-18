"""
Получаем список полей для STOCK отчёта
"""

from iiko_api import IikoAPI
import requests
import json

print("="*80)
print("POLUCHAEM POLYA DLYa STOCK OTCHETA")
print("="*80)

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya k API")
    exit()

# Запрашиваем список полей для STOCK отчёта
url = f"{api.base_url}/v2/reports/olap/columns"
params = {
    "key": api.token,
    "reportType": "STOCK"  # Складской отчёт вместо SALES
}

print("\nZaprashivaem dostupnye polya dlya reportType=STOCK...\n")

try:
    response = requests.get(url, params=params)

    if response.status_code == 200:
        fields_data = response.json()

        # Сохраняем полный список
        with open("olap_stock_fields.json", "w", encoding="utf-8") as f:
            json.dump(fields_data, f, indent=2, ensure_ascii=False)

        print(f"[OK] Polucheno poley: {len(fields_data)}")
        print("[SAVED] olap_stock_fields.json\n")

        # Ищем поля связанные с продуктами/товарами
        print("="*80)
        print("POLYA SVYAZANNYE S TOVARAMI/PRODUKTAMI/KEGAMI:")
        print("="*80)

        interesting_keywords = ['product', 'товар', 'кег', 'бочка', 'ingredient', 'ингредиент', 'item', 'пиво', 'beer']

        count = 0
        for field_name, field_info in fields_data.items():
            field_caption = field_info.get('name', '').lower()
            field_name_lower = field_name.lower()

            # Проверяем название и описание поля
            if any(keyword in field_name_lower or keyword in field_caption for keyword in interesting_keywords):
                print(f"\n{field_name}")
                print(f"  Name: {field_info.get('name')}")
                print(f"  Type: {field_info.get('type')}")
                print(f"  Grouping: {field_info.get('groupingAllowed')}")
                print(f"  Aggregation: {field_info.get('aggregationAllowed')}")
                count += 1

        print(f"\n[FOUND] Naydenopoley: {count}")

        # Также покажем все поля для группировки (grouping)
        print("\n" + "="*80)
        print("VSE POLYA S VOZMOZHNOSTYU GRUPPIROVKI (groupingAllowed=true):")
        print("="*80)

        grouping_fields = [k for k,v in fields_data.items() if v.get('groupingAllowed')]
        print(f"\nVsego poley dlya gruppirovki: {len(grouping_fields)}")
        print("\nPervye 20 poley:")
        for field in grouping_fields[:20]:
            print(f"  {field:50s} -> {fields_data[field].get('name')}")

    else:
        print(f"[ERROR] Status: {response.status_code}")
        print(f"Response: {response.text}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

api.logout()

print("\n" + "="*80)
print("GOTOVO! Prover'te olap_stock_fields.json")
print("="*80)

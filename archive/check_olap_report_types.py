"""
Проверяем какие типы отчетов доступны в OLAP API
Мы знаем про SALES и STOCK
Может есть еще какие-то типы для получения рецептур?
"""

from iiko_api import IikoAPI
import requests

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

print("="*80)
print("PROVERYAEM DOSTUPNYE TIPY OTCHETOV V OLAP")
print("="*80)

# Известные типы
known_types = ["SALES", "STOCK"]

# Пробуем другие возможные типы
possible_types = [
    "PRODUCTS",
    "DISHES",
    "RECIPES",
    "INGREDIENTS",
    "COMPOSITION",
    "TECH_CARDS",
    "NOMENCLATURE",
    "ASSORTMENT",
    "MENU"
]

all_types_to_test = known_types + possible_types

for report_type in all_types_to_test:
    url = f"{api.base_url}/v2/reports/olap/columns"
    params = {
        "key": api.token,
        "reportType": report_type
    }

    print(f"\n[TEST] reportType={report_type}")

    try:
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"  [OK] Rabotaet! Poley: {len(data)}")

            # Если это новый тип, сохраняем
            if report_type not in known_types:
                filename = f"olap_fields_{report_type}.json"
                import json
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  [SAVED] {filename}")

        elif response.status_code == 400:
            error_text = response.text
            if "Invalid" in error_text or "Unknown" in error_text:
                print(f"  [NOT SUPPORTED] Etot tip ne podderzhivaetsya")
            else:
                print(f"  Error 400: {response.text[:100]}")
        else:
            print(f"  Status {response.status_code}: {response.text[:100]}")

    except Exception as e:
        print(f"  Exception: {e}")

api.logout()

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)

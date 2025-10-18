"""
Проверяем все доступные типы отчётов в iiko OLAP API
"""

from iiko_api import IikoAPI
import requests

print("="*80)
print("PROVERKA VSEKH DOSTUPNYKH TIPOV OTCHETOV")
print("="*80)

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

# Известные типы отчётов
known_types = ["SALES", "STOCK", "INGREDIENTS", "PRODUCTS", "CONSUMPTION", "WRITEOFF"]

url = f"{api.base_url}/v2/reports/olap/columns"
params_base = {"key": api.token}

print("\nProveryaem kakie tipy otchetov dostupny:\n")

available_types = []

for report_type in known_types:
    params = params_base.copy()
    params["reportType"] = report_type

    try:
        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()
            field_count = len(data) if isinstance(data, dict) else 0
            print(f"[OK] {report_type:20s} - {field_count} poley")
            available_types.append(report_type)
        elif response.status_code == 400:
            print(f"[NOT FOUND] {report_type:20s} - ne podderzhivaetsya")
        else:
            print(f"[ERROR] {report_type:20s} - status {response.status_code}")

    except Exception as e:
        print(f"[ERROR] {report_type:20s} - {e}")

print("\n" + "="*80)
print("DOSTUPNYE TIPY OTCHETOV:")
print("="*80)

for rt in available_types:
    print(f"  - {rt}")

api.logout()

print("\n" + "="*80)
print("VYVOD:")
print("="*80)
print("""
Esli INGREDIENTS/PRODUCTS ne dostupny, znachit:

1. V SALES otchete uzhe est dannye po raskhodu cherez ProductCostBase
2. Tekuschiy podkhod (porci × obyom) PRAVILEN, tak kak:
   - iiko avtomaticheski spisyvaet ingredienty po tekhkarte
   - ProductCostBase.ProductCost otrazhaet fakticheskiy raskhod
   - Razniza mezhdu OLAP i otchetom v Office mozhet byt iz-za:
     * Vremennykh ram (raznye periody)
     * Filtrov (raznye bary/sklad)
     * Spisaniy ne svyazannykh s prodazhami (degustacii, brak)

3. Dlya tochnogo sravneniya nado:
   - Proverit TOCHNO ODINAKOVYE parametry v oboikh otchetakh
   - Uchest chto v Office mogut byt agregirovan dannye po-drugomu
""")

# -*- coding: utf-8 -*-
"""Точечная проверка одного GTIN: ищем во всех product-группах через
/cises/search. Используется для отладки «нет в ЧЗ»."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chz import load_token, make_request, CHZ_BASE_URL_V4

target = sys.argv[1] if len(sys.argv) > 1 else "04631169328016"
print(f"Probing GTIN: {target}")

token = load_token()
if not token:
    print("NO TOKEN")
    sys.exit(1)

groups_to_try = [
    "beer", "nabeer", "softdrinks", "alcohol",
    "otp", "bio", "milk", "conserve", "meat",
    "vegetableoil", "sweets", "petfood", "frozen",
]

found_in = []
for pg in groups_to_try:
    url = f"{CHZ_BASE_URL_V4}/cises/search"
    payload = {
        "page": 0, "limit": 10,
        "filter": {"productGroups": [pg], "gtins": [target]},
    }
    headers = {"Authorization": f"Bearer {token}"}
    s, resp = make_request(url, method="POST", data=payload, headers=headers)
    items = resp.get("result", []) if isinstance(resp, dict) else []
    if s == 200 and items:
        found_in.append(pg)
        print(f"\n[FOUND] productGroup={pg}: {len(items)} codes")
        for i in items[:5]:
            print(f"  cis={i.get('cis', '?')[:40]}")
            print(f"    gtin={i.get('gtin')} status={i.get('status')} statusEx={i.get('statusEx')}")
            print(f"    ownerInn={i.get('ownerInn')} producerInn={i.get('producerInn')}")
            print(f"    productGroup={i.get('productGroup')} packageType={i.get('packageType')}")
            print(f"    expirationDate={i.get('expirationDate')} productionDate={i.get('productionDate')}")
            print(f"    emissionType={i.get('emissionType')}")
    elif s == 200:
        pass  # empty
    else:
        print(f"  {pg}: HTTP {s}")

if not found_in:
    print(f"\nGTIN {target} НЕ найден ни в одной из {len(groups_to_try)} групп.")

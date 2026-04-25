# -*- coding: utf-8 -*-
"""Тест разных параметров фильтра в /cises/search для пива."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chz import load_token, make_request, CHZ_BASE_URL_V4, INN_ORG

token = load_token()
if not token:
    print("[ERR] No token")
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}
url = f"{CHZ_BASE_URL_V4}/cises/search"

def count_all(filter_dict, label):
    """Подсчёт всех кодов с пагинацией."""
    print(f"\n=== {label} ===")
    print(f"Filter: {filter_dict}")
    total = 0
    page = 0
    statuses = {}
    while page < 50:  # max 5000 codes
        payload = {"page": page, "limit": 100, "filter": filter_dict}
        status, resp = make_request(url, method="POST", data=payload, headers=headers)
        if status != 200:
            print(f"  [ERR] HTTP {status}: {resp}")
            return
        items = resp.get("result", [])
        for it in items:
            s = it.get("status", "?")
            statuses[s] = statuses.get(s, 0) + 1
        total += len(items)
        if resp.get("isLastPage") or len(items) < 100:
            break
        page += 1
    print(f"  Total: {total} codes, statuses: {statuses}")

# 1. Текущий подход: ownerInn
count_all({"productGroups": ["beer"], "ownerInn": INN_ORG}, "ownerInn (текущий)")

# 2. participantInn (как в CSV-экспорте)
count_all({"productGroups": ["beer"], "participantInn": INN_ORG}, "participantInn")

# 3. participants (массив)
count_all({"productGroups": ["beer"], "participants": [INN_ORG]}, "participants[]")

# 4. Без фильтра по статусу — добавить status=INTRODUCED
count_all({"productGroups": ["beer"], "ownerInn": INN_ORG, "statuses": ["INTRODUCED"]}, "ownerInn + statuses[INTRODUCED]")

# 5. С packageType=UNIT (как в CSV-экспорте)
count_all({"productGroups": ["beer"], "ownerInn": INN_ORG, "packageTypes": ["UNIT"]}, "ownerInn + packageTypes[UNIT]")

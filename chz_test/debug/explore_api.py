# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chz import load_token, make_request, CHZ_BASE_URL, CHZ_BASE_URL_V4, INN_ORG

token = load_token()
if not token:
    print("No token")
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}

# 1. Try receipt/search with different filter params
print("=== receipt/search (various filters) ===")
url = f"{CHZ_BASE_URL}/receipt/search"

# Try with participantInn
payload = {"page": 0, "limit": 5, "filter": {"participantInn": INN_ORG}}
status, resp = make_request(url, method="POST", data=payload, headers=headers)
print(f"participantInn: {status} - {resp}")

# Try with empty filter
payload = {"page": 0, "limit": 5, "filter": {}}
status, resp = make_request(url, method="POST", data=payload, headers=headers)
print(f"empty filter: {status} - {resp}")

# 2. Try doc/list with different pg values
print("\n=== doc/list (various pg) ===")
for pg in ["beer", "nabeer", "softdrinks", "milk"]:
    url = f"{CHZ_BASE_URL_V4}/doc/list?pg={pg}&page=0&perPage=5"
    status, resp = make_request(url, headers=headers)
    if status == 200:
        total = resp.get("total", 0)
        print(f"  {pg}: {total} docs")
    else:
        print(f"  {pg}: {status} - {resp}")

# 3. Try cises/search with ALL pages for beer to get total count
print("\n=== cises/search beer (all pages) ===")
url = f"{CHZ_BASE_URL_V4}/cises/search"
all_items = []
page = 0
while True:
    payload = {
        "page": page,
        "limit": 100,
        "filter": {"productGroups": ["beer"]}
    }
    status, resp = make_request(url, method="POST", data=payload, headers=headers)
    if status != 200:
        print(f"  Page {page}: ERROR {status}")
        break
    items = resp.get("result", [])
    is_last = resp.get("isLastPage", True)
    all_items.extend(items)
    print(f"  Page {page}: {len(items)} items (total {len(all_items)}) isLast={is_last}")
    if is_last or len(items) < 100 or len(all_items) >= 10000:
        break
    page += 1

# Summary
introduced = [i for i in all_items if i.get("status") == "INTRODUCED"]
retired = [i for i in all_items if i.get("status") == "RETIRED"]
gtins_introduced = set(i.get("gtin") for i in introduced)
print(f"\n  TOTAL beer codes: {len(all_items)}")
print(f"  INTRODUCED: {len(introduced)} ({len(gtins_introduced)} GTINs)")
print(f"  RETIRED: {len(retired)}")

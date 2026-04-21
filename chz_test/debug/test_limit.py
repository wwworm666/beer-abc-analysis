# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chz import load_token, make_request, CHZ_BASE_URL_V4

token = load_token()
headers = {"Authorization": f"Bearer {token}"}

# Test with limit=1000
payload = {"page": 0, "limit": 1000, "filter": {"productGroups": ["beer"]}}
status, resp = make_request(f"{CHZ_BASE_URL_V4}/cises/search", method="POST", data=payload, headers=headers)
items = resp.get("result", [])
is_last = resp.get("isLastPage")
print(f"status={status} items={len(items)} isLast={is_last}")

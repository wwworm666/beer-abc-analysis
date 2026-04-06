import json

with open(r'C:\chz_test\debug\cises_search.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

result = d.get("result", [])
print(f"result items: {len(result)}")
print(f"total: {d.get('total', 'MISSING')}")
print(f"page: {d.get('page', 'MISSING')}")
print(f"limit: {d.get('limit', 'MISSING')}")
print(f"keys: {list(d.keys())}")

gtins = set()
producers = set()
statuses = set()
products = set()
expirations = set()

for item in result:
    gtins.add(item.get("gtin"))
    producers.add(item.get("producerInn"))
    statuses.add(item.get("status"))
    products.add(item.get("productGroup"))
    exp = item.get("expirationDate", "")[:10] if item.get("expirationDate") else ""
    expirations.add(exp)

print(f"\nGTINs ({len(gtins)}): {gtins}")
print(f"Producers: {producers}")
print(f"Statuses: {statuses}")
print(f"Product groups: {products}")
print(f"Expiration dates: {expirations}")

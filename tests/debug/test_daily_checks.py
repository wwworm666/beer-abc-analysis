"""
Подсчёт чеков по дням для Новаев Артемий
чтобы найти где именно расхождение
"""
from core.olap_reports import OlapReports

def main():
    olap = OlapReports()
    if not olap.connect():
        print("Failed to connect")
        return

    employee_name = "Новаев Артемий"

    request = {
        "reportType": "SALES",
        "groupByRowFields": ["WaiterName", "OpenDate.Typed"],
        "groupByColFields": [],
        "aggregateFields": ["OrderNum"],
        "filters": {
            "OpenDate.Typed": {
                "filterType": "DateRange",
                "periodType": "CUSTOM",
                "from": "2026-01-01",
                "to": "2026-01-22"
            },
            "WaiterName": {
                "filterType": "IncludeValues",
                "values": [employee_name, "Артемий Новаев"]
            },
            "DeletedWithWriteoff": {
                "filterType": "IncludeValues",
                "values": ["NOT_DELETED"]
            },
            "OrderDeleted": {
                "filterType": "IncludeValues",
                "values": ["NOT_DELETED"]
            }
        }
    }

    import requests as req
    url = f"{olap.api.base_url}/v2/reports/olap"
    response = req.post(url, params={"key": olap.token}, json=request, timeout=60)

    if response.status_code == 200:
        data = response.json()
        print("=" * 50)
        print(f"Чеки по дням: {employee_name}")
        print("=" * 50)

        total = 0
        if isinstance(data, dict) and "data" in data:
            rows = sorted(data["data"], key=lambda x: x.get("OpenDate.Typed", ""))
            for row in rows:
                date = row.get("OpenDate.Typed", "?")
                checks = row.get("OrderNum", 0)
                total += checks
                print(f"  {date}: {checks:3} чеков")

        print("-" * 50)
        print(f"  ИТОГО: {total} чеков")
        print("=" * 50)
    else:
        print(f"ERROR: {response.status_code}")

    olap.disconnect()


if __name__ == "__main__":
    main()

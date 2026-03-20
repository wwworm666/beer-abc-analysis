"""
Тест: найти правильный формат дат для соответствия с iiko UI
Цель: получить 233 чека для Новаев Артемий за 01.01-22.01
"""
from core.olap_reports import OlapReports

def test_single(field, employee_name, date_from, date_to, olap, filters_mode="full"):
    try:
        request = {
            "reportType": "SALES",
            "groupByRowFields": ["WaiterName"],
            "groupByColFields": [],
            "aggregateFields": [field],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": date_from,
                    "to": date_to
                },
                "WaiterName": {
                    "filterType": "IncludeValues",
                    "values": [employee_name, "Артемий Новаев"]
                }
            }
        }

        # Добавляем фильтры удаления только если full mode
        if filters_mode == "full":
            request["filters"]["DeletedWithWriteoff"] = {
                "filterType": "IncludeValues",
                "values": ["NOT_DELETED"]
            }
            request["filters"]["OrderDeleted"] = {
                "filterType": "IncludeValues",
                "values": ["NOT_DELETED"]
            }

        import requests as req
        url = f"{olap.api.base_url}/v2/reports/olap"
        response = req.post(url, params={"key": olap.token}, json=request, timeout=30)

        if response.status_code == 200:
            data = response.json()
            total = 0
            if isinstance(data, dict) and "data" in data:
                for row in data["data"]:
                    total += row.get(field, 0)
            return total
        return -1
    except Exception as e:
        print(f"ERROR: {e}")
        return -1


def test_date_variants():
    olap = OlapReports()
    if not olap.connect():
        print("Failed to connect")
        return

    employee_name = "Новаев Артемий"
    base_from = "2026-01-01"
    base_to = "2026-01-22"

    variants = [
        ("01-22", base_from, base_to),
        ("01-21", base_from, "2026-01-21"),
        ("01-23", base_from, "2026-01-23"),
    ]

    print("=" * 70)
    print(f"Ищем: 233 чека для {employee_name}")
    print("=" * 70)

    # Тест 1: OrderNum с полными фильтрами
    print("\n=== OrderNum + DeletedWithWriteoff + OrderDeleted ===")
    for name, df, dt in variants:
        r = test_single("OrderNum", employee_name, df, dt, olap, "full")
        m = "✓✓✓ MATCH!" if r == 233 else ""
        print(f"  {name:10} | {r:4} {m}")

    # Тест 2: OrderNum БЕЗ фильтров удаления
    print("\n=== OrderNum БЕЗ фильтров удаления ===")
    for name, df, dt in variants:
        r = test_single("OrderNum", employee_name, df, dt, olap, "minimal")
        m = "✓✓✓ MATCH!" if r == 233 else ""
        print(f"  {name:10} | {r:4} {m}")

    # Тест 3: UniqOrderId.OrdersCount с полными фильтрами
    print("\n=== UniqOrderId.OrdersCount + полные фильтры ===")
    for name, df, dt in variants:
        r = test_single("UniqOrderId.OrdersCount", employee_name, df, dt, olap, "full")
        m = "✓✓✓ MATCH!" if r == 233 else ""
        print(f"  {name:10} | {r:4} {m}")

    # Тест 4: UniqOrderId.OrdersCount БЕЗ фильтров
    print("\n=== UniqOrderId.OrdersCount БЕЗ фильтров удаления ===")
    for name, df, dt in variants:
        r = test_single("UniqOrderId.OrdersCount", employee_name, df, dt, olap, "minimal")
        m = "✓✓✓ MATCH!" if r == 233 else ""
        print(f"  {name:10} | {r:4} {m}")

    # Тест 5: С фильтром PayTypes (только оплаченные)
    print("\n=== OrderNum + PayTypes (CASH, CARD) ===")
    r = test_with_pay_types("OrderNum", employee_name, base_from, base_to, olap)
    m = "✓✓✓ MATCH!" if r == 233 else ""
    print(f"  01-22      | {r:4} {m}")

    # Тест 6: Только CLOSED заказы
    print("\n=== OrderNum + OrderClosed=CLOSED ===")
    r = test_closed_orders("OrderNum", employee_name, base_from, base_to, olap)
    m = "✓✓✓ MATCH!" if r == 233 else ""
    print(f"  01-22      | {r:4} {m}")

    olap.disconnect()
    print("\n" + "=" * 70)


def test_with_pay_types(field, employee_name, date_from, date_to, olap):
    try:
        request = {
            "reportType": "SALES",
            "groupByRowFields": ["WaiterName"],
            "groupByColFields": [],
            "aggregateFields": [field],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": date_from,
                    "to": date_to
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
                },
                "PayTypes": {
                    "filterType": "ExcludeValues",
                    "values": ["Без выручки", "Сертификат"]
                }
            }
        }

        import requests as req
        url = f"{olap.api.base_url}/v2/reports/olap"
        response = req.post(url, params={"key": olap.token}, json=request, timeout=30)

        if response.status_code == 200:
            data = response.json()
            total = 0
            if isinstance(data, dict) and "data" in data:
                for row in data["data"]:
                    total += row.get(field, 0)
            return total
        return -1
    except Exception as e:
        print(f"ERROR: {e}")
        return -1


def test_closed_orders(field, employee_name, date_from, date_to, olap):
    try:
        request = {
            "reportType": "SALES",
            "groupByRowFields": ["WaiterName"],
            "groupByColFields": [],
            "aggregateFields": [field],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": date_from,
                    "to": date_to
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
                },
                "OpenDate.OrderClose": {
                    "filterType": "IncludeValues",
                    "values": ["CLOSED"]
                }
            }
        }

        import requests as req
        url = f"{olap.api.base_url}/v2/reports/olap"
        response = req.post(url, params={"key": olap.token}, json=request, timeout=30)

        if response.status_code == 200:
            data = response.json()
            total = 0
            if isinstance(data, dict) and "data" in data:
                for row in data["data"]:
                    total += row.get(field, 0)
            return total
        return -1
    except Exception as e:
        print(f"ERROR: {e}")
        return -1


def test_close_date(field, employee_name, date_from, date_to, olap):
    try:
        request = {
            "reportType": "SALES",
            "groupByRowFields": ["WaiterName"],
            "groupByColFields": [],
            "aggregateFields": [field],
            "filters": {
                "CloseDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": date_from,
                    "to": date_to
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
        response = req.post(url, params={"key": olap.token}, json=request, timeout=30)

        if response.status_code == 200:
            data = response.json()
            total = 0
            if isinstance(data, dict) and "data" in data:
                for row in data["data"]:
                    total += row.get(field, 0)
            return total
        return -1
    except Exception as e:
        print(f"ERROR: {e}")
        return -1


if __name__ == "__main__":
    test_date_variants()

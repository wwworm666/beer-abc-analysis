"""Просмотр полей OLAP для поиска поля со скидками"""
from core.olap_reports import OlapReports
import json

olap = OlapReports()

if olap.connect():
    # Получаем данные по разливному
    draft_data = olap.get_draft_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')

    if draft_data and 'data' in draft_data and len(draft_data['data']) > 0:
        print("Первая запись из OLAP данных:")
        print(json.dumps(draft_data['data'][0], indent=2, ensure_ascii=False))
        print()
        print("Доступные поля:")
        for key in draft_data['data'][0].keys():
            value = draft_data['data'][0][key]
            print(f"  {key}: {value}")

    olap.disconnect()

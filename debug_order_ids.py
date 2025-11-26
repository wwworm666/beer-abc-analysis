"""Проверка всех полей связанных с заказами"""
from core.olap_reports import OlapReports

olap = OlapReports()

if olap.connect():
    draft_data = olap.get_draft_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    
    if draft_data and 'data' in draft_data and len(draft_data['data']) > 0:
        print("Все поля в OLAP записи разливного:")
        for key in sorted(draft_data['data'][0].keys()):
            value = draft_data['data'][0][key]
            print(f"  {key}: {value} ({type(value).__name__})")
    
    olap.disconnect()

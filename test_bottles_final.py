"""
Финальный тест для проверки работы endpoint /api/stocks/bottles
"""
import requests
import json

def main():
    print("\n" + "="*80)
    print("ТЕСТ ENDPOINT /api/stocks/bottles")
    print("="*80)

    url = "http://localhost:5000/api/stocks/bottles"
    params = {'bar': 'Большой пр. В.О'}

    print(f"\nЗапрос: {url}")
    print(f"Параметры: {params}\n")

    try:
        response = requests.get(url, params=params, timeout=60)

        if response.status_code == 200:
            data = response.json()

            print("[OK] Запрос выполнен успешно!")
            print(f"\nСтатистика:")
            print(f"  Всего позиций: {data.get('total_items', 0)}")
            print(f"  Требуют пополнения: {data.get('low_stock_count', 0)}")

            items = data.get('items', [])
            if items:
                print(f"\nПервые 20 позиций:")
                print("-" * 80)

                for i, item in enumerate(items[:20], 1):
                    status_text = {
                        'low': 'НИЗКИЙ',
                        'medium': 'СРЕДНИЙ',
                        'high': 'ВЫСОКИЙ'
                    }.get(item.get('stock_level'), 'НЕИЗВЕСТНО')

                    print(f"{i:2}. {item.get('name', 'Без названия')}")
                    print(f"    Поставщик: {item.get('category', 'Не указан')}")
                    print(f"    Остаток: {item.get('stock', 0)} шт | Ср. продажи: {item.get('avg_sales', 0)} шт/день | Статус: {status_text}")
                    print()

                # Группируем по поставщикам
                suppliers = {}
                for item in items:
                    supplier = item.get('category', 'Без поставщика')
                    if supplier not in suppliers:
                        suppliers[supplier] = 0
                    suppliers[supplier] += 1

                print("\n" + "="*80)
                print("СТАТИСТИКА ПО ПОСТАВЩИКАМ:")
                print("-" * 80)

                for supplier, count in sorted(suppliers.items(), key=lambda x: x[1], reverse=True):
                    print(f"{supplier:40} - {count} позиций")

            else:
                print("\n[WARNING] Нет данных")

        else:
            print(f"[ERROR] Ошибка запроса: {response.status_code}")
            print(f"Ответ: {response.text[:500]}")

    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)

if __name__ == '__main__':
    main()

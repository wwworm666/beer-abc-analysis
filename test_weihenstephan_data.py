#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тест для получения ВСЕХ возможных данных по позиции "Вайнштефан Хефе Вайсбир"
из iiko API OLAP отчетов
"""

import json
from datetime import datetime, timedelta
from core.olap_reports import OlapReports

def test_all_fields():
    """Запросить все возможные поля для Вайнштефан Хефе Вайсбир"""

    print("="*80)
    print("ТЕСТ: Запрос всех доступных полей для Вайнштефан Хефе Вайсбир")
    print("="*80)

    # Подключаемся к iiko
    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API")
        return

    try:
        # Период: последние 30 дней
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        print(f"\nПериод: {date_from} - {date_to}")

        # Создаем запрос с МАКСИМАЛЬНО возможным набором полей
        # согласно документации iiko API
        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "Store.Name",
                "DishName",
                "DishGroup.ThirdParent",
                "DishForeignName",
                "OpenDate.Typed",
                "DishId"  # Добавляем ID блюда
            ],
            "groupByColFields": [],
            "aggregateFields": [
                # Основные поля (проверенные)
                "UniqOrderId",
                "UniqOrderId.OrdersCount",
                "DishAmountInt",
                "DishDiscountSumInt",
                "DiscountSum",
                "ProductCostBase.ProductCost",
                "ProductCostBase.MarkUp",
                "DishSumInt",
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": date_from,
                    "to": date_to
                },
                "DishGroup.TopParent": {
                    "filterType": "IncludeValues",
                    "values": ["Напитки Фасовка"]
                },
                # Фильтр по конкретному названию
                "DishName": {
                    "filterType": "IncludeValues",
                    "values": ["Вайнштефан Хефе Вайсбир, светлое, 0,500 бут."]
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

        print("\n[REQUEST] Отправляем запрос с расширенным набором полей...")
        print(f"Запрашиваемые aggregate поля: {len(request['aggregateFields'])} штук")

        # Отправляем запрос
        url = f"{olap.api.base_url}/v2/reports/olap"
        params = {"key": olap.token}
        headers = {"Content-Type": "application/json"}

        import requests
        response = requests.post(
            url,
            params=params,
            json=request,
            headers=headers,
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()

            print(f"\n[OK] Получен ответ!")
            print(f"Количество записей: {len(data.get('data', []))}")

            # Сохраняем полный ответ в JSON
            with open('weihenstephan_full_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"\n[SAVE] Полный ответ сохранен в: weihenstephan_full_data.json")

            # Анализируем данные
            if data.get('data'):
                print(f"\n{'='*80}")
                print("АНАЛИЗ ДАННЫХ")
                print(f"{'='*80}")

                # Показываем первую запись полностью
                first_record = data['data'][0]
                print(f"\nПервая запись (ПОЛНОСТЬЮ):")
                print(json.dumps(first_record, ensure_ascii=False, indent=2))

                # Анализируем поля наценки
                print(f"\n{'='*80}")
                print("АНАЛИЗ НАЦЕНОК ПО ВСЕМ ЗАПИСЯМ:")
                print(f"{'='*80}")

                markups = []
                for record in data['data']:
                    markup = record.get('ProductCostBase.MarkUp')
                    date = record.get('OpenDate.Typed')
                    cost = record.get('ProductCostBase.ProductCost')
                    profit = record.get('ProductCostBase.Profit')
                    dish_sum = record.get('DishDiscountSumInt')

                    markups.append({
                        'date': date,
                        'markup': markup,
                        'cost': cost,
                        'profit': profit,
                        'dish_sum': dish_sum
                    })

                    print(f"\nДата: {date}")
                    print(f"  Наценка (MarkUp): {markup} ({markup*100:.2f}%)")
                    print(f"  Себестоимость: {cost}")
                    print(f"  Прибыль: {profit}")
                    print(f"  Сумма блюда: {dish_sum}")

                    # Проверяем формулу наценки
                    if cost and cost > 0:
                        calculated_markup = (dish_sum / cost) - 1 if dish_sum else 0
                        print(f"  Расчетная наценка (DishSum/Cost - 1): {calculated_markup:.4f} ({calculated_markup*100:.2f}%)")

                print(f"\n{'='*80}")
                print(f"ИТОГО:")
                print(f"  Минимальная наценка: {min(m['markup'] for m in markups if m['markup']):.4f}")
                print(f"  Максимальная наценка: {max(m['markup'] for m in markups if m['markup']):.4f}")
                print(f"  Уникальные значения наценки: {sorted(set(m['markup'] for m in markups if m['markup']))}")
                print(f"{'='*80}")

        else:
            print(f"[ERROR] Ошибка запроса: {response.status_code}")
            print(f"Ответ сервера: {response.text}")

    finally:
        olap.disconnect()

if __name__ == "__main__":
    test_all_fields()

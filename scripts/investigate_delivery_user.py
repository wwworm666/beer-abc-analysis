"""
Исследуем заказы на "Пользователь для централизованной доставки"
Цель: понять откуда берутся эти заказы и что это за операции
"""

import pandas as pd
from datetime import datetime, timedelta
from core.olap_reports import OlapReports

def investigate_delivery_user():
    """Анализируем заказы на пользователя доставки"""

    print("\n" + "="*70)
    print("ИССЛЕДОВАНИЕ: Пользователь для централизованной доставки")
    print("="*70 + "\n")

    # Подключаемся к API
    olap = OlapReports()
    if not olap.connect():
        print("[ОШИБКА] Не удалось подключиться к iiko API")
        return

    print("[OK] Подключение к iiko API установлено\n")

    # Запрашиваем данные за последний месяц
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    print(f"Период анализа: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}\n")

    # Запрашиваем OLAP отчет с максимальным количеством полей
    df = olap.get_sales_report(
        start_date=start_date,
        end_date=end_date,
        group_by_rows=[
            'OpenDate.Typed',
            'DishName',
            'WaiterName',
            'OrderWaiter.Name',
            'DishCategory.Name',
            'DishGroup.Name',
            'OrderType.Name',
            'PaymentType.Name',
            'Store.Name',
            'Cashier.Name',
            'DeletedWithWriteoff.Payer',
            'NonCashPaymentType.Name'
        ],
        aggregate_fields=[
            'DishAmountInt',
            'DishDiscountSumInt'
        ]
    )

    if df is None or df.empty:
        print("[ОШИБКА] Не удалось получить данные из OLAP отчета")
        olap.disconnect()
        return

    print(f"[OK] Получено {len(df)} записей\n")

    # Фильтруем только заказы на "Пользователь для централизованной доставки"
    delivery_user_mask = (
        (df['WaiterName'] == 'Пользователь для централизованной доставки') |
        (df.get('OrderWaiter.Name', '') == 'Пользователь для централизованной доставки')
    )

    delivery_df = df[delivery_user_mask].copy()

    if delivery_df.empty:
        print("[INFO] Заказы на 'Пользователь для централизованной доставки' не найдены")
        olap.disconnect()
        return

    print(f"[НАЙДЕНО] {len(delivery_df)} заказов на 'Пользователь для централизованной доставки'\n")

    # === АНАЛИЗ 1: Общая статистика ===
    print("\n" + "="*70)
    print("1. ОБЩАЯ СТАТИСТИКА")
    print("="*70)

    total_revenue = delivery_df['DishDiscountSumInt'].sum()
    total_items = delivery_df['DishAmountInt'].sum()

    print(f"Общая выручка: {total_revenue:,.2f} руб")
    print(f"Количество позиций: {total_items:,.0f}")
    print(f"Средний чек на позицию: {total_revenue/len(delivery_df):,.2f} руб")

    # === АНАЛИЗ 2: По барам ===
    print("\n" + "="*70)
    print("2. РАСПРЕДЕЛЕНИЕ ПО БАРАМ")
    print("="*70)

    if 'Store.Name' in delivery_df.columns:
        by_bar = delivery_df.groupby('Store.Name').agg({
            'DishDiscountSumInt': 'sum',
            'DishAmountInt': 'sum'
        }).sort_values('DishDiscountSumInt', ascending=False)

        print("\nБар | Выручка (руб) | Кол-во позиций")
        print("-" * 70)
        for bar, row in by_bar.iterrows():
            print(f"{bar:30} | {row['DishDiscountSumInt']:>12,.2f} | {row['DishAmountInt']:>14,.0f}")

    # === АНАЛИЗ 3: По типу заказа ===
    print("\n" + "="*70)
    print("3. ТИП ЗАКАЗА")
    print("="*70)

    if 'OrderType.Name' in delivery_df.columns:
        by_order_type = delivery_df.groupby('OrderType.Name').agg({
            'DishDiscountSumInt': 'sum',
            'DishAmountInt': 'sum'
        }).sort_values('DishDiscountSumInt', ascending=False)

        print("\nТип заказа | Выручка (руб) | Кол-во позиций")
        print("-" * 70)
        for order_type, row in by_order_type.iterrows():
            print(f"{str(order_type):30} | {row['DishDiscountSumInt']:>12,.2f} | {row['DishAmountInt']:>14,.0f}")

    # === АНАЛИЗ 4: По типу оплаты ===
    print("\n" + "="*70)
    print("4. ТИП ОПЛАТЫ")
    print("="*70)

    if 'PaymentType.Name' in delivery_df.columns:
        by_payment = delivery_df.groupby('PaymentType.Name').agg({
            'DishDiscountSumInt': 'sum',
            'DishAmountInt': 'sum'
        }).sort_values('DishDiscountSumInt', ascending=False)

        print("\nТип оплаты | Выручка (руб) | Кол-во позиций")
        print("-" * 70)
        for payment_type, row in by_payment.iterrows():
            print(f"{str(payment_type):30} | {row['DishDiscountSumInt']:>12,.2f} | {row['DishAmountInt']:>14,.0f}")

    # === АНАЛИЗ 5: Топ-20 блюд ===
    print("\n" + "="*70)
    print("5. ТОП-20 БЛЮД")
    print("="*70)

    top_dishes = delivery_df.groupby('DishName').agg({
        'DishDiscountSumInt': 'sum',
        'DishAmountInt': 'sum'
    }).sort_values('DishDiscountSumInt', ascending=False).head(20)

    print("\nБлюдо | Выручка (руб) | Кол-во")
    print("-" * 70)
    for dish, row in top_dishes.iterrows():
        print(f"{dish[:40]:40} | {row['DishDiscountSumInt']:>12,.2f} | {row['DishAmountInt']:>6,.0f}")

    # === АНАЛИЗ 6: По категориям ===
    print("\n" + "="*70)
    print("6. КАТЕГОРИИ БЛЮД")
    print("="*70)

    if 'DishCategory.Name' in delivery_df.columns:
        by_category = delivery_df.groupby('DishCategory.Name').agg({
            'DishDiscountSumInt': 'sum',
            'DishAmountInt': 'sum'
        }).sort_values('DishDiscountSumInt', ascending=False)

        print("\nКатегория | Выручка (руб) | Кол-во позиций")
        print("-" * 70)
        for category, row in by_category.iterrows():
            print(f"{str(category):30} | {row['DishDiscountSumInt']:>12,.2f} | {row['DishAmountInt']:>14,.0f}")

    # === АНАЛИЗ 7: Кассиры ===
    print("\n" + "="*70)
    print("7. КАССИРЫ")
    print("="*70)

    if 'Cashier.Name' in delivery_df.columns:
        by_cashier = delivery_df.groupby('Cashier.Name').agg({
            'DishDiscountSumInt': 'sum',
            'DishAmountInt': 'sum'
        }).sort_values('DishDiscountSumInt', ascending=False)

        print("\nКассир | Выручка (руб) | Кол-во позиций")
        print("-" * 70)
        for cashier, row in by_cashier.iterrows():
            print(f"{str(cashier):30} | {row['DishDiscountSumInt']:>12,.2f} | {row['DishAmountInt']:>14,.0f}")

    # === АНАЛИЗ 8: Временной анализ ===
    print("\n" + "="*70)
    print("8. ВРЕМЕННОЙ АНАЛИЗ (ПО ДНЯМ)")
    print("="*70)

    if 'OpenDate.Typed' in delivery_df.columns:
        delivery_df['Date'] = pd.to_datetime(delivery_df['OpenDate.Typed']).dt.date
        by_date = delivery_df.groupby('Date').agg({
            'DishDiscountSumInt': 'sum',
            'DishAmountInt': 'sum'
        }).sort_values('Date', ascending=False).head(10)

        print("\nДата | Выручка (руб) | Кол-во позиций")
        print("-" * 70)
        for date, row in by_date.iterrows():
            print(f"{str(date):30} | {row['DishDiscountSumInt']:>12,.2f} | {row['DishAmountInt']:>14,.0f}")

    # === АНАЛИЗ 9: Все уникальные значения полей ===
    print("\n" + "="*70)
    print("9. УНИКАЛЬНЫЕ ЗНАЧЕНИЯ ПОЛЕЙ")
    print("="*70)

    interesting_columns = [
        'OrderType.Name',
        'PaymentType.Name',
        'NonCashPaymentType.Name',
        'DeletedWithWriteoff.Payer',
        'DishGroup.Name'
    ]

    for col in interesting_columns:
        if col in delivery_df.columns:
            unique_vals = delivery_df[col].unique()
            print(f"\n{col}:")
            for val in unique_vals:
                count = len(delivery_df[delivery_df[col] == val])
                revenue = delivery_df[delivery_df[col] == val]['DishDiscountSumInt'].sum()
                print(f"  - {str(val):40} | {count:>5} записей | {revenue:>12,.2f} руб")

    # Сохраняем детальный отчет
    output_file = 'data/delivery_user_investigation.csv'
    delivery_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n[СОХРАНЕНО] Детальный отчет: {output_file}")

    # Отключаемся
    olap.disconnect()

    print("\n" + "="*70)
    print("ИССЛЕДОВАНИЕ ЗАВЕРШЕНО")
    print("="*70 + "\n")

if __name__ == "__main__":
    investigate_delivery_user()

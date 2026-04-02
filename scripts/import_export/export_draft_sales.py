# -*- coding: utf-8 -*-
"""
Скрипт для выгрузки данных о продажах разливного пива в Excel

Выгружает:
- Название пива
- Стиль (DishGroup.ThirdParent)
- Страна (DishForeignName)
- Поставщик (из productCategory через маппинг)
- Объём продаж (литры) по месяцам
- Выручка (₽) по месяцам
- Наценка в процентах
- Количество чеков

Период: 01.01.2022 - сегодня
Бары: все 4 бара
"""

import json
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from core.olap_reports import OlapReports
from core.draft_analysis import DraftAnalysis


def load_dish_to_keg_mapping():
    """Загрузить маппинг блюдо → кег"""
    with open('data/dish_to_keg_mapping.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def get_keg_to_supplier_mapping(olap):
    """Получить маппинг кег → поставщик из /products API"""
    print("\n[SUPPLIER] Загружаю справочник поставщиков из /products...")

    url = f'{olap.api.base_url}/products'
    params = {'key': olap.token}
    response = requests.get(url, params=params, timeout=60)

    if response.status_code != 200:
        print(f"[ERROR] Ошибка получения /products: {response.status_code}")
        return {}

    root = ET.fromstring(response.text)
    keg_to_supplier = {}

    for product in root.findall('productDto'):
        name = product.find('name')
        category = product.find('productCategory')

        if name is not None and category is not None:
            product_name = name.text.strip()
            supplier = category.text.strip() if category.text else ''

            # Сохраняем для всех товаров (и кеги, и блюда)
            keg_to_supplier[product_name] = supplier

    print(f"[OK] Загружено {len(keg_to_supplier)} товаров с поставщиками")
    return keg_to_supplier


def build_extended_olap_request(date_from, date_to, bar_name=None):
    """Построить расширенный OLAP запрос с дополнительными полями"""

    request = {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "DishName",
            "DishGroup.ThirdParent",   # Стиль
            "DishForeignName",          # Страна
            "OpenDate.Typed"
        ],
        "groupByColFields": [],
        "aggregateFields": [
            "UniqOrderId.OrdersCount",  # Количество чеков
            "DishAmountInt",            # Количество порций
            "DishDiscountSumInt",       # Выручка
            "ProductCostBase.MarkUp"    # Наценка %
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
                "values": ["Напитки Розлив"]
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

    if bar_name:
        request["filters"]["Store.Name"] = {
            "filterType": "IncludeValues",
            "values": [bar_name]
        }

    return request


def fetch_olap_data(olap, date_from, date_to):
    """Получить данные OLAP"""
    print(f"\n[OLAP] Запрашиваю данные за {date_from} - {date_to}...")

    request = build_extended_olap_request(date_from, date_to)

    url = f"{olap.api.base_url}/v2/reports/olap"
    params = {"key": olap.token}
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, params=params, json=request, headers=headers, timeout=300)

    if response.status_code == 200:
        data = response.json()
        print(f"[OK] Получено {len(data.get('data', []))} записей")
        return data
    else:
        print(f"[ERROR] Ошибка OLAP: {response.status_code}")
        print(f"   {response.text[:500]}")
        return None


def build_optimized_mappings(dish_to_keg: dict, keg_to_supplier: dict) -> tuple[dict, dict]:
    """
    Построить оптимизированные маппинги для O(1) поиска поставщиков

    Вместо O(n²) цикла для каждой строки, создаем предварительно обработанные словари:
    - dish_to_keg_lower: {lowercase_dish: keg}
    - keg_to_supplier_lower: {lowercase_keg: supplier}

    Возвращает:
        (dish_to_keg_lower, keg_to_supplier_lower)
    """
    # Создаем lowercase версию dish_to_keg один раз
    dish_to_keg_lower = {}

    # Прямые ключи + с префиксом ВО
    for dish, keg in dish_to_keg.items():
        dish_lower = dish.strip().lower()
        dish_to_keg_lower[dish_lower] = keg
        dish_to_keg_lower[f'во {dish_lower}'] = keg

    # Создаем lowercase версию keg_to_supplier
    keg_to_supplier_lower = {}
    for keg, supplier in keg_to_supplier.items():
        keg_lower = keg.strip().lower()
        keg_to_supplier_lower[keg_lower] = supplier

        # Также добавляем вариант без размера порции
        clean_name = keg.split('(')[0].strip().lower()
        keg_to_supplier_lower[clean_name] = supplier
        keg_to_supplier_lower[f'во {clean_name}'] = supplier

    return dish_to_keg_lower, keg_to_supplier_lower


def get_supplier_optimized(beer_name: str, dish_to_keg_lower: dict,
                           keg_to_supplier_lower: dict) -> str:
    """
    O(1) поиск поставщика вместо O(n²)

    Логика:
    1. Прямой lowercase маппинг блюдо → кег
    2. С префиксом "во"
    3. Прямой поиск кег → поставщик
    """
    beer_lower = beer_name.strip().lower()

    # 1. Прямой lowercase маппинг блюдо → кег
    keg_name = dish_to_keg_lower.get(beer_lower)
    if keg_name:
        supplier = keg_to_supplier_lower.get(keg_name.lower(), '')
        if supplier:
            return supplier

    # 2. Прямой поиск в keg_to_supplier (lowercase)
    supplier = keg_to_supplier_lower.get(beer_lower, '')
    if supplier:
        return supplier

    # 3. С префиксом "во"
    supplier = keg_to_supplier_lower.get(f'во {beer_lower}', '')
    if supplier:
        return supplier

    return ''


def process_data(df, dish_to_keg, keg_to_supplier):
    """Обработать данные: парсинг, расчёт литров, джойн поставщика"""

    # Используем extract_beer_info из DraftAnalysis
    draft_analyzer = DraftAnalysis(df)

    # Извлекаем название пива и объём порции
    beer_info = df['DishName'].apply(draft_analyzer.extract_beer_info)
    df['BeerName'] = beer_info.apply(lambda x: x[0])
    df['PortionVolume'] = beer_info.apply(lambda x: x[1])

    # Нормализуем название для маппинга (lowercase, без лишних пробелов)
    df['BeerNameNorm'] = df['BeerName'].str.strip().str.replace(r'\s+', ' ', regex=True)

    # Вычисляем литры
    df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce').fillna(0)
    df['Liters'] = df['DishAmountInt'] * df['PortionVolume']

    # Преобразуем остальные числовые поля
    df['DishDiscountSumInt'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce').fillna(0)
    df['ProductCostBase.MarkUp'] = pd.to_numeric(df['ProductCostBase.MarkUp'], errors='coerce').fillna(0)
    df['UniqOrderId.OrdersCount'] = pd.to_numeric(df['UniqOrderId.OrdersCount'], errors='coerce').fillna(0)

    # Извлекаем год-месяц
    df['OpenDate'] = pd.to_datetime(df['OpenDate.Typed'])
    df['YearMonth'] = df['OpenDate'].dt.to_period('M')

    # ОПТИМИЗАЦИЯ: Строим маппинги один раз для O(1) поиска
    print(f"\n[MAPPING] Stroim optimizirovannye mappingi...")
    dish_to_keg_lower, keg_to_supplier_lower = build_optimized_mappings(dish_to_keg, keg_to_supplier)
    print(f"[OK] Mappingi postroeny: {len(dish_to_keg_lower)} dish→keg, {len(keg_to_supplier_lower)} keg→supplier")

    # Джойн поставщика через оптимизированный маппинг
    print(f"[INFO] Primyayem mappingi postavshchikov...")
    df['Supplier'] = df['BeerNameNorm'].apply(
        lambda x: get_supplier_optimized(x, dish_to_keg_lower, keg_to_supplier_lower)
    )

    # Статистика по поставщикам
    suppliers_found = (df['Supplier'] != '').sum()
    total_records = len(df)
    print(f"[OK] Postavshchiki naideny dlya {suppliers_found} iz {total_records} zapisey ({suppliers_found/total_records*100:.1f}%)")

    # Фильтруем записи с нулевым объёмом
    df = df[df['PortionVolume'] > 0]

    return df


def aggregate_by_month(df):
    """Агрегировать данные по пиву, бару и месяцу"""

    # Группируем по пиву, бару и месяцу
    grouped = df.groupby(['BeerNameNorm', 'Store.Name', 'YearMonth']).agg({
        'Liters': 'sum',
        'DishDiscountSumInt': 'sum',
        'ProductCostBase.MarkUp': 'mean',
        'UniqOrderId.OrdersCount': 'sum',
        'DishGroup.ThirdParent': 'first',  # Стиль (один для пива)
        'DishForeignName': 'first',         # Страна
        'Supplier': 'first'                  # Поставщик
    }).reset_index()

    grouped.columns = [
        'BeerName', 'Bar', 'YearMonth',
        'Liters', 'Revenue', 'AvgMarkup', 'OrdersCount',
        'Style', 'Country', 'Supplier'
    ]

    return grouped


def create_pivot_table(df):
    """Создать сводную таблицу с месяцами в столбцах"""

    # Сначала агрегируем по пиву и бару (без месяца) для общей инфы
    summary = df.groupby(['BeerName', 'Bar']).agg({
        'Style': 'first',
        'Country': 'first',
        'Supplier': 'first',
        'AvgMarkup': 'mean',
        'OrdersCount': 'sum',
        'Liters': 'sum',
        'Revenue': 'sum'
    }).reset_index()

    # Pivot по литрам
    liters_pivot = df.pivot_table(
        index=['BeerName', 'Bar'],
        columns='YearMonth',
        values='Liters',
        aggfunc='sum',
        fill_value=0
    )

    # Pivot по выручке
    revenue_pivot = df.pivot_table(
        index=['BeerName', 'Bar'],
        columns='YearMonth',
        values='Revenue',
        aggfunc='sum',
        fill_value=0
    )

    # Переименовываем колонки
    liters_pivot.columns = [f'Литры_{col}' for col in liters_pivot.columns.astype(str)]
    revenue_pivot.columns = [f'Выручка_{col}' for col in revenue_pivot.columns.astype(str)]

    # Объединяем
    result = summary.merge(liters_pivot, on=['BeerName', 'Bar'], how='left')
    result = result.merge(revenue_pivot, on=['BeerName', 'Bar'], how='left')

    # Переименовываем колонки для читаемости
    result = result.rename(columns={
        'BeerName': 'Название',
        'Bar': 'Бар',
        'Style': 'Стиль',
        'Country': 'Страна',
        'Supplier': 'Поставщик',
        'AvgMarkup': 'Наценка_%',
        'OrdersCount': 'Чеков_всего',
        'Liters': 'Литров_всего',
        'Revenue': 'Выручка_всего'
    })

    # Сортируем по общему объёму
    result = result.sort_values('Литров_всего', ascending=False)

    return result


def export_to_excel(df, filename):
    """Экспорт в Excel с форматированием"""

    print(f"\n[EXPORT] Сохраняю в {filename}...")

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Продажи разливного', index=False)

        # Форматирование
        worksheet = writer.sheets['Продажи разливного']

        # Автоширина колонок
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    print(f"[OK] Сохранено: {filename}")
    print(f"   Строк: {len(df)}")


def main():
    print("=" * 80)
    print("ВЫГРУЗКА ДАННЫХ О ПРОДАЖАХ РАЗЛИВНОГО ПИВА")
    print("=" * 80)

    # Период
    date_from = "2022-01-01"
    date_to = datetime.now().strftime("%Y-%m-%d")

    print(f"\nПериод: {date_from} - {date_to}")

    # Подключаемся к API
    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API")
        return

    try:
        # 1. Загружаем маппинги
        print("\n[STEP 1] Загружаю маппинги...")
        dish_to_keg = load_dish_to_keg_mapping()
        print(f"   dish_to_keg: {len(dish_to_keg)} записей")

        keg_to_supplier = get_keg_to_supplier_mapping(olap)

        # 2. Получаем OLAP данные
        print("\n[STEP 2] Получаю данные из OLAP...")
        olap_data = fetch_olap_data(olap, date_from, date_to)

        if not olap_data or not olap_data.get('data'):
            print("[ERROR] Нет данных")
            return

        df = pd.DataFrame(olap_data['data'])
        print(f"   Сырых записей: {len(df)}")

        # 3. Обрабатываем данные
        print("\n[STEP 3] Обрабатываю данные...")
        df = process_data(df, dish_to_keg, keg_to_supplier)
        print(f"   После обработки: {len(df)} записей")

        # Статистика по поставщикам
        suppliers_found = (df['Supplier'] != '').sum()
        print(f"   С поставщиком: {suppliers_found} ({suppliers_found/len(df)*100:.1f}%)")

        # 4. Агрегируем по месяцам
        print("\n[STEP 4] Агрегирую по месяцам...")
        monthly_df = aggregate_by_month(df)
        print(f"   Записей после агрегации: {len(monthly_df)}")

        # 5. Создаём сводную таблицу
        print("\n[STEP 5] Создаю сводную таблицу...")
        result_df = create_pivot_table(monthly_df)

        # 6. Экспорт в Excel
        filename = f"draft_sales_{date_from}_{date_to}.xlsx"
        export_to_excel(result_df, filename)

        print("\n" + "=" * 80)
        print("ГОТОВО!")
        print("=" * 80)

    finally:
        olap.disconnect()


if __name__ == '__main__':
    main()

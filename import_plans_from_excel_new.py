import openpyxl
import json
import calendar
from datetime import datetime, timedelta

# Маппинг названий баров в коде к ключам venue
VENUE_MAPPING = {
    'Большой пр. В.О': 'bolshoy',
    'Лиговский': 'ligovskiy',
    'Кременчугская': 'kremenchugskaya',
    'Варшавская': 'varshavskaya',
    'Общая': 'all'
}

# Маппинг метрик из Excel в ключи JSON
METRIC_MAPPING = {
    'Выручка': 'revenue',
    'Прибыль': 'profit',
    'Гости': 'guests',
    'Средний чек': 'avgCheck',
    'Средний чек на гостя': 'avgCheckPerGuest',
    'Доля розлив': 'shareDraft',
    'Доля фасовка': 'sharePackaged',
    'Доля кухня': 'shareKitchen',
    'Наценка': 'markup',
    'Наценка розлив': 'markupDraft',
    'Наценка фасовка': 'markupPackaged',
    'Наценка кухня': 'markupKitchen'
}

# Маппинг русских названий месяцев
MONTH_NAMES_RU = {
    'Январь': 1, 'Февраль': 2, 'Март': 3, 'Апрель': 4,
    'Май': 5, 'Июнь': 6, 'Июль': 7, 'Август': 8,
    'Сентябрь': 9, 'Октябрь': 10, 'Ноябрь': 11, 'Декабрь': 12
}

def parse_month_header(header_text):
    """Парсит заголовок типа 'Январь 2025' и возвращает (год, месяц)"""
    parts = header_text.strip().split()
    if len(parts) != 2:
        return None, None
    month_name, year_str = parts

    # Проверяем, что второе слово - это год
    try:
        year = int(year_str)
    except ValueError:
        return None, None

    month = MONTH_NAMES_RU.get(month_name)
    if not month:
        return None, None

    return year, month

def get_weeks_for_month(year, month):
    """Возвращает список недель для данного месяца в формате YYYY-MM-DD"""
    # Получаем первый и последний день месяца
    first_day = datetime(year, month, 1)
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = datetime(year, month, last_day_num)

    weeks = []
    current = first_day

    while current <= last_day:
        # Находим понедельник текущей недели
        monday = current - timedelta(days=current.weekday())
        # Находим воскресенье текущей недели
        sunday = monday + timedelta(days=6)

        # Проверяем, попадает ли хотя бы один день недели в текущий месяц
        if monday.month == month or sunday.month == month:
            week_key = monday.strftime('%Y-%m-%d')
            if week_key not in weeks:
                weeks.append(week_key)

        # Переходим к следующей неделе
        current = sunday + timedelta(days=1)

    return weeks

def distribute_monthly_to_weeks(monthly_value, year, month):
    """Распределяет месячное значение по неделям пропорционально количеству дней"""
    weeks = get_weeks_for_month(year, month)
    days_in_month = calendar.monthrange(year, month)[1]

    result = {}
    for week_key in weeks:
        # Для простоты - равномерное распределение
        # В будущем можно учитывать точное количество дней недели в месяце
        week_value = monthly_value / len(weeks)
        result[week_key] = week_value

    return result

def read_excel_plans(file_path):
    """Читает планы из Excel файла новой структуры"""
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active

    all_plans = {}
    current_month_year = None
    bar_columns = {}  # {column_index: venue_key}

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, values_only=False), start=1):
        # Проверяем, является ли строка заголовком месяца
        first_cell = row[0]
        if first_cell.value and isinstance(first_cell.value, str):
            # Пробуем распарсить как заголовок месяца
            year, month = parse_month_header(first_cell.value)
            if year and month:
                current_month_year = (year, month)
                print(f"Найден месяц: {first_cell.value} -> {year}-{month:02d}")
                continue

        # Проверяем, является ли строка заголовком столбцов (Метрика | Бар1 | ...)
        if first_cell.value == 'Метрика':
            bar_columns = {}
            for col_idx, cell in enumerate(row[1:], start=2):  # Начинаем с колонки B (индекс 2)
                if cell.value in VENUE_MAPPING:
                    venue_key = VENUE_MAPPING[cell.value]
                    bar_columns[col_idx] = venue_key
                    print(f"  Колонка {col_idx}: {cell.value} -> {venue_key}")
            continue

        # Проверяем, является ли строка с метрикой
        if first_cell.value in METRIC_MAPPING and current_month_year and bar_columns:
            metric_name = first_cell.value
            metric_key = METRIC_MAPPING[metric_name]
            year, month = current_month_year

            # Читаем значения для каждого бара
            for col_idx, venue_key in bar_columns.items():
                cell_value = row[col_idx - 1].value  # row индексируется с 0

                if cell_value is not None and cell_value != '':
                    try:
                        value = float(cell_value)

                        # Распределяем месячное значение по неделям
                        weeks_data = distribute_monthly_to_weeks(value, year, month)

                        for week_key, week_value in weeks_data.items():
                            # Создаем составной ключ: venue_week
                            composite_key = f"{venue_key}_{week_key}"

                            if composite_key not in all_plans:
                                all_plans[composite_key] = {}

                            all_plans[composite_key][metric_key] = week_value

                    except (ValueError, TypeError) as e:
                        print(f"Ошибка преобразования значения '{cell_value}' для {venue_key}, {metric_name}: {e}")

    return all_plans

# Основной код
if __name__ == '__main__':
    print("Чтение планов из планы_2025_2026.xlsx...")
    plans = read_excel_plans('планы_2025_2026.xlsx')

    print(f"\nВсего создано планов: {len(plans)}")

    # Сохраняем в JSON
    output_file = 'data/plansdashboard.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)

    print(f"\nПланы сохранены в {output_file}")

    # Показываем примеры
    print("\nПримеры планов:")
    for i, (key, plan) in enumerate(list(plans.items())[:5]):
        print(f"\n{key}:")
        for metric, value in plan.items():
            print(f"  {metric}: {value}")

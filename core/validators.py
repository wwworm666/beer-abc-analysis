"""
Валидаторы для входных данных API
"""
from datetime import datetime
from zoneinfo import ZoneInfo

# Московская временная зона
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# Список допустимых баров
VALID_BARS = [
    "Большой пр. В.О",
    "Лиговский",
    "Кременчугская",
    "Варшавская"
]


def validate_days(days_value, min_days=1, max_days=365):
    """
    Валидация количества дней

    Args:
        days_value: значение для проверки
        min_days: минимум дней (default=1)
        max_days: максимум дней (default=365)

    Returns:
        (is_valid, value_or_error)
    """
    try:
        days = int(days_value)
        if days < min_days or days > max_days:
            return False, f'days должен быть от {min_days} до {max_days}'
        return True, days
    except (ValueError, TypeError):
        return False, 'days должен быть целым числом'


def validate_bar(bar_name, allow_empty=True):
    """
    Валидация названия бара

    Args:
        bar_name: название бара
        allow_empty: разрешить пустое значение (для "Общая")

    Returns:
        (is_valid, value_or_error)
    """
    if not bar_name or bar_name == '':
        if allow_empty:
            return True, None
        else:
            return False, 'bar обязателен'

    if bar_name not in VALID_BARS:
        return False, f'Неверное название бара. Допустимые: {", ".join(VALID_BARS)}'

    return True, bar_name


def validate_tap_number(tap_number, max_taps=24):
    """
    Валидация номера крана

    Args:
        tap_number: номер крана
        max_taps: максимум кранов

    Returns:
        (is_valid, value_or_error)
    """
    try:
        tap = int(tap_number)
        if tap < 1 or tap > max_taps:
            return False, f'tap_number должен быть от 1 до {max_taps}'
        return True, tap
    except (ValueError, TypeError):
        return False, 'tap_number должен быть целым числом'


def validate_required_fields(data, required_fields):
    """
    Проверка наличия обязательных полей

    Args:
        data: dict с данными
        required_fields: list обязательных ключей

    Returns:
        (is_valid, missing_fields_or_none)
    """
    missing = [field for field in required_fields if field not in data or not data[field]]
    if missing:
        return False, f'Отсутствуют обязательные поля: {", ".join(missing)}'
    return True, None


def get_moscow_time():
    """Получить текущее время в московской timezone"""
    return datetime.now(MOSCOW_TZ)


def format_date_for_iiko(dt):
    """
    Форматировать дату для iiko API

    Args:
        dt: datetime объект

    Returns:
        str в формате YYYY-MM-DD
    """
    return dt.strftime("%Y-%m-%d")

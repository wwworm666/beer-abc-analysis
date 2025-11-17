"""
Генератор недель для селектора периодов дашборда

Модуль предоставляет функции для:
- Генерации всех недель года (понедельник - воскресенье)
- Определения текущей недели
- Форматирования периодов для отображения
- Конвертации дат в ключи для хранения планов
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple


class WeeksGenerator:
    """Генератор недель для селектора периодов"""

    @staticmethod
    def generate_weeks_for_year(year: int = None) -> List[Dict]:
        """
        Генерировать все недели года (понедельник - воскресенье)

        Args:
            year: Год для генерации (по умолчанию текущий)

        Returns:
            List[Dict]: Список словарей с информацией о неделях
                [
                    {
                        'key': '2024-11-04_2024-11-10',
                        'label': '04.11 - 10.11',
                        'start': '2024-11-04',
                        'end': '2024-11-10',
                        'is_current': False
                    },
                    ...
                ]
        """
        if year is None:
            year = datetime.now().year

        weeks = []

        # Находим первый понедельник года
        # Если 1 января не понедельник, берем понедельник предыдущей недели
        jan_first = datetime(year, 1, 1)
        days_since_monday = jan_first.weekday()  # 0 = Monday, 6 = Sunday

        # Если 1 января НЕ понедельник, отступаем назад до понедельника
        if days_since_monday != 0:
            first_monday = jan_first - timedelta(days=days_since_monday)
        else:
            first_monday = jan_first

        # Генерируем недели до конца года
        current_monday = first_monday
        current_week_info = WeeksGenerator.get_current_week()

        while current_monday.year <= year:
            sunday = current_monday + timedelta(days=6)

            # Если неделя полностью в следующем году - останавливаемся
            if current_monday.year > year:
                break

            week_data = {
                'key': WeeksGenerator.period_to_key(
                    current_monday.strftime('%Y-%m-%d'),
                    sunday.strftime('%Y-%m-%d')
                ),
                'label': WeeksGenerator.format_week(current_monday, sunday),
                'start': current_monday.strftime('%Y-%m-%d'),
                'end': sunday.strftime('%Y-%m-%d'),
                'is_current': (
                    current_monday.strftime('%Y-%m-%d') == current_week_info['start'] and
                    sunday.strftime('%Y-%m-%d') == current_week_info['end']
                )
            }

            weeks.append(week_data)

            # Переходим к следующему понедельнику
            current_monday += timedelta(days=7)

        return weeks

    @staticmethod
    def get_current_week() -> Dict:
        """
        Определить текущую неделю (понедельник - воскресенье)

        Returns:
            Dict: Информация о текущей неделе
                {
                    'key': '2024-11-18_2024-11-24',
                    'label': '18.11 - 24.11',
                    'start': '2024-11-18',
                    'end': '2024-11-24'
                }
        """
        today = datetime.now()

        # Находим понедельник текущей недели
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)

        # Воскресенье = понедельник + 6 дней
        sunday = monday + timedelta(days=6)

        return {
            'key': WeeksGenerator.period_to_key(
                monday.strftime('%Y-%m-%d'),
                sunday.strftime('%Y-%m-%d')
            ),
            'label': WeeksGenerator.format_week(monday, sunday),
            'start': monday.strftime('%Y-%m-%d'),
            'end': sunday.strftime('%Y-%m-%d')
        }

    @staticmethod
    def format_week(start_date: datetime, end_date: datetime) -> str:
        """
        Форматировать неделю для отображения

        Args:
            start_date: Дата начала (понедельник)
            end_date: Дата окончания (воскресенье)

        Returns:
            str: Форматированная строка
                - "04.11 - 10.11" (если в одном году)
                - "30.12.2024 - 05.01.2025" (если пересекает годы)
        """
        # Проверяем, находятся ли даты в разных годах
        if start_date.year != end_date.year:
            # Если пересекаем год - показываем полные даты с годом
            return f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
        else:
            # Если в одном году - показываем день.месяц
            return f"{start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m')}"

    @staticmethod
    def period_to_key(date_from: str, date_to: str) -> str:
        """
        Конвертировать даты в ключ для хранения плана

        Args:
            date_from: Дата начала в формате 'YYYY-MM-DD'
            date_to: Дата окончания в формате 'YYYY-MM-DD'

        Returns:
            str: Ключ периода '2024-11-04_2024-11-10'
        """
        return f"{date_from}_{date_to}"

    @staticmethod
    def key_to_period(key: str) -> Tuple[str, str]:
        """
        Конвертировать ключ обратно в даты

        Args:
            key: Ключ периода '2024-11-04_2024-11-10'

        Returns:
            Tuple[str, str]: (date_from, date_to) в формате 'YYYY-MM-DD'

        Raises:
            ValueError: Если ключ имеет неверный формат
        """
        try:
            parts = key.split('_')
            if len(parts) != 2:
                raise ValueError(f"Invalid period key format: {key}")
            return parts[0], parts[1]
        except Exception as e:
            raise ValueError(f"Failed to parse period key '{key}': {e}")

    @staticmethod
    def validate_period(date_from: str, date_to: str) -> bool:
        """
        Валидация периода

        Args:
            date_from: Дата начала в формате 'YYYY-MM-DD'
            date_to: Дата окончания в формате 'YYYY-MM-DD'

        Returns:
            bool: True если период корректен

        Raises:
            ValueError: Если даты некорректны
        """
        try:
            start = datetime.strptime(date_from, '%Y-%m-%d')
            end = datetime.strptime(date_to, '%Y-%m-%d')

            if start > end:
                raise ValueError("Start date cannot be after end date")

            # Проверяем что период не слишком большой (например, не больше года)
            delta = end - start
            if delta.days > 365:
                raise ValueError("Period cannot exceed 1 year")

            return True

        except ValueError as e:
            if "does not match format" in str(e):
                raise ValueError(f"Invalid date format. Expected YYYY-MM-DD, got: {date_from}, {date_to}")
            raise


# Тестирование модуля
if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ WeeksGenerator")
    print("=" * 60)

    # Тест 1: Получить текущую неделю
    print("\n1. Текущая неделя:")
    current = WeeksGenerator.get_current_week()
    print(f"   Key: {current['key']}")
    print(f"   Label: {current['label']}")
    print(f"   Start: {current['start']}")
    print(f"   End: {current['end']}")

    # Тест 2: Генерация всех недель 2024 года
    print("\n2. Все недели 2024 года:")
    weeks_2024 = WeeksGenerator.generate_weeks_for_year(2024)
    print(f"   Всего недель: {len(weeks_2024)}")
    print(f"   Первая неделя: {weeks_2024[0]['label']}")
    print(f"   Последняя неделя: {weeks_2024[-1]['label']}")

    # Найдем текущую неделю в списке
    current_weeks = [w for w in weeks_2024 if w['is_current']]
    if current_weeks:
        print(f"   Текущая неделя найдена: {current_weeks[0]['label']}")

    # Тест 3: Показать первые 5 недель
    print("\n3. Первые 5 недель 2024:")
    for week in weeks_2024[:5]:
        marker = " ← ТЕКУЩАЯ" if week['is_current'] else ""
        print(f"   {week['label']} ({week['key']}){marker}")

    # Тест 4: Показать последние 5 недель
    print("\n4. Последние 5 недель 2024:")
    for week in weeks_2024[-5:]:
        print(f"   {week['label']} ({week['key']})")

    # Тест 5: Конвертация ключа
    print("\n5. Конвертация ключа:")
    test_key = "2024-11-04_2024-11-10"
    date_from, date_to = WeeksGenerator.key_to_period(test_key)
    print(f"   Key: {test_key}")
    print(f"   Date from: {date_from}")
    print(f"   Date to: {date_to}")

    # Тест 6: Валидация
    print("\n6. Валидация периодов:")
    try:
        WeeksGenerator.validate_period("2024-11-04", "2024-11-10")
        print("   ✓ Корректный период: 2024-11-04 → 2024-11-10")
    except ValueError as e:
        print(f"   ✗ Ошибка: {e}")

    try:
        WeeksGenerator.validate_period("2024-11-10", "2024-11-04")
        print("   ✓ Обратный период принят (ошибка!)")
    except ValueError as e:
        print(f"   ✓ Обратный период отклонен: {e}")

    print("\n" + "=" * 60)
    print("✅ Тестирование завершено!")
    print("=" * 60)

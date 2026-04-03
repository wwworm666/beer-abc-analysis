"""
Менеджер плановых показателей дашборда

Модуль предоставляет функции для:
- Чтения/записи плановых показателей
- Валидации данных планов
- Создания backup перед изменениями
- Безопасной работы с файлом планов на Render Disk (/kultura)

Файл планов хранится в /kultura/plansdashboard.json
Если /kultura недоступна, используется fallback на data/plansdashboard.json
"""

import json
import os
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from calendar import monthrange
from typing import Dict, Optional, List, Tuple
import threading
import shutil
from core.storage_paths import get_data_path


class PlansManager:
    """Менеджер для работы с плановыми показателями"""

    # Схема данных плана (для валидации)
    PLAN_SCHEMA = {
        'revenue': (float, int),
        'checks': (int,),
        'averageCheck': (float, int),
        'draftShare': (float, int),
        'packagedShare': (float, int),
        'kitchenShare': (float, int),
        'revenueDraft': (float, int),
        'revenuePackaged': (float, int),
        'revenueKitchen': (float, int),
        'markupPercent': (float, int),
        'profit': (float, int),
        'markupDraft': (float, int),
        'markupPackaged': (float, int),
        'markupKitchen': (float, int),
        'loyaltyWriteoffs': (float, int),
        'tapActivity': (float, int)
    }

    def __init__(self, data_file: str = None):
        """
        Инициализация менеджера планов

        Args:
            data_file: Путь к файлу планов (опционально)
        """
        if data_file:
            self.data_file = data_file
        else:
            self.data_file = get_data_path('plansdashboard.json', seed_from_local=True)
            print(f"[PLANS] Файл планов: {self.data_file}")

        # Создаем lock для thread-safe операций
        self._lock = threading.Lock()

        # Инициализируем структуру файла если нужно
        self._initialize_file()

    def _initialize_file(self):
        """Инициализировать файл планов если он не существует"""
        # Создаем директорию если нужно
        directory = os.path.dirname(self.data_file)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                print(f"[PLANS] Создана директория: {directory}")
            except Exception as e:
                print(f"[PLANS ERROR] Не удалось создать директорию {directory}: {e}")
                raise

        # Создаем файл с пустой структурой если не существует
        if not os.path.exists(self.data_file):
            empty_structure = {
                'plans': {},
                'metadata': {
                    'lastUpdate': datetime.now().isoformat(),
                    'version': '1.0',
                    'created': datetime.now().isoformat()
                }
            }

            try:
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(empty_structure, f, indent=2, ensure_ascii=False)
                print(f"[PLANS] Создан новый файл планов: {self.data_file}")
            except Exception as e:
                print(f"[PLANS ERROR] Не удалось создать файл {self.data_file}: {e}")
                raise

    def _read_file(self) -> Dict:
        """
        Прочитать файл планов

        Returns:
            Dict: Данные из файла

        Raises:
            FileNotFoundError: Если файл не найден
            json.JSONDecodeError: Если JSON некорректный
        """
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except FileNotFoundError:
            print(f"[PLANS ERROR] Файл не найден: {self.data_file}")
            # Создаем файл и возвращаем пустую структуру
            self._initialize_file()
            return self._read_file()
        except json.JSONDecodeError as e:
            print(f"[PLANS ERROR] Некорректный JSON в файле {self.data_file}: {e}")
            # Пытаемся восстановить из backup
            backup_restored = self._restore_from_backup()
            if backup_restored:
                return self._read_file()
            # Если не удалось - создаем новый файл
            print("[PLANS] Создаю новый файл...")
            self._initialize_file()
            return self._read_file()

    def _write_file(self, data: Dict):
        """
        Записать данные в файл

        Args:
            data: Данные для записи

        Raises:
            IOError: Если не удалось записать файл
        """
        # Создаем backup перед записью
        self._create_backup()

        # Обновляем metadata
        if 'metadata' not in data:
            data['metadata'] = {}

        data['metadata']['lastUpdate'] = datetime.now().isoformat()
        data['metadata']['version'] = '1.0'

        try:
            # Записываем во временный файл
            temp_file = self.data_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Атомарно переименовываем (на Unix это атомарно)
            os.replace(temp_file, self.data_file)
            print(f"[PLANS] Файл успешно обновлен: {self.data_file}")

        except Exception as e:
            print(f"[PLANS ERROR] Ошибка при записи файла: {e}")
            # Пытаемся восстановить из backup
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

    def _create_backup(self):
        """Создать backup файла планов"""
        if os.path.exists(self.data_file):
            backup_file = self.data_file + '.backup'
            try:
                shutil.copy2(self.data_file, backup_file)
                print(f"[PLANS] Создан backup: {backup_file}")
            except Exception as e:
                print(f"[PLANS WARNING] Не удалось создать backup: {e}")

    def _restore_from_backup(self) -> bool:
        """
        Восстановить файл из backup

        Returns:
            bool: True если восстановление успешно
        """
        backup_file = self.data_file + '.backup'
        if os.path.exists(backup_file):
            try:
                shutil.copy2(backup_file, self.data_file)
                print(f"[PLANS] Файл восстановлен из backup: {backup_file}")
                return True
            except Exception as e:
                print(f"[PLANS ERROR] Не удалось восстановить из backup: {e}")
                return False
        return False

    def _validate_plan_data(self, plan_data: Dict) -> bool:
        """
        Валидация данных плана

        Args:
            plan_data: Данные плана для валидации

        Returns:
            bool: True если данные корректны

        Raises:
            ValueError: Если данные некорректны
        """
        # Проверяем наличие всех обязательных полей
        for field, expected_types in self.PLAN_SCHEMA.items():
            if field not in plan_data:
                raise ValueError(f"Missing required field: {field}")

            value = plan_data[field]

            # Проверяем тип
            if not isinstance(value, expected_types):
                raise ValueError(
                    f"Field '{field}' has wrong type. "
                    f"Expected {expected_types}, got {type(value)}"
                )

            # Проверяем что значение неотрицательное
            if value < 0:
                raise ValueError(f"Field '{field}' cannot be negative: {value}")

        # Проверяем что сумма долей примерно равна 100%
        shares_sum = (
            plan_data['draftShare'] +
            plan_data['packagedShare'] +
            plan_data['kitchenShare']
        )

        # Допускаем погрешность ±1% (из-за округления)
        if not (99.0 <= shares_sum <= 101.0):
            raise ValueError(
                f"Sum of shares must be approximately 100%, got {shares_sum}%"
            )

        return True

    def get_plan(self, period_key: str) -> Optional[Dict]:
        """
        Получить план за конкретный период

        Args:
            period_key: Ключ периода ('2024-11-04_2024-11-10')

        Returns:
            Optional[Dict]: Данные плана или None если план не найден
        """
        with self._lock:
            try:
                data = self._read_file()
                plans = data.get('plans', {})

                if period_key in plans:
                    plan = plans[period_key]
                    print(f"[PLANS] План найден для периода: {period_key}")
                    return plan
                else:
                    print(f"[PLANS] План НЕ найден для периода: {period_key}")
                    return None

            except Exception as e:
                print(f"[PLANS ERROR] Ошибка при чтении плана: {e}")
                return None

    def save_plan(self, period_key: str, plan_data: Dict) -> bool:
        """
        Сохранить план за период

        Args:
            period_key: Ключ периода ('2024-11-04_2024-11-10')
            plan_data: Данные плана

        Returns:
            bool: True если сохранение успешно

        Raises:
            ValueError: Если данные плана некорректны
        """
        with self._lock:
            try:
                # Валидация данных
                self._validate_plan_data(plan_data)

                # Читаем текущие данные
                data = self._read_file()

                # Обновляем/добавляем план
                if 'plans' not in data:
                    data['plans'] = {}

                # Добавляем timestamps
                now = datetime.now().isoformat()
                plan_with_metadata = plan_data.copy()

                if period_key in data['plans']:
                    # Обновляем существующий план - сохраняем createdAt
                    if 'createdAt' in data['plans'][period_key]:
                        plan_with_metadata['createdAt'] = data['plans'][period_key]['createdAt']
                    else:
                        plan_with_metadata['createdAt'] = now
                    plan_with_metadata['updatedAt'] = now
                else:
                    # Создаем новый план
                    plan_with_metadata['createdAt'] = now
                    plan_with_metadata['updatedAt'] = now

                data['plans'][period_key] = plan_with_metadata

                # Сохраняем
                self._write_file(data)
                print(f"[PLANS] План успешно сохранен для периода: {period_key}")

                # Авто-генерация ежедневных планов
                try:
                    from core.daily_plans_generator import regenerate_daily_plans
                    regenerate_daily_plans()
                    print(f"[PLANS] Ежедневные планы пересчитаны")
                except Exception as e:
                    print(f"[PLANS WARN] Не удалось пересчитать ежедневные планы: {e}")

                return True

            except ValueError as e:
                print(f"[PLANS ERROR] Ошибка валидации: {e}")
                raise
            except Exception as e:
                print(f"[PLANS ERROR] Ошибка при сохранении плана: {e}")
                return False

    def get_all_plans(self) -> Dict[str, Dict]:
        """
        Получить все планы

        Returns:
            Dict[str, Dict]: Словарь всех планов {period_key: plan_data}
        """
        with self._lock:
            try:
                data = self._read_file()
                plans = data.get('plans', {})
                print(f"[PLANS] Загружено планов: {len(plans)}")
                return plans
            except Exception as e:
                print(f"[PLANS ERROR] Ошибка при чтении планов: {e}")
                return {}

    def delete_plan(self, period_key: str) -> bool:
        """
        Удалить план за период

        Args:
            period_key: Ключ периода

        Returns:
            bool: True если удаление успешно
        """
        with self._lock:
            try:
                data = self._read_file()

                if 'plans' in data and period_key in data['plans']:
                    del data['plans'][period_key]
                    self._write_file(data)
                    print(f"[PLANS] План удален для периода: {period_key}")
                    return True
                else:
                    print(f"[PLANS] План не найден для удаления: {period_key}")
                    return False

            except Exception as e:
                print(f"[PLANS ERROR] Ошибка при удалении плана: {e}")
                return False

    def get_periods_with_plans(self) -> List[str]:
        """
        Получить список всех периодов, для которых есть планы

        Returns:
            List[str]: Список ключей периодов
        """
        plans = self.get_all_plans()
        return sorted(plans.keys())

    def _get_month_key(self, venue_key: str, year: int, month: int) -> str:
        """Создать ключ месячного плана: venue_2025-10"""
        return f"{venue_key}_{year}-{month:02d}"

    def _parse_date(self, date_str: str) -> date:
        """Парсинг даты из строки YYYY-MM-DD"""
        return datetime.strptime(date_str, '%Y-%m-%d').date()

    # Вес дня для расчёта плана: пт/сб приносят ~2x выручки
    WEEKEND_WEIGHT = 2.0
    WEEKDAY_WEIGHT = 1.0

    def _day_weight(self, d: date) -> float:
        """Вес дня: пт(4)/сб(5) = 2x, остальные = 1x"""
        return self.WEEKEND_WEIGHT if d.weekday() in (4, 5) else self.WEEKDAY_WEIGHT

    def _weighted_days(self, start: date, end: date) -> float:
        """Сумма весов дней в диапазоне [start, end]"""
        total = 0.0
        d = start
        while d <= end:
            total += self._day_weight(d)
            d += timedelta(days=1)
        return total

    def _get_months_in_period(self, start_date: date, end_date: date) -> list:
        """
        Получить список месяцев в периоде с взвешенными долями

        Пт/Сб имеют вес 2x, остальные дни — 1x.
        ratio = взвешенные_дни_периода_в_месяце / взвешенные_дни_месяца

        Returns:
            List of tuples: (year, month, ratio)
        """
        months = []
        current = start_date.replace(day=1)

        while current <= end_date:
            year = current.year
            month = current.month
            days_in_month = monthrange(year, month)[1]

            # Границы периода внутри этого месяца
            period_start = max(start_date, current)
            month_end = current.replace(day=days_in_month)
            period_end = min(end_date, month_end)

            # Взвешенная доля: сколько «веса» периода vs весь месяц
            period_weight = self._weighted_days(period_start, period_end)
            month_weight = self._weighted_days(current, month_end)
            ratio = period_weight / month_weight if month_weight > 0 else 0

            months.append((year, month, ratio))

            # Переходим к следующему месяцу
            if month == 12:
                current = current.replace(year=year + 1, month=1)
            else:
                current = current.replace(month=month + 1)

        return months

    def get_monthly_plan(self, venue_key: str, year: int, month: int) -> Optional[Dict]:
        """
        Получить месячный план для заведения

        Args:
            venue_key: Ключ заведения (bolshoy, ligovskiy, kremenchugskaya, varshavskaya)
            year: Год
            month: Месяц (1-12)

        Returns:
            Optional[Dict]: План или None
        """
        month_key = self._get_month_key(venue_key, year, month)
        return self.get_plan(month_key)

    def calculate_plan_for_period(self, venue_key: str, start_date_str: str, end_date_str: str) -> Optional[Dict]:
        """
        Рассчитать пропорциональный план для произвольного периода

        Логика:
        - Находим все месяцы, попадающие в период
        - Для каждого месяца берём пропорциональную долю (дни_периода / дни_месяца)
        - Суммируем абсолютные метрики (выручка, прибыль, чеки)
        - Усредняем относительные метрики (доли, наценки, средний чек)

        Args:
            venue_key: Ключ заведения или '' для общей
            start_date_str: Начало периода 'YYYY-MM-DD'
            end_date_str: Конец периода 'YYYY-MM-DD'

        Returns:
            Optional[Dict]: Рассчитанный план или None если нет данных
        """
        try:
            start_date = self._parse_date(start_date_str)
            end_date = self._parse_date(end_date_str)

            if start_date > end_date:
                print(f"[PLANS] Некорректный период: {start_date_str} > {end_date_str}")
                return None

            # Получаем список месяцев в периоде
            months_data = self._get_months_in_period(start_date, end_date)

            if not months_data:
                return None

            # Абсолютные метрики (суммируются пропорционально)
            absolute_metrics = [
                'revenue', 'profit', 'checks', 'loyaltyWriteoffs',
                'revenueDraft', 'revenuePackaged', 'revenueKitchen'
            ]

            # Относительные метрики (усредняются с весом)
            relative_metrics = [
                'averageCheck', 'draftShare', 'packagedShare', 'kitchenShare',
                'markupPercent', 'markupDraft', 'markupPackaged', 'markupKitchen',
                'tapActivity'
            ]

            # Инициализация результата
            result = {metric: 0.0 for metric in absolute_metrics}
            weighted_sums = {metric: 0.0 for metric in relative_metrics}
            total_weight = 0.0
            months_found = 0

            # Если venue_key пустой - суммируем по всем заведениям
            venues_to_check = [venue_key] if venue_key else ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']

            for year, month, ratio in months_data:

                for venue in venues_to_check:
                    month_plan = self.get_monthly_plan(venue, year, month)

                    if month_plan:
                        months_found += 1

                        # Суммируем абсолютные метрики пропорционально
                        for metric in absolute_metrics:
                            if metric in month_plan:
                                result[metric] += month_plan[metric] * ratio

                        # Накапливаем относительные метрики с весом
                        weight = ratio
                        total_weight += weight

                        for metric in relative_metrics:
                            if metric in month_plan:
                                weighted_sums[metric] += month_plan[metric] * weight

            if months_found == 0:
                print(f"[PLANS] Нет месячных планов для периода {start_date_str} - {end_date_str}")
                return None

            # Рассчитываем средневзвешенные относительные метрики
            if total_weight > 0:
                for metric in relative_metrics:
                    result[metric] = weighted_sums[metric] / total_weight

            # Округляем значения
            for key in result:
                if isinstance(result[key], float):
                    result[key] = round(result[key], 2)

            # Добавляем мета-информацию
            result['_calculated'] = True
            result['_period'] = f"{start_date_str}_{end_date_str}"
            result['_months_used'] = months_found
            result['_total_days'] = (end_date - start_date).days + 1

            print(f"[PLANS] Рассчитан план для {venue_key or 'общая'} на {start_date_str} - {end_date_str}: "
                  f"{months_found} месяцев, {result['_total_days']} дней, выручка={result['revenue']:.0f}")

            return result

        except Exception as e:
            print(f"[PLANS ERROR] Ошибка расчёта плана: {e}")
            import traceback
            traceback.print_exc()
            return None

    def import_monthly_plans_from_weekly(self):
        """
        Конвертировать недельные планы в месячные (одноразовая миграция)

        Берёт существующие недельные планы и группирует их по месяцам,
        беря среднее или первое значение для каждого месяца.
        """
        all_plans = self.get_all_plans()
        monthly_plans = {}

        for key, plan in all_plans.items():
            # Пропускаем уже месячные планы (формат venue_2025-10)
            parts = key.split('_')
            if len(parts) == 2 and len(parts[1]) == 7:  # venue_2025-10
                monthly_plans[key] = plan
                continue

            # Парсим недельный ключ: venue_2025-10-06
            if len(parts) >= 2:
                venue = parts[0]
                date_part = '_'.join(parts[1:])

                try:
                    week_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                    month_key = f"{venue}_{week_date.year}-{week_date.month:02d}"

                    # Берём первый попавшийся план для месяца
                    if month_key not in monthly_plans:
                        monthly_plans[month_key] = plan.copy()
                        print(f"[PLANS] Миграция: {key} -> {month_key}")
                except ValueError:
                    print(f"[PLANS] Не удалось распарсить ключ: {key}")

        # Сохраняем месячные планы
        data = self._read_file()
        data['plans'] = monthly_plans
        data['metadata']['migratedToMonthly'] = datetime.now().isoformat()
        self._write_file(data)

        print(f"[PLANS] Миграция завершена: {len(monthly_plans)} месячных планов")
        return monthly_plans


# Тестирование модуля
if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ PlansManager")
    print("=" * 60)

    # Используем тестовый файл
    test_file = 'data/test_plans.json'

    # Удаляем тестовый файл если существует
    if os.path.exists(test_file):
        os.remove(test_file)
    if os.path.exists(test_file + '.backup'):
        os.remove(test_file + '.backup')

    manager = PlansManager(data_file=test_file)

    # Тест 1: Создание плана
    print("\n1. Создание тестового плана:")
    test_plan = {
        'revenue': 1000000.0,
        'checks': 500,
        'averageCheck': 2000.0,
        'draftShare': 45.0,
        'packagedShare': 30.0,
        'kitchenShare': 25.0,
        'revenueDraft': 450000.0,
        'revenuePackaged': 300000.0,
        'revenueKitchen': 250000.0,
        'markupPercent': 200.0,
        'profit': 500000.0,
        'markupDraft': 250.0,
        'markupPackaged': 180.0,
        'markupKitchen': 150.0,
        'loyaltyWriteoffs': 50000.0
    }

    try:
        success = manager.save_plan('2024-11-04_2024-11-10', test_plan)
        print(f"   {'✓' if success else '✗'} План сохранен: {success}")
    except Exception as e:
        print(f"   ✗ Ошибка: {e}")

    # Тест 2: Чтение плана
    print("\n2. Чтение плана:")
    loaded_plan = manager.get_plan('2024-11-04_2024-11-10')
    if loaded_plan:
        print(f"   ✓ План загружен")
        print(f"   Выручка: {loaded_plan['revenue']}")
        print(f"   Создан: {loaded_plan.get('createdAt', 'N/A')}")
    else:
        print(f"   ✗ План не найден")

    # Тест 3: Обновление плана
    print("\n3. Обновление плана:")
    test_plan['revenue'] = 1200000.0
    try:
        success = manager.save_plan('2024-11-04_2024-11-10', test_plan)
        print(f"   {'✓' if success else '✗'} План обновлен")
        updated_plan = manager.get_plan('2024-11-04_2024-11-10')
        if updated_plan:
            print(f"   Новая выручка: {updated_plan['revenue']}")
            print(f"   Обновлен: {updated_plan.get('updatedAt', 'N/A')}")
    except Exception as e:
        print(f"   ✗ Ошибка: {e}")

    # Тест 4: Валидация (некорректные данные)
    print("\n4. Валидация некорректных данных:")
    invalid_plan = test_plan.copy()
    invalid_plan['revenue'] = -1000  # Отрицательное значение

    try:
        manager.save_plan('2024-11-11_2024-11-17', invalid_plan)
        print("   ✗ Валидация НЕ сработала (ошибка!)")
    except ValueError as e:
        print(f"   ✓ Валидация сработала: {e}")

    # Тест 5: Получение всех планов
    print("\n5. Получение всех планов:")
    all_plans = manager.get_all_plans()
    print(f"   Всего планов: {len(all_plans)}")
    for period_key in all_plans.keys():
        print(f"   - {period_key}")

    # Тест 6: Получение списка периодов
    print("\n6. Периоды с планами:")
    periods = manager.get_periods_with_plans()
    print(f"   Периоды: {periods}")

    # Тест 7: Удаление плана
    print("\n7. Удаление плана:")
    success = manager.delete_plan('2024-11-04_2024-11-10')
    print(f"   {'✓' if success else '✗'} План удален: {success}")

    # Проверяем что план действительно удален
    deleted_plan = manager.get_plan('2024-11-04_2024-11-10')
    print(f"   {'✓' if deleted_plan is None else '✗'} План больше не существует: {deleted_plan is None}")

    # Тест 8: Backup/restore
    print("\n8. Проверка backup файла:")
    backup_exists = os.path.exists(test_file + '.backup')
    print(f"   {'✓' if backup_exists else '✗'} Backup файл создан: {backup_exists}")

    # Очистка
    print("\n9. Очистка тестовых файлов:")
    if os.path.exists(test_file):
        os.remove(test_file)
        print("   ✓ Тестовый файл удален")
    if os.path.exists(test_file + '.backup'):
        os.remove(test_file + '.backup')
        print("   ✓ Backup файл удален")

    print("\n" + "=" * 60)
    print("✅ Тестирование завершено!")
    print("=" * 60)

"""
Менеджер для управления пивными кранами в барах
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json
import os
import threading

class ActionType(Enum):
    """Типы действий с кранами"""
    START = "start"      # Подключение кеги
    STOP = "stop"        # Кега закончилась
    REPLACE = "replace"  # Смена сорта пива

class TapStatus(Enum):
    """Статус крана"""
    EMPTY = "empty"        # Пустой кран
    ACTIVE = "active"      # Работающий кран
    CHANGING = "changing"  # Идет замена кеги

class Bar:
    """Класс для представления бара"""
    def __init__(self, bar_id: str, name: str, tap_count: int):
        self.bar_id = bar_id
        self.name = name
        self.tap_count = tap_count
        self.taps: Dict[int, 'Tap'] = {
            i: Tap(i) for i in range(1, tap_count + 1)
        }

class Tap:
    """Класс для представления крана"""
    def __init__(self, tap_number: int):
        self.tap_number = tap_number
        self.status = TapStatus.EMPTY
        self.current_beer: Optional[str] = None
        self.current_keg_id: Optional[str] = None
        self.started_at: Optional[str] = None
        self.history: List[Dict] = []

    def to_dict(self) -> Dict:
        """Преобразование в словарь"""
        return {
            'tap_number': self.tap_number,
            'status': self.status.value,
            'current_beer': self.current_beer,
            'current_keg_id': self.current_keg_id,
            'started_at': self.started_at,
            'history': self.history
        }

class TapsManager:
    """Менеджер для управления всеми кранами"""

    # Конфигурация баров
    BARS_CONFIG = {
        'bar1': {'name': 'Бар 1', 'taps': 24},
        'bar2': {'name': 'Бар 2', 'taps': 12},
        'bar3': {'name': 'Бар 3', 'taps': 12},
        'bar4': {'name': 'Бар 4', 'taps': 12},
    }

    @staticmethod
    def _now():
        """Возвращает текущее время в московской timezone"""
        moscow_tz = ZoneInfo("Europe/Moscow")
        return datetime.now(moscow_tz)

    def __init__(self, data_file: str = 'data/taps_data.json'):
        """
        Инициализация менеджера кранов

        Args:
            data_file: Путь к файлу с сохраненными данными
        """
        self.data_file = data_file
        self.bars: Dict[str, Bar] = {}
        self._lock = threading.Lock()  # Lock для thread-safe операций
        self._init_bars()
        self._load_data()

    def _init_bars(self):
        """Инициализация баров"""
        for bar_id, config in self.BARS_CONFIG.items():
            self.bars[bar_id] = Bar(bar_id, config['name'], config['taps'])

    def _load_data(self):
        """Загрузка данных из файла"""
        if not os.path.exists(self.data_file):
            return

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for bar_id, bar_taps in data.items():
                if bar_id in self.bars:
                    for tap_data in bar_taps.get('taps', []):
                        tap_num = tap_data.get('tap_number')
                        if tap_num in self.bars[bar_id].taps:
                            tap = self.bars[bar_id].taps[tap_num]
                            tap.status = TapStatus(tap_data.get('status', 'empty'))
                            tap.current_beer = tap_data.get('current_beer')
                            tap.current_keg_id = tap_data.get('current_keg_id')
                            tap.started_at = tap_data.get('started_at')
                            tap.history = tap_data.get('history', [])
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки данных о кранах: {e}")

    def _save_data(self):
        """
        Сохранение данных в файл
        ВАЖНО: Этот метод вызывается только из методов, которые УЖЕ держат self._lock!
        НЕ использовать напрямую без lock!
        """
        try:
            os.makedirs(os.path.dirname(self.data_file) or '.', exist_ok=True)

            data = {}
            for bar_id, bar in self.bars.items():
                data[bar_id] = {
                    'name': bar.name,
                    'taps': [tap.to_dict() for tap in bar.taps.values()]
                }

            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Ошибка сохранения данных о кранах: {e}")

    def get_bars(self) -> List[Dict]:
        """Получить список всех баров"""
        return [
            {
                'bar_id': bar_id,
                'name': bar.name,
                'tap_count': bar.tap_count,
                'active_taps': sum(1 for t in bar.taps.values() if t.status == TapStatus.ACTIVE)
            }
            for bar_id, bar in self.bars.items()
        ]

    def get_bar_taps(self, bar_id: str) -> Dict:
        """Получить информацию о кранах конкретного бара"""
        if bar_id not in self.bars:
            return {'error': f'Бар {bar_id} не найден'}

        bar = self.bars[bar_id]
        return {
            'bar_id': bar_id,
            'bar_name': bar.name,
            'total_taps': bar.tap_count,
            'taps': [tap.to_dict() for tap in bar.taps.values()],
            'active_count': sum(1 for t in bar.taps.values() if t.status == TapStatus.ACTIVE),
            'empty_count': sum(1 for t in bar.taps.values() if t.status == TapStatus.EMPTY),
            'changing_count': sum(1 for t in bar.taps.values() if t.status == TapStatus.CHANGING),
            'active_percentage': round(
                sum(1 for t in bar.taps.values() if t.status == TapStatus.ACTIVE) / bar.tap_count * 100
            )
        }

    def start_tap(self, bar_id: str, tap_number: int, beer_name: str, keg_id: str) -> Dict:
        """
        Подключить кегу (начать работу крана)

        Args:
            bar_id: ID бара
            tap_number: Номер крана
            beer_name: Название пива
            keg_id: ID кеги

        Returns:
            Результат операции
        """
        with self._lock:
            if bar_id not in self.bars:
                return {'success': False, 'error': f'Бар {bar_id} не найден'}

            bar = self.bars[bar_id]
            if tap_number not in bar.taps:
                return {'success': False, 'error': f'Кран {tap_number} не найден в баре {bar_id}'}

            tap = bar.taps[tap_number]

            # Если кран уже работает, добавляем запись в историю
            if tap.status == TapStatus.ACTIVE:
                event = {
                    'timestamp': self._now().isoformat(),
                    'action': ActionType.STOP.value,
                    'beer_name': tap.current_beer,
                    'keg_id': tap.current_keg_id
                }
                tap.history.append(event)

            tap.status = TapStatus.ACTIVE
            tap.current_beer = beer_name
            tap.current_keg_id = keg_id
            tap.started_at = self._now().isoformat()

            event = {
                'timestamp': self._now().isoformat(),
                'action': ActionType.START.value,
                'beer_name': beer_name,
                'keg_id': keg_id
            }
            tap.history.append(event)

            self._save_data()

            return {
                'success': True,
                'tap_number': tap_number,
                'beer_name': beer_name,
                'status': 'started'
            }

    def stop_tap(self, bar_id: str, tap_number: int) -> Dict:
        """
        Остановить кран (кега закончилась)

        Args:
            bar_id: ID бара
            tap_number: Номер крана

        Returns:
            Результат операции
        """
        with self._lock:
            if bar_id not in self.bars:
                return {'success': False, 'error': f'Бар {bar_id} не найден'}

            bar = self.bars[bar_id]
            if tap_number not in bar.taps:
                return {'success': False, 'error': f'Кран {tap_number} не найден'}

            tap = bar.taps[tap_number]

            if tap.status == TapStatus.EMPTY:
                return {'success': False, 'error': 'Кран уже пустой'}

            event = {
                'timestamp': self._now().isoformat(),
                'action': ActionType.STOP.value,
                'beer_name': tap.current_beer,
                'keg_id': tap.current_keg_id
            }
            tap.history.append(event)

            tap.status = TapStatus.EMPTY
            tap.current_beer = None
            tap.current_keg_id = None
            tap.started_at = None

            self._save_data()

            return {
                'success': True,
                'tap_number': tap_number,
                'status': 'stopped'
            }

    def replace_tap(self, bar_id: str, tap_number: int, beer_name: str, keg_id: str) -> Dict:
        """
        Заменить кегу (смена сорта пива)

        Args:
            bar_id: ID бара
            tap_number: Номер крана
            beer_name: Название нового пива
            keg_id: ID новой кеги

        Returns:
            Результат операции
        """
        with self._lock:
            if bar_id not in self.bars:
                return {'success': False, 'error': f'Бар {bar_id} не найден'}

            bar = self.bars[bar_id]
            if tap_number not in bar.taps:
                return {'success': False, 'error': f'Кран {tap_number} не найден'}

            tap = bar.taps[tap_number]

            # Записываем старое пиво как остановленное
            if tap.current_beer:
                event = {
                    'timestamp': self._now().isoformat(),
                    'action': ActionType.STOP.value,
                    'beer_name': tap.current_beer,
                    'keg_id': tap.current_keg_id
                }
                tap.history.append(event)

            # Устанавливаем новое пиво
            tap.status = TapStatus.ACTIVE
            tap.current_beer = beer_name
            tap.current_keg_id = keg_id
            tap.started_at = self._now().isoformat()

            event = {
                'timestamp': self._now().isoformat(),
                'action': ActionType.REPLACE.value,
                'beer_name': beer_name,
                'keg_id': keg_id
            }
            tap.history.append(event)

            self._save_data()

            return {
                'success': True,
                'tap_number': tap_number,
                'beer_name': beer_name,
                'status': 'replaced'
            }

    def get_tap_history(self, bar_id: str, tap_number: int, limit: int = 50) -> Dict:
        """
        Получить историю действий крана

        Args:
            bar_id: ID бара
            tap_number: Номер крана
            limit: Максимальное количество записей

        Returns:
            История действий
        """
        if bar_id not in self.bars:
            return {'error': f'Бар {bar_id} не найден'}

        bar = self.bars[bar_id]
        if tap_number not in bar.taps:
            return {'error': f'Кран {tap_number} не найден'}

        tap = bar.taps[tap_number]
        return {
            'bar_id': bar_id,
            'tap_number': tap_number,
            'history': list(reversed(tap.history))[-limit:]  # Новые записи в начале
        }

    def get_all_events(self, bar_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Получить все события (для общей истории)

        Args:
            bar_id: ID конкретного бара (None = все бары)
            limit: Максимальное количество записей

        Returns:
            Список событий, отсортированный по времени (новые в начале)
        """
        events = []

        bars_to_process = [bar_id] if bar_id else self.bars.keys()

        for current_bar_id in bars_to_process:
            if current_bar_id not in self.bars:
                continue

            bar = self.bars[current_bar_id]
            for tap in bar.taps.values():
                for event in tap.history:
                    event_copy = event.copy()
                    event_copy['bar_id'] = current_bar_id
                    event_copy['bar_name'] = bar.name
                    event_copy['tap_number'] = tap.tap_number
                    events.append(event_copy)

        # Сортируем по времени (новые в начале)
        events.sort(key=lambda x: x['timestamp'], reverse=True)

        return events[:limit]

    def get_statistics(self, bar_id: Optional[str] = None) -> Dict:
        """
        Получить статистику по кранам

        Args:
            bar_id: ID бара (None = все бары)

        Returns:
            Статистика
        """
        if bar_id:
            if bar_id not in self.bars:
                return {'error': f'Бар {bar_id} не найден'}

            bar_data = self.get_bar_taps(bar_id)
            return {
                'bar_id': bar_id,
                'bar_name': bar_data['bar_name'],
                'total_taps': bar_data['total_taps'],
                'active_taps': bar_data['active_count'],
                'empty_taps': bar_data['empty_count'],
                'changing_taps': bar_data['changing_count'],
                'active_percentage': bar_data['active_percentage'],
                'total_events': len(self.get_all_events(bar_id))
            }
        else:
            # Статистика по всем барам
            total_taps = 0
            active_taps = 0
            empty_taps = 0
            changing_taps = 0
            total_events = 0

            for bar_id_key in self.bars.keys():
                bar_data = self.get_bar_taps(bar_id_key)
                total_taps += bar_data['total_taps']
                active_taps += bar_data['active_count']
                empty_taps += bar_data['empty_count']
                changing_taps += bar_data['changing_count']
                total_events += len(self.get_all_events(bar_id_key))

            return {
                'total_bars': len(self.bars),
                'total_taps': total_taps,
                'active_taps': active_taps,
                'empty_taps': empty_taps,
                'changing_taps': changing_taps,
                'active_percentage': round(active_taps / total_taps * 100) if total_taps > 0 else 0,
                'total_events': total_events
            }

    def calculate_tap_activity_for_period(self, bar_id: Optional[str], date_from: str, date_to: str) -> float:
        """
        Рассчитать процент активности кранов за период

        Логика:
        - Для каждого дня недели считаем сколько кранов было активно
        - Суммируем активные кран-дни
        - Процент = (сумма активных кран-дней / (количество кранов × дней)) × 100

        Пример:
        - Бар: 24 крана, период: 7 дней
        - Понедельник: 10 активных, Вторник: 12 активных, ... Воскресенье: 9 активных
        - Сумма: 10+12+...+9 = 70 кран-дней
        - Процент: (70 / (24 × 7)) = 70 / 168 = 41.67%

        Args:
            bar_id: ID бара (None = все бары)
            date_from: Дата начала периода (YYYY-MM-DD)
            date_to: Дата конца периода (YYYY-MM-DD)

        Returns:
            Процент активности кранов (0-100)
        """
        import sys
        from datetime import datetime, timedelta

        # Парсим даты
        period_start = datetime.fromisoformat(date_from)
        period_end = datetime.fromisoformat(date_to)

        print(f"\n[TAP_ACTIVITY] Расчет за период: {date_from} - {date_to}")
        sys.stdout.flush()

        # DEBUG: Проверяем что есть в self.bars
        print(f"[TAP_ACTIVITY] DEBUG: self.bars keys = {list(self.bars.keys())}")
        print(f"[TAP_ACTIVITY] DEBUG: bar_id parameter = {bar_id}")
        sys.stdout.flush()

        # Определяем какие бары анализируем
        bars_to_check = [bar_id] if bar_id else list(self.bars.keys())
        print(f"[TAP_ACTIVITY] DEBUG: bars_to_check = {bars_to_check}")
        sys.stdout.flush()

        # Генерируем список дней в периоде
        days = []
        current_day = period_start
        while current_day <= period_end:
            days.append(current_day)
            current_day += timedelta(days=1)

        total_taps = 0
        total_tap_days = 0  # Сумма активных кран-дней

        print(f"[TAP_ACTIVITY] DEBUG: Начинаем цикл по барам, всего баров: {len(bars_to_check)}")
        sys.stdout.flush()

        for current_bar_id in bars_to_check:
            print(f"[TAP_ACTIVITY] DEBUG: Проверяем бар {current_bar_id}")
            sys.stdout.flush()

            if current_bar_id not in self.bars:
                print(f"[TAP_ACTIVITY] DEBUG: Бар {current_bar_id} не найден в self.bars!")
                sys.stdout.flush()
                continue

            bar = self.bars[current_bar_id]
            total_taps += bar.tap_count

            print(f"[TAP_ACTIVITY] Бар {current_bar_id}: {bar.tap_count} кранов x {len(days)} дней = {bar.tap_count * len(days)} кран-дней")
            print(f"[TAP_ACTIVITY] DEBUG: bar.taps.items() count = {len(bar.taps)}")
            sys.stdout.flush()

            # Для каждого дня считаем активные краны
            for day in days:
                # Срез на конец дня
                day_end = day.replace(hour=23, minute=59, second=59)
                active_taps_today = 0

                # Для каждого крана определяем статус на конец дня
                for tap_num, tap in bar.taps.items():
                    # Находим последнее событие до конца этого дня
                    last_action = None
                    history_count = len(tap.history) if tap.history else 0

                    for event in tap.history:
                        try:
                            # Убираем timezone если есть
                            timestamp_str = event['timestamp'].replace('+03:00', '')
                            event_time = datetime.fromisoformat(timestamp_str)

                            # Событие произошло до или в течение этого дня
                            if event_time <= day_end:
                                last_action = event.get('action')
                        except (ValueError, KeyError) as e:
                            print(f"[TAP_ACTIVITY] DEBUG: Ошибка парсинга события крана {tap_num}: {e}")
                            sys.stdout.flush()
                            continue

                    # Кран активен если последнее действие = START или REPLACE
                    if last_action in ['start', 'replace']:
                        active_taps_today += 1

                total_tap_days += active_taps_today
                print(f"  {day.strftime('%Y-%m-%d')}: {active_taps_today} активных")
                sys.stdout.flush()

        # Рассчитываем процент
        print(f"[TAP_ACTIVITY] DEBUG: total_taps = {total_taps}, days = {len(days)}")
        sys.stdout.flush()

        max_tap_days = total_taps * len(days)
        if max_tap_days == 0:
            print(f"[TAP_ACTIVITY] DEBUG: max_tap_days = 0, возвращаем 0.0")
            sys.stdout.flush()
            return 0.0

        result = round((total_tap_days / max_tap_days) * 100, 2)
        print(f"[TAP_ACTIVITY] ИТОГО: {total_tap_days}/{max_tap_days} кран-дней = {result}%\n")
        sys.stdout.flush()

        return result

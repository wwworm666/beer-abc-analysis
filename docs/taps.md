# Управление кранами

## Что это

Система учёта пивных кранов: подключение/остановка кег, замена сортов, история действий. 4 бара, 12-24 крана.

## Файлы

- [`core/taps_manager.py`](../../core/taps_manager.py) — управление кранами, thread-safe операции
- [`routes/taps.py`](../../routes/taps.py) — Flask endpoint'ы
- [`data/taps_data.json`](../../data/taps_data.json) — текущее состояние и история

---

## Как работает

### Структура данных

```python
# core/taps_manager.py:56-64
BARS_CONFIG = {
    'bar1': {'name': 'Бар 1', 'taps': 24},
    'bar2': {'name': 'Бар 2', 'taps': 12},
    'bar3': {'name': 'Бар 3', 'taps': 12},
    'bar4': {'name': 'Бар 4', 'taps': 12},
}
```

### Статусы крана

```python
# core/taps_manager.py:18-22
class TapStatus(Enum):
    EMPTY = "empty"        # Пустой кран
    ACTIVE = "active"      # Работающий кран
    CHANGING = "changing"  # Идет замена кеги
```

### Типы действий

```python
# core/taps_manager.py:12-17
class ActionType(Enum):
    START = "start"      # Подключение кеги
    STOP = "stop"        # Кега закончилась
    REPLACE = "replace"  # Смена сорта пива
```

---

### Операции с кранами

#### START — Подключение кеги

```python
# core/taps_manager.py:165-218
def start_tap(self, bar_id, tap_number, beer_name, keg_id):
    with self._lock:  # Thread-safe
        tap = self.bars[bar_id].taps[tap_number]

        # Если кран уже работает — закрываем старую кегу
        if tap.status == TapStatus.ACTIVE:
            event = {
                'timestamp': self._now().isoformat(),
                'action': ActionType.STOP.value,
                'beer_name': tap.current_beer,
                'keg_id': tap.current_keg_id
            }
            tap.history.append(event)

        # Подключаем новую кегу
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
```

#### STOP — Остановка крана

```python
# core/taps_manager.py:220-263
def stop_tap(self, bar_id, tap_number):
    with self._lock:
        tap = self.bars[bar_id].taps[tap_number]

        if tap.status == TapStatus.EMPTY:
            return {'success': False, 'error': 'Кран уже пустой'}

        # Записываем событие остановки
        event = {
            'timestamp': self._now().isoformat(),
            'action': ActionType.STOP.value,
            'beer_name': tap.current_beer,
            'keg_id': tap.current_keg_id
        }
        tap.history.append(event)

        # Очищаем кран
        tap.status = TapStatus.EMPTY
        tap.current_beer = None
        tap.current_keg_id = None
        tap.started_at = None

        self._save_data()
```

#### REPLACE — Замена кеги

```python
# core/taps_manager.py:265-319
def replace_tap(self, bar_id, tap_number, beer_name, keg_id):
    with self._lock:
        tap = self.bars[bar_id].taps[tap_number]

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
```

---

### Thread-safe операции

Все операции с кранами защищены lock'ом:

```python
# core/taps_manager.py:81
self._lock = threading.Lock()

def start_tap(self, ...):
    with self._lock:  # Блокировка на время операции
        ...
```

Это предотвращает race conditions при одновременном доступе нескольких пользователей.

---

### Расчёт активности кранов

#### Формула

```
Активность % = (Σ активных кран-дней) / (Всего кранов × Количество дней) × 100
```

#### Пример

```
Бар: 24 крана, период: 7 дней
Понедельник: 10 активных
Вторник: 12 активных
...
Воскресенье: 9 активных

Сумма: 10+12+...+9 = 70 кран-дней
Процент: (70 / (24 × 7)) × 100 = 41.67%
```

#### Реализация (с 2026-09-04 — с разбивкой по кранам)

```python
# core/taps_manager.py
def tap_activity_by_tap(self, bar_id, date_from, date_to) -> dict:
    # 1. Дни периода включительно и срез на 23:59:59 каждого дня
    # 2. Для каждого крана время событий разбирается один раз; для каждого дня
    #    берётся последнее событие (в порядке истории) с временем <= конца дня;
    #    кран активен, если это 'start' или 'replace' -> active_days += 1
    # 3. percent = Σ active_days всех кранов / (кранов × дней) × 100, 0.0 при нуле
    return {'days', 'total_taps', 'active_tap_days', 'percent',
            'taps': [{'bar_id', 'bar_name', 'tap_number', 'active_days', 'current_beer'}]}

def calculate_tap_activity_for_period(self, bar_id, date_from, date_to) -> float:
    # Число карточки «Активность кранов» на дашборде - обёртка:
    return self.tap_activity_by_tap(bar_id, date_from, date_to)['percent']
```

Одна арифметика питает и число карточки, и секцию «Краны» внутри раскрытой
карточки на дашборде (`/api/dashboard-card-details` с `section=taps`, см.
[dashboard.md](dashboard.md) «Детали внутри карточки»): «Простаивали весь период:
K из M кранов», пять кранов с наименьшим числом активных дней, ссылка «Открыть
краны». Клик по карточке с 2026-09-04 раскрывает её, а не уводит на `/taps`.
Тест `tests/test_dashboard_card_details.py` закрепляет равенство обёртки и
разбивки: сумма `active_days` по кранам равна `active_tap_days`.

Ограничение: история крана обрезана до `MAX_TAP_HISTORY = 200` событий, поэтому на
длинных периодах ранние дни могут остаться без события, и кран будет считаться
пустым — это действует и на карточку, и на секцию. «Последнее событие» — последнее
подходящее в порядке списка `history` (история хронологическая), не максимум по
времени.

---

### История событий

#### Формат записи

```json
{
  "timestamp": "2026-03-27T14:30:00+03:00",
  "action": "start",
  "beer_name": "Жигулёвское",
  "keg_id": "KEG-12345"
}
```

#### Получение истории

```python
# core/taps_manager.py:347-378
def get_all_events(self, bar_id=None, limit=100):
    events = []

    bars_to_process = [bar_id] if bar_id else self.bars.keys()

    for current_bar_id in bars_to_process:
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
```

---

## API endpoint'ы

### Список баров

```
GET /api/taps/bars
Response: [
    {
        "bar_id": "bar1",
        "name": "Бар 1",
        "tap_count": 24,
        "active_taps": 18
    }
]
```

### Краны бара

```
GET /api/taps/:bar_id
Response: {
    "bar_id": "bar1",
    "bar_name": "Бар 1",
    "total_taps": 24,
    "active_count": 18,
    "empty_count": 5,
    "changing_count": 1,
    "active_percentage": 75,
    "taps": [...]
}
```

### Действия

```
POST /api/taps/:bar_id/start
Body: {"tapNumber": 5, "beerName": "...", "kegId": "..."}

POST /api/taps/:bar_id/stop
Body: {"tapNumber": 5}

POST /api/taps/:bar_id/replace
Body: {"tapNumber": 5, "beerName": "...", "kegId": "..."}
```

### История

```
GET /api/taps/:bar_id/history?tapNumber=5&limit=50
GET /api/taps/events?bar_id=bar1&limit=100
```

### Экспорт

```
GET /api/taps/export-taplist
Returns: CSV файл со списком кранов
```

---

## Формат данных (JSON)

```json
{
  "bar1": {
    "name": "Бар 1",
    "taps": [
      {
        "tap_number": 1,
        "status": "active",
        "current_beer": "Жигулёвское",
        "current_keg_id": "KEG-12345",
        "started_at": "2026-03-25T10:00:00+03:00",
        "history": [
          {
            "timestamp": "2026-03-25T10:00:00+03:00",
            "action": "start",
            "beer_name": "Жигулёвское",
            "keg_id": "KEG-12345"
          }
        ]
      }
    ]
  }
}
```

---

## Зависимости

### От каких модулей зависит
- Нет внешних зависимостей (полностью автономный модуль)

### Кто использует
- Frontend кранов (`taps.html`, `taps_bar.html`)
- Дашборд (метрика active_percentage)
- Telegram bot (уведомления о замене)

---

## Changelog

- **2026-03-27** — Создан документ taps.md с описанием операций, thread-safe блокировок, формулы активности

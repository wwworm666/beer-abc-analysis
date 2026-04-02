# График смен

## Что это

Модуль управления графиком работы сотрудников: смены, роли, локации, revenue plan/fact, meeting notes.

## Файлы

- [`core/shifts_manager.py`](../../core/shifts_manager.py) — управление сменами
- [`core/meeting_notes.py`](../../core/meeting_notes.py) — заметки по периодам
- [`routes/schedule.py`](../../routes/schedule.py) — Flask endpoint'ы

---

## Как работает

### Структура смены

```python
# core/shifts_manager.py
class Shift:
    """
    Смена сотрудника
    """
    def __init__(self):
        self.date: str           # YYYY-MM-DD
        self.employee_id: str    # ID сотрудника
        self.employee_name: str  # Имя сотрудника
        self.role: str           # Роль (бармен, официант...)
        self.location: str       # Локация (бар)
        self.start_time: str     # HH:MM
        self.end_time: str       # HH:MM
        self.plan_revenue: float # План выручки
        self.fact_revenue: float # Факт выручки
```

---

### Операции со сменами

#### Создание смены

```python
def create_shift(self, date, employee_id, employee_name, role, location,
                 start_time=None, end_time=None):
    shift = Shift()
    shift.date = date
    shift.employee_id = employee_id
    shift.employee_name = employee_name
    shift.role = role
    shift.location = location
    shift.start_time = start_time
    shift.end_time = end_time

    self.shifts.append(shift)
    self._save_data()
```

#### Обновление revenue

```python
def update_revenue(self, date, employee_id, plan_revenue=None, fact_revenue=None):
    for shift in self.shifts:
        if shift.date == date and shift.employee_id == employee_id:
            if plan_revenue is not None:
                shift.plan_revenue = plan_revenue
            if fact_revenue is not None:
                shift.fact_revenue = fact_revenue

    self._save_data()
```

#### Синхронизация из iiko

```python
# routes/schedule.py
def sync_revenue_from_iiko(date):
    """
    Синхронизирует fact_revenue из кассовых смен iiko
    """
    # 1. Получаем кассовые смены за date
    shifts = iiko_api.get_cash_shifts(date, date)

    # 2. Для каждой смены находим сотрудника
    for shift in shifts:
        emp_id = shift.get('responsibleUserId')
        revenue = shift.get('payOrders', 0) + shift.get('payOrdersCash', 0)

        # 3. Обновляем fact_revenue
        shifts_manager.update_revenue(date, emp_id, fact_revenue=revenue)
```

---

### Meeting Notes

#### Структура

```python
# core/meeting_notes.py
class MeetingNote:
    def __init__(self):
        self.id: str           # Уникальный ID
        self.period: str       # Период (YYYY-MM-DD или YYYY-MM)
        self.bar: str          # Бар
        self.author: str       # Автор заметки
        self.content: str      # Текст заметки
        self.created_at: str   # ISO timestamp
        self.updated_at: str   # ISO timestamp
```

#### Операции

```python
# core/meeting_notes.py
def create_note(self, period, bar, author, content):
    note = MeetingNote()
    note.id = str(uuid.uuid4())
    note.period = period
    note.bar = bar
    note.author = author
    note.content = content
    note.created_at = datetime.now().isoformat()
    note.updated_at = note.created_at

    self.notes.append(note)
    self._save_data()
    return note

def update_note(self, note_id, content):
    for note in self.notes:
        if note.id == note_id:
            note.content = content
            note.updated_at = datetime.now().isoformat()
            self._save_data()
            return note

def get_notes_for_period(self, period):
    return [n for n in self.notes if n.period == period]
```

---

### Выходные дни

#### Структура

```python
# core/shifts_manager.py
class DayOff:
    def __init__(self):
        self.date: str           # YYYY-MM-DD
        self.employee_id: str    # ID сотрудника
        self.employee_name: str  # Имя
        self.reason: str         # Причина (опционально)
```

#### Операции

```python
def add_day_off(self, date, employee_id, employee_name, reason=None):
    day_off = DayOff()
    day_off.date = date
    day_off.employee_id = employee_id
    day_off.employee_name = employee_name
    day_off.reason = reason

    self.days_off.append(day_off)
    self._save_data()

def get_day_offs_for_period(self, date_from, date_to):
    return [
        d for d in self.days_off
        if date_from <= d.date <= date_to
    ]
```

---

## API endpoint'ы

### Смены

```
# Получить смены за период
GET /api/schedule/shifts?dateFrom=...&dateTo=...&employee=...

# Создать смену
POST /api/schedule/shift
Body: {
    "date": "YYYY-MM-DD",
    "employeeId": "...",
    "employeeName": "...",
    "role": "barman",
    "location": "bolshoy",
    "startTime": "14:00",
    "endTime": "23:00"
}

# Обновить смену
PUT /api/schedule/shift/:id
Body: {...}

# Удалить смену
DELETE /api/schedule/shift/:id
```

### Revenue

```
# Получить revenue
GET /api/schedule/revenue/:date

# Обновить revenue
PUT /api/schedule/revenue/:date
Body: {
    "plan": 100000,
    "fact": 95000
}

# Синхронизировать из iiko
POST /api/schedule/revenue/sync/:date
```

### Выходные

```
# Добавить выходной
POST /api/schedule/dayoff
Body: {
    "date": "YYYY-MM-DD",
    "employeeId": "...",
    "employeeName": "...",
    "reason": "..."
}

# Получить выходные
GET /api/schedule/dayoffs?dateFrom=...&dateTo=...
```

### Meeting Notes

```
# Получить заметки
GET /api/schedule/notes?period=...&bar=...

# Создать заметку
POST /api/schedule/notes
Body: {
    "period": "2026-03",
    "bar": "bolshoy",
    "author": "...",
    "content": "..."
}

# Обновить заметку
PUT /api/schedule/notes/:id
Body: {"content": "..."}

# Удалить заметку
DELETE /api/schedule/notes/:id
```

---

## Формат данных (JSON)

```json
{
  "shifts": [
    {
      "date": "2026-03-27",
      "employee_id": "emp-123",
      "employee_name": "Иван Петров",
      "role": "barman",
      "location": "bolshoy",
      "start_time": "14:00",
      "end_time": "23:00",
      "plan_revenue": 100000,
      "fact_revenue": 95000
    }
  ],
  "days_off": [
    {
      "date": "2026-03-28",
      "employee_id": "emp-123",
      "employee_name": "Иван Петров",
      "reason": "Отгул"
    }
  ],
  "meeting_notes": [
    {
      "id": "note-456",
      "period": "2026-03",
      "bar": "bolshoy",
      "author": "Менеджер",
      "content": "Заменить кран №5",
      "created_at": "2026-03-01T10:00:00",
      "updated_at": "2026-03-01T10:00:00"
    }
  ]
}
```

---

## Формулы

### Plan/Fact %

```
Plan/Fact % = (fact_revenue / plan_revenue) × 100%
```

### Выручка за период

```
Total_revenue = Σ(fact_revenue для всех смен в периоде)
```

### % выполнения плана

```
Выполнение % = (Σfact / Σplan) × 100%
```

---

## Зависимости

### От каких модулей зависит
- `core/iiko_api.py` → синхронизация revenue из кассовых смен
- `data/bar_plans.json` → планы выручки по дням

### Кто использует
- Frontend графика (`schedule.html`)
- Дашборд (метрики сотрудников)
- Telegram bot (напоминания о сменах)

---

## Changelog

- **2026-03-27** — Создан документ schedule.md с описанием смен, revenue, meeting notes

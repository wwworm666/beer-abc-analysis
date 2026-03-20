# Lessons — Баги, ловушки, паттерны

## Что это

Собрание всех нетривиальных багов и их решений. Обновляется при каждом интересном фиксе.

---

## Баги

### Баг: "Нет данных" для сотрудника

**Симптом**: API возвращает пустой результат для "Артемий Новаев".

**Причина**: В iiko имя записано как "Новаев Артемий".

**Решение**: Запрашиваем оба варианта:
```python
"WaiterName": {
    "filterType": "IncludeValues",
    "values": [employee_name, reverse_name(employee_name)]
}
```

---

### Баг: Расхождение в количестве чеков

**Симптом**: API = 236, UI iiko = 233.

**Причина**: Разные фильтры удаления.

**Решение**:
```python
"DeletedWithWriteoff": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
"OrderDeleted": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]}
```

---

### Баг: План = 0 для всех сотрудников

**Симптом**: `plan_revenue` всегда 0.

**Причина**: `get_attendance()` возвращал "Пивная культура" для всех.

**Решение**: Переключились на Cash Shifts API:
```python
# Старый способ (НЕ РАБОТАЕТ)
attendance = api.get_attendance(employee_id)

# Новый способ (РАБОТАЕТ)
shifts = api.get_cash_shifts(date_from, date_to)
# shift.pointOfSaleId → Groups API → название бара
```

---

### Баг: CardNumber — это банковские карты, не лояльность

**Симптом**: Запрос карт лояльности через `CardNumber` возвращает замаскированные номера (`****1234`) — длинные, похожие на банковские.

**Причина**: Поле `CardNumber` в OLAP iiko — это номер платёжной карты (Visa/Mastercard), а не карты лояльности. Карты лояльности имеют 7-значные номера.

**Решение**: Использовать `Delivery.CustomerPhone` (телефон клиента) как идентификатор карты лояльности. Фильтровать по `Delivery.CustomerCreatedDateTyped` (дата создания клиента) для подсчёта новых регистраций.

```python
# НЕПРАВИЛЬНО — банковские карты
"groupByRowFields": ["WaiterName", "CardNumber"]

# ПРАВИЛЬНО — телефоны = карты лояльности
"groupByRowFields": ["WaiterName", "Delivery.CustomerPhone"]
```

---

### Баг: Employee ID не найден (порядок имени)

**Симптом**: Для "Васильев Никита" не находится employee_id, все метрики из кассовых смен = 0.

**Причина**: OLAP возвращает "Васильев Никита", а iiko employees API — "Никита Васильев". Точное сравнение строк не работает.

**Решение**: Нормализация имён — сравниваем множества слов:
```python
def normalize_name(name):
    return set(name.lower().strip().split())
# {"васильев", "никита"} == {"никита", "васильев"} ✓
```

---

### Баг: Опоздания = 0 на Render, но работает локально

**Симптом**: `late_count` всегда 0 для всех сотрудников на Render (production), но локально показывает корректные 24/53 опоздания.

**Причина**: `_parse_iso_datetime()` тупо обрезала таймзону через `iso_str.split('+')[0]`. Если iiko Cloud API возвращает UTC-таймстемпы (`"2026-01-20T11:04:48.781+00:00"`), обрезка `+00:00` оставляет UTC-час (11), а не московский (14). Сравнение `hour > 14` никогда не срабатывает. Локально формат мог быть без таймзоны (наивный datetime), поэтому всё работало.

**Решение**: Вместо обрезки — правильная конвертация через `datetime.astimezone()`:

```python
MOSCOW_TZ = timezone(timedelta(hours=3))

def _parse_iso_datetime(self, iso_str):
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is not None:
        dt = dt.astimezone(MOSCOW_TZ).replace(tzinfo=None)
    return dt
```

**Урок**: Никогда не стрипай таймзоны строковыми операциями. `split('+')` — это не парсинг таймзоны, это потеря данных. Всегда конвертируй в нужную зону через стандартные datetime-методы.

---

## Паттерны

### Паттерн: Параллельные OLAP-запросы

OLAP-запросы к iiko медленные (2-5 сек). Делаем параллельно:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        'revenue': executor.submit(get_revenue, ...),
        'draft': executor.submit(get_draft, ...),
    }
    results = {k: f.result() for k, f in futures.items()}
```

**Результат**: 8 сек → 3 сек.

---

### Паттерн: Кэширование с TTL

```python
CACHE = {'data': None, 'timestamp': 0}
CACHE_TTL = 300  # 5 минут

def get_cached_data():
    if CACHE['data'] and time.time() - CACHE['timestamp'] < CACHE_TTL:
        return CACHE['data']

    data = fetch_from_api()
    CACHE['data'] = data
    CACHE['timestamp'] = time.time()
    return data
```

---

### Паттерн: Маппинг названий точек

iiko называет точки по-своему, планы — по-своему:

```python
BAR_NAME_MAPPING = {
    "Пивная культура": "Кременчугская",
    "Большой пр. В.О": "Большой пр В.О.",  # Обрати внимание на точку!
}
```

---

## "Ага-моменты"

### ABC-анализ — это три буквы, не одна

```
1-я буква: Выручка (A=80%, B=15%, C=5%)
2-я буква: Наценка (A≥120%, B=100-120%, C<100%)
3-я буква: Маржа (A=80%, B=15%, C=5%)
```

**AAA** = хит по всем метрикам.
**CAC** = ловушка: низкие продажи, высокая наценка, низкая маржа.

### XYZ — про стабильность, не качество

```
X = CV < 10%   (стабильные продажи)
Y = CV 10-25%  (умеренные колебания)
Z = CV > 25%   (непредсказуемо)
```

---

### Паттерн: Рефакторинг монолита на Flask Blueprints

**Проблема**: `app.py` разросся до 5199 строк — 70+ endpoints, импорты на 30 строк, невозможно быстро найти нужный роут.

**Решение**: Разбили на модули по функциональности:

```python
# Было: app.py (5199 строк)
@app.route('/api/analyze')
@app.route('/api/employees')
@app.route('/api/taps/bars')
# ... ещё 67 роутов

# Стало: routes/ (8 файлов)
routes/
├── pages.py      ← HTML-страницы
├── analysis.py   ← ABC/XYZ/категории
├── employee.py   ← Сотрудники, KPI
├── taps.py       ← Краны
├── stocks.py     ← Остатки
├── dashboard.py  ← План/Факт
├── schedule.py   ← Смены
└── misc.py       ← Утилиты
```

**Ключевые моменты**:

1. **Без url_prefix** — все URL остались идентичными (важно для production)
2. **extensions.py** — общие синглтоны (менеджеры, кэши) вынесены отдельно, чтобы избежать циклических импортов
3. **Blueprints без состояния** — импортируют из extensions.py, не создают свои экземпляры
4. **Один blueprint = одна зона ответственности** — легко найти нужный код

**Результат**:
- app.py: 5199 строк → 31 строка
- Время поиска роута: ~30 сек → ~5 сек
- gunicorn app:app работает без изменений

**Урок**: Рефакторинг монолита не требует изменения URL или логики. Flask Blueprints — это просто организация кода, не архитектурная революция.

---

## Changelog

- 2026-03-21: Добавлен паттерн: рефакторинг монолита на Flask Blueprints
- 2026-01-29: Добавлен баг: опоздания = 0 на Render (таймзона UTC vs МСК)
- 2026-01-28: Добавлены баги: CardNumber vs CustomerPhone, нормализация имён сотрудников
- 2026-01-25: Создан файл, собраны баги из FORARTEM.md

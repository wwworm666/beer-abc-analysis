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

## Changelog

- 2026-01-25: Создан файл, собраны баги из FORARTEM.md

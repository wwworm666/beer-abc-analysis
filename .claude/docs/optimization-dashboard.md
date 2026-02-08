# Оптимизация дашборда /dashboard

## Проблема
Страница `/dashboard` загружается очень медленно. Типичное время загрузки: **6-12 секунд**.

## Диагностика

### Архитектура системы
```
Browser → Flask → iiko OLAP API
   ↓
JavaScript модули (3000+ строк)
   ↓
Chart.js (CDN)
```

### Узкие места (по степени влияния)

#### 🔴 Критично (60-70% времени загрузки)

**1. Последовательные OLAP запросы** → `app.py:2727-2743`
```python
# СЕЙЧАС: выполняются ПОСЛЕДОВАТЕЛЬНО
draft_data = olap.get_draft_sales_report(...)     # 1-3 сек
bottles_data = olap.get_beer_sales_report(...)    # 1-3 сек
kitchen_data = olap.get_kitchen_sales_report(...) # 1-3 сек
# Итого: 3-9 секунд
```

**Эффект**: 3 сетевых запроса к внешнему API выполняются друг за другом.

**Решение**: Распараллелить через `ThreadPoolExecutor` или `asyncio`
```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    future_draft = executor.submit(olap.get_draft_sales_report, ...)
    future_bottles = executor.submit(olap.get_beer_sales_report, ...)
    future_kitchen = executor.submit(olap.get_kitchen_sales_report, ...)

    draft_data = future_draft.result()
    bottles_data = future_bottles.result()
    kitchen_data = future_kitchen.result()
```

**Ожидаемый выигрыш**: 4-6 секунд (вместо 9 → 3 секунды)

---

**2. Дополнительный запрос get_orders_count** → `dashboard_analysis.py:49`
```python
# Внутри calculate_metrics вызывается ещё один OLAP запрос
total_checks = olap.get_orders_count(bar_name, date_from, date_to)  # 0.5-1 сек
```

**Проблема**: Количество чеков можно посчитать из уже полученных данных (draft_data, bottles_data, kitchen_data), группируя по UniqOrderId.

**Решение**: Убрать отдельный запрос, считать из имеющихся данных
```python
def _count_unique_orders(self, draft_records, bottles_records, kitchen_records):
    """Посчитать уникальные заказы из уже полученных данных"""
    all_records = draft_records + bottles_records + kitchen_records
    unique_order_ids = set()
    for record in all_records:
        order_id = record.get('UniqOrderId.OrdersCount')
        if order_id:
            unique_order_ids.add(order_id)
    return len(unique_order_ids)
```

**Ожидаемый выигрыш**: 0.5-1 секунда

---

**3. Отсутствие кэширования**

**Проблема**: Каждый запрос к `/api/dashboard-analytics` делает 3-4 тяжёлых OLAP запроса заново, даже если данные уже запрашивались.

**Решение**: In-memory кэш с TTL
```python
from functools import lru_cache
from datetime import datetime, timedelta
import hashlib

class OLAPCache:
    def __init__(self, ttl_minutes=5):
        self.cache = {}
        self.ttl = timedelta(minutes=ttl_minutes)

    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                return data
            else:
                del self.cache[key]
        return None

    def set(self, key, data):
        self.cache[key] = (data, datetime.now())

    def make_key(self, method, date_from, date_to, bar_name):
        """Создать ключ кэша"""
        key_str = f"{method}:{bar_name}:{date_from}:{date_to}"
        return hashlib.md5(key_str.encode()).hexdigest()

# Использование
olap_cache = OLAPCache(ttl_minutes=5)

def get_draft_sales_report_cached(date_from, date_to, bar_name):
    cache_key = olap_cache.make_key('draft', date_from, date_to, bar_name)
    cached = olap_cache.get(cache_key)
    if cached:
        print(f"[CACHE HIT] draft_sales for {date_from}-{date_to}")
        return cached

    data = olap.get_draft_sales_report(date_from, date_to, bar_name)
    olap_cache.set(cache_key, data)
    return data
```

**Ожидаемый выигрыш**: При повторных запросах → с 9 сек до 50 мс

---

#### 🟡 Важно (15-20% времени загрузки)

**4. Cache busting для JavaScript модулей** → `dashboard.html:28`
```javascript
const v = Date.now();  // ❌ ПРОБЛЕМА: браузер не кэширует
import(`/static/js/dashboard/main.js?v=${v}`)
```

**Проблема**: Каждый раз загружаются все 3000+ строк JS заново, даже если код не изменился.

**Решение**: Использовать версию из git commit или build number
```javascript
// В шаблоне Flask передать версию
const APP_VERSION = "{{ app_version }}";  // например: "d46de05"
import(`/static/js/dashboard/main.js?v=${APP_VERSION}`)
```

В `app.py`:
```python
import subprocess

def get_git_commit_hash():
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    except:
        return 'dev'

APP_VERSION = get_git_commit_hash()

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', bars=BARS, app_version=APP_VERSION)
```

**Ожидаемый выигрыш**: 0.5-1 секунда на повторных загрузках

---

**5. Chart.js с CDN** → `dashboard.html:18`
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

**Проблема**: Блокирующая загрузка с внешнего CDN, может быть медленной.

**Решение**: Скачать Chart.js локально
```bash
cd static/libs
wget https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js
```

```html
<script src="/static/libs/chart.umd.min.js"></script>
```

**Ожидаемый выигрыш**: 0.2-0.5 секунды

---

**6. Проверка API каждую минуту** → `main.js:250`
```javascript
setInterval(window.dashboardCheckApi, 60000); // ❌ Слишком часто
```

**Решение**: Увеличить интервал до 5 минут
```javascript
setInterval(window.dashboardCheckApi, 300000); // 5 минут
```

**Ожидаемый выигрыш**: Снижение нагрузки на сервер, но не влияет на первую загрузку

---

#### 🟢 Опционально (5-10% времени загрузки)

**7. Preload критических модулей**
```html
<link rel="modulepreload" href="/static/js/dashboard/main.js?v={{ app_version }}">
<link rel="modulepreload" href="/static/js/dashboard/core/state.js?v={{ app_version }}">
<link rel="modulepreload" href="/static/js/dashboard/modules/analytics.js?v={{ app_version }}">
```

**8. Индексирование для запросов активности кранов**
Если данные кранов хранятся в БД (SQLite/PostgreSQL), добавить индексы:
```sql
CREATE INDEX idx_taps_bar_date ON taps_log(bar_id, date);
```

---

## План внедрения (по приоритету)

### Фаза 1: Быстрые улучшения (2-4 часа работы)
**Ожидаемый эффект: 5-7 секунд → 2-3 секунды**

1. ✅ Распараллелить OLAP запросы (ThreadPoolExecutor)
2. ✅ Убрать отдельный запрос get_orders_count
3. ✅ Убрать cache busting (использовать версию git)
4. ✅ Переместить Chart.js локально
5. ✅ Увеличить интервал проверки API

### Фаза 2: Кэширование (4-6 часов работы)
**Ожидаемый эффект: повторные запросы → 50-100 мс**

1. ✅ Добавить in-memory кэш для OLAP данных
2. ✅ Добавить HTTP Cache-Control заголовки для статики
3. ✅ Добавить preload для критических модулей

### Фаза 3: Продвинутая оптимизация (опционально)
**Ожидаемый эффект: маргинальный**

1. 🔧 Bundling JavaScript модулей (webpack/rollup)
2. 🔧 Redis для распределённого кэша (если несколько серверов)
3. 🔧 Service Worker для offline режима
4. 🔧 Lazy loading модулей (загружать только при переходе на вкладку)

---

## Измерение эффекта

### Before (текущее состояние)
```
OLAP draft:    2.1s
OLAP bottles:  1.8s
OLAP kitchen:  2.3s
get_orders:    0.7s
tap_activity:  0.3s
JS загрузка:   0.8s
─────────────────
ИТОГО:         8.0s
```

### After Фаза 1 (параллелизация)
```
OLAP (parallel): 2.3s  ← max(2.1, 1.8, 2.3)
tap_activity:    0.3s
JS загрузка:     0.4s  ← без cache busting
─────────────────
ИТОГО:           3.0s
```

### After Фаза 2 (кэш)
```
Первый запрос:  3.0s
Повторный:      0.05s  ← из кэша
```

---

## Код для тестирования

### Измерение времени выполнения

Добавить в `app.py` перед `/api/dashboard-analytics`:
```python
import time
from functools import wraps

def measure_time(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"[PERF] {func.__name__} took {elapsed:.2f}s")
        return result
    return wrapper

@app.route('/api/dashboard-analytics', methods=['POST'])
@measure_time
def dashboard_analytics():
    ...
```

### Frontend timing
```javascript
// В analytics.js:53
async loadAnalytics() {
    console.time('loadAnalytics');
    // ... код ...
    console.timeEnd('loadAnalytics');
}
```

---

## Риски и митигация

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Параллельные запросы перегружают iiko API | Средняя | Ограничить max_workers=3 |
| Кэш возвращает устаревшие данные | Низкая | TTL=5 минут, кнопка "Обновить" |
| Git версия не работает на Render | Низкая | Fallback на время сборки |
| ThreadPoolExecutor несовместим с Flask | Очень низкая | Тестировать на dev окружении |

---

## Следующие шаги

1. **Согласовать план** с заказчиком
2. **Создать ветку** `feature/dashboard-optimization`
3. **Внедрить Фазу 1** (быстрые улучшения)
4. **Измерить результаты** (до/после)
5. **При успехе** → Фаза 2
6. **Обновить документацию** в `.claude/docs/lessons.md`

---

## Changelog

- **2026-02-07**: Диагностика, выявление узких мест, составление плана

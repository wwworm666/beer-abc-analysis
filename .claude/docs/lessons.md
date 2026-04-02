# Уроки и паттерны

## Что это

Сборник багов, проблем, решений и паттернов разработки. Формат: Problem → Cause → Solution.

---

## Критические особенности iiko API

### 1. Дата `to` — EXCLUSIVE в OLAP

**Problem:** OLAP запросы не включают последний день периода.

**Cause:** iiko API трактует параметр `to` как НЕ включительный.

**Solution:** Добавлять +1 день к конечной дате для OLAP запросов:

```python
olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
```

**Исключение:** Кассовые смены (cashshifts) используют inclusive даты — не требовать +1 день.

---

### 2. AuthUser vs WaiterName

**Problem:** `WaiterName` пропускает все продажи через стойку (нет столика → нет официанта).

**Cause:** WaiterName заполняется только для заказов с столиками.

**Solution:** Использовать `AuthUser` ("Авторизовал") для агрегированных метрик:

```python
# core/olap_reports.py:1052-1055
request = {
    "groupByRowFields": ["AuthUser"],  # "Авторизовал" — кто пробил чек
    "aggregateFields": [
        "UniqOrderId",
        "UniqOrderId.OrdersCount",
        "DishDiscountSumInt",
        "DiscountSum"
    ]
}
```

---

### 3. Матчинг имён сотрудников

**Problem:** `AuthUser` возвращает "Новаев Артемий", а iiko employee называется "Артемий Новаев".

**Cause:** Разный формат имён (фамилия-имя vs имя-фамилия).

**Solution:** Использовать word-set intersection:

```python
# core/employee_analysis.py:64-70
emp_words = set(employee_name.lower().split())
for auth_name, data in aggregated_data.items():
    auth_words = set(auth_name.lower().split())
    if emp_words == auth_words or (len(emp_words) >= 2 and emp_words.issubset(auth_words)):
        emp_aggregated = data
        break
```

---

### 4. Поле для количества чеков

**Problem:** Нужно добавить ОБА поля в `aggregateFields`.

**Cause:** `UniqOrderId` — это ID заказа, `UniqOrderId.OrdersCount` — счётчик.

**Solution:**

```python
"aggregateFields": [
    "UniqOrderId",              # ID заказа
    "UniqOrderId.OrdersCount",  # Счётчик чеков (это и есть "количество чеков")
    ...
]
```

---

### 5. Средний чек

**Problem:** Нельзя смешивать выручку из OLAP и чеки из кассовых смен.

**Cause:** Разные источники данных дадут неверный результат.

**Solution:** Считать из OLAP:

```
Средний чек = DishDiscountSumInt / UniqOrderId.OrdersCount
```

---

## Паттерны разработки

### 1. Thread-safe операции

**Problem:** Race conditions при одновременном доступе к данным.

**Solution:** Использовать `threading.Lock()`:

```python
# core/taps_manager.py:81
self._lock = threading.Lock()

def start_tap(self, ...):
    with self._lock:  # Блокировка на время операции
        ...
        self._save_data()
```

---

### 2. Backup перед записью

**Problem:** Повреждение данных при сбое записи.

**Solution:** Создавать backup перед изменением файла:

```python
# core/plans_manager.py:139-174
def _write_file(self, data: Dict):
    # Создаем backup перед записью
    self._create_backup()

    # Записываем во временный файл
    temp_file = self.data_file + '.tmp'
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Атомарно переименовываем
    os.replace(temp_file, self.data_file)
```

---

### 3. Кэширование OLAP запросов

**Problem:** OLAP API медленный, частые запросы создают нагрузку.

**Solution:** Кэшировать результаты с TTL:

```python
# extensions.py
DASHBOARD_OLAP_CACHE_TTL = 600  # 10 минут
EMPLOYEES_CACHE_TTL = 300       # 5 минут

# Кэширование в routes
@cache.cached(timeout=DASHBOARD_OLAP_CACHE_TTL)
def get_dashboard_analytics():
    ...
```

---

### 4. Retry logic для нестабильного API

**Problem:** iiko API иногда возвращает timeout.

**Solution:** Retry с экспоненциальной задержкой:

```python
# core/olap_reports.py:374-409
max_retries = 3
timeout = 120

for attempt in range(max_retries):
    try:
        response = requests.post(url, params=params, json=request_body, timeout=timeout)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.ReadTimeout:
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # Exponential backoff
        else:
            raise
```

---

### 5. Валидация данных планов

**Problem:** Некорректные данные планов ломают расчёты.

**Solution:** Строгая валидация схемы:

```python
# core/plans_manager.py:194-238
PLAN_SCHEMA = {
    'revenue': (float, int),
    'checks': (int,),
    'averageCheck': (float, int),
    ...
}

def _validate_plan_data(self, plan_data: Dict) -> bool:
    # Проверяем наличие всех обязательных полей
    for field, expected_types in self.PLAN_SCHEMA.items():
        if field not in plan_data:
            raise ValueError(f"Missing required field: {field}")

        value = plan_data[field]
        if not isinstance(value, expected_types):
            raise ValueError(f"Field '{field}' has wrong type")

        if value < 0:
            raise ValueError(f"Field '{field}' cannot be negative")

    # Проверяем что сумма долей ≈ 100%
    shares_sum = (plan_data['draftShare'] +
                  plan_data['packagedShare'] +
                  plan_data['kitchenShare'])

    if not (99.0 <= shares_sum <= 101.0):
        raise ValueError(f"Sum of shares must be approximately 100%")
```

---

## Планы: независимое редактирование (v3)

**Problem:** Редактирование планов было привязано к периоду дашборда, что создавало путаницу.

**Cause:** Пользователь должен был выбирать период в дашборде, затем открывать редактирование — но период мог охватывать несколько месяцев.

**Solution (v3):** Полностью независимое редактирование планов:
1. Модальное окно с собственным селектором периода (Месяц, Год, Заведение)
2. Кнопка "Загрузить план" — загружает план за выбранный месяц
3. Если план найден — показывается для редактирования
4. Если план не найден — создаётся пустой шаблон
5. Кнопки "Сохранить"/"Удалить" показываются только после загрузки

```javascript
// Выбор периода в модальном окне
const month = this.planMonthSelect?.value;
const year = this.planYearSelect?.value;
const venue = this.planVenueSelect?.value;
this.selectedPeriodKey = `${year}-${month}`;

// Загрузка плана
const plan = await getPlan(venue, this.selectedPeriodKey);
```

**Files:**
- `templates/dashboard/plans_tab.html` — селектор месяца/года/заведения
- `static/js/dashboard/modules/plans.js` — `loadPlanFromModal()`, `openCreateModal()`

---

## Планы: редактирование только одного месяца (v2, устарело)

**Problem:** Пользователь может случайно выбрать период охватывающий два месяца (например, 25 марта — 5 апреля), что приведёт к некорректному сохранению плана.

**Cause:** Планы хранятся в формате `venue_YYYY-MM` (например, `bolshoy_2025-10`) — один план на один месяц. При редактировании периода охватывающего несколько месяцев непонятно в какой план сохранять данные.

**Solution (v2):**
1. Проверять что выбранный период находится в рамках одного месяца
2. Блокировать кнопки "Редактировать" и "Удалить" если период охватывает несколько месяцев
3. Показывать месяц в заголовке модального окна

---

## Баги и решения

### 1. Двойной учёт продаж официантов

**Problem:** Добавление `OrderWaiter.Name` в `groupByRowFields` создавало дублирование строк.

**Cause:** Если `WaiterName` и `OrderWaiter.Name` различаются, OLAP создаёт отдельные строки.

**Solution:** Использовать ТОЛЬКО `WaiterName`:

```python
# core/olap_reports.py:646-652
# Добавляем поля официантов если требуется
if include_waiter:
    # ВАЖНО: Используем ТОЛЬКО WaiterName (официант блюда)
    # Добавление OrderWaiter.Name в groupByRowFields создаёт дублирование строк!
    groupByRowFields.append("WaiterName")
```

---

### 2. Отрицательные часы работы

**Problem:** Смены с отрицательной длительностью.

**Cause:** Смена закрыта в предыдущий день (переход через полночь).

**Solution:** Проверка на отрицательные значения:

```python
# core/iiko_api.py:413-415
if shift_hours < 0 or shift_hours > 24:
    shift_hours = 0.0
```

---

### 3. Опоздания >24 часов

**Problem:** Некорректный подсчёт опозданий.

**Cause:** Смена может быть открыта после 14:30 но до 15:00.

**Solution:** Точная проверка времени:

```python
# core/iiko_api.py:424-426
if open_dt:
    if open_dt.hour > 14 or (open_dt.hour == 14 and open_dt.minute > 30):
        is_late = True
```

---

## Производительность

### 1. Оптимизация widget API

**Problem:** 5 OLAP запросов для виджета.

**Solution:** 1 комплексный запрос вместо 5:

```python
# core/olap_reports.py:339-411
def get_all_sales_report(self, date_from, date_to, bar_name=None):
    """
    Получить КОМПЛЕКСНЫЙ OLAP отчет (розлив + фасовка + кухня) за ОДИН запрос.
    Оптимизация: 1 HTTP запрос вместо 3 параллельных.
    """
```

**Результат:** 5x быстрее загрузка.

---

### 2. Кэширование номенклатуры

**Problem:** Частые запросы `/products` для маппинга товаров.

**Solution:** Кэшировать на 15 минут:

```python
# core/olap_reports.py
@cache.cached(timeout=900)  # 15 минут
def get_nomenclature(self):
    ...
```

---

## Changelog

- **2026-03-27** — Создан документ lessons.md с описанием критических особенностей iiko API, паттернов и багов

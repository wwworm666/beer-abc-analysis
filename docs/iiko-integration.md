# Интеграция с iiko API

## Что это

Модуль интеграции с iiko API для получения данных о продажах, кассовых сменах, сотрудниках. Критически важен — все метрики системы основаны на данных из iiko.

## Файлы

- [`core/iiko_api.py`](../../core/iiko_api.py) — authentication, cashshifts v2, сотрудники, attendance
- [`core/olap_reports.py`](../../core/olap_reports.py) — OLAP отчёты v2 (all_sales, beer, draft, kitchen)

---

## Как работает

### Authentication

iiko использует SHA-1 хэш пароля для аутентификации:

```python
# core/iiko_api.py:21-48
def authenticate(self):
    password_hash = hashlib.sha1(self.password.encode()).hexdigest()

    url = f"{self.base_url}/auth"
    params = {"login": self.login, "pass": password_hash}

    response = requests.get(url, params=params)
    # Токен приходит в формате <string>токен</string>
    self.token = response.text.strip().replace("<string>", "").replace("</string>", "")
```

**Важно:** Токен нужно освобождать через `logout()` после завершения работы (лицензии ограничены).

---

### OLAP API v2

OLAP (Online Analytical Processing) — основной источник данных о продажах.

#### Формат запроса

```python
# core/olap_reports.py:573-625
def _build_all_sales_olap_request(self, date_from, date_to, bar_name=None):
    request = {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "DishName",
            "DishGroup.TopParent",  # Категория: Розлив/Фасовка/Кухня
            "DishForeignName",
            "OpenDate.Typed",
            "UniqOrderId.Id"  # Уникальный ID заказа
        ],
        "groupByColFields": [],
        "aggregateFields": [
            "UniqOrderId.OrdersCount",  # Количество чеков
            "DishAmountInt",            # Количество блюд
            "DishDiscountSumInt",       # Выручка
            "DiscountSum",              # Сумма скидок
            "ProductCostBase.ProductCost",  # Себестоимость
            "ProductCostBase.MarkUp"    # Наценка %
        ],
        "filters": {
            "OpenDate.Typed": {
                "filterType": "DateRange",
                "periodType": "CUSTOM",
                "from": date_from,
                "to": date_to  # ВАЖНО: EXCLUSIVE!
            },
            "DeletedWithWriteoff": {"values": ["NOT_DELETED"]},
            "OrderDeleted": {"values": ["NOT_DELETED"]}
        }
    }

    if bar_name:
        request["filters"]["Store.Name"] = {"values": [bar_name]}

    return request
```

#### Формула расчёта количества чеков

**Проблема:** OLAP не возвращает прямое количество чеков. Нужно использовать `UniqOrderId.Id`.

**Решение:** Считаем уникальные ID заказов:

```python
# core/dashboard_analysis.py:245-271
def _count_unique_orders(self, draft_records, bottles_records, kitchen_records):
    unique_order_ids = set()
    all_records = draft_records + bottles_records + kitchen_records

    for record in all_records:
        # КЛЮЧЕВОЕ: используем UniqOrderId.Id (уникальный UUID заказа)
        order_id = record.get('UniqOrderId.Id')
        if order_id:
            unique_order_ids.add(str(order_id))

    return len(unique_order_ids)
```

#### Формула среднего чека

```
Средний чек = Выручка OLAP / Количество уникальных заказов
            = Σ(DishDiscountSumInt) / count(DISTINCT UniqOrderId.Id)
```

**Важно:** Не смешивать с выручкой из кассовых смен — разные источники дадут неверный результат.

---

### Cashshifts API v2

Кассовые смены содержат точные данные о локациях сотрудников и выручке.

#### Получение смен

```python
# core/iiko_api.py:215-269
def get_cash_shifts(self, date_from, date_to, department_id=None, status=None):
    url = f"{self.base_url}/v2/cashshifts/list"
    params = {
        "key": self.token,
        "openDateFrom": date_from,
        "openDateTo": date_to
    }
    if department_id:
        params["departmentId"] = department_id
    if status:
        params["status"] = status  # 'OPEN' или 'CLOSED'

    response = requests.get(url, params=params)
    return response.json()  # JSON (не XML!)
```

#### Метрики сотрудника из смен

```python
# core/iiko_api.py:346-513
def get_employee_metrics_from_shifts(self, date_from, date_to):
    """
    Returns:
    {
        employee_id: {
            'shifts_count': int,           # Количество смен
            'dates': [str],                # Даты смен
            'locations': {str: int},       # Локация -> кол-во смен
            'shift_locations': {str: str}, # Дата -> локация
            'shift_revenues': {str: float},# Дата -> выручка
            'total_revenue': float,        # Выручка (card + cash)
            'revenue_card': float,
            'revenue_cash': float,
            'total_hours': float,          # Часы работы
            'late_count': int,             # Опоздания (>14:30)
            'late_dates': [str]
        }
    }
    """
```

#### Формула расчёта опозданий

Смена считается опозданием, если открыта позже 14:30:

```python
# core/iiko_api.py:419-429
if open_date_str:
    open_dt = self._parse_iso_datetime(open_date_str)
    if open_dt:
        if open_dt.hour > 14 or (open_dt.hour == 14 and open_dt.minute > 30):
            is_late = True
            emp['late_count'] += 1
```

---

### Критические особенности

#### 1. Дата `to` — EXCLUSIVE

**Проблема:** OLAP API трактует параметр `to` как НЕ включительный.

**Решение:** Добавлять +1 день к конечной дате:

```python
# При вызове OLAP запросов
olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
```

**Исключение:** Кассовые смены (cashshifts) используют `inclusive` даты — не требовать +1 день.

---

#### 2. AuthUser vs WaiterName

**Проблема:**
- `WaiterName` = официант за столиком → пропускает продажи через стойку (нет столика → нет WaiterName)
- `AuthUser` = "Авторизовал" → видит ВСЕ чеки (стойка + столики)

**Решение:** Использовать `AuthUser` для агрегированных метрик:

```python
# core/olap_reports.py:1025-1119
def get_employee_aggregated_metrics(self, date_from, date_to, bar_name=None):
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

#### 3. Матчинг имён сотрудников

**Проблема:** `AuthUser` может вернуть "Новаев Артемий", а iiko employee называется "Артемий Новаев".

**Решение:** Использовать word-set intersection:

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

#### 4. Поле для количества чеков

**Проблема:** Нужно добавить ОБА поля в `aggregateFields`:
- `UniqOrderId` — ID заказа
- `UniqOrderId.OrdersCount` — счётчик уникальных заказов

**Решение:**

```python
"aggregateFields": [
    "UniqOrderId",              # ID заказа
    "UniqOrderId.OrdersCount",  # Счётчик чеков
    ...
]
```

---

### Формулы расчётов

#### Выручка
```
Выручка = Σ(DishDiscountSumInt) из OLAP
```

#### Себестоимость
```
Себестоимость = Σ(ProductCostBase.ProductCost) из OLAP
```

#### Прибыль (маржа)
```
Прибыль = Выручка - Себестоимость
        = Σ(DishDiscountSumInt) - Σ(ProductCostBase.ProductCost)
```

#### Наценка (взвешенная)
```
Средняя наценка = Σ(MarkUp × Cost) / Σ(Cost)

# core/dashboard_analysis.py:192-223
def _calculate_weighted_markup(self, records):
    total_weighted_markup = 0.0
    total_cost = 0.0

    for record in records:
        markup = record.get('ProductCostBase.MarkUp', 0)
        cost = record.get('ProductCostBase.ProductCost', 0)

        if cost > 0:
            total_weighted_markup += markup * cost
            total_cost += cost

    return total_weighted_markup / total_cost if total_cost > 0 else 0
```

#### Средний чек
```
Средний чек = DishDiscountSumInt / UniqOrderId.OrdersCount
```

**Важно:** Считать из OLAP, НЕ смешивать с выручкой из кассовых смен.

---

## Changelog

- **2026-03-27** — Создан документ iiko-integration.md с детальным описанием API, формул и критических особенностей

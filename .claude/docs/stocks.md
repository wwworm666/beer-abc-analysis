# Остатки товаров

> **Раздел про Честный Знак переехал в отдельный документ:**
> [chz-stock-integration.md](chz-stock-integration.md) — полная схема
> dispenser API, КПП-привязка партий к барам, авторефреш в 03:00,
> вкладка «Сроки годности».
>
> Этот файл описывает только taplist / kitchen / bottles. Для всего что
> касается ЧЗ и поэкземплярного учёта смотрите новый документ.

## Что это

Модуль учёта остатков: кеги на кранах (taplist), кухня, фасовка, интеграция с Честным ЗНАКом.

## Файлы

- [`routes/stocks.py`](../../routes/stocks.py) — Flask endpoint'ы (включая `/api/stocks/expiry`, `/api/chz/refresh` — см. chz-stock-integration.md)
- [`chz_test/chz.py`](../../chz_test/chz.py) — единый ЧЗ-клиент (auth + dispenser API + парсер CSV)
- [`core/iiko_barcodes.py`](../../core/iiko_barcodes.py) — баркоды iiko из XML
- [`core/chz_scheduler.py`](../../core/chz_scheduler.py) — daemon-thread авторефреш

---

## Как работает

### Taplist (кеги на кранах)

#### Источник данных

Данные о кранах берутся из `taps_manager`:

```python
# routes/stocks.py
@api.route('/stocks/taplist')
def get_taplist():
    """
    Получить список всех кранов с установленными кегами
    """
    bars = taps_manager.get_bars()
    taplist = []

    for bar in bars:
        bar_data = taps_manager.get_bar_taps(bar['bar_id'])

        for tap in bar_data['taps']:
            if tap['status'] == 'active':
                taplist.append({
                    'bar_name': bar_data['bar_name'],
                    'tap_number': tap['tap_number'],
                    'beer_name': tap['current_beer'],
                    'keg_id': tap['current_keg_id'],
                    'started_at': tap['started_at']
                })

    return jsonify(taplist)
```

#### Формат ответа

```json
[
    {
        "bar_name": "Бар 1",
        "tap_number": 5,
        "beer_name": "Жигулёвское",
        "keg_id": "KEG-12345",
        "started_at": "2026-03-25T10:00:00+03:00"
    }
]
```

---

### Kitchen (кухня)

#### OLAP запрос

```python
# core/olap_reports.py:292-337
def get_kitchen_sales_report(self, date_from, date_to, bar_name=None):
    """
    Получить OLAP отчет по продажам блюд кухни (исключая напитки)
    """
    request_body = self._build_kitchen_olap_request(date_from, date_to, bar_name)

    url = f"{self.api.base_url}/v2/reports/olap"
    params = {"key": self.token}
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, params=params, json=request_body, headers=headers)
    return response.json()
```

#### Фильтр по категориям

```python
# core/olap_reports.py:519-571
def _build_kitchen_olap_request(self, date_from, date_to, bar_name=None):
    request = {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "DishName",
            "DishGroup.TopParent",
            "DishForeignName",
            "OpenDate.Typed"
        ],
        "aggregateFields": [
            "UniqOrderId.OrdersCount",
            "DishAmountInt",
            "DishDiscountSumInt",
            "ProductCostBase.ProductCost",
            "ProductCostBase.MarkUp"
        ],
        "filters": {
            "OpenDate.Typed": {
                "filterType": "DateRange",
                "from": date_from,
                "to": date_to
            },
            # Исключаем напитки
            "DishGroup.TopParent": {
                "filterType": "ExcludeValues",
                "values": ["Напитки Фасовка", "Напитки Розлив"]
            },
            "DeletedWithWriteoff": {"values": ["NOT_DELETED"]},
            "OrderDeleted": {"values": ["NOT_DELETED"]}
        }
    }

    return request
```

---

### Bottles (фасовка)

#### OLAP запрос

```python
# core/olap_reports.py:198-243
def get_draft_sales_report(self, date_from, date_to, bar_name=None):
    """
    Получить OLAP отчет по продажам разливного/фасованного пива

    draft: True - разливное, False - фасовка
    """
    drink_group = "Напитки Розлив" if draft else "Напитки Фасовка"

    request = {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "DishName",
            "DishGroup.ThirdParent",
            "DishForeignName",
            "OpenDate.Typed"
        ],
        "aggregateFields": [
            "UniqOrderId.OrdersCount",
            "DishAmountInt",
            "DishDiscountSumInt",
            "ProductCostBase.ProductCost",
            "ProductCostBase.MarkUp"
        ],
        "filters": {
            "OpenDate.Typed": {
                "filterType": "DateRange",
                "from": date_from,
                "to": date_to
            },
            "DishGroup.TopParent": {
                "filterType": "IncludeValues",
                "values": [drink_group]
            },
            "DeletedWithWriteoff": {"values": ["NOT_DELETED"]},
            "OrderDeleted": {"values": ["NOT_DELETED"]}
        }
    }

    return request
```

---

### Честный ЗНАК API

#### Authentication

```python
# core/chestny_znak.py
class ChestnyZnakAPI:
    def __init__(self, sandbox=False):
        self.base_url = (
            "https://sandbox.api.marking.crpt.ru" if sandbox
            else "https://api.marking.crpt.ru"
        )
        self.auth_token = None

    def authenticate(self, login, password):
        """
        Получить токен аутентификации
        """
        url = f"{self.base_url}/api/v2/auth"
        body = {
            "login": login,
            "password": password
        }

        response = requests.post(url, json=body)
        data = response.json()

        self.auth_token = data.get('token')
        return self.auth_token
```

#### Balance (остатки)

```python
# core/chestny_znak.py
def get_balance(self, product_code=None):
    """
    Получить остатки товаров на складе

    product_code: код товара (опционально)
    """
    url = f"{self.base_url}/api/v2/balance"
    params = {}

    if product_code:
        params['product'] = product_code

    headers = {
        "Authorization": f"Bearer {self.auth_token}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, params=params, headers=headers)
    return response.json()
```

#### Search (поиск товаров)

```python
def search_products(self, query):
    """
    Поиск товаров по названию/коду
    """
    url = f"{self.base_url}/api/v2/products/search"
    params = {"q": query}

    headers = {"Authorization": f"Bearer {self.auth_token}"}

    response = requests.get(url, params=params, headers=headers)
    return response.json()
```

#### Expiring Codes (истекающие коды)

```python
def get_expiring_codes(self, days_threshold=30):
    """
    Получить коды маркировки с истекающим сроком годности

    days_threshold: порог в днях
    """
    url = f"{self.base_url}/api/v2/codes/expiring"
    params = {"days": days_threshold}

    headers = {"Authorization": f"Bearer {self.auth_token}"}

    response = requests.get(url, params=params, headers=headers)
    return response.json()
```

#### Codes Info (информация о кодах)

```python
def get_codes_info(self, codes):
    """
    Получить информацию о кодах маркировки

    codes: список кодов
    """
    url = f"{self.base_url}/api/v2/codes"
    body = {"codes": codes}

    headers = {
        "Authorization": f"Bearer {self.auth_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=body, headers=headers)
    return response.json()
```

---

## API endpoint'ы

### Остатки

```
# Кеги на кранах
GET /api/stocks/taplist

# Кухня
GET /api/stocks/kitchen?dateFrom=...&dateTo=...

# Фасовка
GET /api/stocks/bottles?dateFrom=...&dateTo=...
```

### Честный ЗНАК

```
# Баланс
GET /api/chestny-znak/balance?product=...

# Поиск
GET /api/chestny-znak/search?q=...

# Истекающие коды
GET /api/chestny-znak/expiring?days=30

# Информация о кодах
POST /api/chestny-znak/codes-info
Body: {"codes": ["...", "..."]}
```

---

## Формат данных

### Taplist

```json
[
    {
        "bar_name": "Бар 1",
        "tap_number": 5,
        "beer_name": "Жигулёвское",
        "keg_id": "KEG-12345",
        "started_at": "2026-03-25T10:00:00+03:00"
    }
]
```

### Kitchen

```json
{
    "data": [
        {
            "Store.Name": "Бар 1",
            "DishName": "Бургер классический",
            "DishGroup.TopParent": "Кухня",
            "DishAmountInt": 150,
            "DishDiscountSumInt": 75000.0,
            "ProductCostBase.ProductCost": 35000.0,
            "ProductCostBase.MarkUp": 1.85
        }
    ]
}
```

### Честный ЗНАК Balance

```json
{
    "balances": [
        {
            "product_code": "01234567890123",
            "quantity": 100,
            "warehouse": "Склад 1"
        }
    ]
}
```

---

## Зависимости

### От каких модулей зависит
- `core/taps_manager.py` → данные о кранах
- `core/olap_reports.py` → данные о продажах кухни/фасовки
- Честный ЗНАК API → внешние данные

### Кто использует
- Frontend остатков (`stocks.html`)
- Дашборд (интеграция)
- Telegram bot (напоминания об истекающих кодах)

---

## Changelog

- **2026-03-27** — Создан документ stocks.md с описанием taplist, кухни, фасовки, Честного ЗНАКа

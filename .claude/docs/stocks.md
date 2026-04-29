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

---

### Сводный заказ (Order Board) — прототип

#### Что это

Объединённая таблица фасовка + кеги + кухня в одной вкладке. Цель — дать менеджеру
**одно представление** со всеми позициями, требующими решения «сколько заказать»,
вместо переключения между 4 вкладками («Таплист»/«Фасовка»/«Сроки»/«Меню кухни»).

Главное отличие от старых вкладок: для каждой позиции считается **рекомендованное
количество** к заказу с учётом срока поставки, страхового запаса и срока годности.

#### Endpoint

```
GET /api/stocks/order-board?bar=<bar_name>
```

Возвращает: items[] (отсортирован по срочности), counters по уровням срочности,
суммарная рекомендация.

#### Формулы (см. `routes/stocks.py`)

**Рекомендация к заказу** (`_calc_recommendation`):

```
target_stock = avg_sales × (lead_time_days + SAFETY_DAYS)
deficit      = max(0, target_stock − stock)
recommended  = ceil(deficit / pack_size) × pack_size
```

Где:
- `avg_sales` — расход/день за последние 30 дней
  (из `OlapReports.get_store_operations_report`)
- `lead_time_days` — срок поставки от поставщика (из `SUPPLIER_PARAMS`,
  fallback = 3 дня)
- `SAFETY_DAYS = 3` — страховой запас сверх lead_time на колебания спроса
- `pack_size` — минимальная партия (упаковка), в прототипе = 1 для всех

**Скорость продаж** (`_velocity`) — классификация по продажам в неделю
(`avg_sales × 7`):

| Класс     | Условие                            | Поведение                                    |
|-----------|------------------------------------|----------------------------------------------|
| `dead`    | `avg_sales == 0` (нет продаж)      | `recommended = 0`, urgency = `low`           |
| `slow`    | < 1 продажи в неделю               | `recommended = 0`, urgency = `low`           |
| `regular` | 1–7 в неделю                       | обычная логика                               |
| `fast`    | ≥ 7 в неделю                       | обычная логика                               |

Граничные константы: `SLOW_MOVER_WEEKLY_SALES = 1.0`,
`FAST_MOVER_WEEKLY_SALES = 7.0`.

**Зачем это:** позиция типа «Эплтон Апельсин 0.5л» с продажами 0.03/день
(≈ раз в месяц) при нулевом остатке без velocity-классификации даёт
`days_left = 0` → `urgency = critical`. Это шум: менеджеру не нужно
бежать заказывать редко-продаваемое. Velocity отрезает таких.

**Спецслучаи рекомендации:**
- `velocity ∈ {dead, slow}` → `recommended = 0` (не пополняем)
- `0 <= days_to_expiry < 14` → `recommended = 0` (расходуем то что есть)

**Срочность** (`_urgency_level`):

| Уровень    | Условие                                       |
|------------|-----------------------------------------------|
| `critical` | `stock < 0` (учётная ошибка — важнее velocity) |
| `low`      | `velocity ∈ {dead, slow}` (даже при stock=0)   |
| `critical` | `days_left < 1`                               |
| `high`     | `days_left < lead_time_days`                  |
| `medium`   | `days_left < lead_time_days + SAFETY_DAYS`    |
| `low`      | остальное                                     |

Порядок проверок важен: отрицательный остаток всегда critical
(потенциальная ошибка учёта), но slow-mover с stock=0 — это `low`,
а не critical.

#### Параметры поставщиков

`SUPPLIER_PARAMS` в [`routes/stocks.py`](../../routes/stocks.py) — словарь
`{lead_time_days, pack_size}` на поставщика. Значения подобраны эмпирически
по типу поставщика, требуют калибровки с менеджером.

**TODO:** вынести в редактируемые настройки (БД/файл), чтобы менеджер мог
редактировать без правки кода.

#### Особенности классификации

`classify(product_id, product_info)` в endpoint'е возвращает один из четырёх:
- `'bottle'` — `product_id ∈ fasovka_product_ids` (группа «Напитки Фасовка»)
- `'draft'` — `type == 'GOODS' AND mainUnit == 'л'` (кеги; проверка после bottle)
- `'kitchen'` — `category` ∈ `food_categories` И не пиво по ключевым словам
- `None` — пропускаем

В отличие от старого `/api/stocks/taplist`, **draft-кеги показываются все**,
а не только те что на кране (это важно для заказа — запасные кеги тоже учитываются).

#### Стыковка с ЧЗ

Только для `type='bottle'`: подмешиваем `nearest_expiry`/`days_to_expiry` через
`barcode_map` ↔ `chz_by_gtin` ↔ КПП бара (та же логика что в `/api/stocks/expiry`).

#### UI (`templates/stocks.html`)

Вкладка «Сводный заказ» — теперь **первая и активная по умолчанию**.

Колонки: Срочность, Поставщик, Позиция, Тип, Скорость, Остаток,
**В неделю**, Хватит дн., Поставка дн., Истекает, Рекомендация, Заказ.

Колонка «В неделю» = `avg_sales × 7` — продажи в неделю (раньше было
«Ср/день», поменяли на просьбу менеджера: проще оценивать «надо ли
держать в стоке» по weekly-цифре).

Подсветка строк:
- `critical` → красный фон
- `high` → жёлтый фон
- `days_to_expiry < 30` → светло-красный фон

Фильтры:
- **Тип** (фасовка / кеги / кухня)
- **Поставщик**
- **Срочность** (любая / critical / high / medium / требует заказа)
- **Скорость** (по умолчанию = `Только активные (regular+fast)` —
  slow- и dead-mover'ы скрыты, чтобы не мешали)

Кнопка «Применить рекомендации» — заполняет инпуты значением `recommended`
для всех видимых строк (учитывает фильтр).

#### Экспорт заказа

Изменено: вместо «один CSV на бар» теперь — **один CSV на поставщика**
(через все бары). Это совпадает с реальной единицей отправки заказа.
Колонки CSV: `Тип, Название, Бар, Количество, Ед.`

---

## Changelog

- **2026-04-27 (вечер)** — Добавлена velocity-классификация (`dead/slow/regular/fast`)
  по продажам в неделю. Slow- и dead-mover'ы получают `recommended=0` и `urgency=low`,
  чтобы не зашумлять «критические» (например, Эплтон Апельсин 0.5л при
  0.03/день и нулевом остатке больше не critical). UI: колонка «Ср/день»
  заменена на «В неделю», добавлена колонка «Скорость» и фильтр velocity
  (по умолчанию скрывает slow/dead).
- **2026-04-27** — Прототип «Сводный заказ»: новый endpoint
  `/api/stocks/order-board` с расчётом рекомендации `target − stock`,
  объединение фасовка+кеги+кухня в одной вкладке. Экспорт переключён
  с группировки по барам на группировку по поставщикам.
- **2026-03-27** — Создан документ stocks.md с описанием taplist, кухни, фасовки, Честного ЗНАКа

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

## Честный Знак — уроки из интеграции iiko↔ЧЗ

### 11. API `/cises/search` — каплимит 100/страница

**Problem:** Передавали `limit=1000`, получали по 100 записей. Пагинация
рвалась из-за условия `len(items) < limit`.

**Cause:** ЧЗ API режет страницу до 100 независимо от `limit`.

**Solution:** Использовать `limit=100` и пагинировать по `page`. Условие
выхода — пустой ответ или `isLastPage: true`.

Долгосрочно: для остатков `cises/search` бесполезен — для активного
ИНН возвращает 79k+ кодов исторического накопления (касса не
RETIRE'ит). Использовать **dispenser API** (`FILTERED_CIS_REPORT`).

---

### 12. CSV из ЛК ЧЗ имеет колонки `kpp`/`fiasId` — не игнорируй

**Problem:** Не могли привязать партии к конкретному бару. Делал
эвристику «брать N свежих партий под iiko-сток» — врал когда SKU
размазан по 4 барам.

**Cause:** Не заметили что в стандартной CSV-выгрузке ЛК ЧЗ есть
поля `kpp` (КПП места деятельности) и `fiasId` (адрес МОД). Каждый
CIS-код привязан к конкретному МОД юрлица — для ИНВЕСТАГРО это 4
КПП = 4 бара.

**Solution:** Парсить эти поля, агрегировать `by_kpp: [{kpp, count, batches}]`.
В endpoint `/api/stocks/expiry` фильтровать по `target_kpp` для
выбранного бара. Точные данные, не эвристика.

Маппинг КПП↔бар получен через `chz.py mods` (запрос к
`GET /api/v3/true-api/mods/list`).

---

### 13. Dispenser API возвращает ZIP, не чистый CSV

**Problem:** Парсер падал с `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x9a`.

**Cause:** Dispenser API (`/dispenser/results/{id}/file`) возвращает
**ZIP-архив с одним CSV внутри** (signature `PK\x03\x04`), не чистый
CSV. ЛК-выгрузка отдаёт чистый CSV. Поддерживаем оба варианта.

**Solution:** В `export_csv_via_dispenser` проверять первые 4 байта.
Если ZIP — `zipfile.ZipFile().read(inner_csv_name)`. Парсер CSV
дополнительно умеет UTF-8/UTF-8-sig/cp1251.

---

### 14. status=APPLIED не работает с participantInn=наш

**Problem:** Чтобы поймать импорт в пути (код нанесён, но в оборот
не введён) хотели запросить `status=APPLIED`. Получили `5: данные
не найдены`.

**Cause:** APPLIED-коды принадлежат **producer-у**, не получателю. С
`participantInn=наш` они никогда не вернутся — мы не producer.

**Solution:** Вернуть только `status=INTRODUCED`. Импорт в пути ловится
другим путём — через `GET /doc/list?receiverInn=наш&documentStatus=IN_PROGRESS`
(не реализовано пока).

---

### 15. productGroupCode 11 (alcohol) для пива бесполезен

**Problem:** Добавили `alcohol` в DEFAULT_AUTO_GROUPS чтобы поймать
сидры/медовуху. Получили 0 кодов.

**Cause:** Крепкий алкоголь маркируется **ЕГАИС-маркой**, не ЧЗ.
Сидр/медовуха/перри идут в группу 15 (beer) как «слабоалкогольные».

**Solution:** Не использовать group 11 в нашем сценарии. Полный
актуальный набор: `["beer", "nabeer", "softdrinks"]`.

---

### 16. iiko XML устаревает — не обновляется автоматически

**Problem:** В iiko OLAP были товары которых не было в XML
номенклатуре. Match rate с ЧЗ ~22%.

**Cause:** Файл `data/cache/nomenclature__products.xml` от 26.12.2025
не обновлялся 4 месяца. За это время добавилось 496 товаров.

**Solution:** Скачать свежий XML напрямую через `requests.get(...)/products`
с iiko токеном, перезаписать файл, вызвать
`get_barcode_map(force_refresh=True)`. Match rate скакнул со 82 до 202.

**TODO:** Добавить эндпоинт `POST /api/iiko/refresh-xml` или
автообновление в scheduler раз в неделю.

---

### 17. Баркод в iiko ≠ DataMatrix на бутылке

**Problem:** Товар «Кулинар Смородиновый Крамбл» был в списке «нет в
ЧЗ». Юзер утверждал что бутылка имеет DataMatrix — отсканировал её
приложением «Честный знак».

**Cause:** В iiko на карточке вбит **EAN-13 другого SKU** (`4631169328016`).
Реальный GTIN с DataMatrix — `04610424291500` (есть в нашем
chz_stock.json, 3 шт на Большом В.О).

**Solution:** Создан `chz_test/suggest_barcode_fixes.py` —
автопредложение «правильных» GTIN для несматченных позиций (по
схожести бренда). Создан `chz_test/export_bartender_list.py` —
список для бармен-сверки с пустой колонкой «Реальный GTIN с
DataMatrix» для заполнения.

После заполнения — обновляются карточки в iiko вручную (или через
API в будущем).

---

### 18. 01.12.2025 — водораздел поэкземплярного учёта

**Problem:** Не понимали почему импорт (Westmalle, La Trappe, Paulaner)
не появляется в нашей выгрузке несмотря на DataMatrix на бутылках.

**Cause:** Бутылки розлива до 01.12.2025 шли по объёмно-сортовому
учёту — UPD передавал только GTIN+количество без перечня конкретных
CIS. После 01.12.2025 — обязательный поэкземплярный учёт по
ПП РФ № 1415 от 13.09.2025.

Старые остатки не привязаны к нашему `participantInn` поштучно —
не появятся ни в каком отчёте `FILTERED_CIS_REPORT` для нашего ИНН.

**Solution:** Не пытаться их «вытащить». Это легитимные остатки
без КИ для нашего юрлица. По мере распродажи матч-рейт сам
поднимется. Поставщиков типа СПБ-Премиум (исключительно старый
импорт) — добавили в `EXCLUDE_SUPPLIERS` в bartender-списке.

---

### 19. iiko имеет 3 разных API для разных аспектов товара

**Problem:** Думал что iiko OLAP вернёт всё включая баркоды.

**Cause:** OLAP TRANSACTIONS возвращает только `name, type, category,
mainUnit, parentId` — без баркодов. Баркоды только в **XML**
номенклатуре `/products`. Live-остатки — третий endpoint
`/v2/reports/balance/stores`.

**Solution:** Использовать каждый API по назначению:
- OLAP — для имени/категории/группы (быстрее, кэш 24ч)
- XML — только для баркодов (медленный, обновляем редко)
- balance/stores — для live-остатков на каждый запрос

См. `core/iiko_barcodes.py` для парсинга XML.

---

## Changelog

- **2026-04-26** — Добавлены уроки 11-19 по интеграции iiko↔ЧЗ:
  каплимиты API, КПП-привязка, ZIP-формат dispenser, особенности
  status/productGroup, поэтапные даты обязательной маркировки
- **2026-03-27** — Создан документ lessons.md с описанием критических особенностей iiko API, паттернов и багов

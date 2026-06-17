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

### `fromisoformat` и дробные секунды iiko → ложное «бар закрыт» (open-check)

**Problem:** 2026-06-17 open-check-бот слал «ЗАКРЫТ — Варш», хотя кассовая смена
Варшавской была открыта. Локально (Python 3.14) код показывал её открытой, а
контейнер на проде — закрытой. Остальные 3 бара определялись верно.

**Cause:** `iiko` отдаёт `openDate` с РАЗНЫМ числом цифр дробной секунды. У
Варшавской смена открылась в `2026-06-17T13:42:51.45` — **2 цифры** (iiko срезал
хвостовой ноль). `datetime.fromisoformat()` в **Python 3.10** (база docker-образа
`mcr.microsoft.com/playwright/python:...-jammy`) требует РОВНО 3 или 6 цифр и
бросает `ValueError`. `_parse_iso_datetime` ловил это, возвращал `None`, и в
`check_bars_state` проверка `if not (open_dt and open_dt <= check_dt): continue`
**молча отбрасывала смену** → бар ложно «закрыт». У остальных баров дробь была
3-значной (`...031`, `...611`, `...065`) → парсилась. Локальный Python 3.11+
(у dev — 3.14) парсит 2-значную дробь спокойно — поэтому баг НЕ воспроизводился
локально и долго маскировался. В логах был след: `[WARN] _parse_iso_datetime
failed for '2026-06-17T13:42:51.45': Invalid isoformat string`.

**Solution:** В `IikoAPI._parse_iso_datetime` нормализуем дробную часть секунд до
6 цифр перед `fromisoformat` (tz-суффикс сохраняем) — парс работает на всех
версиях Python. Фикс общий: те же `openDate/closeDate` парсятся в employee-метриках.

**Урок:** dev-Python новее прод-Python — `fromisoformat`/`zoneinfo` и подобные
парсеры ведут себя по-разному. Проверять на версии Python из docker-образа, не
только локально. Не маскировать парс-ошибки тихим `None` в путях, где это
оборачивается в бизнес-вывод («закрыт») — логировать и не терять данные молча.

**Связанная защита (не корень бага):** заодно в `check_bars_state` добавлен резерв
`pointOfSaleId -> venue_key` (`_SEED_POS_MAP` + learned-кэш `open_check_pos_map.json`)
на случай НЕПОЛНОЙ выдачи `/corporation/groups`: смена с неизвестным `pos_id`
теперь логируется и берётся из резерва, а не отбрасывается молча.

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

---

## Selectel-миграция и gunicorn --workers 2 (уроки 05/2026)

### 20. Daemon-thread шедулеры под `--workers 2` — нужен atomic lock-файл

**Problem:** После миграции с Render (один worker) на Selectel (`gunicorn --workers 2`) обнаружено что в 03:00 МСК **два** POST'а к `/api/chz/refresh` срабатывали почти одновременно. Аналогично для open-check в 14:59.

**Cause:** Под `--workers 2` оба процесса импортируют `app.py` → каждый стартует свой daemon-thread шедулера → оба тикают по таймеру → оба вызывают action.

**Solution:** Atomic lock-файл `data/.<feature>_lock_YYYY-MM-DD` через `os.open(O_CREAT | O_EXCL)`. Первый воркер успевает создать файл, второй ловит `FileExistsError` и тихо выходит:

```python
# core/open_check_scheduler.py, core/chz_scheduler.py
def _try_acquire_daily_lock(today_str):
    lock_path = os.path.join(DATA_DIR, f'.<feature>_lock_{today_str}')
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f'pid={os.getpid()}'.encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
```

Старые lock-файлы (>2 дней) убираются при `start_scheduler()`.

**Применить ко всем** существующим daemon-thread шедулерам.

---

### 21. iiko OLAP timeout=300 > gunicorn --timeout 120 → worker рестарт

**Problem:** Иногда iiko OLAP запрос висел 200-300с, gunicorn убивал worker SIGKILL'ом на 120с, кэш не успевал прогреться, следующий запрос начинал заново → бесконечный цикл медленных ответов.

**Cause:** `requests.post(..., timeout=300)` в `core/olap_reports.py` рассчитан на flaky iiko-API, но gunicorn рассчитан на быстрые ответы (worker killed после `--timeout`).

**Solution:** Привести таймауты в соответствие: `timeout=100` в OLAP (fallback укладывается до SIGKILL gunicorn). Для долгих фоновых задач — отдельный thread или scheduler, не synchronous endpoint.

---

### 22. Atomic write JSON через tmp+fsync+os.replace

**Problem:** При SIGTERM/OOM worker'а во время `json.dump` файл `/kultura/taps_data.json` оставался полу-записанным → битый JSON → при рестарте пустой таплист.

**Cause:** `json.dump(data, open(path, 'w'))` не атомарен — частичный buffer уже на диске когда умирает процесс.

**Solution:**

```python
# core/taps_manager.py — паттерн для всех mutable JSON
tmp_path = path + '.tmp'
with open(tmp_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.flush()
    os.fsync(f.fileno())   # данные на диске
os.replace(tmp_path, path)  # атомарный rename (Windows и Linux)
```

`os.replace` атомарен и на Windows (Python 3.3+), и на Linux. Применить везде где есть `json.dump(..., open(...))`.

---

### 23. SQLite под несколькими worker'ами — нужен WAL

**Problem:** `shifts.db` (SQLite) под двумя gunicorn-воркерами — писатели блокировали друг друга и читателей (`database is locked`).

**Cause:** Default journal_mode SQLite = `DELETE` (rollback journal). При записи блокируется ВСЯ база — другие writers и readers ждут.

**Solution:** На каждом коннекте включить WAL + busy_timeout:

```python
# core/shifts_manager.py:36-48
conn = sqlite3.connect(path)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=5000')
conn.execute('PRAGMA synchronous=NORMAL')
```

WAL позволяет одновременные reads + один writer без блокировок. SQLite автоматически конвертирует существующую базу при первом WAL-pragma.

---

### 24. Cross-worker file lock — `portalocker`, не `threading.Lock`

**Problem:** Race condition между двумя gunicorn-воркерами при одновременном `save_plan()`: первый прочитал JSON, второй прочитал тот же JSON, оба записали → потеря изменений первого.

**Cause:** `threading.Lock` защищает только в пределах одного процесса. Под `--workers 2` — два процесса, две независимые блокировки.

**Solution:** `portalocker` через файловый дескриптор (OS-level lock):

```python
# core/plans_manager.py
import portalocker
@contextmanager
def _file_lock(path):
    with open(path + '.lock', 'w') as lockfile:
        portalocker.lock(lockfile, portalocker.LOCK_EX)
        try:
            yield
        finally:
            portalocker.unlock(lockfile)

def save_plan(...):
    with self._lock:        # in-process (быстрый)
        with self._file_lock(...):   # cross-worker (медленный, но надёжный)
            self._read_modify_write(...)
```

Применить ко всем mutable JSON: `plansdashboard.json`, `meeting_notes.json`, `kpi_targets.json`, `taps_data.json`, `open_check_subscribers.json`.

---

### 25. Хардкод-fallback токенов — утечки в публичные форки

**Problem:** В `telegram_bot.py` и `telegram_webhook.py` был fallback `TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8261982160:AAFu...')` — токен утёк в git и публичные форки.

**Cause:** Удобный fallback для локального dev → попал в коммит.

**Solution:** Никаких fallback'ов с секретами. При отсутствии env — `raise RuntimeError`. В [extensions.py](../extensions.py) ловится try/except, выставляется `TELEGRAM_BOT_ENABLED=False`, бот не стартует но приложение работает.

**Принцип:** секрет в коде = секрет в публике. Default'ы только для нечувствительных значений (порты, имена баров).

---

### 26. `cashshifts` использует другие имена точек, чем OLAP

**Problem:** В open-check ботe Кременчугская стабильно числилась закрытой даже когда касса была открыта.

**Cause:** OLAP отдаёт имя `Store.Name = "Кременчугская"`. Cashshifts отдают `pointOfSale.name = "Пивная культура"` (внутреннее имя кассового сервиса). Плюс есть 5-я точка `"Планерная"` которой нет в venue_config (она не в 4 канонических барах).

**Solution:** Отдельный `BAR_NAME_MAPPING` в [core/employee_plans.py:19-55](../core/employee_plans.py#L19-L55) — построен под имена из cashshifts, отличается от `venues_config.IIKO_NAME_TO_KEY` (тот под OLAP-имена). Не путать. Открытая «Планерная» → попадает в `other_open` (только в лог), на статус 4 баров не влияет.

---

### 27. Двойной запрос фронта × 2 воркера = блокировка всего пула

**Problem:** Дашборд «тормозил»: при открытии «Общей» за большой период сайт целиком переставал отвечать на ~17 секунд. Статический аудит кода первопричину не нашёл.

**Cause:** Фронт на старте дёргал `/api/dashboard-analytics` **дважды** (два независимых триггера: `analytics.init()` и `main.js loadInitialData()`), запросы уходили с разницей 2-4 мс и попадали на **оба** gunicorn-воркера одновременно. Оба мимо кэша (стампед), оба берут один и тот же дорогой OLAP (16-17с). На это время свободных воркеров не остаётся — любой другой запрос ждёт. Видно только на стыке «поведение фронта × топология 2 воркеров», не в одном файле.

**Solution:**
1. Убрать дублирующий триггер на фронте + in-flight guard в `loadAnalytics()` ([static/js/dashboard/modules/analytics.js](../static/js/dashboard/modules/analytics.js)) — одинаковые запросы переиспользуют один промис.
2. Backend single-flight: `cached_olap()` в [extensions.py](../extensions.py) с per-key lock и double-checked locking — параллельные одинаковые запросы внутри воркера не дёргают iiko по разу каждый.
3. Удалён отладочный `DASHBOARD_OLAP_CACHE.clear()` из `revenue_metrics` ([routes/dashboard.py](../routes/dashboard.py)), который обнулял тёплый кэш на каждом запросе.

---

### 28. Измеряй по прод-логам, а не по коду

**Problem:** Многоагентный аудит дал 36 находок, но почти все — про доступность и микрооптимизации (regex, df.copy), которые пользователь не ощущает. Реальную причину тормозов они не нашли.

**Cause:** Узкое место — сетевой roundtrip к iiko OLAP (16-17с) и эффективность кэша, а не CPU-работа в коде. Это невозможно увидеть чтением кода: нужно знать hit-rate кэша и реальные тайминги.

**Solution:** Приложение уже логирует per-step тайминги (`Комплексный запрос выполнен за X.XXs`, `[CACHE]`). Снятие с прода (`docker compose logs app | grep`) сразу показало: hit-rate кэша ~17%, каждый запрос дублируется (см. урок 27). Перед оптимизацией — снять реальные цифры с прод-логов, а не гадать по коду.

---

## Changelog

- **2026-05-29** — Добавлены уроки 27-28 после аудита стабильности/скорости: двойной запрос фронта × 2 воркера (блокировка пула), измерение по прод-логам вместо чтения кода.
- **2026-05-28** — Добавлены уроки 20-26 после миграции с Render на Selectel: atomic lock-файлы для шедулеров, gunicorn timeout vs OLAP timeout, atomic-write JSON через tmp+fsync+replace, SQLite WAL, portalocker cross-worker, удалён хардкод токена Telegram, путаница имён точек cashshifts vs OLAP.
- **2026-04-26** — Добавлены уроки 11-19 по интеграции iiko↔ЧЗ: каплимиты API, КПП-привязка, ZIP-формат dispenser, особенности status/productGroup, поэтапные даты обязательной маркировки.
- **2026-03-27** — Создан документ lessons.md с описанием критических особенностей iiko API, паттернов и багов.

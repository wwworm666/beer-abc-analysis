# Ошибки и проблемы анализа проливов (Draft Beer Analysis)

## Что это

Полный список известных ошибок, проблем, расхождений и способов их диагностики в системе анализа разливного пива.

---

## Критические ошибки

### 1. Потеря данных при парсинге объема порции

**Problem:** Записи с нераспознанным объемом порции полностью отбрасываются.

**Cause:** Функция `extract_beer_info()` не может распарсить некоторые форматы названий:
- `"Пиво"` без указания объема
- `"ФестХаус Special"` без скобок
- Нестандартные форматы: `"0.5л"`, `"500ml"` (без скобок)

**Solution:**
```python
# core/draft_analysis.py:84-88
zero_volume_count = (self.df['PortionVolume'] == 0).sum()
if zero_volume_count > 0:
    print(f"[WARNING] Isklyucheno {zero_volume_count} zapisey...")
self.df = self.df[self.df['PortionVolume'] > 0]
```

**Диагностика:**
```python
# Проверить какие записи отбрасываются
df_zero = df[df['PortionVolume'] == 0]
print(df_zero['DishName'].unique())
```

**Impact:** Потеря ~2-5% данных о продажах.

---

### 2. Дублирование пива из-за разной нормализации

**Problem:** Одно и то же пиво считается как два разных.

**Cause:** Нормализация не учитывает все вариации:
- `"ФестХаус Хеллес"` vs `"Фестхаус Хеллес"` (разный регистр)
- `"ФестХаус  Хеллес"` (два пробела) vs `"ФестХаус Хеллес"` (один пробел)
- `"ФестХаус Хеллес (0,5)"` vs `"ФестХаус Хеллес (0.5)"` (запятая vs точка)

**Solution:** Текущая нормализация (строка 82):
```python
self.df['BeerName'] = (
    self.df['BeerName']
    .str.strip()
    .str.replace(r'\s+', ' ', regex=True)
    .str.lower()
)
```

**Диагностика:**
```python
# Найти похожие названия
df_prepared = analyzer.prepare_draft_data()
similar = df_prepared[df_prepared['BeerName'].str.contains('фестхаус', case=False)]
print(similar['BeerName'].unique())
```

---

### 3. Некорректный расчет BeerSharePercent при фильтрации

**Problem:** Процент доли пива не сходится с ожидаемым.

**Cause:**
1. `BeerSharePercent` рассчитывается от ОБЩЕГО объема всех пив
2. Но пользователь может выбрать фильтр по бару
3. При этом знаменатель (total_liters) не пересчитывается для фильтра

**Formula (current):**
```python
# core/draft_analysis.py:202-206
total_liters = summary['TotalLiters'].sum()
summary['BeerSharePercent'] = (summary['TotalLiters'] / total_liters * 100)
```

**Диагностика:**
```bash
# Проверить сумму процентов - должна быть 100%
# Если нет - где-то потеря данных или дублирование
```

**Solution:** Убедиться что `total_liters` рассчитывается после фильтрации по бару.

---

### 4. Потеря данных при матчинге поставщиков

**Problem:** Не все товары имеют поставщика в выгрузке Excel.

**Cause:**
1. Маппинг `dish_to_keg_mapping.json` неполный
2. `/products` API не возвращает поставщика для всех товаров
3. Матчинг имен не учитывает все вариации названий

**Solution (export_draft_sales.py:164-195):**
```python
def get_supplier(beer_name):
    # 1. Прямой маппинг блюдо → кег
    keg_name = dish_to_keg.get(beer_name)
    # 2. С префиксом ВО
    if not keg_name:
        keg_name = dish_to_keg.get(f'ВО {beer_name}')
    # 3. Без учета регистра
    # 4. Прямой поиск по product_name
```

**Диагностика:**
```bash
# Запустить export_draft_sales.py и посмотреть статистику
# "С поставщиком: X (Y%)"
```

---

## Проблемы производительности

### 1. Медленная загрузка OLAP данных

**Problem:** Запрос данных занимает 10-30 секунд.

**Cause:**
- OLAP API iiko медленный по природе
- Нет кэширования результатов
- Большой период запроса (месяц+)

**Solution:**
```python
# core/olap_reports.py - добавить кэширование
@cache.cached(timeout=600)  # 10 минут
def get_draft_sales_report(self, date_from, date_to, bar_name=None):
    ...
```

**Workaround:** Использовать меньшие периоды (7-14 дней вместо 30+).

---

### 2. Отсутствие пагинации в таблице

**Problem:** При большом количестве позиций таблица тормозит.

**Cause:** Все данные загружаются в DOM сразу.

**Solution:**
- Добавить пагинацию (25/50/100 на страницу)
- Виртуальный скроллинг для больших таблиц
- Клиентская сортировка вместо серверной

---

## Проблемы UI/UX

### 1. Нет индикации потерянных записей

**Problem:** Пользователь не видит что 2-5% данных отброшено.

**Cause:** Warning выводится только в консоль сервера.

**Solution:**
```javascript
// draft.html - добавить в results
<div class="warning-banner">
  ⚠️ {zero_volume_count} записей отброшено (не распознан объем)
</div>
```

---

### 2. Нет tooltips с формулами

**Problem:** Пользователи не понимают как считаются метрики.

**Cause:** Нарушение принципа "Deterministic Calculations".

**Solution:** Добавить tooltips:
```html
<th title="Литры = Порции × Объем порции (0.5л)">Литры</th>
<th title="(Литры пива / Общий объем) × 100">Доля, %</th>
<th title="CV = (Стандартное отклонение / Среднее) × 100">XYZ</th>
```

---

## Диагностика расхождений

### Чеклист проверки

```
□ 1. Проверить период
  └─ Совпадает ли date_from/date_to в UI и API?
  └─ Учтен ли +1 день для OLAP (exclusive)?

□ 2. Проверить бар
  └─ Выбран конкретный бар или "Общая"?
  └─ Фильтруется ли data по бару до агрегации?

□ 3. Проверить потерю записей
  └─ Сколько записей отброшено с PortionVolume = 0?
  └─ Какие DishName не распарсились?

□ 4. Проверить дублирование
  └─ Есть ли дубли в OLAP результатах?
  └─ Не создается ли дублей при группировке?

□ 5. Проверить нормализацию
  └─ Сколько уникальных BeerName после нормализации?
  └─ Не распалось ли одно пиво на несколько?

□ 6. Проверить сумму процентов
  └─ Сходится ли сумма BeerSharePercent к 100%?
  └─ Если нет - где потеря/дублирование?
```

---

### Скрипты диагностики

#### 1. Проверка OLAP данных
```bash
python3 -c "
from core.olap_reports import OlapReports
olap = OlapReports()
olap.connect()
data = olap.get_draft_sales_report('2025-09-01', '2025-09-30', None)
print(f'Записей: {len(data[\"data\"])}')
print(f'Уникальных блюд: {len(set([d[\"DishName\"] for d in data[\"data\"]]))}')
olap.disconnect()
"
```

#### 2. Проверка парсинга
```bash
python3 -c "
import pandas as pd
from core.draft_analysis import DraftAnalysis
from core.olap_reports import OlapReports

olap = OlapReports()
olap.connect()
data = olap.get_draft_sales_report('2025-09-01', '2025-09-30', None)
olap.disconnect()

df = pd.DataFrame(data['data'])
analyzer = DraftAnalysis(df)
prepared = analyzer.prepare_draft_data()

print(f'До обработки: {len(df)} записей')
print(f'После: {len(prepared)} записей')
print(f'Отброшено: {len(df) - len(prepared)}')
"
```

#### 3. Проверка нормализации
```bash
python3 -c "
import pandas as pd
from core.draft_analysis import DraftAnalysis

df = pd.DataFrame({'DishName': [
    'ФестХаус Хеллес (0,5)',
    'Фестхаус Хеллес (0.5)',
    'ФестХаус  Хеллес (0,5)',  # два пробела
]})

analyzer = DraftAnalysis(df)
prepared = analyzer.prepare_draft_data()
print('Уникальные BeerName после нормализации:')
print(prepared['BeerName'].unique())
"
```

#### 4. Проверка суммы процентов
```bash
python3 -c "
# В браузере (Developer Tools Console)
fetch('/api/draft-analyze', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({bar: null, days: 30})
})
.then(r => r.json())
.then(data => {
  let beers = data[Object.keys(data)[0]].beers;
  let total = beers.reduce((sum, b) => sum + b.BeerSharePercent, 0);
  console.log('Сумма процентов:', total.toFixed(2) + '%');
  console.log('Должно быть: 100.00%');
});
```

---

## Известные расхождения

### 1. Разница между OLAP и кассовыми сменами

**Problem:** Выручка из OLAP не сходится с кассовыми сменами.

**Cause:** Это НЕ ошибка - разные источники:
- OLAP: детализация по блюдам/чекам
- Кассовые смены: агрегированные данные по смене

**Solution:** Не сравнивать напрямую. Для анализа проливов использовать ТОЛЬКО OLAP.

---

### 2. Разница в количестве чеков

**Problem:** `UniqOrderId.OrdersCount` не сходится с ожидаемым.

**Cause:**
- `UniqOrderId` — это ID заказа
- `UniqOrderId.OrdersCount` — счётчик уникальных заказов

**Solution:** Использовать оба поля в `aggregateFields`:
```python
"aggregateFields": [
    "UniqOrderId",              # ID
    "UniqOrderId.OrdersCount",  # Счётчик чеков
]
```

---

## Changelog

- **2026-03-31** — Создан документ draft-beer-errors.md с полным списком ошибок и проблем

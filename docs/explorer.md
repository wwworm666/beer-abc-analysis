# Конструктор отчётов (iiko Parameter Explorer)

## Что это

Универсальная страница `/explorer` для произвольной агрегации сырых OLAP-данных
из iiko. Пользователь выбирает бар, период, гранулярность времени, измерение
для группировки и (опционально) фильтр верхней категории — и сразу получает
сводную таблицу (время в строках × измерение в столбцах) + переключатель
на линейный/столбчатый график.

**Зачем:** заменить ручное «крыжение табличек под запрос» («сколько еды по
дням», «бутылка в штуках по месяцам»). Любой типовой разрез выручки делается
за 3 клика, без отдельной страницы под каждый запрос.

**MVP-ограничения (намеренно):**
- Метрика только выручка (`DishDiscountSumInt`). Параметр `metric` оставлен в
  контракте для будущего расширения на qty/cost/margin/checks.
- Бары при `venue=all` суммируются в одну колонку (без покабарного сравнения).
- Без экспорта в xlsx/csv.
- Без drilldown по клику на ячейку.

## Файлы

| Путь | Назначение |
|------|------------|
| [core/explorer.py](../core/explorer.py) | Логика: fetch raw OLAP, фильтр, бакетирование, pivot, top-N + «Прочее» |
| [routes/explorer.py](../routes/explorer.py) | Flask blueprint: `/explorer` (страница) + `GET /api/explorer/pivot` |
| [templates/explorer.html](../templates/explorer.html) | UI: тулбар + KPI + таблица/график (inline CSS+JS, как expiration.html) |
| [routes/__init__.py](../routes/__init__.py) | Регистрация `explorer_bp` |
| [templates/shared/nav.html](../templates/shared/nav.html) | Ссылка «Конструктор отчётов» в секции «Аналитика» |

## Как работает

### Поток данных

```
UI controls → fetch /api/explorer/pivot?...
                ↓
            build_pivot()
                ↓
        _fetch_raw_sales() ─── DASHBOARD_OLAP_CACHE (10 min TTL, ключ explorer_*)
                ↓                              ↓ miss
        pandas DataFrame              OlapReports.get_explorer_sales()
                                      (с Top/Second/ThirdParent — шире, чем у дашборда)
                ↓
        _apply_top_category_filter()
                ↓
        _bucket_series() (day/week/month)
                ↓
        groupby([bucket, dim]).sum() → unstack
                ↓
        reindex(full_buckets) → пустые периоды = 0
                ↓
        sort columns desc by total → top-50 + «Прочее»
                ↓
        JSON: {meta, columns, rows, column_totals, grand_total}
```

### Контракт API

**Endpoint:** `GET /api/explorer/pivot`

| Параметр | Значения | Обязательный |
|---|---|---|
| `date_from` | `YYYY-MM-DD` | да |
| `date_to` | `YYYY-MM-DD` | да |
| `venue` | `bolshoy / ligovskiy / kremenchugskaya / varshavskaya / all` | да |
| `granularity` | `day / week / month` | да |
| `group_by` | `top_category / second_parent / third_parent / dish_name` | да |
| `top_category` | `kitchen / draft / bottled / other` или пусто | нет |
| `metric` | `revenue` (по умолчанию) | нет |

**Ответ:**
```json
{
  "meta": {
    "date_from": "2026-05-01", "date_to": "2026-05-14",
    "venue": "all", "granularity": "day", "group_by": "third_parent",
    "top_category": "kitchen", "metric": "revenue",
    "row_count": 14, "col_count": 12,
    "generated_at": "2026-05-17T12:34:56"
  },
  "columns": ["Светлое", "Тёмное", "IPA", "..."],
  "rows": [
    {
      "bucket": "2026-05-01", "label": "01 май",
      "values": {"Светлое": 1240, "Тёмное": 320},
      "total": 1560
    }
  ],
  "column_totals": {"Светлое": 3720, "Тёмное": 950},
  "grand_total": 4670
}
```

### Формулы и правила

1. **Выручка одного бакета × колонки:**
   `Σ DishDiscountSumInt` по строкам, попавшим в этот бакет и в эту группу,
   после фильтра по `top_category`. Округление до целого рубля.

2. **Фильтр top_category** (применяется ДО группировки):
   - `draft` → `DishGroup.TopParent == "Напитки Розлив"`
   - `bottled` → `DishGroup.TopParent == "Напитки Фасовка"`
   - `kitchen` → `DishGroup.TopParent == "ЕДА"` (с 2026-07-16; раньше — все не-напитки)
   - `other` → `NOT IN ("Напитки Розлив", "Напитки Фасовка", "ЕДА")` —
     НАБОРЫ, Чай/Кофе, Газ и Пэт (в UI-селекте пока не показывается, доступен через API)
   - пусто → без фильтра

3. **Бакеты времени:**
   - `day` → `YYYY-MM-DD` (от `OpenDate.Typed`)
   - `week` → `YYYY-Www` ISO-неделя (та же конвенция, что в
     [core/data_processor.py](../core/data_processor.py), для согласованности
     с дашбордом и employee-страницей)
   - `month` → `YYYY-MM`

4. **Заполнение пропусков:** генерируется полный диапазон бакетов между
   `date_from` и `date_to`, отсутствующие — заполняются нулями. Это нужно
   чтобы в таблице/графике не было «дырок» в датах.

5. **Top-50 + «Прочее»:** при `col_count > 50` колонки кроме топ-50 по сумме
   объединяются в искусственную колонку `Прочее`. Это защита от случайного
   `group_by=dish_name` за год (тысячи позиций → нечитаемая таблица).

6. **iiko exclusive date_to:** API трактует `date_to` как невключительный
   конец. Чтобы включить последний день, при запросе передаётся `date_to + 1
   день`. То же делает [routes/dashboard.py:36](../routes/dashboard.py#L36).

### Кэширование

- **Сырые OLAP-данные** кэшируются в общем `DASHBOARD_OLAP_CACHE`
  ([extensions.py:56](../extensions.py#L56)) с TTL 10 мин. Ключ имеет
  префикс `explorer_` — это обязательно, потому что explorer вызывает
  другой OLAP-запрос (`get_explorer_sales` с SecondParent+ThirdParent в
  groupByRowFields), чем дашборд (`get_all_sales_report` только с
  TopParent). Один ключ для двух разных по составу полей ответов привёл
  бы к путанице.
- **Сводные таблицы НЕ кэшируются** — pandas groupby на 50 тыс. строк
  занимает <100 мс, а число параметрических комбинаций (бар × период ×
  гранулярность × измерение × категория) делает кэш бесполезным.

### UI поведение

- Дефолт: последние 4 недели до сегодня, гранулярность «неделя»,
  группировка по подкатегории, без фильтра категории, вид — таблица.
- Изменение любого параметра кроме `view` (таблица/график) → debounce 300 мс
  → fetch. Параметры синхронизированы с `?query` URL — ссылки шарятся.
- Переключение «Таблица ↔ График» только перерисовывает уже загруженные
  данные, без повторного запроса.
- График: `line` для day/week, `bar` (stacked) для month — стопки помогают
  видеть структуру по месяцам.
- Таблица: sticky-шапка, sticky-первая колонка, sticky-итоговая строка,
  sticky-итоговая колонка справа. Нулевые ячейки приглушены цветом.
- В легенде графика по умолчанию видны топ-10 серий, остальные скрыты
  (но доступны кликом по легенде Chart.js).

### Поведение «нет данных»

- Период без продаж или фильтр обрезал всё → ответ имеет `columns=[]` и
  `grand_total=0`, но `rows` всё равно содержит полный диапазон бакетов
  с нулями. UI рисует пустое состояние «Нет данных за выбранный период».

## Verification

Локальный запуск:
```
python app.py
# открыть http://localhost:5000/explorer
```

Кейсы из плана внедрения:

1. **Еда по дням по подкатегориям:** `venue=all`, период последние 14 дней,
   `granularity=day`, `group_by=third_parent`, `top_category=kitchen`. Ожидаем
   ~14 строк, колонки — подкатегории кухни. `grand_total` должен сходиться
   с кухонной выручкой на главном дашборде за тот же период.

2. **Бутылки по месяцам:** период последние 6 месяцев, `granularity=month`,
   `group_by=third_parent`, `top_category=bottled` → 6 строк ×
   подкатегории фасовки. График должен быть stacked bar.

3. **Розлив по неделям по позициям:** период 8 недель,
   `granularity=week`, `group_by=dish_name`, `top_category=draft` → ~8
   ISO-недель × top-50 позиций + «Прочее» (если позиций больше 50).

## Out of scope (фаст-фоловеры)

- Покабарное сравнение (бар как второе измерение или отдельная вкладка).
- Метрики qty, cost, margin, checks. Контракт API уже зарезервировал
  параметр `metric` под это.
- Экспорт CSV / XLSX (openpyxl уже в зависимостях, добавится одним
  endpoint'ом по образцу `/api/plans/export`).
- Переключатель транспонирования (измерение в строки, время в столбцы).
- Drilldown по клику на ячейку.
- Группировка по официанту (`WaiterName`).

## Changelog

- **2026-07-16** — фильтр `kitchen` = строго группа «ЕДА» (раньше — все не-напитки);
  добавлен API-фильтр `other` (НАБОРЫ, Чай/Кофе, Газ и Пэт), в UI-селект пока не выведен
- **2026-05-17** — первая версия. Только метрика «выручка», MVP-фильтры
  (бар × период × гранулярность × измерение × top-category). Реализованы
  страница `/explorer`, API `GET /api/explorer/pivot`, кэш OLAP-данных с
  префиксом `explorer_`. Подключение к навигации в секции «Аналитика».

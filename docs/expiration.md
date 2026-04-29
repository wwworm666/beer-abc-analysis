# Shelf-Life Cockpit — страница `/expiration`

## Что это

Отдельная страница для управления сроками годности фасовки на основе данных
ЧЗ + iiko. Превращает «список с подсветкой» (вкладка «Сроки годности» в `/stocks`)
в action layer:

1. KPI-полоса (3 метрики: ₽ под риском, критичных SKU, излишек шт.)
2. Светофор-вкладки по tier-у срочности (expired / critical / urgent / watch / fresh / unknown)
3. Карточный grid с tier-меткой, метрикой дней до истечения, остатком, расходом, ценой
4. Рекомендация: уценка по tier-ставке ИЛИ перевод в другой бар где velocity выше

Старый таб «Сроки годности» в `/stocks` остаётся как «view-only». Cockpit — отдельная страница.

## Файлы

- `routes/expiration.py` — Blueprint: `GET /expiration` (страница), `GET /api/expiration/board` (данные)
- `core/expiry_recommend.py` — `classify_tier()`, `recommend()`, константы (PRICE_ELASTICITY, tier-пороги)
- `templates/expiration.html` — UI: KPI + tier-tabs + cards-grid
- `routes/__init__.py` — регистрация `expiration_bp`
- `templates/shared/nav.html` — пункт меню «Сроки годности»

## Как работает

### Источники данных

- **iiko OLAP `/balances`** — текущие остатки по складам (товар → store_id → amount, sum)
- **iiko OLAP `/operations`** за последние 30 дней — расход (для расчёта velocity = avg_sales/день)
- **iiko nomenclature** — name, category (поставщик)
- **Цена** = `sum / amount` из balances — это **себестоимость единицы** (cost basis),
  а не цена продажи (sale price отсутствует в nomenclature). Используем cost basis
  как честную базу для оценки риска списания: сколько денег уйдёт «в минус»
  при списании партии.
- **ЧЗ-кэш** `chz_test/debug/chz_stock.json` — партии с production_date, expiration_date,
  привязанные к КПП конкретного бара

Стыковка iiko↔ЧЗ через barcode (EAN-13) ↔ gtin (GTIN-14, lpad'0').

### Tier-классификация (core/expiry_recommend.py)

| Tier | days_to_expiry | Базовая скидка |
|------|----------------|----------------|
| `expired`  | < 0     | (списание) |
| `critical` | 0..7    | 35% |
| `urgent`   | 8..14   | 20% |
| `watch`    | 15..30  | 10% |
| `fresh`    | > 30    | 0% |
| `unknown`  | None    | (нет данных ЧЗ) |

### Формулы

```
velocity        = outgoing_30d / 30                  # шт/день
expected_sales  = velocity × days_to_expiry          # успеем продать без вмешательства
surplus         = max(0, stock − expected_sales)     # излишек

# Уценка (если surplus > 0)
boosted_velocity = velocity × (1 + PRICE_ELASTICITY × discount/100)
boosted_sales    = boosted_velocity × days
expected_writeoff = max(0, stock − boosted_sales)

# Risk
risk_rub = surplus × price                           # ₽ ожидаемого списания
```

`PRICE_ELASTICITY = 1.5` — эмпирическая константа эластичности спроса по цене для пива.
Пример: −20% цены → +30% спроса.

### Перевод в другой бар

Кандидат подходит, если у него:
- тот же `product_id`,
- `velocity × days_to_expiry ≥ surplus` (успеют продать наш излишек),
- `stock_level ∈ {low, medium}` (низкий/средний остаток, есть «куда положить»).

Перебираем кандидатов в порядке raw, берём первого подходящего.

### KPI

- **Под риском, ₽** = Σ(risk_rub) по всем не-fresh не-unknown позициям
- **Критично сейчас** = count(tier ∈ {expired, critical})
- **Не успеваем продать** = Σ(surplus) по всем

### Производительность

- `get_store_balances()` вызывается **1 раз** на запрос (раньше N раз по числу баров),
  фильтрация по `store` идёт уже на уровне `_build_bar_data()`
- Запросы `/operations` по барам выполняются **параллельно** через `ThreadPoolExecutor(4)`
- Ответ **кешируется в памяти на 120 секунд** (`_BOARD_CACHE`, `threading.Lock`).
  Force-refresh — `?force=1`. Кеш у каждого gunicorn worker свой
- Метрики времени отдаются клиенту в `cache: {hit, age_sec}`, UI показывает бейдж

### Endpoint `GET /api/expiration/board?bars=…`

Параметры:
- `bars=all` — все 4 бара (default)
- `bars=bar1,bar2` — выбранные
- `force=1` — игнорировать кеш

Ответ:
```json
{
  "updated_at": "2026-04-30T...",
  "chz_updated_at": "2026-04-29T...",
  "bars": ["Большой пр. В.О", "Лиговский", ...],
  "kpi": {"risk_rub": 124300, "critical_count": 12, "surplus_units": 87.5},
  "tier_counts": {"expired": 3, "critical": 12, "urgent": 28, ...},
  "cache": {"hit": false, "age_sec": 0},
  "items": [...]
}
```

## Известные ограничения

1. **Цена** = себестоимость (cost basis) `sum/amount` из balances, не цена продажи. Это занижает «упущенную выручку», но даёт честную оценку прямого финансового убытка от списания. Если `sum=0` (товар без проводок) — `risk_rub = 0`.
2. **Перевод** — только подсказка, фактическое перемещение не интегрировано (логистика руками).
3. **Журнал действий** не ведётся (MVP). Кнопок «применить» нет — только информация.
4. **PRICE_ELASTICITY** одинаков для всех категорий. Для крафта реальное значение ниже, для масс-маркета выше.
5. **Кандидат на перевод** — берётся первый подходящий, не оптимизируем по «куда выгоднее».

## Changelog

### 2026-04-30 — Оптимизация и удаление календаря

**Что:**
- Цена позиции = себестоимость `sum/amount` из balances (раньше price=0,
  потому что nomenclature не отдаёт sale price). KPI risk_rub теперь работает.
- Удалён календарь риска (визуальный шум, дублировал KPI).
- Балансы — 1 запрос вместо N (фильтр по `store` внутри `_build_bar_data()`).
- TTL-кеш ответа /api/expiration/board на 120с (`?force=1` для обхода).
- Параллельные `/operations` через `ThreadPoolExecutor(4)`.
- UI loader с 3 стадиями + бейдж времени/кеша в meta-row.

**Замер:** холодный 8с, тёплый 0.23с (×35).

### 2026-04-30 — Создание Shelf-Life Cockpit

**Что:** Новая страница `/expiration` с tier-классификацией, рекомендациями и календарём риска.

**Почему:** Текущий таб в `/stocks` пассивный — оператор видит «истекает через 6 дней» и сам считает скидку. Cockpit добавляет action layer.

**Файлы:**
- `routes/expiration.py` (новый)
- `core/expiry_recommend.py` (новый)
- `templates/expiration.html` (новый)
- `routes/__init__.py` (регистрация)
- `templates/shared/nav.html` (пункт меню)

**Не трогали:** существующий `/stocks` таб «Сроки годности».

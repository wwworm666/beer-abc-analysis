# 🍺 Beer ABC-Analysis

> **Система аналитики продаж пива и управления пивными кранами**

Flask веб-приложение для ABC/XYZ анализа продаж пива с интеграцией iiko API.

**Для кого:** Владельцы/менеджеры баров, которым нужно:
- Понять какое пиво приносит максимальную прибыль
- Оптимизировать закупки на основе ABC/XYZ анализа
- Управлять пивными кранами в реальном времени
- Контролировать остатки и формировать заказы

---

## 🚀 Быстрый старт (5 минут)

```bash
# 1. Клонировать репозиторий
git clone https://github.com/wwworm666/beer-abc-analysis.git
cd beer-abc-analysis

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Настроить config.py (ваш логин/пароль iiko API)
# Отредактируйте IIKO_LOGIN и IIKO_PASSWORD

# 4. Запустить приложение
python app.py
```

Приложение будет доступно: `http://localhost:5000`

---

## 📚 Документация

| Документ | Описание |
|----------|----------|
| [README.md](README.md) | ← ВЫ ЗДЕСЬ: Обзор и быстрый старт |
| [docs/PROJECT_ANALYSIS_FULL.md](docs/PROJECT_ANALYSIS_FULL.md) | Технический аудит и найденные проблемы |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Деплой на Render |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Решение проблем и FAQ |
| [docs/TAPS_MANAGEMENT.md](docs/TAPS_MANAGEMENT.md) | Управление пивными кранами |
| [docs/MAPPING_SYSTEM_GUIDE.md](docs/MAPPING_SYSTEM_GUIDE.md) | Система маппинга кег |
| [docs/ru/](docs/ru/) | Документация iiko API (PDF) |

---

## 🎯 Что делает система?

### 6 основных функций:

| № | Функция | Зачем нужна |
|---|---------|-------------|
| 1 | **ABC/XYZ Фасовка** | Какое бутылочное пиво самое прибыльное? |
| 2 | **ABC/XYZ Разливное** | Сколько кег заказывать? Какие сорта приносят прибыль? |
| 3 | **Анализ по категориям** | Какие стили пива продаются лучше? (IPA, Лагер, Стаут) |
| 4 | **Анализ официантов** | Кто продаёт больше всего? Производительность персонала |
| 5 | **Управление кранами** | Какой сорт на каком кране? История замен кег |
| 6 | **Остатки и заказы** | Что заканчивается? Что срочно заказать? |

---

## 📊 Как устроена система? (Схема потока данных)

```
┌─────────────────┐
│   iiko API      │ ← Внешний источник данных (продажи, остатки, номенклатура)
└────────┬────────┘
         │ XML/JSON
         ↓
┌─────────────────┐
│ OlapReports     │ ← Получение данных из iiko
│ (core/)         │   • get_nomenclature() → Список товаров
└────────┬────────┘   • get_beer_sales_report() → Продажи фасовки
         │            • get_draft_sales_report() → Продажи разливного
         ↓            • get_store_balances() → Остатки на складах
┌─────────────────┐
│ DataProcessor   │ ← Преобразование в pandas DataFrame
│ (core/)         │   • prepare_dataframe()
└────────┬────────┘   • aggregate_by_beer_and_bar()
         │
         ├────────────────────────────────────────┐
         │                                        │
         ↓                                        ↓
┌─────────────────┐                      ┌─────────────────┐
│ ABCAnalysis     │                      │ XYZAnalysis     │
│ (core/)         │                      │ (core/)         │
│                 │                      │                 │
│ 3 буквы:        │                      │ Стабильность:   │
│ • Выручка (A/B/C)│                     │ • X (CV<10%)    │
│ • Наценка % (A/B/C)│                   │ • Y (10-25%)    │
│ • Маржа ₽ (A/B/C)│                     │ • Z (CV>25%)    │
└────────┬────────┘                      └────────┬────────┘
         │                                        │
         └────────────────┬───────────────────────┘
                          ↓
                 ┌─────────────────┐
                 │   Flask App     │ ← Веб-интерфейс + API
                 │   (app.py)      │   • 26 API endpoints
                 └────────┬────────┘   • 7 HTML страниц
                          │            • Валидация + Кеширование
                          ↓
                 ┌─────────────────┐
                 │   Browser       │ ← Пользователь (менеджер/бармен)
                 └─────────────────┘
```

---

## 🗂️ Структура проекта (иерархия с описаниями)

### 📁 Корень проекта

```
beer-abc-analysis/
│
├── app.py                  # 🔥 ГЛАВНЫЙ ФАЙЛ (1720 строк)
│   │                       Что внутри:
│   ├── 📍 26 API endpoints (анализ, краны, остатки)
│   ├── 🎨 7 page routes (главная, разливное, официанты, краны, остатки)
│   ├── ⚠️ Error handlers (404, 500)
│   ├── 💾 Кеширование номенклатуры (30 минут)
│   └── ✅ Валидация входных данных
│
├── config.py               # ⚙️ КОНФИГУРАЦИЯ
│   │                       Что настраивается:
│   ├── IIKO_LOGIN, IIKO_PASSWORD (ваши данные iiko API)
│   ├── BARS = ["Большой пр. В.О", "Лиговский", ...]
│   ├── STORE_ID_MAP (маппинг баров на ID складов)
│   ├── FASOVKA_GROUP_ID (ID группы "Напитки Фасовка")
│   ├── NOMENCLATURE_CACHE_MINUTES = 30
│   └── IIKO_API_TIMEOUT, IIKO_OLAP_TIMEOUT
│
├── requirements.txt        # 📦 Зависимости Python
│   ├── Flask==3.0.0
│   ├── pandas==2.2.3
│   ├── requests==2.31.0
│   └── gunicorn==21.2.0 (для Render)
│
└── README.md               # 📖 ← ВЫ ЗДЕСЬ
```

---

### 📁 core/ - Бизнес-логика (9 модулей)

> **Важно:** Каждый модуль делает одну конкретную вещь. Не смешивайте функционал!

```
core/
│
├── iiko_api.py            # 🔐 Аутентификация в iiko API
│   │                      Что делает:
│   ├── authenticate()     → Получить токен (SHA-1 hash пароля)
│   ├── logout()           → Освободить токен (важно!)
│   └── get_sha1_hash()    → Хеширование пароля
│
├── olap_reports.py        # 📊 Получение данных из iiko
│   │                      Что делает:
│   ├── get_nomenclature() → Список всех товаров (XML → dict)
│   ├── get_store_balances(timestamp) → Остатки на складах (JSON)
│   ├── get_beer_sales_report(date_from, date_to, bar) → Продажи фасовки (OLAP)
│   ├── get_draft_sales_report(...) → Продажи разливного (OLAP)
│   ├── get_draft_sales_by_waiter_report(...) → С официантами (OLAP)
│   └── _build_olap_request() → Формирует JSON для OLAP API
│
├── data_processor.py      # 🔄 Подготовка данных для анализа
│   │                      Что делает:
│   ├── prepare_dataframe() → OLAP JSON → pandas DataFrame
│   ├── aggregate_by_beer_and_bar() → Группирует по пиву и бару
│   ├── get_weekly_sales() → Продажи по неделям (для XYZ)
│   └── get_bar_statistics() → Статистика по барам
│
├── abc_analysis.py        # 🅰️ ABC анализ (3 буквы)
│   │                      Как работает:
│   │                      1. Сортирует по метрике (выручка/наценка/маржа)
│   │                      2. Вычисляет накопленный %
│   │                      3. Присваивает A (80%), B (15%), C (5%)
│   │
│   └── perform_abc_analysis_by_bar(bar_name)
│       ├── 1-я буква: по TotalRevenue
│       ├── 2-я буква: по AvgMarkupPercent
│       └── 3-я буква: по TotalMargin
│       Результат: ABC_Combined = "AAA", "ABC", "CCC"...
│
├── xyz_analysis.py        # 📈 XYZ анализ (стабильность)
│   │                      Как работает:
│   │                      1. Группирует продажи по неделям
│   │                      2. Вычисляет CV = (σ / μ) × 100
│   │                      3. Присваивает X (CV<10%), Y (10-25%), Z (>25%)
│   │
│   ├── perform_xyz_analysis_by_bar(bar_name)
│   ├── calculate_coefficient_of_variation(weekly_sales)
│   ├── categorize_xyz(cv)
│   └── get_weekly_chart_data(beer_name)
│
├── category_analysis.py   # 🏷️ Анализ по категориям (стилям)
│   │                      Что делает:
│   ├── get_categories(bar) → Список стилей ("IPA", "Лагер")
│   ├── analyze_category(category, bar) → ABC для стиля
│   ├── get_category_summary() → Сводка по всем стилям
│   └── add_xyz_to_category_analysis() → ABCXYZ для категории
│
├── draft_analysis.py      # 🍺 Анализ разливного пива
│   │                      Особенность: Парсит объёмы из названий!
│   │
│   ├── extract_beer_info("ФестХаус (0,5)")
│   │   → ("ФестХаус Хеллес", 0.5л)
│   │
│   ├── prepare_draft_data()
│   │   → Нормализация: "ФестХаус  Хеллес" → "фестхаус хеллес"
│   │   → Расчёт литров: Количество × Объём порции
│   │
│   ├── get_beer_summary()
│   │   → Для каждого пива:
│   │      • TotalLiters (объём в литрах)
│   │      • Kegs30L, Kegs50L (сколько кег)
│   │      • WeeksActive (недели с продажами)
│   │      • ABC_Combined, XYZ_Category
│   │
│   └── calculate_xyz_for_summary()
│
├── waiter_analysis.py     # 👨‍🍳 Анализ по официантам
│   │                      Что делает:
│   ├── prepare_waiter_data()
│   │   → Фильтрует системных пользователей
│   │   → Парсит объёмы из названий (как в draft_analysis)
│   │
│   ├── get_waiter_summary()
│   │   → Для каждого официанта:
│   │      • TotalLiters (сколько пролил)
│   │      • TotalRevenue, TotalMargin
│   │      • UniqueBeers (количество уникальных сортов)
│   │      • Kegs30L (~сколько кег)
│   │
│   ├── get_waiter_beer_details(waiter_name)
│   │   → Что конкретно пролил этот официант
│   │
│   └── get_top_waiters(top_n=10)
│
├── taps_manager.py        # 🚰 Управление кранами
│   │                      Что делает:
│   │                      Отслеживает состояние 60 кранов в 4 барах
│   │
│   ├── BARS_CONFIG = {
│   │     'bar1': 24 крана,
│   │     'bar2': 12 кранов,
│   │     'bar3': 12 кранов,
│   │     'bar4': 12 кранов
│   │   }
│   │
│   ├── start_tap(bar_id, tap_number, beer_name, keg_id)
│   │   → Подключить кегу к крану
│   │
│   ├── stop_tap(bar_id, tap_number)
│   │   → Остановить кран (кега закончилась)
│   │
│   ├── replace_tap(bar_id, tap_number, beer_name, keg_id)
│   │   → Заменить кегу (смена сорта)
│   │
│   ├── get_bar_taps(bar_id)
│   │   → Состояние всех кранов бара
│   │
│   ├── get_tap_history(bar_id, tap_number)
│   │   → История действий крана
│   │
│   └── _save_data()
│       → Сохраняет в data/taps_data.json (или /kultura/)
│
├── validators.py          # ✅ Валидация входных данных (NEW!)
│   │                      Зачем нужно:
│   │                      Защита от невалидных данных (days=-1000)
│   │
│   ├── validate_days(days, min=1, max=365)
│   ├── validate_bar(bar_name, allow_empty=True)
│   ├── validate_tap_number(tap, max=24)
│   ├── validate_required_fields(data, fields)
│   ├── get_moscow_time() → datetime в Moscow TZ
│   └── MOSCOW_TZ (ZoneInfo)
│
└── abc_helpers.py         # 🛠️ Вспомогательные функции ABC (NEW!)
    │                      Зачем нужно:
    │                      Убрать дублирование кода ABC анализа
    │
    ├── calculate_abc_category(series)
    │   → Рассчитать ABC для pandas Series
    │
    ├── apply_abc_analysis(df)
    │   → Применить ABC к DataFrame (добавляет 4 колонки)
    │
    ├── get_abc_stats(df)
    │   → Статистика по ABC категориям
    │
    └── calculate_revenue_percent(df)
```

---

### 📁 templates/ - HTML интерфейс (7 страниц)

> **Важно:** Каждый template содержит встроенные CSS и JavaScript!

```
templates/
│
├── index.html             # 🏠 Главная: ABC/XYZ фасованного пива
│   │                      Функции:
│   ├── Выбор бара (или "Общая" для всех)
│   ├── Выбор периода (7, 30, 90 дней)
│   ├── Таблица с ABC-XYZ категориями
│   ├── Топ-10 лучших / Аутсайдеры
│   ├── Графики продаж по неделям
│   └── Экспорт в Excel (xlsx)
│
├── draft.html             # 🍺 Анализ разливного пива
│   │                      Функции:
│   ├── Объёмы в литрах
│   ├── Расчёт кег 30л/50л
│   ├── ABC-XYZ для разливного
│   ├── Сортировка по объёму (↓)
│   └── Доля каждого сорта в %
│
├── waiters.html           # 👨‍🍳 Анализ официантов
│   │                      Функции:
│   ├── Топ-10 официантов по литрам
│   ├── Детализация по сортам (клик на официанта)
│   ├── Статистика: выручка, маржа, уникальные сорта
│   └── Сравнение производительности
│
├── stocks.html            # 📦 Остатки и заказы
│   │                      Функции:
│   ├── 3 вкладки: Разливное / Фасовка / Кухня
│   ├── Цветовая индикация: 🔴 LOW, 🟡 MEDIUM, 🟢 HIGH
│   ├── Средние продажи за день
│   ├── Уровень запаса (в днях)
│   └── Формирование заказа
│
├── taps_main.html         # 🏪 Выбор бара для управления кранами
│   │                      Функции:
│   ├── Список всех баров
│   ├── Статистика: активных кранов / всего
│   └── Переход на /taps/<bar_id>
│
├── taps_bar.html          # 🚰 Управление кранами конкретного бара
│   │                      Функции:
│   ├── Визуализация всех кранов (1-24)
│   ├── Цвет крана: 🟢 active, ⚪ empty
│   ├── Кнопки: "Подключить кегу", "Сменить сорт", "Остановить"
│   ├── История действий крана
│   └── Мобильная адаптация (@media queries)
│
└── taps.html              # 📋 Общий таплист всех баров
    │                      Функции:
    ├── Таблица всех активных кранов
    ├── Фильтр по бару
    └── Экспорт в CSV
```

---

### 📁 data/ - Хранилище данных

```
data/
│
├── taps_data.json         # 🚰 Состояние кранов (JSON storage)
│   │                      Структура:
│   │                      {
│   │                        "bar1": {
│   │                          "name": "Бар 1",
│   │                          "taps": [
│   │                            {
│   │                              "tap_number": 1,
│   │                              "status": "active",
│   │                              "current_beer": "ФестХаус Хеллес",
│   │                              "current_keg_id": "KEG-12345",
│   │                              "started_at": "2024-01-15T10:30:00",
│   │                              "history": [...]
│   │                            }
│   │                          ]
│   │                        }
│   │                      }
│   │
│   │                      ⚠️ НА RENDER: хранится в /kultura/taps_data.json
│
├── all_products.json      # 💾 Кешированная номенклатура iiko (опционально)
└── keg_mapping.json       # 🔗 Маппинг кег → блюда (опционально)
```

---

## 🔧 Как работает каждый блок?

### 🅰️ Блок 1: ABC/XYZ Анализ Фасовки

**Вопрос:** Какое бутылочное пиво самое прибыльное?

**Шаги:**

1. **Получение данных** → `olap_reports.get_beer_sales_report()`
   ```
   iiko API → OLAP отчёт за 30 дней → JSON с продажами
   ```

2. **Обработка** → `data_processor.aggregate_by_beer_and_bar()`
   ```
   JSON → pandas DataFrame → Группировка по пиву и бару
   Результат: Bar, Beer, TotalQty, TotalRevenue, TotalCost, AvgMarkupPercent, TotalMargin
   ```

3. **ABC Анализ** → `abc_analysis.perform_abc_analysis_by_bar()`
   ```
   Для каждого пива:
   - 1-я буква (A/B/C): по TotalRevenue
     Сортируем по выручке → Считаем накопленный % → A (0-80%), B (80-95%), C (95-100%)
   - 2-я буква (A/B/C): по AvgMarkupPercent
   - 3-я буква (A/B/C): по TotalMargin

   Результат: ABC_Combined = "AAA" (идеально) или "CCC" (плохо)
   ```

4. **XYZ Анализ** → `xyz_analysis.perform_xyz_analysis_by_bar()`
   ```
   Для каждого пива:
   - Группируем продажи по неделям
   - Вычисляем коэффициент вариации: CV = (σ / μ) × 100
   - Присваиваем категорию:
     X: CV < 10% (стабильный)
     Y: 10% ≤ CV < 25% (средний)
     Z: CV ≥ 25% (нестабильный)
   ```

5. **Объединение** → `app.py`
   ```
   ABC_Combined + XYZ_Category = "AAA-X" (лучшее пиво!)
   ```

**Пример результата:**

| Пиво | ABC_Combined | XYZ | Результат | Действие |
|------|--------------|-----|-----------|----------|
| Балтика 7 0,5 | AAA | X | AAA-X | Всегда в наличии! |
| Гараж IPA | ABC | Y | ABC-Y | Регулярный мониторинг |
| Крафт редкий | CCC | Z | CCC-Z | Вывести из ассортимента |

---

### 🍺 Блок 2: Анализ Разливного Пива

**Вопрос:** Сколько кег заказывать? Какие сорта приносят прибыль?

**Особенность:** Разливное продаётся порциями (0.3л, 0.5л, 1л) → нужно пересчитать в литры!

**Шаги:**

1. **Получение данных** → `olap_reports.get_draft_sales_report()`
   ```
   iiko API → OLAP "Напитки Розлив"
   ```

2. **Парсинг объёмов** → `draft_analysis.extract_beer_info()`
   ```
   "ФестХаус Хеллес (0,5)" → название: "ФестХаус Хеллес", объём: 0.5л
   "Блек Шип (0,25)" → название: "Блек Шип", объём: 0.25л
   "ХБ Октоберфест (1,0) с собой" → название: "ХБ Октоберфест", объём: 1.0л
   ```

3. **Нормализация** (критично!)
   ```
   "ФестХаус  Хеллес" (2 пробела) → "фестхаус хеллес"
   "FESTHAUS Helles" → "festhaus helles"

   Зачем? Чтобы объединить одинаковые сорта!
   ```

4. **Расчёт объёмов** → `draft_analysis.prepare_draft_data()`
   ```
   Литры = Количество порций × Объём порции
   Пример: 120 порций × 0.5л = 60 литров

   Kegs30L = Литры ÷ 30л
   Kegs50L = Литры ÷ 50л
   ```

5. **ABC/XYZ** → применяется как к фасовке

**Пример результата:**

| Пиво | Литры | Кеги 30л | ABC-XYZ | Действие |
|------|-------|----------|---------|----------|
| ФестХаус Хеллес | 450л | ~15 кег | AAA-X | Заказать 20 кег! |
| Блек Шип | 180л | ~6 кег | ABC-Y | Заказать 8 кег |
| Крафт редкий | 30л | ~1 кега | CCC-Z | Не заказывать |

---

### 👨‍🍳 Блок 3: Анализ Официантов

**Вопрос:** Кто продаёт больше всего? Производительность персонала?

**Шаги:**

1. **Получение данных с WaiterName** → `olap_reports.get_draft_sales_by_waiter_report()`

2. **Фильтрация** → `waiter_analysis.prepare_waiter_data()`
   ```
   Исключаем системных пользователей:
   - "Пользователь для централизованной доставки"
   - "Системный пользователь"
   - "Неизвестно"
   ```

3. **Агрегация** → `waiter_analysis.get_waiter_summary()`
   ```
   Для каждого официанта:
   - TotalLiters (сколько пролил)
   - TotalRevenue, TotalMargin
   - UniqueBeers (сколько разных сортов)
   - Kegs30L (~сколько кег)
   ```

**Пример результата:**

| Официант | Литры | Кеги 30л | Выручка | Маржа |
|----------|-------|----------|---------|-------|
| Иванов И. | 320л | ~10 кег | 96,000₽ | 28,800₽ |
| Петров П. | 280л | ~9 кег | 84,000₽ | 25,200₽ |

---

### 🚰 Блок 4: Управление Кранами

**Вопрос:** Какой сорт на каком кране? Когда меняли кегу?

**Данные хранятся в:** `data/taps_data.json` (или `/kultura/` на Render)

**Действия:**

| Действие | Метод | Что делает |
|----------|-------|------------|
| Подключить кегу | `start_tap()` | Кран становится ACTIVE, записывается history |
| Остановить | `stop_tap()` | Кран становится EMPTY |
| Сменить сорт | `replace_tap()` | Старый сорт → history, новый → ACTIVE |

**Пример истории:**

```json
{
  "timestamp": "2024-01-15T14:20:00",
  "action": "start",
  "beer_name": "ФестХаус Хеллес",
  "keg_id": "KEG-12345"
}
```

---

### 📦 Блок 5: Остатки и Заказы

**Вопрос:** Что заканчивается? Что срочно заказать?

**Логика:**

1. **Получение остатков** → `olap_reports.get_store_balances()`
2. **Расчёт средних продаж** → `(Продажи за период) ÷ Дней`
3. **Определение уровня:**
   ```
   Остатки < 3 дней → 🔴 LOW (заказать!)
   Остатки < 7 дней → 🟡 MEDIUM (скоро заказать)
   Иначе → 🟢 HIGH (норма)
   ```

**Пример:**

| Товар | Остаток | Средние продажи | Уровень | Действие |
|-------|---------|-----------------|---------|----------|
| Балтика 7 0,5 | 48 шт | 12 шт/день | 🟡 MEDIUM | 4 дня запаса |
| Сырные палочки | 15 шт | 8 шт/день | 🔴 LOW | Срочно заказать! |

---

## 🔌 API Endpoints (26 штук)

### Анализ (5 endpoints)

```
POST /api/analyze
    Параметры: bar (string), days (int, 1-365)
    Возвращает: ABC-XYZ для каждого пива

POST /api/categories
    Возвращает: ABC по стилям пива

POST /api/draft-analyze
    Возвращает: Литры, кеги, ABC-XYZ для разливного

POST /api/waiter-analyze
    Возвращает: Топ официантов с детализацией

GET /api/weekly-chart/<bar>/<beer>
    Возвращает: Данные для графика продаж
```

### Краны (8 endpoints)

```
GET /api/taps/bars
POST /api/taps/<bar_id>/start
POST /api/taps/<bar_id>/stop
POST /api/taps/<bar_id>/replace
GET /api/taps/<bar_id>/<tap_number>/history
GET /api/taps/export-taplist
...
```

### Остатки (5 endpoints)

```
GET /api/stocks/taplist?bar=<name>
GET /api/stocks/bottles?bar=<name>
GET /api/stocks/kitchen?bar=<name>
...
```

**Полный список:** см. [PROJECT_ANALYSIS_FULL.md](docs/PROJECT_ANALYSIS_FULL.md) (26 API endpoints)

---

## ⚙️ Конфигурация (`config.py`)

```python
# iiko API credentials
IIKO_LOGIN = "your_login"         # ← ИЗМЕНИТЬ!
IIKO_PASSWORD = "your_password"   # ← ИЗМЕНИТЬ!

# Список баров
BARS = [
    "Большой пр. В.О",
    "Лиговский",
    "Кременчугская",
    "Варшавская"
]

# ID группы "Напитки Фасовка" в iiko
FASOVKA_GROUP_ID = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'

# Кеширование номенклатуры (минуты)
NOMENCLATURE_CACHE_MINUTES = 30

# Таймауты (секунды)
IIKO_API_TIMEOUT = 30
IIKO_OLAP_TIMEOUT = 60
```

---

## 🚀 Deployment на Render

1. Создать Web Service на [Render](https://render.com)
2. Подключить GitHub репозиторий
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app`
5. Создать Persist Disk `/kultura` для taps_data.json
6. Добавить Environment Variables (IIKO_LOGIN, IIKO_PASSWORD)

**Подробнее:** [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)

---

## 🐛 Troubleshooting

### "Не удалось подключиться к iiko API"

1. Проверьте `config.py`: правильные ли логин/пароль?
2. Проверьте сеть: доступен ли `first-federation.iiko.it:443`?
3. Проверьте лицензию: возможно занято 10 слотов (вызовите logout)

### "Нет данных за выбранный период"

1. Проверьте период: возможно в это время не было продаж
2. Проверьте название бара: оно должно ТОЧНО совпадать с iiko
3. Проверьте группы: возможно изменились ID групп в iiko

---

## 📝 Changelog

### v2.0 (2025-11-15) - Исправления и улучшения

- ✅ Добавлена валидация входных данных (`core/validators.py`)
- ✅ Вынесены hardcoded ID в `config.py`
- ✅ Реализовано кеширование номенклатуры (30 мин)
- ✅ Добавлены глобальные error handlers (404, 500)
- ✅ Moscow TZ используется везде
- ✅ Timeout добавлен ко всем HTTP запросам
- ✅ Logging вместо print
- ✅ Рефакторинг: убрано дублирование ABC кода (`core/abc_helpers.py`)

### v1.0 (начальная версия)

- Базовый функционал ABC/XYZ анализа
- Управление пивными кранами
- Интеграция с iiko API

---

## 📞 Поддержка

**Issue на GitHub:** [github.com/wwworm666/beer-abc-analysis/issues](https://github.com/wwworm666/beer-abc-analysis/issues)

**Полная документация:**
- [docs/PROJECT_ANALYSIS_FULL.md](docs/PROJECT_ANALYSIS_FULL.md) - Технический аудит проекта
- [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) - Деплой на Render
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - Решение проблем
- [docs/TAPS_MANAGEMENT.md](docs/TAPS_MANAGEMENT.md) - Управление кранами
- [docs/](docs/) - Вся документация

---

**Сделано с ❤️ для пивных баров**

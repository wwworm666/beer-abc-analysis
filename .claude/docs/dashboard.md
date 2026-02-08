# Дашборд План/Факт

## Что это

Главный экран для управленца. Выбираешь бар, выбираешь период — видишь план vs факт по 15 метрикам. Красное — плохо, зелёное — хорошо. Раньше выглядел как "нейрослоп" с эмодзи и холодными синими кнопками, теперь — минималистичный финтех-инструмент в стиле Stripe/Linear 2026.

**Главное отличие от обычных дашбордов:** планы интегрированы прямо в карточки метрик. Не нужно переключаться между вкладками "факт" и "план" — всё видно сразу: прогресс-бар показывает 68% выполнения, рядом точная цифра ±12%.

## Файлы

### Backend (Python)
```
dashboardNovaev/
├── dashboard_analysis.py     ← Расчёт 15 метрик из OLAP
├── plans_manager.py          ← CRUD для планов (JSON)
└── backend/
    ├── venues_config.py      ← Маппинг ключей баров → iiko
    ├── venues_manager.py     ← Агрегация по барам
    ├── comparison_calculator.py  ← Сравнение периодов
    └── trends_analyzer.py    ← Анализ трендов

app.py → Routes:
  /api/dashboard-analytics      ← факт
  /api/plans/calculate/...      ← план
  /api/export/pdf               ← PDF отчёт
```

### Frontend (ES6 модули)
```
static/js/dashboard/
├── main.js                   ← Главный файл, инициализация
├── core/
│   ├── state.js              ← Centralized state (venue, period)
│   └── config.js             ← Конфиг 15 метрик
└── modules/
    ├── analytics.js          ← Загрузка и отображение метрик
    ├── venue_selector.js     ← Селектор бара
    ├── datepicker.js         ← Flatpickr календарь
    ├── export.js             ← PDF экспорт
    ├── comparison.js         ← Сравнение периодов
    └── theme.js              ← Светлая/тёмная тема

templates/dashboard/
├── dashboard.html            ← Entry point
├── base.html                 ← Layout: controls + tabs
├── analytics_tab.html        ← Вкладка "Аналитика"
└── components/
    ├── metric_card.html      ← Шаблон карточки метрики
    └── venue_selector.html   ← (deprecated, теперь inline)

static/dashboard/styles/
├── variables.css             ← Цветовая палитра, spacing
├── base.css                  ← Кнопки, формы, typography
├── cards.css                 ← Карточки метрик
├── tabs.css                  ← Табы с pill-shape
└── fonts.css                 ← IBM Plex Mono @font-face
```

### Data
```
data/
└── plansdashboard.json       ← Хранилище планов
```

## Как работает

### Архитектура: State-Driven UI

Вся логика завязана на **централизованный state** (`state.js`). Это простой pub/sub паттерн:

```javascript
// Устанавливаем venue
state.setVenue('kremenchugskaya');
  ↓
// state.js уведомляет всех подписчиков
analytics.loadAnalytics();      // загружает метрики
venueSelector.update();         // обновляет UI селектора
  ↓
// Устанавливаем период
state.setPeriod({ start: '2026-01-26', end: '2026-02-01' });
  ↓
analytics.loadAnalytics();      // перезагружает с новыми датами
```

**Почему так удобно:** не нужно вручную синхронизировать селекторы, вкладки и графики. Изменил `state.currentVenue` → все модули автоматически обновились.

### Поток данных: от клика до карточки

```
1. User: кликает на бар "Кременчугская"
   ↓
2. venue_selector.js → state.setVenue('kremenchugskaya')
   ↓
3. analytics.js получает событие 'venueChanged'
   ↓
4. Параллельные fetch запросы:
   - /api/dashboard-analytics        ← факт
   - /api/plans/calculate/...        ← план
   ↓
5. Backend:
   - VenuesManager: 'kremenchugskaya' → 'Кременчугская' (iiko name)
   - OlapReports.get_all_sales_report() → 3 параллельных запроса к iiko
   - DashboardMetrics.calculate_metrics() → 15 метрик
   ↓
6. Frontend: displayComparison()
   - Для каждой метрики создаёт карточку
   - Вычисляет % выполнения (actual / plan * 100)
   - Рисует прогресс-бар (accent color #D97757)
   - Красит diff: зелёный (↗) или красный (↘)
   ↓
7. User видит:
   "Выручка 692K (план 252K) → 274.6% ✅"
```

### 15 Метрик дашборда

```javascript
// config.js → METRICS
[
  { id: 'revenue', name: 'Выручка', unit: 'руб', format: 'money' },
  { id: 'checks', name: 'Количество чеков', unit: 'шт' },
  { id: 'avg_check', name: 'Средний чек', unit: 'руб', format: 'money' },

  { id: 'draft_share', name: 'Доля разливного', unit: '%' },
  { id: 'bottles_share', name: 'Доля фасовки', unit: '%' },
  { id: 'kitchen_share', name: 'Доля кухни', unit: '%' },

  { id: 'draft_revenue', name: 'Выручка разлив', unit: 'руб', format: 'money' },
  { id: 'bottles_revenue', name: 'Выручка фасовка', unit: 'руб', format: 'money' },
  { id: 'kitchen_revenue', name: 'Выручка кухня', unit: 'руб', format: 'money' },

  { id: 'avg_markup', name: 'Средняя наценка', unit: '%' },
  { id: 'total_margin', name: 'Прибыль (маржа)', unit: 'руб', format: 'money' },
  { id: 'margin_percent', name: 'Процент маржи', unit: '%' },

  { id: 'total_cost', name: 'Себестоимость', unit: 'руб', format: 'money' },
  { id: 'tap_activity', name: 'Активность кранов', unit: '%' },
  { id: 'avg_positions_per_check', name: 'Позиций в чеке', unit: 'шт' }
]
```

**Расчёт в Python:**

```python
# dashboard_analysis.py → DashboardMetrics.calculate_metrics()

# Общая выручка = сумма всех категорий
total_revenue = draft_revenue + bottles_revenue + kitchen_revenue

# Доли (в процентах)
draft_share = (draft_revenue / total_revenue) * 100 if total_revenue else 0

# Средняя наценка (взвешенная по себестоимости)
avg_markup = ((total_revenue - total_cost) / total_cost) * 100 if total_cost else 0

# Маржа
total_margin = total_revenue - total_cost
margin_percent = (total_margin / total_revenue) * 100 if total_revenue else 0
```

### Планы: JSON-файл + API

Планы хранятся в `data/plansdashboard.json`:

```json
{
  "plans": {
    "2026-01-26_2026-02-01": {
      "revenue": 252077,
      "checks": 143,
      "averageCheck": 1763,
      "draftShare": 45,
      "packagedShare": 35,
      "kitchenShare": 20,
      ...
    }
  }
}
```

**Ключ периода формируется как `{date_from}_{date_to}`**. Плюс такого формата:
- Легко парсить (split по `_`)
- Легко искать (indexOf)
- Легко дебажить (видно даты в логах)

**Важная деталь:** PlansManager делает **backup** перед каждым изменением (`plansdashboard_backup_TIMESTAMP.json`). Если испортили планы — откатываем за 1 минуту.

**API для работы с планами:**

```python
# app.py

# Получить план + факт для периода
GET /api/plans/calculate/kremenchugskaya/2026-01-26/2026-02-01
→ { actual: {...}, plan: {...}, completion: 68.5 }

# Сохранить новый план
POST /api/plans/save
{ venue, date_from, date_to, metrics: {...} }

# Импорт планов из XLSX
POST /api/plans/import/kremenchugskaya
{ планы на 2025-2026 в формате Excel }
```

### Финтех дизайн 2026

**Было:** Холодный синий (#0066cc), эмодзи 💰🍺📊, квадратные углы, системный шрифт.
**Стало:** Терракотовый акцент (#D97757), IBM Plex Mono, pill-shape кнопки (border-radius: 999px), тёплый кремовый фон (#FAF9F7).

#### Цветовая палитра

```css
/* variables.css */

/* Светлая тема */
--bg-primary: #FAF9F7;           /* Тёплый кремовый фон */
--bg-secondary: #FFFFFF;         /* Карточки */
--accent: #D97757;               /* Терракотовый акцент */
--text-primary: #1a1a1a;

/* Тёмная тема */
[data-theme="dark"] {
  --bg-primary: #1C1917;         /* Тёплый коричневый */
  --bg-secondary: #292524;
  --accent: #E89779;             /* Светлее для контраста */
  --text-primary: #FAF9F7;
}
```

**Почему тёплые тона?** Холодный синий ассоциируется с банками и корпорациями. Терракотовый — тёплый, дружелюбный, современный (как у Stripe, Linear, Mercury).

#### Компоненты

**Кнопки (pill-shape):**

```css
.btn {
  padding: 14px 28px;
  border-radius: 999px;          /* Полностью круглые края */
  background: var(--accent);
  transition: all 150ms;
}

.btn:hover {
  transform: translateY(-1px);   /* Микро-подъём */
  box-shadow: var(--shadow-md);
}
```

**Карточки метрик (большие радиусы):**

```css
.metric-card {
  background: var(--bg-secondary);
  border-radius: 24px;           /* Мягкие углы */
  padding: 32px;
  transition: all 200ms;
}

.metric-card:hover {
  transform: translateY(-3px);   /* Поднимается при hover */
  box-shadow: 0 4px 16px rgba(26, 26, 26, 0.06);
}
```

**Прогресс-бары (оранжевые):**

```css
.progress-bar {
  height: 6px;
  background: var(--accent);     /* Терракотовый */
  border-radius: 999px;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
```

#### IBM Plex Mono шрифт

Моноширинный шрифт для всего интерфейса. Почему?
- **Цифры выровнены:** `1,234` и `9,999` одинаковой ширины → таблицы не прыгают
- **Профессиональный вид:** как в терминале или IDE
- **Читаемость:** хорошо различимы `0` и `O`, `1` и `l`

```css
/* fonts.css */
@font-face {
  font-family: 'IBM Plex Mono';
  src: url('/static/fonts/ibm-plex-mono/IBMPlexMono-Regular.ttf');
  font-weight: 400;
  font-display: swap;
}

body {
  font-family: 'IBM Plex Mono', 'Courier New', monospace;
}
```

### Единый блок контролов

Раньше venue selector, period picker и кнопки экспорта были разбросаны по разным местам. Теперь — **единый grid-контейнер**:

```html
<!-- base.html -->
<div class="dashboard-controls">
  <div class="controls-row">
    <!-- 1. Бар -->
    <div class="control-group">
      <label>Бар</label>
      <select id="venue-selector" class="control-input">...</select>
    </div>

    <!-- 2. Период -->
    <div class="control-group">
      <label>Период анализа</label>
      <input id="flexi-range-picker" class="control-input" readonly>
    </div>

    <!-- 3. PDF -->
    <div class="control-group control-group-button">
      <label>&nbsp;</label>
      <button id="btn-export-pdf" class="btn btn-secondary">PDF</button>
    </div>
  </div>
</div>
```

```css
.controls-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;  /* Бар, Период, PDF */
  gap: 20px;
  align-items: end;
}
```

**Адаптивность на mobile:**

```css
@media (max-width: 768px) {
  .controls-row {
    grid-template-columns: 1fr;  /* Вертикальный стек */
  }
}
```

### Flatpickr: выбор периода

Используем **Flatpickr 4.6.13** с русской локалью:

```javascript
// datepicker.js

flatpickr('#flexi-range-picker', {
  mode: 'range',               // Диапазон дат
  dateFormat: 'd.m.Y',         // 01.02.2026
  locale: 'ru',
  maxDate: 'today',            // Нельзя выбрать будущее
  defaultDate: lastWeekRange,  // Прошлая неделя по умолчанию
  onChange: (selectedDates) => {
    if (selectedDates.length === 2) {
      const from = formatDateForAPI(selectedDates[0]);  // 2026-01-26
      const to = formatDateForAPI(selectedDates[1]);    // 2026-02-01
      applyPeriod(from, to);
    }
  }
});
```

**Почему Flatpickr?**
- Легковесный (15KB gzip)
- Поддержка диапазонов из коробки
- Русская локализация
- Красивый минималистичный дизайн

### Вкладки: почему удалили "Планы"?

Раньше была отдельная вкладка "Плановые показатели" → можно было создавать/редактировать планы. **Проблема:** юзеру приходилось переключаться туда-сюда:

1. Смотрю факт в "Аналитике"
2. Переключаюсь на "Планы"
3. Редактирую план
4. Возвращаюсь в "Аналитику"
5. Перезагружаю страницу 🤦

**Решение:** встроили план прямо в карточки метрик. Теперь видно сразу:
```
Выручка
692,645 руб

План: 252,077 руб
██████████░░░ 274.6% ↗ +440,568 руб
```

Вкладка "Планы" удалена:
- HTML: убрали кнопку таба из `base.html`
- JS: закомментировали `plansViewer.init()` в `main.js`
- CSS: скрыли элементы, которые ссылались на планы

### PDF экспорт

```python
# app.py → /api/export/pdf

try:
    # Пытаемся использовать reportlab (красивый PDF)
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, ...

    # Рисуем таблицу с метриками
    data = [['Метрика', 'Факт', 'План', '%']]
    for metric in metrics:
        data.append([metric.name, metric.actual, metric.plan, metric.percent])

    table = Table(data)
    doc.build([table])
    return send_file(pdf_buffer, mimetype='application/pdf')

except ImportError:
    # Fallback: HTML с таблицей
    html = render_template('export_fallback.html', metrics=metrics)
    return html
```

**Проблемы, которые были:**
1. **500 Internal Server Error** → `calculate_metrics()` получал 8 аргументов вместо 2
   - **Причина:** вызывали старую сигнатуру с отдельными `draft_data, bottles_data, kitchen_data`
   - **Решение:** перешли на `get_all_sales_report()` → один аргумент `all_sales_data`

2. **Кнопка не работала** → `btn-export-pdf` была удалена из DOM
   - **Причина:** рефакторинг контролов, забыли добавить `id="btn-export-pdf"`
   - **Решение:** добавили ID в новый unified controls блок

### Completion Badge: процент выполнения

В правом углу tabs-nav показывается **средний процент выполнения** всех метрик:

```html
<div class="tabs-nav">
  <div class="tabs-buttons">
    <button class="tab-button">Аналитика</button>
    ...
  </div>
  <div class="completion-badge" id="completion-badge">
    <span class="completion-value" id="stat-avg-completion">—</span>
  </div>
</div>
```

```javascript
// analytics.js → updateStats()

const avgPercent = metrics.reduce((sum, m) => sum + m.percent, 0) / metrics.length;

document.getElementById('stat-avg-completion').textContent = avgPercent.toFixed(1) + '%';
document.getElementById('completion-badge').style.display = 'flex';  // Показываем
```

**CSS:**

```css
.completion-badge {
  display: none;  /* Скрыт по умолчанию, показывается при загрузке данных */
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border-radius: 999px;
  font-weight: 600;
}

.completion-badge::before {
  content: '% выполнения: ';
}

.completion-value {
  color: var(--accent);  /* Оранжевый */
}
```

## Lessons Learned

### 1. Удаление модуля → проверь все импорты

**Проблема:** Удалили вкладку "Планы", но забыли отключить `plansViewer` модуль → консоль забита ошибками:

```
plans.js:89 Uncaught TypeError: Cannot set property 'innerHTML' of null
```

**Решение:** Закомментировали все упоминания:
```javascript
// main.js
// import { plansViewer } from './modules/plans.js';  // ← ОТКЛЮЧЕНО
// plansViewer.init();
```

**Урок:** При удалении фичи ищи по всем файлам (`Ctrl+Shift+F`) все упоминания модуля.

### 2. DOM элемент может не существовать → null checks

**Проблема:** `analytics.js` пытался обновить `stat-total-metrics`, но элемент был удалён:

```javascript
document.getElementById('stat-total-metrics').textContent = total;  // ❌ Error
```

**Решение:** Всегда проверяй существование:

```javascript
const element = document.getElementById('stat-total-metrics');
if (element) {
  element.textContent = total;
}
```

**Урок:** В динамическом UI всегда делай null-checks перед `.textContent`, `.style`, `.classList`.

### 3. CSS display: none → элемент невидим, но занимает место

**Проблема:** Completion badge был скрыт, но оставлял пустое место в `tabs-nav`.

**Решение:** `display: none` полностью убирает элемент из layout, а показываем через `display: flex`.

```css
.completion-badge {
  display: none;  /* Изначально скрыт */
}
```

```javascript
completionBadge.style.display = 'flex';  // Показываем при загрузке данных
```

### 4. Функция меняет сигнатуру → проверь все вызовы

**Проблема:** PDF экспорт падал с ошибкой:
```
DashboardMetrics.calculate_metrics() takes 2 positional arguments but 8 were given
```

**Причина:** Переписали метод:
```python
# Было:
calculate_metrics(date_from, date_to, bar_name, draft_data, bottles_data, kitchen_data, taps_data)

# Стало:
calculate_metrics(all_sales_data)
```

Но в `app.py` вызывали старую версию.

**Решение:** Нашли все вызовы `calculate_metrics()` и обновили:
```python
all_sales_data = olap.get_all_sales_report(date_from, date_to, bar_name)
metrics = calculator.calculate_metrics(all_sales_data)  # ← 1 аргумент
```

**Урок:** При рефакторинге API метода ищи все вызовы через IDE (Ctrl+Click → Find Usages).

### 5. Эмодзи в коде → плохая идея

**Проблема:** Эмодзи в HTML и JS выглядели как "нейрослоп":
```javascript
icon: '💰',  // Выручка
icon: '🍺',  // Разливное
```

**Решение:** Убрали все эмодзи (160+ мест):
- HTML: удалили из табов, кнопок, labels
- JS: удалили поле `icon` из `config.js`
- Тренды: заменили `📈 📉` на `↗ ↘`

**Урок:** Эмодзи хороши для мемов, но не для production UI. Используй текст или SVG иконки.

### 6. Pill-shape требует вложенных элементов

**Проблема:** Кнопки с `border-radius: 999px` выглядели некрасиво, если внутри длинный текст.

**Решение:** Добавили padding и flex:

```css
.btn {
  padding: 14px 28px;  /* Щедрый горизонтальный padding */
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 6px;            /* Между иконкой и текстом */
}
```

**Урок:** Pill-shape требует баланса padding/font-size/height. Если кнопка выглядит как "таблетка" — увеличь padding.

### 7. Flatpickr onChange срабатывает дважды

**Проблема:** При выборе диапазона `onChange` вызывался 2 раза:
1. Первый клик (выбрали start date) → `selectedDates.length === 1`
2. Второй клик (выбрали end date) → `selectedDates.length === 2`

**Решение:** Проверяем длину массива:

```javascript
onChange: (selectedDates) => {
  if (selectedDates.length === 2) {  // ← Только когда выбраны обе даты
    applyPeriod(dateFrom, dateTo);
  }
}
```

**Урок:** В range mode Flatpickr срабатывает на каждый клик. Всегда проверяй `selectedDates.length`.

## Changelog

- **2026-02-08:** Финтех редизайн 2026 (терракотовый акцент, IBM Plex Mono, pill-shape)
  - Удалена вкладка "Планы", планы встроены в аналитику
  - Единый блок контролов (venue + period + PDF)
  - Completion badge в tabs-nav
  - Удалены все эмодзи (160+ мест)
  - Оранжевые прогресс-бары
  - Исправлены ошибки: plans module, updateStats, PDF export

- **2026-01-26:** Полностью переписан согласно CLAUDE.md
- **2026-01-25:** Создан placeholder

# Frontend архитектура

## Что это

JavaScript модули дашборда и других страниц: state management, API клиент, Chart.js визуализация, 15+ модулей.

## Файлы

### Core модули
- [`static/js/dashboard/core/state.js`](../static/js/dashboard/core/state.js) — централизованное состояние (Singleton)
- [`static/js/dashboard/core/period_model.js`](../static/js/dashboard/core/period_model.js) — арифметика периода (границы гранулярностей, шаг стрелки, подписи); чистые функции, без DOM
- [`static/js/dashboard/core/api.js`](../static/js/dashboard/core/api.js) — HTTP клиент
- [`static/js/dashboard/core/config.js`](../static/js/dashboard/core/config.js) — метрики и их группы, API endpoints, storage keys
- [`static/js/dashboard/core/utils.js`](../static/js/dashboard/core/utils.js) — утилиты

### UI модули
- [`static/js/dashboard/modules/analytics.js`](../static/js/dashboard/modules/analytics.js) — загрузка и отрисовка метрик (десктоп + мобильный)
- [`static/js/dashboard/modules/period_controls.js`](../static/js/dashboard/modules/period_controls.js) — **шапка фильтров**: период, стрелки, список пресетов, календарь
- [`static/js/dashboard/modules/filter_menus.js`](../static/js/dashboard/modules/filter_menus.js) — списки заведения и выгрузки; вид над скрытым `<select>`, данными владеет venue_selector.js
- [`static/js/dashboard/modules/charts.js`](../static/js/dashboard/modules/charts.js) — Chart.js графики
- [`static/js/dashboard/modules/trends.js`](../static/js/dashboard/modules/trends.js) — тренды по неделям
- [`static/js/dashboard/modules/comparison.js`](../static/js/dashboard/modules/comparison.js) — сравнение периодов
- [`static/js/dashboard/modules/venue_selector.js`](../static/js/dashboard/modules/venue_selector.js) — селектор заведений
- [`static/js/dashboard/modules/week_selector.js`](../static/js/dashboard/modules/week_selector.js) — загружает список недель в `state.weeks` (нужен графикам/трендам); DOM-ветки мертвы, селектора недель в разметке нет
- [`static/js/dashboard/modules/datepicker.js`](../static/js/dashboard/modules/datepicker.js) — **устарел, пустая заглушка**; период живёт в `period_controls.js`. Файл оставлен намеренно: старые открытые вкладки импортируют его по имени, 404 уронил бы им весь дашборд
- [`static/js/dashboard/modules/export.js`](../static/js/dashboard/modules/export.js) — экспорт Excel/PDF
- [`static/js/dashboard/modules/comments.js`](../../static/js/dashboard/modules/comments.js) — комментарии
- [`static/js/dashboard/modules/meeting_notes.js`](../../static/js/dashboard/modules/meeting_notes.js) — meeting notes
- [`static/js/dashboard/modules/revenue_metrics.js`](../../static/js/dashboard/modules/revenue_metrics.js) — метрики выручки
- [`static/js/dashboard/modules/expiry.js`](../../static/js/dashboard/modules/expiry.js) — Честный ЗНАК
- [`static/js/dashboard/modules/theme.js`](../../static/js/dashboard/modules/theme.js) — тёмная/светлая тема
- [`static/js/dashboard/modules/plans.js`](../../static/js/dashboard/modules/plans.js) — планы

### Стили
- [`static/dashboard/styles/variables.css`](../../static/dashboard/styles/variables.css) — CSS переменные
- [`static/dashboard/styles/base.css`](../../static/dashboard/styles/base.css) — базовые стили
- [`static/dashboard/styles/tabs.css`](../../static/dashboard/styles/tabs.css) — табы
- [`static/dashboard/styles/cards.css`](../../static/dashboard/styles/cards.css) — карточки
- [`static/dashboard/styles/charts.css`](../../static/dashboard/styles/charts.css) — графики
- [`static/dashboard/styles/mobile.css`](../../static/dashboard/styles/mobile.css) — мобильная версия

---

## Как работает

### State Management (Singleton)

Состояние — класс `DashboardState` с плоскими полями и рассылкой **именованных
событий** (не единый объект `state` + `setState`):

```javascript
// static/js/dashboard/core/state.js
class DashboardState {
    constructor() {
        this.currentVenue = /* localStorage или 'all' */;
        this.currentPeriod = defaultPeriod();   // последняя завершённая неделя
        this.currentMonth = '08';               // строка '01'..'12'
        this.currentYear = 2026;                // число
        this.subscribers = [];
    }

    setPeriod(period) { /* notify('periodChanged'), при смене месяца — 'monthChanged' */ }
    setVenue(key)     { /* notify('venueChanged') */ }
    setActiveTab(tab) { /* notify('tabChanged') */ }
    notify(event, data) { this.subscribers.forEach(cb => cb(event, data)); }
}

export const state = new DashboardState();
```

### Использование

```javascript
// Подписчик получает (event, data), а не весь стейт
state.subscribe((event, data) => {
    if (event === 'periodChanged' || event === 'venueChanged') reload();
});

state.setPeriod(periodFor('week', new Date()));
```

### Контракт, который нельзя ломать

| Поле | Формат | Кто сломается при изменении |
|------|--------|------------------------------|
| `period.start` / `period.end` | ISO `YYYY-MM-DD`, **инклюзивно** | `analytics.js`, `export.js`, `meeting_notes.js`; сдвиг `+1` для iiko делает сервер |
| `period.key` | `YYYY-MM-DD_YYYY-MM-DD` | `comments.js` (уходит в URL), `charts.js`/`trends.js` (ищут неделю по ключу), имя файла экспорта |
| `currentMonth` | **строка** `'01'..'12'` с ведущим нулём | `plans.js` собирает ключ плана `${year}-${month}`; `2026-8` даёт 404 |
| `currentYear` | **число** | там же |
| событие `monthChanged` | шлётся при смене месяца/года | вкладки «Выручка», «Планы», «Планы по дням» |

`setPeriod` рассылает `monthChanged` **только когда месяц или год реально
сменились**, поэтому листание стрелками внутри одного месяца не дёргает месячные
вкладки.

Период **не персистится**: дашборд всегда открывается на последней завершённой
неделе (единственный источник дефолта — конструктор `DashboardState`).

---

### API Client

```javascript
// static/js/dashboard/core/api.js
const API_BASE = '/api';

export const api = {
    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            headers: { 'Content-Type': 'application/json' },
            ...options
        };

        const response = await fetch(url, config);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        return response.json();
    },

    async get(endpoint) {
        return this.request(endpoint);
    },

    async post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
};
```

### Конфигурация

```javascript
// static/js/dashboard/core/config.js
export const config = {
    API_ENDPOINTS: {
        DASHBOARD_ANALYTICS: '/dashboard-analytics',
        VENUES: '/venues',
        WEEKS: '/weeks',
        PLANS: '/plans',
        COMPARE_PERIODS: '/compare/periods',
        TRENDS: '/trends',
        EXPORT_EXCEL: '/export/excel',
        EXPORT_PDF: '/export/pdf'
    },

    STORAGE_KEYS: {
        LAST_VENUE: 'dashboard_last_venue',
        LAST_DATE_FROM: 'dashboard_last_date_from',
        LAST_DATE_TO: 'dashboard_last_date_to',
        THEME: 'dashboard_theme'
    },

    CHART_COLORS: {
        draft: '#D97757',
        bottles: '#57B8D9',
        kitchen: '#7BD957'
    }
};
```

---

### Analytics Module

```javascript
// static/js/dashboard/modules/analytics.js
import { api } from '../core/api.js';
import { state } from '../core/state.js';
import { config } from '../core/config.js';

export async function loadAnalytics() {
    const { dateFrom, dateTo, currentVenue } = state.getState();

    if (!dateFrom || !dateTo) {
        return;
    }

    state.setState({ isLoading: true });

    try {
        const data = await api.post(config.API_ENDPOINTS.DASHBOARD_ANALYTICS, {
            venue: currentVenue || '',
            dateFrom,
            dateTo
        });

        state.setState({
            metrics: data.metrics,
            plan: data.plan,
            comparison: data.comparison,
            isLoading: false
        });
    } catch (error) {
        state.setState({ error: error.message, isLoading: false });
    }
}
```

---

### Charts Module (Chart.js)

```javascript
// static/js/dashboard/modules/charts.js
import { config } from '../core/config.js';

let revenueChart = null;
let shareChart = null;

export function initRevenueChart(ctx) {
    revenueChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Выручка',
                data: [],
                backgroundColor: config.CHART_COLORS.draft
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

export function updateRevenueChart(labels, data) {
    if (!revenueChart) return;

    revenueChart.data.labels = labels;
    revenueChart.data.datasets[0].data = data;
    revenueChart.update();
}

export function initShareChart(ctx) {
    shareChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Розлив', 'Фасовка', 'Кухня'],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: [
                    config.CHART_COLORS.draft,
                    config.CHART_COLORS.bottles,
                    config.CHART_COLORS.kitchen
                ]
            }]
        },
        options: {
            responsive: true,
            cutout: '60%'
        }
    });
}
```

---

### Trends Module

```javascript
// static/js/dashboard/modules/trends.js
import { api } from '../core/api.js';
import { config } from '../core/config.js';

export async function loadTrends(venue, metric) {
    const { dateFrom, dateTo } = state.getState();

    const endpoint = `${config.API_ENDPOINTS.TRENDS}/${venue}/${metric}` +
        `?dateFrom=${dateFrom}&dateTo=${dateTo}`;

    const data = await api.get(endpoint);

    return data; // {week: value, ...}
}
```

---

### Comparison Module

```javascript
// static/js/dashboard/modules/comparison.js
import { api } from '../core/api.js';
import { config } from '../core/config.js';

export async function comparePeriods(current, previous) {
    const data = await api.post(config.API_ENDPOINTS.COMPARE_PERIODS, {
        current: {
            dateFrom: current.dateFrom,
            dateTo: current.dateTo
        },
        previous: {
            dateFrom: previous.dateFrom,
            dateTo: previous.dateTo
        }
    });

    return data; // {metrics: [...], diff: {...}}
}
```

---

### Theme Module

```javascript
// static/js/dashboard/modules/theme.js
import { config } from '../core/config.js';

const THEME_KEY = config.STORAGE_KEYS.THEME;

export function initTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY) || 'light';
    document.body.setAttribute('data-theme', savedTheme);
}

export function toggleTheme() {
    const current = document.body.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';

    document.body.setAttribute('data-theme', next);
    localStorage.setItem(THEME_KEY, next);
}

export function getTheme() {
    return document.body.getAttribute('data-theme');
}
```

---

### Шапка фильтров (period_controls.js)

Flatpickr подключается **глобальным скриптом с CDN** (`templates/dashboard.html`),
а не через `import` — сборщика в проекте нет. Панель владеет единственным
экземпляром календаря:

```javascript
// static/js/dashboard/modules/period_controls.js
this.flatpickr = flatpickr(this.pickerInput, {
    mode: 'range',
    dateFormat: 'd.m.Y',
    locale: 'ru',
    positionElement: this.trigger,       // календарь у подписи, не у скрытого инпута
    maxDate: new Date(2027, 11, 31),     // ТОЛЬКО Date-объект, не строка
    onChange: (dates) => this.onPickerChange(dates)
});
```

**`maxDate` только Date-объектом.** Строку Flatpickr парсит собственным
`dateFormat: 'd.m.Y'` и из `'2027-12-31'` читает день `20` — календарь упирается
в 20-е число текущего месяца.

**Стили Flatpickr подключены ДО наших** (`templates/dashboard.html`): специфичность
правил одинаковая, решает порядок, иначе CDN побеждает и календарь в тёмной теме
остаётся белым. Переопределения — в `static/dashboard/styles/base.css`.

Тёмная тема применяется атрибутом `data-theme="dark"` на `<html>`
(`modules/theme.js`), поэтому оверрайды пишутся как `[data-theme="dark"] .flatpickr-*`.

---

## CSS Архитектура

### Переменные (CSS Custom Properties)

```css
/* static/dashboard/styles/variables.css */
:root {
    /* Цвета */
    --color-primary: #D97757;
    --color-secondary: #57B8D9;
    --color-success: #7BD957;
    --color-warning: #D9B857;
    --color-danger: #D95757;

    /* Тёмная тема */
    --bg-primary: #1a1a2e;
    --bg-secondary: #16213e;
    --bg-card: #0f3460;
    --text-primary: #eaeaea;
    --text-secondary: #a0a0a0;

    /* Светлая тема */
    --bg-primary-light: #f5f5f5;
    --bg-secondary-light: #ffffff;
    --bg-card-light: #f0f0f0;
    --text-primary-light: #1a1a1a;
    --text-secondary-light: #666666;

    /* Отступы */
    --spacing-xs: 0.25rem;
    --spacing-sm: 0.5rem;
    --spacing-md: 1rem;
    --spacing-lg: 1.5rem;
    --spacing-xl: 2rem;

    /* Радиусы */
    --radius-sm: 4px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --radius-xl: 16px;
}
```

### Базовые стили

```css
/* static/dashboard/styles/base.css */
body {
    font-family: 'IBM Plex Mono', monospace;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    margin: 0;
    padding: 0;
}

.card {
    background: var(--bg-card);
    border-radius: var(--radius-md);
    padding: var(--spacing-lg);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.btn {
    padding: var(--spacing-sm) var(--spacing-md);
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: all 0.2s;
}

.btn-primary {
    background: var(--color-primary);
    color: white;
}

.btn-primary:hover {
    opacity: 0.9;
    transform: translateY(-1px);
}
```

---

## Зависимости

### Внешние библиотеки
- **Chart.js** — визуализация графиков
- **Flatpickr** — выбор дат
- **IBM Plex Mono** — шрифт

### От каких модулей зависит
- Backend API (`/api/*` endpoint'ы)

### Кто использует
- Все HTML шаблоны (`dashboard.html`, `employee.html`, ...)

---

## Changelog

- **2026-08-12** — Период и заведение живут в единой шапке фильтров (макет 5a/6a); добавлен `filter_menus.js`. Отдельных селекторов и сегментов гранулярности больше нет.
- **2026-08-11** — Приведено в соответствие с кодом + редизайн дашборда:
  (1) секция State Management описывала несуществующий `StateManager` с
  `setState/getState` — заменена на реальный `DashboardState` с событиями
  `periodChanged`/`monthChanged`, добавлена таблица контракта полей;
  (2) секция Datepicker содержала выдуманный код (`import flatpickr`, `theme: 'dark'`)
  — заменена описанием реальной панели периода и грабель `maxDate`/порядка CSS;
  (3) в список модулей добавлен `period_controls.js` (отсутствовал), у `datepicker.js`
  и `week_selector.js` отмечено, что они устарели/частично мертвы;
  (4) относительные ссылки исправлены с `../../` на `../` (файл лежит в `docs/`).
- **2026-03-27** — Создан документ frontend.md с описанием state management, API клиента, модулей

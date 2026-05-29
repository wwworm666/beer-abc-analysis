# Frontend архитектура

## Что это

JavaScript модули дашборда и других страниц: state management, API клиент, Chart.js визуализация, 15+ модулей.

## Файлы

### Core модули
- [`static/js/dashboard/core/state.js`](../../static/js/dashboard/core/state.js) — централизованное состояние (Singleton)
- [`static/js/dashboard/core/api.js`](../../static/js/dashboard/core/api.js) — HTTP клиент
- [`static/js/dashboard/core/config.js`](../../static/js/dashboard/core/config.js) — API endpoints, storage keys
- [`static/js/dashboard/core/utils.js`](../../static/js/dashboard/core/utils.js) — утилиты

### UI модули
- [`static/js/dashboard/modules/analytics.js`](../../static/js/dashboard/modules/analytics.js) — загрузка аналитики
- [`static/js/dashboard/modules/charts.js`](../../static/js/dashboard/modules/charts.js) — Chart.js графики
- [`static/js/dashboard/modules/trends.js`](../../static/js/dashboard/modules/trends.js) — тренды по неделям
- [`static/js/dashboard/modules/comparison.js`](../../static/js/dashboard/modules/comparison.js) — сравнение периодов
- [`static/js/dashboard/modules/venue_selector.js`](../../static/js/dashboard/modules/venue_selector.js) — селектор заведений
- [`static/js/dashboard/modules/week_selector.js`](../../static/js/dashboard/modules/week_selector.js) — селектор недель
- [`static/js/dashboard/modules/datepicker.js`](../../static/js/dashboard/modules/datepicker.js) — Flatpickr даты
- [`static/js/dashboard/modules/export.js`](../../static/js/dashboard/modules/export.js) — экспорт Excel/PDF
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

```javascript
// static/js/dashboard/core/state.js
class StateManager {
    constructor() {
        if (StateManager.instance) {
            return StateManager.instance;
        }

        this.state = {
            currentVenue: null,
            dateFrom: null,
            dateTo: null,
            metrics: null,
            plan: null,
            comparison: null,
            trends: null,
            isLoading: false,
            error: null
        };

        this.listeners = [];
        StateManager.instance = this;
    }

    setState(newState) {
        this.state = { ...this.state, ...newState };
        this.notifyListeners();
    }

    getState() {
        return this.state;
    }

    subscribe(listener) {
        this.listeners.push(listener);
    }

    notifyListeners() {
        this.listeners.forEach(listener => listener(this.state));
    }
}

export const state = new StateManager();
```

### Использование

```javascript
// Подписка на изменения
state.subscribe((newState) => {
    updateUI(newState);
});

// Обновление состояния
state.setState({
    currentVenue: 'bolshoy',
    dateFrom: '2026-03-01',
    dateTo: '2026-03-07'
});
```

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

### Datepicker Module (Flatpickr)

```javascript
// static/js/dashboard/modules/datepicker.js
import flatpickr from 'flatpickr';
import 'flatpickr/dist/flatpickr.min.css';
import 'flatpickr/dist/themes/dark.css';

export function initDatepicker(selector, options = {}) {
    return flatpickr(selector, {
        dateFormat: 'Y-m-d',
        defaultDate: options.defaultDate,
        maxDate: options.maxDate || 'today',
        onChange: options.onChange,
        theme: 'dark'
    });
}
```

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

- **2026-03-27** — Создан документ frontend.md с описанием state management, API клиента, модулей

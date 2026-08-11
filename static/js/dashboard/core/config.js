/**
 * Конфигурация дашборда
 * Константы, настройки, маппинги метрик
 */

/**
 * Группы метрик (редизайн 2026-08-11).
 *
 * Одна группировка на оба экрана: на десктопе группа = разделитель с названием
 * над сеткой карточек, на мобильном = свёрнутая строка-аккордеон.
 * Порядок массива = порядок на экране.
 *
 * 'main' — три метрики, отвечающие на вопрос «как идёт период»: на мобильном они
 * показаны крупно и не сворачиваются.
 */
export const METRIC_GROUPS = [
    { id: 'main',     name: 'Итого',   mobileName: 'Главное', collapsible: false },
    { id: 'draft',    name: 'Розлив',  mobileName: 'Розлив',  collapsible: true },
    { id: 'packaged', name: 'Фасовка', mobileName: 'Фасовка', collapsible: true },
    { id: 'kitchen',  name: 'Кухня',   mobileName: 'Кухня',   collapsible: true },
    { id: 'other',    name: 'Прочее',  mobileName: 'Прочее',  collapsible: true }
];

// Конфигурация метрик (16 показателей).
// group — к какой группе относится метрика (см. METRIC_GROUPS).
export const METRICS = [
    {
        id: 'revenue',
        name: 'Выручка',
        group: 'main',
        planKey: 'revenue',
        actualKey: 'revenue',  // ИСПРАВЛЕНО: было total_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'checks',
        name: 'Чеки',
        group: 'main',
        planKey: 'checks',
        actualKey: 'checks',  // ИСПРАВЛЕНО: было total_checks
        unit: 'шт',
        format: 'number'
    },
    {
        id: 'averageCheck',
        name: 'Средний чек',
        group: 'main',
        planKey: 'averageCheck',
        actualKey: 'averageCheck',  // ИСПРАВЛЕНО: было avg_check
        unit: '₽',
        format: 'money'
    },
    {
        id: 'draftShare',
        name: 'Доля розлива',
        group: 'draft',
        planKey: 'draftShare',
        actualKey: 'draftShare',  // ИСПРАВЛЕНО: было draft_share
        unit: '%',
        format: 'percent'
    },
    {
        id: 'revenueDraft',
        name: 'Выручка розлив',
        group: 'draft',
        planKey: 'revenueDraft',
        actualKey: 'revenueDraft',  // ИСПРАВЛЕНО: было draft_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupDraft',
        name: 'Наценка розлив',
        group: 'draft',
        planKey: 'markupDraft',
        actualKey: 'markupDraft',  // ИСПРАВЛЕНО: было draft_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'packagedShare',
        name: 'Доля фасовки',
        group: 'packaged',
        planKey: 'packagedShare',
        actualKey: 'packagedShare',  // ИСПРАВЛЕНО: было bottles_share
        unit: '%',
        format: 'percent'
    },
    {
        id: 'revenuePackaged',
        name: 'Выручка фасовка',
        group: 'packaged',
        planKey: 'revenuePackaged',
        actualKey: 'revenuePackaged',  // ИСПРАВЛЕНО: было bottles_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupPackaged',
        name: 'Наценка фасовка',
        group: 'packaged',
        planKey: 'markupPackaged',
        actualKey: 'markupPackaged',  // ИСПРАВЛЕНО: было bottles_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'kitchenShare',
        name: 'Доля кухни',
        group: 'kitchen',
        planKey: 'kitchenShare',
        actualKey: 'kitchenShare',  // ИСПРАВЛЕНО: было kitchen_share
        unit: '%',
        format: 'percent'
    },
    {
        id: 'revenueKitchen',
        name: 'Выручка кухня',
        group: 'kitchen',
        planKey: 'revenueKitchen',
        actualKey: 'revenueKitchen',  // ИСПРАВЛЕНО: было kitchen_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupKitchen',
        name: 'Наценка кухня',
        group: 'kitchen',
        planKey: 'markupKitchen',
        actualKey: 'markupKitchen',  // ИСПРАВЛЕНО: было kitchen_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'markupPercent',
        name: '% наценки',
        group: 'other',
        planKey: 'markupPercent',
        actualKey: 'markupPercent',  // ИСПРАВЛЕНО: было avg_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'profit',
        name: 'Прибыль',
        group: 'other',
        planKey: 'profit',
        actualKey: 'profit',  // ИСПРАВЛЕНО: было total_margin
        unit: '₽',
        format: 'money'
    },
    {
        id: 'loyaltyWriteoffs',
        name: 'Списания баллов',
        group: 'other',
        planKey: 'loyaltyWriteoffs',
        actualKey: 'loyaltyWriteoffs',  // ИСПРАВЛЕНО: было loyalty_points_written_off
        unit: '₽',
        format: 'money'
    },
    {
        id: 'tapActivity',
        name: 'Активность кранов',
        group: 'other',
        planKey: 'tapActivity',
        actualKey: 'tapActivity',
        unit: '%',
        format: 'percent'
    }
];

// Статусы выполнения плана
export const STATUS = {
    SUCCESS: 'success',  // >= 100%
    WARNING: 'warning',  // 90-99%
    DANGER: 'danger'     // < 90%
};

// Пороги для статусов
export const THRESHOLDS = {
    SUCCESS: 100,
    WARNING: 90
};

// localStorage ключи
export const STORAGE_KEYS = {
    THEME: 'dashboard_theme',
    SELECTED_VENUE: 'dashboard_selected_venue',
    SELECTED_PERIOD: 'dashboard_selected_period'
};

// API endpoints
export const API = {
    VENUES: '/api/venues',
    VENUE: (venueKey) => `/api/venues/${venueKey}`,
    WEEKS: '/api/weeks',
    PLAN: (venueKey, periodKey) => `/api/plans/${venueKey}/${periodKey}`,
    // Новый endpoint для расчёта плана на произвольный период
    CALCULATE_PLAN: (venueKey, startDate, endDate) => `/api/plans/calculate/${venueKey || 'total'}/${startDate}/${endDate}`,
    // Подневная разбивка месячного плана (страница «Планы по дням»)
    DAILY_BREAKDOWN: (venueKey, year, month) => `/api/plans/daily/${venueKey || 'all'}/${year}/${month}`,
    DAILY_WEIGHT_RESET: (venueKey, year, month, dateStr) => `/api/plans/daily/${venueKey || 'all'}/${year}/${month}/${dateStr}`,
    ANALYTICS: '/api/dashboard-analytics',  // ИСПРАВЛЕНО: было dashboard-analytics-multi
    COMPARISON_PERIODS: '/api/comparison/periods',
    COMPARISON_VENUES: '/api/comparison/venues',
    TRENDS: (venueKey, metric, weeks) => `/api/trends/${venueKey}/${metric}/${weeks}`,
    EXPORT_EXCEL: '/api/export/excel',
    EXPORT_PDF: '/api/export/pdf',
    COMMENTS: (venueKey, periodKey) => `/api/comments/${venueKey}/${periodKey}`
};

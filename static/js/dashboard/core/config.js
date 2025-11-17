/**
 * Конфигурация дашборда
 * Константы, настройки, маппинги метрик
 */

// Конфигурация метрик (15 показателей)
export const METRICS = [
    {
        id: 'revenue',
        icon: '💰',
        name: 'Выручка',
        planKey: 'revenue',
        actualKey: 'total_revenue',
        unit: '₽',
        format: 'money'
    },
    {
        id: 'checks',
        icon: '🧾',
        name: 'Чеки',
        planKey: 'checks',
        actualKey: 'total_checks',
        unit: 'шт',
        format: 'number'
    },
    {
        id: 'averageCheck',
        icon: '💵',
        name: 'Средний чек',
        planKey: 'averageCheck',
        actualKey: 'avg_check',
        unit: '₽',
        format: 'money'
    },
    {
        id: 'draftShare',
        icon: '🍺',
        name: 'Доля розлива',
        planKey: 'draftShare',
        actualKey: 'draft_share',
        unit: '%',
        format: 'percent'
    },
    {
        id: 'packagedShare',
        icon: '🍾',
        name: 'Доля фасовки',
        planKey: 'packagedShare',
        actualKey: 'bottles_share',
        unit: '%',
        format: 'percent'
    },
    {
        id: 'kitchenShare',
        icon: '🍽️',
        name: 'Доля кухни',
        planKey: 'kitchenShare',
        actualKey: 'kitchen_share',
        unit: '%',
        format: 'percent'
    },
    {
        id: 'revenueDraft',
        icon: '💰',
        name: 'Выручка розлив',
        planKey: 'revenueDraft',
        actualKey: 'draft_revenue',
        unit: '₽',
        format: 'money'
    },
    {
        id: 'revenuePackaged',
        icon: '💰',
        name: 'Выручка фасовка',
        planKey: 'revenuePackaged',
        actualKey: 'bottles_revenue',
        unit: '₽',
        format: 'money'
    },
    {
        id: 'revenueKitchen',
        icon: '💰',
        name: 'Выручка кухня',
        planKey: 'revenueKitchen',
        actualKey: 'kitchen_revenue',
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupPercent',
        icon: '📈',
        name: '% наценки',
        planKey: 'markupPercent',
        actualKey: 'avg_markup',
        unit: '%',
        format: 'percent'
    },
    {
        id: 'profit',
        icon: '💹',
        name: 'Прибыль',
        planKey: 'profit',
        actualKey: 'total_margin',
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupDraft',
        icon: '📈',
        name: 'Наценка розлив',
        planKey: 'markupDraft',
        actualKey: 'draft_markup',
        unit: '%',
        format: 'percent'
    },
    {
        id: 'markupPackaged',
        icon: '📈',
        name: 'Наценка фасовка',
        planKey: 'markupPackaged',
        actualKey: 'bottles_markup',
        unit: '%',
        format: 'percent'
    },
    {
        id: 'markupKitchen',
        icon: '📈',
        name: 'Наценка кухня',
        planKey: 'markupKitchen',
        actualKey: 'kitchen_markup',
        unit: '%',
        format: 'percent'
    },
    {
        id: 'loyaltyWriteoffs',
        icon: '💳',
        name: 'Списания баллов',
        planKey: 'loyaltyWriteoffs',
        actualKey: 'loyalty_points_written_off',
        unit: '₽',
        format: 'money'
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
    ALL_PLANS: (venueKey) => `/api/plans/${venueKey}`,
    ANALYTICS: '/api/dashboard-analytics',  // ИСПРАВЛЕНО: было dashboard-analytics-multi
    COMPARISON_PERIODS: '/api/comparison/periods',
    COMPARISON_VENUES: '/api/comparison/venues',
    TRENDS: (venueKey, metric, weeks) => `/api/trends/${venueKey}/${metric}/${weeks}`,
    EXPORT_EXCEL: '/api/export/excel',
    EXPORT_PDF: '/api/export/pdf',
    COMMENTS: (venueKey, periodKey) => `/api/comments/${venueKey}/${periodKey}`
};

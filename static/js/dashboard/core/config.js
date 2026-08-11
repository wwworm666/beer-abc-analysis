/**
 * Конфигурация дашборда
 * Константы, настройки, маппинги метрик
 */

/**
 * Группы метрик — по ТИПУ показателя, ровно 4 группы по 4 метрики.
 *
 * Почему по типу, а не по направлению (розлив/фасовка/кухня): 16 метрик делятся
 * на 4x4 без остатка, поэтому в сетке из 4 колонок каждая строка заполнена
 * целиком — при группировке по направлению группы были по 3 метрики и справа
 * оставалась пустая четверть ряда. Побочная выгода: один тип показателя по всем
 * направлениям стоит в одном ряду, и розлив/фасовка/кухня сравниваются глазом.
 *
 * Порядок массива = порядок на экране.
 * Одна группировка на оба экрана; на мобильном группа = строка-аккордеон.
 */
export const METRIC_GROUPS = [
    { id: 'revenue',    name: 'Выручка' },
    { id: 'operations', name: 'Чек и прибыль' },
    { id: 'structure',  name: 'Структура' },
    { id: 'markup',     name: 'Наценка' }
];

/**
 * Метрики, отвечающие на вопрос «как идёт период».
 * На мобильном рисуются крупно в блоке «Главное» и исключаются из аккордеонов,
 * чтобы не дублироваться. На десктопе живут в своих группах как обычные карточки.
 */
export const HEADLINE_METRIC_IDS = ['revenue', 'checks', 'averageCheck'];

// Конфигурация метрик (16 показателей).
// group — к какой группе относится метрика (см. METRIC_GROUPS).
export const METRICS = [
    {
        id: 'revenue',
        name: 'Выручка',
        group: 'revenue',
        planKey: 'revenue',
        actualKey: 'revenue',  // ИСПРАВЛЕНО: было total_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'checks',
        name: 'Чеки',
        group: 'operations',
        planKey: 'checks',
        actualKey: 'checks',  // ИСПРАВЛЕНО: было total_checks
        unit: 'шт',
        format: 'number'
    },
    {
        id: 'averageCheck',
        name: 'Средний чек',
        group: 'operations',
        planKey: 'averageCheck',
        actualKey: 'averageCheck',  // ИСПРАВЛЕНО: было avg_check
        unit: '₽',
        format: 'money'
    },
    {
        // Итог группы идёт первым — как «Выручка» в группе выручки.
        id: 'markupPercent',
        name: '% наценки',
        group: 'markup',
        planKey: 'markupPercent',
        actualKey: 'markupPercent',  // ИСПРАВЛЕНО: было avg_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'draftShare',
        name: 'Доля розлива',
        group: 'structure',
        planKey: 'draftShare',
        actualKey: 'draftShare',  // ИСПРАВЛЕНО: было draft_share
        unit: '%',
        format: 'percent'
    },
    {
        id: 'revenueDraft',
        name: 'Выручка розлив',
        group: 'revenue',
        planKey: 'revenueDraft',
        actualKey: 'revenueDraft',  // ИСПРАВЛЕНО: было draft_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupDraft',
        name: 'Наценка розлив',
        group: 'markup',
        planKey: 'markupDraft',
        actualKey: 'markupDraft',  // ИСПРАВЛЕНО: было draft_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'packagedShare',
        name: 'Доля фасовки',
        group: 'structure',
        planKey: 'packagedShare',
        actualKey: 'packagedShare',  // ИСПРАВЛЕНО: было bottles_share
        unit: '%',
        format: 'percent'
    },
    {
        id: 'revenuePackaged',
        name: 'Выручка фасовка',
        group: 'revenue',
        planKey: 'revenuePackaged',
        actualKey: 'revenuePackaged',  // ИСПРАВЛЕНО: было bottles_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupPackaged',
        name: 'Наценка фасовка',
        group: 'markup',
        planKey: 'markupPackaged',
        actualKey: 'markupPackaged',  // ИСПРАВЛЕНО: было bottles_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'kitchenShare',
        name: 'Доля кухни',
        group: 'structure',
        planKey: 'kitchenShare',
        actualKey: 'kitchenShare',  // ИСПРАВЛЕНО: было kitchen_share
        unit: '%',
        format: 'percent'
    },
    {
        id: 'revenueKitchen',
        name: 'Выручка кухня',
        group: 'revenue',
        planKey: 'revenueKitchen',
        actualKey: 'revenueKitchen',  // ИСПРАВЛЕНО: было kitchen_revenue
        unit: '₽',
        format: 'money'
    },
    {
        id: 'markupKitchen',
        name: 'Наценка кухня',
        group: 'markup',
        planKey: 'markupKitchen',
        actualKey: 'markupKitchen',  // ИСПРАВЛЕНО: было kitchen_markup
        unit: '%',
        format: 'percent'
    },
    {
        id: 'profit',
        name: 'Прибыль',
        group: 'operations',
        planKey: 'profit',
        actualKey: 'profit',  // ИСПРАВЛЕНО: было total_margin
        unit: '₽',
        format: 'money'
    },
    {
        id: 'loyaltyWriteoffs',
        name: 'Списания баллов',
        group: 'operations',
        planKey: 'loyaltyWriteoffs',
        actualKey: 'loyaltyWriteoffs',  // ИСПРАВЛЕНО: было loyalty_points_written_off
        unit: '₽',
        format: 'money'
    },
    {
        id: 'tapActivity',
        name: 'Активность кранов',
        group: 'structure',
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

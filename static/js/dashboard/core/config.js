/**
 * Конфигурация дашборда
 * Константы, настройки, маппинги метрик
 */

/**
 * Группы метрик — по ТИПУ показателя: четыре группы по 4 карточки и группа
 * «Лояльность» с одной.
 *
 * Почему по типу, а не по направлению (розлив/фасовка/кухня): 16 базовых метрик
 * делятся на 4x4 без остатка, поэтому в сетке из 4 колонок каждая строка
 * заполнена целиком — при группировке по направлению группы были по 3 метрики и
 * справа оставалась пустая четверть ряда. Побочная выгода: один тип показателя
 * по всем направлениям стоит в одном ряду, и розлив/фасовка/кухня сравниваются
 * глазом.
 *
 * Группа «Лояльность» (2026-09-04) — последняя. С 2026-09-05 в ней одна карточка
 * «Доля чеков с картой» (решение владельца): бывшие карточки «Чеки с картой»,
 * «Чеки без карты» и «Выручка по картам» стали её вкладками, а сами числа
 * по-прежнему отдаются API и живут в сравнении периодов и экспорте. Данные те же,
 * что блок «Выручка карты/без карт» в месячном отчёте, но из того же
 * единственного OLAP-запроса, что и остальные метрики.
 *
 * Порядок массива = порядок на экране.
 * Одна группировка на оба экрана; на мобильном группа = строка-аккордеон.
 */
export const METRIC_GROUPS = [
    { id: 'revenue',    name: 'Выручка' },
    { id: 'operations', name: 'Чек и прибыль' },
    { id: 'structure',  name: 'Структура' },
    { id: 'markup',     name: 'Наценка' },
    { id: 'loyalty',    name: 'Лояльность' }
];

/**
 * Метрики, отвечающие на вопрос «как идёт период».
 * На мобильном рисуются крупно в блоке «Главное» и исключаются из аккордеонов,
 * чтобы не дублироваться. На десктопе живут в своих группах как обычные карточки.
 */
export const HEADLINE_METRIC_IDS = ['revenue', 'checks', 'averageCheck'];

// Конфигурация карточек (17 карточек; данных в API больше — см. comparison.js).
// group — к какой группе относится метрика (см. METRIC_GROUPS).
// hint  — необязательная подсказка-формула простым языком; экран показывает её
//         в title названия метрики (принцип «формула видна пользователю»).
// budget — план метрики является потолком, а не целью (меньше лучше): светофор,
//          цвет отклонения и средние считаются от зеркального процента
//          200 − p (utils.js scorePercent), подпись «бюджет» вместо «план».
//          Зеркало: core/plans_manager.py BUDGET_METRICS (HTML-экспорт).
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
        format: 'money',
        // План списаний — бюджет (5% выручки в форме планов): перерасход — минус
        // для бизнеса, поэтому выше бюджета красный, ниже — зелёный.
        budget: true,
        hint: 'Сумма DiscountSum по строкам чеков: все скидки чека, не только баллы лояльности. '
            + 'План — бюджет: до 100% зелёный, 100–110% жёлтый, выше 110% красный'
    },
    {
        id: 'tapActivity',
        name: 'Активность кранов',
        group: 'structure',
        planKey: 'tapActivity',
        actualKey: 'tapActivity',
        unit: '%',
        format: 'percent',
        hint: 'Активность = сумма активных кран-дней / (кранов × дней) × 100; кран активен в день, если последнее событие до конца дня — подключение или замена кеги'
    },
    {
        // Лояльность: чек «с картой», если хотя бы у одной его строки в OLAP
        // непустое Delivery.CustomerCardNumber. Единственная карточка группы
        // (с 2026-09-05): чеки с картой / без карты и выручка по картам — её
        // вкладки. План как у всех, по умолчанию 70% (PlansManager.PLAN_DEFAULTS),
        // меняется на вкладке «Планы».
        id: 'cardChecksShare',
        name: 'Доля чеков с картой',
        group: 'loyalty',
        planKey: 'cardChecksShare',
        actualKey: 'cardChecksShare',
        unit: '%',
        format: 'percent',
        hint: 'Доля чеков с картой = чеки с картой / все чеки × 100; чек с картой — непустой номер карты лояльности '
            + 'хотя бы в одной строке. План по умолчанию 70%, правится на вкладке «Планы». '
            + 'Чеки с картой / без карты и выручка по картам — во вкладках карточки'
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
    // Раскрытие карточки: вкладка «Сотрудники» и секции метрики (2026-09-04)
    EMPLOYEE_BREAKDOWN: '/api/employee-metrics-breakdown',
    CARD_DETAILS: '/api/dashboard-card-details',
    COMPARISON_PERIODS: '/api/comparison/periods',
    COMPARISON_VENUES: '/api/comparison/venues',
    TRENDS: (venueKey, metric, weeks) => `/api/trends/${venueKey}/${metric}/${weeks}`,
    EXPORT_EXCEL: '/api/export/excel',
    EXPORT_PDF: '/api/export/pdf',
    COMMENTS: (venueKey, periodKey) => `/api/comments/${venueKey}/${periodKey}`
};

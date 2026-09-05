/**
 * Модуль аналитики
 * Загрузка и отображение данных план vs факт
 */

import { state } from '../core/state.js';
import { calculatePlan, getAnalytics, getEmployeeBreakdown, getCardDetails } from '../core/api.js';
import { METRICS, METRIC_GROUPS, HEADLINE_METRIC_IDS } from '../core/config.js';
import { shiftPeriod } from '../core/period_model.js';
import {
    formatValue,
    formatMoney,
    formatNumber,
    formatPercent,
    calculatePercent,
    calculateDiff,
    getStatus,
    scorePercent
} from '../core/utils.js';

/**
 * Метрики, у которых карточка раскрывается (с 2026-09-04 — все 20, см. config.js).
 * Внутри — вкладки: «Сотрудники» и секции метрики с сервера (/api/dashboard-card-details).
 */
const EXPANDABLE_METRICS = [
    'revenue', 'checks', 'averageCheck', 'markupPercent',
    'draftShare', 'revenueDraft', 'markupDraft',
    'packagedShare', 'revenuePackaged', 'markupPackaged',
    'kitchenShare', 'revenueKitchen', 'markupKitchen',
    'profit', 'loyaltyWriteoffs', 'tapActivity',
    'cardChecksShare'
];

/**
 * Метрики с вкладкой «Сотрудники» — ключи строк /api/employee-metrics-breakdown.
 * У активности кранов сотрудников нет: её источник — краны, а не чеки.
 */
const EMPLOYEE_METRICS = [
    'revenue', 'checks', 'averageCheck',
    'draftShare', 'packagedShare', 'kitchenShare',
    'revenueDraft', 'revenuePackaged', 'revenueKitchen',
    'profit', 'markupPercent', 'markupDraft', 'markupPackaged', 'markupKitchen',
    'loyaltyWriteoffs',
    'cardChecksShare'
];

/**
 * Метрики, которые складываются по сотрудникам: у них в разбивке есть строка
 * «Остальные (N)» и «Итого» = сумме строк = карточке. Остальные раскрываемые
 * метрики — отношения (средний чек, наценки, доли): их складывать нельзя, и
 * «Итого» у них — итог периода с карточки, а не среднее строк.
 */
const ADDITIVE_METRICS = [
    'revenue', 'checks', 'revenueDraft', 'revenuePackaged', 'revenueKitchen',
    'profit', 'loyaltyWriteoffs'
];

/**
 * Вкладка, которая открывается первой. По умолчанию — «Сотрудники»; у доли
 * розлива — литры (просьба владельца: «топ сортов по проливам в литрах»), у
 * кранов — сами краны.
 */
const DEFAULT_TAB = { draftShare: 'draft_liters', tapActivity: 'taps' };

/** Формула вкладки «Сотрудники» — показывается текстом, как у серверных секций. */
const EMPLOYEE_FORMULA = 'Строки чеков разложены по полю «Авторизовал» (кто пробил чек); '
    + 'у складываемых метрик сумма строк равна карточке, у отношений «Итого» — итог периода';

/** Сколько сотрудников показывать строками; остальные сворачиваются в одну строку. */
const BREAKDOWN_TOP = 5;

/** Имя сотрудника приходит из iiko — экранируем перед вставкой в разметку. */
function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
}

/**
 * Каретка раскрытия для мобильных карточек и строк — внутри подписи метрики,
 * чтобы не ломать раскладку «подпись слева, точка статуса справа». Пустая
 * строка у метрик без разбивки.
 */
function mobileCaret(metric) {
    return EXPANDABLE_METRICS.includes(metric.id)
        ? '<span class="m-caret" aria-hidden="true">&#9662;</span>' : '';
}

/** Шеврон для строк-аккордеонов и заголовков групп. */
const CHEVRON_SVG = '<svg class="chevron" width="12" height="12" viewBox="0 0 24 24" fill="none"'
    + ' stroke="currentColor" stroke-width="2.5" stroke-linecap="round">'
    + '<polyline points="6 9 12 15 18 9"/></svg>';

/** Ширина шкалы: план перевыполнен — шкала всё равно полная. */
function barWidth(percent) {
    return Math.max(0, Math.min(percent, 100));
}

/**
 * Слово «план»/«бюджет» для подписей карточки: у бюджетной метрики (config.js
 * `budget: true`) план — потолок. gen = родительный падеж («97% плана»).
 */
function planWord(metric, gen = false) {
    if (metric.budget) return gen ? 'бюджета' : 'бюджет';
    return gen ? 'плана' : 'план';
}

/**
 * Атрибут title с подсказкой-формулой метрики (config.js, поле hint):
 * ' title="..."' или пустая строка, если подсказки нет. Двойные кавычки
 * экранируются, чтобы текст не разорвал атрибут.
 */
function hintAttr(metric) {
    if (typeof metric.hint !== 'string' || metric.hint === '') return '';
    return ` title="${metric.hint.replace(/"/g, '&quot;')}"`;
}

class Analytics {
    constructor() {
        this.metricsGrid = document.getElementById('metrics-grid');
        // this.statsBar = document.getElementById('stats-bar'); // Удалено: stats-bar заменён на completion-badge
        this.noPlanState = document.getElementById('no-plan-state');
        this.loadingState = document.getElementById('loading-state');

        this.initialized = false;
        this.employeeData = null;  // Кэш данных по сотрудникам (текущий бар + период)
        this.employeeTotal = null; // Итог периода из того же ответа — числа карточки
        this.cardDetails = {};     // {metricId: секции метрики} для текущего бара + периода
        this.lazySections = {};    // {sectionId: секция} — литры и краны, грузятся по клику на вкладку
        this._lazyInflight = {};   // {sectionId: промис} — ленивые секции, за которыми уже пошёл запрос
        this._detailsInflight = {}; // {metricId: промис} — секции метрики, за которыми уже пошёл запрос
        this.activeTab = {};       // {metricId: id вкладки} — выбор живёт на время сессии
        this.expandedCard = null;  // Текущая раскрытая карточка
        this.isProcessing = false; // Флаг для предотвращения множественных кликов
        this._inflightKey = null;     // Ключ выполняющегося запроса (дедупликация)
        this._inflightPromise = null; // Промис выполняющегося запроса
        this._requestSeq = 0;         // Счётчик запросов (отсечение устаревших ответов)
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        this.setupEventListeners();
        this.initialized = true;

        // Начальную загрузку инициирует main.js loadInitialData() строго после
        // analytics.init(). Здесь НЕ вызываем loadAnalytics() повторно — иначе на
        // старте уходит два идентичных /api/dashboard-analytics, которые попадают
        // на оба воркера gunicorn одновременно и оба берут один и тот же OLAP
        // (стампед, блокировка всего пула на ~17с). См. docs/lessons.md.
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Подписка на изменения состояния
        state.subscribe((event, data) => {
            if (event === 'venueChanged' || event === 'periodChanged') {
                this.loadAnalytics();
            }
        });
    }

    /**
     * Загрузить данные аналитики
     */
    async loadAnalytics() {
        if (!state.currentVenue || !state.currentPeriod) {
            console.log('[Analytics] Пропуск загрузки - нет venue или period');
            return;
        }

        // Дедупликация запросов: если идентичный запрос (бар+период) уже выполняется,
        // переиспользуем его промис, а не шлём ещё один. Защищает от двойного триггера
        // на старте и от подписки venueChanged/periodChanged, срабатывающей одновременно.
        const inflightKey = `${state.currentVenue}|${state.currentPeriod.start}|${state.currentPeriod.end}`;
        if (this._inflightKey === inflightKey && this._inflightPromise) {
            console.log('[Analytics] Запрос уже выполняется, переиспользую промис:', inflightKey);
            return this._inflightPromise;
        }

        this._inflightKey = inflightKey;
        this._inflightPromise = this._loadAnalyticsImpl();
        try {
            return await this._inflightPromise;
        } finally {
            if (this._inflightKey === inflightKey) {
                this._inflightKey = null;
                this._inflightPromise = null;
            }
        }
    }

    async _loadAnalyticsImpl() {
        this.resetEmployeeData();  // Сбрасываем кэш сотрудников при смене бара/периода
        console.log('[Analytics] loadAnalytics вызван. state.currentPeriod:', state.currentPeriod);

        // Номер запроса: ответ более раннего запроса, пришедший позже, игнорируется.
        // Без этого листание стрелками рисует на экране период, который уже не выбран
        // (быстрый ответ из кэша обгоняет медленный холодный OLAP).
        const seq = ++this._requestSeq;
        const isStale = () => seq !== this._requestSeq;

        this.showLoading();

        try {
            // Используем новый endpoint для расчёта плана на произвольный период
            // Он берёт месячные планы и пропорционально делит на выбранный период
            const startDate = state.currentPeriod.start;
            const endDate = state.currentPeriod.end;

            console.log('[Analytics] Загрузка данных для периода:', startDate, '-', endDate);

            // Загружаем план и факт параллельно, но обрабатываем ошибки отдельно
            const [planResult, actualResult] = await Promise.allSettled([
                calculatePlan(state.currentVenue, startDate, endDate),
                getAnalytics(
                    state.currentVenue,
                    startDate,
                    endDate
                )
            ]);

            // Пока ждали ответ, пользователь пролистал дальше — рисовать нельзя.
            if (isStale()) {
                console.log('[Analytics] Ответ устарел, период уже другой — пропускаем');
                return;
            }

            // Извлекаем план (может быть null если не найден)
            const plan = planResult.status === 'fulfilled' ? planResult.value : null;

            // Проверяем что факт загрузился успешно
            if (actualResult.status === 'rejected') {
                throw new Error('Не удалось загрузить фактические данные: ' + actualResult.reason);
            }

            const actual = actualResult.value;

            // DEBUG: Логируем полученные данные
            console.log('[Analytics] План загружен:', plan);
            console.log('[Analytics] Факт загружен:', actual);

            state.setPlan(plan);
            state.setActual(actual);

            // Отображаем данные
            // Всегда показываем факт, план опционален
            this.displayComparison(plan, actual);

            // Отправляем событие для модуля метрик выручки
            document.dispatchEvent(new CustomEvent('dashboard:dataLoaded', {
                detail: {
                    bar: state.currentVenue,
                    dateFrom: state.currentPeriod.start,
                    dateTo: state.currentPeriod.end
                }
            }));

            // Предыдущий период — вторым запросом, НЕ дожидаясь его: вторые шкалы
            // («ПР. ПЕРИОД») дорисуются в уже показанные карточки.
            this.loadPreviousPeriod(seq, isStale);

        } catch (error) {
            console.error('Ошибка загрузки аналитики:', error);
            // Ошибку устаревшего запроса пользователю не показываем: он уже смотрит
            // другой период, и всплывающая ошибка относилась бы не к нему.
            if (!isStale()) {
                state.addMessage('error', 'Не удалось загрузить данные аналитики');
                this.hideLoading();
            }
        }
    }

    /**
     * Свести план и факт в плоский список показателей для отрисовки.
     * Один расчёт на оба экрана (десктоп и мобильный), чтобы цифры не разъезжались.
     */
    buildStats(plan, actual) {
        return METRICS.map(metric => {
            let planValue = plan ? plan[metric.planKey] : null;
            const actualValue = actual ? actual[metric.actualKey] : null;

            // Для активности кранов план всегда 100% (если не задан вручную)
            if (metric.id === 'tapActivity' && !planValue) {
                planValue = 100;
            }

            const hasPlan = planValue !== null && planValue !== undefined && planValue !== 0;
            const percent = hasPlan ? calculatePercent(actualValue, planValue) : 0;
            const diff = hasPlan ? calculateDiff(actualValue, planValue) : 0;
            // Бюджетная метрика: план — потолок. score — процент «в сторону
            // хорошего» для светофора и средних, good — знак отклонения
            // «хорошо/плохо» (перерасход бюджета — плохо, недобор плана — плохо).
            const budget = metric.budget === true;

            return {
                metric,
                planValue: hasPlan ? planValue : null,
                actualValue,
                percent,
                score: hasPlan ? scorePercent(percent, budget) : 0,
                diff,
                good: budget ? diff <= 0 : diff >= 0,
                hasPlan,
                budget,
                status: hasPlan ? getStatus(percent, budget) : 'neutral'
            };
        });
    }

    /**
     * Отобразить сравнение план vs факт.
     * Рисует обе версии разметки; какую показать, решает CSS по ширине экрана
     * (.mv-desktop / .mv-mobile) — так же, как сделано на странице графика смен.
     */
    displayComparison(plan, actual) {
        this.hideLoading();
        this.hideNoPlan();
        this.showMetricsGrid();

        const stats = this.buildStats(plan, actual);
        this.currentStats = stats;

        this.metricsGrid.innerHTML = '';
        // Старые карточки удалены из DOM: раскрытой карточки больше нет.
        this.expandedCard = null;
        this.metricsGrid.appendChild(this.renderDesktop(stats));
        this.metricsGrid.appendChild(this.renderMobile(stats));

        // Среднее и «выполнено» — по score, чтобы перерасход бюджета списаний
        // не поднимал общий процент.
        const withPlan = stats.filter(s => s.hasPlan);
        const avgPercent = withPlan.length
            ? withPlan.reduce((sum, s) => sum + s.score, 0) / withPlan.length
            : 0;
        this.updateStats(stats.length, withPlan.filter(s => s.score >= 100).length, avgPercent);
    }

    // ============================================================
    // ДЕСКТОП: группы + карточки с двумя шкалами
    // ============================================================

    /**
     * Десктоп: метрики разбиты на группы, у каждой — разделитель с названием.
     * Плашек-заголовков и точек-индикаторов больше нет: статус несёт цветной
     * процент выполнения (макет 3b).
     */
    renderDesktop(stats) {
        const root = document.createElement('div');
        root.className = 'mv-desktop';

        METRIC_GROUPS.forEach(group => {
            const groupStats = stats.filter(s => s.metric.group === group.id);
            if (groupStats.length === 0) return;

            const section = document.createElement('section');
            section.className = 'metric-group';
            // Заголовок группы — только название и линия (макет 7a).
            // Легенда шкал стоит один раз на страницу, в строке вкладок.
            section.innerHTML = `
                <div class="mg-separator">
                    <span class="mg-title">${group.name.toUpperCase()}</span>
                    <span class="mg-line"></span>
                </div>
            `;

            const grid = document.createElement('div');
            grid.className = 'metrics-grid-row';
            groupStats.forEach(s => grid.appendChild(this.createMetricCard(s)));

            section.appendChild(grid);
            root.appendChild(section);
        });

        return root;
    }

    /**
     * Карточка метрики: название, значение, шкала «СЕЙЧАС» и шкала «ПР. ПЕРИОД»
     * одной длины (сравнение читается без чисел), внизу отклонение и план.
     *
     * Шкала предыдущего периода добавляется позже, когда догрузятся его данные
     * (см. applyPreviousPeriod) — сначала показываем текущий период, не дожидаясь
     * второго OLAP-запроса.
     */
    createMetricCard(stat) {
        const { metric, planValue, actualValue, percent, diff, good, status, hasPlan } = stat;

        const card = document.createElement('div');
        card.className = 'metric-card';
        card.setAttribute('data-metric-id', metric.id);

        const formattedActual = formatValue(actualValue, metric.format);
        // Каретка раскрытия — в строке заголовка, справа (макет 7a). Раньше она
        // висела абсолютом и налезала на подвал карточки.
        const caret = EXPANDABLE_METRICS.includes(metric.id)
            ? '<span class="mc-caret" aria-hidden="true">&#9662;</span>' : '';

        if (!hasPlan) {
            card.innerHTML = `
                <div class="mc-head">
                    <span class="metric-name"${hintAttr(metric)}>${metric.name.toUpperCase()}</span>
                    ${caret}
                </div>
                <div class="metric-value">${formattedActual}</div>
                <div class="mc-footer">
                    <span class="mc-noplan">План не задан</span>
                </div>
            `;
        } else {
            const formattedDiff = formatValue(Math.abs(diff), metric.format);
            // Процент выполнения окрашен по статусу плана, отклонение — по смыслу
            // знака (макет 7a): у обычной метрики плюс зелёный, минус красный;
            // у бюджетной наоборот — перерасход красный, экономия зелёная.
            const barTitle = metric.budget
                ? 'Использование бюджета за выбранный период'
                : 'Выполнение плана за выбранный период';
            card.innerHTML = `
                <div class="mc-head">
                    <span class="metric-name"${hintAttr(metric)}>${metric.name.toUpperCase()}</span>
                    ${caret}
                </div>
                <div class="metric-value">${formattedActual}</div>
                <div class="mc-bars">
                    <div class="mc-bar-row" title="${barTitle}">
                        <span class="mc-track"><span class="mc-fill" style="width:${barWidth(percent)}%"></span></span>
                        <span class="mc-pct ${status}">${percent.toFixed(0)}%</span>
                    </div>
                </div>
                <div class="mc-footer">
                    <span class="mc-delta ${good ? 'positive' : 'negative'}">${diff >= 0 ? '+' : '−'}${formattedDiff}</span>
                    <span class="mc-plan">${planWord(metric)} ${this.formatPlanShort(planValue, metric.format)}</span>
                </div>
            `;
        }

        this.attachCardBehaviour(card, metric);
        return card;
    }

    /**
     * Клик по карточке раскрывает её. Общий для десктопной карточки и мобильных
     * элементов (m-hero, m-compact, m-row): до 2026-09-04 мобильные рисовались без
     * обработчика, и карточки на телефоне не раскрывались. Краны до 2026-09-04
     * уводили на /taps; теперь они раскрываются, как остальные, а переход на
     * страницу кранов — ссылка внутри секции «Краны».
     */
    attachCardBehaviour(card, metric) {
        if (EXPANDABLE_METRICS.includes(metric.id)) {
            card.classList.add('expandable');
            card.addEventListener('click', (e) => {
                e.stopPropagation();
                this.handleCardClick(card, metric);
            });
        }
    }

    // ============================================================
    // ПРЕДЫДУЩИЙ ПЕРИОД (вторая шкала)
    // ============================================================

    /**
     * Догрузить предыдущий период того же размера и дорисовать вторые шкалы.
     *
     * Отдельным запросом ПОСЛЕ отрисовки текущего периода: пользователь видит
     * цифры сразу, а сравнение доезжает через секунду. Если данных нет или запрос
     * упал — вторая шкала просто не появляется, экран остаётся рабочим.
     */
    async loadPreviousPeriod(seq, isStale) {
        const period = state.currentPeriod;
        if (!period) return;

        const prev = shiftPeriod(period, -1);

        try {
            const [planResult, actualResult] = await Promise.allSettled([
                calculatePlan(state.currentVenue, prev.start, prev.end),
                getAnalytics(state.currentVenue, prev.start, prev.end)
            ]);

            if (isStale()) return;
            if (actualResult.status !== 'fulfilled' || !actualResult.value) return;

            const prevStats = this.buildStats(
                planResult.status === 'fulfilled' ? planResult.value : null,
                actualResult.value
            );
            this.applyPreviousPeriod(prevStats, prev);
        } catch (error) {
            console.warn('[Analytics] Предыдущий период не загружен:', error);
        }
    }

    /** Дорисовать шкалу предыдущего периода в уже отрисованные карточки и строки. */
    applyPreviousPeriod(prevStats, prevPeriod) {
        const title = `Предыдущий период: ${prevPeriod.label}`;

        prevStats.forEach(prevStat => {
            if (!prevStat.hasPlan) return;

            const id = prevStat.metric.id;
            const pct = prevStat.percent;

            // Десктоп: вторая шкала внутри карточки
            const bars = this.metricsGrid.querySelector(`.mv-desktop [data-metric-id="${id}"] .mc-bars`);
            if (bars && !bars.querySelector('.mc-bar-row-prev')) {
                const row = document.createElement('div');
                row.className = 'mc-bar-row mc-bar-row-prev';
                row.title = title;
                row.innerHTML = `
                    <span class="mc-track"><span class="mc-fill mc-fill-prev" style="width:${barWidth(pct)}%"></span></span>
                    <span class="mc-pct mc-pct-prev">${pct.toFixed(0)}%</span>
                `;
                bars.appendChild(row);

                // Легенда — одна на страницу (в строке вкладок). Показываем её,
                // когда вторая шкала реально появилась: без серых шкал подпись
                // «было» вводила бы в заблуждение.
                document.getElementById('tabs-legend')?.classList.remove('hidden');
            }

            // Мобильный: маленькая приписка «было N%» в строке метрики
            const mobilePrev = this.metricsGrid.querySelector(`.mv-mobile [data-metric-id="${id}"] .m-prev`);
            if (mobilePrev) {
                mobilePrev.textContent = `было ${pct.toFixed(0)}%`;
                mobilePrev.title = title;
                mobilePrev.classList.remove('hidden');
            }
        });
    }

    // ============================================================
    // МОБИЛЬНЫЙ: сводка, главное, аккордеон по направлениям
    // ============================================================

    /**
     * Мобильный экран (макет 1a): сверху один ответ на вопрос «как идёт период»,
     * ниже три главные метрики крупно, остальные 17 свёрнуты в группы.
     */
    renderMobile(stats) {
        const root = document.createElement('div');
        root.className = 'mv-mobile';

        root.appendChild(this.renderMobileSummary(stats));

        // «Главное» — метрики из HEADLINE_METRIC_IDS в порядке этого списка.
        const headline = HEADLINE_METRIC_IDS
            .map(id => stats.find(s => s.metric.id === id))
            .filter(Boolean);

        if (headline.length) {
            root.appendChild(this.sectionLabel('Главное'));
            root.appendChild(this.renderMobileHero(headline[0]));
            if (headline.length > 1) {
                const duo = document.createElement('div');
                duo.className = 'm-duo';
                headline.slice(1).forEach(s => duo.appendChild(this.renderMobileCompact(s)));
                root.appendChild(duo);
            }
        }

        // Аккордеоны — те же группы, но БЕЗ метрик из «Главного», иначе они
        // показывались бы дважды на одном экране.
        const rest = stats.filter(s => !HEADLINE_METRIC_IDS.includes(s.metric.id));
        const hasGroups = METRIC_GROUPS.some(g => rest.some(s => s.metric.group === g.id));
        if (hasGroups) root.appendChild(this.sectionLabel('Показатели'));

        METRIC_GROUPS.forEach(group => {
            const groupStats = rest.filter(s => s.metric.group === group.id);
            if (groupStats.length) root.appendChild(this.renderMobileGroup(group, groupStats));
        });

        return root;
    }

    sectionLabel(text) {
        const el = document.createElement('span');
        el.className = 'm-section-label';
        el.textContent = text.toUpperCase();
        return el;
    }

    /** Слово периода для подписи сводки: «за неделю», «за месяц», ... */
    periodWord() {
        const g = state.currentPeriod?.granularity;
        if (g === 'day') return 'за день';
        if (g === 'week') return 'за неделю';
        if (g === 'month') return 'за месяц';
        if (g === 'year') return 'за год';
        return 'за период';
    }

    /**
     * Карточка «ВЫПОЛНЕНИЕ ПЛАНА»: средний процент по метрикам с планом плюс
     * раскладка светофора — сколько метрик отстаёт, сколько близко, сколько в плане.
     * Порог «близко» — 90% (config.js THRESHOLDS).
     */
    renderMobileSummary(stats) {
        const withPlan = stats.filter(s => s.hasPlan);
        const avg = withPlan.length
            ? withPlan.reduce((sum, s) => sum + s.score, 0) / withPlan.length
            : 0;

        const counts = { danger: 0, warning: 0, success: 0 };
        withPlan.forEach(s => { counts[s.status] = (counts[s.status] || 0) + 1; });

        const period = state.currentPeriod;
        const dates = period ? `${this.shortDate(period.start)} — ${this.shortDate(period.end)}` : '';

        const el = document.createElement('div');
        el.className = 'm-summary';
        el.innerHTML = `
            <div class="m-summary-top">
                <span class="m-summary-label">Выполнение плана</span>
                <span class="m-summary-dates">${dates}</span>
            </div>
            <div class="m-summary-value">
                <span class="m-summary-pct">${avg.toFixed(1)}%</span>
                <span class="m-summary-word">${this.periodWord()}</span>
            </div>
            <div class="m-track"><span class="m-fill" style="width:${barWidth(avg)}%"></span></div>
            <div class="m-legend">
                <span class="m-legend-item"><span class="m-dot danger"></span>${counts.danger} отстают</span>
                <span class="m-legend-item"><span class="m-dot warning"></span>${counts.warning} близко</span>
                <span class="m-legend-item"><span class="m-dot success"></span>${counts.success} в плане</span>
            </div>
        `;
        return el;
    }

    /** 'YYYY-MM-DD' -> 'DD.MM' для компактных мобильных подписей. */
    shortDate(iso) {
        if (!iso) return '';
        const [, m, d] = iso.split('-');
        return `${d}.${m}`;
    }

    /** Крупная карточка главной метрики (выручка). */
    renderMobileHero(stat) {
        const { metric, planValue, actualValue, percent, diff, status, hasPlan } = stat;

        const el = document.createElement('div');
        el.className = 'm-hero';
        el.setAttribute('data-metric-id', metric.id);
        el.innerHTML = `
            <div class="m-card-top">
                <span class="m-card-label"${hintAttr(metric)}>${metric.name.toUpperCase()}${mobileCaret(metric)}</span>
                <span class="m-dot ${status}"></span>
            </div>
            <div class="m-hero-row">
                <span class="m-hero-value">${formatValue(actualValue, metric.format)}</span>
                ${hasPlan
                    ? `<span class="m-delta">${diff >= 0 ? '+' : '−'}${formatValue(Math.abs(diff), metric.format)}</span>`
                    : ''}
            </div>
            ${hasPlan ? `
                <div class="m-track"><span class="m-fill" style="width:${barWidth(percent)}%"></span></div>
                <div class="m-card-foot">
                    <span class="m-pct">${percent.toFixed(0)}% ${planWord(metric, true)}</span>
                    <span class="m-prev hidden"></span>
                    <span class="m-plan">${planWord(metric)} ${this.formatPlanShort(planValue, metric.format)}</span>
                </div>
            ` : '<div class="m-card-foot"><span class="m-plan">План не задан</span></div>'}
        `;
        this.attachCardBehaviour(el, metric);
        return el;
    }

    /** Компактная карточка главной метрики (чеки, средний чек) — в паре. */
    renderMobileCompact(stat) {
        const { metric, planValue, actualValue, percent, status, hasPlan } = stat;

        const el = document.createElement('div');
        el.className = 'm-compact';
        el.setAttribute('data-metric-id', metric.id);
        el.innerHTML = `
            <div class="m-card-top">
                <span class="m-card-label"${hintAttr(metric)}>${metric.name.toUpperCase()}${mobileCaret(metric)}</span>
                <span class="m-dot ${status}"></span>
            </div>
            <div class="m-compact-value">${formatValue(actualValue, metric.format)}</div>
            ${hasPlan ? `
                <div class="m-track"><span class="m-fill" style="width:${barWidth(percent)}%"></span></div>
                <div class="m-card-foot">
                    <span class="m-pct">${percent.toFixed(0)}%</span>
                    <span class="m-plan">из ${this.formatPlanShort(planValue, metric.format)}</span>
                </div>
            ` : '<div class="m-card-foot"><span class="m-plan">План не задан</span></div>'}
        `;
        this.attachCardBehaviour(el, metric);
        return el;
    }

    /**
     * Свёрнутая группа: строка с названием, числом метрик и общим процентом.
     * Общий процент группы — среднее по метрикам группы, у которых есть план.
     */
    renderMobileGroup(group, groupStats) {
        const withPlan = groupStats.filter(s => s.hasPlan);
        const avg = withPlan.length
            ? withPlan.reduce((sum, s) => sum + s.score, 0) / withPlan.length
            : 0;
        const status = withPlan.length ? getStatus(avg) : 'neutral';

        const el = document.createElement('div');
        el.className = 'm-group';
        el.setAttribute('data-group-id', group.id);

        const head = document.createElement('button');
        head.type = 'button';
        head.className = 'm-group-head';
        head.setAttribute('aria-expanded', 'false');
        head.innerHTML = `
            <span class="m-group-name">${group.name.toUpperCase()}</span>
            <span class="m-group-count">${groupStats.length} ${this.pluralMetrics(groupStats.length)}</span>
            <span class="m-group-pct ${status}">${withPlan.length ? avg.toFixed(0) + '%' : '—'}</span>
            ${CHEVRON_SVG}
        `;

        const body = document.createElement('div');
        body.className = 'm-group-body hidden';
        groupStats.forEach(s => body.appendChild(this.renderMobileRow(s)));

        head.addEventListener('click', () => {
            const open = el.classList.toggle('open');
            body.classList.toggle('hidden', !open);
            head.setAttribute('aria-expanded', open ? 'true' : 'false');
        });

        el.appendChild(head);
        el.appendChild(body);
        return el;
    }

    /** Склонение слова «метрика» по числу. */
    pluralMetrics(n) {
        const last = n % 10;
        if (n % 100 > 10 && n % 100 < 20) return 'метрик';
        if (last === 1) return 'метрика';
        if (last >= 2 && last <= 4) return 'метрики';
        return 'метрик';
    }

    /** Строка метрики внутри раскрытой мобильной группы. */
    renderMobileRow(stat) {
        const { metric, planValue, actualValue, percent, status, hasPlan } = stat;

        const el = document.createElement('div');
        el.className = 'm-row';
        el.setAttribute('data-metric-id', metric.id);
        el.innerHTML = `
            <div class="m-row-top">
                <span class="m-row-name"${hintAttr(metric)}>${metric.name.toUpperCase()}${mobileCaret(metric)}</span>
                <span class="m-row-value">${formatValue(actualValue, metric.format)}</span>
            </div>
            ${hasPlan ? `
                <div class="m-track"><span class="m-fill" style="width:${barWidth(percent)}%"></span></div>
                <div class="m-card-foot">
                    <span class="m-pct ${status}">${percent.toFixed(0)}%</span>
                    <span class="m-prev hidden"></span>
                    <span class="m-plan">${planWord(metric)} ${this.formatPlanShort(planValue, metric.format)}</span>
                </div>
            ` : '<div class="m-card-foot"><span class="m-plan">План не задан</span></div>'}
        `;
        this.attachCardBehaviour(el, metric);
        return el;
    }

    /**
     * Форматировать план в сокращенном виде (252 077 → 252К)
     */
    formatPlanShort(value, format) {
        if (value === null || value === undefined) return '—';

        if (format === 'money') {
            return formatMoney(value);
        } else if (format === 'number') {
            return formatNumber(value);
        } else if (format === 'percent') {
            return value.toFixed(0) + '%';
        }

        return value.toString();
    }

    /**
     * Обновить статистику
     */
    updateStats(total, completed, avgPercent) {
        // Обновляем только процент выполнения в tabs-nav
        const completionElement = document.getElementById('stat-avg-completion');
        if (completionElement) {
            completionElement.textContent = avgPercent.toFixed(1) + '%';
        }

        // Показываем completion badge
        const completionBadge = document.getElementById('completion-badge');
        if (completionBadge) {
            completionBadge.style.display = 'flex';
        }
    }

    /**
     * Отобразить состояние "нет плана"
     */
    displayNoPlan() {
        this.hideLoading();
        this.hideMetricsGrid();
        this.noPlanState?.classList.remove('hidden');
    }

    /**
     * Показать загрузку
     */
    showLoading() {
        this.loadingState?.classList.remove('hidden');
        this.hideMetricsGrid();
        this.hideNoPlan();
    }

    /**
     * Скрыть загрузку
     */
    hideLoading() {
        this.loadingState?.classList.add('hidden');
    }

    /**
     * Показать сетку метрик
     */
    showMetricsGrid() {
        this.metricsGrid?.classList.remove('hidden');
    }

    /**
     * Скрыть сетку метрик
     */
    hideMetricsGrid() {
        this.metricsGrid?.classList.add('hidden');
    }

    /**
     * Скрыть состояние "нет плана"
     */
    hideNoPlan() {
        this.noPlanState?.classList.add('hidden');
    }

    /** Ключ «бар + период», под который загружены данные по сотрудникам. */
    employeeDataKey() {
        const period = state.currentPeriod || {};
        return `${state.currentVenue}|${period.start}|${period.end}`;
    }

    /**
     * Забыть данные раскрытия (сотрудники, секции метрик, ленивые секции):
     * следующий клик по карточке загрузит их заново. Вызывается при смене бара
     * или периода и при обновлении.
     */
    resetEmployeeData() {
        this.employeeData = null;
        this.employeeTotal = null;
        this.cardDetails = {};
        this.lazySections = {};
        this._lazyInflight = {};
        this._detailsInflight = {};
    }

    /**
     * Загрузить данные по сотрудникам для раскрытия карточек.
     *
     * Ответ принимается, только если бар и период не изменились, пока он шёл:
     * без этой проверки быстрое листание стрелкой оставляло в кэше людей
     * прошлого периода, и они показывались под карточкой нового (карточки
     * рисуются из серверного кэша за доли секунды, разбивка идёт дольше).
     * При ошибке кэш остаётся пустым, чтобы следующий клик повторил запрос.
     */
    async loadEmployeeData() {
        if (!state.currentVenue || !state.currentPeriod) return;

        const requestKey = this.employeeDataKey();
        try {
            const data = await getEmployeeBreakdown(
                state.currentVenue,
                state.currentPeriod.start,
                state.currentPeriod.end
            );
            if (this.employeeDataKey() !== requestKey) {
                console.log('[Analytics] Ответ по сотрудникам устарел, период уже другой — пропускаем');
                return;
            }
            this.employeeData = data.employees || [];
            this.employeeTotal = data.total || null;
            console.log('[Analytics] Employee data loaded:', this.employeeData.length, 'employees');
        } catch (error) {
            console.error('[Analytics] Failed to load employee data:', error);
            if (this.employeeDataKey() === requestKey) {
                this.resetEmployeeData();
                state.addMessage('error', 'Не удалось загрузить разбивку по сотрудникам');
            }
        }
    }

    /**
     * Обработчик клика по карточке — раскрытие/закрытие
     */
    async handleCardClick(card, metric) {
        // Защита от множественных кликов
        if (this.isProcessing) return;

        if (!EXPANDABLE_METRICS.includes(metric.id)) return;

        // Если эта карточка уже раскрыта — закрываем
        if (this.expandedCard === card) {
            this.collapseCard(card);
            return;
        }

        // Устанавливаем флаг обработки
        this.isProcessing = true;

        try {
            // Закрываем предыдущую раскрытую карточку
            if (this.expandedCard) {
                this.collapseCard(this.expandedCard);
            }

            // Сотрудники грузятся один раз на бар + период; у кранов этой вкладки нет.
            if (EMPLOYEE_METRICS.includes(metric.id)) {
                if (!this.employeeData) {
                    card.classList.add('loading');
                    await this.loadEmployeeData();
                    card.classList.remove('loading');
                }

                // Ошибка загрузки или период сменился, пока ждали — раскрывать нечего.
                if (!this.employeeData) return;
            }

            // Пока ждали, сетка могла перерисоваться (листание туда-обратно):
            // раскрывать отсоединённый узел бессмысленно.
            if (!card.isConnected) return;

            // Раскрываем карточку; секции метрики догружаются в неё
            this.expandCard(card, metric);
        } finally {
            // Снимаем флаг после небольшой задержки
            setTimeout(() => {
                this.isProcessing = false;
            }, 300);
        }
    }

    /**
     * Раскрыть карточку: вкладки «Сотрудники» и секции метрики.
     *
     * Сотрудники рисуются сразу из клиентского кэша (пустой список периода без
     * продаж даёт «Нет данных», клик не игнорируется), секции метрики
     * догружаются в уже раскрытую карточку (loadCardDetails). Клики внутри
     * раскрытия не всплывают на карточку: обработчик раскрытия висит на ней
     * самой, и вкладка или ссылка иначе схлопывали бы её.
     */
    expandCard(card, metric) {
        this.expandedCard = card;
        card.classList.add('expanded');

        const breakdown = document.createElement('div');
        breakdown.className = 'metric-breakdown';
        breakdown.innerHTML = `
            <div class="breakdown-header">
                <span class="breakdown-heading">По сотрудникам</span>
                <span class="breakdown-close" onclick="event.stopPropagation()">✕</span>
            </div>
            <div class="breakdown-tabs hidden" role="tablist"></div>
            <div class="breakdown-formula hidden"></div>
            <div class="breakdown-list"></div>
            <div class="breakdown-note hidden"></div>
        `;
        breakdown.addEventListener('click', (e) => e.stopPropagation());
        breakdown.querySelector('.breakdown-close').addEventListener('click', (e) => {
            e.stopPropagation();
            this.collapseCard(card);
        });
        card.appendChild(breakdown);

        this.renderTabs(card, metric);
        this.showTab(card, metric, this.currentTab(metric));
        this.loadCardDetails(card, metric);
    }

    /**
     * Закрыть раскрытую карточку
     */
    collapseCard(card) {
        card.classList.remove('expanded');
        const breakdown = card.querySelector('.metric-breakdown');
        if (breakdown) {
            breakdown.remove();
        }
        if (this.expandedCard === card) {
            this.expandedCard = null;
        }
    }

    /**
     * Отрисовать список сотрудников для метрики.
     *
     * Топ BREAKDOWN_TOP по значению метрики, затем:
     * - складываемые метрики: строка «Остальные (N)» = итог минус показанные и
     *   строка «Итого» = итог периода. Строки сходятся с «Итого» по построению,
     *   а «Итого» равно карточке — оно приходит с сервера из того же ответа iiko;
     * - отношения (средний чек, наценки, доли): у каждого сотрудника личное
     *   значение и число его чеков, внизу «Итого» периода с подсказкой, что это
     *   не среднее строк.
     * Ключи в данных сотрудника совпадают с id метрик (routes/employee.py, _breakdown_row).
     */
    renderEmployeeList(metric) {
        const key = metric.id;
        if (!EMPLOYEE_METRICS.includes(key)) return '<div class="breakdown-empty">Нет данных</div>';

        const employees = this.employeeData || [];
        const sorted = [...employees].sort((a, b) => (b[key] || 0) - (a[key] || 0));
        const top = sorted.slice(0, BREAKDOWN_TOP);
        if (top.length === 0) {
            return '<div class="breakdown-empty">Нет данных</div>';
        }

        const additive = ADDITIVE_METRICS.includes(key);
        const total = this.employeeTotal;

        const rows = top.map((emp, i) => {
            // У отношений рядом с именем — число чеков: видно, что высокая наценка
            // при одном чеке ничего не значит.
            const sub = additive
                ? ''
                : `<span class="breakdown-sub">${formatNumber(emp.checks || 0)} чек.</span>`;
            return `
                <div class="breakdown-item">
                    <span class="breakdown-rank">${i + 1}</span>
                    <span class="breakdown-name">${escapeHtml(emp.name)}${sub}</span>
                    <span class="breakdown-value">${formatValue(emp[key] || 0, metric.format)}</span>
                </div>
            `;
        });

        if (additive) {
            const shownSum = top.reduce((acc, emp) => acc + (emp[key] || 0), 0);
            const totalValue = total
                ? (total[key] || 0)
                : sorted.reduce((acc, emp) => acc + (emp[key] || 0), 0);
            // «Остальные» = итог минус показанные, а не сумма скрытых: так строки
            // сходятся с «Итого» и тогда, когда часть выручки ни к кому не привязана.
            const rest = totalValue - shownSum;
            const hidden = sorted.length - top.length;
            // Каждая строка округлена сервером до целого, поэтому без скрытых
            // сотрудников остаток в пределах «единица на строку» — это округление.
            const roundingDrift = top.length;
            if (hidden > 0 || Math.abs(rest) > roundingDrift) {
                const label = hidden > 0 ? `Остальные (${hidden})` : 'Без сотрудника';
                rows.push(`
                    <div class="breakdown-item breakdown-rest">
                        <span class="breakdown-rank">+</span>
                        <span class="breakdown-name">${label}</span>
                        <span class="breakdown-value">${formatValue(rest, metric.format)}</span>
                    </div>
                `);
            }
            rows.push(this.renderBreakdownTotal(totalValue, metric, 'Сумма строк выше. Равна значению карточки'));
        } else if (total) {
            rows.push(this.renderBreakdownTotal(total[key] || 0, metric,
                'Итог по всем чекам периода, как на карточке. Это не среднее строк выше: '
                + 'каждый сотрудник входит с весом своей выручки'));
        }

        return rows.join('');
    }

    /** Строка «Итого» разбивки; hint — подсказка в title, name — подпись строки. */
    renderBreakdownTotal(value, metric, hint, name = 'Итого') {
        return `
            <div class="breakdown-item breakdown-total" title="${escapeHtml(hint || '')}">
                <span class="breakdown-rank">=</span>
                <span class="breakdown-name">${escapeHtml(name)}</span>
                <span class="breakdown-value">${formatValue(value, metric.format)}</span>
            </div>
        `;
    }

    // ============================================================
    // ДЕТАЛИ КАРТОЧКИ: вкладки-секции (2026-09-04)
    // ============================================================

    /** Вкладки раскрытой карточки: «Сотрудники» (если есть) и секции метрики с сервера. */
    tabsFor(metric) {
        const tabs = [];
        if (EMPLOYEE_METRICS.includes(metric.id)) {
            tabs.push({ id: 'employees', title: 'Сотрудники' });
        }
        const sections = this.cardDetails[metric.id];
        if (Array.isArray(sections)) {
            sections.forEach(s => tabs.push({ id: s.id, title: s.title || s.id }));
        }
        return tabs;
    }

    /** Вкладка по умолчанию: из DEFAULT_TAB, если она уже есть, иначе первая. */
    defaultTab(metric) {
        const tabs = this.tabsFor(metric);
        const preferred = DEFAULT_TAB[metric.id];
        if (preferred && tabs.some(t => t.id === preferred)) return preferred;
        return tabs.length ? tabs[0].id : null;
    }

    /**
     * Выбранная вкладка метрики (живёт на сессию) или вкладка по умолчанию.
     * Пока секции не пришли, карточка с вкладкой по умолчанию (литры, краны)
     * показывает «Загрузка…» (null), а не сотрудников, которых тут же заменят.
     */
    currentTab(metric) {
        const chosen = this.activeTab[metric.id];
        if (chosen && this.tabsFor(metric).some(t => t.id === chosen)) return chosen;
        if (DEFAULT_TAB[metric.id] && this.cardDetails[metric.id] === undefined) return null;
        return this.defaultTab(metric);
    }

    /** Секция метрики по id из ответа /api/dashboard-card-details. */
    findSection(metric, sectionId) {
        const sections = this.cardDetails[metric.id];
        if (!Array.isArray(sections)) return null;
        return sections.find(s => s.id === sectionId) || null;
    }

    /**
     * Полоса вкладок. Клик по вкладке останавливает всплытие: обработчик
     * раскрытия висит на самой карточке, и иначе первый клик схлопнул бы её.
     * Полоса скрыта, пока вкладка одна.
     */
    renderTabs(card, metric) {
        const tabsEl = card.querySelector('.breakdown-tabs');
        if (!tabsEl) return;
        const tabs = this.tabsFor(metric);
        const active = this.currentTab(metric);
        const scrollLeft = tabsEl.scrollLeft;
        tabsEl.innerHTML = tabs.map(t => `
            <button type="button" class="breakdown-tab${t.id === active ? ' active' : ''}"
                    role="tab" aria-selected="${t.id === active}"
                    data-section="${escapeHtml(t.id)}">${escapeHtml(t.title)}</button>
        `).join('');
        tabsEl.classList.toggle('hidden', tabs.length < 2);
        tabsEl.querySelectorAll('.breakdown-tab').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.switchTab(card, metric, btn.dataset.section);
            });
        });
        tabsEl.scrollLeft = scrollLeft;
    }

    /** Переключить активный чип без пересборки полосы: прокрутка и фокус остаются. */
    markActiveTab(card, sectionId) {
        card.querySelectorAll('.breakdown-tab').forEach(btn => {
            const active = btn.dataset.section === sectionId;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
    }

    switchTab(card, metric, sectionId) {
        this.activeTab[metric.id] = sectionId;
        this.markActiveTab(card, sectionId);
        this.showTab(card, metric, sectionId);
    }

    /** Показать вкладку: заголовок, формула, список и заметка секции. */
    showTab(card, metric, sectionId) {
        const heading = card.querySelector('.breakdown-heading');
        const formulaEl = card.querySelector('.breakdown-formula');
        const list = card.querySelector('.breakdown-list');
        const noteEl = card.querySelector('.breakdown-note');
        if (!heading || !list) return;
        const setFormula = (text) => {
            formulaEl.textContent = text || '';
            formulaEl.classList.toggle('hidden', !text);
        };
        const setNote = (html) => {
            noteEl.innerHTML = html || '';
            noteEl.classList.toggle('hidden', !html);
        };

        if (sectionId === 'employees') {
            heading.textContent = 'По сотрудникам';
            setFormula(EMPLOYEE_FORMULA);
            list.innerHTML = this.renderEmployeeList(metric);
            // Секции метрики не загрузились — сказать об этом здесь, иначе
            // пользователь и не узнает, что вкладки «Дни/Бары/...» существуют.
            const details = this.cardDetails[metric.id];
            setNote(details && details.error
                ? 'Детали карточки не загрузились. Закройте и раскройте карточку заново'
                : '');
            return;
        }

        const section = sectionId ? this.findSection(metric, sectionId) : null;
        if (!section) {
            const details = this.cardDetails[metric.id];
            heading.textContent = 'Детали';
            setFormula('');
            list.innerHTML = details && details.error
                ? '<div class="breakdown-empty">Не удалось загрузить детали</div>'
                : '<div class="breakdown-loading">Загрузка…</div>';
            setNote('');
            return;
        }

        if (section.lazy) {
            const loaded = this.lazySections[section.id];
            if (loaded) {
                this.renderSectionInto(card, loaded);
                return;
            }
            heading.textContent = section.title;
            setFormula('');
            list.innerHTML = '<div class="breakdown-loading">Загрузка…</div>';
            setNote('');
            this.loadLazySection(card, metric, section);
            return;
        }

        this.renderSectionInto(card, section);
    }

    /** Заголовок, формула, строки и заметка секции — в разметку раскрытия. */
    renderSectionInto(card, section) {
        const heading = card.querySelector('.breakdown-heading');
        const formulaEl = card.querySelector('.breakdown-formula');
        const list = card.querySelector('.breakdown-list');
        const noteEl = card.querySelector('.breakdown-note');
        heading.textContent = section.heading || section.title || 'Детали';
        formulaEl.textContent = section.formula || '';
        formulaEl.classList.toggle('hidden', !section.formula);
        list.innerHTML = this.renderSection(section);
        const parts = [];
        if (section.note) parts.push(escapeHtml(section.note));
        if (section.link && section.link.href) {
            parts.push(`<a class="breakdown-link" href="${escapeHtml(section.link.href)}">`
                + `${escapeHtml(section.link.label || section.link.href)}</a>`);
        }
        noteEl.innerHTML = parts.join(' · ');
        noteEl.classList.toggle('hidden', parts.length === 0);
    }

    /**
     * Строки секции: та же разметка, что у сотрудников (ранг, имя, значение);
     * доля и подпись — в .breakdown-sub; затем «Остальные» и «Итого», которые
     * сервер посчитал из того же ответа, что и карточка.
     */
    renderSection(section) {
        if (section.error) return `<div class="breakdown-empty">${escapeHtml(section.error)}</div>`;
        const rows = section.rows || [];
        if (rows.length === 0) return '<div class="breakdown-empty">Нет данных</div>';
        const fmt = section.format || 'number';
        const out = rows.map((row, i) => this.renderSectionRow(row, i + 1, fmt, ''));
        if (section.rest) out.push(this.renderSectionRow(section.rest, '+', fmt, 'breakdown-rest'));
        if (section.total) {
            out.push(this.renderBreakdownTotal(section.total.value, { format: fmt },
                section.total.hint || '', section.total.name || 'Итого'));
        }
        return out.join('');
    }

    renderSectionRow(row, rank, fmt, extraClass) {
        const subParts = [];
        if (row.share !== undefined && row.share !== null) subParts.push(formatPercent(row.share));
        if (row.sub) subParts.push(row.sub);
        const sub = subParts.length
            ? `<span class="breakdown-sub">${escapeHtml(subParts.join(' · '))}</span>` : '';
        return `
            <div class="breakdown-item ${extraClass}">
                <span class="breakdown-rank">${rank}</span>
                <span class="breakdown-name">${escapeHtml(row.name)}${sub}</span>
                <span class="breakdown-value">${formatValue(row.value, fmt)}</span>
            </div>
        `;
    }

    /**
     * Догрузить секции метрики в уже раскрытую карточку. Один запрос на метрику:
     * повторное раскрытие, пока ответ идёт, ждёт тот же промис (иначе щёлканье по
     * карточке на холодном кэше слало дубликаты на второй воркер — стампед из
     * lessons.md). Ответ принимается, только если бар и период не сменились, а
     * рисуется, только если раскрыта всё ещё эта карточка. Ошибка показывается
     * внутри карточки без глобального сообщения и не запоминается как данные —
     * следующее раскрытие повторит запрос.
     */
    async loadCardDetails(card, metric) {
        if (Array.isArray(this.cardDetails[metric.id])) return;
        if (!this._detailsInflight[metric.id]) {
            const requestKey = this.employeeDataKey();
            const promise = getCardDetails(
                state.currentVenue, state.currentPeriod.start, state.currentPeriod.end, metric.id
            ).then((data) => {
                if (this.employeeDataKey() === requestKey) this.cardDetails[metric.id] = data.sections || [];
            }).catch((error) => {
                console.error('[Analytics] Failed to load card details:', error);
                if (this.employeeDataKey() === requestKey) this.cardDetails[metric.id] = { error: true };
            }).finally(() => {
                // Снимаем только свой маркер: после смены периода тут может лежать новый запрос.
                if (this._detailsInflight[metric.id] === promise) delete this._detailsInflight[metric.id];
            });
            this._detailsInflight[metric.id] = promise;
        }
        await this._detailsInflight[metric.id];
        if (this.expandedCard !== card) return;
        this.renderTabs(card, metric);
        this.showTab(card, metric, this.currentTab(metric));
    }

    /**
     * Ленивая секция (литры как на /draft, краны): отдельный запрос по клику
     * на вкладку. Одна секция на несколько карточек — литры у карточек розлива
     * грузятся один раз, а каждая раскрытая карточка ждёт тот же промис и
     * рисует результат у себя. Ошибка не запоминается: следующее раскрытие или
     * клик по вкладке пробует снова.
     */
    async loadLazySection(card, metric, section) {
        if (!this._lazyInflight[section.id]) {
            const promise = this.fetchLazySection(metric, section).finally(() => {
                if (this._lazyInflight[section.id] === promise) delete this._lazyInflight[section.id];
            });
            this._lazyInflight[section.id] = promise;
        }
        const failed = await this._lazyInflight[section.id];
        if (this.expandedCard !== card || this.currentTab(metric) !== section.id) return;
        if (failed) {
            this.renderSectionInto(card, { ...section, lazy: false, rows: [], error: 'Не удалось загрузить' });
            return;
        }
        this.showTab(card, metric, section.id);
    }

    /** Сам запрос ленивой секции: результат в lazySections; возвращает true при ошибке. */
    async fetchLazySection(metric, section) {
        const requestKey = this.employeeDataKey();
        try {
            const data = await getCardDetails(
                state.currentVenue, state.currentPeriod.start, state.currentPeriod.end,
                metric.id, section.id
            );
            if (this.employeeDataKey() !== requestKey) return true;
            this.lazySections[section.id] = data.section || { ...section, lazy: false, rows: [] };
            return false;
        } catch (error) {
            console.error('[Analytics] Failed to load lazy section:', error);
            return true;
        }
    }

    /**
     * Обновить данные
     */
    refresh() {
        this.resetEmployeeData();
        this.loadAnalytics();
    }
}

// Экспортируем единственный экземпляр
export const analytics = new Analytics();

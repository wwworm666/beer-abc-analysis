/**
 * Модуль аналитики
 * Загрузка и отображение данных план vs факт
 */

import { state } from '../core/state.js';
import { calculatePlan, getAnalytics, getEmployeeBreakdown } from '../core/api.js';
import { METRICS, METRIC_GROUPS, HEADLINE_METRIC_IDS } from '../core/config.js';
import { shiftPeriod } from '../core/period_model.js';
import {
    formatValue,
    formatMoney,
    formatNumber,
    calculatePercent,
    calculateDiff,
    getStatus
} from '../core/utils.js';

/** Метрики, у которых есть разбивка по сотрудникам (раскрытие карточки). */
const EXPANDABLE_METRICS = [
    'revenue', 'checks', 'averageCheck',
    'draftShare', 'packagedShare', 'kitchenShare',
    'revenueDraft', 'revenuePackaged', 'revenueKitchen',
    'profit', 'markupPercent', 'markupDraft', 'markupPackaged', 'markupKitchen',
    'loyaltyWriteoffs'
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

            return {
                metric,
                planValue: hasPlan ? planValue : null,
                actualValue,
                percent,
                diff,
                hasPlan,
                status: hasPlan ? getStatus(percent) : 'neutral'
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
        this.metricsGrid.appendChild(this.renderDesktop(stats));
        this.metricsGrid.appendChild(this.renderMobile(stats));

        const withPlan = stats.filter(s => s.hasPlan);
        const avgPercent = withPlan.length
            ? withPlan.reduce((sum, s) => sum + s.percent, 0) / withPlan.length
            : 0;
        this.updateStats(stats.length, withPlan.filter(s => s.percent >= 100).length, avgPercent);
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
        const { metric, planValue, actualValue, percent, diff, status, hasPlan } = stat;

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
            // Процент выполнения окрашен по статусу плана, отклонение — по знаку
            // (макет 7a): плюс зелёный, минус красный.
            card.innerHTML = `
                <div class="mc-head">
                    <span class="metric-name"${hintAttr(metric)}>${metric.name.toUpperCase()}</span>
                    ${caret}
                </div>
                <div class="metric-value">${formattedActual}</div>
                <div class="mc-bars">
                    <div class="mc-bar-row" title="Выполнение плана за выбранный период">
                        <span class="mc-track"><span class="mc-fill" style="width:${barWidth(percent)}%"></span></span>
                        <span class="mc-pct ${status}">${percent.toFixed(0)}%</span>
                    </div>
                </div>
                <div class="mc-footer">
                    <span class="mc-delta ${diff >= 0 ? 'positive' : 'negative'}">${diff >= 0 ? '+' : '−'}${formattedDiff}</span>
                    <span class="mc-plan">план ${this.formatPlanShort(planValue, metric.format)}</span>
                </div>
            `;
        }

        this.attachCardBehaviour(card, metric);
        return card;
    }

    /**
     * Клик по карточке: краны ведут на свою страницу, остальные раскрывают сотрудников.
     * Общий для десктопной карточки и мобильных элементов (m-hero, m-compact, m-row):
     * до 2026-09-04 мобильные рисовались без обработчика, и карточки на телефоне
     * не раскрывались.
     */
    attachCardBehaviour(card, metric) {
        if (metric.id === 'tapActivity') {
            card.classList.add('clickable');
            card.addEventListener('click', () => {
                const venueToBarMapping = {
                    'bolshoy': 'bar1',
                    'ligovskiy': 'bar2',
                    'kremenchugskaya': 'bar3',
                    'varshavskaya': 'bar4'
                };
                const barId = venueToBarMapping[state.currentVenue];
                window.location.href = barId ? `/taps/${barId}` : '/taps';
            });
            return;
        }

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
            ? withPlan.reduce((sum, s) => sum + s.percent, 0) / withPlan.length
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
                    <span class="m-pct">${percent.toFixed(0)}% плана</span>
                    <span class="m-prev hidden"></span>
                    <span class="m-plan">план ${this.formatPlanShort(planValue, metric.format)}</span>
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
            ? withPlan.reduce((sum, s) => sum + s.percent, 0) / withPlan.length
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
                    <span class="m-plan">план ${this.formatPlanShort(planValue, metric.format)}</span>
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

    /** Забыть данные по сотрудникам: следующий клик по карточке загрузит их заново. */
    resetEmployeeData() {
        this.employeeData = null;
        this.employeeTotal = null;
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

            // Загружаем данные если ещё не загружены
            if (!this.employeeData) {
                card.classList.add('loading');
                await this.loadEmployeeData();
                card.classList.remove('loading');
            }

            // Ошибка загрузки или период сменился, пока ждали — раскрывать нечего.
            if (!this.employeeData) return;

            // Раскрываем карточку
            this.expandCard(card, metric);
        } finally {
            // Снимаем флаг после небольшой задержки
            setTimeout(() => {
                this.isProcessing = false;
            }, 300);
        }
    }

    /**
     * Раскрыть карточку с данными по сотрудникам
     */
    expandCard(card, metric) {
        // Пустой список (период без продаж) раскрывается с «Нет данных»: карточка
        // не должна молча игнорировать клик.
        if (!this.employeeData) {
            return;
        }

        this.expandedCard = card;
        card.classList.add('expanded');

        // Создаём секцию с данными
        const breakdown = document.createElement('div');
        breakdown.className = 'metric-breakdown';

        // Заголовок
        breakdown.innerHTML = `
            <div class="breakdown-header">
                <span>По сотрудникам</span>
                <span class="breakdown-close" onclick="event.stopPropagation()">✕</span>
            </div>
            <div class="breakdown-list">
                ${this.renderEmployeeList(metric)}
            </div>
        `;

        // Обработчик закрытия
        breakdown.querySelector('.breakdown-close').addEventListener('click', (e) => {
            e.stopPropagation();
            this.collapseCard(card);
        });

        card.appendChild(breakdown);
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
        if (!EXPANDABLE_METRICS.includes(key)) return '<div class="breakdown-empty">Нет данных</div>';

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

    /** Строка «Итого» разбивки; hint — подсказка в title. */
    renderBreakdownTotal(value, metric, hint) {
        return `
            <div class="breakdown-item breakdown-total" title="${hint}">
                <span class="breakdown-rank">=</span>
                <span class="breakdown-name">Итого</span>
                <span class="breakdown-value">${formatValue(value, metric.format)}</span>
            </div>
        `;
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

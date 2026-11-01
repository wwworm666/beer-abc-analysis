/**
 * Сравнение периодов (вкладка «Сравнение» дашборда).
 *
 * С 2026-11-01 по стандарту периодов (docs/period-standard.md, раздел 8): период 1 — тот, что
 * выбран в шапке страницы; период 2 — «прошлый период», «тот же период год назад» или «свой»
 * (второй элемент «Период» во вкладке). Идущий период сравнивается равной длиной по
 * последний полный день: 1–29 окт против 1–29 сен. Раньше у вкладки были свои списки недель:
 * режимы выбирали будущие недели, по воскресеньям текущая неделя не находилась (дата недели
 * читалась как UTC), «Год к году» не работал.
 *
 * Числа каждого периода — те же запросы, что у «Аналитики» (/api/dashboard-analytics).
 */

import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { formatMoney, formatPercent } from '../core/utils.js';

const K = window.KPeriod;
const QUICK = ['last_closed_week', 'current_week', 'last_closed_month', 'current_month',
    'current_quarter', 'current_year'];

/**
 * «Тот же период год назад»: месяц и квартал — на 12 месяцев, год — на один, неделя, день и свой
 * период — на 52 недели (364 дня), чтобы совпали дни недели: у бара пятница — не вторник.
 */
export function yearAgo(p) {
    const s = K.fromISO(p.start);
    const e = K.fromISO(p.end);
    if (p.granularity === 'month' || p.granularity === 'quarter') {
        return K.periodFor(p.granularity, K.addMonths(s, -12));
    }
    if (p.granularity === 'year') return K.shiftPeriod(p, -1);
    if (p.granularity === 'week') return K.periodFor('week', K.addDays(s, -364));
    return K.fromBounds(K.addDays(s, -364), K.addDays(e, -364));
}

/**
 * Равная длина у идущего периода: период 1 — по последний полный день, период 2 — столько же
 * дней от своего начала. Закрытый период 1 не режется. Если в периоде 1 нет ни одного полного
 * дня (выбран сегодняшний), сравнивается как есть — с пометкой.
 * -> {p1, p2, note}
 */
export function equalLength(p1, p2) {
    const lfd = K.lastFullDay();
    const end1 = K.fromISO(p1.end);
    const start1 = K.fromISO(p1.start);
    if (end1 <= lfd) return { p1, p2, note: '' };
    if (lfd < start1) {
        return { p1, p2, note: 'В периоде 1 ещё нет полного дня — сравнение по неполным данным.' };
    }
    const days = K.daysBetweenInclusive(start1, lfd);
    const start2 = K.fromISO(p2.start);
    const end2 = K.addDays(start2, days - 1);
    const p2end = K.fromISO(p2.end);
    return {
        p1: K.fromBounds(start1, lfd),
        p2: K.fromBounds(start2, end2 < p2end ? end2 : p2end),
        note: 'Период 1 ещё идёт: сравниваем ' + days + ' ' + K.pluralDays(days) +
            ' с начала — по последний полный день.'
    };
}

class ComparisonModule {
    constructor() {
        this.initialized = false;
        this.comparisonChart = null;
        this.period1Data = null;
        this.period2Data = null;
        this.mode = 'prev';          // prev | year | custom
        this.customPicker = null;    // элемент «Период» для своего периода 2
        this.timer = null;
        this.runId = 0;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;
        this.setupEventListeners();
        state.subscribe((event, data) => {
            if (event === 'tabChanged') {
                if (data === 'tab-comparison') this.schedule();
            } else if (event === 'periodChanged' || event === 'venueChanged') {
                if (state.activeTab === 'tab-comparison') this.schedule();
                else this.renderLabels();
            }
        });
        this.renderLabels();
        if (state.activeTab === 'tab-comparison') this.schedule();
        this.initialized = true;
    }

    setupEventListeners() {
        document.querySelectorAll('.comparison-mode-tab').forEach(tab => {
            tab.addEventListener('click', () => this.switchMode(tab.dataset.mode));
        });
        document.getElementById('btn-export-comparison')?.addEventListener('click', () => {
            this.exportComparison();
        });
    }

    switchMode(mode) {
        this.mode = mode;
        document.querySelectorAll('.comparison-mode-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.mode === mode);
        });
        const mount = document.getElementById('cmp-p2-picker');
        if (mount) {
            mount.hidden = mode !== 'custom';
            if (mode === 'custom' && !this.customPicker && window.KPeriodPicker) {
                this.customPicker = window.KPeriodPicker.mount(mount, {
                    steps: ['day', 'week', 'month', 'quarter', 'year', 'custom'],
                    quick: QUICK,
                    value: K.shiftPeriod(state.currentPeriod, -1),
                    onChange: () => this.schedule()
                });
            }
        }
        this.schedule();
    }

    /** Два периода сравнения по выбору режима (до выравнивания длины). */
    periods() {
        const p1 = state.currentPeriod;
        let p2;
        if (this.mode === 'year') p2 = yearAgo(p1);
        else if (this.mode === 'custom' && this.customPicker) p2 = this.customPicker.get();
        else p2 = K.shiftPeriod(p1, -1);
        return equalLength(p1, p2);
    }

    renderLabels() {
        const { p1, p2, note } = this.periods();
        const p1el = document.getElementById('cmp-p1');
        const p2el = document.getElementById('cmp-p2');
        const noteEl = document.getElementById('cmp-note');
        if (p1el) p1el.textContent = K.periodTitle(p1);
        if (p2el) p2el.textContent = K.periodTitle(p2);
        if (noteEl) {
            noteEl.textContent = note;
            noteEl.hidden = !note;
        }
        return { p1, p2 };
    }

    // Пауза — одна загрузка на серию переключений.
    schedule() {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.runComparison(), 250);
    }

    async runComparison() {
        const { p1, p2 } = this.renderLabels();
        if (p1.start === p2.start && p1.end === p2.end) {
            state.addMessage('warning', 'Выберите разные периоды', 3000);
            return;
        }
        const run = ++this.runId;
        this.showLoading();
        try {
            const venueKey = state.currentVenue;
            const [data1, data2] = await Promise.all([
                api.getAnalytics(venueKey, p1.start, p1.end),
                api.getAnalytics(venueKey, p2.start, p2.end)
            ]);
            if (run !== this.runId) return;   // пока грузилось, выбрали другое
            this.period1Data = { key: p1.key, label: K.periodTitle(p1), ...data1 };
            this.period2Data = { key: p2.key, label: K.periodTitle(p2), ...data2 };
            this.displayMetricCards();
            this.displayTopChanges();
            this.displayDetailedTable();
            this.showResults();
        } catch (error) {
            if (run !== this.runId) return;
            console.error('[Comparison] Ошибка сравнения:', error);
            state.addMessage('error', 'Ошибка при сравнении периодов');
            this.showEmpty();
        }
    }

    /**
     * Отобразить карточки метрик
     */
    displayMetricCards() {
        const container = document.getElementById('comparison-metrics-grid');
        if (!container) return;

        const metrics = this.getMetricsConfig();

        container.innerHTML = metrics.map(metric => {
            const val1 = this.getMetricValue(this.period1Data, metric);
            const val2 = this.getMetricValue(this.period2Data, metric);
            const diff = val1 - val2;

            // Процент изменения: (val1 - val2) / val2 * 100
            const changePercent = val2 !== 0 ? ((diff / val2) * 100) : 0;

            // Процент для progress bar: val1/val2 * 100 (как в dashboard: факт/план)
            const progressPercent = val2 !== 0 ? (val1 / val2) * 100 : 0;

            // Определяем статус по проценту изменения
            let statusClass = 'neutral';
            if (Math.abs(changePercent) > 1) {
                statusClass = diff > 0 ? 'success' : 'danger';
            }

            // Progress bar: показываем отношение Period 1 к Period 2
            const progressWidth = Math.min(progressPercent, 100);

            // Форматируем разницу
            let formattedDiff;
            if (metric.key.includes('markup') || metric.key.includes('Share')) {
                // Для процентных метрик: значения приходят уже в процентах (193 = 193%)
                // Показываем разницу в п.п.
                formattedDiff = `${diff >= 0 ? '+' : ''}${Math.abs(diff).toFixed(1)} п.п.`;
            } else {
                // Для остальных: используем formatter
                formattedDiff = `${diff >= 0 ? '+' : ''}${metric.formatter(Math.abs(diff))}`;
            }

            return `
                <div class="metric-card ${statusClass}">
                    <div class="status-indicator ${statusClass}"></div>
                    <div class="metric-header">
                        <span class="metric-name">${metric.label.toUpperCase()}</span>
                    </div>
                    <div class="metric-value">${metric.formatter(val1)}</div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" style="width: ${progressWidth}%"></div>
                    </div>
                    <div class="metric-footer">
                        <span class="metric-percentage">${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(1)}%</span>
                        <span class="metric-deviation">${formattedDiff}</span>
                        <span class="metric-plan">было ${metric.formatter(val2)}</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    /**
     * Получить конфигурацию метрик
     */
    getMetricsConfig() {
        // Штучные показатели (чеки) — целое число с разделителями тысяч.
        const formatCount = (v) => Math.round(v).toLocaleString('ru-RU');
        return [
            { key: 'revenue', altKey: 'total_revenue', label: 'Выручка', formatter: formatMoney },
            { key: 'checks', altKey: 'total_checks', label: 'Чеки', formatter: formatCount },
            { key: 'averageCheck', altKey: 'avg_check', label: 'Средний чек', formatter: formatMoney },
            { key: 'draftShare', altKey: 'draft_share', label: 'Доля розлива', formatter: formatPercent },
            { key: 'packagedShare', altKey: 'bottles_share', label: 'Доля фасовки', formatter: formatPercent },
            { key: 'kitchenShare', altKey: 'kitchen_share', label: 'Доля кухни', formatter: formatPercent },
            { key: 'revenueDraft', altKey: 'draft_revenue', label: 'Выручка розлив', formatter: formatMoney },
            { key: 'revenuePackaged', altKey: 'bottles_revenue', label: 'Выручка фасовка', formatter: formatMoney },
            { key: 'revenueKitchen', altKey: 'kitchen_revenue', label: 'Выручка кухня', formatter: formatMoney },
            { key: 'markupPercent', altKey: 'avg_markup', label: '% наценки', formatter: formatPercent },
            { key: 'profit', altKey: 'total_margin', label: 'Прибыль', formatter: formatMoney },
            { key: 'markupDraft', altKey: 'draft_markup', label: 'Наценка розлив', formatter: formatPercent },
            { key: 'markupPackaged', altKey: 'bottles_markup', label: 'Наценка фасовка', formatter: formatPercent },
            { key: 'markupKitchen', altKey: 'kitchen_markup', label: 'Наценка кухня', formatter: formatPercent },
            // budget: рост списаний — минус для бизнеса, цвет изменения зеркальный
            // (как у карточки дашборда, config.js budget: true).
            { key: 'loyaltyWriteoffs', altKey: 'loyalty_points_written_off', label: 'Списания баллов', formatter: formatMoney, budget: true },
            // Лояльность (2026-09-04): чек «с картой» — непустое Delivery.CustomerCardNumber в OLAP.
            { key: 'cardChecks', altKey: 'card_checks', label: 'Чеки с картой', formatter: formatCount },
            { key: 'nocardChecks', altKey: 'nocard_checks', label: 'Чеки без карты', formatter: formatCount },
            { key: 'cardChecksShare', altKey: 'card_checks_share', label: 'Доля чеков с картой', formatter: formatPercent },
            { key: 'cardRevenue', altKey: 'card_revenue', label: 'Выручка по картам', formatter: formatMoney },
            { key: 'tapActivity', altKey: 'tap_activity', label: 'Активность кранов', formatter: formatPercent }
        ];
    }

    /**
     * Получить значение метрики с учётом альтернативных ключей
     */
    getMetricValue(data, metric) {
        return data[metric.key] || data[metric.altKey] || 0;
    }

    /**
     * Отобразить топ-3 изменения
     */
    displayTopChanges() {
        const container = document.getElementById('comparison-top-changes-list');
        if (!container) return;

        const topChanges = this.getTopChanges();

        if (topChanges.length === 0) {
            container.innerHTML = `
                <div class="comparison-top-change-item neutral">
                    <div class="comparison-top-change-metric">Нет значительных изменений</div>
                    <div class="comparison-top-change-text">
                        Все метрики находятся в пределах нормы
                    </div>
                </div>
            `;
            return;
        }

        container.innerHTML = topChanges.map(change => {
            // Цвет — по смыслу: рост хорош, кроме бюджетных метрик (списания).
            const grew = change.percentChange > 0;
            const changeClass = (change.budget ? !grew : grew) ? 'positive' : 'negative';
            const changeIcon = grew ? '↗' : '↘';

            return `
                <div class="comparison-top-change-item ${changeClass}">
                    <div class="comparison-top-change-header">
                        <div class="comparison-top-change-metric">${change.label}</div>
                        <div class="comparison-top-change-badge ${changeClass}">
                            ${changeIcon} ${Math.abs(change.percentChange).toFixed(1)}%
                        </div>
                    </div>
                    <div class="comparison-top-change-values">
                        ${change.formattedVal2} → ${change.formattedVal1}
                        <span class="comparison-top-change-diff ${changeClass}">
                            (${change.percentChange >= 0 ? '+' : ''}${change.formattedDiff})
                        </span>
                    </div>
                </div>
            `;
        }).join('');
    }

    /**
     * Получить топ-3 изменения по абсолютному отклонению
     */
    getTopChanges() {
        const metrics = this.getMetricsConfig();
        const changes = [];

        metrics.forEach(metric => {
            const val1 = this.getMetricValue(this.period1Data, metric);
            const val2 = this.getMetricValue(this.period2Data, metric);
            const diff = val1 - val2;
            const percentChange = val2 !== 0 ? ((diff / val2) * 100) : 0;

            // Пропускаем метрики с нулевыми значениями или без изменений
            if (val1 === 0 && val2 === 0) return;
            if (Math.abs(percentChange) < 0.1) return;

            changes.push({
                label: metric.label,
                budget: metric.budget === true,
                val1: val1,
                val2: val2,
                diff: diff,
                percentChange: percentChange,
                absPercentChange: Math.abs(percentChange),
                formattedVal1: metric.formatter(val1),
                formattedVal2: metric.formatter(val2),
                formattedDiff: metric.formatter(Math.abs(diff))
            });
        });

        // Сортируем по абсолютному отклонению и берём топ-3
        changes.sort((a, b) => b.absPercentChange - a.absPercentChange);
        return changes.slice(0, 3);
    }

    /**
     * Отобразить детальную таблицу
     */
    displayDetailedTable() {
        const tbody = document.getElementById('comparison-table-body');
        if (!tbody) return;

        const metrics = this.getMetricsConfig();

        tbody.innerHTML = metrics.map(metric => {
            const val1 = this.getMetricValue(this.period1Data, metric);
            const val2 = this.getMetricValue(this.period2Data, metric);
            const diff = val1 - val2;
            const diffPercent = val2 !== 0 ? ((diff / val2) * 100) : 0;

            // Семантический цвет — только в колонке Δ%; абсолютная Δ нейтральна.
            // У бюджетных метрик (списания) рост — минус, цвет зеркальный.
            const up = metric.budget ? diff < 0 : diff > 0;
            const down = metric.budget ? diff > 0 : diff < 0;
            const diffClass = up ? 'value-positive' : down ? 'value-negative' : '';
            const trendArrow = diff > 0 ? '↗' : diff < 0 ? '↘' : '→';

            // Для процентных метрик показываем разницу в п.п., для остальных - через formatter
            let formattedDiff;
            if (metric.key.includes('markup') || metric.key.includes('Share')) {
                formattedDiff = `${diff >= 0 ? '+' : ''}${Math.abs(diff).toFixed(1)} п.п.`;
            } else {
                formattedDiff = `${diff >= 0 ? '+' : ''}${metric.formatter(Math.abs(diff))}`;
            }

            return `
                <tr>
                    <td>${metric.label}</td>
                    <td>${metric.formatter(val1)}</td>
                    <td>${metric.formatter(val2)}</td>
                    <td>${formattedDiff}</td>
                    <td class="${diffClass}">
                        ${diffPercent >= 0 ? '+' : ''}${diffPercent.toFixed(1)}%
                    </td>
                    <td><span class="comparison-trend">${trendArrow}</span></td>
                </tr>
            `;
        }).join('');
    }

    /**
     * Экспорт сравнения
     */
    exportComparison() {
        console.log('[Comparison] Экспорт сравнения...');
        state.addMessage('info', 'Функция экспорта в разработке', 3000);
    }

    /**
     * Показать загрузку
     */
    showLoading() {
        document.getElementById('comparison-loading')?.classList.remove('hidden');
        document.getElementById('comparison-empty')?.classList.add('hidden');
        document.getElementById('comparison-results')?.classList.add('hidden');
    }

    /**
     * Показать пустое состояние
     */
    showEmpty() {
        document.getElementById('comparison-loading')?.classList.add('hidden');
        document.getElementById('comparison-empty')?.classList.remove('hidden');
        document.getElementById('comparison-results')?.classList.add('hidden');
    }

    /**
     * Показать результаты
     */
    showResults() {
        document.getElementById('comparison-loading')?.classList.add('hidden');
        document.getElementById('comparison-empty')?.classList.add('hidden');
        document.getElementById('comparison-results')?.classList.remove('hidden');
    }
}

// Экспортируем единственный экземпляр
export const comparisonModule = new ComparisonModule();

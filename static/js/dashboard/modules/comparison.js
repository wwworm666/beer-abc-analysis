/**
 * Comparison Module — Modern Fintech Design
 * Сравнение периодов с AI-инсайтами и продвинутой визуализацией
 */

import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { formatMoney, formatPercent } from '../core/utils.js';

class ComparisonModule {
    constructor() {
        this.initialized = false;
        this.comparisonChart = null;
        this.period1Data = null;
        this.period2Data = null;
        this.currentMode = 'week'; // week | month | year
        this.weeks = [];
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        console.log('[Comparison] Инициализация модуля сравнения...');

        this.setupEventListeners();
        this.loadWeeks();

        this.initialized = true;
        console.log('[Comparison] Модуль сравнения инициализирован');
    }

    /**
     * Загрузить список недель
     */
    async loadWeeks() {
        try {
            const weeksResponse = await api.getWeeks();
            this.weeks = weeksResponse.weeks || [];

            await this.populateSelectors();
            await this.autoSelectPeriods();

        } catch (error) {
            console.error('[Comparison] Ошибка загрузки недель:', error);
        }
    }

    /**
     * Заполнить селекторы периодов
     */
    async populateSelectors() {
        const select1 = document.getElementById('comparison-period-1');
        const select2 = document.getElementById('comparison-period-2');

        if (!select1 || !select2) return;

        const options = this.weeks.map(w =>
            `<option value="${w.key}">${w.label}</option>`
        ).join('');

        select1.innerHTML = '<option value="">Выберите период...</option>' + options;
        select2.innerHTML = '<option value="">Выберите период...</option>' + options;
    }

    /**
     * Автоматически выбрать периоды при загрузке
     */
    async autoSelectPeriods() {
        if (this.weeks.length < 2) return;

        const select1 = document.getElementById('comparison-period-1');
        const select2 = document.getElementById('comparison-period-2');

        if (!select1 || !select2) return;

        // Находим текущую неделю
        const currentWeekIndex = this.weeks.findIndex(w => {
            const today = new Date();
            const start = new Date(w.start);
            const end = new Date(w.end);
            return today >= start && today <= end;
        });

        if (currentWeekIndex >= 0) {
            // Текущая неделя в период 1
            select1.value = this.weeks[currentWeekIndex].key;

            // Предыдущая неделя в период 2 (если есть)
            if (currentWeekIndex > 0) {
                select2.value = this.weeks[currentWeekIndex - 1].key;
            }
        } else {
            // Если текущая неделя не найдена, берём последние две
            select1.value = this.weeks[0].key;
            if (this.weeks.length > 1) {
                select2.value = this.weeks[1].key;
            }
        }
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Mode tabs
        document.querySelectorAll('.comparison-mode-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchMode(e.target.dataset.mode);
            });
        });

        // Кнопка "Сравнить"
        document.getElementById('btn-compare')?.addEventListener('click', () => {
            this.runComparison();
        });

        // Селекторы периодов - автоматическое сравнение при изменении
        document.getElementById('comparison-period-1')?.addEventListener('change', () => {
            const period1 = document.getElementById('comparison-period-1')?.value;
            const period2 = document.getElementById('comparison-period-2')?.value;
            if (period1 && period2) {
                this.runComparison();
            }
        });

        document.getElementById('comparison-period-2')?.addEventListener('change', () => {
            const period1 = document.getElementById('comparison-period-1')?.value;
            const period2 = document.getElementById('comparison-period-2')?.value;
            if (period1 && period2) {
                this.runComparison();
            }
        });

        // Export button
        document.getElementById('btn-export-comparison')?.addEventListener('click', () => {
            this.exportComparison();
        });
    }

    /**
     * Переключить режим сравнения
     */
    switchMode(mode) {
        this.currentMode = mode;

        // Обновляем активный таб
        document.querySelectorAll('.comparison-mode-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.mode === mode);
        });

        // Автоматически выбираем периоды в зависимости от режима
        this.autoSelectPeriodsForMode(mode);
    }

    /**
     * Автоматически выбрать периоды для режима
     */
    async autoSelectPeriodsForMode(mode) {
        if (this.weeks.length < 2) return;

        const select1 = document.getElementById('comparison-period-1');
        const select2 = document.getElementById('comparison-period-2');

        if (!select1 || !select2) return;

        const currentWeekIndex = this.weeks.findIndex(w => {
            const today = new Date();
            const start = new Date(w.start);
            const end = new Date(w.end);
            return today >= start && today <= end;
        });

        if (currentWeekIndex < 0) return;

        select1.value = this.weeks[currentWeekIndex].key;

        let offset = 1; // week-over-week
        if (mode === 'month') offset = 4;
        if (mode === 'year') offset = 52;

        const targetIndex = currentWeekIndex + offset;
        if (targetIndex < this.weeks.length) {
            select2.value = this.weeks[targetIndex].key;
            // Автоматически запускаем сравнение
            this.runComparison();
        }
    }

    /**
     * Запустить сравнение
     */
    async runComparison() {
        const period1Key = document.getElementById('comparison-period-1')?.value;
        const period2Key = document.getElementById('comparison-period-2')?.value;

        if (!period1Key || !period2Key) {
            this.showEmpty();
            return;
        }

        if (period1Key === period2Key) {
            state.addMessage('warning', 'Выберите разные периоды', 3000);
            return;
        }

        console.log(`[Comparison] Сравнение: ${period1Key} vs ${period2Key}`);
        this.showLoading();

        try {
            const venueKey = state.currentVenue;

            const week1 = this.weeks.find(w => w.key === period1Key);
            const week2 = this.weeks.find(w => w.key === period2Key);

            if (!week1 || !week2) {
                throw new Error('Не удалось найти периоды');
            }

            // Загружаем данные для обоих периодов параллельно
            const [data1, data2] = await Promise.all([
                api.getAnalytics(venueKey, week1.start, week1.end),
                api.getAnalytics(venueKey, week2.start, week2.end)
            ]);

            this.period1Data = { key: period1Key, label: week1.label, ...data1 };
            this.period2Data = { key: period2Key, label: week2.label, ...data2 };

            // Отображаем результаты
            this.displayMetricCards();
            this.displayTopChanges();
            this.displayDetailedTable();
            this.showResults();

            state.addMessage('success', 'Сравнение завершено', 3000);

        } catch (error) {
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
        return [
            { key: 'revenue', altKey: 'total_revenue', label: 'Выручка', formatter: formatMoney },
            { key: 'checks', altKey: 'total_checks', label: 'Чеки', formatter: (v) => Math.round(v).toLocaleString('ru-RU') },
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
            { key: 'loyaltyWriteoffs', altKey: 'loyalty_points_written_off', label: 'Списания баллов', formatter: formatMoney },
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
            const changeClass = change.percentChange > 0 ? 'positive' : 'negative';
            const changeIcon = change.percentChange > 0 ? '↗' : '↘';

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

            const diffClass = diff > 0 ? 'value-positive' : diff < 0 ? 'value-negative' : '';

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
                    <td class="${diffClass}">
                        ${formattedDiff}
                    </td>
                    <td class="${diffClass}">
                        ${diffPercent >= 0 ? '+' : ''}${diffPercent.toFixed(1)}%
                    </td>
                    <td><span class="comparison-sparkline-mini">▁▃▅▇▅▃▁</span></td>
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

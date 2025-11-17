/**
 * Модуль сравнения периодов
 * Полная реализация с таблицей и графиком
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
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        console.log('[Comparison] Инициализация модуля сравнения...');

        this.setupEventListeners();

        this.initialized = true;
        console.log('[Comparison] ✅ Модуль сравнения инициализирован');
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Кнопка "Сравнить"
        document.getElementById('btn-compare')?.addEventListener('click', () => {
            this.runComparison();
        });

        // Быстрые кнопки сравнения
        document.getElementById('btn-compare-prev-week')?.addEventListener('click', () => {
            this.compareToPrevWeek();
        });

        document.getElementById('btn-compare-prev-month')?.addEventListener('click', () => {
            this.compareToPrevMonth();
        });

        document.getElementById('btn-compare-prev-year')?.addEventListener('click', () => {
            this.compareToPrevYear();
        });
    }

    /**
     * Запустить сравнение
     */
    async runComparison() {
        const period1Key = document.getElementById('comparison-period-1')?.value;
        const period2Key = document.getElementById('comparison-period-2')?.value;

        if (!period1Key || !period2Key) {
            state.addMessage('warning', 'Выберите оба периода для сравнения', 3000);
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

            // Загружаем данные для обоих периодов
            const [data1, data2] = await Promise.all([
                api.getAnalytics(venueKey, period1Key),
                api.getAnalytics(venueKey, period2Key)
            ]);

            this.period1Data = { key: period1Key, ...data1 };
            this.period2Data = { key: period2Key, ...data2 };

            // Отображаем результаты
            this.displayComparisonTable();
            this.displayKeyChanges();
            this.displayComparisonChart();
            this.showResults();

            state.addMessage('success', 'Сравнение завершено', 3000);

        } catch (error) {
            console.error('[Comparison] Ошибка сравнения:', error);
            state.addMessage('error', 'Ошибка при сравнении периодов');
            this.showNoData();
        }
    }

    /**
     * Сравнить с предыдущей неделей
     */
    async compareToPrevWeek() {
        const weeks = await api.getWeeks();
        const currentPeriod = state.currentPeriod;
        const currentIndex = weeks.weeks.findIndex(w => w.key === currentPeriod);

        if (currentIndex > 0) {
            const prevWeek = weeks.weeks[currentIndex - 1];
            document.getElementById('comparison-period-1').value = currentPeriod;
            document.getElementById('comparison-period-2').value = prevWeek.key;
            this.runComparison();
        } else {
            state.addMessage('warning', 'Нет данных за предыдущую неделю', 3000);
        }
    }

    /**
     * Сравнить с предыдущим месяцем (4 недели назад)
     */
    async compareToPrevMonth() {
        const weeks = await api.getWeeks();
        const currentPeriod = state.currentPeriod;
        const currentIndex = weeks.weeks.findIndex(w => w.key === currentPeriod);

        if (currentIndex >= 4) {
            const prevMonth = weeks.weeks[currentIndex - 4];
            document.getElementById('comparison-period-1').value = currentPeriod;
            document.getElementById('comparison-period-2').value = prevMonth.key;
            this.runComparison();
        } else {
            state.addMessage('warning', 'Нет данных за месяц назад', 3000);
        }
    }

    /**
     * Сравнить с прошлым годом (52 недели назад)
     */
    async compareToPrevYear() {
        const weeks = await api.getWeeks();
        const currentPeriod = state.currentPeriod;
        const currentIndex = weeks.weeks.findIndex(w => w.key === currentPeriod);

        if (currentIndex >= 52) {
            const prevYear = weeks.weeks[currentIndex - 52];
            document.getElementById('comparison-period-1').value = currentPeriod;
            document.getElementById('comparison-period-2').value = prevYear.key;
            this.runComparison();
        } else {
            state.addMessage('warning', 'Нет данных за прошлый год', 3000);
        }
    }

    /**
     * Отобразить таблицу сравнения
     */
    displayComparisonTable() {
        const tbody = document.getElementById('comparison-table-body');
        if (!tbody) return;

        const metrics = [
            { key: 'revenue', label: '💰 Выручка', formatter: formatMoney },
            { key: 'checks', label: '🧾 Чеки', formatter: (v) => Math.round(v) },
            { key: 'averageCheck', label: '💵 Средний чек', formatter: formatMoney },
            { key: 'draftShare', label: '🍺 Доля розлива', formatter: formatPercent },
            { key: 'packagedShare', label: '🍾 Доля фасовки', formatter: formatPercent },
            { key: 'kitchenShare', label: '🍽️ Доля кухни', formatter: formatPercent },
            { key: 'profit', label: '💹 Прибыль', formatter: formatMoney },
            { key: 'markupPercent', label: '📈 % наценки', formatter: formatPercent }
        ];

        tbody.innerHTML = '';

        metrics.forEach(metric => {
            const val1 = this.period1Data.actual?.[metric.key] || 0;
            const val2 = this.period2Data.actual?.[metric.key] || 0;
            const diff = val1 - val2;
            const diffPercent = val2 !== 0 ? ((diff / val2) * 100) : 0;

            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${metric.label}</td>
                <td>${metric.formatter(val1)}</td>
                <td>${metric.formatter(val2)}</td>
                <td class="${diff >= 0 ? 'positive' : 'negative'}">
                    ${diff >= 0 ? '+' : ''}${metric.formatter(diff)}
                </td>
                <td class="${diffPercent >= 0 ? 'positive' : 'negative'}">
                    ${diff >= 0 ? '+' : ''}${diffPercent.toFixed(1)}%
                </td>
            `;
            tbody.appendChild(row);
        });
    }

    /**
     * Отобразить ключевые изменения
     */
    displayKeyChanges() {
        const container = document.getElementById('key-changes-list');
        if (!container) return;

        const insights = this.generateInsights();
        container.innerHTML = insights.map(insight => `
            <div class="insight-item ${insight.type}">
                <span class="insight-icon">${insight.icon}</span>
                <span class="insight-text">${insight.text}</span>
            </div>
        `).join('');
    }

    /**
     * Генерация инсайтов
     */
    generateInsights() {
        const insights = [];
        const actual1 = this.period1Data.actual || {};
        const actual2 = this.period2Data.actual || {};

        // Выручка
        const revenueDiff = actual1.revenue - actual2.revenue;
        const revenuePercent = actual2.revenue !== 0 ? ((revenueDiff / actual2.revenue) * 100) : 0;
        if (Math.abs(revenuePercent) > 5) {
            insights.push({
                type: revenuePercent > 0 ? 'positive' : 'negative',
                icon: revenuePercent > 0 ? '📈' : '📉',
                text: `Выручка ${revenuePercent > 0 ? 'выросла' : 'упала'} на ${formatPercent(Math.abs(revenuePercent))}`
            });
        }

        // Средний чек
        const checkDiff = actual1.averageCheck - actual2.averageCheck;
        const checkPercent = actual2.averageCheck !== 0 ? ((checkDiff / actual2.averageCheck) * 100) : 0;
        if (Math.abs(checkPercent) > 5) {
            insights.push({
                type: checkPercent > 0 ? 'positive' : 'negative',
                icon: '💵',
                text: `Средний чек ${checkPercent > 0 ? 'вырос' : 'снизился'} на ${formatPercent(Math.abs(checkPercent))}`
            });
        }

        // Прибыль
        const profitDiff = actual1.profit - actual2.profit;
        const profitPercent = actual2.profit !== 0 ? ((profitDiff / actual2.profit) * 100) : 0;
        if (Math.abs(profitPercent) > 5) {
            insights.push({
                type: profitDiff > 0 ? 'positive' : 'negative',
                icon: '💹',
                text: `Прибыль ${profitDiff > 0 ? 'выросла' : 'упала'} на ${formatPercent(Math.abs(profitPercent))}`
            });
        }

        return insights;
    }

    /**
     * Отобразить график сравнения
     */
    displayComparisonChart() {
        const canvas = document.getElementById('comparison-chart');
        if (!canvas) return;

        if (this.comparisonChart) {
            this.comparisonChart.destroy();
        }

        const actual1 = this.period1Data.actual || {};
        const actual2 = this.period2Data.actual || {};

        const labels = ['Выручка розлив', 'Выручка фасовка', 'Выручка кухня', 'Прибыль'];

        const ctx = canvas.getContext('2d');
        this.comparisonChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Период 1',
                        data: [
                            actual1.revenueDraft || 0,
                            actual1.revenuePackaged || 0,
                            actual1.revenueKitchen || 0,
                            actual1.profit || 0
                        ],
                        backgroundColor: '#4CAF50'
                    },
                    {
                        label: 'Период 2',
                        data: [
                            actual2.revenueDraft || 0,
                            actual2.revenuePackaged || 0,
                            actual2.revenueKitchen || 0,
                            actual2.profit || 0
                        ],
                        backgroundColor: '#2196F3'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => formatMoney(value)
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                return `${context.dataset.label}: ${formatMoney(context.parsed.y)}`;
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Показать индикатор загрузки
     */
    showLoading() {
        document.getElementById('comparison-loading')?.classList.remove('hidden');
        document.getElementById('comparison-no-data')?.classList.add('hidden');
        document.getElementById('comparison-results')?.classList.add('hidden');
    }

    /**
     * Показать "Нет данных"
     */
    showNoData() {
        document.getElementById('comparison-loading')?.classList.add('hidden');
        document.getElementById('comparison-no-data')?.classList.remove('hidden');
        document.getElementById('comparison-results')?.classList.add('hidden');
    }

    /**
     * Показать результаты
     */
    showResults() {
        document.getElementById('comparison-loading')?.classList.add('hidden');
        document.getElementById('comparison-no-data')?.classList.add('hidden');
        document.getElementById('comparison-results')?.classList.remove('hidden');
    }
}

// Экспортируем единственный экземпляр
export const comparisonModule = new ComparisonModule();

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
        this.loadPeriodSelectors();

        this.initialized = true;
        console.log('[Comparison] Модуль сравнения инициализирован');
    }

    /**
     * Загрузить список периодов в селекторы
     */
    async loadPeriodSelectors() {
        try {
            const weeksResponse = await api.getWeeks();
            const weeks = weeksResponse.weeks || [];

            const select1 = document.getElementById('comparison-period-1');
            const select2 = document.getElementById('comparison-period-2');

            if (!select1 || !select2) return;

            // Заполняем селекторы
            const options = weeks.map(w => `<option value="${w.key}">${w.label}</option>`).join('');
            select1.innerHTML = '<option value="">Выберите период...</option>' + options;
            select2.innerHTML = '<option value="">Выберите период...</option>' + options;

            // Устанавливаем текущий период в первый селектор
            if (state.currentPeriod && state.currentPeriod.key) {
                select1.value = state.currentPeriod.key;
            }

        } catch (error) {
            console.error('[Comparison] Ошибка загрузки периодов:', error);
        }
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

            // Получаем недели для определения start/end
            const weeksResponse = await api.getWeeks();
            const weeks = weeksResponse.weeks || [];

            const week1 = weeks.find(w => w.key === period1Key);
            const week2 = weeks.find(w => w.key === period2Key);

            if (!week1 || !week2) {
                throw new Error('Не удалось найти периоды');
            }

            // Загружаем данные для обоих периодов
            const [data1, data2] = await Promise.all([
                api.getAnalytics(venueKey, week1.start, week1.end),
                api.getAnalytics(venueKey, week2.start, week2.end)
            ]);

            console.log('[Comparison] Данные период 1:', data1);
            console.log('[Comparison] Данные период 2:', data2);

            this.period1Data = { key: period1Key, label: week1.label, ...data1 };
            this.period2Data = { key: period2Key, label: week2.label, ...data2 };

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
        const weeksResponse = await api.getWeeks();
        const weeks = weeksResponse.weeks || [];
        const currentPeriod = state.currentPeriod;

        if (!currentPeriod || !currentPeriod.key) {
            state.addMessage('warning', 'Выберите текущий период', 3000);
            return;
        }

        const currentIndex = weeks.findIndex(w => w.key === currentPeriod.key);

        if (currentIndex > 0) {
            const prevWeek = weeks[currentIndex - 1];
            document.getElementById('comparison-period-1').value = currentPeriod.key;
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
        const weeksResponse = await api.getWeeks();
        const weeks = weeksResponse.weeks || [];
        const currentPeriod = state.currentPeriod;

        if (!currentPeriod || !currentPeriod.key) {
            state.addMessage('warning', 'Выберите текущий период', 3000);
            return;
        }

        const currentIndex = weeks.findIndex(w => w.key === currentPeriod.key);

        if (currentIndex >= 4) {
            const prevMonth = weeks[currentIndex - 4];
            document.getElementById('comparison-period-1').value = currentPeriod.key;
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
        const weeksResponse = await api.getWeeks();
        const weeks = weeksResponse.weeks || [];
        const currentPeriod = state.currentPeriod;

        if (!currentPeriod || !currentPeriod.key) {
            state.addMessage('warning', 'Выберите текущий период', 3000);
            return;
        }

        const currentIndex = weeks.findIndex(w => w.key === currentPeriod.key);

        if (currentIndex >= 52) {
            const prevYear = weeks[currentIndex - 52];
            document.getElementById('comparison-period-1').value = currentPeriod.key;
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
            { key: 'revenue', label: 'Выручка', formatter: formatMoney, altKey: 'total_revenue' },
            { key: 'checks', label: 'Чеки', formatter: (v) => Math.round(v), altKey: 'total_checks' },
            { key: 'averageCheck', label: 'Средний чек', formatter: formatMoney, altKey: 'avg_check' },
            { key: 'draftShare', label: 'Доля розлива', formatter: formatPercent, altKey: 'draft_share' },
            { key: 'packagedShare', label: 'Доля фасовки', formatter: formatPercent, altKey: 'bottles_share' },
            { key: 'kitchenShare', label: 'Доля кухни', formatter: formatPercent, altKey: 'kitchen_share' },
            { key: 'profit', label: 'Прибыль', formatter: formatMoney, altKey: 'total_margin' },
            { key: 'markupPercent', label: '% наценки', formatter: (v) => `${(v * 100).toFixed(1)}%`, altKey: 'avg_markup' }
        ];

        tbody.innerHTML = '';

        metrics.forEach(metric => {
            const val1 = this.period1Data[metric.key] || this.period1Data[metric.altKey] || 0;
            const val2 = this.period2Data[metric.key] || this.period2Data[metric.altKey] || 0;

            // Для наценки конвертируем если нужно
            let displayVal1 = val1;
            let displayVal2 = val2;
            if (metric.key === 'markupPercent' && val1 < 1 && val2 < 1) {
                displayVal1 = val1;
                displayVal2 = val2;
            }

            const diff = displayVal1 - displayVal2;
            const diffPercent = displayVal2 !== 0 ? ((diff / displayVal2) * 100) : 0;

            const row = document.createElement('tr');

            let formattedVal1, formattedVal2, formattedDiff;
            if (metric.key === 'markupPercent') {
                formattedVal1 = `${(displayVal1 * 100).toFixed(1)}%`;
                formattedVal2 = `${(displayVal2 * 100).toFixed(1)}%`;
                formattedDiff = `${(diff * 100).toFixed(1)}%`;
            } else {
                formattedVal1 = metric.formatter(displayVal1);
                formattedVal2 = metric.formatter(displayVal2);
                formattedDiff = metric.formatter(Math.abs(diff));
            }

            row.innerHTML = `
                <td>${metric.label}</td>
                <td>${formattedVal1}</td>
                <td>${formattedVal2}</td>
                <td class="${diff >= 0 ? 'positive' : 'negative'}">
                    ${diff >= 0 ? '+' : '-'}${formattedDiff}
                </td>
                <td class="${diffPercent >= 0 ? 'positive' : 'negative'}">
                    ${diffPercent >= 0 ? '+' : ''}${diffPercent.toFixed(1)}%
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

        // Выручка
        const revenue1 = this.period1Data.revenue || this.period1Data.total_revenue || 0;
        const revenue2 = this.period2Data.revenue || this.period2Data.total_revenue || 0;
        const revenueDiff = revenue1 - revenue2;
        const revenuePercent = revenue2 !== 0 ? ((revenueDiff / revenue2) * 100) : 0;

        if (Math.abs(revenuePercent) > 5) {
            insights.push({
                type: revenuePercent > 0 ? 'positive' : 'negative',
                icon: revenuePercent > 0 ? '↗' : '↘',
                text: `Выручка ${revenuePercent > 0 ? 'выросла' : 'упала'} на ${Math.abs(revenuePercent).toFixed(1)}%`
            });
        }

        // Средний чек
        const check1 = this.period1Data.averageCheck || this.period1Data.avg_check || 0;
        const check2 = this.period2Data.averageCheck || this.period2Data.avg_check || 0;
        const checkDiff = check1 - check2;
        const checkPercent = check2 !== 0 ? ((checkDiff / check2) * 100) : 0;

        if (Math.abs(checkPercent) > 5) {
            insights.push({
                type: checkPercent > 0 ? 'positive' : 'negative',
                icon: '💵',
                text: `Средний чек ${checkPercent > 0 ? 'вырос' : 'снизился'} на ${Math.abs(checkPercent).toFixed(1)}%`
            });
        }

        // Прибыль
        const profit1 = this.period1Data.profit || this.period1Data.total_margin || 0;
        const profit2 = this.period2Data.profit || this.period2Data.total_margin || 0;
        const profitDiff = profit1 - profit2;
        const profitPercent = profit2 !== 0 ? ((profitDiff / profit2) * 100) : 0;

        if (Math.abs(profitPercent) > 5) {
            insights.push({
                type: profitDiff > 0 ? 'positive' : 'negative',
                icon: '💹',
                text: `Прибыль ${profitDiff > 0 ? 'выросла' : 'упала'} на ${Math.abs(profitPercent).toFixed(1)}%`
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

        const labels = ['Выручка розлив', 'Выручка фасовка', 'Выручка кухня', 'Прибыль'];

        const ctx = canvas.getContext('2d');
        this.comparisonChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: `Период 1 (${this.period1Data.label})`,
                        data: [
                            this.period1Data.revenueDraft || this.period1Data.draft_revenue || 0,
                            this.period1Data.revenuePackaged || this.period1Data.bottles_revenue || 0,
                            this.period1Data.revenueKitchen || this.period1Data.kitchen_revenue || 0,
                            this.period1Data.profit || this.period1Data.total_margin || 0
                        ],
                        backgroundColor: '#4CAF50'
                    },
                    {
                        label: `Период 2 (${this.period2Data.label})`,
                        data: [
                            this.period2Data.revenueDraft || this.period2Data.draft_revenue || 0,
                            this.period2Data.revenuePackaged || this.period2Data.bottles_revenue || 0,
                            this.period2Data.revenueKitchen || this.period2Data.kitchen_revenue || 0,
                            this.period2Data.profit || this.period2Data.total_margin || 0
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

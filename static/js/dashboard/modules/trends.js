/**
 * Модуль трендов и прогнозирования
 * Анализ 12 недель + прогноз следующего периода
 */

import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { formatMoney } from '../core/utils.js';

class TrendsModule {
    constructor() {
        this.initialized = false;
        this.trendChart = null;
        this.historicalData = [];
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        console.log('[Trends] Инициализация модуля трендов...');

        // Подписываемся на изменения
        state.subscribe((event) => {
            if (event === 'periodChanged' || event === 'venueChanged') {
                this.loadTrendsData();
            }
        });

        this.initialized = true;
        console.log('[Trends] Модуль трендов инициализирован');
    }

    /**
     * Загрузить данные для анализа трендов
     */
    async loadTrendsData() {
        const currentTab = document.querySelector('.tab-button[data-tab="tab-charts"]');
        if (!currentTab || !currentTab.classList.contains('active')) {
            return;
        }

        console.log('[Trends] Загрузка данных для анализа трендов...');
        this.showLoading();

        try {
            const venueKey = state.currentVenue;
            const periodKey = state.currentPeriod;

            if (!periodKey) {
                this.showNoData();
                return;
            }

            // Получаем 12 недель данных
            const historicalData = await this.load12WeeksData(venueKey, periodKey);

            if (historicalData.length === 0) {
                this.showNoData();
                return;
            }

            this.historicalData = historicalData;

            // Рассчитываем статистику и прогноз
            const statistics = this.calculateStatistics(historicalData);
            const forecast = this.calculateForecast(historicalData);

            // Отображаем результаты
            this.displayStatistics(statistics);
            this.displayForecast(forecast);
            this.displayTrendChart(historicalData, forecast);
            this.displayWeeksTable(historicalData);
            this.showResults();

            console.log('[Trends] Анализ трендов завершен');

        } catch (error) {
            console.error('[Trends] Ошибка загрузки данных:', error);
            state.addMessage('error', 'Ошибка при анализе трендов');
            this.showNoData();
        }
    }

    /**
     * Загрузить данные за 12 недель
     */
    async load12WeeksData(venueKey, currentPeriodKey) {
        const weeksResponse = await api.getWeeks();
        const weeks = weeksResponse.weeks || [];

        const currentIndex = weeks.findIndex(w => w.key === currentPeriodKey);
        if (currentIndex === -1) return [];

        const startIndex = Math.max(0, currentIndex - 11);
        const last12Weeks = weeks.slice(startIndex, currentIndex + 1);

        const data = [];
        for (const week of last12Weeks) {
            try {
                const analytics = await api.getAnalytics(venueKey, week.key);
                data.push({
                    week: week.label,
                    weekKey: week.key,
                    revenue: analytics.actual?.revenue || 0,
                    checks: analytics.actual?.checks || 0,
                    averageCheck: analytics.actual?.averageCheck || 0,
                    profit: analytics.actual?.profit || 0
                });
            } catch (error) {
                console.warn(`[Trends] Нет данных для ${week.label}`);
            }
        }

        return data;
    }

    /**
     * Рассчитать статистику
     */
    calculateStatistics(data) {
        const revenues = data.map(d => d.revenue).filter(r => r > 0);

        if (revenues.length === 0) {
            return { mean: 0, max: 0, min: 0, stdDev: 0 };
        }

        const mean = revenues.reduce((a, b) => a + b, 0) / revenues.length;
        const max = Math.max(...revenues);
        const min = Math.min(...revenues);

        // Стандартное отклонение
        const variance = revenues.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / revenues.length;
        const stdDev = Math.sqrt(variance);

        return { mean, max, min, stdDev };
    }

    /**
     * Рассчитать прогноз
     */
    calculateForecast(data) {
        if (data.length < 3) {
            return {
                revenue: 0,
                confidence: 'low',
                method: 'Недостаточно данных'
            };
        }

        // Простой прогноз: среднее последних 4 недель с учетом тренда
        const lastN = Math.min(4, data.length);
        const recentData = data.slice(-lastN);
        const recentRevenues = recentData.map(d => d.revenue);

        const avgRecent = recentRevenues.reduce((a, b) => a + b, 0) / recentRevenues.length;

        // Линейный тренд (простая регрессия)
        let trendSlope = 0;
        if (data.length >= 4) {
            const x = data.map((_, i) => i);
            const y = data.map(d => d.revenue);
            const n = x.length;

            const sumX = x.reduce((a, b) => a + b, 0);
            const sumY = y.reduce((a, b) => a + b, 0);
            const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
            const sumX2 = x.reduce((sum, xi) => sum + xi * xi, 0);

            trendSlope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
        }

        const forecast = avgRecent + trendSlope;

        return {
            revenue: Math.max(0, forecast),
            confidence: data.length >= 8 ? 'high' : 'medium',
            method: 'Линейная регрессия + среднее последних 4 недель',
            trend: trendSlope > 0 ? 'рост' : trendSlope < 0 ? 'снижение' : 'стабильно'
        };
    }

    /**
     * Отобразить статистику
     */
    displayStatistics(stats) {
        document.getElementById('trends-stat-mean').textContent = formatMoney(stats.mean);
        document.getElementById('trends-stat-max').textContent = formatMoney(stats.max);
        document.getElementById('trends-stat-min').textContent = formatMoney(stats.min);
        document.getElementById('trends-stat-stddev').textContent = formatMoney(stats.stdDev);
    }

    /**
     * Отобразить прогноз
     */
    displayForecast(forecast) {
        document.getElementById('trends-forecast-revenue').textContent = formatMoney(forecast.revenue);
        document.getElementById('trends-forecast-confidence').textContent = forecast.confidence;
        document.getElementById('trends-forecast-trend').textContent = forecast.trend;

        const trendIcon = document.getElementById('trends-trend-icon');
        if (trendIcon) {
            trendIcon.textContent = forecast.trend === 'рост' ? '↗' :
                                    forecast.trend === 'снижение' ? '↘' : '→';
        }
    }

    /**
     * Отобразить график трендов
     */
    displayTrendChart(data, forecast) {
        const canvas = document.getElementById('trends-chart');
        if (!canvas) return;

        if (this.trendChart) {
            this.trendChart.destroy();
        }

        const labels = [...data.map(d => d.week), 'Прогноз'];
        const revenues = [...data.map(d => d.revenue), forecast.revenue];

        const ctx = canvas.getContext('2d');
        this.trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Выручка',
                    data: revenues,
                    borderColor: '#2196F3',
                    backgroundColor: 'rgba(33, 150, 243, 0.1)',
                    fill: true,
                    tension: 0.4,
                    segment: {
                        borderDash: (ctx) => {
                            // Пунктир для прогноза
                            return ctx.p1DataIndex === data.length ? [5, 5] : [];
                        }
                    }
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (context) => formatMoney(context.parsed.y)
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => formatMoney(value)
                        }
                    }
                }
            }
        });
    }

    /**
     * Отобразить таблицу недель
     */
    displayWeeksTable(data) {
        const tbody = document.getElementById('trends-weeks-table-body');
        if (!tbody) return;

        tbody.innerHTML = data.map((week, index) => {
            const change = index > 0 ? week.revenue - data[index - 1].revenue : 0;
            const changePercent = index > 0 && data[index - 1].revenue > 0
                ? ((change / data[index - 1].revenue) * 100)
                : 0;

            return `
                <tr>
                    <td>${week.week}</td>
                    <td>${formatMoney(week.revenue)}</td>
                    <td>${Math.round(week.checks)}</td>
                    <td>${formatMoney(week.averageCheck)}</td>
                    <td class="${change >= 0 ? 'positive' : 'negative'}">
                        ${index > 0 ? (change >= 0 ? '+' : '') + changePercent.toFixed(1) + '%' : '-'}
                    </td>
                </tr>
            `;
        }).join('');
    }

    /**
     * Показать индикатор загрузки
     */
    showLoading() {
        document.getElementById('trends-loading')?.classList.remove('hidden');
        document.getElementById('trends-no-data')?.classList.add('hidden');
        document.getElementById('trends-results')?.classList.add('hidden');
    }

    /**
     * Показать "Нет данных"
     */
    showNoData() {
        document.getElementById('trends-loading')?.classList.add('hidden');
        document.getElementById('trends-no-data')?.classList.remove('hidden');
        document.getElementById('trends-results')?.classList.add('hidden');
    }

    /**
     * Показать результаты
     */
    showResults() {
        document.getElementById('trends-loading')?.classList.add('hidden');
        document.getElementById('trends-no-data')?.classList.add('hidden');
        document.getElementById('trends-results')?.classList.remove('hidden');
    }
}

// Экспортируем единственный экземпляр
export const trendsModule = new TrendsModule();

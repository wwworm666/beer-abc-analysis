/**
 * Модуль графиков - визуализация с Chart.js
 * 4 типа графиков: выручка по дням, тренд, доли категорий, средний чек
 */

import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { formatMoney } from '../core/utils.js';

class ChartsModule {
    constructor() {
        this.initialized = false;
        this.charts = {
            revenueByDay: null,
            revenueTrend: null,
            sharesPlan: null,
            sharesActual: null,
            avgCheck: null
        };
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        console.log('[Charts] Инициализация модуля графиков...');

        // Подписываемся на изменения периода и заведения
        state.subscribe((event) => {
            if (event === 'periodChanged' || event === 'venueChanged') {
                this.loadChartsData();
            }
        });

        this.initialized = true;
        console.log('[Charts] ✅ Модуль графиков инициализирован');
    }

    /**
     * Загрузить данные для графиков
     */
    async loadChartsData() {
        const currentTab = document.querySelector('.tab-button[data-tab="tab-charts"]');
        if (!currentTab || !currentTab.classList.contains('active')) {
            return; // Не загружаем если вкладка не активна
        }

        console.log('[Charts] Загрузка данных для графиков...');
        this.showLoading();

        try {
            const venueKey = state.currentVenue;
            const periodKey = state.currentPeriod;

            if (!periodKey) {
                this.showNoData();
                return;
            }

            // Получаем данные для текущего периода
            const actualData = await api.getAnalytics(venueKey, periodKey);
            const planData = await api.getPlan(venueKey, periodKey);

            // Получаем данные для тренда (12 недель)
            const trendData = await this.loadTrendData(venueKey, periodKey);

            // Получаем данные по дням недели
            const dayOfWeekData = await this.loadDayOfWeekData(venueKey, periodKey);

            // Строим все графики
            this.showCharts();
            this.buildRevenueByDayChart(dayOfWeekData);
            this.buildRevenueTrendChart(trendData);
            this.buildSharesCharts(planData, actualData);
            this.buildAvgCheckChart(trendData, planData);

            console.log('[Charts] ✅ Графики построены успешно');

        } catch (error) {
            console.error('[Charts] Ошибка загрузки данных:', error);
            state.addMessage('error', 'Ошибка загрузки данных для графиков');
            this.showNoData();
        }
    }

    /**
     * Загрузить данные для тренда (12 недель назад)
     */
    async loadTrendData(venueKey, currentPeriodKey) {
        // Получаем список всех недель
        const weeksResponse = await api.getWeeks();
        const weeks = weeksResponse.weeks || [];

        // Находим текущую неделю
        const currentIndex = weeks.findIndex(w => w.key === currentPeriodKey);
        if (currentIndex === -1) {
            return [];
        }

        // Берём 12 недель до текущей (включая текущую)
        const startIndex = Math.max(0, currentIndex - 11);
        const last12Weeks = weeks.slice(startIndex, currentIndex + 1);

        // Загружаем данные для каждой недели
        const trendData = [];
        for (const week of last12Weeks) {
            try {
                const data = await api.getAnalytics(venueKey, week.key);
                trendData.push({
                    label: week.label,
                    revenue: data.actual?.revenue || 0,
                    avgCheck: data.actual?.averageCheck || 0,
                    checks: data.actual?.checks || 0
                });
            } catch (error) {
                console.warn(`[Charts] Нет данных для недели ${week.label}`);
                trendData.push({
                    label: week.label,
                    revenue: 0,
                    avgCheck: 0,
                    checks: 0
                });
            }
        }

        return trendData;
    }

    /**
     * Загрузить данные по дням недели (заглушка - в реальности нужен отдельный endpoint)
     */
    async loadDayOfWeekData(venueKey, periodKey) {
        // TODO: В будущем создать endpoint для группировки по дням недели
        // Пока используем равномерное распределение для демонстрации
        const data = await api.getAnalytics(venueKey, periodKey);
        const totalRevenue = data.actual?.revenue || 0;

        // Временное распределение (в реальности нужны данные из OLAP)
        const avgPerDay = totalRevenue / 7;
        return [
            { day: 'Пн', revenue: avgPerDay * 0.9 },
            { day: 'Вт', revenue: avgPerDay * 0.85 },
            { day: 'Ср', revenue: avgPerDay * 0.95 },
            { day: 'Чт', revenue: avgPerDay * 1.1 },
            { day: 'Пт', revenue: avgPerDay * 1.3 },
            { day: 'Сб', revenue: avgPerDay * 1.4 },
            { day: 'Вс', revenue: avgPerDay * 1.2 }
        ];
    }

    /**
     * График 1: Выручка по дням недели (Bar Chart)
     */
    buildRevenueByDayChart(dayData) {
        const canvas = document.getElementById('chart-revenue-by-day');
        if (!canvas) return;

        // Уничтожаем старый график
        if (this.charts.revenueByDay) {
            this.charts.revenueByDay.destroy();
        }

        const ctx = canvas.getContext('2d');
        this.charts.revenueByDay = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: dayData.map(d => d.day),
                datasets: [{
                    label: 'Выручка, ₽',
                    data: dayData.map(d => d.revenue),
                    backgroundColor: '#4CAF50',
                    borderColor: '#45a049',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
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
     * График 2: Тренд выручки (Line Chart)
     */
    buildRevenueTrendChart(trendData) {
        const canvas = document.getElementById('chart-revenue-trend');
        if (!canvas) return;

        if (this.charts.revenueTrend) {
            this.charts.revenueTrend.destroy();
        }

        const ctx = canvas.getContext('2d');
        this.charts.revenueTrend = new Chart(ctx, {
            type: 'line',
            data: {
                labels: trendData.map(d => d.label),
                datasets: [{
                    label: 'Выручка',
                    data: trendData.map(d => d.revenue),
                    borderColor: '#2196F3',
                    backgroundColor: 'rgba(33, 150, 243, 0.1)',
                    fill: true,
                    tension: 0.4
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
     * График 3: Доли категорий - План vs Факт (Doughnut Charts)
     */
    buildSharesCharts(planData, actualData) {
        this.buildSharesChart('chart-shares-plan', planData?.plan, 'План');
        this.buildSharesChart('chart-shares-actual', actualData?.actual, 'Факт');
    }

    buildSharesChart(canvasId, data, label) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !data) return;

        const chartKey = canvasId === 'chart-shares-plan' ? 'sharesPlan' : 'sharesActual';

        if (this.charts[chartKey]) {
            this.charts[chartKey].destroy();
        }

        const ctx = canvas.getContext('2d');
        this.charts[chartKey] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Розлив', 'Фасовка', 'Кухня'],
                datasets: [{
                    data: [
                        data.draftShare || 0,
                        data.packagedShare || 0,
                        data.kitchenShare || 0
                    ],
                    backgroundColor: ['#FF9800', '#9C27B0', '#F44336'],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                return `${label}: ${value.toFixed(1)}%`;
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * График 4: Динамика среднего чека (Line Chart с планом)
     */
    buildAvgCheckChart(trendData, planData) {
        const canvas = document.getElementById('chart-avg-check');
        if (!canvas) return;

        if (this.charts.avgCheck) {
            this.charts.avgCheck.destroy();
        }

        const planAvgCheck = planData?.plan?.averageCheck || 0;

        const ctx = canvas.getContext('2d');
        this.charts.avgCheck = new Chart(ctx, {
            type: 'line',
            data: {
                labels: trendData.map(d => d.label),
                datasets: [
                    {
                        label: 'Средний чек (факт)',
                        data: trendData.map(d => d.avgCheck),
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: 'Плановый средний чек',
                        data: trendData.map(() => planAvgCheck),
                        borderColor: '#FF5722',
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const label = context.dataset.label || '';
                                return `${label}: ${formatMoney(context.parsed.y)}`;
                            }
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
     * Показать индикатор загрузки
     */
    showLoading() {
        document.getElementById('charts-loading-state')?.classList.remove('hidden');
        document.getElementById('charts-no-data-state')?.classList.add('hidden');
        document.getElementById('charts-grid')?.classList.add('hidden');
    }

    /**
     * Показать сообщение "Нет данных"
     */
    showNoData() {
        document.getElementById('charts-loading-state')?.classList.add('hidden');
        document.getElementById('charts-no-data-state')?.classList.remove('hidden');
        document.getElementById('charts-grid')?.classList.add('hidden');
    }

    /**
     * Показать графики
     */
    showCharts() {
        document.getElementById('charts-loading-state')?.classList.add('hidden');
        document.getElementById('charts-no-data-state')?.classList.add('hidden');
        document.getElementById('charts-grid')?.classList.remove('hidden');
    }
}

// Экспортируем единственный экземпляр
export const chartsModule = new ChartsModule();

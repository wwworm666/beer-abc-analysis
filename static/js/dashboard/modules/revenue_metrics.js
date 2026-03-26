/**
 * Модуль отображения 5 ключевых метрик выручки
 * 5 рядов (Общая + 4 бара) × 5 карточек в ряду
 */

import { state } from '../core/state.js';
import { fetchAPI } from '../core/api.js';
import { formatMoney, getStatus } from '../core/utils.js';

class RevenueMetricsModule {
    constructor() {
        this.initialized = false;
        this.elements = {};
    }

    init() {
        if (this.initialized) return;

        this.cacheElements();
        this.setupListeners();
        this.initialized = true;
        console.log('[RevenueMetrics] Модуль инициализирован');
    }

    cacheElements() {
        const revenueTab = document.getElementById('tab-revenue');
        if (!revenueTab) {
            console.log('[RevenueMetrics] Вкладка revenue не найдена');
            return;
        }

        this.elements = {
            loading: revenueTab.querySelector('#revenue-loading'),
            noData: revenueTab.querySelector('#revenue-no-data'),
            metricsContainer: revenueTab.querySelector('#revenue-metrics-container'),
            metricsRows: revenueTab.querySelector('#revenue-metrics-rows')
        };
    }

    setupListeners() {
        state.subscribe((_event, _data) => {
            const activeTab = document.querySelector('.tab-button.active');
            if (activeTab && activeTab.getAttribute('data-tab') === 'tab-revenue') {
                this.loadAllMetrics();
            }
        });
    }

    showLoading() {
        if (this.elements.loading) this.elements.loading.classList.remove('hidden');
        if (this.elements.noData) this.elements.noData.classList.add('hidden');
        if (this.elements.metricsContainer) this.elements.metricsContainer.classList.add('hidden');
    }

    showNoData() {
        if (this.elements.loading) this.elements.loading.classList.add('hidden');
        if (this.elements.noData) this.elements.noData.classList.remove('hidden');
        if (this.elements.metricsContainer) this.elements.metricsContainer.classList.add('hidden');
    }

    showContent() {
        if (this.elements.loading) this.elements.loading.classList.add('hidden');
        if (this.elements.noData) this.elements.noData.classList.add('hidden');
        if (this.elements.metricsContainer) this.elements.metricsContainer.classList.remove('hidden');
    }

    async loadAllMetrics() {
        const venue = state.currentVenue;

        // Период: с 1-го числа текущего месяца по сегодня
        const now = new Date();
        const year = now.getFullYear();
        const month = now.getMonth();
        const day = now.getDate();

        const dateFrom = `${year}-${String(month + 1).padStart(2, '0')}-01`;
        const dateTo = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

        console.log('[RevenueMetrics] loadAllMetrics:', venue, dateFrom, '-', dateTo);

        if (!this.elements.metricsRows) {
            this.cacheElements();
            if (!this.elements.metricsRows) {
                console.error('[RevenueMetrics] Не удалось найти DOM элементы');
                return;
            }
        }

        this.showLoading();

        // Бары для загрузки
        const bars = ['', 'bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'];
        const barNames = {
            '': 'Общая',
            'bolshoy': 'Большой пр. В.О',
            'ligovskiy': 'Лиговский',
            'kremenchugskaya': 'Кременчугская',
            'varshavskaya': 'Варшавская'
        };

        // Параллельная загрузка
        const promises = bars.map(bar =>
            fetchAPI('/api/revenue-metrics', {
                method: 'POST',
                body: JSON.stringify({ bar, date_from: dateFrom, date_to: dateTo })
            })
            .then(metrics => ({ bar, metrics, name: barNames[bar] }))
            .catch(error => {
                console.error(`[RevenueMetrics] Ошибка для ${bar}:`, error);
                return { bar, metrics: null, name: barNames[bar] };
            })
        );

        const loaded = await Promise.all(promises);

        const results = {};
        loaded.forEach(({ bar, metrics, name }) => {
            console.log(`[RevenueMetrics] Bar ${bar}:`, metrics);
            results[bar] = metrics ? { ...metrics, name } : null;
        });

        // Проверяем наличие данных
        const hasData = Object.values(results).some(r => r !== null && r.current > 0);
        if (!hasData) {
            this.showNoData();
            return;
        }

        // Рендерим все 5 рядов карточек
        this.renderAllRows(results);

        this.showContent();
    }

    /**
     * Рендерит все ряды карточек (5 баров × 5 карточек)
     */
    renderAllRows(results) {
        const container = this.elements.metricsRows;
        if (!container) return;

        container.innerHTML = '';

        const bars = ['', 'bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'];
        const barNames = {
            '': 'Общая',
            'bolshoy': 'Большой пр. В.О',
            'ligovskiy': 'Лиговский',
            'kremenchugskaya': 'Кременчугская',
            'varshavskaya': 'Варшавская'
        };

        for (const bar of bars) {
            const data = results[bar];
            if (!data) continue;

            const rowEl = this.createBarRow(data, barNames[bar]);
            container.appendChild(rowEl);
        }
    }

    /**
     * Создаёт ряд карточек для одного бара
     */
    createBarRow(metrics, barName) {
        const row = document.createElement('div');
        row.className = 'revenue-metrics-row';

        const completionClass = getStatus(metrics.completion_percent);
        const expectedPercent = metrics.plan > 0 ? (metrics.expected / metrics.plan) * 100 : 0;
        const expectedStatus = getStatus(expectedPercent);

        // Карточка 1: Выручка
        const currentCard = document.createElement('div');
        currentCard.className = 'revenue-metric-card';
        currentCard.innerHTML = `
            <div class="status-indicator ${completionClass}"></div>
            <div class="rmc-value">${formatMoney(metrics.current)}</div>
        `;

        // Карточка 2: План
        const planCard = document.createElement('div');
        planCard.className = 'revenue-metric-card';
        planCard.innerHTML = `
            <div class="status-indicator neutral"></div>
            <div class="rmc-value">${formatMoney(metrics.plan)}</div>
        `;

        // Карточка 3: Ожидаемая
        const expectedCard = document.createElement('div');
        expectedCard.className = 'revenue-metric-card';
        expectedCard.innerHTML = `
            <div class="status-indicator ${expectedStatus}"></div>
            <div class="rmc-value">${formatMoney(metrics.expected)}</div>
        `;

        // Карточка 4: Средняя
        const averageCard = document.createElement('div');
        averageCard.className = 'revenue-metric-card';
        averageCard.innerHTML = `
            <div class="status-indicator neutral"></div>
            <div class="rmc-value">${formatMoney(metrics.average)}</div>
        `;

        // Карточка 5: Выполнение (с progress bar)
        const completionCard = document.createElement('div');
        completionCard.className = 'revenue-metric-card completion-card';
        completionCard.innerHTML = `
            <div class="status-indicator ${completionClass}"></div>
            <div class="rmc-value">${metrics.completion_percent.toFixed(1)}%</div>
            <div class="rmc-progress">
                <div class="rmc-progress-bar" style="width: ${Math.min(metrics.completion_percent, 100)}%"></div>
            </div>
            <div class="rmc-footer">
                <span class="rmc-diff ${metrics.current >= metrics.plan ? 'positive' : 'negative'}">
                    ${metrics.current >= metrics.plan ? '+' : ''}${formatMoney(metrics.current - metrics.plan)}
                </span>
            </div>
        `;

        row.appendChild(currentCard);
        row.appendChild(planCard);
        row.appendChild(expectedCard);
        row.appendChild(averageCard);
        row.appendChild(completionCard);

        return row;
    }
}

export const revenueMetricsModule = new RevenueMetricsModule();

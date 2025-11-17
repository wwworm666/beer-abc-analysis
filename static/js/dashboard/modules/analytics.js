/**
 * Модуль аналитики
 * Загрузка и отображение данных план vs факт
 */

import { state } from '../core/state.js';
import { getPlan, getAnalytics } from '../core/api.js';
import { METRICS } from '../core/config.js';
import {
    formatValue,
    calculatePercent,
    calculateDiff,
    getStatus
} from '../core/utils.js';

class Analytics {
    constructor() {
        this.metricsGrid = document.getElementById('metrics-grid');
        this.statsBar = document.getElementById('stats-bar');
        this.noPlanState = document.getElementById('no-plan-state');
        this.loadingState = document.getElementById('loading-state');

        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        this.setupEventListeners();
        this.initialized = true;
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
            return;
        }

        this.showLoading();

        try {
            // Параллельная загрузка плана и факта
            const [plan, actual] = await Promise.all([
                getPlan(state.currentVenue, state.currentPeriod.key),
                getAnalytics(
                    state.currentVenue,
                    state.currentPeriod.start,
                    state.currentPeriod.end
                )
            ]);

            state.setPlan(plan);
            state.setActual(actual);

            // Отображаем данные
            if (plan) {
                this.displayComparison(plan, actual);
            } else {
                this.displayNoPlan();
            }

        } catch (error) {
            console.error('Ошибка загрузки аналитики:', error);
            state.addMessage('error', 'Не удалось загрузить данные аналитики');
            this.hideLoading();
        }
    }

    /**
     * Отобразить сравнение план vs факт
     */
    displayComparison(plan, actual) {
        this.hideLoading();
        this.hideNoPlan();
        this.showMetricsGrid();

        // Очищаем контейнер
        this.metricsGrid.innerHTML = '';

        // Статистика
        let completedCount = 0;
        let totalPercent = 0;

        // Создаем карточки для каждой метрики
        METRICS.forEach(metric => {
            const planValue = plan[metric.planKey];
            const actualValue = actual[metric.actualKey];

            const percent = calculatePercent(actualValue, planValue);
            const diff = calculateDiff(actualValue, planValue);
            const status = getStatus(percent);

            if (percent >= 100) {
                completedCount++;
            }

            totalPercent += percent;

            const card = this.createMetricCard(
                metric,
                planValue,
                actualValue,
                percent,
                diff,
                status
            );

            this.metricsGrid.appendChild(card);
        });

        // Обновляем статистику
        this.updateStats(METRICS.length, completedCount, totalPercent / METRICS.length);
    }

    /**
     * Создать карточку метрики
     */
    createMetricCard(metric, planValue, actualValue, percent, diff, status) {
        const card = document.createElement('div');
        card.className = `metric-card ${status}`;
        card.setAttribute('data-metric-id', metric.id);

        // Форматируем значения
        const formattedPlan = formatValue(planValue, metric.format);
        const formattedActual = formatValue(actualValue, metric.format);
        const formattedDiff = formatValue(Math.abs(diff), metric.format);

        // HTML карточки
        card.innerHTML = `
            <div class="metric-header">
                <span class="metric-icon">${metric.icon}</span>
                <span class="metric-name">${metric.name}</span>
            </div>

            <div class="metric-values">
                <div class="metric-row">
                    <span class="metric-label">План:</span>
                    <span class="metric-value plan">${formattedPlan}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Факт:</span>
                    <span class="metric-value actual">${formattedActual}</span>
                </div>
            </div>

            <div class="metric-progress">
                <div class="progress-bar-container">
                    <div class="progress-bar ${status}" style="width: ${Math.min(percent, 100)}%"></div>
                </div>
                <div class="progress-text">
                    <span class="progress-percent ${status}">${percent.toFixed(1)}%</span>
                    <span class="progress-diff">${diff >= 0 ? '+' : ''}${formattedDiff}</span>
                </div>
            </div>

            <div class="metric-footer">
                <span class="metric-status ${status}">
                    ${this.getStatusText(status, percent)}
                </span>
            </div>
        `;

        return card;
    }

    /**
     * Получить текст статуса
     */
    getStatusText(status, percent) {
        if (status === 'success') {
            return `✅ Выполнено ${percent.toFixed(0)}%`;
        } else if (status === 'warning') {
            return `⚠️ Выполнено ${percent.toFixed(0)}%`;
        } else {
            return `❌ Выполнено ${percent.toFixed(0)}%`;
        }
    }

    /**
     * Обновить статистику
     */
    updateStats(total, completed, avgPercent) {
        document.getElementById('stat-total-metrics').textContent = total;
        document.getElementById('stat-completed-plans').textContent = completed;
        document.getElementById('stat-avg-completion').textContent = avgPercent.toFixed(1) + '%';

        this.statsBar?.classList.remove('hidden');
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

    /**
     * Обновить данные
     */
    refresh() {
        this.loadAnalytics();
    }
}

// Экспортируем единственный экземпляр
export const analytics = new Analytics();

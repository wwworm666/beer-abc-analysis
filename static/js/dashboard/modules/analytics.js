/**
 * Модуль аналитики
 * Загрузка и отображение данных план vs факт
 */

import { state } from '../core/state.js';
import { calculatePlan, getAnalytics, getEmployeeBreakdown } from '../core/api.js';
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
        this.employeeData = null;  // Кэш данных по сотрудникам
        this.expandedCard = null;  // Текущая раскрытая карточка
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
        console.log('[Analytics] loadAnalytics вызван. state.currentPeriod:', state.currentPeriod);

        if (!state.currentVenue || !state.currentPeriod) {
            console.log('[Analytics] Пропуск загрузки - нет venue или period');
            return;
        }

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
        console.log('[Analytics] displayComparison called with:', { plan, actual });

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
            let planValue = plan ? plan[metric.planKey] : null;
            const actualValue = actual[metric.actualKey];

            // Для активности кранов план всегда 100% (если не задан вручную)
            if (metric.id === 'tapActivity' && !planValue) {
                planValue = 100;
            }

            console.log(`[Analytics] Метрика "${metric.name}":`, {
                planKey: metric.planKey,
                actualKey: metric.actualKey,
                planValue,
                actualValue
            });

            const percent = planValue ? calculatePercent(actualValue, planValue) : 0;
            const diff = planValue ? calculateDiff(actualValue, planValue) : 0;
            const status = planValue ? getStatus(percent) : 'neutral';

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

            // Для активности кранов добавляем ссылку на страницу кранов
            if (metric.id === 'tapActivity') {
                card.style.cursor = 'pointer';
                card.addEventListener('click', () => {
                    // Получаем текущий venue из state
                    const currentVenue = state.currentVenue;
                    // Маппинг venue_key -> bar_id для страницы кранов
                    const venueToBarMapping = {
                        'bolshoy': 'bar1',
                        'ligovskiy': 'bar2',
                        'kremenchugskaya': 'bar3',
                        'varshavskaya': 'bar4'
                    };

                    if (currentVenue === 'all') {
                        // Если выбрано "Все заведения", идем на общую страницу кранов
                        window.location.href = '/taps';
                    } else {
                        // Иначе идем на страницу конкретного бара
                        const barId = venueToBarMapping[currentVenue];
                        if (barId) {
                            window.location.href = `/taps/${barId}`;
                        } else {
                            window.location.href = '/taps';
                        }
                    }
                });
            }

            this.metricsGrid.appendChild(card);
        });

        console.log('[Analytics] Всего метрик отрисовано:', METRICS.length);

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

        // Метрики с раскрытием по сотрудникам
        const expandableMetrics = [
            'revenue', 'checks', 'averageCheck',
            'draftShare', 'packagedShare', 'kitchenShare',
            'revenueDraft', 'revenuePackaged', 'revenueKitchen'
        ];

        if (expandableMetrics.includes(metric.id)) {
            card.classList.add('expandable');
            card.addEventListener('click', () => this.handleCardClick(card, metric));
        }

        // Форматируем значения
        const formattedPlan = planValue !== null ? formatValue(planValue, metric.format) : '—';
        const formattedActual = formatValue(actualValue, metric.format);
        const formattedDiff = planValue !== null ? formatValue(Math.abs(diff), metric.format) : '—';

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

            ${planValue !== null ? `
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
            ` : `
            <div class="metric-footer">
                <span class="metric-status neutral">
                    План не задан
                </span>
            </div>
            `}
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
     * Загрузить данные по сотрудникам для раскрытия карточек
     */
    async loadEmployeeData() {
        if (!state.currentVenue || !state.currentPeriod) return;

        try {
            const data = await getEmployeeBreakdown(
                state.currentVenue,
                state.currentPeriod.start,
                state.currentPeriod.end
            );
            this.employeeData = data.employees || [];
            console.log('[Analytics] Employee data loaded:', this.employeeData.length, 'employees');
        } catch (error) {
            console.error('[Analytics] Failed to load employee data:', error);
            this.employeeData = [];
        }
    }

    /**
     * Обработчик клика по карточке — раскрытие/закрытие
     */
    async handleCardClick(card, metric) {
        // Метрики для которых показываем разбивку по сотрудникам
        const expandableMetrics = [
            'revenue', 'checks', 'averageCheck',
            'draftShare', 'packagedShare', 'kitchenShare',
            'revenueDraft', 'revenuePackaged', 'revenueKitchen'
        ];

        if (!expandableMetrics.includes(metric.id)) return;

        // Если эта карточка уже раскрыта — закрываем
        if (this.expandedCard === card) {
            this.collapseCard(card);
            return;
        }

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

        // Раскрываем карточку
        this.expandCard(card, metric);
    }

    /**
     * Раскрыть карточку с данными по сотрудникам
     */
    expandCard(card, metric) {
        if (!this.employeeData || this.employeeData.length === 0) {
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
     * Отрисовать список сотрудников для метрики
     */
    renderEmployeeList(metric) {
        const employees = this.employeeData;

        // Маппинг метрик на ключи в данных сотрудников
        const keyMap = {
            'revenue': 'revenue',
            'checks': 'checks',
            'averageCheck': 'averageCheck',
            'draftShare': 'draftShare',
            'packagedShare': 'packagedShare',
            'kitchenShare': 'kitchenShare',
            'revenueDraft': 'revenueDraft',
            'revenuePackaged': 'revenuePackaged',
            'revenueKitchen': 'revenueKitchen'
        };

        const key = keyMap[metric.id];
        if (!key) return '<div class="breakdown-empty">Нет данных</div>';

        // Сортируем по значению метрики
        const sorted = [...employees].sort((a, b) => (b[key] || 0) - (a[key] || 0));

        // Берём топ-5
        const top5 = sorted.slice(0, 5);

        if (top5.length === 0) {
            return '<div class="breakdown-empty">Нет данных</div>';
        }

        return top5.map((emp, i) => {
            const value = emp[key] || 0;
            const formattedValue = formatValue(value, metric.format);

            return `
                <div class="breakdown-item">
                    <span class="breakdown-rank">${i + 1}</span>
                    <span class="breakdown-name">${emp.name}</span>
                    <span class="breakdown-value">${formattedValue}</span>
                </div>
            `;
        }).join('');
    }

    /**
     * Обновить данные
     */
    refresh() {
        this.employeeData = null;  // Сбрасываем кэш
        this.loadAnalytics();
    }
}

// Экспортируем единственный экземпляр
export const analytics = new Analytics();

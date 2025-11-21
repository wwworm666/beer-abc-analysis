/**
 * Модуль просмотра плановых показателей
 * Отображение плана и факта в виде таблицы (read-only)
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

class PlansViewer {
    constructor() {
        this.loadingState = document.getElementById('plans-loading');
        this.noDataState = document.getElementById('plans-no-data');
        this.tableContainer = document.getElementById('plans-table-container');
        this.tableBody = document.getElementById('plans-table-body');

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
        state.subscribe((event) => {
            if (event === 'venueChanged' || event === 'periodChanged') {
                this.loadData();
            }
        });
    }

    /**
     * Загрузить план и факт
     */
    async loadData() {
        if (!state.currentVenue || !state.currentPeriod) {
            return;
        }

        this.showLoading();

        try {
            // Загружаем план и факт параллельно
            const [planResult, actualResult] = await Promise.allSettled([
                getPlan(state.currentVenue, state.currentPeriod.key),
                getAnalytics(
                    state.currentVenue,
                    state.currentPeriod.start,
                    state.currentPeriod.end
                )
            ]);

            // Извлекаем план (может быть null если не найден)
            const plan = planResult.status === 'fulfilled' ? planResult.value : null;

            // Проверяем что факт загрузился успешно
            if (actualResult.status === 'rejected') {
                throw new Error('Не удалось загрузить фактические данные');
            }

            const actual = actualResult.value;

            // Отображаем данные
            this.displayData(plan, actual);

        } catch (error) {
            console.error('Ошибка загрузки данных:', error);
            state.addMessage('error', 'Не удалось загрузить данные');
            this.hideLoading();
        }
    }

    /**
     * Отобразить данные в таблице
     */
    displayData(plan, actual) {
        this.hideLoading();
        this.hideNoData();
        this.showTable();

        // Очищаем таблицу
        this.tableBody.innerHTML = '';

        // Группировка метрик по секциям
        const sections = [
            {
                name: 'Основные показатели',
                metrics: ['revenue', 'checks', 'averageCheck']
            },
            {
                name: 'Доли категорий',
                metrics: ['draftShare', 'packagedShare', 'kitchenShare']
            },
            {
                name: 'Выручка по категориям',
                metrics: ['revenueDraft', 'revenuePackaged', 'revenueKitchen']
            },
            {
                name: 'Наценка и прибыль',
                metrics: ['markupPercent', 'profit', 'markupDraft', 'markupPackaged', 'markupKitchen']
            },
            {
                name: 'Прочее',
                metrics: ['loyaltyWriteoffs']
            }
        ];

        // Создаем строки таблицы по секциям
        sections.forEach(section => {
            // Заголовок секции
            const headerRow = document.createElement('tr');
            headerRow.className = 'section-header';
            headerRow.innerHTML = `
                <td colspan="5">${section.name}</td>
            `;
            this.tableBody.appendChild(headerRow);

            // Метрики секции
            section.metrics.forEach(metricId => {
                const metric = METRICS.find(m => m.planKey === metricId);
                if (!metric) return;

                const planValue = plan ? plan[metric.planKey] : null;
                const actualValue = actual[metric.actualKey];

                const row = this.createMetricRow(
                    metric,
                    planValue,
                    actualValue
                );

                this.tableBody.appendChild(row);
            });
        });

        // Если нет плана - показываем предупреждение
        if (!plan) {
            this.showNoDataWarning();
        }
    }

    /**
     * Создать строку таблицы для метрики
     */
    createMetricRow(metric, planValue, actualValue) {
        const row = document.createElement('tr');

        // Вычисляем процент и отклонение
        const percent = planValue ? calculatePercent(actualValue, planValue) : null;
        const diff = planValue ? calculateDiff(actualValue, planValue) : null;
        const status = planValue ? getStatus(percent) : 'neutral';

        // Форматируем значения
        const formattedPlan = planValue !== null ? formatValue(planValue, metric.format) : '—';
        const formattedActual = formatValue(actualValue, metric.format);
        const formattedDiff = diff !== null ? formatValue(Math.abs(diff), metric.format) : '—';
        const formattedPercent = percent !== null ? `${percent.toFixed(1)}%` : '—';

        // Класс для отклонения
        let diffClass = 'neutral';
        if (diff !== null) {
            if (diff > 0) diffClass = 'positive';
            else if (diff < 0) diffClass = 'negative';
        }

        // Префикс для отклонения
        const diffPrefix = diff !== null && diff > 0 ? '+' : '';

        // HTML строки
        row.innerHTML = `
            <td class="metric-name">${metric.icon} ${metric.name}</td>
            <td class="value-col plan-col">${formattedPlan}</td>
            <td class="value-col fact-col">${formattedActual}</td>
            <td class="value-col diff-col ${diffClass}">${diffPrefix}${formattedDiff}</td>
            <td class="value-col percent-col ${status}">${formattedPercent}</td>
        `;

        return row;
    }

    /**
     * Показать предупреждение об отсутствии плана
     */
    showNoDataWarning() {
        // Добавляем информационное сообщение в начало таблицы
        const infoRow = document.createElement('tr');
        infoRow.style.backgroundColor = 'var(--bg-tertiary)';
        infoRow.innerHTML = `
            <td colspan="5" style="text-align: center; padding: var(--spacing-lg); color: var(--warning);">
                ⚠️ Для выбранного периода план не задан. Показаны только фактические данные.
            </td>
        `;
        this.tableBody.insertBefore(infoRow, this.tableBody.firstChild);
    }

    /**
     * Показать состояние загрузки
     */
    showLoading() {
        this.loadingState?.classList.remove('hidden');
        this.noDataState?.classList.add('hidden');
        this.tableContainer?.classList.add('hidden');
    }

    /**
     * Скрыть состояние загрузки
     */
    hideLoading() {
        this.loadingState?.classList.add('hidden');
    }

    /**
     * Показать таблицу
     */
    showTable() {
        this.tableContainer?.classList.remove('hidden');
    }

    /**
     * Скрыть таблицу
     */
    hideTable() {
        this.tableContainer?.classList.add('hidden');
    }

    /**
     * Показать состояние "нет данных"
     */
    showNoData() {
        this.noDataState?.classList.remove('hidden');
        this.tableContainer?.classList.add('hidden');
    }

    /**
     * Скрыть состояние "нет данных"
     */
    hideNoData() {
        this.noDataState?.classList.add('hidden');
    }

    /**
     * Обновить данные
     */
    refresh() {
        this.loadData();
    }
}

// Экспортируем единственный экземпляр
export const plansViewer = new PlansViewer();

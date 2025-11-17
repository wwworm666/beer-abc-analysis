/**
 * Модуль управления планами
 * Форма редактирования и сохранения планов
 */

import { state } from '../core/state.js';
import { getPlan, savePlan, getAllPlans } from '../core/api.js';
import { validateShares } from '../core/utils.js';
import { METRICS } from '../core/config.js';

class PlansManager {
    constructor() {
        this.plansForm = document.getElementById('plans-form');
        this.btnSavePlan = document.getElementById('btn-save-plan');
        this.btnCopyPlan = document.getElementById('btn-copy-plan');

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
        // Сохранение плана
        this.btnSavePlan?.addEventListener('click', (e) => {
            e.preventDefault();
            this.handleSavePlan();
        });

        // Копирование плана
        this.btnCopyPlan?.addEventListener('click', () => {
            this.handleCopyPlan();
        });

        // Подписка на изменения состояния
        state.subscribe((event, data) => {
            if (event === 'venueChanged' || event === 'periodChanged') {
                this.loadPlan();
            }
        });
    }

    /**
     * Загрузить план для текущего заведения и периода
     */
    async loadPlan() {
        if (!state.currentVenue || !state.currentPeriod) {
            return;
        }

        state.setLoading('plan', true);

        try {
            const plan = await getPlan(state.currentVenue, state.currentPeriod.key);

            if (plan) {
                this.populateForm(plan);
            } else {
                this.clearForm();
            }

        } catch (error) {
            console.error('Ошибка загрузки плана:', error);
        } finally {
            state.setLoading('plan', false);
        }
    }

    /**
     * Заполнить форму данными плана
     */
    populateForm(plan) {
        METRICS.forEach(metric => {
            const input = document.getElementById(`plan-${metric.planKey}`);
            if (input) {
                input.value = plan[metric.planKey] || '';
            }
        });
    }

    /**
     * Очистить форму
     */
    clearForm() {
        this.plansForm?.reset();
    }

    /**
     * Собрать данные из формы
     */
    collectFormData() {
        const data = {};

        METRICS.forEach(metric => {
            const input = document.getElementById(`plan-${metric.planKey}`);
            if (input) {
                const value = parseFloat(input.value);
                data[metric.planKey] = isNaN(value) ? 0 : value;
            }
        });

        return data;
    }

    /**
     * Валидировать данные плана
     */
    validatePlanData(data) {
        // Проверка суммы долей
        const isValid = validateShares(
            data.draftShare,
            data.packagedShare,
            data.kitchenShare
        );

        if (!isValid) {
            state.addMessage('error', 'Сумма долей (розлив + фасовка + кухня) должна быть ~100%', 5000);
            return false;
        }

        // Проверка на отрицательные значения
        for (const [key, value] of Object.entries(data)) {
            if (value < 0) {
                state.addMessage('error', `Значение "${key}" не может быть отрицательным`, 5000);
                return false;
            }
        }

        return true;
    }

    /**
     * Обработать сохранение плана
     */
    async handleSavePlan() {
        if (!state.currentVenue || !state.currentPeriod) {
            state.addMessage('warning', 'Выберите заведение и период', 3000);
            return;
        }

        const planData = this.collectFormData();

        // Валидация
        if (!this.validatePlanData(planData)) {
            return;
        }

        state.setLoading('plan', true);

        try {
            const result = await savePlan(
                state.currentVenue,
                state.currentPeriod.key,
                planData
            );

            if (result.success) {
                state.addMessage('success', 'План успешно сохранен', 3000);
                state.setPlan(planData);
            } else {
                state.addMessage('error', result.error || 'Ошибка сохранения плана', 5000);
            }

        } catch (error) {
            console.error('Ошибка сохранения плана:', error);
            state.addMessage('error', 'Не удалось сохранить план', 5000);
        } finally {
            state.setLoading('plan', false);
        }
    }

    /**
     * Обработать копирование плана из другого периода
     */
    async handleCopyPlan() {
        if (!state.currentVenue) {
            state.addMessage('warning', 'Выберите заведение', 3000);
            return;
        }

        try {
            // Получаем все планы для текущего заведения
            const allPlans = await getAllPlans(state.currentVenue);

            if (!allPlans || Object.keys(allPlans).length === 0) {
                state.addMessage('info', 'Нет сохраненных планов для этого заведения', 3000);
                return;
            }

            // Показываем модальное окно с выбором периода
            this.showCopyPlanModal(allPlans);

        } catch (error) {
            console.error('Ошибка получения планов:', error);
            state.addMessage('error', 'Не удалось загрузить планы', 5000);
        }
    }

    /**
     * Показать модальное окно выбора плана для копирования
     */
    showCopyPlanModal(allPlans) {
        // TODO: Реализовать модальное окно
        // Пока используем простой prompt
        const periods = Object.keys(allPlans);
        const periodsList = periods.map((key, idx) => `${idx + 1}. ${key}`).join('\n');

        const choice = prompt(
            `Выберите период для копирования (введите номер):\n\n${periodsList}`
        );

        if (choice) {
            const index = parseInt(choice) - 1;
            if (index >= 0 && index < periods.length) {
                const selectedPeriod = periods[index];
                const planToCopy = allPlans[selectedPeriod];

                this.populateForm(planToCopy);
                state.addMessage('success', `План скопирован из периода ${selectedPeriod}`, 3000);
            }
        }
    }

    /**
     * Обновить форму
     */
    refresh() {
        this.loadPlan();
    }
}

// Экспортируем единственный экземпляр
export const plansManager = new PlansManager();

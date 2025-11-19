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
     * Очистить форму и заполнить дефолтными значениями (заглушками)
     */
    clearForm() {
        // Вместо полной очистки, заполняем форму дефолтными значениями
        this.fillDefaultValues();
    }

    /**
     * Заполнить форму дефолтными значениями (заглушками)
     */
    fillDefaultValues() {
        const defaultPlan = {
            revenue: 1000000,           // 1 млн рублей
            checks: 500,                // 500 чеков
            averageCheck: 2000,         // 2000 рублей средний чек
            draftShare: 45,             // 45% розлив
            packagedShare: 30,          // 30% фасовка
            kitchenShare: 25,           // 25% кухня
            revenueDraft: 450000,       // 450к розлив
            revenuePackaged: 300000,    // 300к фасовка
            revenueKitchen: 250000,     // 250к кухня
            markupPercent: 215,         // 215% наценка
            profit: 500000,             // 500к прибыль
            markupDraft: 230,           // 230% наценка розлив
            markupPackaged: 210,        // 210% наценка фасовка
            markupKitchen: 195,         // 195% наценка кухня
            loyaltyWriteoffs: 10000     // 10к списания
        };

        this.populateForm(defaultPlan);
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

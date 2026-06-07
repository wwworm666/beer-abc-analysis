/**
 * Адаптивный период-контрол в верхнем баре.
 * Верхний слот периода меняется под активную вкладку:
 *   Аналитика            → «Период анализа» (диапазон, #flexi-range-picker)
 *   Выручка / Планы      → «Месяц» + «Год» (#global-month-select / #global-year-select)
 *   Сравнение (и прочее) → скрыто (у Сравнения свои Период 1/2)
 * Бар (#venue-selector) и кнопки экспорта видны всегда.
 *
 * Месяц/год — единый источник для месячных вкладок (state.currentMonth/currentYear).
 */

import { state } from '../core/state.js';

class PeriodControls {
    constructor() {
        this.initialized = false;
    }

    init() {
        if (this.initialized) return;

        this.cacheElements();

        // Без глобальных селектов делать нечего (например, на не-дашборд страницах).
        if (!this.monthSelect || !this.yearSelect) {
            this.initialized = true;
            return;
        }

        // Проставляем селекты из состояния (дефолт — текущий месяц, задаётся в state).
        this.monthSelect.value = state.currentMonth;
        const yearStr = String(state.currentYear);
        if ([...this.yearSelect.options].some(o => o.value === yearStr)) {
            this.yearSelect.value = yearStr;
        }
        // Канонизируем state от фактических значений селектов (если года нет в списке опций).
        state.setMonthYear(this.monthSelect.value, parseInt(this.yearSelect.value, 10));

        this.setupEventListeners();
        // Явно выставляем видимость под стартовую вкладку (tabChanged ещё не прилетал).
        this.applyTabVisibility(state.activeTab);

        this.initialized = true;
    }

    cacheElements() {
        this.cgPeriod = document.getElementById('cg-period');
        this.cgMonth = document.getElementById('cg-month');
        this.cgYear = document.getElementById('cg-year');
        this.monthSelect = document.getElementById('global-month-select');
        this.yearSelect = document.getElementById('global-year-select');
    }

    setupEventListeners() {
        const pushMonthYear = () => {
            state.setMonthYear(this.monthSelect.value, parseInt(this.yearSelect.value, 10));
        };
        this.monthSelect.addEventListener('change', pushMonthYear);
        this.yearSelect.addEventListener('change', pushMonthYear);

        // Смена вкладки → перестраиваем видимый период-контрол.
        state.subscribe((event, data) => {
            if (event === 'tabChanged') this.applyTabVisibility(data);
        });
    }

    /**
     * Показать нужный период-контрол под активную вкладку.
     * @param {string} tabId — 'tab-analytics' | 'tab-revenue' | 'tab-plans' | ... (или 'analytics' на старте)
     */
    applyTabVisibility(tabId) {
        const t = tabId || '';
        const isAnalytics = (t === 'tab-analytics' || t === 'analytics');
        const isMonth = (t === 'tab-revenue' || t === 'tab-plans');

        this.cgPeriod?.classList.toggle('hidden', !isAnalytics);
        this.cgMonth?.classList.toggle('hidden', !isMonth);
        this.cgYear?.classList.toggle('hidden', !isMonth);
    }
}

export const periodControls = new PeriodControls();

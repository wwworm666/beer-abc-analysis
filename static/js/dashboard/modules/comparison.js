/**
 * Модуль сравнения (заглушка для будущей реализации)
 * Сравнение периодов и заведений
 */

import { state } from '../core/state.js';

class ComparisonModule {
    constructor() {
        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        console.log('[Comparison] Модуль сравнения инициализирован (заглушка)');
        this.initialized = true;
    }

    /**
     * Сравнить два периода
     */
    async comparePeriods(period1Key, period2Key) {
        console.log(`[Comparison] Сравнение периодов: ${period1Key} vs ${period2Key}`);
        state.addMessage('info', 'Функция сравнения периодов будет реализована позже', 3000);
    }

    /**
     * Сравнить заведения
     */
    async compareVenues(periodKey) {
        console.log(`[Comparison] Сравнение заведений за период: ${periodKey}`);
        state.addMessage('info', 'Функция сравнения заведений будет реализована позже', 3000);
    }
}

// Экспортируем единственный экземпляр
export const comparisonModule = new ComparisonModule();

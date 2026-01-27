/**
 * API клиент для работы с backend
 * Все HTTP запросы к серверу
 */

import { API } from './config.js';

/**
 * Базовая функция для HTTP запросов
 */
async function fetchAPI(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json'
        }
    };

    const config = { ...defaultOptions, ...options };

    try {
        const response = await fetch(url, config);

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Ошибка сервера' }));
            throw new Error(error.error || `HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`API Error [${url}]:`, error);
        throw error;
    }
}

/**
 * Получить список всех заведений
 */
export async function getVenues() {
    const data = await fetchAPI(API.VENUES);
    return data.venues;
}

/**
 * Получить информацию о конкретном заведении
 */
export async function getVenue(venueKey) {
    return await fetchAPI(API.VENUE(venueKey));
}

/**
 * Получить список недель
 */
export async function getWeeks() {
    return await fetchAPI(API.WEEKS);
}

/**
 * Получить план для заведения и периода (старый endpoint - для недельных планов)
 */
export async function getPlan(venueKey, periodKey) {
    try {
        return await fetchAPI(API.PLAN(venueKey, periodKey));
    } catch (error) {
        // Если план не найден (404), вернуть null вместо ошибки
        if (error.message.includes('404') ||
            error.message.includes('не найден') ||
            error.message.includes('not found') ||
            error.message.includes('Plan not found')) {
            return null;
        }
        throw error;
    }
}

/**
 * Рассчитать план для произвольного периода (новый endpoint)
 * Использует месячные планы и пропорционально делит их на выбранный период
 *
 * @param {string} venueKey - ключ заведения (bolshoy, ligovskiy, kremenchugskaya, varshavskaya) или пустая строка для "Общая"
 * @param {string} startDate - дата начала в формате YYYY-MM-DD
 * @param {string} endDate - дата конца в формате YYYY-MM-DD
 * @returns {Object|null} - рассчитанный план или null если нет данных
 */
export async function calculatePlan(venueKey, startDate, endDate) {
    try {
        console.log('[API] calculatePlan вызван:', { venueKey, startDate, endDate });
        return await fetchAPI(API.CALCULATE_PLAN(venueKey, startDate, endDate));
    } catch (error) {
        // Если план не найден (404), вернуть null вместо ошибки
        if (error.message.includes('404') ||
            error.message.includes('не найден') ||
            error.message.includes('not found') ||
            error.message.includes('No monthly plans')) {
            console.log('[API] Месячные планы не найдены для периода');
            return null;
        }
        throw error;
    }
}

/**
 * Сохранить план для заведения и периода
 */
export async function savePlan(venueKey, periodKey, planData) {
    return await fetchAPI(API.PLAN(venueKey, periodKey), {
        method: 'POST',
        body: JSON.stringify(planData)
    });
}

/**
 * Удалить план для заведения и периода
 */
export async function deletePlan(venueKey, periodKey) {
    return await fetchAPI(API.PLAN(venueKey, periodKey), {
        method: 'DELETE'
    });
}

/**
 * Получить все планы для заведения
 */
export async function getAllPlans(venueKey) {
    const data = await fetchAPI(API.ALL_PLANS(venueKey));
    return data.plans;
}

/**
 * Получить фактические данные (аналитика)
 */
export async function getAnalytics(venueKey, dateFrom, dateTo) {
    console.log('[API] getAnalytics вызван с параметрами:', { venueKey, dateFrom, dateTo });

    return await fetchAPI(API.ANALYTICS, {
        method: 'POST',
        body: JSON.stringify({
            bar: venueKey || '',  // ИСПРАВЛЕНО: бэкенд ожидает 'bar', не 'venue_key'
            date_from: dateFrom,
            date_to: dateTo
        })
    });
}

/**
 * Сравнить два периода
 */
export async function comparePeriods(venueKey, period1, period2) {
    return await fetchAPI(API.COMPARISON_PERIODS, {
        method: 'POST',
        body: JSON.stringify({
            venue_key: venueKey,
            period1,
            period2
        })
    });
}

/**
 * Сравнить все заведения за период
 */
export async function compareVenues(periodKey) {
    return await fetchAPI(API.COMPARISON_VENUES, {
        method: 'POST',
        body: JSON.stringify({
            period_key: periodKey
        })
    });
}

/**
 * Получить тренды для метрики
 */
export async function getTrends(venueKey, metric, weeksCount = 12) {
    return await fetchAPI(API.TRENDS(venueKey, metric, weeksCount));
}

/**
 * Экспортировать данные в Excel
 */
export async function exportToExcel(venueKey, periodKey, data) {
    return await fetchAPI(API.EXPORT_EXCEL, {
        method: 'POST',
        body: JSON.stringify({
            venue_key: venueKey,
            period_key: periodKey,
            data
        })
    });
}

/**
 * Экспортировать данные в PDF
 */
export async function exportToPDF(venueKey, periodKey, data) {
    return await fetchAPI(API.EXPORT_PDF, {
        method: 'POST',
        body: JSON.stringify({
            venue_key: venueKey,
            period_key: periodKey,
            data
        })
    });
}

/**
 * Получить комментарий для периода
 */
export async function getComment(venueKey, periodKey) {
    try {
        return await fetchAPI(API.COMMENTS(venueKey, periodKey));
    } catch (error) {
        return null;
    }
}

/**
 * Сохранить комментарий для периода
 */
export async function saveComment(venueKey, periodKey, comment) {
    return await fetchAPI(API.COMMENTS(venueKey, periodKey), {
        method: 'POST',
        body: JSON.stringify({ comment })
    });
}

/**
 * Получить разбивку метрик по сотрудникам
 * Используется для раскрытия карточек на дашборде
 */
export async function getEmployeeBreakdown(venueKey, dateFrom, dateTo) {
    return await fetchAPI('/api/employee-metrics-breakdown', {
        method: 'POST',
        body: JSON.stringify({
            venue_key: venueKey || 'all',
            date_from: dateFrom,
            date_to: dateTo
        })
    });
}

// Экспортируем объект api со всеми функциями для удобного импорта
export const api = {
    getVenues,
    getVenue,
    getWeeks,
    getPlan,
    calculatePlan,
    savePlan,
    deletePlan,
    getAllPlans,
    getAnalytics,
    comparePeriods,
    compareVenues,
    getTrends,
    exportToExcel,
    exportToPDF,
    getComment,
    saveComment,
    getEmployeeBreakdown
};

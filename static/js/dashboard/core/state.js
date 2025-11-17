/**
 * Глобальное состояние приложения
 * Централизованное управление данными
 */

import { STORAGE_KEYS } from './config.js';

class DashboardState {
    constructor() {
        // Текущее выбранное заведение
        this.currentVenue = this.loadFromStorage(STORAGE_KEYS.SELECTED_VENUE) || 'all';

        // Текущий период
        this.currentPeriod = this.loadFromStorage(STORAGE_KEYS.SELECTED_PERIOD) || null;

        // Список всех заведений
        this.venues = [];

        // Список всех недель
        this.weeks = [];

        // Текущий индекс недели (для навигации)
        this.currentWeekIndex = -1;

        // План для текущего периода и заведения
        this.currentPlan = null;

        // Фактические данные для текущего периода и заведения
        this.currentActual = null;

        // Активная вкладка
        this.activeTab = 'analytics';

        // Состояние загрузки
        this.loading = {
            venues: false,
            weeks: false,
            plan: false,
            actual: false
        };

        // Сообщения (ошибки, успех)
        this.messages = [];

        // Подписчики на изменения состояния
        this.subscribers = [];
    }

    /**
     * Загрузить значение из localStorage
     */
    loadFromStorage(key) {
        try {
            const value = localStorage.getItem(key);
            return value ? JSON.parse(value) : null;
        } catch (e) {
            console.error(`Ошибка загрузки из localStorage (${key}):`, e);
            return null;
        }
    }

    /**
     * Сохранить значение в localStorage
     */
    saveToStorage(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            console.error(`Ошибка сохранения в localStorage (${key}):`, e);
        }
    }

    /**
     * Установить текущее заведение
     */
    setVenue(venueKey) {
        this.currentVenue = venueKey;
        this.saveToStorage(STORAGE_KEYS.SELECTED_VENUE, venueKey);
        this.notify('venueChanged', venueKey);
    }

    /**
     * Установить текущий период
     */
    setPeriod(period) {
        this.currentPeriod = period;
        this.saveToStorage(STORAGE_KEYS.SELECTED_PERIOD, period);
        this.notify('periodChanged', period);
    }

    /**
     * Установить список заведений
     */
    setVenues(venues) {
        this.venues = venues;
        this.notify('venuesLoaded', venues);
    }

    /**
     * Установить список недель
     */
    setWeeks(weeks) {
        this.weeks = weeks;

        // Найти индекс текущей недели
        const currentWeek = weeks.find(w => w.is_current);
        if (currentWeek) {
            this.currentWeekIndex = weeks.indexOf(currentWeek);

            // Если период не установлен, использовать текущую неделю
            if (!this.currentPeriod) {
                this.setPeriod({
                    key: currentWeek.key,
                    start: currentWeek.start,
                    end: currentWeek.end,
                    label: currentWeek.label
                });
            }
        }

        this.notify('weeksLoaded', weeks);
    }

    /**
     * Установить текущий план
     */
    setPlan(plan) {
        this.currentPlan = plan;
        this.notify('planLoaded', plan);
    }

    /**
     * Установить фактические данные
     */
    setActual(actual) {
        this.currentActual = actual;
        this.notify('actualLoaded', actual);
    }

    /**
     * Установить активную вкладку
     */
    setActiveTab(tab) {
        this.activeTab = tab;
        this.notify('tabChanged', tab);
    }

    /**
     * Установить состояние загрузки
     */
    setLoading(key, value) {
        this.loading[key] = value;
        this.notify('loadingChanged', { key, value });
    }

    /**
     * Добавить сообщение
     */
    addMessage(type, text, duration = 5000) {
        const message = { type, text, id: Date.now() };
        this.messages.push(message);
        this.notify('messageAdded', message);

        // Автоматически удалить через duration
        if (duration > 0) {
            setTimeout(() => this.removeMessage(message.id), duration);
        }
    }

    /**
     * Удалить сообщение
     */
    removeMessage(id) {
        this.messages = this.messages.filter(m => m.id !== id);
        this.notify('messageRemoved', id);
    }

    /**
     * Подписаться на изменения состояния
     */
    subscribe(callback) {
        this.subscribers.push(callback);

        // Возвращаем функцию отписки
        return () => {
            this.subscribers = this.subscribers.filter(cb => cb !== callback);
        };
    }

    /**
     * Уведомить подписчиков об изменении
     */
    notify(event, data) {
        this.subscribers.forEach(callback => {
            try {
                callback(event, data);
            } catch (e) {
                console.error('Ошибка в subscriber:', e);
            }
        });
    }

    /**
     * Получить текущее состояние
     */
    getState() {
        return {
            currentVenue: this.currentVenue,
            currentPeriod: this.currentPeriod,
            venues: this.venues,
            weeks: this.weeks,
            currentWeekIndex: this.currentWeekIndex,
            currentPlan: this.currentPlan,
            currentActual: this.currentActual,
            activeTab: this.activeTab,
            loading: this.loading,
            messages: this.messages
        };
    }
}

// Экспортируем единственный экземпляр (Singleton)
export const state = new DashboardState();

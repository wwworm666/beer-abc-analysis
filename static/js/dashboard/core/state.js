/**
 * Глобальное состояние приложения
 * Централизованное управление данными
 */

import { STORAGE_KEYS } from './config.js';
import { defaultPeriod, monthYearOf } from './period_model.js';

class DashboardState {
    constructor() {
        // Текущее выбранное заведение
        this.currentVenue = this.loadFromStorage(STORAGE_KEYS.SELECTED_VENUE) || 'all';

        // Текущий период — ЕДИНСТВЕННЫЙ источник дефолта на весь дашборд:
        // последняя завершённая неделя (пн-вс). Намеренно НЕ восстанавливаем из
        // localStorage: у незавершённого/старого периода факт и план несопоставимы,
        // и до этого три источника дефолта (localStorage, /api/weeks, datepicker)
        // перетирали друг друга, давая лишний OLAP-запрос на старте.
        this.currentPeriod = defaultPeriod();

        // Месяц/год месячных вкладок (Выручка, Планы) ВЫВОДЯТСЯ из периода,
        // отдельных селекторов больше нет. Формат обязателен: месяц — строка
        // '01'..'12' (plans.js собирает ключ `${year}-${month}`), год — число.
        const _my = monthYearOf(this.currentPeriod);
        this.currentMonth = _my.month;
        this.currentYear = _my.year;

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
     * Установить текущий период.
     *
     * Рассылает 'periodChanged' всегда, а 'monthChanged' — только когда реально
     * сменился месяц или год. Месячные вкладки (Выручка, Планы, Планы по дням)
     * подписаны именно на 'monthChanged', поэтому листание стрелками внутри
     * одного месяца их не дёргает.
     *
     * Период НЕ персистится: дашборд всегда открывается на последней завершённой
     * неделе (см. конструктор).
     */
    setPeriod(period) {
        this.currentPeriod = period;

        const my = monthYearOf(period);
        const monthYearChanged = my && (my.month !== this.currentMonth || my.year !== this.currentYear);
        if (monthYearChanged) {
            this.currentMonth = my.month;
            this.currentYear = my.year;
        }

        this.notify('periodChanged', period);

        if (monthYearChanged) {
            this.notify('monthChanged', { month: this.currentMonth, year: this.currentYear });
        }
    }

    /**
     * Установить месяц/год напрямую.
     *
     * Оставлено для совместимости: штатный путь — setPeriod(), который выводит
     * месяц/год из периода. Прямой вызов нужен только тому, кто меняет месяц,
     * не трогая период.
     *
     * @param {string} month — '01'..'12' (строка с ведущим нулём обязательна:
     *                         plans.js собирает ключ плана как `${year}-${month}`)
     * @param {number} year
     */
    setMonthYear(month, year) {
        this.currentMonth = month;
        this.currentYear = year;
        this.notify('monthChanged', { month, year });
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

        // Найти индекс текущей недели (нужен графикам/трендам для окна в 12 недель).
        // Период отсюда НЕ выставляется: единственный источник дефолта — конструктор,
        // иначе ответ /api/weeks перетирал бы уже выбранный пользователем период.
        const currentWeek = weeks.find(w => w.is_current);
        if (currentWeek) {
            this.currentWeekIndex = weeks.indexOf(currentWeek);
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
                // Проверяем что callback это функция перед вызовом
                if (typeof callback === 'function') {
                    callback(event, data);
                } else {
                    console.warn('Subscriber is not a function:', callback);
                }
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

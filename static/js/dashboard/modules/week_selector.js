/**
 * Модуль селектора недель и периодов
 * Управление выбором периода, навигация по неделям
 */

import { state } from '../core/state.js';
import { getWeeks } from '../core/api.js';

class WeekSelector {
    constructor() {
        // Этих элементов может не быть в HTML (используется Flatpickr вместо селектора)
        this.selectElement = document.getElementById('week-selector');
        this.btnPrevWeek = document.getElementById('btn-prev-week');
        this.btnCurrentWeek = document.getElementById('btn-current-week');
        this.btnNextWeek = document.getElementById('btn-next-week');
        this.customPeriod = document.getElementById('custom-period');
        this.dateFrom = document.getElementById('date-from');
        this.dateTo = document.getElementById('date-to');
        this.btnApplyCustom = document.getElementById('btn-apply-custom');

        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    async init() {
        if (this.initialized) return;

        // Если элементов нет в DOM - используем Flatpickr вместо селектора недель
        if (!this.selectElement) {
            console.log('[WeekSelector] Элементы не найдены, используем Flatpickr');
            // Просто загружаем недели в state для использования другими модулями
            await this.loadWeeks();
            this.initialized = true;
            return;
        }

        try {
            await this.loadWeeks();
            this.setupEventListeners();
            this.initialized = true;
        } catch (error) {
            console.error('Ошибка инициализации WeekSelector:', error);
            state.addMessage('error', 'Не удалось загрузить список недель');
        }
    }

    /**
     * Загрузить список недель
     */
    async loadWeeks() {
        state.setLoading('weeks', true);

        try {
            const data = await getWeeks();
            const weeks = data.weeks || [];
            const currentWeek = data.current_week || null;

            state.setWeeks(weeks);

            // Заполняем select только если он есть в DOM
            if (this.selectElement) {
                // Добавляем опцию "Произвольный период"
                weeks.push({
                    key: 'custom',
                    label: '📅 Произвольный период',
                    start: null,
                    end: null,
                    is_current: false
                });

                this.populateSelect(weeks);

                // Установить текущую неделю по умолчанию
                if (currentWeek && !state.currentPeriod) {
                    this.selectWeek(currentWeek.key);
                }
            } else {
                // Если селектора нет, просто устанавливаем период из currentWeek
                if (currentWeek && !state.currentPeriod) {
                    state.setPeriod({
                        key: currentWeek.key,
                        start: currentWeek.start,
                        end: currentWeek.end,
                        label: currentWeek.label
                    });
                }
            }

        } finally {
            state.setLoading('weeks', false);
        }
    }

    /**
     * Заполнить select элемент
     */
    populateSelect(weeks) {
        this.selectElement.innerHTML = '';

        weeks.forEach(week => {
            const option = document.createElement('option');
            option.value = week.key;
            option.textContent = week.label;

            // Отметить текущую неделю
            if (week.is_current) {
                option.textContent += ' (текущая)';
                option.setAttribute('data-current', 'true');
            }

            this.selectElement.appendChild(option);
        });

        // Установить выбранный период
        if (state.currentPeriod) {
            this.selectElement.value = state.currentPeriod.key;
        }
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Изменение недели в dropdown
        this.selectElement.addEventListener('change', (e) => {
            const weekKey = e.target.value;

            if (weekKey === 'custom') {
                this.showCustomPeriod();
            } else {
                this.hideCustomPeriod();
                this.selectWeek(weekKey);
            }
        });

        // Кнопка "Предыдущая неделя"
        this.btnPrevWeek?.addEventListener('click', () => {
            this.navigateWeek(-1);
        });

        // Кнопка "Текущая неделя"
        this.btnCurrentWeek?.addEventListener('click', () => {
            this.goToCurrentWeek();
        });

        // Кнопка "Следующая неделя"
        this.btnNextWeek?.addEventListener('click', () => {
            this.navigateWeek(1);
        });

        // Применить произвольный период
        this.btnApplyCustom?.addEventListener('click', () => {
            this.applyCustomPeriod();
        });

        // Подписка на изменения состояния
        state.subscribe((event, data) => {
            if (event === 'periodChanged') {
                this.selectElement.value = data.key;
            }
        });
    }

    /**
     * Выбрать неделю по ключу
     */
    selectWeek(weekKey) {
        const week = state.weeks.find(w => w.key === weekKey);

        if (!week) {
            console.error('Неделя не найдена:', weekKey);
            return;
        }

        // Обновляем индекс текущей недели
        state.currentWeekIndex = state.weeks.indexOf(week);

        // Устанавливаем период
        state.setPeriod({
            key: week.key,
            start: week.start,
            end: week.end,
            label: week.label
        });
    }

    /**
     * Навигация по неделям (вперед/назад)
     */
    navigateWeek(direction) {
        const newIndex = state.currentWeekIndex + direction;

        // Проверяем границы
        if (newIndex < 0 || newIndex >= state.weeks.length - 1) { // -1 для исключения "custom"
            state.addMessage('warning', 'Достигнут предел доступных недель', 2000);
            return;
        }

        const week = state.weeks[newIndex];
        if (week && week.key !== 'custom') {
            this.selectWeek(week.key);
        }
    }

    /**
     * Перейти к текущей неделе
     */
    goToCurrentWeek() {
        const currentWeek = state.weeks.find(w => w.is_current);

        if (currentWeek) {
            this.selectWeek(currentWeek.key);
            state.addMessage('info', 'Выбрана текущая неделя', 2000);
        }
    }

    /**
     * Показать поля произвольного периода
     */
    showCustomPeriod() {
        this.customPeriod?.classList.remove('hidden');

        // Установить дефолтные даты (последняя неделя)
        if (state.currentPeriod) {
            this.dateFrom.value = state.currentPeriod.start;
            this.dateTo.value = state.currentPeriod.end;
        }
    }

    /**
     * Скрыть поля произвольного периода
     */
    hideCustomPeriod() {
        this.customPeriod?.classList.add('hidden');
    }

    /**
     * Применить произвольный период
     */
    applyCustomPeriod() {
        const dateFrom = this.dateFrom.value;
        const dateTo = this.dateTo.value;

        if (!dateFrom || !dateTo) {
            state.addMessage('warning', 'Укажите обе даты', 3000);
            return;
        }

        if (dateFrom > dateTo) {
            state.addMessage('warning', 'Дата начала не может быть позже даты окончания', 3000);
            return;
        }

        // Создаем кастомный период
        const customKey = `${dateFrom}_${dateTo}`;
        const label = `${this.formatDate(dateFrom)} - ${this.formatDate(dateTo)}`;

        state.setPeriod({
            key: customKey,
            start: dateFrom,
            end: dateTo,
            label: label
        });

        this.hideCustomPeriod();
        state.addMessage('success', `Выбран период: ${label}`, 2000);
    }

    /**
     * Форматировать дату для отображения
     */
    formatDate(dateString) {
        const [year, month, day] = dateString.split('-');
        return `${day}.${month}.${year}`;
    }

    /**
     * Получить текущий период
     */
    getCurrentPeriod() {
        return state.currentPeriod;
    }

    /**
     * Установить период программно
     */
    setPeriod(periodKey) {
        const week = state.weeks.find(w => w.key === periodKey);
        if (week) {
            this.selectWeek(periodKey);
        }
    }
}

// Экспортируем единственный экземпляр
export const weekSelector = new WeekSelector();

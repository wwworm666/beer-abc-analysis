/**
 * Модуль селектора заведений
 * Управление выбором бара и отображением информации
 */

import { state } from '../core/state.js';
import { getVenues } from '../core/api.js';

class VenueSelector {
    constructor() {
        this.selectElement = document.getElementById('venue-selector');
        this.venueInfo = document.getElementById('venue-info');
        this.venueIcon = document.getElementById('venue-icon');
        this.venueName = document.getElementById('venue-name');
        this.venueTaps = document.getElementById('venue-taps');

        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    async init() {
        if (this.initialized) return;

        try {
            await this.loadVenues();
            this.setupEventListeners();
            this.initialized = true;
        } catch (error) {
            console.error('Ошибка инициализации VenueSelector:', error);
            state.addMessage('error', 'Не удалось загрузить список заведений');
        }
    }

    /**
     * Загрузить список заведений
     */
    async loadVenues() {
        state.setLoading('venues', true);

        try {
            const venues = await getVenues();
            state.setVenues(venues);
            this.populateSelect(venues);

            // Установить выбранное заведение
            if (state.currentVenue) {
                this.selectElement.value = state.currentVenue;
                this.updateInfo(state.currentVenue);
            }

        } finally {
            state.setLoading('venues', false);
        }
    }

    /**
     * Заполнить select элемент
     */
    populateSelect(venues) {
        this.selectElement.innerHTML = '';

        venues.forEach(venue => {
            const option = document.createElement('option');
            option.value = venue.key;
            option.textContent = venue.label;

            // Отметить текущую опцию
            if (venue.key === state.currentVenue) {
                option.selected = true;
            }

            this.selectElement.appendChild(option);
        });
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        this.selectElement.addEventListener('change', (e) => {
            this.handleVenueChange(e.target.value);
        });

        // Подписаться на изменения состояния
        state.subscribe((event, data) => {
            if (event === 'venueChanged') {
                this.selectElement.value = data;
                this.updateInfo(data);
            }
        });
    }

    /**
     * Обработать изменение заведения
     */
    handleVenueChange(venueKey) {
        state.setVenue(venueKey);
        this.updateInfo(venueKey);

        // Уведомить об изменении (для обновления данных)
        state.addMessage('info', `Выбрано: ${this.getVenueName(venueKey)}`, 2000);
    }

    /**
     * Обновить информацию о заведении
     */
    updateInfo(venueKey) {
        const venue = state.venues.find(v => v.key === venueKey);

        if (!venue) {
            this.venueInfo.classList.add('hidden');
            return;
        }

        // Для заведения "all" не показываем детали
        if (venueKey === 'all') {
            this.venueInfo.classList.add('hidden');
            return;
        }

        // Получаем полную информацию о заведении из state.venues
        const fullVenue = state.venues.find(v => v.key === venueKey);

        if (fullVenue && this.venueIcon && this.venueName && this.venueTaps) {
            this.venueIcon.textContent = fullVenue.icon || '🍺';
            this.venueName.textContent = fullVenue.name || venue.name;

            // Показываем количество кранов (нужно будет добавить в API)
            // Пока оставляем пустым или дефолтное значение
            this.venueTaps.textContent = '12'; // TODO: получать из API

            this.venueInfo.classList.remove('hidden');
        }
    }

    /**
     * Получить название заведения по ключу
     */
    getVenueName(venueKey) {
        const venue = state.venues.find(v => v.key === venueKey);
        return venue ? venue.name : venueKey;
    }

    /**
     * Получить текущее заведение
     */
    getCurrentVenue() {
        return state.currentVenue;
    }

    /**
     * Установить заведение программно
     */
    setVenue(venueKey) {
        if (this.selectElement.querySelector(`option[value="${venueKey}"]`)) {
            this.selectElement.value = venueKey;
            this.handleVenueChange(venueKey);
        }
    }
}

// Экспортируем единственный экземпляр
export const venueSelector = new VenueSelector();

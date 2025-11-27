/**
 * Главный файл дашборда
 * Инициализация и координация всех модулей
 */

import { state } from './core/state.js';
import { themeManager } from './modules/theme.js';
import { venueSelector } from './modules/venue_selector.js';
import { weekSelector } from './modules/week_selector.js';
import { analytics } from './modules/analytics.js';
import { plansViewer } from './modules/plans.js';
import { chartsModule } from './modules/charts.js';
import { trendsModule } from './modules/trends.js';
import { commentsManager } from './modules/comments.js';

class Dashboard {
    constructor() {
        this.initialized = false;
    }

    /**
     * Инициализация дашборда
     */
    async init() {
        if (this.initialized) return;

        console.log('🚀 Инициализация дашборда...');

        try {
            // 1. Инициализируем тему (синхронно, должно быть первым)
            themeManager.init();
            console.log('✅ Тема инициализирована');

            // 2. Инициализируем селекторы (последовательно)
            await venueSelector.init();
            console.log('✅ Селектор заведений инициализирован');

            await weekSelector.init();
            console.log('✅ Селектор периодов инициализирован');

            // 3. Инициализируем модули данных
            analytics.init();
            console.log('✅ Модуль аналитики инициализирован');

            chartsModule.init();
            console.log('✅ Модуль графиков инициализирован');

            trendsModule.init();
            console.log('✅ Модуль трендов инициализирован');

            plansViewer.init();
            console.log('✅ Модуль просмотра планов инициализирован');

            commentsManager.init();
            console.log('✅ Модуль комментариев инициализирован');

            // 4. Настраиваем вкладки
            this.setupTabs();
            console.log('✅ Вкладки настроены');

            // 5. Настраиваем сообщения
            this.setupMessages();
            console.log('✅ Система сообщений настроена');

            // 6. Загружаем начальные данные
            await this.loadInitialData();
            console.log('✅ Начальные данные загружены');

            this.initialized = true;
            console.log('🎉 Дашборд успешно инициализирован!');

        } catch (error) {
            console.error('❌ Ошибка инициализации дашборда:', error);
            this.showError('Не удалось инициализировать дашборд');
        }
    }

    /**
     * Настроить систему вкладок
     */
    setupTabs() {
        const tabButtons = document.querySelectorAll('.tab-button');
        const tabContents = document.querySelectorAll('.tab-content');

        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tabId = button.getAttribute('data-tab');

                // Убираем active у всех
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabContents.forEach(content => content.classList.remove('active'));

                // Добавляем active к выбранным
                button.classList.add('active');
                const selectedTab = document.getElementById(tabId);
                if (selectedTab) {
                    selectedTab.classList.add('active');
                    state.setActiveTab(tabId);

                    // Загружаем данные при переключении на вкладки
                    if (tabId === 'tab-charts') {
                        chartsModule.loadChartsData();
                        trendsModule.loadTrendsData();
                    } else if (tabId === 'tab-plans') {
                        plansViewer.loadData();
                    }
                }
            });
        });

        // Активируем первую вкладку по умолчанию
        if (tabButtons.length > 0) {
            tabButtons[0].click();
        }
    }

    /**
     * Настроить систему сообщений
     */
    setupMessages() {
        // Создаем контейнер для сообщений если его нет
        let container = document.getElementById('messages-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'messages-container';
            container.className = 'messages-container';
            document.body.appendChild(container);
        }

        // Подписываемся на добавление сообщений
        state.subscribe((event, data) => {
            if (event === 'messageAdded') {
                this.showMessage(data);
            } else if (event === 'messageRemoved') {
                this.removeMessage(data);
            }
        });
    }

    /**
     * Показать сообщение
     */
    showMessage(message) {
        const container = document.getElementById('messages-container');
        if (!container) return;

        const messageEl = document.createElement('div');
        messageEl.className = `message ${message.type}`;
        messageEl.setAttribute('data-id', message.id);
        messageEl.innerHTML = `
            <span class="message-icon">${this.getMessageIcon(message.type)}</span>
            <span class="message-text">${message.text}</span>
        `;

        container.appendChild(messageEl);
    }

    /**
     * Удалить сообщение
     */
    removeMessage(messageId) {
        const messageEl = document.querySelector(`[data-id="${messageId}"]`);
        if (messageEl) {
            messageEl.style.animation = 'fadeOut 0.3s ease';
            setTimeout(() => messageEl.remove(), 300);
        }
    }

    /**
     * Получить иконку для типа сообщения
     */
    getMessageIcon(type) {
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };
        return icons[type] || 'ℹ️';
    }

    /**
     * Загрузить начальные данные
     */
    async loadInitialData() {
        // Данные загружаются автоматически через подписки в модулях
        // когда устанавливается venue и period

        if (state.currentVenue && state.currentPeriod) {
            // Загружаем аналитику
            await analytics.loadAnalytics();
        }
    }

    /**
     * Показать ошибку
     */
    showError(message) {
        state.addMessage('error', message, 0); // 0 = не автоскрыть
    }
}

// Создаем и экспортируем экземпляр дашборда
const dashboard = new Dashboard();

// Инициализируем при загрузке DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        dashboard.init();
    });
} else {
    dashboard.init();
}

export default dashboard;

// Глобальная функция для проверки API
window.dashboardCheckApi = async function() {
    const statusElement = document.getElementById('api-status');
    if (!statusElement) return;
    
    const textElement = statusElement.querySelector('.api-status-text');
    
    statusElement.className = 'api-status checking';
    textElement.textContent = 'Проверка подключения...';
    
    try {
        const response = await fetch('/api/connection-status');
        const data = await response.json();
        
        if (response.ok && data.status === 'connected') {
            statusElement.className = 'api-status connected';
            textElement.textContent = 'iiko API подключен';
        } else {
            statusElement.className = 'api-status error';
            textElement.textContent = 'Ошибка подключения';
            console.error('API connection error:', data.message);
        }
    } catch (error) {
        statusElement.className = 'api-status error';
        textElement.textContent = 'Ошибка подключения';
        console.error('API connection error:', error);
    }
};

// Проверяем API при загрузке страницы
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.dashboardCheckApi();
        setInterval(window.dashboardCheckApi, 60000); // Каждую минуту
    });
} else {
    window.dashboardCheckApi();
    setInterval(window.dashboardCheckApi, 60000);
}

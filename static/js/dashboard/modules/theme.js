/**
 * Модуль управления темой
 * Переключение light/dark режимов
 */

import { STORAGE_KEYS } from '../core/config.js';

class ThemeManager {
    constructor() {
        this.themeButtons = null;
        this.currentTheme = this.loadTheme();

        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        this.themeButtons = document.querySelectorAll('.theme-btn');
        this.applyTheme(this.currentTheme);
        this.setupEventListeners();

        this.initialized = true;
    }

    /**
     * Загрузить тему из localStorage
     */
    loadTheme() {
        const saved = localStorage.getItem(STORAGE_KEYS.THEME);
        if (saved) {
            return saved;
        }

        // Проверяем системные настройки
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }

        return 'light';
    }

    /**
     * Сохранить тему в localStorage
     */
    saveTheme(theme) {
        localStorage.setItem(STORAGE_KEYS.THEME, theme);
    }

    /**
     * Применить тему
     */
    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        this.currentTheme = theme;
        this.saveTheme(theme);

        // Обновить активную кнопку
        if (this.themeButtons) {
            this.themeButtons.forEach(btn => {
                btn.classList.remove('active');
                const btnTheme = btn.textContent === 'Светлая' ? 'light' : 'dark';
                if (btnTheme === theme) {
                    btn.classList.add('active');
                }
            });
        }
    }

    /**
     * Переключить тему
     */
    toggleTheme() {
        const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme(newTheme);
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Обработчики для новых кнопок (через onclick в HTML)
        // Делаем setTheme доступным глобально
        window.dashboardSetTheme = (theme) => this.setTheme(theme);

        // Слушаем изменения системных настроек
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (!localStorage.getItem(STORAGE_KEYS.THEME)) {
                    // Если пользователь не выбирал тему вручную,
                    // следуем системным настройкам
                    this.applyTheme(e.matches ? 'dark' : 'light');
                }
            });
        }
    }

    /**
     * Получить текущую тему
     */
    getTheme() {
        return this.currentTheme;
    }

    /**
     * Установить тему программно
     */
    setTheme(theme) {
        if (theme === 'light' || theme === 'dark') {
            this.applyTheme(theme);
        }
    }
}

// Экспортируем единственный экземпляр
export const themeManager = new ThemeManager();

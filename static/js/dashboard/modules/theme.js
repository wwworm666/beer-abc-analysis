/**
 * Модуль управления темой
 * Переключение light/dark режимов
 */

import { STORAGE_KEYS } from '../core/config.js';

class ThemeManager {
    constructor() {
        this.themeToggle = document.getElementById('theme-toggle');
        this.currentTheme = this.loadTheme();

        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

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

        // Обновить иконку кнопки
        if (this.themeToggle) {
            this.themeToggle.textContent = theme === 'dark' ? '☀️' : '🌙';
            this.themeToggle.setAttribute('title',
                theme === 'dark' ? 'Светлая тема' : 'Темная тема'
            );
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
        this.themeToggle?.addEventListener('click', () => {
            this.toggleTheme();
        });

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

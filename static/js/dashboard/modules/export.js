/**
 * Модуль экспорта данных
 * Экспорт в текст, Excel (заглушка для будущей реализации)
 */

import { state } from '../core/state.js';
import { copyToClipboard } from '../core/utils.js';

class ExportModule {
    constructor() {
        this.btnExportText = document.getElementById('btn-copy-clipboard');
        this.btnShare = document.getElementById('btn-share');

        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        this.setupEventListeners();
        this.initialized = true;
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Копирование в буфер обмена
        this.btnExportText?.addEventListener('click', () => {
            this.handleCopyToClipboard();
        });

        // Share API (для мобильных)
        this.btnShare?.addEventListener('click', () => {
            this.handleShare();
        });
    }

    /**
     * Копировать данные в буфер обмена
     */
    async handleCopyToClipboard() {
        if (!state.currentPlan || !state.currentActual) {
            state.addMessage('warning', 'Нет данных для экспорта', 3000);
            return;
        }

        try {
            // Формируем текстовый отчёт
            const report = this.formatTextReport();

            const success = await copyToClipboard(report);

            if (success) {
                state.addMessage('success', 'Данные скопированы в буфер обмена', 3000);
            } else {
                state.addMessage('error', 'Не удалось скопировать', 3000);
            }

        } catch (error) {
            console.error('Ошибка экспорта:', error);
            state.addMessage('error', 'Ошибка при экспорте данных', 5000);
        }
    }

    /**
     * Поделиться через Share API
     */
    async handleShare() {
        if (!navigator.share) {
            state.addMessage('info', 'Share API не поддерживается браузером', 3000);
            return;
        }

        const report = this.formatTextReport();

        try {
            await navigator.share({
                title: 'Отчёт дашборда',
                text: report
            });
        } catch (error) {
            // Пользователь отменил или ошибка
            console.log('Share cancelled or error:', error);
        }
    }

    /**
     * Форматировать текстовый отчёт
     */
    formatTextReport() {
        const venue = state.venues.find(v => v.key === state.currentVenue);
        const venueName = venue ? venue.name : 'Unknown';
        const period = state.currentPeriod || {};

        const lines = [];

        lines.push('📊 ОТЧЁТ ПО АНАЛИТИКЕ');
        lines.push('='.repeat(40));
        lines.push('');
        lines.push(`Заведение: ${venueName}`);
        lines.push(`Период: ${period.label || 'N/A'}`);
        lines.push(`Дата: ${new Date().toLocaleDateString('ru-RU')}`);
        lines.push('');
        lines.push('-'.repeat(40));
        lines.push('ОСНОВНЫЕ ПОКАЗАТЕЛИ:');
        lines.push('-'.repeat(40));

        // Добавляем основные метрики
        const actual = state.currentActual || {};
        const plan = state.currentPlan || {};

        if (actual.total_revenue) {
            lines.push('');
            lines.push(`💰 Выручка: ${actual.total_revenue.toLocaleString('ru-RU')} ₽`);
            if (plan.revenue) {
                lines.push(`   План: ${plan.revenue.toLocaleString('ru-RU')} ₽`);
            }
        }

        if (actual.total_checks) {
            lines.push('');
            lines.push(`🧾 Чеки: ${actual.total_checks.toLocaleString('ru-RU')} шт`);
            if (plan.checks) {
                lines.push(`   План: ${plan.checks.toLocaleString('ru-RU')} шт`);
            }
        }

        if (actual.avg_check) {
            lines.push('');
            lines.push(`💵 Средний чек: ${actual.avg_check.toLocaleString('ru-RU')} ₽`);
            if (plan.averageCheck) {
                lines.push(`   План: ${plan.averageCheck.toLocaleString('ru-RU')} ₽`);
            }
        }

        lines.push('');
        lines.push('='.repeat(40));

        return lines.join('\n');
    }
}

// Экспортируем единственный экземпляр
export const exportModule = new ExportModule();

/**
 * Модуль экспорта данных
 * Экспорт в текст, Excel, PDF
 */

import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { copyToClipboard } from '../core/utils.js';

class ExportModule {
    constructor() {
        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        console.log('[Export] Инициализация модуля экспорта...');

        this.setupEventListeners();
        this.initialized = true;

        console.log('[Export] ✅ Модуль экспорта инициализирован');
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Копирование в буфер обмена
        document.getElementById('btn-copy-clipboard')?.addEventListener('click', () => {
            this.handleCopyToClipboard();
        });

        // Excel экспорт
        document.getElementById('btn-export-excel')?.addEventListener('click', () => {
            this.handleExportExcel();
        });

        // PDF экспорт
        document.getElementById('btn-export-pdf')?.addEventListener('click', () => {
            this.handleExportPDF();
        });

        // Share API (для мобильных)
        document.getElementById('btn-share')?.addEventListener('click', () => {
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

    /**
     * Экспортировать в Excel
     */
    async handleExportExcel() {
        const venueKey = state.currentVenue;
        const periodKey = state.currentPeriod;

        if (!venueKey || !periodKey) {
            state.addMessage('warning', 'Выберите заведение и период', 3000);
            return;
        }

        try {
            console.log('[Export] Экспорт в Excel...');
            state.addMessage('info', 'Генерация Excel файла...', 2000);

            const response = await fetch('/api/export/excel', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    venue_key: venueKey,
                    period_key: periodKey
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Получаем файл как blob
            const blob = await response.blob();
            const filename = `dashboard_${venueKey}_${periodKey}.xlsx`;

            // Скачиваем файл
            this.downloadFile(blob, filename);

            state.addMessage('success', 'Excel файл сохранен', 3000);

        } catch (error) {
            console.error('[Export] Ошибка экспорта в Excel:', error);
            state.addMessage('error', 'Ошибка при экспорте в Excel', 5000);
        }
    }

    /**
     * Экспортировать в PDF
     */
    async handleExportPDF() {
        const venueKey = state.currentVenue;
        const periodKey = state.currentPeriod;

        if (!venueKey || !periodKey) {
            state.addMessage('warning', 'Выберите заведение и период', 3000);
            return;
        }

        try {
            console.log('[Export] Экспорт в PDF...');
            state.addMessage('info', 'Генерация PDF файла...', 2000);

            const response = await fetch('/api/export/pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    venue_key: venueKey,
                    period_key: periodKey
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Получаем файл как blob
            const blob = await response.blob();
            const filename = `dashboard_${venueKey}_${periodKey}.pdf`;

            // Скачиваем файл
            this.downloadFile(blob, filename);

            state.addMessage('success', 'PDF файл сохранен', 3000);

        } catch (error) {
            console.error('[Export] Ошибка экспорта в PDF:', error);
            state.addMessage('error', 'Ошибка при экспорте в PDF', 5000);
        }
    }

    /**
     * Скачать файл
     */
    downloadFile(blob, filename) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;

        document.body.appendChild(a);
        a.click();

        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
}

// Экспортируем единственный экземпляр
export const exportModule = new ExportModule();

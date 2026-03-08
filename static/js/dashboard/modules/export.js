/**
 * Модуль экспорта данных
 * PDF и Excel экспорт через серверные API
 */

import { state } from '../core/state.js';

class ExportModule {
    constructor() {
        this.initialized = false;
    }

    init() {
        if (this.initialized) return;

        this.btnPdf = document.getElementById('btn-export-pdf');
        this.btnExcel = document.getElementById('btn-export-excel');

        if (this.btnPdf) {
            this.btnPdf.addEventListener('click', () => this.exportPDF());
        }
        if (this.btnExcel) {
            this.btnExcel.addEventListener('click', () => this.exportExcel());
        }

        this.initialized = true;
        console.log('[Export] Модуль экспорта инициализирован');
    }

    /**
     * Получить текущие параметры (venue + period)
     * Возвращает null если данные не выбраны
     */
    getParams() {
        const venueKey = state.currentVenue;
        const period = state.currentPeriod;

        if (!venueKey || !period || !period.start || !period.end) {
            state.addMessage('warning', 'Выберите заведение и период', 3000);
            return null;
        }

        return {
            bar: venueKey,
            date_from: period.start,
            date_to: period.end
        };
    }

    /**
     * Скачать blob как файл
     */
    downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /**
     * Определить имя файла из ответа сервера или сгенерировать дефолтное
     */
    getFilename(response, fallbackName) {
        const disposition = response.headers.get('Content-Disposition');
        if (disposition) {
            const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match && match[1]) {
                return match[1].replace(/['"]/g, '');
            }
        }
        return fallbackName;
    }

    /**
     * Установить состояние кнопки (loading/ready)
     */
    setButtonLoading(btn, loading) {
        if (!btn) return;
        btn.disabled = loading;
        if (loading) {
            btn.dataset.originalText = btn.textContent;
            btn.textContent = '...';
        } else {
            btn.textContent = btn.dataset.originalText || btn.textContent;
        }
    }

    /**
     * Экспорт в Excel
     */
    async exportExcel() {
        const params = this.getParams();
        if (!params) return;

        this.setButtonLoading(this.btnExcel, true);

        try {
            const response = await fetch('/api/export/excel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `Ошибка сервера: ${response.status}`);
            }

            const blob = await response.blob();
            const filename = this.getFilename(
                response,
                `dashboard_${params.bar}_${params.date_from}_${params.date_to}.xlsx`
            );

            this.downloadBlob(blob, filename);
            state.addMessage('success', 'Excel файл скачан', 3000);

        } catch (error) {
            console.error('[Export] Excel error:', error);
            state.addMessage('error', `Ошибка экспорта Excel: ${error.message}`, 5000);
        } finally {
            this.setButtonLoading(this.btnExcel, false);
        }
    }

    /**
     * Экспорт в PDF
     */
    async exportPDF() {
        const params = this.getParams();
        if (!params) return;

        this.setButtonLoading(this.btnPdf, true);

        try {
            const response = await fetch('/api/export/pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `Ошибка сервера: ${response.status}`);
            }

            const blob = await response.blob();

            // Сервер может вернуть HTML fallback если нет reportlab
            const contentType = response.headers.get('Content-Type') || '';
            const ext = contentType.includes('text/html') ? '.html' : '.pdf';

            const filename = this.getFilename(
                response,
                `dashboard_${params.bar}_${params.date_from}_${params.date_to}${ext}`
            );

            this.downloadBlob(blob, filename);

            const msg = ext === '.html'
                ? 'Отчёт скачан как HTML (PDF библиотека не установлена)'
                : 'PDF файл скачан';
            state.addMessage('success', msg, 3000);

        } catch (error) {
            console.error('[Export] PDF error:', error);
            state.addMessage('error', `Ошибка экспорта PDF: ${error.message}`, 5000);
        } finally {
            this.setButtonLoading(this.btnPdf, false);
        }
    }
}

export const exportModule = new ExportModule();

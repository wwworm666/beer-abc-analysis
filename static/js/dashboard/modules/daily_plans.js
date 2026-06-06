/**
 * Модуль «Планы по дням»
 * Подневная разбивка месячного плана + редактирование веса дня (праздник, закрытый день).
 * Источник данных — единый канонический расчёт на бэкенде (core/day_weights.py).
 */

import { state } from '../core/state.js';
import { getDailyBreakdown, setDayWeight, resetDayWeight } from '../core/api.js';
import { formatMoney, formatValue } from '../core/utils.js';

const VENUE_NAMES = {
    'all': 'Все заведения',
    'bolshoy': 'Большой пр. В.О',
    'ligovskiy': 'Лиговский',
    'kremenchugskaya': 'Кременчугская',
    'varshavskaya': 'Варшавская'
};

class DailyPlansViewer {
    constructor() {
        this.initialized = false;
        this.currentPayload = null;
        this.editingDate = null;
    }

    init() {
        if (this.initialized) return;
        this.cacheElements();
        this.setupEventListeners();
        this.initDefaults();
        this.initialized = true;
    }

    cacheElements() {
        this.monthSelect = document.getElementById('daily-month-select');
        this.yearSelect = document.getElementById('daily-year-select');
        this.venueSelect = document.getElementById('daily-venue-select');
        this.venueLabel = document.getElementById('daily-venue-label');
        this.loadingState = document.getElementById('daily-loading');
        this.noDataState = document.getElementById('daily-no-data');
        this.tableContainer = document.getElementById('daily-table-container');
        this.tableBody = document.getElementById('daily-table-body');
        this.footer = document.getElementById('daily-validation-footer');
        this.sumValue = document.getElementById('daily-sum-value');
        this.monthlyValue = document.getElementById('daily-monthly-value');
        this.sumCheck = document.getElementById('daily-sum-check');

        // Модалка веса дня
        this.modal = document.getElementById('day-weight-edit-modal');
        this.modalDate = document.getElementById('day-weight-modal-date');
        this.weightInput = document.getElementById('day-weight-input');
        this.modalCloseBtn = document.getElementById('day-weight-close-btn');
        this.cancelBtn = document.getElementById('day-weight-cancel-btn');
        this.resetBtn = document.getElementById('day-weight-reset-btn');
        this.saveBtn = document.getElementById('day-weight-save-btn');
    }

    setupEventListeners() {
        // Переключение подвкладок Месячные / По дням
        document.querySelectorAll('.plans-subtab-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchSubtab(btn));
        });

        this.venueSelect?.addEventListener('change', () => this.loadData());
        this.monthSelect?.addEventListener('change', () => this.loadData());
        this.yearSelect?.addEventListener('change', () => this.loadData());

        // Модалка
        this.modalCloseBtn?.addEventListener('click', () => this.closeModal());
        this.cancelBtn?.addEventListener('click', () => this.closeModal());
        this.saveBtn?.addEventListener('click', () => this.saveWeight());
        this.resetBtn?.addEventListener('click', () => this.resetWeightFromModal());

        // Делегирование кликов по кнопкам строк таблицы
        this.tableBody?.addEventListener('click', (e) => {
            const editBtn = e.target.closest('[data-edit-date]');
            if (editBtn) {
                this.openModal(editBtn.getAttribute('data-edit-date'));
                return;
            }
            const resetBtn = e.target.closest('[data-reset-date]');
            if (resetBtn) {
                this.resetDay(resetBtn.getAttribute('data-reset-date'));
            }
        });
    }

    initDefaults() {
        // Заведение по умолчанию: текущее из верхнего селектора, если это конкретный
        // бар; иначе первый бар — чтобы сразу были доступны кнопки редактирования.
        const REAL = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'];
        if (this.venueSelect) {
            this.venueSelect.value = REAL.includes(state.currentVenue) ? state.currentVenue : 'bolshoy';
        }
        // Месяц/год по умолчанию — из текущего периода либо текущая дата
        const src = (state.currentPeriod && state.currentPeriod.start)
            || new Date().toISOString().slice(0, 10);
        const [y, m] = src.split('-');
        if (this.monthSelect && m) this.monthSelect.value = m;
        if (this.yearSelect && y && [...this.yearSelect.options].some(o => o.value === y)) {
            this.yearSelect.value = y;
        }
    }

    switchSubtab(btn) {
        const target = btn.getAttribute('data-subtab');
        document.querySelectorAll('.plans-subtab-btn').forEach(b => {
            b.classList.toggle('active', b === btn);
        });
        document.querySelectorAll('.plans-sub-content').forEach(c => {
            c.classList.toggle('active', c.id === target);
        });
        if (target === 'plans-sub-daily') {
            this.loadData();
        }
    }

    isDailyActive() {
        const el = document.getElementById('plans-sub-daily');
        return !!(el && el.classList.contains('active'));
    }

    _venue() {
        return this.venueSelect ? this.venueSelect.value : 'all';
    }

    async loadData() {
        if (!this.isDailyActive()) return;

        const venue = this._venue();
        const year = this.yearSelect?.value;
        const month = this.monthSelect ? parseInt(this.monthSelect.value, 10) : null;
        if (!year || !month) return;

        this.showLoading();
        try {
            const payload = await getDailyBreakdown(venue, year, month);
            this.currentPayload = payload;
            this.displayData(payload);
        } catch (error) {
            console.error('[DAILY] Ошибка загрузки разбивки:', error);
            state.addMessage('error', 'Не удалось загрузить подневную разбивку: ' + error.message);
            this.showNoData();
        }
    }

    displayData(payload) {
        const venueName = VENUE_NAMES[payload.venue] || payload.venue;
        const suffix = payload.editable ? '' : ' — агрегат (только просмотр)';
        this.venueLabel.textContent = `Заведение: ${venueName}${suffix}`;

        // Нет месячного плана — показываем заглушку
        if (!payload.days || !payload.days.length || !payload.monthly_revenue) {
            this.showNoData();
            return;
        }

        // Рендер строк
        this.tableBody.innerHTML = '';
        payload.days.forEach(day => {
            this.tableBody.appendChild(this.createDayRow(day, payload.editable));
        });

        // Футер-валидация
        this.sumValue.textContent = formatMoney(payload.daily_sum);
        this.monthlyValue.textContent = formatMoney(payload.monthly_revenue);
        if (payload.sum_check) {
            this.sumCheck.textContent = 'Совпадает: Да';
            this.sumCheck.className = 'daily-check ok';
        } else {
            this.sumCheck.textContent = 'Совпадает: Нет';
            this.sumCheck.className = 'daily-check bad';
        }

        this.showTable();
    }

    createDayRow(day, editable) {
        const tr = document.createElement('tr');
        if (day.weekday === 4 || day.weekday === 5) tr.classList.add('weekend-day');
        if (day.is_override) tr.classList.add('override-day');

        const weightText = day.weight == null ? '—' : String(day.weight);

        let actionHtml = '<span class="value-col">—</span>';
        if (editable) {
            actionHtml = `<button class="btn btn-secondary btn-day" data-edit-date="${day.date}">Изменить</button>`;
            if (day.is_override) {
                actionHtml += `<button class="btn btn-secondary btn-day" data-reset-date="${day.date}">Сброс</button>`;
            }
        }

        tr.innerHTML = `
            <td class="metric-name">${this.formatDate(day.date)}</td>
            <td>${day.weekday_name}</td>
            <td class="value-col">${weightText}</td>
            <td class="value-col">${formatValue(day.daily_plan, 'money')}</td>
            <td class="value-col daily-action-col">${actionHtml}</td>
        `;
        return tr;
    }

    formatDate(dateString) {
        const [year, month, day] = dateString.split('-');
        return `${day}.${month}.${year}`;
    }

    // --- модалка веса дня ---

    openModal(dateStr) {
        if (!this.currentPayload) return;
        const day = this.currentPayload.days.find(d => d.date === dateStr);
        if (!day) return;
        this.editingDate = dateStr;
        this.modalDate.textContent = `${this.formatDate(dateStr)} (${day.weekday_name})`;
        this.weightInput.value = day.weight != null ? day.weight : '';
        this.modal.classList.remove('hidden');
    }

    closeModal() {
        this.modal.classList.add('hidden');
        this.editingDate = null;
    }

    async saveWeight() {
        if (!this.editingDate) return;
        const weight = parseFloat(this.weightInput.value);
        if (isNaN(weight) || weight < 0) {
            state.addMessage('error', 'Вес дня должен быть числом не меньше 0');
            return;
        }
        const venue = this._venue();
        const year = this.yearSelect.value;
        const month = parseInt(this.monthSelect.value, 10);
        try {
            const payload = await setDayWeight(venue, year, month, this.editingDate, weight);
            this.currentPayload = payload;
            this.displayData(payload);
            state.addMessage('success', `Вес дня ${this.formatDate(this.editingDate)} сохранён`);
            this.closeModal();
        } catch (error) {
            state.addMessage('error', 'Не удалось сохранить вес дня: ' + error.message);
        }
    }

    async resetWeightFromModal() {
        if (!this.editingDate) return;
        await this.resetDay(this.editingDate);
        this.closeModal();
    }

    async resetDay(dateStr) {
        const venue = this._venue();
        const year = this.yearSelect.value;
        const month = parseInt(this.monthSelect.value, 10);
        try {
            const payload = await resetDayWeight(venue, year, month, dateStr);
            this.currentPayload = payload;
            this.displayData(payload);
            state.addMessage('success', `Вес дня ${this.formatDate(dateStr)} сброшен к умолчанию`);
        } catch (error) {
            state.addMessage('error', 'Не удалось сбросить вес дня: ' + error.message);
        }
    }

    // --- состояния отображения ---

    showLoading() {
        this.loadingState?.classList.remove('hidden');
        this.noDataState?.classList.add('hidden');
        this.tableContainer?.classList.add('hidden');
        this.footer?.classList.add('hidden');
    }

    showNoData() {
        this.loadingState?.classList.add('hidden');
        this.noDataState?.classList.remove('hidden');
        this.tableContainer?.classList.add('hidden');
        this.footer?.classList.add('hidden');
    }

    showTable() {
        this.loadingState?.classList.add('hidden');
        this.noDataState?.classList.add('hidden');
        this.tableContainer?.classList.remove('hidden');
        this.footer?.classList.remove('hidden');
    }
}

export const dailyPlansViewer = new DailyPlansViewer();

/**
 * Модуль управления плановыми показателями
 * Просмотр, создание, редактирование и удаление планов
 */

import { state } from '../core/state.js';
import { getPlan, getAnalytics, savePlan, deletePlan, calculatePlan } from '../core/api.js';
import { METRICS } from '../core/config.js';
import {
    formatValue,
    calculatePercent,
    calculateDiff,
    getStatus
} from '../core/utils.js';

class PlansViewer {
    constructor() {
        this.loadingState = document.getElementById('plans-loading');
        this.noDataState = document.getElementById('plans-no-data');
        this.tableContainer = document.getElementById('plans-table-container');
        this.tableBody = document.getElementById('plans-table-body');

        // Кнопки управления
        this.btnCreatePlan = document.getElementById('btn-create-plan');
        this.btnEditPlan = document.getElementById('btn-edit-plan');
        this.btnDeletePlan = document.getElementById('btn-delete-plan');
        this.btnCreateFromNoData = document.getElementById('btn-create-from-no-data');

        // Модальное окно
        this.modal = document.getElementById('plan-edit-modal');
        this.modalCloseBtn = document.getElementById('modal-close-btn');
        this.btnCancelPlan = document.getElementById('btn-cancel-plan');
        this.btnSavePlan = document.getElementById('btn-save-plan');
        this.modalTitle = document.getElementById('modal-title');
        this.validationError = document.getElementById('plan-validation-error');
        this.validationErrorText = document.getElementById('validation-error-text');
        this.sharesSumLabel = document.getElementById('shares-sum-label');

        // Поля формы
        this.formFields = {
            revenue: document.getElementById('plan-revenue'),
            checks: document.getElementById('plan-checks'),
            averageCheck: document.getElementById('plan-averageCheck'),
            profit: document.getElementById('plan-profit'),
            draftShare: document.getElementById('plan-draftShare'),
            packagedShare: document.getElementById('plan-packagedShare'),
            kitchenShare: document.getElementById('plan-kitchenShare'),
            revenueDraft: document.getElementById('plan-revenueDraft'),
            revenuePackaged: document.getElementById('plan-revenuePackaged'),
            revenueKitchen: document.getElementById('plan-revenueKitchen'),
            markupPercent: document.getElementById('plan-markupPercent'),
            markupDraft: document.getElementById('plan-markupDraft'),
            markupPackaged: document.getElementById('plan-markupPackaged'),
            markupKitchen: document.getElementById('plan-markupKitchen'),
            loyaltyWriteoffs: document.getElementById('plan-loyaltyWriteoffs'),
            tapActivity: document.getElementById('plan-tapActivity')
        };

        this.initialized = false;
        this.currentPlan = null;
        this.currentPeriodKey = null;
        this.modalPeriodDisplay = document.getElementById('modal-period-display');

        // Селектор модального окна
        this.planMonthSelect = null;
        this.planYearSelect = null;
        this.planVenueSelect = null;
        this.planMetricsSection = null;
        this.btnLoadPlanFooter = null;
        this.selectedVenue = null;
        this.selectedPeriodKey = null;
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
        // Подписка на изменения состояния
        state.subscribe((event) => {
            if (event === 'venueChanged' || event === 'periodChanged') {
                this.loadData();
            }
        });

        // Кнопки управления
        this.btnCreatePlan?.addEventListener('click', () => this.createPlan());
        this.btnEditPlan?.addEventListener('click', () => this.editPlan());
        this.btnDeletePlan?.addEventListener('click', () => this.deletePlan());
        this.btnCreateFromNoData?.addEventListener('click', () => this.createPlan());

        // Модальное окно
        this.modalCloseBtn?.addEventListener('click', () => this.closeModal());
        this.btnCancelPlan?.addEventListener('click', () => this.closeModal());
        this.btnSavePlan?.addEventListener('click', () => this.savePlan());

        // Кнопки модального окна
        const btnDeletePlanModal = document.getElementById('btn-delete-plan-modal');
        btnDeletePlanModal?.addEventListener('click', () => this.deletePlan());

        // Селектор модального окна
        this.planMonthSelect = document.getElementById('plan-month-select');
        this.planYearSelect = document.getElementById('plan-year-select');
        this.planVenueSelect = document.getElementById('plan-venue-select');
        this.planMetricsSection = document.getElementById('plan-metrics-section');
        this.btnLoadPlanFooter = null;

        // Автозагрузка плана при изменении селекторов
        this.planMonthSelect?.addEventListener('change', () => this.loadPlanFromModal());
        this.planYearSelect?.addEventListener('change', () => this.loadPlanFromModal());
        this.planVenueSelect?.addEventListener('change', () => this.loadPlanFromModal());

        // Закрытие по клику вне окна
        this.modal?.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.closeModal();
            }
        });

        // Авто-расчёт производных метрик при изменении долей
        const shareInputs = this.formFields.draftShare?.parentElement?.parentElement?.querySelectorAll('.share-input');
        shareInputs?.forEach(input => {
            input.addEventListener('input', () => {
                this.updateSharesSum();
                this.autoCalculateDerivedMetrics();
            });
        });

        // Авто-расчёт общей наценки при изменении наценок по категориям
        this.formFields.markupDraft?.addEventListener('input', () => this.autoCalculateDerivedMetrics());
        this.formFields.markupPackaged?.addEventListener('input', () => this.autoCalculateDerivedMetrics());
        this.formFields.markupKitchen?.addEventListener('input', () => this.autoCalculateDerivedMetrics());

        // Авто-расчёт при изменении выручки
        this.formFields.revenue?.addEventListener('input', () => {
            this.autoCalculateDerivedMetrics();
        });
    }

    /**
     * Обновить сумму долей
     */
    updateSharesSum() {
        const draft = parseFloat(this.formFields.draftShare?.value) || 0;
        const packaged = parseFloat(this.formFields.packagedShare?.value) || 0;
        const kitchen = parseFloat(this.formFields.kitchenShare?.value) || 0;
        const sum = draft + packaged + kitchen;

        this.sharesSumLabel.textContent = `Сумма: ${sum.toFixed(1)}%`;

        if (Math.abs(sum - 100) > 1) {
            this.sharesSumLabel.classList.add('error');
        } else {
            this.sharesSumLabel.classList.remove('error');
        }
    }

    /**
     * Авто-расчёт производных метрик
     */
    autoCalculateDerivedMetrics() {
        const revenue = parseFloat(this.formFields.revenue?.value) || 0;
        const draftShare = parseFloat(this.formFields.draftShare?.value) || 0;
        const packagedShare = parseFloat(this.formFields.packagedShare?.value) || 0;
        const kitchenShare = parseFloat(this.formFields.kitchenShare?.value) || 0;

        // Выручка по категориям
        if (this.formFields.revenueDraft) {
            this.formFields.revenueDraft.value = (revenue * draftShare / 100).toFixed(2);
        }
        if (this.formFields.revenuePackaged) {
            this.formFields.revenuePackaged.value = (revenue * packagedShare / 100).toFixed(2);
        }
        if (this.formFields.revenueKitchen) {
            this.formFields.revenueKitchen.value = (revenue * kitchenShare / 100).toFixed(2);
        }

        // Общая наценка как взвешенное среднее наценок по категориям
        // Формула: markupPercent = (draftMarkup × draftShare + packagedMarkup × packagedShare + kitchenMarkup × kitchenShare) / 100
        const markupDraft = parseFloat(this.formFields.markupDraft?.value) || 0;
        const markupPackaged = parseFloat(this.formFields.markupPackaged?.value) || 0;
        const markupKitchen = parseFloat(this.formFields.markupKitchen?.value) || 0;

        if (this.formFields.markupPercent) {
            const weightedMarkup = (markupDraft * draftShare + markupPackaged * packagedShare + markupKitchen * kitchenShare) / 100;
            this.formFields.markupPercent.value = weightedMarkup.toFixed(2);
        }
    }

    /**
     * Загрузить план и факт
     */
    async loadData() {
        if (!state.currentVenue || !state.currentPeriod) {
            return;
        }

        this.showLoading();
        this.updateButtonStates(false);

        try {
            // Для планов используем месячный ключ: venue_YYYY-MM
            const periodDate = state.currentPeriod.start;
            const dateObj = new Date(periodDate);
            const year = dateObj.getFullYear();
            const month = String(dateObj.getMonth() + 1).padStart(2, '0');
            this.currentPeriodKey = `${year}-${month}`;

            // Загружаем план и факт параллельно
            const [planResult, actualResult] = await Promise.allSettled([
                getPlan(state.currentVenue, this.currentPeriodKey),
                getAnalytics(
                    state.currentVenue,
                    state.currentPeriod.start,
                    state.currentPeriod.end
                )
            ]);

            // Извлекаем план (может быть null если не найден)
            this.currentPlan = planResult.status === 'fulfilled' ? planResult.value : null;
            this.currentActual = actualResult.status === 'fulfilled' ? actualResult.value : null;

            // Проверяем что факт загрузился успешно
            if (actualResult.status === 'rejected') {
                throw new Error('Не удалось загрузить фактические данные');
            }

            const actual = actualResult.value;

            // Отображаем данные
            this.displayData(this.currentPlan, actual);

        } catch (error) {
            console.error('Ошибка загрузки данных:', error);
            state.addMessage('error', 'Не удалось загрузить данные');
            this.hideLoading();
        }
    }

    /**
     * Обновить состояние кнопок
     */
    updateButtonStates(hasPlan) {
        // Кнопки активны только если есть план
        if (this.btnEditPlan) {
            this.btnEditPlan.disabled = !hasPlan;
        }
        if (this.btnDeletePlan) {
            this.btnDeletePlan.disabled = !hasPlan;
        }
    }

    /**
     * Отобразить данные в таблице
     */
    displayData(plan, actual) {
        this.hideLoading();
        this.hideNoData();
        this.showTable();

        // Обновляем состояние кнопок
        this.updateButtonStates(!!plan);

        // Очищаем таблицу
        this.tableBody.innerHTML = '';

        // Группировка метрик по секциям
        const sections = [
            {
                name: 'Основные показатели',
                metrics: ['revenue', 'checks', 'averageCheck']
            },
            {
                name: 'Доли категорий',
                metrics: ['draftShare', 'packagedShare', 'kitchenShare']
            },
            {
                name: 'Выручка по категориям',
                metrics: ['revenueDraft', 'revenuePackaged', 'revenueKitchen']
            },
            {
                name: 'Наценка и прибыль',
                metrics: ['markupPercent', 'profit', 'markupDraft', 'markupPackaged', 'markupKitchen']
            },
            {
                name: 'Прочее',
                metrics: ['loyaltyWriteoffs', 'tapActivity']
            }
        ];

        // Создаем строки таблицы по секциям
        sections.forEach(section => {
            // Заголовок секции
            const headerRow = document.createElement('tr');
            headerRow.className = 'section-header';
            headerRow.innerHTML = `
                <td colspan="5">${section.name}</td>
            `;
            this.tableBody.appendChild(headerRow);

            // Метрики секции
            section.metrics.forEach(metricId => {
                const metric = METRICS.find(m => m.planKey === metricId);
                if (!metric) return;

                let planValue = plan ? plan[metric.planKey] : null;
                const actualValue = actual[metric.actualKey];

                // Для активности кранов план всегда 100% (если не задан вручную)
                if (metric.id === 'tapActivity' && !planValue) {
                    planValue = 100;
                }

                const row = this.createMetricRow(
                    metric,
                    planValue,
                    actualValue
                );

                this.tableBody.appendChild(row);
            });
        });

        // Если нет плана - показываем состояние "нет данных"
        if (!plan) {
            this.showNoData();
        }
    }

    /**
     * Создать строку таблицы для метрики
     */
    createMetricRow(metric, planValue, actualValue) {
        const row = document.createElement('tr');

        // Вычисляем процент и отклонение
        const percent = planValue ? calculatePercent(actualValue, planValue) : null;
        const diff = planValue ? calculateDiff(actualValue, planValue) : null;
        const status = planValue ? getStatus(percent) : 'neutral';

        // Форматируем значения
        const formattedPlan = planValue !== null ? formatValue(planValue, metric.format) : '—';
        const formattedActual = formatValue(actualValue, metric.format);
        const formattedDiff = diff !== null ? formatValue(Math.abs(diff), metric.format) : '—';
        const formattedPercent = percent !== null ? `${percent.toFixed(1)}%` : '—';

        // Класс для отклонения
        let diffClass = 'neutral';
        if (diff !== null) {
            if (diff > 0) diffClass = 'positive';
            else if (diff < 0) diffClass = 'negative';
        }

        // Префикс для отклонения
        const diffPrefix = diff !== null && diff > 0 ? '+' : '';

        // HTML строки
        row.innerHTML = `
            <td class="metric-name">${metric.name}</td>
            <td class="value-col plan-col">${formattedPlan}</td>
            <td class="value-col fact-col">${formattedActual}</td>
            <td class="value-col diff-col ${diffClass}">${diffPrefix}${formattedDiff}</td>
            <td class="value-col percent-col ${status}">${formattedPercent}</td>
        `;

        return row;
    }

    /**
     * Создать новый план (открыть модальное окно)
     */
    createPlan() {
        // Просто открываем модальное окно с выбором месяца
        this.openCreateModal();
    }

    /**
     * Открыть модальное окно создания плана
     */
    openCreateModal() {
        this.modalTitle.textContent = 'Плановые показатели';

        // Устанавливаем текущий месяц и год
        const now = new Date();
        if (this.planMonthSelect) {
            this.planMonthSelect.value = String(now.getMonth() + 1).padStart(2, '0');
        }
        if (this.planYearSelect) {
            this.planYearSelect.value = now.getFullYear().toString();
        }
        if (this.planVenueSelect) {
            this.planVenueSelect.value = state.currentVenue || 'all';
        }

        // Отключаем секцию метрик до загрузки
        this.setMetricsEnabled(false);
        this.currentPlan = null;
        this.updateDeleteButton(false);

        // Показываем модальное окно
        this.modal?.classList.remove('hidden');

        // Автозагрузка плана
        this.loadPlanFromModal();
    }

    /**
     * Обновить кнопку удаления
     */
    updateDeleteButton(hasPlan) {
        if (this.btnDeletePlanModal) {
            this.btnDeletePlanModal.style.display = hasPlan ? 'inline-flex' : 'none';
        }
    }

    /**
     * Показать/скрыть секцию метрик
     */
    setMetricsEnabled(enabled) {
        if (this.planMetricsSection) {
            this.planMetricsSection.style.opacity = enabled ? '1' : '0.5';
            this.planMetricsSection.style.pointerEvents = enabled ? 'auto' : 'none';
        }
    }

    /**
     * Загрузить план из модального окна (автозагрузка при изменении селекторов)
     */
    async loadPlanFromModal() {
        const month = this.planMonthSelect?.value;
        const year = this.planYearSelect?.value;
        const venue = this.planVenueSelect?.value;

        if (!month || !year || !venue) {
            return;
        }

        this.selectedVenue = venue;
        this.selectedPeriodKey = `${year}-${month}`;

        try {
            const plan = await getPlan(venue, this.selectedPeriodKey);

            if (plan) {
                // План найден - заполняем форму
                this.fillPlanForm(plan);
                this.setMetricsEnabled(true);
                this.updateDeleteButton(true);
                this.modalTitle.textContent = 'Редактирование плана';

                // Обновляем подзаголовок с выбранным периодом
                const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                                   'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
                const monthName = monthNames[parseInt(month) - 1];
                const venueNames = {
                    'all': 'Все заведения',
                    'bolshoy': 'Большой пр. В.О',
                    'ligovskiy': 'Лиговский',
                    'kremenchugskaya': 'Кременчугская',
                    'varshavskaya': 'Варшавская'
                };
                if (this.modalPeriodDisplay) {
                    this.modalPeriodDisplay.textContent = `${venueNames[venue] || venue} — ${monthName} ${year}`;
                    this.modalPeriodDisplay.classList.remove('error');
                }

            } else {
                // План не найден - создаём пустой
                const emptyPlan = this.createEmptyPlan();
                this.fillPlanForm(emptyPlan);
                this.setMetricsEnabled(true);
                this.updateDeleteButton(false);
                this.modalTitle.textContent = 'Создание плана';

                if (this.modalPeriodDisplay) {
                    const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                                       'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
                    const monthName = monthNames[parseInt(month) - 1];
                    this.modalPeriodDisplay.textContent = `Создание плана на ${monthName} ${year}`;
                    this.modalPeriodDisplay.classList.remove('error');
                }
            }

        } catch (error) {
            console.error('Ошибка загрузки плана:', error);
        }
    }

    /**
     * Заполнить форму данными плана
     */
    fillPlanForm(planData) {
        this.currentPlan = planData;

        for (const [key, value] of Object.entries(planData)) {
            const field = this.formFields[key];
            if (field && value !== null && value !== undefined) {
                field.value = typeof value === 'number' ? value.toFixed(2) : value;
            }
        }

        // Обновляем сумму долей
        this.updateSharesSum();
        // Авто-расчёт производных метрик
        this.autoCalculateDerivedMetrics();
    }

    /**
     * Создать пустой план с дефолтными значениями
     */
    createEmptyPlan() {
        return {
            revenue: 0,
            checks: 0,
            averageCheck: 0,
            profit: 0,
            draftShare: 60,
            packagedShare: 25,
            kitchenShare: 15,
            revenueDraft: 0,
            revenuePackaged: 0,
            revenueKitchen: 0,
            markupPercent: 200,
            markupDraft: 250,
            markupPackaged: 120,
            markupKitchen: 160,
            loyaltyWriteoffs: 0,
            tapActivity: 100
        };
    }

    /**
     * Редактировать текущий план
     */
    editPlan() {
        // Просто открываем модальное окно с выбором месяца
        this.openCreateModal();
    }

    /**
     * Открыть модальное окно редактирования
     */
    openModal(planData, title) {
        this.modalTitle.textContent = title;

        // Отображаем период (месяц) в модальном окне
        const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                           'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
        const [year, month] = this.currentPeriodKey.split('-');
        const monthName = monthNames[parseInt(month) - 1];
        const periodText = `${monthName} ${year}`;

        if (this.modalPeriodDisplay) {
            this.modalPeriodDisplay.textContent = `Период: ${periodText}`;
            this.modalPeriodDisplay.classList.remove('error');
        }

        this.hideValidationError();

        // Заполняем поля формы
        for (const [key, value] of Object.entries(planData)) {
            const field = this.formFields[key];
            if (field && value !== null && value !== undefined) {
                field.value = typeof value === 'number' ? value.toFixed(2) : value;
            }
        }

        // Обновляем сумму долей
        this.updateSharesSum();

        // Показываем модальное окно
        this.modal?.classList.remove('hidden');
    }

    /**
     * Закрыть модальное окно
     */
    closeModal() {
        this.modal?.classList.add('hidden');
        this.currentPlan = null;
    }

    /**
     * Показать ошибку валидации
     */
    showValidationError(message) {
        this.validationErrorText.textContent = message;
        this.validationError?.classList.remove('hidden');
    }

    /**
     * Скрыть ошибку валидации
     */
    hideValidationError() {
        this.validationError?.classList.add('hidden');
    }

    /**
     * Валидировать данные плана
     */
    validatePlanData(planData) {
        // Проверка всех обязательных полей
        const requiredFields = [
            'revenue', 'checks', 'averageCheck', 'profit',
            'draftShare', 'packagedShare', 'kitchenShare',
            'revenueDraft', 'revenuePackaged', 'revenueKitchen',
            'markupPercent', 'markupDraft', 'markupPackaged', 'markupKitchen',
            'loyaltyWriteoffs', 'tapActivity'
        ];

        for (const field of requiredFields) {
            const value = planData[field];
            if (value === null || value === undefined || value === '') {
                return { valid: false, message: `Заполните поле "${this.getFieldLabel(field)}"` };
            }
            if (typeof value === 'number' && value < 0) {
                return { valid: false, message: `Поле "${this.getFieldLabel(field)}" не может быть отрицательным` };
            }
        }

        // Проверка суммы долей
        const sharesSum = (planData.draftShare || 0) + (planData.packagedShare || 0) + (planData.kitchenShare || 0);
        if (Math.abs(sharesSum - 100) > 1) {
            return { valid: false, message: `Сумма долей категорий должна быть 100% (сейчас ${sharesSum.toFixed(1)}%)` };
        }

        return { valid: true };
    }

    /**
     * Получить человеко-читаемое название поля
     */
    getFieldLabel(key) {
        const labels = {
            revenue: 'Выручка',
            checks: 'Чеки',
            averageCheck: 'Средний чек',
            profit: 'Прибыль',
            draftShare: 'Доля розлива',
            packagedShare: 'Доля фасовки',
            kitchenShare: 'Доля кухни',
            revenueDraft: 'Выручка розлив',
            revenuePackaged: 'Выручка фасовка',
            revenueKitchen: 'Выручка кухня',
            markupPercent: 'Общая наценка',
            markupDraft: 'Наценка розлив',
            markupPackaged: 'Наценка фасовка',
            markupKitchen: 'Наценка кухня',
            loyaltyWriteoffs: 'Списания баллов',
            tapActivity: 'Активность кранов'
        };
        return labels[key] || key;
    }

    /**
     * Сохранить план
     */
    async savePlan() {
        // Собираем данные из формы
        const planData = {};
        for (const [key, field] of Object.entries(this.formFields)) {
            if (field) {
                const value = parseFloat(field.value);
                planData[key] = isNaN(value) ? 0 : value;
            }
        }

        // Валидация
        const validation = this.validatePlanData(planData);
        if (!validation.valid) {
            this.showValidationError(validation.message);
            return;
        }

        if (!this.selectedVenue || !this.selectedPeriodKey) {
            state.addMessage('error', 'Не выбрано заведение или период');
            return;
        }

        try {
            // Backend создаст составной ключ: venue_YYYY-MM
            await savePlan(this.selectedVenue, this.selectedPeriodKey, planData);

            state.addMessage('success', 'План сохранён');
            this.currentPlan = planData;

            // Перезагружаем данные если текущее заведение и период совпадают
            if (state.currentVenue === this.selectedVenue) {
                const currentMonthKey = this.selectedPeriodKey;
                if (this.currentPeriodKey === currentMonthKey) {
                    await this.loadData();
                }
            }

            // Обновляем таблицу с новыми данными
            this.displayData(this.currentPlan, this.currentActual || {}, true);

        } catch (error) {
            console.error('Ошибка сохранения плана:', error);
            state.addMessage('error', 'Не удалось сохранить план: ' + error.message);
        }
    }

    /**
     * Удалить план
     */
    async deletePlan() {
        if (!this.currentPlan) {
            state.addMessage('warning', 'Нет плана для удаления');
            return;
        }

        if (!confirm('Вы уверены, что хотите удалить план? Это действие нельзя отменить.')) {
            return;
        }

        if (!this.selectedVenue || !this.selectedPeriodKey) {
            state.addMessage('error', 'Не выбрано заведение или период');
            return;
        }

        try {
            // Backend создаст составной ключ: venue_YYYY-MM
            await deletePlan(this.selectedVenue, this.selectedPeriodKey);

            state.addMessage('success', 'План удалён');
            this.currentPlan = null;

            // Перезагружаем данные если текущее заведение и период совпадают
            if (state.currentVenue === this.selectedVenue) {
                const currentMonthKey = this.selectedPeriodKey;
                if (this.currentPeriodKey === currentMonthKey) {
                    await this.loadData();
                }
            }

            // Обновляем таблицу
            this.displayData(null, this.currentActual || {}, true);

        } catch (error) {
            console.error('Ошибка удаления плана:', error);
            state.addMessage('error', 'Не удалось удалить план: ' + error.message);
        }
    }

    /**
     * Показать состояние загрузки
     */
    showLoading() {
        this.loadingState?.classList.remove('hidden');
        this.noDataState?.classList.add('hidden');
        this.tableContainer?.classList.add('hidden');
    }

    /**
     * Скрыть состояние загрузки
     */
    hideLoading() {
        this.loadingState?.classList.add('hidden');
    }

    /**
     * Показать таблицу
     */
    showTable() {
        this.tableContainer?.classList.remove('hidden');
    }

    /**
     * Скрыть таблицу
     */
    hideTable() {
        this.tableContainer?.classList.add('hidden');
    }

    /**
     * Показать состояние "нет данных"
     */
    showNoData() {
        this.noDataState?.classList.remove('hidden');
        this.tableContainer?.classList.add('hidden');
    }

    /**
     * Скрыть состояние "нет данных"
     */
    hideNoData() {
        this.noDataState?.classList.add('hidden');
    }

    /**
     * Обновить данные
     */
    refresh() {
        this.loadData();
    }
}

// Экспортируем единственный экземпляр
export const plansViewer = new PlansViewer();

/**
 * Единая панель периода в верхнем баре.
 *
 *   [День|Неделя|Месяц|Год]  [<]  подпись периода  [>]  [Сегодня]
 *                                 вторая строка: «неделя 32 · 7 дней»
 *
 * Одна панель на все вкладки (раньше «Аналитика» имела диапазон-пикер, а
 * «Выручка»/«Планы» — отдельные селекты Месяц+Год, которые жили своей жизнью).
 *
 * Что делает модуль:
 *   - держит период в state (единственный источник — state.currentPeriod);
 *   - листает стрелками шагом выбранной гранулярности;
 *   - открывает Flatpickr по клику на подпись (день -> одна дата, иначе диапазон);
 *   - гасит гранулярности, неприменимые к активной вкладке;
 *   - показывает бейдж незавершённого периода;
 *   - дебаунсит применение периода, чтобы серия кликов по стрелке не превратилась
 *     в серию холодных OLAP-запросов (см. docs/lessons.md, урок про стампед).
 *
 * Вся арифметика дат — в core/period_model.js, здесь только DOM и события.
 */

import { state } from '../core/state.js';
import {
    CUSTOM,
    changeGranularity,
    currentPeriodFor,
    formatSubLabel,
    fromISO,
    periodFromSelection,
    progressBadge,
    shiftPeriod,
    today
} from '../core/period_model.js';

/**
 * Пауза перед применением периода после клика по стрелке.
 * 350 мс: успеваешь долистать до нужной недели, не отправив запрос на каждый шаг.
 * Подпись при этом обновляется мгновенно — ощущение мгновенного отклика есть,
 * дорогой запрос уходит один.
 */
const APPLY_DEBOUNCE_MS = 350;

/**
 * Какие гранулярности осмысленны на каждой вкладке.
 *
 * tab-revenue  — все четыре: эндпоинт /api/revenue-metrics принимает явные границы
 *                периода и считает «Ожидаемую» и «% выполнения» относительно них.
 * tab-plans    — только месяц и год: планы хранятся помесячно (ключ venue_YYYY-MM),
 *                день и неделю не к чему привязать; год = сумма месячных планов.
 * tab-comparison — панель скрыта целиком, у вкладки свои Период 1 / Период 2.
 */
const TAB_GRANULARITIES = {
    'tab-analytics': ['day', 'week', 'month', 'year'],
    'analytics': ['day', 'week', 'month', 'year'],
    'tab-revenue': ['day', 'week', 'month', 'year'],
    'tab-plans': ['month', 'year']
};

const HIDDEN_TABS = ['tab-comparison'];

const DISABLED_HINT = {
    'tab-plans': 'Планы задаются на месяц — день и неделя недоступны'
};

class PeriodControls {
    constructor() {
        this.initialized = false;
        this.pendingPeriod = null;   // период, показанный в панели, но ещё не применённый
        this.applyTimer = null;
        this.flatpickr = null;
    }

    init() {
        if (this.initialized) return;

        this.cacheElements();
        if (!this.bar) {
            // Панели нет в DOM (не-дашбордная страница) — модуль ничего не делает.
            this.initialized = true;
            return;
        }

        this.setupEventListeners();
        this.initFlatpickr();
        this.applyTabVisibility(state.activeTab);
        this.render();

        this.initialized = true;
    }

    cacheElements() {
        this.group = document.getElementById('cg-period');
        this.bar = document.getElementById('period-bar');
        this.granularityBox = document.getElementById('period-granularity');
        this.granularityButtons = Array.from(document.querySelectorAll('.pg-btn'));
        this.btnPrev = document.getElementById('period-prev');
        this.btnNext = document.getElementById('period-next');
        this.btnToday = document.getElementById('period-today');
        this.btnCurrent = document.getElementById('period-current');
        this.labelEl = document.getElementById('period-label');
        this.subLabelEl = document.getElementById('period-sublabel');
        this.warningEl = document.getElementById('period-warning');
        this.pickerInput = document.getElementById('flexi-range-picker');
    }

    setupEventListeners() {
        this.granularityButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                if (btn.disabled) return;
                const g = btn.getAttribute('data-granularity');
                this.setPeriod(changeGranularity(this.viewPeriod(), g), { immediate: true });
            });
        });

        this.btnPrev?.addEventListener('click', () => this.navigate(-1));
        this.btnNext?.addEventListener('click', () => this.navigate(1));
        this.btnToday?.addEventListener('click', () => this.goToCurrent());

        // Клик по подписи открывает календарь — одинаково на десктопе и телефоне.
        // Раньше на телефоне тот же клик разворачивал спрятанные кнопки
        // гранулярности: про этот тап неоткуда было узнать, и сменить
        // день/неделю/месяц/год на телефоне было нельзя. Теперь кнопки видны всегда.
        this.btnCurrent?.addEventListener('click', () => this.openPicker());

        // Клавиши: стрелки листают, Home возвращает к текущему периоду.
        // Игнорируем, когда пользователь печатает в поле или панель скрыта.
        document.addEventListener('keydown', (e) => {
            if (this.group?.classList.contains('hidden')) return;
            if (e.altKey || e.ctrlKey || e.metaKey) return;

            const t = e.target;
            const tag = t && t.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) return;
            // Открытый календарь сам обрабатывает стрелки.
            if (document.querySelector('.flatpickr-calendar.open')) return;

            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                this.navigate(-1);
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                this.navigate(1);
            } else if (e.key === 'Home') {
                e.preventDefault();
                this.goToCurrent();
            }
        });

        state.subscribe((event, data) => {
            if (event === 'tabChanged') {
                this.applyTabVisibility(data);
                this.snapToAllowedGranularity();
                this.render();
            } else if (event === 'periodChanged') {
                // Период мог измениться и не через панель — держим её в согласии со state.
                if (!this.applyTimer) this.render();
            }
        });
    }

    // ============================================================
    // Период: чтение и запись
    // ============================================================

    /** Период, который панель СЕЙЧАС показывает (с учётом ещё не применённого). */
    viewPeriod() {
        return this.pendingPeriod || state.currentPeriod;
    }

    /**
     * Показать период в панели и применить его в state.
     *
     * @param {Object} period — объект из period_model
     * @param {{immediate?: boolean}} opts — immediate:true применяет сразу
     *        (смена гранулярности, календарь, «Сегодня»); стрелки идут через дебаунс.
     */
    setPeriod(period, { immediate = false } = {}) {
        if (!period) return;

        this.pendingPeriod = period;
        this.render();

        clearTimeout(this.applyTimer);
        if (immediate) {
            this.applyTimer = null;
            this.commit();
        } else {
            this.applyTimer = setTimeout(() => {
                this.applyTimer = null;
                this.commit();
            }, APPLY_DEBOUNCE_MS);
        }
    }

    /** Отдать накопленный период в state (отсюда расходятся periodChanged/monthChanged). */
    commit() {
        const period = this.pendingPeriod;
        this.pendingPeriod = null;
        if (!period) return;
        if (state.currentPeriod
            && state.currentPeriod.start === period.start
            && state.currentPeriod.end === period.end) {
            // Границы те же — данные перезапрашивать незачем, но гранулярность
            // (шаг стрелки) могла смениться, поэтому объект в state обновляем молча.
            state.currentPeriod = period;
            return;
        }
        state.setPeriod(period);
    }

    navigate(direction) {
        const next = shiftPeriod(this.viewPeriod(), direction);
        this.setPeriod(next);
    }

    goToCurrent() {
        const view = this.viewPeriod();
        const granularity = (view.granularity && view.granularity !== CUSTOM) ? view.granularity : 'week';
        this.setPeriod(currentPeriodFor(granularity), { immediate: true });
    }

    // ============================================================
    // Календарь
    // ============================================================

    initFlatpickr() {
        if (!this.pickerInput || typeof flatpickr === 'undefined') {
            // Библиотека грузится с CDN — если её нет, панель остаётся рабочей
            // (стрелки и гранулярность), недоступен только выбор даты вручную.
            this.btnCurrent?.setAttribute('title', 'Календарь недоступен: библиотека не загрузилась');
            return;
        }

        this.flatpickr = flatpickr(this.pickerInput, {
            mode: 'range',
            dateFormat: 'd.m.Y',
            locale: 'ru',
            positionElement: this.btnCurrent,
            // Date-объект, НЕ строка: строку Flatpickr парсит своим dateFormat 'd.m.Y'
            // и из '2027-12-31' читает день '20' -> календарь упирается в 20-е число
            // текущего месяца. См. docs/CHANGELOG.md (2026-06).
            maxDate: new Date(2027, 11, 31),
            onChange: (selectedDates) => this.onPickerChange(selectedDates)
        });
    }

    openPicker() {
        if (!this.flatpickr) return;
        const view = this.viewPeriod();
        const isDay = view.granularity === 'day';

        // Режим календаря идёт за гранулярностью: день — одна дата, иначе диапазон.
        this.flatpickr.set('mode', isDay ? 'single' : 'range');
        this.flatpickr.setDate(
            isDay ? [fromISO(view.start)] : [fromISO(view.start), fromISO(view.end)],
            false
        );
        this.flatpickr.open();
    }

    onPickerChange(selectedDates) {
        if (!selectedDates || selectedDates.length === 0) return;

        const view = this.viewPeriod();
        const isDay = view.granularity === 'day';

        if (isDay) {
            this.setPeriod(periodFromSelection(selectedDates[0], selectedDates[0], 'day'), { immediate: true });
            this.flatpickr.close();
            return;
        }

        // Диапазон: ждём вторую дату.
        if (selectedDates.length < 2) return;

        const period = periodFromSelection(selectedDates[0], selectedDates[1], view.granularity);
        const allowed = this.allowedGranularities();
        if (!allowed.includes(period.granularity)) {
            // На вкладке, где выбранная гранулярность запрещена (например день на
            // «Планах»), молча не переключаемся — иначе экран покажет не то, что просили.
            state.addMessage('warning', DISABLED_HINT[state.activeTab]
                || 'Этот период недоступен на текущей вкладке', 3000);
            return;
        }

        this.setPeriod(period, { immediate: true });
        this.flatpickr.close();
    }

    // ============================================================
    // Отрисовка
    // ============================================================

    /** Гранулярности, разрешённые на активной вкладке. */
    allowedGranularities() {
        return TAB_GRANULARITIES[state.activeTab] || TAB_GRANULARITIES['tab-analytics'];
    }

    /**
     * Перейти на ближайшую разрешённую гранулярность, если текущая на этой
     * вкладке недоступна. Пример: смотрел неделю на «Аналитике», переключился на
     * «Планы» -> показываем месяц, в который попадала эта неделя. Без этого
     * «Планы» получили бы недельный период и не нашли месячный ключ плана.
     */
    snapToAllowedGranularity() {
        const period = this.viewPeriod();
        const allowed = this.allowedGranularities();
        if (!period || allowed.includes(period.granularity)) return;

        // Ближайшая по «крупности» разрешённая: месяц — единственный общий знаменатель.
        const target = allowed.includes('month') ? 'month' : allowed[0];
        this.setPeriod(changeGranularity(period, target), { immediate: true });
    }

    render() {
        const period = this.viewPeriod();
        if (!period || !this.labelEl) return;

        this.labelEl.textContent = period.label || `${period.start} - ${period.end}`;
        if (this.subLabelEl) this.subLabelEl.textContent = formatSubLabel(period);

        const allowed = this.allowedGranularities();
        this.granularityButtons.forEach(btn => {
            const g = btn.getAttribute('data-granularity');
            const isAllowed = allowed.includes(g);
            btn.disabled = !isAllowed;
            btn.classList.toggle('active', g === period.granularity);
            btn.title = isAllowed ? '' : (DISABLED_HINT[state.activeTab] || '');
        });

        // Бейдж незавершённого периода. Защита от «смотрю период, который ещё не
        // прошёл, и вижу недовыполнение плана»: план урезается на весь период,
        // а факт есть только за прошедшие дни.
        const badge = progressBadge(period);
        if (this.warningEl) {
            this.warningEl.textContent = badge || '';
            this.warningEl.classList.toggle('hidden', !badge);
        }

        // Вперёд дальше текущего периода листать незачем — данных там нет.
        if (this.btnNext) {
            const nextPeriod = shiftPeriod(period, 1);
            const nextStart = fromISO(nextPeriod.start);
            this.btnNext.disabled = !!(nextStart && nextStart > today());
        }
    }

    /**
     * Показать/скрыть панель под активную вкладку.
     * «Сравнение» прячет её целиком — там свои Период 1 / Период 2.
     */
    applyTabVisibility(tabId) {
        const t = tabId || '';
        this.group?.classList.toggle('hidden', HIDDEN_TABS.includes(t));
    }
}

export const periodControls = new PeriodControls();

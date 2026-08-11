/**
 * Шапка фильтров дашборда (макет 5a/6a).
 *
 *   [ Все заведения ▾ | ‹  Август 2026  1—11 авг ▾  › |            Excel  PDF ]
 *
 * В строке ровно два выбора: заведение и период. Переключателя гранулярности,
 * кнопки «Сегодня» и счётчика дней нет — всё это живёт в выпадающем списке
 * периода, где выбор занимает один клик. Гранулярность задаёт сам пресет:
 * выбрал «Прошлая неделя» — стрелки дальше листают неделями.
 *
 * На телефоне полоса разворачивается в две строки, а списки открываются снизу
 * нижним листом (одна и та же разметка, разные стили).
 *
 * Вся арифметика дат — в core/period_model.js, здесь только DOM и события.
 */

import { state } from '../core/state.js';
import {
    PERIOD_PRESETS,
    changeGranularity,
    fromISO,
    matchPreset,
    periodFromSelection,
    periodHint,
    periodTitle,
    progressBadge,
    shiftPeriod,
    today
} from '../core/period_model.js';

/**
 * Пауза перед применением периода после клика по стрелке.
 * 350 мс: успеваешь долистать до нужной недели, не отправив запрос на каждый шаг.
 * Подпись при этом обновляется мгновенно — отклик есть, дорогой запрос уходит один.
 */
const APPLY_DEBOUNCE_MS = 350;

/**
 * Какие гранулярности осмысленны на каждой вкладке.
 * Неприменимые пресеты в списке гаснут (а не исчезают — список не должен «прыгать»).
 *
 * tab-plans — только месяц и год: планы хранятся помесячно (ключ venue_YYYY-MM),
 *             день, неделю и квартал не к чему привязать.
 * tab-comparison — шапка периода скрыта, у вкладки свои Период 1 / Период 2.
 */
const TAB_GRANULARITIES = {
    'tab-analytics': ['day', 'week', 'month', 'quarter', 'year', 'custom'],
    'analytics': ['day', 'week', 'month', 'quarter', 'year', 'custom'],
    'tab-revenue': ['day', 'week', 'month', 'quarter', 'year', 'custom'],
    'tab-plans': ['month', 'year']
};

const HIDDEN_TABS = ['tab-comparison'];

const DISABLED_HINT = {
    'tab-plans': 'Планы задаются на месяц — доступны только месяц и год'
};

class PeriodControls {
    constructor() {
        this.initialized = false;
        this.pendingPeriod = null;   // период, показанный в шапке, но ещё не применённый
        this.applyTimer = null;
        this.flatpickr = null;
        this.openMenu = null;        // id открытого списка
    }

    init() {
        if (this.initialized) return;

        this.cacheElements();
        if (!this.bar) {
            // Шапки нет в DOM (не-дашбордная страница) — модуль ничего не делает.
            this.initialized = true;
            return;
        }

        this.renderPresetList();
        this.setupEventListeners();
        this.initFlatpickr();
        this.applyTabVisibility(state.activeTab);
        this.render();

        this.initialized = true;
    }

    cacheElements() {
        this.bar = document.getElementById('filter-bar');
        this.group = document.getElementById('cg-period');
        this.btnPrev = document.getElementById('period-prev');
        this.btnNext = document.getElementById('period-next');
        this.trigger = document.getElementById('period-trigger');
        this.titleEl = document.getElementById('period-title');
        this.hintEl = document.getElementById('period-hint');
        this.menu = document.getElementById('period-menu');
        this.presetList = document.getElementById('period-preset-list');
        this.btnCustom = document.getElementById('period-custom');
        this.backdrop = document.getElementById('fb-backdrop');
        this.pickerInput = document.getElementById('flexi-range-picker');
    }

    // ============================================================
    // Список периода
    // ============================================================

    /** Отрисовать пункты быстрого выбора один раз; подсветку обновляет render(). */
    renderPresetList() {
        if (!this.presetList) return;

        this.presetList.innerHTML = '';
        PERIOD_PRESETS.forEach(preset => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'fb-menu-item';
            item.setAttribute('role', 'menuitem');
            item.dataset.preset = preset.id;
            item.innerHTML = `
                <span class="fb-menu-name"></span>
                <span class="fb-menu-hint"></span>
            `;
            item.addEventListener('click', () => {
                if (item.disabled) return;
                this.setPeriod(preset.build(today()), { immediate: true });
                this.closeMenus();
            });
            this.presetList.appendChild(item);
        });
    }

    /** Обновить подписи, подсказки, активный пункт и гашение в списке. */
    updatePresetList() {
        if (!this.presetList) return;

        const now = today();
        const activeId = matchPreset(this.viewPeriod(), now);
        const allowed = this.allowedGranularities();

        PERIOD_PRESETS.forEach(preset => {
            const item = this.presetList.querySelector(`[data-preset="${preset.id}"]`);
            if (!item) return;

            const candidate = preset.build(now);
            const isAllowed = allowed.includes(candidate.granularity);

            item.querySelector('.fb-menu-name').textContent = preset.name;
            // Подсказка — какие это числа: «11 авг», «3—9 авг», «янв—авг».
            item.querySelector('.fb-menu-hint').textContent =
                periodHint(candidate, now, { dayAsDate: true });
            item.classList.toggle('active', preset.id === activeId);
            item.disabled = !isAllowed;
            item.title = isAllowed ? '' : (DISABLED_HINT[state.activeTab] || '');
        });

        if (this.btnCustom) {
            const customAllowed = allowed.includes('custom');
            this.btnCustom.disabled = !customAllowed;
            this.btnCustom.classList.toggle('active', activeId === null);
        }
    }

    // ============================================================
    // Открытие/закрытие списков
    // ============================================================

    toggleMenu(id, triggerEl) {
        if (this.openMenu === id) {
            this.closeMenus();
            return;
        }
        this.closeMenus();

        const menu = document.getElementById(id);
        if (!menu) return;

        menu.classList.remove('hidden');
        this.backdrop?.classList.remove('hidden');
        triggerEl?.setAttribute('aria-expanded', 'true');
        // Список выпадает от своего триггера: на десктопе он абсолютный внутри
        // шапки, поэтому смещение считаем от левого края триггера.
        if (triggerEl && this.bar) {
            const barRect = this.bar.getBoundingClientRect();
            const tRect = triggerEl.getBoundingClientRect();
            menu.style.setProperty('--fb-menu-left', `${Math.round(tRect.left - barRect.left)}px`);
        }
        this.openMenu = id;
    }

    closeMenus() {
        document.querySelectorAll('.fb-menu').forEach(m => m.classList.add('hidden'));
        document.querySelectorAll('[aria-haspopup]').forEach(t => t.setAttribute('aria-expanded', 'false'));
        this.backdrop?.classList.add('hidden');
        this.openMenu = null;
    }

    setupEventListeners() {
        this.btnPrev?.addEventListener('click', () => this.navigate(-1));
        this.btnNext?.addEventListener('click', () => this.navigate(1));

        this.trigger?.addEventListener('click', () => {
            this.updatePresetList();
            this.toggleMenu('period-menu', this.trigger);
        });

        this.btnCustom?.addEventListener('click', () => {
            if (this.btnCustom.disabled) return;
            this.closeMenus();
            this.openPicker();
        });

        this.backdrop?.addEventListener('click', () => this.closeMenus());

        // Клик вне списка закрывает его.
        document.addEventListener('click', (e) => {
            if (!this.openMenu) return;
            const menu = document.getElementById(this.openMenu);
            if (menu?.contains(e.target)) return;
            if (e.target.closest('[aria-haspopup]')) return;
            this.closeMenus();
        });

        // Клавиши: стрелки листают период, Esc закрывает список.
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.openMenu) {
                this.closeMenus();
                return;
            }
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
            }
        });

        state.subscribe((event, data) => {
            if (event === 'tabChanged') {
                this.applyTabVisibility(data);
                this.snapToAllowedGranularity();
                this.render();
            } else if (event === 'periodChanged') {
                // Период мог измениться и не через шапку — держим её в согласии со state.
                if (!this.applyTimer) this.render();
            }
        });
    }

    // ============================================================
    // Период: чтение и запись
    // ============================================================

    /** Период, который шапка СЕЙЧАС показывает (с учётом ещё не применённого). */
    viewPeriod() {
        return this.pendingPeriod || state.currentPeriod;
    }

    /**
     * Показать период в шапке и применить его в state.
     *
     * @param {Object} period — объект из period_model
     * @param {{immediate?: boolean}} opts — immediate:true применяет сразу
     *        (выбор в списке, календарь); стрелки идут через дебаунс.
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
        this.setPeriod(shiftPeriod(this.viewPeriod(), direction));
    }

    // ============================================================
    // Календарь
    // ============================================================

    initFlatpickr() {
        if (!this.pickerInput || typeof flatpickr === 'undefined') {
            // Библиотека грузится с CDN — если её нет, шапка остаётся рабочей
            // (стрелки и пресеты), недоступен только «Свой период».
            this.btnCustom?.setAttribute('title', 'Календарь недоступен: библиотека не загрузилась');
            return;
        }

        this.flatpickr = flatpickr(this.pickerInput, {
            mode: 'range',
            dateFormat: 'd.m.Y',
            locale: 'ru',
            positionElement: this.trigger,
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
        this.flatpickr.setDate([fromISO(view.start), fromISO(view.end)], false);
        this.flatpickr.open();
    }

    onPickerChange(selectedDates) {
        if (!selectedDates || selectedDates.length < 2) return;

        const period = periodFromSelection(selectedDates[0], selectedDates[1], null);
        if (!this.allowedGranularities().includes(period.granularity)) {
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

        const target = allowed.includes('month') ? 'month' : allowed[0];
        this.setPeriod(changeGranularity(period, target), { immediate: true });
    }

    render() {
        const period = this.viewPeriod();
        if (!period || !this.titleEl) return;

        this.titleEl.textContent = periodTitle(period);

        // Подсказка: какие это числа. Для незавершённого периода — прошедшая часть,
        // то есть ровно тот диапазон, за который на экране есть факт. Отдельного
        // счётчика дней в шапке нет (макет 5a), поэтому предупреждение о
        // незавершённости уходит в подсказку title.
        if (this.hintEl) {
            this.hintEl.textContent = periodHint(period);
            const badge = progressBadge(period);
            this.hintEl.title = badge || '';
        }

        this.updatePresetList();

        // Вперёд дальше текущего периода листать незачем — данных там нет.
        if (this.btnNext) {
            const nextStart = fromISO(shiftPeriod(period, 1).start);
            this.btnNext.disabled = !!(nextStart && nextStart > today());
        }
    }

    /**
     * Показать/скрыть выбор периода под активную вкладку.
     * «Сравнение» прячет его целиком — там свои Период 1 / Период 2.
     */
    applyTabVisibility(tabId) {
        const hide = HIDDEN_TABS.includes(tabId || '');
        this.group?.classList.toggle('hidden', hide);
        if (hide) this.closeMenus();
    }
}

export const periodControls = new PeriodControls();

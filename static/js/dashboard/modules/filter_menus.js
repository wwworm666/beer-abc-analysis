/**
 * Списки заведения и выгрузки в шапке фильтров (макет 5a/6a).
 *
 * Заведение: данные по-прежнему держит скрытый `<select id="venue-selector">` —
 * его наполняет modules/venue_selector.js, он же владеет загрузкой и событием
 * change. Этот модуль — только ВИД над ним: строит пункты из options и при
 * выборе выставляет `select.value` + шлёт `change`. Один источник истины
 * сохраняется, логику загрузки заведений не дублируем.
 *
 * Выгрузка: на телефоне вместо двух текстовых кнопок одна иконка, открывающая
 * тот же выбор Excel/PDF нижним листом; клик просто нажимает исходные кнопки,
 * поэтому modules/export.js менять не пришлось.
 */

import { state } from '../core/state.js';

class FilterMenus {
    constructor() {
        this.initialized = false;
    }

    init() {
        if (this.initialized) return;

        this.select = document.getElementById('venue-selector');
        this.trigger = document.getElementById('venue-trigger');
        this.triggerName = document.getElementById('venue-trigger-name');
        this.menu = document.getElementById('venue-menu');
        this.optionList = document.getElementById('venue-option-list');
        this.backdrop = document.getElementById('fb-backdrop');

        this.exportTrigger = document.getElementById('export-trigger');
        this.exportMenu = document.getElementById('export-menu');

        if (!this.trigger || !this.select) {
            this.initialized = true;
            return;
        }

        this.setupVenue();
        this.setupExport();
        this.syncVenue();

        this.initialized = true;
    }

    // ============================================================
    // Заведение
    // ============================================================

    setupVenue() {
        this.trigger.addEventListener('click', () => {
            this.renderOptions();
            this.toggle(this.menu, this.trigger);
        });

        // Список приходит асинхронно (venue_selector.loadVenues) — обновляем подпись,
        // когда заведения загрузились и когда выбор сменился.
        state.subscribe((event) => {
            if (event === 'venuesLoaded' || event === 'venueChanged') {
                this.syncVenue();
            }
        });

        this.backdrop?.addEventListener('click', () => this.closeAll());

        document.addEventListener('click', (e) => {
            if (this.menu?.classList.contains('hidden') && this.exportMenu?.classList.contains('hidden')) return;
            if (e.target.closest('.fb-menu')) return;
            if (e.target.closest('[aria-haspopup]')) return;
            this.closeAll();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeAll();
        });
    }

    /** Подпись на кнопке = текст выбранной опции скрытого select. */
    syncVenue() {
        if (!this.select || !this.triggerName) return;
        const opt = this.select.selectedOptions[0];
        if (opt && opt.textContent.trim()) {
            this.triggerName.textContent = opt.textContent.trim();
        }
    }

    renderOptions() {
        if (!this.optionList || !this.select) return;

        this.optionList.innerHTML = '';
        Array.from(this.select.options).forEach(opt => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'fb-menu-item';
            item.setAttribute('role', 'option');
            item.classList.toggle('active', opt.value === this.select.value);
            item.setAttribute('aria-selected', opt.value === this.select.value ? 'true' : 'false');
            item.innerHTML = `<span class="fb-menu-name"></span>`;
            item.querySelector('.fb-menu-name').textContent = opt.textContent.trim();

            item.addEventListener('click', () => {
                if (opt.value !== this.select.value) {
                    this.select.value = opt.value;
                    // change слушает venue_selector.js — он и меняет state.
                    this.select.dispatchEvent(new Event('change', { bubbles: true }));
                }
                this.closeAll();
            });

            this.optionList.appendChild(item);
        });
    }

    // ============================================================
    // Выгрузка (мобильный)
    // ============================================================

    setupExport() {
        if (!this.exportTrigger || !this.exportMenu) return;

        this.exportTrigger.addEventListener('click', () => {
            this.toggle(this.exportMenu, this.exportTrigger);
        });

        this.exportMenu.querySelectorAll('[data-export]').forEach(item => {
            item.addEventListener('click', () => {
                const id = item.dataset.export === 'pdf' ? 'btn-export-pdf' : 'btn-export-excel';
                this.closeAll();
                document.getElementById(id)?.click();
            });
        });
    }

    // ============================================================
    // Общее для списков
    // ============================================================

    toggle(menu, triggerEl) {
        const wasOpen = !menu.classList.contains('hidden');
        this.closeAll();
        if (wasOpen) return;

        menu.classList.remove('hidden');
        this.backdrop?.classList.remove('hidden');
        triggerEl?.setAttribute('aria-expanded', 'true');

        const bar = document.getElementById('filter-bar');
        if (bar && triggerEl) {
            const barRect = bar.getBoundingClientRect();
            const tRect = triggerEl.getBoundingClientRect();
            // Список выпадает от своего триггера; для правого края (выгрузка)
            // прижимаем к правой границе шапки, иначе он вылезет за неё.
            const left = Math.min(
                Math.round(tRect.left - barRect.left),
                Math.round(barRect.width - menu.offsetWidth)
            );
            menu.style.setProperty('--fb-menu-left', `${Math.max(0, left)}px`);
        }
    }

    closeAll() {
        document.querySelectorAll('.fb-menu').forEach(m => m.classList.add('hidden'));
        document.querySelectorAll('[aria-haspopup]').forEach(t => t.setAttribute('aria-expanded', 'false'));
        this.backdrop?.classList.add('hidden');
    }
}

export const filterMenus = new FilterMenus();

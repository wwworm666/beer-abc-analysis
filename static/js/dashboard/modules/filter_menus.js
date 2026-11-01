/**
 * Выгрузка в общей полосе «Бар и период» на дашборде.
 *
 * Бар и период с 2026-11-01 выбирает общая полоса сайта (templates/shared/scope_strip.html,
 * static/js/shared/period/scope_strip.js) — прежний список заведений этого модуля ушёл туда.
 * Здесь осталась только выгрузка: на телефоне вместо двух текстовых кнопок одна иконка,
 * открывающая тот же выбор Excel/PDF нижним листом; клик просто нажимает исходные кнопки,
 * поэтому modules/export.js менять не пришлось. Кнопки и меню лежат в полосе
 * (strip_actions в templates/dashboard/base.html).
 */

class FilterMenus {
    constructor() {
        this.initialized = false;
    }

    init() {
        if (this.initialized) return;
        this.initialized = true;

        this.strip = document.getElementById('kultura-strip');
        this.backdrop = document.getElementById('ks-backdrop');
        this.exportTrigger = document.getElementById('export-trigger');
        this.exportMenu = document.getElementById('export-menu');
        if (!this.exportTrigger || !this.exportMenu) return;

        this.exportTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        this.exportMenu.querySelectorAll('[data-export]').forEach(item => {
            item.addEventListener('click', () => {
                const id = item.dataset.export === 'pdf' ? 'btn-export-pdf' : 'btn-export-excel';
                this.close();
                document.getElementById(id)?.click();
            });
        });

        // Затемнение под листом общее с меню бара полосы: закрывает и выгрузку.
        this.backdrop?.addEventListener('click', () => this.close());

        document.addEventListener('click', (e) => {
            if (this.exportMenu.classList.contains('hidden')) return;
            if (this.exportMenu.contains(e.target)) return;
            this.close();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.close();
        });
    }

    toggle() {
        if (!this.exportMenu.classList.contains('hidden')) {
            this.close();
            return;
        }
        // Открыт один список полосы: меню бара закрывается.
        document.getElementById('ks-bar-menu')?.classList.add('hidden');
        document.getElementById('ks-bar-trigger')?.setAttribute('aria-expanded', 'false');
        this.exportMenu.classList.remove('hidden');
        this.backdrop?.classList.remove('hidden');
        this.exportTrigger.setAttribute('aria-expanded', 'true');

        if (this.strip) {
            const stripRect = this.strip.getBoundingClientRect();
            const tRect = this.exportTrigger.getBoundingClientRect();
            // Список прижат к правой границе полосы, иначе он вылезет за неё.
            const left = Math.min(
                Math.round(tRect.left - stripRect.left),
                Math.round(stripRect.width - this.exportMenu.offsetWidth)
            );
            this.exportMenu.style.setProperty('--fb-menu-left', `${Math.max(0, left)}px`);
        }
    }

    close() {
        if (this.exportMenu.classList.contains('hidden')) return;
        this.exportMenu.classList.add('hidden');
        this.backdrop?.classList.add('hidden');
        this.exportTrigger.setAttribute('aria-expanded', 'false');
    }
}

export const filterMenus = new FilterMenus();

/**
 * Период в шапке дашборда — общий элемент сайта (стандарт docs/period-standard.md).
 *
 *   [ Все заведения ▾ | ‹  26 окт – 1 ноя 2026  неделя 44 · идёт, по 01.11 ▾  › |  Excel  PDF ]
 *
 * Элемент (static/js/shared/period/period_picker.js) рисует стрелки, название и панель: шаг,
 * сетку периодов, быстрый выбор, свой период. Этот модуль — связка с состоянием дашборда:
 * какие шаги доступны на вкладке, что делать со сменой периода и вкладки.
 *
 * Правила вкладок:
 *   - «Аналитика», «Выручка», «Сравнение» — все шаги и свой период; «Сравнение» берёт период 1
 *     из шапки (раньше у него были свои списки недель);
 *   - «Планы» — только месяц и год (планы хранятся помесячно). Если смотрел неделю, «Планы»
 *     показывают её месяц — видно в шапке, — а при возврате на другую вкладку неделя
 *     возвращается, если период не меняли (раньше «Планы» молча оставляли месяц навсегда).
 */

import { state } from '../core/state.js';

const K = window.KPeriod;

const ALL_STEPS = ['day', 'week', 'month', 'quarter', 'year', 'custom'];
const TAB_STEPS = {
    'tab-analytics': ALL_STEPS,
    'analytics': ALL_STEPS,
    'tab-revenue': ALL_STEPS,
    'tab-comparison': ALL_STEPS,
    'tab-plans': ['month', 'year']
};
const STEP_NOTES = {
    'tab-plans': 'Планы задаются на месяц — здесь доступны месяц и год'
};
// Быстрый выбор дашборда — тот же набор, что был в списке до 2026-11-01.
const QUICK = ['today', 'yesterday', 'current_week', 'last_closed_week', 'current_month',
    'last_closed_month', 'current_quarter', 'current_year'];

class PeriodControls {
    constructor() {
        this.initialized = false;
        this.picker = null;
        this.beforeSnap = null;   // период до перехода на вкладку с другими шагами
        this.snapped = null;      // период, которым его заменили
    }

    init() {
        if (this.initialized) return;
        this.initialized = true;
        const mount = document.getElementById('cg-period');
        if (!mount || !window.KPeriodPicker) return;   // не дашбордная страница

        this.picker = window.KPeriodPicker.mount(mount, {
            variant: 'strip',
            steps: this.stepsFor(state.activeTab),
            quick: QUICK,
            value: state.currentPeriod,
            urlSync: true,
            freshness: 'Данные iiko — по сегодня, обновляются не реже раза в 10 минут',
            onChange: (period) => this.apply(period)
        });
        // Адрес сразу показывает открытый период: ссылку можно скопировать с первой секунды.
        this.picker.set(state.currentPeriod, { silent: true });

        state.subscribe((event, data) => {
            if (event === 'tabChanged') {
                this.onTab(data);
            } else if (event === 'periodChanged') {
                // Период мог смениться не через шапку — держим её в согласии с состоянием.
                const shown = this.picker.get();
                if (!shown || shown.start !== data.start || shown.end !== data.end) {
                    this.picker.set(data, { silent: true });
                }
            }
        });
    }

    stepsFor(tab) {
        return TAB_STEPS[tab] || ALL_STEPS;
    }

    /** Период из шапки — в состояние (отсюда расходятся periodChanged / monthChanged). */
    apply(period) {
        const cur = state.currentPeriod;
        if (cur && cur.start === period.start && cur.end === period.end) {
            // Границы те же — данные перезапрашивать незачем, но шаг стрелки мог смениться.
            state.currentPeriod = period;
            return;
        }
        state.setPeriod(period);
    }

    onTab(tab) {
        const steps = this.stepsFor(tab);
        this.picker.setSteps(steps, STEP_NOTES[tab] || '');
        const period = state.currentPeriod;

        // Вернулись с «Планов»: неделя возвращается, если месяц на «Планах» не меняли.
        if (this.beforeSnap && this.snapped && steps.includes(this.beforeSnap.granularity)) {
            const untouched = period && period.start === this.snapped.start && period.end === this.snapped.end;
            const restore = this.beforeSnap;
            this.beforeSnap = null;
            this.snapped = null;
            if (untouched) this.picker.set(restore);
            return;
        }

        if (period && !steps.includes(period.granularity)) {
            const target = steps.includes('month') ? 'month' : steps[0];
            this.beforeSnap = period;
            this.snapped = K.changeGranularity(period, target);
            this.picker.set(this.snapped);
        }
    }
}

export const periodControls = new PeriodControls();

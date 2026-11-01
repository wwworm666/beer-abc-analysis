/**
 * Бар и период дашборда — общая полоса сайта (templates/shared/scope_strip.html,
 * static/js/shared/period/scope_strip.js; план единого виджета — docs/planning/period-widget-rollout.md).
 *
 *   [ Все бары ▾ | ‹  26 окт – 1 ноя 2026  неделя 44 · идёт, по 01.11 ▾  › |  Excel  PDF ]
 *
 * Полоса сама рисует бар и период, хранит выбор для всего сайта (час — период, бар — пока не
 * сменишь) и пишет адрес. Этот модуль — связка с состоянием дашборда:
 *   - выбор в полосе -> state.setPeriod / state.setVenue (отсюда расходятся события вкладкам);
 *   - какие шаги доступны на вкладке.
 *
 * Правила вкладок:
 *   - «Аналитика», «Выручка», «Сравнение» — все шаги и свой период; «Сравнение» берёт период 1
 *     из полосы;
 *   - «Планы» — только месяц и год (планы хранятся помесячно). Если выбрана неделя, «Планы»
 *     ПОКАЗЫВАЮТ месяц выбранного периода (ответ владельца Р3: месяц четверга недели) — общий
 *     выбор при этом не меняется (показ — не выбор); при возврате на другую вкладку неделя
 *     возвращается, если месяц на «Планах» не меняли.
 */

import { state } from '../core/state.js';

const K = window.KPeriod;

const ALL_STEPS = ['day', 'week', 'month', 'year', 'custom'];   // кварталов нет (2026-11-01)
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

class PeriodControls {
    constructor() {
        this.initialized = false;
        this.strip = null;
        this.beforeSnap = null;   // период до перехода на вкладку с другими шагами
        this.snapped = null;      // месяц, который вкладка показала вместо него
    }

    init() {
        if (this.initialized) return;
        this.initialized = true;
        this.strip = window.KStrip || null;
        if (!this.strip) return;   // не дашбордная страница или полоса не загрузилась

        this.strip.setSteps(this.stepsFor(state.activeTab), STEP_NOTES[state.activeTab] || '');
        this.strip.onChange((e) => {
            if (e.type === 'period') this.apply(e.period);
            else if (e.type === 'bar') state.setVenue(e.bar || 'all', { fromStrip: true });
        });

        state.subscribe((event, data) => {
            if (event === 'tabChanged') {
                this.onTab(data);
            } else if (event === 'periodChanged') {
                // Период мог смениться не через полосу — держим её в согласии с состоянием.
                const shown = this.strip.get().period;
                if (!shown || shown.start !== data.start || shown.end !== data.end) {
                    this.strip.showPeriod(data);
                }
            }
        });
    }

    stepsFor(tab) {
        return TAB_STEPS[tab] || ALL_STEPS;
    }

    /** Период из полосы — в состояние (отсюда расходятся periodChanged / monthChanged). */
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
        this.strip.setSteps(steps, STEP_NOTES[tab] || '');
        const period = state.currentPeriod;

        // Вернулись с «Планов»: неделя возвращается, если месяц на «Планах» не меняли.
        if (this.beforeSnap && this.snapped && steps.includes(this.beforeSnap.granularity)) {
            const untouched = period && period.start === this.snapped.start && period.end === this.snapped.end;
            const restore = this.beforeSnap;
            this.beforeSnap = null;
            this.snapped = null;
            if (untouched) {
                this.strip.showPeriod(restore);
                state.setPeriod(restore);
            }
            return;
        }

        if (period && !steps.includes(period.granularity)) {
            this.beforeSnap = period;
            this.snapped = K.monthOf(period);
            this.strip.showPeriod(this.snapped);
            state.setPeriod(this.snapped);
        }
    }
}

export const periodControls = new PeriodControls();

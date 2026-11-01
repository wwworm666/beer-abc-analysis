/**
 * Модуль "Месячный отчёт" — помесячная динамика метрик за год (Chart.js).
 *
 * Бар и период — общая полоса сайта «Бар и период» (window.KStrip, с 2026-11-01, план единого
 * виджета docs/planning/period-widget-rollout.md, этап 3): своих списков года, месяца ТОП-10 и
 * бара у графиков нет.
 *   - Год отчёта — год показанного периода; полоса помесячная (mode='monthly', шаги месяц и
 *     год), без выбора — последний закрытый месяц (в январе — декабрь прошлого года).
 *   - Месяц ТОП-10 — показанный месяц, если он закрыт; иначе последний закрытый месяц того же
 *     года с подписью (у года — его декабрь или последний закрытый месяц).
 *   - Бар: ЛИНЕЙНЫЕ графики (одна метрика) при «Все бары» накладывают четыре бара (линия на
 *     бар, цвет = цвет бара), при выбранном баре — только его линию (ответ владельца Р9);
 *     графики С РАЗБИВКОЙ по категориям, СТОЛБЧАТЫЕ и ТОП-10 — по выбранному бару или всей
 *     сети ('all' при «Все бары»).
 *   - Какие месяцы закрыты — по часам сервера (KPeriod.lastClosed, рабочие сутки до 06:00),
 *     а не по часам устройства.
 *
 * Данные читаются из витрины (диск) — core/monthly_report.py serve_*:
 *   GET /api/monthly-report?venue=&years=        — выручка/наценка/доли/локал-импорт
 *   GET /api/monthly-report/loyalty?venue=&year= — новые гости, выручка карты/без
 *   GET /api/monthly-report/draft-liters?...      — литры по стилям
 *   GET /api/monthly-report/top-guests?...&month= — ТОП-10 гостей за месяц
 */

import { fetchAPI } from '../core/api.js';
import { formatMoney, formatNumber } from '../core/utils.js';

// Бары: ключ -> подпись + сигнатурный цвет (легенда сверху). Подписи — короткие имена из
// таблицы баров полосы (KStrip.barInfo(ключ).short), здесь — запасные, если полосы нет.
const BARS = [
    { key: 'all', label: 'Все бары', color: '#D97757' },        // оранжевый
    { key: 'bolshoy', label: 'ВО', color: '#D957A8' },           // розовый
    { key: 'ligovskiy', label: 'Лиг', color: '#7BD957' },        // зелёный
    { key: 'kremenchugskaya', label: 'Крем', color: '#D9B857' }, // жёлтый
    { key: 'varshavskaya', label: 'Вар', color: '#57B8D9' },     // синий
];

// Бары для ЛИНЕЙНЫХ графиков (наложение): без всей сети — её сумма кратно выше
// выручки/чеков отдельных баров и сплющивает их линии у нижней границы, ничего не
// видно. Вся сеть — на графиках с разбивкой, столбчатых и ТОП-10 при «Все бары».
const LINE_BARS = BARS.filter((b) => b.key !== 'all');

const RU_MONTHS_FULL = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                        'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
// Пауза перед перезагрузкой после выбора в полосе: серия шагов стрелкой — одна загрузка.
const STRIP_PAUSE_MS = 300;

// Последний закрытый месяц {year, month} по часам сервера (полоса настраивает KPeriod часами
// сервера: рабочие сутки до 06:00 МСК). Без полосы — по часам устройства (запасной путь).
function lastClosedMonth() {
    const K = typeof window !== 'undefined' ? window.KPeriod : null;
    if (K && K.lastClosed) {
        const p = K.lastClosed('month');
        return { year: Number(p.start.slice(0, 4)), month: Number(p.start.slice(5, 7)) };
    }
    const now = new Date();
    const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

/**
 * Что показывает отчёт при выбранном в полосе периоде (чистая функция — проверяется тестом
 * tests/test_monthly_report_scope.mjs).
 *   period — {start, end, granularity} полосы; closed — последний закрытый месяц {year, month}.
 * -> {year, month, topMonth, closedMonths, note}
 *   year — год отчёта; month — показанный месяц (у года — декабрь); topMonth — месяц ТОП-10
 *   (null — в году закрытых месяцев нет); closedMonths — сколько месяцев года закрыто
 *   (графики рисуются по них); note — подпись, если ТОП-10 не за показанный месяц.
 * Показанный месяц недели или своего периода — месяц его середины (у недели — четверга),
 * у длинного — последний (ответ Р3, как KPeriod.monthOf).
 */
export function monthlyScope(period, closed) {
    let year, month;
    if (period && period.granularity === 'year') {
        year = Number(period.start.slice(0, 4));
        month = 12;
    } else if (period && period.start) {
        const K = typeof window !== 'undefined' ? window.KPeriod : null;
        const shown = period.granularity === 'month' || !K ? period : K.monthOf(period);
        year = Number(shown.start.slice(0, 4));
        month = Number(shown.start.slice(5, 7));
    } else {
        year = closed.year;
        month = closed.month;
    }
    const closedMonths = year < closed.year ? 12 : (year > closed.year ? 0 : closed.month);
    const topMonth = month <= closedMonths ? month : (closedMonths || null);
    let note = '';
    if (topMonth === null) {
        note = 'В ' + year + ' году закрытых месяцев ещё нет — ТОП-10 появится, когда закроется январь';
    } else if (topMonth !== month) {
        const what = period && period.granularity === 'year' ? year + ' год' : RU_MONTHS_FULL[month - 1] + ' ' + year;
        note = what.charAt(0).toUpperCase() + what.slice(1) + ' ещё идёт — ТОП-10 за ' +
            RU_MONTHS_FULL[topMonth - 1] + ' ' + year + ', последний закрытый месяц';
    }
    return { year, month, topMonth, closedMonths, note };
}

// Категории (для столбчатых, независимо от цвета бара)
const CAT_COLORS = { draft: '#D97757', packaged: '#57B8D9', kitchen: '#7BD957' };
const LI_COLORS = { local: '#059669', import: '#D97757' };
const CARD_COLORS = { card: '#D97757', nocard: '#B0AAA4' };
const STYLE_PALETTE = [
    '#D97757', '#57B8D9', '#7BD957', '#D9B857', '#9C7BD9',
    '#D957A8', '#57D9B8', '#E08A5B', '#8A8A8A',
];

const RU_MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
                   'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

function hexToRgba(hex, alpha) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Плагин: подписать долю каждого сегмента внутри накопительного столбца.
// Сумму видно по оси Y; доля (сегмент / сумма столбца, %) вписывается по центру
// сегмента. Тонкие сегменты пропускаются (нет места / визуально незначимы).
const MIN_SEGMENT_PCT = 6;    // не подписывать сегменты мельче N% столбца
const MIN_SEGMENT_PX = 14;    // ...и ниже N пикселей (текст не влезет)
const percentInStackPlugin = {
    id: 'percentInStack',
    afterDatasetsDraw(chart) {
        const { ctx, data } = chart;
        const datasets = data.datasets || [];
        const count = (data.labels || []).length;

        // Сумма положительных значений по каждому столбцу (только видимые датасеты)
        const totals = new Array(count).fill(0);
        datasets.forEach((ds, di) => {
            if (chart.getDatasetMeta(di).hidden) return;
            for (let i = 0; i < count; i++) {
                const v = Number(ds.data[i]) || 0;
                if (v > 0) totals[i] += v;
            }
        });

        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '600 10px "IBM Plex Mono", ui-monospace, monospace';
        ctx.fillStyle = '#fff';
        datasets.forEach((ds, di) => {
            const meta = chart.getDatasetMeta(di);
            if (meta.hidden) return;
            meta.data.forEach((el, i) => {
                const v = Number(ds.data[i]) || 0;
                const total = totals[i];
                if (!total || v <= 0) return;
                const pct = (v / total) * 100;
                if (pct < MIN_SEGMENT_PCT) return;
                if ((el.height || 0) < MIN_SEGMENT_PX) return;
                const c = el.getCenterPoint();
                ctx.fillText(`${pct.toFixed(0)}%`, c.x, c.y);
            });
        });
        ctx.restore();
    },
};

class MonthlyReportModule {
    constructor() {
        this.initialized = false;
        this.charts = {};

        // Год, месяц ТОП-10 и бар — из полосы (init -> _applyScope). До init — последний
        // закрытый месяц (по часам сервера, если полоса уже настроила KPeriod).
        const closed = lastClosedMonth();
        this.year = closed.year;
        this.closedMonths = closed.month;
        this.selectedMonth = closed.month;     // месяц ТОП-10 (null — закрытых месяцев в году нет)
        this.topNote = '';
        this.venue = 'all';                    // бар полосы; 'all' — «Все бары» (вся сеть)
        this.consumptionMode = 'money';        // money | units

        this.coreByVenue = {};
        this.loyaltyByVenue = {};
        this.litersByVenue = {};
        this.topData = null;
        this.gen = 0;                          // номер загрузки: ответ старого года не ляжет в новый
        this.strip = null;
        this.stripTimer = null;
    }

    init() {
        if (this.initialized) return;
        this.strip = (typeof window !== 'undefined' && window.KStrip) || null;
        this._applyScope();
        this._buildBarLegend();
        this._setupToggles();
        // Выбор в полосе (бар, месяц, год) — перезагрузка после паузы.
        if (this.strip) {
            this.strip.onChange(() => {
                clearTimeout(this.stripTimer);
                this.stripTimer = setTimeout(() => { this.stripTimer = null; this._onStrip(); }, STRIP_PAUSE_MS);
            });
        }
        this.initialized = true;
        console.log('[Monthly] Модуль месячного отчёта инициализирован');
    }

    // ------------------------ Бар и период из полосы ------------------------ //

    // Год, месяц ТОП-10, бар и подпись — из выбора в полосе. -> была ли смена года.
    _applyScope() {
        const sel = this.strip ? this.strip.get() : { bar: '', period: null };
        const scope = monthlyScope(sel.period, lastClosedMonth());
        const yearChanged = scope.year !== this.year;
        this.year = scope.year;
        this.closedMonths = scope.closedMonths;
        this.selectedMonth = scope.topMonth;
        this.topNote = scope.note;
        this.venue = sel.bar || 'all';
        return yearChanged;
    }

    _onStrip() {
        if (this._applyScope()) {
            // Другой год -> данные прежнего года не подходят, грузим заново.
            this.coreByVenue = {};
            this.loyaltyByVenue = {};
            this.litersByVenue = {};
        }
        this._buildBarLegend();
        this.load();
    }

    // Подпись бара в легенде и на линиях: короткое имя из таблицы баров полосы («ВО», «Лиг»…).
    _label(bar) {
        const info = bar.key !== 'all' && this.strip && this.strip.barInfo ? this.strip.barInfo(bar.key) : null;
        return info ? (info.short || info.name) : bar.label;
    }

    // Бар полосы словами: «Все бары» или полное имя бара («Варшавская»).
    _venueName() {
        if (this.venue === 'all') return 'Все бары';
        const info = this.strip && this.strip.barInfo ? this.strip.barInfo(this.venue) : null;
        return info ? info.name : this._label(BARS.find((b) => b.key === this.venue) || BARS[0]);
    }

    // Линии наложения: при «Все бары» — четыре бара, при выбранном баре — только он (Р9).
    _lineBars() {
        return this.venue === 'all' ? LINE_BARS : LINE_BARS.filter((b) => b.key === this.venue);
    }

    // Какие бары грузить: линиям — их бары, разбивкам, столбцам и ТОП-10 — бар полосы.
    _venuesToLoad() {
        const keys = this._lineBars().map((b) => b.key);
        if (keys.indexOf(this.venue) < 0) keys.unshift(this.venue);
        return keys;
    }

    // ----------------------------- Контролы ----------------------------- //

    // Легенда (цвет -> бар) линий наложения: четыре бара при «Все бары», иначе выбранный.
    _buildBarLegend() {
        const container = document.getElementById('mr-bar-buttons');
        if (!container) return;
        container.innerHTML = '';
        this._lineBars().forEach((bar) => {
            const item = document.createElement('span');
            item.className = 'mr-legend-item';
            item.innerHTML = `<span class="mr-bar-dot" style="--bar-color:${bar.color}"></span>${this._label(bar)}`;
            container.appendChild(item);
        });
    }

    _setupToggles() {
        // Деньги/Штуки для расхода (кнопки «Обновить» нет — данные обновляются
        // автоматически ночным шедулером, как только закрывается новый месяц)
        this._wireToggle('mr-consumption-toggle', 'mode', (val) => {
            this.consumptionMode = val;
            this._renderConsumption();
        });
    }

    // Общая навеска pill-переключателя: active-класс + колбэк со значением data-<key>
    _wireToggle(toggleId, dataKey, onChange) {
        const toggle = document.getElementById(toggleId);
        if (!toggle) return;
        toggle.querySelectorAll('.mr-toggle-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                toggle.querySelectorAll('.mr-toggle-btn').forEach((b) => b.classList.remove('active'));
                btn.classList.add('active');
                onChange(btn.dataset[dataKey]);
            });
        });
    }

    // Кол-во ЗАКРЫТЫХ месяцев года отчёта (текущий неполный не показываем) — по часам сервера.
    _completeMonths() {
        return this.closedMonths;
    }

    _labels() {
        return RU_MONTHS.slice(0, this._completeMonths());
    }

    _clip(arr) {
        return (arr || []).slice(0, this._completeMonths());
    }

    // ------------------------------ Загрузка ----------------------------- //

    async _runTasks(thunks, sequential) {
        if (sequential) {
            for (const t of thunks) await t();
        } else {
            await Promise.all(thunks.map((t) => t()));
        }
    }

    async load(force = false) {
        // Номер загрузки: выбор в полосе сменился, пока шла загрузка, — её ответы не рисуются
        // (иначе данные прежнего года или бара легли бы под новой подписью).
        const gen = ++this.gen;
        this._showLoading(true);
        this._renderTopHeader();
        // Грузим только нужные бары: линиям — их бары, разбивкам, столбцам и ТОП-10 — бар полосы.
        const venues = this._venuesToLoad();

        // 1. core (наложение линий + разбивки и столбцы по бару полосы)
        try {
            await this._runTasks(venues.map((v) => () => this._loadCore(v, force, gen)), force);
            if (gen !== this.gen) return;
            const primaryCore = this.coreByVenue[this.venue];
            this._renderRefreshed(primaryCore ? primaryCore.refreshed_at : null);
            this._renderCoreCharts();
            this._showNoData(!primaryCore);
        } catch (e) {
            console.error('[Monthly] core:', e);
            if (gen === this.gen) this._showNoData(true);
        } finally {
            if (gen === this.gen) this._showLoading(false);
        }

        // 2. остальные блоки в фоне
        try {
            await this._runTasks(venues.map((v) => () => this._loadLoyalty(v, force, gen)), force);
            if (gen !== this.gen) return;
            this._renderLoyalty();
            await this._loadLiters(this.venue, force, gen);
            if (gen !== this.gen) return;
            this._renderLitersChart();
            // Литры загружены -> обновить расход (в режиме «Кол-во» розлив берёт литры отсюда)
            this._renderConsumption();
            await this._loadTop(this.venue, this.selectedMonth, force, gen);
        } catch (e) {
            console.error('[Monthly] Фоновая загрузка блоков:', e);
        }
    }

    async _loadCore(venue, force, gen) {
        if (!force && this.coreByVenue[venue]) return;  // уже загружен за этот год
        const params = new URLSearchParams({ venue, years: this.year });
        if (force) params.set('force', '1');
        try {
            const data = await fetchAPI(`/api/monthly-report?${params.toString()}`);
            if (gen === undefined || gen === this.gen) this.coreByVenue[venue] = data;
        } catch (e) {
            console.error('[Monthly] core', venue, e);
            if (gen === undefined || gen === this.gen) this.coreByVenue[venue] = null;
        }
    }

    async _loadLoyalty(venue, force, gen) {
        if (!force && this.loyaltyByVenue[venue]) return;
        const params = new URLSearchParams({ venue, year: this.year });
        if (force) params.set('force', '1');
        try {
            const data = await fetchAPI(`/api/monthly-report/loyalty?${params.toString()}`);
            if (gen === undefined || gen === this.gen) this.loyaltyByVenue[venue] = data;
        } catch (e) {
            console.error('[Monthly] loyalty', venue, e);
        }
    }

    async _loadLiters(venue, force, gen) {
        if (!force && this.litersByVenue[venue]) return;
        const params = new URLSearchParams({ venue, year: this.year });
        if (force) params.set('force', '1');
        try {
            const data = await fetchAPI(`/api/monthly-report/draft-liters?${params.toString()}`);
            if (gen === undefined || gen === this.gen) this.litersByVenue[venue] = data;
        } catch (e) {
            console.error('[Monthly] liters', venue, e);
        }
    }

    // ТОП-10 за месяц ТОП-10 (закрытый): в году нет закрытых месяцев — таблица с подписью.
    async _loadTop(venue, month, force, gen) {
        if (!month) {
            this.topData = { guests: [] };
            this._renderTop();
            return;
        }
        const params = new URLSearchParams({ venue, year: this.year, month });
        if (force) params.set('force', '1');
        try {
            const data = await fetchAPI(`/api/monthly-report/top-guests?${params.toString()}`);
            if (gen !== undefined && gen !== this.gen) return;
            this.topData = data;
            this._renderTop();
        } catch (e) {
            console.error('[Monthly] top-guests', e);
        }
    }

    // ------------------------------ Данные ------------------------------- //

    _coreSeries(venue, key) {
        const d = this.coreByVenue[venue];
        const y = d && d.data ? d.data[String(this.year)] : null;
        return y ? (y[key] || []) : [];
    }

    _loyaltySeries(venue, key) {
        const d = this.loyaltyByVenue[venue];
        return d && d.data ? (d.data[key] || []) : [];
    }

    // ----------------------------- Рендеринг ----------------------------- //

    _renderCoreCharts() {
        // Наложение баров на линейных графиках
        this._overlayLine('mr-revenue', 'revenue', formatMoney, 'core');
        // Наценка % и средний чек — «уровневые», ось не от нуля (видно вариацию)
        this._overlayLine('mr-markup-pct', 'markup_pct', (v) => `${(v || 0).toFixed(1)}%`, 'core', false);
        this._overlayLine('mr-margin', 'margin', formatMoney, 'core');
        this._overlayLine('mr-checks', 'checks', formatNumber, 'core');
        this._overlayLine('mr-avg-check', 'avg_check', formatMoney, 'core', false);
        this._overlayLine('mr-loyalty-writeoffs', 'loyalty_writeoffs', formatMoney, 'core');

        // Разбивки и столбчатые — по бару полосы («Все бары» — вся сеть)
        this._updateStackedNote();
        this._renderRevenueStacked();
        this._renderMarkupCat();
        this._renderShares();
        this._renderLiPackaged();
        this._renderLiDraft();
        this._renderConsumption();
    }

    // Бар графиков с разбивкой, столбчатых и ТОП-10 — бар полосы ('all' — вся сеть).
    _venueFor() {
        return this.venue;
    }

    _renderRevenueStacked() {
        const v = this._venueFor('mr-revenue-stacked');
        this._stackedBar('mr-revenue-stacked', [
            { label: 'Кухня', data: this._coreSeries(v, 'revenue_kitchen'), color: CAT_COLORS.kitchen },
            { label: 'Фасовка', data: this._coreSeries(v, 'revenue_packaged'), color: CAT_COLORS.packaged },
            { label: 'Розлив', data: this._coreSeries(v, 'revenue_draft'), color: CAT_COLORS.draft },
        ], { valueFormat: formatMoney });
    }

    _renderShares() {
        const v = this._venueFor('mr-shares');
        this._stackedBar('mr-shares', [
            { label: 'Кухня', data: this._coreSeries(v, 'share_kitchen'), color: CAT_COLORS.kitchen },
            { label: 'Фасовка', data: this._coreSeries(v, 'share_packaged'), color: CAT_COLORS.packaged },
            { label: 'Розлив', data: this._coreSeries(v, 'share_draft'), color: CAT_COLORS.draft },
        ], { valueFormat: (x) => `${(x || 0).toFixed(1)}%`, percent: true });
    }

    _renderLiPackaged() {
        const v = this._venueFor('mr-li-packaged');
        this._stackedBar('mr-li-packaged', [
            { label: 'Локал (Россия)', data: this._coreSeries(v, 'local_packaged'), color: LI_COLORS.local },
            { label: 'Импорт', data: this._coreSeries(v, 'import_packaged'), color: LI_COLORS.import },
        ], { valueFormat: formatMoney });
    }

    _renderLiDraft() {
        const v = this._venueFor('mr-li-draft');
        this._stackedBar('mr-li-draft', [
            { label: 'Локал (Россия)', data: this._coreSeries(v, 'local_draft'), color: LI_COLORS.local },
            { label: 'Импорт', data: this._coreSeries(v, 'import_draft'), color: LI_COLORS.import },
        ], { valueFormat: formatMoney });
    }

    _renderRevenueCard() {
        const v = this._venueFor('mr-revenue-card');
        this._stackedBar('mr-revenue-card', [
            { label: 'По картам', data: this._loyaltySeries(v, 'revenue_card'), color: CARD_COLORS.card },
            { label: 'Без карты', data: this._loyaltySeries(v, 'revenue_nocard'), color: CARD_COLORS.nocard },
        ], { valueFormat: formatMoney });
    }

    _renderLitersChart() {
        const v = this._venueFor('mr-liters');
        const d = this.litersByVenue[v];
        const fmt = (x) => `${(x || 0).toFixed(0)} л`;
        if (!d) { this._stackedBar('mr-liters', [], { valueFormat: fmt }); return; }
        const series = d.series || {};
        const styles = d.styles || [];
        const datasets = styles.map((style, i) => ({
            label: style,
            data: series[style],
            color: STYLE_PALETTE[i % STYLE_PALETTE.length],
        }));
        this._stackedBar('mr-liters', datasets, { valueFormat: fmt });
    }

    // Линии-категории для ОДНОГО бара (старый дизайн); бар выбирается выпадающим списком.
    // it.data — готовый ряд (иначе берётся core-серия по it.key); it.fmt — свой формат
    // значения этой линии (для смешанных единиц: розлив в литрах, фасовка в штуках).
    _renderCategoryLines(canvasId, items, valueFormat, zeroBased) {
        const v = this._venueFor(canvasId);
        const datasets = items.map((it) => ({
            label: it.label,
            data: this._clip(it.data || this._coreSeries(v, it.key)),
            borderColor: it.color,
            backgroundColor: hexToRgba(it.color, it.fill ? 0.12 : 0.08),
            fill: !!it.fill,
            tension: 0.3,
            pointRadius: 2,
            borderWidth: 2,
            _fmt: it.fmt || null,
        }));
        this._render(canvasId, 'line', this._labels(), datasets, { valueFormat, legend: true, zeroBased });
    }

    // Суммарные литры розлива по месяцам для бара (сумма по всем стилям из блока литров)
    _draftLitersSeries(venue) {
        const d = this.litersByVenue[venue];
        if (!d || !d.series) return [];
        const styles = d.styles || [];
        const totals = new Array(12).fill(0);
        styles.forEach((s) => {
            const arr = d.series[s] || [];
            for (let i = 0; i < 12; i++) totals[i] += Number(arr[i]) || 0;
        });
        return totals;
    }

    // Наценка: Розлив/Фасовка/Кухня — 3 линии для выбранного бара
    _renderMarkupCat() {
        this._renderCategoryLines('mr-markup-cat', [
            { label: 'Розлив', key: 'markup_draft', color: CAT_COLORS.draft },
            { label: 'Фасовка', key: 'markup_packaged', color: CAT_COLORS.packaged },
            { label: 'Кухня', key: 'markup_kitchen', color: CAT_COLORS.kitchen },
        ], (x) => `${(x || 0).toFixed(1)}%`, false);
    }

    // Расход: Розлив/Фасовка — 2 линии для выбранного бара.
    // Деньги: обе линии в ₽. Количество: розлив — в ЛИТРАХ (он продаётся объёмом, штуки-
    // порции 0.3/0.5 несопоставимы), фасовка — в штуках (бутылки/банки). У каждой линии
    // своя единица (см. _fmt), ось — просто число.
    _renderConsumption() {
        if (this.consumptionMode === 'money') {
            this._renderCategoryLines('mr-consumption', [
                { label: 'Розлив', key: 'revenue_draft', color: CAT_COLORS.draft, fill: true },
                { label: 'Фасовка', key: 'revenue_packaged', color: CAT_COLORS.packaged, fill: true },
            ], formatMoney, true);
            return;
        }
        const v = this._venueFor('mr-consumption');
        const litersFmt = (x) => `${formatNumber(Math.round(x || 0))} л`;
        const unitsFmt = (x) => `${formatNumber(x || 0)} шт`;
        this._renderCategoryLines('mr-consumption', [
            { label: 'Розлив, л', data: this._draftLitersSeries(v), color: CAT_COLORS.draft, fill: true, fmt: litersFmt },
            { label: 'Фасовка, шт', key: 'units_packaged', color: CAT_COLORS.packaged, fill: true, fmt: unitsFmt },
        ], formatNumber, true);
    }

    _renderLoyalty() {
        // Новые гости — наложение баров (линия на бар)
        this._overlayLine('mr-new-guests', 'new_guests', formatNumber, 'loyalty');
        // Выручка карты/без — столбчатый, бар выбирается выпадающим списком
        this._renderRevenueCard();
    }

    // Подзаголовок ТОП-10: за какой месяц и по какому бару; подпись, если месяц не показанный.
    _renderTopHeader() {
        const sub = document.getElementById('mr-top-guests-sub');
        if (sub) {
            const month = this.selectedMonth ? `${RU_MONTHS_FULL[this.selectedMonth - 1]} ${this.year}` : `${this.year}`;
            sub.textContent = `Держатели карт лояльности за ${month} · ${this._venueName()}`;
        }
        const note = document.getElementById('mr-top-note');
        if (note) {
            note.textContent = this.topNote;
            note.hidden = !this.topNote;
        }
    }

    _renderTop() {
        const tbody = document.getElementById('mr-top-guests-body');
        if (!tbody) return;
        this._renderTopHeader();
        const guests = (this.topData && this.topData.guests) || [];
        if (!guests.length) {
            tbody.innerHTML = `<tr class="mr-empty-row"><td colspan="5">${this.selectedMonth
                ? 'Нет гостей с картой за месяц' : 'Закрытых месяцев в году ещё нет'}</td></tr>`;
            return;
        }
        tbody.innerHTML = guests.map((g, i) => `
            <tr>
                <td>${i + 1}</td>
                <td>${this._escape(g.name)}</td>
                <td>${this._escape(g.card)}</td>
                <td>${formatNumber(g.visits)}</td>
                <td>${formatMoney(g.spend)}</td>
            </tr>
        `).join('');
    }

    // Короткая подпись: по какому бару графики «одного бара» (разбивки, столбцы, ТОП-10).
    _updateStackedNote() {
        const el = document.getElementById('mr-stacked-note');
        if (!el) return;
        el.textContent = 'Графики с разбивкой, столбчатые и ТОП-10 — '
            + (this.venue === 'all' ? 'вся сеть (Все бары)' : this._venueName());
    }

    // -------------------------- Chart.js строители ----------------------- //

    _overlayLine(canvasId, key, valueFormat, source, zeroBased = true) {
        // Только отдельные бары, без всей сети — иначе её линия сплющивает остальные; при
        // выбранном в полосе баре — только он (Р9)
        const bars = this._lineBars();
        const datasets = bars.map((b) => {
            const raw = source === 'loyalty' ? this._loyaltySeries(b.key, key) : this._coreSeries(b.key, key);
            return {
                label: this._label(b),
                data: this._clip(raw),
                borderColor: b.color,
                backgroundColor: hexToRgba(b.color, 0.06),
                fill: false,
                tension: 0.3,
                pointRadius: 2,
                borderWidth: 2,
            };
        });
        this._render(canvasId, 'line', this._labels(), datasets, { valueFormat, legend: bars.length > 1, zeroBased });
    }

    _stackedBar(canvasId, items, opts = {}) {
        const datasets = items.map((it) => ({
            label: it.label,
            data: this._clip(it.data),
            backgroundColor: it.color,
            borderWidth: 0,
        }));
        this._render(canvasId, 'bar', this._labels(), datasets, {
            valueFormat: opts.valueFormat,
            stacked: true,
            percent: opts.percent,
            legend: true,
        });
    }

    _render(canvasId, type, labels, datasets, opts = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        if (this.charts[canvasId]) this.charts[canvasId].destroy();

        const valueFormat = opts.valueFormat || ((v) => v);
        const scales = {
            x: { stacked: !!opts.stacked, grid: { display: false } },
            y: {
                stacked: !!opts.stacked,
                // «Уровневые» метрики (наценка %, средний чек) не начинаем с нуля —
                // иначе вариация в их диапазоне (напр. 150-300%) сжата у потолка.
                beginAtZero: opts.zeroBased !== false,
                ticks: { callback: (v) => valueFormat(v) },
            },
        };
        if (opts.percent) scales.y.max = 100;

        // Накопительные столбцы: подписываем долю каждого сегмента внутри столбца
        const localPlugins = opts.stacked ? [percentInStackPlugin] : [];

        this.charts[canvasId] = new Chart(canvas.getContext('2d'), {
            type,
            data: { labels, datasets },
            plugins: localPlugins,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: opts.legend !== false,
                        position: 'bottom',
                        labels: { boxWidth: 12, font: { size: 11 } },
                    },
                    tooltip: {
                        // _fmt на датасете переопределяет формат (смешанные единицы: л/шт)
                        callbacks: {
                            label: (ctx) => {
                                const f = ctx.dataset._fmt || valueFormat;
                                return `${ctx.dataset.label}: ${f(ctx.parsed.y)}`;
                            },
                        },
                    },
                },
                scales,
            },
        });
    }

    // ------------------------------- UI utils ---------------------------- //

    _escape(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    _renderRefreshed(iso) {
        const el = document.getElementById('mr-refreshed');
        if (!el) return;
        if (!iso) {
            el.textContent = 'Данные ещё считаются';
            return;
        }
        const m = String(iso).match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
        el.textContent = m ? `данные на ${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}` : `данные на ${iso}`;
    }

    _showLoading(show) {
        const el = document.getElementById('mr-loading');
        const content = document.getElementById('mr-content');
        if (el) el.classList.toggle('hidden', !show);
        if (content) content.style.opacity = show ? '0.4' : '1';
    }

    _showNoData(show) {
        const el = document.getElementById('mr-no-data');
        const content = document.getElementById('mr-content');
        if (el) el.classList.toggle('hidden', !show);
        if (content) content.classList.toggle('hidden', show);
    }
}

export const monthlyReport = new MonthlyReportModule();

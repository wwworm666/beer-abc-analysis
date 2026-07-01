/**
 * Модуль "Месячный отчёт" — помесячная динамика метрик за год (Chart.js).
 *
 * Сверху — статичная ЛЕГЕНДА (цвет -> бар); все 5 баров показываются всегда:
 *   - ЛИНЕЙНЫЕ (одна метрика) накладывают ВСЕ бары (линия на бар, цвет = цвет бара);
 *   - С РАЗБИВКОЙ по категориям и СТОЛБЧАТЫЕ показывают ОДИН бар — выбор выпадающим
 *     списком (mr-bar-select), опции = все 5 баров.
 *
 * Данные читаются из витрины (диск) — core/monthly_report.py serve_*:
 *   GET /api/monthly-report?venue=&years=        — выручка/наценка/доли/локал-импорт
 *   GET /api/monthly-report/loyalty?venue=&year= — новые гости, выручка карты/без
 *   GET /api/monthly-report/draft-liters?...      — литры по стилям
 *   GET /api/monthly-report/top-guests?...&month= — ТОП-10 гостей за месяц
 */

import { fetchAPI } from '../core/api.js';
import { formatMoney, formatNumber } from '../core/utils.js';

// Бары: ключ -> подпись + сигнатурный цвет (легенда сверху)
const BARS = [
    { key: 'all', label: 'Общая', color: '#D97757' },           // оранжевый
    { key: 'bolshoy', label: 'ВО', color: '#D957A8' },           // розовый
    { key: 'ligovskiy', label: 'Лиг', color: '#7BD957' },        // зелёный
    { key: 'kremenchugskaya', label: 'Крем', color: '#D9B857' }, // жёлтый
    { key: 'varshavskaya', label: 'Варш', color: '#57B8D9' },    // синий
];

// Бары для ЛИНЕЙНЫХ графиков (наложение): без «Общей» — её сумма кратно выше
// выручки/чеков отдельных баров и сплющивает их линии у нижней границы, ничего не
// видно. «Общая» остаётся выбором в выпадающих списках столбчатых/категорийных графиков.
const LINE_BARS = BARS.filter((b) => b.key !== 'all');

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
        ctx.font = '600 10px "IBM Plex Mono", "Courier New", monospace';
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

        const now = new Date();
        this.currentYear = now.getFullYear();
        this.currentMonth = now.getMonth() + 1;

        this.year = this.currentYear;
        // ТОП-гости: по умолчанию последний ЗАВЕРШЁННЫЙ месяц (текущий не считаем)
        this.selectedMonth = Math.max(1, this.currentMonth - 1);
        this.consumptionMode = 'money';        // money | units

        this.coreByVenue = {};
        this.loyaltyByVenue = {};
        this.litersByVenue = {};
        this.topData = null;
        this.topVenue = null;          // выбранный бар таблицы ТОП-гостей (null -> первый)
        this.stackedVenue = {};        // canvasId -> выбранный бар столбчатого графика
    }

    init() {
        if (this.initialized) return;
        this._buildBarLegend();
        this._buildYearSelect();
        this._buildMonthSelect();
        this._setupToggles();
        this.initialized = true;
        console.log('[Monthly] Модуль месячного отчёта инициализирован');
    }

    // ----------------------------- Контролы ----------------------------- //

    // Статичная легенда (цвет -> бар). Бары не выбираются — показываются ВСЕ.
    _buildBarLegend() {
        const container = document.getElementById('mr-bar-buttons');
        if (!container) return;
        container.innerHTML = '';
        // Легенда описывает линии наложения -> без «Общей» (её на линейных нет)
        LINE_BARS.forEach((bar) => {
            const item = document.createElement('span');
            item.className = 'mr-legend-item';
            item.innerHTML = `<span class="mr-bar-dot" style="--bar-color:${bar.color}"></span>${bar.label}`;
            container.appendChild(item);
        });
    }

    _buildYearSelect() {
        const select = document.getElementById('mr-year');
        if (!select) return;
        select.innerHTML = '';
        for (let y = this.currentYear; y >= this.currentYear - 2; y--) {
            const opt = document.createElement('option');
            opt.value = y;
            opt.textContent = y;
            if (y === this.year) opt.selected = true;
            select.appendChild(opt);
        }
        select.addEventListener('change', () => {
            this.year = parseInt(select.value, 10);
            // другой год -> кэш данных невалиден, грузим заново
            this.coreByVenue = {};
            this.loyaltyByVenue = {};
            this.litersByVenue = {};
            this._buildMonthSelect();
            this.load();
        });
    }

    _buildMonthSelect() {
        const select = document.getElementById('mr-top-month');
        if (!select) return;
        const cm = this._completeMonths();
        // Только завершённые месяцы; текущий неполный не предлагаем
        if (this.selectedMonth > cm) this.selectedMonth = cm || 1;
        select.innerHTML = '';
        if (cm === 0) {
            const opt = document.createElement('option');
            opt.textContent = '—';
            select.appendChild(opt);
        }
        for (let m = 1; m <= cm; m++) {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = `${RU_MONTHS[m - 1]} ${this.year}`;
            if (m === this.selectedMonth) opt.selected = true;
            select.appendChild(opt);
        }
        select.onchange = () => {
            this.selectedMonth = parseInt(select.value, 10);
            this._loadTop(this._topVenue(), this.selectedMonth);
        };
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

    // --------------------------- Выбор баров ---------------------------- //

    // Все бары всегда (сверху — только легенда, выбора нет)
    _orderedSelected() {
        return BARS;
    }

    _primary() {
        const ordered = this._orderedSelected();
        return ordered.length ? ordered[0].key : 'all';
    }

    _barMeta(key) {
        return BARS.find((b) => b.key === key) || BARS[0];
    }

    // Кол-во ЗАВЕРШЁННЫХ месяцев для выбранного года (текущий неполный не показываем)
    _completeMonths() {
        if (this.year < this.currentYear) return 12;
        if (this.year > this.currentYear) return 0;
        return Math.max(0, this.currentMonth - 1);
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
        this._showLoading(true);
        // Грузим ВСЕ бары: линии накладывают выбранные, а выпадающие списки
        // столбчатых/категорийных графиков должны видеть любой бар.
        const bars = BARS;

        // 1. core по всем барам (наложение линий по выбранным + выбор бара у остальных)
        try {
            await this._runTasks(bars.map((b) => () => this._loadCore(b.key, force)), force);
            const primaryCore = this.coreByVenue[this._primary()];
            this._renderRefreshed(primaryCore ? primaryCore.refreshed_at : null);
            this._renderCoreCharts();
            this._showNoData(!primaryCore);
        } catch (e) {
            console.error('[Monthly] core:', e);
            this._showNoData(true);
        } finally {
            this._showLoading(false);
        }

        // 2. остальные блоки в фоне
        try {
            await this._runTasks(bars.map((b) => () => this._loadLoyalty(b.key, force)), force);
            this._renderLoyalty();
            await this._runTasks(bars.map((b) => () => this._loadLiters(b.key, force)), force);
            this._renderLitersChart();
            await this._loadTop(this._topVenue(), this.selectedMonth, force);
        } catch (e) {
            console.error('[Monthly] Фоновая загрузка блоков:', e);
        }
    }

    async _loadCore(venue, force) {
        if (!force && this.coreByVenue[venue]) return;  // уже загружен за этот год
        const params = new URLSearchParams({ venue, years: this.year });
        if (force) params.set('force', '1');
        try {
            this.coreByVenue[venue] = await fetchAPI(`/api/monthly-report?${params.toString()}`);
        } catch (e) {
            console.error('[Monthly] core', venue, e);
            this.coreByVenue[venue] = null;
        }
    }

    async _loadLoyalty(venue, force) {
        if (!force && this.loyaltyByVenue[venue]) return;
        const params = new URLSearchParams({ venue, year: this.year });
        if (force) params.set('force', '1');
        try {
            this.loyaltyByVenue[venue] = await fetchAPI(`/api/monthly-report/loyalty?${params.toString()}`);
        } catch (e) {
            console.error('[Monthly] loyalty', venue, e);
        }
    }

    async _loadLiters(venue, force) {
        if (!force && this.litersByVenue[venue]) return;
        const params = new URLSearchParams({ venue, year: this.year });
        if (force) params.set('force', '1');
        try {
            this.litersByVenue[venue] = await fetchAPI(`/api/monthly-report/draft-liters?${params.toString()}`);
        } catch (e) {
            console.error('[Monthly] liters', venue, e);
        }
    }

    async _loadTop(venue, month, force) {
        const params = new URLSearchParams({ venue, year: this.year, month: month || this.currentMonth });
        if (force) params.set('force', '1');
        try {
            this.topData = await fetchAPI(`/api/monthly-report/top-guests?${params.toString()}`);
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

        // Столбчатые — у каждого свой выбор бара (выпадающий список)
        this._buildStackedSelects();
        this._updateStackedNote();
        this._renderRevenueStacked();
        this._renderMarkupCat();
        this._renderShares();
        this._renderLiPackaged();
        this._renderLiDraft();
        this._renderConsumption();
    }

    // ----------------- Выбор бара для столбчатых графиков ----------------- //

    // Опции = ВСЕ бары (любой можно показать независимо от кнопок наверху);
    // по умолчанию первый выбранный, либо ранее выбранный в этом списке.
    _buildStackedSelects() {
        document.querySelectorAll('.mr-bar-select').forEach((select) => {
            const chartId = select.dataset.chart;
            const cur = (chartId === 'mr-top-guests' ? this.topVenue : this.stackedVenue[chartId]) || this._primary();
            select.innerHTML = '';
            BARS.forEach((b) => {
                const opt = document.createElement('option');
                opt.value = b.key;
                opt.textContent = b.label;
                if (b.key === cur) opt.selected = true;
                select.appendChild(opt);
            });
            select.onchange = () => this._onStackedVenueChange(chartId, select.value);
        });
    }

    _onStackedVenueChange(chartId, venue) {
        if (chartId === 'mr-top-guests') {
            this.topVenue = venue;
            this._loadTop(venue, this.selectedMonth);
            return;
        }
        this.stackedVenue[chartId] = venue;
        const render = this._stackedRenderers()[chartId];
        if (render) render();
    }

    // Выбранный в списке бар графика (любой из 5); по умолчанию первый выбранный кнопками
    _venueFor(chartId) {
        return this.stackedVenue[chartId] || this._primary();
    }

    _topVenue() {
        return this.topVenue || this._primary();
    }

    _stackedRenderers() {
        return {
            'mr-markup-cat': () => this._renderMarkupCat(),
            'mr-consumption': () => this._renderConsumption(),
            'mr-revenue-stacked': () => this._renderRevenueStacked(),
            'mr-shares': () => this._renderShares(),
            'mr-li-packaged': () => this._renderLiPackaged(),
            'mr-li-draft': () => this._renderLiDraft(),
            'mr-revenue-card': () => this._renderRevenueCard(),
            'mr-liters': () => this._renderLitersChart(),
        };
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

    // Линии-категории для ОДНОГО бара (старый дизайн); бар выбирается выпадающим списком
    _renderCategoryLines(canvasId, items, valueFormat, zeroBased) {
        const v = this._venueFor(canvasId);
        const datasets = items.map((it) => ({
            label: it.label,
            data: this._clip(this._coreSeries(v, it.key)),
            borderColor: it.color,
            backgroundColor: hexToRgba(it.color, it.fill ? 0.12 : 0.08),
            fill: !!it.fill,
            tension: 0.3,
            pointRadius: 2,
            borderWidth: 2,
        }));
        this._render(canvasId, 'line', this._labels(), datasets, { valueFormat, legend: true, zeroBased });
    }

    // Наценка: Розлив/Фасовка/Кухня — 3 линии для выбранного бара
    _renderMarkupCat() {
        this._renderCategoryLines('mr-markup-cat', [
            { label: 'Розлив', key: 'markup_draft', color: CAT_COLORS.draft },
            { label: 'Фасовка', key: 'markup_packaged', color: CAT_COLORS.packaged },
            { label: 'Кухня', key: 'markup_kitchen', color: CAT_COLORS.kitchen },
        ], (x) => `${(x || 0).toFixed(1)}%`, false);
    }

    // Расход: Розлив/Фасовка — 2 линии (деньги/штуки) для выбранного бара
    _renderConsumption() {
        const prefix = this.consumptionMode === 'money' ? 'revenue' : 'units';
        const fmt = this.consumptionMode === 'money' ? formatMoney : formatNumber;
        this._renderCategoryLines('mr-consumption', [
            { label: 'Розлив', key: `${prefix}_draft`, color: CAT_COLORS.draft, fill: true },
            { label: 'Фасовка', key: `${prefix}_packaged`, color: CAT_COLORS.packaged, fill: true },
        ], fmt, true);
    }

    _renderLoyalty() {
        // Новые гости — наложение баров (линия на бар)
        this._overlayLine('mr-new-guests', 'new_guests', formatNumber, 'loyalty');
        // Выручка карты/без — столбчатый, бар выбирается выпадающим списком
        this._renderRevenueCard();
    }

    _renderTop() {
        const tbody = document.getElementById('mr-top-guests-body');
        if (!tbody) return;
        const guests = (this.topData && this.topData.guests) || [];
        if (!guests.length) {
            tbody.innerHTML = '<tr class="mr-empty-row"><td colspan="5">Нет гостей с картой за месяц</td></tr>';
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

    _updateStackedNote() {
        const el = document.getElementById('mr-stacked-note');
        if (!el) return;
        el.textContent = 'Графики с разбивкой по категориям, столбчатые и ТОП-гости показывают '
            + 'один бар — он выбирается выпадающим списком на каждом';
    }

    // -------------------------- Chart.js строители ----------------------- //

    _overlayLine(canvasId, key, valueFormat, source, zeroBased = true) {
        // Только отдельные бары, без «Общей» — иначе её линия сплющивает остальные
        const bars = LINE_BARS;
        const datasets = bars.map((b) => {
            const raw = source === 'loyalty' ? this._loyaltySeries(b.key, key) : this._coreSeries(b.key, key);
            return {
                label: b.label,
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
                        callbacks: { label: (ctx) => `${ctx.dataset.label}: ${valueFormat(ctx.parsed.y)}` },
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

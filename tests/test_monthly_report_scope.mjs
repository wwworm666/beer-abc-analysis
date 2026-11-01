/**
 * Ежемесячный отчёт (/monthly-report) на общей полосе «Бар и период» (с 2026-11-01, план единого
 * виджета, этап 3): год и месяц ТОП-10 — из периода полосы, бар — общий выбор.
 *
 *     node tests/test_monthly_report_scope.mjs
 *
 * Проверяется: правило «что показывает отчёт» (monthlyScope) на примерах, в том числе январь
 * (прошлый год) и неполный месяц (ТОП-10 за последний закрытый с подписью); модуль
 * static/js/dashboard/modules/monthly_report.js с подменённой полосой — какие запросы уходят,
 * линии при «Все бары» и при одном баре, смена бара и года в полосе. Ядро периодов —
 * настоящее (period_core.js), часы страницы — 01.11.2026; Chart.js и DOM подменены.
 */

import assert from 'node:assert/strict';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);

let passed = 0;
let failed = 0;
async function test(name, fn) {
    try {
        await fn();
        passed++;
        console.log(`  ok  ${name}`);
    } catch (e) {
        failed++;
        console.log(`FAIL  ${name}`);
        console.log(`      ${e && e.message}`);
    }
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ---------------------------------------------------------------- окружение страницы
globalThis.window = globalThis;
require(path.join(ROOT, 'static/js/shared/period/period_core.js'));
const K = globalThis.KPeriod;
K.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });

function makeEl(id) {
    const el = {
        id, textContent: '', hidden: false, style: {}, children: [], className: '', _html: '',
        classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
                     toggle(c, on) { if (on) this._s.add(c); else this._s.delete(c); }, contains(c) { return this._s.has(c); } },
        appendChild(c) { this.children.push(c); return c; },
        addEventListener() {}, querySelectorAll() { return []; },
        getContext() { return { canvas: id }; }
    };
    // Как в браузере: innerHTML = '' убирает и узлы, добавленные appendChild.
    Object.defineProperty(el, 'innerHTML', {
        get() { return this._html; },
        set(v) { this._html = v; this.children = []; }
    });
    return el;
}
const nodes = {};
globalThis.document = {
    getElementById: (id) => (nodes[id] = nodes[id] || makeEl(id)),
    querySelectorAll: () => [],
    createElement: () => makeEl('created')
};
const charts = {};
globalThis.Chart = class {
    constructor(ctx, config) { this.config = config; charts[ctx.canvas] = this; }
    destroy() {}
};
const calls = [];
globalThis.fetch = (url) => {
    calls.push(url);
    const q = new URLSearchParams(url.split('?')[1] || '');
    const venue = q.get('venue');
    const year = q.get('years') || q.get('year');
    const series = (base) => Array.from({ length: 12 }, (_, i) => base + i);
    let body = {};
    if (url.startsWith('/api/monthly-report/top-guests')) {
        body = { guests: [{ name: 'Гость ' + venue + ' ' + q.get('month'), card: '1', visits: 3, spend: 1000 }] };
    } else if (url.startsWith('/api/monthly-report/loyalty')) {
        body = { data: { new_guests: series(10), revenue_card: series(100), revenue_nocard: series(50) } };
    } else if (url.startsWith('/api/monthly-report/draft-liters')) {
        body = { styles: ['Лагер'], series: { 'Лагер': series(5) } };
    } else {
        body = { refreshed_at: '2026-11-01T03:10', data: { [year]: { revenue: series(venue === 'all' ? 1000 : 100),
                 revenue_kitchen: series(1), revenue_packaged: series(2), revenue_draft: series(3) } } };
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
};
const SITE_BARS = [
    { key: 'bolshoy', name: 'Большой пр. В.О', short: 'ВО', iiko_name: 'Большой пр. В.О', bar_id: 'bar1' },
    { key: 'ligovskiy', name: 'Лиговский', short: 'Лиг', iiko_name: 'Лиговский', bar_id: 'bar2' },
    { key: 'kremenchugskaya', name: 'Кременчугская', short: 'Крем', iiko_name: 'Кременчугская', bar_id: 'bar3' },
    { key: 'varshavskaya', name: 'Варшавская', short: 'Вар', iiko_name: 'Варшавская', bar_id: 'bar4' }
];
const listeners = [];
const st = { bar: '', period: K.lastClosed('month') };   // правило страницы: последний закрытый месяц
globalThis.KStrip = {
    get: () => ({ bar: st.bar, period: st.period }),
    onChange: (fn) => listeners.push(fn),
    barInfo: (key) => SITE_BARS.find((b) => b.key === key) || null,
    config: { allLabel: 'Все бары' }
};
function choose(change) {
    if (change.bar !== undefined) st.bar = change.bar;
    if (change.period) st.period = change.period;
    listeners.forEach((fn) => fn({ type: change.bar !== undefined ? 'bar' : 'period', cause: 'user' }));
}

const { monthlyScope, monthlyReport } = await import(
    pathToFileURL(path.join(ROOT, 'static/js/dashboard/modules/monthly_report.js')).href);

// ---------------------------------------------------------------- правило monthlyScope

const OCT = { year: 2026, month: 10 };   // последний закрытый месяц на 01.11.2026
const month = (iso) => K.periodFor('month', K.fromISO(iso));
const year = (y) => K.periodFor('year', K.fromISO(y + '-01-01'));

await test('закрытый месяц: год отчёта — его год, ТОП-10 — он же', () => {
    const s = monthlyScope(month('2026-10-01'), OCT);
    assert.deepEqual({ ...s }, { year: 2026, month: 10, topMonth: 10, closedMonths: 10, note: '' });
});

await test('идущий месяц: ТОП-10 за последний закрытый, с подписью', () => {
    const s = monthlyScope(month('2026-11-01'), OCT);
    assert.equal(s.topMonth, 10);
    assert.equal(s.note, 'Ноябрь 2026 ещё идёт — ТОП-10 за октябрь 2026, последний закрытый месяц');
});

await test('прошлый год целиком: двенадцать закрытых месяцев, ТОП-10 за декабрь', () => {
    const s = monthlyScope(year(2025), OCT);
    assert.deepEqual([s.year, s.month, s.topMonth, s.closedMonths, s.note], [2025, 12, 12, 12, '']);
});

await test('текущий год: ТОП-10 за последний закрытый месяц, подпись про год', () => {
    const s = monthlyScope(year(2026), OCT);
    assert.equal(s.topMonth, 10);
    assert.match(s.note, /^2026 год ещё идёт — ТОП-10 за октябрь 2026/);
});

await test('неделя и свой период — месяц середины (у недели — четверга), у длинного — последний', () => {
    assert.equal(monthlyScope(K.periodFor('week', K.fromISO('2026-10-26')), OCT).month, 10, 'неделя 26 окт – 1 ноя — октябрь');
    const long = monthlyScope(K.customPeriod(K.fromISO('2024-03-01'), K.fromISO('2025-06-30')), OCT);
    assert.deepEqual([long.year, long.month, long.topMonth], [2025, 6, 6]);
});

await test('январь: без выбора — декабрь прошлого года; январь — закрытых месяцев ещё нет', () => {
    K.configure({ today: '2027-01-02', last_full_day: '2027-01-01', max_date: '2027-01-02' });
    try {
        const closed = K.lastClosed('month');
        assert.deepEqual([closed.start, closed.end], ['2026-12-01', '2026-12-31'], 'правило страницы в январе — декабрь');
        const dec = { year: 2026, month: 12 };
        const s = monthlyScope(closed, dec);
        assert.deepEqual([s.year, s.topMonth, s.closedMonths], [2026, 12, 12]);
        const jan = monthlyScope(month('2027-01-01'), dec);
        assert.deepEqual([jan.year, jan.topMonth, jan.closedMonths], [2027, null, 0]);
        assert.match(jan.note, /В 2027 году закрытых месяцев ещё нет/);
    } finally {
        K.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });
    }
});

// ---------------------------------------------------------------- модуль на полосе

monthlyReport.init();
await monthlyReport.load();

await test('открытие: октябрь 2026, «Все бары» — пять разрезов ядра, литры и ТОП-10 по всей сети', () => {
    const core = calls.filter((u) => u.startsWith('/api/monthly-report?'));
    assert.deepEqual(core.map((u) => new URLSearchParams(u.split('?')[1]).get('venue')).sort(),
        ['all', 'bolshoy', 'kremenchugskaya', 'ligovskiy', 'varshavskaya']);
    assert.ok(core.every((u) => u.includes('years=2026')), 'год не из полосы');
    const liters = calls.filter((u) => u.startsWith('/api/monthly-report/draft-liters'));
    assert.deepEqual(liters, ['/api/monthly-report/draft-liters?venue=all&year=2026'], 'литры не только по бару полосы');
    assert.ok(calls.includes('/api/monthly-report/top-guests?venue=all&year=2026&month=10'), 'ТОП-10 не за октябрь');
    assert.equal(nodes['mr-top-guests-sub'].textContent, 'Держатели карт лояльности за октябрь 2026 · Все бары');
    assert.equal(nodes['mr-top-note'].hidden, true);
    assert.equal(nodes['mr-stacked-note'].textContent, 'Графики с разбивкой, столбчатые и ТОП-10 — вся сеть (Все бары)');
});

await test('линии при «Все бары» — четыре бара с короткими именами, месяцы — только закрытые', () => {
    const cfg = charts['mr-revenue'].config;
    assert.deepEqual(cfg.data.datasets.map((d) => d.label), ['ВО', 'Лиг', 'Крем', 'Вар']);
    assert.equal(cfg.data.labels.length, 10, 'ноябрь (идёт) попал на график');
    assert.equal(nodes['mr-bar-buttons'].children.length, 4, 'в легенде не четыре бара');
    assert.deepEqual(charts['mr-revenue-stacked'].config.data.datasets.map((d) => d.data[0]), [1, 2, 3]);
});

await test('бар в полосе: линия только его, разбивки и ТОП-10 — по нему, ядро не грузится заново', async () => {
    calls.length = 0;
    choose({ bar: 'ligovskiy' });
    await sleep(380);
    for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
    assert.deepEqual(calls.filter((u) => u.startsWith('/api/monthly-report?')), [], 'ядро бара уже было загружено');
    assert.ok(calls.includes('/api/monthly-report/draft-liters?venue=ligovskiy&year=2026'));
    assert.ok(calls.includes('/api/monthly-report/top-guests?venue=ligovskiy&year=2026&month=10'));
    assert.deepEqual(charts['mr-revenue'].config.data.datasets.map((d) => d.label), ['Лиг'], 'при одном баре — одна линия (Р9)');
    assert.equal(nodes['mr-bar-buttons'].children.length, 1);
    assert.equal(nodes['mr-top-guests-sub'].textContent, 'Держатели карт лояльности за октябрь 2026 · Лиговский');
    assert.equal(nodes['mr-stacked-note'].textContent, 'Графики с разбивкой, столбчатые и ТОП-10 — Лиговский');
});

await test('идущий месяц в полосе: год тот же, ТОП-10 за октябрь с подписью', async () => {
    calls.length = 0;
    choose({ period: month('2026-11-01') });
    await sleep(380);
    for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
    assert.ok(calls.includes('/api/monthly-report/top-guests?venue=ligovskiy&year=2026&month=10'));
    assert.equal(nodes['mr-top-note'].hidden, false);
    assert.match(nodes['mr-top-note'].textContent, /Ноябрь 2026 ещё идёт/);
});

await test('другой год в полосе: данные года заново, ТОП-10 за декабрь, все двенадцать месяцев', async () => {
    calls.length = 0;
    choose({ period: year(2025) });
    await sleep(380);
    for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
    assert.ok(calls.includes('/api/monthly-report?venue=ligovskiy&years=2025'), 'ядро 2025 не загружено');
    assert.ok(calls.includes('/api/monthly-report/top-guests?venue=ligovskiy&year=2025&month=12'));
    assert.equal(charts['mr-revenue'].config.data.labels.length, 12);
    assert.equal(nodes['mr-top-note'].hidden, true);
});

await test('своих списков года, месяца и бара в модуле нет, часы устройства не нужны', async () => {
    const src = require('node:fs').readFileSync(path.join(ROOT, 'static/js/dashboard/modules/monthly_report.js'), 'utf8');
    for (const gone of ['mr-year', 'mr-top-month', 'mr-bar-select', '_buildYearSelect', 'stackedVenue', "'Общая'"]) {
        assert.ok(!src.includes(gone), 'в monthly_report.js осталось: ' + gone);
    }
    const tpl = require('node:fs').readFileSync(path.join(ROOT, 'templates/dashboard/monthly_tab.html'), 'utf8');
    assert.ok(!/<select/.test(tpl), 'в шаблоне остались списки');
    const page = require('node:fs').readFileSync(path.join(ROOT, 'templates/monthly_report.html'), 'utf8');
    assert.match(page, /kultura_strip\(mode='monthly', step='last_closed_month', live=True, steps=\['month', 'year'\]/);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

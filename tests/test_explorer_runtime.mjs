/**
 * ЗАПУСК конструктора отчётов (/explorer, static/js/explorer/page.js) в Node с DOM-стабом:
 * связка с полосой «Бар и период» (с 2026-11-01, план единого виджета, этап 3).
 *
 *     node tests/test_explorer_runtime.mjs
 *
 * Что проверяется: отчёт строится сам — сразу при открытии, после паузы в правке полей и в
 * смене бара или периода (кнопки «Построить» нет); в запрос идут даты полосы; бар полосы —
 * фильтр по полю бара типа отчёта (Store.Name у продаж), свой фильтр отчёта сильнее, у
 * типа без поля бара — подпись «по всей сети»; пресеты сервера — синонимы периодов полосы
 * (сохранение и открытие отчёта); черновик без периода; ошибка iiko — понятный текст и
 * «Повторить». Ядро периодов — настоящее (period_core.js, 01.11.2026), полоса и сводная
 * (grid.js) подменены, куба нет (страница работает и без cube.js).
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { bootStrip } from './abc_strip_stub.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const pageJs = read('static/js/explorer/page.js');

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
// Объекты из песочницы vm — со своими прототипами: для строгого сравнения — через JSON.
const plain = (x) => JSON.parse(JSON.stringify(x));
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)); };

// ---------------------------------------------------------------- данные страницы
// Как отдаёт routes/explorer.py: пресеты сервера на 01.11.2026 (рабочий день — воскресенье).
const BOOT = {
    report_types: [
        { id: 'SALES', title: 'Продажи', hint: '' }, { id: 'TRANSACTIONS', title: 'Проводки', hint: '' },
        { id: 'DELIVERIES', title: 'Доставка', hint: '' }, { id: 'STOCK', title: 'Контроль хранения', hint: '' }
    ],
    periods: [
        { id: 'yesterday', title: 'Вчера', date_from: '2026-10-31', date_to: '2026-10-31' },
        { id: 'today', title: 'Сегодня', date_from: '2026-11-01', date_to: '2026-11-01' },
        { id: 'this_week', title: 'Эта неделя', date_from: '2026-10-26', date_to: '2026-11-01' },
        { id: 'last_week', title: 'Прошлая неделя', date_from: '2026-10-19', date_to: '2026-10-25' },
        { id: 'this_month', title: 'Этот месяц', date_from: '2026-11-01', date_to: '2026-11-01' },
        { id: 'last_month', title: 'Прошлый месяц', date_from: '2026-10-01', date_to: '2026-10-31' },
        { id: 'last_7_days', title: 'Последние 7 дней', date_from: '2026-10-25', date_to: '2026-10-31' },
        { id: 'last_30_days', title: 'Последние 30 дней', date_from: '2026-10-02', date_to: '2026-10-31' },
        { id: 'this_year', title: 'Этот год', date_from: '2026-01-01', date_to: '2026-11-01' },
        { id: 'last_year', title: 'Прошлый год', date_from: '2025-01-01', date_to: '2025-12-31' }
    ],
    default: {
        report_type: 'SALES', rows: ['DishGroup.TopParent'], columns: ['Store.Name'],
        measures: ['DishDiscountSumInt', 'UniqOrderId'],
        filters: [{ field: 'DeletedWithWriteoff', op: 'in', values: ['NOT_DELETED'] },
                  { field: 'OrderDeleted', op: 'in', values: ['NOT_DELETED'] }],
        include_deleted: true
    },
    guarded_types: ['SALES', 'DELIVERIES'],
    guard_filters: [{ field: 'DeletedWithWriteoff', op: 'in', values: ['NOT_DELETED'] },
                    { field: 'OrderDeleted', op: 'in', values: ['NOT_DELETED'] }],
    limits: { rows: 6, columns: 3, measures: 10, filters: 12, leaves: 20000, recommended_fields: 7 },
    bar_fields: { SALES: 'Store.Name', DELIVERIES: 'Store.Name', TRANSACTIONS: 'Account.Name', STOCK: null }
};
const field = (id, name, extra) => Object.assign({ id, name, type: 'STRING', group: true, agg: false,
    filter_op: 'values', blocked: null, hint: '', tags: [] }, extra || {});
const CATALOG_SALES = {
    report_type: 'SALES', source: 'live', fetched_at: '2026-11-01 12:00', field_count: 6,
    fields: [
        field('DishGroup.TopParent', 'Группа блюда 1-го уровня'),
        field('Store.Name', 'Со склада'),
        field('DeletedWithWriteoff', 'Удалено со списанием', { type: 'ENUM' }),
        field('OrderDeleted', 'Заказ удалён', { type: 'ENUM' }),
        field('DishDiscountSumInt', 'Сумма со скидкой', { type: 'MONEY', group: false, agg: true, filter_op: null }),
        field('UniqOrderId', 'Чеков', { type: 'INTEGER', group: false, agg: true, filter_op: null })
    ],
    groups: [{ title: 'Избранное', ids: ['DishGroup.TopParent', 'Store.Name', 'DishDiscountSumInt', 'UniqOrderId',
                                         'DeletedWithWriteoff', 'OrderDeleted'] }]
};

// Сводная подменена: страница числа не считает, проверяется только связка.
const FakeGrid = {
    prepare: () => ({
        fields: { rows: [{ id: 'DishGroup.TopParent' }], columns: [], measures: [{ id: 'DishDiscountSumInt', name: 'Сумма' }] },
        tree: { ch: [1] }, columns: [], leaf_count: 1, warnings: [],
        meta: { date_from: '2026-10-26', date_to: '2026-11-01', date_to_exclusive: '2026-11-02',
                date_field_name: 'Учётный день', filters: [], totals: { sum: [], server: [] }, requests: [],
                fetched_at: '12:00', cached: false }
    }),
    render: () => ({ shown: 1, visible: 1 }),
    fmtDimText: (v) => String(v),
    isoDate: (v) => String(v)
};

// ---------------------------------------------------------------- DOM-стаб
function makeEl(id) {
    return {
        id, dataset: {}, style: { setProperty() {} }, value: '', textContent: '', innerHTML: '', title: '',
        hidden: false, disabled: false, className: '',
        classList: {
            _s: new Set(),
            add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
            toggle(c, on) { if (on === undefined ? !this._s.has(c) : on) this._s.add(c); else this._s.delete(c); },
            contains(c) { return this._s.has(c); }
        },
        listeners: {},
        addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
        querySelector() { return null; }, querySelectorAll() { return []; }, closest() { return null; },
        appendChild(c) { return c; }, insertAdjacentHTML() {}, setAttribute() {}, getAttribute() { return null; },
        getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; },
        focus() {}, remove() {}, contains() { return false; }
    };
}

function boot(opts) {
    opts = opts || {};
    const nodes = {};
    const bootEl = makeEl('exBoot');
    bootEl.textContent = JSON.stringify(BOOT);
    const get = (key) => (nodes[key] = nodes[key] || makeEl(key));
    const store = new Map(opts.storage || []);
    const calls = [];
    const sandbox = {
        console, Intl, Math, Number, String, Object, Array, JSON, Date, isNaN, Promise, URL, URLSearchParams,
        setTimeout, clearTimeout,
        document: {
            readyState: 'complete',
            getElementById: (id) => (id === 'exBoot' ? bootEl : get(id)),
            querySelector: (sel) => get(sel),
            querySelectorAll: () => [],
            addEventListener() {},
            createElement: () => makeEl('created'),
            body: makeEl('body')
        },
        location: { href: 'http://localhost/explorer' + (opts.search || ''), search: opts.search || '', hash: '' },
        history: { state: null, replaceState() {} },
        localStorage: {
            getItem: (k) => (store.has(k) ? store.get(k) : null),
            setItem: (k, v) => store.set(k, String(v)),
            removeItem: (k) => store.delete(k)
        },
        matchMedia: () => ({ matches: false }),
        innerWidth: 1280,
        addEventListener() {},
        ExplorerGrid: FakeGrid,
        ExplorerCube: null
    };
    sandbox.window = sandbox;
    sandbox.fetch = (url, init) => {
        const method = (init && init.method) || 'GET';
        const body = init && init.body ? JSON.parse(init.body) : null;
        calls.push({ url, method, body });
        const reply = (opts.reply || defaultReply)(url, method, body);
        return reply instanceof Error ? Promise.reject(reply)
            : Promise.resolve({ ok: reply.status < 400, status: reply.status,
                                text: () => Promise.resolve(typeof reply.body === 'string' ? reply.body : JSON.stringify(reply.body)) });
    };
    vm.createContext(sandbox);
    const strip = bootStrip(sandbox, 'week');
    new vm.Script(pageJs, { filename: 'page.js' }).runInContext(sandbox);
    return { sandbox, nodes: get, calls, strip, store, api: sandbox.__explorer };
}
function defaultReply(url) {
    if (url.indexOf('/api/explorer/columns') === 0) return { status: 200, body: CATALOG_SALES };
    if (url === '/api/explorer/report') return { status: 200, body: { leaf_count: 1 } };
    return { status: 404, body: { error: 'нет' } };
}
const reports = (env) => env.calls.filter((c) => c.url === '/api/explorer/report');
const barFilter = (body) => body.filters.find((f) => f.field === 'Store.Name');

// ---------------------------------------------------------------- проверки

const env = boot();
await flush();

await test('отчёт строится сам при открытии — за эту неделю полосы, без пресета', async () => {
    const r = reports(env);
    assert.equal(r.length, 1, 'при открытии отчёт не построился');
    assert.equal(r[0].method, 'POST');
    assert.deepEqual([r[0].body.date_from, r[0].body.date_to], ['2026-10-26', '2026-11-01']);
    assert.equal(r[0].body.period, undefined, 'в запросе пресет вместо дат полосы');
    assert.equal(barFilter(r[0].body), undefined, 'при «Все бары» фильтра бара быть не должно');
    assert.equal(r[0].body.format, 'pivot');
    assert.equal(env.nodes('exResult').hidden, false, 'результат не показан');
});

await test('бар в полосе — фильтр «Со склада» = имя iiko, построение через 350 мс', async () => {
    env.strip.choose({ bar: 'ligovskiy' });
    assert.equal(reports(env).length, 1, 'построение без паузы');
    await sleep(env.sandbox.KPeriod ? 420 : 0);
    await flush();
    const r = reports(env);
    assert.equal(r.length, 2, 'после смены бара отчёт не перестроился');
    assert.deepEqual(barFilter(r[1].body), { field: 'Store.Name', op: 'in', values: ['Лиговский'] });
    assert.ok(r[1].body.filters.some((f) => f.field === 'OrderDeleted'), 'фильтры отчёта потерялись');
    assert.match(env.nodes('exContext').innerHTML, /Бар: <b>Лиговский<\/b> — фильтр «Со склада»/);
    // В черновик и сохраняемый отчёт бар не попадает.
    assert.ok(!env.api.layoutConfig().filters.some((f) => f.field === 'Store.Name'));
    assert.ok(!env.api.currentConfig().filters.some((f) => f.field === 'Store.Name'));
});

await test('период в полосе — даты запроса, серия шагов — одно построение', async () => {
    const K = env.sandbox.KPeriod;
    env.strip.choose({ period: K.periodFor('week', K.fromISO('2026-10-12')) });
    env.strip.choose({ period: K.periodFor('week', K.fromISO('2026-10-19')) });
    await sleep(420);
    await flush();
    const r = reports(env);
    assert.equal(r.length, 3, 'на серию из двух шагов ушло ' + (r.length - 2) + ' построений');
    assert.deepEqual([r[2].body.date_from, r[2].body.date_to], ['2026-10-19', '2026-10-25']);
});

await test('правка полей — построение через секунду, черновик без периода', async () => {
    env.api.state.measures = ['DishDiscountSumInt'];
    env.api.changed();
    await sleep(700);
    assert.equal(reports(env).length, 3, 'построение раньше паузы после правки');
    await sleep(450);
    await flush();
    assert.equal(reports(env).length, 4, 'после правки отчёт не перестроился');
    assert.deepEqual(reports(env)[3].body.measures, ['DishDiscountSumInt']);
    const draft = JSON.parse(env.store.get('explorer.draft.v1'));
    assert.equal(draft.config.period, undefined, 'черновик хранит свой период');
    assert.deepEqual(draft.config.measures, ['DishDiscountSumInt']);
});

await test('отчёт без показателя не строится: подсказка вместо запроса', async () => {
    const before = reports(env).length;
    env.api.state.measures = [];
    env.api.changed();
    await sleep(1100);
    assert.equal(reports(env).length, before, 'неполный отчёт ушёл в iiko');
    assert.match(env.nodes('exMsgBody').innerHTML, /Отчёт построится сам/);
    env.api.state.measures = ['DishDiscountSumInt', 'UniqOrderId'];
    env.api.changed();
    await sleep(1100);
    await flush();
});

await test('свой фильтр отчёта по полю бара сильнее полосы; у типа без поля бара — вся сеть', async () => {
    env.api.state.filters.push({ field: 'Store.Name', op: 'in', values: ['Варшавская'] });
    const own = env.api.barScope();
    assert.equal(own.state, 'own');
    const body = env.api.requestPayload('pivot');
    assert.deepEqual(body.filters.filter((f) => f.field === 'Store.Name'), [{ field: 'Store.Name', op: 'in', values: ['Варшавская'] }]);
    env.api.state.filters.pop();
    const keep = env.api.state.type;
    env.api.state.type = 'STOCK';
    env.api.state.catalogs.STOCK = { byId: { ProductName: field('ProductName', 'Товар') } };
    assert.equal(env.api.barScope().state, 'network');
    assert.deepEqual(plain(env.api.requestPayload('pivot').filters), plain(env.api.state.filters),
        'у контроля хранения к фильтрам отчёта добавился фильтр бара');
    env.api.state.type = 'TRANSACTIONS';
    env.api.state.catalogs.TRANSACTIONS = { byId: { 'Account.Name': field('Account.Name', 'Счет') } };
    assert.equal(env.api.barScope().value, 'Лиговский');
    assert.equal(env.api.barScope().field, 'Account.Name');
    env.api.state.type = keep;
});

await test('пресеты сервера — синонимы периодов полосы (сохранение отчёта)', async () => {
    const K = env.sandbox.KPeriod;
    const of = (p) => env.api.presetOf({ from: p.start, to: p.end, period: p });
    assert.equal(of(K.lastClosed('week')), 'last_week');
    assert.equal(of(K.currentPeriod('week')), 'this_week', 'текущая неделя полосы (пн–вс) — this_week');
    assert.equal(of(K.currentPeriod('month')), 'this_month');
    assert.equal(of(K.lastClosed('month')), 'last_month');
    assert.equal(of(K.lastDays(30)), 'last_30_days');
    assert.equal(of(K.periodFor('day', K.fromISO('2026-10-31'))), 'yesterday');
    assert.equal(of(K.lastClosed('year')), 'last_year');
    assert.equal(of(K.customPeriod(K.fromISO('2026-03-01'), K.fromISO('2026-05-10'))), null);
    assert.equal(of(K.QUICK.ytd.build()), 'this_year', '«С начала года» — те же даты, что у this_year');
    env.strip.choose({ period: K.lastClosed('week') });
    assert.deepEqual(plain(env.api.currentConfig().period), { preset: 'last_week' });
    env.strip.choose({ period: K.customPeriod(K.fromISO('2026-03-01'), K.fromISO('2026-05-10')) });
    assert.deepEqual(plain(env.api.currentConfig().period), { from: '2026-03-01', to: '2026-05-10' });
    await sleep(420);
    await flush();
});

await test('открытый сохранённый отчёт делает свой период общим выбором (KStrip.setPeriod)', async () => {
    const K = env.sandbox.KPeriod;
    const p1 = env.api.stripPeriodOf({ preset: 'last_week' });
    assert.deepEqual([p1.start, p1.end, p1.granularity], ['2026-10-19', '2026-10-25', 'week']);
    const p2 = env.api.stripPeriodOf({ preset: 'this_month' });
    assert.deepEqual([p2.start, p2.end, p2.granularity], ['2026-11-01', '2026-11-30', 'month'],
        'текущий месяц — целый, «идёт», а не 1–1 ноября');
    const p3 = env.api.stripPeriodOf({ from: '2025-12-01', to: '2025-12-31' });
    assert.equal(p3.granularity, 'month');
    assert.equal(env.api.stripPeriodOf({ from: '2026-05-10', to: '2026-03-01' }), null, 'перевёрнутые даты');
    env.strip.setCalls.length = 0;
    env.api.applyReportPeriod({ preset: 'last_month' });
    assert.equal(env.strip.setCalls.length, 1);
    assert.deepEqual([env.strip.setCalls[0].start, env.strip.setCalls[0].end], ['2026-10-01', '2026-10-31']);
    env.api.applyReportPeriod({ preset: 'last_month' });
    assert.equal(env.strip.setCalls.length, 1, 'тот же период выбран повторно');
    assert.ok(K);
    await sleep(420);
    await flush();
});

// Ошибки: отдельная страница, где построение падает.
const fail502 = boot({ reply: (url) => (url.indexOf('/api/explorer/columns') === 0 ? { status: 200, body: CATALOG_SALES }
    : { status: 504, body: { error: 'iiko не ответил за 120 с. Сузьте период или уберите поля с большим числом значений.', code: 'iiko' } }) });
await flush();
await test('тайм-аут iiko с причиной от сервера — причина и кнопка «Повторить»', async () => {
    const html = fail502.nodes('exMsgBody').innerHTML;
    assert.match(html, /Отчёт не построен/);
    assert.match(html, /iiko не ответил за 120 с\. Сузьте период/);
    assert.match(html, /data-retry>Повторить</);
});
const failNet = boot({ reply: (url) => (url.indexOf('/api/explorer/columns') === 0 ? { status: 200, body: CATALOG_SALES }
    : (url === '/api/explorer/report' ? new TypeError('Failed to fetch') : { status: 404, body: {} })) });
await flush();
await test('ответа нет совсем — «iiko не успел ответить — сократите период»', async () => {
    assert.match(failNet.nodes('exMsgBody').innerHTML, /iiko не успел ответить — сократите период/);
    assert.match(failNet.nodes('exMsgBody').innerHTML, /data-retry/);
});
const failProxy = boot({ reply: (url) => (url.indexOf('/api/explorer/columns') === 0 ? { status: 200, body: CATALOG_SALES }
    : { status: 502, body: '<html>502 Bad Gateway</html>' }) });
await flush();
await test('страница ошибки прокси без JSON — та же просьба сократить период', async () => {
    assert.match(failProxy.nodes('exMsgBody').innerHTML, /iiko не успел ответить — сократите период/);
});

await test('своего меню периода и кнопки «Построить» в коде нет', async () => {
    for (const gone of ['buildPeriodMenu', 'exPerBtn', 'exRun', "'Построить'", 'state.period', 'нажмите «Построить»']) {
        assert.ok(!pageJs.includes(gone), 'в page.js осталось: ' + gone);
    }
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

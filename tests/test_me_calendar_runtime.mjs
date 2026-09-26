/**
 * Календарь «Мой график» на /me: статусы смен видны в ячейках, легенда не врёт.
 *
 *     node tests/test_me_calendar_runtime.mjs
 *
 * Настоящие common.js + screens.js исполняются в Node на подставном месяце
 * (смены всех статусов), разметка renderMyShifts проверяется по классам ячеек.
 *
 * Зачем: на /me плашки плоские (flatBars), и статус там рисует CSS страницы по
 * классам ячейки. Раньше классов не было — «ждёт факт» и конфликт выглядели
 * как отработанная смена, хотя легенда обещала кольцо. Связка «JS пишет класс —
 * me.css его красит» ломается молча, поэтому проверяются обе стороны.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const meCss = read('static/me/me.css');
const scheduleCss = read('static/schedule/schedule.css');

let passed = 0;
let failed = 0;
function test(name, fn) {
    try {
        fn();
        passed++;
        console.log(`  ok  ${name}`);
    } catch (e) {
        failed++;
        console.log(`FAIL  ${name}`);
        console.log(`      ${e && e.message}`);
    }
}

// ---------------------------------------------------------------- стенд
const TODAY = '2026-09-26';
const EMP = 'Макарова Татьяна';

function shift(id, day, loc, eve, fact) {
    return {
        id, date: '2026-09-' + day, location_id: loc, employee_id: 'e1', employee_name: EMP,
        role_name: eve ? 'второй бармен' : 'бармен', start_time: eve ? '18:00' : '14:00',
        fact_minutes: fact, cash_end_kop: fact != null ? 100 : null
    };
}

function boot({ dayOffs }) {
    const sandbox = { console, Math, Number, String, Object, Array, JSON, Date, isNaN, Promise };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    for (const f of ['static/js/schedule/common.js', 'static/js/schedule/screens.js']) {
        new vm.Script(read(f), { filename: f }).runInContext(sandbox);
    }
    const S = sandbox.Schedule;
    S.todayStr = () => TODAY;
    S.state.year = 2026;
    S.state.month = 9;
    S.state.locations = [
        { id: 1, name: 'Варшавская', short_name: 'Вар', venue_key: 'varshavskaya' },
        { id: 2, name: 'Большой', short_name: 'ВО', venue_key: 'bolshoy' }
    ];
    S.state.employees = [{ id: 'e1', name: EMP }];
    S.state.shifts = [
        shift(1, '12', 1, false, null),   // прошла без факта  -> nofact
        shift(2, '18', 1, false, 720),    // прошла с фактом   -> done
        shift(3, '23', 2, false, 700),    // выходной по заявке -> conflict
        shift(4, '26', 1, false, null),   // сегодня           -> today
        shift(5, '29', 2, true, null)     // впереди, вечер    -> soon
    ];
    S.state.dayOffs = dayOffs;
    return S;
}

function render(S, opts) {
    const host = { innerHTML: '', querySelectorAll: () => [] };
    S.renderMyShifts(host, Object.assign({ employeeIikoId: 'e1' }, opts));
    return host.innerHTML;
}

// { '12': { cls: Set, bar: 'style…' | null } }
function cells(html) {
    const out = {};
    const re = /<div class="(ms-cell[^"]*)" data-n="(\d+)"><span[^>]*>\d+<\/span><span class="ms-cwrap">(.*?)<\/span><\/div>/g;
    let m;
    while ((m = re.exec(html))) {
        const bar = /class="ms-cbar" style="([^"]*)"/.exec(m[3]);
        out[m[2]] = { cls: new Set(m[1].split(/\s+/)), bar: bar ? bar[1] : null };
    }
    return out;
}

const DAYOFFS = [
    { employee_name: EMP, date_from: '2026-09-23', date_to: '2026-09-23' },
    { employee_name: EMP, date_from: '2026-09-28', date_to: '2026-09-28' }
];
const ME_OPTS = { dayFirst: true, monthTitle: true, chips: false, flatBars: true };

const meHtml = render(boot({ dayOffs: DAYOFFS }), ME_OPTS);
const me = cells(meHtml);

// ---------------------------------------------------------------- ячейки
test('ячейка несёт статус смены классом st-<статус>', () => {
    assert.ok(me['12'].cls.has('st-nofact'), '12-е: прошла без факта');
    assert.ok(me['18'].cls.has('st-done'), '18-е: отработана');
    assert.ok(me['23'].cls.has('st-conflict'), '23-е: смена в день заявки на выходной');
    assert.ok(me['26'].cls.has('st-today'), '26-е: сегодня');
    assert.ok(me['29'].cls.has('st-soon'), '29-е: впереди');
});

test('is-past — только у прошедших смен, не у сегодня и не у пустых дней', () => {
    for (const n of ['12', '18', '23']) assert.ok(me[n].cls.has('is-past'), n + '-е прошло');
    for (const n of ['26', '29']) assert.ok(!me[n].cls.has('is-past'), n + '-е не прошло');
    assert.ok(!me['11'].cls.has('is-past'), 'день без смены не должен получать is-past');
    assert.ok(![...me['28'].cls].some((c) => c.startsWith('st-')),
        'выходной по заявке без смены — не статус смены');
});

test('плоская плашка /me: только цвет и размер, яркость и кольцо — дело CSS', () => {
    for (const n of ['12', '18', '23', '26', '29']) {
        assert.ok(me[n].bar, n + '-е: нет плашки');
        assert.doesNotMatch(me[n].bar, /opacity/, n + '-е: прозрачность инлайном перебьёт CSS темы');
        assert.doesNotMatch(me[n].bar, /(^|;)border:/, n + '-е: у плоской плашки рамки нет');
    }
    assert.match(me['29'].bar, /height:9px/, 'вечерняя смена — низкая плашка');
    assert.match(me['26'].bar, /height:17px/, 'дневная смена — высокая плашка');
});

test('/schedule не задет: там статус по-прежнему рисует сама плашка', () => {
    const sch = cells(render(boot({ dayOffs: DAYOFFS }), {}));
    assert.match(sch['12'].bar, /border:2px solid/, 'ждёт факт — рамка на плашке');
    assert.match(sch['23'].bar, /border:2px solid/, 'конфликт — рамка на плашке');
    assert.match(sch['18'].bar, /rgba\([^)]*,0\.45\)/, 'отработана — приглушена');
    assert.match(sch['29'].bar, /rgba\([^)]*,0\.9\)/, 'предстоит — ярко');
});

// ---------------------------------------------------------------- легенда
test('легенда: кольца классами, без инлайнового цвета', () => {
    assert.match(meHtml, /class="ms-lgi ms-lg-today">кольцо — сегодня/);
    assert.match(meHtml, /class="ms-lgi ms-lg-nofact">кольцо — ждёт факт/);
    assert.match(meHtml, /бледная — прошла/, 'яркость плашки не объяснена');
    assert.doesNotMatch(meHtml, /class="ms-lgi" style="color/,
        'инлайновый цвет не даст /me перекрасить пункт под свои кольца');
});

test('легенда: пункт о конфликте — только если конфликт в месяце есть', () => {
    assert.match(meHtml, /ms-lg-conflict/);
    const calm = render(boot({ dayOffs: [DAYOFFS[1]] }), ME_OPTS);
    assert.doesNotMatch(calm, /ms-lg-conflict/);
});

// ---------------------------------------------------------------- CSS
test('me.css красит классы, которые пишет JS', () => {
    assert.match(meCss, /\.ms-cell\.st-nofact\s*\{[^}]*var\(--me-warn\)/, 'нет кольца «ждёт факт»');
    assert.match(meCss, /\.ms-cell\.st-conflict\s*\{[^}]*var\(--me-bad\)/, 'нет кольца конфликта');
    assert.match(meCss, /\.ms-cell\.is-past \.ms-cbar\s*\{[^}]*var\(--me-bar-past\)/,
        'прошедшая плашка не бледнеет');
    assert.equal((meCss.match(/--me-bar-past:\s*[\d.]+/g) || []).length, 2,
        '--me-bar-past нужен в светлой и в тёмной теме');
    assert.match(meCss, /\.ms-cell\.is-today\.is-sel\s*\{[^}]*var\(--me-today\)/,
        'выбор перекроет рамку «сегодня», и легенда разойдётся с экраном');
    for (const k of ['today', 'nofact', 'conflict']) {
        assert.match(meCss, new RegExp('\\.ms-lg-' + k + '::before'), 'нет образца кольца ' + k);
    }
});

test('schedule.css держит прежние цвета пунктов легенды', () => {
    assert.match(scheduleCss, /\.ms-lg-today\s*\{\s*color:\s*var\(--sh-ring-today\)/);
    assert.match(scheduleCss, /\.ms-lg-nofact\s*\{\s*color:\s*var\(--sh-ring-nofact\)/);
    assert.match(scheduleCss, /\.ms-lg-conflict\s*\{\s*color:\s*var\(--sh-ring-conflict\)/);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

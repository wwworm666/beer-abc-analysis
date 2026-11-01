/**
 * График на полосе «Бар и период»: месяц — из полосы, без полосы — месяц рабочего дня бара,
 * выбранный бар выделен, а все точки остаются (ответ владельца Р9).
 *
 *     node tests/test_schedule_strip_runtime.mjs
 *
 * Настоящие period_core.js, common.js и screens.js исполняются в Node; полоса (window.KStrip) —
 * подставная, её период и бар меняет тест.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

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
        console.log(`      ${e && e.stack}`);
    }
}

// ---------------------------------------------------------------- стенд

const LOCATIONS = [
    { id: 1, name: 'Варшавская', short_name: 'Вар', venue_key: 'varshavskaya' },
    { id: 2, name: 'Большой', short_name: 'ВО', venue_key: 'bolshoy' },
    { id: 3, name: 'Кременчугская', short_name: 'Крем', venue_key: 'kremenchugskaya' },
    { id: 4, name: 'Лиговский', short_name: 'Лиг', venue_key: 'ligovskiy' }
];

// nowMs — «часы устройства» для запасного пути без полосы.
function boot({ strip, nowMs } = {}) {
    const RealDate = Date;
    class FakeDate extends RealDate {
        constructor(...args) { super(...(args.length ? args : [nowMs === undefined ? RealDate.now() : nowMs])); }
        static now() { return nowMs === undefined ? RealDate.now() : nowMs; }
    }
    const sandbox = { console, Math, Number, String, Object, Array, JSON, Date: FakeDate, isNaN, Promise, parseInt, parseFloat };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    new vm.Script(read('static/js/shared/period/period_core.js'), { filename: 'period_core.js' }).runInContext(sandbox);
    if (strip) sandbox.KStrip = strip;
    for (const f of ['static/js/schedule/common.js', 'static/js/schedule/screens.js']) {
        new vm.Script(read(f), { filename: f }).runInContext(sandbox);
    }
    const S = sandbox.Schedule;
    S.state.locations = LOCATIONS;
    return { S, sandbox };
}

function fakeStrip(period, bar) {
    const st = { period, bar: bar || '' };
    return { get: () => ({ period: st.period, bar: st.bar }), _st: st };
}

const month = (start, end) => ({ granularity: 'month', start, end, key: start + '_' + end });
const week = (start, end) => ({ granularity: 'week', start, end, key: start + '_' + end });

function host() {
    return { innerHTML: '', querySelectorAll: () => [], style: { setProperty() {}, removeProperty() {} } };
}

// ---------------------------------------------------------------- месяц

test('месяц графика — показанный в полосе', () => {
    const { S } = boot({ strip: fakeStrip(month('2026-12-01', '2026-12-31')) });
    assert.equal(S.state.year, 2026);
    assert.equal(S.state.month, 12, 'будущий месяц — график планируют вперёд');
});

test('неделя в полосе — месяц её четверга (Р3)', () => {
    const { S } = boot({ strip: fakeStrip(week('2026-10-26', '2026-11-01')) });
    assert.equal(`${S.state.year}-${S.state.month}`, '2026-10');
});

test('без полосы — месяц рабочего дня: 1-е число до 06:00 МСК — ещё прошлый месяц', () => {
    // 01.11.2026 02:00 МСК = 31.10.2026 23:00 UTC
    const { S } = boot({ nowMs: Date.UTC(2026, 9, 31, 23, 0) });
    assert.equal(`${S.state.year}-${S.state.month}`, '2026-10');
    // 01.11.2026 07:00 МСК — уже ноябрь
    const later = boot({ nowMs: Date.UTC(2026, 10, 1, 4, 0) }).S;
    assert.equal(`${later.state.year}-${later.state.month}`, '2026-11');
});

test('смена месяца в полосе — syncMonthFromStrip сообщает, что надо перезагрузить', () => {
    const strip = fakeStrip(month('2026-10-01', '2026-10-31'));
    const { S } = boot({ strip });
    assert.equal(S.syncMonthFromStrip(), false, 'тот же месяц — без перезагрузки');
    strip._st.period = month('2026-09-01', '2026-09-30');
    assert.equal(S.syncMonthFromStrip(), true);
    assert.equal(`${S.state.year}-${S.state.month}`, '2026-9');
});

// ---------------------------------------------------------------- бар (Р9)

test('точка бара — по locations.venue_key; «Все бары» и чужой ключ — null', () => {
    const strip = fakeStrip(month('2026-10-01', '2026-10-31'), 'ligovskiy');
    const { S } = boot({ strip });
    assert.equal(S.focusLocationId(), 4);
    strip._st.bar = '';
    assert.equal(S.focusLocationId(), null);
    strip._st.bar = 'bar9';
    assert.equal(S.focusLocationId(), null);
});

function withShifts(S) {
    S.todayStr = () => '2026-10-15';
    S.state.year = 2026;
    S.state.month = 10;
    S.state.employees = [{ id: 'e1', name: 'Иван Петров' }];
    S.state.dayOffs = [];
    S.state.shifts = [
        { id: 1, date: '2026-10-20', location_id: 1, employee_id: 'e1', employee_name: 'Иван Петров', role_name: 'бармен', fact_minutes: null },
        { id: 2, date: '2026-10-21', location_id: 4, employee_id: 'e1', employee_name: 'Иван Петров', role_name: 'бармен', fact_minutes: null }
    ];
}

test('полосы по людям: все точки на месте, чужие приглушены, выбранная — как есть', () => {
    const strip = fakeStrip(month('2026-10-01', '2026-10-31'), 'ligovskiy');
    const { S } = boot({ strip });
    withShifts(S);
    const h = host();
    S.renderEditLanes(h, {});
    const cell = (ds) => new RegExp(`<div class="el-cell([^"]*)"[^>]*data-ds="${ds}"[^>]*data-shift-id`).exec(h.innerHTML);
    const varCell = cell('2026-10-20');
    const ligCell = cell('2026-10-21');
    assert.ok(varCell && ligCell, 'обе смены нарисованы — сетка не сужается до бара');
    assert.match(varCell[1], /is-dim/);
    assert.match(ligCell[1], /is-focus/);
    // Заливка чужой точки — доля яркости, рамка статуса (сегодня/ждёт факт) не меняется.
    assert.match(h.innerHTML, /rgba\(111,147,166,0\.315\)/, 'Вар: 0.9 x 0.35');
    assert.match(h.innerHTML, /rgba\(125,155,107,0\.9\)/, 'Лиг: полная яркость');
});

test('«Все бары» — без приглушения', () => {
    const { S } = boot({ strip: fakeStrip(month('2026-10-01', '2026-10-31'), '') });
    withShifts(S);
    const h = host();
    S.renderEditLanes(h, {});
    assert.doesNotMatch(h.innerHTML, /is-dim|is-focus/);
});

test('«Что сейчас»: карточка выбранной точки выделена, остальные приглушены', () => {
    const { S } = boot({ strip: fakeStrip(month('2026-10-01', '2026-10-31'), 'varshavskaya') });
    withShifts(S);
    const h = host();
    S.renderTodayBoard(h);
    assert.equal((h.innerHTML.match(/tb-card is-focus/g) || []).length, 1);
    assert.equal((h.innerHTML.match(/tb-card is-dim/g) || []).length, 3);
});

test('«План / Факт»: колонка выбранной точки выделена', () => {
    const { S } = boot({ strip: fakeStrip(month('2026-10-01', '2026-10-31'), 'bolshoy') });
    withShifts(S);
    S.state.plans = { days: { '2026-10-20': { plan_total: 100, fact_total: 90,
        locations: { 1: { plan: 50, fact: 40 }, 2: { plan: 50, fact: 50 } } } } };
    const h = host();
    S.renderPlanFact(h);
    assert.match(h.innerHTML, /<th class="pf-tt pf-focus" title="Большой">/);
    assert.equal((h.innerHTML.match(/<th class="pf-tt pf-focus"/g) || []).length, 1);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);

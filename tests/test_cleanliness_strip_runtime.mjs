/**
 * «Чистота» на полосе «Бар и период»: месяц — из полосы, бар — точка графика с тем же ключом
 * (locations.venue_key), фильтры журнала работают поверх бара.
 *
 *     node tests/test_cleanliness_strip_runtime.mjs
 *
 * Настоящие period_core.js и static/js/cleanliness/view.js исполняются в Node без DOM: страница
 * отдаёт чистые помощники в window.CleanlinessView.
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

function boot(strip) {
    const sandbox = { console, Math, Number, String, Object, Array, JSON, Date, isNaN, Promise };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    new vm.Script(read('static/js/shared/period/period_core.js'), { filename: 'period_core.js' }).runInContext(sandbox);
    if (strip) sandbox.KStrip = strip;
    new vm.Script(read('static/js/cleanliness/view.js'), { filename: 'view.js' }).runInContext(sandbox);
    return sandbox.CleanlinessView;
}

const PLACES = [
    { id: 1, name: 'Варшавская', venue_key: 'varshavskaya' },
    { id: 4, name: 'Лиговский', venue_key: 'ligovskiy' }
];
const ROWS = [
    { location_id: 1, status: 'clean', problems: [], employee_name: 'Анна', note: '' },
    { location_id: 4, status: 'bad', problems: [], employee_name: 'Борис', note: 'краны не промыты' },
    { location_id: 4, status: null, problems: ['not_marked'], employee_name: 'Вера', note: '' }
];

test('бар полосы -> точка графика по venue_key; «Все бары» — null, чужой бар — undefined', () => {
    const V = boot();
    assert.equal(V.locationIdForBar('ligovskiy', PLACES), 4);
    assert.equal(V.locationIdForBar('', PLACES), null);
    assert.equal(V.locationIdForBar('bolshoy', PLACES), undefined, 'точки бара нет в графике');
});

test('строки бара и фильтры журнала поверх него', () => {
    const V = boot();
    assert.equal(V.filterRows(ROWS, {}).length, 3, 'все бары — все точки');
    assert.deepEqual(V.filterRows(ROWS, { locationId: 4 }).map((r) => r.employee_name), ['Борис', 'Вера']);
    assert.deepEqual(V.filterRows(ROWS, { locationId: 4, status: 'not_marked' }).map((r) => r.employee_name), ['Вера']);
    assert.deepEqual(V.filterRows(ROWS, { locationId: null, q: 'КРАНЫ' }).map((r) => r.employee_name), ['Борис']);
});

test('месяц — из полосы; неделя — месяц её четверга', () => {
    const month = { granularity: 'month', start: '2026-09-01', end: '2026-09-30' };
    assert.deepEqual({ ...boot({ get: () => ({ period: month, bar: '' }) }).stripMonth() }, { year: 2026, month: 9 });
    const week = { granularity: 'week', start: '2026-10-26', end: '2026-11-01' };
    assert.deepEqual({ ...boot({ get: () => ({ period: week, bar: '' }) }).stripMonth() }, { year: 2026, month: 10 });
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);

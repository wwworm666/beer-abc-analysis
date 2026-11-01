/**
 * Тесты модели периода дашборда (static/js/dashboard/core/period_model.js).
 *
 *     node tests/test_period_model.mjs
 *
 * С 2026-11-01 модель дашборда — обёртка над общим ядром стандарта периодов
 * (static/js/shared/period/period_core.js; его арифметика и подписи — tests/test_period_core.mjs).
 * Здесь — то, что важно именно дашборду: обёртка отдаёт функции ядра, период по умолчанию —
 * последняя закрытая неделя по учётному дню с СЕРВЕРА (не по часам устройства), месяц и год
 * месячных вкладок, бейдж идущего периода, зажим числа при шаге по месяцам.
 */

import assert from 'node:assert/strict';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Как на странице: ядро — обычным скриптом до модулей дашборда (window.KPeriod).
globalThis.window = globalThis;
const require = createRequire(import.meta.url);
require(path.join(ROOT, 'static/js/shared/period/period_core.js'));
const K = globalThis.KPeriod;
const pm = await import(pathToFileURL(path.join(ROOT, 'static/js/dashboard/core/period_model.js')).href);

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
const d = (iso) => K.fromISO(iso);

test('обёртка отдаёт функции общего ядра, а не свою копию', () => {
    for (const name of ['periodFor', 'shiftPeriod', 'changeGranularity', 'periodTitle', 'toISO',
                        'fromISO', 'monthYearOf', 'progressBadge', 'periodFromSelection']) {
        assert.equal(pm[name], K[name], name);
    }
});

test('по умолчанию — последняя закрытая неделя по учётному дню с сервера', () => {
    K.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });
    const p = pm.defaultPeriod();
    assert.deepEqual([p.granularity, p.start, p.end], ['week', '2026-10-19', '2026-10-25'],
        'воскресенье 1 ноября ещё идёт — неделя 26 окт – 1 ноя не закрыта');
    K.configure({ today: '2026-11-02', last_full_day: '2026-11-01', max_date: '2026-11-02' });
    assert.equal(pm.defaultPeriod().start, '2026-10-26', 'в понедельник закрыта прошлая неделя');
    // Ночь на понедельник до 06:00 — ещё воскресенье: сервер отдаёт учётный день 1 ноября.
    K.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });
    assert.equal(pm.defaultPeriod().start, '2026-10-19');
    assert.equal(pm.toISO(pm.today()), '2026-11-01', '«сегодня» — с сервера');
});

test('название периода в шапке — с годом, неделя — датами', () => {
    assert.equal(pm.periodTitle(pm.periodFor('week', d('2026-10-28'))), '26 окт – 1 ноя 2026');
    assert.equal(pm.periodTitle(pm.periodFor('month', d('2026-10-28'))), 'Октябрь 2026');
});

test('месяц и год месячных вкладок — строка с ведущим нулём и число', () => {
    assert.deepEqual(pm.monthYearOf(pm.periodFor('week', d('2026-03-04'))), { month: '03', year: 2026 });
});

test('бейдж идущего периода — сколько дней прошло по последний доступный день', () => {
    K.configure({ today: '2026-10-29', last_full_day: '2026-10-28', max_date: '2026-10-29' });
    assert.equal(pm.progressBadge(pm.periodFor('month', d('2026-10-01'))), 'прошло 29 из 31 дня');
    assert.equal(pm.progressBadge(pm.periodFor('month', d('2026-09-01'))), null, 'закрытый — без бейджа');
    assert.equal(pm.progressBadge(pm.periodFor('month', d('2026-11-01'))), 'период ещё не начался');
});

test('шаг по месяцам зажимает число: 31 января + 1 месяц = 28 февраля', () => {
    assert.equal(pm.toISO(pm.addMonths(d('2026-01-31'), 1)), '2026-02-28');
    assert.equal(pm.shiftPeriod(pm.periodFor('month', d('2026-01-31')), 1).end, '2026-02-28');
});

test('ключ периода — как у /api/weeks и комментариев: YYYY-MM-DD_YYYY-MM-DD', () => {
    assert.equal(pm.periodFor('week', d('2026-10-28')).key, '2026-10-26_2026-11-01');
});

console.log(`\n${passed} ok, ${failed} failed`);
if (failed) process.exit(1);

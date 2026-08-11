/**
 * Тесты модели периода дашборда (static/js/dashboard/core/period_model.js).
 *
 * Чистая арифметика дат, без DOM и без сети — запускается голым Node:
 *     node tests/test_period_model.mjs
 *
 * Что защищаем: границы гранулярностей, шаг стрелки, переход через границы
 * месяца/года, формат ключа периода и бейдж незавершённого периода.
 */

import assert from 'node:assert/strict';
import {
    CUSTOM,
    addMonths,
    changeGranularity,
    customPeriod,
    daysBetweenInclusive,
    defaultPeriod,
    detectGranularity,
    formatSubLabel,
    isoWeekNumber,
    monthYearOf,
    periodFor,
    periodFromSelection,
    periodProgress,
    pluralDays,
    progressBadge,
    shiftPeriod,
    startOfWeek,
    toISO
} from '../static/js/dashboard/core/period_model.js';

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
        console.log(`      ${e.message}`);
    }
}

/** Локальная дата без сюрпризов таймзоны. */
const D = (y, m, d) => new Date(y, m - 1, d);

console.log('\n--- границы гранулярностей ---');

test('день = сам себе период', () => {
    const p = periodFor('day', D(2026, 8, 11));
    assert.equal(p.start, '2026-08-11');
    assert.equal(p.end, '2026-08-11');
});

test('неделя = понедельник..воскресенье', () => {
    // 11.08.2026 — вторник
    const p = periodFor('week', D(2026, 8, 11));
    assert.equal(p.start, '2026-08-10');
    assert.equal(p.end, '2026-08-16');
});

test('неделя от воскресенья берёт ПРЕДЫДУЩИЙ понедельник (ISO, не US)', () => {
    // 16.08.2026 — воскресенье, оно закрывает неделю с 10.08
    const p = periodFor('week', D(2026, 8, 16));
    assert.equal(p.start, '2026-08-10');
    assert.equal(p.end, '2026-08-16');
});

test('месяц = 1-е..последнее число', () => {
    const p = periodFor('month', D(2026, 2, 17));
    assert.equal(p.start, '2026-02-01');
    assert.equal(p.end, '2026-02-28');
});

test('февраль високосного года = 29 дней', () => {
    const p = periodFor('month', D(2028, 2, 5));
    assert.equal(p.end, '2028-02-29');
});

test('год = 01.01..31.12', () => {
    const p = periodFor('year', D(2026, 8, 11));
    assert.equal(p.start, '2026-01-01');
    assert.equal(p.end, '2026-12-31');
});

console.log('\n--- шаг стрелки ---');

test('день назад', () => {
    assert.equal(shiftPeriod(periodFor('day', D(2026, 8, 11)), -1).start, '2026-08-10');
});

test('день через границу месяца', () => {
    const p = shiftPeriod(periodFor('day', D(2026, 9, 1)), -1);
    assert.equal(p.start, '2026-08-31');
});

test('неделя назад = ровно 7 дней', () => {
    const p = shiftPeriod(periodFor('week', D(2026, 8, 11)), -1);
    assert.equal(p.start, '2026-08-03');
    assert.equal(p.end, '2026-08-09');
});

test('месяц назад с 31-го не переполняет февраль', () => {
    // Штатный Date.setMonth дал бы 03.03 — проверяем зажим числа.
    const p = shiftPeriod(periodFor('month', D(2026, 3, 31)), -1);
    assert.equal(p.start, '2026-02-01');
    assert.equal(p.end, '2026-02-28');
});

test('addMonths зажимает число месяца', () => {
    assert.equal(toISO(addMonths(D(2026, 1, 31), 1)), '2026-02-28');
});

test('месяц вперёд через границу года', () => {
    const p = shiftPeriod(periodFor('month', D(2026, 12, 5)), 1);
    assert.equal(p.start, '2027-01-01');
    assert.equal(p.end, '2027-01-31');
});

test('год назад', () => {
    const p = shiftPeriod(periodFor('year', D(2026, 5, 5)), -1);
    assert.equal(p.start, '2025-01-01');
    assert.equal(p.end, '2025-12-31');
});

test('произвольный период сдвигается на свою длину', () => {
    const p = customPeriod(D(2026, 8, 1), D(2026, 8, 10)); // 10 дней
    const back = shiftPeriod(p, -1);
    assert.equal(back.start, '2026-07-22');
    assert.equal(back.end, '2026-07-31');
    assert.equal(daysBetweenInclusive(new Date(2026, 6, 22), new Date(2026, 6, 31)), 10);
});

test('шаг туда-обратно возвращает исходный период', () => {
    for (const g of ['day', 'week', 'month', 'year']) {
        const p = periodFor(g, D(2026, 8, 11));
        const roundTrip = shiftPeriod(shiftPeriod(p, 1), -1);
        assert.equal(roundTrip.start, p.start, `${g}: start`);
        assert.equal(roundTrip.end, p.end, `${g}: end`);
    }
});

console.log('\n--- ключ периода ---');

test('ключ = YYYY-MM-DD_YYYY-MM-DD для всех гранулярностей', () => {
    for (const g of ['day', 'week', 'month', 'year']) {
        const p = periodFor(g, D(2026, 8, 11));
        assert.match(p.key, /^\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}$/, g);
    }
});

test('ключ НЕ похож на ключ плана (YYYY-MM или venue_YYYY-MM)', () => {
    // Иначе POST /api/comments/<venue>/<key> перезаписал бы боевой план.
    for (const g of ['day', 'week', 'month', 'year']) {
        const key = periodFor(g, D(2026, 8, 11)).key;
        assert.ok(!/^\d{4}-\d{2}$/.test(key), `${g}: совпал с месячным ключом`);
        assert.notEqual(key.length, 7, `${g}: длина 7 трактуется сервером как месяц`);
    }
});

test('ключ безопасен для имени файла экспорта', () => {
    const key = periodFor('week', D(2026, 8, 11)).key;
    assert.ok(!/[\\/:*?"<>|\s]/.test(key));
});

console.log('\n--- дефолт и смена гранулярности ---');

test('дефолт = последняя ЗАВЕРШЁННАЯ неделя', () => {
    const now = D(2026, 8, 11);            // вторник
    const p = defaultPeriod(now);
    assert.equal(p.granularity, 'week');
    assert.equal(p.start, '2026-08-03');   // пн предыдущей недели
    assert.equal(p.end, '2026-08-09');     // вс предыдущей недели
    assert.ok(new Date(p.end) < now, 'дефолтный период должен быть в прошлом');
});

test('дефолт в понедельник тоже даёт прошлую неделю', () => {
    const p = defaultPeriod(D(2026, 8, 10));
    assert.equal(p.start, '2026-08-03');
    assert.equal(p.end, '2026-08-09');
});

test('смена гранулярности вне текущего периода якорится на начало', () => {
    const week = periodFor('week', D(2026, 3, 18));
    const day = changeGranularity(week, 'day', D(2026, 8, 11));
    assert.equal(day.start, '2026-03-16'); // понедельник той недели
});

test('смена гранулярности внутри текущего периода якорится на сегодня', () => {
    const now = D(2026, 8, 11);
    const week = periodFor('week', now);
    const day = changeGranularity(week, 'day', now);
    assert.equal(day.start, '2026-08-11');
});

console.log('\n--- выбор в календаре ---');

test('диапазон, совпавший с месяцем, распознаётся как месяц', () => {
    assert.equal(detectGranularity(D(2026, 8, 1), D(2026, 8, 31)), 'month');
});

test('диапазон пн-вс распознаётся как неделя', () => {
    assert.equal(detectGranularity(D(2026, 8, 10), D(2026, 8, 16)), 'week');
});

test('кривой диапазон остаётся произвольным', () => {
    assert.equal(detectGranularity(D(2026, 8, 3), D(2026, 8, 20)), null);
    const p = periodFromSelection(D(2026, 8, 3), D(2026, 8, 20), 'week');
    assert.equal(p.granularity, CUSTOM);
    assert.equal(p.start, '2026-08-03');
    assert.equal(p.end, '2026-08-20');
});

test('одна дата при активном «Месяц» = весь месяц (якорь)', () => {
    const p = periodFromSelection(D(2026, 8, 15), D(2026, 8, 15), 'month');
    assert.equal(p.granularity, 'month');
    assert.equal(p.start, '2026-08-01');
    assert.equal(p.end, '2026-08-31');
});

test('одна дата при активном «День» = этот день', () => {
    const p = periodFromSelection(D(2026, 8, 15), D(2026, 8, 15), 'day');
    assert.equal(p.granularity, 'day');
    assert.equal(p.start, '2026-08-15');
});

test('перевёрнутый диапазон нормализуется', () => {
    const p = customPeriod(D(2026, 8, 20), D(2026, 8, 3));
    assert.equal(p.start, '2026-08-03');
    assert.equal(p.end, '2026-08-20');
});

console.log('\n--- незавершённый период ---');

test('прошлый период считается завершённым, бейджа нет', () => {
    const p = periodFor('week', D(2026, 8, 3));
    assert.equal(progressBadge(p, D(2026, 8, 11)), null);
    assert.equal(periodProgress(p, D(2026, 8, 11)).isComplete, true);
});

test('текущая неделя: прошло 2 из 7 дней', () => {
    const p = periodFor('week', D(2026, 8, 11)); // 10..16 авг
    const prog = periodProgress(p, D(2026, 8, 11));
    assert.equal(prog.elapsed, 2);   // 10-е и 11-е
    assert.equal(prog.total, 7);
    assert.equal(prog.isComplete, false);
    assert.equal(progressBadge(p, D(2026, 8, 11)), 'прошло 2 из 7 дней');
});

test('будущий период помечается как ещё не начавшийся', () => {
    const p = periodFor('week', D(2026, 9, 1));
    assert.equal(progressBadge(p, D(2026, 8, 11)), 'период ещё не начался');
    assert.equal(periodProgress(p, D(2026, 8, 11)).isFuture, true);
});

test('сегодняшний день считается прошедшим целиком', () => {
    const p = periodFor('day', D(2026, 8, 11));
    assert.deepEqual(periodProgress(p, D(2026, 8, 11)), {
        elapsed: 1, total: 1, isComplete: false, isFuture: false
    });
});

console.log('\n--- подписи ---');

test('склонение слова «день»', () => {
    assert.equal(pluralDays(1), 'день');
    assert.equal(pluralDays(2), 'дня');
    assert.equal(pluralDays(5), 'дней');
    assert.equal(pluralDays(11), 'дней');   // 11 — исключение
    assert.equal(pluralDays(21), 'день');
    assert.equal(pluralDays(365), 'дней');
});

test('подпись недели содержит её номер', () => {
    const p = periodFor('week', D(2026, 8, 11));
    assert.equal(formatSubLabel(p), `неделя ${isoWeekNumber(D(2026, 8, 11))} · 7 дней`);
});

test('номер ISO-недели: 4 января всегда в первой неделе', () => {
    assert.equal(isoWeekNumber(D(2026, 1, 4)), 1);
    assert.equal(isoWeekNumber(D(2025, 1, 4)), 1);
});

test('подпись месяца — именительный падеж с годом', () => {
    assert.equal(periodFor('month', D(2026, 8, 11)).label, 'август 2026');
});

test('подпись года — просто год', () => {
    assert.equal(periodFor('year', D(2026, 8, 11)).label, '2026');
});

test('подпись недели через границу месяца показывает оба месяца', () => {
    const p = periodFor('week', D(2026, 7, 30)); // 27.07 - 02.08
    assert.equal(p.label, '27 июл - 2 авг 2026');
});

test('произвольный период подписан как произвольный', () => {
    const p = customPeriod(D(2026, 8, 3), D(2026, 8, 20));
    assert.equal(formatSubLabel(p), 'произвольный · 18 дней');
});

console.log('\n--- месяц/год для месячных вкладок ---');

test('месяц отдаётся строкой с ведущим нулём', () => {
    // plans.js собирает ключ плана как `${year}-${month}`; '2026-8' даст 404.
    const my = monthYearOf(periodFor('month', D(2026, 8, 11)));
    assert.equal(my.month, '08');
    assert.equal(typeof my.month, 'string');
    assert.equal(my.year, 2026);
    assert.equal(typeof my.year, 'number');
});

test('месяц берётся от НАЧАЛА периода', () => {
    const p = periodFor('week', D(2026, 8, 1)); // 27.07 - 02.08
    assert.equal(monthYearOf(p).month, '07');
});

console.log('\n--- вспомогательное ---');

test('daysBetweenInclusive включает обе границы', () => {
    assert.equal(daysBetweenInclusive(D(2026, 8, 1), D(2026, 8, 1)), 1);
    assert.equal(daysBetweenInclusive(D(2026, 8, 1), D(2026, 8, 31)), 31);
    assert.equal(daysBetweenInclusive(D(2026, 1, 1), D(2026, 12, 31)), 365);
});

test('startOfWeek идемпотентен', () => {
    const mon = startOfWeek(D(2026, 8, 13));
    assert.equal(toISO(startOfWeek(mon)), toISO(mon));
});

test('toISO не уезжает на день в положительной таймзоне', () => {
    assert.equal(toISO(D(2026, 1, 1)), '2026-01-01');
    assert.equal(toISO(D(2026, 12, 31)), '2026-12-31');
});

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed === 0 ? 0 : 1);

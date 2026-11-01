/**
 * Тесты клиентского ядра стандарта периодов (static/js/shared/period/period_core.js).
 *
 *     node tests/test_period_core.mjs
 *
 * Подписи, состояния и правила открытия сверяются с теми же примерами, что и сервер
 * (tests/fixtures/period_labels.json ↔ tests/test_periods.py): страница и сервер обязаны
 * писать период одинаково. Плюс арифметика шагов, смена шага, быстрый выбор и адрес.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const K = require(path.join(ROOT, 'static/js/shared/period/period_core.js'));
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests/fixtures/period_labels.json'), 'utf8'));

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

test('общие примеры: названия и короткие названия — как на сервере', () => {
    for (const c of CASES.titles) {
        const p = K.fromBounds(d(c.from), d(c.to));
        assert.equal(p.granularity, c.step, JSON.stringify(c));
        assert.equal(K.periodTitle(p), c.title, JSON.stringify(c));
        assert.equal(p.label, c.title, 'label периода = название');
        assert.equal(K.periodShort(p), c.short, JSON.stringify(c));
    }
});

test('общие примеры: состояние, cutoff и вторая строка — как на сервере', () => {
    for (const c of CASES.states) {
        const p = K.fromBounds(d(c.from), d(c.to));
        assert.equal(K.periodState(p, c.last_full_day, c.max_date), c.state, JSON.stringify(c));
        assert.equal(K.cutoffOf(p, c.last_full_day, c.max_date), c.cutoff, JSON.stringify(c));
        assert.equal(K.periodSub(p, c.last_full_day, c.max_date), c.sub, JSON.stringify(c));
    }
});

test('общие примеры: последний закрытый и последние N дней', () => {
    for (const c of CASES.last_closed) {
        const p = K.lastClosed(c.step, c.last_full_day);
        assert.deepEqual([p.start, p.end], [c.from, c.to], JSON.stringify(c));
    }
    for (const c of CASES.last_days) {
        const p = K.lastDays(c.n, c.last_full_day);
        assert.deepEqual([p.start, p.end], [c.from, c.to], JSON.stringify(c));
        assert.equal(K.daysBetweenInclusive(d(p.start), d(p.end)), c.n, 'ровно N дат');
    }
});

test('часы страницы — с сервера, а не с устройства', () => {
    K.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });
    assert.equal(K.toISO(K.today()), '2026-11-01');
    assert.deepEqual([K.lastClosed('week').start, K.lastClosed('week').end], ['2026-10-19', '2026-10-25'],
        'воскресенье 1 ноября ещё идёт — последняя закрытая неделя 19–25 октября');
    assert.equal(K.currentPeriod('month').start, '2026-11-01');
    assert.equal(K.periodState(K.currentPeriod('week')), 'partial');
    assert.equal(K.QUICK.yesterday.build().start, '2026-10-31');
    assert.equal(K.QUICK.last30.build().start, '2026-10-02');
    K.configure({});
});

test('шаг стрелки — через границы месяца и года; свой период — на свою длину', () => {
    assert.equal(K.shiftPeriod(K.periodFor('month', d('2026-01-31')), 1).start, '2026-02-01');
    assert.equal(K.shiftPeriod(K.periodFor('month', d('2026-12-14')), 1).start, '2027-01-01');
    assert.equal(K.shiftPeriod(K.periodFor('week', d('2026-12-30')), 1).start, '2027-01-04');
    const custom = K.fromBounds(d('2026-10-12'), d('2026-10-25'));
    const back = K.shiftPeriod(custom, -1);
    assert.deepEqual([back.start, back.end], ['2026-09-28', '2026-10-11']);
});

test('смена шага — период нового шага, где лежит конец текущего', () => {
    K.configure({ today: '2026-10-30', last_full_day: '2026-10-29', max_date: '2026-10-29' });
    const october = K.periodFor('month', d('2026-10-15'));
    assert.equal(K.changeGranularity(october, 'week').start, '2026-10-26',
        'из октября «по 29.10» — неделя 26 окт – 1 ноя, а не неделя 1-го числа');
    const week = K.periodFor('week', d('2026-10-20'));
    assert.equal(K.changeGranularity(week, 'month').start, '2026-10-01');
    assert.equal(K.changeGranularity(K.periodFor('month', d('2026-09-10')), 'day').start, '2026-09-30');
    K.configure({});
});

test('выбор в календаре: натуральные границы — шаг, иначе свой период', () => {
    assert.equal(K.periodFromSelection(d('2026-08-01'), d('2026-08-31')).granularity, 'month');
    assert.equal(K.periodFromSelection(d('2026-08-03'), d('2026-08-12')).granularity, 'custom');
    assert.equal(K.periodFromSelection(d('2026-08-15'), d('2026-08-15'), 'month').start, '2026-08-01',
        'один день при шаге «месяц» — якорь месяца');
});

test('адрес страницы: date_from и date_to включительно, неверный — null', () => {
    const p = K.readUrlPeriod('?date_from=2026-10-01&date_to=2026-10-31&bar=ligovskiy');
    assert.deepEqual([p.granularity, p.start, p.end], ['month', '2026-10-01', '2026-10-31']);
    assert.equal(K.readUrlPeriod('?date_from=2026-10-01'), null);
    assert.equal(K.readUrlPeriod('?date_from=2026-02-30&date_to=2026-03-01'), null, '30 февраля нет');
    assert.equal(K.readUrlPeriod('?date_to=2026-10-01&date_from=2026-10-31'), null,
        'перевёрнутые даты — неверная ссылка, как 400 на сервере');
});

test('кварталов нет: 1 июля – 30 сентября — свой период', () => {
    assert.ok(!K.GRANULARITIES.includes('quarter'));
    assert.equal(K.fromBounds(d('2026-07-01'), d('2026-09-30')).granularity, 'custom');
    for (const id of Object.keys(K.QUICK)) assert.ok(!/quarter/.test(id), id);
});

test('месяц выбранного периода — как на сервере (общие примеры)', () => {
    for (const c of CASES.month_of) {
        const p = K.fromBounds(d(c.from), d(c.to));
        assert.equal(K.monthOf(p).start, c.month, JSON.stringify(c));
    }
});

test('свой период цифрами: маска, разбор, вставка диапазона', () => {
    assert.equal(K.maskTyped('01032024'), '01.03.2024');
    assert.equal(K.maskTyped('0103'), '01.03');
    assert.equal(K.maskTyped('01a03b2024999'), '01.03.2024', 'только цифры, не длиннее даты');
    assert.equal(K.maskTyped('2024-03-01'), '2024-03-01', 'готовую дату не трогает');
    // Набор по одной цифре — как в поле: каждая следующая буква к уже замаскированному тексту.
    let typed = '';
    for (const ch of '01032024') typed = K.maskTyped(typed + ch);
    assert.equal(typed, '01.03.2024', 'точки ставятся по мере набора');
    assert.equal(K.maskTyped('1.3.2024'), '1.3.2024', 'точки, набранные вручную, не трогает');
    assert.equal(K.maskTyped('01.03.'), '01.03.', 'стирание назад не возвращает цифры');
    assert.equal(K.maskTyped('01.03.20245'), '01.03.2024');
    for (const raw of ['01.03.2024', '1.3.2024', '01.03.24', '01/03/2024', '2024-03-01', '01032024']) {
        assert.equal(K.toISO(K.parseTyped(raw)), '2024-03-01', raw);
    }
    assert.equal(K.parseTyped('31.02.2026'), null, '31 февраля нет');
    assert.equal(K.parseTyped('12.2026'), null);
    assert.deepEqual(K.parseTypedRange('01.03.2024 – 31.10.2026').map(K.toISO), ['2024-03-01', '2026-10-31']);
    assert.deepEqual(K.parseTypedRange('с 1.3.24 по 31.10.26').map(K.toISO), ['2024-03-01', '2026-10-31']);
    assert.equal(K.parseTypedRange('01.03.2024'), null, 'одна дата — не диапазон');
    assert.equal(K.formatTyped(d('2024-03-01')), '01.03.2024');
});

test('свой период цифрами: ошибки текстом, длина не ограничена', () => {
    K.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01',
                  data_start: '2017-12-18' });
    assert.equal(K.validateRange('01.03.2024', '31.10.2026'), null, 'больше года — можно');
    assert.equal(K.validateRange('31.02.2026', '01.03.2026'), 'Такой даты нет: 31.02.2026');
    assert.equal(K.validateRange('', '01.03.2026'), 'Введите первую дату');
    assert.equal(K.validateRange('31.10.2026', '01.03.2024'), 'Первая дата позже второй');
    assert.equal(K.validateRange('01.01.2010', '01.03.2024'), 'Раньше начала данных: данные с 18.12.2017');
    assert.equal(K.validateRange('01.10.2026', '05.11.2026'), 'Позже последнего дня с данными: 01.11.2026');
    assert.equal(K.validateRange('01.10.2026', '05.11.2026', { allowFuture: true }), null, 'планирование');
    assert.equal(K.validateRange('01.01.2025', '31.10.2026', { maxDays: 366, maxReason: 'дольше iiko не отвечает' }),
        'Здесь — не больше 366 дней: дольше iiko не отвечает');
    K.configure({});
});

test('быстрый выбор сайта: 12 целых месяцев, всё время, без кварталов', () => {
    K.configure({ today: '2026-11-15', last_full_day: '2026-11-14', max_date: '2026-11-15',
                  data_start: '2017-12-18' });
    assert.equal(K.QUICK.last12m.build().key, '2025-11-01_2026-10-31', 'по последний закрытый месяц');
    assert.equal(K.QUICK.all.build().key, '2017-12-18_2026-11-15');
    assert.deepEqual(K.SITE_QUICK, ['today', 'yesterday', 'current_week', 'last_closed_week', 'current_month',
        'last_closed_month', 'last30', 'last90', 'last12m', 'ytd', 'last_closed_year', 'all']);
    for (const id of K.SITE_QUICK) assert.ok(K.QUICK[id], id);
    K.configure({ today: '2026-11-15', last_full_day: '2026-11-14', max_date: '2026-11-15' });
    assert.equal(K.QUICK.all.build(), null, 'без первого дня данных «Всё время» недоступно');
    K.configure({});
});

test('быстрый выбор — подсветка совпадающего пункта', () => {
    K.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });
    assert.equal(K.matchQuick(K.lastClosed('week'), ['current_week', 'last_closed_week']), 'last_closed_week');
    assert.equal(K.matchQuick(K.periodFor('week', d('2026-09-01')), ['last_closed_week']), null);
    K.configure({});
});

test('ключ периода — как у /api/weeks; год в каждом названии', () => {
    assert.equal(K.periodFor('week', d('2026-10-28')).key, '2026-10-26_2026-11-01');
    for (const g of K.GRANULARITIES) {
        assert.match(K.periodTitle(K.periodFor(g, d('2026-10-28'))), /2026/, g + ' без года');
    }
});

console.log(`\n${passed} ok, ${failed} failed`);
if (failed) process.exit(1);

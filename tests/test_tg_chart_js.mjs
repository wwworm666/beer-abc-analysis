/**
 * Расчёты и форматирование мини-приложения «Графики» (static/tg_chart/charts.js) без браузера:
 *
 *     node tests/test_tg_chart_js.mjs <fixtures.json>
 *
 * fixtures.json — описания графиков после kultura_bot/charts/spec.normalize (его пишет
 * tests/test_tg_chart_js.py, он же запускает этот файл под pytest). Проверяется:
 *   1. числа и даты по-русски: пробел-разделитель тысяч, запятая, минус «−», склонение
 *      единиц, проценты с одним знаком, «тыс. ₽», диапазоны дат и «данные на … МСК»;
 *   2. расчёты из «Как считается»: изменение в %, итоги без пропусков, порядок «По
 *      изменению», фильтр рейтинга и итоги групп, итоги в окне зума;
 *   3. опция ECharts строится для каждой фикстуры во всех режимах: проценты, PNG без
 *      подсказок и зума, зум у длинного ряда по дням, цвета по ролям серий;
 *   4. таблица и тексты «Как считается» есть у каждого вида.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const T = require(path.join(here, '..', 'static', 'tg_chart', 'charts.js'));
const fixtures = Object.fromEntries(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).map(f => [f.name, f.chart]));

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
}

const NB = ' ';
const { fmt, calc } = T;

check('числа', () => {
  assert.equal(fmt.num(1234.5, 1), '1' + NB + '234,5');
  assert.equal(fmt.num(-5, 0), '−5');
  assert.equal(fmt.num(-0.04, 1), '0,0', 'минус ноль не пишется');
  assert.equal(fmt.num(null, 0), '—');
  assert.equal(fmt.signed(12, 0), '+12');
  assert.equal(fmt.signed(-16.4, 1), '−16,4');
  assert.equal(fmt.signed(0.04, 1), '0,0');
  assert.equal(fmt.pctText(5.4999, true), '▲ +5,5%');
  assert.equal(fmt.pctText(-16.4, true), '▼ −16,4%');
  assert.equal(fmt.pctText(null), '—');
});

check('склонение и единицы', () => {
  const forms = ['порция', 'порции', 'порций'];
  assert.deepEqual([1, 2, 5, 11, 12, 21, 22, 25, 111, 2.5].map(n => fmt.plural(n, forms)),
    ['порция', 'порции', 'порций', 'порций', 'порций', 'порция', 'порции', 'порций', 'порций', 'порции']);
  const desserts = fixtures.desserts;
  assert.equal(fmt.exact(desserts, 2), '2 порции');
  assert.equal(fmt.exact(desserts, 73), '73 порции');
  assert.equal(fmt.shortUnit(desserts, 54), '54 порции', 'без деления — со склонением');
  const belgium = fixtures.belgium;
  assert.equal(fmt.scaledUnit(belgium), 'тыс. ₽');
  assert.equal(fmt.short(belgium, 534000), '534');
  assert.equal(fmt.short(belgium, 4500), '4,5', 'меньше 10 тысяч — один знак');
  assert.equal(fmt.short(belgium, 4000), '4');
  assert.equal(fmt.exact(belgium, 136000), '136' + NB + '000 ₽', 'точное значение — в рублях');
  assert.equal(fmt.exactSigned(belgium, -17000), '−17' + NB + '000 ₽');
  assert.equal(fmt.short(fixtures.liters, 252.9), '252,9');
  assert.equal(fmt.valueLabel(belgium), 'Рубли');
  assert.equal(fmt.valueLabel(fixtures.liters), 'Литры');
  assert.equal(fmt.valueLabel(desserts), 'Порции');
});

check('даты', () => {
  assert.equal(fmt.dayShort('2026-09-01'), '1 сен');
  assert.equal(fmt.dayLong('2026-09-18'), 'пт, 18 сен 2026');
  assert.equal(fmt.dayRange('2026-07-01', '2026-09-30'), '1 июл – 30 сен 2026');
  assert.equal(fmt.dayRange('2025-12-29', '2026-01-04'), '29 дек 2025 – 4 янв 2026');
  assert.equal(fmt.dayRange('2026-05-09', '2026-05-09'), '9 мая 2026');
  assert.equal(fmt.dataAt('2026-09-14T00:58:00+03:00'), '14 сен 2026, 00:58 МСК');
});

check('изменение и итоги', () => {
  assert.ok(Math.abs(calc.pct(534000, 506161) - 5.49999) < 0.001);
  assert.equal(calc.pct(1, 0), null, 'база 0 — процент не считается');
  assert.equal(calc.pct(null, 5), null);
  assert.equal(calc.pct(-5, -10), 50, 'знаменатель — модуль базы');
  assert.equal(calc.sum([null, 1, 2]), 3);
  assert.equal(calc.sum([null, null]), null);
});

check('два периода: порядок «По изменению»', () => {
  const b = fixtures.belgium;
  const label = rows => rows.map(r => r.c.label);
  assert.deepEqual(label(calc.periodRows(b, { order: 'report' })).slice(0, 2), ['Квак', 'Стинбрюгге Бланш']);
  assert.deepEqual(label(calc.periodRows(b, { order: 'delta', values: 'abs' })),
    ['Квак', 'Барбе Руби', 'Стинбрюгге Бланш', 'Роденбах', 'Стинбрюгге Блонд', 'Палм', 'Гулден Драк']);
  assert.deepEqual(label(calc.periodRows(b, { order: 'delta', values: 'pct' })),
    ['Барбе Руби', 'Стинбрюгге Бланш', 'Роденбах', 'Палм', 'Стинбрюгге Блонд', 'Гулден Драк', 'Квак'],
    'без базы — в конце');
});

check('рейтинг: фильтр по группе и итоги', () => {
  const l = fixtures.liters;
  const st = T.initialState(l);
  assert.equal(calc.ratingRows(l, st).length, 15);
  st.group = 'g0';
  assert.deepEqual(calc.ratingRows(l, st).map(r => r.c.label), ['Heartless Bitch 2.0', "It's Mango", 'Bananed', 'Blueberry Jam']);
  assert.equal(Math.round(calc.groupTotal(l, l.groups[0]) * 10) / 10, 329.8);
  assert.equal(Math.round(calc.groupTotal(l, l.groups[1]) * 10) / 10, 63.6);
  assert.equal(Math.round(calc.groupTotal(l, null) * 10) / 10, 406.7);
  assert.deepEqual(calc.ungrouped(l).map(r => r.c.label), ['Прочие (8)']);
});

check('стек: итог строки из видимых частей', () => {
  const d = fixtures.desserts;
  const st = T.initialState(d);
  assert.equal(calc.rowTotal(d, st, 2), 27);
  st.show.s2 = false;                                 // выключили Варшавскую
  assert.equal(calc.rowTotal(d, st, 2), 4);
});

check('ряд по дням: итоги в окне зума', () => {
  const days = fixtures.days;
  const st = T.initialState(days);
  const all = calc.windowTotals(days, st);
  assert.equal(all.s0, days.series[0].data.reduce((a, b) => a + b, 0));
  st.zoom = { start: 85, end: 91 };
  assert.equal(calc.windowTotals(days, st).s1, days.series[1].data.slice(85, 92).reduce((a, b) => a + b, 0));
});

const P = new Proxy({}, { get: (_, key) => (typeof key === 'string' ? '#' + key.length.toString(16).padStart(6, '0') : undefined) });

check('опция ECharts для каждой фикстуры и режима', () => {
  for (const [name, spec] of Object.entries(fixtures)) {
    for (const mode of ['app', 'png']) {
      const st = T.initialState(spec);
      const opt = T.buildOption(spec, st, P, 380, mode);
      assert.ok(Array.isArray(opt.series) && opt.series.length > 0, name);
      assert.equal(opt.animation, mode !== 'png', name + ': PNG без анимации');
      if (mode === 'png') assert.deepEqual(opt.tooltip, { show: false }, name + ': в PNG подсказок нет');
      if (spec.kind === 'days') assert.equal(Boolean(opt.dataZoom), mode === 'app', name + ': зум только в приложении');
    }
  }
  const b = fixtures.belgium;
  const st = T.initialState(b);
  st.values = 'pct';
  const pctOpt = T.buildOption(b, st, P, 380, 'app');
  assert.deepEqual(pctOpt.series.map(s => s.id), ['p-pct']);
  const kvak = pctOpt.series[0].data[0];              // «Квак»: в базе 0, процента нет
  assert.equal(kvak.value, 0);
  assert.equal(kvak.label.formatter, '—', 'без базы — прочерк вместо столбика');
  assert.equal(pctOpt.series[0].data[3].value.toFixed(1), '95.8', 'Барбе Руби: (47 − 24) / 24 × 100');
  st.values = 'abs';
  st.show.s1 = false;
  assert.deepEqual(T.buildOption(b, st, P, 380, 'app').series.map(s => s.id), ['p-cur'], 'база выключена в легенде');
  const rating = T.buildOption(fixtures.liters, Object.assign(T.initialState(fixtures.liters), { group: 'g1' }), P, 380, 'app');
  assert.equal(rating.yAxis.data.length, 10, 'фасовка: 9 бутылок и банка');
});

check('цвета по ролям', () => {
  assert.deepEqual(T.colorKeys(fixtures.belgium), { s0: 'accent', s1: 'base' });
  assert.deepEqual(T.colorKeys(fixtures.days), { s0: 'accent', s1: 'greige' }, 'база по дням — линия, серая заметнее');
  assert.deepEqual(T.colorKeys(fixtures.desserts), { s0: 'ligovskiy', s1: 'kremenchugskaya', s2: 'varshavskaya' });
  assert.deepEqual(T.colorKeys(fixtures.check), { s0: 'part_light', s1: 'part_dark' });
  assert.deepEqual(T.colorKeys(fixtures.liters), { s0: 'greige' });
  const parts = Object.assign({}, fixtures.desserts, { series: fixtures.desserts.series.map(s => ({ key: s.key, name: s.name, role: s.role, data: s.data })) });
  const keys = Object.values(T.colorKeys(parts));
  assert.equal(new Set(keys).size, 3, 'три части без цветов — три разных цвета');
});

check('таблица и «Как считается»', () => {
  const b = T.table(fixtures.belgium);
  assert.deepEqual(b.head, ['Категория', '19–30 авг', '2–13 сен (ивент)', 'Разница', 'Изм., %']);
  assert.deepEqual(b.foot, ['Всего', '207' + NB + '000', '327' + NB + '000', '+120' + NB + '000', '+58,0%']);
  assert.equal(T.table(fixtures.check).foot, null, 'средний чек не складывается');
  assert.deepEqual(T.table(fixtures.desserts).foot, ['Всего', '5', '14', '54', '73']);
  assert.equal(T.table(fixtures.liters).rows[0][3], '62,2%');
  for (const spec of Object.values(fixtures)) assert.ok(T.howText(spec).length >= 2, spec.kind);
  assert.ok(T.howText(fixtures.belgium).some(t => t.includes('(текущий − база) / база × 100')));
});

console.log('test_tg_chart_js: ' + passed + ' проверок прошли');

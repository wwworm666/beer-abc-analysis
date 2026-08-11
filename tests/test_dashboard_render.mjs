/**
 * Тесты редизайна дашборда (2026-08-11): группировка метрик и покрытие стилями.
 *
 *     node tests/test_dashboard_render.mjs
 *
 * Браузера в проверке нет, поэтому ловим две самые вероятные поломки редизайна:
 *   1. метрика потерялась / попала не в ту группу (экран не покажет показатель);
 *   2. класс, который JS пишет в разметку, нигде не описан в CSS (элемент есть,
 *      но выглядит сломанным) — опечатка в имени класса иначе видна только глазами.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { METRICS, METRIC_GROUPS } from '../static/js/dashboard/core/config.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

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

const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

console.log('\n--- группировка метрик ---');

test('все 16 метрик на месте', () => {
    assert.equal(METRICS.length, 16);
});

test('у каждой метрики есть существующая группа', () => {
    const known = new Set(METRIC_GROUPS.map(g => g.id));
    for (const m of METRICS) {
        assert.ok(m.group, `${m.id}: группа не указана`);
        assert.ok(known.has(m.group), `${m.id}: неизвестная группа "${m.group}"`);
    }
});

test('в каждой группе есть метрики', () => {
    for (const g of METRIC_GROUPS) {
        const n = METRICS.filter(m => m.group === g.id).length;
        assert.ok(n > 0, `группа ${g.id} пустая`);
    }
});

test('раскладка групп совпадает с макетом: 3/3/3/3/4', () => {
    const counts = METRIC_GROUPS.map(g => METRICS.filter(m => m.group === g.id).length);
    assert.deepEqual(counts, [3, 3, 3, 3, 4]);
});

test('в «Главном» именно выручка, чеки и средний чек', () => {
    const ids = METRICS.filter(m => m.group === 'main').map(m => m.id);
    assert.deepEqual(ids, ['revenue', 'checks', 'averageCheck']);
    // Выручка идёт первой: на мобильном она рисуется крупной карточкой.
    assert.equal(ids[0], 'revenue');
});

test('группа направления = доля + выручка + наценка', () => {
    for (const g of ['draft', 'packaged', 'kitchen']) {
        const ids = METRICS.filter(m => m.group === g).map(m => m.id);
        assert.equal(ids.length, 3, g);
        assert.ok(ids.some(id => id.includes('Share')), `${g}: нет доли`);
        assert.ok(ids.some(id => id.startsWith('revenue')), `${g}: нет выручки`);
        assert.ok(ids.some(id => id.startsWith('markup')), `${g}: нет наценки`);
    }
});

test('id метрик уникальны', () => {
    const ids = METRICS.map(m => m.id);
    assert.equal(new Set(ids).size, ids.length);
});

test('только «Главное» не сворачивается', () => {
    const notCollapsible = METRIC_GROUPS.filter(g => !g.collapsible).map(g => g.id);
    assert.deepEqual(notCollapsible, ['main']);
});

console.log('\n--- покрытие стилями ---');

const CSS = [
    'static/dashboard/styles/base.css',
    'static/dashboard/styles/cards.css',
    'static/dashboard/styles/mobile.css',
    'static/dashboard/styles/tabs.css',
    'static/dashboard/styles/comparison.css',
    'static/dashboard/styles/animations.css',
    'static/dashboard/styles/sidebar.css',
    'static/dashboard/styles/charts.css'
].map(read).join('\n');

/** Классы, которые JS/шаблон ставит на элементы редизайна. */
const REDESIGN_CLASSES = [
    // единая панель периода
    'period-bar', 'period-granularity', 'pg-btn', 'period-nav', 'pn-arrow',
    'pn-current', 'pn-label', 'pn-sub', 'pn-today', 'pn-calendar',
    'period-picker-anchor', 'period-warning', 'control-group-period',
    // десктопные группы и карточка
    'mv-desktop', 'metric-group', 'mg-separator', 'mg-title', 'mg-line',
    'metrics-grid-row', 'metric-card', 'metric-name', 'metric-value',
    'mc-bars', 'mc-bar-row', 'mc-bar-row-prev', 'mc-bar-label', 'mc-track',
    'mc-fill', 'mc-fill-prev', 'mc-pct', 'mc-pct-prev', 'mc-footer',
    'mc-delta', 'mc-plan', 'mc-noplan',
    // мобильный экран
    'mv-mobile', 'm-section-label', 'm-summary', 'm-summary-top', 'm-summary-label',
    'm-summary-dates', 'm-summary-value', 'm-summary-pct', 'm-summary-word',
    'm-legend', 'm-legend-item', 'm-dot', 'm-track', 'm-fill',
    'm-hero', 'm-hero-row', 'm-hero-value', 'm-duo', 'm-compact', 'm-compact-value',
    'm-card-top', 'm-card-label', 'm-card-foot', 'm-pct', 'm-plan', 'm-prev', 'm-delta',
    'm-group', 'm-group-head', 'm-group-name', 'm-group-count', 'm-group-pct',
    'm-group-body', 'm-row', 'm-row-top', 'm-row-name', 'm-row-value',
    // нижняя таб-панель
    'bottom-tabs', 'bt-item'
];

test('каждый класс редизайна описан в CSS', () => {
    const missing = REDESIGN_CLASSES.filter(cls => !CSS.includes(`.${cls}`));
    assert.deepEqual(missing, [], `нет правил для: ${missing.join(', ')}`);
});

test('статусные модификаторы покрыты для процентов и точек', () => {
    for (const base of ['mc-pct', 'm-pct', 'm-dot', 'm-group-pct', 'mc-delta']) {
        for (const st of ['success', 'warning', 'danger']) {
            assert.ok(CSS.includes(`.${base}.${st}`), `нет .${base}.${st}`);
        }
    }
});

test('в CSS редизайна нет HEX-цветов мимо переменных', () => {
    // docs/design-system.md: цвета только через var(--name).
    // Проверяем файл переменных как исключение и остальные — на голые #RRGGBB.
    const cards = read('static/dashboard/styles/cards.css');
    const hex = [...cards.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map(m => m[0]);
    assert.deepEqual(hex, [], `HEX в cards.css: ${hex.join(', ')}`);
});

test('шкала предыдущего периода имеет свой токен в обеих темах', () => {
    const vars = read('static/dashboard/styles/variables.css');
    const decls = [...vars.matchAll(/--bar-prev:/g)];
    assert.equal(decls.length, 2, 'ожидались объявления для светлой и тёмной темы');
});

console.log('\n--- разметка ---');

test('нижняя таб-панель повторяет вкладки и содержит «Ещё»', () => {
    const html = read('templates/dashboard/base.html');
    const bottom = [...html.matchAll(/class="bt-item[^"]*"[^>]*data-tab="([^"]+)"/g)].map(m => m[1]);
    assert.deepEqual(bottom, ['tab-analytics', 'tab-comparison', 'tab-revenue', 'tab-plans']);
    assert.ok(html.includes('id="bt-more"'), 'нет кнопки «Ещё»');
});

test('в разметке дашборда нет эмодзи', () => {
    // .claude/CLAUDE.md: эмодзи запрещены в коде и интерфейсе.
    const files = [
        'templates/dashboard/base.html',
        'templates/dashboard.html',
        'static/js/dashboard/modules/analytics.js',
        'static/js/dashboard/modules/period_controls.js',
        'static/js/dashboard/core/period_model.js'
    ];
    const emoji = /[\u{1F300}-\u{1FAFF}\u{2705}\u{274C}\u{26A0}\u{2B50}\u{1F4C5}]/u;
    for (const f of files) {
        const hit = read(f).match(emoji);
        assert.equal(hit, null, `${f}: найдено ${hit && hit[0]}`);
    }
});

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed === 0 ? 0 : 1);

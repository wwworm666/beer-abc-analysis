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

import { METRICS, METRIC_GROUPS, HEADLINE_METRIC_IDS } from '../static/js/dashboard/core/config.js';

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

test('ровно 4 группы по 4 метрики — 4-колоночная сетка заполняется целиком', () => {
    assert.equal(METRIC_GROUPS.length, 4);
    const counts = METRIC_GROUPS.map(g => METRICS.filter(m => m.group === g.id).length);
    assert.deepEqual(counts, [4, 4, 4, 4]);
});

test('итог группы идёт первым', () => {
    // «Выручка» открывает группу выручки, «% наценки» — группу наценки:
    // сначала общий показатель, потом разбивка по направлениям.
    const first = (id) => METRICS.filter(m => m.group === id)[0].id;
    assert.equal(first('revenue'), 'revenue');
    assert.equal(first('markup'), 'markupPercent');
});

test('группа выручки и наценки покрывают все три направления', () => {
    for (const g of ['revenue', 'markup']) {
        const ids = METRICS.filter(m => m.group === g).map(m => m.id).join(' ');
        for (const dir of ['Draft', 'Packaged', 'Kitchen']) {
            assert.ok(ids.includes(dir), `${g}: нет ${dir}`);
        }
    }
});

test('«Главное» — выручка, чеки, средний чек и все они существуют', () => {
    assert.deepEqual(HEADLINE_METRIC_IDS, ['revenue', 'checks', 'averageCheck']);
    for (const id of HEADLINE_METRIC_IDS) {
        assert.ok(METRICS.some(m => m.id === id), `нет метрики ${id}`);
    }
});

test('id метрик уникальны', () => {
    const ids = METRICS.map(m => m.id);
    assert.equal(new Set(ids).size, ids.length);
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
    // шапка фильтров: одна полоса «заведение | период | экспорт»
    'filter-bar', 'fb-native-select', 'fb-item', 'fb-venue', 'fb-strong', 'fb-hint',
    'fb-icon', 'fb-caret', 'fb-divider', 'fb-spacer',
    'fb-period', 'fb-arrow', 'fb-period-trigger',
    'fb-export', 'fb-ghost', 'fb-export-mobile', 'period-picker-anchor',
    // выпадающие списки / нижний лист
    'fb-backdrop', 'fb-menu', 'fb-grab', 'fb-menu-label', 'fb-menu-item',
    'fb-menu-name', 'fb-menu-hint', 'fb-menu-icon', 'fb-menu-sep', 'fb-menu-muted',
    // десктопные группы и карточка
    'mv-desktop', 'metric-group', 'mg-separator', 'mg-title', 'mg-line',
    'metrics-grid-row', 'metric-card', 'metric-name', 'metric-value',
    'mc-head', 'mc-caret',
    // легенда шкал — одна на страницу, в строке вкладок
    'tabs-legend', 'tl-item', 'tl-swatch', 'tl-swatch-prev', 'tabs-divider',
    'tabs-spacer', 'completion-label', 'completion-value',
    'mc-bars', 'mc-bar-row', 'mc-bar-row-prev', 'mc-track',
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
    for (const base of ['mc-pct', 'm-pct', 'm-dot', 'm-group-pct']) {
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

test('шапка фильтров: один контрол, без сегментов и «Сегодня»', () => {
    const html = read('templates/dashboard/base.html');
    // Обязательные части полосы (макет 5a)
    for (const id of ['filter-bar', 'venue-trigger', 'venue-selector', 'period-prev',
                      'period-trigger', 'period-title', 'period-hint', 'period-next',
                      'period-menu', 'venue-menu', 'export-menu', 'fb-backdrop',
                      'period-preset-list', 'period-custom', 'flexi-range-picker']) {
        assert.ok(html.includes(`id="${id}"`), `нет элемента #${id}`);
    }
    // Убранное макетом не должно вернуться
    for (const gone of ['data-granularity', 'period-today', 'period-sublabel',
                        'dashboard-controls', 'control-group-period']) {
        assert.ok(!html.includes(gone), `в разметке осталось «${gone}»`);
    }
});

test('легенда шкал стоит один раз — в строке вкладок', () => {
    const html = read('templates/dashboard/base.html');
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(html.includes('id="tabs-legend"'), 'нет легенды в строке вкладок');
    // Заголовок группы — только название и линия (макет 7a).
    assert.ok(!js.includes('mg-legend'), 'легенда осталась в заголовке группы');
    assert.ok(js.includes('tabs-legend'), 'JS не показывает легенду в строке вкладок');
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

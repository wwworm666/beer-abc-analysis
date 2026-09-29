/**
 * Тесты куба OLAP на странице «Конструктор отчётов» (static/js/explorer/cube.js):
 *
 *     node tests/test_explorer_cube.mjs
 *
 * Браузера в проверке нет, поэтому ловим то, что иначе видно только глазами:
 *   1. правила куба: слои осей, поворот (pivot) только при переезде поля между строками и
 *      столбцами, подпись с экранированием и числом фильтров;
 *   2. класс, который пишет cube.js, не описан в CSS — куб есть, но выглядит сломанным;
 *   3. длительности в JS и CSS разошлись — поворот обрывается или строки мигают;
 *   4. цвета куба не заданы для тёмной темы, нет правила «уменьшить движение»;
 *   5. страница не подключает куб или пишет в карточку мимо setMsg (стирает куб).
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
        console.log(`      ${e.message}`);
    }
}

const cubeJs = read('static/js/explorer/cube.js');
const pageJs = read('static/js/explorer/page.js');
const css = read('static/explorer/explorer.css');
const html = read('templates/explorer.html');

const sandbox = { window: {} };
vm.runInNewContext(cubeJs, sandbox);
const Cube = sandbox.window.ExplorerCube;

test('модуль публикует window.ExplorerCube', () => {
    assert.ok(Cube, 'нет window.ExplorerCube');
    for (const name of ['create', 'segments', 'pivoted', 'legendHtml', 'motionAllowed', 'unfold']) {
        assert.equal(typeof Cube[name], 'function', name);
    }
});

test('слои оси: нет полей — 1, одно — 3, два и больше — 4; глубина — 3', () => {
    assert.deepEqual([0, 1, 2, 3, 8].map(Cube.segments), [1, 3, 4, 4, 4]);
    assert.equal(Cube.DEPTH, 3);
});

test('pivot — только когда поле переехало между строками и столбцами', () => {
    const base = { rows: ['Store.Name', 'DishName'], columns: ['OpenDate.Typed'] };
    assert.equal(Cube.pivoted(null, base), false, 'первый рендер — без поворота');
    assert.equal(Cube.pivoted(base, { rows: ['DishName'], columns: ['OpenDate.Typed', 'Store.Name'] }), true);
    assert.equal(Cube.pivoted(base, { rows: ['Store.Name', 'DishName', 'OpenDate.Typed'], columns: [] }), true);
    assert.equal(Cube.pivoted(base, { rows: ['DishName', 'Store.Name'], columns: ['OpenDate.Typed'] }), false,
        'перестановка внутри строк — не pivot');
    assert.equal(Cube.pivoted(base, { rows: ['Store.Name', 'DishName'], columns: ['OpenDate.Typed', 'AuthUser'] }), false,
        'новое поле — не pivot');
    assert.equal(Cube.pivoted(base, { rows: ['Store.Name'], columns: ['OpenDate.Typed'] }), false,
        'поле убрали — не pivot');
});

test('подпись: экранирование, «не выбраны», вложенность строк, число фильтров', () => {
    const out = Cube.legendHtml({
        rows: ['Группа <b>', 'Блюдо'], columns: [], measures: ['Сумма со скидкой', 'Чеков'],
        filters: 2, period: 'Прошлая неделя'
    });
    assert.ok(out.includes('Группа &lt;b&gt; › Блюдо'), 'строки через «›» и с экранированием');
    assert.ok(!out.includes('<b>'), 'имя поля попало в разметку без экранирования');
    assert.match(out, /class="ex-cube-li is-empty" data-axis="columns"[\s\S]*?не выбраны/);
    assert.ok(out.includes('Сумма со скидкой, Чеков'));
    assert.ok(out.includes('срез: 2 фильтра'));
    const one = Cube.legendHtml({ rows: [], columns: [], measures: [], filters: 1, period: 'Вчера' });
    assert.ok(one.includes('срез: 1 фильтр'));
    const five = Cube.legendHtml({ rows: [], columns: [], measures: [], filters: 5, period: 'Вчера' });
    assert.ok(five.includes('срез: 5 фильтров'));
    const none = Cube.legendHtml({ rows: [], columns: [], measures: [], filters: 0, period: 'Вчера' });
    assert.ok(!none.includes('срез'), 'без фильтров — без «срез»');
});

test('каждый класс ex-cube-* и ex-unfold* из cube.js описан в CSS', () => {
    const classes = new Set();
    for (const m of cubeJs.matchAll(/ex-(?:cube|unfold)[a-z-]*/g)) {
        if (!m[0].endsWith('-')) classes.add(m[0]);   // «--ex-cube-*» в комментарии — шаблон, не класс
    }
    for (const cls of ['ex-cube-delay', 'ex-cube-nx', 'ex-cube-ny', 'ex-cube-nz', 'ex-unfold-i']) {
        classes.delete(cls);   // это CSS-переменные (--ex-...), а не классы
    }
    const missing = [...classes].filter((cls) => !new RegExp('\\.' + cls + '(?![a-z-])').test(css));
    assert.deepEqual(missing, [], 'нет в explorer.css: ' + missing.join(', '));
    for (const flag of ['is-hollow', 'has-slice', 'no-rows', 'no-cols', 'is-pivot', 'no-anim', 'is-new', 'is-empty']) {
        assert.ok(cubeJs.includes(flag) && css.includes('.' + flag), 'флаг ' + flag);
    }
});

test('длительности JS и CSS совпадают: поворот и раскладка строк', () => {
    const js = (name) => Number(cubeJs.match(new RegExp('var ' + name + ' = (\\d+);'))[1]);
    const pivotCss = css.match(/\.ex-cube-body \{ transition: transform (\d+)ms/);
    assert.ok(pivotCss, 'нет transition у .ex-cube-body');
    assert.equal(Number(pivotCss[1]), js('PIVOT_MS'));
    const rowCss = css.match(/\.ex-unfold-row \{[^}]*animation: exRowIn (\d+)ms/);
    assert.ok(rowCss, 'нет анимации у .ex-unfold-row');
    assert.equal(Number(rowCss[1]), js('UNFOLD_ROW_MS'));
    const stepCss = css.match(/--ex-unfold-i, 0\) \* (\d+)ms/);
    assert.equal(Number(stepCss[1]), js('UNFOLD_STEP_MS'));
});

test('цвета куба заданы и в светлой, и в тёмной теме; «уменьшить движение» есть', () => {
    const blocks = css.split('[data-theme="dark"] body.explorer-page');
    assert.equal(blocks.length, 2, 'блок тёмной темы не найден');
    const tokens = ['--ex-axis-rows', '--ex-axis-cols', '--ex-axis-time', '--ex-cube-gap', '--ex-cube-front',
        '--ex-cube-top', '--ex-cube-side', '--ex-cube-back', '--ex-cube-edge', '--ex-cube-wire', '--ex-cube-slice'];
    for (const token of tokens) {
        assert.ok(blocks[0].includes(token + ':'), 'светлая тема: ' + token);
        assert.ok(blocks[1].split('}')[0].includes(token + ':'), 'тёмная тема: ' + token);
    }
    const reduced = css.match(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/);
    assert.ok(reduced, 'нет @media (prefers-reduced-motion: reduce)');
    assert.ok(reduced[0].includes('.ex-cube *') && reduced[0].includes('.ex-unfold-row'));
    assert.ok(cubeJs.includes("prefers-reduced-motion: reduce"), 'JS тоже должен знать о настройке');
});

test('страница подключает куб и пишет в карточку только через setMsg', () => {
    const grid = html.indexOf('explorer/grid.js');
    const cube = html.indexOf('explorer/cube.js');
    const page = html.indexOf('explorer/page.js');
    assert.ok(grid > 0 && cube > grid && page > cube, 'порядок скриптов: grid.js, cube.js, page.js');
    for (const id of ['exCube', 'exCubeLegend', 'exMsgBody']) assert.ok(html.includes('id="' + id + '"'), id);
    assert.ok(!/el\.msg\.innerHTML\s*=/.test(pageJs), 'el.msg.innerHTML = … стирает куб — только setMsg');
    assert.ok(/Cube\.create\(\$\('exCube'\), \$\('exCubeLegend'\)\)/.test(pageJs));
    assert.ok(/if \(state\.unfold && Cube\) Cube\.unfold\(el\.gridWrap\)/.test(pageJs), 'раскладка — только у свежего ответа');
    assert.ok(/state\.unfold = false;/.test(pageJs));
});

test('без эмодзи в коде куба', () => {
    const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
    assert.ok(!emoji.test(cubeJs), 'cube.js');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);

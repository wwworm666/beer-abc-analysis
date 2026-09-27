/**
 * ТЕКСТОВЫЕ проверки страницы «Кухня — ABC/XYZ и потери» (/kitchen).
 *
 *     node tests/test_kitchen_render.mjs
 *
 * Страница — клон «Фасовки»: разметка и стили общие (классы pk-*,
 * static/packaging/packaging.css), свои шаблон, id узлов (kt*) и скрипт.
 * Здесь проверяется согласованность файлов между собой: шаблон объявляет узлы,
 * JS их ищет, CSS описывает классы, пороги в подписях совпадают с ядром.
 * Исполнение — в tests/test_kitchen_runtime.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const html = read('templates/kitchen.html');
const css = read('static/packaging/packaging.css');
const js = read('static/js/kitchen/kitchen.js');
const view = read('static/js/shared/abc_view.js');
const viewCss = read('static/shared/abc_view.css');
const pages = read('routes/pages.py');
const analysisPy = read('routes/analysis.py');
const thresholds = read('core/abc_thresholds.py');
const nav = read('templates/shared/nav.html');

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

test('маршрут, эндпоинт и пункт меню на месте', () => {
    assert.match(pages, /@pages_bp\.route\('\/kitchen'\)[\s\S]*?render_template\('kitchen\.html', bars=BARS, app_version=APP_VERSION\)/,
        'нет маршрута /kitchen с app_version');
    assert.match(analysisPy, /@analysis_bp\.route\('\/api\/kitchen', methods=\['POST'\]\)/, 'нет эндпоинта');
    assert.match(nav, /<a href="\/kitchen" class="sidebar-link">[\s\S]*?Кухня\n/, 'нет пункта «Кухня» в меню');
});

test('шаблон подключает общие стили фасовки, раскладку и свой скрипт с кэш-бастингом', () => {
    assert.match(html, /body class="packaging-page kitchen-page"/, 'нет класса страницы для токенов --pk-*');
    for (const href of ['/static/packaging/packaging.css?v={{ app_version }}',
                        '/static/shared/abc_view.css?v={{ app_version }}',
                        '/static/draft/draft.css?v={{ app_version }}']) {
        assert.ok(html.includes(href), `нет ${href}`);
    }
    assert.match(html, /static\/js\/shared\/abc_view\.js\?v=\{\{ app_version \}\}[\s\S]*static\/js\/kitchen\/kitchen\.js\?v=\{\{ app_version \}\}/,
        'общий модуль не подключён до kitchen.js');
    assert.ok(!/packaging\.js/.test(html), 'шаблон тянет скрипт фасовки');
    assert.match(html, /<title>Кухня — ABC\/XYZ и потери — Пивная культура<\/title>/);
    assert.match(html, /pk-title-n">Кухня — ABC\/XYZ и потери</);
});

test('все id, которые ищет JS, объявлены в шаблоне, и чужих id фасовки нет', () => {
    const wanted = new Set();
    for (const m of js.matchAll(/getElementById\('([^']+)'\)/g)) wanted.add(m[1]);
    wanted.delete('sidebar-toggle');
    wanted.delete('ktFrom');
    wanted.delete('ktTo');
    const missing = [...wanted].filter((id) => !html.includes(`id="${id}"`));
    assert.deepEqual(missing, [], `нет узлов в шаблоне: ${missing.join(', ')}`);
    assert.ok(!/id="pk[A-Z]/.test(html), 'в шаблоне остались id фасовки');
    assert.ok(!/getElementById\('pk/.test(js), 'скрипт ищет id фасовки');
});

test('страница берёт данные из /api/kitchen и только оттуда', () => {
    assert.match(js, /fetch\('\/api\/kitchen'/, 'нет запроса к эндпоинту кухни');
    assert.equal([...js.matchAll(/fetch\(/g)].length, 1);
    assert.ok(!/\/api\/packaging/.test(js), 'остался запрос фасовки');
    assert.match(js, /AbcView\.fromKitchen\(data\)/, 'модель раскладки не кухонная');
    assert.match(view, /function fromKitchen\(d\)/, 'в общем модуле нет fromKitchen');
});

test('вкладки: у каждой своя панель, видна только «Обзор»', () => {
    for (const [id, panel] of [['ktOverview', 'overview'], ['ktPanelItems', 'items'],
                               ['ktPanelCats', 'cats'], ['ktPrices', 'prices'],
                               ['ktPanelLosses', 'losses'], ['ktPanelBars', 'bars']]) {
        assert.match(html, new RegExp(`id="${id}" data-panel="${panel}"`), `нет панели ${panel}`);
    }
    const shown = [...html.matchAll(/class="av-panel" id="(\w+)" data-panel="\w+"( hidden)?/g)]
        .filter((m) => !m[2]).map((m) => m[1]);
    assert.deepEqual(shown, ['ktOverview']);
});

test('классы pk-, которые пишет JS, описаны в CSS фасовки, av- — в abc_view.css', () => {
    const used = new Set();
    for (const m of js.matchAll(/class="(pk-[a-z0-9 -]+)"/g)) {
        m[1].split(/\s+/).filter(Boolean).forEach((c) => used.add(c));
    }
    const missing = [...used].filter((c) => !css.includes(`.${c}`));
    assert.deepEqual(missing, [], `нет в packaging.css: ${missing.join(', ')}`);
    const av = new Set();
    for (const m of js.matchAll(/["' ](av-[\w-]+)/g)) av.add(m[1]);
    const missingAv = [...av].filter((c) => !viewCss.includes(`.${c}`));
    assert.deepEqual(missingAv, [], `нет в abc_view.css: ${missingAv.join(', ')}`);
});

test('пороги наценки в расшифровке и в карточке совпадают с ядром (180/150)', () => {
    const aMin = Math.round(parseFloat(thresholds.match(/KITCHEN_MARKUP_A_MIN = ([\d.]+)/)[1]) * 100);
    const bMin = Math.round(parseFloat(thresholds.match(/KITCHEN_MARKUP_B_MIN = ([\d.]+)/)[1]) * 100);
    assert.equal(aMin, 180);
    assert.equal(bMin, 150);
    const key = html.match(/<div class="pk-key" id="ktKey">([\s\S]*?)<\/div>\s*<!--/);
    assert.ok(key, 'нет блока расшифровки букв');
    assert.ok(key[1].includes(`от ${aMin}%`), 'в расшифровке не тот порог A');
    assert.ok(key[1].includes(`от ${bMin}% до ${aMin}%`), 'в расшифровке не тот порог B');
    assert.ok(key[1].includes(`ниже ${bMin}%`), 'в расшифровке не тот порог C');
    assert.ok(!/от 120%|ниже 100%/.test(html), 'в шаблоне остались пороги фасовки');
    assert.ok(js.includes(`'наценка ${aMin}% и выше'`), 'в карточке не тот порог A');
    assert.ok(js.includes(`'наценка от ${bMin}% до ${aMin}%'`), 'в карточке не тот порог B');
    assert.match(view, /M\.aMin = 1\.8;\s*M\.bMin = 1\.5;/, 'в общем модуле не пороги кухни');
});

test('пояснения расчётов свёрнуты в «Как считается», а не висят на экране', () => {
    const loose = html.replace(/<details[\s\S]*?<\/details>/g, '');
    assert.ok(!/class="pk-legend"/.test(loose), 'легенда вне раскрывашки');
    assert.ok(!/id="ktKey"/.test(loose), 'расшифровка кода вне раскрывашки');
    assert.ok(!/<div class="pk-note">/.test(js), 'заметка расчёта рисуется открытой');
    assert.match(js, /function howNote/, 'нет общей обёртки пояснения');
});

test('баланс и расхождения — в рублях, единицы продуктов только в подписи', () => {
    assert.match(js, /Баланс кухни за период/, 'нет заголовка баланса кухни');
    assert.match(js, /Изменение остатка кухни/, 'нет итога баланса');
    assert.match(js, /' ₽<\/span><\/div>' \+/, 'итог баланса не в рублях');
    assert.match(js, /row\.LossRub/, 'расхождения не из рублёвых полей');
    assert.ok(!/row\.LossQty|p\.LossQty/.test(js), 'остались штучные потери фасовки');
    assert.match(js, /function units\(value, unit\)/, 'нет подписи в единице продукта');
    assert.match(html, /рубли по закупке/, 'единица вкладки не названа');
});

test('категория и модификаторы объяснены, фасовочных слов не осталось', () => {
    assert.match(html, /третий уровень дерева, если он есть, иначе второй/, 'не объяснено, откуда категория');
    assert.match(html, /Без категории \(К\)/, 'не названа группа без категории');
    assert.match(thresholds, /UNCATEGORIZED_KITCHEN = 'Без категории \(К\)'/, 'подпись не в ядре');
    assert.match(html, /Соусы-модификаторы/, 'в легенде нет модификаторов');
    assert.match(js, /соусы-модификаторы не входят в позиции/, 'модификаторы не названы в диагностике');
    const visible = html.replace(/<!--[\s\S]*?-->/g, '');
    assert.ok(!/фасовк|бутыл/i.test(visible), 'в разметке кухни остались слова фасовки');
    const strings = [...js.matchAll(/'[^'\n]*'/g)].map((m) => m[0]).join('\n');
    assert.ok(!/фасовк|бутыл|' шт'/i.test(strings), 'в строках скрипта остались слова фасовки');
});

test('обработчики кликов не подставляют данные в атрибуты, имена экранируются', () => {
    assert.ok(!/onclick=/.test(js + html), 'появился инлайновый onclick');
    assert.match(js, /data-cat="' \+ esc\(/, 'имя категории пишется без экранирования');
    assert.match(js, /esc\(row\.ProductName\)/, 'имя продукта склада не экранируется');
    assert.match(js, /esc\(p\.Beer\)/, 'имя позиции не экранируется');
});

test('без эмодзи в разметке и скрипте', () => {
    const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/u;
    assert.ok(!emoji.test(html), 'эмодзи в шаблоне');
    assert.ok(!emoji.test(js), 'эмодзи в скрипте');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

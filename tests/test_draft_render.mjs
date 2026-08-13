/**
 * ТЕКСТОВЫЕ проверки страницы «Анализ проливов» (/draft).
 *
 *     node tests/test_draft_render.mjs
 *
 * Здесь проверяется согласованность трёх файлов между собой: шаблон объявляет
 * узлы, JS их ищет, CSS описывает классы, которые JS пишет в разметку. Такие
 * расхождения не ловятся ни юнит-тестами расчёта, ни глазами на одном экране:
 * страница просто молча не рисует блок.
 *
 * Исполнение видов — в tests/test_draft_runtime.mjs (тот же приём, что у пары
 * test_marketing_render.mjs / test_marketing_runtime.mjs).
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const html = read('templates/draft.html');
const css = read('static/draft/draft.css');
const js = read('static/js/draft/draft.js');

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

test('шаблон подключает свои стили и скрипт с кэш-бастингом', () => {
    assert.match(html, /static\/draft\/draft\.css\?v=\{\{ app_version \}\}/,
        'draft.css без ?v — правки вёрстки не доедут до браузеров');
    assert.match(html, /static\/js\/draft\/draft\.js\?v=\{\{ app_version \}\}/,
        'draft.js без ?v');
    assert.match(html, /body class="draft-page"/, 'нет класса страницы для токенов');
});

test('все id, которые ищет JS, объявлены в шаблоне', () => {
    const wanted = new Set();
    for (const m of js.matchAll(/getElementById\('([^']+)'\)/g)) wanted.add(m[1]);
    // sidebar-toggle приходит из общего shared/nav.html, а не из этого шаблона.
    wanted.delete('sidebar-toggle');
    // Поля «своего периода» JS сам же и рисует внутри меню.
    wanted.delete('drFrom');
    wanted.delete('drTo');
    const missing = [...wanted].filter((id) => !html.includes(`id="${id}"`));
    assert.deepEqual(missing, [], `нет узлов в шаблоне: ${missing.join(', ')}`);
});

test('страница берёт данные из /api/draft-kegs и только оттуда', () => {
    assert.match(js, /fetch\('\/api\/draft-kegs'/, 'нет запроса к новому эндпоинту');
    assert.ok(!/draft-analyze|waiter-analyze/.test(js), 'остался вызов старого эндпоинта');
    const fetches = [...js.matchAll(/fetch\(/g)].length;
    assert.equal(fetches, 1, `запросов должно быть ровно один, найдено ${fetches}`);
});

test('список баров приходит из шаблона, а не захардкожен в JS', () => {
    assert.match(html, /id="drBars"[^>]*>\{\{ bars \| tojson \}\}/,
        'бары не отдаются страницей');
    assert.ok(!/Лиговский|Варшавская|Кременчугская/.test(js),
        'название бара захардкожено в JS');
});

test('все классы, которые JS пишет в разметку, описаны в CSS', () => {
    // Классы страницы всегда с префиксом dr-, состояния — is-. Разметка
    // собирается конкатенацией, поэтому ищем литералы, а не целые атрибуты.
    const used = new Set();
    for (const m of js.matchAll(/["'\s]((?:dr-|is-)[\w-]+)/g)) used.add(m[1]);
    const known = new Set([...css.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
    const missing = [...used].filter((c) => !known.has(c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
});

test('в CSS нет цветов мимо блока токенов', () => {
    const body = css.slice(css.indexOf('/* Общий каркас'));
    const strays = [...body.matchAll(/#[0-9A-Fa-f]{3,8}\b/g)].map((m) => m[0]);
    // Аватар бармена — единственный именной цвет, как и на /me.
    const allowed = new Set(['#D3B471', '#FFFFFF']);
    const bad = strays.filter((hex) => !allowed.has(hex));
    assert.deepEqual(bad, [], `HEX вне токенов: ${bad.join(', ')}`);
});

test('тёмная тема переопределяет те же токены, что светлая', () => {
    const light = css.slice(css.indexOf('body.draft-page {'), css.indexOf('[data-theme="dark"]'));
    const dark = css.slice(css.indexOf('[data-theme="dark"]'),
                           css.indexOf('/* Общий каркас'));
    const names = (block) => new Set([...block.matchAll(/(--dr-[\w-]+):/g)].map((m) => m[1]));
    const lightNames = names(light);
    const darkNames = names(dark);
    // Радиусы, шрифты и тени задаются один раз — их тема не меняет.
    const skip = (n) => n.startsWith('--dr-r-') || n === '--dr-sans' || n === '--dr-mono';
    const missing = [...lightNames].filter((n) => !skip(n) && !darkNames.has(n) &&
        !n.startsWith('--dr-shadow'));
    assert.deepEqual(missing, [], `в тёмной теме не заданы: ${missing.join(', ')}`);
});

test('обработчики кликов не подставляют данные в атрибуты', () => {
    // На апострофе в «Gravity It's Mango» ломался прежний onclick с JSON.
    assert.ok(!/onclick=/.test(js), 'в разметке появился инлайновый onclick');
    assert.match(js, /data-keg="' \+ esc\(/, 'идентификатор кега пишется без экранирования');
    assert.match(js, /data-bt="' \+ esc\(/, 'имя бармена пишется без экранирования');
});

test('имена из данных экранируются везде, где попадают в разметку', () => {
    const names = js.match(/\+ (esc\()?\w+\.(KegName|Bartender|DishName)/g) || [];
    const bare = names.filter((s) => !s.includes('esc('));
    assert.deepEqual(bare, [], `без экранирования: ${bare.join(', ')}`);
});

test('вкладок больше нет: обе таблицы на одном экране', () => {
    assert.ok(!/dtab-btn|data-tab=/.test(html), 'остались кнопки вкладок');
    assert.match(html, /id="drKegs"/, 'нет таблицы кегов');
    assert.match(html, /id="drBts"/, 'нет таблицы барменов');
    assert.match(html, /id="drBalance"/, 'нет баланса');
    assert.match(html, /id="drLosses"/, 'нет блока расхождений');
});

test('на странице объяснено, что такое бармен и откуда литры', () => {
    assert.match(html, /Авторизовал/, 'нет оговорки про AuthUser');
    assert.match(html, /объём порции из техкарты/, 'не объяснено, откуда литры на человека');
    assert.match(html, /расход кегов со склада/, 'не объяснено, откуда литры вообще');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

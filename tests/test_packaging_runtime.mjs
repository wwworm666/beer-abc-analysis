/**
 * ЗАПУСК страницы «ABC/XYZ анализ» фасовки (/packaging) в Node с DOM-стабом.
 *
 *     node tests/test_packaging_runtime.mjs
 *
 * Зачем отдельно от test_packaging_render.mjs: тот проверяет ТЕКСТ файлов (узел
 * объявлен, класс описан в CSS). Ошибку времени выполнения так не поймать — а
 * именно она страшнее всего: страница молча остаётся пустой.
 *
 * Здесь настоящий packaging.js исполняется на настоящем ответе /api/packaging
 * (tests/fixtures/packaging_sample.json — посчитан из data/beer_report.json,
 * 4 бара, 30 дней, все 28 категорий) и проверяется, что в узлы легла ожидаемая
 * разметка: сводка, корзины, обе таблицы с итогами, карточки.
 *
 * Тот же приём, что у пары test_draft_render.mjs / test_draft_runtime.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const js = read('static/js/packaging/packaging.js');
const BLOCK = JSON.parse(read('tests/fixtures/packaging_sample.json'));

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

// ---------------------------------------------------------------- DOM-стаб
function makeEl(id) {
    return {
        id: id || '',
        dataset: {},
        style: {},
        value: '',
        textContent: '',
        innerHTML: '',
        hidden: false,
        disabled: false,
        scrollTop: 0,
        className: '',
        classList: {
            _s: new Set(),
            add(c) { this._s.add(c); },
            remove(c) { this._s.delete(c); },
            contains(c) { return this._s.has(c); }
        },
        listeners: {},
        addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
        querySelector() { return null; },
        querySelectorAll() { return []; },
        closest() { return null; },
        click() { (this.listeners.click || []).forEach((fn) => fn({ target: this })); }
    };
}

const IDS = ['pkBurger', 'pkBarBtn', 'pkBarMenu', 'pkBarLabel', 'pkPerBtn', 'pkPerMenu',
             'pkPerLabel', 'pkPerHint', 'pkCatch', 'pkRun', 'pkRunLabel', 'pkSpin',
             'pkContext', 'pkXyzChip', 'pkMsg', 'pkBody', 'pkSum', 'pkBuckets',
             'pkCatCount', 'pkCats', 'pkPosCount', 'pkSearch', 'pkPos',
             'pkDrawer', 'pkBackdrop', 'pkBars'];

function boot() {
    const byId = {};
    IDS.forEach((id) => { byId[id] = makeEl(id); });
    byId.pkBars.textContent = JSON.stringify(['Лиговский', 'Варшавская']);

    const fetchCalls = [];
    const sandbox = {
        console, Intl, Math, Number, String, Object, Array, JSON, Date, isNaN, Promise,
        setTimeout, module: undefined,
        document: {
            readyState: 'complete',
            getElementById: (id) => byId[id] || null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            body: makeEl('body')
        },
        location: { hash: '' },
        fetch: (url, opts) => {
            fetchCalls.push({ url, body: JSON.parse(opts.body) });
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve(BLOCK)
            });
        }
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    new vm.Script(js, { filename: 'packaging.js' }).runInContext(sandbox);
    return { sandbox, byId, fetchCalls };
}

const env = boot();
// Запрос уходит промисом, поэтому ждём микрозадачи перед проверками.
await new Promise((resolve) => setTimeout(resolve, 0));

const api = env.sandbox.window.__packaging;

test('скрипт исполняется и сам запрашивает данные при загрузке', () => {
    assert.equal(env.fetchCalls.length, 1, 'страница не сходила за данными');
    assert.equal(env.fetchCalls[0].url, '/api/packaging');
    const body = env.fetchCalls[0].body;
    assert.ok(body.date_from && body.date_to, 'период не передан в запрос');
    assert.equal(body.bar, '', 'по умолчанию должен быть сводный разрез «Общая»');
});

test('период по умолчанию достаточен для XYZ', () => {
    // Прежняя страница открывалась на одной неделе, где третья буква не
    // считается ни у кого, и молча показывала анализ без XYZ.
    const body = env.fetchCalls[0].body;
    const weeks = api.weeksIn(body.date_from, body.date_to);
    assert.ok(weeks >= 3, `в периоде по умолчанию ${weeks} полных недель, нужно от 3`);
});

test('после ответа тело страницы показано, сообщение убрано', () => {
    assert.equal(env.byId.pkBody.hidden, false, 'тело страницы осталось скрытым');
    assert.equal(env.byId.pkMsg.hidden, true, 'сообщение о загрузке не убрано');
    assert.match(env.byId.pkContext.textContent, /разрез: Общая/, 'нет строки разреза');
    assert.match(env.byId.pkContext.textContent, /полных недель|полные недели/,
        'не показано, сколько недель в периоде');
});

test('сводка: семь плиток с числами из ответа', () => {
    const html = env.byId.pkSum.innerHTML;
    const tiles = (html.match(/class="pk-tile"/g) || []).length;
    assert.equal(tiles, 7, `плиток должно быть 7, найдено ${tiles}`);
    for (const cap of ['ВЫРУЧКА', 'ПРОДАНО', 'ПОЗИЦИЙ', 'КАТЕГОРИЙ', 'НАЦЕНКА',
                       'МАРЖА', 'СРЕДНЯЯ ЦЕНА']) {
        assert.ok(html.includes(cap), `нет плитки ${cap}`);
    }
    assert.ok(html.includes(String(BLOCK.totals.categories)), 'число категорий не выведено');
    assert.ok(html.includes('(выручка − себестоимость) / себестоимость'),
        'формула наценки не показана на экране');
});

test('корзины действий: все шесть, с долей выручки', () => {
    const html = env.byId.pkBuckets.innerHTML;
    const cards = (html.match(/class="pk-bucket"/g) || []).length;
    assert.equal(cards, 6, `корзин должно быть 6, найдено ${cards}`);
    for (const name of ['Звёзды', 'Рабочие лошадки', 'Недооценённые', 'Премиум-ниша',
                        'Фон', 'Удалить']) {
        assert.ok(html.includes(name), `нет корзины «${name}»`);
    }
    assert.match(html, /% выручки/, 'не показана доля выручки корзины');
    // Сумма по корзинам должна сойтись с числом позиций, у которых есть наценка.
    const withMarkup = BLOCK.positions.filter((p) => p.ABC_Bucket).length;
    const shown = Object.values(BLOCK.bucket_stats).reduce((a, v) => a + v, 0);
    assert.equal(shown, withMarkup, 'корзины не покрывают все позиции с наценкой');
});

test('таблица категорий: ВСЕ категории, без урезания до топ-10', () => {
    const html = env.byId.pkCats.innerHTML;
    const rows = (html.match(/class="pk-row is-body"/g) || []).length;
    assert.equal(rows, BLOCK.categories.length,
        `строк ${rows}, категорий ${BLOCK.categories.length} — список урезан`);
    assert.ok(rows > 10, 'в фикстуре меньше 11 категорий — тест ничего не доказывает');
    assert.match(html, /Итого · \d+ категор/, 'нет строки итога');
    assert.match(env.byId.pkCatCount.textContent, /· все$/, 'не подписано, что показаны все');
});

test('в таблице категорий есть и самая мелкая категория тоже', () => {
    const html = env.byId.pkCats.innerHTML;
    const last = BLOCK.categories[BLOCK.categories.length - 1];
    assert.ok(html.includes(api.esc(last.Category)),
        `последняя категория «${last.Category}» не выведена`);
});

test('итог таблицы категорий сходится со сводкой', () => {
    const html = env.byId.pkCats.innerHTML;
    assert.ok(html.includes(api.money(BLOCK.totals.revenue)),
        'итог по выручке не совпал со сводкой');
    assert.ok(html.includes('100,0%'), 'накопленная доля итога не 100%');
});

test('таблица позиций: все позиции, итог и направление сортировки', () => {
    const html = env.byId.pkPos.innerHTML;
    const rows = (html.match(/class="pk-row is-body"/g) || []).length;
    assert.equal(rows, BLOCK.positions.length, `строк ${rows}, позиций ${BLOCK.positions.length}`);
    assert.match(html, /ВЫРУЧКА ↓/, 'не показано направление сортировки');
    assert.match(html, /Итого · \d+ позиц/, 'нет строки итога');
    // Первая строка — самая выручная позиция.
    const first = html.indexOf(api.esc(BLOCK.positions[0].Beer));
    const second = html.indexOf(api.esc(BLOCK.positions[1].Beer));
    assert.ok(first > 0 && first < second, 'порядок строк не по убыванию выручки');
});

test('позиции без буквы XYZ показаны прочерком, а не выдуманной буквой', () => {
    const html = env.byId.pkPos.innerHTML;
    const noLetter = BLOCK.positions.filter((p) => !p.XYZ_Category).length;
    const dashes = (html.match(/class="pk-xyz">—/g) || []).length;
    assert.equal(dashes, noLetter,
        `прочерков ${dashes}, позиций без буквы ${noLetter}`);
});

test('поиск фильтрует позиции и по названию, и по категории', () => {
    const cat = BLOCK.categories[0].Category;
    api.state.query = cat;
    api.render();
    const html = env.byId.pkPos.innerHTML;
    const rows = (html.match(/class="pk-row is-body"/g) || []).length;
    const expected = BLOCK.positions.filter((p) =>
        p.Beer.toLowerCase().includes(cat.toLowerCase()) ||
        p.Category.toLowerCase().includes(cat.toLowerCase())).length;
    assert.equal(rows, expected, `по запросу «${cat}» строк ${rows}, ждали ${expected}`);
    assert.match(env.byId.pkPosCount.textContent, /из/, 'счётчик не показал «N из M»');
    api.state.query = '';
    api.render();
});

test('число ячеек в строках совпадает с числом колонок грида', () => {
    // Молчаливая поломка: если в шапке 9 колонок, а в строке итога 8 ячеек, таблица
    // не падает — она просто съезжает. Считаем по РЕАЛЬНОЙ разметке, а не по глазам.
    const css = fs.readFileSync(path.join(ROOT, 'static/packaging/packaging.css'), 'utf8');

    function columnsOf(selector) {
        const re = new RegExp(selector.replace(/[.\s]/g, (m) => (m === '.' ? '\\.' : '\\s+')) +
            '\\s*\\{[^}]*grid-template-columns:([^;]+);');
        const m = css.match(re);
        assert.ok(m, `не найден грид для ${selector}`);
        // Колонки разделены пробелами, но minmax(190px, 1.5fr) — одна колонка.
        return m[1].trim().replace(/\([^)]*\)/g, '()').split(/\s+/).filter(Boolean).length;
    }

    function cellsPerRow(html) {
        // Режем по началу строки, в каждом куске считаем ячейки верхнего уровня.
        const parts = html.split(/<div class="pk-row/).slice(1);
        return parts.map((part) => {
            const body = part.split(/<\/div>/)[0];
            return (body.match(/<span/g) || []).length -
                   // Вложенные span внутри ячейки доли и таблетки ABC не считаются.
                   (body.match(/<span class="pk-bar/g) || []).length * 2 -
                   (body.match(/<span class="pk-abc /g) || []).length;
        });
    }

    for (const [selector, node] of [['.pk-cats .pk-row', env.byId.pkCats],
                                   ['.pk-pos .pk-row', env.byId.pkPos]]) {
        const columns = columnsOf(selector);
        const counts = cellsPerRow(node.innerHTML);
        assert.ok(counts.length > 2, `в ${selector} не нашлось строк`);
        const wrong = counts.filter((n) => n !== columns);
        assert.deepEqual(wrong, [],
            `${selector}: колонок ${columns}, но есть строки с ${[...new Set(wrong)].join(', ')} ячейками`);
    }
});

test('карточка позиции: разбор всех трёх букв с формулами', () => {
    const top = BLOCK.positions[0];
    api.openPosition(top.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.equal(env.byId.pkDrawer.hidden, false, 'карточка не открылась');
    assert.ok(html.includes(api.esc(top.Beer)), 'в карточке нет названия позиции');
    for (const band of ['ПРОДАЖИ', 'ДЕНЬГИ', 'ABC-АНАЛИЗ', 'ВТОРАЯ ШКАЛА',
                        'XYZ — СТАБИЛЬНОСТЬ СПРОСА']) {
        assert.ok(html.includes(band), `нет секции ${band}`);
    }
    const formulas = (html.match(/class="pk-formula"/g) || []).length;
    assert.ok(formulas >= 5, `формул в карточке ${formulas}, ждали не меньше 5`);
    assert.ok(html.includes('база: весь ассортимент разреза'),
        'не подписана база буквы по выручке');
});

test('карточка позиции: разбивка по барам в разрезе «Общая»', () => {
    const top = BLOCK.positions[0];
    api.openPosition(top.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('ПО БАРАМ'), 'нет разбивки по барам');
    const rows = (html.match(/class="pk-mini-row(?! is-head)[^"]*"/g) || []).length;
    assert.ok(rows >= top.ByBar.length, 'строки баров не выведены');
    top.ByBar.forEach((b) => {
        assert.ok(html.includes(api.esc(b.Bar)), `нет бара ${b.Bar}`);
    });
});

test('карточка позиции: недельный ряд, из которого получилась буква XYZ', () => {
    const withXyz = BLOCK.positions.find((p) => p.XYZ_Category);
    assert.ok(withXyz, 'в фикстуре нет позиций с буквой XYZ');
    api.openPosition(withXyz.Id);
    const html = env.byId.pkDrawer.innerHTML;
    const bars = (html.match(/class="pk-week-bar/g) || []).length;
    assert.equal(bars, withXyz.WeeklyQty.length,
        `столбиков ${bars}, недель в ряду ${withXyz.WeeklyQty.length}`);
    assert.ok(html.includes('коэффициент вариации'), 'не показан CV');
});

test('карточка позиции без XYZ объясняет, почему буквы нет', () => {
    const without = BLOCK.positions.find((p) => !p.XYZ_Category);
    assert.ok(without, 'в фикстуре нет позиций без буквы XYZ');
    api.openPosition(without.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('Категория не присвоена'), 'нет объяснения прочерка');
    assert.ok(html.includes('данных не хватило'), 'прочерк не подписан в разборе букв');
});

test('карточка категории: все её позиции внутри', () => {
    const cat = BLOCK.categories[0];
    api.openCategory(cat.Category);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes(api.esc(cat.Category)), 'нет названия категории');
    assert.ok(html.includes('ВСЕ ПОЗИЦИИ КАТЕГОРИИ'), 'нет списка позиций');
    const rows = (html.match(/class="pk-mini-row(?! is-head)[^"]*"/g) || []).length;
    const members = BLOCK.positions.filter((p) => p.Category === cat.Category).length;
    assert.equal(rows, members, `строк ${rows}, позиций в категории ${members}`);
});

test('карточка корзины: состав и что с ним делать', () => {
    api.openBucket('price_up');
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('Недооценённые'), 'нет названия корзины');
    assert.ok(html.includes('Поднять наценку'), 'нет действия');
    assert.ok(html.includes('наценка ниже 100%') || html.includes('ниже 100%'),
        'не объяснено, почему позиция сюда попала');
    const rows = (html.match(/class="pk-mini-row(?! is-head)[^"]*"/g) || []).length;
    const members = BLOCK.positions.filter((p) => p.ABC_Bucket === 'price_up').length;
    assert.equal(rows, members, `строк ${rows}, позиций в корзине ${members}`);
});

test('ошибка сервера показывается словами, а не молчанием', () => {
    const local = boot();
    local.sandbox.fetch = () => Promise.resolve({
        ok: false, status: 404,
        json: () => Promise.resolve({ error: 'Нет данных за выбранный период' })
    });
    return new Promise((resolve) => {
        local.sandbox.window.__packaging.state.data = null;
        local.byId.pkRun.click();
        setTimeout(() => {
            assert.equal(local.byId.pkBody.hidden, true, 'тело осталось показанным');
            assert.equal(local.byId.pkMsg.hidden, false, 'сообщение не показано');
            assert.match(local.byId.pkMsg.textContent, /Нет данных/,
                'причина от сервера не доехала до экрана');
            assert.match(local.byId.pkMsg.className, /err/, 'сообщение не помечено ошибкой');
            resolve();
        }, 0);
    });
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

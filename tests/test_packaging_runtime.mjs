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
 * (tests/fixtures/packaging_sample.json — собран скриптом
 * tests/fixtures/build_packaging_sample.py: продажи из data/beer_report.json,
 * 4 бара, 30 дней, проводки склада синтетические) и проверяется, что в узлы легла ожидаемая
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
// Общая раскладка (вкладки, «Обзор», «Цены», бары): на странице подключена до packaging.js.
const viewJs = read('static/js/shared/abc_view.js');
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
             'pkContext', 'pkXyzChip', 'pkMsg', 'pkBody',
             'pkTabs', 'pkOverview', 'pkPrices', 'pkFilter',
             'pkPanelItems', 'pkPanelCats', 'pkPanelLosses', 'pkPanelBars',
             'pkCatCount', 'pkCats', 'pkPosCount', 'pkSearch', 'pkPos',
             'pkUpdated', 'pkBalance', 'pkLosses', 'pkDiag',
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
        history: { replaceState: () => {} },
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
    new vm.Script(viewJs, { filename: 'abc_view.js' }).runInContext(sandbox);
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

// Клик по элементу с data-атрибутами: стаб не умеет closest(), поэтому цель
// клика отвечает только на селектор своего атрибута.
function clickAttr(node, attrs) {
    const target = {
        closest: (sel) => {
            const m = sel.match(/^\[(data-[\w-]+)\]$/);
            return m && attrs[m[1]] !== undefined
                ? { getAttribute: (a) => (attrs[a] === undefined ? null : attrs[a]) } : null;
        }
    };
    node.listeners.click.forEach((fn) => fn({ target }));
}
// Intl ставит неразрывные пробелы между разрядами: сравниваем с обычными.
const flat = (h) => h.replace(/[  ]/g, ' ');
// Таблица позиций показывает порцию строк; проверкам «все строки» нужна вся.
function withAllRows(fn) {
    const keep = api.state.limit;
    api.state.limit = 1e9;
    api.render();
    try { fn(); } finally { api.state.limit = keep; api.render(); }
}

test('обзор: маржа, продано и выручка с бутылки из ответа', () => {
    const html = flat(env.byId.pkOverview.innerHTML);
    assert.match(html, /Маржа за 30 дней/, 'нет главного числа');
    assert.match(html, /325 459/, 'маржа не совпала с суммами ответа');
    assert.match(html, /605 944/, 'выручка не выведена');
    assert.match(html, /1 103 шт/, 'проданные штуки не выведены');
    assert.ok(html.includes(`${BLOCK.totals.categories} категори`), 'число категорий не выведено');
    assert.match(html, /116,0%[\s\S]*ниже минимума сети 120%/, 'наценка сети против минимума не показана');
    assert.ok(html.includes('Наценка = (выручка − закупка) / закупка'), 'формула наценки не показана');
    const loose = html.replace(/<details[\s\S]*?<\/details>/g, '');
    assert.ok(!loose.includes('Наценка = (выручка − закупка)'), 'формула висит открытой');
});

test('вкладки: числа на кнопках, «Бары» только в «Общей»', () => {
    const tabs = flat(env.byId.pkTabs.innerHTML);
    for (const id of ['overview', 'items', 'cats', 'prices', 'losses', 'bars']) {
        assert.match(tabs, new RegExp(`data-tab="${id}"`), `нет вкладки ${id}`);
    }
    assert.ok(!/data-tab="people"/.test(tabs), 'у фасовки нет барменов');
    assert.match(tabs, new RegExp(`Позиции<span class="n">${BLOCK.positions.length}<`), 'на вкладке позиций нет числа');
    assert.match(tabs, /Цены<span class="n neg">−23 тыс ₽/, 'на вкладке цен нет недополученной суммы со знаком минус');
    const panels = ['pkOverview', 'pkPanelItems', 'pkPanelCats', 'pkPrices', 'pkPanelLosses', 'pkPanelBars'];
    assert.deepEqual(panels.filter((id) => !env.byId[id].hidden), ['pkOverview']);
    clickAttr(env.byId.pkTabs, { 'data-tab': 'bars' });
    assert.deepEqual(panels.filter((id) => !env.byId[id].hidden), ['pkPanelBars']);
    const bars = flat(env.byId.pkPanelBars.innerHTML);
    for (const bar of BLOCK.bars_in_scope) assert.ok(bars.includes(api.esc(bar)), `нет бара ${bar}`);
    clickAttr(env.byId.pkTabs, { 'data-tab': 'overview' });
});

test('обзор: «где деньги» — цены, недостача и «сверить учёт» в рублях', () => {
    const html = flat(env.byId.pkOverview.innerHTML);
    assert.match(html, /Цены ниже минимума сети[\s\S]*class="av-neg">−23 261 ₽[\s\S]*недополучено/,
        'недобор по ценам не показан как недополученные деньги');
    assert.match(html, /Недостача по инвентаризации[\s\S]*−14 501/, 'нет недостачи в рублях');
    assert.match(html, /Сверить учёт/, 'нет строки «Сверить учёт»');
    assert.ok(!/Бармены ниже средней/.test(html), 'у фасовки нет разреза по барменам');
});

test('решения по ассортименту: шесть групп с сервера, с долей выручки', () => {
    const html = env.byId.pkOverview.innerHTML;
    for (const card of BLOCK.buckets) {
        assert.ok(html.includes(api.esc(card.name)), `нет группы «${card.name}»`);
        assert.ok(html.includes(api.esc(card.action)), `нет действия «${card.action}»`);
        if (card.count > 0) {
            assert.ok(html.includes(`data-go="items" data-filter="${card.key}"`), `группа ${card.key} не кликается`);
        }
    }
    // Каждая позиция ровно в одной группе: сумма групп равна числу позиций,
    // и позиций без группы нет (раньше без себестоимости позиция исчезала).
    assert.equal(BLOCK.buckets.reduce((a, c) => a + c.count, 0), BLOCK.positions.length,
        'группы не покрывают все позиции');
    assert.ok(BLOCK.positions.every((p) => p.ABC_Bucket), 'есть позиция без группы');
    assert.ok(Math.abs(BLOCK.buckets.reduce((a, c) => a + c.revenue_share_percent, 0) - 100) < 1e-6,
        'доли групп не складываются в 100%');
});

test('клик по группе открывает таблицу позиций с фильтром', () => {
    const view = api.view();
    const low = BLOCK.positions.filter((p) => p.ABC_Bucket === 'low_markup').length;
    try {
        clickAttr(env.byId.pkOverview, { 'data-go': 'items', 'data-filter': 'low_markup' });
        assert.equal(view.tab(), 'items', 'не открылась вкладка позиций');
        assert.equal(view.filter(), 'low_markup');
        const rows = (env.byId.pkPos.innerHTML.match(/class="pk-row is-body"/g) || []).length;
        assert.equal(rows, Math.min(low, 30), `строк ${rows}, позиций в группе ${low}`);
        assert.match(env.byId.pkPosCount.textContent, new RegExp(`${low} из ${BLOCK.positions.length}`));
        assert.match(env.byId.pkPos.innerHTML, new RegExp(`Итого · ${low} позиц`), 'итог не по выборке группы');
        assert.match(env.byId.pkFilter.innerHTML, /data-filter="low_markup" aria-pressed="true"/);
    } finally {
        view.setFilter(null);
        view.show('overview', false);
    }
    const rows = (env.byId.pkPos.innerHTML.match(/class="pk-row is-body"/g) || []).length;
    assert.equal(rows, 30, 'фильтр не снялся');
});

test('таблица позиций: порция в 30 строк, «Показать ещё» добавляет следующие', () => {
    const count = () => (env.byId.pkPos.innerHTML.match(/class="pk-row is-body"/g) || []).length;
    assert.equal(count(), 30, 'первая порция не 30 строк');
    assert.match(flat(env.byId.pkPos.innerHTML), new RegExp(`Показать ещё 30 · всего ${BLOCK.positions.length}`));
    // Итог — по всем позициям, а не по показанным.
    assert.match(env.byId.pkPos.innerHTML, new RegExp(`Итого · ${BLOCK.positions.length} позиц`));
    clickAttr(env.byId.pkPos, { 'data-more-rows': '' });
    assert.equal(count(), 60, 'кнопка не добавила строки');
    // Новый поиск начинает с первой порции.
    env.byId.pkSearch.value = '';
    env.byId.pkSearch.listeners.input[0]({});
    assert.equal(count(), 30, 'поиск не сбросил порцию');
});

test('потери в рублях: недостача в балансе и ₽ по строкам расхождений', () => {
    const bal = flat(env.byId.pkBalance.innerHTML);
    assert.match(bal, /недостача в деньгах: <b>≈ 14 501 ₽<\/b> по закупке/, 'нет недостачи в рублях');
    const loss = flat(env.byId.pkLosses.innerHTML);
    assert.match(loss, /class="av-rub-head">≈ [\d ]+ ₽ по закупке/, 'нет суммы потерь в рублях');
    assert.ok((loss.match(/class="av-rub"/g) || []).length > 0, 'у строк нет рублей');
    assert.match(env.byId.pkBalance.innerHTML, /<details class="av-how"><summary>Как считается/,
        'формула баланса не свёрнута');
});

test('таблица категорий: ВСЕ категории, без урезания до топ-10', () => {
    const html = env.byId.pkCats.innerHTML;
    const rows = (html.match(/class="pk-row is-body"/g) || []).length;
    assert.equal(rows, BLOCK.categories.length,
        `строк ${rows}, категорий ${BLOCK.categories.length} — список урезан`);
    assert.ok(rows > 10, 'в фикстуре меньше 11 категорий — тест ничего не доказывает');
    const revAt = html.indexOf('ДОЛЯ ВЫРУЧКИ');
    const qtyAt = html.indexOf('ДОЛЯ ШТУК');
    const marAt = html.indexOf('ДОЛЯ МАРЖИ');
    assert.ok(revAt >= 0 && qtyAt > revAt && marAt > qtyAt,
        'в категориях нет трёх долей: выручки, штук и маржи');
    const total = html.match(/class="pk-row is-total"[\s\S]*?<\/div>/);
    assert.equal((total[0].match(/100,0%/g) || []).length, 3,
        'в итоге категорий должны быть три стопроцентные доли');
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

test('таблица позиций: все позиции, итог и направление сортировки', () => withAllRows(() => {
    const html = env.byId.pkPos.innerHTML;
    const rows = (html.match(/class="pk-row is-body"/g) || []).length;
    assert.equal(rows, BLOCK.positions.length, `строк ${rows}, позиций ${BLOCK.positions.length}`);
    const revAt = html.indexOf('ДОЛЯ ВЫРУЧКИ');
    const qtyAt = html.indexOf('ДОЛЯ ШТУК');
    const marAt = html.indexOf('ДОЛЯ МАРЖИ');
    assert.ok(revAt >= 0 && qtyAt > revAt && marAt > qtyAt,
        'в позициях нет трёх долей: выручки, штук и маржи');
    assert.ok(!/>ДОЛЯ</.test(html), 'старая колонка «ДОЛЯ» ещё в таблице позиций');
    assert.match(html, /ВЫРУЧКА ↓/, 'не показано направление сортировки');
    assert.match(html, /Итого · \d+ позиц/, 'нет строки итога');
    // Первая строка — самая выручная позиция.
    const first = html.indexOf(api.esc(BLOCK.positions[0].Beer));
    const second = html.indexOf(api.esc(BLOCK.positions[1].Beer));
    assert.ok(first > 0 && first < second, 'порядок строк не по убыванию выручки');
}));

test('спрос — третья буква кода, отдельной колонки XYZ нет', () => withAllRows(() => {
    // С 2026-09-26 колонки XYZ нет: она повторяла третью букву кода и не влезала
    // в ширину страницы. Позиция без буквы спроса показана «?», а не выдуманной буквой.
    const html = env.byId.pkPos.innerHTML;
    const head = html.match(/class="pk-row is-head"[\s\S]*?<\/div>/)[0];
    assert.ok(!/>XYZ</.test(head), 'в шапке таблицы позиций осталась колонка XYZ');
    assert.ok(!html.includes('pk-xyz'), 'в строках осталась ячейка XYZ');
    const codes = [...html.matchAll(/class="pk-abc [a-z]*">([^<]*)</g)].map((m) => m[1]);
    assert.equal(codes.length, BLOCK.positions.length, 'не у каждой позиции есть код');
    const noLetter = BLOCK.positions.filter((p) => !p.XYZ_Category).length;
    const questions = codes.filter((c) => c.endsWith('?')).length;
    assert.equal(questions, noLetter, `кодов с «?» ${questions}, позиций без буквы ${noLetter}`);
    for (const p of BLOCK.positions) {
        assert.equal(p.ABC_Combined.charAt(2), p.XYZ_Category || '?',
            `третья буква кода ${p.Beer} не спрос`);
    }
}));

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

test('чип «обновлено» показывает время забора данных из iiko', () => {
    assert.equal(env.byId.pkUpdated.hidden, false, 'чип скрыт');
    assert.match(env.byId.pkUpdated.textContent, /обновлено \d\d:\d\d/);
});

test('баланс фасовки: шесть строк со знаками, итог и формула словами', () => {
    const html = env.byId.pkBalance.innerHTML;
    for (const label of ['Приход по накладным', 'Перемещения · приход', 'Перемещения · расход',
                         'Продано через кассу', 'Списано актами']) {
        assert.ok(html.includes(label), `нет строки «${label}»`);
    }
    assert.ok(/Недостача по инвентаризациям|Излишек по инвентаризациям/.test(html),
        'нет строки инвентаризации');
    assert.ok(html.includes('Изменение остатка фасовки'), 'нет итога');
    assert.ok(html.includes('+' + api.qty(BLOCK.losses.invoice_in)), 'приход без знака плюс');
    assert.ok(html.includes('−' + api.qty(BLOCK.losses.sold)), 'продажи без знака минус');
    assert.match(html, /от продаж/, 'нет плашки «% от продаж»');
    assert.match(html, /приход .* − расход .* \(продано/, 'формула баланса не напечатана');
    // Подписи /draft, которые для бутылок ложны: «кег…» и «списание по техкарте».
    assert.ok(!/кег|по техкарте/.test(html), 'в баланс фасовки просочились подписи розлива');
    assert.ok(html.includes('без техкарты'), 'не сказано, что товар списывается сам');
});

test('расхождения: все строки, раскрывашка после восьми, серые без карточки', () => {
    const html = env.byId.pkLosses.innerHTML;
    const items = BLOCK.losses.by_item;
    assert.ok(items.length > 8, 'в фикстуре меньше 9 расхождений — раскрывашка не проверяется');
    const rows = (html.match(/class="pk-loss-row(?! is-head)/g) || []).length;
    assert.equal(rows, items.length, `строк ${rows}, расхождений ${items.length}`);
    assert.match(html, /<details class="pk-more">/, 'нет раскрывашки');
    assert.match(html, /ещё \d+ позиц/, 'раскрывашка без подписи');
    const unmatched = items.filter((k) => k.PositionId === null);
    assert.ok(unmatched.length > 0, 'в фикстуре нет несопоставленных товаров');
    assert.equal((html.match(/pk-loss-row is-static/g) || []).length, unmatched.length,
        'несопоставленные строки не помечены как некликабельные');
    const linked = (html.match(/pk-loss-row" data-pos="/g) || []).length;
    assert.equal(linked, items.length - unmatched.length, 'сопоставленные строки без data-pos');
    // Излишек печатается со знаком плюс и не считается потерей.
    const surplus = items.find((k) => k.InventoryNetQty < 0);
    assert.ok(surplus, 'в фикстуре нет излишка');
    assert.ok(html.includes('+' + api.qty(Math.abs(surplus.InventoryNetQty))), 'излишек без плюса');
});

test('пороги плашек потерь: 10% и 30%', () => {
    assert.equal(api.lossTone(4), 'calm');
    assert.equal(api.lossTone(12), 'warn');
    assert.equal(api.lossTone(40), 'bad');
    assert.equal(api.lossTone(null), 'calm');
});

test('диагностика склада называет всё, что выпало из баланса', () => {
    const html = env.byId.pkDiag.innerHTML;
    const d = BLOCK.losses.diagnostics;
    assert.ok(d.non_piece_products.length > 0 && Object.keys(d.ignored_types).length > 0,
        'фикстура не покрывает диагностику');
    assert.ok(html.includes('не в штуках'), 'не названы товары не в штуках');
    assert.ok(html.includes('других типов'), 'не названы чужие типы проводок');
    // Число строк само по себе не говорит, сколько бутылок ушло: штуки печатаются.
    const type = Object.keys(d.ignored_types)[0];
    assert.ok(html.includes(type + ' × ' + d.ignored_types[type].rows + ' (расход ' +
        api.qty(d.ignored_types[type].out)), 'у чужих типов не напечатаны штуки');
    assert.ok(html.includes('(расход ' + api.qty(d.non_piece_products[0].Out) + ' ' +
        d.non_piece_products[0].Unit), 'у товара не в штуках не напечатано количество');
    if (Math.abs(d.sold_delta) > 0.005) {
        assert.ok(html.includes('без карточки склада'), 'причины разницы названы не те же, что в документе');
    }
    assert.ok(html.includes('не сопоставлен'), 'не названы несопоставленные');
    if (Math.abs(d.sold_delta) > 0.005) {
        assert.ok(html.includes('по кассе продано'), 'разница касса/склад не показана');
    }
});

test('карточка позиции: секция потерь с формулой', () => {
    const withLoss = BLOCK.positions.find((p) => p.LossQty > 0);
    assert.ok(withLoss, 'в фикстуре нет позиции с потерями');
    api.openPosition(withLoss.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('ПОТЕРИ'), 'нет секции потерь');
    for (const cap of ['ПРОДАНО ПО СКЛАДУ', 'СПИСАНО АКТАМИ', 'НЕДОСТАЧА ИНВЕНТ.']) {
        assert.ok(html.includes(cap), `нет ячейки ${cap}`);
    }
    assert.ok(html.includes(api.qty(withLoss.LossQty) + ' / ' + api.qty(withLoss.SoldQtyStock)),
        'формула процента потерь не напечатана числами');
});

test('клик по строке расхождений открывает карточку той же позиции', () => {
    const linked = BLOCK.losses.by_item.find((k) => k.PositionId !== null);
    const handlers = env.byId.pkLosses.listeners.click || [];
    assert.ok(handlers.length, 'на блоке расхождений нет обработчика клика');
    env.byId.pkDrawer.hidden = true;
    // Делегирование: цель клика — потомок строки с data-pos.
    handlers.forEach((fn) => fn({ target: { closest: (sel) =>
        sel === '[data-pos]' ? { dataset: { pos: String(linked.PositionId) } } : null } }));
    assert.equal(env.byId.pkDrawer.hidden, false, 'карточка не открылась по клику');
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes(api.esc(BLOCK.positions[linked.PositionId].Beer)),
        'карточка открылась не на той позиции');
});

test('страница переживает ответ без блока losses', () => {
    const stripped = JSON.parse(JSON.stringify(BLOCK));
    delete stripped.losses;
    delete stripped.generated_at;
    api.state.data = stripped;
    api.render();
    assert.ok(env.byId.pkBalance.innerHTML.includes('проводки склада за период не пришли'),
        'без проводок баланс должен сказать об этом, а не молчать');
    assert.ok(env.byId.pkLosses.innerHTML.includes('проводки склада за период не пришли'),
        'без проводок блок расхождений не должен утверждать, что расхождений не было');
    assert.equal(env.byId.pkUpdated.hidden, true);
    api.state.data = BLOCK;
    api.render();
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

test('формула в карточке ЧИСЛЕННО даёт показанный процент', () => {
    // Требование .claude/CLAUDE.md пункт 1. Раньше в знаменатель подставлялся
    // totals.margin, а доли считались от суммы положительных марж — деление на
    // экране не давало написанного справа результата.
    const t = BLOCK.totals;
    assert.ok(typeof t.revenue_abc_base === 'number', 'сервер не отдаёт базу по выручке');
    assert.ok(typeof t.margin_abc_base === 'number', 'сервер не отдаёт базу по марже');
    BLOCK.positions.slice(0, 40).forEach((p) => {
        assert.ok(Math.abs(p.TotalRevenue / t.revenue_abc_base * 100 -
            p.RevenueSharePercent) < 1e-6, `доля выручки не сходится: ${p.Beer}`);
        assert.ok(Math.abs(p.TotalMargin / t.margin_abc_base * 100 -
            p.MarginSharePercent) < 1e-6, `доля маржи не сходится: ${p.Beer}`);
        assert.ok(Math.abs(p.TotalRevenue / p.RevenueBaseInCategory * 100 -
            p.RevenueShareInCategoryPercent) < 1e-6, `доля в категории: ${p.Beer}`);
    });
    // И то же самое в разметке: карточка печатает именно базу, а не итог.
    api.openPosition(BLOCK.positions[0].Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes(api.money(t.revenue_abc_base)), 'в формуле не база по выручке');
    assert.ok(html.includes(api.money(t.margin_abc_base)), 'в формуле не база по марже');
});

test('продажи вне недельного окна объяснены, а не показаны голым нулём', () => {
    const outside = BLOCK.positions.find((p) => p.QtyOutsideWeeks > 0);
    assert.ok(outside, 'в фикстуре нет позиций с продажами вне окна');
    api.openPosition(outside.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('вне недельного окна'), 'нет объяснения про окно');
    assert.ok(html.includes('учтены полностью'), 'не сказано, что деньги не потеряны');
    // Недели всегда в форме «N из M», а не голым числом.
    assert.ok(/НЕДЕЛЬ С ПРОДАЖАМИ<\/div>\s*<div class="pk-cell-v[^"]*">\d+ из \d+/.test(html),
        'число недель показано без базы');
});

test('шапка называет границы недельного окна', () => {
    const period = BLOCK.period;
    assert.ok(period.weeks_from && period.weeks_to, 'сервер не отдаёт границы окна');
    assert.notEqual(period.weeks_from, period.from,
        'в фикстуре окно совпадает с периодом — тест ничего не доказывает');
    assert.match(env.byId.pkContext.textContent, /\(\d\d\.\d\d — \d\d\.\d\d\.\d{4}\)/,
        'границы окна не показаны в строке контекста');
});

test('сортировка по наценке не ставит «нет данных» впереди', () => {
    const withoutMarkup = BLOCK.positions.filter((p) => p.MarkupPercent === null).length;
    assert.ok(withoutMarkup > 0, 'в фикстуре нет позиций без наценки');
    api.state.posSort = { key: 'MarkupPercent', dir: 1 };   // по возрастанию
    try {
        withAllRows(() => {
            const html = env.byId.pkPos.innerHTML;
            const firstDash = html.indexOf('class="pk-num dash"');
            const firstValue = html.search(/class="pk-num">\d/);
            assert.ok(firstDash > firstValue,
                'позиции без наценки встали первыми, как будто их наценка худшая');
        });
    } finally {
        api.state.posSort = { key: 'TotalRevenue', dir: -1 };
        api.render();
    }
});

test('доля маржи: значения с сервера, сортировка и итог 100%', () => {
    // Колонка берёт MarginSharePercent из ответа: у позиции — доля в сумме
    // положительных маржей, у категории — то же по категориям. Страница не пересчитывает.
    const sum = BLOCK.positions.reduce((a, p) => a + p.MarginSharePercent, 0);
    assert.ok(Math.abs(sum - 100) < 1e-6, 'доли позиций в марже не складываются в 100%');
    const catSum = BLOCK.categories.reduce((a, c) => a + c.MarginSharePercent, 0);
    assert.ok(Math.abs(catSum - 100) < 1e-6, 'доли категорий в марже не складываются в 100%');
    const top = BLOCK.positions.slice().sort((a, b) => b.MarginSharePercent - a.MarginSharePercent)[0];
    api.state.posSort = { key: 'MarginSharePercent', dir: -1 };
    try {
        withAllRows(() => {
            const html = env.byId.pkPos.innerHTML;
            assert.match(html, /ДОЛЯ МАРЖИ ↓/, 'не показано направление сортировки');
            const firstRow = html.match(/class="pk-row is-body"[\s\S]*?(?=class="pk-row)/)[0];
            assert.ok(firstRow.includes(api.esc(top.Beer)), 'первая строка не лидер по марже');
            assert.ok(firstRow.includes(api.pct(top.MarginSharePercent, 1)), 'доля маржи не из ответа');
            const total = html.match(/class="pk-row is-total"[\s\S]*?<\/div>/)[0];
            assert.equal((total.match(/100,0%/g) || []).length, 3, 'в итоге позиций не три доли по 100%');
        });
    } finally {
        api.state.posSort = { key: 'TotalRevenue', dir: -1 };
        api.render();
    }
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

test('карточка группы: правило с числами, подсказка и состав', () => {
    api.openBucket('low_markup');
    const html = env.byId.pkDrawer.innerHTML;
    const card = BLOCK.buckets.find((c) => c.key === 'low_markup');
    assert.ok(html.includes(api.esc(card.name)), 'нет названия группы');
    assert.ok(html.includes(api.esc(card.action)), 'нет действия');
    assert.ok(html.includes('правило: ' + api.esc(card.rule)), 'правило группы не напечатано');
    assert.ok(/120%/.test(card.rule) && / 5\b/.test(card.rule), 'в правиле нет порогов');
    assert.ok(html.includes(api.esc(card.hint)), 'нет подсказки, что делать');
    const rows = (html.match(/class="pk-mini-row(?! is-head)[^"]*"/g) || []).length;
    const members = BLOCK.positions.filter((p) => p.ABC_Bucket === 'low_markup').length;
    assert.equal(rows, members, `строк ${rows}, позиций в группе ${members}`);
    assert.equal(rows, card.count, 'счётчик карточки не совпал с составом');
});

test('карточка позиции называет её группу решения', () => {
    const p = BLOCK.positions.find((x) => x.ABC_Bucket === 'core');
    api.openPosition(p.Id);
    const html = env.byId.pkDrawer.innerHTML;
    const card = BLOCK.buckets.find((c) => c.key === 'core');
    assert.ok(html.includes(api.esc(card.name + ' · ' + card.action)), 'в карточке позиции нет группы');
});

// Ожидание вынесено ИЗ теста наружу: раннер синхронный и возвращённый промис не
// ждёт, поэтому тест с отложенными проверками был зелёным всегда — что бы ни
// случилось внутри. Сначала доводим сценарий до конца здесь, потом проверяем
// синхронно.
const failing = boot();
// Сначала ДОЖДАТЬСЯ стартовой загрузки: init() сам зовёт run(), и пока её промис
// не разрешился, state.loading === true — повторный клик молча игнорируется
// (`if (state.loading) return`), а потом стартовый ответ дорисовывает страницу.
await new Promise((resolve) => setTimeout(resolve, 0));
failing.sandbox.fetch = () => Promise.resolve({
    ok: false, status: 404,
    json: () => Promise.resolve({ error: 'Нет данных за выбранный период' })
});
failing.byId.pkRun.click();
await new Promise((resolve) => setTimeout(resolve, 0));

test('ошибка сервера показывается словами, а не молчанием', () => {
    assert.equal(failing.byId.pkBody.hidden, true, 'тело осталось показанным');
    assert.equal(failing.byId.pkMsg.hidden, false, 'сообщение не показано');
    assert.match(failing.byId.pkMsg.textContent, /Нет данных/,
        'причина от сервера не доехала до экрана');
    assert.match(failing.byId.pkMsg.className, /err/, 'сообщение не помечено ошибкой');
});

test('баланс: излишек по инвентаризациям — своя строка, плюс, спокойная плашка, минус в формуле', () => {
    const data = JSON.parse(JSON.stringify(BLOCK));
    const l = data.losses;
    l.inventory_in = l.inventory_out + 4;
    l.inventory_net = l.inventory_out - l.inventory_in;
    l.inventory_percent_of_sold = l.inventory_net / l.sold * 100;
    api.state.data = data;
    api.render();
    const html = env.byId.pkBalance.innerHTML;
    assert.ok(html.includes('Излишек по инвентаризациям'), 'нет строки излишка');
    assert.ok(!html.includes('Недостача по инвентаризациям'), 'недостача и излишек одновременно');
    assert.ok(html.includes('+' + api.qty(4)), 'излишек без знака плюс');
    assert.match(html, /pk-pill ok">[\d,]+% от продаж/, 'плашка излишка не спокойная или с минусом');
    assert.ok(html.includes('− излишек ' + api.qty(4)), 'в формуле излишек напечатан как «+ недостача −4»');
    assert.ok(html.includes('приход ' + api.qty(l.received)), 'приход в формуле не с сервера');
    api.state.data = BLOCK;
    api.render();
});

test('карточка: излишек у позиции подписан излишком, процент со знаком плюс', () => {
    const surplus = BLOCK.positions.find((p) => p.InventoryNetQty < 0 && p.SoldQtyStock > 0);
    assert.ok(surplus, 'в фикстуре нет позиции с излишком и продажами по складу');
    api.openPosition(surplus.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('ИЗЛИШЕК ИНВЕНТ.'), 'ячейка не переименована в излишек');
    assert.ok(!html.includes('НЕДОСТАЧА ИНВЕНТ.'), 'у излишка осталась подпись недостачи');
    const at = html.indexOf('ИЗЛИШЕК ИНВЕНТ.');
    const cellHtml = html.slice(at, at + 400);
    assert.match(cellHtml, /pk-pill ok">\+[\d,]+%/, 'процент излишка без плюса или не спокойный');
    assert.ok(!/pk-pill (calm|warn|bad|ok)">−/.test(cellHtml), 'процент излишка с минусом');
});

test('карточка: весовой товар — пометка вместо формулы потерь', () => {
    const nuts = BLOCK.positions.find((p) => p.StockUnit && p.StockUnit !== 'шт');
    assert.ok(nuts, 'в фикстуре нет весовой позиции');
    api.openPosition(nuts.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('в единице «' + nuts.StockUnit + '»'), 'нет пометки про единицу склада');
    assert.ok(!html.includes('Движений по складу за период у позиции нет'),
        'весовой товар выдан за отсутствие движений');
});

test('карточка: акт без продаж по складу — потери названы, процент не выдуман', () => {
    const data = JSON.parse(JSON.stringify(BLOCK));
    const p = data.positions[1];
    p.SoldQtyStock = 0; p.WriteoffQty = 3; p.InventoryNetQty = 2; p.LossQty = 5;
    p.LossPercentOfSold = null; p.WriteoffPercentOfSold = null; p.InventoryPercentOfSold = null;
    api.state.data = data;
    api.render();
    api.openPosition(p.Id);
    const html = env.byId.pkDrawer.innerHTML;
    assert.ok(html.includes('не продано, но движения есть'), 'подпись не признаёт движений');
    assert.ok(html.includes('потери ' + api.qty(5) + ' шт'), 'потери не названы');
    assert.ok(!html.includes('Движений по складу за период у позиции нет'), 'сказано «движений нет» при акте');
    assert.ok(!html.includes('% от проданного по складу'), 'процент выдуман при нуле продаж');
    api.state.data = BLOCK;
    api.render();
});

test('склад без продаж: таблица позиций говорит про отсутствие продаж, а не про поиск', () => {
    const data = JSON.parse(JSON.stringify(BLOCK));
    data.positions = [];
    data.categories = [];
    api.state.data = data;
    api.render();
    assert.ok(env.byId.pkPos.innerHTML.includes('продаж фасовки за период нет'),
        'пустая таблица просит уточнить запрос, хотя запроса не было');
    api.state.data = BLOCK;
    api.render();
});

test('раннер действительно исполняет проверки (защита от вечнозелёного теста)', () => {
    // Мета-проверка: если кто-то снова напишет тест, возвращающий промис,
    // его проверки молча перестанут исполняться. Ловим это прямо здесь.
    let ran = false;
    test('__self_check__', () => { ran = true; });
    assert.ok(ran, 'раннер не вызывает переданную функцию');
    // Компенсируем счётчик служебного прогона.
    passed--;
    // Игла собирается из кусков, иначе проверка находит саму себя в исходнике.
    const needle = new RegExp('return' + '\\s+new\\s+' + 'Promise');
    const src = fs.readFileSync(path.join(ROOT, 'tests/test_packaging_runtime.mjs'), 'utf8')
        .replace(/const needle[\s\S]*?;\n/, '');
    assert.ok(!needle.test(src),
        'тест возвращает промис — раннер синхронный и его проверки не исполнятся');
});

test('наценка округляется вниз и не спорит с буквой', () => {
    // «Айингер Лагер Хелл» — 119,5%: буква B и «Низкая наценка»; до 2026-09-26
    // таблица печатала «120%».
    assert.equal(api.markupPct(119.5, 0), '119%');
    assert.equal(api.markupPct(120, 0), '120%');
    assert.equal(api.markupPct(99.96, 1), '99,9%');
    assert.equal(api.markupPct(null, 0), '—');
    const near = BLOCK.positions.find((p) => p.MarkupPercent !== null &&
        p.MarkupPercent >= 119.5 && p.MarkupPercent < 120);
    assert.ok(near, 'в фикстуре нет позиции с наценкой 119,5–120%');
    assert.equal(near.ABC_Markup, 'B');
    withAllRows(() => {
        const html = env.byId.pkPos.innerHTML;
        const row = html.slice(html.indexOf(api.esc(near.Beer)));
        assert.ok(row.slice(0, 1500).includes('>119%<'), 'наценка 119,5% напечатана не как 119%');
    });
});

test('карточка категории: «N позиций», формула делит на базу категорий', () => {
    const cat = BLOCK.categories.find((c) => c.BeersCount > 1);
    api.openCategory(cat.Category);
    const html = env.byId.pkDrawer.innerHTML;
    const word = api.plural(cat.BeersCount, 'позиция', 'позиции', 'позиций');
    assert.ok(html.includes(cat.BeersCount + ' ' + word), 'число позиций подписано не позициями');
    assert.ok(!/\d+ штук(а|и)? · клик/.test(html), 'осталось «N штук»');
    const base = BLOCK.totals.category_revenue_abc_base;
    assert.equal(typeof base, 'number', 'сервер не отдал базу долей категорий');
    assert.ok(html.includes(api.esc(api.money(cat.TotalRevenue) + ' / ' + api.money(base))),
        'в формуле не база категорий');
    assert.ok(Math.abs(cat.TotalRevenue / base * 100 - cat.RevenueSharePercent) < 1e-9,
        'выручка / база не даёт напечатанную долю');
});

test('скользящие пресеты заканчиваются вчера, текущие — сегодня', () => {
    const iso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
        '-' + String(d.getDate()).padStart(2, '0');
    const today = new Date();
    const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
    const mod = env.sandbox.window.__packaging;
    for (const [key, days] of [['d30', 30], ['d90', 90], ['d180', 180]]) {
        const range = mod.presetRange ? mod.presetRange(key) : null;
        assert.ok(range, 'presetRange не экспортирован');
        assert.equal(range.to, iso(yesterday), `${key} кончается не вчера`);
        const span = Math.round((new Date(range.to) - new Date(range.from)) / 86400000) + 1;
        assert.equal(span, days, `${key}: ${span} дней`);
    }
    assert.equal(mod.presetRange('week').to, iso(today));
    assert.equal(mod.presetRange('month').to, iso(today));
    assert.equal(env.fetchCalls[0].body.date_to, iso(yesterday), 'по умолчанию уходит не по вчера');
});

test('расхождения в «Общей»: недостача одного бара не гасится излишком другого', () => {
    const data = JSON.parse(JSON.stringify(BLOCK));
    const row = data.losses.by_item.find((r) => r.PositionId !== null);
    Object.assign(row, { InventoryNetQty: 0, InventoryShortQty: 5, InventorySurplusQty: 5,
                         WriteoffQty: 0, LossQty: 5 });
    const pos = data.positions.find((p) => p.Id === row.PositionId);
    Object.assign(pos, { InventoryNetQty: 0, InventoryShortQty: 5, InventorySurplusQty: 5,
                         WriteoffQty: 0, LossQty: 5, SoldQtyStock: 40,
                         LossPercentOfSold: 12.5, InventoryShortPercentOfSold: 12.5,
                         InventorySurplusPercentOfSold: 12.5, StockUnit: null });
    api.state.data = data;
    api.render();
    assert.ok(env.byId.pkLosses.innerHTML.includes('5<i class="pk-loss-plus"> +5</i>'),
        'в строке нет недостачи с излишком рядом');
    api.openPosition(pos.Id);
    const card = env.byId.pkDrawer.innerHTML;
    assert.ok(card.includes('НЕДОСТАЧА ИНВЕНТ.'), 'ячейка не недостача');
    assert.ok(card.includes('Ещё излишек 5 шт в других барах'), 'излишек других баров не назван');
    assert.ok(card.includes('недостача 5 · 5 / 40 = 12,5%'), 'формула потерь не по недостаче баров');
    api.state.data = BLOCK;
    api.render();
});

async function asyncTest(name, fn) {
    try {
        await fn();
        passed++;
        console.log(`  ok  ${name}`);
    } catch (e) {
        failed++;
        console.log(`FAIL  ${name}`);
        console.log(`      ${e && e.message}`);
    }
}
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

await asyncTest('смена бара во время загрузки: старый ответ выброшен, новый запрос ушёл', async () => {
    const calls = [];
    const pending = [];
    env.sandbox.fetch = (url, opts) => {
        calls.push(JSON.parse(opts.body));
        let resolve;
        const promise = new Promise((r) => { resolve = r; });
        pending.push(resolve);
        return promise;
    };
    const reply = (label) => ({ ok: true, status: 200, json: () =>
        Promise.resolve(Object.assign({}, BLOCK, { scope: 'bar', bar_label: label })) });
    const pick = (bar) => env.byId.pkBarMenu.listeners.click[0](
        { target: { closest: () => ({ dataset: { bar } }) } });
    pick('Лиговский');
    pick('Варшавская');
    assert.equal(calls.length, 1, 'второй запрос ушёл, не дождавшись первого');
    pending[0](reply('Лиговский'));
    for (let i = 0; i < 5; i++) await flush();
    assert.equal(calls.length, 2, 'новый выбор потерян: запрос по нему не ушёл');
    assert.equal(calls[1].bar, 'Варшавская');
    assert.equal(env.byId.pkBody.hidden, true, 'устаревший ответ лёг на экран');
    pending[1](reply('Варшавская'));
    for (let i = 0; i < 5; i++) await flush();
    assert.equal(env.byId.pkBody.hidden, false, 'ответ по новому выбору не показан');
    assert.match(env.byId.pkContext.textContent, /разрез: Варшавская/);
    assert.equal(env.byId.pkBarLabel.textContent, 'Варшавская');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

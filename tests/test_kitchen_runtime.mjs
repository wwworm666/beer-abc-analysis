/**
 * ЗАПУСК страницы «Кухня — ABC/XYZ и потери» (/kitchen) в Node с DOM-стабом.
 *
 *     node tests/test_kitchen_runtime.mjs
 *
 * Настоящий kitchen.js (с общим модулем abc_view.js) исполняется на ответе
 * /api/kitchen из tests/fixtures/kitchen_sample.json — собран скриптом
 * tests/fixtures/build_kitchen_sample.py: продажи группы «ЕДА» из
 * data/cache/kitchen_report.json (4 бара, 30 дней), категории по кухонному меню,
 * проводки склада синтетические, в рублях. Проверяется, что в узлы легла
 * ожидаемая разметка: вкладки, «Обзор», таблицы, баланс и расхождения в рублях,
 * диагностика с модификаторами, карточки товара и блюда.
 *
 * Тот же приём, что у tests/test_packaging_runtime.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const js = read('static/js/kitchen/kitchen.js');
const viewJs = read('static/js/shared/abc_view.js');
const BLOCK = JSON.parse(read('tests/fixtures/kitchen_sample.json'));

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

const IDS = ['ktBurger', 'ktBarBtn', 'ktBarMenu', 'ktBarLabel', 'ktPerBtn', 'ktPerMenu',
             'ktPerLabel', 'ktPerHint', 'ktCatch', 'ktRun', 'ktRunLabel', 'ktSpin',
             'ktContext', 'ktXyzChip', 'ktMsg', 'ktBody', 'ktTabs', 'ktOverview',
             'ktPrices', 'ktFilter', 'ktPanelItems', 'ktPanelCats', 'ktPanelLosses',
             'ktPanelBars', 'ktCatCount', 'ktCats', 'ktPosCount', 'ktSearch', 'ktPos',
             'ktUpdated', 'ktBalance', 'ktLosses', 'ktDiag', 'ktDrawer', 'ktBackdrop',
             'ktBars'];

function boot() {
    const byId = {};
    IDS.forEach((id) => { byId[id] = makeEl(id); });
    byId.ktBars.textContent = JSON.stringify(['Лиговский', 'Варшавская']);

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
    new vm.Script(js, { filename: 'kitchen.js' }).runInContext(sandbox);
    return { sandbox, byId, fetchCalls };
}


const env = boot();
// Запрос уходит промисом, поэтому ждём микрозадачи перед проверками.
await new Promise((resolve) => setTimeout(resolve, 0));
const api = env.sandbox.window.__kitchen;
const b = env.byId;

// Клик по элементу с data-атрибутами: стаб не умеет closest(), поэтому цель
// клика отвечает только на селектор своего атрибута.
function clickAttr(node, attrs) {
    const target = {
        closest: (sel) => {
            const m = sel.match(/^\[(data-[\w-]+)\]$/);
            return m && attrs[m[1]] !== undefined
                ? { getAttribute: (a) => (attrs[a] === undefined ? null : attrs[a]),
                    dataset: { pos: attrs['data-pos'], cat: attrs['data-cat'] } } : null;
        }
    };
    node.listeners.click.forEach((fn) => fn({ target }));
}
// Intl ставит неразрывные пробелы между разрядами: сравниваем с обычными.
const flat = (h) => h.replace(/[  ]/g, ' ');
const rows = (h) => (h.match(/class="pk-row is-body"/g) || []).length;
const fmt = (v) => new Intl.NumberFormat('ru-RU').format(Math.round(v)).replace(/[  ]/g, ' ');

test('скрипт исполняется и сам запрашивает /api/kitchen за 30 дней', () => {
    assert.equal(env.fetchCalls.length, 1, 'страница не сходила за данными');
    assert.equal(env.fetchCalls[0].url, '/api/kitchen');
    const body = env.fetchCalls[0].body;
    const days = Math.round((new Date(body.date_to) - new Date(body.date_from)) / 86400000) + 1;
    assert.equal(days, 30);
    assert.equal(body.bar, '');
});

test('после ответа тело показано, строка разреза и чип «обновлено» на месте', () => {
    assert.equal(b.ktBody.hidden, false);
    assert.equal(b.ktMsg.hidden, true);
    assert.match(b.ktContext.textContent, /разрез: Общая \(4 бара\)/);
    assert.match(b.ktUpdated.textContent, /обновлено 12:34/);
});

test('вкладки: позиции, категории, цены, потери и бары; барменов нет', () => {
    const tabs = flat(b.ktTabs.innerHTML);
    for (const id of ['overview', 'items', 'cats', 'prices', 'losses', 'bars']) {
        assert.match(tabs, new RegExp(`data-tab="${id}"`), `нет вкладки ${id}`);
    }
    assert.ok(!/data-tab="people"/.test(tabs));
    assert.match(tabs, new RegExp(`Позиции<span class="n">${BLOCK.positions.length}<`));
    assert.match(tabs, /Цены<span class="n neg">−\d+ тыс ₽/, 'недобор не в минусе');
    assert.match(tabs, new RegExp(`Потери<span class="n neg">−${Math.round(BLOCK.losses.inventory_net / 1000)} тыс ₽`),
        'на вкладке потерь не рублёвая недостача склада');
});

test('обзор: маржа, наценка против минимума 180% и порции', () => {
    const html = flat(b.ktOverview.innerHTML);
    assert.match(html, /Маржа за 30 дней/);
    assert.ok(html.includes(fmt(BLOCK.totals.margin)), 'маржа не из ответа');
    assert.match(html, /ниже минимума сети 180%/, 'не минимум кухни');
    assert.ok(html.includes(fmt(BLOCK.totals.qty) + ' порц.'), 'продано не в порциях');
    assert.match(html, /Выручка с порции/);
    assert.match(html, /Цены ниже минимума сети[\s\S]*class="av-neg">−[\d ]+ ₽[\s\S]*недополучено/);
    assert.ok(html.includes('−' + fmt(BLOCK.losses.inventory_net) + ' ₽'), 'недостача не в рублях из баланса');
    assert.match(html, /от списанного при продаже по складу/);
});

test('таблица позиций: 30 строк, итог по всем, заголовок в порциях, модификаторов нет', () => {
    const html = flat(b.ktPos.innerHTML);
    assert.equal(rows(html), 30);
    assert.match(html, new RegExp(`Итого · ${BLOCK.positions.length} позиц`));
    assert.match(html, /ПОРЦИЙ/);
    assert.match(html, /ДОЛЯ В ПОРЦИЯХ/);
    assert.ok(!/ШТУК/.test(html), 'остался заголовок фасовки');
    for (const m of BLOCK.modifiers.items) {
        assert.ok(!BLOCK.positions.some((p) => p.Beer === m.Name), `модификатор ${m.Name} стал позицией`);
    }
    clickAttr(b.ktPos, { 'data-more-rows': '' });
    assert.equal(rows(b.ktPos.innerHTML), BLOCK.positions.length, '«Показать ещё» не добавил строки');
    b.ktSearch.value = '';
    b.ktSearch.listeners.input[0]({});
    assert.equal(rows(b.ktPos.innerHTML), 30, 'поиск не сбросил порцию');
});

test('категории: третий уровень, второй и «Без категории (К)»', () => {
    const html = b.ktCats.innerHTML;
    assert.equal(rows(html), BLOCK.categories.length);
    for (const name of ['Пицца', 'Горячее', 'Орехи', 'Без категории (К)']) {
        assert.ok(html.includes(api.esc(name)), `нет категории ${name}`);
    }
});

test('клик по группе открывает таблицу позиций с фильтром', () => {
    const view = api.view();
    const low = BLOCK.positions.filter((p) => p.ABC_Bucket === 'low_markup').length;
    try {
        clickAttr(b.ktOverview, { 'data-go': 'items', 'data-filter': 'low_markup' });
        assert.equal(view.tab(), 'items');
        assert.equal(rows(b.ktPos.innerHTML), Math.min(low, 30));
        assert.match(b.ktPosCount.textContent, new RegExp(`${low} из ${BLOCK.positions.length}`));
    } finally {
        view.setFilter(null);
        view.show('overview', false);
    }
});

test('баланс кухни: строки в рублях, итог и формула в «Как считается»', () => {
    const html = flat(b.ktBalance.innerHTML);
    assert.match(html, /Баланс кухни за период/);
    assert.match(html, /склад iiko · ₽ по закупке/);
    for (const label of ['Приход по накладным', 'Перемещения · приход', 'Перемещения · расход',
                         'Списано при продаже', 'Списано актами', 'Недостача по инвентаризациям']) {
        assert.ok(html.includes(label), `нет строки ${label}`);
    }
    assert.ok(html.includes('+' + fmt(BLOCK.losses.balance) + ' ₽'), 'итог не совпал с сервером');
    assert.match(html, /<details class="av-how"><summary>Как считается[\s\S]*приход [\d ]+ − расход [\d ]+/);
    assert.ok(!/недостача в деньгах/.test(html), 'строка пересчёта в деньги лишняя: баланс уже в рублях');
});

test('расхождения: рубли, ингредиенты серые с подписью, позиции кликаются', () => {
    const html = flat(b.ktLosses.innerHTML);
    const total = BLOCK.losses.by_item.reduce((a, r) => a + r.LossRub, 0);
    assert.ok(html.includes(fmt(total) + ' ₽ потерь по закупке'), 'шапка не в рублях');
    assert.match(html, /АКТЫ, ₽/);
    assert.equal((html.match(/class="pk-loss-row is-static"/g) || []).length,
        BLOCK.losses.by_item.filter((r) => r.PositionId === null).length);
    assert.match(html, /акты 3,2 кг · ингредиент/, 'нет подписи в единице продукта');
    const linked = BLOCK.losses.by_item.find((r) => r.PositionId !== null);
    assert.ok(html.includes(`data-pos="${linked.PositionId}"`), 'строка позиции не кликается');
});

test('диагностика: покрытие склада и модификаторы названы', () => {
    const html = flat(b.ktDiag.innerHTML);
    assert.match(html, /склад группы «ЕДА» списал при продаже [\d ]+ ₽ из [\d ]+ ₽ закупки проданного по кассе \(97,1%\)/);
    assert.match(html, /соусы-модификаторы не входят в позиции: 6 позиций, отдано \d+ порц\. на 3 918 ₽ по закупке/);
    assert.match(html, /из них 20 продаются как есть и связаны с позициями, 9 — ингредиенты блюд/);
    assert.match(html, /OUTGOING_INVOICE × 1 \(расход 900 ₽/);
});

test('карточка товара «как есть»: потери в рублях к списанному при продаже', () => {
    const p = BLOCK.positions.find((x) => x.SoldCostStock > 0 && x.WriteoffRub > 0);
    api.openPosition(p.Id);
    const html = flat(b.ktDrawer.innerHTML);
    assert.match(html, /ПОТЕРИ[\s\S]*₽ по закупке, к списанному при продаже/);
    assert.match(html, /СПИСАНО ПРИ ПРОДАЖЕ/);
    assert.ok(html.includes('акты ' + fmt(p.WriteoffRub) + ' ₽'), 'формула потерь не в рублях');
    assert.match(html, /ПРОДАНО[\s\S]*порц\./);
    assert.match(html, /ЦЕНА ПОРЦИИ/);
});

test('карточка блюда: потери — у продуктов, а не у блюда', () => {
    const p = BLOCK.positions.find((x) => x.Beer === 'Картофель фри, порция');
    api.openPosition(p.Id);
    const html = b.ktDrawer.innerHTML;
    assert.match(html, /готовится из ингредиентов/);
    assert.ok(!/СПИСАНО ПРИ ПРОДАЖЕ/.test(html), 'у блюда нарисованы нули склада');
});

test('буква наценки в карточке — по порогам кухни', () => {
    const b180 = BLOCK.positions.find((x) => x.ABC_Markup === 'B');
    api.openPosition(b180.Id);
    assert.match(b.ktDrawer.innerHTML, /наценка от 150% до 180%/);
    assert.ok(b180.MarkupPercent >= 150 && b180.MarkupPercent < 180, 'сервер дал B вне 150–180%');
    const low = BLOCK.buckets.find((x) => x.key === 'low_markup');
    api.openBucket('low_markup');
    assert.ok(b.ktDrawer.innerHTML.includes(api.esc(low.rule)), 'правило группы не напечатано');
    assert.match(low.rule, /180%/);
});

test('бары: профиль в «Общей», слова кухни', () => {
    const html = flat(b.ktPanelBars.innerHTML);
    for (const bar of BLOCK.bars_in_scope) assert.ok(html.includes(api.esc(bar)), `нет бара ${bar}`);
    assert.match(html, /доля категории в выручке кухни бара/);
    assert.match(html, /Цена порции к сети/);
    assert.ok(!/бутыл|фасовк/.test(html), 'в профиле баров слова фасовки');
});

test('опасные символы в данных экранируются', () => {
    const keep = api.state.data;
    const data = JSON.parse(JSON.stringify(BLOCK));
    data.positions[0].Beer = '<img src=x onerror=alert(1)> O\'Hara';
    data.losses.by_item[0].ProductName = '<b>Сыр</b>';
    api.state.data = data;
    try {
        api.render();
        assert.ok(!b.ktPos.innerHTML.includes('<img'), 'имя позиции попало тегом');
        assert.ok(!b.ktLosses.innerHTML.includes('<b>Сыр'), 'имя продукта попало тегом');
    } finally {
        api.state.data = keep;
        api.render();
    }
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

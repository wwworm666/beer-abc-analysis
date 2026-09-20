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
    api.render();
    const html = env.byId.pkPos.innerHTML;
    const firstDash = html.indexOf('class="pk-num dash"');
    const firstValue = html.search(/class="pk-num">\d/);
    assert.ok(firstDash > firstValue,
        'позиции без наценки встали первыми, как будто их наценка худшая');
    api.state.posSort = { key: 'TotalRevenue', dir: -1 };
    api.render();
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

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

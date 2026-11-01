/**
 * Общая раскладка /draft и /packaging (static/js/shared/abc_view.js).
 *
 *     node tests/test_abc_view.mjs
 *
 * Модуль считает новые числа страницы: недобор до минимума наценки, недостачу и
 * потери в рублях, сравнение барменов на одних и тех же кегах, профиль баров.
 * Здесь каждое число пересчитывается независимо от модуля прямо из фикстур
 * боевого ответа API (розлив — неделя 03-09.08.2026, фасовка — 30 дней) и
 * сверяется с тем, что модуль печатает. Плюс проверки разметки: пояснения только
 * в «Как считается», классы описаны в CSS, данные экранируются.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const src = read('static/js/shared/abc_view.js');
const css = read('static/shared/abc_view.css');
const thresholds = read('core/abc_thresholds.py');
const DRAFT_RESPONSE = JSON.parse(read('tests/fixtures/draft_kegs_sample.json'));
const DRAFT = DRAFT_RESPONSE[Object.keys(DRAFT_RESPONSE)[0]];
const PACK = JSON.parse(read('tests/fixtures/packaging_sample.json'));

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

const sandbox = { console, Intl, Math, Number, String, Object, Array, JSON, isNaN };
sandbox.window = sandbox;
vm.createContext(sandbox);
new vm.Script(src, { filename: 'abc_view.js' }).runInContext(sandbox);
const V = sandbox.AbcView;

const KITCHEN = JSON.parse(read('tests/fixtures/kitchen_sample.json'));
const MD = V.fromDraft(DRAFT);
const MP = V.fromPackaging(PACK);
const MK = V.fromKitchen(KITCHEN);
const flat = (h) => h.replace(/[  ]/g, ' ');
const near = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;
// Разметка без раскрывашек «Как считается» — то, что видно на экране сразу.
const loose = (h) => h.replace(/<details[\s\S]*?<\/details>/g, '');

// ---------------------------------------------------------------- пороги
test('пороги модуля совпадают с ядром', () => {
    const minSales = +thresholds.match(/MIN_SALES_FOR_VERDICT = (\d+)/)[1];
    assert.equal(V.MIN_SALES, minSales, 'MIN_SALES разошёлся с MIN_SALES_FOR_VERDICT');
    assert.equal(MD.aMin, +thresholds.match(/KEG_MARKUP_A_MIN = ([\d.]+)/)[1]);
    assert.equal(MD.bMin, +thresholds.match(/KEG_MARKUP_B_MIN = ([\d.]+)/)[1]);
    assert.equal(MP.aMin, +thresholds.match(/\nMARKUP_A_MIN = ([\d.]+)/)[1]);
    assert.equal(MP.bMin, +thresholds.match(/\nMARKUP_B_MIN = ([\d.]+)/)[1]);
});

// ---------------------------------------------------------------- модель
test('модель розлива: итоги и кеги из ответа как есть', () => {
    assert.equal(MD.items.length, DRAFT.kegs.length);
    assert.equal(MD.totals.revenue, DRAFT.total_revenue);
    assert.equal(MD.totals.qty, DRAFT.total_liters);
    assert.equal(MD.totals.margin, DRAFT.total_margin);
    assert.ok(MD.items.every((it) => MD.byId[it.id] === it), 'индекс по id неполный');
});

test('модель фасовки: итоги, позиции и разбивка по барам из ответа', () => {
    assert.equal(MP.items.length, PACK.positions.length);
    assert.equal(MP.totals.revenue, PACK.totals.revenue);
    assert.equal(MP.totals.qty, PACK.totals.qty);
    assert.deepEqual([...MP.barNames], PACK.bars_in_scope);
    const withBars = MP.items.filter((it) => it.byBar.length > 0).length;
    assert.ok(withBars > 0, 'в «Общей» у позиций нет разбивки по барам');
});

// ---------------------------------------------------------------- недобор
function priceGapByHand(rows, aMin, pick) {
    let total = 0;
    let count = 0;
    for (const r of rows) {
        const f = pick(r);
        if (f.bucket === 'check' || f.markup === null || f.markup === undefined) continue;
        if (!(f.cost > 0) || !(f.qty > 0) || f.sales < 5) continue;
        // Сравнение с порогом с округлением до 9 знаков, как в ядре (snap).
        if (Math.round(f.markup / 100 * 1e9) / 1e9 >= aMin) continue;
        total += f.cost * (1 + aMin) - f.revenue;
        count++;
    }
    return { total, count };
}

test('недобор розлива: закупка × 3,5 − выручка по кегам ниже 250%', () => {
    const pg = V.priceGap(MD);
    const hand = priceGapByHand(DRAFT.kegs, 2.5, (k) => ({ bucket: k.ABC_Bucket, markup: k.MarkupPercent,
        cost: k.TotalCost, qty: k.TotalLiters, sales: k.TotalPortions, revenue: k.TotalRevenue }));
    assert.equal(pg.rows.length, hand.count);
    assert.ok(near(pg.total, hand.total), `модуль ${pg.total}, вручную ${hand.total}`);
    assert.equal(Math.round(pg.total), 75128);
    assert.equal(pg.rows.length, 24);
    assert.equal(pg.half, 5, 'половину суммы должны давать первые 5 кегов');
    // Каждая строка — положительный недобор, по убыванию.
    assert.ok(pg.rows.every((r, i) => r.up > 0 && (i === 0 || pg.rows[i - 1].up >= r.up)));
});

test('недобор фасовки: закупка × 2,2 − выручка по позициям ниже 120%', () => {
    const pg = V.priceGap(MP);
    const hand = priceGapByHand(PACK.positions, 1.2, (p) => ({ bucket: p.ABC_Bucket, markup: p.MarkupPercent,
        cost: p.TotalCost, qty: p.TotalQty, sales: p.TotalQty, revenue: p.TotalRevenue }));
    assert.equal(pg.rows.length, hand.count);
    assert.ok(near(pg.total, hand.total), `модуль ${pg.total}, вручную ${hand.total}`);
    assert.equal(Math.round(pg.total), 23261);
    assert.equal(pg.half, 10);
    const half = pg.rows.slice(0, pg.half).reduce((a, r) => a + r.up, 0);
    const before = pg.rows.slice(0, pg.half - 1).reduce((a, r) => a + r.up, 0);
    assert.ok(half >= pg.total / 2 && before < pg.total / 2, 'граница «половины» не там');
});

// ---------------------------------------------------------------- рубли потерь
test('недостача в рублях: единицы × средняя закупка единицы за период', () => {
    const d = V.shortage(MD);
    assert.ok(near(d.cost, DRAFT.losses.inventory_net * DRAFT.total_cost / DRAFT.total_liters));
    assert.equal(Math.round(d.cost), 63595);
    const p = V.shortage(MP);
    assert.ok(near(p.cost, PACK.losses.inventory_net * PACK.totals.cost / PACK.totals.qty));
    assert.equal(Math.round(p.cost), 14501);
    assert.ok(p.price > p.cost, 'по цене продажи недостача должна быть дороже, чем по закупке');
});

test('потери по строкам в рублях: своя закупка единицы, без продаж — средняя', () => {
    function byHand(M, rows, id, loss) {
        const avg = M.totals.cost / M.totals.qty;
        return rows.reduce((a, r) => {
            const it = M.byId[id(r)];
            return a + loss(r) * (it && it.qty > 0 ? it.cost / it.qty : avg);
        }, 0);
    }
    const d = V.lossRubles(MD);
    assert.ok(near(d.total, byHand(MD, DRAFT.losses.by_keg, (r) => r.KegId, (r) => r.LossLiters)));
    assert.equal(Math.round(d.total), 72901);
    const p = V.lossRubles(MP);
    assert.ok(near(p.total, byHand(MP, PACK.losses.by_item, (r) => r.PositionId, (r) => r.LossQty)));
    assert.equal(Math.round(p.total), 47246);
    const byAvg = Object.values(p.byId).filter((r) => r.byAvg).length;
    const noSales = PACK.losses.by_item.filter((r) => !(MP.byId[r.PositionId] && MP.byId[r.PositionId].qty > 0)).length;
    assert.equal(byAvg, noSales, 'пометка «по средней закупке» не у тех строк');
});

// ---------------------------------------------------------------- бармены
test('бармены: выручка против тех же литров по средней цене литра кега', () => {
    const bt = V.bartenders(MD);
    assert.equal(bt.rows.length, DRAFT.bartenders.length);
    const price = {};
    DRAFT.kegs.forEach((k) => { if (k.TotalLiters > 0) price[k.KegId] = k.TotalRevenue / k.TotalLiters; });
    for (const b of DRAFT.bartenders) {
        const row = bt.rows.find((r) => r.name === b.Bartender);
        const exp = b.kegs.reduce((a, x) => a + (price[x.KegId] !== undefined ? x.Liters * price[x.KegId] : 0), 0);
        const act = b.kegs.reduce((a, x) => a + (price[x.KegId] !== undefined ? x.Revenue : 0), 0);
        assert.ok(near(row.idx, (act / exp - 1) * 100), `индекс ${b.Bartender} не сходится`);
    }
    assert.equal(bt.rows[0].name, 'Дарья Коновцова');
    assert.equal(bt.rows[0].idx.toFixed(1), '-7.7');
    assert.equal(bt.neg.length, 3);
    assert.equal(Math.round(bt.negSum), -13214);
    // Литры барменов нормированы к списанию кегов, поэтому ожидаемая выручка всех
    // барменов вместе — это выручка кегов, и отклонения в сумме почти нулевые.
    const sumDiff = bt.rows.reduce((a, r) => a + r.diff, 0);
    assert.ok(Math.abs(sumDiff) < DRAFT.total_revenue * 0.01, `отклонения в сумме ${sumDiff}`);
    assert.equal(V.bartenders(MP), null, 'у фасовки барменов нет');
});

// ---------------------------------------------------------------- профиль баров
test('профиль баров: доли категорий в каждом баре складываются в 100%', () => {
    const sp = V.barProfile(MP);
    assert.ok(sp, 'в «Общей» с несколькими барами профиль должен считаться');
    sp.bars.forEach((bar, bi) => {
        const sum = sp.rows.concat(sp.extra).reduce((a, r) => a + r.cells[bi].share, 0);
        assert.ok(near(sum, 100, 1e-6), `у бара ${bar} доли дают ${sum}`);
    });
    const net = sp.rows.concat(sp.extra).reduce((a, r) => a + r.net, 0);
    assert.ok(near(net, 100, 1e-6), `доли сети дают ${net}`);
    assert.ok(near(sp.info.reduce((a, i) => a + i.share, 0), 100, 1e-6), 'доли баров в сети не 100%');
    assert.ok(sp.rows.length <= 10, 'в таблице больше 10 категорий');
    assert.ok(sp.rows.every((r) => !/^Без категории/.test(r.name)), '«Без категории» среди первых строк');
    // Разрез одного бара — профиля нет, как и у розлива.
    assert.equal(V.barProfile(V.fromPackaging(Object.assign({}, PACK, { scope: 'bar' }))), null);
    assert.equal(V.barProfile(MD), null);
});

// ---------------------------------------------------------------- вкладки
test('вкладки: у розлива бармены, у фасовки бары только в «Общей»', () => {
    const ids = (M) => V.tabsFor(M).map((t) => t.id);
    assert.deepEqual([...ids(MD)], ['overview', 'items', 'cats', 'prices', 'losses', 'people']);
    assert.deepEqual([...ids(MP)], ['overview', 'items', 'cats', 'prices', 'losses', 'bars']);
    const oneBar = V.fromPackaging(Object.assign({}, PACK, { scope: 'bar', bars_in_scope: ['Лиговский'] }));
    assert.ok(!ids(oneBar).includes('bars'), 'у одного бара вкладка «Бары» не нужна');
    const tabs = flat(V.tabsHtml(MD, 'overview'));
    assert.match(tabs, /data-tab="overview"[^>]*aria-selected="true"|aria-selected="true"[^>]*data-tab="overview"/,
        'активная вкладка не отмечена');
});

// ---------------------------------------------------------------- разметка
test('пояснения расчётов только в «Как считается»', () => {
    const blocks = { overview: V.overviewHtml(MD), prices: V.pricesHtml(MD, 12), people: V.peopleHtml(MD),
                     overviewPack: V.overviewHtml(MP), pricesPack: V.pricesHtml(MP, 12), bars: V.barsHtml(MP) };
    for (const [name, html] of Object.entries(blocks)) {
        assert.ok(/<details class="av-how/.test(html), `в блоке ${name} нет раскрывашки`);
        // Формула на экране — «X = Y»; такие строки должны жить в раскрывашке.
        const text = loose(html).replace(/<[^>]+>/g, ' ');
        assert.ok(!/\s=\s/.test(text), `в блоке ${name} формула висит открытой`);
    }
});

test('недобор по ценам — недополученные деньги: минус и красный, не «заработок»', () => {
    // Владелец: «+335 тыс» зелёным читалось как лишние деньги от низкой наценки.
    const ov = flat(V.overviewHtml(MD));
    assert.match(ov, /class="av-lg-ic neg"[\s\S]*Цены ниже минимума сети[\s\S]*class="av-neg">−75 128 ₽/);
    const pr = flat(loose(V.pricesHtml(MD, 12)));
    assert.match(pr, /Недополучено из-за цен ниже минимума сети 250%/);
    assert.match(pr, /class="av-big av-neg">−75 128 ₽/);
    assert.ok(!/av-pos/.test(pr), 'в «Ценах» осталась зелёная сумма');
    assert.ok(!/\+\d[\d ]* ₽/.test(pr.replace(/<[^>]+>/g, ' ')), 'в «Ценах» осталась сумма со знаком плюс');
    const tab = flat(V.tabsHtml(MD, 'overview'));
    assert.match(tab, /data-tab="prices"[^>]*>Цены<span class="n neg">−75 тыс ₽/);
    const cats = flat(V.pricesHtml(MP, 12));
    assert.ok(!/av-pos/.test(cats), 'в недоборе по категориям осталась зелёная сумма');
});

test('кухня: пороги 180/150, недостача и потери сразу в рублях', () => {
    assert.equal(MK.key, 'kitchen');
    assert.equal(MK.aMin, +thresholds.match(/KITCHEN_MARKUP_A_MIN = ([\d.]+)/)[1]);
    assert.equal(MK.bMin, +thresholds.match(/KITCHEN_MARKUP_B_MIN = ([\d.]+)/)[1]);
    const sh = V.shortage(MK);
    // Сервер отдаёт недостачу в рублях: пересчитывать через закупку единицы нельзя.
    assert.equal(sh.cost, KITCHEN.losses.inventory_net);
    assert.ok(near(sh.price, KITCHEN.losses.inventory_net * KITCHEN.totals.revenue / KITCHEN.totals.cost));
    const lr = V.lossRubles(MK);
    assert.ok(near(lr.total, KITCHEN.losses.by_item.reduce((a, r) => a + r.LossRub, 0)));
    // Недобор — тот же расчёт, минимум кухни.
    const pg = V.priceGap(MK);
    const hand = priceGapByHand(KITCHEN.positions, 1.8, (p) => ({ bucket: p.ABC_Bucket, markup: p.MarkupPercent,
        cost: p.TotalCost, qty: p.TotalQty, sales: p.TotalQty, revenue: p.TotalRevenue }));
    assert.ok(near(pg.total, hand.total));
    assert.equal(pg.rows.length, hand.count);
    const ids = V.tabsFor(MK).map((t) => t.id);
    assert.deepEqual([...ids], ['overview', 'items', 'cats', 'prices', 'losses', 'bars']);
    const text = flat(V.overviewHtml(MK) + V.barsHtml(MK)).replace(/<[^>]+>/g, ' ');
    assert.ok(!/фасовк|бутыл/.test(text), 'в разметке кухни слова фасовки');
    assert.match(text, /Выручка с порции/);
});

test('бар без категории: «не берут», а не «в — раза реже»', () => {
    const html = flat(V.barsHtml(MK)).replace(/<[^>]+>/g, ' ');
    assert.ok(!/в — раза/.test(html), 'деление на ноль в подписи отличия');
});

test('одинаковый вход — одинаковая разметка', () => {
    assert.equal(V.overviewHtml(V.fromDraft(DRAFT)), V.overviewHtml(V.fromDraft(DRAFT)));
    assert.equal(V.pricesHtml(V.fromPackaging(PACK), 12), V.pricesHtml(V.fromPackaging(PACK), 12));
});

test('названия из данных экранируются', () => {
    const data = JSON.parse(JSON.stringify(PACK));
    const bad = `O'Hara's <img src=x onerror=alert(1)> "Stout"`;
    data.positions[0].Beer = bad;
    const M = V.fromPackaging(data);
    const html = V.overviewHtml(M) + V.pricesHtml(M, 500);
    assert.ok(!html.includes('<img'), 'имя позиции попало в разметку как тег');
    assert.ok(html.includes('O&#39;Hara&#39;s &lt;img'), 'имя позиции не выведено экранированным');
});

test('все классы av-, которые пишет модуль, описаны в abc_view.css', () => {
    const used = new Set();
    for (const m of src.matchAll(/["' ](av-[\w-]+)/g)) used.add(m[1]);
    // Классы цвета группы собираются как 'av-c-' + ключ группы.
    used.delete('av-c-');
    for (const k of V.BUCKET_ORDER) used.add('av-c-' + k);
    const missing = [...used].filter((c) => !css.includes(`.${c}`));
    assert.deepEqual(missing, [], `нет в CSS: ${missing.join(', ')}`);
});

test('цвета abc_view.css — только токены страниц, без своих HEX', () => {
    assert.ok(!/#[0-9A-Fa-f]{3,8}\b/.test(css), 'в abc_view.css свой HEX мимо токенов');
    assert.match(css, /body\.draft-page \{[\s\S]*?--av-[\w-]+: var\(--dr-/, 'нет привязки к токенам /draft');
    assert.match(css, /body\.packaging-page \{[\s\S]*?--av-[\w-]+: var\(--pk-/, 'нет привязки к токенам /packaging');
});

test('без эмодзи в модуле и стилях', () => {
    const emoji = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/u;
    assert.ok(!emoji.test(src), 'эмодзи в abc_view.js');
    assert.ok(!emoji.test(css), 'эмодзи в abc_view.css');
});

// ---------------------------------------------------------------- бар и период из полосы
// С 2026-11-01 у розлива, фасовки и кухни нет своих меню: бар и период — общая полоса сайта.

test('полные недели и подпись «XYZ не считается» — как сервер (дни // 7, нужно от 3)', () => {
    assert.match(thresholds, /MIN_XYZ_WEEKS = 3\b/, 'порог XYZ в ядре сменился');
    assert.equal(V.XYZ_MIN_WEEKS, 3);
    assert.equal(V.fullWeeks('2026-10-19', '2026-10-25'), 1);
    assert.equal(V.fullWeeks('2026-10-02', '2026-10-31'), 4);   // 30 дней — 4 полные недели
    assert.equal(V.fullWeeks('2026-10-11', '2026-10-31'), 3);   // 21 день
    assert.equal(V.fullWeeks('2026-10-12', '2026-10-31'), 2);   // 20 дней
    assert.equal(V.fullWeeks('2026-03-29', '2026-04-04'), 1, 'переход на летнее время ломает счёт дней');
    assert.equal(V.noXyzText('2026-10-11', '2026-10-31'), '', 'три полные недели — XYZ считается');
    assert.equal(V.noXyzText('2026-10-12', '2026-10-31'),
        'XYZ не считается: в периоде 2 полные недели, нужно от 3; ABC показан');
    assert.equal(V.noXyzText('2026-10-31', '2026-10-31'),
        'XYZ не считается: в периоде 0 полных недель, нужно от 3; ABC показан');
    assert.equal(V.noXyzText(null, null), '', 'без периода подписи нет');
});

test('вся сеть подписана «Все бары», даже если сервер зовёт её «Общая»', () => {
    assert.equal(V.barText(''), 'Все бары');
    assert.equal(V.barText('Общая'), 'Все бары');
    assert.equal(V.barText('Лиговский'), 'Лиговский');
});

test('ошибка запроса: iiko не успел — просьба сократить период, остальное — причина сервера', () => {
    const T = 'iiko не успел ответить — сократите период';
    assert.equal(V.TIMEOUT_TEXT, T);
    assert.equal(V.failText(502, { error: 'Не удалось получить данные из iiko API' }), T);
    assert.equal(V.failText(504, null), T, 'страница прокси без JSON');
    assert.equal(V.failText(503, null), T);
    assert.equal(V.failText(0, null), T, 'соединение оборвалось');
    assert.equal(V.failText(500, null), T, '500 без JSON — тоже прокси');
    assert.equal(V.failText(404, { error: 'Нет данных за выбранный период' }), 'Нет данных за выбранный период');
    assert.equal(V.failText(500, { error: 'KeyError: x' }), 'KeyError: x');
    assert.equal(V.failText(418, null), 'Ошибка сервера: HTTP 418');
});

test('строка расчёта называет, что, за какой период и по какому бару считается', () => {
    assert.equal(V.progressText('розлив', { title: '2 – 31 окт 2026', label: 'Все бары' }),
        'Считаю розлив за 2 – 31 окт 2026, Все бары…');
    assert.equal(V.progressText('кухню', {}), 'Считаю кухню…');
});

test('память ответов: тот же ключ — тот же ответ, не дольше 10 минут и не больше 8 ответов', () => {
    const m = V.memo();
    m.put('a', { n: 1 });
    assert.deepEqual(m.get('a'), { n: 1 });
    assert.equal(m.get('b'), null);
    for (let i = 0; i < 8; i++) m.put('k' + i, i);
    assert.equal(m.get('a'), null, 'девятый ответ не вытеснил самый старый');
    assert.equal(m.get('k7'), 7);
    // Часы песочницы — свой Date контекста vm, а не Date этого файла.
    const SandboxDate = vm.runInContext('Date', sandbox);
    const realNow = SandboxDate.now;
    try {
        const t0 = realNow();
        SandboxDate.now = () => t0 + 10 * 60 * 1000 + 1;
        assert.equal(m.get('k7'), null, 'ответ старше 10 минут отдан из памяти');
    } finally {
        SandboxDate.now = realNow;
    }
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
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

await asyncTest('связка с полосой: бар — имя iiko, серия выборов — один вызов после паузы', async () => {
    const listeners = [];
    const st = { bar: '', period: { start: '2026-10-02', end: '2026-10-31', granularity: 'custom' } };
    const strip = {
        get: () => ({ bar: st.bar, period: st.period }),
        onChange: (fn) => listeners.push(fn),
        barInfo: (key) => (key === 'bolshoy'
            ? { key: 'bolshoy', name: 'Большой пр. В.О', iiko_name: 'Большой пр. В.О', bar_id: 'bar1' } : null),
        config: { allLabel: 'Все бары' }
    };
    sandbox.setTimeout = setTimeout;
    sandbox.clearTimeout = clearTimeout;
    const seen = [];
    const link = V.connect((sel) => seen.push(sel), { strip, pause: 30 });
    const first = link.get();
    assert.equal(first.bar, '');
    assert.equal(first.label, 'Все бары');
    assert.deepEqual([first.from, first.to], ['2026-10-02', '2026-10-31']);
    st.bar = 'bolshoy';
    listeners.forEach((fn) => fn({ type: 'bar' }));
    st.period = { start: '2026-10-19', end: '2026-10-25', granularity: 'week' };
    listeners.forEach((fn) => fn({ type: 'period' }));
    assert.equal(seen.length, 0, 'вызов без паузы');
    await sleep(60);
    assert.equal(seen.length, 1, 'серия из двух выборов дала ' + seen.length + ' вызова');
    assert.equal(seen[0].bar, 'Большой пр. В.О', 'бар для запроса — не имя iiko');
    assert.equal(seen[0].barKey, 'bolshoy');
    assert.equal(seen[0].label, 'Большой пр. В.О');
    assert.deepEqual([seen[0].from, seen[0].to], ['2026-10-19', '2026-10-25']);
    assert.equal(V.connect(null, { strip: null }).get().bar, '', 'без полосы — вся сеть');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

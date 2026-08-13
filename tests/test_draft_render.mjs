/**
 * Тесты отрисовки страницы проливов (/draft) после перехода на проводки iiko.
 *
 *     node tests/test_draft_render.mjs
 *
 * Браузера в проверке нет, поэтому вытаскиваем <script> из шаблона, подсовываем
 * заглушки document/fetch и прогоняем настоящие функции отрисовки на реальном
 * ответе /api/draft-kegs. Ловим то, что иначе видно только глазами:
 *   1. синтаксическую поломку в шаблонных строках;
 *   2. класс, который JS пишет в разметку, но которого нет в CSS;
 *   3. возврат к JSON в onclick — именно там ломался клик на «Gravity It's Mango»;
 *   4. подпись «% от выручки», под которой раньше стояла накопленная доля ABC.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const template = fs.readFileSync(path.join(ROOT, 'templates/draft.html'), 'utf8');

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

// --- выделяем инлайновый скрипт и CSS страницы ---
const scriptBlocks = [...template.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
assert.equal(scriptBlocks.length, 1, 'ожидали один инлайновый <script> в шаблоне');
const pageScript = scriptBlocks[0];
const pageCss = [...template.matchAll(/<style>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n');

// --- окружение-заглушка ---
function makeElement() {
    const el = {
        innerHTML: '',
        textContent: '',
        value: '',
        className: '',
        children: [],
        classList: { add() {}, remove() {}, contains: () => false },
        appendChild(child) { this.children.push(child); },
        querySelector: () => makeElement(),
    };
    return el;
}

const created = [];
const sandbox = {
    console,
    Intl,
    Math,
    Number,
    Object,
    String,
    JSON,
    Date,
    document: {
        getElementById: () => makeElement(),
        createElement: () => { const el = makeElement(); created.push(el); return el; },
        addEventListener: () => {},
        body: { insertAdjacentHTML(_pos, html) { sandbox.__lastModal = html; } },
    },
    window: {},
    setInterval: () => {},
    fetch: () => Promise.reject(new Error('сеть в тесте не используется')),
    flatpickr: () => ({ selectedDates: [] }),
};
sandbox.window = sandbox;
vm.createContext(sandbox);

test('инлайновый JS страницы синтаксически корректен', () => {
    new vm.Script(pageScript, { filename: 'draft.html<script>' }).runInContext(sandbox);
});

// --- фикстура: реальный ответ /api/draft-kegs (Лиговский, неделя 04-10.08.2026) ---
const RESPONSE = {
    'Лиговский': {
        period: { from: '2026-08-04', to: '2026-08-10', days: 7, weeks: 1 },
        total_liters: 167.15,
        total_portions: 325,
        total_revenue: 169775,
        total_cost: 50156,
        total_margin: 119619,
        total_kegs: 2,
        avg_price_per_liter: 1015.7,
        avg_portion_liters: 0.5143,
        markup_percent: 238.47,
        xyz_buckets: 1,
        xyz_available: false,
        losses: {
            invoice_in: 90, transfer_in: 0, sold: 167.15, writeoff: 0.5,
            inventory_out: 0, inventory_in: 0, inventory_net: 0, transfer_out: 0,
            balance: -77.65, writeoff_percent_of_sold: 0.2991,
            inventory_percent_of_sold: 0,
            by_keg: [{ KegName: 'КЕГ ФестХаус Хеллес', WriteoffLiters: 0.5,
                       InventoryNetLiters: 0, SoldLiters: 56.2 }],
        },
        unmapped_dishes: [],
        kegs: [
            {
                KegId: 'k1', KegName: 'КЕГ ФестХаус Хеллес', Bar: 'Лиговский',
                TotalLiters: 56.2, TotalPortions: 104, TotalRevenue: 47142,
                TotalCost: 10678, TotalMargin: 36464, MarkupPercent: 341.49,
                PricePerLiter: 838.83, AvgPortionLiters: 0.54, AvgLitersPerWeek: 56.2,
                WeeksWithSales: 1, WeeksInPeriod: 1, WriteoffLiters: 0.5,
                InventoryNetLiters: 0, LitersSharePercent: 33.62,
                RevenueSharePercent: 27.77, RevenueCumulativePercent: 27.77,
                ABC_Revenue: 'A', ABC_Markup: 'A', ABC_Margin: 'A', ABC_Combined: 'AAA',
                XYZ_Category: null, CoefficientOfVariation: null,
            },
            {
                // Апостроф в названии: именно на нём ломался старый обработчик клика
                KegId: 'k2', KegName: "КЕГ Gravity It's Mango <20 л>", Bar: 'Лиговский',
                TotalLiters: 11.05, TotalPortions: 22.33, TotalRevenue: 14653,
                TotalCost: 4641, TotalMargin: 10012, MarkupPercent: null,
                PricePerLiter: 1326, AvgPortionLiters: 0.49, AvgLitersPerWeek: 11.05,
                WeeksWithSales: 1, WeeksInPeriod: 1, WriteoffLiters: 0,
                InventoryNetLiters: -1.5, LitersSharePercent: 6.61,
                RevenueSharePercent: 8.63, RevenueCumulativePercent: 100,
                ABC_Revenue: 'C', ABC_Markup: 'C', ABC_Margin: 'B', ABC_Combined: 'CCB',
                XYZ_Category: 'X', CoefficientOfVariation: 12.5,
            },
        ],
    },
};

let markup = '';

test('displayResults рисует разметку без исключений', () => {
    created.length = 0;
    sandbox.displayResults(RESPONSE);
    assert.ok(created.length >= 1, 'секция бара не создана');
    markup = created.map((el) => el.innerHTML + el.children.map((c) => c.innerHTML).join('')).join('');
    assert.ok(markup.length > 500, `разметка подозрительно короткая: ${markup.length}`);
});

test('литры взяты из ответа и подписаны как расход кегов', () => {
    assert.match(markup, /167,15/, 'нет общего объёма 167,15');
    assert.match(markup, /расход кегов со склада/i, 'нет пояснения источника литров');
});

test('дробные порции не обрезаются до целого', () => {
    assert.match(markup, /22,33/, 'порции 22,33 округлились');
});

test('наценка выводится как процент и допускает прочерк', () => {
    assert.match(markup, /238,5%|238,47%/, 'нет наценки по разрезу');
    assert.match(markup, /class="dash"/, 'нет прочерка для неизвестной наценки');
});

test('в onclick передаётся индекс, а не JSON', () => {
    assert.match(markup, /onclick="showKegDetails\(\d+\)"/, 'клик по строке не по индексу');
    assert.ok(!/onclick='showKegDetails\(\{/.test(markup), 'JSON вернулся в атрибут onclick');
});

test('название с апострофом и угловыми скобками экранировано', () => {
    assert.match(markup, /It&#39;s Mango &lt;20 л&gt;/, 'название не экранировано');
    assert.ok(!markup.includes("It's Mango <20"), 'сырое название попало в разметку');
});

test('блок баланса кегов на месте со всеми строками', () => {
    for (const label of ['Приход по накладным', 'Продано через кассу', 'Списано актами',
                         'Недостача по инвентаризациям', 'Изменение остатка кегов']) {
        assert.ok(markup.includes(label), `нет строки баланса: ${label}`);
    }
    assert.match(markup, /−77,65|-77,65/, 'нет значения изменения остатка');
});

test('XYZ показывает прочерк с причиной, когда период короткий', () => {
    assert.match(markup, /XYZ не рассчитан/, 'нет пояснения про нерассчитанный XYZ');
    assert.match(markup, /меньше 3 полных недель|нужно минимум 3/, 'нет причины');
});

test('карточка позиции: доля в выручке своя, а накопленная подписана отдельно', () => {
    sandbox.showKegDetails(0);
    const modal = sandbox.__lastModal || '';
    assert.ok(modal.includes('27,8% от выручки') || modal.includes('27,77% от выручки'),
        'своя доля в выручке не выведена');
    assert.match(modal, /накопленным итогом/, 'накопленный процент не подписан как накопленный');
    assert.ok(!/100,0% от выручки/.test(modal), 'накопленная доля снова выводится как своя');
});

test('карточка позиции объясняет формулы наценки и CV', () => {
    sandbox.showKegDetails(0);
    const modal = sandbox.__lastModal || '';
    assert.match(modal, /\(выручка - себестоимость\) \/ себестоимость/, 'нет формулы наценки');
    assert.match(modal, /стандартное отклонение недельных литров/i, 'нет формулы CV');
    assert.match(modal, /На кране/, 'не показано, сколько недель позиция была на кране');
});

test('все классы из JS описаны в CSS', () => {
    sandbox.showKegDetails(1);
    const all = markup + (sandbox.__lastModal || '');
    const used = new Set();
    for (const m of all.matchAll(/class="([^"]+)"/g)) {
        for (const cls of m[1].trim().split(/\s+/)) {
            if (cls) used.add(cls);
        }
    }
    const known = new Set([...pageCss.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
    // Классы из общих стилей дашборда и шаблона навигации в этот CSS не входят.
    const external = new Set(['container', 'bar-section', 'bar-header', 'stats-grid',
        'stat-card', 'label', 'value', 'unit', 'section-title', 'card', 'badge',
        'modal', 'modal-content', 'modal-header', 'modal-close', 'detail-grid',
        'detail-item', 'beer-row', 'v', 'pct', 'total', 'hint', 'dash',
        'balance-grid', 'controls', 'form-group', 'btn', 'loading', 'spinner',
        'results', 'error', 'api-status', 'api-status-text']);
    const unknown = [...used].filter((c) => !known.has(c) && !external.has(c)
        && !c.startsWith('abc-') && !c.startsWith('xyz-'));
    assert.deepEqual(unknown, [], `классы без стилей: ${unknown.join(', ')}`);
});

test('страница запрашивает новый эндпоинт проливов', () => {
    assert.match(pageScript, /fetch\('\/api\/draft-kegs'/, 'страница не переключена на /api/draft-kegs');
    assert.ok(!/\/api\/draft-analyze/.test(pageScript), 'остался вызов старого эндпоинта');
});

test('ошибка от сервера показывается пользователю', () => {
    assert.match(pageScript, /data\.error/, 'текст ошибки от сервера не используется');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

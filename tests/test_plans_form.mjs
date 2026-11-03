/**
 * Тесты формы планов (2026-09-05): план «Доля чеков с картой» (cardChecksShare).
 *
 *     node tests/test_plans_form.mjs
 *
 * Браузера в проверке нет, поэтому ловим текстом самую вероятную поломку:
 * форма планов перечисляет свои поля в шести местах (шаблон, formFields,
 * дефолты нового плана, обязательные поля, подписи, секция таблицы), и
 * забытое место даёт поле, которое видно, но не сохраняется — или сохраняется,
 * но не показывается. Плюс дефолт 70% обязан совпадать с бэкендом
 * (core/plans_manager.py PlansManager.PLAN_DEFAULTS), иначе новый план и
 * старый месяц покажут разные цифры.
 *
 * config.js сюда не импортируем: метрика описана там, но форма планов
 * перечисляет поля сама — проверяем именно её списки.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

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

const JS = read('static/js/dashboard/modules/plans.js');
const HTML = read('templates/dashboard/plans_tab.html');

/** Значение константы `const NAME = <число>;` в тексте JS. */
function jsConst(name) {
    const m = JS.match(new RegExp(`const ${name} = (\\d+(?:\\.\\d+)?);`));
    assert.ok(m, `в plans.js нет константы ${name}`);
    return Number(m[1]);
}

/** Тело первого блока `<prefix> [ ... ]` или `<prefix> { ... }` (без вложенных скобок того же типа). */
function body(prefix, open, close) {
    const start = JS.indexOf(prefix);
    assert.ok(start >= 0, `в plans.js нет «${prefix}»`);
    const from = JS.indexOf(open, start);
    const to = JS.indexOf(close, from);
    assert.ok(from > 0 && to > from, `не нашли ${open}...${close} после «${prefix}»`);
    return JS.slice(from + 1, to);
}

/** Список строковых литералов внутри тела блока. */
const ids = (text) => (text.match(/'([^']+)'/g) || []).map(s => s.slice(1, -1));

console.log('\n--- константа дефолта ---');

test('CARD_CHECKS_SHARE_DEFAULT = 70 и стоит рядом с LOYALTY_WRITEOFF_RATE', () => {
    assert.equal(jsConst('CARD_CHECKS_SHARE_DEFAULT'), 70);
    const rate = JS.indexOf('const LOYALTY_WRITEOFF_RATE');
    const share = JS.indexOf('const CARD_CHECKS_SHARE_DEFAULT');
    assert.ok(rate > 0 && share > rate, 'константа не рядом с LOYALTY_WRITEOFF_RATE');
    // Комментарий обязан ссылаться на зеркало в Python — иначе одно из двух мест забудут.
    assert.ok(JS.slice(rate, share).includes('PlansManager.PLAN_DEFAULTS'), 'нет ссылки на PLAN_DEFAULTS');
});

test('дефолт совпадает с core/plans_manager.py PLAN_DEFAULTS', () => {
    const py = read('core/plans_manager.py');
    const m = py.match(/'cardChecksShare':\s*(\d+(?:\.\d+)?)/);
    assert.ok(m, "в plans_manager.py нет 'cardChecksShare': <число> (PLAN_DEFAULTS)");
    assert.equal(Number(m[1]), jsConst('CARD_CHECKS_SHARE_DEFAULT'));
});

console.log('\n--- шаблон формы ---');

test('input#plan-cardChecksShare: number, value=70, min=0, max=100', () => {
    const m = HTML.match(/<input[^>]*id="plan-cardChecksShare"[^>]*>/);
    assert.ok(m, 'в plans_tab.html нет input#plan-cardChecksShare');
    const tag = m[0];
    for (const attr of ['type="number"', 'value="70"', 'min="0"', 'max="100"', 'class="form-input"']) {
        assert.ok(tag.includes(attr), `у поля нет ${attr}`);
    }
    // Значение в разметке — то же, что константа в JS (форма до первого fillPlanForm).
    assert.equal(Number(tag.match(/value="([^"]+)"/)[1]), jsConst('CARD_CHECKS_SHARE_DEFAULT'));
    assert.ok(!tag.includes('readonly'), 'поле должно редактироваться');
});

test('поле подписано и стоит в секции «Прочее» между списаниями и кранами', () => {
    assert.ok(HTML.includes('<label>Доля чеков с картой (%)</label>'), 'нет подписи поля');
    const section = HTML.indexOf('<h4>Прочее</h4>');
    const writeoffs = HTML.indexOf('id="plan-loyaltyWriteoffs"');
    const share = HTML.indexOf('id="plan-cardChecksShare"');
    const taps = HTML.indexOf('id="plan-tapActivity"');
    assert.ok(section > 0 && writeoffs > section && share > writeoffs && taps > share,
        'порядок полей в «Прочее» не loyaltyWriteoffs, cardChecksShare, tapActivity');
    // Сетка секции auto-fit: третье поле встаёт в ряд без правок CSS.
    assert.ok(/\.form-grid\s*\{[^}]*repeat\(auto-fit/.test(HTML), '.form-grid не auto-fit — третье поле сломает ряд');
});

console.log('\n--- plans.js: все места, где форма перечисляет поля ---');

test('formFields читает #plan-cardChecksShare', () => {
    const fields = body('this.formFields = {', '{', '}');
    assert.ok(fields.includes("cardChecksShare: document.getElementById('plan-cardChecksShare')"), 'нет в formFields');
});

test('дефолты нового плана: cardChecksShare = CARD_CHECKS_SHARE_DEFAULT', () => {
    const start = JS.indexOf('createEmptyPlan() {');
    assert.ok(start > 0, 'нет createEmptyPlan');
    const from = JS.indexOf('return {', start);
    const defaults = JS.slice(from, JS.indexOf('};', from));
    assert.ok(defaults.includes('cardChecksShare: CARD_CHECKS_SHARE_DEFAULT'), 'дефолт не через константу');
});

test('requiredFields содержит cardChecksShare', () => {
    assert.ok(ids(body('const requiredFields = [', '[', ']')).includes('cardChecksShare'));
});

test('подпись поля для сообщений валидации', () => {
    const labels = body('const labels = {', '{', '}');
    assert.ok(labels.includes("cardChecksShare: 'Доля чеков с картой'"), 'нет подписи в getFieldLabel');
});

test('секция таблицы «Прочее»: loyaltyWriteoffs, cardChecksShare, tapActivity', () => {
    const m = JS.match(/name: 'Прочее',\s*metrics: \[([^\]]+)\]/);
    assert.ok(m, 'нет секции «Прочее»');
    assert.deepEqual(ids(m[1]), ['loyaltyWriteoffs', 'cardChecksShare', 'tapActivity']);
});

console.log('\n--- старые планы без поля ---');

test('таблица показывает дефолт, если в плане нет cardChecksShare (проверка на null, не на 0)', () => {
    const start = JS.indexOf('displayData(plan) {');
    const end = JS.indexOf('createMetricRow(metric, planValue) {', start);
    const fn = JS.slice(start, end);
    assert.ok(fn.includes("metric.id === 'cardChecksShare'"), 'displayData не знает cardChecksShare');
    assert.ok(fn.includes('planValue = CARD_CHECKS_SHARE_DEFAULT'), 'дефолт не через константу');
    assert.ok(/cardChecksShare' && plan\s*&& \(planValue === null \|\| planValue === undefined\)/.test(fn),
        'ожидалась проверка null/undefined — 0% допустимое значение');
});

test('заполнение формы — один helper, отсутствующее поле получает дефолт', () => {
    assert.equal(JS.split('applyPlanToForm(planData) {').length - 1, 1, 'helper объявлен не один раз');
    assert.equal(JS.split('this.applyPlanToForm(planData)').length - 1, 2, 'fillPlanForm и openModal должны звать helper');
    assert.equal(JS.split('for (const [key, value] of Object.entries(planData))').length - 1, 1,
        'цикл заполнения формы продублирован');
    assert.ok(JS.includes('this.formFields.cardChecksShare.value = CARD_CHECKS_SHARE_DEFAULT.toFixed(2)'),
        'старый план оставит в поле цифру от прошлого открытого плана');
});

test('клиентская валидация: потолок 100% с понятным сообщением', () => {
    assert.ok(JS.includes('Доля чеков с картой должна быть от 0 до 100%'), 'нет сообщения о диапазоне');
    assert.ok(/cardChecksShare > 100\)/.test(JS), 'нет проверки > 100');
});

console.log('\n--- стиль ---');

test('в plans.js и plans_tab.html нет эмодзи', () => {
    // .claude/CLAUDE.md: эмодзи запрещены в коде и интерфейсе.
    const emoji = /[\u{1F300}-\u{1FAFF}\u{2705}\u{274C}\u{26A0}\u{2B50}\u{1F4C5}]/u;
    for (const [name, text] of [['plans.js', JS], ['plans_tab.html', HTML]]) {
        const hit = text.match(emoji);
        assert.equal(hit, null, `${name}: найдено ${hit && hit[0]}`);
    }
});

console.log('\n--- годы и значения по умолчанию (с 2026-11-01) ---');

test('в шаблоне нет зашитых годов: список строит plans.js', () => {
    const m = HTML.match(/<select id="plan-year-select"[^>]*>([\s\S]*?)<\/select>/);
    assert.ok(m, 'нет select#plan-year-select');
    assert.ok(!/<option/.test(m[1]), 'в списке годов остались зашитые option');
    assert.ok(!/2025|2026|2027/.test(m[1]));
});

test('форма плана не берёт месяц и год с часов устройства', () => {
    const start = JS.indexOf('openCreateModal() {');
    const fn = JS.slice(start, JS.indexOf('\n    }\n', start));
    assert.ok(!/new Date\(/.test(fn), 'openCreateModal читает часы устройства');
    assert.ok(fn.includes('planFormDefaults(state'), 'значения по умолчанию не из общего периода');
});

// Модуль целиком: настоящее ядро периодов (часы страницы — 01.11.2026) и пустой DOM.
const { createRequire } = await import('node:module');
const { pathToFileURL } = await import('node:url');
const requireCjs = createRequire(import.meta.url);
globalThis.window = globalThis;
requireCjs(path.join(ROOT, 'static/js/shared/period/period_core.js'));
globalThis.KPeriod.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });
globalThis.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] };
const plansMod = await import(pathToFileURL(path.join(ROOT, 'static/js/dashboard/modules/plans.js')).href);
const { state } = await import(pathToFileURL(path.join(ROOT, 'static/js/dashboard/core/state.js')).href);

test('годы: текущий −1…+1, плюс год периода и годы заведённых планов', () => {
    assert.deepEqual(plansMod.planYears(2026, []), [2025, 2026, 2027]);
    assert.deepEqual(plansMod.planYears(2026, [2024, '2031', 'x', 1999, 2026]), [2024, 2025, 2026, 2027, 2031]);
    assert.deepEqual(plansMod.planYears(2027, null), [2026, 2027, 2028], 'с 2027 года список сдвигается сам');
});

test('по умолчанию — месяц общего периода и общий бар; «Все бары» — первый бар списка', () => {
    const keys = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'];
    assert.deepEqual({ ...plansMod.planFormDefaults({ currentMonth: '10', currentYear: 2026, currentVenue: 'all' }, keys) },
        { month: '10', year: '2026', venue: 'bolshoy' });
    assert.equal(plansMod.planFormDefaults({ currentMonth: '03', currentYear: 2027, currentVenue: 'ligovskiy' }, keys).venue,
        'ligovskiy');
    assert.equal(plansMod.planFormDefaults({ currentMonth: '12', currentYear: 2024, currentVenue: '' }, keys).year, '2024');
});

test('список годов формы держит год общего периода, даже вне текущего −1…+1', () => {
    const select = { innerHTML: '', value: '' };
    plansMod.plansViewer.planYearSelect = select;
    const keep = state.currentYear;
    try {
        state.currentYear = 2023;
        plansMod.plansViewer.knownPlanYears = [2028];
        plansMod.plansViewer.fillYearSelect('2023');
        const years = [...select.innerHTML.matchAll(/value="(\d{4})"/g)].map((m) => Number(m[1]));
        assert.deepEqual(years, [2023, 2025, 2026, 2027, 2028]);
        assert.equal(select.value, '2023');
    } finally {
        state.currentYear = keep;
        plansMod.plansViewer.knownPlanYears = [];
        plansMod.plansViewer.planYearSelect = null;
    }
});

console.log('\n--- крепкий алкоголь (2026-11-03) ---');

const STRONG = ['strongShare', 'revenueStrong', 'markupStrong'];

test('шаблон: доля крепкого — вводимая доля между фасовкой и кухней, выручка — авто, наценка вводится', () => {
    const tag = (id) => {
        const m = HTML.match(new RegExp(`<input[^>]*id="plan-${id}"[^>]*>`));
        assert.ok(m, `нет input#plan-${id}`);
        return m[0];
    };
    const share = tag('strongShare');
    for (const attr of ['type="number"', 'share-input', 'min="0"', 'max="100"', 'value="0"']) {
        assert.ok(share.includes(attr), `у доли крепкого нет ${attr}`);
    }
    assert.ok(!share.includes('readonly'), 'долю крепкого вводят руками');
    assert.ok(tag('revenueStrong').includes('readonly'), 'выручка крепкого — авто-расчёт');
    const markup = tag('markupStrong');
    assert.ok(!markup.includes('readonly') && markup.includes('min="0"'), 'наценку крепкого вводят руками');
    const at = (id) => HTML.indexOf(`id="plan-${id}"`);
    assert.ok(at('packagedShare') < at('strongShare') && at('strongShare') < at('kitchenShare'),
        'доля крепкого не между фасовкой и кухней (авто)');
    assert.ok(tag('kitchenShare').includes('title="100 - розлив - фасовка - крепкий алкоголь"'),
        'подсказка кухни не говорит, что крепкий вычитается');
    assert.ok(at('revenueKitchen') < at('revenueStrong') && at('markupKitchen') < at('markupStrong'));
    assert.equal(HTML.split('<label>Крепкий алкоголь (%)</label>').length - 1, 2, 'подписи доли и наценки');
    // Четыре поля долей в ряд: подпись суммы — на всю строку, а не пятой узкой колонкой.
    assert.ok(/<div class="form-group form-group-wide">\s*<label id="shares-sum-label"/.test(HTML),
        'подпись суммы долей не на всю строку');
    assert.ok(/\.form-group-wide\s*\{[^}]*grid-column: 1 \/ -1/.test(HTML), 'нет правила .form-group-wide');
});

test('plans.js перечисляет поля крепкого во всех местах формы', () => {
    const fields = body('this.formFields = {', '{', '}');
    for (const id of STRONG) {
        assert.ok(fields.includes(`${id}: document.getElementById('plan-${id}')`), `${id}: нет в formFields`);
        assert.ok(ids(body('const requiredFields = [', '[', ']')).includes(id), `${id}: нет в requiredFields`);
        assert.ok(body('const labels = {', '{', '}').includes(`${id}: '`), `${id}: нет подписи`);
    }
    assert.deepEqual(ids(body('const STRONG_PLAN_FIELDS = [', '[', ']')), STRONG);
    const start = JS.indexOf('createEmptyPlan() {');
    const defaults = JS.slice(JS.indexOf('return {', start), JS.indexOf('};', start));
    for (const id of STRONG) assert.ok(defaults.includes(`${id}: 0`), `${id}: новый план не с 0`);
    // Таблица плана: доля, выручка и наценка — в своих секциях.
    const section = (name) => ids(JS.match(new RegExp(`name: '${name}',\\s*metrics: \\[([^\\]]+)\\]`))[1]);
    assert.deepEqual(section('Доли категорий'), ['draftShare', 'packagedShare', 'kitchenShare', 'strongShare']);
    assert.deepEqual(section('Выручка по категориям'), ['revenueDraft', 'revenuePackaged', 'revenueKitchen', 'revenueStrong']);
    assert.ok(section('Наценка и прибыль').includes('markupStrong'));
});

test('бэкенд-зеркало: PLAN_DEFAULTS даёт крепкому 0, сумма долей включает strongShare', () => {
    const py = read('core/plans_manager.py');
    for (const id of STRONG) {
        assert.ok(new RegExp(`'${id}':\\s*0\\.0`).test(py), `в PLAN_DEFAULTS нет '${id}': 0.0`);
    }
    assert.ok(py.includes("SHARE_FIELDS = ('draftShare', 'packagedShare', 'kitchenShare', 'strongShare')"),
        'проверка суммы долей на бэкенде без крепкого');
});

/** Поле формы для поведенческих проверок: только value. */
const input = (value) => ({ value: String(value), addEventListener() {} });

function withForm(values, fn) {
    const viewer = plansMod.plansViewer;
    const keep = { fields: viewer.formFields, label: viewer.sharesSumLabel };
    const label = { textContent: '', classes: new Set() };
    label.classList = { add: (c) => label.classes.add(c), remove: (c) => label.classes.delete(c) };
    viewer.formFields = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, input(v)]));
    viewer.sharesSumLabel = label;
    try {
        fn(viewer, label);
    } finally {
        viewer.formFields = keep.fields;
        viewer.sharesSumLabel = keep.label;
    }
}

const BASE_FORM = {
    revenue: 1000000, averageCheck: 2000, checks: 0, profit: 0,
    draftShare: 50, packagedShare: 25, kitchenShare: 0, strongShare: 3,
    revenueDraft: 0, revenuePackaged: 0, revenueKitchen: 0, revenueStrong: 0,
    markupPercent: 0, markupDraft: 250, markupPackaged: 120, markupKitchen: 160, markupStrong: 300,
    loyaltyWriteoffs: 0, cardChecksShare: 70, tapActivity: 100
};

test('кухня = 100 − розлив − фасовка − крепкий; выручка и себестоимость крепкого в прибыли', () => {
    withForm(BASE_FORM, (viewer, label) => {
        viewer.updateSharesSum();
        assert.equal(viewer.formFields.kitchenShare.value, '22.00');
        assert.ok(label.textContent.includes('Розлив + фасовка + крепкий: 78.0%'), label.textContent);
        viewer.autoCalculateDerivedMetrics();
        assert.equal(viewer.formFields.revenueStrong.value, '30000.00');
        // Себестоимость = выручка / (1 + наценка/100) по четырём категориям.
        const cost = 500000 / 3.5 + 250000 / 2.2 + 220000 / 2.6 + 30000 / 4;
        assert.equal(viewer.formFields.profit.value, (1000000 - cost).toFixed(2));
        assert.equal(viewer.formFields.markupPercent.value, (100 * 1000000 / cost - 100).toFixed(2));
    });
    // Без крепкого — расчёт и подпись прежние.
    withForm({ ...BASE_FORM, strongShare: 0 }, (viewer, label) => {
        viewer.updateSharesSum();
        assert.equal(viewer.formFields.kitchenShare.value, '25.00');
        assert.ok(label.textContent.startsWith('Розлив + фасовка: 75.0%'), label.textContent);
        viewer.autoCalculateDerivedMetrics();
        assert.equal(viewer.formFields.revenueStrong.value, '0.00');
    });
    // Доли больше 100 — подпись красная.
    withForm({ ...BASE_FORM, draftShare: 80, strongShare: 25 }, (viewer, label) => {
        viewer.updateSharesSum();
        assert.ok(label.classes.has('error'));
        assert.equal(viewer.formFields.kitchenShare.value, '0.00');
    });
});

test('валидация: сумма долей с крепким, доля крепкого требует его наценки', () => {
    const viewer = plansMod.plansViewer;
    const plan = { ...BASE_FORM, kitchenShare: 22, revenueStrong: 30000 };
    assert.deepEqual(viewer.validatePlanData(plan), { valid: true });
    const tooMuch = viewer.validatePlanData({ ...plan, kitchenShare: 25 });
    assert.equal(tooMuch.valid, false);
    assert.ok(tooMuch.message.includes('103.0%'), tooMuch.message);
    const noMarkup = viewer.validatePlanData({ ...plan, markupStrong: 0 });
    assert.equal(noMarkup.valid, false);
    assert.ok(noMarkup.message.includes('наценку крепкого алкоголя'), noMarkup.message);
    // Бар без крепкого: доля 0, наценка 0 — план валиден, как до 2026-11-03.
    assert.deepEqual(viewer.validatePlanData({ ...plan, strongShare: 0, revenueStrong: 0, markupStrong: 0,
        kitchenShare: 25 }), { valid: true });
});

test('план без полей крепкого не наследует цифры прошлого открытого плана', () => {
    withForm(BASE_FORM, (viewer) => {
        const old = { ...BASE_FORM };
        for (const id of STRONG) delete old[id];
        viewer.applyPlanToForm(old);
        for (const id of STRONG) assert.equal(viewer.formFields[id].value, '0.00', id);
    });
});

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed === 0 ? 0 : 1);

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

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed === 0 ? 0 : 1);

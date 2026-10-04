/**
 * Тесты JS-порта разбора кода со сканера приёмки РЦ (static/js/receiving/codes.js).
 *
 *     node tests/test_receiving_codes.mjs
 *
 * Та же фикстура, что у tests/test_receiving_codes.py
 * (tests/fixtures/receiving_codes.json): каждый случай обязан дать ровно тот же
 * словарь {ok, kind, gtin, serial, key, code, reason, message}, что и Python, —
 * сигнал приёмщику в браузере не должен расходиться с ответом сервера.
 *
 * Файл грузится двумя путями, как в жизни: в браузере (vm-контекст с window,
 * объект window.RcCodes) и в Node через require (module.exports). Без DOM и сети.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const JS_PATH = path.join(ROOT, 'static/js/receiving/codes.js');
const SRC = fs.readFileSync(JS_PATH, 'utf8');
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests/fixtures/receiving_codes.json'), 'utf8'));
const RESULT_KEYS = ['ok', 'kind', 'gtin', 'serial', 'key', 'code', 'reason', 'message'];

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

/** Загрузить файл как обычный <script> в браузере: глобальный window = сам контекст. */
function loadInBrowser() {
    const sandbox = {};
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(SRC, sandbox, { filename: JS_PATH });
    return sandbox;
}

/** Объекты из vm-контекста — другого «мира» (свой Object.prototype): сравниваем через JSON. */
const plain = (v) => JSON.parse(JSON.stringify(v));

const browser = loadInBrowser();
const RcCodes = browser.RcCodes;
const require = createRequire(import.meta.url);
const RcCodesNode = require(JS_PATH);

function expected(c) {
    const out = {};
    RESULT_KEYS.forEach((k) => { out[k] = c[k]; });
    return out;
}

console.log('\n--- загрузка ---');

test('в браузере файл кладёт window.RcCodes и не трогает module', () => {
    assert.equal(typeof RcCodes, 'object');
    assert.equal(typeof RcCodes.parseCode, 'function');
    assert.equal(typeof RcCodes.gtinCheckOk, 'function');
    assert.equal(typeof RcCodes.barcodeForIiko, 'function');
    assert.equal(browser.module, undefined);
});

test('без window берётся this (глобальный объект скрипта)', () => {
    const sandbox = {};
    vm.createContext(sandbox);
    vm.runInContext(SRC, sandbox, { filename: JS_PATH });
    assert.equal(typeof sandbox.RcCodes.parseCode, 'function');
});

test('в Node require отдаёт тот же API через module.exports', () => {
    assert.equal(typeof RcCodesNode.parseCode, 'function');
    assert.equal(RcCodesNode.MAX_CODE_LEN, 512);
    assert.equal(RcCodesNode.KEY_LEN, 200);
    assert.equal(RcCodesNode.GS, '\x1d');
});

console.log('\n--- общая фикстура (паритет с Python) ---');

test(`фикстура: не меньше 25 случаев (сейчас ${CASES.length})`, () => {
    assert.ok(CASES.length >= 25);
});

for (const c of CASES) {
    test(`фикстура: ${c.name}`, () => {
        const got = plain(RcCodes.parseCode(c.raw));
        assert.deepEqual(got, expected(c));
        assert.deepEqual(Object.keys(got), RESULT_KEYS);
        assert.deepEqual(RcCodesNode.parseCode(c.raw), expected(c));
        if (c.ok) {
            assert.equal(RcCodes.gtinCheckOk(c.gtin), true);
            assert.equal(RcCodes.barcodeForIiko(c.gtin), c.barcode);
        }
    });
}

test('повторный разбор нормализованного code даёт тот же ключ', () => {
    for (const c of CASES) {
        if (!c.ok) continue;
        const again = RcCodes.parseCode(c.code);
        assert.equal(again.ok, true, c.name);
        for (const k of ['kind', 'gtin', 'serial', 'key', 'code']) assert.equal(again[k], c[k], `${c.name}: ${k}`);
    }
});

console.log('\n--- контрольная цифра и штрихкод для iiko ---');

test('gtinCheckOk: верные и неверные', () => {
    const g = RcCodes.gtinCheckOk;
    assert.equal(g('04610093628430'), true);
    assert.equal(g('14610093628437'), true);
    assert.equal(g('00000046009999'), true);
    assert.equal(g('00036000291452'), true);
    assert.equal(g('04610093628431'), false);
    assert.equal(g('4610093628430'), false);       // 13 цифр
    assert.equal(g('046100936284300'), false);     // 15 цифр
    assert.equal(g('0461009362843A'), false);
    assert.equal(g(' 04610093628430'), false);
    assert.equal(g(''), false);
    assert.equal(g(null), false);
    assert.equal(g(undefined), false);
    assert.equal(g(4610093628430), false);         // не строка
});

test('gtinCheckOk: любая ошибка в одной цифре ловится', () => {
    const base = '04610093628430';
    for (let pos = 0; pos < 14; pos++) {
        for (const d of '0123456789') {
            if (d === base[pos]) continue;
            assert.equal(RcCodes.gtinCheckOk(base.slice(0, pos) + d + base.slice(pos + 1)), false, `${pos}:${d}`);
        }
    }
});

test('barcodeForIiko: EAN-8 / EAN-13 / GTIN-14 и мусор как есть', () => {
    const b = RcCodes.barcodeForIiko;
    assert.equal(b('04610093628430'), '4610093628430');
    assert.equal(b('00000046009999'), '46009999');
    assert.equal(b('00036000291452'), '0036000291452');
    assert.equal(b('14610093628437'), '14610093628437');
    assert.equal(b('4610093628430'), '4610093628430');
    assert.equal(b(' 04610093628430\n'), '4610093628430');
    assert.equal(b(4610093628430), '4610093628430');
    assert.equal(b(''), '');
    assert.equal(b(null), '');
    assert.equal(b(undefined), '');
    assert.equal(b('ABC'), 'ABC');
    assert.equal(b('046100936284301'), '046100936284301');
});

console.log('\n--- правила ---');

test('тексты для приёмщика', () => {
    const p = RcCodes.parseCode;
    assert.equal(p('4610093628430').message, 'Принято');
    assert.equal(p('').message, 'Код не распознан — повторите');
    assert.equal(p('https://x').message, 'Код не распознан — повторите');
    assert.equal(p('4610093628431').message, 'Код прочитан с ошибкой — повторите');
    assert.equal(p('00146012340000000018').message, 'Код короба или паллеты — отсканируйте бутылку');
});

test('одна бутылка — один ключ при любом виде скана', () => {
    const raws = [
        '010461009362843021GLTP9kqZn5QRt\x1d93dGVz',
        '010461009362843021GLTP9kqZn5QRt93dGVz',
        ']d2010461009362843021GLTP9kqZn5QRt\u241d93dGVz',
        '010461009362843021ПДЕЗ9лйЯт5ЙКе\x1d93вПМя',
        '(01)04610093628430(21)GLTP9kqZn5QRt(93)dGVz',
    ];
    const keys = new Set(raws.map((r) => RcCodes.parseCode(r).key));
    assert.deepEqual([...keys], ['04610093628430|GLTP9kqZn5QRt']);
});

test('граница MAX_CODE_LEN — в кодовых точках, а не в UTF-16', () => {
    const astral = '\u{1D400}';
    const r512 = RcCodes.parseCode(astral.repeat(512));
    assert.equal(r512.reason, 'unsupported');
    assert.equal(Array.from(r512.key).length, 200);
    const r513 = RcCodes.parseCode(astral.repeat(513));
    assert.equal(r513.reason, 'too_long');
    assert.equal(Array.from(r513.code).length, 512);
    assert.equal(r513.code.length, 1024);
});

test('русская раскладка: все 33 буквы в обоих регистрах переводятся в ASCII', () => {
    const lower = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя';
    for (const ch of lower + lower.toUpperCase()) {
        const code = RcCodes.parseCode('x' + ch).code;   // 'x' — чтобы не сработал префикс ]..
        assert.equal(code.length, 2, ch);
        assert.ok(code.charCodeAt(1) < 128, ch);
    }
});

test('длинная строка пробелов разбирается за линейное время (без квадратичной регулярки)', () => {
    const t0 = Date.now();
    const r = RcCodes.parseCode(' '.repeat(200000) + 'x' + ' '.repeat(200000));
    assert.equal(r.reason, 'unsupported');
    assert.equal(r.code, 'x');
    assert.ok(Date.now() - t0 < 1000, `${Date.now() - t0} мс`);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

/**
 * ТЕКСТОВЫЕ проверки экрана приёмщика РЦ (/receiving).
 *
 *     node tests/test_receiving_scan_render.mjs
 *
 * Согласованность файлов между собой: шаблон объявляет узлы, которые ищет JS;
 * классы из шаблона и JS описаны в CSS; ресурсы подключены с ?v= (Caddy кэширует
 * /static/* на 30 дней); пункты меню на месте; нет эмодзи; HEX только в блоках
 * токенов; запросы JS совпадают с маршрутами из раздела 7 спецификации (и с
 * routes/receiving.py, если он уже есть). Исполнение — tests/test_receiving_scan_runtime.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(ROOT, p));

const html = read('templates/receiving.html');
const css = read('static/receiving/scan.css');
const js = read('static/js/receiving/scan.js');
const nav = read('templates/shared/nav.html');
const routes = exists('routes/receiving.py') ? read('routes/receiving.py') : null;
// Код без комментариев: пояснения в шапке файла упоминают innerHTML, это не вызов.
const jsCode = js.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

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

// Есть ли в CSS селектор класса (а не просто подстрока: .rc-row не равно .rc-row-time).
const hasClassRule = (name) => new RegExp('\\.' + name.replace(/[-]/g, '\\-') + '(?![\\w-])').test(css);

// Маршруты раздела 7 спецификации (метод, путь с параметрами в виде <p>).
const SPEC_ROUTES = [
    'GET /api/receiving',
    'POST /api/receiving',
    'GET /api/receiving/<p>',
    'POST /api/receiving/<p>/scan',
    'DELETE /api/receiving/<p>/scans/<p>',
    'POST /api/receiving/<p>/invoice',
    'GET /api/receiving/invoice/<p>',
    'DELETE /api/receiving/<p>/invoice/<p>',
    'POST /api/receiving/<p>/close',
    'GET /api/receiving/review',
    'PUT /api/receiving/review/<p>',
    'GET /api/receiving/products',
    'POST /api/receiving/barcodes/refresh',
    'GET /api/receiving/barcodes/status',
];

// Аргумент вызова до запятой верхнего уровня: «API + '/' + id + '/scan'».
function splitArgs(src, start) {
    const args = [];
    let depth = 0;
    let quote = null;
    let current = '';
    for (let i = start; i < src.length; i++) {
        const ch = src[i];
        if (quote) {
            current += ch;
            if (ch === '\\') { current += src[++i]; continue; }
            if (ch === quote) quote = null;
            continue;
        }
        if (ch === "'" || ch === '"' || ch === '`') { quote = ch; current += ch; continue; }
        if (ch === '(' || ch === '[' || ch === '{') depth++;
        if (ch === ')' || ch === ']' || ch === '}') {
            if (depth === 0) { args.push(current.trim()); return args; }
            depth--;
        }
        if (ch === ',' && depth === 0) { args.push(current.trim()); current = ''; continue; }
        current += ch;
    }
    return args;
}

// Выражение пути -> шаблон: строки как есть, API — '/api/receiving', прочее — <p>.
function urlPattern(expr) {
    const parts = [];
    let depth = 0;
    let quote = null;
    let current = '';
    for (const ch of expr) {
        if (quote) { current += ch; if (ch === quote) quote = null; continue; }
        if (ch === "'" || ch === '"') { quote = ch; current += ch; continue; }
        if (ch === '(') depth++;
        if (ch === ')') depth--;
        if (ch === '+' && depth === 0) { parts.push(current.trim()); current = ''; continue; }
        current += ch;
    }
    parts.push(current.trim());
    return parts.map((part) => {
        const literal = /^'([^']*)'$/.exec(part);
        if (literal) return literal[1];
        if (part === 'API') return '/api/receiving';
        if (part === 'PAGE') return '/receiving';
        return '<p>';
    }).join('');
}

function jsRequests() {
    const out = [];
    const re = /\brequest\(\s*'(GET|POST|PUT|DELETE)'\s*,/g;
    let m;
    while ((m = re.exec(js)) !== null) {
        const [urlExpr] = splitArgs(js, m.index + m[0].length);
        out.push({ method: m[1], expr: urlExpr, url: urlPattern(urlExpr) });
    }
    return out;
}

function normalizeRoute(method, url) {
    const pathOnly = url.split('?')[0].replace(/<p>[^/]*/g, '<p>').replace(/\/+$/, '');
    return method + ' ' + (pathOnly || '/');
}

// ---------------------------------------------------------------- шаблон

test('шаблон: без наследования, nav, свой CSS и codes.js раньше scan.js — всё с ?v=', () => {
    assert.ok(!/\{% extends/.test(html), 'шаблон наследуется');
    assert.match(html, /\{% include 'shared\/nav\.html' %\}/);
    assert.match(html, /<body class="rc-page rc-scope">/);
    assert.match(html, /<title>Приёмка — Пивная культура<\/title>/);
    assert.ok(html.includes('<link rel="stylesheet" href="/static/receiving/scan.css?v={{ app_version }}">'));
    const codesAt = html.indexOf('<script src="/static/js/receiving/codes.js?v={{ app_version }}"></script>');
    const scanAt = html.indexOf('<script src="/static/js/receiving/scan.js?v={{ app_version }}"></script>');
    assert.ok(codesAt > 0, 'codes.js не подключён с ?v=');
    assert.ok(scanAt > 0, 'scan.js не подключён с ?v=');
    assert.ok(codesAt < scanAt, 'codes.js должен грузиться раньше scan.js');
    for (const m of html.matchAll(/(?:href|src)="(\/static\/(?:receiving|js\/receiving)\/[^"]+)"/g)) {
        assert.match(m[1], /\?v=\{\{ app_version \}\}$/, 'без кэш-бастинга: ' + m[1]);
    }
    // Свой CSS — последним в <head>: перекрывает общие стили.
    const head = html.slice(0, html.indexOf('</head>'));
    const links = [...head.matchAll(/<link rel="stylesheet" href="([^"]+)"/g)].map((x) => x[1]);
    assert.equal(links.at(-1), '/static/receiving/scan.css?v={{ app_version }}');
});

test('id в шаблоне уникальны, и все id, которые ищет JS, объявлены', () => {
    const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
    const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
    assert.deepEqual(dup, [], 'повторяются id: ' + dup.join(', '));
    const wanted = new Set();
    for (const m of js.matchAll(/\$\('([^']+)'\)/g)) wanted.add(m[1]);
    for (const m of js.matchAll(/getElementById\('([^']+)'\)/g)) wanted.add(m[1]);
    assert.ok(wanted.size > 30, 'JS почти не ищет узлы — регэксп сломался?');
    const missing = [...wanted].filter((id) => !ids.includes(id));
    assert.deepEqual(missing, [], 'нет узлов в шаблоне: ' + missing.join(', '));
    // aria-labelledby ссылается на существующие id.
    for (const m of html.matchAll(/aria-labelledby="([^"]+)"/g)) assert.ok(ids.includes(m[1]), 'нет id ' + m[1]);
    // Все id страницы — с префиксом rc- (nav.html — свой).
    const foreign = ids.filter((id) => !id.startsWith('rc-') && id !== 'rc');
    assert.deepEqual(foreign, [], 'id без префикса rc-: ' + foreign.join(', '));
});

test('классы шаблона и JS — с префиксом rc- и описаны в scan.css', () => {
    const allowed = new Set(['container']);   // общий каркас base.css
    const used = new Set();
    for (const m of html.matchAll(/\sclass="([^"]+)"/g)) m[1].split(/\s+/).filter(Boolean).forEach((c) => used.add(c));
    for (const m of js.matchAll(/\bel\(\s*'[a-z0-9]+'\s*,\s*'([^']+)'/g)) m[1].split(/\s+/).filter(Boolean).forEach((c) => used.add(c));
    for (const m of js.matchAll(/classList\.(?:add|remove|toggle|contains)\(\s*'([^']+)'\s*[,)]/g)) used.add(m[1]);
    // Метки строк сканов: ['Принят', 'is-ok'] и классы вспышки FLASH_CLASSES.
    for (const m of js.matchAll(/\['[^']+', '(is-[a-z-]+)'\]/g)) used.add(m[1]);
    const flash = js.match(/const FLASH_CLASSES = \[([^\]]+)\];/);
    assert.ok(flash, 'нет FLASH_CLASSES');
    for (const m of flash[1].matchAll(/'([^']+)'/g)) used.add(m[1]);
    // Составной класс: 'rc-tag ' + модификатор.
    for (const m of js.matchAll(/el\(\s*'[a-z0-9]+'\s*,\s*'(rc-[a-z0-9-]+) '\s*\+/g)) used.add(m[1]);
    const bad = [...used].filter((c) => !allowed.has(c) && c !== 'rc' && !c.startsWith('rc-') && !c.startsWith('is-'));
    assert.deepEqual(bad, [], 'классы без префикса rc-: ' + bad.join(', '));
    const missing = [...used].filter((c) => !allowed.has(c) && !hasClassRule(c));
    assert.deepEqual(missing, [], 'нет правил в scan.css: ' + missing.join(', '));
    for (const c of ['is-flash-ok', 'is-flash-repeat', 'is-flash-bad', 'is-ok', 'is-repeat', 'is-bad', 'is-wait', 'is-busy']) {
        assert.ok(hasClassRule(c), 'нет правила .' + c);
    }
});

test('поля ввода на экране нет: только скрытый выбор фото и поле в окне «ввести вручную»', () => {
    const inputs = [...html.matchAll(/<input\b[^>]*>/g)].map((m) => m[0]);
    assert.equal(inputs.length, 2, 'лишние поля ввода: ' + inputs.join(' | '));
    const photo = inputs.find((i) => i.includes('id="rc-photo-input"'));
    assert.ok(photo, 'нет выбора фото');
    assert.match(photo, /type="file"/);
    assert.match(photo, /accept="image\/\*"/);
    assert.match(photo, /capture="environment"/);
    assert.match(photo, /\shidden>/);
    const manual = inputs.find((i) => i.includes('id="rc-sheet-input"'));
    assert.ok(manual, 'нет поля ввода вручную');
    assert.match(manual, /\shidden>/, 'поле «вручную» видно сразу');
    assert.match(manual, /inputmode="numeric"/);
    // Поле — внутри окна, а не на экране сканирования.
    const sheet = html.slice(html.indexOf('id="rc-sheet-wrap"'), html.indexOf('id="rc-cam-wrap"'));
    assert.ok(sheet.includes('id="rc-sheet-input"'));
    assert.ok(!/<textarea|<select/.test(html));
});

test('кнопки экрана сканирования: «Сканировать камерой» сразу под счётчиком, Накладная, Отменить последний, Завершить', () => {
    // Только телефон (решение владельца 2026-10-03): камера — главная кнопка экрана,
    // сразу под счётчиком, до пояснения и остальных кнопок.
    const counterAt = html.indexOf('id="rc-counter"');
    const cameraAt = html.indexOf('id="rc-camera"');
    assert.ok(counterAt > 0 && cameraAt > counterAt, 'кнопка камеры не под счётчиком');
    assert.ok(cameraAt < html.indexOf('<details class="rc-how">'), 'кнопка камеры ниже пояснения');
    assert.match(html, /<button class="rc-btn rc-btn-lg rc-btn-primary rc-cam-cta" id="rc-camera" type="button">[\s\S]*?Сканировать камерой/);
    // На экране сканирования главная кнопка одна — камера; «Завершить» выделена иначе.
    const scanScreen = html.slice(html.indexOf('id="rc-scan"'), html.indexOf('id="rc-done"'));
    assert.equal((scanScreen.match(/rc-btn-primary/g) || []).length, 1, 'на экране сканирования больше одной главной кнопки');
    assert.match(scanScreen, /class="rc-btn rc-btn-lg rc-btn-finish" id="rc-finish"/);
    const actions = html.slice(html.indexOf('<div class="rc-actions">'), html.indexOf('id="rc-photo-input"'));
    for (const [id, label] of [['rc-photo', 'Накладная'],
                               ['rc-undo', 'Отменить последний'], ['rc-finish', 'Завершить']]) {
        assert.match(actions, new RegExp('id="' + id + '" type="button">[\\s\\S]*?' + label), 'нет кнопки ' + label);
    }
    // В окне камеры: отмена последнего скана без выхода из камеры.
    const camBar = html.slice(html.indexOf('class="rc-cam-bar"'), html.indexOf('id="rc-toast"'));
    for (const [id, label] of [['rc-torch', 'Фонарик'], ['rc-cam-undo', 'Отменить последний'], ['rc-cam-close', 'Закрыть камеру']]) {
        assert.match(camBar, new RegExp('id="' + id + '" type="button"[^>]*>' + label), 'нет кнопки ' + label + ' в окне камеры');
    }
    assert.match(html, /id="rc-new" type="button">[\s\S]*?Новая приёмка/);
    assert.match(html, /href="\/receiving\/review">Разбор приёмок<\/a>/, 'нет ссылки на разбор');
    assert.match(html, /class="rc-pending" id="rc-pending" hidden/);
    // Все <button> — type="button" (на странице нет форм, но привычка защищает от submit).
    for (const m of html.matchAll(/<button\b[^>]*>/g)) assert.match(m[0], /type="button"/, m[0]);
});

test('«Как считается» свёрнуто у счётчика, а пауза сканера в тексте совпадает с JS', () => {
    const details = html.match(/<details class="rc-how">\s*<summary>Как считается<\/summary>([\s\S]*?)<\/details>/);
    assert.ok(details, 'нет раскрывашки «Как считается»');
    assert.ok(html.indexOf('id="rc-counter"') < html.indexOf('<details class="rc-how">'), 'пояснение не у счётчика');
    const gap = Number(js.match(/const SCAN_GAP_MS = (\d+);/)[1]);
    assert.equal(gap, 80);
    assert.ok(details[1].includes(gap + ' мс'), 'в пояснении другая пауза сканера');
    for (const word of ['DataMatrix', 'EAN', 'SSCC', 'Не отправлено', 'Отменить последний', 'Камера']) {
        assert.ok(details[1].includes(word), 'в пояснении нет «' + word + '»');
    }
    // Числа камеры в пояснении — те же, что в JS.
    const sec = (name) => (Number(js.match(new RegExp('const ' + name + ' = (\\d+);'))[1]) / 1000).toString().replace('.', ',') + ' с';
    assert.equal(sec('CAMERA_REPEAT_MS'), '2,5 с');
    assert.equal(sec('CAMERA_EAN_WAIT_MS'), '0,8 с');
    for (const text of [sec('CAMERA_REPEAT_MS'), sec('CAMERA_EAN_WAIT_MS')]) {
        assert.ok(details[1].includes(text), 'в пояснении нет «' + text + '»');
    }
    const tick = Number(js.match(/const CAMERA_TICK_MS = (\d+);/)[1]);
    assert.ok(details[1].includes('пауза ' + tick + ' мс'), 'пауза между проверками кадра в пояснении не совпадает с JS');
    assert.ok(!/<details(?![^>]*class="rc-how")/.test(html), 'раскрывашка без своего класса');
});

// ---------------------------------------------------------------- CSS

test('CSS: HEX только в двух блоках токенов, у тёмной темы те же токены', () => {
    const light = css.match(/\n\.rc-scope \{([\s\S]*?)\n\}/);
    const dark = css.match(/\n\[data-theme="dark"\] \.rc-scope,\n\.rc-scope\[data-theme="dark"\] \{([\s\S]*?)\n\}/);
    assert.ok(light, 'нет блока светлых токенов .rc-scope');
    assert.ok(dark, 'нет блока тёмных токенов [data-theme="dark"] .rc-scope');
    const rest = css.replace(light[0], '').replace(dark[0], '');
    const hex = rest.match(/#[0-9a-fA-F]{3,8}\b/g);
    assert.equal(hex, null, 'HEX вне блоков токенов: ' + (hex || []).join(', '));
    const names = (block) => [...block.matchAll(/(--rc-[\w-]+):/g)].map((m) => m[1]);
    const colorNames = (block) => [...block.matchAll(/(--rc-[\w-]+):\s*(#|rgba?\()/g)].map((m) => m[1]).sort();
    assert.deepEqual(colorNames(dark[1]), colorNames(light[1]), 'цветовые токены тем расходятся');
    for (const n of names(dark[1])) assert.ok(names(light[1]).includes(n), 'токен только в тёмной теме: ' + n);
    // Каждый использованный токен объявлен.
    const declared = new Set(names(light[1]));
    const usedTokens = new Set([...css.matchAll(/var\((--rc-[\w-]+)\)/g)].map((m) => m[1]));
    const undeclared = [...usedTokens].filter((t) => !declared.has(t));
    assert.deepEqual(undeclared, [], 'необъявленные токены: ' + undeclared.join(', '));
    assert.ok(!/style="/.test(html), 'встроенные стили в шаблоне');
    assert.equal(js.match(/#[0-9a-fA-F]{6}\b/g), null, 'цвет HEX в JS');
});

test('CSS: [hidden] сильнее display, телефон 768px, шаг кнопок не мельче 44px', () => {
    assert.match(css, /\.rc-scope \[hidden\] \{ display: none !important; \}/);
    assert.match(css, /@media \(max-width: 768px\)/);
    assert.match(css, /--rc-ctl-h: 44px;/);
    assert.match(css, /--rc-ctl-lg: 56px;/);
    // Свой префикс везде: в CSS нет голых селекторов чужих классов.
    const selectors = css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\{[^{}]*\}/g, '{}')
        .replace(/@media[^{]*\{/g, '').replace(/@font-face\s*\{\}/g, '').replace(/@keyframes[^{]*\{/g, '');
    const classes = [...selectors.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]);
    const foreign = [...new Set(classes)].filter((c) => c !== 'rc' && !c.startsWith('rc-') && !c.startsWith('is-'));
    assert.deepEqual(foreign, [], 'чужие классы в scan.css: ' + foreign.join(', '));
});

// ---------------------------------------------------------------- JS

test('JS: только textContent (без innerHTML), keydown на window в фазе захвата', () => {
    assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function/.test(jsCode), 'небезопасная вставка HTML');
    assert.match(js, /window\.addEventListener\('keydown', onKeyDown, true\)/);
    assert.match(js, /event\.preventDefault\(\);\s*event\.stopPropagation\(\);/);
    assert.match(js, /code === 'BracketRight'/, 'нет Ctrl+] -> GS');
    for (const key of ['Minus', 'Equal', 'BracketLeft', 'BracketRight', 'Semicolon', 'Quote', 'Comma',
                       'Period', 'Slash', 'Backslash', 'Backquote', 'Space']) {
        assert.ok(new RegExp('\\b' + key + ': \\[').test(js), 'нет клавиши ' + key);
    }
    assert.match(js, /const END_CODES = \['Enter', 'NumpadEnter', 'Tab'\];/);
    assert.match(js, /window\.RcCodes/);
    assert.match(js, /window\.__rcScan = \{/);
});

test('JS: очередь rc.queue.v1 пишется до отправки, повторы 2/5/10/30 с, online и visibilitychange', () => {
    assert.match(js, /const QUEUE_KEY = 'rc\.queue\.v1';/);
    assert.match(js, /const RETRY_DELAYS_MS = \[2000, 5000, 10000, 30000\];/);
    const handle = js.slice(js.indexOf('function handleCode('), js.indexOf('function flush('));
    assert.ok(handle.indexOf('saveQueue()') !== -1 && handle.indexOf('saveQueue()') < handle.indexOf('flush()'),
        'скан уходит раньше, чем ложится в localStorage');
    assert.match(js, /addEventListener\('online'/);
    assert.match(js, /addEventListener\('visibilitychange'/);
    assert.match(js, /crypto/);
    assert.match(js, /randomUUID/);
    assert.match(js, /status === 401/);
    assert.match(js, /'\/login\?next=' \+ encodeURIComponent\(next\)/);
    assert.match(js, /Есть неотправленные сканы — дождитесь связи/);
});

test('JS: камера — BarcodeDetector с форматами спецификации, запасной полифил, 2,5 с, фонарик', () => {
    assert.match(js, /const CAMERA_FORMATS = \['data_matrix', 'ean_13', 'ean_8', 'upc_a'\];/);
    // Полифил: своя копия в static/libs (версия в пути), CDN той же версии — запасной.
    const dir = js.match(/const CAMERA_POLYFILL_DIR = '(\/static\/libs\/barcode-detector-[0-9.]+\/)';/);
    assert.ok(dir, 'нет своей копии полифила');
    for (const file of ['pure.js', 'zxing_reader.wasm', 'LICENSE.txt']) {
        assert.ok(fs.existsSync(path.join(ROOT, dir[1].slice(1), file)), 'нет файла ' + dir[1] + file);
    }
    const version = dir[1].match(/barcode-detector-([0-9.]+)\//)[1];
    assert.match(js, new RegExp("'https://cdn\\.jsdelivr\\.net/npm/barcode-detector@" + version.replace(/\./g, '\\.') + "/dist/es/pure\\.min\\.js'"));
    // Своя копия грузит .wasm рядом с собой, а не с fastly.jsdelivr.net.
    assert.match(js, /setZXingModuleOverrides\(/);
    assert.match(js, /facingMode: 'environment', width: \{ ideal: 1920 \}, height: \{ ideal: 1080 \}/);
    assert.match(js, /const CAMERA_EAN_WAIT_MS = 800;/);
    assert.match(js, /wakeLock/);
    assert.match(js, /const CAMERA_REPEAT_MS = 2500;/);
    assert.match(js, /\.torch/);
    assert.match(js, /const PHOTO_MAX_SIDE = 2400;/);
    assert.match(js, /const PHOTO_QUALITY = 0\.85;/);
    assert.match(js, /'image\/jpeg'/);
});

test('JS: запросы совпадают с маршрутами раздела 7 спецификации', () => {
    const calls = jsRequests();
    assert.ok(calls.length >= 9, 'найдено мало запросов: ' + calls.length);
    const used = new Set();
    for (const call of calls) {
        const route = normalizeRoute(call.method, call.url);
        assert.ok(SPEC_ROUTES.includes(route), 'запрос вне спецификации: ' + route + '  (' + call.expr + ')');
        used.add(route);
    }
    // Ссылка на фото накладной — GET /api/receiving/invoice/<name>.
    assert.match(js, /API \+ '\/invoice\/' \+ encodeURIComponent\(invoice\.name\)/);
    for (const route of ['GET /api/receiving', 'POST /api/receiving', 'GET /api/receiving/<p>',
                         'POST /api/receiving/<p>/scan', 'DELETE /api/receiving/<p>/scans/<p>',
                         'POST /api/receiving/<p>/invoice', 'DELETE /api/receiving/<p>/invoice/<p>',
                         'POST /api/receiving/<p>/close']) {
        assert.ok(used.has(route), 'страница не использует ' + route);
    }
    const list = calls.find((c) => c.method === 'GET' && c.url.startsWith('/api/receiving?'));
    assert.equal(list.url, '/api/receiving?status=open', 'стартовый список — только открытые');
});

test('маршруты страницы есть в routes/receiving.py (если файл уже написан)', () => {
    if (!routes) {
        console.log('      (routes/receiving.py ещё нет — проверка по спецификации выше)');
        return;
    }
    const declared = new Set();
    for (const m of routes.matchAll(/@receiving_bp\.route\('([^']+)'(?:,\s*methods=\[([^\]]+)\])?\)/g)) {
        const methods = m[2] ? [...m[2].matchAll(/'([A-Z]+)'/g)].map((x) => x[1]) : ['GET'];
        const url = m[1].replace(/<[^>]+>/g, '<p>');
        for (const method of methods) declared.add(normalizeRoute(method, url));
    }
    assert.ok(declared.has('GET /receiving'), 'нет страницы /receiving');
    for (const call of jsRequests()) {
        const route = normalizeRoute(call.method, call.url);
        assert.ok(declared.has(route), 'в routes/receiving.py нет ' + route);
    }
    assert.ok(declared.has('GET /api/receiving/invoice/<p>'), 'нет раздачи фото накладной');
});

// ---------------------------------------------------------------- меню

function navSection(label) {
    const re = /<div class="sidebar-section-label">([^<]+)<\/div>/g;
    const marks = [];
    let m;
    while ((m = re.exec(nav)) !== null) marks.push({ label: m[1].trim(), at: m.index, end: re.lastIndex });
    const i = marks.findIndex((s) => s.label === label);
    return i === -1 ? null : nav.slice(marks[i].end, i + 1 < marks.length ? marks[i + 1].at : nav.length);
}

test('меню: «Приёмка» и «Разбор приёмок» в «Управлении» сразу после «Поставщиков», иконки в общем стиле', () => {
    const body = navSection('Управление');
    assert.ok(body, 'нет секции «Управление»');
    const hrefs = [...body.matchAll(/<a href="([^"]+)" class="sidebar-link">/g)].map((m) => m[1]);
    const at = hrefs.indexOf('/suppliers');
    assert.ok(at !== -1, 'нет /suppliers');
    assert.deepEqual(hrefs.slice(at, at + 3), ['/suppliers', '/receiving', '/receiving/review'],
        'порядок ссылок: ' + hrefs.join(', '));
    for (const [href, label] of [['/receiving', 'Приёмка'], ['/receiving/review', 'Разбор приёмок']]) {
        const block = body.match(new RegExp('<a href="' + href.replace(/\//g, '\\/') + '" class="sidebar-link">([\\s\\S]*?)</a>'));
        assert.ok(block, 'нет ссылки ' + href);
        assert.match(block[1], /<span class="sidebar-link-icon">\s*<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">/,
            'иконка ' + href + ' не в стиле соседей');
        assert.ok(!/fill="(?!none)/.test(block[1]), 'залитая иконка у ' + href);
        assert.match(block[1], new RegExp('</span>\\s*' + label + '\\s*$'), 'подпись ' + href + ' не «' + label + '»');
        assert.equal((nav.match(new RegExp('href="' + href.replace(/\//g, '\\/') + '"', 'g')) || []).length, 1,
            'ссылка ' + href + ' в меню не одна');
    }
});

// ---------------------------------------------------------------- без эмодзи

test('без эмодзи и «•» в шаблоне, CSS, JS и меню', () => {
    const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}\u{2B50}\u{2B55}\u{FE0F}•]/u;
    for (const [name, src] of Object.entries({ html, css, js, nav })) {
        const hit = src.match(EMOJI);
        assert.equal(hit, null, `эмодзи в ${name}: ${hit && JSON.stringify(hit[0])}`);
    }
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);

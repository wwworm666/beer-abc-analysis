/**
 * ТЕКСТОВЫЕ проверки страницы «Разбор приёмок» (/receiving/review).
 *
 *     node tests/test_receiving_review_render.mjs
 *
 * Согласованность файлов страницы между собой и с сервером: шаблон объявляет
 * узлы, которые ищет JS; CSS описывает классы, которые пишут шаблон и JS; цвета
 * только токенами (HEX — в двух блоках токенов); ресурсы с ?v=; без эмодзи и
 * innerHTML; пути и параметры API — те, что в контракте (раздел 7 спецификации,
 * routes/receiving.py); пределы и стоп-слова — те же, что в ядре.
 * Исполнение — в tests/test_receiving_review_runtime.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const readOpt = (p) => (fs.existsSync(path.join(ROOT, p)) ? read(p) : null);

const html = read('templates/receiving_review.html');
const css = read('static/receiving/review.css');
const js = read('static/js/receiving/review.js');
const vars = read('static/dashboard/styles/variables.css');
const nav = read('templates/shared/nav.html');
// Модули других зон: проверки паритета пропускаются, если файла ещё нет.
const routes = readOpt('routes/receiving.py');
const indexPy = readOpt('core/receiving_index.py');
const storePy = readOpt('core/receiving_store.py');

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

const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '');
const visibleHtml = html.replace(/<!--[\s\S]*?-->/g, '');
const pyConst = (src, name) => {
    const m = new RegExp('^' + name + '\\s*=\\s*([^\\n#]+)', 'm').exec(src || '');
    return m ? m[1].trim() : null;
};
const jsConst = (name) => {
    const m = new RegExp('const ' + name + ' = ([^;]+);').exec(js);
    return m ? m[1].trim() : null;
};

// ---------------------------------------------------------------- шаблон и ресурсы

test('шаблон без наследования: свой title, общий nav, заголовок страницы', () => {
    assert.ok(!/\{%\s*extends/.test(html), 'шаблон наследуется — на сайте наследования нет');
    assert.match(html, /<title>Разбор приёмок — Пивная культура<\/title>/);
    assert.match(html, /\{% set page_title = "Разбор приёмок" %\}/);
    assert.match(html, /\{% include 'shared\/nav\.html' %\}/);
    assert.match(html, /<html lang="ru">/);
    assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1\.0">/);
});

test('свои CSS и JS подключены с ?v={{ app_version }}, CSS страницы — последним', () => {
    const links = [...html.matchAll(/<link rel="stylesheet" href="([^"]+)">/g)].map((m) => m[1]);
    assert.deepEqual(links, [
        '/static/dashboard/styles/fonts.css',
        '/static/dashboard/styles/variables.css',
        '/static/dashboard/styles/base.css',
        '/static/dashboard/styles/sidebar.css',
        '/static/dashboard/styles/mobile.css',
        '/static/logo.css',
        '/static/receiving/review.css?v={{ app_version }}',
    ]);
    const scripts = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]);
    assert.deepEqual(scripts, ['/static/logo.js', '/static/js/receiving/review.js?v={{ app_version }}']);
    for (const ref of [...links, ...scripts]) {
        if (/\/static\/(receiving|js\/receiving)\//.test(ref)) {
            assert.match(ref, /\?v=\{\{ app_version \}\}$/, `${ref} без кэш-бастинга`);
        }
    }
    assert.ok(!/<script>(?!\s*<\/script>)/.test(html), 'инлайновый скрипт в шаблоне');
    assert.ok(!/<style>/.test(html), 'инлайновые стили в шаблоне');
});

test('страница и пункт меню подключены: маршрут рендерит шаблон с app_version, ссылка в nav', () => {
    assert.match(nav, /<a href="\/receiving\/review" class="sidebar-link">[\s\S]*?Разбор приёмок/,
        'нет пункта «Разбор приёмок» в меню');
    if (routes) {
        assert.match(routes, /@receiving_bp\.route\('\/receiving\/review'\)[\s\S]*?render_template\('receiving_review\.html', app_version=/,
            'маршрут /receiving/review не рендерит шаблон с app_version');
    }
});

test('id в шаблоне уникальны, все id, которые ищет JS, есть в шаблоне', () => {
    const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
    const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
    assert.deepEqual(dupes, [], `повторяющиеся id: ${dupes.join(', ')}`);
    const wanted = new Set([...js.matchAll(/\$\('([^']+)'\)/g)].map((m) => m[1]));
    for (const m of js.matchAll(/getElementById\('([^']+)'\)/g)) wanted.add(m[1]);
    assert.ok(wanted.size >= 15, 'JS почти не ищет узлы — регулярка сломалась?');
    const missing = [...wanted].filter((id) => !ids.includes(id));
    assert.deepEqual(missing, [], `нет узлов в шаблоне: ${missing.join(', ')}`);
    const unused = ids.filter((id) => !wanted.has(id) && id !== 'rv');
    assert.deepEqual(unused, [], `id в шаблоне, которые JS не использует: ${unused.join(', ')}`);
    assert.ok(ids.every((id) => /^rv[A-Z]?/.test(id)), 'id без префикса rv');
});

test('скрытые изначально узлы помечены hidden, а скрывающее правило есть в CSS', () => {
    for (const id of ['rvJob', 'rvError', 'rvMore', 'rvIikoMsg', 'rvToast']) {
        assert.match(html, new RegExp(`id="${id}"[^>]*\\shidden`), `${id} виден до загрузки`);
    }
    assert.match(html, /<body class="rv-page rv-scope">/);
    assert.match(css, /\.rv-scope \[hidden\] \{ display: none !important; \}/);
});

// ---------------------------------------------------------------- CSS: классы и токены

test('каждый класс rv- из шаблона и JS описан в review.css', () => {
    const used = new Set();
    for (const m of html.matchAll(/class="([^"]+)"/g)) {
        m[1].split(/\s+/).filter((c) => c.startsWith('rv-')).forEach((c) => used.add(c));
    }
    for (const m of js.matchAll(/'([^'\n]*)'/g)) {
        for (const c of m[1].match(/\brv-[a-z0-9-]+/g) || []) {
            if (!/-$/.test(c)) used.add(c);
        }
    }
    assert.ok(used.size > 50, 'классов подозрительно мало — регулярка сломалась?');
    const body = stripComments(css);
    const missing = [...used].filter((c) => !new RegExp('\\.' + c + '(?![\\w-])').test(body));
    assert.deepEqual(missing, [], `нет в review.css: ${missing.join(', ')}`);
});

test('модификаторы, которые ставит JS, описаны в CSS у своих компонентов', () => {
    const body = stripComments(css);
    const pairs = [
        'rv-pill.is-ok', 'rv-pill.is-warn', 'rv-pill.is-new', 'rv-tab.is-active', 'rv-tab-n.has-items',
        'rv-row.is-closed', 'rv-row.is-busy', 'rv-btn.is-busy', 'rv-name.is-none', 'rv-index.is-missing',
        'rv-job.is-bad', 'rv-msg.is-bad', 'rv-saved.is-bad', 'rv-toast.is-bad', 'rv-rc.is-current',
        'rv-rc-note.is-bad', 'rv-flag.is-plain', 'rv-rc-proc.is-done', 'rv-rc-proc.is-wait', 'rv-rc-proc.is-error',
        'rv-chip.is-on', 'rv-chip-n.is-wait', 'rv-chip-n.is-error', 'rv-rc-prog.is-done',
    ];
    const missing = pairs.filter((p) => !body.includes('.' + p));
    assert.deepEqual(missing, [], `нет правил: ${missing.join(', ')}`);
    // Цвет таблетки берётся из STATUS_TONE: у каждого тона — своё правило.
    const tone = /const STATUS_TONE = \{([^}]+)\}/.exec(js);
    assert.ok(tone, 'нет STATUS_TONE');
    const tones = [...tone[1].matchAll(/'(\w+)'/g)].map((m) => m[1]);
    assert.deepEqual([...new Set(tones)].sort(), ['new', 'ok', 'warn']);
    tones.forEach((t) => assert.ok(body.includes('.rv-pill.is-' + t), `нет .rv-pill.is-${t}`));
    const proc = /const PROCESS = \{([\s\S]*?)\n    \};/.exec(js)[1];
    for (const m of proc.matchAll(/cls: '([\w-]*)'/g)) {
        if (m[1]) assert.ok(body.includes('.rv-rc-proc.' + m[1]), `нет .rv-rc-proc.${m[1]}`);
    }
});

test('цвета только токенами: HEX и rgba — только в двух блоках токенов', () => {
    const body = stripComments(css);
    const light = /\n\.rv-scope \{[\s\S]*?\n\}/.exec(body);
    const dark = /\n\[data-theme="dark"\] \.rv-scope,\n\.rv-scope\[data-theme="dark"\] \{[\s\S]*?\n\}/.exec(body);
    assert.ok(light, 'нет светлого блока токенов');
    assert.ok(dark, 'нет тёмного блока токенов [data-theme="dark"]');
    const rest = body.replace(light[0], '').replace(dark[0], '');
    const hex = rest.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
    assert.deepEqual(hex, [], `HEX вне токенов: ${hex.join(', ')}`);
    assert.ok(!/rgba?\(|hsla?\(/.test(rest), 'rgba/hsl вне токенов');
    assert.ok(!/\b(white|black|red|green|blue|yellow|orange|gray|grey)\b/.test(rest.replace(/white-space/g, '')),
        'именованный цвет вне токенов');

    const defined = (block) => new Set([...block.matchAll(/(--rv-[\w-]+):/g)].map((m) => m[1]));
    const lightVars = defined(light[0]);
    const darkVars = defined(dark[0]);
    const usedVars = new Set([...rest.matchAll(/var\((--rv-[\w-]+)\)/g)].map((m) => m[1]));
    const undef = [...usedVars].filter((v) => !lightVars.has(v));
    assert.deepEqual(undef, [], `токены не определены: ${undef.join(', ')}`);
    // Тёмная тема переопределяет каждый цветовой токен светлой (размеры и радиусы — общие).
    const colorTokens = [...light[0].matchAll(/(--rv-[\w-]+):\s*([^;]+);/g)]
        .filter((m) => /#|rgba/.test(m[2])).map((m) => m[1]);
    const noDark = colorTokens.filter((v) => !darkVars.has(v));
    assert.deepEqual(noDark, [], `нет в тёмной теме: ${noDark.join(', ')}`);
    // Общие переменные — только существующие в variables.css.
    const globals = [...rest.matchAll(/var\((--(?!rv-)[\w-]+)\)/g)].map((m) => m[1]);
    const unknown = globals.filter((v) => !vars.includes(v + ':'));
    assert.deepEqual(unknown, [], `нет в variables.css: ${unknown.join(', ')}`);
});

test('синего нет: «Новая» — акцентом (в дизайн-системе нет синего токена)', () => {
    assert.ok(!/blue|син/i.test(stripComments(css)), 'в стилях появился синий');
    assert.match(css, /\.rv-pill\.is-new \{[^}]*var\(--rv-accent-ink\)[^}]*var\(--rv-accent-soft\)/);
    assert.match(css, /\.rv-pill\.is-ok \{[^}]*var\(--rv-ok-ink\)/);
    assert.match(css, /\.rv-pill\.is-warn \{[^}]*var\(--rv-warn-ink\)/);
});

test('радиусы по шкале: 14px панели, 10px кнопки и поля, 999px таблетки', () => {
    assert.match(css, /--rv-r-panel: 14px;/);
    assert.match(css, /--rv-r-ctl: 10px;/);
    assert.match(css, /--rv-r-pill: 999px;/);
    const radii = [...stripComments(css).matchAll(/border-radius:\s*([^;]+);/g)].map((m) => m[1].trim());
    const odd = radii.filter((r) => !/^var\(--rv-r-(panel|ctl|pill)\)$/.test(r));
    assert.deepEqual(odd, [], `радиусы вне шкалы: ${odd.join(', ')}`);
});

test('телефон: брейкпоинт 768px, таблица превращается в карточки, поля от 16px', () => {
    const mobile = /@media \(max-width: 768px\) \{([\s\S]*)\n\}\s*$/.exec(css);
    assert.ok(mobile, 'нет блока @media (max-width: 768px) в конце файла');
    const m = mobile[1];
    assert.match(m, /\.rv-table thead \{ display: none; \}/);
    assert.match(m, /\.rv-table tr \{[\s\S]*?display: grid;/);
    assert.match(m, /\.rv-td-st \{ grid-column: 1; grid-row: 1; \}/);
    assert.match(m, /font-size: 16px/, 'поля мельче 16px — iOS увеличит страницу при фокусе');
    assert.ok(!/@media \(max-width: (?!768px)/.test(css), 'брейкпоинт не из дизайн-системы');
});

// ---------------------------------------------------------------- безопасность и стиль

test('без эмодзи и без значка-точки в шаблоне, стилях и скрипте', () => {
    const emoji = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}•]/u;
    for (const [name, text] of [['шаблон', html], ['стили', css], ['скрипт', js]]) {
        const hit = emoji.exec(text);
        assert.ok(!hit, `${name}: недопустимый символ ${hit && hit[0]}`);
    }
});

test('DOM только через textContent: ни innerHTML, ни инлайновых обработчиков', () => {
    const code = stripComments(js);
    for (const bad of ['innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function']) {
        assert.ok(!code.includes(bad), `в скрипте ${bad}`);
    }
    assert.ok(!/\son[a-z]+=/.test(html), 'инлайновый обработчик в шаблоне');
    assert.match(js, /'use strict'/);
    assert.match(js, /^\(function \(\) \{/m, 'скрипт не в IIFE');
    assert.match(js, /window\.__rvReview = \{/, 'нет экспорта для тестов');
});

test('ссылки на фото накладных ставятся только на свой путь', () => {
    assert.match(js, /const INVOICE_PREFIX = '\/api\/receiving\/invoice\/';/);
    assert.match(js, /url\.indexOf\(INVOICE_PREFIX\) !== 0\) return;/);
    assert.match(js, /setAttribute\('rel', 'noopener'\)/);
});

// ---------------------------------------------------------------- контракт API

const SPEC_PATHS = {
    API_REVIEW: '/api/receiving/review',
    API_PRODUCTS: '/api/receiving/products',
    API_REFRESH: '/api/receiving/barcodes/refresh',
    API_STATUS: '/api/receiving/barcodes/status',
    API_RECEIPT: '/api/receiving/',
};

test('пути API — из раздела 7 спецификации, других запросов нет', () => {
    for (const [name, value] of Object.entries(SPEC_PATHS)) {
        assert.equal(jsConst(name), `'${value}'`, `${name} не ${value}`);
    }
    const literals = [...stripComments(js).matchAll(/'(\/api\/[^']*)'/g)].map((m) => m[1]);
    const allowed = new Set([...Object.values(SPEC_PATHS), '/api/receiving/invoice/']);
    const extra = literals.filter((p) => !allowed.has(p));
    assert.deepEqual(extra, [], `пути вне контракта: ${extra.join(', ')}`);
    assert.equal([...js.matchAll(/\bfetch\(/g)].length, 1, 'запросы мимо общего помощника request()');
    assert.match(js, /request\('PUT', API_REVIEW \+ '\/' \+ encodeURIComponent\(row\.gtin\), body\)/);
    assert.match(js, /request\('POST', API_REFRESH\)/);
    assert.match(js, /request\('GET', API_STATUS\)/);
    assert.match(js, /request\('GET', API_RECEIPT \+ Number\(id\)\)/);
    assert.match(js, /request\('DELETE', API_RECEIPT \+ id\)/);
    assert.match(js, /window\.confirm\(deleteQuestion\(r\)\)/, 'удаление без подтверждения');
    assert.match(js, /API_PRODUCTS \+ '\?q=' \+ encodeURIComponent\(q\) \+ '&limit=' \+ IIKO_LIMIT/);
});

test('маршруты, которые зовёт страница, объявлены в routes/receiving.py с нужными методами', () => {
    if (!routes) { console.log('      (routes/receiving.py ещё нет — пропуск)'); return; }
    const want = [
        ["'/api/receiving/review'", "'GET'"],
        ["'/api/receiving/review/<gtin>'", "'PUT'"],
        ["'/api/receiving/products'", "'GET'"],
        ["'/api/receiving/barcodes/refresh'", "'POST'"],
        ["'/api/receiving/barcodes/status'", "'GET'"],
        ["'/api/receiving/<int:receipt_id>'", "'GET'"],
        ["'/api/receiving/<int:receipt_id>'", "'DELETE'"],
        ["'/api/receiving/invoice/<name>'", "'GET'"],
    ];
    for (const [route, method] of want) {
        const re = new RegExp('@receiving_bp\\.route\\(' + route.replace(/[/<>:]/g, (c) => '\\' + c)
            + ", methods=\\[" + method + '\\]\\)');
        assert.match(routes, re, `нет ${method} ${route}`);
    }
});

test('параметры запроса и поля тела — те, что читает маршрут', () => {
    for (const p of ['state', 'status', 'receipt_id', 'q', 'limit']) {
        assert.ok(js.includes(`'${p}=`) || js.includes(`'&${p}=`) || js.includes(`?${p}=`), `JS не шлёт ${p}`);
        if (routes) assert.ok(routes.includes(`request.args.get('${p}')`), `маршрут не читает ${p}`);
    }
    for (const field of ['supplier', 'state', 'note']) {
        assert.match(js, new RegExp(`putRow\\(row, \\{ ${field}: `), `JS не шлёт ${field} в PUT`);
        if (routes) assert.ok(routes.includes(`body.get('${field}')`), `маршрут не читает ${field}`);
    }
    // Значения state у PUT — ровно из контракта: done / not_needed / open.
    const states = [...js.matchAll(/setRowState\(row, '(\w+)'\)/g)].map((m) => m[1]).sort();
    assert.deepEqual(states, ['done', 'not_needed', 'open']);
    // Вкладки -> state/status из контракта list_review.
    const tabs = [...js.matchAll(/\{ id: '(\w+)', label: '([^']+)', state: '(\w+)', status: '(\w*)' \}/g)]
        .map((m) => [m[1], m[2], m[3], m[4]]);
    assert.deepEqual(tabs, [
        ['open', 'К разбору', 'open', ''],
        ['new', 'Новые', 'open', 'new'],
        ['similar', 'Похожие', 'open', 'similar'],
        ['restore', 'Восстановить', 'open', 'restore'],
        ['duplicate', 'Дубли', 'open', 'duplicate'],
        ['closed', 'Закрытые', 'closed', ''],
        ['all', 'Все', 'all', ''],
    ]);
});

test('подписи статусов — из раздела 1 спецификации', () => {
    const block = /const STATUS_LABELS = \{([\s\S]*?)\};/.exec(js)[1];
    const labels = Object.fromEntries([...block.matchAll(/(\w+): '([^']+)'/g)].map((m) => [m[1], m[2]]));
    assert.deepEqual(labels, {
        new: 'Новая', similar: 'Похожая карточка', restore: 'Удалена или в архиве',
        duplicate: 'Дубль штрихкода', found: 'Есть в iiko',
    });
    for (const label of Object.values(labels)) {
        assert.ok(html.includes('<b>' + label + '</b>'), `правило «${label}» не объяснено в «Как считается»`);
    }
});

test('пределы совпадают с маршрутом и хранилищем', () => {
    if (routes) {
        assert.equal(jsConst('LIST_LIMIT'), pyConst(routes, 'REVIEW_LIMIT_DEFAULT'), 'LIST_LIMIT');
        assert.equal(jsConst('IIKO_MIN_Q'), pyConst(routes, 'PRODUCTS_MIN_Q'), 'IIKO_MIN_Q');
        assert.ok(Number(jsConst('IIKO_LIMIT')) <= Number(pyConst(routes, 'PRODUCTS_LIMIT_MAX')), 'IIKO_LIMIT');
        const qMax = pyConst(routes, 'SEARCH_Q_MAX');
        for (const m of html.matchAll(/type="search"[^>]*maxlength="(\d+)"|maxlength="(\d+)"[^>]*type="search"/g)) {
            assert.equal(m[1] || m[2], qMax, 'maxlength поиска не равен SEARCH_Q_MAX');
        }
    }
    if (storePy) assert.equal(jsConst('NOTE_LIMIT'), pyConst(storePy, 'NOTE_LIMIT'), 'NOTE_LIMIT');
    if (storePy) assert.equal(jsConst('PICK_MAX'), pyConst(storePy, 'RECEIPT_FILTER_MAX'), 'PICK_MAX');
    if (routes) assert.equal(pyConst(routes, 'REVIEW_RECEIPTS_MAX'), 'receiving_store.RECEIPT_FILTER_MAX');
    assert.equal(jsConst('POLL_MS'), '4000', 'опрос — каждые 4 с (раздел 9)');
});

test('стоп-слова и длина слова «Найти в iiko» — как у «похожей карточки» в индексе', () => {
    const jsWords = /const STOP_WORDS = new Set\(\[([\s\S]*?)\]\);/.exec(js);
    assert.ok(jsWords, 'нет STOP_WORDS в JS');
    const mine = [...jsWords[1].matchAll(/'([^']+)'/g)].map((m) => m[1]).sort();
    assert.equal(mine.length, 21, 'список стоп-слов не из спецификации (21 слово)');
    if (indexPy) {
        const py = /STOP_WORDS = frozenset\(\{([\s\S]*?)\}\)/.exec(indexPy);
        assert.ok(py, 'нет STOP_WORDS в core/receiving_index.py');
        const theirs = [...py[1].matchAll(/'([^']+)'/g)].map((m) => m[1]).sort();
        assert.deepEqual(mine, theirs, 'стоп-слова разошлись с core/receiving_index.py');
        assert.equal(jsConst('MIN_WORD_LEN'), pyConst(indexPy, 'MIN_WORD_LEN'), 'MIN_WORD_LEN');
    }
});

// ---------------------------------------------------------------- «Как считается»

test('пояснения свёрнуты в «Как считается» у каждого блока, на экране — только числа', () => {
    const how = [...html.matchAll(/<details class="rv-how[^"]*">\s*<summary>Как считается<\/summary>/g)];
    assert.equal(how.length, 5, 'у шапки, выбора приёмок, таблицы, поиска в iiko и истории — по раскрывашке');
    const sections = [...html.matchAll(/<section[\s\S]*?<\/section>/g)].map((m) => m[0]);
    assert.equal(sections.length, 5);
    sections.forEach((s, i) => assert.match(s, /<details class="rv-how/, `секция ${i + 1} без пояснения`));
    const loose = visibleHtml.replace(/<details[\s\S]*?<\/details>/g, '');
    assert.ok(!/<ul>|<li>/.test(loose), 'правила висят на экране вне раскрывашки');
    assert.ok(!/Похожая карточка|EAN-13|стоп-слов/.test(loose), 'пояснение расчёта вне раскрывашки');
    assert.ok(!/<details[^>]*\sopen/.test(html), 'раскрывашка открыта по умолчанию');
    const listHow = /<section class="rv-panel rv-list"[\s\S]*?<\/section>/.exec(html)[0];
    for (const topic of ['Закрытие', 'Название', 'Поставщик', 'Кол-во', 'Штрихкод для iiko', 'нашлась сама']) {
        assert.ok(listHow.includes(topic), `в пояснении таблицы нет «${topic}»`);
    }
});

test('единицы не спрятаны: «шт.» у количества в строке и в приёмках', () => {
    assert.match(js, /fmtInt\(row\.qty\) \+ ' шт\.'/);
    assert.match(js, /fmtInt\(c\.units\) \+ ' шт\.'/);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

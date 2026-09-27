/**
 * Общий фундамент раздела «Гости» (/content-plan, /reviews, полоса на /guests):
 *
 *     node tests/test_guest_hub_render.mjs
 *
 * Что проверяется и зачем (браузера в проверке нет, ловим то, что иначе видно
 * только глазами или только в проде):
 *   1. сайдбар: три ссылки раздела «Гости» стоят своей секцией сразу после
 *      «Аналитики», а /guests из «Аналитики» ушёл (иначе пункт задвоится);
 *   2. partials шапки и полосы объявляют ровно те id / data-атрибуты, которые
 *      ищет static/js/guest_hub/common.js — расхождение молча оставляет полосу
 *      с прочерками;
 *   3. /guests подключает полосу внутри .gh-scope (токены цвета живут на нём)
 *      и грузит hub.css / common.js с ?v={{ app_version }};
 *   4. стиль: без эмодзи; в hub.css нет цвета мимо двух блоков токенов, тёмная
 *      тема переопределяет те же токены; каждый класс gh-*, который пишут
 *      partials и common.js, описан в hub.css;
 *   5. common.js исполняется (в vm с поддельными window/document) и отдаёт
 *      API window.GH из спецификации; чистые помощники дают документированные
 *      значения; полоса «требует внимания» заполняется и прячет нулевые
 *      счётчики; GH.api разбирает ошибки сервера.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(ROOT, p));

const FILES = {
    css: 'static/guest_hub/hub.css',
    js: 'static/js/guest_hub/common.js',
    head: 'templates/shared/guest_hub_head.html',
    strip: 'templates/shared/guest_hub_strip.html',
    nav: 'templates/shared/nav.html',
    guests: 'templates/guests.html',
};
const css = read(FILES.css);
const js = read(FILES.js);
const head = read(FILES.head);
const strip = read(FILES.strip);
const nav = read(FILES.nav);
const guests = read(FILES.guests);

// ---------------------------------------------------------------- мини-раннер
// Тесты бывают асинхронными (промисы GH.api / loadAttention), поэтому
// выполняются по очереди с await, а не сразу при объявлении.
const queue = [];
function test(name, fn) { queue.push({ name, fn }); }

// ---------------------------------------------------------------- 1. сайдбар

function navSections(src) {
    // [{label, body}] — текст между подписью секции и следующей подписью.
    const re = /<div class="sidebar-section-label">([^<]+)<\/div>/g;
    const marks = [];
    let m;
    while ((m = re.exec(src)) !== null) marks.push({ label: m[1].trim(), at: m.index, end: re.lastIndex });
    return marks.map((s, i) => ({
        label: s.label,
        body: src.slice(s.end, i + 1 < marks.length ? marks[i + 1].at : src.length),
    }));
}

test('сайдбар: секция «Гости» сразу после «Аналитики»', () => {
    const labels = navSections(nav).map((s) => s.label);
    const ia = labels.indexOf('Аналитика');
    const ig = labels.indexOf('Гости');
    assert.ok(ia >= 0, 'нет секции «Аналитика»');
    assert.ok(ig >= 0, 'нет секции «Гости»');
    assert.equal(ig, ia + 1, `«Гости» должна идти сразу после «Аналитики», порядок: ${labels.join(', ')}`);
});

test('сайдбар: в «Гостях» три ссылки по порядку, /guests ушёл из «Аналитики»', () => {
    const sections = navSections(nav);
    const guestsSec = sections.find((s) => s.label === 'Гости');
    const hrefs = [...guestsSec.body.matchAll(/href="([^"]+)"/g)].map((m) => m[1]);
    assert.deepEqual(hrefs, ['/content-plan', '/reviews', '/guests'],
        `ссылки секции «Гости»: ${hrefs.join(', ')}`);
    for (const label of ['Контент-план', 'Отзывы', 'Маркетинг']) {
        assert.ok(guestsSec.body.includes(label), `нет подписи «${label}»`);
    }
    const analytics = sections.find((s) => s.label === 'Аналитика');
    assert.ok(!analytics.body.includes('href="/guests"'), '/guests остался в «Аналитике»');
    const all = (nav.match(/href="\/guests"/g) || []).length;
    assert.equal(all, 1, `ссылка на /guests в меню должна быть одна, найдено ${all}`);
});

test('сайдбар: у каждой ссылки раздела своя SVG-иконка в общем стиле', () => {
    const body = navSections(nav).find((s) => s.label === 'Гости').body;
    const links = body.split('<a ').slice(1);
    assert.equal(links.length, 3);
    for (const l of links) {
        assert.ok(/<span class="sidebar-link-icon">\s*<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"/.test(l),
            'иконка не в стиле остальных пунктов меню');
    }
    // «Маркетинг» переехал с той же иконкой, что была в «Аналитике».
    assert.ok(body.includes('<rect x="2" y="5" width="20" height="14" rx="2"/>'), 'иконка «Маркетинга» сменилась');
});

// ---------------------------------------------------------------- 2. partials

test('шапка раздела: бургер, заголовок, подзаголовок, логотип и полоса', () => {
    assert.ok(head.includes('id="ghBurger"'), 'нет #ghBurger (его ищет GH.initHeader)');
    assert.ok(head.includes('{{ hub_title'), 'заголовок не из hub_title');
    assert.ok(/\{% if hub_subtitle %\}/.test(head), 'подзаголовок не из hub_subtitle');
    assert.ok(head.includes('class="gh-logo"'), 'нет логотипа');
    assert.ok(head.includes("{% include 'shared/guest_hub_strip.html' %}"), 'шапка не подключает полосу');
});

test('полоса: вкладки раздела ведут на три страницы и подсвечиваются по hub_active', () => {
    const tabs = [['content', '/content-plan', 'Контент-план'],
                  ['reviews', '/reviews', 'Отзывы'],
                  ['guests', '/guests', 'Маркетинг']];
    for (const [key, href, label] of tabs) {
        const re = new RegExp(`<a class="gh-tab\\{% if hub_active == '${key}' %\\} is-active\\{% endif %\\}" href="${href}"[^>]*>${label}</a>`);
        assert.ok(re.test(strip), `вкладка ${label} (${key} -> ${href}) объявлена не так`);
    }
});

// Счётчики полосы: ключ -> [ссылка, прячется при нуле]. Ссылки — как в
// разметке (& в атрибуте записан как &amp;).
// «Отзывы без ответа» считаются за любую дату, поэтому ведут на «За всё
// время» (month=all): без него страница открывала текущий месяц, и отзывы,
// ждущие дольше всех, пропадали из списка при живом счётчике (ревью 2026-09-27).
const ATTN = {
    reviews_unanswered: ['/reviews?status=new&amp;month=all', false],
    publications_today: ['/content-plan?view=calendar', false],
    delivery_errors: ['/content-plan?state=failed', true],
    overdue: ['/content-plan?state=overdue', true],
};

function stripItems(src) {
    const out = {};
    for (const m of src.matchAll(/<a class="gh-attn-item" data-attn="([a-z_]+)"([^>]*)>([\s\S]*?)<\/a>/g)) {
        const href = /href="([^"]+)"/.exec(m[2]);
        out[m[1]] = {
            href: href ? href[1] : null,
            hidden: /\shidden(\s|$)/.test(m[2]),
            tip: /data-tip="[^"]{20,}"/.test(m[2]),
            hasN: m[3].includes('class="gh-attn-n"'),
            label: (/<span class="gh-attn-l">([^<]+)<\/span>/.exec(m[3]) || [])[1] || null,
        };
    }
    return out;
}

test('полоса «требует внимания»: #ghAttention, четыре счётчика со ссылками и подсказками', () => {
    assert.ok(strip.includes('id="ghAttention"'), 'нет #ghAttention');
    assert.ok(strip.includes('data-attn-scope'), 'нет подписи области (data-attn-scope)');
    const items = stripItems(strip);
    assert.deepEqual(Object.keys(items).sort(), Object.keys(ATTN).sort(), 'набор счётчиков не совпал');
    for (const [key, [href, hideZero]] of Object.entries(ATTN)) {
        const it = items[key];
        assert.equal(it.href, href, `${key}: ссылка ${it.href}`);
        assert.equal(it.hidden, hideZero, `${key}: исходная видимость`);
        assert.ok(it.tip, `${key}: нет подсказки с определением`);
        assert.ok(it.hasN, `${key}: нет .gh-attn-n для числа`);
        assert.ok(it.label, `${key}: нет подписи .gh-attn-l`);
    }
});

test('common.js и полоса согласованы: те же ключи счётчиков, те же id', () => {
    const tone = /var ATTN_TONE = \{([\s\S]*?)\};/.exec(js);
    assert.ok(tone, 'нет таблицы тонов ATTN_TONE');
    const keys = [...tone[1].matchAll(/([a-z_]+):/g)].map((m) => m[1]).sort();
    assert.deepEqual(keys, Object.keys(ATTN).sort(), 'ключи ATTN_TONE не совпадают со счётчиками полосы');
    const hide = /var ATTN_HIDE_WHEN_ZERO = \{([^}]*)\}/.exec(js);
    const hideKeys = [...hide[1].matchAll(/([a-z_]+):/g)].map((m) => m[1]).sort();
    assert.deepEqual(hideKeys, ['delivery_errors', 'overdue'], 'прячутся при нуле не те счётчики');
    // Все id, которые common.js ищет через byId, есть в partials (кроме
    // #sidebar-toggle — он из shared/nav.html).
    const ids = new Set([...js.matchAll(/byId\('([^']+)'\)/g)].map((m) => m[1]));
    assert.ok(ids.has('ghAttention') && ids.has('ghBurger'), 'common.js не ищет узлы полосы');
    for (const id of ids) {
        const src = id === 'sidebar-toggle' ? nav : head + strip;
        assert.ok(src.includes(`id="${id}"`), `узла #${id} нет в разметке`);
    }
    assert.ok(js.includes("'/api/guest-hub/attention?bar='"), 'полоса ходит не в /api/guest-hub/attention');
});

// ---------------------------------------------------------------- 3. /guests

test('/guests: полоса в своём .gh-scope в начале .guests-wrap, hub_active = guests', () => {
    const wrapAt = guests.indexOf('<div class="guests-wrap">');
    assert.ok(wrapAt > 0, 'нет .guests-wrap');
    const inc = guests.indexOf("{% include 'shared/guest_hub_strip.html' %}");
    assert.ok(inc > wrapAt, 'полоса не подключена внутри .guests-wrap');
    assert.ok(inc < guests.indexOf('class="guests-controls"'), 'полоса должна стоять до панели периода');
    const before = guests.slice(wrapAt, inc);
    assert.ok(/\{% set hub_active = 'guests' %\}/.test(before), 'нет hub_active = guests');
    // Обёртка с gh-scope открыта перед include и ещё не закрыта.
    const scopeAt = before.lastIndexOf('<div class="gh-scope');
    assert.ok(scopeAt >= 0, 'полоса не обёрнута в .gh-scope');
    assert.ok(!before.slice(scopeAt).includes('</div>'), 'обёртка .gh-scope закрыта до полосы');
    assert.ok(!guests.includes("guest_hub_head.html"), 'на /guests своя шапка — шапку раздела подключать не нужно');
});

test('/guests: hub.css и common.js раздела подключены с ?v={{ app_version }}', () => {
    assert.match(guests, /href="\/static\/guest_hub\/hub\.css\?v=\{\{ app_version \}\}"/, 'hub.css без ?v');
    assert.match(guests, /src="\/static\/js\/guest_hub\/common\.js\?v=\{\{ app_version \}\}"/, 'common.js раздела без ?v');
    // Файл раздела не должен путаться со своим common.js страницы /guests.
    assert.ok(guests.includes('/static/js/guests/common.js'), 'пропал common.js самой страницы');
    for (const f of [FILES.css, FILES.js]) assert.ok(exists(f), `нет файла ${f}`);
});

// ---------------------------------------------------------------- 4. стиль

// Эмодзи: символы с эмодзи-свойством, селектор варианта эмодзи, звёзды.
const EMOJI = /[\p{Extended_Pictographic}\u{FE0F}\u{2605}\u{2606}\u{2B50}]/u;

test('без эмодзи и звёзд в файлах раздела', () => {
    for (const [name, src] of Object.entries({ css, js, head, strip, nav, guests })) {
        const lines = src.split('\n');
        const bad = lines.map((l, i) => [i + 1, l]).filter(([, l]) => EMOJI.test(l));
        assert.deepEqual(bad.map(([n]) => n), [], `${name}: эмодзи в строках ${bad.map(([n]) => n).join(', ')}`);
    }
});

function stripComments(src) { return src.replace(/\/\*[\s\S]*?\*\//g, ''); }
// Блок правила, начиная с селектора: '.gh-scope {' -> текст до парной '}'.
function ruleBlock(src, selectorStart) {
    const at = src.indexOf(selectorStart);
    if (at < 0) return null;
    const open = src.indexOf('{', at);
    let depth = 0;
    for (let i = open; i < src.length; i++) {
        if (src[i] === '{') depth++;
        else if (src[i] === '}' && --depth === 0) return { start: at, end: i + 1, text: src.slice(at, i + 1) };
    }
    return null;
}
const cssNoComments = stripComments(css);
const LIGHT = ruleBlock(cssNoComments, '.gh-scope {');
const DARK = ruleBlock(cssNoComments, '[data-theme="dark"] .gh-scope');

test('hub.css: цвета только в двух блоках токенов', () => {
    assert.ok(LIGHT && DARK, 'не найдены блоки токенов');
    const rest = cssNoComments.slice(0, LIGHT.start) +
        cssNoComments.slice(LIGHT.end, DARK.start) + cssNoComments.slice(DARK.end);
    const hex = [...rest.matchAll(/#[0-9A-Fa-f]{3,8}\b/g)].map((m) => m[0]);
    assert.deepEqual(hex, [], `HEX вне токенов: ${hex.join(', ')}`);
    const fn = [...rest.matchAll(/\b(rgba?|hsla?)\(/g)].map((m) => m[0]);
    assert.deepEqual(fn, [], `цветовые функции вне токенов: ${fn.join(', ')}`);
});

test('hub.css: тёмная тема переопределяет те же цветовые токены', () => {
    const names = (block) => new Set([...block.matchAll(/(--gh-[\w-]+)\s*:/g)].map((m) => m[1]));
    const light = names(LIGHT.text);
    const dark = names(DARK.text);
    // Радиусы, высота контролов и шрифты от темы не зависят.
    const themeless = (n) => n.startsWith('--gh-r-') || n === '--gh-ctl-h' || n === '--gh-sans' || n === '--gh-mono';
    const missing = [...light].filter((n) => !themeless(n) && !dark.has(n));
    assert.deepEqual(missing, [], `в тёмной теме не заданы: ${missing.join(', ')}`);
    const extra = [...dark].filter((n) => !light.has(n));
    assert.deepEqual(extra, [], `в тёмной теме лишние токены: ${extra.join(', ')}`);
    assert.ok(DARK.text.includes('.gh-scope[data-theme="dark"]'), 'нет второго селектора тёмной темы');
});

test('hub.css: токены на .gh-scope, общая шапка скрыта только на body.gh-page', () => {
    assert.ok(!/(^|\n)\s*(body|:root)\s*\{[^}]*--gh-/.test(cssNoComments), 'токены объявлены не на .gh-scope');
    assert.match(cssNoComments, /body\.gh-page \.header-bar\s*\{\s*display:\s*none/, 'общая .header-bar не скрыта');
    // Ни одного правила на голые теги: полоса встраивается в /guests и не
    // должна трогать остальную страницу.
    // После '}' или '{' (первое правило внутри @media) до следующей '{'.
    const selectors = [...cssNoComments.matchAll(/(^|[{}])\s*([^{}@;]+)\{/g)].map((m) => m[2].trim());
    const bare = selectors.flatMap((s) => s.split(',').map((x) => x.trim()))
        .filter((s) => s && !/^(from|to|\d+%)/.test(s))
        .filter((s) => !/\.gh-|\[data-theme/.test(s) && !/^html\.gh-/.test(s));
    assert.deepEqual(bare, [], `селекторы без gh-: ${bare.join(' | ')}`);
});

test('каждый класс gh-* из partials и common.js описан в hub.css', () => {
    const known = new Set([...css.matchAll(/\.(gh-[\w-]+)/g)].map((m) => m[1]));
    const used = new Set();
    // (?<![\w-]) — чтобы не взять хвост data-gh-close / data-gh-keep;
    // (?![\w-]) — чтобы не взять склейку 'gh-tone-' + tone как класс gh-tone.
    for (const src of [js, head, strip, guests]) {
        for (const m of src.matchAll(/(?<![\w-])(gh-[a-z0-9-]*[a-z0-9])(?![\w-])/g)) used.add(m[1]);
    }
    // Не классы: ключ localStorage и имена событий пишутся иначе (gh.bar,
    // gh:open), но на всякий случай — их здесь нет.
    const missing = [...used].filter((c) => !known.has(c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
    for (const state of ['is-on', 'is-hot', 'is-loading', 'is-out', 'is-right', 'is-active']) {
        assert.ok(css.includes('.' + state), `состояние .${state} не описано`);
    }
});

test('hub.css: компоненты из спецификации на месте', () => {
    const need = ['.gh-wrap', '.gh-head', '.gh-burger', '.gh-tabs', '.gh-tab', '.gh-attn', '.gh-filters',
        '.gh-pick', '.gh-menu', '.gh-btn', '.gh-btn-primary', '.gh-btn-ghost', '.gh-btn-danger', '.gh-chip',
        '.gh-badge', '.gh-input', '.gh-select', '.gh-textarea', '.gh-drawer', '.gh-modal', '.gh-toast',
        '.gh-banner', '.gh-empty', '.gh-tipbox', '.gh-seg', '.gh-check', '.gh-embed'];
    const missing = need.filter((c) => !new RegExp(`\\${c}(?![\\w-])`).test(css));
    assert.deepEqual(missing, [], `нет компонентов: ${missing.join(', ')}`);
    for (const tone of ['muted', 'warning', 'accent', 'success', 'danger']) {
        assert.ok(css.includes(`.gh-tone-${tone} {`), `нет тона ${tone}`);
    }
    assert.match(css, /@media \(max-width: 768px\)/, 'нет телефонного брейкпоинта 768px');
    assert.match(css, /@font-face\s*\{\s*font-family: 'IBM Plex Sans'/, 'нет @font-face IBM Plex Sans');
});

// ---------------------------------------------------------------- 5. common.js

test('common.js — обычный IIFE в стиле ES5 (без let/const/стрелок/классов)', () => {
    const code = js.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
    assert.ok(code.includes("'use strict'"), "нет 'use strict'");
    assert.ok(!/\b(let|const|class)\s/.test(code), 'встречаются let/const/class');
    assert.ok(!/=>/.test(code), 'встречаются стрелочные функции');
    assert.ok(!/`/.test(code), 'встречаются шаблонные строки');
});

// Минимальный DOM: только то, что трогает common.js.
class FakeClassList {
    constructor() { this.s = new Set(); }
    add(...c) { c.forEach((x) => this.s.add(x)); }
    remove(...c) { c.forEach((x) => this.s.delete(x)); }
    toggle(c, on) { const v = on === undefined ? !this.s.has(c) : !!on; if (v) this.s.add(c); else this.s.delete(c); return v; }
    contains(c) { return this.s.has(c); }
}
class FakeEl {
    constructor(tag, attrs) {
        this.tagName = (tag || 'div').toUpperCase();
        this.attrs = Object.assign({}, attrs || {});
        this.classList = new FakeClassList();
        (this.attrs.class || '').split(/\s+/).filter(Boolean).forEach((c) => this.classList.add(c));
        this.hidden = 'hidden' in this.attrs;
        this.children = [];
        this.textContent = '';
        this.listeners = {};
        this.style = {};
    }
    getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; }
    setAttribute(n, v) { this.attrs[n] = String(v); }
    hasAttribute(n) { return n in this.attrs; }
    removeAttribute(n) { delete this.attrs[n]; }
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
    click() { (this.listeners.click || []).forEach((f) => f({ target: this })); }
    appendChild(c) { this.children.push(c); return c; }
    matches(sel) {
        let m;
        if ((m = /^\.([\w-]+)$/.exec(sel))) return this.classList.contains(m[1]);
        if ((m = /^\[([\w-]+)\]$/.exec(sel))) return this.hasAttribute(m[1]);
        return false;
    }
    all() { return this.children.flatMap((c) => [c, ...c.all()]); }
    querySelectorAll(sel) { return this.all().filter((e) => e.matches(sel)); }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}

// Узел #ghAttention строится из НАСТОЯЩЕГО partial: те же ключи, та же
// исходная видимость. Так тест ломается, если разметка и JS разойдутся.
function buildAttention() {
    const node = new FakeEl('div', { class: 'gh-attn is-loading', id: 'ghAttention' });
    node.appendChild(new FakeEl('span', { class: 'gh-attn-scope', 'data-attn-scope': '' }));
    for (const [key, it] of Object.entries(stripItems(strip))) {
        const a = new FakeEl('a', Object.assign({ class: 'gh-attn-item', 'data-attn': key },
            it.hidden ? { hidden: '' } : {}));
        a.appendChild(new FakeEl('b', { class: 'gh-attn-n' }));
        const l = new FakeEl('span', { class: 'gh-attn-l' });
        l.textContent = it.label;
        a.appendChild(l);
        node.appendChild(a);
    }
    return node;
}

// Объекты из vm-контекста — другого «мира» (свои Object/Array), deepStrictEqual
// сравнивает и прототипы. Сравниваем данные через JSON.
const plain = (x) => JSON.parse(JSON.stringify(x));

function jsonResponse(status, body) {
    const text = typeof body === 'string' ? body : JSON.stringify(body);
    return { ok: status >= 200 && status < 300, status, text: () => Promise.resolve(text) };
}

// Загружает common.js в отдельном vm-контексте. dom=false — как в Node без
// браузера (document нет), dom=true — с поддельным документом и узлами полосы.
function loadCommon({ dom = false, storage = 'memory', respond } = {}) {
    const calls = [];
    const store = {};
    let localStorage;
    if (storage === 'memory') {
        localStorage = {
            getItem: (k) => (k in store ? store[k] : null),
            setItem: (k, v) => { store[k] = String(v); },
            removeItem: (k) => { delete store[k]; },
        };
    } else if (storage === 'throws') {
        localStorage = {
            getItem() { throw new Error('SecurityError'); },
            setItem() { throw new Error('SecurityError'); },
            removeItem() { throw new Error('SecurityError'); },
        };
    }
    const window = {
        localStorage,
        addEventListener() {},
        innerWidth: 1440,
        innerHeight: 900,
        location: { search: '', pathname: '/content-plan', hash: '' },
        history: { replaceState() {}, pushState() {} },
    };
    const ids = {};
    let document;
    if (dom) {
        ids.ghAttention = buildAttention();
        ids.ghBurger = new FakeEl('button', { id: 'ghBurger' });
        ids['sidebar-toggle'] = new FakeEl('button', { id: 'sidebar-toggle' });
        ids['sidebar-toggle'].clicked = 0;
        ids['sidebar-toggle'].addEventListener('click', () => { ids['sidebar-toggle'].clicked++; });
        document = {
            readyState: 'complete',
            documentElement: new FakeEl('html'),
            body: new FakeEl('body'),
            getElementById: (id) => ids[id] || null,
            createElement: (t) => new FakeEl(t),
            addEventListener() {},
            activeElement: null,
        };
    }
    const sandbox = {
        window,
        console, setTimeout, clearTimeout, Promise, JSON, Math, Date, Intl,
        URLSearchParams, FormData, Error, String, Number, Object, Array, isFinite,
        fetch(url, init) {
            calls.push({ url, init });
            return respond ? respond(url, init) : Promise.reject(new Error('offline'));
        },
    };
    if (document) sandbox.document = document;
    const ctx = vm.createContext(sandbox);
    vm.runInContext(`${js}`, ctx, { filename: FILES.js });
    // Файл сам кладёт себя в root: у нас root = window (есть в контексте).
    const GH = window.GH;
    assert.ok(GH, 'common.js не положил GH в window');
    return { GH, window, ids, calls, store };
}

test('common.js грузится через require (module.exports) и в «браузере» (window.GH)', () => {
    const require = createRequire(import.meta.url);
    const GHm = require(path.join(ROOT, FILES.js));
    assert.equal(typeof GHm.fmtDate, 'function', 'module.exports не отдаёт GH');
    const { GH } = loadCommon();
    assert.equal(typeof GH.api, 'function');
});

test('GH отдаёт весь API из спецификации (п. 3)', () => {
    const { GH } = loadCommon();
    const fns = ['api', 'esc', 'barName', 'barShort', 'fmtDate', 'fmtDateShort', 'fmtDateTime',
        'monthLabel', 'addMonths', 'mskNow', 'fmtHours', 'plural', 'fmtNum', 'getBar', 'setBar',
        'toast', 'confirm', 'prompt', 'openDrawer', 'closeDrawer', 'loadAttention', 'initHeader',
        // дополнительные, на которые опираются страницы раздела
        'openModal', 'closeModal', 'openMenu', 'closeMenus', 'toggleMenu', 'setSeg', 'bindSeg',
        'debounce', 'copyText', 'params', 'setParams', 'weekday', 'addDays', 'daysInMonth', 'toneClass'];
    const missing = fns.filter((f) => typeof GH[f] !== 'function');
    assert.deepEqual(missing, [], `нет функций: ${missing.join(', ')}`);
    assert.deepEqual(plain(GH.CHANNEL_NAMES), { telegram: 'Telegram', instagram: 'Instagram', bot: 'Бот' });
    assert.deepEqual(plain(GH.CHANNEL_SHORT), { telegram: 'TG', instagram: 'IG', bot: 'Бот' });
});

test('GH.BARS — ключи и порядок core/venues_config.PHYSICAL_VENUES, имена из спецификации', () => {
    const { GH } = loadCommon();
    const py = read('core/venues_config.py');
    const m = /PHYSICAL_VENUES = \[([^\]]+)\]/.exec(py);
    const keys = [...m[1].matchAll(/'([a-z]+)'/g)].map((x) => x[1]);
    assert.deepEqual(plain(GH.BARS.map((b) => b.key)), keys, 'ключи баров разошлись с venues_config');
    assert.deepEqual(plain(GH.BARS), [
        { key: 'bolshoy', name: 'Большой пр. В.О', short: 'ВО' },
        { key: 'ligovskiy', name: 'Лиговский', short: 'Лиг' },
        { key: 'kremenchugskaya', name: 'Кременчугская', short: 'Крем' },
        { key: 'varshavskaya', name: 'Варшавская', short: 'Вар' },
    ]);
    assert.equal(GH.barName('all'), 'Вся сеть');
    assert.equal(GH.barShort('all'), 'Сеть');
    assert.equal(GH.barName(''), 'Все бары');
    assert.equal(GH.barShort(''), 'Все');
    assert.equal(GH.barName('bolshoy'), 'Большой пр. В.О');
    assert.equal(GH.barShort('ligovskiy'), 'Лиг');
    assert.equal(GH.barShort('nowhere'), 'nowhere');
});

test('даты: fmtDate, fmtDateShort, fmtDateTime, monthLabel, weekday', () => {
    const { GH } = loadCommon();
    assert.equal(GH.fmtDate('2026-10-09'), '9 октября');
    assert.equal(GH.fmtDate('2026-10-09', true), '9 октября 2026');
    assert.equal(GH.fmtDate('2026-05-01'), '1 мая');
    assert.equal(GH.fmtDate(''), '');
    assert.equal(GH.fmtDate(null), '');
    assert.equal(GH.fmtDate('2026-02-30'), '2026-02-30', 'несуществующая дата отдаётся как есть');
    assert.equal(GH.fmtDateShort('2026-10-09'), '9 окт, пт');
    assert.equal(GH.fmtDateShort('2026-05-04'), '4 мая, пн');
    assert.equal(GH.fmtDateShort('2026-10-11'), '11 окт, вс');
    assert.equal(GH.fmtDateTime('2026-10-09T16:00'), '9 октября, 16:00');
    assert.equal(GH.fmtDateTime('2026-10-09 16:05:59'), '9 октября, 16:05');
    assert.equal(GH.fmtDateTime('2026-10-09'), '9 октября');
    assert.equal(GH.monthLabel('2026-10'), 'Октябрь 2026');
    assert.equal(GH.monthLabel('2027-01'), 'Январь 2027');
    assert.equal(GH.monthLabel('2026-13'), '2026-13');
    // 0 = понедельник ... 6 = воскресенье, как datetime.weekday() в Python.
    assert.equal(GH.weekday('2026-10-05'), 0);
    assert.equal(GH.weekday('2026-10-11'), 6);
    assert.equal(GH.daysInMonth('2028-02'), 29);
    assert.equal(GH.addDays('2026-10-30', 3), '2026-11-02');
});

test('addMonths: переходы через год в обе стороны', () => {
    const { GH } = loadCommon();
    assert.equal(GH.addMonths('2026-10', -1), '2026-09');
    assert.equal(GH.addMonths('2026-12', 1), '2027-01');
    assert.equal(GH.addMonths('2026-01', -1), '2025-12');
    assert.equal(GH.addMonths('2026-10', 14), '2027-12');
    assert.equal(GH.addMonths('2026-10', -22), '2024-12');
    assert.equal(GH.addMonths('2026-10', 0), '2026-10');
    assert.equal(GH.addMonths('bad', 1), null);
});

test('mskNow: московское время (UTC+3) через Intl, граница суток и месяца', () => {
    const { GH } = loadCommon();
    // 30.09.2026 21:30 UTC = 01.10.2026 00:30 МСК.
    const r = GH.mskNow(new Date(Date.UTC(2026, 8, 30, 21, 30)));
    assert.equal(r.date, '2026-10-01');
    assert.equal(r.time, '00:30');
    assert.equal(r.month, '2026-10');
    assert.equal(r.datetime, '2026-10-01T00:30');
    const r2 = GH.mskNow(new Date(Date.UTC(2026, 11, 31, 12, 5)));
    assert.deepEqual([r2.date, r2.time, r2.month], ['2026-12-31', '15:05', '2026-12']);
});

test('plural: 1 / 2-4 / 5-20 и 11-14 как «много»', () => {
    const { GH } = loadCommon();
    const p = (n) => GH.plural(n, 'отзыв', 'отзыва', 'отзывов');
    assert.deepEqual([0, 1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 104, 111, 112].map(p),
        ['отзывов', 'отзыв', 'отзыва', 'отзыва', 'отзывов', 'отзывов', 'отзывов', 'отзывов',
         'отзыв', 'отзыва', 'отзывов', 'отзыв', 'отзыва', 'отзывов', 'отзывов']);
});

test('fmtHours: «< 1 ч», целые часы до 48, дальше целые сутки (половина вверх)', () => {
    const { GH } = loadCommon();
    assert.equal(GH.fmtHours(0), '< 1 ч');
    assert.equal(GH.fmtHours(0.99), '< 1 ч');
    assert.equal(GH.fmtHours(-3), '< 1 ч', 'отрицательное (часы разошлись) считается нулём');
    assert.equal(GH.fmtHours(5), '5 ч');
    assert.equal(GH.fmtHours(4.5), '5 ч');
    assert.equal(GH.fmtHours(47.4), '47 ч');
    assert.equal(GH.fmtHours(48), '2 д');
    assert.equal(GH.fmtHours(72), '3 д');
    assert.equal(GH.fmtHours(83), '3 д');     // 3,46 сут
    assert.equal(GH.fmtHours(84), '4 д');     // ровно 3,5 сут -> вверх
    assert.equal(GH.fmtHours(null), '—');
    assert.equal(GH.fmtHours('x'), '—');
});

test('fmtNum: запятая, пробелы между тысячами, половина вверх по записи числа', () => {
    const { GH } = loadCommon();
    const NB = ' ';
    assert.equal(GH.fmtNum(4.25, 1), '4,3');
    assert.equal(GH.fmtNum(2.45, 1), '2,5', '2.45 в двоичном виде 2.4499…, но округляем по записи');
    assert.equal(GH.fmtNum(1.005, 2), '1,01');
    assert.equal(GH.fmtNum(4, 1), '4,0', 'ровно digits знаков');
    assert.equal(GH.fmtNum(1234567), `1${NB}234${NB}567`);
    assert.equal(GH.fmtNum(1234.5, 1), `1${NB}234,5`);
    assert.equal(GH.fmtNum(-2.5), '−3', 'минус типографский, от нуля');
    assert.equal(GH.fmtNum(-0.04, 1), '0,0', 'минус у нуля не пишется');
    assert.equal(GH.fmtNum(null), '—');
    assert.equal(GH.fmtNum(''), '—');
    assert.equal(GH.fmtNum(NaN), '—');
    assert.equal(GH.fmtNum('3.14159', 2), '3,14');
    // Большие числа JS пишет в экспоненте: строковый сдвиг давал NaN.
    assert.equal(GH.roundHalfUp(1e20, 2), 1e20);
    assert.ok(!GH.fmtNum(1e20, 2).includes('NaN'));
});

test('esc: экранирует пять символов HTML', () => {
    const { GH } = loadCommon();
    assert.equal(GH.esc(`<a href="x">'&`), '&lt;a href=&quot;x&quot;&gt;&#39;&amp;');
    assert.equal(GH.esc(null), '');
    assert.equal(GH.esc(0), '0');
});

test('getBar / setBar: общий фильтр в localStorage gh.bar, мусор и сбои -> «все бары»', () => {
    const { GH, store } = loadCommon();
    assert.equal(GH.getBar(), '');
    assert.equal(GH.setBar('ligovskiy'), 'ligovskiy');
    assert.equal(store['gh.bar'], 'ligovskiy', 'ключ localStorage не gh.bar');
    assert.equal(GH.getBar(), 'ligovskiy');
    assert.equal(GH.setBar('all'), '', "'all' — не фильтр, а размещение на сеть");
    assert.ok(!('gh.bar' in store), 'пустой выбор должен удалять ключ');
    store['gh.bar'] = 'hacked';
    assert.equal(GH.getBar(), '', 'неизвестное значение читается как «все бары»');
    const broken = loadCommon({ storage: 'throws' }).GH;
    assert.equal(broken.getBar(), '');
    assert.equal(broken.setBar('bolshoy'), 'bolshoy', 'сбой хранилища не должен ронять страницу');
    const none = loadCommon({ storage: 'none' }).GH;
    assert.equal(none.getBar(), '');
});

test('GH.api: JSON-тело, FormData как есть, ошибки сервера по-русски со статусом', async () => {
    const { GH, calls } = loadCommon({
        respond(url) {
            if (url === '/ok') return Promise.resolve(jsonResponse(200, { a: 1 }));
            if (url === '/empty') return Promise.resolve(jsonResponse(204, ''));
            if (url === '/conflict') return Promise.resolve(jsonResponse(409, { error: 'Этот месяц уже скопирован' }));
            if (url === '/down') return Promise.resolve(jsonResponse(503, { error: 'Хранилище недоступно', code: 'store_unavailable' }));
            if (url === '/html500') return Promise.resolve(jsonResponse(500, '<html>oops</html>'));
            return Promise.reject(new TypeError('Failed to fetch'));
        },
    });
    assert.deepEqual(plain(await GH.api('GET', '/ok')), { a: 1 });
    assert.equal(calls[0].init.method, 'GET');
    assert.equal(calls[0].init.body, undefined);

    await GH.api('post', '/ok', { title: 'x' });
    assert.equal(calls[1].init.method, 'POST');
    assert.equal(calls[1].init.headers['Content-Type'], 'application/json');
    assert.equal(calls[1].init.body, '{"title":"x"}');

    const fd = new FormData();
    fd.append('file', 'data');
    await GH.api('POST', '/ok', fd);
    assert.equal(calls[2].init.body, fd, 'FormData должна уйти как есть (multipart)');
    assert.ok(!('Content-Type' in calls[2].init.headers), 'для multipart Content-Type ставит браузер');

    assert.deepEqual(plain(await GH.api('DELETE', '/empty')), {});

    const fail = async (url) => { try { await GH.api('GET', url); } catch (e) { return e; } throw new Error('ожидалась ошибка'); };
    let e = await fail('/conflict');
    assert.equal(e.message, 'Этот месяц уже скопирован');
    assert.equal(e.status, 409);
    e = await fail('/down');
    assert.equal(e.status, 503);
    assert.equal(e.code, 'store_unavailable');
    e = await fail('/html500');
    assert.equal(e.status, 500);
    assert.match(e.message, /Ошибка сервера/);
    e = await fail('/offline');
    assert.equal(e.status, 0);
    assert.match(e.message, /Нет связи/);
});

test('GH.api: {keepalive: true} уходит в fetch, без опции — обычный запрос', async () => {
    // Сохранение при уходе со страницы (pagehide) шлётся с keepalive: обычный
    // fetch браузер обрывает вместе со страницей, и F5 терял набранное.
    const { GH, calls } = loadCommon({ respond: () => Promise.resolve(jsonResponse(200, { ok: true })) });
    await GH.api('PATCH', '/ok', { reply_draft: 'x' }, { keepalive: true });
    assert.equal(calls[0].init.keepalive, true, 'keepalive не передан в fetch');
    assert.equal(calls[0].init.body, '{"reply_draft":"x"}', 'тело потерялось');
    await GH.api('PATCH', '/ok', { reply_draft: 'y' });
    assert.ok(!('keepalive' in calls[1].init), 'без опции keepalive ставиться не должен');
    await GH.api('PATCH', '/ok', { reply_draft: 'z' }, {});
    assert.ok(!('keepalive' in calls[2].init), 'пустые опции — обычный запрос');
});

test('GH.onAttention: страница получает ответ полосы и узнаёт об ошибке', async () => {
    let answer = { reviews_unanswered: 4, publications_today: 1, delivery_errors: 0, overdue: 0 };
    let status = 200;
    const { GH } = loadCommon({ dom: true, respond: () => Promise.resolve(jsonResponse(status, answer)) });
    await new Promise((r) => setTimeout(r, 0));
    const got = [];
    // Ответ уже пришёл при автозапуске — подписчик получает его сразу.
    GH.onAttention((data, bar) => got.push([data && data.reviews_unanswered, bar]));
    assert.deepEqual(got, [[4, '']], 'подписчик не получил уже пришедший ответ');
    answer = { reviews_unanswered: 1 };
    GH.setBar('ligovskiy');
    await new Promise((r) => setTimeout(r, 0));
    assert.deepEqual(got[got.length - 1], [1, 'ligovskiy'], 'новый ответ не дошёл, или бар не тот');
    status = 500;
    await GH.loadAttention();
    assert.deepEqual(got[got.length - 1], [null, null], 'об ошибке подписчик не узнал');
});

test('полоса «требует внимания»: числа, тона, прячет нулевые «ошибки» и «время вышло»', async () => {
    let answer = { reviews_unanswered: 3, publications_today: 0, delivery_errors: 0, overdue: 2 };
    const { GH, ids, calls } = loadCommon({
        dom: true,
        respond: () => Promise.resolve(jsonResponse(200, answer)),
    });
    // Автозапуск: при загрузке уже был запрос с пустым баром.
    assert.equal(calls.length, 1, 'полоса не загрузилась сама');
    assert.equal(calls[0].url, '/api/guest-hub/attention?bar=');
    await new Promise((r) => setTimeout(r, 0));
    const node = ids.ghAttention;
    const item = (k) => node.querySelectorAll('[data-attn]').find((x) => x.getAttribute('data-attn') === k);
    const n = (k) => item(k).querySelector('.gh-attn-n').textContent;
    assert.equal(node.hidden, false);
    assert.ok(!node.classList.contains('is-loading'), 'не снят is-loading');
    assert.equal(n('reviews_unanswered'), '3');
    assert.ok(item('reviews_unanswered').classList.contains('is-hot'));
    assert.ok(item('reviews_unanswered').classList.contains('gh-tone-warning'));
    assert.equal(n('publications_today'), '0');
    assert.ok(!item('publications_today').classList.contains('is-hot'), 'ноль не подсвечивается');
    assert.equal(item('publications_today').hidden, false, '«Публикаций сегодня» видна и при нуле');
    assert.equal(item('delivery_errors').hidden, true, 'ноль ошибок должен прятаться');
    assert.equal(item('overdue').hidden, false);
    assert.ok(item('overdue').classList.contains('gh-tone-warning'));
    assert.match(item('overdue').getAttribute('aria-label'), /Время вышло: 2/);

    // Смена бара: запрос с баром, подпись области — имя бара; null -> прочерк и скрытие.
    answer = { reviews_unanswered: 0, publications_today: null, delivery_errors: 1, overdue: null };
    GH.setBar('varshavskaya');
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(calls[calls.length - 1].url, '/api/guest-hub/attention?bar=varshavskaya');
    assert.equal(node.querySelector('[data-attn-scope]').textContent, 'Варшавская');
    assert.equal(n('publications_today'), '—');
    assert.equal(item('overdue').hidden, true, 'null у «время вышло» -> скрыто');
    assert.equal(item('delivery_errors').hidden, false);
    assert.ok(item('delivery_errors').classList.contains('gh-tone-danger'));
    assert.ok(!item('reviews_unanswered').classList.contains('gh-tone-warning'), 'тон не снят при нуле');
});

test('полоса «требует внимания»: ошибка запроса молча прячет полосу', async () => {
    const { ids } = loadCommon({ dom: true, respond: () => Promise.resolve(jsonResponse(500, { error: 'x' })) });
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(ids.ghAttention.hidden, true);
});

test('бургер шапки открывает общий сайдбар (клик по #sidebar-toggle)', () => {
    const { GH, ids } = loadCommon({ dom: true, respond: () => Promise.resolve(jsonResponse(200, {})) });
    ids.ghBurger.click();
    assert.equal(ids['sidebar-toggle'].clicked, 1);
    GH.initHeader();                 // повторный вызов не вешает второй обработчик
    ids.ghBurger.click();
    assert.equal(ids['sidebar-toggle'].clicked, 2);
});

// ---------------------------------------------------------------- запуск

let passed = 0;
let failed = 0;
for (const { name, fn } of queue) {
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
console.log(`\n${passed} ok, ${failed} failed`);
process.exit(failed ? 1 : 0);

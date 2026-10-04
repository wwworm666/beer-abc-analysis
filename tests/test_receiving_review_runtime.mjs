/**
 * ЗАПУСК страницы «Разбор приёмок» (/receiving/review) в Node с DOM-стабом.
 *
 *     node tests/test_receiving_review_runtime.mjs
 *
 * Настоящий static/js/receiving/review.js исполняется в node:vm. Узлы страницы
 * создаются по id из templates/receiving_review.html (тег и hidden — как в
 * шаблоне), fetch отвечает маленький поддельный сервер по контракту раздела 7
 * спецификации (routes/receiving.py): GET /api/receiving/review с фильтрами,
 * PUT /api/receiving/review/<gtin>, GET /api/receiving/products, POST
 * /api/receiving/barcodes/refresh + GET /api/receiving/barcodes/status, GET
 * /api/receiving/<id>. Таймеры поддельные: опрос и пауза поиска прокручиваются
 * вручную. Стаб бросает исключение на любое обращение к innerHTML — страница
 * обязана строить DOM только через textContent (данные iiko и ЧЗ недоверенные).
 *
 * Тот же приём, что у tests/test_kitchen_runtime.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const JS = read('static/js/receiving/review.js');
const HTML = read('templates/receiving_review.html');

let passed = 0;
let failed = 0;
async function test(name, fn) {
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

// ---------------------------------------------------------------- DOM-стаб

const camel = (s) => s.replace(/-([a-z])/g, (m, c) => c.toUpperCase());

class El {
    constructor(tag) {
        this.tagName = String(tag).toUpperCase();
        this.nodeType = 1;
        this.id = '';
        this.children = [];
        this.parentNode = null;
        this._text = '';
        this.attributes = {};
        this.dataset = {};
        this.style = {};
        this.listeners = {};
        this.hidden = false;
        this.disabled = false;
        this.value = '';
        this.type = '';
        this.title = '';
        this.className = '';
        this.placeholder = '';
        this.colSpan = 1;
        this.maxLength = -1;
        this.scrolled = 0;
        this.blurred = 0;
    }
    get classList() {
        const self = this;
        const list = () => self.className.split(/\s+/).filter(Boolean);
        return {
            add(...names) { const s = new Set(list()); names.forEach((n) => s.add(n)); self.className = [...s].join(' '); },
            remove(...names) { self.className = list().filter((n) => !names.includes(n)).join(' '); },
            toggle(name, force) {
                const has = list().includes(name);
                const want = force === undefined ? !has : Boolean(force);
                if (want && !has) this.add(name);
                if (!want && has) this.remove(name);
                return want;
            },
            contains(name) { return list().includes(name); },
        };
    }
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
    set textContent(v) {
        this.children.forEach((c) => { c.parentNode = null; });
        this.children = [];
        this._text = v === null || v === undefined ? '' : String(v);
    }
    get innerHTML() { throw new Error('innerHTML читать нельзя: только textContent'); }
    set innerHTML(v) { throw new Error('innerHTML писать нельзя: только textContent'); }
    appendChild(child) {
        if (child.parentNode) child.parentNode.removeChild(child);
        child.parentNode = this;
        this.children.push(child);
        return child;
    }
    removeChild(child) {
        const i = this.children.indexOf(child);
        if (i >= 0) this.children.splice(i, 1);
        child.parentNode = null;
        return child;
    }
    setAttribute(name, value) {
        const v = String(value);
        this.attributes[name] = v;
        if (name === 'class') this.className = v;
        if (name === 'id') this.id = v;
        if (name.startsWith('data-')) this.dataset[camel(name.slice(5))] = v;
    }
    getAttribute(name) {
        if (name === 'class') return this.className;
        return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    }
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
    removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter((f) => f !== fn); }
    dispatch(type, init) {
        const event = Object.assign({
            type,
            target: this,
            defaultPrevented: false,
            preventDefault() { this.defaultPrevented = true; },
            stopPropagation() {},
        }, init || {});
        let node = this;
        while (node) {
            (node.listeners[type] || []).slice().forEach((fn) => fn.call(node, event));
            node = node.parentNode;
        }
        return event;
    }
    click(init) {
        if (this.disabled) return null;
        return this.dispatch('click', Object.assign({ button: 0 }, init || {}));
    }
    focus() { if (El.doc) El.doc.activeElement = this; }
    blur() { this.blurred++; if (El.doc && El.doc.activeElement === this) El.doc.activeElement = null; }
    select() {}
    scrollIntoView() { this.scrolled++; }
}

function walk(node, fn) {
    fn(node);
    node.children.forEach((c) => walk(c, fn));
}
function findAll(root, pred) {
    const out = [];
    walk(root, (n) => { if (n !== root && pred(n)) out.push(n); });
    return out;
}
const hasClass = (cls) => (n) => n.classList.contains(cls);
const byTag = (tag) => (n) => n.tagName === tag.toUpperCase();
const flat = (s) => String(s).replace(/[  ]/g, ' ');

// Узлы шаблона: каждый id из receiving_review.html со своим тегом и hidden.
function templateNodes() {
    const byId = {};
    for (const m of HTML.matchAll(/<(\w+)\b([^>]*?)\bid="([^"]+)"([^>]*)>/g)) {
        const node = new El(m[1]);
        node.id = m[3];
        const attrs = m[2] + ' ' + m[4];
        node.hidden = /\shidden(\s|$|>)/.test(' ' + attrs + ' ');
        const cls = /class="([^"]*)"/.exec(attrs);
        if (cls) node.className = cls[1];
        byId[m[3]] = node;
    }
    return byId;
}

// ---------------------------------------------------------------- данные

const IDX_MORNING = {
    built_at: '2026-10-03T07:30:05+03:00',
    age_minutes: 30,
    counts: { products: 9120, gtins: 4650, with_barcodes: 4200, deleted: 1300, archived: 800, duplicates: 12 },
    source: 'v2',
};
const IDX_FRESH = {
    built_at: '2026-10-03T10:02:00+03:00',
    age_minutes: 0,
    counts: { products: 9200, gtins: 4700, with_barcodes: 4260, deleted: 1300, archived: 801, duplicates: 11 },
    source: 'v2+xml',
};
const JOB_IDLE = { running: false, trigger: 'schedule', started_at: '2026-10-03T07:30:00+03:00',
                   finished_at: '2026-10-03T07:30:05+03:00', error: '', counts: null };

const XSS = '<img src=x onerror=alert(1)>';

function card(extra) {
    return Object.assign({ id: 'c-' + Math.random().toString(16).slice(2, 8), name: '', num: '', group: '',
                           supplier: '', unit: 'шт', deleted: false, archived: false, keg: false }, extra);
}

function baseRow(extra) {
    return Object.assign({
        gtin: '', barcode: '', status: 'new', state: 'open', resolution: '',
        cards: [], candidates: [], chz: {}, supplier: '', supplier_hint: '', note: '',
        qty: 0, receipts: [],
        first_seen_at: '2026-10-02T15:00:00+03:00', last_seen_at: '2026-10-03T09:00:00+03:00',
        classified_at: '2026-10-03T09:01:00+03:00', index_built_at: IDX_MORNING.built_at,
        updated_at: '2026-10-03T09:01:00+03:00', updated_by: '', resolved_at: null, resolved_by: '',
        reopened: 0,
    }, extra);
}

function makeRows() {
    return [
        baseRow({
            gtin: '04650075420019', barcode: '4650075420019', status: 'new',
            chz: { name: 'Пиво светлое нефильтрованное «Жигулёвское Барное»', brand: 'Жигулёвское',
                   full_name: '', product_group: 'beer', volume: '0,5 л', package_type: 'bottle', source: 'product_info' },
            qty: 24, receipts: [{ id: 12, qty: 24, closed_at: '2026-10-03T09:00:00+03:00' }],
        }),
        baseRow({
            gtin: '04607043562301', barcode: '4607043562301', status: 'similar',
            chz: { name: 'Сидр "Mystery" яблочный ' + XSS, brand: 'Mystery', full_name: '', product_group: 'beer',
                   volume: '', package_type: '', source: 'cache' },
            candidates: [card({ name: 'Mystery Сидр Яблочный 0,5 ст', num: '00123', group: 'Бутылочное / Сидр',
                                supplier: 'Бирмаркет', score: 2 })],
            supplier: 'Бирмаркет', qty: 13, reopened: 2,
            receipts: [{ id: 12, qty: 6, closed_at: '2026-10-03T09:00:00+03:00' },
                       { id: 11, qty: 4, closed_at: '2026-10-02T18:00:00+03:00' },
                       { id: 10, qty: 2, closed_at: '2026-10-01T18:00:00+03:00' },
                       { id: 9, qty: 1, closed_at: '2026-09-30T18:00:00+03:00' }],
        }),
        baseRow({
            gtin: '00000046123456', barcode: '46123456', status: 'restore',
            cards: [card({ name: 'Старая карточка эля', num: '777', group: 'Архив товаров / Пиво',
                           supplier: 'Пивторг', deleted: true }),
                    card({ name: 'Старая карточка эля (2)', num: '778', group: 'Архив товаров',
                           supplier: 'Пивторг', archived: true })],
            supplier_hint: 'Пивторг', qty: 2, receipts: [{ id: 11, qty: 2, closed_at: '2026-10-02T18:00:00+03:00' }],
        }),
        baseRow({
            gtin: '14600000000005', barcode: '14600000000005', status: 'duplicate',
            chz: { name: 'Kriek Boon', brand: 'Boon', full_name: '', product_group: 'beer', volume: '20 л',
                   package_type: 'keg', source: 'stock' },
            cards: [card({ name: 'Kriek Boon КЕГ 20 л', num: '501', group: 'Kеги', supplier: 'Солодовня', keg: true }),
                    card({ name: 'Kriek Boon 20', num: '502', group: 'Kеги', supplier: 'Солодовня', keg: true })],
            supplier_hint: 'Солодовня', qty: 1, receipts: [{ id: 12, qty: 1, closed_at: '2026-10-03T09:00:00+03:00' }],
        }),
        baseRow({
            gtin: '04601234567891', barcode: '4601234567891', status: 'found', state: 'closed', resolution: 'found',
            chz: { name: 'Балтика 7', brand: 'Балтика', full_name: '', product_group: 'beer', volume: '0,45 л',
                   package_type: '', source: 'stock' },
            cards: [card({ name: 'Балтика 7 0,45 ст', num: '100', group: 'Бутылочное', supplier: 'Пивторг' })],
            supplier_hint: 'Пивторг', resolved_at: '2026-10-03T09:01:00+03:00', resolved_by: '',
            qty: 120, receipts: [{ id: 12, qty: 120, closed_at: '2026-10-03T09:00:00+03:00' }],
        }),
        baseRow({
            gtin: '04600000000017', barcode: '4600000000017', status: 'new', state: 'closed', resolution: 'done',
            chz: { name: 'Эль Тёмный', brand: '', full_name: '', product_group: '', volume: '', package_type: '', source: 'cache' },
            supplier: 'Солодовня', resolved_at: '2026-10-03T12:00:00+03:00', resolved_by: 'Анна',
            qty: 5, receipts: [{ id: 11, qty: 5, closed_at: '2026-10-02T18:00:00+03:00' }],
        }),
    ];
}

const RECEIPTS = [
    { id: 12, status: 'closed', note: '', created_at: '2026-10-03T08:00:00+03:00', created_by: 'Пётр',
      closed_at: '2026-10-03T09:00:00+03:00', closed_by: 'Пётр', process_state: 'done',
      processed_at: '2026-10-03T09:01:00+03:00', process_note: '',
      counts: { units: 340, gtins: 18, rejected: 2, repeats: 5, invoices: 1 },
      review: { open: 3, closed: 15, missing: 0 }, reviewed: false, can_delete: true },
    { id: 11, status: 'closed', note: 'Машина Бирмаркета', created_at: '2026-10-02T17:00:00+03:00', created_by: 'Пётр',
      closed_at: '2026-10-02T18:00:00+03:00', closed_by: 'Пётр', process_state: 'error',
      processed_at: '2026-10-02T18:01:00+03:00', process_note: 'Нет индекса iiko: Не настроено подключение к iiko',
      counts: { units: 11, gtins: 3, rejected: 0, repeats: 0, invoices: 0 },
      review: { open: 0, closed: 0, missing: 3 }, reviewed: false, can_delete: true },
    { id: 10, status: 'closed', note: '', created_at: '2026-10-01T10:00:00+03:00', created_by: 'Анна',
      closed_at: '2026-10-01T11:00:00+03:00', closed_by: 'Анна', process_state: 'done',
      processed_at: '2026-10-01T11:01:00+03:00', process_note: '',
      counts: { units: 24, gtins: 2, rejected: 0, repeats: 0, invoices: 0 },
      review: { open: 0, closed: 2, missing: 0 }, reviewed: true, can_delete: false },
];

const SUPPLIERS = ['Бирмаркет', 'Пивторг', 'Солодовня'];

// ---------------------------------------------------------------- поддельный сервер

const NETWORK = Symbol('network');

function makeServer() {
    const db = {
        rows: makeRows(),
        index: IDX_MORNING,
        job: JOB_IDLE,
        totalExtra: 0,
        statusQueue: [],       // ответы /barcodes/status по очереди
        refreshReply: { status: 202, data: { status: 'started' } },
        reviewReply: null,     // принудительный ответ /review (ошибки)
        putReply: null,        // принудительный ответ PUT
        deferred: [],          // запросы, ответ на которые тест отдаст сам
        holdNext: null,        // предикат: какой запрос задержать
        receipts: JSON.parse(JSON.stringify(RECEIPTS)),
        deleteReply: null,     // принудительный ответ DELETE /api/receiving/<id>
    };

    function counts(items) {
        const c = { open: { new: 0, similar: 0, restore: 0, duplicate: 0 }, open_total: 0, closed_total: 0 };
        items.forEach((r) => {
            if (r.state === 'open') {
                c.open_total++;
                if (r.status in c.open) c.open[r.status]++;
            } else {
                c.closed_total++;
            }
        });
        return c;
    }

    function review(url) {
        const u = new URL(url, 'http://test');
        const st = u.searchParams.get('state') || 'open';
        const statuses = (u.searchParams.get('status') || '').split(',').filter(Boolean);
        const rids = (u.searchParams.get('receipt_id') || '').split(',').filter(Boolean);
        const q = (u.searchParams.get('q') || '').toLowerCase().replace(/ё/g, 'е');
        let items = db.rows;
        if (rids.length) items = items.filter((r) => r.receipts.some((x) => rids.includes(String(x.id))));
        if (q) items = items.filter((r) => JSON.stringify(r).toLowerCase().replace(/ё/g, 'е').includes(q));
        const selected = items.filter((r) => (st === 'all' || r.state === st)
            && (!statuses.length || statuses.includes(r.status)));
        selected.sort((a, b) => (a.state === b.state ? 0 : a.state === 'open' ? -1 : 1));
        return { rows: selected, total: selected.length + db.totalExtra, counts: counts(items),
                 index: db.index, job: db.job, suppliers: SUPPLIERS, receipts: db.receipts };
    }

    function put(gtin, body) {
        if (db.putReply) return db.putReply;
        const row = db.rows.find((r) => r.gtin === gtin);
        if (!row) return { status: 404, data: { error: 'Строки разбора нет' } };
        if (body.supplier !== undefined) {
            if (body.supplier && !SUPPLIERS.includes(body.supplier)) {
                return { status: 400, data: { error: 'Поставщика нет в справочнике' } };
            }
            row.supplier = body.supplier;
        }
        if (body.note !== undefined) row.note = body.note;
        if (body.state === 'open') {
            Object.assign(row, { state: 'open', resolution: '', resolved_at: null, resolved_by: '' });
        } else if (body.state) {
            Object.assign(row, { state: 'closed', resolution: body.state, resolved_at: '2026-10-03T15:00:00+03:00',
                                 resolved_by: 'Бухгалтер' });
        }
        row.updated_by = 'Бухгалтер';
        return { status: 200, data: { row: JSON.parse(JSON.stringify(row)) } };
    }

    function products(url) {
        const u = new URL(url, 'http://test');
        const q = (u.searchParams.get('q') || '').toLowerCase();
        if (db.productsReply) return db.productsReply;
        const all = [
            card({ name: 'Жигулевское Барное 0,5 ст', num: '00042', group: 'Бутылочное / Лагеры', supplier: 'Пивторг',
                   barcodes: ['4650075420002', '04650075420002'] }),
            card({ name: 'Жигулевское Барное КЕГ 30 л', num: '00043', group: 'Kеги', supplier: 'Пивторг',
                   deleted: true, keg: true, barcodes: [] }),
        ];
        const words = q.split(/\s+/).filter(Boolean);
        const hit = all.filter((c) => words.every((w) => c.name.toLowerCase().includes(w)));
        return { status: 200, data: { cards: hit, index: db.index } };
    }

    function receipt(id) {
        if (id !== '12') return { status: 404, data: { error: 'Приёмки нет' } };
        return { status: 200, data: {
            receipt: RECEIPTS[0], lines: [], dm_keys: [], rows: [],
            recent: [
                { id: 5, gtin: null, kind: 'unknown', accepted: false, reason: 'bad_check_digit',
                  raw_short: '0104650075420018215abc', scanned_at: '2026-10-03T08:40:00+03:00', source: 'scanner', by: 'Пётр' },
                { id: 4, gtin: '04650075420019', kind: 'datamatrix', accepted: false, reason: 'repeat',
                  raw_short: '010465007542001921xyz', scanned_at: '2026-10-03T08:39:00+03:00', source: 'scanner', by: 'Пётр' },
                { id: 3, gtin: null, kind: 'sscc', accepted: false, reason: 'sscc',
                  raw_short: '00146000000000000017', scanned_at: '2026-10-03T08:30:00+03:00', source: 'camera', by: 'Пётр' },
                { id: 2, gtin: '04650075420019', kind: 'datamatrix', accepted: true, reason: '',
                  raw_short: '010465007542001921abc', scanned_at: '2026-10-03T08:20:00+03:00', source: 'scanner', by: 'Пётр' },
            ],
            invoices: [
                { name: 'r12_20261003T085000_ab12cd34.jpg', url: '/api/receiving/invoice/r12_20261003T085000_ab12cd34.jpg',
                  size: 120000, uploaded_at: '2026-10-03T08:50:00+03:00', uploaded_by: 'Пётр' },
                { name: 'bad', url: 'javascript:alert(1)', size: 1, uploaded_at: '', uploaded_by: '' },
            ],
        } };
    }

    function handle(method, url, body) {
        if (method === 'GET' && url.startsWith('/api/receiving/review?')) return db.reviewReply || { status: 200, data: review(url) };
        if (method === 'PUT' && url.startsWith('/api/receiving/review/')) return put(decodeURIComponent(url.split('/').pop()), body);
        if (method === 'GET' && url.startsWith('/api/receiving/products?')) return products(url);
        if (method === 'POST' && url === '/api/receiving/barcodes/refresh') return db.refreshReply;
        if (method === 'GET' && url === '/api/receiving/barcodes/status') {
            const next = db.statusQueue.length ? db.statusQueue.shift() : { status: 200, data: { index: db.index, job: db.job } };
            return next;
        }
        const m = /^\/api\/receiving\/(\d+)$/.exec(url);
        if (method === 'GET' && m) return receipt(m[1]);
        if (method === 'DELETE' && m) {
            if (db.deleteReply) return db.deleteReply;
            const gone = db.receipts.find((r) => String(r.id) === m[1]);
            if (!gone) return { status: 404, data: { error: 'Приёмка не найдена' } };
            db.receipts = db.receipts.filter((r) => r !== gone);
            return { status: 200, data: { deleted: true, receipt: gone, rows_deleted: 2, rows_kept: 1,
                                          invoices_deleted: gone.counts.invoices } };
        }
        return { status: 404, data: { error: 'нет маршрута ' + method + ' ' + url } };
    }

    return { db, handle };
}

// ---------------------------------------------------------------- окружение

function boot(opts) {
    const options = opts || {};
    const byId = templateNodes();
    const server = makeServer();
    // Подготовка «сервера» до запуска скрипта: первый запрос уходит сразу при старте.
    if (options.setup) options.setup(server.db);
    const calls = [];
    const clipboard = [];
    const urls = [];
    const execCalls = [];
    const confirms = [];
    let confirmAnswer = options.confirm !== false;
    let timers = [];
    let timerSeq = 0;
    const body = new El('body');
    const docListeners = {};

    const fetchStub = (url, init) => {
        const o = init || {};
        const method = String(o.method || 'GET').toUpperCase();
        const parsed = o.body ? JSON.parse(o.body) : undefined;
        const call = { method, url, body: parsed, headers: o.headers || {} };
        calls.push(call);
        const reply = () => {
            const r = server.handle(method, url, parsed);
            if (r === NETWORK) return Promise.reject(new TypeError('Failed to fetch'));
            return Promise.resolve({
                ok: r.status >= 200 && r.status < 300,
                status: r.status,
                json: () => Promise.resolve(JSON.parse(JSON.stringify(r.data))),
            });
        };
        if (server.db.network) return Promise.reject(new TypeError('Failed to fetch'));
        if (server.db.holdNext && server.db.holdNext(call)) {
            server.db.holdNext = null;
            return new Promise((resolve, reject) => {
                server.db.deferred.push({ call, release: () => reply().then(resolve, reject) });
            });
        }
        return reply();
    };

    const sandbox = {
        console,
        document: {
            readyState: 'complete',
            hidden: false,
            body,
            createElement: (tag) => new El(tag),
            getElementById: (id) => byId[id] || null,
            addEventListener: (type, fn) => { (docListeners[type] = docListeners[type] || []).push(fn); },
            execCommand: (cmd) => { execCalls.push(cmd); return true; },
        },
        location: { search: options.search || '', pathname: '/receiving/review' },
        history: { replaceState: (s, t, url) => { urls.push(url); } },
        navigator: options.noClipboard ? {} : {
            clipboard: { writeText: (text) => { clipboard.push(text); return Promise.resolve(); } },
        },
        fetch: fetchStub,
        confirm: (text) => { confirms.push(text); return confirmAnswer; },
        setTimeout: (fn, ms) => { const id = ++timerSeq; timers.push({ id, fn, ms }); return id; },
        clearTimeout: (id) => { timers = timers.filter((t) => t.id !== id); },
    };
    sandbox.document.activeElement = null;
    El.doc = sandbox.document;     // фокус — у последнего окружения (тесты идут по одному)
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    new vm.Script(JS, { filename: 'review.js' }).runInContext(sandbox);

    const env = {
        sandbox, byId, server, db: server.db, calls, clipboard, urls, execCalls, body, docListeners, confirms,
        setConfirm(value) { confirmAnswer = value; },
        chip(id) { return byId.rvPickList.children.find((n) => n.dataset.receipt === String(id)); },
        api: sandbox.__rvReview,
        timers: () => timers.slice(),
        async runTimers(ms) {
            const due = timers.filter((t) => ms === undefined || t.ms === ms);
            timers = timers.filter((t) => !due.includes(t));
            due.forEach((t) => t.fn());
            await flush();
        },
        async release() {
            const item = server.db.deferred.shift();
            item.release();
            await flush();
        },
        document: sandbox.document,
        rows() { return byId.rvRows.children.filter((tr) => tr.dataset.gtin); },
        row(gtin) { return byId.rvRows.children.find((tr) => tr.dataset.gtin === gtin); },
        button(tr, action) { return findAll(tr, (n) => n.tagName === 'BUTTON' && n.dataset.action === action)[0]; },
        tab(id) { return byId.rvTabs.children.find((b) => b.dataset.tab === id); },
        lastGet(prefix) { return calls.filter((c) => c.method === 'GET' && c.url.startsWith(prefix)).pop(); },
        clearCalls() { calls.length = 0; },
    };
    return env;
}

async function flush() {
    for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
}

// ---------------------------------------------------------------- тесты

const env = await (async () => { const e = boot(); await flush(); return e; })();
const b = env.byId;

await test('при старте один запрос разбора: вкладка «К разбору», лимит 200', () => {
    const gets = env.calls.filter((c) => c.url.startsWith('/api/receiving/review?'));
    assert.equal(gets.length, 1, 'страница не сходила за данными или сходила дважды');
    assert.equal(gets[0].url, '/api/receiving/review?state=open&limit=200');
    assert.equal(gets[0].method, 'GET');
    assert.ok(env.chip('all').classList.contains('is-on'), 'без ?receipt= выбраны «Все приёмки»');
    assert.equal(b.rvError.hidden, true);
});

await test('шапка: дата индекса и число карточек, диагностика в «Как считается»', () => {
    assert.equal(flat(b.rvIndex.textContent), 'Индекс iiko: 03.10.2026 07:30, 9 120 карточек');
    assert.ok(!b.rvIndex.classList.contains('is-missing'));
    const diag = flat(b.rvIndexDiag.textContent);
    assert.match(diag, /В индексе 9 120 карточек, со штрихкодом 4 200/);
    assert.match(diag, /разных штрихкодов 4 650/);
    assert.match(diag, /удалённых 1 300, в архиве 800/);
    assert.match(diag, /актуальных карточках 12/);
    assert.equal(b.rvJob.hidden, true, 'строка хода видна без обновления');
    assert.equal(b.rvRefresh.disabled, false);
    assert.equal(b.rvRefreshLabel.textContent, 'Обновить из iiko');
});

await test('вкладки со счётчиками сервера; активна «К разбору»', () => {
    const tabs = b.rvTabs.children;
    assert.deepEqual(tabs.map((t) => t.dataset.tab), ['open', 'new', 'similar', 'restore', 'duplicate', 'closed', 'all']);
    const label = (id) => flat(env.tab(id).textContent);
    assert.equal(label('open'), 'К разбору4');
    assert.equal(label('new'), 'Новые1');
    assert.equal(label('similar'), 'Похожие1');
    assert.equal(label('restore'), 'Восстановить1');
    assert.equal(label('duplicate'), 'Дубли1');
    assert.equal(label('closed'), 'Закрытые2');
    assert.equal(label('all'), 'Все6');
    assert.ok(env.tab('open').classList.contains('is-active'));
    assert.equal(env.tab('open').getAttribute('aria-pressed'), 'true');
    assert.equal(env.tab('new').getAttribute('aria-pressed'), 'false');
    assert.ok(findAll(env.tab('new'), hasClass('rv-tab-n'))[0].classList.contains('has-items'));
    assert.equal(flat(b.rvCount.textContent), '4 строки');
});

await test('строки всех открытых статусов: таблетка, цвет по токену, порядок как у сервера', () => {
    const rows = env.rows();
    assert.deepEqual(rows.map((r) => r.dataset.gtin),
        ['04650075420019', '04607043562301', '00000046123456', '14600000000005']);
    const pill = (tr) => findAll(tr, hasClass('rv-pill'))[0];
    const expect = [['Новая', 'is-new'], ['Похожая карточка', 'is-warn'],
                    ['Удалена или в архиве', 'is-warn'], ['Дубль штрихкода', 'is-warn']];
    rows.forEach((tr, i) => {
        assert.equal(pill(tr).textContent, expect[i][0]);
        assert.ok(pill(tr).classList.contains(expect[i][1]), `${expect[i][0]}: нет ${expect[i][1]}`);
        assert.ok(!tr.classList.contains('is-closed'));
    });
    const cells = findAll(rows[0], byTag('td')).map((td) => td.className);
    assert.deepEqual(cells, ['rv-td-st', 'rv-td-pos', 'rv-td-qty', 'rv-td-cards', 'rv-td-sup', 'rv-td-note', 'rv-td-act']);
});

await test('позиция: название ЧЗ, бренд/группа/объём, штрихкод для iiko и GTIN; без ЧЗ — «нет данных ЧЗ»', () => {
    const fresh = env.row('04650075420019');
    const pos = findAll(fresh, hasClass('rv-td-pos'))[0];
    assert.equal(findAll(pos, hasClass('rv-name'))[0].textContent, 'Пиво светлое нефильтрованное «Жигулёвское Барное»');
    assert.match(findAll(pos, hasClass('rv-name'))[0].title, /карточка товара ЧЗ/);
    assert.equal(findAll(pos, hasClass('rv-meta'))[0].textContent, 'Жигулёвское · beer · 0,5 л');
    assert.equal(flat(findAll(pos, hasClass('rv-codes'))[0].textContent),
        'штрихкод для iiko 4650075420019GTIN 04650075420019');

    const restore = findAll(env.row('00000046123456'), hasClass('rv-td-pos'))[0];
    const name = findAll(restore, hasClass('rv-name'))[0];
    assert.equal(name.textContent, 'нет данных ЧЗ');
    assert.ok(name.classList.contains('is-none'));
    assert.equal(findAll(restore, hasClass('rv-meta')).length, 0);
    assert.match(restore.textContent, /штрихкод для iiko 46123456/);

    const dup = findAll(env.row('14600000000005'), hasClass('rv-td-pos'))[0];
    assert.equal(findAll(dup, hasClass('rv-code')).length, 1, 'GTIN из 14 цифр повторён дважды');
});

await test('недоверенное название ЧЗ ложится текстом (innerHTML в стабе запрещён)', () => {
    const similar = env.row('04607043562301');
    assert.ok(similar.textContent.includes(XSS), 'строка с разметкой в названии потерялась');
    assert.equal(findAll(similar, byTag('img')).length, 0, 'название стало разметкой');
});

await test('количество и приёмки: ссылки-фильтры, лишние свёрнуты в «ещё N»', () => {
    const qty = findAll(env.row('04607043562301'), hasClass('rv-td-qty'))[0];
    assert.equal(flat(findAll(qty, hasClass('rv-qty'))[0].textContent), '13 шт.');
    const links = findAll(qty, byTag('a'));
    assert.deepEqual(links.map((a) => flat(a.textContent)), ['№12 · 6 шт.', '№11 · 4 шт.', '№10 · 2 шт.']);
    assert.deepEqual(links.map((a) => a.getAttribute('href')),
        ['/receiving/review?receipt=12', '/receiving/review?receipt=11', '/receiving/review?receipt=10']);
    assert.equal(findAll(qty, hasClass('rv-muted'))[0].textContent, 'ещё 1');
    const again = findAll(env.row('04607043562301'), hasClass('rv-again'))[0];
    assert.equal(again.textContent, 'вернулась в разбор: 2 раза');
});

await test('карточки iiko: кандидаты «похожей» со счётом, пометки удалена/архив/кега', () => {
    const sim = findAll(env.row('04607043562301'), hasClass('rv-td-cards'))[0];
    assert.match(sim.textContent, /похожие по названию:/);
    assert.match(flat(sim.textContent), /Mystery Сидр Яблочный 0,5 старт\. 00123 · Бутылочное \/ Сидр · поставщик Бирмаркет/);
    assert.equal(findAll(sim, hasClass('rv-score'))[0].textContent, 'совпало слов: 2');

    const res = findAll(env.row('00000046123456'), hasClass('rv-td-cards'))[0];
    assert.deepEqual(findAll(res, hasClass('rv-flag')).map((f) => f.textContent), ['удалена', 'в архиве']);
    assert.equal(findAll(res, hasClass('rv-score')).length, 0, 'у восстановления нет счёта слов');

    const dup = findAll(env.row('14600000000005'), hasClass('rv-td-cards'))[0];
    assert.equal(findAll(dup, hasClass('rv-card-i')).length, 2);
    assert.deepEqual(findAll(dup, hasClass('rv-flag')).map((f) => f.textContent), ['кега', 'кега']);

    const fresh = findAll(env.row('04650075420019'), hasClass('rv-td-cards'))[0];
    assert.equal(fresh.textContent, 'карточки нет');
});

await test('поставщик: выбор из справочника у новой/похожей/восстановить, подсказка с карточки', () => {
    const select = (gtin) => findAll(env.row(gtin), byTag('select'))[0];
    assert.ok(select('04650075420019') && select('04607043562301') && select('00000046123456'));
    assert.equal(select('14600000000005'), undefined, 'у дубля выбор поставщика не нужен');
    const options = select('04650075420019').children.map((o) => [o.value, o.textContent]);
    assert.deepEqual(options, [['', 'Поставщик...'], ['Бирмаркет', 'Бирмаркет'], ['Пивторг', 'Пивторг'],
                               ['Солодовня', 'Солодовня']]);
    assert.equal(select('04607043562301').value, 'Бирмаркет');
    assert.equal(select('04650075420019').value, '');
    const hint = findAll(env.row('00000046123456'), hasClass('rv-sup-hint'))[0];
    assert.equal(hint.textContent, 'у карточки iiko: Пивторг');
    const dupSup = findAll(env.row('14600000000005'), hasClass('rv-td-sup'))[0];
    assert.equal(dupSup.textContent, 'Солодовнякатегория карточки iiko');
});

await test('кнопки: «Скопировать» у новой и похожей, «Найти», «Сделано», «Не нужно» у открытых', () => {
    const actions = (gtin) => findAll(env.row(gtin), byTag('button')).map((n) => n.dataset.action);
    assert.deepEqual(actions('04650075420019'), ['copy', 'find', 'done', 'not_needed']);
    assert.deepEqual(actions('04607043562301'), ['copy', 'find', 'done', 'not_needed']);
    assert.deepEqual(actions('00000046123456'), ['find', 'done', 'not_needed']);
    assert.deepEqual(actions('14600000000005'), ['find', 'done', 'not_needed']);
    const done = env.button(env.row('04650075420019'), 'done');
    assert.equal(done.textContent, 'Сделано');
    assert.ok(done.classList.contains('rv-btn-primary'));
});

await test('блок «Приёмки»: номер, кто и когда, шт., позиции, сверка, ошибка сверки', () => {
    const items = b.rvReceipts.children;
    assert.equal(items.length, 3);
    const first = flat(items[0].textContent);
    assert.match(first, /^№1203\.10 09:00 · Пётрсверена/);
    assert.match(first, /340 шт\. · 18 позиций · отклонено 2 · повторов 5 · фото накладных 1/);
    assert.ok(findAll(items[0], hasClass('rv-rc-proc'))[0].classList.contains('is-done'));
    const second = items[1];
    assert.ok(findAll(second, hasClass('rv-rc-proc'))[0].classList.contains('is-error'));
    const note = findAll(second, hasClass('rv-rc-note'));
    assert.equal(note[0].textContent, 'Нет индекса iiko: Не настроено подключение к iiko');
    assert.ok(note[0].classList.contains('is-bad'));
    assert.equal(note[1].textContent, 'Заметка приёмщика: Машина Бирмаркета');
    assert.equal(findAll(second, (n) => n.dataset.action === 'details').length, 0,
        'у приёмки без фото и отклонённых не нужна кнопка подробностей');
});

await test('фото накладных и отклонённые сканы: по щелчку, ссылки только на свои пути', async () => {
    const box = b.rvReceipts.children[0];
    const more = findAll(box, (n) => n.dataset.action === 'details')[0];
    const holder = findAll(box, hasClass('rv-rc-more'))[0];
    assert.equal(holder.hidden, true);
    env.clearCalls();
    more.click();
    await flush();
    assert.deepEqual(env.calls.map((c) => c.method + ' ' + c.url), ['GET /api/receiving/12']);
    assert.equal(holder.hidden, false);
    const links = findAll(holder, byTag('a'));
    assert.equal(links.length, 1, 'ссылка javascript: не отфильтрована');
    assert.equal(links[0].getAttribute('href'), '/api/receiving/invoice/r12_20261003T085000_ab12cd34.jpg');
    assert.equal(links[0].getAttribute('target'), '_blank');
    assert.equal(links[0].getAttribute('rel'), 'noopener');
    const scans = findAll(holder, hasClass('rv-rc-scan')).map((n) => n.textContent);
    assert.deepEqual(scans, ['08:40 · прочитан с ошибкой · 0104650075420018215abc',
                             '08:30 · код короба или паллеты · 00146000000000000017']);
    assert.equal(more.textContent, 'Скрыть фото и сканы');
    more.click();
    await flush();
    assert.equal(holder.hidden, true);
    more.click();
    await flush();
    assert.equal(env.calls.length, 1, 'подробности загрузились второй раз');
    assert.equal(holder.hidden, false);
});

await test('«Скопировать для iiko»: семь строк текста, «Скопировано» на кнопке', async () => {
    const button = env.button(env.row('04650075420019'), 'copy');
    button.click();
    await flush();
    assert.equal(env.clipboard.length, 1);
    assert.equal(env.clipboard[0], [
        'Название: Пиво светлое нефильтрованное «Жигулёвское Барное»',
        'Бренд: Жигулёвское',
        'Штрихкод: 4650075420019',
        'GTIN: 04650075420019',
        'Поставщик:',
        'Объём: 0,5 л',
        'Группа ЧЗ: beer',
    ].join('\n'));
    assert.equal(button.textContent, 'Скопировано');
    await env.runTimers(1500);
    assert.equal(button.textContent, 'Скопировать для iiko');
    const sim = env.api.buildCopyText(env.api.state.rows.find((r) => r.gtin === '04607043562301'));
    assert.match(sim, /^Поставщик: Бирмаркет$/m, 'выбранный поставщик не в тексте');
    const res = env.api.buildCopyText(env.api.state.rows.find((r) => r.gtin === '00000046123456'));
    assert.match(res, /^Название:$/m);
    assert.match(res, /^Поставщик: Пивторг$/m, 'подсказка поставщика не подставлена');
});

await test('копирование без Clipboard API — через скрытое поле и execCommand', async () => {
    const e2 = boot({ noClipboard: true });
    await flush();
    const button = e2.button(e2.row('04650075420019'), 'copy');
    button.click();
    await flush();
    assert.deepEqual(e2.execCalls, ['copy']);
    assert.equal(e2.body.children.length, 0, 'скрытое поле не убрано');
    assert.equal(button.textContent, 'Скопировано');
});

await test('«Сделано»: PUT state=done, строка заблокирована до ответа, затем список перечитан', async () => {
    env.clearCalls();
    env.db.holdNext = (call) => call.method === 'PUT';
    const tr = env.row('04650075420019');
    env.button(tr, 'done').click();
    await flush();
    assert.equal(env.calls.length, 1);
    assert.equal(env.calls[0].method, 'PUT');
    assert.equal(env.calls[0].url, '/api/receiving/review/04650075420019');
    assert.deepEqual(env.calls[0].body, { state: 'done' });
    assert.equal(env.calls[0].headers['Content-Type'], 'application/json');
    assert.ok(tr.classList.contains('is-busy'));
    assert.equal(env.button(tr, 'done').disabled, true);
    assert.equal(env.button(tr, 'not_needed').disabled, true);
    env.button(tr, 'done').click();
    await flush();
    assert.equal(env.calls.length, 1, 'второй щелчок отправил второй PUT');
    await env.release();
    assert.equal(env.calls[1].url, '/api/receiving/review?state=open&limit=200', 'список не перечитан');
    assert.equal(flat(b.rvToast.textContent), 'Сделано: Пиво светлое нефильтрованное «Жигулёвское Барное»');
    assert.equal(b.rvToast.hidden, false);
    assert.equal(env.row('04650075420019'), undefined, 'закрытая строка осталась на вкладке «К разбору»');
    assert.equal(flat(env.tab('open').textContent), 'К разбору3');
    assert.equal(flat(env.tab('closed').textContent), 'Закрытые3');
});

await test('«Не нужно»: PUT state=not_needed', async () => {
    env.clearCalls();
    env.button(env.row('14600000000005'), 'not_needed').click();
    await flush();
    assert.equal(env.calls[0].url, '/api/receiving/review/14600000000005');
    assert.deepEqual(env.calls[0].body, { state: 'not_needed' });
    assert.match(flat(b.rvToast.textContent), /^Не нужно: Kriek Boon$/);
});

await test('вкладка «Закрытые»: state=closed, решение и кто закрыл, «Вернуть в разбор» — PUT state=open', async () => {
    env.clearCalls();
    env.tab('closed').click();
    await flush();
    assert.equal(env.calls[0].url, '/api/receiving/review?state=closed&limit=200');
    assert.ok(env.tab('closed').classList.contains('is-active'));
    assert.ok(!env.tab('open').classList.contains('is-active'));
    const rows = env.rows();
    assert.equal(rows.length, 4);
    rows.forEach((tr) => assert.ok(tr.classList.contains('is-closed')));
    const res = (gtin) => flat(findAll(env.row(gtin), hasClass('rv-res'))[0].textContent);
    assert.equal(res('04601234567891'), 'Сразу была в iiko · 03.10 09:01');
    assert.equal(res('04600000000017'), 'Сделано · Анна, 03.10 12:00');
    assert.ok(findAll(env.row('04601234567891'), hasClass('rv-pill'))[0].classList.contains('is-ok'));
    assert.deepEqual(findAll(env.row('04600000000017'), byTag('button')).map((n) => n.dataset.action), ['open']);
    assert.equal(findAll(env.row('04600000000017'), byTag('select')).length, 0, 'у закрытой строки выбор поставщика');
    assert.equal(findAll(env.row('04600000000017'), hasClass('rv-td-sup'))[0].textContent, 'Солодовня');
    env.clearCalls();
    env.button(env.row('04600000000017'), 'open').click();
    await flush();
    assert.equal(env.calls[0].method, 'PUT');
    assert.deepEqual(env.calls[0].body, { state: 'open' });
    assert.equal(env.calls[1].url, '/api/receiving/review?state=closed&limit=200');
    assert.match(flat(b.rvToast.textContent), /^Возвращена в разбор: Эль Тёмный$/);
    assert.equal(env.row('04600000000017'), undefined);
});

await test('вкладки статусов: state=open&status=...; «Все» — state=all', async () => {
    for (const [id, query] of [['new', 'state=open&status=new'], ['similar', 'state=open&status=similar'],
                               ['restore', 'state=open&status=restore'], ['duplicate', 'state=open&status=duplicate'],
                               ['all', 'state=all']]) {
        env.clearCalls();
        env.tab(id).click();
        await flush();
        assert.equal(env.calls[0].url, '/api/receiving/review?' + query + '&limit=200', `вкладка ${id}`);
    }
    assert.equal(env.rows().length, 6);
    env.clearCalls();
    env.tab('duplicate').click();
    await flush();
    assert.equal(env.rows().length, 0);
    assert.equal(b.rvRows.textContent, 'Строк со статусом «Дубль штрихкода» нет');
    env.tab('open').click();
    await flush();
});

await test('смена вкладки во время загрузки: устаревший ответ отбрасывается', async () => {
    env.clearCalls();
    env.db.holdNext = (call) => call.url.includes('status=similar');
    env.tab('similar').click();
    await flush();
    env.tab('restore').click();
    await flush();
    assert.equal(env.rows().map((r) => r.dataset.gtin).join(), '00000046123456');
    await env.release();
    assert.equal(env.rows().map((r) => r.dataset.gtin).join(), '00000046123456', 'поздний ответ «Похожих» затёр «Восстановить»');
    assert.ok(env.tab('restore').classList.contains('is-active'));
    env.tab('open').click();
    await flush();
});

await test('поиск по таблице: пауза в наборе, затем q в запросе; пустой результат объяснён', async () => {
    env.clearCalls();
    b.rvSearch.value = 'Mys';
    b.rvSearch.dispatch('input');
    b.rvSearch.value = 'Mystery';
    b.rvSearch.dispatch('input');
    await flush();
    assert.equal(env.calls.length, 0, 'запрос ушёл без паузы');
    await env.runTimers(300);
    assert.equal(env.calls.length, 1, 'на каждую букву ушёл запрос');
    assert.equal(env.calls[0].url, '/api/receiving/review?state=open&q=Mystery&limit=200');
    assert.deepEqual(env.rows().map((r) => r.dataset.gtin), ['04607043562301']);
    assert.equal(flat(env.tab('open').textContent), 'К разбору1', 'счётчики не из ответа с поиском');
    b.rvSearch.value = 'нет такого';
    b.rvSearch.dispatch('input');
    await env.runTimers(300);
    assert.equal(env.lastGet('/api/receiving/review').url,
        '/api/receiving/review?state=open&q=' + encodeURIComponent('нет такого') + '&limit=200');
    assert.equal(b.rvRows.textContent, 'По запросу «нет такого» ничего не нашлось');
    b.rvSearch.value = '';
    b.rvSearch.dispatch('input');
    await env.runTimers(300);
    assert.equal(env.rows().length, 3);
});

await test('поставщик: PUT supplier, «сохранено»; не из справочника — откат и ошибка; пусто — снят', async () => {
    const tr = env.row('00000046123456');
    const select = findAll(tr, byTag('select'))[0];
    const status = findAll(findAll(tr, hasClass('rv-td-sup'))[0], hasClass('rv-saved'))[0];
    env.clearCalls();
    select.value = 'Солодовня';
    select.dispatch('change');
    await flush();
    assert.equal(env.calls.length, 1, 'смена поставщика перечитала весь список');
    assert.equal(env.calls[0].url, '/api/receiving/review/00000046123456');
    assert.deepEqual(env.calls[0].body, { supplier: 'Солодовня' });
    assert.equal(status.hidden, false);
    assert.equal(status.textContent, 'сохранено');
    assert.equal(env.api.state.rows.find((r) => r.gtin === '00000046123456').supplier, 'Солодовня');
    assert.match(env.api.buildCopyText(env.api.state.rows.find((r) => r.gtin === '00000046123456')),
        /^Поставщик: Солодовня$/m);

    env.clearCalls();
    select.value = 'Чужой поставщик';
    select.dispatch('change');
    await flush();
    assert.deepEqual(env.calls[0].body, { supplier: 'Чужой поставщик' });
    assert.equal(select.value, 'Солодовня', 'отказ сервера не откатил выбор');
    assert.equal(status.textContent, 'не сохранено');
    assert.ok(status.classList.contains('is-bad'));
    assert.equal(b.rvToast.textContent, 'Поставщика нет в справочнике');
    assert.ok(b.rvToast.classList.contains('is-bad'));

    env.clearCalls();
    select.value = '';
    select.dispatch('change');
    await flush();
    assert.deepEqual(env.calls[0].body, { supplier: '' });
    assert.equal(status.textContent, 'поставщик снят');
    assert.ok(!status.classList.contains('is-bad'));
    env.clearCalls();
    select.value = '';
    select.dispatch('change');
    await flush();
    assert.equal(env.calls.length, 0, 'тот же поставщик отправлен повторно');
});

await test('заметка: PUT note без пробелов по краям; повтор того же текста не отправляется', async () => {
    const tr = env.row('04607043562301');
    const input = findAll(tr, hasClass('rv-input-note'))[0];
    assert.equal(input.maxLength, 500);
    env.clearCalls();
    input.value = '  проверить цену у поставщика  ';
    input.dispatch('change');
    await flush();
    assert.deepEqual(env.calls.map((c) => [c.method, c.url, c.body]),
        [['PUT', '/api/receiving/review/04607043562301', { note: 'проверить цену у поставщика' }]]);
    assert.equal(input.value, 'проверить цену у поставщика');
    env.clearCalls();
    input.dispatch('change');
    await flush();
    assert.equal(env.calls.length, 0);
    const enter = input.dispatch('keydown', { key: 'Enter' });
    assert.ok(enter.defaultPrevented);
    assert.equal(input.blurred, 1, 'Enter не сохранил заметку уходом из поля');
});

await test('заметка и «Сделано» подряд: PUT уходят по очереди, заметка первой', async () => {
    const tr = env.row('04607043562301');
    const input = findAll(tr, hasClass('rv-input-note'))[0];
    env.clearCalls();
    env.db.holdNext = (call) => call.method === 'PUT';
    input.value = 'заведено как Mystery Apple';
    input.dispatch('change');
    env.button(tr, 'done').click();
    await flush();
    assert.equal(env.calls.length, 1, '«Сделано» ушло, не дождавшись заметки');
    await env.release();
    const puts = env.calls.filter((c) => c.method === 'PUT').map((c) => c.body);
    assert.deepEqual(puts, [{ note: 'заведено как Mystery Apple' }, { state: 'done' }]);
    assert.equal(env.db.rows.find((r) => r.gtin === '04607043562301').note, 'заведено как Mystery Apple');
    assert.equal(env.row('04607043562301'), undefined);
});

await test('PUT 404 — сообщение и перечитанный список; нет связи — сообщение', async () => {
    const tr = env.row('00000046123456');
    env.db.putReply = { status: 404, data: { error: 'Строки разбора нет' } };
    env.clearCalls();
    env.button(tr, 'done').click();
    await flush();
    env.db.putReply = null;
    assert.equal(b.rvToast.textContent, 'Строки разбора нет');
    assert.ok(env.calls.some((c) => c.method === 'GET' && c.url.startsWith('/api/receiving/review?')));
    assert.equal(env.button(env.row('00000046123456'), 'done').disabled, false, 'строка осталась заблокированной');
    env.db.network = true;
    env.button(env.row('00000046123456'), 'not_needed').click();
    await flush();
    env.db.network = false;
    assert.equal(b.rvToast.textContent, 'Нет связи с сервером — изменение не сохранено');
    assert.equal(env.db.rows.find((r) => r.gtin === '00000046123456').state, 'open');
});

await test('«Найти в iiko»: слова названия без стоп-слов, запрос к /api/receiving/products', async () => {
    env.api.state.rows.push(Object.assign({}, makeRows()[0]));
    env.api.render();
    const tr = env.row('04650075420019');
    env.clearCalls();
    const before = b.rvIiko.scrolled;
    env.button(tr, 'find').click();
    await flush();
    assert.equal(b.rvIikoQ.value, 'жигулевское барное');
    assert.equal(env.calls.length, 1);
    assert.equal(env.calls[0].url, '/api/receiving/products?q=' + encodeURIComponent('жигулевское барное') + '&limit=20');
    assert.equal(b.rvIiko.scrolled, before + 1, 'блок поиска не прокручен в вид');
    const hits = b.rvIikoResults.children;
    assert.equal(hits.length, 2);
    assert.equal(flat(hits[0].textContent),
        'Жигулевское Барное 0,5 старт. 00042 · Бутылочное / Лагеры · поставщик Пивторг · ед. штштрихкоды: 4650075420002, 04650075420002');
    assert.deepEqual(findAll(hits[1], hasClass('rv-flag')).map((f) => f.textContent), ['удалена', 'кега']);
    assert.match(hits[1].textContent, /штрихкодов нет/);
    assert.equal(b.rvIikoMsg.textContent, 'Найдено: 2');
    assert.equal(b.rvIikoInfo.textContent, 'индекс от 03.10.2026 07:30');
    env.api.load();
    await flush();
});

await test('«Найти в iiko» без названия ЧЗ ищет по штрихкоду', async () => {
    env.clearCalls();
    env.button(env.row('00000046123456'), 'find').click();
    await flush();
    assert.equal(b.rvIikoQ.value, '46123456');
    assert.equal(env.calls[0].url, '/api/receiving/products?q=46123456&limit=20');
    assert.equal(b.rvIikoMsg.textContent, 'Ничего не нашлось — попробуйте одно слово, артикул или штрихкод');
});

await test('ключевые слова — те же правила, что у «похожей карточки»', () => {
    const k = env.api.keywords;
    assert.deepEqual([...k('Пиво светлое пастеризованное "Балтика 7 Экспортное" 0,45 бут.')], ['балтика', 'экспортное']);
    assert.deepEqual([...k('Ёлка ёлка  ЁЛКА')], ['елка']);
    assert.deepEqual([...k('ab 12345 IPA')], ['ipa']);
    // Ревью 2026-10-04: объём одним словом — не слово, описания ЧЗ мужского рода — стоп-слова.
    assert.deepEqual([...k('КЕГ Варка Лагер 30л. 500мл')], ['варка', 'лагер']);
    assert.deepEqual([...k('Сидр традиционный газированный Майзельс')], ['сидр', 'майзельс']);
    assert.deepEqual([...k('')], []);
    assert.equal(env.api.searchQueryFor({ chz: { name: 'Напиток пивной Хугарден Вит Бланш' }, barcode: '1' }), 'хугарден вит');
});

await test('форма «Поиск в iiko»: короткий запрос не уходит, 503 без индекса — текст сервера', async () => {
    env.clearCalls();
    b.rvIikoQ.value = ' ж ';
    const ev = b.rvIikoForm.dispatch('submit');
    await flush();
    assert.ok(ev.defaultPrevented, 'форма отправилась по-настоящему');
    assert.equal(env.calls.length, 0);
    assert.equal(b.rvIikoMsg.textContent, 'Введите хотя бы 2 символа');
    assert.equal(b.rvIikoResults.children.length, 0);
    env.db.productsReply = { status: 503, data: { error: 'Индекс карточек iiko ещё не собран — нажмите «Обновить из iiko»',
                                                 code: 'index_missing' } };
    b.rvIikoQ.value = 'Kriek';
    b.rvIikoForm.dispatch('submit');
    await flush();
    env.db.productsReply = null;
    assert.equal(env.calls[0].url, '/api/receiving/products?q=Kriek&limit=20');
    assert.equal(b.rvIikoMsg.textContent, 'Индекс карточек iiko ещё не собран — нажмите «Обновить из iiko»');
    assert.ok(b.rvIikoMsg.classList.contains('is-bad'));
});

await test('«Обновить из iiko»: POST, опрос каждые 4 с до running=false, затем список перечитан', async () => {
    env.clearCalls();
    env.db.statusQueue.push(
        { status: 200, data: { index: IDX_MORNING, job: { running: true, trigger: 'button', started_at: '2026-10-03T10:00:00+03:00',
                                                           finished_at: '', error: '', counts: null } } },
        { status: 500, data: {} },
        { status: 200, data: { index: IDX_FRESH, job: { running: false, trigger: 'button', started_at: '2026-10-03T10:00:00+03:00',
                                                         finished_at: '2026-10-03T10:02:00+03:00', error: '', counts: IDX_FRESH.counts } } },
    );
    b.rvRefresh.click();
    await flush();
    assert.deepEqual(env.calls.map((c) => c.method + ' ' + c.url), ['POST /api/receiving/barcodes/refresh']);
    assert.equal(b.rvRefresh.disabled, true);
    assert.ok(b.rvRefresh.classList.contains('is-busy'));
    assert.equal(b.rvRefreshLabel.textContent, 'Обновляем...');
    assert.equal(b.rvJob.hidden, false);
    assert.match(b.rvJob.textContent, /^Обновляется из iiko/);
    assert.ok(env.timers().some((t) => t.ms === 4000), 'опрос не запланирован через 4 с');
    b.rvRefresh.click();
    await flush();
    assert.equal(env.calls.length, 1, 'кнопка во время обновления запустила второе');

    await env.runTimers(4000);
    assert.equal(env.calls[1].url, '/api/receiving/barcodes/status');
    assert.match(b.rvJob.textContent, /^Обновляется из iiko с 10:00/);
    assert.equal(b.rvRefresh.disabled, true);
    await env.runTimers(4000);
    assert.equal(env.calls[2].url, '/api/receiving/barcodes/status', 'сбой опроса остановил его');
    assert.equal(b.rvRefresh.disabled, true);
    await env.runTimers(4000);
    assert.equal(env.calls[3].url, '/api/receiving/barcodes/status');
    assert.equal(env.calls[4].url, '/api/receiving/review?state=open&limit=200', 'после обновления список не перечитан');
    assert.equal(env.calls.length, 5);
    assert.equal(b.rvRefresh.disabled, false);
    assert.equal(b.rvRefreshLabel.textContent, 'Обновить из iiko');
    assert.equal(b.rvJob.hidden, true);
    assert.equal(b.rvToast.textContent, 'Индекс iiko обновлён, открытые строки пересверены');
    env.db.index = IDX_FRESH;
    env.api.load();
    await flush();
    assert.equal(flat(b.rvIndex.textContent), 'Индекс iiko: 03.10.2026 10:02, 9 200 карточек');
    assert.match(b.rvIndexDiag.textContent, /XML-выгрузки/);
    env.clearCalls();
    await env.runTimers(4000);
    assert.equal(env.calls.length, 0, 'опрос продолжился после конца обновления');
});

await test('обновление: 409 — тоже опрос; ошибка в job — видна в шапке', async () => {
    env.db.refreshReply = { status: 409, data: { status: 'already_running' } };
    env.db.statusQueue.push({ status: 200, data: { index: IDX_FRESH, job: {
        running: false, trigger: 'schedule', started_at: '2026-10-03T10:05:00+03:00',
        finished_at: '2026-10-03T10:06:00+03:00', error: 'iiko не отвечает', counts: null } } });
    env.db.job = { running: false, trigger: 'schedule', started_at: '2026-10-03T10:05:00+03:00',
                   finished_at: '2026-10-03T10:06:00+03:00', error: 'iiko не отвечает', counts: null };
    env.clearCalls();
    b.rvRefresh.click();
    await flush();
    assert.equal(b.rvToast.textContent, 'Индекс уже обновляется — ждём, когда закончится');
    await env.runTimers(4000);
    assert.equal(env.calls[1].url, '/api/receiving/barcodes/status');
    assert.equal(b.rvToast.textContent, 'Индекс iiko не обновился: iiko не отвечает');
    assert.ok(b.rvToast.classList.contains('is-bad'));
    assert.equal(b.rvJob.hidden, false);
    assert.ok(b.rvJob.classList.contains('is-bad'));
    assert.equal(b.rvJob.textContent, 'Последнее обновление не удалось (03.10 10:06): iiko не отвечает');
    assert.equal(b.rvRefresh.disabled, false);
    env.db.job = JOB_IDLE;
    env.db.refreshReply = { status: 202, data: { status: 'started' } };
});

await test('обновление: 503 без кредов iiko — ошибка без опроса', async () => {
    env.db.refreshReply = { status: 503, data: { status: 'error', error: 'Не настроено подключение к iiko' } };
    env.clearCalls();
    b.rvRefresh.click();
    await flush();
    assert.equal(env.calls.length, 1);
    assert.ok(!env.timers().some((t) => t.ms === 4000 && env.api.state.polling));
    assert.equal(env.api.state.polling, false);
    assert.equal(b.rvRefresh.disabled, false);
    assert.equal(b.rvJob.textContent, 'Последнее обновление не удалось: Не настроено подключение к iiko');
    assert.equal(b.rvToast.textContent, 'Не настроено подключение к iiko');
    env.db.refreshReply = { status: 202, data: { status: 'started' } };
});

await test('опрос сдаётся после 5 неудачных ответов подряд', async () => {
    for (let i = 0; i < 5; i++) env.db.statusQueue.push({ status: 502, data: {} });
    b.rvRefresh.click();
    await flush();
    for (let i = 0; i < 5; i++) await env.runTimers(4000);
    assert.equal(env.api.state.polling, false);
    assert.equal(b.rvRefresh.disabled, false);
    assert.match(b.rvJob.textContent, /не удалось узнать ход обновления/);
});

await test('обновление уже идёт при открытии страницы — опрос начинается сам', async () => {
    const e2 = boot({ setup: (db) => {
        db.job = { running: true, trigger: 'schedule', started_at: '2026-10-03T07:30:00+03:00',
                   finished_at: '', error: '', counts: null };
        db.statusQueue.push({ status: 200, data: { index: IDX_FRESH, job: JOB_IDLE } });
    } });
    await flush();
    assert.equal(e2.byId.rvRefresh.disabled, true);
    assert.match(e2.byId.rvJob.textContent, /^Обновляется из iiko с 07:30/);
    e2.db.job = JOB_IDLE;
    e2.clearCalls();
    await e2.runTimers(4000);
    assert.deepEqual(e2.calls.map((c) => c.url),
        ['/api/receiving/barcodes/status', '/api/receiving/review?state=open&limit=200']);
    assert.equal(e2.byId.rvRefresh.disabled, false);
});

await test('?receipt=12: фильтр в запросе и выбранная приёмка; «Все приёмки» снимает выбор и чистит адрес', async () => {
    const e2 = boot({ search: '?receipt=12' });
    await flush();
    assert.equal(e2.calls[0].url, '/api/receiving/review?state=open&receipt_id=12&limit=200');
    assert.ok(e2.chip(12).classList.contains('is-on'));
    assert.equal(e2.chip(12).getAttribute('aria-pressed'), 'true');
    assert.ok(!e2.chip('all').classList.contains('is-on'));
    assert.equal(e2.byId.rvPickSub.textContent, 'выбрана приёмка №12 — показаны только её позиции');
    assert.deepEqual(e2.rows().map((r) => r.dataset.gtin), ['04650075420019', '04607043562301', '14600000000005']);
    assert.ok(e2.byId.rvReceipts.children[0].classList.contains('is-current'), 'приёмка не подсвечена в списке');
    e2.clearCalls();
    e2.chip('all').click();
    await flush();
    assert.deepEqual(e2.urls, ['/receiving/review']);
    assert.equal(e2.calls[0].url, '/api/receiving/review?state=open&limit=200');
    assert.ok(e2.chip('all').classList.contains('is-on'));
    assert.equal(e2.rows().length, 4);
});

await test('выбор приёмок: неразобранные вверху, щелчок добавляет и убирает, можно несколько', async () => {
    const e2 = boot();
    await flush();
    const chips = e2.byId.rvPickList.children.map((n) => n.dataset.receipt);
    assert.deepEqual(chips, ['all', '12', '11'], 'разобранная №10 в выбор не попадает');
    assert.equal(flat(e2.chip(12).textContent), '№12 · 03.103 к разбору');
    assert.equal(flat(e2.chip(11).textContent), '№11 · 02.10ошибка сверки');
    assert.match(e2.chip(12).title, /Приёмка №12: 03\.10 09:00, Пётр; 340 шт\., 18 позиций/);
    assert.equal(e2.byId.rvPickSub.textContent, 'неразобранных 2');
    e2.clearCalls();
    e2.chip(12).click();
    await flush();
    e2.chip(11).click();
    await flush();
    assert.equal(e2.lastGet('/api/receiving/review?').url, '/api/receiving/review?state=open&receipt_id=12,11&limit=200');
    assert.deepEqual(e2.urls.slice(-1), ['/receiving/review?receipt=12,11']);
    assert.ok(e2.chip(12).classList.contains('is-on') && e2.chip(11).classList.contains('is-on'));
    assert.equal(e2.byId.rvPickSub.textContent, 'выбрано приёмок: 2 — показаны только их позиции');
    assert.equal(e2.rows().length, 4, 'строки обеих приёмок');
    e2.chip(12).click();
    await flush();
    assert.equal(e2.lastGet('/api/receiving/review?').url, '/api/receiving/review?state=open&receipt_id=11&limit=200');
    assert.ok(!e2.chip(12).classList.contains('is-on'), 'повторный щелчок не снял выбор');
});

await test('?receipt=12,10,99: выбранные видны, даже разобранная и несуществующая', async () => {
    const e2 = boot({ search: '?receipt=12,10,99' });
    await flush();
    assert.equal(e2.calls[0].url, '/api/receiving/review?state=open&receipt_id=12,10,99&limit=200');
    assert.deepEqual(e2.byId.rvPickList.children.map((n) => n.dataset.receipt), ['all', '12', '11', '10', '99']);
    assert.equal(flat(e2.chip(10).textContent), '№10 · 01.10разобрана');
    assert.equal(flat(e2.chip(99).textContent), '№99не найдена');
    e2.chip(99).click();
    await flush();
    assert.deepEqual(e2.urls.slice(-1), ['/receiving/review?receipt=12,10']);
});

await test('щелчок по приёмке в строке и «Показать позиции» ставят фильтр без перехода', async () => {
    const e2 = boot();
    await flush();
    const link = findAll(e2.row('00000046123456'), byTag('a'))[0];
    e2.clearCalls();
    const ev = link.click();
    await flush();
    assert.ok(ev.defaultPrevented, 'ссылка перезагрузила страницу');
    assert.deepEqual(e2.urls, ['/receiving/review?receipt=11']);
    assert.equal(e2.calls[0].url, '/api/receiving/review?state=open&receipt_id=11&limit=200');
    assert.equal(JSON.stringify(e2.api.state.picked), '[11]');     // массив из другого контекста vm
    assert.ok(e2.chip(11).classList.contains('is-on'));
    assert.equal(e2.byId.rvTabs.scrolled, 1, 'таблица не прокручена в вид');
    const ctrl = findAll(e2.row('00000046123456'), byTag('a'))[0].click({ ctrlKey: true });
    assert.ok(!ctrl.defaultPrevented, 'Ctrl-щелчок не открыл новую вкладку');
    const show = findAll(e2.byId.rvReceipts, (n) => n.dataset.action === 'receipt')[0];
    e2.clearCalls();
    show.click();
    await flush();
    assert.equal(e2.calls[0].url, '/api/receiving/review?state=open&receipt_id=12&limit=200');
    assert.deepEqual(e2.urls.slice(-1), ['/receiving/review?receipt=12']);
});

await test('история: прогресс разбора, «Удалить приёмку» только у разобранных не полностью', async () => {
    const e2 = boot();
    await flush();
    const [r12, r11, r10] = e2.byId.rvReceipts.children;
    assert.equal(findAll(r12, hasClass('rv-rc-prog'))[0].textContent, 'к разбору 3 из 18');
    assert.equal(findAll(r11, hasClass('rv-rc-prog'))[0].textContent, 'не сверено 3');
    const done = findAll(r10, hasClass('rv-rc-prog'))[0];
    assert.equal(done.textContent, 'разобрана');
    assert.ok(done.classList.contains('is-done'));
    const del = (box) => findAll(box, (n) => n.dataset.action === 'delete');
    assert.equal(del(r12).length, 1);
    assert.equal(del(r12)[0].textContent, 'Удалить приёмку');
    assert.equal(del(r11).length, 1);
    assert.equal(del(r10).length, 0, 'у разобранной полностью кнопки нет');
});

await test('«Удалить приёмку»: подтверждение, DELETE, выбор снят, список перечитан', async () => {
    const e2 = boot({ search: '?receipt=12,11' });
    await flush();
    const button = () => findAll(e2.byId.rvReceipts.children.find((n) => /№12/.test(n.textContent)),
        (n) => n.dataset.action === 'delete')[0];
    e2.setConfirm(false);
    e2.clearCalls();
    button().click();
    await flush();
    assert.equal(e2.calls.length, 0, 'без подтверждения ушёл запрос');
    assert.equal(e2.confirms.length, 1);
    assert.match(e2.confirms[0], /^Удалить приёмку №12 \(03\.10 09:00, Пётр\)\?/);
    assert.match(e2.confirms[0], /340 шт\., 18 позиций, фото накладных 1/);
    assert.match(e2.confirms[0], /Вернуть нельзя\.$/);

    e2.setConfirm(true);
    button().click();
    await flush();
    assert.equal(e2.calls[0].method, 'DELETE');
    assert.equal(e2.calls[0].url, '/api/receiving/12');
    assert.equal(e2.lastGet('/api/receiving/review?').url, '/api/receiving/review?state=open&receipt_id=11&limit=200');
    assert.deepEqual(e2.urls.slice(-1), ['/receiving/review?receipt=11']);
    assert.equal(e2.byId.rvToast.textContent, 'Приёмка №12 удалена; убрано из разбора позиций: 2');
    assert.ok(!e2.byId.rvReceipts.children.some((n) => /№12/.test(n.textContent)), 'удалённая осталась в истории');
});

await test('«Удалить приёмку»: 409 — текст сервера и перечитанный список; нет связи — сообщение', async () => {
    const e2 = boot({ setup: (db) => {
        db.deleteReply = { status: 409, data: { error: 'Приёмка разобрана полностью — она остаётся в истории',
                                                 code: 'receipt_reviewed' } };
    } });
    await flush();
    const del = () => findAll(e2.byId.rvReceipts.children[0], (n) => n.dataset.action === 'delete')[0];
    e2.clearCalls();
    del().click();
    await flush();
    assert.equal(e2.byId.rvToast.textContent, 'Приёмка разобрана полностью — она остаётся в истории');
    assert.ok(e2.byId.rvToast.classList.contains('is-bad'));
    assert.ok(e2.calls.some((c) => c.method === 'GET' && c.url.startsWith('/api/receiving/review?')), 'список не перечитан');
    e2.db.network = true;
    del().click();
    await flush();
    e2.db.network = false;
    assert.equal(e2.byId.rvToast.textContent, 'Нет связи с сервером — приёмка не удалена');
    assert.equal(del().textContent, 'Удалить приёмку', 'кнопка не вернулась после сбоя');
});

await test('удаление: приёмка уходит из истории и выбора сразу, даже если перечитать не удалось', async () => {
    const e2 = boot();
    await flush();
    const box = () => e2.byId.rvReceipts.children.find((n) => /№12/.test(n.textContent));
    e2.db.holdNext = (call) => call.method === 'GET' && call.url.startsWith('/api/receiving/review?');
    findAll(box(), (n) => n.dataset.action === 'delete')[0].click();
    await flush();
    assert.equal(box(), undefined, 'удалённая приёмка ещё в истории до ответа');
    assert.equal(e2.chip(12), undefined, 'удалённая приёмка ещё в выборе');
    e2.db.reviewReply = { status: 503, data: { error: 'База приёмки недоступна' } };   // перечитать не удалось
    await e2.release();
    assert.equal(box(), undefined, 'после сбоя перечитывания удалённая вернулась');
    assert.equal(e2.chip(12), undefined);
});

await test('пустая таблица у выбранных приёмок объясняет, почему: сверяется, не прошла, нет такой', async () => {
    const e2 = boot({ search: '?receipt=11', setup: (db) => { db.rows = []; } });
    await flush();
    assert.equal(e2.byId.rvRows.textContent,
        'Сверка приёмки №11 с iiko не прошла: Нет индекса iiko: Не настроено подключение к iiko');
    const e3 = boot({ search: '?receipt=99', setup: (db) => { db.rows = []; } });
    await flush();
    assert.equal(e3.byId.rvRows.textContent, 'Приёмки №99 нет — удалена или номер неверный');
    assert.equal(flat(e3.chip(99).textContent), '№99не найдена');
    const e4 = boot({ search: '?receipt=12', setup: (db) => {
        db.rows = [];
        db.receipts[0] = Object.assign({}, db.receipts[0], { process_state: 'running', can_delete: false });
    } });
    await flush();
    assert.equal(e4.byId.rvRows.textContent, 'Приёмка №12 ещё сверяется с iiko — позиции появятся после сверки');
    assert.equal(findAll(e4.byId.rvReceipts.children[0], (n) => n.dataset.action === 'delete').length, 0,
        'у сверяемой приёмки кнопки удаления нет');
});

await test('выбранная из строки приёмка не «не найдена», пока список перечитывается', async () => {
    const e2 = boot();
    await flush();
    e2.db.holdNext = (call) => call.method === 'GET' && call.url.startsWith('/api/receiving/review?');
    e2.api.setReceipt(7);
    await flush();
    assert.equal(flat(e2.chip(7).textContent), '№7', 'до ответа приёмка помечена «не найдена»');
    e2.db.reviewReply = { status: 503, data: { error: 'База приёмки недоступна' } };   // загрузка не удалась
    await e2.release();
    assert.equal(flat(e2.chip(7).textContent), '№7', 'после сбоя загрузки приёмка помечена «не найдена»');
});

await test('фокус клавиатуры остаётся на чипе приёмки после щелчка', async () => {
    const e2 = boot();
    await flush();
    e2.chip(11).focus();
    e2.chip(11).click();
    await flush();
    assert.equal(e2.document.activeElement, e2.chip(11), 'фокус ушёл с чипа');
    assert.ok(e2.chip(11).classList.contains('is-on'));
});

await test('кривой ?receipt= игнорируется', async () => {
    const e2 = boot({ search: '?receipt=abc' });
    await flush();
    assert.equal(e2.calls[0].url, '/api/receiving/review?state=open&limit=200');
    const e3 = boot({ search: '?x=1&receipt=7' });
    await flush();
    assert.equal(e3.calls[0].url, '/api/receiving/review?state=open&receipt_id=7&limit=200');
});

await test('ошибка загрузки: текст сервера на месте таблицы; 401 — войти снова', async () => {
    const e2 = boot({ setup: (db) => {
        db.reviewReply = { status: 503, data: { error: 'База приёмки недоступна', code: 'receiving_unavailable' } };
    } });
    await flush();
    assert.equal(e2.byId.rvError.hidden, false);
    assert.equal(e2.byId.rvError.textContent, 'База приёмки недоступна');
    assert.equal(e2.byId.rvRows.textContent, 'Список не загружен');
    e2.db.reviewReply = { status: 401, data: { error: 'Требуется вход', auth_required: true } };
    e2.api.load();
    await flush();
    assert.equal(e2.byId.rvError.textContent, 'Сессия истекла — войдите снова');
    e2.db.reviewReply = null;
    e2.api.load();
    await flush();
    assert.equal(e2.byId.rvError.hidden, true);
    assert.equal(e2.rows().length, 4);
});

await test('строк больше лимита — подсказка «уточните поиск»', async () => {
    const e2 = boot({ setup: (db) => { db.totalExtra = 300; } });
    await flush();
    assert.equal(e2.byId.rvMore.hidden, false);
    assert.equal(flat(e2.byId.rvMore.textContent), 'Показаны первые 4 из 304 — уточните поиск или выберите приёмку');
    assert.equal(flat(e2.byId.rvCount.textContent), '4 из 304 строки');
});

await test('индекса нет — шапка просит обновить', async () => {
    const e2 = boot({ setup: (db) => { db.index = null; } });
    await flush();
    assert.equal(e2.byId.rvIndex.textContent, 'Индекс iiko ещё не собран — нажмите «Обновить из iiko»');
    assert.ok(e2.byId.rvIndex.classList.contains('is-missing'));
    assert.equal(e2.byId.rvIndexDiag.textContent, '');
});

await test('пустая очередь — «разбирать нечего»', async () => {
    const e2 = boot({ setup: (db) => { db.rows = db.rows.filter((r) => r.state === 'closed'); } });
    await flush();
    assert.equal(e2.byId.rvRows.textContent, 'Разбирать нечего: всё принятое есть в iiko');
    e2.api.setReceipt(12);
    await flush();
    assert.equal(e2.byId.rvRows.textContent, 'В приёмке №12 разбирать нечего: всё принятое есть в iiko');
});

await test('возврат на вкладку через минуту перечитывает список', async () => {
    const e2 = boot();
    await flush();
    e2.clearCalls();
    e2.docListeners.visibilitychange.forEach((fn) => fn());
    await flush();
    assert.equal(e2.calls.length, 0, 'перечитал сразу после загрузки');
    e2.api.state.loadedAt -= 61000;
    e2.docListeners.visibilitychange.forEach((fn) => fn());
    await flush();
    assert.equal(e2.calls.length, 1);
});

// ---------------------------------------------------------------- ревью 2026-10-03

await test('автообновление списка не стирает набираемую заметку и не уводит фокус', async () => {
    const e3 = boot();
    await flush();
    const tr = e3.row('04607043562301');
    const input = findAll(tr, hasClass('rv-input-note'))[0];
    input.focus();
    input.value = 'Завести в группу Разливное, уточнить у Пети';
    e3.clearCalls();
    await e3.api.load();                                   // конец обновления индекса / возврат на вкладку
    const fresh = findAll(e3.row('04607043562301'), hasClass('rv-input-note'))[0];
    assert.notEqual(fresh, input, 'строка не перерисована — проверка бессмысленна');
    assert.equal(fresh.value, 'Завести в группу Разливное, уточнить у Пети');
    assert.equal(e3.document.activeElement, fresh, 'фокус не вернулся в поле заметки');
    assert.equal(e3.calls.filter((c) => c.method === 'PUT').length, 0, 'заметка ушла без ухода из поля');
});

await test('«Скопировать для iiko» дважды подряд: подпись возвращается к исходной', async () => {
    const e4 = boot();
    await flush();
    const button = e4.button(e4.row('04650075420019'), 'copy');
    button.click();
    await flush();
    button.click();
    await flush();
    assert.equal(button.textContent, 'Скопировано');
    await e4.runTimers(1500);
    assert.equal(button.textContent, 'Скопировать для iiko', 'подпись осталась «Скопировано»');
});

await test('мультипак: кандидат — единица упаковки, в тексте для iiko — строка «Упаковка»', async () => {
    const e5 = boot();
    await flush();
    const row = {
        gtin: '04600000000073', barcode: '4600000000073', status: 'similar', state: 'open', resolution: '',
        cards: [], candidates: [{ id: 'u1', name: 'Пиво Хеллес 0,45 ж/б', num: '101', group: 'Пиво', supplier: '',
            unit: 'шт', deleted: false, archived: false, keg: false, score: 0, pack: true, pack_units: '6',
            unit_gtin: '04600000000011' }],
        chz: { name: 'Пиво Хеллес 6 банок', brand: '', full_name: '', product_group: 'beer', volume: '',
            package_type: '', source: 'product_info', level: 'inner-pack', main_gtin: '04600000000011', pack_units: '6' },
        supplier: '', supplier_hint: '', note: '', qty: 2, receipts: [], first_seen_at: '', last_seen_at: '',
        classified_at: '', index_built_at: '', updated_at: '', updated_by: '', resolved_at: null, resolved_by: '', reopened: 0,
    };
    e5.api.state.rows = [row];
    e5.api.render();
    const text = flat(e5.row('04600000000073').textContent);
    assert.match(text, /единица этой упаковки \(в упаковке 6 шт\.\)/);
    assert.doesNotMatch(text, /совпало слов/);
    assert.match(e5.api.buildCopyText(row), /^Упаковка: 6 шт\. товара GTIN 04600000000011$/m);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

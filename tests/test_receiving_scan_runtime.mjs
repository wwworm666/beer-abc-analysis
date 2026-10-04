/**
 * ЗАПУСК экрана приёмщика РЦ (/receiving) в Node: настоящий scan.js в node:vm.
 *
 *     node tests/test_receiving_scan_runtime.mjs
 *
 * Вокруг скрипта — заглушки браузера: DOM (узлы по id из templates/receiving.html),
 * localStorage, fetch с поддельным сервером по контракту API (раздел 7 спецификации,
 * routes/receiving.py), WebAudio, vibrate, crypto, таймеры с виртуальным временем.
 * Разбор кода — настоящий static/js/receiving/codes.js (если файла нет — минимальная
 * заглушка с тем же контрактом), им же пользуется поддельный сервер.
 *
 * Проверяется: новая приёмка; сбор кода ручного сканера по event.code (Shift,
 * Ctrl+] = GS, русская раскладка не мешает, медленный набор — не скан); очередь в
 * localStorage до отправки, POST с client_id, повтор без связи с паузами и по
 * событию online, потерянный ответ не считается дважды, 401 держит очередь,
 * 400/409 выбрасывают сканы; поправка по ответу сервера («уже посчитана»); отмена
 * последнего (из очереди и на сервере); «Завершить» не пускает при непустой очереди;
 * продолжение по ?r= и работа по снимку без связи; камера; фото накладной.
 * Статические проверки файлов — tests/test_receiving_scan_render.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const require = createRequire(import.meta.url);

const SCAN_JS = read('static/js/receiving/scan.js');
const TEMPLATE = read('templates/receiving.html');
const CODES_PATH = path.join(ROOT, 'static/js/receiving/codes.js');
const HAVE_CODES = fs.existsSync(CODES_PATH);
const CODES_JS = HAVE_CODES ? fs.readFileSync(CODES_PATH, 'utf8') : null;

// Минимальная заглушка RcCodes на случай, если codes.js ещё не написан: тот же
// контракт (ok, kind, gtin, serial, key, code, reason, message), без раскладки.
const CODES_STUB = `(function (root) {
    function zfill(s) { while (s.length < 14) s = '0' + s; return s; }
    function parseCode(raw) {
        var code = String(raw == null ? '' : raw).trim();
        var fail = function (kind, reason) { return { ok: false, kind: kind, gtin: null, serial: null, key: code.slice(0, 200), code: code, reason: reason, message: 'Код не распознан — повторите' }; };
        if (!code) return fail('empty', 'empty');
        if (/^[0-9]+$/.test(code) && [8, 12, 13, 14].indexOf(code.length) !== -1) {
            var g = zfill(code);
            return { ok: true, kind: 'ean', gtin: g, serial: null, key: g, code: code, reason: '', message: 'Принято' };
        }
        if (/^01[0-9]{14}21./.test(code)) {
            var gt = code.slice(2, 16); var serial = code.slice(18).split('\\x1d')[0];
            return { ok: true, kind: 'datamatrix', gtin: gt, serial: serial, key: gt + '|' + serial, code: code, reason: '', message: 'Принято' };
        }
        return fail('unknown', 'unsupported');
    }
    root.RcCodes = { parseCode: parseCode };
    if (typeof module !== 'undefined' && module.exports) module.exports = root.RcCodes;
})(typeof window !== 'undefined' ? window : this);`;

function serverCodes() {
    if (HAVE_CODES) return require(CODES_PATH);
    const box = {};
    box.window = box;
    vm.createContext(box);
    vm.runInContext(CODES_STUB, box);
    return box.RcCodes;
}
const CODES = serverCodes();

// ---------------------------------------------------------------- тестовые коды
// GTIN с верной контрольной цифрой (как в tests/fixtures/receiving_codes.json).
const GTIN_A = '04610093628430';
const GTIN_B = '04606820000013';
const GS = '\x1d';
const DM_1 = '01' + GTIN_A + '21' + 'GLTP9kqZn5QRt' + GS + '93dGVz';
const DM_2 = '01' + GTIN_A + '21' + 'AbCdEfGhJk' + GS + '93XyZw';
const DM_3 = '01' + GTIN_A + '21' + 'MmNnPpQq77' + GS + '93Ab1c';
const DM_4 = '01' + GTIN_B + '21' + 'zzTop5Qx' + GS + '93Kw9z';
const EAN_A = '4610093628430';
const EAN_B = '4606820000013';

// ---------------------------------------------------------------- раннер
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
        console.log(`      ${e && e.stack ? e.stack.split('\n').slice(0, 3).join('\n      ') : e}`);
    }
}

// Объекты из vm-контекста живут в другом «мире» (свои Array.prototype):
// сравниваем через JSON.
const plain = (value) => JSON.parse(JSON.stringify(value));

// ---------------------------------------------------------------- DOM-заглушка
class FakeClassList {
    constructor() { this.set = new Set(); }
    add(...names) { names.forEach((n) => this.set.add(n)); }
    remove(...names) { names.forEach((n) => this.set.delete(n)); }
    toggle(name, force) {
        const on = force === undefined ? !this.set.has(name) : Boolean(force);
        if (on) this.set.add(name); else this.set.delete(name);
        return on;
    }
    contains(name) { return this.set.has(name); }
}

class FakeElement {
    constructor(tag, id, env) {
        this.tagName = String(tag).toUpperCase();
        this.id = id || '';
        this.env = env;
        this.children = [];
        this.ownText = '';
        this.attributes = {};
        this.listeners = {};
        this.classList = new FakeClassList();
        this.hidden = false;
        this.disabled = false;
        this.value = '';
        this.type = '';
        this.style = {};
        this.dataset = {};
        this.files = null;
        this.parentNode = null;
    }
    get className() { return [...this.classList.set].join(' '); }
    set className(value) { this.classList.set = new Set(String(value).split(/\s+/).filter(Boolean)); }
    get textContent() { return this.ownText + this.children.map((c) => c.textContent).join(''); }
    set textContent(value) { this.ownText = String(value); this.children = []; }
    get isConnected() { return true; }
    appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null; }
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
    dispatch(type, event) {
        const ev = event || {};
        if (!ev.target) ev.target = this;
        for (const fn of this.listeners[type] || []) fn(ev);
        return ev;
    }
    click() { return this.dispatch('click', { target: this, preventDefault() {} }); }
    focus() { this.env.document.activeElement = this; }
    blur() { if (this.env.document.activeElement === this) this.env.document.activeElement = this.env.document.body; }
    play() { return Promise.resolve(); }
    // Поиск по классу среди потомков — только для проверок теста.
    findAll(cls) {
        const out = [];
        const walk = (node) => {
            for (const child of node.children) {
                if (child.classList.contains(cls)) out.push(child);
                walk(child);
            }
        };
        walk(this);
        return out;
    }
}

// Узлы шаблона: тег и id из настоящего templates/receiving.html.
const TEMPLATE_NODES = [...TEMPLATE.matchAll(/<([a-z0-9]+)\b([^>]*?)\sid="([^"]+)"([^>]*)>/g)].map((m) => ({
    tag: m[1], id: m[3], hidden: /\shidden(\s|$|>)/.test(m[2] + ' ' + m[4] + ' '),
}));

// ---------------------------------------------------------------- поддельный сервер
const SCAN_RE = /^\/api\/receiving\/(\d+)\/scan$/;
const SCAN_DELETE_RE = /^\/api\/receiving\/(\d+)\/scans\/(\d+)$/;
const RECEIPT_RE = /^\/api\/receiving\/(\d+)$/;
const CLOSE_RE = /^\/api\/receiving\/(\d+)\/close$/;
const INVOICE_RE = /^\/api\/receiving\/(\d+)\/invoice$/;
const INVOICE_DELETE_RE = /^\/api\/receiving\/(\d+)\/invoice\/([^/]+)$/;
const CLIENT_ID_RE = /^[A-Za-z0-9-]{8,64}$/;

// Маршруты из раздела 7 спецификации: каждый запрос страницы обязан попасть в один из них.
const SPEC_ROUTES = [
    ['GET', /^\/api\/receiving$/],
    ['POST', /^\/api\/receiving$/],
    ['GET', /^\/api\/receiving\/\d+$/],
    ['POST', /^\/api\/receiving\/\d+\/scan$/],
    ['DELETE', /^\/api\/receiving\/\d+\/scans\/\d+$/],
    ['POST', /^\/api\/receiving\/\d+\/invoice$/],
    ['GET', /^\/api\/receiving\/invoice\/[^/]+$/],
    ['DELETE', /^\/api\/receiving\/\d+\/invoice\/[^/]+$/],
    ['POST', /^\/api\/receiving\/\d+\/close$/],
];

class FakeServer {
    constructor() {
        this.receipts = new Map();
        this.nextReceipt = 12;
        this.nextScan = 500;
        this.override = null;     // (call) -> {status, data} | null — подмена ответа
        this.deleted = new Set(); // удалённые в «Разборе приёмок»: скан в них — 409 receipt_deleted
    }

    addReceipt(extra) {
        const receipt = Object.assign({
            id: this.nextReceipt++, status: 'open', note: '', created_at: '2026-10-03T09:00:00+03:00',
            created_by: 'Приёмщик', closed_at: null, closed_by: '', process_state: 'none',
            processed_at: null, process_note: '', scans: [], invoices: [],
        }, extra || {});
        this.receipts.set(receipt.id, receipt);
        return receipt;
    }

    counts(r) {
        const live = r.scans.filter((s) => !s.deleted);
        const accepted = live.filter((s) => s.accepted);
        return {
            units: accepted.length,
            gtins: new Set(accepted.map((s) => s.gtin)).size,
            rejected: live.filter((s) => !s.accepted && s.reason !== 'repeat').length,
            repeats: live.filter((s) => s.reason === 'repeat').length,
            invoices: r.invoices.length,
        };
    }

    receiptDict(r) {
        const { scans, invoices, ...rest } = r;
        return Object.assign({}, rest, { counts: this.counts(r) });
    }

    scanDict(s) {
        return {
            id: s.id, gtin: s.gtin, kind: s.kind, accepted: s.accepted, reason: s.reason,
            raw_short: s.raw.split(GS).join(' ').slice(0, 60), scanned_at: s.scanned_at, source: s.source, by: 'Приёмщик',
        };
    }

    // Как receiving_store.add_scan: повтор client_id — тот же результат; повтор
    // принятой DataMatrix — accepted=0, reason='repeat'.
    record(r, code, clientId, source) {
        const replay = r.scans.find((s) => s.client_id === clientId);
        if (replay) return { scan: replay, replayed: true };
        const p = CODES.parseCode(code);
        let accepted = p.ok;
        let reason = p.ok ? '' : p.reason;
        if (p.ok && p.kind === 'datamatrix'
            && r.scans.some((s) => !s.deleted && s.accepted && s.kind === 'datamatrix' && s.key === p.key)) {
            accepted = false;
            reason = 'repeat';
        }
        const scan = {
            id: this.nextScan++, client_id: clientId, raw: code, kind: p.kind, gtin: p.gtin, key: p.ok ? p.key : '',
            accepted, reason, source: source || 'scanner', scanned_at: '2026-10-03T10:00:00+03:00', deleted: false,
        };
        r.scans.push(scan);
        return { scan, replayed: false };
    }

    resultOf(scan) {
        if (scan.accepted) return 'accepted';
        return scan.reason === 'repeat' ? 'repeat' : 'rejected';
    }

    handle(call) {
        if (this.override) {
            const res = this.override(call);
            if (res) return res;
        }
        const [pathname, query] = call.url.split('?');
        const params = new URLSearchParams(query || '');
        let m;
        if (pathname === '/api/receiving' && call.method === 'GET') {
            const status = params.get('status') || 'all';
            const list = [...this.receipts.values()].filter((r) => status === 'all' || r.status === status)
                .sort((a, b) => b.id - a.id).map((r) => this.receiptDict(r));
            return { status: 200, data: { receipts: list } };
        }
        if (pathname === '/api/receiving' && call.method === 'POST') {
            return { status: 201, data: { receipt: this.receiptDict(this.addReceipt({ created_by: 'Приёмщик' })) } };
        }
        if ((m = RECEIPT_RE.exec(pathname)) && call.method === 'GET') {
            const r = this.receipts.get(Number(m[1]));
            if (!r) return { status: 404, data: { error: 'Приёмка не найдена' } };
            const live = r.scans.filter((s) => !s.deleted);
            const lines = {};
            for (const s of live.filter((x) => x.accepted)) lines[s.gtin] = (lines[s.gtin] || 0) + 1;
            return {
                status: 200,
                data: {
                    receipt: this.receiptDict(r),
                    lines: Object.entries(lines).map(([gtin, qty]) => ({ gtin, qty, kind: 'datamatrix' })),
                    recent: live.slice().reverse().slice(0, 20).map((s) => this.scanDict(s)),
                    invoices: r.invoices.slice(),
                    dm_keys: r.status === 'open' ? live.filter((s) => s.accepted && s.kind === 'datamatrix').map((s) => s.key) : [],
                    rows: [],
                },
            };
        }
        if ((m = SCAN_RE.exec(pathname)) && call.method === 'POST') {
            const r = this.receipts.get(Number(m[1]));
            if (!r && this.deleted.has(Number(m[1]))) {
                return { status: 409, data: { error: 'Приёмку удалили в «Разборе приёмок» — сканы в неё не записываются',
                                              code: 'receipt_deleted' } };
            }
            if (!r) return { status: 404, data: { error: 'Приёмка не найдена' } };
            const body = call.body || {};
            if (typeof body.code !== 'string') return { status: 400, data: { error: 'code — строка с прочитанным кодом' } };
            if (typeof body.client_id !== 'string' || !CLIENT_ID_RE.test(body.client_id)) {
                return { status: 400, data: { error: 'client_id — от 8 до 64 символов: латиница, цифры, дефис' } };
            }
            if (r.status !== 'open') return { status: 409, data: { error: 'Приёмка уже закрыта — сканы в ней не меняются', code: 'receipt_closed' } };
            const saved = this.record(r, body.code, body.client_id, body.source);
            const result = this.resultOf(saved.scan);
            const message = result === 'accepted' ? 'Принято' : (result === 'repeat' ? 'Уже посчитана' : 'Код не распознан — повторите');
            return {
                status: 200,
                data: { result, kind: saved.scan.kind, gtin: saved.scan.gtin, message, scan_id: saved.scan.id, replayed: saved.replayed, counts: this.counts(r) },
            };
        }
        if ((m = SCAN_DELETE_RE.exec(pathname)) && call.method === 'DELETE') {
            const r = this.receipts.get(Number(m[1]));
            if (!r) return { status: 404, data: { error: 'Приёмка не найдена' } };
            if (r.status !== 'open') return { status: 409, data: { error: 'Приёмка уже закрыта', code: 'receipt_closed' } };
            const scan = r.scans.find((s) => s.id === Number(m[2]));
            if (!scan) return { status: 404, data: { error: 'Скан не найден' } };
            scan.deleted = true;
            return { status: 200, data: { deleted: true, counts: this.counts(r) } };
        }
        if ((m = CLOSE_RE.exec(pathname)) && call.method === 'POST') {
            const r = this.receipts.get(Number(m[1]));
            if (!r) return { status: 404, data: { error: 'Приёмка не найдена' } };
            r.status = 'closed';
            r.closed_at = '2026-10-03T11:00:00+03:00';
            r.process_state = 'running';
            return { status: 202, data: { receipt: this.receiptDict(r), processing: 'started' } };
        }
        if ((m = INVOICE_RE.exec(pathname)) && call.method === 'POST') {
            const r = this.receipts.get(Number(m[1]));
            if (!r) return { status: 404, data: { error: 'Приёмка не найдена' } };
            const name = 'r' + r.id + '_20261003T100000_0000000' + r.invoices.length + '.jpg';
            const invoice = { name, url: '/api/receiving/invoice/' + name, size: 1000, uploaded_at: '2026-10-03T10:05:00+03:00', uploaded_by: 'Приёмщик' };
            r.invoices.push(invoice);
            return { status: 201, data: { invoice, invoices: r.invoices.slice() } };
        }
        if ((m = INVOICE_DELETE_RE.exec(pathname)) && call.method === 'DELETE') {
            const r = this.receipts.get(Number(m[1]));
            const name = decodeURIComponent(m[2]);
            if (!r || !r.invoices.some((i) => i.name === name)) return { status: 404, data: { error: 'Фото не найдено' } };
            r.invoices = r.invoices.filter((i) => i.name !== name);
            return { status: 200, data: { deleted: true, invoices: r.invoices.slice() } };
        }
        return { status: 404, data: { error: 'нет маршрута ' + call.method + ' ' + call.url } };
    }
}

// ---------------------------------------------------------------- окружение
function makeEnv(options) {
    const opts = options || {};
    const env = {
        server: opts.server || new FakeServer(),
        net: { mode: opts.offline ? 'offline' : 'online', calls: [], hold: opts.hold || null },   // online | offline | lost (сервер записал, ответ потерян)
        timers: { now: 1000, seq: 0, tasks: new Map() },
        tones: [],
        vibrations: [],
        storageWrites: [],
        warnings: [],
        windowListeners: [],
        docListeners: {},
        replaced: [],
        held: [],
    };
    env.release = () => { const list = env.held.splice(0); list.forEach((go) => go()); };

    const storage = new Map(Object.entries(opts.storage || {}));
    env.localStorage = {
        getItem: (k) => (storage.has(k) ? storage.get(k) : null),
        setItem: (k, v) => { storage.set(k, String(v)); env.storageWrites.push(k); },
        removeItem: (k) => { storage.delete(k); },
        dump: () => Object.fromEntries(storage),
    };

    const document = {
        hidden: false,
        visibilityState: 'visible',
        getElementById: (id) => env.byId.get(id) || null,
        createElement: (tag) => new FakeElement(tag, '', env),
        addEventListener: (type, fn) => { (env.docListeners[type] = env.docListeners[type] || []).push(fn); },
    };
    env.document = document;
    document.body = new FakeElement('body', '', env);
    document.documentElement = new FakeElement('html', '', env);
    document.activeElement = document.body;

    env.byId = new Map();
    for (const node of TEMPLATE_NODES) {
        const element = new FakeElement(node.tag, node.id, env);
        element.hidden = node.hidden;
        if (node.tag === 'input') element.type = node.id === 'rc-photo-input' ? 'file' : 'text';
        env.byId.set(node.id, element);
    }

    const setTimeoutFake = (fn, ms) => {
        const id = ++env.timers.seq;
        env.timers.tasks.set(id, { at: env.timers.now + (Number(ms) || 0), fn });
        return id;
    };
    const clearTimeoutFake = (id) => { env.timers.tasks.delete(id); };

    class FakeAudioContext {
        constructor() { this.state = 'suspended'; this.currentTime = 0; this.destination = {}; }
        resume() { this.state = 'running'; return Promise.resolve(); }
        createOscillator() {
            const osc = {
                type: '', frequency: { value: 0 }, connect() {},
                start: () => { env.tones.push({ freq: osc.frequency.value, type: osc.type }); },
                stop() {},
            };
            return osc;
        }
        createGain() { return { gain: { value: 1, setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} }; }
    }

    class FakeFormData {
        constructor() { this.entries = []; }
        append(name, value, filename) { this.entries.push([name, value, filename]); }
    }

    const location = { pathname: '/receiving', search: opts.search || '' };
    const history = {
        replaceState: (_s, _t, url) => {
            env.replaced.push(url);
            const [p, q] = String(url).split('?');
            location.pathname = p;
            location.search = q ? '?' + q : '';
        },
    };

    const fetchFake = (url, init) => {
        const options = init || {};
        let body = options.body;
        if (typeof body === 'string') body = JSON.parse(body);
        const call = {
            url, method: options.method || 'GET', body,
            headers: options.headers || {},
            queueAtCall: env.localStorage.getItem('rc.queue.v1'),
        };
        env.net.calls.push(call);
        if (env.net.mode === 'offline') return Promise.reject(new TypeError('Failed to fetch'));
        const respond = () => {
            const res = env.server.handle(call);
            call.status = res.status;
            if (env.net.mode === 'lost') return Promise.reject(new TypeError('network connection was lost'));
            return Promise.resolve({
                ok: res.status >= 200 && res.status < 300,
                status: res.status,
                json: () => Promise.resolve(JSON.parse(JSON.stringify(res.data))),
            });
        };
        // Придержать ответ (запрос «в пути»), пока тест не вызовет env.release().
        if (env.net.hold && env.net.hold(call)) {
            return new Promise((resolve, reject) => {
                env.held.push(() => respond().then(resolve, reject));
            });
        }
        return respond();
    };

    const navigator = {
        onLine: true,
        vibrate: (pattern) => { env.vibrations.push(JSON.stringify(pattern)); return true; },
        mediaDevices: opts.mediaDevices,
        wakeLock: opts.wakeLock,
    };

    let uuidSeq = 0;
    const cryptoStub = opts.noUuid
        ? { getRandomValues: (arr) => { for (let i = 0; i < arr.length; i++) arr[i] = (i * 37 + 11) % 256; return arr; } }
        : { randomUUID: () => '00000000-0000-4000-8000-' + String(++uuidSeq).padStart(12, '0') };

    const sandbox = {
        console: {
            log: () => {},
            warn: (...args) => env.warnings.push(args.map(String).join(' ')),
            error: (...args) => env.warnings.push(args.map(String).join(' ')),
        },
        document,
        location,
        history,
        navigator,
        localStorage: env.localStorage,
        fetch: fetchFake,
        setTimeout: setTimeoutFake,
        clearTimeout: clearTimeoutFake,
        performance: { now: () => env.timers.now },
        URLSearchParams,
        FormData: FakeFormData,
        AudioContext: FakeAudioContext,
        crypto: cryptoStub,
        addEventListener: (type, fn, capture) => {
            env.windowListeners.push({ type, fn, capture: capture === true || Boolean(capture && capture.capture) });
        },
    };
    if (opts.barcodeDetector) sandbox.BarcodeDetector = opts.barcodeDetector;
    if (opts.noWebAssembly) sandbox.WebAssembly = undefined;
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    if (!opts.noCodes) {
        vm.runInContext(HAVE_CODES ? CODES_JS : CODES_STUB, sandbox, { filename: 'codes.js' });
    }
    vm.runInContext(SCAN_JS, sandbox, { filename: 'scan.js' });
    env.sandbox = sandbox;
    env.api = sandbox.__rcScan;
    env.$ = (id) => env.byId.get(id);
    env.queue = () => JSON.parse(env.localStorage.getItem('rc.queue.v1') || '[]');
    env.scanCalls = () => env.net.calls.filter((c) => c.method === 'POST' && SCAN_RE.test(c.url));
    return env;
}

// Дать отработать микрозадачам (ответы заглушки fetch — уже разрешённые промисы).
async function settle(env) {
    for (let i = 0; i < 6; i++) await new Promise((resolve) => setImmediate(resolve));
    if (env) await Promise.resolve();
}

// Сдвинуть виртуальные часы, выполняя таймеры по порядку.
async function advance(env, ms) {
    const target = env.timers.now + ms;
    for (;;) {
        let next = null;
        for (const [id, task] of env.timers.tasks) {
            if (task.at <= target && (!next || task.at < next.task.at)) next = { id, task };
        }
        if (!next) break;
        env.timers.tasks.delete(next.id);
        env.timers.now = Math.max(env.timers.now, next.task.at);
        next.task.fn();
        await settle(env);
    }
    env.timers.now = target;
}

async function boot(options) {
    const env = makeEnv(options);
    await env.api.ready;
    await settle(env);
    return env;
}

// ---------------------------------------------------------------- клавиатура
const RU = {
    q: 'й', w: 'ц', e: 'у', r: 'к', t: 'е', y: 'н', u: 'г', i: 'ш', o: 'щ', p: 'з',
    a: 'ф', s: 'ы', d: 'в', f: 'а', g: 'п', h: 'р', j: 'о', k: 'л', l: 'д',
    z: 'я', x: 'ч', c: 'с', v: 'м', b: 'и', n: 'т', m: 'ь',
};

function keyEvent(env, fields) {
    return Object.assign({
        code: '', key: '', shiftKey: false, ctrlKey: false, altKey: false, metaKey: false,
        target: env.document.body, defaultPrevented: false, propagationStopped: false,
        preventDefault() { this.defaultPrevented = true; },
        stopPropagation() { this.propagationStopped = true; },
    }, fields);
}

// Нажатие: сначала слушатели window в фазе захвата, затем (если не остановлено) document.
function press(env, fields, dt) {
    env.timers.now += dt === undefined ? 5 : dt;
    const event = keyEvent(env, fields);
    for (const l of env.windowListeners.filter((x) => x.type === 'keydown' && x.capture)) l.fn(event);
    if (!event.propagationStopped) {
        event.reachedDocument = true;
        for (const fn of env.docListeners.keydown || []) fn(event);
    }
    return event;
}

// Событие клавиши для символа так, как его шлёт сканер-клавиатура.
function keyFor(ch, layout) {
    if (ch === GS) return { code: 'BracketRight', key: layout === 'ru' ? 'ъ' : ']', ctrlKey: true };
    if (/[0-9]/.test(ch)) return { code: 'Digit' + ch, key: ch };
    if (/[a-z]/.test(ch)) return { code: 'Key' + ch.toUpperCase(), key: layout === 'ru' ? RU[ch] : ch };
    if (/[A-Z]/.test(ch)) {
        const low = ch.toLowerCase();
        return { code: 'Key' + ch, key: layout === 'ru' ? RU[low].toUpperCase() : ch, shiftKey: true };
    }
    throw new Error('нет клавиши для ' + JSON.stringify(ch));
}

// Скан: символы с паузой 5 мс и Enter в конце. Возвращает события (для проверок).
function scan(env, code, options) {
    const opts = options || {};
    const events = [];
    for (const ch of code) {
        const fields = keyFor(ch, opts.layout);
        if (opts.noCode && fields.code !== 'BracketRight') fields.code = '';
        events.push(press(env, fields, opts.gap));
    }
    events.push(press(env, { code: opts.end || 'Enter', key: opts.end === 'Tab' ? 'Tab' : 'Enter' }, opts.gap));
    return events;
}

const units = (env) => Number(env.$('rc-units').textContent);
const tonesSince = (env, mark) => env.tones.slice(mark).map((t) => t.freq);

// ================================================================ тесты

await test('без ?r= — стартовый экран: список открытых приёмок из GET /api/receiving?status=open', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 7, created_by: 'Иван' });
    server.nextReceipt = 12;
    const env = await boot({ server });
    assert.equal(env.net.calls[0].method, 'GET');
    assert.equal(env.net.calls[0].url, '/api/receiving?status=open');
    assert.equal(env.$('rc-start').hidden, false);
    assert.equal(env.$('rc-scan').hidden, true);
    assert.equal(env.$('rc-done').hidden, true);
    const rows = env.$('rc-open-list').findAll('rc-open-row');
    assert.equal(rows.length, 1);
    assert.match(rows[0].textContent, /Приёмка №7/);
    assert.match(rows[0].textContent, /Иван/);
    assert.match(rows[0].textContent, /Продолжить/);
    assert.equal(env.$('rc-open-empty').hidden, true);
});

await test('«Продолжить» открывает приёмку из списка: GET /api/receiving/<id>, адрес ?r=<id>', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 7 });
    const env = await boot({ server });
    const button = env.$('rc-open-list').findAll('rc-btn')[0];
    button.click();
    await settle(env);
    assert.equal(env.net.calls.at(-1).url, '/api/receiving/7');
    assert.equal(env.$('rc-scan').hidden, false);
    assert.equal(env.$('rc-title').textContent, 'Приёмка №7');
    assert.equal(env.sandbox.location.search, '?r=7');
});

// Основной сценарий — одно окружение на несколько шагов.
const main = await boot();

await test('«Новая приёмка»: POST /api/receiving и сразу экран сканирования', async () => {
    const env = main;
    env.$('rc-new').click();
    await settle(env);
    const post = env.net.calls.find((c) => c.method === 'POST' && c.url === '/api/receiving');
    assert.ok(post, 'нет POST /api/receiving');
    assert.equal(env.$('rc-scan').hidden, false);
    assert.equal(env.$('rc-start').hidden, true);
    assert.equal(env.$('rc-title').textContent, 'Приёмка №12');
    assert.equal(env.sandbox.location.search, '?r=12');
    assert.equal(units(env), 0);
    assert.equal(env.$('rc-status').textContent, 'Сканируйте товар');
    assert.equal(env.$('rc-pending').hidden, true);
});

await test('сканер: DataMatrix по event.code (Shift = заглавные, Ctrl+] = GS), Enter — скан', async () => {
    const env = main;
    const mark = env.tones.length;
    const events = scan(env, DM_1);
    for (const ev of events) {
        assert.ok(ev.defaultPrevented, 'нажатие ' + ev.code + ' не погашено');
        assert.ok(ev.propagationStopped, 'нажатие ' + ev.code + ' дошло до document (горячая клавиша меню)');
    }
    // Очередь в localStorage — ДО отправки.
    const call = env.scanCalls().at(-1);
    assert.ok(call, 'скан не отправлен');
    assert.equal(call.url, '/api/receiving/12/scan');
    assert.equal(call.body.code, DM_1);
    assert.match(call.body.client_id, CLIENT_ID_RE);
    assert.equal(call.body.source, 'scanner');
    assert.ok(typeof call.body.client_time === 'string' && call.body.client_time.length <= 40);
    const queued = JSON.parse(call.queueAtCall || '[]');
    assert.equal(queued.length, 1, 'скан не лёг в localStorage до POST');
    assert.equal(queued[0].client_id, call.body.client_id);
    assert.equal(queued[0].code, DM_1);
    // Мгновенный сигнал по разбору в браузере.
    assert.deepEqual(tonesSince(env, mark), [1760], 'нет короткого высокого сигнала');
    assert.equal(env.vibrations.at(-1), '30');
    assert.ok(env.$('rc-counter').classList.contains('is-flash-ok'), 'нет зелёной вспышки');
    await settle(env);
    assert.deepEqual(env.queue(), [], 'после 2xx скан не убран из очереди');
    assert.equal(units(env), 1);
    assert.equal(env.$('rc-gtins').textContent, '1');
    assert.equal(env.$('rc-gtins-label').textContent, 'позиция');
    assert.equal(env.$('rc-status').textContent, 'Принято');
    assert.ok(env.$('rc-status').classList.contains('is-ok'));
    assert.match(env.$('rc-last').textContent, new RegExp('GTIN ' + GTIN_A));
    await advance(env, 1000);
    assert.ok(!env.$('rc-counter').classList.contains('is-flash-ok'), 'вспышка не погасла');
});

await test('русская раскладка не мешает: те же клавиши с кириллицей в event.key дают тот же код', async () => {
    const env = main;
    scan(env, DM_2, { layout: 'ru' });
    const call = env.scanCalls().at(-1);
    assert.equal(call.body.code, DM_2, 'код собран не по event.code');
    await settle(env);
    assert.equal(units(env), 2);
});

await test('клавиша без event.code: символ из event.key (кириллицу переводит разбор кода)', async () => {
    const env = main;
    const mark = env.tones.length;
    scan(env, DM_3, { layout: 'ru', noCode: true });
    const call = env.scanCalls().at(-1);
    assert.match(call.body.code, /[а-яА-Я]/, 'ожидался сырой код с кириллицей');
    if (HAVE_CODES) {
        assert.deepEqual(tonesSince(env, mark), [1760], 'кириллица не переведена разбором');
        await settle(env);
        assert.equal(units(env), 3);
    } else {
        await settle(env);
    }
});

await test('повтор той же DataMatrix: «Уже посчитана», двойной сигнал, счётчик не растёт, скан всё равно уходит', async () => {
    const env = main;
    const before = units(env);
    const mark = env.tones.length;
    const sent = env.scanCalls().length;
    scan(env, DM_1);
    assert.deepEqual(tonesSince(env, mark), [1320, 1320]);
    assert.equal(env.vibrations.at(-1), '[40,60,40]');
    assert.equal(env.$('rc-status').textContent, 'Уже посчитана');
    assert.ok(env.$('rc-status').classList.contains('is-repeat'));
    assert.ok(env.$('rc-counter').classList.contains('is-flash-repeat'));
    assert.equal(units(env), before);
    await settle(env);
    assert.equal(env.scanCalls().length, sent + 1, 'повтор не отправлен для диагностики');
    assert.equal(units(env), before);
    assert.match(env.$('rc-recent-count').textContent, /повторов: 1/);
});

await test('EAN считается каждый раз и добавляет позицию; Tab тоже завершает код', async () => {
    const env = main;
    const before = units(env);
    scan(env, EAN_B);
    await settle(env);
    scan(env, EAN_B, { end: 'Tab' });
    await settle(env);
    assert.equal(units(env), before + 2);
    assert.equal(env.$('rc-gtins').textContent, '2');
    assert.equal(env.$('rc-gtins-label').textContent, 'позиции');
});

await test('не распознан (SSCC короба): низкий длинный сигнал, красная вспышка, текст разбора', async () => {
    const env = main;
    const before = units(env);
    const mark = env.tones.length;
    scan(env, '00146100936284300015');
    assert.deepEqual(tonesSince(env, mark), [220]);
    assert.equal(env.vibrations.at(-1), '300');
    assert.ok(env.$('rc-counter').classList.contains('is-flash-bad'));
    assert.ok(env.$('rc-status').classList.contains('is-bad'));
    if (HAVE_CODES) assert.equal(env.$('rc-status').textContent, 'Код короба или паллеты — отсканируйте бутылку');
    await settle(env);
    assert.equal(units(env), before);
    assert.match(env.$('rc-recent-count').textContent, /не распознано: 1/);
});

await test('медленный набор руками (пауза > 80 мс) — не скан: ни сигнала, ни запроса', async () => {
    const env = main;
    const sent = env.scanCalls().length;
    const mark = env.tones.length;
    for (const ch of '46100936') press(env, keyFor(ch), 150);
    const enter = press(env, { code: 'Enter', key: 'Enter' }, 150);
    await settle(env);
    assert.equal(env.scanCalls().length, sent);
    assert.deepEqual(tonesSince(env, mark), []);
    assert.equal(enter.defaultPrevented, false, 'Enter после ручного набора не должен гаситься');
});

await test('пауза > 80 мс начинает буфер заново: в код идёт только быстрая очередь символов', async () => {
    const env = main;
    press(env, keyFor('x'), 5);
    press(env, keyFor('y'), 5);
    scan(env, EAN_A, { gap: 5 });   // первая цифра придёт через 5 мс — обнулим паузой ниже
    const call = env.scanCalls().at(-1);
    assert.equal(call.body.code, 'xy' + EAN_A, 'быстрые символы должны склеиться');
    await settle(env);
    // теперь с паузой между мусором и кодом
    press(env, keyFor('q'), 5);
    env.timers.now += 200;
    scan(env, EAN_A);
    assert.equal(env.scanCalls().at(-1).body.code, EAN_A);
    await settle(env);
});

await test('Enter с пустым буфером, Ctrl+R, стрелки и набор в поле ввода — не трогаются', async () => {
    const env = main;
    const sent = env.scanCalls().length;
    const enter = press(env, { code: 'Enter', key: 'Enter' }, 500);
    assert.equal(enter.defaultPrevented, false);
    assert.equal(enter.reachedDocument, true);
    const reload = press(env, { code: 'KeyR', key: 'r', ctrlKey: true });
    assert.equal(reload.defaultPrevented, false);
    const arrow = press(env, { code: 'ArrowDown', key: 'ArrowDown' });
    assert.equal(arrow.defaultPrevented, false);
    const input = env.$('rc-sheet-input');
    const typed = press(env, { code: 'Digit4', key: '4', target: input });
    assert.equal(typed.defaultPrevented, false, 'набор в поле «вручную» перехвачен сканером');
    const space = press(env, { code: 'Space', key: ' ' }, 500);
    assert.equal(space.defaultPrevented, false, 'пробел по кнопке перехвачен');
    await settle(env);
    assert.equal(env.scanCalls().length, sent);
});

await test('буква «m» серийника не доходит до горячей клавиши меню в nav.html', async () => {
    const env = main;
    const ev = press(env, { code: 'KeyM', key: 'm' }, 500);
    assert.ok(ev.propagationStopped && ev.defaultPrevented);
    assert.equal(ev.reachedDocument, undefined);
    press(env, { code: 'Escape', key: 'Escape' }, 500);   // сбросить буфер паузой
});

await test('без связи: скан остаётся в очереди, «не отправлено: 1», счётчик локальный; повтор 2 с, 5 с', async () => {
    const env = main;
    const before = units(env);
    env.net.mode = 'offline';
    const sent = env.scanCalls().length;
    scan(env, DM_4);
    await settle(env);
    assert.equal(env.queue().length, 1);
    const clientId = env.queue()[0].client_id;
    assert.equal(units(env), before + 1, 'счётчик = серверный + принятые в очереди');
    assert.equal(env.$('rc-gtins').textContent, '2', 'GTIN_B уже был — позиций по-прежнему 2');
    assert.equal(env.$('rc-pending').hidden, false);
    assert.match(env.$('rc-pending').textContent, /Не отправлено: 1/);
    assert.match(env.$('rc-pending').textContent, /нет связи/);
    assert.equal(env.scanCalls().length, sent + 1);
    await advance(env, 1999);
    assert.equal(env.scanCalls().length, sent + 1, 'повтор раньше 2 с');
    await advance(env, 1);
    assert.equal(env.scanCalls().length, sent + 2, 'нет повтора через 2 с');
    await advance(env, 4999);
    assert.equal(env.scanCalls().length, sent + 2, 'второй повтор раньше 5 с');
    await advance(env, 1);
    assert.equal(env.scanCalls().length, sent + 3, 'нет повтора через 5 с');
    for (const call of env.scanCalls().slice(sent)) assert.equal(call.body.client_id, clientId, 'повтор с другим client_id');
    assert.equal(env.queue().length, 1, 'очередь потеряна без связи');
});

await test('связь вернулась (событие online): очередь уходит, счётчик с сервера', async () => {
    const env = main;
    const before = units(env);
    env.net.mode = 'online';
    for (const l of env.windowListeners.filter((x) => x.type === 'online')) l.fn({});
    await settle(env);
    assert.deepEqual(env.queue(), []);
    assert.equal(units(env), before);
    assert.equal(env.$('rc-pending').hidden, true);
    assert.equal(env.timers.tasks.size >= 0, true);
});

await test('потерянный ответ: сервер записал скан, повтор тем же client_id не считает его дважды', async () => {
    const env = main;
    const server = env.server.receipts.get(12);
    const before = server.scans.filter((s) => !s.deleted && s.accepted).length;
    env.net.mode = 'lost';
    scan(env, EAN_A);
    await settle(env);
    assert.equal(env.queue().length, 1, 'скан ушёл из очереди без ответа сервера');
    env.net.mode = 'online';
    await advance(env, 2000);
    assert.deepEqual(env.queue(), []);
    const after = server.scans.filter((s) => !s.deleted && s.accepted).length;
    assert.equal(after, before + 1, 'сервер посчитал повтор запроса дважды');
    assert.equal(units(env), after);
});

await test('401 (сессия истекла): очередь держится, «Войдите снова» со ссылкой назад на приёмку', async () => {
    const env = main;
    env.server.override = (call) => (call.method === 'POST' && SCAN_RE.test(call.url)
        ? { status: 401, data: { error: 'Требуется вход', auth_required: true } } : null);
    scan(env, DM_3.replace('MmNnPpQq77', 'Auth401xyz'));
    await settle(env);
    assert.equal(env.queue().length, 1, '401 выбросил скан');
    assert.equal(env.$('rc-auth').hidden, false);
    assert.equal(env.$('rc-login').getAttribute('href'), '/login?next=' + encodeURIComponent('/receiving?r=12'));
    assert.match(env.$('rc-pending').textContent, /нужен вход/);
    // Повторы продолжаются: вошёл в соседней вкладке — сканы уйдут сами.
    await advance(env, 2000);
    assert.equal(env.queue().length, 1);
    env.server.override = null;
    env.document.hidden = false;
    for (const fn of env.docListeners.visibilitychange || []) fn({});
    await settle(env);
    assert.deepEqual(env.queue(), []);
    assert.equal(env.$('rc-auth').hidden, true);
});

await test('ответ сервера главнее: локально «принято», сервер — «repeat» -> счётчик по серверу и сигнал', async () => {
    const env = main;
    const r = env.server.receipts.get(12);
    const serverUnits = () => r.scans.filter((s) => !s.deleted && s.accepted).length;
    // Ту же бутылку только что посчитал второй телефон: в dm_keys этой вкладки её нет.
    const other = DM_4.replace('zzTop5Qx', 'OtherPh1');
    env.server.record(r, other, 'other-device-0001', 'scanner');
    const before = units(env);
    const mark = env.tones.length;
    scan(env, other);
    assert.equal(units(env), before + 1, 'локально скан принят');
    await settle(env);
    assert.deepEqual(tonesSince(env, mark), [1760, 1320, 1320], 'нет сигнала поправки');
    assert.equal(units(env), serverUnits(), 'счётчик не совпал с сервером');
    assert.equal(env.$('rc-status').textContent, 'Уже посчитана');
    assert.ok(env.$('rc-status').classList.contains('is-repeat'));
    // Ключ запомнен: следующий скан этой бутылки — сразу «повтор».
    const mark2 = env.tones.length;
    scan(env, other);
    assert.deepEqual(tonesSince(env, mark2), [1320, 1320]);
    await settle(env);
});

await test('ответ сервера главнее: локально «принято», сервер — «rejected» -> счётчик назад, красный сигнал', async () => {
    const env = main;
    const r = env.server.receipts.get(12);
    env.server.override = (call) => (call.method === 'POST' && SCAN_RE.test(call.url) && call.body.code === EAN_B
        ? { status: 200, data: { result: 'rejected', kind: 'ean', gtin: null, message: 'Код не распознан — повторите',
                                 scan_id: 9999, replayed: false, counts: env.server.counts(r) } }
        : null);
    const before = units(env);
    const mark = env.tones.length;
    scan(env, EAN_B);
    assert.equal(units(env), before + 1);
    await settle(env);
    assert.deepEqual(tonesSince(env, mark), [1760, 220]);
    assert.equal(units(env), before, 'счётчик не вернулся');
    assert.equal(env.$('rc-status').textContent, 'Код не распознан — повторите');
    assert.ok(env.$('rc-status').classList.contains('is-bad'));
    env.server.override = null;
});

await test('400 на скан: этот скан выброшен с сообщением, следующие уходят', async () => {
    const env = main;
    env.server.override = (call) => (call.method === 'POST' && SCAN_RE.test(call.url) && call.body.code === EAN_A + '0'
        ? { status: 400, data: { error: 'code — строка с прочитанным кодом' } } : null);
    env.net.mode = 'offline';
    scan(env, EAN_A + '0');   // 14 цифр, контрольная неверна — локально «не распознан»
    scan(env, EAN_B);
    await settle(env);
    assert.equal(env.queue().length, 2);
    env.net.mode = 'online';
    await advance(env, 30000);
    assert.deepEqual(env.queue(), []);
    assert.match(env.$('rc-toast').textContent, /Скан не принят сервером/);
    env.server.override = null;
});

await test('«Отменить последний»: неотправленный скан убирается из очереди, отправлявшийся — удаляется на сервере', async () => {
    const env = main;
    const server = env.server.receipts.get(12);
    const serverUnits = () => server.scans.filter((s) => !s.deleted && s.accepted).length;
    const before = units(env);
    env.net.mode = 'offline';
    scan(env, EAN_B);           // попытка отправки была (tries = 1)
    await settle(env);
    scan(env, EAN_A);           // повторная попытка уходит за первым, этот ещё не отправлялся
    await settle(env);
    assert.equal(env.queue().length, 2);
    assert.equal(env.queue()[1].tries, 0);
    assert.equal(units(env), before + 2);

    env.$('rc-undo').click();   // последний: ещё не отправлялся — просто из очереди
    await settle(env);
    assert.equal(env.queue().length, 1);
    assert.equal(units(env), before + 1);

    env.$('rc-undo').click();   // отправлялся: мог дойти — помечается «отменить»
    await settle(env);
    assert.equal(env.queue().length, 1);
    assert.equal(env.queue()[0].undo, true);
    assert.equal(units(env), before);
    assert.match(env.$('rc-recent').textContent, /Отменяется/);

    const serverBefore = serverUnits();
    env.net.mode = 'online';
    await advance(env, 30000);
    assert.deepEqual(env.queue(), []);
    const del = env.net.calls.filter((c) => c.method === 'DELETE' && SCAN_DELETE_RE.test(c.url));
    assert.ok(del.length >= 1, 'отменённый скан не удалён на сервере');
    assert.equal(serverUnits(), serverBefore, 'на сервере остался отменённый скан');
    assert.equal(units(env), before);
});

await test('«Отменить последний» при пустой очереди: DELETE последнего принятого скана сервера', async () => {
    const env = main;
    const server = env.server.receipts.get(12);
    const lastAccepted = server.scans.filter((s) => !s.deleted && s.accepted).at(-1);
    const before = units(env);
    env.$('rc-undo').click();
    await settle(env);
    const del = env.net.calls.filter((c) => c.method === 'DELETE').at(-1);
    assert.equal(del.url, '/api/receiving/12/scans/' + lastAccepted.id);
    assert.equal(lastAccepted.deleted, true);
    assert.equal(units(env), before - 1);
    assert.equal(env.net.calls.at(-1).url, '/api/receiving/12', 'после отмены приёмка не перечитана');
});

await test('«Завершить» не пускает, пока очередь не пуста: «Есть неотправленные сканы — дождитесь связи»', async () => {
    const env = main;
    env.net.mode = 'offline';
    scan(env, EAN_A);
    await settle(env);
    env.$('rc-finish').click();
    await settle(env);
    assert.equal(env.$('rc-sheet-wrap').hidden, true, 'окно подтверждения открылось при непустой очереди');
    assert.equal(env.$('rc-toast').textContent, 'Есть неотправленные сканы — дождитесь связи');
    assert.ok(!env.net.calls.some((c) => CLOSE_RE.test(c.url)), 'ушёл POST close');
    env.net.mode = 'online';
    await advance(env, 30000);
    assert.deepEqual(env.queue(), []);
});

await test('скан при открытом подтверждении отменяет завершение', async () => {
    const env = main;
    env.$('rc-finish').click();
    assert.equal(env.$('rc-sheet-wrap').hidden, false);
    scan(env, EAN_A);
    assert.equal(env.$('rc-sheet-wrap').hidden, true);
    await settle(env);
});

await test('«Завершить»: подтверждение со счётчиком -> POST close -> «Приёмка №12 передана в разбор»', async () => {
    const env = main;
    const shown = units(env);
    env.$('rc-finish').click();
    assert.equal(env.$('rc-sheet-wrap').hidden, false);
    assert.equal(env.$('rc-sheet-title').textContent, 'Завершить приёмку №12?');
    assert.match(env.$('rc-sheet-text').textContent, new RegExp('Посчитано: ' + shown + ' шт\\.'));
    await advance(env, 100);
    assert.equal(env.document.activeElement, env.$('rc-sheet-cancel'), 'фокус не на «Отмене»');
    env.$('rc-sheet-ok').click();
    await settle(env);
    const close = env.net.calls.find((c) => c.method === 'POST' && CLOSE_RE.test(c.url));
    assert.ok(close);
    assert.equal(close.url, '/api/receiving/12/close');
    assert.equal(env.$('rc-done').hidden, false);
    assert.equal(env.$('rc-scan').hidden, true);
    assert.equal(env.$('rc-sheet-wrap').hidden, true);
    assert.equal(env.$('rc-done-title').textContent, 'Приёмка №12 передана в разбор');
    assert.match(env.$('rc-done-text').textContent, new RegExp('Посчитано: ' + shown + ' шт\\.'));
    assert.equal(env.$('rc-done-review').getAttribute('href'), '/receiving/review?receipt=12');
    assert.equal(env.sandbox.location.search, '');
    assert.equal(env.localStorage.getItem('rc.receipt.v1'), null, 'снимок закрытой приёмки остался');
});

await test('скан, пока «Завершить» в пути, не пишется: сигнал ошибки и подсказка', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 120 });
    const env = await boot({ server, search: '?r=120' });
    scan(env, EAN_A);
    await settle(env);
    env.net.hold = (call) => CLOSE_RE.test(call.url);
    env.$('rc-finish').click();
    env.$('rc-sheet-ok').click();
    await settle(env);
    assert.equal(env.held.length, 1, 'запрос close не в пути');
    const sent = env.scanCalls().length;
    const mark = env.tones.length;
    scan(env, EAN_B);
    await settle(env);
    assert.deepEqual(env.queue(), [], 'скан в закрываемую приёмку лёг в очередь');
    assert.equal(env.scanCalls().length, sent);
    assert.deepEqual(tonesSince(env, mark), [220]);
    assert.match(env.$('rc-toast').textContent, /Приёмка завершается/);
    assert.equal(env.$('rc-sheet-ok').disabled, true, 'кнопка «Завершить» не заблокирована на время запроса');
    env.net.hold = null;
    env.release();
    await settle(env);
    assert.equal(env.$('rc-done').hidden, false);
    assert.equal(env.$('rc-sheet-ok').disabled, false);
});

await test('скан после завершения не пишется: сигнал ошибки и подсказка', async () => {
    const env = main;
    const sent = env.scanCalls().length;
    const mark = env.tones.length;
    scan(env, EAN_A);
    await settle(env);
    assert.equal(env.scanCalls().length, sent);
    assert.deepEqual(env.queue(), []);
    assert.deepEqual(tonesSince(env, mark), [220]);
    assert.match(env.$('rc-toast').textContent, /Новая приёмка/);
});

await test('все запросы страницы попадают в маршруты раздела 7 спецификации', async () => {
    const env = main;
    for (const call of env.net.calls) {
        const pathname = call.url.split('?')[0];
        const ok = SPEC_ROUTES.some(([method, re]) => method === call.method && re.test(pathname));
        assert.ok(ok, 'запрос вне контракта: ' + call.method + ' ' + call.url);
    }
});

await test('в main-сценарии не было предупреждений скрипта', async () => {
    assert.deepEqual(main.warnings, []);
});

// ---------------------------------------------------------------- отдельные сценарии

await test('?r=<id> продолжает приёмку: dm_keys с сервера дают «Уже посчитана» сразу', async () => {
    const server = new FakeServer();
    const r = server.addReceipt({ id: 30 });
    server.record(r, DM_1, 'earlier-scan-0001', 'scanner');
    const env = await boot({ server, search: '?r=30' });
    assert.equal(env.net.calls[0].url, '/api/receiving/30');
    assert.equal(env.$('rc-scan').hidden, false);
    assert.equal(units(env), 1);
    assert.match(env.$('rc-recent').textContent, /Принят/);
    const mark = env.tones.length;
    scan(env, DM_1);
    assert.deepEqual(tonesSince(env, mark), [1320, 1320]);
    assert.ok(env.localStorage.getItem('rc.receipt.v1'), 'нет снимка приёмки');
});

await test('?r= закрытой приёмки — стартовый экран и сообщение', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 31, status: 'closed' });
    const env = await boot({ server, search: '?r=31' });
    assert.equal(env.$('rc-start').hidden, false);
    assert.match(env.$('rc-toast').textContent, /уже закрыта/);
    assert.equal(env.sandbox.location.search, '');
});

await test('очередь из прошлого запуска отправляется при загрузке страницы', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 40 });
    const stored = [{
        client_id: 'stored-0000-0001', receipt_id: 40, code: EAN_A, source: 'scanner',
        client_time: '2026-10-03T07:00:00.000Z', at: 1, local: 'accepted', kind: 'ean', gtin: GTIN_A, key: GTIN_A,
        message: 'Принято', tries: 1,
    }];
    const env = await boot({ server, search: '?r=40', storage: { 'rc.queue.v1': JSON.stringify(stored) } });
    await settle(env);
    const call = env.scanCalls()[0];
    assert.ok(call, 'очередь не отправлена');
    assert.equal(call.body.client_id, 'stored-0000-0001');
    assert.deepEqual(env.queue(), []);
    assert.equal(units(env), 1);
});

await test('без связи после перезагрузки: экран открывается по снимку, сканы копятся', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 50 });
    const first = await boot({ server, search: '?r=50' });
    scan(first, DM_1);
    await settle(first);
    const storage = first.localStorage.dump();
    const env = makeEnv({ server, search: '?r=50', storage, offline: true });
    await env.api.ready;
    await settle(env);
    assert.equal(env.$('rc-scan').hidden, false, 'экран сканирования не открылся без связи');
    assert.equal(env.$('rc-offline').hidden, false);
    assert.equal(units(env), 1);
    const mark = env.tones.length;
    scan(env, DM_1);
    assert.deepEqual(tonesSince(env, mark), [1320, 1320], 'ключи DataMatrix не восстановлены из снимка');
    scan(env, DM_2);
    await settle(env);
    assert.equal(units(env), 2);
    assert.equal(env.queue().length, 2);
    env.net.mode = 'online';
    for (const l of env.windowListeners.filter((x) => x.type === 'online')) l.fn({});
    await settle(env);
    assert.deepEqual(env.queue(), []);
    assert.equal(env.$('rc-offline').hidden, true, 'после связи данные не перечитаны');
    assert.equal(units(env), 2);
});

await test('409 на скан (приёмку закрыли на другом телефоне): сканы переносятся в новую приёмку', async () => {
    // Ревью 2026-10-03: второй телефон был без связи, первый нажал «Завершить» —
    // неотправленные сканы второго не выбрасываются, а уходят в новую приёмку.
    const server = new FakeServer();
    const r = server.addReceipt({ id: 60 });
    server.nextReceipt = 61;
    const env = await boot({ server, search: '?r=60' });
    env.net.mode = 'offline';
    scan(env, EAN_A);
    scan(env, DM_1);
    await settle(env);
    assert.equal(env.queue().length, 2);
    r.status = 'closed';
    env.net.mode = 'online';
    await advance(env, 30000);
    assert.deepEqual(env.queue(), [], 'сканы не дошли');
    const created = env.net.calls.filter((c) => c.method === 'POST' && c.url === '/api/receiving');
    assert.equal(created.length, 1);
    assert.match(created[0].body.note, /после закрытия приёмки №60/);
    const moved = env.scanCalls().filter((c) => c.url === '/api/receiving/61/scan');
    assert.equal(moved.length, 2, 'сканы не перенесены в новую приёмку');
    assert.equal(server.receipts.get(61).scans.filter((s) => s.accepted).length, 2);
    assert.match(env.$('rc-toast').textContent, /Приёмку №60 уже закрыли — неотправленные сканы из телефона \(2\) перенесены в новую приёмку №61/);
    assert.equal(env.$('rc-title').textContent, 'Приёмка №61');
    assert.equal(env.sandbox.location.search, '?r=61');
});

await test('409 receipt_deleted (приёмку удалили в разборе): сканы переносятся в новую приёмку', async () => {
    // Ревью 2026-10-04: удаление приёмки не должно выбрасывать неотправленные сканы телефона.
    const server = new FakeServer();
    server.addReceipt({ id: 63 });
    server.nextReceipt = 64;
    const env = await boot({ server, search: '?r=63' });
    env.net.mode = 'offline';
    scan(env, EAN_A);
    scan(env, DM_1);
    await settle(env);
    assert.equal(env.queue().length, 2);
    server.receipts.delete(63);
    server.deleted.add(63);
    env.net.mode = 'online';
    await advance(env, 30000);
    assert.deepEqual(env.queue(), [], 'сканы не дошли');
    const created = env.net.calls.filter((c) => c.method === 'POST' && c.url === '/api/receiving');
    assert.equal(created.length, 1);
    assert.match(created[0].body.note, /после удаления приёмки №63/);
    assert.equal(server.receipts.get(64).scans.filter((s) => s.accepted).length, 2);
    assert.match(env.$('rc-toast').textContent, /Приёмку №63 удалили — неотправленные сканы из телефона \(2\) перенесены в новую приёмку №64/);
});

await test('отмена скана в закрытой приёмке (409) не выбрасывает следующие сканы: они уходят в новую', async () => {
    const server = new FakeServer();
    const r = server.addReceipt({ id: 66 });
    server.nextReceipt = 67;
    const saved = server.record(r, EAN_A, 'saved-scan-0001', 'scanner');
    r.status = 'closed';
    const base = { source: 'scanner', client_time: '2026-10-03T07:00:00.000Z', at: 1, local: 'accepted',
                   kind: 'ean', message: 'Принято' };
    const queue = [
        Object.assign({}, base, { client_id: 'undo-item-0001', receipt_id: 66, code: EAN_A, gtin: GTIN_A, key: GTIN_A,
                                  tries: 1, undo: true, scan_id: saved.scan.id }),
        Object.assign({}, base, { client_id: 'next-scan-0002', receipt_id: 66, code: EAN_B, gtin: GTIN_B, key: GTIN_B,
                                  tries: 0 }),
    ];
    const env = await boot({ server, storage: { 'rc.queue.v1': JSON.stringify(queue) } });
    await advance(env, 30000);
    assert.deepEqual(env.queue(), [], 'очередь не разобрана');
    assert.equal(server.receipts.get(67).scans.filter((s) => s.accepted).length, 1, 'скан после отмены потерян');
    assert.match(env.$('rc-toast').textContent, /Приёмку №66 уже закрыли — неотправленные сканы из телефона \(1\) перенесены в новую приёмку №67/);
});

await test('404 на скан (приёмки нет): сканы этой приёмки выброшены с сообщением', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 62 });
    const env = await boot({ server, search: '?r=62' });
    server.receipts.delete(62);
    scan(env, EAN_A);
    await settle(env);
    assert.deepEqual(env.queue(), []);
    assert.match(env.$('rc-toast').textContent, /Приёмка №62 не найдена — не записано сканов из телефона: 1/);
});

await test('другая вкладка: её сканы в localStorage не затираются записью этой вкладки', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 70 });
    const env = await boot({ server, search: '?r=70' });
    env.net.mode = 'offline';
    const foreign = {
        client_id: 'other-tab-0000-01', receipt_id: 70, code: EAN_B, source: 'scanner',
        client_time: '2026-10-03T07:00:00.000Z', at: 1, local: 'accepted', kind: 'ean', gtin: GTIN_B, key: GTIN_B,
        message: 'Принято', tries: 0,
    };
    env.localStorage.setItem('rc.queue.v1', JSON.stringify([foreign]));
    scan(env, EAN_A);
    await settle(env);
    const ids = env.queue().map((i) => i.client_id);
    assert.ok(ids.includes('other-tab-0000-01'), 'скан другой вкладки стёрт');
    assert.equal(ids.length, 2);
    env.net.mode = 'online';
    await advance(env, 30000);
    assert.deepEqual(env.queue(), []);
    assert.equal(units(env), 2);
});

await test('нет crypto.randomUUID (http): запасной client_id проходит проверку маршрута', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 80 });
    const env = await boot({ server, search: '?r=80', noUuid: true });
    scan(env, EAN_A);
    scan(env, EAN_B);
    await settle(env);
    const ids = env.scanCalls().map((c) => c.body.client_id);
    for (const id of ids) assert.match(id, CLIENT_ID_RE);
    assert.equal(units(env), 2);
});

await test('codes.js не загрузился: скан всё равно уходит, сигнал — по ответу сервера', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 90 });
    const env = await boot({ server, search: '?r=90', noCodes: true });
    const mark = env.tones.length;
    scan(env, EAN_A);
    assert.deepEqual(tonesSince(env, mark), [], 'без разбора в браузере сигнал раньше сервера');
    await settle(env);
    assert.deepEqual(tonesSince(env, mark), [1760]);
    assert.equal(units(env), 1);
    assert.equal(env.$('rc-status').textContent, 'Принято');
});

await test('ввод вручную: окно с полем, Enter в поле — скан с source=manual', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 95 });
    const env = await boot({ server, search: '?r=95' });
    env.$('rc-manual').click();
    assert.equal(env.$('rc-sheet-wrap').hidden, false);
    assert.equal(env.$('rc-sheet-input').hidden, false);
    env.$('rc-sheet-input').value = ' ' + EAN_A + ' ';
    env.$('rc-sheet-input').dispatch('keydown', keyEvent(env, { key: 'Enter', code: 'Enter', target: env.$('rc-sheet-input') }));
    await settle(env);
    assert.equal(env.$('rc-sheet-wrap').hidden, true);
    const call = env.scanCalls().at(-1);
    assert.equal(call.body.code, EAN_A);
    assert.equal(call.body.source, 'manual');
    assert.equal(units(env), 1);
});

await test('камера: BarcodeDetector, тот же код в кадре 2,5 с не считается, фонарик, закрытие гасит поток', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 100 });
    let frame = [];
    const stopped = [];
    class Detector {
        static getSupportedFormats() { return Promise.resolve(['ean_13', 'data_matrix', 'qr_code']); }
        constructor(opts) { Detector.formats = opts.formats; }
        detect() { return Promise.resolve(frame.map((rawValue) => ({ rawValue }))); }
    }
    const torch = [];
    const track = {
        stop: () => stopped.push('video'),
        getCapabilities: () => ({ torch: true }),
        applyConstraints: (c) => { torch.push(c.advanced[0].torch); return Promise.resolve(); },
    };
    const stream = { getTracks: () => [track], getVideoTracks: () => [track] };
    const media = { getUserMedia: (c) => { media.constraints = c; return Promise.resolve(stream); } };
    const env = await boot({ server, search: '?r=100', mediaDevices: media, barcodeDetector: Detector });
    env.$('rc-camera').click();
    await settle(env);
    assert.equal(env.$('rc-cam-wrap').hidden, false);
    assert.deepEqual(plain(media.constraints),
        { video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
    assert.deepEqual(plain(Detector.formats), ['data_matrix', 'ean_13']);
    assert.equal(env.$('rc-torch').hidden, false);
    frame = [EAN_A];
    await advance(env, 200);
    assert.equal(env.scanCalls().length, 0, 'штрихкод с камеры посчитан, не дождавшись 0,8 с');
    await advance(env, 800);
    assert.equal(env.scanCalls().length, 1);
    assert.equal(env.scanCalls()[0].body.source, 'camera');
    for (let i = 0; i < 20; i++) await advance(env, 200);   // 4 с в кадре — окно скользит
    assert.equal(env.scanCalls().length, 1, 'код в кадре посчитан повторно');
    frame = [];
    await advance(env, 2600);
    frame = [EAN_A];
    await advance(env, 1000);
    assert.equal(env.scanCalls().length, 2, 'код, ушедший из кадра на 2,5 с, не считается снова');
    await settle(env);
    assert.equal(env.$('rc-cam-units').textContent, '2 шт.');
    env.$('rc-torch').click();
    await settle(env);
    assert.deepEqual(torch, [true]);
    assert.equal(env.$('rc-torch').getAttribute('aria-pressed'), 'true');
    env.$('rc-cam-close').click();
    assert.equal(env.$('rc-cam-wrap').hidden, true);
    assert.deepEqual(stopped, ['video']);
    const sent = env.scanCalls().length;
    await advance(env, 1000);
    assert.equal(env.scanCalls().length, sent, 'камера читает после закрытия');
});

await test('камера недоступна: понятная ошибка, окно камеры не висит', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 101 });
    const denied = { getUserMedia: () => Promise.reject(Object.assign(new Error('denied'), { name: 'NotAllowedError' })) };
    class Detector {
        static getSupportedFormats() { return Promise.resolve(['data_matrix']); }
        detect() { return Promise.resolve([]); }
    }
    const env = await boot({ server, search: '?r=101', mediaDevices: denied, barcodeDetector: Detector });
    env.$('rc-camera').click();
    await settle(env);
    assert.equal(env.$('rc-cam-wrap').hidden, true);
    assert.match(env.$('rc-toast').textContent, /Нет доступа к камере/);
    const env2 = await boot({ server, search: '?r=101' });
    env2.$('rc-camera').click();
    await settle(env2);
    assert.match(env2.$('rc-toast').textContent, /Камера недоступна/);
});

await test('фото накладной: multipart photo -> POST /invoice, список фото, удаление через подтверждение', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 110 });
    const env = await boot({ server, search: '?r=110' });
    const input = env.$('rc-photo-input');
    const file = { name: 'IMG_0001.HEIC', size: 3000000, type: 'image/heic' };
    input.files = [file];
    input.dispatch('change', {});
    await settle(env);
    const call = env.net.calls.find((c) => c.method === 'POST' && INVOICE_RE.test(c.url));
    assert.ok(call, 'фото не отправлено');
    assert.equal(call.url, '/api/receiving/110/invoice');
    assert.equal(call.headers['Content-Type'], undefined, 'multipart не должен идти с JSON-заголовком');
    assert.equal(call.body.entries[0][0], 'photo');
    assert.equal(call.body.entries[0][1], file, 'без canvas фото должно уйти как есть');
    assert.equal(env.$('rc-invoices-box').hidden, false);
    const links = env.$('rc-invoices').findAll('rc-invoice');
    assert.equal(links.length, 1);
    assert.match(links[0].children[0].getAttribute('href'), /^\/api\/receiving\/invoice\/r110_/);
    assert.match(env.$('rc-toast').textContent, /Фото накладной сохранено/);
    links[0].children[2].click();
    assert.equal(env.$('rc-sheet-wrap').hidden, false);
    env.$('rc-sheet-ok').click();
    await settle(env);
    const del = env.net.calls.find((c) => c.method === 'DELETE' && INVOICE_DELETE_RE.test(c.url));
    assert.ok(del, 'фото не удалено');
    assert.equal(env.$('rc-invoices-box').hidden, true);
});

await test('новая приёмка без связи — сообщение, экран не меняется', async () => {
    const env = makeEnv({ offline: true });
    await env.api.ready;
    await settle(env);
    assert.match(env.$('rc-start-error').textContent, /Нет связи/);
    env.$('rc-new').click();
    await settle(env);
    assert.equal(env.$('rc-start').hidden, false);
    assert.match(env.$('rc-toast').textContent, /Нет связи — новую приёмку открыть не получилось/);
});

// ---------------------------------------------------------------- ревью 2026-10-03

await test('опоздавший Enter после кода сканера: код считается, Enter не нажимает кнопку в фокусе', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 120 });
    const env = await boot({ server, search: '?r=120' });
    const sent = env.scanCalls().length;
    for (const ch of EAN_A) press(env, keyFor(ch), 5);
    const enter = press(env, { code: 'Enter', key: 'Enter' }, 150);
    await settle(env);
    assert.equal(env.scanCalls().length, sent + 1, 'код с опоздавшим Enter потерян');
    assert.equal(enter.defaultPrevented, true, 'Enter сканера нажал бы кнопку в фокусе');
});

await test('сканер без Enter/Tab: код уходит после паузы 300 мс, поздний Enter проглатывается', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 121 });
    const env = await boot({ server, search: '?r=121' });
    const sent = env.scanCalls().length;
    for (const ch of EAN_A) press(env, keyFor(ch), 5);
    await advance(env, 299);
    assert.equal(env.scanCalls().length, sent, 'код ушёл раньше паузы');
    await advance(env, 2);
    assert.equal(env.scanCalls().length, sent + 1, 'код без суффикса не ушёл по паузе');
    const late = press(env, { code: 'Enter', key: 'Enter' }, 100);
    assert.equal(late.defaultPrevented, true);
    await settle(env);
    assert.equal(env.scanCalls().length, sent + 1, 'поздний Enter не должен давать второй скан');
});

await test('поздний ответ про прежнюю приёмку не переключает экран на неё', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 7 });
    server.nextReceipt = 30;
    // Перезагрузка ?r=7 на слабом Wi-Fi: GET 7 висит, приёмщик видит старт и жмёт «Новая приёмка».
    const env = makeEnv({ server, search: '?r=7',
        hold: (call) => call.method === 'GET' && call.url === '/api/receiving/7' });
    await settle(env);                                   // GET 7 «в пути»
    env.net.hold = null;
    assert.equal(env.net.calls.filter((c) => c.url === '/api/receiving/7').length, 1);
    env.$('rc-new').click();
    await settle(env);
    assert.equal(env.$('rc-title').textContent, 'Приёмка №30');
    env.release();                                       // пришёл ответ про №7
    await settle(env);
    assert.equal(env.$('rc-title').textContent, 'Приёмка №30', 'экран ушёл на прежнюю приёмку');
    assert.equal(env.sandbox.location.search, '?r=30');
    for (const ch of EAN_A) press(env, keyFor(ch), 5);
    press(env, { code: 'Enter', key: 'Enter' }, 5);
    await settle(env);
    assert.equal(env.scanCalls().at(-1).url, '/api/receiving/30/scan');
});

await test('«Завершить» не идёт, пока отмена скана ещё в пути', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 122 });
    const env = await boot({ server, search: '?r=122' });
    scan(env, EAN_A);
    await settle(env);
    env.net.hold = (call) => call.method === 'DELETE';
    env.$('rc-undo').click();
    await settle(env);
    env.net.hold = null;
    env.$('rc-finish').click();
    await settle(env);
    assert.equal(env.$('rc-sheet-wrap').hidden, true, 'окно «Завершить?» открылось во время отмены');
    assert.match(env.$('rc-toast').textContent, /Идёт отмена скана/);
    env.release();
    await settle(env);
    assert.ok(!env.net.calls.some((c) => CLOSE_RE.test(c.url)), 'приёмка закрылась во время отмены');
});

await test('камера: закрыли и открыли заново, пока ждали разрешения, — первый поток гасится', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 123 });
    class Detector {
        static getSupportedFormats() { return Promise.resolve(['data_matrix', 'ean_13']); }
        constructor() {}
        detect() { return Promise.resolve([]); }
    }
    const stopped = [];
    const pending = [];
    const makeStream = (name) => {
        const track = { stop: () => stopped.push(name), getCapabilities: () => ({}) };
        return { getTracks: () => [track], getVideoTracks: () => [track] };
    };
    const media = { getUserMedia: () => new Promise((resolve) => pending.push(resolve)) };
    const env = await boot({ server, search: '?r=123', mediaDevices: media, barcodeDetector: Detector });
    env.$('rc-camera').click();
    await settle(env);
    env.$('rc-cam-close').click();
    env.$('rc-camera').click();
    await settle(env);
    assert.equal(pending.length, 2);
    pending[0](makeStream('first'));
    await settle(env);
    assert.deepEqual(stopped, ['first'], 'первый поток камеры остался гореть');
    pending[1](makeStream('second'));
    await settle(env);
    env.$('rc-cam-close').click();
    assert.deepEqual(stopped, ['first', 'second']);
});

// Камера-заглушка для тестов «только телефон»: кадр задаёт тест, детектор отдаёт его.
function cameraRig() {
    const rig = { frame: [], stopped: [], wake: [] };
    class Detector {
        static getSupportedFormats() { return Promise.resolve(['ean_13', 'data_matrix']); }
        detect() { return Promise.resolve(rig.frame.map((rawValue) => ({ rawValue }))); }
    }
    const track = { stop: () => rig.stopped.push('video'), getCapabilities: () => ({}) };
    const stream = { getTracks: () => [track], getVideoTracks: () => [track] };
    rig.media = { getUserMedia: () => Promise.resolve(stream) };
    rig.Detector = Detector;
    rig.wakeLock = {
        request: (type) => {
            const sentinel = { type, released: false, release: () => { sentinel.released = true; return Promise.resolve(); } };
            rig.wake.push(sentinel);
            return Promise.resolve(sentinel);
        },
    };
    return rig;
}

await test('камера: DataMatrix и штрихкод той же бутылки в одном кадре — одна штука', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 130 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=130', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    rig.frame = [EAN_A, DM_1];            // EAN раньше в ответе детектора — всё равно не считается
    for (let i = 0; i < 10; i++) await advance(env, 200);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [DM_1]);
    // Следующая бутылка того же товара: новый код ЧЗ, штрихкод тот же — снова одна штука.
    rig.frame = [DM_2, EAN_A];
    for (let i = 0; i < 10; i++) await advance(env, 200);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [DM_1, DM_2]);
    await settle(env);
    assert.equal(units(env), 2);
});

await test('камера: штрихкод, за которым через 0,4 с прочитан код ЧЗ того же товара, не считается', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 131 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=131', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    rig.frame = [EAN_A];
    await advance(env, 400);
    rig.frame = [DM_1];
    for (let i = 0; i < 10; i++) await advance(env, 200);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [DM_1]);
    // Штрихкод другого товара (без кода ЧЗ в кадре) считается через 0,8 с.
    rig.frame = [EAN_B];
    await advance(env, 1000);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [DM_1, EAN_B]);
    // У товара A в приёмке уже есть код ЧЗ: его штрихкод не считается и через 2,5 с —
    // маркированный товар считается только по кодам ЧЗ, на экране камеры подсказка.
    rig.frame = [];
    await advance(env, 2600);
    rig.frame = [EAN_A];
    await advance(env, 1000);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [DM_1, EAN_B]);
    assert.match(env.$('rc-cam-status').textContent, /Штрихкод не считается: у товара есть код Честного знака/);
});

await test('камера: штрихкод без сигнала не считается, если камеру закрыли раньше 0,8 с', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 132 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=132', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    rig.frame = [EAN_A];
    await advance(env, 400);
    env.$('rc-cam-close').click();
    await advance(env, 2000);
    assert.equal(env.scanCalls().length, 0);
    assert.equal(env.api.cam.eans.size, 0);
});

await test('камера: «Отменить последний» в окне камеры отменяет скан, камера остаётся открытой', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 133 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=133', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    rig.frame = [DM_1];
    await advance(env, 200);
    await settle(env);
    rig.frame = [];
    assert.equal(units(env), 1);
    env.$('rc-cam-undo').click();
    await settle(env);
    await advance(env, 200);
    await settle(env);
    assert.equal(units(env), 0);
    assert.equal(env.$('rc-cam-wrap').hidden, false, 'отмена закрыла камеру');
    assert.equal(env.$('rc-cam-units').textContent, '0 шт.');
});

await test('камера: экран не гаснет, пока она открыта (Wake Lock), закрытие отпускает', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 134 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=134', mediaDevices: rig.media, barcodeDetector: rig.Detector,
        wakeLock: rig.wakeLock });
    env.$('rc-camera').click();
    await settle(env);
    assert.equal(rig.wake.length, 1);
    assert.equal(rig.wake[0].type, 'screen');
    assert.equal(rig.wake[0].released, false);
    assert.ok(env.sandbox.document.documentElement.classList.contains('rc-cam-on'));
    env.$('rc-cam-close').click();
    await settle(env);
    assert.equal(rig.wake[0].released, true);
    assert.ok(!env.sandbox.document.documentElement.classList.contains('rc-cam-on'));
    // Без Wake Lock в браузере камера работает как раньше.
    const env2 = await boot({ server, search: '?r=134', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env2.$('rc-camera').click();
    await settle(env2);
    assert.equal(env2.$('rc-cam-wrap').hidden, false);
});

await test('камера: полифил не загрузился (ни своя копия, ни CDN) — ошибка про интернет, без «сканера»', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 135 });
    class EanOnly {
        static getSupportedFormats() { return Promise.resolve(['qr_code']); }
        detect() { return Promise.resolve([]); }
    }
    const rig = cameraRig();
    // В песочнице vm import() не работает — как недоступные своя копия и CDN.
    const env = await boot({ server, search: '?r=135', mediaDevices: rig.media, barcodeDetector: EanOnly });
    env.$('rc-camera').click();
    await settle(env);
    assert.equal(env.$('rc-cam-wrap').hidden, true);
    assert.match(env.$('rc-toast').textContent, /Не загрузился модуль распознавания кодов — проверьте интернет/);
    assert.ok(!/сканер/.test(env.$('rc-toast').textContent));
    // Браузер без WebAssembly полифил не потянет — тогда совет обновить браузер.
    const old = await boot({ server, search: '?r=135', mediaDevices: rig.media, barcodeDetector: EanOnly,
        noWebAssembly: true });
    old.$('rc-camera').click();
    await settle(old);
    assert.match(old.$('rc-toast').textContent, /обновите Safari или Chrome либо введите код вручную/);
});

await test('камера: штрихкод посчитан, а код ЧЗ той же бутылки прочитан через 1,6 с — штрихкод отозван', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 136 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=136', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    rig.frame = [EAN_A];                     // крупный штрихкод читается издалека
    await advance(env, 1600);
    await settle(env);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [EAN_A]);
    assert.equal(units(env), 1);
    rig.frame = [EAN_A, DM_1];               // поднесли ближе — прочитался DataMatrix
    await advance(env, 200);
    await settle(env);
    await advance(env, 200);
    await settle(env);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [EAN_A, DM_1]);
    const deletes = env.net.calls.filter((c) => c.method === 'DELETE' && SCAN_DELETE_RE.test(c.url));
    assert.equal(deletes.length, 1, 'штрихкод не удалён на сервере');
    assert.equal(units(env), 1, 'одна бутылка посчитана дважды');
    assert.equal(env.$('rc-cam-units').textContent, '1 шт.');
});

await test('камера: штрихкод отозван, пока нет связи — на сервере остаётся только код ЧЗ', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 137 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=137', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    env.net.mode = 'offline';
    rig.frame = [EAN_A];
    await advance(env, 1000);                // штрихкод посчитан в телефоне, отправка не дошла
    await settle(env);
    assert.equal(units(env), 1);
    rig.frame = [DM_1];
    await advance(env, 200);
    await settle(env);
    assert.equal(units(env), 1, 'штрихкод не отозван');
    assert.deepEqual(env.queue().filter((i) => !i.undo).map((i) => i.code), [DM_1]);
    env.$('rc-cam-close').click();
    env.net.mode = 'online';
    await advance(env, 31000);
    await settle(env);
    assert.equal(env.queue().length, 0, 'очередь не опустела');
    assert.equal(units(env), 1);
    assert.equal(server.counts(server.receipts.get(137)).units, 1, 'на сервере не одна штука');
});

await test('камера: плёнка упаковки (штрихкод другого GTIN) рядом с кодом ЧЗ банки — не считается', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 138 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=138', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    rig.frame = [EAN_B, DM_1];               // штрихкод упаковки раньше в ответе детектора
    for (let i = 0; i < 10; i++) await advance(env, 200);
    rig.frame = [EAN_B, DM_2];               // следующая банка, плёнка всё ещё в кадре
    for (let i = 0; i < 10; i++) await advance(env, 200);
    await settle(env);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [DM_1, DM_2]);
    assert.equal(units(env), 2);
    // Немаркированный товар отдельно (кода ЧЗ в кадре нет 0,8 с) — считается.
    rig.frame = [];
    await advance(env, 2600);
    rig.frame = [EAN_B];
    await advance(env, 1000);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [DM_1, DM_2, EAN_B]);
});

await test('камера: штрихкод упаковки посчитан один, а потом попал в кадр с кодом ЧЗ банки — отозван', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 140 });
    const rig = cameraRig();
    const env = await boot({ server, search: '?r=140', mediaDevices: rig.media, barcodeDetector: rig.Detector });
    env.$('rc-camera').click();
    await settle(env);
    rig.frame = [EAN_B];                     // плёнка упаковки видна одна больше 0,8 с
    await advance(env, 1200);
    await settle(env);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [EAN_B]);
    rig.frame = [EAN_B, DM_1];               // а это банка под плёнкой
    await advance(env, 200);
    await settle(env);
    await advance(env, 200);
    await settle(env);
    assert.deepEqual(env.scanCalls().map((c) => c.body.code), [EAN_B, DM_1]);
    assert.equal(units(env), 1);
});

await test('камера: разбор кадра всё время с ошибкой (модуль распознавания сломан) — подсказка на экране камеры', async () => {
    const server = new FakeServer();
    server.addReceipt({ id: 139 });
    const rig = cameraRig();
    class Broken {
        static getSupportedFormats() { return Promise.resolve(['data_matrix', 'ean_13']); }
        detect() { return Promise.reject(new Error('Aborted(wasm)')); }
    }
    const env = await boot({ server, search: '?r=139', mediaDevices: rig.media, barcodeDetector: Broken });
    env.$('rc-camera').click();
    await settle(env);
    for (let i = 0; i < 16; i++) await advance(env, 200);
    assert.match(env.$('rc-cam-status').textContent, /Камера не читает коды — закройте её и откройте снова/);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);

/**
 * Общий выбор бара и периода в браузере (static/js/shared/period/scope.js).
 *
 *     node tests/test_scope_store.mjs
 *
 * Решения владельца 2026-11-01: выбор один на весь сайт; период помнится час, у каждого
 * пользователя свой (Р1); бар — пока не сменишь. Хранилище — cookie (сервер рисует полосу с
 * выбором, core/scope.py), бар дублируется в localStorage для раздела «Гости».
 */

import assert from 'node:assert/strict';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);

// ---------------------------------------------------------------- браузер-заглушка
const jar = new Map();
const writes = [];
const listeners = {};
const storage = new Map();
globalThis.window = globalThis;
globalThis.document = {
    visibilityState: 'visible',
    get cookie() { return Array.from(jar, ([k, v]) => k + '=' + v).join('; '); },
    set cookie(line) {
        writes.push(line);
        const [pair, ...attrs] = line.split(';').map((s) => s.trim());
        const eq = pair.indexOf('=');
        const name = pair.slice(0, eq), value = pair.slice(eq + 1);
        const maxAge = attrs.find((a) => a.startsWith('Max-Age='));
        if (maxAge && Number(maxAge.slice(8)) <= 0) jar.delete(name); else jar.set(name, value);
    },
    addEventListener(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); },
};
globalThis.addEventListener = (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); };
globalThis.localStorage = {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
};
let search = '';
globalThis.location = { get search() { return search; }, pathname: '/dashboard', hash: '', protocol: 'https:' };
globalThis.history = { state: null, replaceState(_s, _t, url) { search = url.includes('?') ? url.slice(url.indexOf('?')) : ''; } };

const S = require(path.join(ROOT, 'static/js/shared/period/scope.js'));
S.configure({ user: 7 });

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
function reset() { jar.clear(); writes.length = 0; storage.clear(); search = ''; }

test('период: пишется с номером пользователя, срок — час, Secure на https', () => {
    reset();
    S.setPeriod({ start: '2026-10-01', end: '2026-10-31' });
    assert.equal(writes.at(-1), 'kultura_period=7%3A2026-10-01_2026-10-31; Max-Age=3600; Path=/; SameSite=Lax; Secure');
    assert.deepEqual(S.getPeriod(), { start: '2026-10-01', end: '2026-10-31' });
});

test('чужой, перевёрнутый или мусорный период — нет выбора', () => {
    reset();
    jar.set('kultura_period', encodeURIComponent('8:2026-10-01_2026-10-31'));
    assert.equal(S.getPeriod(), null, 'выбор другого пользователя на общем компьютере');
    jar.set('kultura_period', encodeURIComponent('7:2026-10-31_2026-10-01'));
    assert.equal(S.getPeriod(), null);
    jar.set('kultura_period', 'мусор');
    assert.equal(S.getPeriod(), null);
});

test('час — с последнего открытия страницы: touchPeriod продлевает срок', () => {
    reset();
    S.setPeriod({ start: '2026-10-01', end: '2026-10-31' });
    writes.length = 0;
    assert.deepEqual(S.touchPeriod(), { start: '2026-10-01', end: '2026-10-31' });
    assert.match(writes.at(-1), /Max-Age=3600/);
});

test('«Сбросить» удаляет выбранный период', () => {
    reset();
    S.setPeriod({ start: '2026-10-01', end: '2026-10-31' });
    S.resetPeriod();
    assert.equal(S.getPeriod(), null);
    assert.match(writes.at(-1), /Max-Age=0/);
});

test('бар: cookie на год, копия для раздела «Гости», ?bar= в адресе; вся сеть — явным all', () => {
    reset();
    assert.equal(S.setBar('ligovskiy'), 'ligovskiy');
    assert.equal(writes.at(-1), 'kultura_bar=7%3Aligovskiy; Max-Age=31536000; Path=/; SameSite=Lax; Secure');
    assert.equal(localStorage.getItem('kultura.bar'), 'ligovskiy');
    assert.equal(search, '?bar=ligovskiy');
    assert.equal(S.setBar(''), '');
    assert.match(writes.at(-1), /^kultura_bar=7%3Aall;/);
    assert.equal(search, '', 'вся сеть — без параметра');
    assert.equal(S.setBar('bar9'), '', 'мусор — вся сеть');
});

test('порядок чтения бара: ссылка -> cookie -> копия -> старые ключи страниц', () => {
    reset();
    localStorage.setItem('gh.bar', 'varshavskaya');
    assert.equal(S.getBar(), 'varshavskaya', 'старый ключ раздела «Гости»');
    localStorage.setItem('dashboard_selected_venue', '"kremenchugskaya"');
    assert.equal(S.getBar(), 'kremenchugskaya', 'старый ключ дашборда');
    localStorage.setItem('kultura.bar', 'bolshoy');
    assert.equal(S.getBar(), 'bolshoy');
    jar.set('kultura_bar', encodeURIComponent('7:ligovskiy'));
    assert.equal(S.getBar(), 'ligovskiy', 'cookie сильнее копии');
    jar.set('kultura_bar', encodeURIComponent('8:varshavskaya'));
    assert.equal(S.getBar(), 'bolshoy', 'чужой cookie не читается');
    search = '?bar=kremenchugskaya';
    assert.equal(S.getBar(), 'kremenchugskaya', 'ссылка сильнее всего');
});

test('выбор из другой вкладки подхватывается при возвращении к странице', () => {
    reset();
    const seen = [];
    const w = S.watch((snap) => seen.push(snap));
    jar.set('kultura_period', encodeURIComponent('7:2026-09-01_2026-09-30'));
    jar.set('kultura_bar', encodeURIComponent('7:bolshoy'));
    listeners.visibilitychange.forEach((fn) => fn());
    assert.deepEqual(seen, [{ bar: 'bolshoy', period: { start: '2026-09-01', end: '2026-09-30' } }]);
    listeners.focus.forEach((fn) => fn());
    assert.equal(seen.length, 1, 'без изменений — без повтора');
    // Свой выбор на этой странице — не «чужое изменение».
    S.setPeriod({ start: '2026-08-01', end: '2026-08-31' });
    w.sync();
    listeners.visibilitychange.forEach((fn) => fn());
    assert.equal(seen.length, 1);
});

test('без номера пользователя cookie не пишутся (страница без входа)', () => {
    reset();
    delete require.cache[require.resolve(path.join(ROOT, 'static/js/shared/period/scope.js'))];
    const fresh = require(path.join(ROOT, 'static/js/shared/period/scope.js'));
    fresh.setPeriod({ start: '2026-10-01', end: '2026-10-31' });
    assert.equal(writes.length, 0);
    assert.equal(fresh.getPeriod(), null);
});

console.log(`\n${passed} ok, ${failed} failed`);
if (failed) process.exit(1);

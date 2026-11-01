/**
 * Загрузка страницы по полосе «Бар и период» (static/js/shared/strip_runner.js): считать сразу,
 * без кнопок (ответ владельца Р5), серия изменений — один запрос после паузы, устаревший ответ
 * отбрасывается, «Считаю…» видно сразу.
 *
 *     node tests/test_strip_runner.mjs
 *
 * Скрипт исполняется в Node с подставными таймерами: время двигает сам тест.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = fs.readFileSync(path.join(ROOT, 'static/js/shared/strip_runner.js'), 'utf8');

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
        console.log(`      ${e && e.stack}`);
    }
}

// ---------------------------------------------------------------- стенд

function boot() {
    let now = 0;
    let nextId = 1;
    const timers = new Map();
    const sandbox = {
        console, Promise, AbortController,
        setTimeout(fn, ms) { const id = nextId++; timers.set(id, { at: now + ms, fn }); return id; },
        clearTimeout(id) { timers.delete(id); },
    };
    vm.createContext(sandbox);
    new vm.Script(SRC, { filename: 'strip_runner.js' }).runInContext(sandbox);
    const advance = (ms) => {
        now += ms;
        for (const [id, t] of [...timers]) {
            if (t.at <= now) { timers.delete(id); t.fn(); }
        }
    };
    return { R: sandbox.KStripRunner, advance, pending: () => timers.size };
}

const flush = () => new Promise((r) => setImmediate(r));

function deferred() {
    let resolve, reject;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}

// ---------------------------------------------------------------- тесты

await test('серия изменений — один запрос после паузы 350 мс', async () => {
    const { R, advance } = boot();
    let runs = 0;
    const r = R.create({ run: () => { runs++; return Promise.resolve('ok'); } });
    assert.equal(R.DEFAULT_DELAY_MS, 350);
    r.schedule();
    advance(200);
    r.schedule();
    advance(200);
    r.schedule();
    advance(349);
    assert.equal(runs, 0, 'до паузы запроса нет');
    advance(1);
    assert.equal(runs, 1, 'после паузы — ровно один');
});

await test('now() — сразу, без паузы (открытие страницы)', async () => {
    const { R } = boot();
    let runs = 0;
    const done = [];
    const r = R.create({ run: () => { runs++; return Promise.resolve(7); }, onDone: (v) => done.push(v) });
    await r.now();
    assert.equal(runs, 1);
    assert.deepEqual(done, [7]);
});

await test('устаревший ответ отбрасывается, рисуется только последний', async () => {
    const { R, advance } = boot();
    const calls = [];
    const done = [];
    const r = R.create({
        run: (signal) => { const d = deferred(); calls.push({ d, signal }); return d.promise; },
        onDone: (v) => done.push(v),
    });
    r.now();
    r.schedule();            // пользователь сменил период, пока считался первый
    advance(350);
    assert.equal(calls.length, 2);
    assert.equal(calls[0].signal.aborted, true, 'прежний запрос браузера отменён');
    calls[1].d.resolve('новый');
    calls[0].d.resolve('старый');
    await flush();
    assert.deepEqual(done, ['новый']);
});

await test('ошибка устаревшего запуска и отмена — не ошибка на экране', async () => {
    const { R, advance } = boot();
    const calls = [];
    const errors = [];
    const r = R.create({
        run: () => { const d = deferred(); calls.push(d); return d.promise; },
        onError: (e) => errors.push(e.message),
    });
    r.now();
    r.schedule();
    advance(350);
    const abort = new Error('aborted');
    abort.name = 'AbortError';
    calls[0].reject(new Error('старая ошибка'));
    calls[1].reject(abort);
    await flush();
    assert.deepEqual(errors, []);
    r.now();
    calls[2].reject(new Error('iiko не ответил'));
    await flush();
    assert.deepEqual(errors, ['iiko не ответил']);
});

await test('«Считаю…» видно сразу при изменении, finally — один раз в конце', async () => {
    const { R, advance } = boot();
    const log = [];
    const d = deferred();
    const r = R.create({
        run: () => d.promise,
        onStart: () => log.push('start'),
        onFinally: () => log.push('finally'),
    });
    r.schedule();
    assert.deepEqual(log, ['start'], 'подпись до паузы');
    assert.equal(r.busy(), true);
    advance(350);
    d.resolve(1);
    await flush();
    assert.deepEqual(log, ['start', 'start', 'finally']);
    assert.equal(r.busy(), false);
});

await test('cancel() — ни запроса, ни ответа', async () => {
    const { R, advance, pending } = boot();
    let runs = 0;
    const r = R.create({ run: () => { runs++; return Promise.resolve(1); } });
    r.schedule();
    r.cancel();
    advance(1000);
    assert.equal(runs, 0);
    assert.equal(pending(), 0);
});

await test('исключение в run — onError, страница не падает', async () => {
    const { R } = boot();
    const errors = [];
    const r = R.create({ run: () => { throw new Error('нет полосы'); }, onError: (e) => errors.push(e.message) });
    await r.now();
    assert.deepEqual(errors, ['нет полосы']);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);

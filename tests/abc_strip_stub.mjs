/**
 * Полоса «Бар и период» для Node-тестов страниц ABC (розлив, фасовка, кухня) — не тест,
 * а помощник: test_draft_runtime.mjs, test_packaging_runtime.mjs, test_kitchen_runtime.mjs.
 *
 * С 2026-11-01 своих меню бара и периода у страниц нет: бар и период — общая полоса сайта
 * (window.KStrip, static/js/shared/period/scope_strip.js). Здесь:
 *   - bootStrip(sandbox) — настоящее ядро периодов (period_core.js) с часами страницы на
 *     01.11.2026 и подменённая полоса с тем же интерфейсом (get, onChange, barInfo, config);
 *   - stripChecks(...) — одни и те же проверки связки для трёх страниц: запрос после паузы,
 *     бар — имя iiko, серия выборов — один запрос, устаревший ответ выброшен, память ответов,
 *     подпись «XYZ не считается» до ответа, понятная ошибка, когда iiko не успел.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PERIOD_CORE = fs.readFileSync(path.join(ROOT, 'static/js/shared/period/period_core.js'), 'utf8');

// Таблица баров сайта — как её отдаёт сервер полосе (core/scope.bars_client).
export const SITE_BARS = [
    { key: 'bolshoy', name: 'Большой пр. В.О', short: 'ВО', iiko_name: 'Большой пр. В.О', bar_id: 'bar1' },
    { key: 'ligovskiy', name: 'Лиговский', short: 'Лиг', iiko_name: 'Лиговский', bar_id: 'bar2' },
    { key: 'kremenchugskaya', name: 'Кременчугская', short: 'Крем', iiko_name: 'Кременчугская', bar_id: 'bar3' },
    { key: 'varshavskaya', name: 'Варшавская', short: 'Вар', iiko_name: 'Варшавская', bar_id: 'bar4' }
];

// Полоса: get / onChange / barInfo / setPeriod / config — как у scope_strip.js; choose() —
// выбор в полосе, как кликом: меняет бар или период и рассылает событие подписчикам.
// period — период полосы при открытии (по умолчанию последние 30 дней, как у ABC-страниц).
export function fakeStrip(K, period) {
    const listeners = [];
    const st = { bar: '', period: period || K.lastDays(30) };
    const setCalls = [];
    return {
        get: () => ({ bar: st.bar, period: st.period }),
        onChange: (fn) => { listeners.push(fn); },
        barInfo: (key) => SITE_BARS.find((b) => b.key === key) || null,
        config: { allLabel: 'Все бары', bars: SITE_BARS },
        listeners,
        setCalls,
        // Выбор периода из кода страницы (открыт сохранённый отчёт) — как выбор в элементе.
        setPeriod(p) { setCalls.push(p); this.choose({ period: p }); },
        choose(change) {
            const type = change.bar !== undefined ? 'bar' : 'period';
            if (change.bar !== undefined) st.bar = change.bar;
            if (change.period) st.period = change.period;
            listeners.forEach((fn) => fn({ type, bar: st.bar, period: st.period, cause: 'user' }));
        }
    };
}

// Ядро периодов и полоса — в песочницу страницы (до запуска abc_view.js и скрипта страницы).
// step — правило открытия страницы: 'last30' (ABC) или 'week' (конструктор, эта неделя).
export function bootStrip(sandbox, step) {
    new vm.Script(PERIOD_CORE, { filename: 'period_core.js' }).runInContext(sandbox);
    // Часы страницы — как их отдаёт сервер полосе (core/periods.page_config, живой iiko).
    sandbox.KPeriod.configure({ today: '2026-11-01', last_full_day: '2026-10-31', max_date: '2026-11-01' });
    const K = sandbox.KPeriod;
    sandbox.KStrip = fakeStrip(K, step === 'week' ? K.currentPeriod('week') : K.lastDays(30));
    return sandbox.KStrip;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)); };

/**
 * Проверки связки страницы с полосой. cfg:
 *   env: {sandbox, byId, strip}, asyncTest(name, fn), ids: {msg, body, chip, context},
 *   url, what ('розлив'), reply(barName) -> ответ fetch с данными этого бара,
 *   contextLabel(barName) -> как бар напечатан в строке разреза.
 */
export async function stripChecks(cfg) {
    const { env, asyncTest, ids } = cfg;
    const $ = (id) => env.byId[id];
    const PAUSE = env.sandbox.AbcView.CHANGE_PAUSE_MS + 60;
    const K = env.sandbox.KPeriod;

    // Запросы под контролем теста: ответ уходит, когда тест разрешит промис.
    function controlledFetch() {
        const calls = [];
        const pending = [];
        env.sandbox.fetch = (url, opts) => {
            calls.push({ url, body: JSON.parse(opts.body) });
            let resolve;
            const promise = new Promise((r) => { resolve = r; });
            pending.push(resolve);
            return promise;
        };
        return { calls, pending };
    }

    await asyncTest('смена бара в полосе: запрос после паузы, бар — имя iiko из таблицы баров', async () => {
        const { calls, pending } = controlledFetch();
        env.strip.choose({ bar: 'ligovskiy' });
        assert.equal(calls.length, 0, 'запрос ушёл без паузы — серия выборов даст серию запросов в iiko');
        await sleep(PAUSE);
        assert.equal(calls.length, 1, 'после паузы запрос не ушёл: страница не считает сама');
        assert.equal(calls[0].url, cfg.url);
        assert.equal(calls[0].body.bar, 'Лиговский', 'в iiko уходит не имя бара');
        assert.ok($(ids.msg).textContent.startsWith('Считаю ' + cfg.what + ' за 2 – 31 окт 2026, Лиговский…'),
            'не видно, что считается: ' + $(ids.msg).textContent);
        pending[0](cfg.reply('Лиговский'));
        await flush();
        assert.equal($(ids.body).hidden, false, 'ответ не показан');
        assert.match($(ids.context).textContent, new RegExp('разрез: ' + cfg.contextLabel('Лиговский')));
    });

    await asyncTest('серия выборов в полосе — один запрос, по последнему выбору', async () => {
        const { calls, pending } = controlledFetch();
        env.strip.choose({ bar: 'kremenchugskaya' });
        env.strip.choose({ bar: 'varshavskaya' });
        await sleep(PAUSE);
        assert.equal(calls.length, 1, 'на серию выборов ушло ' + calls.length + ' запросов');
        assert.equal(calls[0].body.bar, 'Варшавская');
        pending[0](cfg.reply('Варшавская'));
        await flush();
    });

    await asyncTest('смена бара во время загрузки: старый ответ выброшен, новый запрос ушёл', async () => {
        // До 2026-09-26 run() молча выходил, пока шёл запрос: страница показывала данные
        // всей сети под подписью выбранного бара.
        const { calls, pending } = controlledFetch();
        env.strip.choose({ bar: 'bolshoy' });
        await sleep(PAUSE);
        env.strip.choose({ bar: 'kremenchugskaya' });
        await sleep(PAUSE);
        assert.equal(calls.length, 1, 'второй запрос ушёл, не дождавшись первого');
        pending[0](cfg.reply('Большой пр. В.О'));
        await flush();
        assert.equal(calls.length, 2, 'новый выбор потерян: запрос по нему не ушёл');
        assert.equal(calls[1].body.bar, 'Кременчугская');
        assert.equal($(ids.body).hidden, true, 'устаревший ответ лёг на экран');
        pending[1](cfg.reply('Кременчугская'));
        await flush();
        assert.equal($(ids.body).hidden, false, 'ответ по новому выбору не показан');
        assert.match($(ids.context).textContent, new RegExp('разрез: ' + cfg.contextLabel('Кременчугская')));
    });

    await asyncTest('тот же бар и период повторно — из памяти страницы, без запроса', async () => {
        const { calls } = controlledFetch();
        env.strip.choose({ bar: 'bolshoy' });   // его ответ пришёл в прошлой проверке устаревшим
        await sleep(PAUSE);
        assert.equal(calls.length, 0, 'повторный выбор снова пошёл в iiko');
        assert.match($(ids.context).textContent, new RegExp('разрез: ' + cfg.contextLabel('Большой пр. В.О').replace(/\./g, '\\.')));
        assert.equal($(ids.body).hidden, false);
    });

    await asyncTest('вся сеть — пустой бар в запросе и «Все бары» в строке разреза', async () => {
        const { calls, pending } = controlledFetch();
        env.strip.choose({ bar: '' });
        await sleep(PAUSE);
        // Ответ по всей сети за этот период уже в памяти (первый запрос страницы) —
        // запроса может не быть; если он есть, бар в нём пустой.
        calls.forEach((c) => assert.equal(c.body.bar, ''));
        if (pending.length) { pending[0](cfg.reply('')); await flush(); }
        assert.match($(ids.context).textContent, /разрез: Все бары/);
        assert.ok(!/Общая/.test($(ids.context).textContent), 'вся сеть подписана не «Все бары»');
    });

    await asyncTest('короткий период: «XYZ не считается» видно сразу, до ответа сервера', async () => {
        const { calls, pending } = controlledFetch();
        env.strip.choose({ period: K.periodFor('week', K.fromISO('2026-10-19')) });
        await sleep(PAUSE);
        assert.equal(calls.length, 1);
        assert.deepEqual([calls[0].body.date_from, calls[0].body.date_to], ['2026-10-19', '2026-10-25']);
        assert.equal($(ids.chip).hidden, false, 'на неделе не сказано, что XYZ не считается');
        assert.match($(ids.chip).textContent,
            /XYZ не считается: в периоде 1 полная неделя, нужно от 3; ABC показан/);
        assert.match($(ids.msg).textContent, /за 19 – 25 окт 2026/);
        pending[0](cfg.reply(''));
        await flush();
        env.strip.choose({ period: K.lastDays(21) });
        await sleep(PAUSE);
        assert.ok(!/1 полная неделя/.test($(ids.chip).textContent) || $(ids.chip).hidden,
            'подпись недели осталась на трёх полных неделях');
        pending[1](cfg.reply(''));
        await flush();
    });

    await asyncTest('iiko не успел ответить — просьба сократить период, а не сырой текст ошибки', async () => {
        const cases = [
            { status: 502, body: JSON.stringify({ error: 'Не удалось получить данные из iiko API' }) },
            { status: 504, body: '<html><body>504 Gateway Time-out</body></html>' },
            { status: 0 }
        ];
        for (let i = 0; i < cases.length; i++) {
            const c = cases[i];
            env.sandbox.fetch = () => (c.status
                ? Promise.resolve({ ok: false, status: c.status, text: () => Promise.resolve(c.body) })
                : Promise.reject(new TypeError('Failed to fetch')));
            env.strip.choose({ period: K.lastDays(40 + i) });
            await sleep(PAUSE);
            await flush();
            assert.equal($(ids.msg).textContent, 'iiko не успел ответить — сократите период',
                'HTTP ' + c.status + ': ' + $(ids.msg).textContent);
            assert.match($(ids.msg).className, /err/);
            assert.equal($(ids.body).hidden, true);
        }
        // Причина с сервера остаётся причиной.
        env.sandbox.fetch = () => Promise.resolve({ ok: false, status: 404,
            text: () => Promise.resolve(JSON.stringify({ error: 'Нет данных за выбранный период' })) });
        env.strip.choose({ period: K.lastDays(45) });
        await sleep(PAUSE);
        await flush();
        assert.equal($(ids.msg).textContent, 'Нет данных за выбранный период');
    });
}

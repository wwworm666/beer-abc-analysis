/**
 * ЗАПУСК видов страницы «Маркетинг» в Node с минимальным DOM-стабом.
 *
 *     node tests/test_marketing_runtime.mjs
 *
 * Зачем отдельно от test_marketing_render.mjs: тот проверяет ТЕКСТ файлов
 * (вкладка объявлена, класс описан в CSS, ключ формулы есть). Такой проверкой
 * нельзя поймать ошибку времени выполнения — и она реально прошла мимо:
 * при открытии вкладки «Акции» падало `Cannot read properties of undefined
 * (reading 'from')`, потому что функция вызывалась без обязательного аргумента.
 *
 * Здесь виды по-настоящему исполняются: подставляем document/window/fetch,
 * прогоняем formulas -> common -> charts -> вид, дёргаем Guests.activateTab и
 * проверяем, что в пейне появилась разметка, а не исключение.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

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

// ---------------------------------------------------------------- DOM-стаб
function makeEl(tag) {
    const el = {
        tagName: tag || 'div',
        dataset: {},
        classList: {
            _s: new Set(),
            add(c) { this._s.add(c); },
            remove(c) { this._s.delete(c); },
            toggle(c, on) { if (on) this._s.add(c); else this._s.delete(c); },
            contains(c) { return this._s.has(c); },
        },
        style: {},
        value: '',
        textContent: '',
        innerHTML: '',
        hidden: false,
        listeners: {},
        children: [],
        addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
        removeEventListener() {},
        appendChild(c) { this.children.push(c); return c; },
        querySelector() { return null; },
        querySelectorAll() { return []; },
        scrollIntoView() {},
        getContext() { return {}; },
        setAttribute() {},
        getAttribute() { return null; },
        click() { (this.listeners.click || []).forEach((f) => f({})); },
    };
    return el;
}

function makeDom() {
    const byId = {};
    // Элементы, которые ищет common.js при инициализации и виды при рендере.
    for (const id of ['periodPrev', 'periodNext', 'periodLabel', 'coverageBanner',
                      'pane-promo', 'pane-rfm', 'promoFrom', 'promoTo', 'promoBar',
                      'promoName', 'promoLoad', 'promoStale', 'promoGuestRows',
                      'promoGuestNote', 'promoFilter', 'rfmFilter', 'rfmTbody',
                      'rfmMore', 'rfmScatterNote']) {
        byId[id] = makeEl(id.startsWith('pane') ? 'div' : 'input');
    }
    const document = {
        getElementById(id) { return byId[id] || null; },
        querySelector() { return makeEl(); },
        querySelectorAll() { return []; },
        createElement: makeEl,
        addEventListener() {},          // DOMContentLoaded нам не нужен
        documentElement: makeEl(),
    };
    return { document, byId };
}

function loadGuests(opts) {
    const { document, byId } = makeDom();
    const fetchCalls = [];
    const sandbox = {
        console,
        setTimeout,
        clearTimeout,
        Promise,
        URLSearchParams,
        JSON,
        Math,
        Date,
        Object,
        Array,
        String,
        Number,
        isNaN,
        parseInt,
        parseFloat,
        document,
        // activateTab пишет хеш через history.replaceState.
        history: { replaceState() {}, pushState() {} },
        location: { hash: '' },
        getComputedStyle: () => ({ getPropertyValue: () => '' }),
        Chart: function () { return { destroy() {} }; },
        fetch(url, init) {
            fetchCalls.push({ url, init });
            const body = (opts && opts.respond && opts.respond(url, init)) || {};
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve(body),
            });
        },
    };
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;
    sandbox.GUESTS_CONFIG = { bars: ['Лиговский', 'Варшавская'] };
    sandbox.window.GUESTS_CONFIG = sandbox.GUESTS_CONFIG;

    const ctx = vm.createContext(sandbox);
    for (const f of ['static/js/guests/formulas.js',
                     'static/js/guests/common.js',
                     'static/js/guests/charts.js',
                     ...(opts && opts.views ? opts.views : [])]) {
        vm.runInContext(read(f), ctx, { filename: f });
    }
    return { sandbox, byId, fetchCalls };
}

// ---------------------------------------------------------------- вкладка «Акции»
test('вкладка «Акции» открывается без исключения и НЕ ходит в iiko', () => {
    const { sandbox, byId, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-promo.js'],
    });
    sandbox.Guests.activateTab('promo');
    const pane = byId['pane-promo'];
    assert.ok(pane.innerHTML.length > 0, 'пейн пустой — вид не отрисовался');
    assert.ok(pane.innerHTML.includes('Анализировать'), 'нет кнопки загрузки');
    assert.ok(pane.innerHTML.includes('promo-controls'), 'нет панели контролов');
    assert.equal(fetchCalls.length, 0,
        'при открытии вкладки был запрос: ' + fetchCalls.map((c) => c.url).join(', '));
});

test('«Акции»: контролы получили значения по умолчанию', () => {
    const { sandbox, byId } = loadGuests({ views: ['static/js/guests/views-promo.js'] });
    sandbox.Guests.activateTab('promo');
    const html = byId['pane-promo'].innerHTML;
    assert.ok(/id="promoFrom" value="\d{4}-\d{2}-\d{2}"/.test(html),
        'дата начала не подставлена');
    assert.ok(/id="promoTo" value="\d{4}-\d{2}-\d{2}"/.test(html),
        'дата конца не подставлена');
    assert.ok(html.includes('Лиговский'), 'точки из конфига не попали в селект');
});

test('«Акции»: нажатие «Анализировать» отправляет POST и рисует отчёт', () => {
    const answer = {
        discount_names: ['Часы'],
        total_rows: 2,
        stores_summary: {
            'Часы': [{ store: 'Лиговский', orders_count: 1, guests_count: 1,
                       sum_with_discount: 900, discount_sum: 100 }],
            '__all__': [{ store: 'Лиговский', orders_count: 1, guests_count: 1,
                          sum_with_discount: 900, discount_sum: 100 }],
        },
        discounts: {
            'Часы': [{ card_number: '2001', customer_name: 'Гость', visits: 1,
                       orders: 1, visit_dates: ['2026-07-01'], last_visit: '2026-07-01',
                       first_visit: '2026-07-01', recency_days: 0,
                       frequency_per_week: 1, avg_check: 900,
                       sum_with_discount: 900, discount_sum: 100,
                       stores: ['Лиговский'],
                       dishes: [{ name: 'Пиво', sum_with_discount: 900,
                                  discount_sum: 100, store: 'Лиговский',
                                  order_num: '1', date: '2026-07-01' }] }],
            '__all__': [{ card_number: '2001', customer_name: 'Гость', visits: 1,
                          orders: 1, visit_dates: ['2026-07-01'],
                          last_visit: '2026-07-01', first_visit: '2026-07-01',
                          recency_days: 0, frequency_per_week: 1, avg_check: 900,
                          sum_with_discount: 900, discount_sum: 100,
                          stores: ['Лиговский'], dishes: [] }],
        },
    };
    const { sandbox, byId, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-promo.js'],
        respond: () => answer,
    });
    sandbox.Guests.activateTab('promo');
    // Кнопка появилась после первого рендера — жмём её.
    byId.promoLoad.click();
    return new Promise((resolve) => setTimeout(() => {
        try {
            assert.equal(fetchCalls.length, 1, 'ожидался один запрос');
            assert.ok(fetchCalls[0].url.includes('/api/discount-analyze'),
                'запрос ушёл не туда: ' + fetchCalls[0].url);
            assert.equal(fetchCalls[0].init.method, 'POST', 'должен быть POST');
            const body = JSON.parse(fetchCalls[0].init.body);
            assert.ok(body.date_from && body.date_to, 'в теле нет диапазона');
            const html = byId['pane-promo'].innerHTML;
            assert.ok(html.includes('Выручка без скидки'), 'нет метрик');
            assert.ok(html.includes('По точкам'), 'нет разбивки по точкам');
            assert.ok(html.includes('Гости акции'), 'нет таблицы гостей');
            resolve();
        } catch (e) {
            failed++;
            passed--;
            console.log('      (после клика) ' + e.message);
            resolve();
        }
    }, 30));
});

// ---------------------------------------------------------------- вкладка RFM
test('вкладка RFM открывается, запрашивает витрину и рисует таблицу', () => {
    const rfmAnswer = {
        meta: { period_label: 'Август 2026', p_end: '2026-08-31',
                asof: '2026-08-13', coverage_from: '2017-12-18',
                coverage_to: '2026-08-12', last_synced_at: '2026-08-13T05:10:00' },
        data: {
            asof: '2026-08-13', window_start: '2025-08-14', window_days: 365,
            total_guests: 2, venue: null, venue_name: null,
            venues: [{ key: 'bolshoy', name: 'Большой пр. В.О' },
                     { key: 'ligovskiy', name: 'Лиговский' }],
            r_thresholds: [7, 14, 30, 60], f_thresholds: [260, 104, 52, 12],
            segments: [{ segment: 'CHAMPIONS', count: 1, share_pct: 50, revenue: 5000 },
                       { segment: 'CHURNED', count: 1, share_pct: 50, revenue: 1000 }],
            guests: [
                { guest_id: '79001', name: 'Аня', phone: '79001',
                  card_number: '2001', last_visit: '2026-08-12', recency_days: 1,
                  frequency: 120, orders: 130, avg_check: 400, monetary: 52000,
                  r: 'R5', f: 'F4', segment: 'CHAMPIONS' },
                { guest_id: '79002', name: 'Боб', phone: '79002',
                  card_number: '2002', last_visit: '2026-01-01', recency_days: 224,
                  frequency: 60, orders: 60, avg_check: 200, monetary: 12000,
                  r: 'R1', f: 'F3', segment: 'CHURNED' },
            ],
        },
    };
    const { sandbox, byId, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-rfm.js'],
        respond: () => rfmAnswer,
    });
    sandbox.Guests.activateTab('rfm');
    return new Promise((resolve) => setTimeout(() => {
        try {
            assert.ok(fetchCalls.length >= 1, 'запроса не было');
            assert.ok(fetchCalls[0].url.includes('/api/guests/rfm'),
                'не тот эндпоинт: ' + fetchCalls[0].url);
            const html = byId['pane-rfm'].innerHTML;
            assert.ok(html.includes('Чемпионы'), 'нет карточек сегментов');
            assert.ok(html.includes('Вся сеть'), 'нет переключателя точек');
            assert.ok(html.includes('Давность последнего визита'), 'нет гистограммы');
            assert.ok(html.includes('Частота против давности'), 'нет диаграммы');
            assert.ok(html.includes('rfmTbody'), 'нет таблицы гостей');
            assert.ok(html.includes('Последний визит'), 'потеряна колонка даты визита');
            assert.ok(html.includes('Ср. чек'), 'потеряна колонка среднего чека');
            resolve();
        } catch (e) {
            failed++;
            passed--;
            console.log('      (RFM) ' + e.message);
            resolve();
        }
    }, 30));
});

// ---------------------------------------------------------------- панель периода
test('панель периода скрывается на «Акциях» и возвращается на других вкладках', () => {
    const { sandbox, byId } = loadGuests({
        views: ['static/js/guests/views-promo.js', 'static/js/guests/views-rfm.js'],
    });
    // querySelector('.guests-controls') должен отдавать один и тот же элемент,
    // иначе класс проверять негде.
    const controls = makeEl('div');
    sandbox.document.querySelector = (sel) =>
        (sel === '.guests-controls' ? controls : makeEl());
    sandbox.Guests.activateTab('promo');
    assert.ok(controls.classList.contains('own-period'),
        'на «Акциях» глобальный период не скрыт');
    sandbox.Guests.activateTab('rfm');
    assert.ok(!controls.classList.contains('own-period'),
        'класс залип после уход с «Акций»');
});

// Итог печатаем после того, как отработают асинхронные проверки.
setTimeout(() => {
    console.log(`\n${passed} ok, ${failed} failed`);
    process.exit(failed ? 1 : 0);
}, 200);

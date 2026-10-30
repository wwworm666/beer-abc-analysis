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
                      'pane-summary', 'pane-growth', 'pane-churn', 'pane-activity', 'pane-cohorts',
                      'pane-rfm', 'pane-ltv', 'pane-promo', 'pane-products', 'pane-venues',
                      'pane-never', 'pane-guest',
                      'barPick', 'barPickBtn', 'barPickMenu', 'barPickLabel',
                      'promoFrom', 'promoTo', 'promoBar',
                      'promoName', 'promoLoad', 'promoStale', 'promoGuestRows',
                      'promoGuestNote', 'promoFilter', 'rfmFilter', 'rfmTbody',
                      'rfmMore', 'rfmScatterNote']) {
        byId[id] = makeEl(id.startsWith('pane') ? 'div' : 'input');
    }
    // DOMContentLoaded копим: тесты общего бара запускают init страницы сами.
    const ready = [];
    const document = {
        getElementById(id) { return byId[id] || null; },
        querySelector() { return makeEl(); },
        querySelectorAll() { return []; },
        createElement: makeEl,
        addEventListener(ev, fn) { if (ev === 'DOMContentLoaded') ready.push(fn); },
        documentElement: makeEl(),
    };
    return { document, byId, ready };
}

// Заглушка window.GH (static/js/guest_hub/common.js): общий фильтр бара раздела.
function makeGh(initialBar) {
    const gh = {
        bar: initialBar || '',
        setCalls: [],
        menuToggles: 0,
        BARS: [
            { key: 'bolshoy', name: 'Большой пр. В.О', short: 'ВО' },
            { key: 'ligovskiy', name: 'Лиговский', short: 'Лиг' },
            { key: 'kremenchugskaya', name: 'Кременчугская', short: 'Крем' },
            { key: 'varshavskaya', name: 'Варшавская', short: 'Вар' },
        ],
        getBar() { return gh.bar; },
        setBar(key) {
            gh.setCalls.push(key);
            gh.bar = gh.BARS.some((b) => b.key === key) ? key : '';
            return gh.bar;
        },
        barName(key) {
            const b = gh.BARS.find((x) => x.key === key);
            return b ? b.name : 'Все бары';
        },
        toggleMenu() { gh.menuToggles++; return true; },
    };
    return gh;
}

function loadGuests(opts) {
    const { document, byId, ready } = makeDom();
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
    if (opts && opts.gh) sandbox.GH = opts.gh;

    const ctx = vm.createContext(sandbox);
    for (const f of ['static/js/guests/formulas.js',
                     'static/js/guests/common.js',
                     'static/js/guests/charts.js',
                     ...(opts && opts.views ? opts.views : [])]) {
        vm.runInContext(read(f), ctx, { filename: f });
    }
    // init страницы (как по DOMContentLoaded) — только если тест просит.
    if (opts && opts.init) ready.forEach((fn) => fn());
    return { sandbox, byId, fetchCalls };
}

// Параметры запроса: '/api/guests/rfm?period_type=month&store=x' -> URLSearchParams.
function query(url) {
    return new URLSearchParams(String(url).split('?')[1] || '');
}

// Ответ витрины с meta: venue — бар, по которому сервер посчитал отчёт.
function metaOf(venue, venueName) {
    return { period_label: 'Август 2026', p_end: '2026-08-31', asof: '2026-08-13',
             coverage_from: '2017-12-18', coverage_to: '2026-08-12',
             last_synced_at: '2026-08-13T05:10:00',
             venue: venue || null, venue_name: venueName || null };
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
            // Своего переключателя точек у RFM больше нет (2026-09-29): бар общий
            // для страницы, и без выбранного бара store в запрос не уходит.
            assert.ok(!html.includes('data-rvenue'), 'у RFM снова свой переключатель точек');
            assert.ok(!query(fetchCalls[0].url).has('store'), 'store без выбранного бара');
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

// ---------------------------------------------------------------- общий бар (2026-09-29)
// Бар — общий фильтр раздела «Гости» (GH.getBar / GH.setBar). Страница берёт его
// при init, показывает в кнопке «Бар» и шлёт параметром store во все отчёты.

const SUMMARY = {
    base_size: 100, active_guests: 10, registrations: 5, registrations_ytd: 50,
    first_orders: 6, first_orders_ytd: 60, conversion_pct: 100, avg_days_to_first_order: 0,
    avg_frequency: 1.5, avg_check: 1500, avg_check_ytd: 1400, avg_ltv: 9000,
    revenue_period: 150000, orders_period: 100,
    activity_segments: [{ segment: 'active', count: 10 }],
    registrations_by_store: [{ store: 'bolshoy', store_name: 'Большой пр. В.О', count: 5 }],
    never: { available: false, reason: null, source_status: 'ok' },
};

// Шаг асинхронного сценария: ждём, пока fetch-промисы и отрисовка отработают.
function later(fn) {
    return new Promise((resolve) => setTimeout(() => {
        try {
            fn();
        } catch (e) {
            failed++;
            passed--;
            console.log('      (общий бар) ' + e.message);
        }
        resolve();
    }, 30));
}

test('общий бар: кнопка и меню из фильтра раздела, store уходит в запросы', () => {
    const gh = makeGh('ligovskiy');
    const { sandbox, byId, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-summary.js'],
        gh, init: true,
        respond: (url) => {
            const store = query(url).get('store');
            const name = store ? gh.barName(store) : null;
            // Сервер с баром отдаёт пустое сравнение баров и never с reason=venue.
            const data = store
                ? Object.assign({}, SUMMARY, { registrations_by_store: [],
                                               never: { available: false, reason: 'venue' } })
                : SUMMARY;
            return { meta: metaOf(store, name), data };
        },
    });
    assert.equal(byId.barPickLabel.textContent, 'Лиговский', 'кнопка не показывает бар раздела');
    assert.ok(byId.barPick.classList.contains('is-set'), 'выбранный бар не подсвечен');
    assert.equal(query(fetchCalls[0].url).get('store'), 'ligovskiy',
        'первая загрузка ушла без бара: ' + fetchCalls[0].url);
    return later(() => {
        const html = byId['pane-summary'].innerHTML;
        assert.ok(html.includes('за баром первой покупки'), 'у регистраций нет подписи бара');
        assert.ok(html.includes('по барам не делится'), 'Orderia не помечена «по барам не делится»');
        assert.ok(!html.includes('Регистраций на точку'), 'сравнение баров показано в режиме бара');
        assert.ok(html.includes('Выбран бар'), 'в «Как считается» нет правила бара');
        // Меню: пункты раздела и пояснение; открывает его общий GH.toggleMenu.
        byId.barPickBtn.click();
        assert.equal(gh.menuToggles, 1, 'меню не открывается через GH.toggleMenu');
        const menu = byId.barPickMenu.innerHTML;
        for (const needle of ['data-bar=""', 'data-bar="varshavskaya"', 'Все бары', 'gh-menu-note']) {
            assert.ok(menu.includes(needle), 'в меню нет ' + needle);
        }
        const pick = (key) => byId.barPickMenu.listeners.click[0]({
            target: { closest: () => ({ getAttribute: () => key }) },
        });
        pick('varshavskaya');
        assert.deepEqual(gh.setCalls, ['varshavskaya'], 'выбор не записан в общий фильтр');
        assert.equal(byId.barPickLabel.textContent, 'Варшавская');
        const last = fetchCalls[fetchCalls.length - 1];
        assert.equal(query(last.url).get('store'), 'varshavskaya', 'вкладка не перезагрузилась по бару');
        pick('');
        const all = fetchCalls[fetchCalls.length - 1];
        assert.ok(!query(all.url).has('store'), '«Все бары» отправили store');
        assert.ok(!byId.barPick.classList.contains('is-set'), 'подсветка осталась на «Все бары»');
    });
});

test('без модуля раздела (GH) страница работает по всей сети', () => {
    const { sandbox, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-summary.js'], init: true,
        respond: () => ({ meta: metaOf(null), data: SUMMARY }),
    });
    assert.equal(sandbox.Guests.state.bar, '');
    assert.ok(!query(fetchCalls[0].url).has('store'));
});

test('«Не купившие» при выбранном баре подписаны «по всей сети»', () => {
    const never = {
        source: { status: 'ok', fetched_at: '2026-08-13T05:10:00', error: null, reported: 3 },
        coverage: { from: '2024-02-29', to: '2026-08-12' },
        totals: { reported: 3, confirmed: 2, junk: 0, false_positives: 1, fp_same_card: 1,
                  fp_other_card: 0, fp_guests: 1, fp_revenue: 1000, reachable_telegram: 2 },
        period: { registered_total: 5, bought: 3, never: 2, conversion_pct: 60,
                  conversion_available: true },
        by_month: [], by_balance: [], false_positives: [],
    };
    const { sandbox, byId } = loadGuests({
        views: ['static/js/guests/views-never.js'], gh: makeGh('bolshoy'), init: true,
        // Сервер ?store= у этого отчёта не читает: meta.venue = null.
        respond: () => ({ meta: metaOf(null), data: never }),
    });
    sandbox.Guests.activateTab('never');
    return later(() => {
        const html = byId['pane-never'].innerHTML;
        assert.ok(html.includes('scope-note') && html.includes('по всей сети'),
            'нет подписи, что отчёт по всей сети');
    });
});

// ---------------------------------------------------------------- вкладка «Отток»
function churnRow(over) {
    return Object.assign({
        p_start: '2026-08-01', p_end: '2026-08-31', label: 'Август 2026',
        asof: '2026-08-31', state: 'complete', start_alive: 100, died: 12, reactivated: 5,
        bounced: 0, new: 20, new_died: 0, end_alive: 113, churn_pct: 12.0,
        newbie_no_return: 9, newbie_no_return_pct: 45.0, newbie_matures_on: '2026-10-01',
        damage_month: 2500, damage_year: 30000, slowing: 4, slowing_base: 40, slowing_pct: 10.0,
    }, over || {});
}
function churnData(period) {
    return {
        dead_days: 30, choices: [30, 60, 90, 180], data_to: '2026-09-12',
        series: [churnRow({ p_start: '2026-07-01', p_end: '2026-07-31', label: 'Июль 2026',
                            churn_pct: 10.0, new: 18, reactivated: 6 }), period],
        period: period,
        leavers: { total: 12, damage_month: 2500, damage_year: 30000, buckets: [
            { segment: '1', visits_from: 1, visits_to: 1, count: 7, share_pct: 58.3, avg_ltv: 1500,
              damage_month: 900 },
            { segment: '2-3', visits_from: 2, visits_to: 3, count: 3, share_pct: 25.0, avg_ltv: 4200,
              damage_month: 700 },
            { segment: '4-8', visits_from: 4, visits_to: 8, count: 2, share_pct: 16.7, avg_ltv: 9000,
              damage_month: 900 },
            { segment: '9+', visits_from: 9, visits_to: null, count: 0, share_pct: 0.0, avg_ltv: null,
              damage_month: 0 },
        ] },
        return_gaps: { window_from: '2025-09-01', window_to: '2026-08-31', returns: 300,
                       percentiles: [{ pct: 50, days: 9 }, { pct: 90, days: 75 }],
                       later_than: [{ days: 30, pct: 27.1 }, { days: 60, pct: 12.0 },
                                    { days: 90, pct: 6.2 }, { days: 180, pct: 2.1 }] },
    };
}
// Ответ /api/guests/churn-guests для группы из запроса: limit 50 отдал 2 строки из 4.
function guestList(group, bucket) {
    return { asof: '2026-08-31', dead_days: 30, group: group, bucket: bucket || null, mature: true,
             matures_on: null, total: 4, returned: 2, limit: 50, guests: [
        { guest_id: 'g1', name: 'Анна', phone: '79110000001', card_number: '1001',
          first_visit: '2025-02-01', last_visit: '2026-07-20', recency_days: 42, visits_total: 31,
          ltv: 64000, visits_period: 0, revenue_period: 0, revenue_12m: 52000, pause_days: null,
          visits_prev: 6, visits_recent: 3, damage_month: 4300 },
        { guest_id: 'g2', name: '', phone: '79110000002', card_number: '1002',
          first_visit: '2026-03-01', last_visit: '2026-07-02', recency_days: 60, visits_total: 5,
          ltv: 9000, visits_period: 0, revenue_period: 0, revenue_12m: 9000, pause_days: null,
          visits_prev: 3, visits_recent: 1, damage_month: 750 },
    ] };
}
// Два запроса вкладки: отток и список гостей выбранной плитки — каждому свой ответ.
function churnRespond(meta, data) {
    return (url) => {
        if (String(url).startsWith('/api/guests/churn-guests?')) {
            const q = query(url);
            return { meta: meta, data: guestList(q.get('group'), q.get('bucket')) };
        }
        return { meta: meta, data: data };
    };
}

test('«Отток»: открывается, просит порог 30 и бар страницы, рисует плитки и «Кто уходит»', () => {
    const { sandbox, byId, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-churn.js'], gh: makeGh('ligovskiy'), init: true,
        respond: churnRespond(Object.assign(metaOf('ligovskiy', 'Лиговский'),
                                            { period_type: 'month' }),
                              churnData(churnRow())),
    });
    sandbox.Guests.activateTab('churn');
    return later(() => {
        const call = fetchCalls.find((c) => String(c.url).startsWith('/api/guests/churn?'));
        assert.ok(call, 'вкладка не запросила /api/guests/churn');
        assert.equal(query(call.url).get('dead_days'), '30', 'порог по умолчанию — 30');
        assert.equal(query(call.url).get('store'), 'ligovskiy', 'бар страницы не ушёл в запрос');
        const html = byId['pane-churn'].innerHTML.replace(/[  ]/g, ' ');
        assert.ok(html.includes('Отток за период') && html.includes('12%'), 'нет плитки оттока');
        assert.ok(html.includes('июл 26: 10%'), 'нет сравнения с прошлым периодом');
        assert.ok(html.includes('пришёл и не вернулся'), 'нет таблицы «Кто уходит»');
        assert.ok(html.includes('data-days="90"'), 'нет переключателя порога');
        assert.equal((html.match(/class="gmetric"/g) || []).length, 8,
            'восемь плиток: потери и приток с базой');
        assert.ok(html.includes('Новые гости') && html.includes('июл 26: 18'),
            '«Новые гости» без сравнения с прошлым периодом');
        assert.ok(html.includes('Вернулись после паузы') && html.includes('июл 26: 6'),
            'нет отдельной плитки «Вернулись после паузы»');
        assert.equal((html.match(/class="how-block"/g) || []).length, 5,
            '«Как считается» — у подсказки к порогу и у каждой из четырёх карточек');
    });
});

test('«Отток»: ущерб, подсказка к порогу и кликабельные плитки со списком гостей', () => {
    const { sandbox, byId, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-churn.js'], gh: makeGh('ligovskiy'), init: true,
        respond: churnRespond(Object.assign(metaOf('ligovskiy', 'Лиговский'),
                                            { period_type: 'month', p_end: '2026-08-31' }),
                              churnData(churnRow())),
    });
    sandbox.Guests.activateTab('churn');
    return later(() => {
        const call = fetchCalls.find((c) => String(c.url).startsWith('/api/guests/churn-guests?'));
        assert.ok(call, 'вкладка не запросила список гостей');
        const q = query(call.url);
        assert.deepEqual([q.get('group'), q.get('dead_days'), q.get('limit'), q.get('store')],
            ['left', '30', '50', 'ligovskiy'], 'по умолчанию — «Ушли», тот же порог и бар, 50 строк');
        assert.equal(q.get('bucket'), null, 'без выбранной строки «Кто уходит» корзины нет');
        const html = byId['pane-churn'].innerHTML.replace(/[\u2009\u00a0]/g, ' ');
        assert.ok(html.includes('Ущерб от оттока') && html.includes('2 500 ₽') &&
            html.includes('в год: 30 000 ₽'), 'нет плитки ущерба');
        assert.ok(html.includes('Ущерб в месяц') && html.includes('900 ₽'),
            'нет колонки ущерба в «Кто уходит»');
        assert.ok(html.includes('из 40 ходивших раз в месяц и чаще (10%)'),
            'нет плитки «Стали ходить реже»');
        assert.ok(html.includes('Возвратов позже порога') && html.includes('<b>30 дн — 27,1%</b>') &&
            html.includes('90 дн — 6,2%') && html.includes('9 из 10 — за 75 дн'),
            'нет подсказки к порогу или выбранный порог не выделен');
        // Плитки с гостями кликабельны: «Ушли» и «Ущерб» (одна группа), «Стали ходить реже»,
        // «Новые гости», «Вернулись после паузы» и созревшая «Не вернулись»; «Ушли» выбраны.
        assert.equal((html.match(/class="churn-pick/g) || []).length, 6, 'кликабельных плиток не 6');
        assert.equal((html.match(/class="churn-pick active" data-group="left"/g) || []).length, 2,
            'выбранная группа «Ушли» не подсвечена');
        for (const group of ['slowing', 'new', 'reactivated', 'newbie_no_return']) {
            assert.ok(html.includes('data-group="' + group + '"'), 'не кликается: ' + group);
        }
        assert.equal((html.match(/class="churn-bucket-pick/g) || []).length, 4,
            'строки «Кто уходит» не кликаются');
        assert.ok(html.includes('data-bucket="9+"'), 'нет строки «9 визитов и больше»');
        assert.ok(html.includes('<td><span class="dim">без имени</span></td>') && !html.includes('<td>g2</td>'),
            'гость без имени показан номером, а не «без имени», как в RFM');
        assert.ok(html.includes('Ушли · 4') && html.includes('Анна') && html.includes('4 300 ₽') &&
            html.includes('всего 4, все с телефонами — в CSV') && html.includes('Другая группа'),
            'нет списка «Ушли»');
        // С баром: колонки «Любимая точка» нет (все визиты в нём), сравнения баров — тоже.
        assert.ok(!html.includes('Любимая точка') && !html.includes('Бары рядом'),
            'в режиме бара — колонка любимой точки или сравнение баров');
        assert.ok(html.includes('Сравнение баров — при выборе «Все бары».'), 'нет подсказки про «Все бары»');
        assert.ok(!html.includes('churn-more-btn'), '2 строки — без кнопки «Показать ещё»');
        // Длина графиков: месяц — 1 год · 2 года (по умолчанию) · 5 лет · всё время.
        const main = fetchCalls.find((c) => String(c.url).startsWith('/api/guests/churn?'));
        assert.equal(query(main.url).get('periods'), '24', 'по умолчанию два года месяцев');
        for (const [v, label] of [['12', '1 год'], ['60', '5 лет'], ['all', 'всё время']]) {
            assert.ok(html.includes('data-range="' + v + '">' + label + '<'), 'нет кнопки ' + label);
        }
        assert.ok(html.includes('class="sub-btn active" data-range="24">2 года<'),
            'выбранная длина не подсвечена');
        assert.ok(html.includes('/api/guests/churn-guests?period_type=month&anchor=2026-08-31' +
            '&store=ligovskiy&group=left&dead_days=30&export=csv'), 'нет выгрузки CSV по тем же условиям');
    });
});

// «Все бары»: тот же отчёт по каждому бару — у каждого свои числа; Варшавская не ответила.
function barRow(over) {
    return churnRow(Object.assign({ p_start: '2026-08-01', p_end: '2026-08-31' }, over));
}
const BAR_PERIODS = {
    bolshoy: barRow({ churn_pct: 61.6, died: 98, new_died: 0, damage_month: 74238 }),
    ligovskiy: barRow({ churn_pct: 48.1, died: 77, new_died: 0, damage_month: 71233 }),
    kremenchugskaya: barRow({ churn_pct: 30.0, died: 20, new_died: 1, damage_month: 9000 }),
};

test('«Отток» во всей сети: «Бары рядом», «Отток по барам» и любимая точка в списке', () => {
    const net = churnRow({ p_start: '2026-08-01', p_end: '2026-08-31' });
    const { sandbox, byId, fetchCalls } = loadGuests({
        views: ['static/js/guests/views-churn.js'], gh: makeGh(''), init: true,
        respond: (url) => {
            const q = query(url);
            const meta = Object.assign(metaOf(q.get('store')), { period_type: 'month',
                                                                  p_end: '2026-08-31' });
            if (String(url).startsWith('/api/guests/churn-guests?')) {
                const list = guestList(q.get('group'), q.get('bucket'));
                list.guests[0].favorite_store = 'ligovskiy';
                list.guests[0].favorite_store_name = 'Лиговский';
                return { meta: meta, data: list };
            }
            const store = q.get('store');
            if (store === 'varshavskaya') return { error: 'TypeError: boom' };
            const period = store ? BAR_PERIODS[store] : net;
            return { meta: meta, data: Object.assign(churnData(period),
                { series: [barRow({ p_start: '2026-07-01', p_end: '2026-07-31' }), period] }) };
        },
    });
    sandbox.Guests.activateTab('churn');
    return later(() => {
        const churnCalls = fetchCalls.filter((c) => String(c.url).startsWith('/api/guests/churn?'));
        assert.deepEqual(churnCalls.map((c) => query(c.url).get('store')),
            [null, 'bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'],
            'сеть и каждый бар — тем же маршрутом');
        for (const c of churnCalls) {
            assert.deepEqual([query(c.url).get('dead_days'), query(c.url).get('periods')], ['30', '24'],
                'у баров тот же порог и та же длина графиков');
        }
        const html = byId['pane-churn'].innerHTML.replace(/[\u2009\u00a0]/g, ' ');
        assert.ok(!html.includes('pane-error'), 'вкладка упала из-за бара без ответа');
        assert.ok(html.includes('Бары рядом · авг 26'), 'нет сравнения баров');
        for (const needle of ['<td>Большой пр. В.О</td><td class="num">61,6%</td><td class="num">98</td>',
                              '<td>Лиговский</td><td class="num">48,1%</td>',
                              '<td>Кременчугская</td><td class="num">30%</td><td class="num">21</td>',
                              '<td>Варшавская</td><td class="num">—</td>',
                              '<tr class="row-total"><td>Вся сеть</td><td class="num">12%</td>']) {
            assert.ok(html.includes(needle), 'в таблице баров нет: ' + needle);
        }
        assert.ok(html.includes('Бары не складываются в сеть'), 'нет подписи, что бары не складываются');
        assert.ok(html.includes('id="churnBarsChart"'), 'нет столбиков по барам');
        assert.ok(html.includes('Отток по барам'), 'нет малых графиков по барам');
        for (const key of ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']) {
            assert.ok(html.includes('id="churnBarChart-' + key + '"'), 'нет графика бара ' + key);
        }
        assert.ok(html.includes('<th>Любимая точка</th>') && html.includes('<td>Лиговский</td>'),
            'в списке по сети нет любимой точки гостя');
        // Порядок: плитки, бары рядом, кто уходит, список, графики по периодам, по барам, баланс.
        const order = ['class="metric-grid', '<h3>Бары рядом', '<h3>Кто уходит', 'id="churnList"',
                       '<h3>Отток по периодам', '<h3>Отток по барам', '<h3>Баланс базы']
            .map((t) => html.indexOf(t));
        assert.ok(order.every((v, i) => v >= 0 && (i === 0 || v > order[i - 1])),
            'карточки не в том порядке: ' + order.join(', '));
    });
});

test('«Отток»: список — первые 10 гостей, остальные по кнопке «Показать ещё»', () => {
    const many = (group, bucket) => {
        const list = guestList(group, bucket);
        list.total = 82;
        list.returned = 12;
        list.guests = Array.from({ length: 12 }, (_, i) => Object.assign({}, list.guests[0],
            { guest_id: 'g' + i, name: 'Гость ' + i }));
        return list;
    };
    const { sandbox, byId } = loadGuests({
        views: ['static/js/guests/views-churn.js'], gh: makeGh('ligovskiy'), init: true,
        respond: (url) => {
            const meta = Object.assign(metaOf('ligovskiy', 'Лиговский'), { period_type: 'month' });
            const q = query(url);
            return String(url).startsWith('/api/guests/churn-guests?')
                ? { meta: meta, data: many(q.get('group'), q.get('bucket')) }
                : { meta: meta, data: churnData(churnRow()) };
        },
    });
    sandbox.Guests.activateTab('churn');
    return later(() => {
        const html = byId['pane-churn'].innerHTML;
        assert.equal((html.match(/<tr class="churn-more" hidden>/g) || []).length, 2,
            'строки после десятой не спрятаны');
        assert.ok(html.includes('class="sync-btn churn-more-btn">Показать ещё 2<'),
            'нет кнопки «Показать ещё 2»');
        assert.ok(html.includes('всего 82, все с телефонами — в CSV'), 'нет числа всех гостей группы');
    });
});

test('«Отток»: будущий период — подпись вместо плиток, без исключения', () => {
    const future = churnRow({ p_start: '2026-10-01', p_end: '2026-10-31', label: 'Октябрь 2026',
                              asof: null, state: 'future', start_alive: null, died: null,
                              reactivated: null, bounced: null, new: null, new_died: null,
                              end_alive: null, churn_pct: null, newbie_no_return: null,
                              newbie_no_return_pct: null, newbie_matures_on: null,
                              damage_month: null, damage_year: null, slowing: null,
                              slowing_base: null, slowing_pct: null });
    const { sandbox, byId } = loadGuests({
        views: ['static/js/guests/views-churn.js'], init: true,
        respond: churnRespond(Object.assign(metaOf(), { period_type: 'month' }),
                              Object.assign(churnData(future), { return_gaps: null })),
    });
    sandbox.Guests.activateTab('churn');
    return later(() => {
        const html = byId['pane-churn'].innerHTML;
        assert.ok(!html.includes('pane-error'), 'вид упал на будущем периоде');
        assert.ok(html.includes('считать пока нечего'), 'нет подписи про будущий период');
        assert.ok(!html.includes('<h3>Кто уходит'), 'у будущего периода нечего разбирать');
        assert.ok(!html.includes('Бары рядом'), 'у будущего периода нечего сравнивать');
    });
});

// ---------------------------------------------------------------- вкладка «LTV»
function ltvRow(over) {
    return Object.assign({
        p_start: '2026-08-01', p_end: '2026-08-31', label: 'Август 2026', asof: '2026-08-31',
        state: 'complete', guests: 10, checks: 40, revenue: 50000, ltv: 5000, avg_check: 1250,
        checks_per_guest: 4.0, delta: 614, check_effect: 332, frequency_effect: 282,
    }, over || {});
}
function ltvData(byVenue) {
    return {
        asof: '2026-08-31',
        lifetime: { guests: 10, revenue: 50000, avg_ltv: 5000, checks: 40, avg_check: 1250,
                    checks_per_guest: 4.0 },
        ytd: { guests: 5, revenue: 10000, avg_revenue_per_guest: 2000 },
        by_venue: byVenue,
        series: [ltvRow({ p_start: '2026-07-01', p_end: '2026-07-31', label: 'Июль 2026',
                          ltv: 4386, delta: null, check_effect: null, frequency_effect: null }),
                 ltvRow(),
                 ltvRow({ p_start: '2026-09-01', p_end: '2026-09-30', state: 'partial',
                          asof: '2026-09-12', delta: -400, check_effect: 0,
                          frequency_effect: -400 })],
    };
}

test('LTV: дата среза, из чего состоит и ряд с разложением изменения', () => {
    const { sandbox, byId } = loadGuests({
        views: ['static/js/guests/views-ltv.js'], init: true,
        respond: () => ({ meta: Object.assign(metaOf(), { period_type: 'month' }),
                          data: ltvData([{ store: 'bolshoy', store_name: 'Большой пр. В.О',
                                           guests: 10, ltv: 5000 }]) }),
    });
    sandbox.Guests.activateTab('ltv');
    return later(() => {
        // fmtMoney ставит перед «₽» узкий пробел — сравниваем без оглядки на вид пробела.
        const html = byId['pane-ltv'].innerHTML.replace(/[\u2009\u00a0]/g, ' ');
        assert.ok(html.includes('LTV на 31.08.2026'), 'нет даты среза у LTV');
        assert.ok(html.includes('Чеков на гостя') && html.includes('4,00'), 'нет частоты');
        assert.ok(html.includes('+614 ₽') && html.includes('+332 ₽') && html.includes('+282 ₽'),
            'нет разложения изменения');
        assert.ok(html.includes('−400 ₽'), 'отрицательное изменение без знака');
        assert.ok(html.includes('row-partial') && html.includes('по 12.09'),
            'неполный период не помечен');
        assert.ok(html.includes('LTV по точкам'), 'у сети есть сравнение баров');
    });
});

test('LTV при выбранном баре не рисует сравнение баров', () => {
    const { sandbox, byId } = loadGuests({
        views: ['static/js/guests/views-ltv.js'], gh: makeGh('ligovskiy'), init: true,
        respond: () => ({ meta: metaOf('ligovskiy', 'Лиговский'), data: ltvData([]) }),
    });
    sandbox.Guests.activateTab('ltv');
    return later(() => {
        const html = byId['pane-ltv'].innerHTML;
        assert.ok(!html.includes('LTV по точкам'), 'сравнение баров показано в режиме бара');
        assert.ok(html.includes('при выборе «Все бары»'), 'нет подсказки, где сравнение');
    });
});

test('«Акции»: бар страницы — начальное значение «Точки», чужое имя — все точки', () => {
    const first = loadGuests({
        views: ['static/js/guests/views-promo.js'], gh: makeGh('ligovskiy'), init: true,
    });
    first.sandbox.Guests.activateTab('promo');
    const html = first.byId['pane-promo'].innerHTML;
    assert.ok(html.includes('<option value="Лиговский" selected>'), 'точка не взята из бара страницы');
    assert.equal(first.fetchCalls.length, 0, 'вкладка «Акции» сама пошла в iiko');
    // Бара нет среди вариантов селекта (config.bars) — не выдумываем имя для iiko.
    const second = loadGuests({
        views: ['static/js/guests/views-promo.js'], gh: makeGh('bolshoy'), init: true,
    });
    second.sandbox.Guests.activateTab('promo');
    assert.ok(!second.byId['pane-promo'].innerHTML.includes(' selected>Большой'),
        'подставлено имя, которого нет в списке точек');
    assert.ok(second.byId['pane-promo'].innerHTML.includes('<option value="">Все точки</option>'));
});

// Итог печатаем после того, как отработают асинхронные проверки.
setTimeout(() => {
    console.log(`\n${passed} ok, ${failed} failed`);
    process.exit(failed ? 1 : 0);
}, 400);

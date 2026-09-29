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
                      'pane-summary', 'pane-growth', 'pane-activity', 'pane-cohorts',
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

test('LTV при выбранном баре не рисует сравнение баров', () => {
    const { sandbox, byId } = loadGuests({
        views: ['static/js/guests/views-ltv.js'], gh: makeGh('ligovskiy'), init: true,
        respond: () => ({ meta: metaOf('ligovskiy', 'Лиговский'), data: {
            lifetime: { guests: 10, revenue: 50000, avg_ltv: 5000 },
            ytd: { guests: 5, revenue: 10000, avg_revenue_per_guest: 2000 },
            by_venue: [] } }),
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

/**
 * ЗАПУСК страницы «Анализ проливов» (/draft) в Node с минимальным DOM-стабом.
 *
 *     node tests/test_draft_runtime.mjs
 *
 * Зачем отдельно от test_draft_render.mjs: тот проверяет ТЕКСТ файлов (узел
 * объявлен, класс описан в CSS). Ошибку времени выполнения так не поймать —
 * а именно она страшнее всего: страница молча остаётся пустой.
 *
 * Здесь настоящий draft.js исполняется на настоящем ответе API
 * (tests/fixtures/draft_kegs_sample.json — снят с боевого iiko за неделю
 * 03-09.08.2026) и проверяется, что в узлы легла ожидаемая разметка: сводка,
 * таблицы с итогами, баланс, расхождения, карточки кега и бармена.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const js = read('static/js/draft/draft.js');
const RESPONSE = JSON.parse(read('tests/fixtures/draft_kegs_sample.json'));
const BLOCK = RESPONSE[Object.keys(RESPONSE)[0]];

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
function makeEl(id) {
    return {
        id: id || '',
        dataset: {},
        style: {},
        value: '',
        textContent: '',
        innerHTML: '',
        hidden: false,
        disabled: false,
        scrollTop: 0,
        classList: {
            _s: new Set(),
            add(c) { this._s.add(c); },
            remove(c) { this._s.delete(c); },
            toggle(c, on) { if (on) this._s.add(c); else this._s.delete(c); },
            contains(c) { return this._s.has(c); }
        },
        listeners: {},
        addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
        querySelector() { return null; },
        querySelectorAll() { return []; },
        closest() { return null; },
        click() { (this.listeners.click || []).forEach((fn) => fn({ target: this })); }
    };
}

const IDS = ['drBurger', 'drBarBtn', 'drBarMenu', 'drBarLabel', 'drPerBtn', 'drPerMenu',
             'drPerLabel', 'drPerHint', 'drCatch', 'drRun', 'drRunLabel', 'drSpin',
             'drContext', 'drUpdated', 'drMsg', 'drBody', 'drSum', 'drKegCount',
             'drSearch', 'drKegs', 'drBts', 'drBalance', 'drLosses', 'drDiag',
             'drDrawer', 'drBackdrop', 'drBars'];

function boot() {
    const byId = {};
    IDS.forEach((id) => { byId[id] = makeEl(id); });
    byId.drBars.textContent = JSON.stringify(['Лиговский', 'Варшавская']);

    const fetchCalls = [];
    const sandbox = {
        console, Intl, Math, Number, String, Object, Array, JSON, Date, isNaN, Promise,
        setTimeout, module: undefined,
        document: {
            readyState: 'complete',
            getElementById: (id) => byId[id] || null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            body: makeEl('body')
        },
        location: { hash: '' },
        history: { replaceState: () => {} },
        fetch: (url, opts) => {
            fetchCalls.push({ url, body: JSON.parse(opts.body) });
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve(RESPONSE)
            });
        }
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    new vm.Script(js, { filename: 'draft.js' }).runInContext(sandbox);
    return { sandbox, byId, fetchCalls };
}

const env = boot();
// Запрос уходит промисом, поэтому ждём микрозадачи перед проверками.
await new Promise((resolve) => setTimeout(resolve, 0));

test('скрипт исполняется и сам запрашивает данные при загрузке', () => {
    assert.equal(env.fetchCalls.length, 1, 'страница не сходила за данными');
    assert.equal(env.fetchCalls[0].url, '/api/draft-kegs');
    const body = env.fetchCalls[0].body;
    assert.ok(body.date_from && body.date_to, 'период не передан в запрос');
    assert.equal(body.bar, '', 'по умолчанию должен быть сводный разрез');
});

test('период по умолчанию — прошлая неделя, понедельник-воскресенье', () => {
    const body = env.fetchCalls[0].body;
    const from = new Date(body.date_from);
    const to = new Date(body.date_to);
    assert.equal(from.getDay(), 1, 'период начинается не с понедельника');
    assert.equal(to.getDay(), 0, 'период кончается не воскресеньем');
    assert.equal(Math.round((to - from) / 86400000) + 1, 7, 'в периоде не 7 дней');
});

test('после ответа тело страницы показано, сообщение убрано', () => {
    assert.equal(env.byId.drBody.hidden, false, 'тело страницы осталось скрытым');
    assert.equal(env.byId.drMsg.hidden, true, 'сообщение о загрузке не убрано');
    assert.match(env.byId.drContext.textContent, /разрез: Общая/, 'нет строки разреза');
    assert.match(env.byId.drUpdated.textContent, /обновлено \d\d:\d\d/, 'нет времени расчёта');
});

test('сводка: семь плиток с числами из ответа', () => {
    const html = env.byId.drSum.innerHTML;
    const tiles = (html.match(/class="dr-tile"/g) || []).length;
    assert.equal(tiles, 7, `плиток должно быть 7, найдено ${tiles}`);
    for (const cap of ['ПРОДАНО', 'ВЫРУЧКА', 'ВСЕГО ПОРЦИЙ', 'ЦЕНА ЗА ЛИТР',
                       'ОБЪЁМ ПОРЦИИ', 'НАЦЕНКА', 'БАРМЕНОВ']) {
        assert.ok(html.includes(cap), `нет плитки ${cap}`);
    }
    assert.match(html, /770,01/, 'литры из ответа не выведены');
    assert.match(html, />8</, 'число барменов не выведено');
});

test('таблица кегов: все позиции, итог и сортировка по литрам', () => {
    const html = env.byId.drKegs.innerHTML;
    const rows = (html.match(/class="dr-row is-body"/g) || []).length;
    assert.equal(rows, BLOCK.kegs.length, `строк ${rows}, кегов ${BLOCK.kegs.length}`);
    assert.match(html, /Итого · 33 кега/, 'нет строки итога');
    assert.match(html, /ЛИТРЫ ↓/, 'не показано направление сортировки');
    // Первая строка — самый объёмный кег.
    const first = html.indexOf(BLOCK.kegs[0].KegName);
    const second = html.indexOf(BLOCK.kegs[1].KegName);
    assert.ok(first > 0 && first < second, 'порядок строк не по убыванию литров');
});

test('таблица барменов: люди, итог и «—» вместо суммы кегов', () => {
    const html = env.byId.drBts.innerHTML;
    const rows = (html.match(/class="dr-row is-body"/g) || []).length;
    assert.equal(rows, BLOCK.bartenders.length);
    assert.match(html, /Итого · 8 барменов/, 'нет строки итога');
    assert.match(html, /770,01/, 'итог по литрам не совпал с разрезом по кегам');
    assert.match(html, /class="dr-total-v dash">—/, 'кеги в итоге должны быть прочерком');
});

test('баланс: строки со знаками и итог изменения остатка', () => {
    const html = env.byId.drBalance.innerHTML;
    for (const label of ['Приход по накладным', 'Перемещения · приход',
                         'Перемещения · расход', 'Продано через кассу',
                         'Списано актами', 'Недостача по инвентаризациям',
                         'Изменение остатка кегов']) {
        assert.ok(html.includes(label), `нет строки баланса: ${label}`);
    }
    assert.match(html, /\+620,00/, 'приход без знака или без копеек');
    assert.match(html, /−770,01/, 'продажа не показана расходом');
    assert.match(html, /от продаж/, 'нет доли потерь от продаж');
});

test('расхождения: восемь строк и раскрывашка на остальные', () => {
    const html = env.byId.drLosses.innerHTML;
    const visible = (html.match(/class="dr-loss-row"/g) || []).length;
    const total = BLOCK.losses.by_keg.length;
    assert.equal(visible, total, 'строки под <details> тоже должны быть в разметке');
    assert.match(html, /<details class="dr-more">/, 'нет раскрывашки «ещё N кегов»');
    assert.match(html, /ещё \d+ кег/, 'не подписано, сколько кегов скрыто');
    assert.ok(total > 8, 'фикстура должна иметь больше 8 кегов с расхождениями');
});

test('поиск по кегам фильтрует таблицу и счётчик', () => {
    env.byId.drSearch.value = 'хеллес';
    env.byId.drSearch.listeners.input[0]({});
    const html = env.byId.drKegs.innerHTML;
    const rows = (html.match(/class="dr-row is-body"/g) || []).length;
    assert.ok(rows > 0 && rows < BLOCK.kegs.length, `фильтр не сработал: ${rows} строк`);
    assert.match(env.byId.drKegCount.textContent, /из 33/, 'счётчик не показал отбор');

    env.byId.drSearch.value = 'нетакогокега';
    env.byId.drSearch.listeners.input[0]({});
    assert.match(env.byId.drKegs.innerHTML, /ничего не найдено/, 'нет пустого состояния');

    env.byId.drSearch.value = '';
    env.byId.drSearch.listeners.input[0]({});
});

test('карточка кега: продажи, деньги, кто наливал, потери, ABC и XYZ', () => {
    const keg = BLOCK.kegs[0];
    env.sandbox.window.__draft.openKeg(keg.KegId);
    const html = env.byId.drDrawer.innerHTML;
    assert.equal(env.byId.drDrawer.hidden, false, 'карточка не открылась');
    assert.equal(env.byId.drBackdrop.hidden, false, 'нет затемнения под карточкой');
    for (const section of ['ПРОДАЖИ', 'ДЕНЬГИ', 'КТО НАЛИВАЛ', 'ПОТЕРИ',
                           'ABC-АНАЛИЗ', 'XYZ']) {
        assert.ok(html.includes(section), `нет секции ${section}`);
    }
    assert.ok(html.includes(keg.KegName), 'нет названия кега');
    const people = (html.match(/class="dr-who-row" data-bt=/g) || []).length;
    assert.equal(people, keg.Bartenders.length, 'разбивка «кто наливал» не совпала');
    assert.match(html, /накопленным итогом/, 'накопленная доля не подписана отдельно');
});

test('карточка бармена: налив, деньги и что наливал', () => {
    const person = BLOCK.bartenders[0];
    env.sandbox.window.__draft.openBartender(person.Bartender);
    const html = env.byId.drDrawer.innerHTML;
    for (const section of ['НАЛИВ', 'ДЕНЬГИ', 'ЧТО НАЛИВАЛ']) {
        assert.ok(html.includes(section), `нет секции ${section}`);
    }
    assert.ok(html.includes(person.Bartender), 'нет имени бармена');
    assert.match(html, /поле «Авторизовал» в iiko/, 'нет оговорки об источнике имени');
    const kegs = (html.match(/class="dr-who-row" data-keg=/g) || []).length;
    assert.equal(kegs, person.kegs.length, 'разбивка «что наливал» не совпала');
});

test('опасные символы в данных экранируются', () => {
    const evil = JSON.parse(JSON.stringify(BLOCK));
    evil.kegs[0].KegName = 'КЕГ It\'s <b>Mango</b> "20"';
    evil.bartenders[0].Bartender = 'Д\'Артаньян <script>';
    env.sandbox.window.__draft.state.data = evil;
    env.sandbox.window.__draft.render();
    const html = env.byId.drKegs.innerHTML + env.byId.drBts.innerHTML;
    assert.ok(!html.includes('<b>Mango</b>'), 'сырой HTML из названия попал в разметку');
    assert.ok(!html.includes('<script>'), 'сырой HTML из имени попал в разметку');
    assert.match(html, /It&#39;s/, 'апостроф не экранирован');
});

test('форматирование чисел совпадает с макетом', () => {
    const f = env.sandbox.window.__draft;
    // Разделитель тысяч у Intl — неразрывный пробел, в сравнении он мешает.
    const plain = (s) => s.replace(/[  ]/g, ' ');
    assert.equal(f.num(86.7), '86,7', 'хвостовой ноль в литрах');
    assert.equal(f.num(8), '8');
    assert.equal(f.fixed(620, 2), '620,00');
    assert.equal(f.fixed(-11.5, 2), '−11,50', 'минус должен быть типографским');
    assert.equal(f.pct(10, 1), '10,0%');
    assert.equal(f.pct(252, 0), '252%');
    assert.equal(plain(f.money(226986.4)), '226 986 ₽');
    assert.equal(f.signed(770.01, '−'), '−770,01');
    assert.equal(f.plural(1, 'кег', 'кега', 'кегов'), 'кег');
    assert.equal(f.plural(3, 'кег', 'кега', 'кегов'), 'кега');
    assert.equal(f.plural(11, 'кег', 'кега', 'кегов'), 'кегов');
    assert.equal(f.initials('Станислав Колганов'), 'СК');
});

test('шкала потерь: у излишка полосы нет, цвет плашки по величине', () => {
    const f = env.sandbox.window.__draft;
    assert.equal(f.lossTone(4), 'calm');
    assert.equal(f.lossTone(12), 'warn');
    assert.equal(f.lossTone(40), 'bad');
    assert.equal(f.lossTone(null), 'calm', 'кег без продаж не должен краснеть');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

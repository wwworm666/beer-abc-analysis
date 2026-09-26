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
             'drContext', 'drXyzChip', 'drUpdated', 'drMsg', 'drBody', 'drSum', 'drBuckets',
             'drCatCount', 'drCats', 'drKegCount',
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

test('период по умолчанию — последние 30 дней, на них считается спрос', () => {
    // До 2026-09-26 страница открывалась на прошлой неделе, где третья буква
    // кода (спрос, XYZ) не считается ни у одного кега. Теперь как на /packaging.
    const body = env.fetchCalls[0].body;
    const dapi = env.sandbox.window.__draft;
    const days = Math.round((new Date(body.date_to) - new Date(body.date_from)) / 86400000) + 1;
    assert.equal(days, 30, `в периоде по умолчанию ${days} дней`);
    assert.ok(dapi.weeksIn(body.date_from, body.date_to) >= 3, 'на периоде по умолчанию нет XYZ');
    assert.equal(dapi.state.preset, 'd30');
});

test('меню периодов: короткие пресеты подписаны «без XYZ»', () => {
    env.byId.drPerMenu.hidden = true;          // в стабе узлы по умолчанию видимы
    env.byId.drPerBtn.listeners.click[0]({});
    assert.equal(env.byId.drPerMenu.hidden, false, 'меню периодов не открылось');
    const html = env.byId.drPerMenu.innerHTML;
    const items = [...html.matchAll(/data-preset="([^"]+)"><span>[^<]*<\/span><span>([^<]*)<\/span>/g)];
    assert.ok(items.length >= 8, `пресетов в меню ${items.length}`);
    assert.equal(items[0][1], 'd30', 'первым в меню стоит не «Последние 30 дней»');
    const short = items.filter((m) => ['week', 'prev_week', 'yesterday', 'today'].includes(m[1]));
    assert.ok(short.every((m) => m[2] === 'без XYZ'), 'неделя и дни не помечены «без XYZ»');
    const long = items.filter((m) => ['d30', 'd90', 'prev_month'].includes(m[1]));
    assert.ok(long.every((m) => m[2] !== 'без XYZ'), 'длинный период помечен «без XYZ»');
    env.byId.drCatch.listeners.click[0]({});
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
    const revAt = html.indexOf('ДОЛЯ В ВЫРУЧКЕ');
    const litAt = html.indexOf('ДОЛЯ В ЛИТРАХ');
    assert.ok(revAt >= 0 && litAt > revAt, 'доли кега стоят не в порядке выручка, затем литры');
    assert.ok(!html.includes('ДОЛЯ ПО Л'), 'старая колонка «доля по л» ещё в таблице кегов');
    assert.ok(html.includes(env.sandbox.window.__draft.pct(BLOCK.kegs[0].LitersSharePercent, 1)),
        'доля кега по литрам не выведена');
    assert.ok(html.includes(env.sandbox.window.__draft.pct(BLOCK.kegs[0].RevenueSharePercent, 1)),
        'доля кега в выручке не выведена');
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
    // Серые строки (кеги без продаж) — тоже строки расхождений.
    const visible = (html.match(/class="dr-loss-row( is-static)?"/g) || []).length;
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

test('карточка кега: три буквы кода — выручка, наценка, спрос; маржа отдельно', () => {
    const dapi = env.sandbox.window.__draft;
    const keg = BLOCK.kegs[0];
    dapi.openKeg(keg.KegId);
    const html = env.byId.drDrawer.innerHTML;
    const box = html.slice(html.indexOf('ABC-АНАЛИЗ'), html.indexOf('ВТОРАЯ ШКАЛА'));
    const lines = [...box.matchAll(/class="dr-abc-cat">([^<]*)</g)].map((m) => m[1]);
    assert.deepEqual(lines, ['Выручка', 'Наценка', 'Спрос'], `строки разбора кода: ${lines}`);
    assert.ok(box.includes('>' + dapi.esc(keg.ABC_Combined) + '<'), 'нет самого кода');
    assert.equal(keg.ABC_Combined.charAt(2), keg.XYZ_Category || '?', 'третья буква кода не спрос');
    // Фикстура — неделя: буквы спроса нет, строка объясняет почему, а не молчит.
    assert.ok(/не считается: в периоде 1 полная неделя, нужно от 3/.test(box),
        'не объяснено, почему у спроса «?»');
    const second = html.slice(html.indexOf('ВТОРАЯ ШКАЛА'));
    assert.ok(/class="dr-abc-cat">Маржа</.test(second), 'буква маржи пропала из карточки');
    assert.ok(second.includes(dapi.money(keg.TotalMargin)), 'нет маржи в рублях');
    assert.match(second, /Маржа в код не входит/, 'не сказано, что маржа вне кода');
});

test('карточка кега: спрос с буквой печатает коэффициент вариации', () => {
    const dapi = env.sandbox.window.__draft;
    const keg = JSON.parse(JSON.stringify(BLOCK.kegs[0]));
    keg.XYZ_Category = 'Y';
    keg.CoefficientOfVariation = 42.5;
    keg.WeeksInPeriod = 4;
    keg.WeeksWithSales = 4;
    keg.ABC_Combined = keg.ABC_Combined.slice(0, 2) + 'Y';
    const data = JSON.parse(JSON.stringify(BLOCK));
    data.kegs[0] = keg;
    dapi.state.data = data;
    dapi.openKeg(keg.KegId);
    const html = env.byId.drDrawer.innerHTML;
    assert.ok(html.includes('умеренный разброс: от 30% до 60% (42,5%)'), 'спрос Y не расшифрован');
    assert.ok(html.includes('dr-abc-ltr y">Y<'), 'у буквы спроса нет цвета');
    dapi.state.data = BLOCK;
    dapi.render();
});

test('таблица кегов: колонки XYZ нет, ячеек в строке столько же, сколько колонок', () => {
    const html = env.byId.drKegs.innerHTML;
    const head = html.match(/class="dr-row is-head"[\s\S]*?<\/div>/)[0];
    assert.ok(!/>XYZ</.test(head), 'в шапке осталась колонка XYZ');
    const css = read('static/draft/draft.css');
    const grid = css.match(/\.dr-kegs \.dr-row \{[^}]*grid-template-columns:([^;]+);/)[1];
    const columns = grid.trim().replace(/\([^)]*\)/g, '()').split(/\s+/).length;
    const parts = html.split(/<div class="dr-row/).slice(1);
    const counts = parts.map((part) => {
        const body = part.split(/<\/div>/)[0];
        return (body.match(/<span/g) || []).length -
               (body.match(/<span class="dr-bar/g) || []).length * 2 -
               (body.match(/<span class="dr-abc /g) || []).length;
    });
    const wrong = counts.filter((n) => n !== columns);
    assert.deepEqual(wrong, [], `колонок ${columns}, строки с ${[...new Set(wrong)].join(', ')} ячейками`);
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

test('решения по ассортименту: шесть групп с сервера, каждый кег в одной', () => {
    const html = env.byId.drBuckets.innerHTML;
    const dapi = env.sandbox.window.__draft;
    const cards = (html.match(/class="dr-bucket"/g) || []).length;
    assert.equal(cards, 6, `групп должно быть 6, найдено ${cards}`);
    for (const card of BLOCK.buckets) {
        assert.ok(html.includes(dapi.esc(card.name)), `нет группы «${card.name}»`);
    }
    assert.equal(BLOCK.buckets.reduce((a, c) => a + c.count, 0), BLOCK.kegs.length,
        'группы не покрывают все кеги');
    assert.ok(BLOCK.kegs.every((k) => k.ABC_Bucket), 'есть кег без группы');
    assert.match(html, /кег(а|ов)?<\/u>/, 'счётчик не в кегах');
    // Неделя: «вывести» не выносится, карточка честно говорит «смотреть за 4 недели».
    const weak = BLOCK.buckets.find((c) => c.key === 'weak');
    assert.equal(weak.verdict_ready, false, 'на неделе решение о выводе не должно выноситься');
    assert.ok(html.includes('Смотреть за 4 недели'), 'нет отложенного действия');
    assert.ok(!html.includes('Вывести из ассортимента'), 'на неделе показано «вывести»');
});

test('карточка группы: правило в порциях, подсказка и кеги', () => {
    const dapi = env.sandbox.window.__draft;
    dapi.openBucket('low_markup');
    const html = env.byId.drDrawer.innerHTML;
    const card = BLOCK.buckets.find((c) => c.key === 'low_markup');
    assert.ok(html.includes(dapi.esc(card.name)) && html.includes(dapi.esc(card.action)),
        'нет названия или действия группы');
    assert.ok(html.includes('Правило: ' + dapi.esc(card.rule)), 'правило не напечатано');
    assert.ok(/порций/.test(card.rule) && /250%/.test(card.rule),
        'правило кегов не в порциях или без минимума 250%');
    assert.ok(html.includes(dapi.esc(card.hint)), 'нет подсказки');
    const rows = (html.match(/class="dr-who-row" data-keg=/g) || []).length;
    assert.equal(rows, card.count, `строк ${rows}, кегов в группе ${card.count}`);
    assert.ok(card.count > 0, 'в фикстуре нет кегов с низкой наценкой');
});

test('карточка кега повторяет решение по ассортименту и не выдумывает букву наценки', () => {
    const dapi = env.sandbox.window.__draft;
    const keg = BLOCK.kegs[0];
    dapi.openKeg(keg.KegId);
    const html = env.byId.drDrawer.innerHTML;
    const card = BLOCK.buckets.find((c) => c.key === keg.ABC_Bucket);
    assert.ok(html.includes('Решение по ассортименту: ' + dapi.esc(card.name)),
        'в карточке кега нет решения');
    assert.ok(/наценка 250% и выше|от 200% до 250%|ниже 200%/.test(html),
        'буква наценки не объяснена порогами');
    assert.ok(!/треть по наценке/.test(html), 'наценка всё ещё объяснена третями');
});

test('категории: таблица со всеми стилями, итог и доли', () => {
    const html = env.byId.drCats.innerHTML;
    const dapi = env.sandbox.window.__draft;
    const rows = (html.match(/class="dr-row is-body"/g) || []).length;
    assert.equal(rows, BLOCK.categories.length, `строк ${rows}, категорий ${BLOCK.categories.length}`);
    assert.ok(BLOCK.categories.length > 1, 'в фикстуре одна категория — таблица не проверяется');
    assert.ok(html.includes(dapi.esc(BLOCK.categories[0].Category)), 'нет первой категории');
    assert.match(html, /Итого · \d+ категор/, 'нет строки итога');
    assert.match(env.byId.drCatCount.textContent, /категор/, 'нет счётчика категорий');
    // Каждый кег ровно в одной категории, суммы сходятся с разрезом.
    assert.equal(BLOCK.categories.reduce((a, c) => a + c.KegsCount, 0), BLOCK.kegs.length,
        'категории не покрывают все кеги');
    const liters = BLOCK.categories.reduce((a, c) => a + c.TotalLiters, 0);
    assert.ok(Math.abs(liters - BLOCK.total_liters) < 1e-6, 'литры категорий не равны литрам разреза');
    assert.ok(Math.abs(BLOCK.categories.reduce((a, c) => a + c.RevenueSharePercent, 0) - 100) < 1e-6,
        'доли категорий не складываются в 100%');
    assert.ok(Math.abs(BLOCK.categories.reduce((a, c) => a + c.LitersSharePercent, 0) - 100) < 1e-6,
        'доли по литрам не складываются в 100%');
    const revAt = html.indexOf('ДОЛЯ В ВЫРУЧКЕ');
    const litAt = html.indexOf('ДОЛЯ В ЛИТРАХ');
    assert.ok(revAt >= 0 && litAt > revAt, 'колонка «доля в литрах» стоит не после доли в выручке');
    const shown = BLOCK.categories[0];
    assert.ok(html.includes(dapi.pct(shown.LitersSharePercent, 1)),
        'доля категории по литрам не выведена');
    const total = html.match(/class="dr-row is-total"[\s\S]*?<\/div>/);
    assert.equal((total[0].match(/100,0%/g) || []).length, 2,
        'в итоге должны быть две стопроцентные доли');
    for (const key of ['Category', 'KegsCount', 'TotalLiters', 'TotalRevenue',
                       'RevenueSharePercent', 'LitersSharePercent', 'TotalMargin',
                       'MarkupPercent', 'ABC_Category']) {
        assert.ok(html.includes(`data-sort="${key}"`), `нет сортировки столбца ${key}`);
    }
});

function catNames() {
    return [...env.byId.drCats.innerHTML.matchAll(/class="dr-name">([^<]*)</g)].map((m) => m[1]);
}

function clickCatSort(key) {
    const head = {
        dataset: { sort: key },
        closest: (sel) => (sel === '.dr-cats' ? head : null)
    };
    const handlers = env.byId.drCats.listeners.click || [];
    assert.ok(handlers.length, 'на таблице категорий нет обработчика');
    handlers.forEach((fn) => fn({
        target: { closest: (sel) => (sel === '.dr-th.s' ? head : null) }
    }));
}

test('категории: сортировка кликом, пустая наценка уходит вниз', () => {
    const dapi = env.sandbox.window.__draft;
    const withoutMarkup = BLOCK.categories.filter((c) => c.MarkupPercent === null).length;
    dapi.state.catSort = { key: 'MarkupPercent', dir: 1 };
    env.sandbox.window.__draft.render();
    const names = [...env.byId.drCats.innerHTML.matchAll(/class="dr-name">([^<]*)</g)].map((m) => m[1]);
    if (withoutMarkup) {
        const tail = names.slice(-withoutMarkup);
        const expected = BLOCK.categories.filter((c) => c.MarkupPercent === null)
            .map((c) => dapi.esc(c.Category));
        assert.deepEqual(tail.slice().sort(), expected.slice().sort(),
            'категории без наценки не в конце при сортировке по возрастанию');
    }
    dapi.state.catSort = { key: 'TotalRevenue', dir: -1 };
    dapi.render();
});

test('категории: клик сортирует название, доли и букву ABC', () => {
    const dapi = env.sandbox.window.__draft;
    const byLiters = BLOCK.categories.slice()
        .sort((a, b) => b.LitersSharePercent - a.LitersSharePercent);
    clickCatSort('LitersSharePercent');
    assert.equal(catNames()[0], dapi.esc(byLiters[0].Category),
        'первая строка не лидер по литрам');
    assert.match(env.byId.drCats.innerHTML, /ДОЛЯ В ЛИТРАХ ↓/);

    const byName = BLOCK.categories.map((c) => dapi.esc(c.Category))
        .sort((a, b) => b.localeCompare(a, 'ru'));
    clickCatSort('Category');
    assert.deepEqual(catNames(), byName, 'убывание по названию не совпало');
    clickCatSort('Category');
    assert.deepEqual(catNames(), byName.slice().reverse(), 'возрастание по названию не совпало');
    assert.match(env.byId.drCats.innerHTML, /КАТЕГОРИЯ ↑/);

    const byAbc = BLOCK.categories.slice()
        .sort((a, b) => b.ABC_Category.localeCompare(a.ABC_Category, 'ru'));
    clickCatSort('ABC_Category');
    assert.equal(catNames()[0], dapi.esc(byAbc[0].Category), 'первая строка не с буквой C');
    assert.match(env.byId.drCats.innerHTML, /ABC ↓/);

    dapi.state.catSort = { key: 'TotalRevenue', dir: -1 };
    dapi.render();
});

test('карточка категории: итоги, ABC и состав', () => {
    const dapi = env.sandbox.window.__draft;
    const cat = BLOCK.categories[0];
    dapi.openCategory(cat.Category);
    const html = env.byId.drDrawer.innerHTML;
    assert.equal(env.byId.drDrawer.hidden, false, 'карточка категории не открылась');
    assert.ok(html.includes(dapi.esc(cat.Category)), 'нет названия категории');
    for (const band of ['ИТОГИ КАТЕГОРИИ', 'ABC КАТЕГОРИИ', 'КЕГИ КАТЕГОРИИ']) {
        assert.ok(html.includes(band), `нет секции ${band}`);
    }
    const rows = (html.match(/class="dr-who-row" data-keg=/g) || []).length;
    assert.equal(rows, cat.KegsCount, `кегов в карточке ${rows}, в категории ${cat.KegsCount}`);
    assert.ok(html.includes(dapi.pct(cat.CumulativePercent, 1)), 'нет накопленного итога');
});

test('клик по строке категории открывает её карточку', () => {
    const dapi = env.sandbox.window.__draft;
    const cat = BLOCK.categories[1] || BLOCK.categories[0];
    const handlers = env.byId.drCats.listeners.click || [];
    assert.ok(handlers.length, 'на таблице категорий нет обработчика');
    env.byId.drDrawer.hidden = true;
    handlers.forEach((fn) => fn({ target: { closest: (sel) =>
        sel === '.dr-th.s' ? null
            : (sel.includes('data-cat') ? { dataset: { cat: cat.Category } } : null) } }));
    assert.equal(env.byId.drDrawer.hidden, false, 'карточка не открылась по клику');
    assert.ok(env.byId.drDrawer.innerHTML.includes(dapi.esc(cat.Category)), 'открылась не та категория');
});

test('карточка кега: разрез по барам, вторая шкала и недельные столбики', () => {
    const dapi = env.sandbox.window.__draft;
    const keg = BLOCK.kegs.find((k) => (k.ByBar || []).length > 1);
    assert.ok(keg, 'в фикстуре нет кега с двумя барами');
    dapi.openKeg(keg.KegId);
    const html = env.byId.drDrawer.innerHTML;
    assert.ok(html.includes('ПО БАРАМ'), 'нет секции «по барам»');
    for (const bar of keg.ByBar) {
        assert.ok(html.includes(dapi.esc(bar.Bar)), `нет бара ${bar.Bar}`);
    }
    // Строки баров не кликабельны: карточки бара на странице нет.
    assert.ok(html.includes('dr-who-row is-static'), 'строки баров кликабельны');
    assert.ok(html.includes('ВТОРАЯ ШКАЛА'), 'нет второй шкалы');
    assert.ok(html.includes(dapi.esc(keg.Category)), 'в карточке не названа категория кега');
    assert.ok(html.includes(dapi.money(keg.RevenueBaseInCategory)), 'нет базы доли в категории');
    // Ряд рисуется от двух недель: один столбик на весь период ничего не значит.
    const weeks = (keg.WeeklyLiters || []).length;
    const bars = (html.match(/class="dr-week-bar/g) || []).length;
    assert.equal(bars, weeks > 1 ? weeks : 0,
        `столбиков ${bars} при ${weeks} неделях в периоде`);
});

test('разрез по барам: в «Общей» есть даже у кега из одного бара, в разрезе бара нет', () => {
    const dapi = env.sandbox.window.__draft;
    const keg = BLOCK.kegs.find((k) => (k.ByBar || []).length === 1);
    assert.ok(keg, 'в фикстуре нет кега из одного бара');
    // «Общая»: вопрос «в каком баре стоит этот кег» — главный, секция нужна.
    dapi.state.bar = '';
    dapi.openKeg(keg.KegId);
    assert.ok(env.byId.drDrawer.innerHTML.includes('ПО БАРАМ'),
        'в сводном разрезе не видно, в каком баре кег');
    assert.ok(env.byId.drDrawer.innerHTML.includes(dapi.esc(keg.ByBar[0].Bar)), 'нет имени бара');
    // Разрез одного бара: строка повторяла бы таблицу выше.
    dapi.state.bar = keg.ByBar[0].Bar;
    dapi.openKeg(keg.KegId);
    assert.ok(!env.byId.drDrawer.innerHTML.includes('ПО БАРАМ'),
        'разрез по барам показан в разрезе одного бара');
    dapi.state.bar = '';
});

test('плашка «XYZ не считается» на коротком периоде', () => {
    // Фикстура — неделя: третьей буквы нет ни у одного кега.
    assert.equal(BLOCK.xyz_available, false, 'фикстура не проверяет плашку');
    assert.equal(env.byId.drXyzChip.hidden, false, 'плашка скрыта, хотя XYZ не считается');
    assert.match(env.byId.drXyzChip.textContent, /XYZ не считается/, 'плашка без текста');
    assert.match(env.byId.drXyzChip.textContent, /нужно от 3/, 'в плашке нет порога');
    assert.ok(env.byId.drXyzChip.textContent.includes(' ' + BLOCK.xyz_buckets + ' полн'),
        'число полных недель в плашке не из xyz_buckets');
});

test('плашка считает полные недели целым, а не дробью дней на семь', () => {
    // period.weeks — это дни/7: на трёхдневном периоде из него выходило
    // «в периоде 0.42857142857142855 полных недель».
    const dapi = env.sandbox.window.__draft;
    const data = JSON.parse(JSON.stringify(BLOCK));
    data.period = Object.assign({}, data.period, { days: 3, weeks: 3 / 7 });
    data.xyz_buckets = 0;
    data.xyz_available = false;
    dapi.state.data = data;
    dapi.render();
    const text = env.byId.drXyzChip.textContent;
    assert.ok(!/\d\.\d/.test(text), `в плашке дробное число недель: ${text}`);
    assert.ok(text.includes('в периоде 0 полных недель'), `плашка говорит «${text}»`);
    dapi.state.data = BLOCK;
    dapi.render();
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

test('баланс: излишек отдельной строкой, приход в подписи — вместе с перемещениями', () => {
    // До 2026-09-26 излишек печатался как «Недостача −25», а в «приход» подписи
    // не входили перемещения: строки баланса не складывались в итог.
    const dapi = env.sandbox.window.__draft;
    const data = JSON.parse(JSON.stringify(BLOCK));
    const L = data.losses;
    L.transfer_in = 50;
    L.inventory_out = 0;
    L.inventory_in = 25;
    L.inventory_net = -25;
    L.inventory_percent_of_sold = -25 / L.sold * 100;
    L.received = L.invoice_in + L.transfer_in;
    L.spent = L.sold + L.writeoff + L.inventory_net + L.transfer_out;
    L.balance = L.received - L.spent;
    dapi.state.data = data;
    dapi.render();
    const html = env.byId.drBalance.innerHTML;
    assert.ok(html.includes('Излишек по инвентаризациям'), 'нет строки излишка');
    assert.ok(!html.includes('Недостача по инвентаризациям'), 'излишек подписан недостачей');
    assert.ok(html.includes('+25,00'), 'излишек не со знаком плюс');
    assert.ok(html.includes('приход ' + dapi.fixed(L.received, 2) + ' − расход ' +
        dapi.fixed(L.spent, 2)), 'подпись «приход − расход» не с сервера');
    assert.ok(html.includes('− излишек 25,00'), 'в расшифровке расхода нет излишка');
    // Проверка арифметики подписи: приход − расход = итог.
    assert.ok(Math.abs(L.received - L.spent - L.balance) < 1e-9);
    dapi.state.data = BLOCK;
    dapi.render();
});

test('баланс на фикстуре: подпись сходится с итогом', () => {
    const html = env.byId.drBalance.innerHTML;
    const dapi = env.sandbox.window.__draft;
    const L = BLOCK.losses;
    assert.ok(typeof L.received === 'number' && typeof L.spent === 'number',
        'в ответе нет received/spent — подпись опять складывала бы страница');
    assert.ok(Math.abs(L.received - L.spent - L.balance) < 1e-9, 'сервер: приход − расход ≠ итог');
    assert.ok(html.includes('приход ' + dapi.fixed(L.received, 2)), 'приход в подписи не с сервера');
});

test('расхождения: кеги без продаж серые и не кликаются', () => {
    const html = env.byId.drLosses.innerHTML;
    const ids = new Set(BLOCK.kegs.map((k) => k.KegId));
    const outside = BLOCK.losses.by_keg.filter((r) => !ids.has(r.KegId)).length;
    assert.ok(outside > 0, 'в фикстуре нет кегов с расхождениями вне таблицы');
    assert.equal((html.match(/class="dr-loss-row is-static"/g) || []).length, outside,
        'кеги вне таблицы не помечены');
    assert.equal((html.match(/class="dr-loss-row" data-keg=/g) || []).length,
        BLOCK.losses.by_keg.length - outside, 'кликабельных строк не столько, сколько кегов в таблице');
    assert.match(html, /излишек одного бара не гасит недостачу/,
        'не объяснено, почему шапка больше баланса');
});

test('наценка округляется вниз и не спорит с буквой', () => {
    // 249,6% — это буква B и «Низкая наценка»; печатать «250%» нельзя.
    const f = env.sandbox.window.__draft;
    assert.equal(f.markupPct(249.6, 0), '249%');
    assert.equal(f.markupPct(250, 0), '250%');
    assert.equal(f.markupPct(199.96, 1), '199,9%');
    assert.equal(f.markupPct(373.49, 1), '373,4%');
    assert.equal(f.markupPct(null, 0), '—');
    const dapi = env.sandbox.window.__draft;
    const data = JSON.parse(JSON.stringify(BLOCK));
    data.kegs[0].MarkupPercent = 249.6;
    dapi.state.data = data;
    dapi.render();
    assert.ok(env.byId.drKegs.innerHTML.includes('>249%<'), 'в таблице наценка округлена вверх');
    assert.ok(!env.byId.drKegs.innerHTML.includes('>250%<'));
    dapi.state.data = BLOCK;
    dapi.render();
});

test('скользящие пресеты заканчиваются вчера, «сегодня» и текущие — сегодня', () => {
    const f = env.sandbox.window.__draft;
    const iso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
        '-' + String(d.getDate()).padStart(2, '0');
    const today = new Date();
    const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
    for (const [key, days] of [['d30', 30], ['d90', 90]]) {
        const range = f.presetRange(key);
        assert.equal(range.to, iso(yesterday), `${key} кончается не вчера`);
        const span = Math.round((new Date(range.to) - new Date(range.from)) / 86400000) + 1;
        assert.equal(span, days, `${key}: ${span} дней`);
    }
    assert.equal(f.presetRange('today').to, iso(today));
    assert.equal(f.presetRange('week').to, iso(today));
    assert.equal(f.presetRange('month').to, iso(today));
    assert.equal(env.fetchCalls[0].body.date_to, iso(yesterday), 'по умолчанию уходит не по вчера');
});

test('карточка кега: литры в неделю на кране и формула маржи по Парето', () => {
    const dapi = env.sandbox.window.__draft;
    const keg = BLOCK.kegs[0];
    dapi.openKeg(keg.KegId);
    const html = env.byId.drDrawer.innerHTML;
    assert.ok(html.includes('Л В НЕДЕЛЮ НА КРАНЕ'), 'нет литров в неделю на кране');
    assert.ok(html.includes('>' + dapi.num(keg.AvgLitersPerActiveWeek) + '<'), 'не то число');
    assert.ok(!html.includes('>ЛИТРОВ В НЕДЕЛЮ<'), 'осталось среднее за весь период');
    assert.ok(html.includes(dapi.money(keg.TotalMargin) + ' / ' + dapi.money(BLOCK.margin_abc_base) +
        ' = ' + dapi.pct(keg.MarginSharePercent, 1)), 'нет формулы доли маржи');
    assert.ok(/первые 80% накопленной маржи|следующие 15% маржи|последние 5% маржи/.test(html),
        'буква маржи объяснена не Парето');
    assert.ok(!/треть/.test(html), 'в карточке осталась маржа по третям');
});

test('расхождения в «Общей»: недостача одного бара не гасится излишком другого', () => {
    const dapi = env.sandbox.window.__draft;
    const data = JSON.parse(JSON.stringify(BLOCK));
    const row = data.losses.by_keg[0];
    row.InventoryNetLiters = 0;
    row.InventoryShortLiters = 10;
    row.InventorySurplusLiters = 10;
    row.WriteoffLiters = 0;
    row.LossLiters = 10;
    const keg = data.kegs.find((k) => k.KegId === row.KegId);
    keg.InventoryNetLiters = 0;
    keg.InventoryShortLiters = 10;
    keg.InventorySurplusLiters = 10;
    dapi.state.data = data;
    dapi.render();
    const html = env.byId.drLosses.innerHTML;
    assert.ok(html.includes('10,00<i class="dr-loss-plus"> +10,00</i>'),
        'в строке нет недостачи с излишком рядом');
    dapi.openKeg(keg.KegId);
    const card = env.byId.drDrawer.innerHTML;
    assert.ok(card.includes('НЕДОСТАЧА ИНВЕНТ.') && card.includes('Ещё излишек 10,00 л в других барах'),
        'карточка кега не показывает недостачу по барам');
    dapi.state.data = BLOCK;
    dapi.render();
});

test('карточка кега: отрицательная маржа в формуле Парето считается нулём', () => {
    const dapi = env.sandbox.window.__draft;
    const data = JSON.parse(JSON.stringify(BLOCK));
    const keg = data.kegs[data.kegs.length - 1];
    keg.TotalMargin = -1200;
    keg.MarginSharePercent = 0;
    dapi.state.data = data;
    dapi.render();
    dapi.openKeg(keg.KegId);
    const html = env.byId.drDrawer.innerHTML;
    assert.ok(html.includes(' · ' + dapi.money(0) + ' / ' + dapi.money(data.margin_abc_base) + ' = ' +
        dapi.pct(0, 1)), 'в числителе не ноль');
    assert.ok(html.includes('маржа ' + dapi.money(-1200) + ' — в Парето считается нулём'),
        'отрицательная маржа не названа');
    dapi.state.data = BLOCK;
    dapi.render();
});

async function asyncTest(name, fn) {
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
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

await asyncTest('смена бара во время загрузки: старый ответ выброшен, новый запрос ушёл', async () => {
    // До 2026-09-26 run() молча выходил, пока шёл запрос: страница показывала
    // данные «Общей» под подписью выбранного бара.
    const calls = [];
    const pending = [];
    env.sandbox.fetch = (url, opts) => {
        calls.push(JSON.parse(opts.body));
        let resolve;
        const promise = new Promise((r) => { resolve = r; });
        pending.push(resolve);
        return promise;
    };
    const reply = (bar) => ({ ok: true, status: 200,
                              json: () => Promise.resolve({ [bar]: BLOCK }) });
    const pick = (bar) => env.byId.drBarMenu.listeners.click[0](
        { target: { closest: () => ({ dataset: { bar } }) } });
    pick('Лиговский');
    pick('Варшавская');
    assert.equal(calls.length, 1, 'второй запрос ушёл, не дождавшись первого');
    pending[0](reply('Лиговский'));
    for (let i = 0; i < 5; i++) await flush();
    assert.equal(calls.length, 2, 'новый выбор потерян: запрос по нему не ушёл');
    assert.equal(calls[1].bar, 'Варшавская');
    assert.equal(env.byId.drBody.hidden, true, 'устаревший ответ лёг на экран');
    pending[1](reply('Варшавская'));
    for (let i = 0; i < 5; i++) await flush();
    assert.equal(env.byId.drBody.hidden, false, 'ответ по новому выбору не показан');
    assert.match(env.byId.drContext.textContent, /разрез: Варшавская/);
    assert.equal(env.byId.drBarLabel.textContent, 'Варшавская');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

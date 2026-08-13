/**
 * Тесты страницы «Маркетинг» (слияние /discounts в /guests, 2026-08-13):
 *
 *     node tests/test_marketing_render.mjs
 *
 * Браузера в проверке нет, поэтому ловим поломки, которые иначе видны только глазами:
 *   1. вкладка объявлена не во всех трёх местах (кнопка / пейн / подключение скрипта)
 *      — вкладка либо не появится, либо будет пустой навсегда;
 *   2. класс, который JS пишет в разметку, нигде не описан в CSS — элемент есть,
 *      но выглядит сломанным;
 *   3. ключ формулы, которого нет в GUEST_FORMULAS — helpIcon молча вернёт '',
 *      и требование проекта «расчёт виден пользователю» нарушится незаметно;
 *   4. следы удалённой страницы: старый шаблон, мёртвый эндпоинт, ссылки в меню.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(ROOT, p));

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
        console.log(`      ${e.message}`);
    }
}

const html = read('templates/guests.html');
const css = read('static/guests/guests.css');
const nav = read('templates/shared/nav.html');
const formulas = read('static/js/guests/formulas.js');
const common = read('static/js/guests/common.js');
const promo = read('static/js/guests/views-promo.js');
const rfm = read('static/js/guests/views-rfm.js');
const charts = read('static/js/guests/charts.js');

// ---------------------------------------------------------------- вкладки
const TABS = ['summary', 'growth', 'activity', 'cohorts', 'rfm', 'ltv',
              'promo', 'products', 'venues', 'never', 'guest'];

test('каждая вкладка объявлена кнопкой, пейном и подключённым скриптом', () => {
    for (const tab of TABS) {
        assert.ok(html.includes(`data-tab="${tab}"`), `нет кнопки вкладки ${tab}`);
        assert.ok(html.includes(`id="pane-${tab}"`), `нет пейна pane-${tab}`);
        const file = `static/js/guests/views-${tab}.js`;
        assert.ok(exists(file), `нет файла вида ${file}`);
        assert.ok(html.includes(`views-${tab}.js`), `вид ${tab} не подключён в шаблоне`);
    }
});

test('каждый вид регистрируется под тем же именем, что вкладка', () => {
    for (const tab of TABS) {
        const src = read(`static/js/guests/views-${tab}.js`);
        assert.ok(src.includes(`registerView('${tab}'`),
            `views-${tab}.js не регистрирует вид '${tab}'`);
    }
});

test('порядок подключения: formulas -> common -> charts -> виды', () => {
    const iF = html.indexOf('formulas.js');
    const iC = html.indexOf('js/guests/common.js');
    const iCh = html.indexOf('charts.js');
    const iFirstView = Math.min(...TABS.map((t) => {
        const i = html.indexOf(`views-${t}.js`);
        return i < 0 ? Number.MAX_SAFE_INTEGER : i;
    }));
    assert.ok(iF > 0 && iC > iF, 'common.js должен идти после formulas.js');
    assert.ok(iCh > iC, 'charts.js должен идти после common.js');
    assert.ok(iFirstView > iCh, 'виды должны подключаться после charts.js');
});

test('конфиг точек передаётся в страницу до скриптов раздела', () => {
    assert.ok(html.includes('window.GUESTS_CONFIG'), 'нет GUESTS_CONFIG');
    assert.ok(html.includes('bars | tojson') || html.includes('bars|tojson'),
        'bars не отдаются в шаблон');
    // Ключи витрины в конфиг намеренно НЕ кладутся: витринные отчёты получают
    // точки вместе с данными, а второй список в шаблоне разъезжался бы с первым.
    // Проверяем именно конфиг: слово venues есть и в имени вкладки «Точки».
    const cfg = html.slice(html.indexOf('window.GUESTS_CONFIG'),
                           html.indexOf('formulas.js'));
    assert.ok(!cfg.includes('venues'), 'ключи витрины снова дублируются в конфиге');
    assert.ok(html.indexOf('GUESTS_CONFIG') < html.indexOf('js/guests/common.js'),
        'GUESTS_CONFIG должен объявляться до common.js');
});

// ---------------------------------------------------------------- переименование
test('страница называется «Маркетинг», старого пункта меню нет', () => {
    assert.ok(html.includes('Маркетинг'), 'заголовок страницы не переименован');
    assert.ok(!nav.includes('Анализ акций'), 'в меню остался пункт «Анализ акций»');
    assert.ok(!nav.includes('href="/discounts"'), 'в меню осталась ссылка на /discounts');
    assert.ok(nav.includes('Маркетинг'), 'в меню нет пункта «Маркетинг»');
});

test('старый шаблон ни на что не подключён, мёртвый RFM-эндпоинт вырезан', () => {
    // Проверяем ИНВАРИАНТ, а не отсутствие файла: пока шаблон никем не
    // рендерится и не подключается, он безвреден. Сам файл-сирота удаляется
    // отдельно (см. запись в CHANGELOG).
    for (const f of ['routes/pages.py', 'routes/guests.py', 'routes/__init__.py']) {
        assert.ok(!read(f).includes("'discounts.html'"),
            `${f} всё ещё ссылается на discounts.html`);
    }
    assert.ok(!nav.includes('discounts'), 'меню всё ещё ведёт на старую страницу');
    const analysis = read('routes/analysis.py');
    assert.ok(!analysis.includes('/api/rfm-analyze'),
        'дубль RFM-эндпоинта не удалён');
    assert.ok(!analysis.includes('def get_rfm_segment'),
        'клиентская модель сегментов не удалена');
    assert.ok(analysis.includes('/api/discount-analyze'),
        'эндпоинт акций должен остаться — им живёт вкладка «Акции»');
});

test('/discounts отдаёт редирект, а не шаблон', () => {
    const pages = read('routes/pages.py');
    assert.ok(pages.includes("redirect('/guests#promo'"), 'нет редиректа на вкладку акций');
    assert.ok(pages.includes("redirect('/guests#rfm'"), 'нет редиректа старого ?mode=rfm');
    assert.ok(!pages.includes("render_template('discounts.html'"),
        'страница всё ещё рендерит удалённый шаблон');
});

// ---------------------------------------------------------------- CSS-покрытие
// Классы, которые JS пишет в разметку, должны существовать в CSS раздела или в
// общих стилях дашборда. Опечатка в имени иначе видна только глазами.
const sharedCss = ['static/dashboard/styles/base.css',
                   'static/dashboard/styles/variables.css',
                   'static/dashboard/styles/sidebar.css',
                   'static/dashboard/styles/mobile.css']
    .filter(exists).map(read).join('\n');
const allCss = css + '\n' + sharedCss;

// Имена классов собираются из строк вида '<div class="a b">'. В JS значение
// атрибута часто склеивается из кусков ('class="sub-btn' + (cond ? ' active' : '')),
// поэтому берём только токены, похожие на имя класса, а обрывки выражений
// (кавычки, скобки, операторы) отбрасываем.
const CLASS_NAME = /^[a-z][a-z0-9_-]*$/i;
function classesUsedIn(src) {
    const found = new Set();
    const re = /class="([^"{}]+)"/g;
    let m;
    while ((m = re.exec(src)) !== null) {
        for (const cls of m[1].split(/\s+/)) {
            if (CLASS_NAME.test(cls)) found.add(cls);
        }
    }
    return found;
}

test('классы вкладки «Акции» описаны в CSS', () => {
    const missing = [...classesUsedIn(promo)].filter((c) => !allCss.includes('.' + c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
});

test('классы вкладки RFM описаны в CSS', () => {
    const missing = [...classesUsedIn(rfm)].filter((c) => !allCss.includes('.' + c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
});

test('скрытие глобального периода описано в CSS и включается из JS', () => {
    assert.ok(css.includes('.guests-controls.own-period'),
        'нет правила скрытия панели периода');
    assert.ok(common.includes("classList.toggle('own-period'"),
        'JS не переключает класс own-period');
    assert.ok(promo.includes('ownPeriod: true'),
        'вкладка «Акции» не объявлена как владеющая своим периодом');
});

// ---------------------------------------------------------------- формулы
test('все ключи формул, на которые ссылаются виды, существуют', () => {
    const keys = new Set();
    for (const src of [promo, rfm]) {
        for (const re of [/helpIcon\('([a-z0-9_]+)'\)/g,
                          /metricCard\('([a-z0-9_]+)'/g]) {
            let m;
            while ((m = re.exec(src)) !== null) keys.add(m[1]);
        }
        const hb = /howBlock\(\[([^\]]+)\]\)/g;
        let m;
        while ((m = hb.exec(src)) !== null) {
            for (const raw of m[1].split(',')) {
                const k = raw.trim().replace(/^['"]|['"]$/g, '');
                if (/^[a-z0-9_]+$/.test(k)) keys.add(k);
            }
        }
    }
    assert.ok(keys.size > 5, `ключей подозрительно мало: ${keys.size}`);
    const missing = [...keys].filter((k) => !new RegExp(`^\\s{4}${k}:`, 'm').test(formulas));
    assert.deepEqual(missing, [], `нет в GUEST_FORMULAS: ${missing.join(', ')}`);
});

test('формулы не ссылаются на удалённую страницу', () => {
    assert.ok(!formulas.includes('Анализ акций'),
        'текст формулы ссылается на страницу, которой больше нет');
});

// ---------------------------------------------------------------- графики
test('scatter добавлен в обёртку графиков и используется RFM', () => {
    assert.ok(charts.includes('function scatter('), 'нет функции scatter');
    assert.ok(/return \{[^}]*scatter: scatter/s.test(charts), 'scatter не экспортирован');
    assert.ok(rfm.includes('GCharts.scatter('), 'RFM не использует scatter');
});

test('id канвасов уникальны по всей странице', () => {
    const ids = [];
    for (const tab of TABS) {
        const src = read(`static/js/guests/views-${tab}.js`);
        const re = /<canvas id="([^"]+)"/g;
        let m;
        while ((m = re.exec(src)) !== null) ids.push(m[1]);
    }
    const dup = ids.filter((v, i) => ids.indexOf(v) !== i);
    assert.deepEqual(dup, [], `дублирующиеся id канвасов: ${dup.join(', ')}`);
});

// ---------------------------------------------------------------- баги, которые не переносим
test('в перенесённом коде нет захардкоженных 180 дней', () => {
    assert.ok(!/\/\s*180\b/.test(promo),
        'вернулся хардкод 180 дней вместо фактической длины диапазона');
    // Частоту и давность считает сервер по фактической длине диапазона;
    // клиентского пересчёта (источника прежнего бага) быть не должно.
    assert.ok(!/frequency_per_week\s*[:=]\s*[^,\n]*\/(?![*/])/.test(promo),
        'частота снова считается на клиенте');
});

test('сводка «Все акции» берётся с сервера, а не складывается на клиенте', () => {
    // Тип скидки — измерение позиции чека: один чек лежит в множествах двух
    // акций, поэтому складывать orders_count/orders по акциям нельзя.
    assert.ok(promo.includes("'__all__'"), 'нет служебного ведра сводки');
    assert.ok(!/orders_count\s*\+=/.test(promo), 'чеки точек снова складываются');
    assert.ok(!/\.orders\s*\+=/.test(promo), 'чеки гостя снова складываются');
    const analysis = read('routes/analysis.py');
    assert.ok(analysis.includes("ALL_BUCKET = '__all__'"),
        'сервер не объявляет сводное ведро');
    assert.ok(/for bucket in \(discount_name, ALL_BUCKET\)/.test(analysis),
        'сервер не наполняет сводное ведро');
});

test('псевдогость «Без карты» исключён из гостевых метрик', () => {
    assert.ok(promo.includes("NO_CARD = 'Без карты'"), 'нет константы');
    assert.ok(promo.includes('splitNoCard'), 'нет отделения продаж без карты');
});

test('смена точки и дат вызывает загрузку, а не молчит', () => {
    assert.ok(/\['promoBar', 'promoFrom', 'promoTo'\]/.test(promo),
        'точка и даты не подписаны на перезагрузку');
    assert.ok(!promo.includes('function sameRange'),
        'вернулась проверка, из-за которой смена точки ничего не делала');
});

test('повторный клик по «Анализировать» защищён', () => {
    assert.ok(promo.includes('var gen = 0'), 'нет поколения запроса');
    assert.ok(promo.includes('my !== gen'), 'устаревший ответ не отбрасывается');
    assert.ok(promo.includes("busy ? 'Запрашиваю…'"), 'кнопка не блокируется');
});

test('вкладка «Акции» не грузит iiko при открытии', () => {
    assert.ok(promo.includes('Анализировать'), 'нет кнопки явной загрузки');
    // Запрос отчёта должен идти только из load(), вызываемого по кнопке/drill-down.
    // Считаем именно ВЫЗОВЫ, а не упоминания в комментариях.
    const calls = (promo.match(/G\.post\('\/api\/discount-analyze'/g) || []).length;
    assert.equal(calls, 1, 'вызов discount-analyze должен быть ровно один (в load)');
    // Ни одного другого обращения к iiko: список акций приходит вместе с отчётом.
    assert.ok(!promo.includes('discount-names'),
        'вернулся отдельный запрос за списком акций — он лезет в iiko при открытии');
    // Точка входа вида не должна ничего запрашивать.
    const entry = promo.slice(promo.lastIndexOf('--------- вход'));
    assert.ok(!/G\.(api|post)\(/.test(entry), 'точка входа делает запрос');
});

console.log(`\n${passed} ok, ${failed} failed`);
process.exit(failed ? 1 : 0);

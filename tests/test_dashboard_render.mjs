/**
 * Тесты редизайна дашборда (2026-08-11): группировка метрик и покрытие стилями.
 *
 *     node tests/test_dashboard_render.mjs
 *
 * Браузера в проверке нет, поэтому ловим две самые вероятные поломки редизайна:
 *   1. метрика потерялась / попала не в ту группу (экран не покажет показатель);
 *   2. класс, который JS пишет в разметку, нигде не описан в CSS (элемент есть,
 *      но выглядит сломанным) — опечатка в имени класса иначе видна только глазами.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { METRICS, METRIC_GROUPS, HEADLINE_METRIC_IDS } from '../static/js/dashboard/core/config.js';
import { getStatus, scorePercent } from '../static/js/dashboard/core/utils.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

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

const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

console.log('\n--- группировка метрик ---');

test('все 17 карточек на месте', () => {
    // 16 базовых + «Доля чеков с картой» (с 2026-09-05 четыре карточки лояльности
    // свёрнуты в одну; их числа остались в API, сравнении и экспорте).
    assert.equal(METRICS.length, 17);
});

test('у каждой метрики есть существующая группа', () => {
    const known = new Set(METRIC_GROUPS.map(g => g.id));
    for (const m of METRICS) {
        assert.ok(m.group, `${m.id}: группа не указана`);
        assert.ok(known.has(m.group), `${m.id}: неизвестная группа "${m.group}"`);
    }
});

test('в каждой группе есть метрики', () => {
    for (const g of METRIC_GROUPS) {
        const n = METRICS.filter(m => m.group === g.id).length;
        assert.ok(n > 0, `группа ${g.id} пустая`);
    }
});

test('четыре группы по 4 метрики заполняют ряд целиком, «Лояльность» — одна карточка', () => {
    assert.equal(METRIC_GROUPS.length, 5);
    const counts = METRIC_GROUPS.map(g => METRICS.filter(m => m.group === g.id).length);
    assert.deepEqual(counts, [4, 4, 4, 4, 1]);
});

test('итог группы идёт первым', () => {
    // «Выручка» открывает группу выручки, «% наценки» — группу наценки:
    // сначала общий показатель, потом разбивка по направлениям.
    const first = (id) => METRICS.filter(m => m.group === id)[0].id;
    assert.equal(first('revenue'), 'revenue');
    assert.equal(first('markup'), 'markupPercent');
});

test('группа выручки и наценки покрывают все три направления', () => {
    for (const g of ['revenue', 'markup']) {
        const ids = METRICS.filter(m => m.group === g).map(m => m.id).join(' ');
        for (const dir of ['Draft', 'Packaged', 'Kitchen']) {
            assert.ok(ids.includes(dir), `${g}: нет ${dir}`);
        }
    }
});

test('«Главное» — выручка, чеки, средний чек и все они существуют', () => {
    assert.deepEqual(HEADLINE_METRIC_IDS, ['revenue', 'checks', 'averageCheck']);
    for (const id of HEADLINE_METRIC_IDS) {
        assert.ok(METRICS.some(m => m.id === id), `нет метрики ${id}`);
    }
});

test('id метрик уникальны', () => {
    const ids = METRICS.map(m => m.id);
    assert.equal(new Set(ids).size, ids.length);
});

test('planKey и actualKey каждой метрики совпадают с id', () => {
    // План и факт приходят с API под тем же ключом, что id метрики
    // (frontend_mapping в routes/dashboard.py).
    for (const m of METRICS) {
        assert.equal(m.planKey, m.id, `${m.id}: planKey`);
        assert.equal(m.actualKey, m.id, `${m.id}: actualKey`);
    }
});

console.log('\n--- лояльность (2026-09-04) ---');

/** Карточки группы «Лояльность»: с 2026-09-05 одна — «Доля чеков с картой». */
const LOYALTY_IDS = ['cardChecksShare'];
/** Бывшие карточки лояльности — теперь вкладки внутри «Доли чеков с картой». */
const FOLDED_LOYALTY_IDS = ['cardChecks', 'nocardChecks', 'cardRevenue'];

test('группа «Лояльность» последняя, в ней одна карточка «Доля чеков с картой»', () => {
    const last = METRIC_GROUPS[METRIC_GROUPS.length - 1];
    assert.equal(last.id, 'loyalty');
    assert.equal(last.name, 'Лояльность');
    const ids = METRICS.filter(m => m.group === 'loyalty').map(m => m.id);
    assert.deepEqual(ids, LOYALTY_IDS);
    // Карточка дописана в конец массива — прежние 16 не сдвинуты.
    assert.deepEqual(METRICS.slice(-1).map(m => m.id), LOYALTY_IDS);
    for (const id of FOLDED_LOYALTY_IDS) {
        assert.ok(!METRICS.some(m => m.id === id), `${id}: карточка должна быть свёрнута во вкладку`);
    }
    const m = METRICS.find(x => x.id === 'cardChecksShare');
    assert.equal(m.planKey, 'cardChecksShare', 'план карточки — cardChecksShare');
    assert.ok(m.hint.includes('70%'), 'подсказка не говорит про план по умолчанию 70%');
});

test('у метрик лояльности есть подсказка-формула; у остальных она не обязательна', () => {
    for (const m of METRICS) {
        if (LOYALTY_IDS.includes(m.id)) {
            assert.equal(typeof m.hint, 'string', `${m.id}: hint не строка`);
            assert.ok(m.hint.trim().length > 0, `${m.id}: пустая подсказка`);
        } else if ('hint' in m) {
            // Поле необязательное, но если задано — только непустая строка.
            assert.ok(typeof m.hint === 'string' && m.hint.trim().length > 0, `${m.id}: hint задан, но пуст`);
        }
    }
});

test('метрики лояльности не попадают в «Главное»', () => {
    for (const id of LOYALTY_IDS) {
        assert.ok(!HEADLINE_METRIC_IDS.includes(id), `${id} в HEADLINE_METRIC_IDS`);
    }
});

test('analytics.js показывает hint как title названия метрики на десктопе и мобильном', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(/metric\.hint/.test(js), 'analytics.js не читает metric.hint');
    assert.ok(js.includes('title="${metric.hint'), 'hint не попадает в атрибут title');
    const count = (needle) => js.split(needle).length - 1;
    // Десктоп: обе ветки createMetricCard (с планом и без).
    assert.equal(count('class="metric-name"${hintAttr(metric)}'), 2, '.metric-name без подсказки');
    // Мобильный: hero и compact в «Главном», строка внутри раскрытой группы.
    assert.equal(count('class="m-card-label"${hintAttr(metric)}'), 2, '.m-card-label без подсказки');
    assert.equal(count('class="m-row-name"${hintAttr(metric)}'), 1, '.m-row-name без подсказки');
});

test('comparison.js сравнивает метрики лояльности под ключами API', () => {
    const js = read('static/js/dashboard/modules/comparison.js');
    for (const [key, altKey] of [
        ['cardChecks', 'card_checks'], ['nocardChecks', 'nocard_checks'],
        ['cardChecksShare', 'card_checks_share'], ['cardRevenue', 'card_revenue']
    ]) {
        assert.ok(js.includes(`key: '${key}', altKey: '${altKey}'`), `нет ${key}/${altKey}`);
    }
});

console.log('\n--- покрытие стилями ---');

const CSS = [
    'static/dashboard/styles/base.css',
    'static/dashboard/styles/cards.css',
    'static/dashboard/styles/mobile.css',
    'static/dashboard/styles/tabs.css',
    'static/dashboard/styles/comparison.css',
    'static/dashboard/styles/animations.css',
    'static/dashboard/styles/sidebar.css',
    'static/dashboard/styles/charts.css'
].map(read).join('\n');

/** Классы, которые JS/шаблон ставит на элементы редизайна. */
const REDESIGN_CLASSES = [
    // шапка фильтров: одна полоса «заведение | период | экспорт»
    'filter-bar', 'fb-native-select', 'fb-item', 'fb-venue', 'fb-strong', 'fb-hint',
    'fb-icon', 'fb-caret', 'fb-divider', 'fb-spacer',
    'fb-period', 'fb-arrow', 'fb-period-trigger',
    'fb-export', 'fb-ghost', 'fb-export-mobile', 'period-picker-anchor',
    // выпадающие списки / нижний лист
    'fb-backdrop', 'fb-menu', 'fb-grab', 'fb-menu-label', 'fb-menu-item',
    'fb-menu-name', 'fb-menu-hint', 'fb-menu-icon', 'fb-menu-sep', 'fb-menu-muted',
    // десктопные группы и карточка
    'mv-desktop', 'metric-group', 'mg-separator', 'mg-title', 'mg-line',
    'metrics-grid-row', 'metric-card', 'metric-name', 'metric-value',
    'mc-head', 'mc-caret', 'metric-breakdown-panel', 'breakdown-metric',
    // легенда шкал — одна на страницу, в строке вкладок
    'tabs-legend', 'tl-item', 'tl-swatch', 'tl-swatch-prev', 'tabs-divider',
    'tabs-spacer', 'completion-label', 'completion-value',
    'mc-bars', 'mc-bar-row', 'mc-bar-row-prev', 'mc-track',
    'mc-fill', 'mc-fill-prev', 'mc-pct', 'mc-pct-prev', 'mc-footer',
    'mc-delta', 'mc-plan', 'mc-noplan',
    // мобильный экран
    'mv-mobile', 'm-section-label', 'm-summary', 'm-summary-top', 'm-summary-label',
    'm-summary-dates', 'm-summary-value', 'm-summary-pct', 'm-summary-word',
    'm-legend', 'm-legend-item', 'm-dot', 'm-track', 'm-fill',
    'm-hero', 'm-hero-row', 'm-hero-value', 'm-duo', 'm-compact', 'm-compact-value',
    'm-card-top', 'm-card-label', 'm-card-foot', 'm-pct', 'm-plan', 'm-prev', 'm-delta',
    'm-group', 'm-group-head', 'm-group-name', 'm-group-count', 'm-group-pct',
    'm-group-body', 'm-row', 'm-row-top', 'm-row-name', 'm-row-value',
    // нижняя таб-панель
    'bottom-tabs', 'bt-item'
];

test('каждый класс редизайна описан в CSS', () => {
    const missing = REDESIGN_CLASSES.filter(cls => !CSS.includes(`.${cls}`));
    assert.deepEqual(missing, [], `нет правил для: ${missing.join(', ')}`);
});

console.log('\n--- разбивка карточки по сотрудникам (2026-09-04) ---');

test('классы разбивки по сотрудникам описаны в CSS', () => {
    const classes = [
        'metric-breakdown', 'breakdown-header', 'breakdown-close', 'breakdown-list',
        'breakdown-item', 'breakdown-rank', 'breakdown-name', 'breakdown-value',
        'breakdown-empty', 'breakdown-rest', 'breakdown-total', 'breakdown-sub'
    ];
    const missing = classes.filter(cls => !CSS.includes(`.${cls}`));
    assert.deepEqual(missing, [], `нет правил для: ${missing.join(', ')}`);
});

test('список раскрываемых метрик один — EXPANDABLE_METRICS, без дубля в обработчике клика', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(!js.includes('const expandableMetrics'), 'в handleCardClick остался свой список');
    assert.ok(js.includes('if (!EXPANDABLE_METRICS.includes(metric.id)) return;'), 'клик не сверяется с EXPANDABLE_METRICS');
});

test('разбивка рисует «Остальные», «Итого» и число чеков у отношений', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(js.includes('breakdown-rest'), 'нет строки «Остальные»');
    assert.ok(js.includes('breakdown-total'), 'нет строки «Итого»');
    assert.ok(js.includes('breakdown-sub'), 'нет числа чеков у отношений');
    // Складываемые метрики — подмножество раскрываемых; отношения в них не входят.
    const additive = js.match(/const ADDITIVE_METRICS = \[([^\]]+)\]/)[1].match(/'([^']+)'/g).map(s => s.slice(1, -1));
    const expandable = js.match(/const EXPANDABLE_METRICS = \[([^\]]+)\]/)[1].match(/'([^']+)'/g).map(s => s.slice(1, -1));
    for (const id of additive) assert.ok(expandable.includes(id), `${id} не раскрывается`);
    for (const id of ['averageCheck', 'draftShare', 'markupPercent']) assert.ok(!additive.includes(id), `${id} нельзя складывать`);
});

test('мобильные карточки и строки раскрываются тем же обработчиком, что десктопные', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    // Десктопная карточка + m-hero + m-compact + m-row.
    assert.equal(js.split('this.attachCardBehaviour(').length - 1, 4, 'не все элементы получают обработчик клика');
    for (const label of ['m-card-label', 'm-row-name']) {
        assert.ok(js.includes(`${label}"${'$'}{hintAttr(metric)}>${'$'}{metric.name.toUpperCase()}${'$'}{mobileCaret(metric)}`),
            `${label}: нет каретки раскрытия`);
    }
    for (const cls of ['m-caret', 'm-compact.expanded', 'm-row .metric-breakdown']) {
        assert.ok(CSS.includes(`.${cls}`), `нет правил для .${cls}`);
    }
});

console.log('\n--- панель деталей под рядом и заметный шеврон (2026-09-05) ---');

test('раскрытие карточки в сетке — панель после ряда, а не внутри ячейки', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(js.includes('panelHost(card)'), 'нет выбора места для панели');
    assert.ok(js.includes("parent.classList.contains('metrics-grid-row') || parent.classList.contains('m-duo')"),
        'панель под рядом должна работать для десктопного ряда и мобильной пары');
    assert.ok(js.includes("this.rowEndCard(card, host).insertAdjacentElement('afterend', breakdown)"), 'панель не вставляется после последней карточки ряда');
    assert.ok(js.includes('el.offsetTop === card.offsetTop'), 'ряд карточки не определяется по offsetTop');
    assert.ok(/\.metric-breakdown-panel \{[^}]*grid-column: 1 \/ -1/.test(CSS), 'панель не на всю ширину сетки');
    assert.ok(js.includes("host ? 'metric-breakdown metric-breakdown-panel' : 'metric-breakdown'"), 'нет класса панели');
    assert.ok(js.includes('breakdown-metric'), 'в шапке панели нет названия метрики');
    // Разметка раскрытия больше не ищется внутри карточки — только через breakdownOf.
    assert.ok(!js.includes("card.querySelector('.breakdown-"), 'осталась выборка раскрытия внутри карточки');
    assert.ok(!js.includes("card.querySelectorAll('.breakdown-"), 'осталась выборка вкладок внутри карточки');
    assert.ok(!js.includes("card.querySelector('.metric-breakdown')"), 'закрытие ищет раскрытие внутри карточки');
    assert.ok(js.includes('return this.expandedCard === card ? this.breakdownEl : null;'), 'нет breakdownOf');
    // Сброс ссылки на панель вместе с раскрытой карточкой при перерисовке.
    assert.equal(js.split('this.breakdownEl = null;').length - 1, 3, 'breakdownEl не сбрасывается везде, где expandedCard');
});

test('шеврон раскрытия — SVG в кружке на десктопе и телефоне, старой стрелки нет', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(js.includes('class="mc-caret" aria-hidden="true">${CHEVRON_SVG}</span>'), 'десктопная каретка не шеврон');
    assert.ok(js.includes('class="m-caret" aria-hidden="true">${CHEVRON_SVG}</span>'), 'мобильная каретка не шеврон');
    assert.ok(!js.includes('&#9662;'), 'осталась старая стрелка');
    for (const rule of ['.mc-caret .chevron', '.m-caret .chevron', '.metric-card.expandable:hover .mc-caret',
                        '.metric-card.expandable:hover', '.metric-card.expanded::before', '.metric-card.expanded .mc-caret']) {
        assert.ok(CSS.includes(rule), `нет правила ${rule}`);
    }
});

test('панель под рядом: сетка неподвижна — пара на телефоне больше не растягивает карточку', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(!/\.m-compact\.expanded[^{]*\{[^}]*grid-column/.test(CSS), 'раскрытая карточка пары снова на всю ширину');
    // Плитка панели не шире панели: на телефоне минимум 360px переполнял пару.
    assert.ok(CSS.includes('minmax(min(360px, 100%), 1fr)'), 'минимум плитки панели жёстче ширины панели');
    // Тёмная тема не должна гасить акцентную рамку раскрытой/наведённой карточки.
    assert.ok(CSS.includes('[data-theme="dark"] .metric-card.expanded'), 'в тёмной теме нет рамки у раскрытой карточки');
    assert.ok(!/\[data-theme="dark"\] \.metric-card \{/.test(CSS), 'осталось правило тёмной темы, перебивающее состояния карточки');
    // Спиннер загрузки — на шевроне, а не псевдоэлементом в потоке (менял высоту карточки).
    assert.ok(!CSS.includes('.metric-card.loading::after'), 'спиннер загрузки снова в потоке карточки');
    assert.ok(CSS.includes('.metric-card.loading .mc-caret'), 'спиннер загрузки не на шевроне');
    assert.ok(/\.metrics-grid-row \{[^}]*align-items: stretch/.test(CSS), 'карточки ряда не одной высоты');
    assert.ok(!read('static/dashboard/styles/variables.css').includes('--caret-color'), 'мёртвый токен --caret-color');
    assert.ok(js.includes('<button type="button" class="breakdown-close" aria-label="Закрыть">'), 'крестик закрытия не кнопка');
    assert.ok(CSS.includes('.metric-breakdown-panel .breakdown-list'), 'нет плитки строк в панели');
    assert.ok(/\.metric-breakdown-panel \.breakdown-total[^{]*\{[^}]*grid-column: 1 \/ -1/.test(CSS), '«Итого» в панели не на всю ширину');
    assert.ok(CSS.includes('.metric-breakdown-panel {'), 'нет стиля панели');
});

test('ответ по сотрудникам принимается только для текущего бара и периода', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(js.includes('employeeDataKey()'), 'нет ключа «бар + период» у данных сотрудников');
    assert.ok(js.includes('this.employeeDataKey() !== requestKey'), 'нет проверки устаревшего ответа');
});

console.log('\n--- детали внутри карточки (2026-09-04) ---');

test('классы деталей карточки описаны в CSS', () => {
    const classes = [
        'breakdown-tabs', 'breakdown-tab', 'breakdown-heading', 'breakdown-formula',
        'breakdown-note', 'breakdown-link', 'breakdown-loading'
    ];
    const missing = classes.filter(cls => !CSS.includes(`.${cls}`));
    assert.deepEqual(missing, [], `нет правил для: ${missing.join(', ')}`);
    assert.ok(CSS.includes('.breakdown-tab.active'), 'нет стиля активной вкладки');
});

test('раскрываются все 17 карточек; «Сотрудники» — у всех, кроме кранов', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    const list = (name) => js.match(new RegExp(`const ${name} = \\[([^\\]]+)\\]`))[1]
        .match(/'([^']+)'/g).map(s => s.slice(1, -1));
    const expandable = list('EXPANDABLE_METRICS');
    assert.deepEqual([...expandable].sort(), METRICS.map(m => m.id).sort());
    const employee = list('EMPLOYEE_METRICS');
    assert.ok(!employee.includes('tapActivity'), 'у кранов нет сотрудников');
    for (const id of employee) assert.ok(expandable.includes(id), `${id} не раскрывается`);
    for (const id of LOYALTY_IDS) assert.ok(employee.includes(id), `${id}: нет вкладки «Сотрудники»`);
    const additive = list('ADDITIVE_METRICS');
    assert.ok(!additive.includes('cardChecksShare'), 'доля чеков с картой не складывается');
    // Свёрнутые карточки лояльности ушли из всех списков analytics.js.
    for (const id of FOLDED_LOYALTY_IDS) {
        for (const name of ['EXPANDABLE_METRICS', 'EMPLOYEE_METRICS', 'ADDITIVE_METRICS']) {
            assert.ok(!list(name).includes(id), `${id} остался в ${name}`);
        }
    }
});

test('клик по вкладке не схлопывает карточку, краны раскрываются вместо перехода', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    const idx = js.indexOf('this.switchTab(card, metric, btn.dataset.section)');
    assert.ok(idx > 0, 'нет обработчика вкладки');
    assert.ok(js.slice(idx - 200, idx).includes('e.stopPropagation()'), 'клик по вкладке всплывает на карточку');
    assert.ok(js.includes("breakdown.addEventListener('click', (e) => e.stopPropagation())"), 'клики внутри раскрытия всплывают');
    assert.ok(!js.includes('window.location.href'), 'карточка кранов всё ещё уводит на /taps');
    assert.ok(js.includes("DEFAULT_TAB = { draftShare: 'draft_liters', tapActivity: 'taps' }"), 'у розлива первой должна быть вкладка «Литры»');
});

test('детали принимаются только для текущего бара, периода и раскрытой карточки', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(js.includes('async loadCardDetails(card, metric)'), 'нет загрузки деталей');
    assert.ok(js.includes('if (this.expandedCard !== card) return;'), 'детали рисуются в чужую карточку');
    // Сброс вместе с сотрудниками при смене бара/периода (конструктор + resetEmployeeData).
    assert.equal(js.split('this.cardDetails = {};').length - 1, 2, 'детали не сбрасываются при смене периода');
    assert.ok(js.includes('breakdown-formula'), 'формула секции не показывается текстом');
    // Один запрос на метрику и на ленивую секцию: повторное раскрытие ждёт тот же промис.
    assert.ok(js.includes('this._detailsInflight[metric.id] = promise'), 'детали без дедупликации запросов');
    assert.ok(js.includes('await this._detailsInflight[metric.id]'), 'повторное раскрытие не ждёт идущий запрос');
    assert.ok(js.includes('async fetchLazySection(metric, section)'), 'нет отдельного запроса ленивой секции');
    assert.ok(js.includes('await this._lazyInflight[section.id]'), 'вторая карточка не ждёт запрос ленивой секции');
    // Ошибки не запоминаются как данные.
    assert.ok(!js.includes("this.lazySections[section.id] = { ...section, lazy: false, rows: [], error"), 'ошибка ленивой секции кэшируется');
    assert.ok(js.includes('Детали карточки не загрузились'), 'ошибка деталей невидима под списком сотрудников');
    // Перерисовка сетки забывает раскрытую карточку; клик по отсоединённому узлу не раскрывает его.
    assert.ok(js.includes('if (!card.isConnected) return;'), 'раскрытие отсоединённого узла');
});

test('мобильный перенос названий стоит после базовых правил и не перекрыт ими', () => {
    const cards = read('static/dashboard/styles/cards.css').replace(/\r\n/g, '\n');
    const base = cards.indexOf('\n.breakdown-name {');
    const mobile = cards.indexOf('@media (max-width: 768px) {\n    .breakdown-name {');
    assert.ok(base > 0 && mobile > 0, 'нет правил .breakdown-name');
    assert.ok(mobile > base, 'медиа-правило переноса стоит выше базового и проигрывает ему');
    assert.ok(!/\.breakdown-tab\.active \{[^}]*\bwhite\b/.test(cards), 'цвет активной вкладки не через токен');
    const vars = read('static/dashboard/styles/variables.css');
    assert.equal([...vars.matchAll(/--text-on-accent:/g)].length, 2, 'токен --text-on-accent нужен обеим темам');
});

test('api.js и config.js знают эндпоинты разбивки и деталей', () => {
    const api = read('static/js/dashboard/core/api.js');
    const cfg = read('static/js/dashboard/core/config.js');
    assert.ok(cfg.includes("CARD_DETAILS: '/api/dashboard-card-details'"), 'нет API.CARD_DETAILS');
    assert.ok(cfg.includes("EMPLOYEE_BREAKDOWN: '/api/employee-metrics-breakdown'"), 'нет API.EMPLOYEE_BREAKDOWN');
    assert.ok(api.includes('fetchAPI(API.CARD_DETAILS'), 'getCardDetails не через config');
    assert.ok(api.includes('fetchAPI(API.EMPLOYEE_BREAKDOWN'), 'getEmployeeBreakdown не через config');
    assert.ok(!api.includes("'/api/employee-metrics-breakdown'"), 'URL разбивки захардкожен строкой');
    const utils = read('static/js/dashboard/core/utils.js');
    assert.ok(utils.includes("case 'liters'"), 'formatValue не знает литров');
    assert.ok(utils.includes('export function formatLiters'), 'нет formatLiters');
});

test('анимация раскрытия не ограничивает высоту списка', () => {
    const cards = read('static/dashboard/styles/cards.css');
    assert.ok(!/@keyframes slideDown[\s\S]{0,300}max-height/.test(cards), 'slideDown снова с max-height');
});

test('статусные модификаторы покрыты для процентов и точек', () => {
    for (const base of ['mc-pct', 'm-pct', 'm-dot', 'm-group-pct']) {
        for (const st of ['success', 'warning', 'danger']) {
            assert.ok(CSS.includes(`.${base}.${st}`), `нет .${base}.${st}`);
        }
    }
});

test('в CSS редизайна нет HEX-цветов мимо переменных', () => {
    // docs/design-system.md: цвета только через var(--name).
    // Проверяем файл переменных как исключение и остальные — на голые #RRGGBB.
    const cards = read('static/dashboard/styles/cards.css');
    const hex = [...cards.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map(m => m[0]);
    assert.deepEqual(hex, [], `HEX в cards.css: ${hex.join(', ')}`);
});

test('шкала предыдущего периода имеет свой токен в обеих темах', () => {
    const vars = read('static/dashboard/styles/variables.css');
    const decls = [...vars.matchAll(/--bar-prev:/g)];
    assert.equal(decls.length, 2, 'ожидались объявления для светлой и тёмной темы');
});

test('мобильный каркас лежит в base.css, а не в mobile.css', () => {
    // Управление страницей (шапка фильтров, нижняя таб-панель) обязано ехать
    // вместе с разметкой. Пока эти правила жили в отдельном mobile.css,
    // недоехавший файл отдавал телефону десктопную полосу: одна строка 56px,
    // из которой контролы вылетают за край на ~140px и наезжают друг на друга.
    const base = read('static/dashboard/styles/base.css');
    const mobile = read('static/dashboard/styles/mobile.css');
    for (const sel of ['.fb-export-mobile', '.bottom-tabs', '.bt-item', '.fb-menu']) {
        assert.ok(base.includes(sel), `${sel} пропал из base.css`);
        assert.ok(!mobile.includes(sel), `${sel} снова уехал в mobile.css`);
    }
    const bar = base.match(/\.filter-bar\s*\{[^}]*\}/);
    assert.ok(bar, 'нет правила .filter-bar');
    assert.ok(/min-height/.test(bar[0]), '.filter-bar снова с жёсткой height');
    assert.ok(/flex-wrap:\s*wrap/.test(bar[0]), '.filter-bar без flex-wrap: полоса не свернётся');
});

console.log('\n--- бюджетные метрики (2026-09-05) ---');

test('scorePercent/getStatus: у бюджетной метрики план — потолок', () => {
    // Обычная метрика — как есть; бюджетная — зеркало 200 − p, не ниже нуля.
    assert.equal(scorePercent(103), 103);
    assert.equal(scorePercent(103, true), 97);
    assert.equal(scorePercent(95, true), 105);
    assert.equal(scorePercent(250, true), 0);
    assert.equal(getStatus(103), 'success');
    assert.equal(getStatus(95, true), 'success');
    assert.equal(getStatus(100, true), 'success');
    assert.equal(getStatus(103, true), 'warning');
    assert.equal(getStatus(110, true), 'warning');
    assert.equal(getStatus(111, true), 'danger');
    // Python-зеркало формулы (HTML-экспорт) — та же арифметика и тот же список.
    const py = read('core/plans_manager.py');
    assert.ok(py.includes('return max(0.0, 200.0 - percent)'), 'plan_score в Python отличается');
    assert.ok(py.includes("BUDGET_METRICS = frozenset({'loyaltyWriteoffs'})"), 'BUDGET_METRICS не совпадает с config.js');
});

test('config.js: бюджетная метрика — только списания баллов, подсказка объясняет пороги', () => {
    assert.deepEqual(METRICS.filter(m => m.budget === true).map(m => m.id), ['loyaltyWriteoffs']);
    const m = METRICS.find(m => m.id === 'loyaltyWriteoffs');
    assert.ok(m.hint.includes('бюджет'), 'подсказка не объясняет светофор бюджета');
});

test('analytics.js: средние и «выполнено» по score, отклонение по good, подпись «бюджет»', () => {
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(js.includes('scorePercent(percent, budget)'), 'buildStats не считает score');
    assert.ok(js.includes('good: budget ? diff <= 0 : diff >= 0'), 'нет знака good');
    // Три средних (шапка, мобильная сводка, группа) — по score, не по percent.
    assert.equal((js.match(/sum \+ s\.score, 0\) \/ withPlan\.length/g) || []).length, 3, 'среднее не по score');
    assert.ok(!js.includes('sum + s.percent, 0)'), 'осталось среднее по percent');
    assert.ok(js.includes('s.score >= 100'), '«выполнено» не по score');
    assert.ok(js.includes("mc-delta ${good ? 'positive' : 'negative'}"), 'цвет отклонения не по good');
    assert.ok(!js.includes("diff >= 0 ? 'positive'"), 'цвет отклонения по знаку diff');
    assert.ok(js.includes('function planWord('), 'нет planWord');
    assert.ok(!js.includes('план ${this.formatPlanShort'), 'подпись «план» зашита в разметку');
});

test('comparison.js: рост списаний красится как ухудшение', () => {
    const js = read('static/js/dashboard/modules/comparison.js');
    assert.ok(/key: 'loyaltyWriteoffs'[^\n]*budget: true/.test(js), 'списания без budget: true');
    assert.ok(js.includes('change.budget ? !grew : grew'), 'топ изменений не зеркалит бюджет');
    assert.ok(js.includes('metric.budget ? diff < 0 : diff > 0'), 'таблица не зеркалит бюджет');
});

console.log('\n--- разметка ---');

test('нижняя таб-панель повторяет вкладки и содержит «Ещё»', () => {
    const html = read('templates/dashboard/base.html');
    const bottom = [...html.matchAll(/class="bt-item[^"]*"[^>]*data-tab="([^"]+)"/g)].map(m => m[1]);
    assert.deepEqual(bottom, ['tab-analytics', 'tab-comparison', 'tab-revenue', 'tab-plans']);
    assert.ok(html.includes('id="bt-more"'), 'нет кнопки «Ещё»');
});

test('шапка фильтров: один контрол, без сегментов и «Сегодня»', () => {
    const html = read('templates/dashboard/base.html');
    // Обязательные части полосы (макет 5a)
    for (const id of ['filter-bar', 'venue-trigger', 'venue-selector', 'period-prev',
                      'period-trigger', 'period-title', 'period-hint', 'period-next',
                      'period-menu', 'venue-menu', 'export-menu', 'fb-backdrop',
                      'period-preset-list', 'period-custom', 'flexi-range-picker']) {
        assert.ok(html.includes(`id="${id}"`), `нет элемента #${id}`);
    }
    // Убранное макетом не должно вернуться
    for (const gone of ['data-granularity', 'period-today', 'period-sublabel',
                        'dashboard-controls', 'control-group-period']) {
        assert.ok(!html.includes(gone), `в разметке осталось «${gone}»`);
    }
});

test('легенда шкал стоит один раз — в строке вкладок', () => {
    const html = read('templates/dashboard/base.html');
    const js = read('static/js/dashboard/modules/analytics.js');
    assert.ok(html.includes('id="tabs-legend"'), 'нет легенды в строке вкладок');
    // Заголовок группы — только название и линия (макет 7a).
    assert.ok(!js.includes('mg-legend'), 'легенда осталась в заголовке группы');
    assert.ok(js.includes('tabs-legend'), 'JS не показывает легенду в строке вкладок');
});

test('в разметке дашборда нет эмодзи', () => {
    // .claude/CLAUDE.md: эмодзи запрещены в коде и интерфейсе.
    const files = [
        'templates/dashboard/base.html',
        'templates/dashboard.html',
        'static/js/dashboard/core/config.js',
        'static/js/dashboard/modules/analytics.js',
        'static/js/dashboard/modules/comparison.js',
        'static/js/dashboard/modules/period_controls.js',
        'static/js/dashboard/core/period_model.js'
    ];
    const emoji = /[\u{1F300}-\u{1FAFF}\u{2705}\u{274C}\u{26A0}\u{2B50}\u{1F4C5}]/u;
    for (const f of files) {
        const hit = read(f).match(emoji);
        assert.equal(hit, null, `${f}: найдено ${hit && hit[0]}`);
    }
});

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed === 0 ? 0 : 1);

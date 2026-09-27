/**
 * ТЕКСТОВЫЕ проверки страницы «Контент-план» (/content-plan) раздела «Гости».
 *
 *     node tests/test_content_plan_render.mjs
 *
 * Проверяется согласованность файлов страницы между собой и с бэкендом:
 * шаблон объявляет узлы, которые ищет JS; JS ходит только в существующие
 * эндпоинты (routes/content_plan.py, слой отзывов — routes/reviews.py);
 * классы, которые JS пишет в разметку, описаны в CSS (своём или hub.css);
 * нет эмодзи и цветов мимо токенов. Такие расхождения не ловятся ни юнит-
 * тестами хранилища, ни глазами на одном экране: страница просто молча не
 * рисует блок или получает 404.
 *
 * ИИ-агент (MCP, 2026-09-27): пометка «ИИ» в таблице, календаре, карточке и
 * окне утверждения; «Почему этот пост» / «Что снять» с автосохранением и
 * пределом как в ядре; фильтр «Только от ИИ» (?origin=agent); «Удалить
 * черновики ИИ» (число и id — из agent_draft сервера, подтверждение);
 * карточка «Бриф для агента» (поля и пределы — из schema сервера, PUT одним
 * полем, сброс несохранённого при уходе, ?brief=1).
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const html = read('templates/content_plan.html');
const css = read('static/guest_hub/content_plan.css');
const hubCss = read('static/guest_hub/hub.css');
const js = read('static/js/guest_hub/content_plan.js');
const common = read('static/js/guest_hub/common.js');
const routes = read('routes/content_plan.py');
const reviewRoutes = read('routes/reviews.py');

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

test('шаблон подключает стили и скрипты с кэш-бастингом, common.js раньше страницы', () => {
    for (const asset of ['static/guest_hub/hub.css', 'static/guest_hub/content_plan.css',
                         'static/js/guest_hub/common.js', 'static/js/guest_hub/content_plan.js']) {
        const re = new RegExp(asset.replace(/[./]/g, (c) => '\\' + c) + '\\?v=\\{\\{ app_version \\}\\}');
        assert.match(html, re, `${asset} без ?v — правки не доедут до браузеров`);
    }
    assert.ok(html.indexOf('guest_hub/hub.css') < html.indexOf('guest_hub/content_plan.css'),
        'стили страницы должны идти после hub.css (при равной специфичности побеждает последний)');
    assert.ok(html.indexOf('js/guest_hub/common.js') < html.indexOf('js/guest_hub/content_plan.js'),
        'common.js (window.GH) должен загружаться раньше скрипта страницы');
});

test('каркас страницы: body, сайдбар, шапка раздела внутри .gh-wrap', () => {
    assert.match(html, /<body class="gh-page gh-scope">/, 'нет классов страницы раздела на body');
    assert.match(html, /\{% include 'shared\/nav\.html' %\}/, 'нет общего сайдбара');
    const wrapAt = html.indexOf('class="gh-wrap');
    const headAt = html.indexOf("{% include 'shared/guest_hub_head.html' %}");
    assert.ok(wrapAt > 0 && headAt > wrapAt, 'шапка раздела подключена не внутри .gh-wrap');
    assert.match(html, /\{% set hub_active = 'content' %\}/, 'не отмечена активная вкладка');
    assert.match(html, /\{% set hub_title = 'Контент-план' %\}/, 'нет заголовка');
    assert.match(html, /\{% set hub_subtitle = 'План публикаций и рассылок на месяц' %\}/, 'нет подзаголовка');
    for (const partial of ['templates/shared/guest_hub_head.html', 'templates/shared/guest_hub_strip.html']) {
        assert.ok(fs.existsSync(path.join(ROOT, partial)), `нет общего шаблона ${partial}`);
    }
});

test('все id, которые ищет JS, объявлены в шаблоне', () => {
    const wanted = new Set();
    for (const m of js.matchAll(/(?:getElementById|byId)\('([^']+)'\)/g)) wanted.add(m[1]);
    assert.ok(wanted.size > 20, `JS ищет подозрительно мало узлов: ${wanted.size}`);
    const missing = [...wanted].filter((id) => !html.includes(`id="${id}"`));
    assert.deepEqual(missing, [], `нет узлов в шаблоне: ${missing.join(', ')}`);
});

// Эндпоинты: собираем из JS выражения вида API + '/materials/' + enc(x) + '/log'
// и сверяем с правилами @content_plan_bp.route(...) (метод тоже, где он виден).
function routeRules(src, bp) {
    const rules = [];
    const re = new RegExp(`@${bp}\\.route\\('([^']+)'(?:,\\s*methods=\\[([^\\]]*)\\])?\\)`, 'g');
    for (const m of src.matchAll(re)) {
        const methods = m[2] ? [...m[2].matchAll(/'(\w+)'/g)].map((x) => x[1]) : ['GET'];
        rules.push({ path: m[1].replace(/<[^>]+>/g, '<x>'), methods });
    }
    return rules;
}
const cpRules = routeRules(routes, 'content_plan_bp');
const rvRules = routeRules(reviewRoutes, 'reviews_bp');

function jsCalls() {
    const calls = [];
    const re = /(?:(?:GH\.api|mutate)\('(\w+)',\s*(?:withMonth\()?)?API((?:\s*\+\s*(?:'[^']*'|enc\([^)]*\)))*)/g;
    for (const m of js.matchAll(re)) {
        let tail = '';
        for (const part of m[2].matchAll(/'([^']*)'|enc\([^)]*\)/g)) tail += part[1] !== undefined ? part[1] : '<x>';
        const pathOnly = ('/api/content-plan' + tail).split('?')[0];
        calls.push({ method: m[1] || null, path: pathOnly, raw: m[0] });
    }
    return calls;
}

test('каждый эндпоинт, который вызывает JS, есть в routes/content_plan.py', () => {
    assert.ok(cpRules.length >= 15, `в routes/content_plan.py найдено мало маршрутов: ${cpRules.length}`);
    const calls = jsCalls();
    assert.ok(calls.length >= 15, `в JS найдено мало вызовов API: ${calls.length}`);
    const bad = [];
    for (const c of calls) {
        // У одного пути может быть несколько правил (GET / PATCH / DELETE).
        const rules = cpRules.filter((r) => r.path === c.path);
        if (!rules.length) { bad.push(`${c.path} (нет маршрута)`); continue; }
        const methods = rules.flatMap((r) => r.methods);
        if (c.method && !methods.includes(c.method)) bad.push(`${c.method} ${c.path} (метод не разрешён)`);
    }
    assert.deepEqual(bad, [], `вызовы мимо бэкенда: ${bad.join('; ')}`);
});

test('нужные спецификации вызовы действительно есть в JS', () => {
    const calls = jsCalls().map((c) => `${c.method || '*'} ${c.path}`);
    const need = [
        'GET /api/content-plan',
        'POST /api/content-plan/materials',
        'PATCH /api/content-plan/materials/<x>',
        'POST /api/content-plan/materials/<x>/placements',
        'PATCH /api/content-plan/placements/<x>',
        'POST /api/content-plan/placements/<x>/action',
        'DELETE /api/content-plan/placements/<x>',
        'POST /api/content-plan/materials/<x>/shift',
        'POST /api/content-plan/materials/<x>/repeat',
        'POST /api/content-plan/materials/<x>/media',
        'DELETE /api/content-plan/materials/<x>/media/<x>',
        'GET /api/content-plan/approve-preview',
        'POST /api/content-plan/approve',
        'POST /api/content-plan/bulk-pause',
        'POST /api/content-plan/bulk',
        'POST /api/content-plan/copy-month',
        'POST /api/content-plan/live-preview',
        'GET /api/content-plan/materials/<x>/log',
        'DELETE /api/content-plan/materials/<x>',
        'GET /api/content-plan/materials/<x>',
        // ИИ-агент (MCP): бриф сети и «Удалить черновики ИИ».
        'GET /api/content-plan/brief',
        'PUT /api/content-plan/brief',
        'POST /api/content-plan/agent-drafts/delete',
    ];
    const missing = need.filter((n) => !calls.includes(n));
    assert.deepEqual(missing, [], `нет вызова: ${missing.join('; ')}`);
});

test('слой отзывов ходит в /api/reviews/daily, который есть в routes/reviews.py', () => {
    assert.match(js, /'\/api\/reviews\/daily\?month='/, 'календарь не запрашивает отзывы по дням');
    assert.ok(rvRules.some((r) => r.path === '/api/reviews/daily' && r.methods.includes('GET')),
        'в routes/reviews.py нет GET /api/reviews/daily');
    const extra = [...js.matchAll(/'(\/api\/[^'?]+)/g)].map((m) => m[1])
        .filter((p) => p !== '/api/content-plan' && p !== '/api/reviews/daily');
    assert.deepEqual(extra, [], `неожиданные адреса API: ${extra.join(', ')}`);
});

test('все запросы идут через GH.api, без прямого fetch и инлайновых обработчиков', () => {
    assert.ok(!/\bfetch\(/.test(js), 'прямой fetch мимо GH.api (ошибки не будут по-русски)');
    assert.ok(!/onclick=|onchange=|oninput=/.test(js + html), 'инлайновый обработчик в разметке');
});

test('все классы, которые JS пишет в разметку, описаны в CSS страницы или hub.css', () => {
    const used = new Set();
    for (const m of js.matchAll(/["'\s.]((?:gh-|is-)[\w-]+)/g)) {
        if (!m[1].endsWith('-')) used.add(m[1]);
    }
    const known = new Set([...(css + hubCss).matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
    const missing = [...used].filter((c) => !known.has(c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
});

test('классы страницы — с префиксом gh-cp-, свои токены цвета не заводятся', () => {
    const own = [...css.matchAll(/\.((?:gh|is)-[\w-]+)/g)].map((m) => m[1])
        .filter((c) => c.startsWith('gh-') && !c.startsWith('gh-cp-'));
    const hubKnown = new Set([...hubCss.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
    const strangers = [...new Set(own)].filter((c) => !hubKnown.has(c));
    assert.deepEqual(strangers, [], `классы без префикса gh-cp-, которых нет в hub.css: ${strangers.join(', ')}`);
    const tokens = [...css.matchAll(/(--gh-[\w-]+)\s*:/g)].map((m) => m[1])
        .filter((t) => t !== '--gh-t' && t !== '--gh-t-ink');
    assert.deepEqual(tokens, [], `страница объявляет свои токены (тёмная тема их не знает): ${tokens.join(', ')}`);
});

test('тон по умолчанию у своих компонентов не перебивает классы тона hub.css', () => {
    // content_plan.css идёт после hub.css: одноклассовый селектор с --gh-t
    // перебил бы .gh-tone-*. Поэтому значения по умолчанию — только в :where().
    for (const m of css.matchAll(/([^{}]+)\{[^}]*--gh-t\s*:/g)) {
        assert.match(m[1].trim(), /^:where\(/, `тон по умолчанию без :where(): ${m[1].trim()}`);
    }
});

test('нет HEX-цветов: только токены hub.css (и в шаблоне, и в JS)', () => {
    for (const [name, src] of [['content_plan.css', css], ['content_plan.js', js], ['content_plan.html', html]]) {
        const strays = [...src.matchAll(/#[0-9A-Fa-f]{3,8}\b/g)].map((m) => m[0]);
        assert.deepEqual(strays, [], `HEX в ${name}: ${strays.join(', ')}`);
    }
    assert.ok(!/style="[^"]*(?:color|background)/.test(html), 'инлайновый цвет в шаблоне');
});

test('нет эмодзи и символов-звёзд в файлах страницы', () => {
    const re = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/u;
    for (const [name, src] of [['html', html], ['css', css], ['js', js]]) {
        const m = src.match(re);
        assert.ok(!m, `в ${name} найден символ ${m && JSON.stringify(m[0])}`);
    }
});

test('клиент не пересчитывает готовность: состояние и сводка приходят с сервера', () => {
    for (const code of ['no_media', 'no_text', 'no_template', 'text_too_long', 'in_past', 'no_audience']) {
        assert.ok(!js.includes(`'${code}'`), `JS проверяет готовность сам (код ${code})`);
    }
    assert.match(js, /display_state/, 'не читается display_state');
    assert.match(js, /display_label/, 'не читается display_label');
    assert.match(js, /\.summary/, 'не читается summary материала');
    assert.match(js, /summary_rules/, 'правила сводки не показываются в подсказке');
    assert.match(js, /readiness_rules/, 'правила готовности не показываются в подсказке');
    // После изменения месяц перечитывается целиком (reload = полоса внимания + load).
    assert.match(js, /function mutate\([\s\S]*?return reload\(/, 'изменение не перечитывает месяц');
    assert.match(js, /function reload\(opts\) \{\s*refreshAttention\(\);\s*return load\(opts\);/,
        'reload должен перечитывать и план, и полосу внимания');
});

test('данные пользователя экранируются, где попадают в разметку', () => {
    const fields = /\+\s*[\w.]+\.(title|display_label|effective_text|base_text|original_name|note|failed_error)\b/;
    const bad = [];
    js.split('\n').forEach((line, i) => {
        if (!line.includes('<')) return;
        const m = line.match(fields);
        if (m && !line.slice(0, m.index + m[0].length).match(/(?:esc|tip)\([^()]*$/)) bad.push(`${i + 1}: ${line.trim()}`);
    });
    assert.deepEqual(bad, [], `без экранирования:\n${bad.join('\n')}`);
    assert.match(js, /function esc\(value\) \{ return GH\.esc\(value\); \}/, 'экранирование не через GH.esc');
});

test('адрес страницы: ?month, ?view, ?open, ?state', () => {
    for (const key of ['month', 'view', 'open', 'state']) {
        assert.match(js, new RegExp(`params\\.get\\('${key}'\\)`), `не читается ?${key}=`);
    }
    for (const s of ['overdue', 'failed', 'incomplete', 'ready', 'scheduled', 'paused']) {
        assert.ok(js.includes(`'${s}'`), `фильтр состояния ${s} не поддержан`);
    }
    assert.match(js, /GH\.setParams\(\{ open: id \}\)/, 'карточка не пишет ?open=');
});

test('тексты спецификации на месте', () => {
    assert.match(html, /Отправка пока не подключена: утверждённые публикации\s+не уходят автоматически\. Когда публикация вышла, отметьте её вручную\./,
        'нет баннера про неподключённую отправку');
    assert.match(js, /При выходе подставляются только данные таплиста; остальной текст не меняется\. ' \+\s*'Если данных нет или они не проверены — публикация остановится\./,
        'нет пояснения к живым данным');
    assert.match(js, /Рассылка через бота добавляется отдельно и никогда не включается выбором всех баров\./,
        'нет оговорки про рассылку бота');
    assert.match(js, /Утверждаются только эти подготовленные материалы\. Незаконченные остаются ' \+\s*'черновиками и не уходят\./,
        'нет текста диалога утверждения');
    assert.match(js, /Изменение снимет утверждение/, 'нет предупреждения при правке утверждённого');
    assert.match(js, /Публикация будет остановлена:/, 'нет итога проверки живых данных');
    for (const label of ['Утвердить готовые', 'Добавить материал', 'Скопировать прошлый месяц', 'Пауза',
                         'Таблица', 'Календарь']) {
        assert.ok(html.includes(label), `нет кнопки «${label}»`);
    }
    for (const label of ['Сдвинуть на N дней', 'Отменить размещения', 'Удалить']) {
        assert.ok(html.includes(label), `в панели массовых действий нет «${label}»`);
    }
    for (const label of ['Бриф для агента', 'Только от ИИ', 'Удалить черновики ИИ']) {
        assert.ok(html.includes(label), `нет «${label}» (поддержка ИИ-агента)`);
    }
    for (const label of ['Почему этот пост', 'Что снять']) {
        assert.ok(js.includes(`'${label}'`), `в карточке нет раздела «${label}»`);
    }
});

test('рассылка бота в диалоге утверждения не отмечена по умолчанию', () => {
    assert.match(js, /data-bot="' \+ esc\(it\.placement_id\) \+ '"' \+\s*\(a\.bots\[it\.placement_id\] \? ' checked' : ''\)/,
        'флажок рассылки должен зависеть только от явного выбора');
    assert.match(js, /confirm_bot: x\.bots > 0/, 'confirm_bot не привязан к отмеченным рассылкам');
    assert.match(js, /S\.approve = \{ data: res \|\| \{\}, bots: \{\} \}/, 'выбор рассылок не сбрасывается при открытии');
});

test('константы страницы объяснены и совпадают со спецификацией', () => {
    assert.match(js, /var AUTOSAVE_MS = 700;/, 'автосохранение не 700 мс');
    assert.match(js, /var CAL_MAX_PILLS = 4;/, 'в клетке календаря не 4 размещения');
    assert.match(js, /var CAL_DENSE_MIN = 3;/, 'метка плотности не от 3 размещений');
    assert.match(js, /var DEFAULT_TIME = '12:00';/, 'время по умолчанию не 12:00');
    const core = read('core/content_plan.py');
    const shift = core.match(/SHIFT_DAYS_MAX = (\d+)/)[1];
    assert.match(js, new RegExp(`var SHIFT_MAX = ${shift};`), `SHIFT_MAX разошёлся с ядром (${shift})`);
    const title = core.match(/TITLE_MAX = (\d+)/)[1];
    assert.match(js, new RegExp(`var TITLE_MAX = ${title};`), `TITLE_MAX разошёлся с ядром (${title})`);
});

test('общий модуль даёт всё, чем пользуется страница', () => {
    const usedGh = new Set([...js.matchAll(/GH\.(\w+)/g)].map((m) => m[1]));
    const missing = [...usedGh].filter((name) => !new RegExp(`GH\\.${name}\\s*=`).test(common));
    assert.deepEqual(missing, [], `в common.js нет: ${missing.join(', ')}`);
});

// ---------------------------------------------------------------- исполнение
// Страница исполняется в vm с заглушкой GH: document.readyState === 'loading',
// поэтому init() не запускается (DOM не нужен), а чистые правила доступны через
// window.__contentPlan. GH.api записывает вызовы и возвращает промис, который
// никогда не выполнится: цепочка «ответ -> перечитать план -> перерисовать»
// не идёт дальше отправки, и проверяется именно то, ЧТО ушло на сервер.
import vm from 'node:vm';

// extra — дополнительные члены заглушки GH (например, confirm для диалогов).
function loadPage(extra = {}) {
    const calls = [];
    const toasts = [];
    const GH = {
        TONES: ['muted', 'warning', 'accent', 'success', 'danger'],
        toneClass: (t) => 'gh-tone-' + t,
        esc: (s) => String(s === null || s === undefined ? '' : s),
        api: (...args) => { calls.push(args); return new Promise(() => {}); },
        toast: (...args) => { toasts.push(args); },
        loadAttention: () => { calls.push(['ATTENTION']); return Promise.resolve(null); },
        plural: (n, one, few, many) => many,
        ...extra,
    };
    const ctx = {
        window: { GH },
        document: { readyState: 'loading', addEventListener() {}, activeElement: null },
        Date, setTimeout, console, Promise,
    };
    vm.createContext(ctx);
    vm.runInContext(js, ctx);
    return { cp: ctx.window.__contentPlan, calls, toasts };
}

// Поле <input> для правил даты/времени: атрибуты, value, validity.
function fakeInput(attrs, value, badInput = false) {
    return {
        attrs, value, validity: { badInput },
        getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    };
}

// Тело функции страницы (от «function name(» до следующей функции того же уровня).
function fnBody(name) {
    const start = js.indexOf(`    function ${name}(`);
    assert.ok(start >= 0, `нет функции ${name}`);
    const next = js.indexOf('\n    function ', start + 10);
    return js.slice(start, next < 0 ? undefined : next);
}

function planWithApproved() {
    return {
        states: [{ key: 'incomplete', label: 'Не хватает данных', tone: 'warning' },
                 { key: 'scheduled', label: 'Запланировано', tone: 'success' }],
        materials: [{
            id: 'm1', month: '2026-10', kind: 'fixed', planned_date: '2026-10-09', media: [],
            placements: [{ id: 'p1', status: 'approved', channel: 'telegram', bar: 'bolshoy',
                           date: '2026-10-11', time: '16:00', display_state: 'scheduled' }],
        }],
    };
}

test('дата с клавиатуры: во время набора ничего не уходит на сервер (регрессия: 8 PATCH на «20102026»)', () => {
    const { cp, calls } = loadPage();
    cp.state.data = planWithApproved();
    cp.state.openId = 'm1';
    const node = fakeInput({ 'data-dt': 'date', 'data-pf': 'date', 'data-pid': 'p1', 'data-fk': 'pd:p1' }, '2026-10-02');
    // Нажатие клавиши только что: change от сегмента дня — это набор, не выбор.
    cp.state.dtKeyAt['pd:p1'] = Date.now();
    cp.dtChange(node);
    assert.equal(calls.length, 0, 'промежуточная дата ушла на сервер во время набора');
    assert.equal(cp.state.dtPending['pd:p1'], true, 'набранное значение не ждёт ухода из поля');
    // Уход из поля / Enter: целая новая дата уходит одним запросом.
    node.value = '2026-10-20';
    cp.dtCommit(node);
    assert.equal(calls.length, 1, `ожидался один запрос, ушло ${calls.length}`);
    assert.equal(calls[0][0], 'PATCH');
    assert.match(calls[0][1], /^\/api\/content-plan\/placements\/p1\?/);
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), { date: '2026-10-20' });
    assert.ok(!cp.state.dtPending['pd:p1'], 'после сохранения значение всё ещё «ждёт»');
});

test('дата: неполная, вне 2020–2100 и прежняя — не отправляются; неполная возвращает сохранённую', () => {
    const { cp, calls, toasts } = loadPage();
    cp.state.data = planWithApproved();
    cp.state.openId = 'm1';
    const attrs = { 'data-dt': 'date', 'data-pf': 'date', 'data-pid': 'p1', 'data-fk': 'pd:p1' };
    const partial = fakeInput(attrs, '', true);
    cp.dtCommit(partial);
    assert.equal(partial.value, '2026-10-11', 'неполная дата не вернулась к сохранённой');
    assert.ok(toasts.some((t) => /не полностью/.test(t[0])), 'нет объяснения про неполную дату');
    cp.dtCommit(fakeInput(attrs, '0202-10-20'));
    cp.dtCommit(fakeInput(attrs, '2026-10-11'));
    assert.equal(calls.length, 0, `ушли запросы: ${JSON.stringify(calls)}`);
    // Стёрто целиком (без badInput) — осознанная очистка: уходит null.
    cp.dtCommit(fakeInput(attrs, ''));
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), { date: null });
});

test('дата: выбор в календаре браузера (без нажатий клавиш) сохраняется сразу', () => {
    const { cp, calls } = loadPage();
    cp.state.data = planWithApproved();
    cp.state.openId = 'm1';
    cp.dtChange(fakeInput({ 'data-dt': 'date', 'data-pf': 'date', 'data-pid': 'p1', 'data-fk': 'pd:p1' }, '2026-10-15'));
    assert.equal(calls.length, 1, 'выбор в календаре не сохранился');
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), { date: '2026-10-15' });
});

test('время: «ЧЧ:ММ:СС» сохраняется как «ЧЧ:ММ»; дата темы — через материал; форма добавления — без запроса', () => {
    const { cp, calls } = loadPage();
    cp.state.data = planWithApproved();
    cp.state.openId = 'm1';
    cp.dtCommit(fakeInput({ 'data-dt': 'time', 'data-pf': 'time', 'data-pid': 'p1', 'data-fk': 'ptm:p1' }, '18:30:00'));
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), { time: '18:30' });
    cp.dtCommit(fakeInput({ 'data-dt': 'date', 'data-mf': 'planned_date', 'data-fk': 'planned_date' }, '2026-10-16'));
    assert.match(calls[1][1], /^\/api\/content-plan\/materials\/m1\?/);
    assert.deepEqual(JSON.parse(JSON.stringify(calls[1][2])), { planned_date: '2026-10-16' });
    cp.dtCommit(fakeInput({ 'data-dt': 'date', 'data-add': 'date', 'data-fk': 'add_date' }, '2026-10-17'));
    assert.equal(calls.length, 2, 'форма добавления не должна слать запрос');
    assert.equal(cp.state.addForm.date, '2026-10-17', 'дата формы добавления не запомнилась');
});

test('дата и время: карточка не перерисовывается во время набора, поля — только через data-dt', () => {
    assert.match(fnBody('renderDrawer'), /if \(dtBusy\(\)\) \{ S\.drawerStale = true; return; \}/,
        'renderDrawer пересобирает поле даты, в котором идёт набор');
    assert.match(fnBody('onDrawerChange'), /if \(isDT\(t\)\) \{ dtChange\(t\); return; \}/,
        'change даты/времени идёт мимо правил сохранения целым значением');
    const pfc = fnBody('placementFieldChange');
    assert.ok(!/pf === 'date'|pf === 'time'/.test(pfc), 'дата/время размещения снова сохраняются на каждый change');
    assert.ok(!/planned_date: t\.value/.test(js), 'дата темы снова сохраняется на каждый change');
    assert.ok(!/<input type="date"(?![^']*data-dt)/.test(js) && !/<input type="time"(?![^']*data-dt)/.test(js),
        'поле даты/времени без data-dt');
    assert.match(fnBody('onDrawerFocusOut'), /if \(S\.dtPending\[fk\]\) \{ dtCommit\(t\); return; \}/,
        'уход из поля не сохраняет набранное');
    assert.match(fnBody('onDrawerKey'), /e\.key === 'Enter'[^\n]*dtCommit\(t\)/, 'Enter не сохраняет дату');
    const core = read('core/content_plan.py');
    const [, ymin, ymax] = core.match(/YEAR_MIN, YEAR_MAX = (\d+), (\d+)/);
    assert.match(js, new RegExp(`var YEAR_MIN = ${ymin};`), 'YEAR_MIN разошёлся с ядром');
    assert.match(js, new RegExp(`var YEAR_MAX = ${ymax};`), 'YEAR_MAX разошёлся с ядром');
});

test('выбор файлов: одно постоянное поле вне карточки (регрессия: файл терялся при перерисовке)', () => {
    const drawerAt = html.indexOf('id="cpDrawer"');
    const drawerEnd = html.indexOf('</aside>', drawerAt);
    const fileAt = html.indexOf('<input type="file" id="cpFile"');
    assert.ok(fileAt > 0, 'нет постоянного поля #cpFile в шаблоне');
    assert.ok(fileAt > drawerEnd, 'поле выбора файлов внутри перерисовываемой карточки');
    assert.ok(!/type="file"/.test(js), 'JS снова рисует <input type="file"> внутри карточки');
    assert.match(js, /el\.file\.addEventListener\('change', onFilePicked\)/, 'нет обработчика постоянного поля');
    assert.match(fnBody('onDrawerClick'), /a === 'pick-files'[\s\S]*?el\.file\.click\(\)/, 'кнопка не открывает выбор');
    assert.match(fnBody('onFilePicked'), /Array\.prototype\.slice\.call\(el\.file\.files/,
        'список файлов не копируется до сброса поля');
});

test('название: пока поле в фокусе, сохранённое сервером не переписывает набранное (регрессия: съеденный пробел)', () => {
    const save = fnBody('saveKey');
    assert.match(save, /if \(fieldFocused\(key\)\) S\.savedVal\[key\] = value;\s*else delete S\.dirty\[key\];/,
        'после сохранения поле в фокусе перерисовывается значением сервера');
    const input = fnBody('onDrawerInput');
    assert.ok(!/normTitle|\.trim\(\)/.test(input), 'название обрезается во время набора');
    assert.match(fnBody('onDrawerFocusOut'), /normTitle\(t\.value\)/, 'название не нормализуется при уходе из поля');
    const { cp } = loadPage();
    assert.equal(cp.normTitle('  Дегустация   осенних элей '), 'Дегустация осенних элей');
});

test('отклонённая правка (400): карточка перерисовывается из последнего ответа сервера', () => {
    assert.match(fnBody('mutate'), /if \(err\.status === 404 \|\| err\.status === 409\) reload\(\);\s*else if \(current\(\)\) renderDrawer\(\);/,
        'после 400 поле показывает отклонённое значение');
});

test('полоса «Требует внимания» перечитывается после каждого успешного изменения', () => {
    assert.match(fnBody('refreshAttention'), /GH\.loadAttention\(\)/, 'refreshAttention не зовёт GH.loadAttention');
    for (const name of ['mutate', 'saveKey', 'approveOne', 'submitApprove', 'runBulk', 'bulkPause', 'submitCopy',
                        'uploadFiles', 'deleteMaterial', 'addMaterial']) {
        assert.match(fnBody(name), /reload\(/, `${name}: после изменения полоса внимания не обновляется`);
    }
});

test('уход со страницы: несохранённое уходит с keepalive', () => {
    assert.match(js, /addEventListener\('pagehide', function \(\) \{\s*S\.keepalive = true;\s*try \{ flushAll\(\); \} finally \{ S\.keepalive = false; \}/,
        'pagehide не отправляет несохранённое с keepalive');
    assert.match(fnBody('saveKey'), /GH\.api\('PATCH', withMonth\(req\.url\), req\.body, apiOpts\(\)\)/,
        'автосохранение текста без параметра keepalive');
    const { cp, calls } = loadPage();
    cp.state.data = planWithApproved();
    cp.state.openId = 'm1';
    cp.state.keepalive = true;
    cp.dtCommit(fakeInput({ 'data-dt': 'date', 'data-pf': 'date', 'data-pid': 'p1', 'data-fk': 'pd:p1' }, '2026-10-21'));
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0][3])), { keepalive: true }, 'запрос ушёл без keepalive');
});

test('сквозной вид ?state= без ?month=: запрос без месяца, чип «Все месяцы», выход в месяц', () => {
    const { cp } = loadPage();
    cp.state.month = '2026-09';
    cp.state.stateFilter = 'overdue';
    assert.equal(cp.listUrl(), '/api/content-plan?month=2026-09');
    cp.state.scope = 'state';
    assert.equal(cp.listUrl(), '/api/content-plan?state=overdue');
    assert.match(js, /S\.scope = !monthGiven && SCOPE_STATES\.indexOf\(S\.stateFilter\) >= 0 && S\.view === 'table' \? 'state' : '';/,
        'сквозной вид не включается по ?state= без ?month=');
    assert.match(fnBody('load'), /if \(S\.scope && data\.scope !== 'state'\)/, 'нет отката, если сервер не знает сквозного вида');
    assert.match(fnBody('renderStateBar'), /Все месяцы · ' \+ esc\(SCOPE_NAMES\[S\.stateFilter\]\)/, 'нет чипа «Все месяцы · …»');
    assert.match(fnBody('switchMonth'), /if \(S\.scope\) \{ leaveScope\(mon, S\.stateFilter\); return; \}/,
        'стрелки месяца не выводят из сквозного вида');
    assert.match(fnBody('setStateFilter'), /if \(S\.scope\) \{ leaveScope\(S\.month, next\); return; \}/,
        'крестик чипа не возвращает план месяца');
    assert.match(fnBody('setView'), /S\.view === 'calendar' && S\.scope\) \{ leaveScope/, 'календарь в сквозном виде');
    assert.match(fnBody('groupKey'), /S\.scope \? m\.date\.slice\(0, 7\)/, 'сквозной вид не группируется по месяцам');
});

test('фильтр состояния в месяце показывает и материалы других месяцев с размещением в этом месяце', () => {
    const { cp } = loadPage();
    const m = { id: 'm8', month: '2026-08', in_month: false,
                placements: [{ id: 'p', bar: 'bolshoy', channel: 'telegram', date: '2026-09-02', display_state: 'overdue' }] };
    cp.state.month = '2026-09';
    cp.state.stateFilter = '';
    assert.equal(cp.inTable(m), false, 'без фильтра состояния чужой материал попал в таблицу');
    cp.state.stateFilter = 'overdue';
    assert.equal(cp.inTable(m), true, 'сводка «Время вышло: 1» ведёт в пустую таблицу');
    m.placements[0].date = '2026-08-30';
    assert.equal(cp.inTable(m), false, 'размещение другого месяца не должно тянуть материал в таблицу');
});

test('вышедшее показывает, что ушло: media_items и пометка снимка', () => {
    const { cp } = loadPage();
    const m = { media: [{ name: 'a.jpg', kind: 'image', url: '/a' }] };
    const snap = { effective_media: ['gone.jpg'], media_items: [{ name: 'gone.jpg', kind: 'image', url: '/api/content-plan/media/gone.jpg' }] };
    assert.equal(cp.placementFiles(m, snap)[0].name, 'gone.jpg', 'файл из снимка не показывается, если его убрали из материала');
    assert.equal(cp.placementFiles(m, { effective_media: ['a.jpg'] })[0].url, '/a', 'нет запасного пути без media_items');
    assert.ok(!/mediaFor\(m, p\.effective_media/.test(fnBody('previewHtml')), 'предпросмотр ищет файлы в material.media');
    assert.match(js, /Так вышло: текст и файлы на момент утверждения/, 'нет пометки снимка');
    assert.match(js, /p\.content_source === 'snapshot'/, 'пометка снимка не привязана к content_source');
    assert.match(js, /данные на сейчас, не на момент выхода/, 'нет пометки для вышедшего живого материала');
});

test('живые данные: предпросмотр размещения передаёт площадку и наличие файлов (предел длины)', () => {
    assert.match(fnBody('maybeLoadPreviewLive'), /channel: p\.channel, has_media: placementFiles\(m, p\)\.length > 0/,
        'проверка шаблона размещения идёт с пределом 4096 вместо предела площадки');
});

test('цвет — по display_state: у каждого состояния свой вид, легенда та же', () => {
    const { cp } = loadPage();
    const states = ['incomplete', 'ready', 'scheduled', 'overdue', 'paused', 'published', 'failed', 'cancelled'];
    const looks = states.map((s) => cp.stateCls(s));
    assert.equal(new Set(looks).size, states.length, `одинаковый вид у разных состояний: ${looks.join(' | ')}`);
    assert.notEqual(cp.stateCls('published'), cp.stateCls('scheduled'));
    assert.notEqual(cp.stateCls('overdue'), cp.stateCls('incomplete'));
    for (const s of states) {
        assert.ok(css.includes(`.gh-cp-sw.gh-cp-st-${s}`), `легенда: нет образца для ${s}`);
        if (s !== 'cancelled') {
            assert.ok(css.includes(`.gh-chip.gh-cp-st-${s}`), `чип: нет вида для ${s}`);
            assert.ok(css.includes(`.gh-cp-pill.gh-cp-st-${s}`), `плашка календаря: нет вида для ${s}`);
        }
    }
    assert.match(js, new RegExp(`var LEGEND_STATES = \\[${states.map((s) => `'${s}'`).join(', ')}\\];`),
        'легенда показывает не все состояния');
    for (const name of ['chipHtml', 'pillHtml', 'legendHtml', 'placementHtml']) {
        const body = fnBody(name);
        assert.match(body, /stateCls\(/, `${name}: цвет не по состоянию`);
        assert.ok(!/toneClass\((?:st|info)\.tone\)/.test(body), `${name}: цвет по тону сервера`);
    }
    assert.match(fnBody('renderTable'), /legendHtml\(\)/, 'у таблицы нет легенды');
    assert.match(fnBody('calbarHtml'), /legendHtml\(\)/, 'у календаря нет легенды');
});

test('подпись состояния: у живого утверждённого — «Шаблон утверждён…», у «Не хватает» — коротко', () => {
    const { cp } = loadPage();
    cp.state.data = planWithApproved();
    assert.equal(cp.stateLabel({ display_state: 'scheduled', display_label: 'Шаблон утверждён, данные — при выходе' }),
        'Шаблон утверждён, данные — при выходе');
    assert.equal(cp.stateLabel({ display_state: 'incomplete', display_label: 'Не хватает: нет фото, нет времени' }),
        'Не хватает данных');
    assert.match(js, /шаблон · данные при выходе/, 'в диалоге утверждения живые строки не помечены');
});

test('загрузка файла: заранее — предупреждение, после — несгораемый тост со списком снятых утверждений', () => {
    assert.match(fnBody('mediaHtml'), /снимет ' \+\s*'утверждение с '/, 'нет предупреждения до загрузки');
    const up = fnBody('uploadFiles');
    assert.match(up, /each\(res && res\.unapproved, function \(id\)/, 'unapproved из ответа не собирается');
    assert.match(up, /'warning', \{ timeout: 0 \}/, 'тост о снятом утверждении исчезает сам');
    assert.match(up, /placementNames\(lastMaterial, unapproved\)/, 'тост не называет размещения');
});

test('календарь: плотность — по материалам, а не по копиям на бары; метка «пост + бот»', () => {
    const { cp } = loadPage();
    const pl = (id, channel, bar, st = 'scheduled') => ({ m: { id }, p: { channel, bar, display_state: st } });
    // Один таплист на четыре бара — одна публикация, не перегрузка.
    const taplist = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'].map((b) => pl('tap', 'telegram', b));
    assert.equal(cp.dayStats(taplist).materials, 1);
    assert.equal(cp.dayStats(taplist).placements, 4);
    assert.equal(cp.dayStats([pl('a', 'telegram', 'bolshoy'), pl('b', 'instagram', 'all'),
                              pl('c', 'telegram', 'ligovskiy'), pl('d', 'telegram', 'bolshoy', 'cancelled')]).materials, 3,
        'отменённое посчитано или разные материалы склеены');
    assert.equal(cp.dayStats([{ m: { id: 't' }, theme: true }]).materials, 1, 'тема дня не посчитана');
    // Пост + рассылка для пересекающейся аудитории.
    assert.equal(cp.dayStats([pl('a', 'telegram', 'bolshoy'), pl('b', 'bot', 'all')]).clash, true);
    assert.equal(cp.dayStats([pl('a', 'instagram', 'all'), pl('b', 'bot', 'ligovskiy')]).clash, true);
    assert.equal(cp.dayStats([pl('a', 'telegram', 'bolshoy'), pl('b', 'bot', 'ligovskiy')]).clash, false,
        'разные бары — разные аудитории');
    assert.equal(cp.dayStats([pl('a', 'telegram', 'bolshoy'), pl('b', 'bot', 'bolshoy', 'cancelled')]).clash, false,
        'отменённая рассылка не пересекается');
    assert.match(fnBody('dayCell'), /var dense = !c\.out && st\.materials >= CAL_DENSE_MIN;/, 'плотность снова по размещениям');
});

test('диалог копирования: правила дат — с сервера (copy_rules), а не свой старый текст «каждая дата по n-му дню»', () => {
    // Регрессия: после исправления copy_month (опорная дата + общий сдвиг, серия —
    // из всех дней) диалог продолжал описывать перенос каждой даты отдельно.
    const { cp } = loadPage();
    cp.state.data = { copy_rules: ['Правило опорной даты', 'Правило серии'] };
    assert.deepEqual([...cp.copyRules()], ['Правило опорной даты', 'Правило серии'],
        'диалог показывает не те правила, что прислал сервер');
    cp.state.data = null;
    const fallback = [...cp.copyRules()];
    assert.ok(fallback.length > 0, 'до загрузки плана диалог остаётся без правил');
    assert.match(fallback.join(' '), /порядок и интервалы размещений материала сохраняются/);
    const body = fnBody('renderCopy');
    assert.match(body, /each\(copyRules\(\), function \(r\)/, 'список правил в диалоге не из copyRules()');
    assert.ok(!/Тот же день недели с тем же номером в месяце/.test(body), 'в диалоге снова своё правило переноса дат');
    assert.match(read('core/content_plan.py'), /'copy_rules': list\(COPY_RULES\)/, 'сервер больше не отдаёт copy_rules');
});

// ---------------------------------------------------------------- ИИ-агент (MCP)

test('ИИ-агент: пометка «ИИ» в таблице, плашках календаря, шапке карточки и окне утверждения', () => {
    const { cp } = loadPage();
    const mark = cp.aiMark({ origin: 'agent' }, true);
    assert.match(mark, /class="gh-cp-ai"/, 'пометка без своего класса');
    assert.match(mark, />ИИ</, 'пометка без текста «ИИ»');
    assert.match(mark, /data-tip=/, 'у пометки в таблице нет пояснения');
    assert.equal(cp.aiMark({ origin: 'human' }, true), '', 'материал людей помечен «ИИ»');
    assert.equal(cp.aiMark({}, true), '', 'материал без origin (старые данные) помечен «ИИ»');
    assert.ok(!/data-tip=/.test(cp.aiMark({ origin: 'agent' }, false)), 'в плашке календаря у метки своя подсказка');
    assert.match(fnBody('rowHtml'), /aiMark\(m, true\)/, 'в строке таблицы нет пометки «ИИ»');
    assert.match(fnBody('pillHtml'), /aiMark\(x\.m, false\)/, 'в плашке календаря нет пометки «ИИ»');
    assert.match(fnBody('drawerHead'), /aiMark\(m, true\)/, 'в шапке карточки нет пометки «ИИ»');
    assert.match(fnBody('apRow'), /aiMark\(g, true\)/, 'в окне утверждения посты агента не помечены');
    assert.match(fnBody('pillTip'), /ИИ: материал создал агент/, 'подсказка плашки не говорит, что это агент');
    assert.ok(css.includes('.gh-cp-ai {'), 'нет стиля пометки «ИИ»');
    // Происхождение ставит сервер: клиент его не шлёт.
    assert.ok(!/origin:\s*['"](?:agent|human)/.test(js.replace(/setOrigin\([^)]*\)/g, '')),
        'клиент отправляет origin материала на сервер');
});

test('ИИ-агент: «Почему этот пост» и «Что снять» — автосохранение полей материала, предел как в ядре', () => {
    assert.match(fnBody('renderDrawer'), /secMain\(m\) \+ secWhy\(m\) \+ secContent\(m\) \+ secShots\(m\)/,
        'разделы агента не на своих местах в карточке');
    assert.match(fnBody('secWhy'), /agentFieldHtml\(m, 'agent_rationale'/, '«Почему этот пост» не из agent_rationale');
    assert.match(fnBody('secShots'), /agentFieldHtml\(m, 'shot_list'/, '«Что снять» не из shot_list');
    const field = fnBody('agentFieldHtml');
    assert.match(field, /var key = 'm:' \+ m\.id \+ ':' \+ field;/, 'ключ автосохранения не материала');
    assert.match(field, /data-save-key="' \+\s*esc\(key\)/, 'поле без автосохранения (data-save-key)');
    assert.match(field, /data-limit="' \+ AGENT_TEXT_MAX/, 'счётчик без предела');
    const core = read('core/content_plan.py');
    const max = core.match(/AGENT_TEXT_MAX = (\d+)/)[1];
    assert.match(js, new RegExp(`var AGENT_TEXT_MAX = ${max};`), `AGENT_TEXT_MAX разошёлся с ядром (${max})`);
    assert.match(core, /MATERIAL_EDITABLE = \([^)]*'agent_rationale', 'shot_list'\)/,
        'ядро не принимает поля агента в правке материала');
});

test('фильтр «Только от ИИ»: ?origin=agent, скрывает материалы людей и в таблице, и в календаре', () => {
    assert.match(js, /params\.get\('origin'\) === ORIGIN_AGENT/, 'не читается ?origin=agent');
    assert.match(fnBody('setOrigin'), /GH\.setParams\(\{ origin: S\.origin \|\| null \}\)/, 'фильтр не пишется в адрес');
    assert.match(fnBody('calendarItems'), /if \(!originMatches\(m\)\) return;/, 'календарь не фильтрует по происхождению');
    assert.match(fnBody('openApprove'), /'&origin=' \+ enc\(S\.origin\)/, '«Утвердить готовые» не учитывает фильтр');
    assert.match(fnBody('filtersActive'), /S\.origin/, 'фильтр не считается активным');
    const { cp } = loadPage();
    const human = { id: 'h', origin: 'human', placements: [] };
    const agent = { id: 'a', origin: 'agent', placements: [] };
    const old = { id: 'o', placements: [] };
    assert.equal(cp.materialVisible(human), true);
    cp.state.origin = 'agent';
    assert.equal(cp.materialVisible(human), false, 'материал людей виден под «Только от ИИ»');
    assert.equal(cp.materialVisible(old), false, 'старый материал (без origin) виден под «Только от ИИ»');
    assert.equal(cp.materialVisible(agent), true, 'материал агента скрыт под «Только от ИИ»');
});

test('«Удалить черновики ИИ»: число из agent_draft сервера, подтверждение, на сервер — ровно эти id', () => {
    const confirms = [];
    const { cp, calls } = loadPage({
        // Синхронный «промис»: подтверждение сразу «да».
        confirm: (opts) => { confirms.push(opts); return { then: (fn) => fn(true) }; },
        monthLabel: (m) => 'Октябрь 2026 (' + m + ')',
    });
    cp.state.month = '2026-10';
    cp.state.data = { materials: [
        { id: 'a1', title: 'Черновик агента', origin: 'agent', in_month: true, agent_draft: true, placements: [] },
        { id: 'a2', title: 'Утверждённый агента', origin: 'agent', in_month: true, agent_draft: false, placements: [] },
        { id: 'a3', title: 'Другой месяц', origin: 'agent', in_month: false, agent_draft: true, placements: [] },
        { id: 'h1', title: 'Черновик людей', origin: 'human', in_month: true, agent_draft: false, placements: [] },
    ] };
    const st = cp.agentStats();
    assert.equal(st.total, 2, 'чип «Только от ИИ» считает не материалы агента этого месяца');
    assert.deepEqual(Array.from(st.drafts, (m) => m.id), ['a1'], 'удалить предлагается не только черновики ИИ месяца');
    cp.deleteAgentDrafts();
    assert.equal(confirms.length, 1, 'удаление без подтверждения');
    assert.match(confirms[0].title, /Удалить черновики ИИ: 1\?/, 'в подтверждении нет числа');
    assert.match(confirms[0].text, /«Черновик агента»/, 'подтверждение не называет материалы');
    assert.equal(confirms[0].danger, true, 'кнопка удаления не опасная');
    const del = calls.filter((c) => c[1] === '/api/content-plan/agent-drafts/delete');
    assert.equal(del.length, 1, `ожидался один запрос удаления, ушло: ${JSON.stringify(calls)}`);
    assert.equal(del[0][0], 'POST');
    assert.deepEqual(JSON.parse(JSON.stringify(del[0][2])), { month: '2026-10', material_ids: ['a1'] });
    // В сквозном виде (все месяцы) удаления по месяцу нет.
    cp.state.scope = 'state';
    cp.deleteAgentDrafts();
    assert.equal(confirms.length, 1, 'в виде «Все месяцы» предложено удаление');
    assert.match(fnBody('deleteAgentDrafts'), /reload\(\)/, 'после удаления план и полоса внимания не перечитываются');
});

test('бриф для агента: поля и пределы — из ответа сервера, PUT шлёт одно поле, сохранение не теряется при уходе', () => {
    const { cp } = loadPage();
    const plain = (x) => JSON.parse(JSON.stringify(x));
    assert.deepEqual(plain(cp.briefBody('s:tone', 'На «вы»')), { sections: { tone: 'На «вы»' } });
    assert.deepEqual(plain(cp.briefBody('b:ligovskiy:hours', '12–02')),
        { sections: { bars: { ligovskiy: { hours: '12–02' } } } });
    assert.deepEqual(plain(cp.briefBody('e', ['Пример'])), { sections: { examples: ['Пример'] } });
    // Подписи, подсказки и пределы — только с сервера (schema), не свои числа.
    assert.match(fnBody('briefBodyHtml'), /each\(schema\.sections, function \(spec\)/, 'разделы брифа не из schema');
    assert.match(fnBody('briefBarsHtml'), /each\(schema\.bars, function \(bar\)/, 'бары брифа не из schema.bars');
    assert.match(fnBody('briefBarsHtml'), /each\(schema\.bar_fields/, 'поля бара не из schema.bar_fields');
    assert.match(fnBody('updateBriefTotal'), /briefSchema\(\)\.total_max/, 'предел всего брифа не из schema');
    assert.ok(!/40000|40 000/.test(js), 'в JS свой предел всего брифа');
    const brief = read('core/content_brief.py');
    for (const name of ['SECTION_TEXT_MAX', 'BAR_FIELD_MAX', 'BRIEF_TOTAL_MAX', 'EXAMPLES_MAX']) {
        assert.match(brief, new RegExp(`^${name} = `, 'm'), `в core/content_brief.py нет ${name}`);
    }
    // Автосохранение: PUT брифа с keepalive на уходе; сброс — вместе с остальными.
    assert.match(fnBody('briefSaveKey'), /GH\.api\('PUT', API \+ '\/brief', briefBody\(key, value\), apiOpts\(\)\)/,
        'поле брифа сохраняется не через PUT /brief с keepalive');
    assert.match(fnBody('flushSavers'), /flushBrief\(\)/, 'несохранённое в брифе теряется при уходе со страницы');
    assert.match(fnBody('onBriefClose'), /flushBrief\(\)/, 'закрытие брифа теряет несохранённое');
    // Карточка брифа — вне .gh-wrap, как карточка материала; открывается кнопкой и ?brief=1.
    const at = html.indexOf('id="cpBriefDrawer"');
    assert.ok(at > html.indexOf('id="cpDrawer"'), 'нет выдвижной карточки брифа');
    assert.match(html, /<aside class="gh-drawer gh-cp-drawer gh-cp-brief" id="cpBriefDrawer" hidden/);
    const acts = html.slice(html.indexOf('class="gh-cp-bar-acts"'), html.indexOf('id="cpPauseBtn"'));
    assert.ok(acts.includes('id="cpBriefBtn"'), 'кнопка «Бриф для агента» не в панели действий');
    assert.match(js, /params\.get\('brief'\) === '1'/, 'не читается ?brief=1');
    assert.match(fnBody('openBrief'), /GH\.openDrawer\(el\.briefDrawer/, 'бриф открывается не выдвижной карточкой');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

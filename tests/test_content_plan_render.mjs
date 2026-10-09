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
 *
 * Отправка (2026-09-28): баннер состояния по delivery месяца; «Каналы и
 * отправка» (выключатели — включение только с подтверждением, адрес канала — те
 * же правила, что parse_chat сервера, поля сохраняются по одному, пояснения
 * свёрнуты в «Как считается»); строка «как ушло» у размещения (ссылка на пост,
 * ошибка, «дошло N из M»), «Отправить сейчас», «Повторить неудавшимся», архив
 * для Instagram; реальный размер аудитории; «Попросить агента» (claude.ai/new?q=,
 * коннектор kultura-content и сценарии раздела); числа пояснений — зеркала
 * констант сервера. Эти проверки исполняют страницу с НАСТОЯЩИМ common.js
 * (даты и склонения — как в браузере).
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
    // data-is-admin — права пользователя для экрана (решает сервер: 403 admin_required).
    assert.match(html, /<body class="gh-page gh-scope" data-is-admin="\{\{ 'true' if current_user and current_user\.is_admin else 'false' \}\}">/,
        'нет классов страницы раздела или флага прав на body');
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
        // Отправка (2026-09-28): каналы, проверка и тест канала, «Отправить сейчас»,
        // размер аудитории, архив для Instagram (ссылка, метод — GET браузера).
        'GET /api/content-plan/channels',
        'PUT /api/content-plan/channels',
        'POST /api/content-plan/channels/check',
        'POST /api/content-plan/channels/test',
        'POST /api/content-plan/publish-now',
        'GET /api/content-plan/audience',
        '* /api/content-plan/materials/<x>/download',
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
    // Баннер отправки рисует JS по delivery месяца; «не подключено» — прежними словами.
    assert.match(js, /Отправка пока не подключена: утверждённые публикации не уходят автоматически\. ' \+\s*'Когда публикация вышла, отметьте её вручную\./,
        'нет текста «отправка не подключена»');
    for (const label of ['Каналы и отправка', 'Попросить агента']) {
        assert.ok(html.includes(label), `нет кнопки «${label}»`);
    }
    assert.match(js, /При выходе подставляются данные таплиста, а \{вступление\} и \{концовка\} — фразы из ' \+\s*'набора, свои на каждую неделю и каждый бар; остальной текст не меняется\. В канал бара пост уходит ' \+\s*'с гифкой из набора\. Если данных нет или они не проверены — публикация остановится\./,
        'нет пояснения к живым данным');
    // 2026-10-09: какой вариант фраз достался бару — под «Как считается» предпросмотра (phrase сервера)
    assert.match(js, /function phraseHow\(m, p\)[\s\S]*?r\.result\.phrase[\s\S]*?howHtml\('phrase-'/,
        'нет пояснения к выбору фраз');
    assert.match(js, /'Например:\\n\{вступление\}\\n\\n\{таплист\}\\n\\n\{концовка\}'/,
        'нет подсказки шаблона таплиста');
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
    assert.match(fnBody('mutate'), /if \(err\.status === 404 \|\| err\.status === 409\) reload\(\);\s*else if \(current\(\) && !isAdminDenied\(err\)\) renderDrawer\(\);/,
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

test('ИИ-агент: пометка «ИИ» — в шапке карточки и окне утверждения; в строках таблицы и плашках её нет', () => {
    const { cp } = loadPage();
    const mark = cp.aiMark({ origin: 'agent' }, true);
    assert.match(mark, /class="gh-cp-ai"/, 'пометка без своего класса');
    assert.match(mark, />ИИ</, 'пометка без текста «ИИ»');
    assert.match(mark, /data-tip=/, 'у пометки в таблице нет пояснения');
    assert.equal(cp.aiMark({ origin: 'human' }, true), '', 'материал людей помечен «ИИ»');
    assert.equal(cp.aiMark({}, true), '', 'материал без origin (старые данные) помечен «ИИ»');
    assert.ok(!/data-tip=/.test(cp.aiMark({ origin: 'agent' }, false)), 'в плашке календаря у метки своя подсказка');
    // Решение владельца 2026-10-04: от агента почти весь план — метка в каждой
    // строке и плашке ничего не различала и съедала место названия.
    assert.ok(!/aiMark\(/.test(fnBody('rowHtml')), 'в строке таблицы снова пометка «ИИ»');
    assert.ok(!/aiMark\(/.test(fnBody('pillHtml')), 'в плашке календаря снова пометка «ИИ»');
    assert.match(fnBody('drawerHead'), /aiMark\(m, true\)/, 'в шапке карточки нет пометки «ИИ»');
    assert.match(fnBody('apRow'), /aiMark\(g, true\)/, 'в окне утверждения посты агента не помечены');
    assert.match(fnBody('pillTip'), /ИИ: материал создал агент/, 'подсказка плашки не говорит, что это агент');
    assert.ok(css.includes('.gh-cp-ai {'), 'нет стиля пометки «ИИ»');
    // Происхождение ставит сервер: клиент его не шлёт.
    assert.ok(!/origin:\s*['"](?:agent|human)/.test(js.replace(/setOrigin\([^)]*\)/g, '')),
        'клиент отправляет origin материала на сервер');
});

test('ИИ-агент: «Почему этот пост» и «Что снять» — свёрнуты в «От агента», автосохранение, предел как в ядре', () => {
    // Порядок карточки (2026-10-04): куда и когда, пост; служебное агента, «Ещё»
    // и история — свёрнутыми разделами.
    assert.match(fnBody('renderDrawer'), /secWhere\(m\) \+ secPost\(m\) \+ secAgent\(m\) \+ secMore\(m\) \+ secLog\(m\)/,
        'разделы карточки не на своих местах');
    const agent = fnBody('secAgent');
    assert.match(agent, /agentFieldHtml\(m, 'agent_rationale'/, '«Почему этот пост» не из agent_rationale');
    assert.match(agent, /agentFieldHtml\(m, 'shot_list'/, '«Что снять» не из shot_list');
    assert.match(agent, /foldHtml\('fold:agent'/, '«От агента» не свёрнут');
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

// ---------------------------------------------------------------- отправка (2026-09-28)

// Страница в vm с НАСТОЯЩИМ common.js (даты, склонения, esc — как в браузере),
// но с подменёнными запросами, тостами и подтверждениями. GH.api записывает вызов
// и возвращает промис, который не выполнится (проверяется, ЧТО ушло на сервер).
// confirm — синхронный «промис» с ответом answer(opts) (по умолчанию «да»).
const plain = (x) => JSON.parse(JSON.stringify(x));
function loadReal({ answer = () => true, copy = true } = {}) {
    const calls = [];
    const toasts = [];
    const confirms = [];
    const ctx = {
        window: {},
        document: { readyState: 'loading', addEventListener() {}, activeElement: null },
        console, setTimeout, clearTimeout, Promise, Date,
    };
    vm.createContext(ctx);
    vm.runInContext(common, ctx);
    const GH = ctx.window.GH;
    GH.api = (...args) => { calls.push(args); return new Promise(() => {}); };
    GH.toast = (...args) => { toasts.push(args); };
    GH.loadAttention = () => { calls.push(['ATTENTION']); return Promise.resolve(null); };
    GH.confirm = (opts) => { confirms.push(opts); const ok = answer(opts); return { then: (fn) => fn(ok) }; };
    GH.copyText = () => Promise.resolve(copy);
    GH.setParams = () => {};
    vm.runInContext(js, ctx);
    return { cp: ctx.window.__contentPlan, GH, calls, toasts, confirms };
}

// delivery месяца «как у сервера» (core/content_channels.delivery_state): всё выключено.
function deliveryFixture(over = {}) {
    const telegram = {};
    for (const bar of ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']) {
        telegram[bar] = { connected: false, chat: '', title: '', reason: 'канал не указан' };
    }
    return {
        enabled: false, bot_configured: true, telegram,
        instagram: { connected: false, reminder_chat: '', reminder_minutes_before: 0, reason: 'не указан чат для напоминаний' },
        bot: { connected: false, enabled: false, subscribers_total: 0, reason: 'рассылки гостям выключены' },
        ...over,
    };
}

test('отправка: баннер по delivery месяца — не подключено / выключено / нет бота / ни одной площадки / что уходит само', () => {
    const { cp } = loadReal();
    const none = cp.deliveryState({ delivery: deliveryFixture() });
    assert.equal(none.mode, 'none');
    assert.match(none.html, /Отправка пока не подключена/);
    assert.equal(none.action, true, 'в «не подключено» нет кнопки «Каналы и отправка»');
    const off = deliveryFixture();
    off.telegram.bolshoy.chat = '@kult_vo';
    assert.equal(cp.deliveryState({ delivery: off }).mode, 'off', 'канал задан, выключатель выключен — не «выключено»');
    const noBot = cp.deliveryState({ delivery: deliveryFixture({ enabled: true, bot_configured: false }) });
    assert.equal(noBot.mode, 'idle');
    assert.match(noBot.html, /бот не настроен/);
    assert.equal(cp.deliveryState({ delivery: deliveryFixture({ enabled: true }) }).mode, 'idle');
    const on = deliveryFixture({ enabled: true });
    on.telegram.bolshoy = { connected: true, chat: '@kult_vo' };
    on.telegram.ligovskiy = { connected: true, chat: '@kult_lig' };
    on.bot = { connected: true, enabled: true, subscribers_total: 124 };
    const st = cp.deliveryState({ delivery: on });
    assert.equal(st.mode, 'on');
    assert.equal(st.action, false);
    assert.match(st.html, /Сами уходят: Telegram — ВО, Лиг; рассылки гостям \(124 подписчика\)\./);
    assert.match(st.html, /Вручную: Telegram — Крем, Вар; Instagram\./);
    const all = deliveryFixture({ enabled: true });
    for (const bar of Object.keys(all.telegram)) all.telegram[bar] = { connected: true, chat: '@x_' + bar };
    assert.match(cp.deliveryState({ delivery: all }).html, /Telegram — все бары/);
    const broken = cp.deliveryState({ delivery: deliveryFixture({ error: 'Файл настроек каналов повреждён: <x>' }) });
    assert.equal(broken.mode, 'error');
    assert.equal(broken.tone, 'danger');
    assert.ok(!broken.html.includes('<x>'), 'текст ошибки сервера не экранирован');
    // Старый ответ сервера — только delivery_connected.
    assert.equal(cp.deliveryState({ delivery_connected: { telegram: false, instagram: false, bot: false } }).mode, 'none');
    assert.equal(cp.deliveryState({ delivery_connected: { telegram: true } }).mode, 'on');
    assert.equal(cp.deliveryState(null), null);
    // Шаблон: баннер рисует JS, его кнопка открывает «Каналы и отправка».
    assert.match(html, /id="cpDelivery" hidden/);
    for (const id of ['cpDeliveryText', 'cpDeliveryBtn']) assert.ok(html.includes(`id="${id}"`), `нет #${id}`);
    assert.match(fnBody('renderChrome'), /renderDelivery\(\)/, 'баннер не перерисовывается');
    assert.match(js, /el\.deliveryBtn\.addEventListener\('click', openChannels\)/);
});

test('отправка: адрес канала — те же правила, что parse_chat на сервере; поле сохраняется одним PUT', () => {
    const { cp, calls } = loadReal();
    assert.equal(cp.normChat(' https://t.me/kult_vo/ '), '@kult_vo');
    assert.equal(cp.normChat('www.t.me/s/kult_vo'), '@kult_vo');
    assert.equal(cp.normChat('kult_vo'), '@kult_vo');
    assert.equal(cp.normChat('@kult_vo'), '@kult_vo');
    assert.equal(cp.normChat('-1001234567890'), '-1001234567890');
    for (const good of ['@kult_vo', '-1001234567890', '123456789', '']) assert.equal(cp.chatValid(good), true, good);
    for (const bad of ['@kult', '@kult_', '@1kult', 't.me/+AbCdEf', 'https://t.me/joinchat/xyz', 'kult vo']) {
        assert.equal(cp.chatValid(cp.normChat(bad)), false, `принят неверный адрес ${bad}`);
    }
    assert.match(plain(cp.chanValue('tg:bolshoy', 't.me/+AbCd')).why, /Пригласительная ссылка не подходит/);
    assert.deepEqual(plain(cp.chanValue('tg:bolshoy', 'https://t.me/kult_vo')), { ok: true, value: '@kult_vo' });
    assert.deepEqual(plain(cp.chanBody('tg:ligovskiy', '@kult_lig')), { telegram: { ligovskiy: { chat: '@kult_lig' } } });
    assert.deepEqual(plain(cp.chanBody('ig:chat', '123456789')), { instagram: { reminder_chat: '123456789' } });
    assert.deepEqual(plain(cp.chanBody('ig:min', 30)), { instagram: { reminder_minutes_before: 30 } });
    // Правила имени и пределы — зеркала core/content_channels.py.
    const channels = read('core/content_channels.py');
    const pyName = channels.match(/_USERNAME_RE = re\.compile\(r'\^(.+?)\\Z'\)/)[1];
    const jsName = js.match(/var CHAT_NAME_RE = \/\^(.+?)\$\/;/)[1];
    assert.equal(jsName, pyName, 'правило имени канала разошлось с parse_chat сервера');
    const max = Number(channels.match(/REMINDER_MINUTES_MAX = (\d+)/)[1]);
    assert.match(js, new RegExp(`var REMINDER_MAX_MIN = ${max};`), 'предел «минут заранее» разошёлся с сервером');
    assert.deepEqual(plain(cp.chanValue('ig:min', String(max))), { ok: true, value: max });
    for (const bad of [String(max + 1), '1.5', '-1', 'полчаса']) assert.equal(cp.chanValue('ig:min', bad).ok, false, bad);
    // Сохранение: неверное — не уходит; то же, что сохранено, — не уходит; верное — один PUT.
    cp.state.chan = { data: { channels: { telegram: { bolshoy: { chat: '@kult_vo' } }, instagram: {}, bot: {} } },
                      busy: {}, tests: {} };
    cp.state.chanDirty['tg:bolshoy'] = 't.me/+invite';
    cp.chanSave('tg:bolshoy');
    assert.ok(cp.state.chanErr['tg:bolshoy'], 'неверный адрес без объяснения');
    cp.state.chanDirty['tg:bolshoy'] = 'https://t.me/kult_vo';
    cp.chanSave('tg:bolshoy');
    assert.equal(calls.length, 0, `ушли запросы: ${JSON.stringify(calls)}`);
    cp.state.chanDirty['tg:bolshoy'] = 't.me/kult_vo_new';
    cp.chanSave('tg:bolshoy');
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], 'PUT');
    assert.equal(calls[0][1], '/api/content-plan/channels');
    assert.deepEqual(plain(calls[0][2]), { telegram: { bolshoy: { chat: '@kult_vo_new' } } });
    // Поля сохраняются при уходе из поля, закрытии карточки и уходе со страницы.
    assert.match(fnBody('onChanChange'), /if \(key\) \{ chanSave\(key\); return; \}/);
    assert.match(fnBody('flushAll'), /flushChannels\(\)/, 'несохранённый адрес теряется при уходе со страницы');
    assert.match(fnBody('onChannelsClose'), /flushChannels\(\)/, 'несохранённый адрес теряется при закрытии');
});

test('отправка: главный выключатель и рассылки — включение только после подтверждения, выключение сразу', () => {
    let answer = false;
    const { cp, calls, confirms } = loadReal({ answer: () => answer });
    cp.state.chan = { data: { channels: { enabled: false, telegram: {}, instagram: {}, bot: {} }, token_source: 'taplist' },
                      busy: {}, tests: {} };
    const puts = () => calls.filter((c) => c[0] === 'PUT');
    const box = { checked: true };
    cp.setAutoSend(true, box);
    assert.equal(confirms.length, 1, 'включение без подтверждения');
    assert.match(confirms[0].title, /Включить автоматическую отправку/);
    assert.equal(box.checked, false, 'после отказа выключатель остался включённым');
    assert.equal(puts().length, 0, 'отправка включена без согласия');
    answer = true;
    cp.setAutoSend(true, { checked: true });
    assert.equal(puts().length, 1);
    assert.equal(puts()[0][1], '/api/content-plan/channels');
    assert.deepEqual(plain(puts()[0][2]), { enabled: true });
    // Хвост «Время вышло» при включении сам не уходит — так и сказано.
    assert.match(confirms[1].text, /Публикации, время которых уже прошло .*сами не уйдут/s);
    cp.setAutoSend(false, { checked: false });
    assert.equal(confirms.length, 2, 'выключение (безопасное) требует подтверждения');
    assert.deepEqual(plain(puts()[1][2]), { enabled: false });
    cp.setBotSend(true, { checked: true });
    assert.equal(confirms.length, 3);
    assert.match(confirms[2].title, /Включить рассылки гостям/);
    assert.deepEqual(plain(puts()[2][2]), { bot: { enabled: true } });
    cp.setBotSend(false, { checked: false });
    assert.deepEqual(plain(puts()[3][2]), { bot: { enabled: false } });
    // Кнопки подписки и отзывов в гостевом боте — свой выключатель (bot.signup), отдельно от рассылок.
    answer = false;
    const signupBox = { checked: true };
    cp.setBotSignup(true, signupBox);
    assert.equal(confirms.length, 4, 'кнопки в боте показаны гостям без подтверждения');
    assert.equal(signupBox.checked, false);
    assert.equal(puts().length, 4);
    answer = true;
    cp.setBotSignup(true, { checked: true });
    assert.deepEqual(plain(puts()[4][2]), { bot: { signup: true } });
    cp.setBotSignup(false, { checked: false });
    assert.deepEqual(plain(puts()[5][2]), { bot: { signup: false } });
    const botHtml = fnBody('chanBotHtml');
    assert.match(botHtml, /switchHtml\('bot', on, 'Рассылки гостям через бота'\)/);
    assert.match(botHtml, /switchHtml\('signup', signup, 'Кнопки подписки и отзывов в боте'\)/);
    assert.match(js, /Гости увидят в ' \+ GUEST_BOT \+ ' кнопки «Подписаться на новости» и «Оставить отзыв»\. ' \+\s*'Включайте после того, как проверили тексты\./,
        'нет подсказки к кнопкам подписки и отзывов');
    assert.match(js, /var GUEST_BOT = '@kult_taplist_bot';/);
    // Проверка и тест канала — через сервер; тестовое сообщение видят подписчики — с подтверждением.
    assert.match(fnBody('checkChannel'), /GH\.api\('POST', API \+ '\/channels\/check', \{ bar: bar \}\)/);
    assert.match(fnBody('testChannel'), /GH\.confirm\(/);
    assert.match(fnBody('testChannel'), /GH\.api\('POST', API \+ '\/channels\/test', \{ bar: bar \}\)/);
});

test('отправка: «Отправить сейчас» — только утверждённое на подключённой площадке, с подтверждением', () => {
    const { cp, calls, confirms } = loadReal();
    const d = deliveryFixture({ enabled: true });
    d.telegram.bolshoy = { connected: true, chat: '@kult_vo' };
    cp.state.data = { now: '2026-10-09T15:00', today: '2026-10-09', delivery: d, materials: [] };
    const p = { id: 'p1', status: 'approved', channel: 'telegram', bar: 'bolshoy', date: '2026-10-09', time: '16:00' };
    assert.equal([...cp.actionList(p)][0], 'send_now', 'нет «Отправить сейчас» у утверждённого');
    cp.sendNow({ id: 'm1' }, p);
    assert.equal(confirms.length, 1, 'отправка без подтверждения');
    assert.match(confirms[0].text, /@kult_vo/, 'подтверждение не называет канал');
    const sent = calls.filter((c) => /^\/api\/content-plan\/publish-now/.test(c[1]));
    assert.equal(sent.length, 1);
    assert.equal(sent[0][0], 'POST');
    assert.deepEqual(plain(sent[0][2]), { placement_id: 'p1' });
    for (const [why, q] of [['площадка не подключена', { ...p, bar: 'ligovskiy' }],
                            ['не утверждено', { ...p, status: 'draft' }],
                            ['уже отправляется', { ...p, delivery: { state: 'sending', started_at: '2026-10-09T14:58' } }],
                            ['отправка зависла — статус неизвестен', { ...p, delivery: { state: 'sending', started_at: '2026-10-09T14:00' } }],
                            ['в очереди', { ...p, delivery: { state: 'queued', retry_at: '2026-10-09T14:59' } }]]) {
        assert.ok(![...cp.actionList(q)].includes('send_now'), `«Отправить сейчас» при: ${why}`);
    }
    cp.state.data.delivery = deliveryFixture();
    assert.ok(![...cp.actionList(p)].includes('send_now'), '«Отправить сейчас» при выключенной отправке');
});

test('отправка: рассылка дошла не всем — «дошло N из M» и «Повторить неудавшимся» (только им, с подтверждением)', () => {
    const { cp, calls, confirms } = loadReal();
    cp.state.data = { now: '2026-10-09T18:00', today: '2026-10-09', delivery: deliveryFixture(), materials: [] };
    const p = { id: 'p9', status: 'published', channel: 'bot', bar: 'all', published_by: 'бот',
                published_at: '2026-10-09T16:00', display_label: 'Вышло: дошло 95 из 100',
                delivery: { state: 'partial', stats: { total: 100, sent: 95, failed: 3, blocked: 2, unsubscribed: 0, unknown: 0 } } };
    assert.equal(cp.canRetryFailed(p), true);
    assert.ok([...cp.actionList(p)].includes('retry_failed'));
    const line = cp.deliveryHtml({ id: 'm1' }, p);
    assert.match(line, /Рассылка ушла 9 октября, 16:00: дошло 95 из 100 · не дошло: 3 · заблокировали бота: 2/);
    cp.placementAction({ id: 'm1' }, p, 'retry_failed');
    assert.equal(confirms.length, 1, 'повтор рассылки без подтверждения');
    assert.match(confirms[0].text, /только 3 подписчикам/);
    const act = calls.filter((c) => /\/placements\/p9\/action/.test(c[1]));
    assert.equal(act.length, 1);
    assert.deepEqual(plain(act[0][2]), { action: 'retry_failed' });
    // Повторять некому (только заблокировавшие) или повтор уже в очереди — кнопки нет.
    assert.equal(cp.canRetryFailed({ ...p, delivery: { state: 'partial', stats: { total: 100, sent: 98, failed: 0, blocked: 2 } } }), false);
    assert.equal(cp.canRetryFailed({ ...p, delivery: { state: 'queued', retry_at: '2026-10-09T17:59', stats: p.delivery.stats } }), false);
    // «Повторить отправку» после ошибки — тоже с подтверждением (уйдёт в ближайшую минуту).
    cp.placementAction({ id: 'm1' }, { id: 'p8', status: 'failed', channel: 'telegram', bar: 'bolshoy' }, 'retry');
    assert.equal(confirms.length, 2);
    assert.deepEqual(plain(calls.filter((c) => /\/placements\/p8\/action/.test(c[1]))[0][2]), { action: 'retry' });
});

test('отправка: строка «как ушло» — ссылка на пост, ошибка целиком и экранирована, очередь, Instagram', () => {
    const { cp } = loadReal();
    cp.state.data = { now: '2026-10-09T18:00', today: '2026-10-09', delivery: deliveryFixture(), materials: [] };
    const pub = { id: 'p1', status: 'published', channel: 'telegram', bar: 'bolshoy', published_by: 'бот',
                  published_at: '2026-10-09T16:00', post_url: 'https://t.me/kult_vo/42',
                  delivery: { state: 'sent', chat: '@kult_vo', message_ids: [42] } };
    const line = cp.deliveryHtml({}, pub);
    assert.match(line, /Вышло автоматически 9 октября, 16:00/);
    assert.match(line, /href="https:\/\/t\.me\/kult_vo\/42" target="_blank" rel="noopener noreferrer"/);
    const priv = cp.deliveryHtml({}, { ...pub, post_url: null, delivery: { state: 'sent', chat: '-1001234567890', message_ids: [42] } });
    assert.ok(!/href=/.test(priv), 'ссылка на пост закрытого канала');
    assert.match(priv, /закрытый канал/);
    assert.equal(cp.postLink('@kult_vo', 42), 'https://t.me/kult_vo/42');
    assert.equal(cp.postLink('-1001234567890', 42), '');
    assert.equal(cp.isAutoPublished({ ...pub, published_by: 'anna', delivery: null }), false, 'отметка человека — «автоматически»');
    const failed = cp.deliveryHtml({}, { id: 'p2', status: 'failed', channel: 'telegram', bar: 'bolshoy',
                                         failed_error: 'Бот не <админ> канала' });
    assert.match(failed, /Ошибка отправки:<\/b> Бот не &lt;админ&gt; канала/);
    const sending = cp.deliveryHtml({}, { id: 'p3', status: 'approved', channel: 'telegram', bar: 'bolshoy',
                                          delivery: { state: 'sending', started_at: '2026-10-09T17:58' } });
    assert.match(sending, /Отправляется с 9 октября, 17:58/);
    const queued = cp.deliveryHtml({}, { id: 'p4', status: 'approved', channel: 'bot', bar: 'all',
                                         delivery: { state: 'queued', retry_at: '2026-10-09T17:59' } });
    assert.match(queued, /В очереди на отправку/);
    assert.equal(cp.inFlight({ delivery: { state: 'sending', started_at: '2026-10-09T17:40' } }), false,
        'отправка дольше 10 минут считается идущей');
    const ig = { id: 'p5', status: 'approved', channel: 'instagram', bar: 'all' };
    assert.match(cp.deliveryHtml({}, { ...ig, delivery: { state: 'reminded', reminded_at: '2026-10-09T15:30' } }),
        /Напоминание отправлено 9 октября, 15:30/);
    // Что случилось — на бейдже (подпись сервера), в строке — что делать.
    assert.match(cp.deliveryHtml({}, { ...ig, delivery: { state: 'reminder_failed', error: 'чат не найден' } }),
        /Напоминание не ушло: выложите пост по плану сами и отметьте выход или повторите кнопкой «Напомнить сейчас»/);
    assert.match(cp.deliveryHtml({}, ig), /Напоминания не настроены/);
    // Instagram выкладывают руками: у утверждённого — архив с подписями и файлами.
    assert.match(fnBody('actionButtons'), /p\.channel === 'instagram'[\s\S]*?Скачать для Instagram/);
    assert.match(fnBody('downloadUrl'), /API \+ '\/materials\/' \+ enc\(m\.id\) \+ '\/download'/);
});

test('аудитория рассылки: реальный размер (размещение, ответ месяца, /audience), без «бот не подключён»', () => {
    const { cp, calls } = loadReal();
    cp.state.data = { materials: [], audiences: [
        { key: 'bot_all', name: 'Все подписчики бота', needs_bar: false, size: 124, size_note: 'n' },
        { key: 'bot_bar', name: 'Подписчики, выбравшие бар', needs_bar: true, size: null, size_by_bar: { ligovskiy: 31 } },
        { key: 'bot_recent_30', name: 'Были за 30 дней', needs_bar: false, size: 12 },
    ] };
    assert.equal(cp.sizeText(cp.audienceSize('bot_all', 'all', { size: 7 })), '7 подписчиков', 'размер размещения не главный');
    assert.equal(cp.sizeText(cp.audienceSize('bot_all', 'all', null)), '124 подписчика');
    assert.equal(cp.sizeText(cp.audienceSize('bot_bar', 'ligovskiy', null)), '31 подписчик');
    assert.equal(calls.length, 0, 'запрос размера, который уже есть в ответе месяца');
    assert.equal(cp.sizeText(cp.audienceSize('bot_recent_30', 'bolshoy', null)), 'считаю…');
    assert.equal(calls.length, 1);
    assert.equal(calls[0][1], '/api/content-plan/audience?segment=bot_recent_30&bar=bolshoy');
    cp.audienceSize('bot_recent_30', 'bolshoy', null);
    assert.equal(calls.length, 1, 'повторный запрос той же аудитории');
    assert.equal(cp.sizeText(null), 'неизвестно');
    assert.ok(!/бот не подключён/i.test(js), 'осталась подпись «бот не подключён»');
    assert.match(fnBody('renderApprove'), /sizeText\(audienceSize\(it\.audience\.segment, it\.bar, it\.audience\)\)/,
        'окно утверждения показывает не реальный размер');
    assert.match(fnBody('approveOne'), /audienceReady\(/, 'подтверждение рассылки не ждёт размер аудитории');
});

test('«Как считается»: пояснения отправки свёрнуты (details без open), у каждого блока свои', () => {
    for (const name of ['chanMainHtml', 'chanTelegramHtml', 'chanInstagramHtml', 'chanBotHtml']) {
        assert.match(fnBody(name), /howHtml\('ch:/, `${name}: нет «Как считается»`);
    }
    const how = fnBody('howHtml');
    assert.match(how, /<details class="gh-cp-how" data-how="' \+ esc\(key\) \+ '"' \+ \(S\.howOpen\[key\] \? ' open' : ''\)/,
        '«Как считается» раскрыт по умолчанию или сворачивается при перерисовке');
    assert.match(how, /<summary>Как считается<\/summary>/);
    assert.match(js, /document\.addEventListener\('toggle', function \(e\)/, 'раскрытое не запоминается');
    assert.match(fnBody('audienceNote'), /howHtml\(howKey/, 'пояснение размера аудитории не свёрнуто');
    assert.match(fnBody('chanTelegramHtml'), /администратором канала бара с правом «Публикация сообщений»/,
        'не сказано, что нужно для отправки в канал');
    for (const sel of ['.gh-cp-how > summary', '.gh-cp-how[open] > summary::before', '.gh-cp-how-in']) {
        assert.ok(css.includes(sel), `нет стиля ${sel}`);
    }
});

test('«Каналы и отправка»: выдвижная карточка, кнопки в ряду действий, ?channels=1', () => {
    assert.match(html, /<aside class="gh-drawer gh-cp-drawer gh-cp-chan" id="cpChanDrawer" hidden/);
    assert.ok(html.indexOf('id="cpChanDrawer"') > html.indexOf('id="cpBriefDrawer"'), 'карточка каналов внутри страницы');
    const acts = html.slice(html.indexOf('class="gh-cp-bar-acts"'), html.indexOf('id="cpPauseBtn"'));
    for (const id of ['cpBriefBtn', 'cpAgentBtn', 'cpChanBtn', 'cpCopyBtn']) {
        assert.ok(acts.includes(`id="${id}"`), `#${id} не в ряду действий`);
    }
    assert.match(js, /params\.get\('channels'\) === '1'/, 'не читается ?channels=1');
    assert.match(fnBody('openChannels'), /GH\.openDrawer\(el\.chanDrawer/);
    assert.match(fnBody('openChannels'), /GH\.api\('GET', API \+ '\/channels'\)|loadChannels\(\)/);
    assert.match(fnBody('loadChannels'), /GH\.api\('GET', API \+ '\/channels'\)/);
    // Кнопки — пункты двух меню: «ИИ-агент» (бриф, задания) и «Ещё» (каналы, копия
    // месяца, пауза); на телефоне меню — две кнопки поровну во всю ширину.
    const more = html.slice(html.indexOf('id="cpMoreMenu"'), html.indexOf('id="cpPauseMenu"'));
    for (const id of ['cpChanBtn', 'cpCopyBtn', 'cpPauseBtn']) assert.ok(more.includes(`id="${id}"`), `#${id} не в меню «Ещё»`);
    const agentMenu = html.slice(html.indexOf('id="cpAgentMenu"'), html.indexOf('id="cpMoreBtn"'));
    for (const id of ['cpAgentTasks', 'cpBriefBtn', 'cpOriginBtn', 'cpAgentDelBtn']) {
        assert.ok(agentMenu.includes(`id="${id}"`), `#${id} не в меню «ИИ-агент»`);
    }
    assert.match(css, /\.gh-cp-bar-acts \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
});

test('«Попросить агента»: три задания, Claude в новой вкладке с текстом, копия в буфер, подсказка про коннектор', () => {
    const { cp } = loadReal();
    const tasks = [...cp.agentTasks('2026-12-15')];
    assert.deepEqual(tasks.map((t) => t.key), ['plan', 'week', 'reviews']);
    assert.equal(tasks[0].label, 'План на январь 2027', 'следующий месяц после декабря — январь следующего года');
    assert.deepEqual(tasks.slice(1).map((t) => t.label), ['Проверить неделю', 'Разобрать отзывы']);
    const scenarios = ['content_plan_month', 'content_review_week', 'content_reviews_digest'];
    tasks.forEach((t, i) => {
        assert.ok(t.url.startsWith('https://claude.ai/new?q='), `${t.key}: не claude.ai/new?q=`);
        const text = decodeURIComponent(t.url.slice('https://claude.ai/new?q='.length));
        assert.equal(text, t.text, `${t.key}: в адресе не тот текст`);
        assert.match(text, /kultura-content/, `${t.key}: не назван коннектор`);
        assert.ok(text.includes(scenarios[i]), `${t.key}: не назван сценарий ${scenarios[i]}`);
        assert.ok(text.length <= 300, `${t.key}: задание длиннее 300 знаков`);
    });
    assert.match(tasks[0].text, /month=2027-01/);
    assert.match(tasks[0].text, /ничего не утверждай/);
    const mcpContent = read('core/mcp/tools/content.py');
    for (const s of scenarios) assert.match(mcpContent, new RegExp(`name='${s}'`), `нет сценария ${s} в MCP`);
    const menu = fnBody('renderAgentMenu');
    assert.match(menu, /target="_blank" ' \+\s*'rel="noopener noreferrer"/, 'задание открывается не в новой вкладке');
    assert.match(menu, /MCP_ADMIN_URL/, 'нет ссылки на «Доступ агентов»');
    assert.match(js, /var MCP_ADMIN_URL = '\/admin\/mcp';/);
    assert.match(read('routes/mcp.py'), /\/admin\/mcp/, 'нет страницы /admin/mcp');
    assert.match(fnBody('onAgentMenuClick'), /GH\.copyText\(task\.text\)/, 'задание не копируется в буфер');
    assert.match(js, /el\.agentBtn\.addEventListener\('click', function \(\) \{ renderAgentMenu\(\); GH\.toggleMenu\(el\.agentMenu, el\.agentBtn\); \}\)/);
});

test('отправка: числа в пояснениях — зеркала констант сервера', () => {
    const core = read('core/content_plan.py');
    const grace = core.match(/DELIVERY_GRACE_MINUTES = (\d+)/)[1];
    const stale = core.match(/SENDING_STALE_MINUTES = (\d+)/)[1];
    assert.match(js, new RegExp(`var PUBLISH_GRACE_MIN = ${grace};`), 'GRACE разошёлся с ядром');
    assert.match(js, new RegExp(`var SENDING_STALE_MIN = ${stale};`), 'порог зависшей отправки разошёлся с ядром');
    assert.match(core, /PUBLISHED_BY_BOT = 'бот'/);
    assert.match(js, /var AUTO_PUBLISHER = 'бот';/, 'подпись отправителя разошлась с ядром');
    const publisher = read('core/content_publisher.py');
    const rate = publisher.match(/^BOT_RATE_PER_SEC = (\d+)/m)[1];
    assert.match(js, new RegExp(`var BOT_RATE_PER_SEC = ${rate};`), 'скорость рассылки разошлась с отправщиком');
});

// ------------------------------------------ права: выпуск наружу — только администратор

// Утверждённое в подключённый канал, ошибка, пауза, готовый черновик — у каждого
// своя кнопка «только администратор».
function adminFixture(cp) {
    const d = deliveryFixture({ enabled: true });
    d.telegram.bolshoy = { connected: true, chat: '@kult_vo' };
    d.bot = { connected: true, enabled: true, subscribers_total: 7 };
    cp.state.data = { now: '2026-10-09T15:00', today: '2026-10-09', delivery: d, materials: [] };
    const base = { channel: 'telegram', bar: 'bolshoy', date: '2026-10-09', time: '16:00' };
    return {
        approved: { ...base, id: 'pa', status: 'approved' },
        failed: { ...base, id: 'pf', status: 'failed', failed_error: 'нет права' },
        paused: { ...base, id: 'pp', status: 'paused' },
        ready: { ...base, id: 'pr', status: 'draft', ready: true },
        partial: { id: 'pb', channel: 'bot', bar: 'all', status: 'published', published_by: 'бот',
                   delivery: { state: 'partial', stats: { total: 10, sent: 8, failed: 2, blocked: 0 } } },
    };
}
// <button ... data-act="pl-<action>" ...> из разметки действий.
const buttonOf = (htmlText, action) => (htmlText.match(new RegExp(`<button[^>]*data-act="pl-${action}"[^>]*>`)) || [''])[0];

test('права: не администратору кнопки выпуска наружу выключены с подсказкой «Только администратор»', () => {
    const { cp } = loadReal();
    const f = adminFixture(cp);
    const cases = [['approved', 'send_now'], ['failed', 'retry'], ['paused', 'resume'], ['ready', 'approve'],
                   ['partial', 'retry_failed']];
    for (const [key, action] of cases) {
        const admin = buttonOf(cp.actionButtons({ id: 'm1' }, f[key]), action);
        assert.ok(admin, `${action}: нет кнопки у администратора`);
        assert.ok(!/aria-disabled/.test(admin), `${action}: у администратора кнопка выключена`);
    }
    cp.state.isAdmin = false;
    for (const [key, action] of cases) {
        const btn = buttonOf(cp.actionButtons({ id: 'm1' }, f[key]), action);
        assert.match(btn, /aria-disabled="true"/, `${action}: не выключена не администратору`);
        assert.match(btn, /data-admin="1"/, `${action}: нажатие не объясняется`);
        assert.match(btn, /data-tip="Только администратор"/, `${action}: нет подсказки`);
    }
    // Пауза, отмена, отметка выхода — не выпуск наружу: остаются.
    for (const action of ['pause', 'cancel', 'mark_published']) {
        assert.ok(!/aria-disabled/.test(buttonOf(cp.actionButtons({ id: 'm1' }, f.approved), action)),
            `${action} выключена не администратору`);
    }
    assert.match(js, /var ADMIN_ONLY_ACTIONS = \['approve', 'send_now', 'retry', 'retry_failed', 'resume'\];/);
    // Флаг — из data-is-admin на body; нажатие на выключенную кнопку объясняет тост.
    assert.match(js, /getAttribute\('data-is-admin'\)/, 'флаг прав не читается');
    assert.match(fnBody('onDrawerClick'), /aria-disabled[\s\S]*?adminBlocked\(\)/);
    assert.match(fnBody('renderChrome'), /el\.approveBtn\.setAttribute\('aria-disabled', 'true'\)/,
        '«Утвердить готовые» не выключается не администратору');
    assert.match(fnBody('renderPauseMenu'), /menuItem\('data-pause', 'resume\|all', 'Вся сеть', 'все бары и сеть', false, off\)/,
        '«Снять паузу» в меню паузы не выключается не администратору');
});

test('права: не администратору ничего не уходит на сервер, пауза и отмена — можно', () => {
    const { cp, calls, confirms, toasts } = loadReal();
    const f = adminFixture(cp);
    cp.state.isAdmin = false;
    cp.state.chan = { data: { channels: { enabled: false, telegram: { bolshoy: { chat: '@kult_vo' } }, instagram: {}, bot: {} },
                              token_source: 'taplist' }, busy: {}, tests: {} };
    cp.sendNow({ id: 'm1' }, f.approved);
    cp.placementAction({ id: 'm1' }, f.failed, 'retry');
    cp.placementAction({ id: 'm1' }, f.paused, 'resume');
    cp.placementAction({ id: 'm1' }, f.partial, 'retry_failed');
    cp.approveOne({ id: 'm1' }, f.ready);
    cp.openApprove();
    cp.bulkPause('resume', 'all');
    const box = { checked: true };
    cp.setAutoSend(true, box);
    cp.setBotSend(true, { checked: true });
    cp.setBotSignup(true, { checked: true });
    cp.checkChannel('bolshoy');
    cp.testChannel('bolshoy');
    assert.deepEqual(calls, [], `не администратор отправил запросы: ${JSON.stringify(calls)}`);
    assert.equal(confirms.length, 0, 'не администратору показано подтверждение выпуска');
    assert.equal(box.checked, false, 'выключатель остался включённым');
    assert.ok(toasts.length >= 1 && toasts.every((t) => /только администратору/.test(t[0])), 'нет объяснения');
    // Не выпуск наружу — работает как раньше.
    cp.bulkPause('pause', 'all');
    assert.equal(confirms.length, 1, 'пауза сети недоступна не администратору');
    cp.placementAction({ id: 'm1' }, f.approved, 'pause');
    assert.ok(calls.some((c) => /\/placements\/pa\/action/.test(c[1]) && c[2] && c[2].action === 'pause'),
        'пауза размещения недоступна не администратору');
    // Карточка каналов — только просмотр.
    assert.match(cp.switchHtml('enabled', true, 'Отправлять автоматически'), /disabled/);
    assert.match(cp.switchHtml('enabled', true, 'Отправлять автоматически'), /data-tip="Только администратор"/);
    assert.match(fnBody('renderChannels'), /Только просмотр: каналы, выключатели и ' \+\s*'проверку канала меняет администратор\./);
    assert.match(fnBody('chanBarHtml'), /chanRo\(\)/, 'адрес канала можно править не администратору');
    cp.state.isAdmin = true;
    assert.ok(!/disabled/.test(cp.switchHtml('enabled', true, 'Отправлять автоматически')));
});

test('права: устаревший флаг — 403 admin_required обрабатывается (тост, перечитать, кнопки выключаются)', () => {
    const { cp, calls, toasts } = loadReal();
    cp.state.month = '2026-10';
    cp.state.data = { materials: [] };      // план уже загружен (как на странице)
    assert.equal(cp.state.isAdmin, true);
    cp.reportError({ status: 403, code: 'admin_required', message: 'Только администратор может утверждать' });
    assert.equal(cp.state.isAdmin, false, 'флаг прав не сброшен после 403');
    assert.deepEqual(toasts.map((t) => t[0]), ['Только администратор может утверждать']);
    assert.equal(toasts[0][1], 'warning');
    assert.ok(calls.some((c) => c[0] === 'GET' && /^\/api\/content-plan\?month=2026-10/.test(c[1])), 'план не перечитан');
    assert.ok(calls.some((c) => c[0] === 'ATTENTION'), 'полоса внимания не перечитана');
    // Прочие 403 (не «только администратор») — обычная ошибка.
    cp.reportError({ status: 403, code: null, message: 'Недостаточно прав' });
    assert.equal(toasts[1][1], 'danger');
    assert.match(fnBody('reportChanError'), /if \(isAdminDenied\(err\)\) \{ adminDenied\(err\); return; \}/);
    assert.match(fnBody('chanSave'), /isAdminDenied\(err\)/, 'поле канала после 403 не возвращается');
});

test('«Отправить сейчас» — в очередь: уйдёт в течение минуты; карточка показывает «В очереди»', () => {
    const { cp, calls, confirms } = loadReal();
    const f = adminFixture(cp);
    cp.sendNow({ id: 'm1' }, f.approved);
    assert.match(confirms[0].text, /встанет в очередь и уйдёт в канал @kult_vo в течение минуты/);
    assert.ok(!/сразу/.test(confirms[0].text), 'подтверждение обещает мгновенную отправку');
    assert.equal(calls.filter((c) => /^\/api\/content-plan\/publish-now/.test(c[1])).length, 1);
    assert.match(js, /var QUEUED_TEXT = 'Поставлено в очередь: уйдёт в течение минуты';/);
    assert.match(fnBody('sendNow'), /if \(res\.queued\) GH\.toast\(QUEUED_TEXT/, 'тост ответа — не «в очереди»');
    const queued = cp.deliveryHtml({}, { ...f.approved, delivery: { state: 'queued', retry_at: '2026-10-09T14:59' } });
    assert.match(queued, /В очереди на отправку: уйдёт в течение минуты/);
});

test('идущая рассылка: пауза и отмена остановят её после текущей пачки (с подтверждением)', () => {
    const { cp, calls, confirms } = loadReal();
    adminFixture(cp);
    const sending = { id: 'pm', channel: 'bot', bar: 'all', status: 'approved', date: '2026-10-09', time: '14:58',
                      audience_info: { segment: 'bot_all', name: 'Все подписчики бота', size: 7 },
                      delivery: { state: 'sending', started_at: '2026-10-09T14:58' } };
    assert.deepEqual([...cp.actionList(sending)], ['pause', 'cancel'], 'у идущей рассылки не «пауза» и «отмена»');
    assert.deepEqual([...cp.actionList({ ...sending, channel: 'telegram' })], [], 'у отправляемого поста есть действия');
    cp.placementAction({ id: 'm1' }, sending, 'pause');
    assert.match(confirms[0].text, /Рассылка остановится после текущей пачки; кому уже ушло — останется\./);
    cp.placementAction({ id: 'm1' }, sending, 'cancel');
    assert.match(confirms[1].text, /Рассылка остановится после текущей пачки; кому уже ушло — останется\./);
    assert.equal(confirms[1].danger, true);
    const acts = calls.filter((c) => /\/placements\/pm\/action/.test(c[1])).map((c) => c[2].action);
    assert.deepEqual(acts, ['pause', 'cancel']);
    // Обычная пауза (рассылка не идёт) — без подтверждения, как раньше.
    cp.placementAction({ id: 'm1' }, { ...sending, id: 'pn', delivery: null }, 'pause');
    assert.equal(confirms.length, 2);
});

test('счётчик длины считает как сервер: Telegram и бот — UTF-16 (эмодзи = 2), Instagram — символы', () => {
    const { cp } = loadPage();
    const smile = String.fromCodePoint(0x1F600);
    assert.equal(cp.unitsFor('telegram'), 'utf16');
    assert.equal(cp.unitsFor('bot'), 'utf16');
    assert.equal(cp.unitsFor('instagram'), 'chars');
    assert.equal(cp.textLen('ab' + smile, 'utf16'), 4, 'эмодзи в Telegram — 2 единицы');
    assert.equal(cp.textLen('ab' + smile, 'chars'), 3, 'эмодзи в Instagram — 1 символ');
    // счётчик несёт единицы в data-units, а обновление при вводе их читает
    assert.match(fnBody('counterHtml'), /data-units=/);
    assert.match(fnBody('updateCounter'), /data-units/);
    // сервер считает так же (core/content_plan.text_units)
    const core = read('core/content_plan.py');
    assert.match(core, /def text_units\(/, 'нет серверной функции text_units');
});

// ---------------------------------------------------------------- переделка экрана (2026-10-04)
// Решение владельца: «открываешь день, чтобы поправить пост, — там ужас: проверки,
// поля для ИИ-агента». Карточка: куда и когда (дата и время прямо в строке), пост;
// служебное агента, «Ещё» и история — свёрнуты. Верх страницы: два меню вместо
// семи кнопок. Чипы и плашки одного материала на нескольких барах — склеены.

test('карточка: дата и время — прямо в строке размещения, главное действие на виду, остальное — по «⋯»', () => {
    const { cp } = loadReal();
    const f = adminFixture(cp);
    const m = { id: 'm1', kind: 'fixed', media: [], placements: [] };
    const ready = { ...f.ready, display_state: 'ready', display_label: 'Готово к утверждению', missing: [] };
    const row = cp.placementHtml(m, ready);
    assert.match(row, /<input type="date" class="gh-input" data-dt="date" data-pf="date" data-pid="pr" data-fk="pd:pr"/,
        'дата размещения не правится в строке (или без правил «дата и время»)');
    assert.match(row, /<input type="time" class="gh-input" data-dt="time" data-pf="time" data-pid="pr" data-fk="ptm:pr"/);
    assert.match(row, /data-act="pl-approve"/, 'у готового черновика нет «Утвердить» в строке');
    assert.ok(!/gh-cp-stbadge/.test(row), 'у готового бейдж повторяет кнопку «Утвердить»');
    assert.ok(!/data-act="pl-cancel"|data-pf="bar"/.test(row), 'действия и настройки не спрятаны за «⋯»');
    assert.match(row, /data-act="toggle-pl"/, 'нет «⋯»');
    cp.state.expanded.pr = true;
    const open = cp.placementHtml(m, ready);
    assert.match(open, /data-act="pl-cancel"/, '«⋯» не показывает остальные действия');
    assert.match(open, /data-pf="bar"/, '«⋯» не показывает настройки размещения');
    assert.equal(open.match(/data-act="pl-approve"/g).length, 1, 'главное действие продублировано под «⋯»');
    // Неготовый — без бейджа «Не хватает данных», строкой ниже — чего именно.
    const draft = { ...f.ready, id: 'pi', ready: false, display_state: 'incomplete', display_label: 'Не хватает: нет фото',
                    missing: [{ code: 'x', text: 'нет фото' }] };
    const inc = cp.placementHtml(m, draft);
    assert.match(inc, /class="gh-cp-pl-miss"[^>]*>Нет фото</);
    assert.ok(!/gh-cp-stbadge|data-act="pl-approve"/.test(inc), 'у неготового бейдж или «Утвердить»');
    // Вышедшее не правится: дата и время — текстом.
    const pub = { ...f.approved, id: 'pp2', status: 'published', display_state: 'published', display_label: 'Вышло' };
    assert.ok(!/type="date"/.test(cp.placementHtml(m, pub)), 'у вышедшего размещения поле даты');
});

test('карточка: главное действие строки — по состоянию размещения', () => {
    const { cp } = loadReal();
    const f = adminFixture(cp);
    assert.equal(cp.primaryAction({ ...f.ready, display_state: 'ready' }), 'approve');
    assert.equal(cp.primaryAction({ ...f.ready, ready: false, display_state: 'incomplete' }), '', 'неготовый — «Утвердить»');
    assert.equal(cp.primaryAction({ ...f.failed, display_state: 'failed' }), 'retry');
    assert.equal(cp.primaryAction({ ...f.paused, display_state: 'paused' }), 'resume');
    assert.equal(cp.primaryAction({ ...f.ready, status: 'cancelled', display_state: 'cancelled' }), 'restore');
    assert.equal(cp.primaryAction({ ...f.approved, display_state: 'scheduled' }), '', 'у запланированного главное действие');
    // Время вышло: площадка подключена — «Отправить сейчас», иначе — «Отметить вышедшим».
    assert.equal(cp.primaryAction({ ...f.approved, display_state: 'overdue' }), 'send_now');
    assert.equal(cp.primaryAction({ ...f.approved, bar: 'ligovskiy', display_state: 'overdue' }), 'mark_published');
    assert.equal(cp.primaryAction(f.partial), 'retry_failed');
});

test('карточка: служебное свёрнуто — «От агента», «Ещё», «История»; внизу — «Утвердить» все готовые', () => {
    const { cp } = loadReal();
    const closed = cp.foldHtml('fold:x', 'Ещё', 'тип', '<p>в</p>');
    assert.match(closed, /^<details class="gh-cp-fold" data-how="fold:x"><summary>/, 'раздел раскрыт по умолчанию');
    cp.state.howOpen['fold:x'] = true;
    assert.match(cp.foldHtml('fold:x', 'Ещё', 'тип', '<p>в</p>'), /^<details class="gh-cp-fold" data-how="fold:x" open>/,
        'раскрытое сворачивается при перерисовке');
    assert.match(fnBody('secMore'), /foldHtml\('fold:more'/);
    assert.match(fnBody('secMore'), /data-kind-seg/, 'тип материала не в «Ещё»');
    assert.match(fnBody('secMore'), /data-act="delete">Удалить материал/, 'удаление материала не в «Ещё»');
    assert.match(fnBody('secLog'), /foldHtml\('fold:log'/, 'история не свёрнута');
    assert.ok(!/data-act="delete"/.test(fnBody('drawerFoot')), '«Удалить материал» снова внизу каждой карточки');
    assert.match(fnBody('drawerFoot'), /data-act="approve-all"/);
    assert.match(fnBody('approveMaterial'), /readyPlacements\(m\)/, '«Утвердить» берёт не готовые размещения');
    assert.match(fnBody('approveMaterial'), /audienceReady\(/, 'рассылка утверждается без подтверждения аудитории');
    // Дата темы — только у темы без размещений (у остальных дата — у размещений).
    assert.match(fnBody('secWhere'), /if \(!pls\.length\) \{[\s\S]*?data-mf="planned_date"[\s\S]*?\} else \{/);
    // Легенда цветов свёрнута.
    cp.state.data = { states: [] };
    assert.match(cp.legendHtml(), /^<details class="gh-cp-legendbox" data-how="legend"><summary>Цвета состояний/);
});

test('таблица и календарь: одинаковые размещения на нескольких барах — один чип и одна плашка', () => {
    const { cp } = loadReal();
    cp.state.data = { materials: [] };
    const pl = (id, bar, extra = {}) => ({ id, channel: 'telegram', bar, date: '2026-10-09', time: '16:00',
                                          display_state: 'ready', ...extra });
    const m = { id: 'm1', title: 'Таплист пятницы', placements: [
        pl('a', 'bolshoy'), pl('b', 'ligovskiy'), pl('c', 'kremenchugskaya'), pl('d', 'varshavskaya'),
        { ...pl('e', 'all'), channel: 'instagram' }, pl('f', 'bolshoy', { time: '19:00' })] };
    const groups = [...cp.chipGroups(m)];
    assert.deepEqual(groups.map((g) => [...g.bars].join(',')),
        ['bolshoy,ligovskiy,kremenchugskaya,varshavskaya', 'all', 'bolshoy']);
    assert.equal(cp.barsLabel(['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']), 'все бары');
    assert.equal(cp.barsLabel(['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'], true), 'все');
    assert.equal(cp.barsLabel(['bolshoy', 'varshavskaya']), 'ВО, Вар');
    // Разное состояние — разные чипы.
    m.placements[1].display_state = 'scheduled';
    assert.equal([...cp.chipGroups(m)].length, 4);
    // Плашки календаря: склейка по материалу, площадке, времени и состоянию; темы — как есть.
    const items = [{ m, p: pl('a', 'bolshoy') }, { m, p: pl('b', 'ligovskiy') }, { m: { id: 't' }, theme: true }];
    const pills = [...cp.pillGroups(items)];
    assert.equal(pills.length, 2);
    assert.deepEqual([...pills[0].bars], ['bolshoy', 'ligovskiy']);
    assert.equal(pills[1].theme, true);
    // dayStats по-прежнему считает по пунктам до склейки (плотность — по материалам).
    assert.equal(cp.dayStats(items).placements, 2);
});

test('плашка календаря: название без приставки «<бар>, <дата> — » (бар и время уже в плашке)', () => {
    const { cp } = loadReal();
    assert.equal(cp.pillTitle('ВО, 10 окт — Гозе: стиль, который вернули из архива'), 'Гозе: стиль, который вернули из архива');
    assert.equal(cp.pillTitle('Лиг, 13 окт — Как Мюнхен сдался светлому'), 'Как Мюнхен сдался светлому');
    assert.equal(cp.pillTitle('Вар, 15 окт — Amarillo'), 'Amarillo');
    // «Бот» и «Сеть» плашка показывает сама (площадка, «все»): приставка снимается.
    assert.equal(cp.pillTitle('Бот, 22 окт — Рассылка «Краны не ждут»'), 'Рассылка «Краны не ждут»');
    assert.equal(cp.pillTitle('Сеть, 10 окт — Фламандский красный'), 'Фламандский красный');
    for (const keep of ['Кухня, 14 окт — Брискет и ирландский стаут', 'Таплист пятницы (октябрь) — живой список кранов',
                        'Хэллоуин, 31 окт — анонс', 'вАРШ, 4 окт — 5 октября', 'крем', 'ВО — ']) {
        const got = cp.pillTitle(keep);
        assert.ok(got === keep || keep === 'ВО — ', `«${keep}» обрезано до «${got}»`);
    }
    assert.equal(cp.pillTitle('ВО — '), 'ВО — ', 'название из одной приставки стало пустым');
    assert.ok(!/aiMark\(/.test(fnBody('pillHtml')));
    assert.match(fnBody('pillHtml'), /esc\(pillTitle\(x\.m\.title\)\)/);
    assert.match(fnBody('pillTip'), /x\.m\.title/, 'в подсказке плашки нет полного названия');
});

test('предпросмотр таплиста: названия пива — ссылки на Untappd (сущности Telegram, UTF-16)', () => {
    const { cp } = loadReal();
    // U+1D504 — две единицы UTF-16, как эмодзи: offset Telegram совпадает с индексом строки JS.
    const text = 'Таплист \u{1D504}\n1. Zavod Dopamine — двойной IPA, 7,2%\n2. <b>Злое</b> — сидр';
    const url = 'https://untappd.com/b/zavod-dopamine/3636325';
    const html = cp.linkedText(text, [
        { type: 'text_link', offset: text.indexOf('Zavod'), length: 'Zavod Dopamine'.length, url },
        { type: 'text_link', offset: text.indexOf('<b>'), length: 3, url: 'javascript:alert(1)' },
    ]);
    assert.ok(html.includes('<a href="' + url + '" target="_blank" rel="noopener noreferrer">Zavod Dopamine</a> — двойной IPA'));
    assert.ok(!html.includes('javascript:'), 'не https — ссылки нет');
    assert.ok(html.includes('&lt;b&gt;Злое&lt;/b&gt;'), 'текст вне ссылок экранируется');
    assert.ok(html.includes('Таплист \u{1D504}<br>1. '));
    // выход за конец текста и наложение — без ссылки, текст целиком
    assert.equal(cp.linkedText('abc', [{ type: 'text_link', offset: 2, length: 5, url: 'https://x' }]), 'abc');
    assert.equal(cp.linkedText('abcd', [{ type: 'text_link', offset: 1, length: 2, url: 'https://x' },
                                        { type: 'text_link', offset: 2, length: 1, url: 'https://y' }]),
                 'a<a href="https://x" target="_blank" rel="noopener noreferrer">bc</a>d');
    assert.equal(cp.linkedText('a\nb', []), 'a<br>b');
    // пузырь Telegram берёт entities из ответа live-preview; Instagram ссылок не показывает
    const m = { id: 'm1', kind: 'live', live_source: 'taplist', media: [], placements: [] };
    const tg = { id: 'p1', channel: 'telegram', bar: 'varshavskaya', date: '2026-10-09', time: '16:00',
                 status: 'approved', effective_text: '{таплист}', media: null };
    const ig = Object.assign({}, tg, { id: 'p2', channel: 'instagram', bar: 'all' });
    const result = { text, entities: [{ type: 'text_link', offset: text.indexOf('Zavod'), length: 14, url }],
                     length: 60, limit: 4096, problems: [] };
    cp.state.previewLive[cp.previewKey(m, tg)] = { result };
    cp.state.previewLive[cp.previewKey(m, ig)] = { result };
    assert.ok(cp.previewHtml(m, tg).includes('>Zavod Dopamine</a>'));
    assert.ok(!cp.previewHtml(m, ig).includes('<a href'), 'в подписи Instagram ссылок нет');
    assert.match(css, /\.gh-cp-bubble-t a \{[^}]*color: var\(--gh-accent-ink\)/);
});

test('новый материал одной формой: название, площадка, бары, дата и время — сразу', () => {
    const { cp } = loadReal();
    const base = { title: 'Осенний сидр', channel: 'telegram', bars: ['bolshoy', 'ligovskiy'], bar: 'all', audience: '',
                   date: '2026-10-12', time: '19:30' };
    assert.equal(cp.newProblem(base), '');
    assert.deepEqual(plain(cp.newPlacementBody(base)),
        { channel: 'telegram', date: '2026-10-12', time: '19:30', bars: ['bolshoy', 'ligovskiy'] });
    assert.deepEqual(plain(cp.newPlacementBody({ ...base, channel: 'bot', bar: 'all', audience: 'bot_all' })),
        { channel: 'bot', date: '2026-10-12', time: '19:30', bars: ['all'], audience: { segment: 'bot_all' } });
    assert.deepEqual(plain(cp.newPlacementBody({ ...base, channel: 'instagram', bars: [] })).bars, ['all']);
    assert.match(cp.newProblem({ ...base, title: '   ' }), /Название обязательно/);
    assert.match(cp.newProblem({ ...base, bars: [] }), /хотя бы один бар/);
    assert.match(cp.newProblem({ ...base, channel: 'bot', audience: '' }), /аудиторию/);
    assert.equal(cp.newProblem({ ...base, channel: 'none', bars: [] }), '', 'тема без площадки не создаётся');
    assert.match(cp.newProblem({ ...base, date: '0202-10-12' }), /год от 2020 до 2100/);
    const add = fnBody('addMaterial');
    assert.match(add, /GH\.api\('POST', withMonth\(API \+ '\/materials'\)/);
    assert.match(add, /'\/materials\/' \+ enc\(created\.id\) \+ '\/placements'/, 'размещения не создаются вместе с материалом');
    assert.match(add, /openMaterial\(mat\.id\)/, 'после создания не открывается карточка');
    assert.match(html, /id="cpNewModal"/);
    for (const call of ["if (a === 'add') { openNew(null); return; }", "openNew(addDay.getAttribute('data-add-day'))"]) {
        assert.ok(js.includes(call), `нет вызова диалога: ${call}`);
    }
});

test('утвердить отмеченные: панель выбора -> окно утверждения только по этим материалам', () => {
    const { cp } = loadReal();
    assert.match(html, /data-bulk="approve"/, 'в панели выбора нет «Утвердить»');
    assert.match(fnBody('bulkAction'), /if \(kind === 'approve'\) \{ openApprove\(ids\); return; \}/);
    const res = { month: '2026-10',
        will_approve: [{ placement_id: 'p1', material_id: 'a' }, { placement_id: 'p2', material_id: 'b' }],
        bot: [{ placement_id: 'p3', material_id: 'b' }], stays_draft: [{ placement_id: 'p4', material_id: 'c' }] };
    const got = plain(cp.onlySelected(res, { b: true, c: true }));
    assert.deepEqual(got.will_approve.map((x) => x.placement_id), ['p2']);
    assert.deepEqual(got.bot.map((x) => x.placement_id), ['p3']);
    assert.deepEqual(got.stays_draft.map((x) => x.placement_id), ['p4']);
    // Без отмеченных — всё готовое под фильтрами, как раньше.
    assert.match(fnBody('openApprove'), /if \(only\) res = onlySelected\(res, only\);/);
    assert.match(js, /el\.approveBtn\.addEventListener\('click', function \(\) \{ openApprove\(\); \}\)/,
        'кнопка «Утвердить готовые» передаёт событие клика вместо списка');
});

test('каналы: «Подключить»; удачное тестовое сообщение само подключает канал', () => {
    const { cp } = loadReal();
    cp.state.chan = { data: { channels: { telegram: { bolshoy: { chat: '@kult_vo' } }, instagram: {}, bot: {} } },
                      busy: {}, tests: {} };
    assert.equal(cp.chanBarStatus('bolshoy').label, 'Не подключён');
    assert.match(cp.chanBarStatus('bolshoy').note, /«Подключить»/);
    assert.equal(cp.barChecked('bolshoy'), false);
    cp.state.chan.data.channels.telegram.bolshoy.check = { ok: true, can_post: true, chat: '@kult_vo' };
    assert.equal(cp.barChecked('bolshoy'), true);
    cp.state.chan.data.channels.telegram.bolshoy.check.chat = '@old';
    assert.equal(cp.barChecked('bolshoy'), false, 'проверка другого адреса считается подключением');
    assert.match(fnBody('chanBarHtml'), /barChecked\(b\.key\) \? 'Проверить снова' : 'Подключить'/);
    // Регрессия 2026-10-04: тест дошёл, а «Проверить» не нажали — канал оставался не подключён.
    assert.match(fnBody('testChannel'), /if \(sent && !barChecked\(bar\)\) checkChannel\(bar\);/);
});

test('предпросмотр таплиста: какая гифка уйдёт, отдельным сообщением ли, правило под «Как считается»', () => {
    // Решение владельца 2026-10-09: «к каждому таплисту прикрепляем рандомную гифку из списка».
    const { cp } = loadReal();
    const m = { id: 'm1', kind: 'live' };
    const p = { id: 'p1', channel: 'telegram', bar: 'bolshoy' };
    const key = cp.previewKey(m, p);
    const gif = { number: 24, total: 25, title: 'Теория большого взрыва', note: 'Пенни и Леонард смеются за пивом.',
                  page: 'https://tenor.com/view/x-gif-1', separate: false };
    cp.state.previewLive[key] = { result: { gif } };
    let html = cp.gifHtml(m, p);
    assert.match(html, /Гифка: «Теория большого взрыва» — Пенни и Леонард смеются за пивом\./);
    assert.match(html, /href="https:\/\/tenor\.com\/view\/x-gif-1" target="_blank" rel="noopener noreferrer">открыть/);
    assert.ok(!/отдельным сообщением перед текстом/.test(html.split('<details')[0]), 'короткий текст — подписью');
    assert.match(html, /<details class="gh-cp-how"[\s\S]*Гифка 24 из 25\./, 'правило не свёрнуто в «Как считается»');
    assert.match(html, /повторится через 25 недель/);
    cp.state.previewLive[key] = { result: { gif: { ...gif, separate: true, title: '<b>' } } };
    html = cp.gifHtml(m, p);
    assert.match(html, /гифка уйдёт отдельным сообщением перед текстом/);
    assert.ok(!html.includes('<b>'), 'название гифки не экранировано');
    cp.state.previewLive[key] = { result: { gif: null } };
    assert.equal(cp.gifHtml(m, p), '', 'без гифки (Instagram, бот, свои фото) — строки нет');
    assert.match(fnBody('previewHtml'), /liveNotesHtml\(m, p\) \+ gifHtml\(m, p\) \+ phraseHow\(m, p\)/);
    assert.match(css, /\.gh-cp-gif \{/);
});

test('каналы: дошедший тест подключает канал ответом сервера — без отдельной проверки', () => {
    // Регрессия 2026-10-09: тест на Лиговском дошёл, а проверка после него попала в
    // перезапуск сайта. Теперь канал подключает сам ответ теста (connected, настройки).
    const { cp, GH, calls, toasts } = loadReal();
    cp.state.month = '2026-10';
    cp.state.data = { materials: [] };      // план уже загружен (как на странице)
    const stale = { channels: { telegram: { ligovskiy: { chat: '@kult_lig', checked_at: '2026-10-04T03:26',
        check: { ok: true, can_post: false, chat: '@kult_lig', error: 'Bad Request: member list is inaccessible' } } },
        instagram: {}, bot: {} } };
    cp.state.chan = { data: stale, busy: {}, tests: {} };
    assert.equal(cp.chanBarStatus('ligovskiy').label, 'Нет права публиковать');
    const answer = { ok: true, message_id: 7, error: null, chat: '@kult_lig', connected: true,
        channels: { telegram: { ligovskiy: { chat: '@kult_lig', checked_at: '2026-10-09T16:30',
            check: { ok: true, can_post: true, chat: '@kult_lig', via: 'test', chat_title: 'kult_lig' } } },
            instagram: {}, bot: {} } };
    GH.api = (...args) => {
        calls.push(args);
        return args[1] === '/api/content-plan/channels/test' ? { then: (fn) => fn(answer) } : new Promise(() => {});
    };
    cp.testChannel('ligovskiy');
    assert.equal(cp.barChecked('ligovskiy'), true, 'ответ теста не подключил канал на странице');
    assert.equal(cp.chanBarStatus('ligovskiy').label, 'Можно публиковать');
    assert.match(cp.chanBarStatus('ligovskiy').note, /проверено .* тестовым сообщением/);
    assert.match(toasts[toasts.length - 1][0], /тестовое сообщение дошло, канал подключён/);
    assert.ok(calls.some((c) => c[0] === 'GET' && /^\/api\/content-plan\?month=/.test(c[1])),
        'после подключения план не перечитан (баннер «что уходит само»)');
    assert.match(fnBody('testChannel'), /if \(res && res\.channels\) S\.chan\.data = res;/);
    // Подсказка «Как это работает» — о подключении тестом.
    assert.match(fnBody('chanTelegramHtml'), /Дошедший тест сам подключает канал/);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

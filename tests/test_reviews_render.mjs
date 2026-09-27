/**
 * ТЕКСТОВЫЕ проверки страницы «Отзывы» (/reviews) раздела «Гости».
 *
 *     node tests/test_reviews_render.mjs
 *
 * Проверяется согласованность файлов между собой: шаблон объявляет узлы, JS
 * их ищет, CSS описывает классы, которые JS пишет в разметку, эндпоинты,
 * которые зовёт JS, есть в routes/reviews.py, а поля ответа — в
 * core/guest_reviews.py. Такие расхождения не ловятся ни юнит-тестами API
 * (tests/test_guest_reviews.py), ни глазами на одном экране: страница просто
 * молча не рисует блок. Тот же приём, что tests/test_draft_render.mjs.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const html = read('templates/reviews.html');
const css = read('static/guest_hub/reviews.css');
const hubCss = read('static/guest_hub/hub.css');
const js = read('static/js/guest_hub/reviews.js');
const commonJs = read('static/js/guest_hub/common.js');
const routes = read('routes/reviews.py');
const core = read('core/guest_reviews.py');
const headPartial = read('templates/shared/guest_hub_head.html');

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

// Все классы, описанные в стилях страницы и в общих стилях раздела.
// Комментарии вырезаются: «static/guest_hub/hub.css» в тексте — не класс .css.
const noComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '');
const classesOf = (text) => new Set([...noComments(text).matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
const knownClasses = new Set([...classesOf(css), ...classesOf(hubCss)]);

test('шаблон подключает стили и скрипты раздела с кэш-бастингом', () => {
    for (const asset of ['static/guest_hub/hub.css', 'static/guest_hub/reviews.css',
                         'static/js/guest_hub/common.js', 'static/js/guest_hub/reviews.js']) {
        const re = new RegExp(asset.replace(/[./]/g, (c) => '\\' + c) + '\\?v=\\{\\{ app_version \\}\\}');
        assert.match(html, re, `${asset} без ?v={{ app_version }} — правки не доедут до браузеров`);
    }
    const common = html.indexOf('static/js/guest_hub/common.js');
    const page = html.indexOf('static/js/guest_hub/reviews.js');
    assert.ok(common > 0 && common < page, 'common.js (window.GH) должен грузиться раньше reviews.js');
    const hub = html.indexOf('static/guest_hub/hub.css');
    const own = html.indexOf('static/guest_hub/reviews.css');
    assert.ok(hub > 0 && hub < own, 'reviews.css должен идти после hub.css (перекрывает его)');
});

test('каркас страницы: body, сайдбар, шапка раздела внутри gh-wrap', () => {
    assert.match(html, /<body class="gh-page gh-scope">/, 'нет классов страницы раздела на body');
    assert.match(html, /\{% include 'shared\/nav\.html' %\}/, 'нет общего сайдбара');
    const wrap = html.indexOf('<div class="gh-wrap">');
    const head = html.indexOf("{% include 'shared/guest_hub_head.html' %}");
    assert.ok(wrap > 0 && head > wrap, 'шапка раздела подключается вне .gh-wrap');
    assert.match(html, /\{% set hub_active = 'reviews' %\}/, 'вкладка «Отзывы» не активна');
    assert.match(html, /\{% set hub_title = 'Отзывы' %\}/, 'нет заголовка');
    assert.match(html, /\{% set hub_subtitle = 'Яндекс Карты: ответы гостям' %\}/, 'нет подзаголовка');
    assert.match(headPartial, /hub_title/, 'шапка раздела больше не читает hub_title');
});

test('все id, которые ищет JS, объявлены в шаблоне', () => {
    const wanted = new Set();
    for (const m of js.matchAll(/(?:getElementById|byId)\('([^']+)'\)/g)) wanted.add(m[1]);
    // Таблица id в init(): el[k] = byId(ids[k]).
    const idsBlock = js.match(/var ids = \{([\s\S]*?)\};/);
    assert.ok(idsBlock, 'нет таблицы id в init()');
    for (const m of idsBlock[1].matchAll(/:\s*'([^']+)'/g)) wanted.add(m[1]);
    // Кнопки и меню фильтров — таблица PICKERS.
    for (const m of js.matchAll(/(?:btn|menu): '([^']+)'/g)) wanted.add(m[1]);
    assert.ok(wanted.size > 30, `подозрительно мало id: ${wanted.size}`);
    const missing = [...wanted].filter((id) => !html.includes(`id="${id}"`));
    assert.deepEqual(missing, [], `нет узлов в шаблоне: ${missing.join(', ')}`);
});

test('id в шаблоне не повторяются', () => {
    const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
    const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
    assert.deepEqual(dup, [], `повторы id: ${dup.join(', ')}`);
});

test('каждый вызов API есть в routes/reviews.py с тем же методом', () => {
    const apiBlock = js.match(/var API = \{([\s\S]*?)\};/);
    assert.ok(apiBlock, 'нет таблицы эндпоинтов API');
    const api = {};
    for (const m of apiBlock[1].matchAll(/(\w+):\s*'([^']+)'/g)) api[m[1]] = m[2];
    // Маршруты блюпринта: путь (параметры сведены к <>) -> методы.
    const routeMap = {};
    for (const m of routes.matchAll(/@reviews_bp\.route\('([^']+)'(?:,\s*methods=\[([^\]]*)\])?\)/g)) {
        const p = m[1].replace(/<[^>]+>/g, '<>');
        const methods = m[2] ? [...m[2].matchAll(/'(\w+)'/g)].map((x) => x[1]) : ['GET'];
        routeMap[p] = (routeMap[p] || []).concat(methods);
    }
    const calls = [...js.matchAll(/call\('(GET|POST|PATCH|DELETE)', '(\w+)'/g)];
    assert.ok(calls.length >= 8, `подозрительно мало вызовов: ${calls.length}`);
    const bad = [];
    for (const [, method, key] of calls) {
        assert.ok(api[key], `ключ «${key}» не описан в API`);
        const p = api[key].replace(/<[^>]+>/g, '<>');
        if (!(routeMap[p] || []).includes(method)) bad.push(`${method} ${api[key]}`);
    }
    assert.deepEqual(bad, [], `нет маршрута: ${bad.join(', ')}`);
    // Прямых fetch мимо GH.api нет: ошибки и 503 разбираются в одном месте.
    assert.ok(!/\bfetch\(/.test(js), 'прямой fetch мимо GH.api');
});

test('поля ответа, которые читает JS, отдаёт сервер', () => {
    const metricKeys = ['count', 'rated', 'avg_rating', 'unanswered', 'answered', 'skipped',
                        'unanswered_pct', 'median_response_hours', 'oldest_unanswered_hours'];
    for (const k of metricKeys) {
        assert.ok(new RegExp(`'${k}':`).test(core), `сервер не отдаёт метрику ${k}`);
    }
    for (const k of ['avg_rating', 'unanswered_pct', 'median_response_hours', 'oldest_unanswered_hours',
                     'age_hours', 'response_hours', 'reply_draft', 'material_id', 'skip_reason']) {
        assert.ok(js.includes(k), `страница не использует ${k}`);
    }
    // Формулы для подсказок: каждый ключ f.<key>, который читает страница, есть в FORMULAS.
    const formulasBlock = core.match(/FORMULAS = \{([\s\S]*?)\n\}/);
    assert.ok(formulasBlock, 'нет FORMULAS в core/guest_reviews.py');
    const known = new Set([...formulasBlock[1].matchAll(/'(\w+)':/g)].map((m) => m[1]));
    const used = new Set([...js.matchAll(/\bf\.(\w+)/g)].map((m) => m[1]));
    const missing = [...used].filter((k) => !known.has(k));
    assert.deepEqual(missing, [], `формул нет на сервере: ${missing.join(', ')}`);
    for (const k of ['count', 'avg_rating', 'unanswered_pct', 'median_response_hours', 'sort', 'period',
                     'rating_filter', 'response_hours']) {
        assert.ok(used.has(k), `формула ${k} не показывается пользователю`);
    }
    for (const k of ['now', 'reviews', 'metrics', 'formulas', 'sources']) {
        assert.ok(new RegExp(`'${k}':`).test(core), `в ответе списка нет ${k}`);
    }
    assert.match(routes, /'material_id': material_id,\s*'month':/, 'to-material не отдаёт material_id и month');
});

test('страница не пересчитывает показатели сама', () => {
    // Средняя, доля и медиана приходят с сервера; на клиенте только формат.
    assert.ok(!/\.reduce\(/.test(js), 'на клиенте появилась свёртка — пересчёт показателей?');
    assert.ok(!/sort\(/.test(js), 'клиент пересортировывает список — порядок задаёт сервер');
    assert.match(js, /m\.avg_rating/, 'средняя не берётся из metrics');
    assert.match(js, /m\.unanswered_pct/, 'доля без ответа не берётся из metrics');
    assert.match(js, /m\.median_response_hours/, 'медиана не берётся из metrics');
    assert.match(js, /r\.age_hours/, 'ожидание не берётся из age_hours');
});

test('все классы, которые JS пишет в разметку, описаны в CSS', () => {
    // Классы раздела — с префиксом gh-, состояния — is-. Разметка собирается
    // конкатенацией: ищем литералы; «gh-tone-' + tone» (обрывок) не считается.
    const used = new Set();
    for (const m of js.matchAll(/["'\s]((?:gh-|is-)[\w-]*\w)(?![\w-])/g)) used.add(m[1]);
    const missing = [...used].filter((c) => !knownClasses.has(c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
    // Тоны пипсов и бейджей берутся из hub.css.
    for (const tone of ['muted', 'warning', 'accent', 'success', 'danger']) {
        assert.ok(knownClasses.has(`gh-tone-${tone}`), `нет тона gh-tone-${tone}`);
    }
});

test('все классы шаблона описаны в CSS', () => {
    const used = new Set();
    for (const m of html.matchAll(/class="([^"{]+)"/g)) {
        for (const c of m[1].split(/\s+/)) if (/^(gh-|is-)/.test(c)) used.add(c);
    }
    const missing = [...used].filter((c) => !knownClasses.has(c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
});

test('узлы, которые прячутся атрибутом hidden, действительно прячутся', () => {
    // Класс с display (.gh-btn — inline-flex, .gh-seg-btn, .gh-form-row — flex)
    // перебивает правило браузера [hidden]{display:none}: нужен явный [hidden].
    const noDisplay = noComments(css + '\n' + hubCss);
    const hiddenIds = new Set([...js.matchAll(/el\.(\w+)\.hidden\s*=/g)].map((m) => m[1]));
    const idsBlock = js.match(/var ids = \{([\s\S]*?)\};/)[1];
    const idOf = {};
    for (const m of idsBlock.matchAll(/(\w+):\s*'([^']+)'/g)) idOf[m[1]] = m[2];
    const bad = [];
    for (const key of hiddenIds) {
        const id = idOf[key];
        const tag = html.match(new RegExp(`<[a-z]+[^>]*\\sid="${id}"[^>]*>`));
        assert.ok(tag, `узел ${id} не найден`);
        const cls = (tag[0].match(/class="([^"]+)"/) || [, ''])[1].split(/\s+/).filter(Boolean);
        const shown = cls.filter((c) => new RegExp(`\\.${c}\\s*\\{[^}]*display:\\s*(flex|inline-flex|grid|inline-block|block)`).test(noDisplay));
        if (!shown.length) continue;
        const covered = cls.some((c) => new RegExp(`\\.${c}\\[hidden\\]`).test(noDisplay));
        if (!covered) bad.push(`${id} (.${shown.join(', .')})`);
    }
    assert.deepEqual(bad, [], `hidden не спрячет: ${bad.join('; ')}`);
});

test('классы страницы — с префиксом gh-rv-, без глобальных имён', () => {
    const own = classesOf(css);
    const bad = [...own].filter((c) => !/^(gh-|is-)/.test(c));
    assert.deepEqual(bad, [], `классы без префикса: ${bad.join(', ')}`);
    // Новые классы страницы — только gh-rv-; остальные gh-* должны быть из hub.css.
    const hub = classesOf(hubCss);
    const stray = [...own].filter((c) => c.startsWith('gh-') && !c.startsWith('gh-rv-') && !hub.has(c));
    assert.deepEqual(stray, [], `новые классы без префикса gh-rv-: ${stray.join(', ')}`);
    assert.ok(!/metric-card|metric-value|stat-value/.test(css + js + html),
        'имена metric-card/metric-value/stat-value перебиваются mobile.css');
});

test('цвета — только токены: ни HEX, ни rgb/hsl вне hub.css', () => {
    const hexCss = [...css.matchAll(/#[0-9A-Fa-f]{3,8}\b/g)].map((m) => m[0]);
    assert.deepEqual(hexCss, [], `HEX в reviews.css: ${hexCss.join(', ')}`);
    assert.ok(!/\b(rgba?|hsla?)\(/.test(css), 'rgb()/hsl() в reviews.css — нужен токен --gh-*');
    const hexJs = [...js.matchAll(/['"]#[0-9A-Fa-f]{3,8}['"]/g)].map((m) => m[0]);
    assert.deepEqual(hexJs, [], `HEX в reviews.js: ${hexJs.join(', ')}`);
    assert.ok(!/style="[^"]*#[0-9A-Fa-f]{3,8}/.test(html), 'HEX в инлайновом стиле шаблона');
    assert.ok(!/style="/.test(js), 'инлайновый стиль в разметке из JS');
    // Каждый var(--gh-*) страницы объявлен в hub.css (иначе тёмная тема не подхватит).
    const vars = new Set([...css.matchAll(/var\((--gh-[\w-]+)/g)].map((m) => m[1]));
    const declared = new Set([...hubCss.matchAll(/(--gh-[\w-]+):/g)].map((m) => m[1]));
    const undeclared = [...vars].filter((v) => !declared.has(v));
    assert.deepEqual(undeclared, [], `токены не объявлены в hub.css: ${undeclared.join(', ')}`);
});

test('нет эмодзи и символов-звёзд', () => {
    const emoji = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2300}-\u{23FF}\u{FE0F}]/u;
    for (const [name, text] of [['reviews.html', html], ['reviews.css', css], ['reviews.js', js]]) {
        const m = text.match(emoji);
        assert.ok(!m, `${name}: символ ${m && JSON.stringify(m[0])}`);
    }
});

test('пользовательский текст экранируется', () => {
    // Любое поле отзыва, попавшее в РАЗМЕТКУ (строка с тегом), идёт через GH.esc.
    // Текст для GH.confirm / GH.toast экранирует сам common.js.
    const field = /\+ (GH\.esc\()?(?:r|review)\.(?:text|author|skip_reason|guest\.phone|guest\.telegram|reply\.text|reply\.by)\b/g;
    const bare = [];
    for (const line of js.split('\n')) {
        if (!/<[a-z]/.test(line)) continue;
        for (const m of line.matchAll(field)) if (!m[0].includes('GH.esc(')) bare.push(line.trim());
    }
    const fieldOnce = new RegExp(field.source);   // без /g: test() не помнит lastIndex
    const markupLines = js.split('\n').filter((l) => /<[a-z]/.test(l) && fieldOnce.test(l));
    assert.ok(markupLines.length >= 4, `подозрительно мало полей отзыва в разметке: ${markupLines.length}`);
    assert.deepEqual(bare, [], `без экранирования: ${bare.join(', ')}`);
    assert.ok(!/onclick=|onchange=|oninput=/.test(js + html), 'инлайновые обработчики');
    assert.ok(!/innerHTML\s*=\s*[^;]*\b(err|e)\.message/.test(js), 'текст ошибки попадает в innerHTML');
});

test('тексты страницы по спецификации', () => {
    assert.match(html, /Отзывов за период нет/, 'нет пустого состояния');
    assert.match(html, /Отзывы приходят из Яндекс Бизнеса раз в сутки\./, 'нет пояснения пустого состояния');
    // Ручного ввода нет (решение владельца 2026-09-28): ни кнопки, ни вызова диалога «Новый отзыв».
    assert.ok(!(html + js).includes('Добавить отзыв'), 'вернулась кнопка «Добавить отзыв»');
    assert.ok(!/openDialog\(null\)/.test(js), 'диалог нового отзыва снова открывается');
    assert.match(js, /Отправка в источник не подключена — скопируйте ответ и опубликуйте вручную/,
        'нет пометки, что ответ не отправляется');
    for (const text of ['Сохранить ответ', 'Оставить без ответа', 'Вернуть в работу', 'Сделать материалом',
                        'Открыть в контент-плане', 'Открыть в Маркетинге', 'Скопировать', 'Изменить', 'Удалить']) {
        assert.ok(js.includes(text), `нет действия «${text}»`);
    }
    // Ссылка на гостя несёт запрос для поиска: /guests?q=<телефон>#guest.
    assert.match(js, /'\/guests' \+ \(q \? '\?q=' \+ encodeURIComponent\(q\) : ''\) \+ '#guest'/,
        'ссылка на гостя в Маркетинге без запроса ?q=');
    assert.match(js, /\/content-plan\?/, 'ссылка на материал в контент-плане');
    for (const text of ['За всё время', 'без оценки', 'Telegram гостя', 'Телефон гостя']) {
        assert.ok((html + js).includes(text), `нет «${text}»`);
    }
    for (const label of ['1–2', '4–5', 'Без оценки', 'Без ответа', 'Отвечены', 'Без ответа по решению']) {
        assert.ok(js.includes(`'${label}'`), `нет пункта фильтра «${label}»`);
    }
});

test('срок ответа 48 ч — одна именованная константа с объяснением', () => {
    const m = js.match(/\/\/[^\n]*\n(?:\s*\/\/[^\n]*\n)*\s*var WAIT_WARN_HOURS = 48;/);
    assert.ok(m, 'нет константы WAIT_WARN_HOURS с комментарием');
    const bare = js.split('\n').filter((l) => /[^\w.]48\b/.test(l) && !/WAIT_WARN_HOURS = 48|48 ч|4096/.test(l));
    assert.deepEqual(bare, [], `голое число 48: ${bare.join(' | ')}`);
    assert.match(js, /data-tip="' \+ GH\.esc\(tip\)/, 'у отметки ожидания нет подсказки с правилом');
});

test('адрес страницы: status, source, month (и all) читаются и пишутся', () => {
    for (const key of ['status', 'source', 'month', 'rating']) {
        assert.match(js, new RegExp(`p\\.get\\('${key}'\\)`), `не читается ?${key}=`);
    }
    assert.match(js, /month === 'all'/, '«За всё время» не читается из адреса');
    assert.match(js, /GH\.setParams\(/, 'фильтры не пишутся в адрес');
    assert.match(js, /GH\.getBar\(\)/, 'бар не берётся из общего фильтра раздела');
    assert.match(js, /GH\.setBar\(/, 'бар не сохраняется в общий фильтр раздела');
});

test('телефон: у стилей есть разметка до 768px и лист диалога', () => {
    assert.match(css, /@media \(max-width: 768px\)/, 'нет правил для телефона');
    assert.match(hubCss, /\.gh-drawer \{[\s\S]*?width: 100%/, 'выдвижная карточка не во весь экран на телефоне');
    assert.match(hubCss, /\.gh-modal \{ align-items: flex-end/, 'диалог не лист снизу на телефоне');
});

test('общий модуль GH даёт всё, что зовёт страница', () => {
    const used = new Set([...js.matchAll(/GH\.(\w+)/g)].map((m) => m[1]));
    const missing = [...used].filter((k) => !new RegExp(`GH\\.${k}\\s*=`).test(commonJs));
    assert.deepEqual(missing, [], `нет в common.js: ${missing.join(', ')}`);
});

test('каждое изменение обновляет и список, и полосу «требует внимания»', () => {
    // Ревью 2026-09-27: счётчик «Отзывы без ответа» должен меняться сразу
    // после ответа, пропуска, возврата, материала, добавления и удаления.
    const body = (name) => {
        const at = js.indexOf(`function ${name}(`);
        assert.ok(at >= 0, `нет функции ${name}`);
        const next = js.indexOf('\n    function ', at + 10);
        return js.slice(at, next < 0 ? js.length : next);
    };
    for (const fn of ['doReply', 'doSkip', 'doReopen', 'doMaterial', 'doDelete', 'saveDialog']) {
        assert.match(body(fn), /afterChange\(/, `${fn} не зовёт afterChange — полоса отстанет`);
    }
    assert.match(body('afterChange'), /GH\.loadAttention\(\)/, 'afterChange не обновляет полосу');
    assert.match(body('afterChange'), /load\(\)/, 'afterChange не перечитывает список');
});

test('черновик ответа уходит и показывается как набран', () => {
    // Ревью 2026-09-27: сервер хранит reply_draft без обрезки; клиент тоже не
    // обрезает его и не теряет первый перевод строки в <textarea>.
    const save = js.slice(js.indexOf('function saveDraft('), js.indexOf('function saver('));
    assert.match(save, /\{ reply_draft: text \}/, 'черновик уходит не как набран');
    assert.ok(!/trim\(/.test(save), 'черновик обрезается перед отправкой');
    assert.match(js, /var TA_LEAD = '\\n';/, 'нет перевода строки-«жертвы» после <textarea>');
    assert.match(js, /placeholder="Ответ гостю\. Черновик сохраняется сам\.">' \+ TA_LEAD \+/,
        'поле черновика без TA_LEAD — ведущий перевод строки пропадёт');
    assert.match(js, /aria-label="Правка ответа">' \+ TA_LEAD \+/, 'поле правки ответа без TA_LEAD');
});

// ================================================================ исполнение
// reviews.js и common.js выполняются в vm с поддельным DOM: так проверяется
// поведение, а не только текст (ревью 2026-09-27: куда ведёт полоса, что
// видно у удалённого материала, как уходит черновик при уходе со страницы).

const asyncTests = [];
function atest(name, fn) { asyncTests.push({ name, fn }); }

// Узел-заглушка: любой id находится (узел создаётся по запросу), разметка
// списка остаётся строкой в innerHTML — её и проверяем.
class El {
    constructor(tag, id) {
        this.tagName = String(tag || 'div').toUpperCase();
        this.id = id || '';
        this.attrs = {};
        this.listeners = {};
        this.children = [];
        this.parentNode = null;
        this.hidden = false;
        this.disabled = false;
        this.value = '';
        this.textContent = '';
        this.innerHTML = '';
        this.style = {};
        this.className = '';
        const s = new Set();
        this.classList = {
            add: (...c) => c.forEach((x) => s.add(x)),
            remove: (...c) => c.forEach((x) => s.delete(x)),
            toggle: (c, on) => { const v = on === undefined ? !s.has(c) : !!on; if (v) s.add(c); else s.delete(c); return v; },
            contains: (c) => s.has(c),
        };
    }
    get firstChild() { return this.children[0] || null; }
    setAttribute(n, v) { this.attrs[n] = String(v); }
    getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; }
    hasAttribute(n) { return n in this.attrs; }
    removeAttribute(n) { delete this.attrs[n]; }
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
    removeEventListener() {}
    fire(t, e) { (this.listeners[t] || []).forEach((f) => f(e)); }
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
    removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; }
    contains(x) { return x === this || this.children.some((c) => c.contains(x)); }
    closest() { return null; }
    querySelector() { return new El('div'); }
    querySelectorAll() { return []; }
    focus() {}
    blur() {}
    setSelectionRange() {}
    getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

function jsonResponse(status, body) {
    const text = JSON.stringify(body);
    return { ok: status >= 200 && status < 300, status, text: () => Promise.resolve(text) };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

// Поднимает страницу: common.js + reviews.js в одном vm-контексте.
// search — строка адреса (?status=new&month=all); respond(url, init) -> {status, body}.
function bootPage({ search = '', respond }) {
    const ids = {};
    const document = {
        readyState: 'complete',
        documentElement: new El('html'),
        body: new El('body'),
        activeElement: null,
        visibilityState: 'visible',
        listeners: {},
        getElementById(id) { if (!ids[id]) ids[id] = new El('div', id); return ids[id]; },
        createElement: (t) => new El(t),
        addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
        removeEventListener() {},
        querySelector() { return null; },
        querySelectorAll() { return []; },
    };
    const urls = [];
    const window = {
        location: { search, pathname: '/reviews', hash: '' },
        history: { replaceState: (s, t, url) => urls.push(url), pushState: (s, t, url) => urls.push(url) },
        localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
        innerWidth: 1440,
        innerHeight: 900,
        listeners: {},
        addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
        removeEventListener() {},
    };
    const calls = [];
    const sandbox = {
        window, document,
        console, setTimeout, clearTimeout, Promise, JSON, Math, Date, Intl,
        URLSearchParams, Error, String, Number, Object, Array, isFinite, encodeURIComponent,
        fetch(url, init) {
            calls.push({ url, init });
            const r = respond(url, init) || { status: 200, body: {} };
            return Promise.resolve(jsonResponse(r.status, r.body));
        },
    };
    window.document = document;
    const ctx = vm.createContext(sandbox);
    vm.runInContext(commonJs, ctx, { filename: 'common.js' });
    sandbox.GH = window.GH;
    vm.runInContext(js, ctx, { filename: 'reviews.js' });
    return { ids, calls, urls, window, document };
}

// Ответ GET /api/reviews: только поля, которые читает страница.
function listPayload(reviews, unanswered) {
    const m = { count: reviews.length, rated: 0, avg_rating: null, unanswered, answered: 0, skipped: 0,
                unanswered_pct: null, median_response_hours: null, oldest_unanswered_hours: null };
    return {
        now: '2026-09-27T12:00', reviews,
        metrics: { total: m, by_bar: { bolshoy: m } },
        formulas: {}, sources: [{ key: 'yandex', name: 'Яндекс Карты' }, { key: 'bot', name: 'Бот' }],
    };
}
const REVIEW_BASE = {
    bar: 'bolshoy', rating: 5, author: 'Игорь', text: 'Отличный бар', created_at: '2026-09-20T18:00',
    status: 'new', reply: null, reply_draft: '', skip_reason: '', guest: null, origin: 'manual',
    added_at: '2026-09-20T18:05', added_by: 'dev', material_id: null, age_hours: 5,
};
const rv = (o) => Object.assign({}, REVIEW_BASE, o);

function fakeServer(state) {
    return (url, init) => {
        const method = (init && init.method) || 'GET';
        if (url.startsWith('/api/guest-hub/attention')) return { status: 200, body: state.attn };
        if (url.startsWith('/api/reviews?')) return { status: 200, body: state.list };
        if (method !== 'GET') return { status: 200, body: { review: null } };
        return { status: 404, body: { error: 'нет' } };
    };
}
const listUrls = (calls) => calls.filter((c) => c.url.startsWith('/api/reviews?')).map((c) => c.url);

atest('ссылка полосы ?status=new&month=all открывает «За всё время» + «Без ответа»', async () => {
    const st = { attn: { reviews_unanswered: 0 }, list: listPayload([], 0) };
    const { ids, calls, urls } = bootPage({ search: '?status=new&month=all', respond: fakeServer(st) });
    await tick();
    assert.equal(listUrls(calls)[0], '/api/reviews?all=1&status=new', 'список запрошен не за всё время');
    assert.equal(ids.rvMonthLabel.textContent, 'За всё время');
    assert.equal(ids.rvStatusLabel.textContent, 'Без ответа');
    assert.match(urls[urls.length - 1], /month=all/, 'адрес потерял month=all');
});

atest('без ?month «Без ответа» — за всё время, остальные — текущий месяц', async () => {
    const st = { attn: { reviews_unanswered: 0 }, list: listPayload([], 0) };
    let page = bootPage({ search: '?status=new', respond: fakeServer(st) });
    await tick();
    assert.equal(listUrls(page.calls)[0], '/api/reviews?all=1&status=new');
    page = bootPage({ search: '', respond: fakeServer(st) });
    await tick();
    assert.match(listUrls(page.calls)[0], /^\/api\/reviews\?month=\d{4}-\d{2}$/, 'по умолчанию — не месяц');
    assert.ok(!/month=/.test(page.urls[page.urls.length - 1]), 'текущий месяц не пишется в адрес');
    // Выбранный текущий месяц у «Без ответа» пишется явно — иначе F5 открыл бы «За всё время».
    const cur = listUrls(page.calls)[0].slice(-7);
    page = bootPage({ search: `?status=new&month=${cur}`, respond: fakeServer(st) });
    await tick();
    assert.equal(listUrls(page.calls)[0], `/api/reviews?month=${cur}&status=new`);
    assert.match(page.urls[page.urls.length - 1], new RegExp(`month=${cur}`), 'месяц пропал из адреса');
});

atest('карточки: гость со ссылкой ?q=, строка про Яндекс, три состояния материала, черновик как набран', async () => {
    const reviews = [
        rv({ id: 'r_y', source: 'yandex', material_id: 'm_gone', material_exists: false, reply_draft: '\nНачало ' }),
        rv({ id: 'r_b1', source: 'bot', guest: { phone: '+7 (921) 555-12-34', telegram: '@igor' },
             material_id: 'm_unk', material_exists: null }),
        rv({ id: 'r_b2', source: 'bot', guest: { phone: '', telegram: '@anna' },
             material_id: 'm_ok', material_exists: true }),
    ];
    const st = { attn: { reviews_unanswered: 3 }, list: listPayload(reviews, 3) };
    const { ids } = bootPage({ search: '?month=all', respond: fakeServer(st) });
    await tick();
    const html = ids.rvList.innerHTML;
    const card = (id) => html.split('<article ').find((c) => c.includes(`data-id="${id}"`)) || '';
    // Гость: телефон — последние 10 цифр (так номер находится в базе гостей).
    assert.match(card('r_b1'), /href="\/guests\?q=9215551234#guest"/, 'ссылка по телефону');
    assert.match(card('r_b2'), /href="\/guests\?q=%40anna#guest"/, 'ссылка по Telegram');
    // Яндекс: ни ссылки на гостя, ни строки-пояснения (убрана 2026-09-28 — шум на каждой карточке).
    assert.ok(!card('r_y').includes('/guests'), 'у отзыва с Яндекса не должно быть ссылки на гостя');
    assert.ok(!card('r_y').includes('не передают контакт'), 'вернулась строка «не передают контакт» на карточке');
    // Материал: удалён -> пометка и снова кнопка; null -> ссылка без ошибки; есть -> ссылка.
    assert.match(card('r_y'), /Материал удалён/);
    assert.match(card('r_y'), /data-act="material"/, 'у удалённого материала нет кнопки «Сделать материалом»');
    assert.ok(!card('r_y').includes('open=m_gone'), 'ссылка на удалённый материал');
    assert.match(card('r_b1'), /href="\/content-plan\?open=m_unk"/);
    assert.match(card('r_b1'), /не отвечает/, 'нет пояснения, что проверить материал не удалось');
    assert.ok(!card('r_b1').includes('data-act="material"'));
    assert.match(card('r_b2'), /href="\/content-plan\?open=m_ok"/);
    assert.ok(!card('r_b2').includes('Материал удалён'));
    // Черновик: перевод строки-«жертва» + текст как набран (с ведущей пустой строкой и пробелом).
    assert.ok(card('r_y').includes('>\n\nНачало </textarea>'), 'черновик показан не как набран');
});

atest('«ещё N без ответа за другие месяцы»: по счётчику полосы и только когда сравнимо', async () => {
    const st = { attn: { reviews_unanswered: 5 }, list: listPayload([], 3) };
    let page = bootPage({ search: '', respond: fakeServer(st) });
    await tick();
    await tick();
    const box = page.ids.rvElsewhere;
    assert.equal(box.hidden, false, 'подсказка не показана');
    assert.equal(page.ids.rvElsewhereText.textContent, 'Ещё 2 отзыва без ответа — за другие месяцы.');
    assert.match(box.getAttribute('data-tip'), /5 − 3 = 2/, 'в подсказке нет расчёта');
    // «Показать все без ответа» -> за всё время, только без ответа.
    page.ids.rvElsewhereShow.fire('click', {});
    await tick();
    assert.equal(listUrls(page.calls).pop(), '/api/reviews?all=1&status=new');
    assert.equal(box.hidden, true, 'у «За всё время» других месяцев нет');
    // Фильтр источника: счётчик полосы его не учитывает — не сравниваем.
    page = bootPage({ search: '?source=yandex', respond: fakeServer(st) });
    await tick();
    await tick();
    assert.equal(page.ids.rvElsewhere.hidden, true, 'с фильтром источника числа несравнимы');
    // Всё без ответа — в этом месяце: подсказки нет.
    page = bootPage({ search: '', respond: fakeServer({ attn: { reviews_unanswered: 3 }, list: listPayload([], 3) }) });
    await tick();
    await tick();
    assert.equal(page.ids.rvElsewhere.hidden, true);
});

atest('ответ на отзыв перечитывает список и полосу', async () => {
    const st = { attn: { reviews_unanswered: 1 }, list: listPayload([rv({ id: 'r_1', source: 'yandex' })], 1) };
    const page = bootPage({ search: '', respond: fakeServer(st) });
    await tick();
    const before = page.calls.length;
    const card = { getAttribute: () => 'r_1', querySelector: (s) => (s === '[data-draft]' ? { value: 'Спасибо!' } : null) };
    const btn = {
        getAttribute: (n) => (n === 'data-act' ? 'reply' : null), setAttribute() {}, disabled: false,
        closest: (s) => (s === '[data-act]' ? btn : s === '.gh-rv-card' ? card : null),
    };
    page.ids.rvList.contains = () => true;
    page.ids.rvList.fire('click', { target: btn, preventDefault() {} });
    await tick();
    await tick();
    const after = page.calls.slice(before).map((c) => `${(c.init && c.init.method) || 'GET'} ${c.url}`);
    assert.equal(after[0], 'POST /api/reviews/r_1/reply');
    assert.ok(after.includes('GET /api/guest-hub/attention?bar='), `полоса не перечитана: ${after.join(', ')}`);
    assert.ok(after.some((x) => x.startsWith('GET /api/reviews?')), 'список не перечитан');
});

atest('черновик при уходе со страницы уходит сразу, с keepalive и как набран', async () => {
    const st = { attn: { reviews_unanswered: 1 }, list: listPayload([rv({ id: 'r_1', source: 'yandex' })], 1) };
    const page = bootPage({ search: '', respond: fakeServer(st) });
    await tick();
    const card = { getAttribute: () => 'r_1', querySelector: () => null };
    const ta = (value) => ({
        tagName: 'TEXTAREA', value, classList: { toggle() {} },
        hasAttribute: (a) => a === 'data-draft',
        closest: (s) => (s === '.gh-rv-card' ? card : null),
    });
    const patches = () => page.calls.filter((c) => c.init && c.init.method === 'PATCH');
    // Обычное сохранение (уход фокуса) — без keepalive.
    page.ids.rvList.fire('input', { target: ta('Игорь,') });
    page.ids.rvList.fire('focusout', { target: ta('Игорь,') });
    await tick();
    assert.equal(patches().length, 1);
    assert.ok(!('keepalive' in patches()[0].init), 'обычное сохранение не должно идти с keepalive');
    // Набор и сразу F5 / закрытие вкладки: pagehide.
    page.ids.rvList.fire('input', { target: ta('Игорь, простите за ожидание. ') });
    page.window.listeners.pagehide.forEach((f) => f({}));
    assert.equal(patches().length, 2, 'при pagehide запрос должен уйти сразу, без ожидания');
    const last = patches()[1];
    assert.equal(last.url, '/api/reviews/r_1');
    assert.equal(last.init.keepalive, true, 'без keepalive браузер оборвёт запрос вместе со страницей');
    assert.equal(JSON.parse(last.init.body).reply_draft, 'Игорь, простите за ожидание. ', 'пробел в конце потерян');
});

atest('/guests?q=…#guest: вкладка «Гость» подставляет запрос и ищет один раз', async () => {
    // Приёмная сторона ссылки «Открыть в Маркетинге»: static/js/guests/views-guest.js.
    const ids = {};
    const document = {
        getElementById(id) { if (!ids[id]) { ids[id] = new El('div', id); ids[id].dataset = {}; } return ids[id]; },
        querySelector() { return null; },
        querySelectorAll() { return []; },
        createElement: (t) => new El(t),
        addEventListener() {},          // DOMContentLoaded не нужен: вкладку открываем сами
        documentElement: new El('html'),
    };
    const fetched = [];
    const sandbox = {
        console, setTimeout, clearTimeout, Promise, URLSearchParams, JSON, Math, Date, Object, Array,
        String, Number, isNaN, parseInt, parseFloat, encodeURIComponent, document,
        history: { replaceState() {}, pushState() {} },
        location: { hash: '#guest', search: '?q=9215551234' },
        fetch(url) {
            fetched.push(url);
            return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ guests: [] }) });
        },
    };
    sandbox.window = sandbox;
    sandbox.GUESTS_CONFIG = { bars: [] };
    const ctx = vm.createContext(sandbox);
    for (const f of ['static/js/guests/formulas.js', 'static/js/guests/common.js', 'static/js/guests/views-guest.js']) {
        vm.runInContext(read(f), ctx, { filename: f });
    }
    sandbox.Guests.activateTab('guest');
    assert.equal(ids.guestQ.value, '9215551234', 'запрос из адреса не подставлен в поиск');
    assert.deepEqual(fetched, ['/api/guests/search?q=9215551234'], 'поиск не запущен сам');
    // Смена периода перерисовывает вкладку — повторного поиска быть не должно.
    sandbox.Guests.state.anchor = new Date(2020, 0, 15);
    sandbox.Guests.activateTab('guest');
    await tick();
    assert.equal(fetched.length, 1, 'поиск повторился при перерисовке вкладки');
});

for (const { name, fn } of asyncTests) {
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


test('сверка с Яндекс Бизнесом: строка статуса, ответы из Яндекса, пропавшие отзывы', () => {
    assert.match(html, /id="rvSync"/, 'нет строки сверки');
    assert.match(routes, /payload\['yandex_sync'\]/, 'список не отдаёт yandex_sync');
    for (const status of ['ok', 'running', 'never', 'partial', 'captcha', 'expired', 'not_configured', 'stale']) {
        assert.match(js, new RegExp(`status === '${status}'|${status}: '`), `статус сверки ${status} не обработан`);
    }
    assert.match(js, /var SYNC_STALE_MIN = 60;/, 'нет константы прерванной сверки');
    assert.match(js, /r\.reply\.source/, 'ответ из Яндекса не отличается от сохранённого здесь');
    assert.match(js, /Опубликован в Яндексе/, 'нет отметки «Опубликован в Яндексе»');
    assert.match(js, /r\.gone_at/, 'пропавший из Яндекса отзыв не помечается');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

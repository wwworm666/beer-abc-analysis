/**
 * Проверки страницы «Доступ агентов» (/admin/mcp).
 *
 *     node tests/test_mcp_admin_render.mjs
 *
 * Текстовые: шаблон объявляет все узлы, которые ищет JS; id не повторяются; каждый
 * вызов API из JS есть в routes/mcp.py с тем же методом; классы из шаблона и JS описаны
 * в CSS; цвета только через токены (ни одного HEX/rgb); нет эмодзи и инлайновых
 * обработчиков; стили и скрипт с кэш-бастингом; ссылка в меню только для администратора.
 * Исполнение: admin_mcp.js в vm с поддельным DOM и fetch — страница рисует токены,
 * журнал и настройки, а данные (имя токена, превью аргументов) попадают в textContent,
 * а не в разметку.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const html = read('templates/admin_mcp.html');
const js = read('static/js/admin_mcp.js');
const css = read('static/admin_mcp.css');
const routes = read('routes/mcp.py');
const nav = read('templates/shared/nav.html');

let passed = 0;
let failed = 0;
const pending = [];
function test(name, fn) {
    try {
        const out = fn();
        if (out && typeof out.then === 'function') {
            pending.push(out.then(() => { passed++; console.log(`  ok  ${name}`); },
                (e) => { failed++; console.log(`FAIL  ${name}\n      ${e && e.message}`); }));
            return;
        }
        passed++;
        console.log(`  ok  ${name}`);
    } catch (e) {
        failed++;
        console.log(`FAIL  ${name}`);
        console.log(`      ${e && e.message}`);
    }
}

const noComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '');
const cssClasses = new Set([...noComments(css).matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
const templateIds = [...html.matchAll(/\sid="([^"{]+)"/g)].map((m) => m[1]);

test('все id, которые ищет JS, объявлены в шаблоне', () => {
    const wanted = new Set([...js.matchAll(/byId\('([^']+)'\)/g)].map((m) => m[1]));
    for (const m of js.matchAll(/querySelectorAll\('#([\w-]+)/g)) wanted.add(m[1]);
    assert.ok(wanted.size >= 20, `подозрительно мало id: ${wanted.size}`);
    const missing = [...wanted].filter((id) => !templateIds.includes(id));
    assert.deepEqual(missing, [], `нет узлов в шаблоне: ${missing.join(', ')}`);
});

test('id в шаблоне не повторяются', () => {
    const dup = templateIds.filter((id, i) => templateIds.indexOf(id) !== i);
    assert.deepEqual(dup, [], `повторы id: ${dup.join(', ')}`);
});

test('каждый вызов API есть в routes/mcp.py с тем же методом', () => {
    const block = js.match(/var API = \{([\s\S]*?)\};/);
    assert.ok(block, 'нет таблицы API');
    const api = {};
    for (const m of block[1].matchAll(/(\w+):\s*'([^']+)'/g)) api[m[1]] = m[2];
    const routeMap = {};
    for (const m of routes.matchAll(/@mcp_bp\.route\('([^']+)'(?:,\s*methods=\[([^\]]*)\])?/g)) {
        const p = m[1].replace(/<[^>]+>/g, '<>');
        const methods = m[2] ? [...m[2].matchAll(/'(\w+)'/g)].map((x) => x[1]) : ['GET'];
        routeMap[p] = (routeMap[p] || []).concat(methods);
    }
    const calls = [...js.matchAll(/call\('(GET|POST|PUT|PATCH|DELETE)', API\.(\w+)( \+)?/g)];
    assert.ok(calls.length >= 8, `мало вызовов: ${calls.length}`);
    const bad = [];
    for (const [, method, key, plus] of calls) {
        assert.ok(api[key], `ключ API.${key} не описан`);
        let url = api[key].split('?')[0];
        if (plus && url.endsWith('/')) url += '<>';        // API.token + id -> /tokens/<id>
        if (!(routeMap[url] || []).includes(method)) bad.push(`${method} ${url}`);
    }
    assert.deepEqual(bad, [], `нет маршрута: ${bad.join(', ')}`);
    assert.ok(!/\bfetch\(/.test(js.replace(/return fetch\(url, opt\)/, '')), 'fetch мимо call()');
});

test('классы шаблона и JS описаны в CSS (префикс mcp-)', () => {
    const used = new Set();
    for (const m of html.matchAll(/class="([^"{]+)"/g)) {
        for (const c of m[1].split(/\s+/)) if (c.startsWith('mcp-')) used.add(c);
    }
    for (const m of js.matchAll(/['"\s](mcp-[\w-]*\w)(?![\w-])/g)) used.add(m[1]);
    // Классы тегов собираются как 'mcp-tag-' + статус: все статусы должны иметь стиль.
    for (const s of ['ok', 'error', 'denied', 'active', 'revoked', 'expired', 'owner_disabled', 'owner_not_admin',
                     'owner_missing']) used.add(`mcp-tag-${s}`);
    used.delete('mcp-tag-');
    const missing = [...used].filter((c) => !cssClasses.has(c));
    assert.deepEqual(missing, [], `классы без стилей: ${missing.join(', ')}`);
    const stray = [...cssClasses].filter((c) => !c.startsWith('mcp-'));
    assert.deepEqual(stray, [], `классы без префикса mcp-: ${stray.join(', ')}`);
});

test('цвета — только токены: ни HEX, ни rgb/hsl', () => {
    const hex = [...noComments(css).matchAll(/#[0-9A-Fa-f]{3,8}\b/g)].map((m) => m[0]);
    assert.deepEqual(hex, [], `HEX в admin_mcp.css: ${hex.join(', ')}`);
    assert.ok(!/\b(rgba?|hsla?)\(/.test(css), 'rgb()/hsl() в admin_mcp.css');
    const tokenBlock = css.match(/\.mcp-page \{([\s\S]*?)\n\}/);
    assert.ok(tokenBlock, 'нет блока токенов .mcp-page');
    const declared = new Set([...tokenBlock[1].matchAll(/(--mcp-[\w-]+):/g)].map((m) => m[1]));
    const usedVars = new Set([...css.matchAll(/var\((--mcp-[\w-]+)/g)].map((m) => m[1]));
    const undeclared = [...usedVars].filter((v) => !declared.has(v));
    assert.deepEqual(undeclared, [], `токены не объявлены: ${undeclared.join(', ')}`);
    assert.ok(!/['"]#[0-9A-Fa-f]{3,8}['"]/.test(js), 'HEX в admin_mcp.js');
    assert.ok(!/style="/.test(html), 'инлайновый стиль в шаблоне');
    assert.ok(!/\.style\./.test(js), 'инлайновый стиль из JS');
});

test('нет эмодзи и инлайновых обработчиков', () => {
    const emoji = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2300}-\u{23FF}\u{FE0F}]/u;
    for (const [name, text] of [['admin_mcp.html', html], ['admin_mcp.js', js], ['admin_mcp.css', css]]) {
        const m = text.match(emoji);
        assert.ok(!m, `${name}: символ ${m && JSON.stringify(m[0])}`);
    }
    assert.ok(!/\son\w+="/.test(html), 'onclick= и т.п. в шаблоне');
    assert.ok(!/innerHTML/.test(js), 'innerHTML в admin_mcp.js — данные только через textContent');
});

test('режим токена: выбор при выпуске и пояснение суффиксов адреса', () => {
    assert.match(html, /<select id="mcpTokenMode" class="mcp-input">[\s\S]*?\{% for m in modes\|reverse %\}/);
    assert.match(html, /<th>Режим<\/th>/);
    assert.match(html, /\/read<\/code>[\s\S]*\/draft<\/code>/, 'пояснение суффиксов /read и /draft');
    for (const s of ['owner_disabled', 'owner_not_admin', 'owner_missing']) {
        assert.match(js, new RegExp(`${s}: '`), `нет подписи статуса ${s}`);
    }
});

test('каркас страницы: меню, кэш-бастинг, скрытые узлы прячутся', () => {
    assert.match(html, /\{% include 'shared\/nav\.html' %\}/);
    assert.match(html, /\/static\/admin_mcp\.css\?v=\{\{ app_version \}\}/);
    assert.match(html, /\/static\/js\/admin_mcp\.js\?v=\{\{ app_version \}\}/);
    assert.match(html, /<body class="dashboard-page mcp-page">/);
    for (const cls of ['mcp-token-box', 'mcp-empty', 'mcp-panel']) {
        assert.match(css, new RegExp(`\\.${cls}\\[hidden\\] \\{ display: none; \\}`), `.${cls}[hidden]`);
    }
    assert.match(html, /Токен показан один раз/);
    assert.match(html, /\{% if oauth_available %\}[\s\S]*id="mcpGrantsPanel"[\s\S]*\{% endif %\}/,
        'раздел OAuth скрыт, если модуля нет');
});

test('ссылка «Доступ агентов» в меню — только администратору, рядом с «Аккаунты»', () => {
    const block = nav.match(/\{% if current_user and current_user\.is_admin %\}([\s\S]*?)\{% endif %\}/);
    assert.ok(block, 'нет админ-блока в меню');
    assert.match(block[1], /href="\/admin\/users"/);
    assert.match(block[1], /href="\/admin\/mcp"[\s\S]*Доступ агентов/);
    assert.equal((nav.match(/\/admin\/mcp/g) || []).length, 1, 'ссылка ровно одна');
});

// ------------------------------------------------------------------ исполнение в vm

class El {
    constructor(tag, id) {
        this.tagName = String(tag || 'div').toUpperCase();
        this.id = id || '';
        this.children = [];
        this.listeners = {};
        this.hidden = false;
        this.disabled = false;
        this.checked = false;
        this.value = '';
        this.type = '';
        this._text = '';
        this.className = '';
        const set = new Set();
        this.classList = { add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c) };
    }
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
    set textContent(v) { this._text = String(v); this.children = []; }
    get childNodes() { return this.children; }
    appendChild(c) { this.children.push(c); return c; }
    removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; }
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
    fire(t) { (this.listeners[t] || []).forEach((f) => f({})); }
    select() {}
}

function boot(respond) {
    const nodes = {};
    const byId = (id) => {
        if (!templateIds.includes(id)) return null;
        if (!nodes[id]) nodes[id] = new El('div', id);
        return nodes[id];
    };
    const domainBoxes = ['content', 'stocks', 'analytics', 'staff'].map((k) => {
        const box = new El('input');
        box.value = k;
        return box;
    });
    const calls = [];
    const document = {
        readyState: 'complete',
        body: new El('body'),
        getElementById: byId,
        createElement: (tag) => new El(tag),
        querySelectorAll: (sel) => (sel.includes('mcp-domain') ? domainBoxes : []),
        addEventListener() {},
        execCommand() { return true; },
    };
    const fetch = (url, opt) => {
        calls.push({ url, method: opt.method, body: opt.body ? JSON.parse(opt.body) : undefined });
        const [status, body] = respond(url, opt);
        return Promise.resolve({ ok: status < 400, status, text: () => Promise.resolve(JSON.stringify(body)) });
    };
    const confirms = [];
    const window = { confirm: (text) => { confirms.push(text); return true; } };
    const context = vm.createContext({ document, window, fetch, navigator: {}, setTimeout, console });
    vm.runInContext(js, context, { filename: 'admin_mcp.js' });
    return { nodes, byId, calls, confirms, domainBoxes };
}

const tick = () => new Promise((r) => setTimeout(r, 0));
const EVIL = '<img src=x onerror=alert(1)>';
const DATA = {
    tokens: { tokens: [
        { id: 'st_1', name: EVIL, prefix: 'kmcp_abcdefg', domains: ['*'], created_at: '2026-09-27T10:00:00+03:00',
          last_used_at: null, expires_at: null, status: 'active', token_status: 'active', mode: 'draft' },
        { id: 'st_2', name: 'старый', prefix: 'kmcp_zzzzzzz', domains: ['content', 'staff'],
          created_at: '2026-09-01T10:00:00+03:00', last_used_at: '2026-09-02T11:30:00+03:00',
          expires_at: '2026-10-01T10:00:00+03:00', status: 'revoked', token_status: 'revoked', mode: 'full' },
        { id: 'st_3', name: 'ночной', prefix: 'kmcp_yyyyyyy', domains: ['*'], created_at: '2026-09-03T10:00:00+03:00',
          last_used_at: null, expires_at: null, status: 'owner_disabled', token_status: 'active', mode: 'read' }],
        domains: [{ key: 'content', title: 'Контент и отзывы' }, { key: 'staff', title: 'Сотрудники' }],
        modes: [{ key: 'read', title: 'Только чтение' }, { key: 'draft', title: 'Чтение и черновики' },
                { key: 'full', title: 'Полный доступ' }] },
    audit: { items: [{ at: '2026-09-27T16:40:05+03:00', tool: 'content_plan_get', connector: 'content',
        client_name: 'Claude', status: 'error', http_status: 400, duration_ms: 12,
        args_preview: '{"note":"' + EVIL + '"}', error_preview: 'Неизвестный бар' }] },
    settings: { settings: { notify_chat_id: '-100500', oauth_redirect_hosts: ['claude.ai', 'localhost'] },
        subscribers: ['670033096'], bot_configured: false },
};

function respond(url, opt) {
    if (url === '/api/admin/mcp/tokens' && opt.method === 'GET') return [200, DATA.tokens];
    if (url === '/api/admin/mcp/tokens' && opt.method === 'POST') {
        return [200, { token: 'kmcp_' + 'x'.repeat(40), row: {},
            commands: [{ connector: '/mcp/content', title: 'Контент', command: 'claude mcp add --transport http kultura-content http://h/mcp/content --header "Authorization: Bearer kmcp_xx"' }] }];
    }
    if (url.startsWith('/api/admin/mcp/tokens/')) return [200, { ok: true, revoked: true }];
    if (url.startsWith('/api/admin/mcp/audit')) return [200, DATA.audit];
    if (url === '/api/admin/mcp/settings') return [200, DATA.settings];
    if (url === '/api/admin/mcp/grants') return [200, { available: false, grants: [] }];
    return [404, { error: 'нет' }];
}

test('исполнение: токены, журнал и настройки рисуются, данные — текстом', async () => {
    const page = boot(respond);
    await tick(); await tick(); await tick();
    const rows = page.nodes.mcpTokensBody.children;
    assert.equal(rows.length, 3);
    assert.equal(rows[0].children[0].textContent, EVIL, 'имя токена — текстом, как есть');
    assert.equal(rows[0].children[2].textContent, 'все разделы');
    assert.equal(rows[1].children[2].textContent, 'Контент и отзывы, Сотрудники');
    assert.equal(rows[1].className, 'mcp-row-off');
    assert.equal(rows[0].children[3].textContent, 'Чтение и черновики', 'режим токена в списке');
    assert.equal(rows[1].children[3].textContent, 'Полный доступ');
    assert.equal(rows[0].children[7].children[0].className, 'mcp-tag mcp-tag-active');
    assert.equal(rows[1].children[8].children.length, 0, 'отозванный токен без кнопки');
    assert.equal(rows[2].children[7].children[0].textContent, 'владелец отключён', 'состояние владельца');
    assert.equal(rows[2].children[7].children[0].className, 'mcp-tag mcp-tag-owner_disabled');
    assert.equal(rows[2].className, 'mcp-row-off');
    assert.equal(rows[2].children[8].children.length, 1, 'токен неработающего владельца можно отозвать');
    assert.equal(page.nodes.mcpTokensEmpty.hidden, true);
    const audit = page.nodes.mcpAuditBody.children[0];
    assert.equal(audit.children[0].textContent, '27.09.2026 16:40:05');
    assert.equal(audit.children[4].children[0].textContent, 'ошибка');
    assert.equal(audit.children[7].children[0].textContent, '{"note":"' + EVIL + '"}');
    assert.equal(audit.children[7].children[1].textContent, 'Неизвестный бар');
    const select = page.nodes.mcpChatSelect;
    assert.deepEqual(select.children.map((o) => o.value), ['', '670033096', '-100500'], 'сохранённый чат вне списка');
    assert.equal(select.value, '-100500');
    assert.equal(page.nodes.mcpHosts.value, 'claude.ai\nlocalhost');
    assert.match(page.nodes.mcpBotStatus.textContent, /нет токена бота/);
    assert.ok(page.calls.some((c) => c.url === '/api/admin/mcp/audit?limit=200'));
});

test('исполнение: выпуск токена показывает токен и команды один раз', async () => {
    const page = boot(respond);
    await tick();
    page.nodes.mcpTokenCreate.fire('click');
    await tick(); await tick();
    assert.match(page.nodes.mcpTokenError.textContent, /имя/, 'без имени — подсказка, без запроса');
    page.byId('mcpTokenName').value = 'ноутбук';
    page.byId('mcpDomainAll').checked = false;
    page.domainBoxes[0].checked = true;
    page.domainBoxes[3].checked = true;
    page.byId('mcpTokenExpiry').value = '90';
    page.byId('mcpTokenMode').value = 'read';
    page.nodes.mcpTokenCreate.fire('click');
    await tick(); await tick(); await tick();
    const post = page.calls.find((c) => c.method === 'POST');
    assert.deepEqual(post.body, { name: 'ноутбук', domains: ['content', 'staff'], expires_days: 90, mode: 'read' });
    assert.equal(page.nodes.mcpTokenResult.hidden, false);
    assert.equal(page.nodes.mcpTokenValue.textContent, 'kmcp_' + 'x'.repeat(40));
    assert.match(page.nodes.mcpCommands.textContent, /claude mcp add --transport http kultura-content/);
    page.nodes.mcpTokenHide.fire('click');
    assert.equal(page.nodes.mcpTokenResult.hidden, true);
    assert.equal(page.nodes.mcpTokenValue.textContent, '', 'скрытый токен стирается со страницы');
});

test('исполнение: отзыв спрашивает подтверждение, настройки уходят PUT', async () => {
    const page = boot(respond);
    await tick(); await tick(); await tick();
    const revokeBtn = page.nodes.mcpTokensBody.children[0].children[8].children[0];
    revokeBtn.fire('click');
    await tick();
    assert.equal(page.confirms.length, 1);
    assert.ok(page.calls.some((c) => c.method === 'DELETE' && c.url === '/api/admin/mcp/tokens/st_1'));
    page.nodes.mcpChatInput.value = ' 123 ';
    page.nodes.mcpHosts.value = 'claude.ai\n\n localhost \n';
    page.nodes.mcpSettingsSave.fire('click');
    await tick(); await tick();
    const put = page.calls.find((c) => c.method === 'PUT');
    assert.deepEqual(put.body, { notify_chat_id: '123', oauth_redirect_hosts: ['claude.ai', 'localhost'] });
    assert.equal(page.nodes.mcpSettingsOk.textContent, 'Сохранено');
});

test('исполнение: OAuth-приложения с режимом доступа', async () => {
    const grant = { client_id: 'kmcpc_1', client_name: 'Claude', redirect_host: 'claude.ai',
        connector_title: 'Контент и отзывы', resource: 'https://h/mcp/content/draft', mode: 'draft',
        mode_title: 'Чтение и черновики', user_login: 'owner', created_at: '2026-09-27T10:00:00+03:00',
        last_used_at: null };
    const page = boot((url, opt) => (url === '/api/admin/mcp/grants' ? [200, { available: true, grants: [grant] }]
        : respond(url, opt)));
    await tick(); await tick(); await tick();
    const row = page.nodes.mcpGrantsBody.children[0];
    assert.equal(row.children[0].textContent, 'Claude');
    assert.equal(row.children[3].textContent, 'Чтение и черновики', 'режим подключения в таблице');
    assert.equal(row.children[7].children[0].textContent, 'Отключить');
    assert.match(html, /<th>Режим<\/th>\s*<th>Чьё<\/th>/, 'колонка «Режим» у OAuth-приложений');
});

await Promise.all(pending);
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);

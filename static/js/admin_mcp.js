/**
 * Страница «Доступ агентов» (/admin/mcp): токены MCP, OAuth-приложения, журнал вызовов, настройки.
 *
 * Данные — админ-API routes/mcp.py (таблица API ниже). Разметка строк собирается через
 * DOM (textContent), а не строками HTML: имена токенов, клиентов и превью аргументов
 * приходят от пользователей и агентов — это данные, их нельзя исполнять как разметку.
 * Токен целиком приходит только в ответе на выпуск и показывается один раз.
 */
(function () {
    'use strict';

    var API = {
        tokens: '/api/admin/mcp/tokens',
        token: '/api/admin/mcp/tokens/',
        grants: '/api/admin/mcp/grants',
        grant: '/api/admin/mcp/grants/',
        audit: '/api/admin/mcp/audit',
        settings: '/api/admin/mcp/settings'
    };

    // Сколько строк журнала показывать: страница — обзор последнего, глубже — фильтром.
    var AUDIT_LIMIT = 200;

    var STATUS_LABELS = { ok: 'успешно', error: 'ошибка', denied: 'отказ' };
    // Статус строки токена: сам токен (действует/отозван/истёк) или, если он действует,
    // но владелец не может им пользоваться, — состояние владельца (tokens.list_tokens).
    var TOKEN_STATUS_LABELS = {
        active: 'действует', revoked: 'отозван', expired: 'истёк',
        owner_disabled: 'владелец отключён', owner_not_admin: 'владелец не админ',
        owner_missing: 'владелец удалён'
    };
    var DOMAIN_TITLES = {};
    var MODE_TITLES = { full: 'Полный доступ', draft: 'Чтение и черновики', read: 'Только чтение' };

    function byId(id) { return document.getElementById(id); }

    function call(method, url, body) {
        var opt = { method: method, credentials: 'same-origin', headers: { 'Accept': 'application/json' } };
        if (body !== undefined) {
            opt.headers['Content-Type'] = 'application/json';
            opt.body = JSON.stringify(body);
        }
        return fetch(url, opt).then(function (r) {
            return r.text().then(function (text) {
                var data = {};
                try { data = text ? JSON.parse(text) : {}; } catch (e) { data = {}; }
                if (!r.ok) throw new Error(data.error || ('Ошибка ' + r.status));
                return data;
            });
        });
    }

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function cell(row, text, cls) {
        var td = el('td', cls || '', text === null || text === undefined || text === '' ? '—' : text);
        row.appendChild(td);
        return td;
    }

    // '2026-09-27T16:40:05+03:00' -> '27.09.2026 16:40'
    function fmtTime(iso, withSeconds) {
        if (!iso) return '—';
        var m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):?(\d{2})?/);
        if (!m) return String(iso);
        return m[3] + '.' + m[2] + '.' + m[1] + ' ' + m[4] + ':' + m[5] + (withSeconds && m[6] ? ':' + m[6] : '');
    }

    function setText(id, text) {
        var node = byId(id);
        if (node) node.textContent = text || '';
    }

    function copyText(text, button) {
        function done() {
            var old = button.textContent;
            button.textContent = 'Скопировано';
            setTimeout(function () { button.textContent = old; }, 1500);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
        } else {
            fallbackCopy(text);
            done();
        }
    }

    function fallbackCopy(text) {
        var area = el('textarea', 'mcp-offscreen');
        area.value = text;
        document.body.appendChild(area);
        area.select();
        try { document.execCommand('copy'); } catch (e) { /* владелец скопирует вручную */ }
        document.body.removeChild(area);
    }

    function domainsLabel(domains) {
        if (!domains || !domains.length) return '—';
        if (domains.indexOf('*') >= 0) return 'все разделы';
        return domains.map(function (d) { return DOMAIN_TITLES[d] || d; }).join(', ');
    }

    // ------------------------------------------------------------ токены

    function pickedDomains() {
        if (byId('mcpDomainAll').checked) return ['*'];
        var out = [];
        var boxes = document.querySelectorAll('#mcpDomainChecks input.mcp-domain');
        for (var i = 0; i < boxes.length; i++) if (boxes[i].checked) out.push(boxes[i].value);
        return out;
    }

    function syncDomainBoxes() {
        var all = byId('mcpDomainAll').checked;
        var boxes = document.querySelectorAll('#mcpDomainChecks input.mcp-domain');
        for (var i = 0; i < boxes.length; i++) boxes[i].disabled = all;
    }

    function createToken() {
        setText('mcpTokenError', '');
        var name = byId('mcpTokenName').value.trim();
        var domains = pickedDomains();
        if (!name) { setText('mcpTokenError', 'Дайте токену имя'); return; }
        if (!domains.length) { setText('mcpTokenError', 'Выберите хотя бы один раздел'); return; }
        var expiry = byId('mcpTokenExpiry').value;
        var mode = byId('mcpTokenMode').value || 'full';
        var button = byId('mcpTokenCreate');
        button.disabled = true;
        call('POST', API.tokens, { name: name, domains: domains, expires_days: expiry ? Number(expiry) : null,
                                   mode: mode })
            .then(function (data) {
                showToken(data.token, data.commands || []);
                byId('mcpTokenName').value = '';
                loadTokens();
            })
            .catch(function (e) { setText('mcpTokenError', e.message); })
            .then(function () { button.disabled = false; });
    }

    function showToken(token, commands) {
        byId('mcpTokenValue').textContent = token;
        var box = byId('mcpCommands');
        box.textContent = '';
        commands.forEach(function (c) {
            var row = el('div', 'mcp-cmd');
            row.appendChild(el('div', 'mcp-cmd-title', c.title + ' — ' + c.connector));
            var line = el('div', 'mcp-copy-row');
            line.appendChild(el('code', 'mcp-code mcp-cmd-text', c.command));
            var btn = el('button', 'mcp-btn mcp-btn-ghost mcp-btn-sm', 'Скопировать');
            btn.type = 'button';
            btn.addEventListener('click', function () { copyText(c.command, btn); });
            line.appendChild(btn);
            row.appendChild(line);
            box.appendChild(row);
        });
        byId('mcpTokenResult').hidden = false;
    }

    function hideToken() {
        byId('mcpTokenValue').textContent = '';
        byId('mcpCommands').textContent = '';
        byId('mcpTokenResult').hidden = true;
    }

    function loadTokens() {
        setText('mcpTokensError', '');
        return call('GET', API.tokens).then(function (data) {
            (data.domains || []).forEach(function (d) { DOMAIN_TITLES[d.key] = d.title; });
            (data.modes || []).forEach(function (m) { MODE_TITLES[m.key] = m.title; });
            renderTokens(data.tokens || []);
        }).catch(function (e) { setText('mcpTokensError', e.message); });
    }

    function renderTokens(tokens) {
        var body = byId('mcpTokensBody');
        body.textContent = '';
        byId('mcpTokensEmpty').hidden = tokens.length > 0;
        tokens.forEach(function (t) {
            var tokenStatus = t.token_status || t.status;
            var row = el('tr', t.status === 'active' ? '' : 'mcp-row-off');
            cell(row, t.name).classList.add('mcp-strong');
            cell(row, t.prefix ? t.prefix + '…' : '', 'mcp-mono');
            cell(row, domainsLabel(t.domains));
            cell(row, MODE_TITLES[t.mode] || t.mode || MODE_TITLES.full);
            cell(row, fmtTime(t.created_at));
            cell(row, fmtTime(t.last_used_at));
            cell(row, t.expires_at ? fmtTime(t.expires_at) : 'без срока');
            var st = cell(row, '');
            st.textContent = '';
            st.appendChild(el('span', 'mcp-tag mcp-tag-' + t.status, TOKEN_STATUS_LABELS[t.status] || t.status));
            var act = cell(row, '');
            act.textContent = '';
            if (tokenStatus === 'active') {
                var btn = el('button', 'mcp-btn mcp-btn-danger mcp-btn-sm', 'Отозвать');
                btn.type = 'button';
                btn.addEventListener('click', function () { revokeToken(t); });
                act.appendChild(btn);
            }
            body.appendChild(row);
        });
    }

    function revokeToken(t) {
        if (!window.confirm('Отозвать токен «' + t.name + '»? Клиенты с этим токеном сразу потеряют доступ.')) return;
        call('DELETE', API.token + encodeURIComponent(t.id))
            .then(loadTokens)
            .catch(function (e) { setText('mcpTokensError', e.message); });
    }

    // ------------------------------------------------------------ OAuth-приложения

    function loadGrants() {
        if (!byId('mcpGrantsPanel')) return Promise.resolve();
        setText('mcpGrantsError', '');
        return call('GET', API.grants).then(function (data) {
            if (!data.available) { byId('mcpGrantsPanel').hidden = true; return; }
            renderGrants(data.grants || []);
        }).catch(function (e) { setText('mcpGrantsError', e.message); });
    }

    function renderGrants(grants) {
        var body = byId('mcpGrantsBody');
        body.textContent = '';
        byId('mcpGrantsEmpty').hidden = grants.length > 0;
        grants.forEach(function (g) {
            var row = el('tr');
            cell(row, g.client_name).classList.add('mcp-strong');
            cell(row, g.redirect_host, 'mcp-mono');
            cell(row, g.connector_title || g.resource);
            cell(row, g.mode_title || MODE_TITLES[g.mode] || '');
            cell(row, g.user_display_name || g.user_login);
            cell(row, fmtTime(g.created_at));
            cell(row, fmtTime(g.last_used_at));
            var act = cell(row, '');
            act.textContent = '';
            var btn = el('button', 'mcp-btn mcp-btn-danger mcp-btn-sm', 'Отключить');
            btn.type = 'button';
            btn.addEventListener('click', function () { revokeGrant(g); });
            act.appendChild(btn);
            body.appendChild(row);
        });
    }

    function revokeGrant(g) {
        if (!window.confirm('Отключить приложение «' + (g.client_name || g.client_id) +
                            '»? Все его токены погаснут, для работы понадобится новое подключение.')) return;
        call('DELETE', API.grant + encodeURIComponent(g.client_id))
            .then(loadGrants)
            .catch(function (e) { setText('mcpGrantsError', e.message); });
    }

    // ------------------------------------------------------------ журнал

    function loadAudit() {
        setText('mcpAuditError', '');
        var params = ['limit=' + AUDIT_LIMIT];
        var tool = byId('mcpAuditTool').value.trim();
        var status = byId('mcpAuditStatus').value;
        if (tool) params.push('tool=' + encodeURIComponent(tool));
        if (status) params.push('status=' + encodeURIComponent(status));
        return call('GET', API.audit + '?' + params.join('&')).then(function (data) {
            renderAudit(data.items || []);
        }).catch(function (e) { setText('mcpAuditError', e.message); });
    }

    function renderAudit(items) {
        var body = byId('mcpAuditBody');
        body.textContent = '';
        byId('mcpAuditEmpty').hidden = items.length > 0;
        items.forEach(function (a) {
            var row = el('tr');
            cell(row, fmtTime(a.at, true), 'mcp-nowrap');
            cell(row, a.tool, 'mcp-mono');
            cell(row, a.connector);
            cell(row, a.client_name);
            var st = cell(row, '');
            st.textContent = '';
            st.appendChild(el('span', 'mcp-tag mcp-tag-' + a.status, STATUS_LABELS[a.status] || a.status));
            cell(row, a.http_status);
            cell(row, a.duration_ms);
            var det = cell(row, '');
            det.textContent = '';
            if (a.args_preview && a.args_preview !== '{}') det.appendChild(el('code', 'mcp-code mcp-args', a.args_preview));
            if (a.error_preview) det.appendChild(el('div', 'mcp-err-text', a.error_preview));
            if (!det.childNodes.length) det.textContent = '—';
            body.appendChild(row);
        });
    }

    // ------------------------------------------------------------ настройки

    function loadSettings() {
        setText('mcpSettingsError', '');
        return call('GET', API.settings).then(renderSettings)
            .catch(function (e) { setText('mcpSettingsError', e.message); });
    }

    function renderSettings(data) {
        var s = data.settings || {};
        var chat = String(s.notify_chat_id || '');
        var select = byId('mcpChatSelect');
        select.textContent = '';
        var none = el('option', '', '— не выбран —');
        none.value = '';
        select.appendChild(none);
        var subscribers = data.subscribers || [];
        subscribers.forEach(function (id) {
            var opt = el('option', '', id);
            opt.value = id;
            select.appendChild(opt);
        });
        var listed = subscribers.indexOf(chat) >= 0;
        if (chat && !listed) {
            var own = el('option', '', chat + ' (введён вручную)');
            own.value = chat;
            select.appendChild(own);
        }
        select.value = chat;
        byId('mcpChatInput').value = '';
        byId('mcpHosts').value = (s.oauth_redirect_hosts || []).join('\n');
        setText('mcpBotStatus', data.bot_configured ? 'Бот подключён.'
            : 'У сервиса нет токена бота (TELEGRAM_OPEN_CHECK_BOT_TOKEN) — отправка не заработает.');
    }

    function saveSettings() {
        setText('mcpSettingsError', '');
        setText('mcpSettingsOk', '');
        var manual = byId('mcpChatInput').value.trim();
        var chat = manual || byId('mcpChatSelect').value;
        var hosts = byId('mcpHosts').value.split(/\n+/).map(function (h) { return h.trim(); })
            .filter(function (h) { return h; });
        var button = byId('mcpSettingsSave');
        button.disabled = true;
        call('PUT', API.settings, { notify_chat_id: chat, oauth_redirect_hosts: hosts })
            .then(function (data) { renderSettings(data); setText('mcpSettingsOk', 'Сохранено'); })
            .catch(function (e) { setText('mcpSettingsError', e.message); })
            .then(function () { button.disabled = false; });
    }

    // ------------------------------------------------------------ запуск

    function init() {
        byId('mcpDomainAll').addEventListener('change', syncDomainBoxes);
        byId('mcpTokenCreate').addEventListener('click', createToken);
        byId('mcpTokenCopy').addEventListener('click', function () {
            copyText(byId('mcpTokenValue').textContent, byId('mcpTokenCopy'));
        });
        byId('mcpTokenHide').addEventListener('click', hideToken);
        byId('mcpAuditRefresh').addEventListener('click', loadAudit);
        byId('mcpAuditStatus').addEventListener('change', loadAudit);
        byId('mcpAuditTool').addEventListener('change', loadAudit);
        byId('mcpSettingsSave').addEventListener('click', saveSettings);
        syncDomainBoxes();
        loadTokens();
        loadGrants();
        loadAudit();
        loadSettings();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

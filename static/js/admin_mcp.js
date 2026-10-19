/**
 * Страница «Доступ агентов» (/admin/mcp): бот @MCPkulturabot, токены MCP, OAuth-приложения, журнал
 * вызовов, настройки.
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
        settings: '/api/admin/mcp/settings',
        bot: '/api/admin/mcp/bot',
        botLink: '/api/admin/mcp/bot/link',
        botLinks: '/api/admin/mcp/bot/links/',
        botInstall: '/api/admin/mcp/bot/install'
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

    // ------------------------------------------------------------ бот @MCPkulturabot

    var BOT_LINK_POLL_MS = 5000;      // после «Подключить мой Telegram» — ждём привязку
    var BOT_LINK_POLL_TIMES = 60;     // 5 минут
    var botLinkPoll = null;
    var botLast = null;               // последний ответ /api/admin/mcp/bot (для подтверждения переустановки)
    var botLinksSig = '';             // привязки как строка: изменилась — Telegram подключили
    var botLinksBaseline = null;      // привязки в момент «Подключить мой Telegram»

    function money(value) {
        return '$' + (Number(value) || 0).toFixed(2);
    }

    // Состояние — из отчёта сервера бота в Амстердаме (kultura_bot/site_api.py). Отчёт раз в
    // минуту; нет дольше трёх минут — stale. Новая команда установки стирает прежнее
    // состояние: до первого отчёта нового сервера — «ещё не отзывался».
    function botStatusText(data) {
        var st = data.status || {};
        var engine = data.engine || {};
        var bot = '@' + ((data.telegram && data.telegram.bot_username) || 'MCPkulturabot');
        if (!engine.issued) return { text: 'Бот ещё не установлен: нажмите «Команда установки» ниже и выполните ' +
            'команду на сервере в Амстердаме.', bad: true };
        if (!engine.active) return { text: 'Ключ сервера бота отозван — бот молчит. Нажмите «Команда установки» и ' +
            'выполните новую команду на сервере в Амстердаме.', bad: true };
        if (!st.at) return { text: 'Сервер бота ещё не отзывался: выполните команду установки на сервере в ' +
            'Амстердаме. Уже выполнили — посмотрите журнал там: journalctl -u kultura-bot -n 50.', bad: true };
        if (st.stale) return { text: 'Сервер бота ' + bot + ' давно не отзывался (последний раз ' + fmtTime(st.at) +
            '): он перезапускается, выключен или потерял связь с сайтом. Если так дольше пяти минут — проверьте ' +
            'сервер в Амстердаме (systemctl status kultura-bot).', bad: true };
        switch (st.state) {
            case 'running':
                // Telegram слушается, но последний ответ Claude не получился (ключ, отказ серверу,
                // деньги, связь) — держим это на виду, пока следующий ответ не получится.
                if (st.claude_error) return { text: 'Бот ' + bot + ' слушает Telegram, но Claude не ответил: ' +
                    st.claude_error, bad: true };
                return { text: 'Бот ' + bot + ' работает: слушает Telegram и отвечает.', bad: false };
            case 'waiting': return { text: 'Бот ждёт настройки: ' + st.detail + '.', bad: true };
            case 'paused': return { text: 'Бот на паузе: на сообщения не отвечает.', bad: true };
            case 'conflict': return { text: 'Конфликт: ' + st.detail + '.', bad: true };
            case 'error': return { text: 'Ошибка: ' + st.detail, bad: true };
            case 'starting': return { text: 'Бот запускается…', bad: false };
            case 'stopped': return { text: 'Сервер бота остановлен (' + fmtTime(st.at) + ').', bad: true };
            default: return { text: 'Сервер бота сообщил непонятное состояние: ' + st.state + '.', bad: true };
        }
    }

    // resetForm — после загрузки страницы и сохранения: поля секретов пустые, «Пауза» — как
    // сохранено. Опрос привязки форму не трогает: владелец мог начать её заполнять.
    function renderBot(data, resetForm) {
        botLast = data;
        var status = botStatusText(data);
        var node = byId('mcpBotState');
        node.textContent = status.text;
        node.className = 'mcp-note ' + (status.bad ? 'mcp-state-bad' : 'mcp-state-good');

        var tg = data.telegram || {};
        setText('mcpBotTokenHint', tg.configured
            ? 'Сохранён: ' + tg.token_hint + ' (@' + tg.bot_username + ')' + (tg.source === 'env' ? ', из файла .env' : '') +
              '. Новый токен — вставьте сюда; пустое поле — токен не меняется.'
            : 'Нет. @BotFather → /mybots → бот → API Token. Сервис проверит токен в Telegram.');
        var key = data.anthropic || {};
        setText('mcpBotKeyHint', key.configured
            ? 'Сохранён: ' + key.key_hint + '. Новый ключ — вставьте сюда; пустое поле — ключ не меняется.'
            : 'Нет. console.anthropic.com → API Keys → Create Key. Ключ проверит сервер бота — ошибку покажет ' +
              'строка состояния вверху.');
        if (resetForm) {
            byId('mcpBotToken').value = '';
            byId('mcpBotKey').value = '';
            byId('mcpBotPaused').checked = !!data.paused;
        }
        var engine = data.engine || {};
        setText('mcpBotEngine', engine.issued
            ? 'Ключ сервера: ' + engine.prefix + '… (выпустил ' + engine.owner + ' ' + fmtTime(engine.created_at) +
              (engine.active ? '' : ', отозван — нужна новая команда установки') +
              (engine.last_used_at ? ', сервер последний раз обращался ' + fmtTime(engine.last_used_at) : ', сервер ещё не обращался') + ').'
            : 'Сервер бота ещё не установлен.');

        var usage = data.usage || {};
        var today = usage.today || {};
        var period = usage.period || {};
        setText('mcpBotUsage', 'Расход на Claude: сегодня ' + money(today.cost_usd) +
            (data.budget_usd ? ' из ' + money(data.budget_usd) : '') + ' (запросов к модели ' + (today.requests || 0) +
            '), за ' + (usage.days || 30) + ' дней ' + money(period.cost_usd) + '.');
        var agents = (data.agents || []).map(function (a) { return a.title; }).join(', ');
        setText('mcpBotModel', 'Сейчас: модель ' + data.model + ', усилие ' + data.effort +
            (data.budget_usd ? ', предел ' + money(data.budget_usd) + ' в сутки' : '') +
            (agents ? '. Агенты: ' + agents + '.' : '.'));

        var body = byId('mcpBotLinksBody');
        body.textContent = '';
        var links = data.links || [];
        links.forEach(function (link) {
            var row = el('tr');
            cell(row, link.login);
            cell(row, link.tg_name);
            cell(row, fmtTime(link.linked_at));
            var td = el('td');
            var btn = el('button', 'mcp-btn mcp-btn-danger mcp-btn-sm', 'Отключить');
            btn.type = 'button';
            btn.addEventListener('click', function () { unlinkBot(link); });
            td.appendChild(btn);
            row.appendChild(td);
            body.appendChild(row);
        });
        byId('mcpBotLinksEmpty').hidden = links.length > 0;
        botLinksSig = links.map(function (l) { return l.tg_user_id + '@' + l.linked_at; }).join(',');
        if (botLinkPoll && botLinksBaseline !== null && botLinksSig !== botLinksBaseline) {
            clearInterval(botLinkPoll);
            botLinkPoll = null;
            byId('mcpBotLinkUrl').hidden = true;
            setText('mcpBotLinkHint', 'Готово: Telegram подключён.');
        }
    }

    function loadBot(resetForm) {
        return call('GET', API.bot).then(function (data) { renderBot(data, resetForm); })
            .catch(function (e) { setText('mcpBotError', e.message); });
    }

    function saveBot() {
        setText('mcpBotError', '');
        setText('mcpBotOk', '');
        var body = { paused: !!byId('mcpBotPaused').checked };
        var token = byId('mcpBotToken').value.trim();
        var key = byId('mcpBotKey').value.trim();
        if (token) body.token = token;
        if (key) body.anthropic_key = key;
        var button = byId('mcpBotSave');
        button.disabled = true;
        call('PUT', API.bot, body)
            .then(function (data) {
                renderBot(data, true);
                setText('mcpBotOk', 'Сохранено');
                if (data.warnings && data.warnings.length) setText('mcpBotError', data.warnings.join(' '));
            })
            .catch(function (e) { setText('mcpBotError', e.message); })
            .then(function () { button.disabled = false; });
    }

    function linkBot() {
        setText('mcpBotError', '');
        call('POST', API.botLink, {})
            .then(function (data) {
                var link = byId('mcpBotLinkUrl');
                link.href = data.url;
                link.hidden = false;
                setText('mcpBotLinkHint', 'Ссылка одноразовая и действует ' + Math.round(data.expires_in_s / 60) +
                    ' минут: откройте её там, где у вас Telegram, и нажмите «Старт».');
                var times = 0;
                if (botLinkPoll) clearInterval(botLinkPoll);
                botLinksBaseline = botLinksSig;
                botLinkPoll = setInterval(function () {
                    times += 1;
                    if (times > BOT_LINK_POLL_TIMES) { clearInterval(botLinkPoll); botLinkPoll = null; return; }
                    loadBot(false);
                }, BOT_LINK_POLL_MS);
            })
            .catch(function (e) { setText('mcpBotError', e.message); });
    }

    function unlinkBot(link) {
        if (!window.confirm('Отключить Telegram «' + (link.tg_name || link.tg_user_id) + '» (' + link.login +
            ')? Бот перестанет ему отвечать.')) return;
        call('DELETE', API.botLinks + encodeURIComponent(link.tg_user_id))
            .then(function () { return loadBot(false); })
            .catch(function (e) { setText('mcpBotError', e.message); });
    }

    // Команда установки сервера бота: новый ключ, прежний отзывается — поэтому спрашиваем.
    // Команда целиком только в ответе и на экране, пока её не скрыли (как новый токен выше).
    function installBot() {
        setText('mcpBotInstallError', '');
        var engine = (botLast && botLast.engine) || {};
        if (engine.issued && engine.active && !window.confirm('Выпустить новую команду установки? Прежний ключ ' +
            'сервера бота перестанет работать — бот замолчит, пока команду не выполнят на сервере.')) return;
        call('POST', API.botInstall, {})
            .then(function (data) {
                byId('mcpBotInstallCmd').textContent = data.command;
                byId('mcpBotInstallResult').hidden = false;
                return loadBot(false);
            })
            .catch(function (e) { setText('mcpBotInstallError', e.message); });
    }

    function hideInstall() {
        byId('mcpBotInstallCmd').textContent = '';
        byId('mcpBotInstallResult').hidden = true;
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
        byId('mcpBotSave').addEventListener('click', saveBot);
        byId('mcpBotLink').addEventListener('click', linkBot);
        byId('mcpBotInstall').addEventListener('click', installBot);
        byId('mcpBotInstallCopy').addEventListener('click', function () {
            copyText(byId('mcpBotInstallCmd').textContent, byId('mcpBotInstallCopy'));
        });
        byId('mcpBotInstallHide').addEventListener('click', hideInstall);
        syncDomainBoxes();
        loadTokens();
        loadGrants();
        loadAudit();
        loadSettings();
        loadBot(true);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

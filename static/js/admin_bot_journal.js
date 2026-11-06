/* Журнал вопросов и ответов бота @MCPkulturabot (templates/admin_bot_journal.html).
 *
 * Список — GET /api/admin/bot/journal (фильтры формы, по 50 записей, «Показать ещё»), запись целиком —
 * тот же адрес с ?uid=, удаление — DELETE /api/admin/bot/journal/<uid>, выгрузка — .csv с теми же
 * фильтрами. Весь текст из журнала (вопросы, ответы, реакции людей) вставляется через textContent:
 * разметку из него страница не исполняет. */
(function () {
    'use strict';

    var API = '/api/admin/bot/journal';
    var PAGE = 50;
    var MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    var STATUS = {
        done: ['Ответ', 'mcp-tag-ok'],
        error: ['Ошибка', 'mcp-tag-error'],
        stopped: ['Остановлен', 'mcp-tag-denied'],
        budget: ['Предел', 'mcp-tag-denied']
    };
    var RATING = { bad: 'плохая', good: 'хорошая', other: 'другая' };
    var NOTES = {
        max_rounds: 'кончились шаги',
        question_budget: 'упёрся в предел на вопрос',
        refusal: 'модель отказалась',
        max_tokens: 'ответ упёрся в предел длины',
        max_tokens_tool: 'вызов оборвался на пределе длины',
        pause_turn: 'сервер модели прервал шаг',
        report_finish: 'отчёт собран без данных после предела'
    };

    var root = document.getElementById('journalRoot');
    if (!root) { return; }
    var form = document.getElementById('journalFilters');
    var rows = document.getElementById('journalRows');
    var stats = document.getElementById('journalStats');
    var errorBox = document.getElementById('journalError');
    var empty = document.getElementById('journalEmpty');
    var more = document.getElementById('journalMore');
    var csv = document.getElementById('jCsv');
    var loginSelect = document.getElementById('jLogin');
    var offset = 0;

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) { node.className = cls; }
        if (text !== undefined && text !== null) { node.textContent = String(text); }
        return node;
    }

    function plural(n, forms) {
        var a = Math.abs(n) % 100, b = a % 10;
        if (a > 10 && a < 20) { return forms[2]; }
        if (b === 1) { return forms[0]; }
        if (b > 1 && b < 5) { return forms[1]; }
        return forms[2];
    }

    function when(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || '');
        if (!m) { return iso || ''; }
        return Number(m[3]) + ' ' + MONTHS[Number(m[2]) - 1] + ' ' + m[1] + ', ' + m[4] + ':' + m[5];
    }

    function money(value) {
        return '$' + Number(value || 0).toFixed(2);
    }

    function seconds(value) {
        var s = Math.round(Number(value || 0));
        if (s < 60) { return s + ' с'; }
        return Math.floor(s / 60) + ' мин ' + (s % 60) + ' с';
    }

    function params(extra) {
        var data = new FormData(form);
        var out = new URLSearchParams();
        data.forEach(function (value, key) {
            if (String(value).trim()) { out.set(key, String(value).trim()); }
        });
        Object.keys(extra || {}).forEach(function (key) { out.set(key, extra[key]); });
        return out;
    }

    function showError(text) {
        errorBox.textContent = text || '';
        errorBox.hidden = !text;
    }

    function fetchJson(url, options) {
        return fetch(url, Object.assign({ credentials: 'same-origin', headers: { 'Accept': 'application/json' } },
                                        options || {}))
            .then(function (resp) {
                return resp.json().catch(function () { return {}; }).then(function (data) {
                    if (!resp.ok) { throw new Error(data.error || ('Сайт ответил ' + resp.status)); }
                    return data;
                });
            });
    }

    function renderStats(s, filters) {
        stats.textContent = '';
        var parts = [
            ['За ' + filters.days + ' ' + plural(filters.days, ['день', 'дня', 'дней']) + ': ', null],
            [s.count + ' ' + plural(s.count, ['вопрос', 'вопроса', 'вопросов']), true],
            [' · ответов ' + s.done, null],
            [' · ошибок ' + s.errors, s.errors > 0],
            [' · остановлено ' + s.stopped, null],
            [' · упёрлись в предел ' + s.budget, s.budget > 0],
            [' · плохих оценок ' + s.bad, s.bad > 0],
            [' · хороших ' + s.good, null],
            [' · расход ' + money(s.cost_usd), true],
            [' · в среднем ' + seconds(s.avg_seconds), null]
        ];
        parts.forEach(function (part) {
            stats.appendChild(part[1] ? el('b', '', part[0]) : document.createTextNode(part[0]));
        });
    }

    function renderPeople(people) {
        var current = loginSelect.value;
        while (loginSelect.options.length > 1) { loginSelect.remove(1); }
        (people || []).forEach(function (p) {
            var option = el('option', '', (p.name || p.login) + ' (' + p.n + ')');
            option.value = p.login;
            loginSelect.appendChild(option);
        });
        loginSelect.value = current;
        if (loginSelect.value !== current) { loginSelect.value = ''; }
    }

    function statusTag(status) {
        var info = STATUS[status] || [status, 'mcp-tag-denied'];
        return el('span', 'mcp-tag ' + info[1], info[0]);
    }

    function rowFor(item) {
        var tr = el('tr', 'bj-row');
        tr.tabIndex = 0;
        tr.dataset.uid = item.uid;
        tr.appendChild(el('td', 'bj-when', when(item.asked_at)));
        var who = el('td', '', item.name || item.login || '—');
        if (item.chat_type && item.chat_type !== 'private') { who.appendChild(el('span', 'bj-preview', 'в группе')); }
        tr.appendChild(who);
        var q = el('td', 'bj-question', (item.mode === 'report' ? 'Отчёт: ' : '') + (item.question || '(без текста)'));
        var preview = item.status === 'done' ? item.answer : (item.error || item.answer);
        if (preview) { q.appendChild(el('span', 'bj-preview', preview)); }
        tr.appendChild(q);
        var st = el('td', '');
        st.appendChild(statusTag(item.status));
        if (item.failed_calls) {
            st.appendChild(el('span', 'bj-preview', item.failed_calls + ' ' +
                plural(item.failed_calls, ['вызов с ошибкой', 'вызова с ошибкой', 'вызовов с ошибкой'])));
        }
        tr.appendChild(st);
        tr.appendChild(el('td', 'bj-num', money(item.cost_usd)));
        tr.appendChild(el('td', 'bj-num', Math.round(item.seconds || 0)));
        var rating = el('td', '');
        if (item.rating) {
            rating.appendChild(el('span', '', RATING[item.rating] || item.rating));
            if (item.reactions && item.reactions.length) {
                rating.appendChild(el('span', 'bj-preview bj-reaction', item.reactions.join(' ')));
            }
        } else {
            rating.textContent = '—';
        }
        tr.appendChild(rating);
        tr.addEventListener('click', function () { toggle(tr); });
        tr.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(tr); }
        });
        return tr;
    }

    function block(title, text) {
        var box = el('div', 'bj-block');
        box.appendChild(el('h3', '', title));
        box.appendChild(el('pre', 'bj-text', text || '—'));
        return box;
    }

    function callsTable(calls) {
        var wrap = el('div', 'mcp-table-wrap bj-calls');
        var table = el('table', 'mcp-table');
        var head = el('tr');
        ['#', 'Инструмент', 'Аргументы', 'Секунд', 'Итог'].forEach(function (h) { head.appendChild(el('th', '', h)); });
        var thead = el('thead');
        thead.appendChild(head);
        table.appendChild(thead);
        var body = el('tbody');
        calls.forEach(function (c, i) {
            var tr = el('tr');
            tr.appendChild(el('td', '', i + 1));
            tr.appendChild(el('td', 'mcp-mono', (c.agent ? 'агент · ' : '') + (c.name || '')));
            tr.appendChild(el('td', 'mcp-mono bj-args', c.args || ''));
            tr.appendChild(el('td', 'bj-num', c.seconds));
            var result = el('td', c.ok ? 'mcp-ok' : 'mcp-err', c.ok ? 'ok' : (c.error || 'ошибка'));
            tr.appendChild(result);
            body.appendChild(tr);
        });
        table.appendChild(body);
        wrap.appendChild(table);
        return wrap;
    }

    function details(record, tr) {
        var td = el('td');
        td.colSpan = 7;
        var grid = el('div', 'bj-detail-grid');
        var question = record.question || '(без текста)';
        var extra = [];
        if (record.source === 'button') { extra.push('нажата кнопка под ответом'); }
        if (record.reply_to && record.reply_to.message_id) { extra.push('ответ на сообщение бота ' + record.reply_to.message_id); }
        (record.files || []).forEach(function (f) { extra.push('приложено: ' + (f.kind === 'image' ? 'фото' : (f.mime || 'файл'))); });
        if (extra.length) { question += '\n\n[' + extra.join('; ') + ']'; }
        grid.appendChild(block(record.mode === 'report' ? 'Вопрос (отчёт)' : 'Вопрос', question));
        var answer = record.answer || '';
        (record.cards || []).forEach(function (card) {
            if (card.tool === 'common_chart_send') {
                answer += '\n\n[График «' + (card.title || '') + '»]\n' + (card.caption || '');
            } else {
                answer += '\n\n[Отчёт «' + (card.title || '') + '», разделов: ' + (card.sections || 0) + ']\n' + (card.summary || '');
            }
        });
        grid.appendChild(block('Ответ', answer.trim()));
        td.appendChild(grid);

        var meta = [];
        meta.push('Чат: ' + (record.chat_type === 'private' ? 'личный' : 'группа') + ' ' + (record.chat_id || ''));
        if (record.format) { meta.push('вид: ' + (record.format === 'rich' ? 'новый' : 'прежний')); }
        meta.push('запросов к модели: ' + (record.steps || 0) + ', вызовов инструментов: ' + (record.tool_calls || 0));
        meta.push('расход ' + money(record.cost_usd) + ', работа ' + seconds(record.seconds) +
                  (record.waited ? ', ждал очереди ' + seconds(record.waited) : ''));
        if (record.model) { meta.push('модель ' + record.model); }
        var notes = (record.notes || []).map(function (n) { return NOTES[n] || n; });
        if (notes.length) { meta.push('пометки: ' + notes.join(', ')); }
        if (record.error) { meta.push('причина: ' + record.error); }
        var feedback = record.feedback || {};
        Object.keys(feedback).forEach(function (who) {
            var item = feedback[who] || {};
            meta.push('реакция ' + who + ': ' + (item.reactions || []).join(' ') + (item.at ? ' (' + when(item.at) + ')' : ''));
        });
        td.appendChild(el('p', 'bj-meta', meta.join(' · ')));
        if (record.calls && record.calls.length) { td.appendChild(callsTable(record.calls)); }

        var del = el('div', 'bj-delete');
        var ask = el('button', 'mcp-btn mcp-btn-ghost mcp-btn-sm', 'Удалить запись');
        ask.type = 'button';
        del.appendChild(ask);
        ask.addEventListener('click', function () {
            del.textContent = '';
            del.appendChild(el('span', '', 'Удалить безвозвратно?'));
            var yes = el('button', 'mcp-btn mcp-btn-danger mcp-btn-sm', 'Удалить');
            yes.type = 'button';
            var no = el('button', 'mcp-btn mcp-btn-ghost mcp-btn-sm', 'Отмена');
            no.type = 'button';
            del.appendChild(yes);
            del.appendChild(no);
            no.addEventListener('click', function () { del.textContent = ''; del.appendChild(ask); });
            yes.addEventListener('click', function () {
                yes.disabled = true;
                fetchJson(API + '/' + encodeURIComponent(record.uid), { method: 'DELETE' })
                    .then(function () { load(true); })
                    .catch(function (err) { yes.disabled = false; showError(err.message); });
            });
        });
        td.appendChild(del);
        var detailRow = el('tr', 'bj-detail');
        detailRow.appendChild(td);
        tr.parentNode.insertBefore(detailRow, tr.nextSibling);
    }

    function toggle(tr) {
        var next = tr.nextSibling;
        if (next && next.classList && next.classList.contains('bj-detail')) {
            next.parentNode.removeChild(next);
            tr.classList.remove('bj-open');
            return;
        }
        tr.classList.add('bj-open');
        fetchJson(API + '?uid=' + encodeURIComponent(tr.dataset.uid))
            .then(function (data) { details(data.record || {}, tr); })
            .catch(function (err) { tr.classList.remove('bj-open'); showError(err.message); });
    }

    function load(reset) {
        if (reset) { offset = 0; }
        showError('');
        var query = params({ limit: String(PAGE), offset: String(offset) });
        var csvQuery = params();
        csv.href = API + '.csv' + (csvQuery.toString() ? '?' + csvQuery.toString() : '');
        return fetchJson(API + '?' + query.toString())
            .then(function (data) {
                if (reset) { rows.textContent = ''; }
                renderStats(data.stats || {}, data.filters || { days: 30 });
                renderPeople(data.people);
                (data.items || []).forEach(function (item) { rows.appendChild(rowFor(item)); });
                offset += (data.items || []).length;
                empty.hidden = offset > 0;
                more.hidden = (data.items || []).length < PAGE || offset >= (data.stats || {}).count;
            })
            .catch(function (err) {
                stats.textContent = '';
                showError(err.message);
            });
    }

    form.addEventListener('submit', function (e) { e.preventDefault(); load(true); });
    ['jDays', 'jLogin', 'jStatus', 'jRating'].forEach(function (id) {
        document.getElementById(id).addEventListener('change', function () { load(true); });
    });
    more.addEventListener('click', function () { load(false); });
    load(true);
}());

/* Контроллер личной страницы /me.

   Две независимые загрузки, и это принципиально:
     - ЖИВОЕ (смены, часы, календарь) — через window.Schedule, теми же запросами
       и тем же рендером (renderMyShifts), что мобильный экран /schedule. Второй
       реализации нет: два независимых расчёта «смены 8/15» разъехались бы.
     - СНИМОК (показатели, KPI, деньги) — GET /api/me.
   Сбой одной загрузки не гасит другую: источники разные (shifts.db против
   ночного расчёта), и страница обязана оставаться полезной, когда iiko лежит.

   Оформление — по макету владельца; раскрытия формул сделаны нативными
   <details>, поэтому JS для них не нужен вовсе.

   Ширину экрана этот файл НЕ читает нигде — вся адаптивность в me.css.

   Подключать ПОСЛЕ common.js, screens.js, fact_modal.js, snapshot.js. */
(function () {
    'use strict';
    var S = window.Schedule;
    if (!S) return;

    var EMP_IIKO = (document.body.dataset.empIiko || '').trim();
    var me = null;            // последний ответ /api/me
    var summary = null;       // сводка месяца из renderMyShifts
    var loadingLive = false;

    // ==================== Живая часть ====================

    function renderLive() {
        var host = document.getElementById('myShifts');
        summary = S.renderMyShifts(host, {
            employeeIikoId: EMP_IIKO || null,
            icsHref: EMP_IIKO ? '/schedule/cal.ics' : null,
            onDayOffToggle: onDayOffToggle,
            // Карточка дня и действия — ПЕРЕД календарём: главная кнопка должна
            // быть в первом экране без скролла.
            dayFirst: true,
            // Оформление макета: строка месяца вместо аватара (аватар в шапке),
            // сводка месяца отдельными плитками, плоские плашки смен.
            monthTitle: true,
            chips: false,
            flatBars: true,
            norms: me && me.norms ? me.norms : null
        });
        var Snap = (window.Me || {}).snapshot;
        if (Snap && summary) {
            Snap.renderMonthTiles(document.getElementById('meMonthTiles'), summary,
                                  me && me.norms);
        }
        fillHeader();
        setLiveStamp();
    }

    // Подпись в шапке: роль и точки, где человек работает в этом месяце.
    function fillHeader() {
        var sub = document.getElementById('meWhoSub');
        if (!sub) return;
        var venues = (summary && summary.venues) || [];
        sub.textContent = venues.length
            ? 'бармен · ' + venues.map(function (v) { return v.name; }).join(' · ')
            : 'бармен';
        var ava = document.getElementById('meAva');
        if (ava && !ava.textContent.trim() && summary && summary.label) {
            ava.textContent = summary.label;
        }
        // Кружок аватара красим цветом первой точки — тот же язык, что у смен.
        if (ava && venues.length) {
            ava.style.setProperty('--me-ava-bg', venues[0].color);
        }
    }

    function setLiveStamp() {
        var el = document.getElementById('meLiveTs');
        if (!el) return;
        var d = new Date();
        var p = function (n) { return n < 10 ? '0' + n : '' + n; };
        el.textContent = 'обновлено ' + p(d.getHours()) + ':' + p(d.getMinutes());
    }

    function reloadLive() {
        if (loadingLive) return Promise.resolve();
        loadingLive = true;
        return S.loadMonthData()
            .then(function () { renderLive(); })
            .catch(function (err) {
                showBlockError('meNotice', 'Не удалось загрузить график смен.', reloadLive, err);
            })
            .then(function () { loadingLive = false; });
    }

    // Заявка на выходной: смену не трогаем, конфликт разруливает владелец.
    function onDayOffToggle(empName, ds, isOff) {
        var req = isOff ? findDayOffRequest(empName, ds) : null;
        var call = isOff
            ? (req ? S.api('/api/schedule/dayoff/' + req.id, { method: 'DELETE' }) : null)
            : S.api('/api/schedule/dayoff', {
                method: 'POST',
                body: { employee_name: empName, date_from: ds, date_to: ds }
            });
        if (!call) return;
        call.then(function () { S.showToast(isOff ? 'Выходной отменён' : 'Выходной запрошен'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { return reloadLive(); });
    }

    function findDayOffRequest(empName, ds) {
        var list = S.state.dayOffs || [];
        for (var i = 0; i < list.length; i++) {
            var r = list[i];
            if (r.employee_name === empName && r.date_from <= ds && ds <= r.date_to) return r;
        }
        return null;
    }

    // ==================== Снимок ====================

    function loadSnapshot() {
        return S.api('/api/me')
            .then(function (data) {
                me = data;
                renderSnapshot();
                renderLive();      // нормы приходят вместе со снимком
            })
            .catch(function (err) {
                showBlockError('meSnapNotice', 'Не удалось загрузить личные показатели.',
                               loadSnapshot, err);
            });
    }

    function renderSnapshot() {
        var col = document.getElementById('meSnapCol');
        var notice = document.getElementById('meSnapNotice');
        var ts = document.getElementById('meSnapTs');
        var btn = document.getElementById('meRefresh');
        notice.innerHTML = '';
        ['meMoney', 'meKpi', 'meMetrics'].forEach(function (id) {
            document.getElementById(id).innerHTML = '';
        });
        renderPersonalNotice();
        renderFoot();

        var ident = me.identity || {};
        var snap = me.snapshot || {};
        var Snap = (window.Me || {}).snapshot;

        // Аккаунт не привязан либо привязка спорная: снимочную колонку прячем
        // целиком. Нулевые деньги у непривязанного читались бы как «мне ничего
        // не начислили».
        if (ident.status === 'not_linked' || ident.status === 'unknown_employee'
                || ident.status === 'ambiguous_link') {
            col.hidden = true;
            return;
        }
        col.hidden = false;

        ts.textContent = snap.refreshed_at
            ? 'данные на ' + (Snap ? Snap.fmtStamp(snap.refreshed_at) : '')
            : 'за ' + (me.month_label || me.month) + ' ещё не собран';
        renderRefreshBtn(btn, me.refresh || {});

        if (snap.status !== 'ok' || !me.money) {
            notice.innerHTML = '<div class="me-empty">'
                + esc(ident.message || 'Показатели за этот месяц пока не посчитаны.')
                + '</div>';
            return;
        }
        if (!Snap) return;
        Snap.renderMoney(document.getElementById('meMoney'), me);
        Snap.renderKpi(document.getElementById('meKpi'), me);
        Snap.renderMetrics(document.getElementById('meMetrics'), me);
    }

    // ==================== Кнопка «Обновить» ====================
    // Пять состояний одной кнопки. Причина отказа проговаривается словами, а не
    // серым цветом: «нельзя» без объяснения читается как поломка.

    var pollTimer = null;

    function renderRefreshBtn(btn, info) {
        if (!btn) return;
        btn.hidden = false;
        btn.className = 'me-refresh';
        btn.disabled = false;
        if (!info.can_refresh) { btn.hidden = true; return; }
        if (info.running) {
            setBusy(btn, 'считается…');
            startPolling();
        } else if (info.cooldown_left_sec > 0) {
            btn.classList.add('is-cool');
            btn.disabled = true;
            btn.textContent = 'обновить можно через '
                + Math.ceil(info.cooldown_left_sec / 60) + ' мин';
            btn.title = 'Пересчёт общий для всех и запускается раз в '
                + (info.cooldown_min || 30) + ' минут';
        } else if (info.last_error) {
            btn.classList.add('is-error');
            btn.textContent = 'не обновилось, повторить';
            btn.title = String(info.last_error);
        } else {
            btn.textContent = 'обновить';
            btn.title = 'Пересчитать показатели, KPI и деньги. Занимает 1-2 минуты';
        }
    }

    function setBusy(btn, text) {
        btn.className = 'me-refresh is-busy';
        btn.disabled = true;
        btn.innerHTML = '<span class="me-spin"></span>' + esc(text);
    }

    function onRefreshClick() {
        var btn = document.getElementById('meRefresh');
        setBusy(btn, 'обновляю…');
        // Штампы не меняем, но приглушаем: числа под ними уже неактуальны, а
        // новых ещё нет. Время в штампе меняется только при успешном пересчёте.
        document.querySelectorAll('.me-stamp').forEach(function (el) {
            el.style.opacity = '.55';
        });
        S.api('/api/me/refresh', { method: 'POST' })
            .then(function () { startPolling(); })
            .catch(function (err) {
                if (/уже идёт|раз в/.test(err.message || '')) {
                    S.showToast(err.message);
                    startPolling();
                    return;
                }
                btn.className = 'me-refresh is-error';
                btn.disabled = false;
                btn.textContent = 'не обновилось, повторить';
                S.showToast('Не обновилось: ' + err.message, true);
            });
    }

    function startPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(function () {
            S.api('/api/me/refresh-status')
                .then(function (st) {
                    var p = st.progress || {};
                    var btn = document.getElementById('meRefresh');
                    if (p.running) {
                        setBusy(btn, p.current_month ? 'считаю ' + p.current_month + '…' : 'обновляю…');
                        return;
                    }
                    stopPolling();
                    loadSnapshot();
                })
                .catch(function () { stopPolling(); });
        }, 3000);
    }

    function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    // ==================== Сообщения и подвал ====================

    // Предупреждения резолвера: расщеплённые часы, спорная привязка и т.п.
    function renderPersonalNotice() {
        var host = document.getElementById('meNotice');
        var ident = (me && me.identity) || {};
        var html = '';
        if (ident.status && ident.status !== 'ok' && ident.message) {
            html += '<div class="me-empty">' + esc(ident.message) + '</div>';
        }
        (ident.issues || []).forEach(function (i) {
            html += i.severity === 'error'
                ? '<div class="me-error">' + esc(i.message) + '</div>'
                : '<div class="me-empty is-warn">' + esc(i.message) + '</div>';
        });
        host.innerHTML = html;
    }

    function renderFoot() {
        var el = document.getElementById('meFoot');
        var notes = (me && me.notes) || {};
        var parts = [notes.live_vs_snapshot, notes.accrued_to_date, notes.excel]
            .filter(Boolean).map(esc);
        el.innerHTML = parts.length ? '<p>' + parts.join('<br>') + '</p>' : '';
    }

    function esc(s) { return S.escapeHtml(s == null ? '' : String(s)); }

    // Ошибка показывается НА МЕСТЕ блока, а не тостом: тост живёт 2,5 секунды,
    // и бармен на телефоне его не поймает.
    function showBlockError(hostId, text, retry, err) {
        var host = document.getElementById(hostId);
        if (!host) return;
        console.error('[ME]', text, err);
        host.innerHTML = '<div class="me-error">' + esc(text)
            + ' <button type="button" class="me-refresh" data-retry>повторить</button></div>';
        var btn = host.querySelector('[data-retry]');
        if (btn) btn.addEventListener('click', function () { host.innerHTML = ''; retry(); });
    }

    // ==================== Старт ====================

    document.addEventListener('DOMContentLoaded', function () {
        S.factModal.init({ onSaved: reloadLive });

        // БЕЗ этой строки главная кнопка страницы мертва. Кнопки карточки дня
        // («Отметить конец смены», «Закрыть смену — часы и касса», «Факт …
        // править») и клик по дню календаря живут в screens.js и все стоят под
        // `if (S._onScreenShiftClick)` — обработчик ставится только здесь.
        // factModal.init() его НЕ ставит: он привязывает саму модалку (поля,
        // сабмит, закрытие), а не то, что её открывает. На /schedule такая
        // строка есть (view.js), на /me её забыли при постройке страницы.
        S.setScreenShiftClick(function (shift) { S.factModal.open(shift); });

        var refreshBtn = document.getElementById('meRefresh');
        if (refreshBtn) refreshBtn.addEventListener('click', onRefreshClick);

        // Гамбургер шапки открывает общий сайдбар: пробрасываем клик на скрытую
        // кнопку из shared/nav.html, чтобы не дублировать её обработчик.
        var burger = document.getElementById('meBurger');
        var navToggle = document.getElementById('sidebar-toggle');
        if (burger && navToggle) {
            burger.addEventListener('click', function () { navToggle.click(); });
        }

        S.showLoading(true);
        S.loadDictionaries()
            .then(function () { return S.loadMonthData(); })
            .then(function () { renderLive(); })
            .catch(function (err) {
                showBlockError('meNotice', 'Не удалось загрузить график смен.', reloadLive, err);
            })
            .then(function () { S.showLoading(false); });

        // Независимо от живой части: сбой одной не гасит другую.
        loadSnapshot();

        // Вернулся в таб — тихо перечитываем живое (часы вводит бармен в конце
        // смены, а смену мог закрыть кто-то другой).
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) reloadLive();
        });
    });
})();

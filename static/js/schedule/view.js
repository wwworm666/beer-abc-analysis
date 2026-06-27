/* Страница /schedule — просмотр графика. Клик по смене — ввод факта часов.
   Показывает «План / Факт по дням» (деньги) — владелец решил видеть выручку и
   здесь; доступ к странице тот же, что к редактору (равные права). */

(function () {
    'use strict';

    var S = window.Schedule;
    var currentShift = null;

    document.addEventListener('DOMContentLoaded', function () {
        document.getElementById('prevMonth').addEventListener('click', function () {
            S.shiftMonth(-1); reload();
        });
        document.getElementById('nextMonth').addEventListener('click', function () {
            S.shiftMonth(1); reload();
        });

        document.getElementById('planFactToggle').addEventListener('click', function () {
            var body = document.getElementById('planFactCollapse');
            body.style.display = body.style.display === 'none' ? '' : 'none';
        });

        document.getElementById('factForm').addEventListener('submit', onFactSubmit);
        document.getElementById('factClear').addEventListener('click', onFactClear);
        document.getElementById('factCancel').addEventListener('click', closeFactModal);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeFactModal();
        });

        S.showLoading(true);
        S.loadDictionaries()
            .then(reload)
            .catch(function (err) {
                console.error(err);
                S.showToast('Ошибка загрузки данных', true);
                S.showLoading(false);
            });
    });

    function reload() {
        S.showLoading(true);
        S.updateMonthDisplay(document.getElementById('currentMonth'));
        return S.loadMonthData()
            .then(loadPlans)        // план/факт нужны борду «Сегодня» до рендера
            .then(renderScreens)
            .then(loadFeed)
            .then(loadWishes)
            .catch(function (err) {
                console.error(err);
                S.showToast('Ошибка загрузки месяца', true);
            })
            .then(function () { S.showLoading(false); });
    }

    // План/факт месяца (план из весов дней + факт = живой iiko OLAP) — в state,
    // используется бордом «Сегодня вживую» и таблицей «План / Факт по дням».
    function loadPlans() {
        return S.api('/api/schedule/plans/' + S.state.year + '/' + S.state.month)
            .then(function (p) { S.state.plans = p; })
            .catch(function (err) { console.error(err); S.state.plans = null; });
    }

    // Три экрана «kultura.os» + денежная таблица — всё из уже загруженного state,
    // без новых запросов. Клик по смене — ввод факта часов (openFactModal).
    function renderScreens() {
        S.setScreenShiftClick(openFactModal);
        var emp = (document.body.dataset.empIiko || '').trim();
        S.renderMyShifts(document.getElementById('myShifts'),
            { employeeIikoId: emp || null, icsHref: emp ? '/schedule/cal.ics' : null });
        S.renderTodayBoard(document.getElementById('todayBoard'));
        S.renderLanes(document.getElementById('lanes'));
        S.renderLegend(document.getElementById('legend'));
        S.renderPlanFact(document.getElementById('planFactBody'));
    }

    // ==================== Факт часов ====================
    // Вводится барменом руками в конце смены: смена может длиться дольше
    // кассовой, поэтому по API факт часов не вытащить. Это единственный
    // источник факта часов (зарплата, нагрузка).

    function openFactModal(shift) {
        currentShift = shift;
        document.getElementById('factModalTitle').textContent =
            shift.employee_name + ' — ' + S.formatDateHuman(shift.date)
            + ' — ' + shift.location_name;
        var input = document.getElementById('factInput');
        input.value = shift.fact_minutes != null
            ? S.minutesToHhMm(shift.fact_minutes) : '';
        document.getElementById('factModal').classList.add('active');
        input.focus();
    }

    function closeFactModal() {
        document.getElementById('factModal').classList.remove('active');
        currentShift = null;
    }

    function onFactSubmit(e) {
        e.preventDefault();
        if (!currentShift) return;
        var raw = document.getElementById('factInput').value;
        var minutes = S.parseHoursInput(raw);
        if (minutes === null || minutes < 0 || minutes > 1440) {
            S.showToast('Введи часы как 10:30 или 10.5', true);
            return;
        }
        S.api('/api/schedule/shift/' + currentShift.id + '/fact', {
            method: 'PUT',
            body: { fact_minutes: minutes }
        }).then(function () {
            closeFactModal();
            S.showToast('Часы сохранены');
            reload();
        }).catch(function (err) {
            S.showToast('Не сохранилось: ' + err.message, true);
        });
    }

    function onFactClear() {
        if (!currentShift) return;
        S.api('/api/schedule/shift/' + currentShift.id + '/fact', {
            method: 'PUT',
            body: { fact_minutes: null }
        }).then(function () {
            closeFactModal();
            S.showToast('Часы очищены');
            reload();
        }).catch(function (err) {
            S.showToast('Ошибка: ' + err.message, true);
        });
    }

    // ==================== Пожелания ====================
    // read-only: что бармены просят учесть. Прежние рейл-виджеты «Нагрузка» и
    // «Выполнение плана» заменены экранами «Полосы по людям» и «Сегодня вживую»
    // (считаются из state, см. screens.js); денежная «План / Факт по дням»
    // рендерится в renderScreens из уже загруженного state.plans.

    function loadWishes() {
        return S.api('/api/schedule/wishes')
            .then(function (ws) {
                S.renderWishesReadonly(document.getElementById('wishesView'), ws);
            })
            .catch(function (err) {
                console.error(err);
                var w = document.getElementById('wishesView');
                if (w) w.innerHTML = '<div class="cov-empty">Не удалось загрузить</div>';
            });
    }

    // ==================== Лента последних изменений ====================
    // Кто что менял в графике за выбранный месяц (смены, факт часов, выходные).
    // Компактно, новые сверху, цветная точка по типу действия.

    var FEED_DOT = {
        shift_create: '#2e9e5b', shift_update: '#d97706', shift_delete: '#dc2626',
        fact_set: '#2563eb', fact_clear: '#9aa0a6',
        dayoff_create: '#7c3aed', dayoff_delete: '#7c3aed'
    };

    function loadFeed() {
        return S.api('/api/schedule/audit/' + S.state.year + '/' + S.state.month + '?limit=8')
            .then(renderFeed)
            .catch(function () {
                var el = document.getElementById('feedList');
                if (el) el.innerHTML = '<div class="feed-empty">Не удалось загрузить</div>';
            });
    }

    function renderFeed(rows) {
        var list = document.getElementById('feedList');
        if (!list) return;
        if (!rows || !rows.length) {
            list.innerHTML = '<div class="feed-empty">Изменений за этот месяц пока нет</div>';
            return;
        }
        list.innerHTML = rows.map(function (r) {
            var color = FEED_DOT[r.action] || 'var(--accent, #d97706)';
            return '<div class="feed-row">'
                + '<span class="feed-dot" style="background:' + color + '"></span>'
                + '<span class="feed-main"><span class="feed-who">'
                + S.escapeHtml(r.actor_name || '—') + '</span>'
                + '<span class="feed-sep">·</span>'
                + '<span class="feed-what">' + S.escapeHtml(r.summary) + '</span></span>'
                + '<span class="feed-when">' + S.escapeHtml(S.formatAuditTs(r.ts)) + '</span>'
                + '</div>';
        }).join('');
    }
})();

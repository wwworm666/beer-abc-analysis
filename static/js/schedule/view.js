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
            .then(render)
            .then(loadFeed)
            .then(loadWidgets)
            .then(loadPlanFact)
            .then(loadWishes)
            .catch(function (err) {
                console.error(err);
                S.showToast('Ошибка загрузки месяца', true);
            })
            .then(function () { S.showLoading(false); });
    }

    function render() {
        S.renderGrid({
            gridEl: document.getElementById('scheduleGrid'),
            markHoles: true,
            showPlans: false,
            onChipClick: openFactModal
        });
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

    // ==================== Виджеты: Нагрузка + Пожелания ====================
    // Те же, что в редакторе, но read-only и money-free. Данные — общий /widgets
    // (без iiko, без рублей) и /wishes. Рендер — Schedule.render*. Денежного
    // «План/Факт по дням» тут нет: на странице барменов финансов не показываем.

    function loadWidgets() {
        return S.api('/api/schedule/widgets/' + S.state.year + '/' + S.state.month)
            .then(function (w) {
                S.renderLoad(document.getElementById('loadTableBody'),
                             w.employees_load || [], w.shift_norm || 15);
            })
            .catch(function (err) {
                console.error(err);
                var c = document.getElementById('loadTableBody');
                if (c) c.innerHTML = '<tr><td colspan="5" class="missing-fact">Не удалось загрузить</td></tr>';
            });
    }

    // План / Факт по дням — деньги. Тот же виджет, что в редакторе (S.renderPlanFact).
    // Тянем /plans (план из весов дней + факт = живой iiko OLAP) в S.state.plans.
    function loadPlanFact() {
        return S.api('/api/schedule/plans/' + S.state.year + '/' + S.state.month)
            .then(function (p) {
                S.state.plans = p;
                S.renderPlanFact(document.getElementById('planFactBody'));
            })
            .catch(function (err) {
                console.error(err);
                var h = document.getElementById('planFactBody');
                if (h) h.innerHTML = '<div class="pf-empty">Не удалось загрузить</div>';
            });
    }

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

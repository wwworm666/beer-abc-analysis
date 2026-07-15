/* Раздел «Гости»: состояние периода, загрузка API, форматирование, вкладки.
   Простые скрипты без ES-модулей (паттерн schedule). Документация: docs/guests.md */

window.Guests = (function () {
    'use strict';

    var state = {
        periodType: 'month',
        anchor: new Date(),          // любая дата внутри периода
        activeTab: 'summary',
        meta: null                   // meta последнего успешного ответа
    };
    var views = {};                  // tab -> render(pane)
    var rendered = {};               // tab -> ключ периода, на котором отрисован

    // ---------------- форматирование ----------------
    function fmtNum(n) {
        if (n === null || n === undefined) return '—';
        return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    }
    function fmtMoney(n) {
        if (n === null || n === undefined) return '—';
        return fmtNum(n) + ' ₽';
    }
    function fmtPct(n) {
        if (n === null || n === undefined) return '—';
        return (Math.round(n * 10) / 10).toString().replace('.', ',') + '%';
    }
    function fmtDate(iso) {
        if (!iso) return '—';
        var p = iso.split('-');
        return p[2] + '.' + p[1] + '.' + p[0];
    }
    function fmtMonth(ym) {
        var names = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
                     'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
        return names[parseInt(ym.slice(5, 7), 10) - 1] + ' ' + ym.slice(2, 4);
    }
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ---------------- периоды ----------------
    function anchorISO() {
        var d = state.anchor;
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
               '-' + String(d.getDate()).padStart(2, '0');
    }
    function periodKey() {
        return state.periodType + ':' + anchorISO();
    }
    function shiftPeriod(dir) {
        var d = new Date(state.anchor);
        if (state.periodType === 'week') d.setDate(d.getDate() + 7 * dir);
        else if (state.periodType === 'month') { d.setDate(1); d.setMonth(d.getMonth() + dir); }
        else if (state.periodType === 'quarter') { d.setDate(1); d.setMonth(d.getMonth() + 3 * dir); }
        else { d.setDate(1); d.setFullYear(d.getFullYear() + dir); }
        state.anchor = d;
        onPeriodChanged();
    }
    function setPeriodType(t) {
        if (state.periodType === t) return;
        state.periodType = t;
        document.querySelectorAll('.ptype-btn').forEach(function (b) {
            b.classList.toggle('active', b.dataset.ptype === t);
        });
        onPeriodChanged();
    }
    function onPeriodChanged() {
        rendered = {};   // все вкладки устарели
        renderActive();
    }

    // ---------------- API ----------------
    function api(path, params) {
        var q = new URLSearchParams(params || {});
        if (!q.has('period_type')) q.set('period_type', state.periodType);
        if (!q.has('anchor')) q.set('anchor', anchorISO());
        return fetch(path + '?' + q.toString())
            .then(function (r) {
                return r.json().then(function (j) {
                    if (!r.ok || j.error) throw new Error(j.error || ('HTTP ' + r.status));
                    return j;
                });
            })
            .then(function (j) {
                if (j.meta) { state.meta = j.meta; updatePeriodHeader(j.meta); }
                return j;
            });
    }

    function updatePeriodHeader(meta) {
        var lbl = document.getElementById('periodLabel');
        if (lbl && meta.period_label) lbl.textContent = meta.period_label;
        var cov = document.getElementById('coverageBanner');
        if (cov && meta.coverage_from) {
            var upd = meta.last_synced_at ? meta.last_synced_at.replace('T', ' ').slice(0, 16) : '—';
            cov.textContent = 'Данные: ' + fmtDate(meta.coverage_from) + ' — ' +
                fmtDate(meta.coverage_to) + ' · обновлено ' + upd;
        }
    }

    // ---------------- тултипы формул и «Как считается» ----------------
    function helpIcon(key) {
        var f = window.GUEST_FORMULAS[key];
        if (!f) return '';
        return '<span class="metric-help" title="' + esc(f.text) + '">?</span>';
    }
    function howBlock(keys) {
        var items = keys.map(function (k) {
            var f = window.GUEST_FORMULAS[k];
            if (!f) return '';
            return '<div class="how-item"><b>' + esc(f.title) + '.</b> ' + esc(f.text) + '</div>';
        }).join('');
        return '<details class="how-block"><summary>Как считается</summary>' + items + '</details>';
    }
    function metricCard(key, label, value, sub) {
        return '<div class="gmetric">' +
            '<div class="gmetric-label">' + esc(label) + helpIcon(key) + '</div>' +
            '<div class="gmetric-value">' + value + '</div>' +
            (sub ? '<div class="gmetric-sub">' + sub + '</div>' : '') +
            '</div>';
    }

    // ---------------- вкладки ----------------
    function registerView(tab, renderFn) { views[tab] = renderFn; }

    function renderActive() {
        var tab = state.activeTab;
        var pane = document.getElementById('pane-' + tab);
        if (!pane || !views[tab]) return;
        if (rendered[tab] === periodKey()) return;   // уже актуально
        rendered[tab] = periodKey();
        pane.innerHTML = '<div class="pane-loading">Загрузка…</div>';
        Promise.resolve(views[tab](pane)).catch(function (e) {
            pane.innerHTML = '<div class="pane-error">Ошибка: ' + esc(e.message) + '</div>';
            rendered[tab] = null;
        });
    }

    function activateTab(tab) {
        state.activeTab = tab;
        document.querySelectorAll('.gtab-btn').forEach(function (b) {
            b.classList.toggle('active', b.dataset.tab === tab);
        });
        document.querySelectorAll('.gtab-pane').forEach(function (p) {
            p.classList.toggle('active', p.id === 'pane-' + tab);
        });
        if (history.replaceState) history.replaceState(null, '', '#' + tab);
        renderActive();
    }

    // ---------------- синхронизация (админ) ----------------
    function bindSync() {
        var btn = document.getElementById('syncBtn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            btn.disabled = true;
            btn.textContent = 'Обновляю…';
            fetch('/api/guests/sync', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function () { pollSync(btn); })
                .catch(function () { btn.disabled = false; btn.textContent = 'Обновить данные'; });
        });
    }
    function pollSync(btn) {
        fetch('/api/guests/sync-status').then(function (r) { return r.json(); })
            .then(function (j) {
                if (j.progress && j.progress.running) {
                    var p = j.progress;
                    btn.textContent = 'Синк ' + p.done + '/' + p.total +
                        (p.current_month ? ' (' + p.current_month + ')' : '');
                    setTimeout(function () { pollSync(btn); }, 2000);
                } else {
                    btn.disabled = false;
                    btn.textContent = 'Обновить данные';
                    rendered = {};
                    renderActive();
                }
            });
    }

    // ---------------- инициализация ----------------
    function init() {
        document.querySelectorAll('.ptype-btn').forEach(function (b) {
            b.addEventListener('click', function () { setPeriodType(b.dataset.ptype); });
        });
        document.getElementById('periodPrev').addEventListener('click', function () { shiftPeriod(-1); });
        document.getElementById('periodNext').addEventListener('click', function () { shiftPeriod(1); });
        document.querySelectorAll('.gtab-btn').forEach(function (b) {
            b.addEventListener('click', function () { activateTab(b.dataset.tab); });
        });
        bindSync();
        var hash = (location.hash || '').replace('#', '');
        if (hash && document.getElementById('pane-' + hash)) state.activeTab = hash;
        activateTab(state.activeTab);
    }
    document.addEventListener('DOMContentLoaded', init);

    return {
        state: state,
        api: api,
        registerView: registerView,
        fmtNum: fmtNum, fmtMoney: fmtMoney, fmtPct: fmtPct,
        fmtDate: fmtDate, fmtMonth: fmtMonth, esc: esc,
        helpIcon: helpIcon, howBlock: howBlock, metricCard: metricCard
    };
})();

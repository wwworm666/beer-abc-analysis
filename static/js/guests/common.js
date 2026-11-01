/* Раздел «Гости»: бар и период из общей полосы сайта, загрузка API, форматирование, вкладки.
   Простые скрипты без ES-модулей (паттерн schedule). Документация: docs/guests.md

   Бар и период выбираются один раз на весь сайт — полоса «Бар и период» в общем меню
   (templates/shared/scope_strip.html, window.KStrip; решение владельца 2026-11-01). Своих кнопок
   «Неделя / Месяц / Квартал / Год», стрелок и меню бара у страницы больше нет: она читает выбор
   полосы и слушает его изменения. Отчёты получают период датами (?date_from=&date_to=, обе
   включительно), бар — параметром store. */

window.Guests = (function () {
    'use strict';

    var state = {
        period: null,                // {start, end, granularity, key} — выбранный в полосе период
        bar: '',                     // ключ бара или '' — все бары
        activeTab: 'summary',
        meta: null                   // meta последнего успешного ответа
    };
    var views = {};                  // tab -> render(pane)
    var rendered = {};               // tab -> ключ, на котором отрисован

    // Имена точек из iiko (Store.Name) — нужны вкладке «Акции» для живого OLAP. Ключи витрины
    // сюда не кладём: витринные отчёты получают их вместе с данными.
    var config = window.GUESTS_CONFIG || { bars: [] };

    // 'YYYY-MM-DD' -> Date (местная полночь) или null.
    function isoToDate(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
        return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
    }
    function dateToISO(d) {
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
               '-' + String(d.getDate()).padStart(2, '0');
    }

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
    // Короткая подпись точки ряда по её первому дню — ось графика рядов «Оттока» и LTV: «16.03» у
    // дня и недели, «мар 26» у месяца, «2026» у года. step — шаг ряда (ответ отчёта, data.step).
    function periodShort(pStart, step) {
        if (!pStart) return '—';
        if (step === 'day' || step === 'week') return fmtDate(pStart).slice(0, 5);
        if (step === 'year') return pStart.slice(0, 4);
        return fmtMonth(pStart.slice(0, 7));
    }
    // Подпись отрезка дат: целый месяц — «мар 26», целый год — «2026», один день — «16.03.26»,
    // иначе «02.03–08.03.26» (год — у конца; у разных лет — у обеих дат).
    function rangeLabel(start, end) {
        if (!start || !end) return '—';
        if (start === end) return fmtDate(start).slice(0, 6) + start.slice(2, 4);
        var s = isoToDate(start), e = isoToDate(end);
        var monthEnd = new Date(e.getFullYear(), e.getMonth() + 1, 0).getDate();
        if (s.getDate() === 1 && start.slice(0, 7) === end.slice(0, 7) && e.getDate() === monthEnd) {
            return fmtMonth(start.slice(0, 7));
        }
        if (start.slice(5) === '01-01' && end.slice(5) === '12-31' && start.slice(0, 4) === end.slice(0, 4)) {
            return start.slice(0, 4);
        }
        var yearEnd = '.' + end.slice(2, 4);
        var first = fmtDate(start).slice(0, 5) + (start.slice(0, 4) !== end.slice(0, 4) ? '.' + start.slice(2, 4) : '');
        return first + '–' + fmtDate(end).slice(0, 5) + yearEnd;
    }

    // ---------------- бар и период: общая полоса ----------------
    function strip() {
        return window.KStrip || null;
    }
    // Без полосы (страница в тесте, скрипт полосы не загрузился) — текущий месяц по последнему
    // полному дню данных: правило страницы (core/scope.page_default, шаг месяц).
    function fallbackPeriod() {
        var d = isoToDate(config.last_full_day) || new Date();
        var start = dateToISO(new Date(d.getFullYear(), d.getMonth(), 1));
        var end = dateToISO(new Date(d.getFullYear(), d.getMonth() + 1, 0));
        return { start: start, end: end, granularity: 'month', key: start + '_' + end };
    }
    function readStrip() {
        var s = strip();
        var cur = s ? s.get() : null;
        state.period = (cur && cur.period) || state.period || fallbackPeriod();
        state.bar = cur ? (cur.bar || '') : state.bar;
    }
    readStrip();

    // Срез отчётов витрины: период + бар. Смена любого из них делает вкладки устаревшими.
    function scopeKey() {
        return (state.period ? state.period.key : '') + ':' + state.bar;
    }
    // Период и бар для ссылок (CSV): те же параметры, что у запросов вкладок.
    function periodQuery(withStore) {
        var p = state.period;
        var q = 'date_from=' + p.start + '&date_to=' + p.end;
        return q + (withStore !== false && state.bar ? '&store=' + encodeURIComponent(state.bar) : '');
    }
    // Кнопка «Открыть последний период с данными» у периода без данных: период того же шага, где
    // лежит дата (свой отрезок — месяц), выбирается в полосе — как выбор владельца, для всего сайта.
    function showPeriodOf(iso) {
        var s = strip(), K = window.KPeriod;
        var d = isoToDate(iso);
        if (!s || !K || !d) return;
        var steps = ['day', 'week', 'month', 'year'];
        var g = state.period && steps.indexOf(state.period.granularity) >= 0 ? state.period.granularity : 'month';
        s.setPeriod(K.periodFor(g, d));
    }
    function onPeriodChanged() {
        rendered = {};
        renderActive();
    }

    // Бар — из полосы; имя и короткое имя — из таблицы баров сайта (core/venues_config.SITE_BARS).
    function barList() {
        var s = strip();
        if (s && s.config && s.config.bars) return s.config.bars;
        return window.GH ? window.GH.BARS : [];
    }
    function barName(key) {
        var row = barList().filter(function (b) { return b.key === key; })[0];
        return row ? row.name : 'Все бары';
    }
    // Бары сети по порядку показа ({key, name, short, iiko_name}) — для сравнения баров рядом.
    function bars() {
        return barList();
    }
    // Сменить бар из кода вида — как выбор в полосе: сохраняется для всего сайта.
    function setBar(key) {
        var s = strip();
        if (s) s.setBar(key);
    }

    // ---------------- API ----------------
    // Период уходит датами, бар — параметром store во все отчёты. Отчёт, который на бары не
    // делится («Не купившие», карточка гостя), его не читает и отвечает meta.venue = null — виды
    // сверяются с meta, а не с выбором.
    function api(path, params) {
        var q = new URLSearchParams(params || {});
        if (state.period && !q.has('date_from') && !q.has('period_type')) {
            q.set('date_from', state.period.start);
            q.set('date_to', state.period.end);
        }
        if (state.bar && !q.has('store')) q.set('store', state.bar);
        return fetch(path + '?' + q.toString())
            .then(function (r) {
                return r.json().then(function (j) {
                    if (!r.ok || j.error) throw new Error(j.error || ('HTTP ' + r.status));
                    return j;
                });
            })
            .then(function (j) {
                if (j.meta) state.meta = j.meta;
                return j;
            });
    }

    // POST с JSON-телом. Нужен вкладке «Акции»: её данные приходят живым запросом в iiko через
    // POST /api/discount-analyze (период и имя точки iiko — в теле).
    function post(path, body) {
        return fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        }).then(function (r) {
            return r.json().then(function (j) {
                if (!r.ok || j.error) throw new Error(j.error || ('HTTP ' + r.status));
                return j;
            });
        });
    }

    // ---------------- тултипы формул и «Как считается» ----------------
    function helpIcon(key) {
        var f = window.GUEST_FORMULAS[key];
        if (!f) return '';
        return '<span class="metric-help" title="' + esc(f.text) + '">?</span>';
    }
    // meta — ответ отчёта: если он посчитан по бару (meta.venue), первым пунктом
    // идёт правило «бар как отдельное заведение». Берётся из ответа, а не из
    // выбора: отчёт, который на бары не делится, отвечает meta.venue = null.
    function howBlock(keys, meta) {
        var list = (meta && meta.venue) ? ['venue_scope'].concat(keys) : keys;
        var items = list.map(function (k) {
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
    // Короткая видимая подпись над отчётом, когда выбран бар, а отчёт считается
    // иначе, чем «только чеки бара» (по всей сети или по гостям бара во всех
    // барах). Без неё число читается неверно, поэтому её не прячем в «Как
    // считается». html — готовая разметка вида (имена баров экранирует вид).
    function scopeNote(html) {
        return '<div class="scope-note">' + html + '</div>';
    }

    // ---------------- вкладки ----------------
    // Все вкладки живут по периоду и бару полосы (у «Акций» своих полей дат и точки больше нет).
    function registerView(tab, renderFn) {
        views[tab] = renderFn;
    }

    function renderActive() {
        var tab = state.activeTab;
        var pane = document.getElementById('pane-' + tab);
        if (!pane || !views[tab]) return;
        if (rendered[tab] === scopeKey()) return;   // уже актуально
        rendered[tab] = scopeKey();
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
    // Кнопка — в полосе страницы (strip_actions): подпись в <span>, иконка остаётся; на телефоне
    // подпись скрыта — ход синка виден в подсказке кнопки.
    function syncLabel(btn, text) {
        var label = btn.querySelector ? btn.querySelector('span') : null;
        (label || btn).textContent = text;
        btn.title = text;
    }
    function bindSync() {
        var btn = document.getElementById('syncBtn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            btn.disabled = true;
            syncLabel(btn, 'Обновляю…');
            fetch('/api/guests/sync', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function () { pollSync(btn); })
                .catch(function () { btn.disabled = false; syncLabel(btn, 'Обновить данные'); });
        });
    }
    function pollSync(btn) {
        fetch('/api/guests/sync-status').then(function (r) { return r.json(); })
            .then(function (j) {
                if (j.progress && j.progress.running) {
                    var p = j.progress;
                    syncLabel(btn, 'Синк ' + p.done + '/' + p.total +
                        (p.current_month ? ' (' + p.current_month + ')' : ''));
                    setTimeout(function () { pollSync(btn); }, 2000);
                } else {
                    btn.disabled = false;
                    syncLabel(btn, 'Обновить данные');
                    // Синк обновил витрину — вкладки перерисовываются (у «Акций» свой кэш ответа
                    // iiko по периоду и точке, витрина его не касается).
                    onPeriodChanged();
                }
            });
    }

    // ---------------- инициализация ----------------
    function init() {
        document.querySelectorAll('.gtab-btn').forEach(function (b) {
            b.addEventListener('click', function () { activateTab(b.dataset.tab); });
        });
        bindSync();
        // Выбор в полосе (здесь, на другой странице или в другой вкладке браузера) — вкладки
        // пересчитываются. Счётчики «требует внимания» над страницей обновляет сам раздел (GH).
        readStrip();
        var s = strip();
        if (s) {
            s.onChange(function (e) {
                if (e.period) state.period = e.period;
                state.bar = e.bar || '';
                onPeriodChanged();
            });
        }
        var hash = (location.hash || '').replace('#', '');
        if (hash && document.getElementById('pane-' + hash)) state.activeTab = hash;
        activateTab(state.activeTab);
    }
    document.addEventListener('DOMContentLoaded', init);

    return {
        state: state,
        config: config,
        api: api,
        post: post,
        activateTab: activateTab,
        registerView: registerView,
        setBar: setBar,
        barName: barName,
        bars: bars,
        showPeriodOf: showPeriodOf,
        periodQuery: periodQuery,
        fmtNum: fmtNum, fmtMoney: fmtMoney, fmtPct: fmtPct,
        fmtDate: fmtDate, fmtMonth: fmtMonth, periodShort: periodShort, rangeLabel: rangeLabel,
        esc: esc,
        helpIcon: helpIcon, howBlock: howBlock, metricCard: metricCard,
        scopeNote: scopeNote
    };
})();

/* Экраны графика «kultura.os» — новая визуальная ДНК:
     цвет = точка (бар), высота блока = смена (день/вечер), рамка = статус.
   Три рендера на window.Schedule, всё из уже загруженного state (без новых
   запросов): renderLanes (полосы по людям), renderTodayBoard (сегодня вживую),
   renderMyShifts (мобильный «мои смены»). Источник идеи — Claude Design
   «График смен — идеи». Назначение смен и ввод факта живут в edit.js/view.js. */
(function () {
    'use strict';
    var S = window.Schedule;
    if (!S) return;

    // ---------- ДНК: цвета точек, роль, статус ----------

    // Цвет точки по venue_key; запасной — по порядку колонки.
    var BAR_COLORS = {
        varshavskaya: '#6f93a6', bolshoy: '#c08f9b',
        kremenchugskaya: '#c3a55f', ligovskiy: '#7d9b6b'
    };
    var FALLBACK = ['#6f93a6', '#c08f9b', '#c3a55f', '#7d9b6b'];
    var ACCENT = '#c0673a', AMBER = '#c98a32', RED = '#c0492f';

    function locColor(loc, idx) {
        return (loc && BAR_COLORS[loc.venue_key]) || FALLBACK[(idx || 0) % FALLBACK.length];
    }
    function locIndex(id) {
        var L = S.state.locations;
        for (var i = 0; i < L.length; i++) if (L[i].id === id) return i;
        return -1;
    }
    function locById(id) {
        var L = S.state.locations;
        for (var i = 0; i < L.length; i++) if (L[i].id === id) return L[i];
        return null;
    }
    function colorById(id) {
        var i = locIndex(id);
        return i < 0 ? '#9a8f7f' : locColor(S.state.locations[i], i);
    }
    function rgba(hex, a) {
        var n = parseInt(hex.slice(1), 16);
        return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
    }
    function pad2(n) { return n < 10 ? '0' + n : '' + n; }
    function esc(s) { return S.escapeHtml(s == null ? '' : String(s)); }

    // Вечер: роль «второй …» или старт >= 16:00. Иначе день.
    function isEvening(shift) {
        if (shift.role_name && /втор/i.test(shift.role_name)) return true;
        if (shift.start_time && shift.start_time >= '16:00') return true;
        return false;
    }
    // Статус смены: conflict > today > (прошлое: done|nofact) > soon.
    function shiftStatus(shift, today) {
        var ds = shift.date;
        if (S.getDayOffEmployees(ds).indexOf(shift.employee_name) !== -1) return 'conflict';
        if (ds === today) return 'today';
        if (ds < today) return shift.fact_minutes != null ? 'done' : 'nofact';
        return 'soon';
    }
    function statusBorder(st) {
        if (st === 'today') return '2px solid ' + ACCENT;
        if (st === 'nofact') return '2px solid ' + AMBER;
        if (st === 'conflict') return '2px solid ' + RED;
        return '1px solid rgba(0,0,0,.06)';
    }

    function empKey(shiftOrEmp) {
        return shiftOrEmp.employee_id || shiftOrEmp.id || shiftOrEmp.employee_name;
    }
    // Смены сотрудника в загруженном месяце.
    function shiftsOf(emp) {
        var byId = emp.id;
        return S.state.shifts.filter(function (s) {
            return byId ? s.employee_id === byId : s.employee_name === emp.name;
        });
    }
    function daysInMonth() { return new Date(S.state.year, S.state.month, 0).getDate(); }
    function dows(dow) { return ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'][dow]; }
    function isWeekend(dow) { return dow === 5 || dow === 6; } // пт/сб

    // ============================================================
    // ЭКРАН 1 — Полосы по людям
    // ============================================================
    function renderLanes(host) {
        if (!host) return;
        var today = S.todayStr();
        var dim = daysInMonth();
        var days = [];
        for (var d = 1; d <= dim; d++) {
            var dow = new Date(S.state.year, S.state.month - 1, d).getDay();
            var ds = S.dateStr(S.state.year, S.state.month, d);
            days.push({ d: d, dow: dow, ds: ds, today: ds === today, wknd: isWeekend(dow) });
        }

        // шапка дней
        var head = '<div class="ln-row ln-head">'
            + '<div class="ln-name">СОТРУДНИК</div><div class="ln-cells">'
            + days.map(function (x) {
                var cls = 'ln-dh' + (x.today ? ' is-today' : (x.wknd ? ' is-wknd' : ''));
                return '<div class="' + cls + '"><span class="ln-dow">' + dows(x.dow)
                    + '</span><span class="ln-dt">' + pad2(x.d) + '</span></div>';
            }).join('')
            + '</div><div class="ln-gauge-h">НОРМА 15</div></div>';

        var rows = S.state.employees.map(function (emp) {
            var mine = shiftsOf(emp);
            var byDate = {};
            mine.forEach(function (s) { if (!byDate[s.date]) byDate[s.date] = s; });

            var maxRun = 0, run = 0;
            var cells = days.map(function (x) {
                var s = byDate[x.ds];
                if (s) { run++; if (run > maxRun) maxRun = run; } else { run = 0; }
                if (!s) return '<div class="ln-c"><span class="ln-empty"></span></div>';
                var st = shiftStatus(s, today);
                var col = colorById(s.location_id);
                var eve = isEvening(s);
                var op = st === 'soon' ? 0.5 : 0.92;
                var style = 'height:' + (eve ? '56%' : '100%')
                    + ';background:' + rgba(col, op) + ';border:' + statusBorder(st);
                var loc = locById(s.location_id);
                var title = emp.name + ' · ' + (loc ? loc.short_name || loc.name : '')
                    + ' · ' + (eve ? 'вечер' : 'день')
                    + (s.start_time ? ' · с ' + s.start_time : '')
                    + (s.fact_minutes != null ? ' · факт ' + S.minutesToHhMm(s.fact_minutes) : '');
                return '<div class="ln-c"><span class="ln-blk" data-shift-id="' + esc(s.id)
                    + '" title="' + esc(title) + '" style="' + style + '"></span></div>';
            }).join('');

            var month = mine.length;
            var over = month > 15, streak = maxRun >= 6;
            var gColor = over ? AMBER : (streak ? ACCENT : '#5e8c4a');
            var gPct = Math.min(100, Math.round(month / 15 * 100));
            var flag = streak
                ? '<span class="ln-flag" title="' + maxRun + ' смен подряд — переработка">⚑</span>' : '';

            return '<div class="ln-row">'
                + '<div class="ln-name"><span class="ln-ini">' + esc(S.employeeLabel(emp.name))
                + '</span><span class="ln-nm">' + esc(S.employeeShortName(emp.name)) + '</span>' + flag + '</div>'
                + '<div class="ln-cells">' + cells + '</div>'
                + '<div class="ln-gauge"><span class="ln-bar"><span style="width:' + gPct
                + '%;background:' + gColor + '"></span></span>'
                + '<span class="ln-num" style="color:' + gColor + '">' + month + '/15</span></div>'
                + '</div>';
        }).join('');

        host.innerHTML = '<div class="ln-tbl">' + head + rows + '</div>';

        // клик по блоку — ввод факта (как по чипу в старой сетке)
        if (S._onScreenShiftClick) {
            host.querySelectorAll('.ln-blk').forEach(function (el) {
                el.addEventListener('click', function () {
                    var sh = S.state.shifts.filter(function (s) { return String(s.id) === el.dataset.shiftId; })[0];
                    if (sh) S._onScreenShiftClick(sh);
                });
            });
        }
    }

    // ============================================================
    // ЭКРАН 2 — Сегодня вживую
    // ============================================================
    function dayData(ds) {
        return (S.state.plans && S.state.plans.days && S.state.plans.days[ds]) || null;
    }
    function planPct(ds, locId) {
        var dd = dayData(ds); if (!dd || !dd.locations) return null;
        var c = dd.locations[locId]; if (!c || c.plan == null || !c.plan || c.fact == null) return null;
        return Math.round(c.fact / c.plan * 100);
    }

    function renderTodayBoard(host) {
        if (!host) return;
        var today = S.todayStr();
        var p = today.split('-');
        var dt = new Date(+p[0], +p[1] - 1, +p[2]);
        var yest = S.dateStr(dt.getFullYear(), dt.getMonth() + 1, dt.getDate() - 1);

        var head = '<div class="tb-head"><span class="tb-live"></span>'
            + '<span class="tb-date">' + dows(dt.getDay()) + ' · ' + p[2] + '.' + p[1] + '</span>'
            + '<span class="tb-tag">смены идут</span>'
            + '<span class="tb-os">&gt; kultura.os</span></div>';

        var cards = S.state.locations.map(function (loc, i) {
            var col = locColor(loc, i);
            var todays = S.state.shifts.filter(function (s) {
                return s.date === today && s.location_id === loc.id;
            });
            var dayS = todays.filter(function (s) { return !isEvening(s); })[0];
            var eveS = todays.filter(function (s) { return isEvening(s); })[0];
            function line(s, dot) {
                if (!s) return '<div class="tb-person tb-empty"><span class="tb-pdot" style="background:'
                    + dot + '"></span><span class="tb-pn">—</span></div>';
                return '<div class="tb-person"><span class="tb-pdot" style="background:' + dot + '"></span>'
                    + '<span class="tb-pn">' + esc(S.employeeShortName(s.employee_name)) + '</span>'
                    + '<span class="tb-pt">' + esc(s.start_time || '') + '</span></div>';
            }
            var pct = planPct(today, loc.id);
            var yp = planPct(yest, loc.id);
            var w = pct == null ? 3 : Math.max(3, Math.min(100, pct));
            return '<div class="tb-card">'
                + '<div class="tb-bar"><span class="tb-sq" style="background:' + col + '"></span>'
                + '<span class="tb-bn">' + esc(loc.short_name || loc.name) + '</span></div>'
                + line(dayS, '#5e8c4a') + line(eveS, '#c98a32')
                + '<div class="tb-prog"><span style="width:' + w + '%"></span></div>'
                + '<div class="tb-foot"><span>факт <b>' + (pct == null ? '—' : pct + '%') + '</b> идёт</span>'
                + '<span class="tb-y">вчера ' + (yp == null ? '—' : yp + '%') + '</span></div>'
                + '</div>';
        }).join('');

        // очередь действий: дыры (будущее, точка пуста), конфликты, нет факта
        var dim = daysInMonth(), queue = [];
        var holes = 0, holeEx = '';
        for (var d = 1; d <= dim; d++) {
            var ds = S.dateStr(S.state.year, S.state.month, d);
            if (ds < today) continue;
            S.state.locations.forEach(function (loc) {
                var has = S.state.shifts.some(function (s) { return s.date === ds && s.location_id === loc.id; });
                if (!has) { holes++; if (!holeEx) holeEx = d + '.' + S.state.month + ' · ' + (loc.short_name || loc.name); }
            });
        }
        if (holes) queue.push({ g: '▢', cls: 'q-red', t: 'Дыра', x: holeEx + (holes > 1 ? ' +' + (holes - 1) : ''), b: 'Закрыть' });
        var confs = S.state.shifts.filter(function (s) {
            return S.getDayOffEmployees(s.date).indexOf(s.employee_name) !== -1;
        });
        if (confs.length) {
            var c0 = confs[0];
            queue.push({ g: '▲', cls: 'q-red', t: 'Конфликт', x: parseInt(c0.date.slice(8), 10) + '.' + S.state.month
                + ' · ' + S.employeeLabel(c0.employee_name) + (confs.length > 1 ? ' +' + (confs.length - 1) : ''), b: 'Решить' });
        }
        var nofact = S.state.shifts.filter(function (s) { return s.date < today && s.fact_minutes == null; });
        if (nofact.length) queue.push({ g: '?', cls: 'q-amber', t: 'Нет факта', x: nofact.length + ' смен', b: 'Напомнить' });

        var queueHtml = queue.length ? '<div class="tb-queue">'
            + '<div class="tb-qh"><span>Требует действий</span><span class="tb-qn">' + queue.length + '</span></div>'
            + queue.map(function (q) {
                return '<div class="tb-qrow"><span class="tb-qg ' + q.cls + '">' + q.g + '</span>'
                    + '<span class="tb-qt">' + esc(q.t) + ' <span class="tb-qx">· ' + esc(q.x) + '</span></span>'
                    + '<span class="tb-qb">' + esc(q.b) + '</span></div>';
            }).join('') + '</div>' : '';

        host.innerHTML = '<div class="tb-card-wrap">' + head
            + '<div class="tb-grid">' + cards + '</div>' + queueHtml + '</div>';
    }

    // ============================================================
    // ЭКРАН 3 — Мобильный «мои смены»
    // ============================================================
    function renderMyShifts(host, opts) {
        if (!host) return;
        opts = opts || {};
        var today = S.todayStr();
        // найти сотрудника: по iiko_id (привязка аккаунта) или по имени
        var emp = null;
        if (opts.employeeIikoId) {
            emp = S.state.employees.filter(function (e) { return e.id === opts.employeeIikoId; })[0];
        }
        if (!emp && opts.employeeName) {
            emp = S.state.employees.filter(function (e) { return e.name === opts.employeeName; })[0];
        }
        if (!emp) {
            host.innerHTML = '<div class="ms-note">Аккаунт не привязан к сотруднику — личный график недоступен.</div>';
            return;
        }
        var mine = shiftsOf(emp).slice().sort(function (a, b) { return a.date < b.date ? -1 : 1; });
        var locName = function (id) { var l = locById(id); return l ? (l.short_name || l.name) : ''; };

        function dlabel(ds) {
            var q = ds.split('-'); var dd = new Date(+q[0], +q[1] - 1, +q[2]);
            return dows(dd.getDay()) + ' · ' + q[2] + '.' + q[1];
        }

        var html = '';
        // заголовок
        html += '<div class="ms-top"><div class="ms-av">' + esc(S.employeeLabel(emp.name)) + '</div>'
            + '<div><div class="ms-t">Мои смены</div><div class="ms-sub">' + esc(emp.name) + '</div></div></div>';

        // сегодня / идёт
        var todayShift = mine.filter(function (s) { return s.date === today; })[0];
        if (todayShift) {
            var eve = isEvening(todayShift);
            html += '<div class="ms-card ms-today">'
                + '<div class="ms-live"><span class="tb-live"></span><span>СЕГОДНЯ · ИДЁТ</span></div>'
                + '<div class="ms-trow"><span class="ms-bar">' + esc(locName(todayShift.location_id)) + '</span>'
                + '<span class="ms-role">' + (eve ? 'вечер · второй бармен' : 'день · бармен') + '</span></div>'
                + (todayShift.start_time ? '<div class="ms-start">старт ' + esc(todayShift.start_time) + '</div>' : '')
                + '</div>';
        }

        // нужен факт часов (прошлые без факта)
        var pending = mine.filter(function (s) { return s.date < today && s.fact_minutes == null; });
        if (pending.length) {
            html += '<div class="ms-lbl">НУЖЕН ФАКТ ЧАСОВ</div>';
            html += pending.map(function (s) {
                return '<div class="ms-pend" data-shift-id="' + esc(s.id) + '">'
                    + '<div class="ms-pmain"><div class="ms-pd">' + esc(dlabel(s.date)) + '</div>'
                    + '<div class="ms-pb">' + esc(locName(s.location_id)) + ' · ' + (isEvening(s) ? 'вечер' : 'день') + '</div></div>'
                    + '<div class="ms-pbtn">ввести факт</div></div>';
            }).join('');
        }

        // моя полоса (этот месяц)
        var dim = daysInMonth(), byDate = {};
        mine.forEach(function (s) { if (!byDate[s.date]) byDate[s.date] = s; });
        var strip = '';
        for (var d = 1; d <= dim; d++) {
            var ds = S.dateStr(S.state.year, S.state.month, d);
            var s = byDate[ds];
            if (!s) { strip += '<div class="ms-sc"><span class="ms-sempty"></span></div>'; continue; }
            var st = shiftStatus(s, today), col = colorById(s.location_id), eve2 = isEvening(s);
            var op = st === 'soon' ? 0.5 : 0.92;
            strip += '<div class="ms-sc"><span class="ms-sblk" style="height:' + (eve2 ? '56%' : '100%')
                + ';background:' + rgba(col, op) + ';border:' + statusBorder(st) + '"></span></div>';
        }
        html += '<div class="ms-lbl">МОЯ ПОЛОСА · ' + dows(new Date(S.state.year, S.state.month - 1, 1).getDay())
            + ' ' + pad2(1) + '–' + pad2(dim) + '.' + pad2(S.state.month) + '</div>';
        html += '<div class="ms-strip">' + strip + '</div>';

        // ближайшие смены
        var upcoming = mine.filter(function (s) { return s.date > today; }).slice(0, 5);
        if (upcoming.length) {
            html += '<div class="ms-lbl">БЛИЖАЙШИЕ СМЕНЫ</div>';
            html += upcoming.map(function (s) {
                return '<div class="ms-up"><span class="ms-udot" style="background:' + colorById(s.location_id) + '"></span>'
                    + '<span class="ms-ud">' + esc(dlabel(s.date)) + '</span>'
                    + '<span class="ms-ub">' + esc(locName(s.location_id)) + ' · ' + (isEvening(s) ? 'вечер' : 'день') + '</span>'
                    + '<span class="ms-ut">' + esc(s.start_time || '') + '</span></div>';
            }).join('');
        }

        // действия + сводка
        var monthCount = mine.length;
        var noFact = mine.filter(function (s) { return s.date < today && s.fact_minutes == null; }).length;
        html += '<div class="ms-acts"><div class="ms-act ms-act-out">Запросить выходной</div>';
        if (opts.icsHref) html += '<a class="ms-act ms-act-ics" href="' + esc(opts.icsHref) + '">.ics</a>';
        html += '</div>';
        html += '<div class="ms-stat">' + monthCount + '/15 смен · '
            + (noFact ? noFact + ' без факта' : 'факт везде') + '</div>';

        host.innerHTML = html;

        // клик по «нужен факт» — ввод
        if (S._onScreenShiftClick) {
            host.querySelectorAll('.ms-pend').forEach(function (el) {
                el.addEventListener('click', function () {
                    var sh = S.state.shifts.filter(function (s) { return String(s.id) === el.dataset.shiftId; })[0];
                    if (sh) S._onScreenShiftClick(sh);
                });
            });
        }
    }

    // экспорт
    S.renderLanes = renderLanes;
    S.renderTodayBoard = renderTodayBoard;
    S.renderMyShifts = renderMyShifts;
    // страница задаёт обработчик клика по смене (ввод факта)
    S.setScreenShiftClick = function (fn) { S._onScreenShiftClick = fn; };
})();

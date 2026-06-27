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
    var NORM_SHIFTS = 15, NORM_HOURS = 113; // месячная норма: смен / часов

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
    // Статус смены — кольцо вокруг блока (box-shadow): видно поверх любого цвета
    // точки, в отличие от тонкой рамки. Сегодня — терракот, ждёт факт — янтарь,
    // конфликт — красный. Отработана/предстоит — без кольца (различаются яркостью).
    function statusRing(st) {
        if (st === 'today') return '0 0 0 2px ' + ACCENT;
        if (st === 'nofact') return '0 0 0 2px ' + AMBER;
        if (st === 'conflict') return '0 0 0 2px ' + RED;
        return '';
    }
    function blockStyle(col, op, eve, st) {
        var ring = statusRing(st);
        return 'height:' + (eve ? '56%' : '100%') + ';background:' + rgba(col, op)
            + ';border:1px solid rgba(0,0,0,.08)' + (ring ? ';box-shadow:' + ring : '');
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
            + '</div><div class="ln-gauge-h">ПЛАН / ФАКТ</div></div>';

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
                var style = blockStyle(col, op, eve, st);
                var loc = locById(s.location_id);
                var title = emp.name + ' · ' + (loc ? loc.short_name || loc.name : '')
                    + ' · ' + (eve ? 'вечер' : 'день')
                    + (s.start_time ? ' · с ' + s.start_time : '')
                    + (s.fact_minutes != null ? ' · факт ' + S.minutesToHhMm(s.fact_minutes) : '');
                return '<div class="ln-c"><span class="ln-slot"><span class="ln-blk" data-shift-id="' + esc(s.id)
                    + '" title="' + esc(title) + '" style="' + style + '"></span></span></div>';
            }).join('');

            var month = mine.length;
            var factMin = 0;
            mine.forEach(function (s) { if (s.fact_minutes != null) factMin += s.fact_minutes; });
            var factH = Math.round(factMin / 60);
            var over = month > NORM_SHIFTS, streak = maxRun >= 6;
            var gColor = over ? AMBER : (streak ? ACCENT : '#5e8c4a');
            var gPct = Math.min(100, Math.round(month / NORM_SHIFTS * 100));
            var flag = streak
                ? '<span class="ln-flag" title="' + maxRun + ' смен подряд — переработка">⚑</span>' : '';

            return '<div class="ln-row">'
                + '<div class="ln-name"><span class="ln-ini">' + esc(S.employeeLabel(emp.name))
                + '</span><span class="ln-nm">' + esc(S.employeeShortName(emp.name)) + '</span>' + flag + '</div>'
                + '<div class="ln-cells">' + cells + '</div>'
                + '<div class="ln-gauge"><span class="ln-bar"><span style="width:' + gPct
                + '%;background:' + gColor + '"></span></span>'
                + '<span class="ln-pf">'
                + '<span class="ln-pf-l">' + NORM_SHIFTS + '/<b style="color:' + gColor + '">' + month + '</b> см</span>'
                + '<span class="ln-pf-l">' + NORM_HOURS + '/<b>' + factH + '</b> ч</span>'
                + '</span></div>'
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

    // Выбранный день борда (по умолчанию сегодня). Стрелки ‹ › листают день в
    // пределах загруженного месяца — данные уже в state, без новых запросов.
    var boardDate = null;
    function clampBoardDate() {
        var today = S.todayStr();
        var prefix = S.state.year + '-' + pad2(S.state.month);
        var dim = daysInMonth();
        if (!boardDate || boardDate.indexOf(prefix) !== 0) {
            boardDate = today.indexOf(prefix) === 0 ? today : S.dateStr(S.state.year, S.state.month, 1);
        }
        var d = +boardDate.slice(8, 10);
        if (d < 1) boardDate = S.dateStr(S.state.year, S.state.month, 1);
        else if (d > dim) boardDate = S.dateStr(S.state.year, S.state.month, dim);
        return boardDate;
    }

    function renderTodayBoard(host) {
        if (!host) return;
        var today = S.todayStr();
        var ds = clampBoardDate();
        var p = ds.split('-');
        var dt = new Date(+p[0], +p[1] - 1, +p[2]);
        var prev = S.dateStr(dt.getFullYear(), dt.getMonth() + 1, dt.getDate() - 1);
        var dim = daysInMonth(), dnum = +p[2];
        var isToday = ds === today, isPast = ds < today;

        var tag = isToday ? '<span class="tb-tag">смены идут</span>'
            : '<span class="tb-tag tb-tag-mut">' + (isPast ? 'смены закрыты' : 'план') + '</span>';
        var head = '<div class="tb-head">'
            + '<button class="tb-nav' + (dnum <= 1 ? ' is-disabled' : '') + '" data-step="-1" title="День назад">‹</button>'
            + '<span class="tb-live' + (isToday ? '' : ' tb-live-off') + '"></span>'
            + '<span class="tb-date">' + dows(dt.getDay()) + ' · ' + p[2] + '.' + p[1] + '</span>'
            + '<button class="tb-nav' + (dnum >= dim ? ' is-disabled' : '') + '" data-step="1" title="День вперёд">›</button>'
            + tag + '<span class="tb-os">&gt; kultura.os</span></div>';

        var cards = S.state.locations.map(function (loc, i) {
            var col = locColor(loc, i);
            var dayList = S.state.shifts.filter(function (s) {
                return s.date === ds && s.location_id === loc.id;
            });
            var dayS = dayList.filter(function (s) { return !isEvening(s); })[0];
            var eveS = dayList.filter(function (s) { return isEvening(s); })[0];
            function line(s, dot) {
                if (!s) return '<div class="tb-person tb-empty"><span class="tb-pdot" style="background:'
                    + dot + '"></span><span class="tb-pn">—</span></div>';
                return '<div class="tb-person"><span class="tb-pdot" style="background:' + dot + '"></span>'
                    + '<span class="tb-pn">' + esc(S.employeeShortName(s.employee_name)) + '</span>'
                    + '<span class="tb-pt">' + esc(s.start_time || '') + '</span></div>';
            }
            var pct = planPct(ds, loc.id);
            var yp = planPct(prev, loc.id);
            var w = pct == null ? 3 : Math.max(3, Math.min(100, pct));
            var prevLbl = isToday ? 'вчера' : (prev.slice(8, 10) + '.' + prev.slice(5, 7));
            return '<div class="tb-card">'
                + '<div class="tb-bar"><span class="tb-sq" style="background:' + col + '"></span>'
                + '<span class="tb-bn">' + esc(loc.short_name || loc.name) + '</span></div>'
                + line(dayS, '#5e8c4a') + line(eveS, '#c98a32')
                + '<div class="tb-prog"><span style="width:' + w + '%"></span></div>'
                + '<div class="tb-foot"><span>факт <b>' + (pct == null ? '—' : pct + '%') + '</b>'
                + (isToday ? ' идёт' : '') + '</span>'
                + '<span class="tb-y">' + prevLbl + ' ' + (yp == null ? '—' : yp + '%') + '</span></div>'
                + '</div>';
        }).join('');

        host.innerHTML = '<div class="tb-card-wrap">' + head
            + '<div class="tb-grid">' + cards + '</div></div>';

        // листание дня — перерисовать борд на месте (без запросов)
        host.querySelectorAll('.tb-nav').forEach(function (el) {
            el.addEventListener('click', function () {
                if (el.classList.contains('is-disabled')) return;
                var nd = +boardDate.slice(8, 10) + (+el.dataset.step);
                if (nd < 1 || nd > dim) return;
                boardDate = S.dateStr(S.state.year, S.state.month, nd);
                renderTodayBoard(host);
            });
        });
    }

    // ============================================================
    // ЭКРАН 3 — Мобильный «мои смены»
    // ============================================================
    // Личный экран бармена: месяц-календарь (Пн→Вс) с блоком-сменой в каждом
    // дне (цвет = точка, высота = день/вечер, рамка = статус), сводка
    // смены/часы/без факта, мини-легенда и карточка выбранного дня с действием
    // (ввести факт / отметить конец смены / править факт). Источник идеи —
    // Claude Design «График смен — идеи» (мобильный экран).
    var DOW_HDR = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

    // Блок-смена внутри ячейки календаря (px, не %): высота — день/вечер,
    // ширина — день/вечер, рамка-кольцо — статус (сегодня/ждёт факт/конфликт).
    function calBarStyle(col, st, eve) {
        var bg = rgba(col, st === 'soon' ? 0.45 : 0.9);
        var bd = '1px solid rgba(0,0,0,.06)';
        if (st === 'today') { bd = '2px solid ' + ACCENT; bg = rgba(col, 0.85); }
        else if (st === 'nofact') { bd = '2px solid ' + AMBER; bg = rgba(col, 0.18); }
        else if (st === 'conflict') { bd = '2px solid ' + RED; bg = rgba(col, 0.5); }
        return 'width:' + (eve ? '58%' : '100%') + ';height:' + (eve ? '9px' : '17px')
            + ';background:' + bg + ';border:' + bd;
    }

    function renderMyShifts(host, opts) {
        if (!host) return;
        opts = opts || {};
        var today = S.todayStr();
        var year = S.state.year, month = S.state.month;
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
        var mine = shiftsOf(emp);
        var byDate = {};
        mine.forEach(function (s) { if (!byDate[s.date]) byDate[s.date] = s; });
        var locName = function (id) { var l = locById(id); return l ? (l.short_name || l.name) : ''; };
        function offReqOn(ds) { return S.getDayOffEmployees(ds).indexOf(emp.name) !== -1; }

        var dim = daysInMonth();
        var monthPrefix = year + '-' + pad2(month);
        var todayInMonth = today.indexOf(monthPrefix) === 0;

        // сводка месяца
        var monthCount = mine.length;
        var factMin = 0;
        mine.forEach(function (s) { if (s.fact_minutes != null) factMin += s.fact_minutes; });
        var factH = Math.round(factMin / 60);
        var noFact = mine.filter(function (s) { return s.date < today && s.fact_minutes == null; }).length;

        // точки сотрудника (для подзаголовка и мини-легенды)
        var venueIdx = [];
        mine.forEach(function (s) { var i = locIndex(s.location_id); if (i >= 0 && venueIdx.indexOf(i) === -1) venueIdx.push(i); });
        venueIdx.sort(function (a, b) { return a - b; });

        // выбранный день по умолчанию: сегодня (если месяц текущий), иначе первый
        // день без факта, иначе первая смена, иначе 1.
        var selN;
        if (todayInMonth) selN = +today.slice(8, 10);
        else {
            var firstNoFact = mine.filter(function (s) { return s.date < today && s.fact_minutes == null; })
                .sort(function (a, b) { return a.date < b.date ? -1 : 1; })[0];
            var firstShift = mine.slice().sort(function (a, b) { return a.date < b.date ? -1 : 1; })[0];
            selN = firstNoFact ? +firstNoFact.date.slice(8, 10)
                : (firstShift ? +firstShift.date.slice(8, 10) : 1);
        }

        // ---- статические части (шапка, сводка, легенда, действия) ----
        var venues = venueIdx.map(function (i) { return S.state.locations[i].short_name || S.state.locations[i].name; });
        var sub = esc(emp.name) + (venues.length ? ' · ' + esc(venues.join(' · ')) : '');
        var headHtml = '<div class="ms-top"><div class="ms-av">' + esc(S.employeeLabel(emp.name)) + '</div>'
            + '<div class="ms-tt"><div class="ms-t">Мои смены</div><div class="ms-sub">' + sub + '</div></div></div>';

        var overShifts = monthCount > NORM_SHIFTS;
        var chipsHtml = '<div class="ms-chips">'
            + '<div class="ms-chip"><div class="ms-ck">смены</div><div class="ms-cv"' + (overShifts ? ' style="color:' + AMBER + '"' : '') + '>'
            + monthCount + '<span class="ms-cn2">/' + NORM_SHIFTS + '</span></div></div>'
            + '<div class="ms-chip"><div class="ms-ck">часы</div><div class="ms-cv">'
            + factH + '<span class="ms-cn2">/' + NORM_HOURS + '</span></div></div>'
            + '<div class="ms-chip' + (noFact ? ' ms-chip-warn' : '') + '"><div class="ms-ck">без факта</div>'
            + '<div class="ms-cv"' + (noFact ? ' style="color:' + AMBER + '"' : '') + '>' + noFact + '</div></div>'
            + '</div>';

        // мини-легенда: точки сотрудника + смысл высоты/колец
        var legVenues = venueIdx.map(function (i) {
            var loc = S.state.locations[i];
            return '<span class="ms-lgi"><span class="ms-lgsq" style="background:' + locColor(loc, i)
                + '"></span>' + esc(loc.short_name || loc.name) + '</span>';
        }).join('');
        var legendHtml = '<div class="ms-leg">' + legVenues
            + '<span class="ms-lgi">высота — день/вечер</span>'
            + '<span class="ms-lgi" style="color:' + ACCENT + '">кольцо — сегодня</span>'
            + '<span class="ms-lgi" style="color:' + AMBER + '">кольцо — ждёт факт</span>'
            + '<span class="ms-lgi"><span class="ms-lgoff"></span>выходной по заявке</span>'
            + '</div>';

        // Действия: «Запросить/Отменить выходной» на выбранный день + .ics.
        // Текст и data-off зависят от выбранного дня (строится в paint).
        function actsHtml(sel) {
            var ds = S.dateStr(year, month, sel);
            var off = offReqOn(ds);
            return '<div class="ms-acts"><div class="ms-act ms-act-out" data-ds="' + ds
                + '" data-off="' + (off ? '1' : '') + '">'
                + (off ? 'Отменить выходной' : 'Запросить выходной') + '</div>'
                + (opts.icsHref ? '<a class="ms-act ms-act-ics" href="' + esc(opts.icsHref) + '">.ics</a>' : '')
                + '</div>';
        }

        // ---- календарь (зависит от выбранного дня) ----
        function calendarHtml(sel) {
            var firstDow = new Date(year, month - 1, 1).getDay();
            var lead = (firstDow + 6) % 7; // понедельник = 0
            var cells = DOW_HDR.map(function (d, i) {
                return '<div class="ms-wd' + (i >= 5 ? ' is-wknd' : '') + '">' + d + '</div>';
            }).join('');
            for (var b = 0; b < lead; b++) cells += '<div class="ms-cell ms-blank"></div>';
            for (var n = 1; n <= dim; n++) {
                var ds = S.dateStr(year, month, n);
                var dow = new Date(year, month - 1, n).getDay();
                var wknd = isWeekend(dow);
                var isToday = ds === today;
                var isSel = n === sel;
                var s = byDate[ds];
                var off = !s && offReqOn(ds);
                var cls = 'ms-cell' + (isToday ? ' is-today' : '') + (isSel ? ' is-sel' : '');
                var numCls = 'ms-cnum' + (isToday ? ' is-today' : (wknd ? ' is-wknd' : ''));
                var inner;
                if (s) {
                    var st = shiftStatus(s, today), col = colorById(s.location_id), eve = isEvening(s);
                    inner = '<span class="ms-cbar" style="' + calBarStyle(col, st, eve) + '"></span>';
                } else if (off) {
                    inner = '<span class="ms-coff"></span>';
                } else {
                    inner = '';
                }
                cells += '<div class="' + cls + '" data-n="' + n + '">'
                    + '<span class="' + numCls + '">' + n + '</span>'
                    + '<span class="ms-cwrap">' + inner + '</span></div>';
            }
            return '<div class="ms-cal">' + cells + '</div>';
        }

        // ---- карточка выбранного дня ----
        var PILL = {
            done: ['отработана', '#4f7a3e', '#e4eedb'],
            nofact: ['ждёт факт', '#a9772a', '#f7e6c6'],
            soon: ['предстоит', '#6f7c9a', '#e7eaf1'],
            today: ['идёт сейчас', ACCENT, '#f7e6d8'],
            conflict: ['конфликт', RED, '#eec3b3']
        };
        function detailHtml(sel) {
            var ds = S.dateStr(year, month, sel);
            var dow = new Date(year, month - 1, sel).getDay();
            var s = byDate[ds];
            var dateLbl = dows(dow) + ' · ' + pad2(sel) + '.' + pad2(month);
            var out = '<div class="ms-lbl">ВЫБРАННЫЙ ДЕНЬ</div>';
            if (s) {
                var st = shiftStatus(s, today), eve = isEvening(s), col = colorById(s.location_id);
                var pill = PILL[st] || ['', '#6f675c', '#eeeae2'];
                var role = eve ? 'вечер · второй бармен' : 'день · бармен';
                var hours = st === 'done' ? 'факт ' + S.minutesToHhMm(s.fact_minutes)
                    : (st === 'nofact' ? 'часы не введены' : '');
                // кнопка действия
                var btn = '';
                if (st === 'nofact') btn = '<div class="ms-dbtn ms-dbtn-warn" data-act="fact" data-shift-id="' + esc(s.id) + '">Ввести факт часов</div>';
                else if (st === 'today') btn = '<div class="ms-dbtn ms-dbtn-dark" data-act="fact" data-shift-id="' + esc(s.id) + '">Отметить конец смены</div>';
                else if (st === 'done') btn = '<div class="ms-dbtn" data-act="fact" data-shift-id="' + esc(s.id) + '">Факт ' + S.minutesToHhMm(s.fact_minutes) + ' · править</div>';
                return out + '<div class="ms-card' + (st === 'today' ? ' ms-today' : '') + '">'
                    + '<div class="ms-drow"><span class="ms-dd">' + esc(dateLbl) + '</span>'
                    + '<span class="ms-pill" style="color:' + pill[1] + ';background:' + pill[2] + '">' + esc(pill[0]) + '</span></div>'
                    + '<div class="ms-dwho"><span class="ms-dsq" style="background:' + col + '"></span>'
                    + '<span class="ms-dpt">' + esc(locName(s.location_id)) + '</span>'
                    + '<span class="ms-drole">' + role + '</span></div>'
                    + '<div class="ms-dmeta">' + (s.start_time ? '<span>старт ' + esc(s.start_time) + '</span>' : '')
                    + (hours ? '<span class="ms-dh">' + esc(hours) + '</span>' : '') + '</div>'
                    + btn + '</div>';
            }
            // выходной / не назначено
            var off = offReqOn(ds);
            return out + '<div class="ms-card">'
                + '<div class="ms-drow"><span class="ms-dd">' + esc(dateLbl) + '</span>'
                + '<span class="ms-pill" style="color:#8a8073;background:#efe9de">' + (off ? 'выходной по заявке' : 'выходной') + '</span></div>'
                + '<div class="ms-doff">' + (off
                    ? 'Вы подали заявку на выходной — смена не назначена.'
                    : 'Смена не назначена. Можно подать пожелание выйти в этот день.') + '</div></div>';
        }

        // ---- сборка + перерисовка по выбранному дню ----
        function paint() {
            host.innerHTML = headHtml + chipsHtml + calendarHtml(selN) + legendHtml
                + detailHtml(selN) + actsHtml(selN);
            // выбор дня
            host.querySelectorAll('.ms-cell[data-n]').forEach(function (el) {
                el.addEventListener('click', function () {
                    selN = +el.dataset.n;
                    paint();
                });
            });
            // запрос/снятие выходного на выбранный день
            if (opts.onDayOffToggle) {
                host.querySelectorAll('.ms-act-out[data-ds]').forEach(function (el) {
                    el.addEventListener('click', function () {
                        opts.onDayOffToggle(emp.name, el.dataset.ds, el.dataset.off === '1');
                    });
                });
            }
            // кнопка действия в карточке дня — ввод/правка факта
            if (S._onScreenShiftClick) {
                host.querySelectorAll('.ms-dbtn[data-act="fact"]').forEach(function (el) {
                    el.addEventListener('click', function () {
                        var sh = S.state.shifts.filter(function (s) { return String(s.id) === el.dataset.shiftId; })[0];
                        if (sh) S._onScreenShiftClick(sh);
                    });
                });
            }
        }
        paint();
    }

    // ============================================================
    // ЛЕГЕНДА — как читать график
    // ============================================================
    function renderLegend(host) {
        if (!host) return;
        var NEU = '#9a8f7f', SAMPLE = '#6f93a6';

        // ТОЧКА — ЦВЕТ (из реальных локаций)
        var dots = S.state.locations.map(function (loc, i) {
            return '<div class="lg-item"><span class="lg-sq" style="background:' + locColor(loc, i)
                + '"></span><span class="lg-t">' + esc(loc.short_name || loc.name) + '</span></div>';
        }).join('');

        // СМЕНА — ВЫСОТА БЛОКА
        function slot(h) {
            return '<span class="lg-slot"><span class="lg-blk" style="height:' + h
                + ';background:' + NEU + '"></span></span>';
        }
        var height = '<div class="lg-item">' + slot('100%')
            + '<span class="lg-t">день <span class="lg-x">· бармен, открытие</span></span></div>'
            + '<div class="lg-item">' + slot('56%')
            + '<span class="lg-t">вечер <span class="lg-x">· 2-й бармен, с 17:00</span></span></div>';

        // СТАТУС СМЕНЫ
        var sts = [
            { l: 'отработана', s: 'факт есть', r: '', o: 0.92 },
            { l: 'предстоит', s: '', r: '', o: 0.5 },
            { l: 'сегодня', s: 'идёт', r: '0 0 0 2px ' + ACCENT, o: 0.92 },
            { l: 'ждёт факт', s: 'прошла без часов', r: '0 0 0 2px ' + AMBER, o: 0.92 },
            { l: 'конфликт', s: 'просил выходной', r: '0 0 0 2px ' + RED, o: 0.92 }
        ].map(function (x) {
            return '<div class="lg-item"><span class="lg-sq" style="background:' + rgba(SAMPLE, x.o)
                + ';border:1px solid rgba(0,0,0,.08)' + (x.r ? ';box-shadow:' + x.r : '')
                + '"></span><span class="lg-t">' + x.l
                + (x.s ? ' <span class="lg-x">· ' + x.s + '</span>' : '') + '</span></div>';
        }).join('');

        // НАГРУЗКА
        var load = '<div class="lg-item"><span class="lg-gauge"><span style="width:100%;background:#5e8c4a"></span></span>'
            + '<span class="lg-t">план <b>' + NORM_SHIFTS + '</b> смен · ' + NORM_HOURS + ' ч</span></div>'
            + '<div class="lg-item"><span class="lg-flag">⚑</span>'
            + '<span class="lg-t">переработка <span class="lg-x">· 6 смен подряд</span></span></div>'
            + '<div class="lg-item"><span class="lg-off"></span>'
            + '<span class="lg-t">обязательный выходной <span class="lg-x">· серый, кистью «Выходной»</span></span></div>'
            + '<div class="lg-item"><span class="lg-dash"></span>'
            + '<span class="lg-t">пусто <span class="lg-x">· не назначен</span></span></div>';

        host.innerHTML = '<div class="lg-card">'
            + '<div class="lg-col"><div class="lg-h">ТОЧКА — ЦВЕТ</div>' + dots + '</div>'
            + '<div class="lg-col"><div class="lg-h">СМЕНА — ВЫСОТА</div>' + height + '</div>'
            + '<div class="lg-col"><div class="lg-h">СТАТУС СМЕНЫ</div>' + sts + '</div>'
            + '<div class="lg-col"><div class="lg-h">НАГРУЗКА</div>' + load + '</div>'
            + '</div>';
    }

    // ============================================================
    // РЕДАКТОР — Полосы по людям (сотрудник × день), кисть/ластик
    // ============================================================
    // Та же ДНК, что в просмотре (цвет = точка, высота = день/вечер), но клетка
    // редактируема: страница (edit.js) держит «кисть» (точка + день/вечер) и
    // ластик и решает в onCell, что делать с кликом. Строка справа — гейдж
    // 15/{смен} · 113/{факт ч}; снизу — «Покрытие точек» (по точке-цвету: дыра =
    // красная обводка). Источник идеи — Claude Design «Редактор графика».
    function renderEditLanes(host, opts) {
        if (!host) return;
        opts = opts || {};
        var today = S.todayStr();
        var year = S.state.year, month = S.state.month, dim = daysInMonth();
        var locs = S.state.locations;

        var days = [];
        for (var d = 1; d <= dim; d++) {
            var dow = new Date(year, month - 1, d).getDay();
            days.push({ d: d, dow: dow, ds: S.dateStr(year, month, d) });
        }
        function dayCls(x) { return x.ds === today ? ' is-today' : (isWeekend(x.dow) ? ' is-wknd' : ''); }

        // шапка дней
        var head = '<div class="el-row el-head"><div class="el-name">СОТРУДНИК</div><div class="el-cells">'
            + days.map(function (x) {
                return '<div class="el-dh' + dayCls(x) + '" data-ds="' + x.ds + '" title="План / факт дня">'
                    + '<span class="el-dow">' + dows(x.dow) + '</span><span class="el-dt">' + pad2(x.d) + '</span></div>';
            }).join('')
            + '</div><div class="el-gauge-h">ПЛАН/ФАКТ</div></div>';

        // строки сотрудников
        var rows = S.state.employees.map(function (emp) {
            var byDate = {};
            shiftsOf(emp).forEach(function (s) {
                // для клетки показываем дневную смену в приоритете над вечерней
                if (!byDate[s.date] || (isEvening(byDate[s.date]) && !isEvening(s))) byDate[s.date] = s;
            });
            var maxRun = 0, run = 0, factMin = 0, shifts = 0;
            var cells = days.map(function (x) {
                var s = byDate[x.ds];
                var off = S.getDayOffEmployees(x.ds).indexOf(emp.name) !== -1;
                if (s) { run++; if (run > maxRun) maxRun = run; shifts++; if (s.fact_minutes != null) factMin += s.fact_minutes; }
                else { run = 0; }
                var dataEmp = esc(emp.id || emp.name);
                if (!s) {
                    // обязательный выходной — серый блок (явная пометка, не пусто)
                    return '<div class="el-cell' + dayCls(x) + '" data-emp="' + dataEmp + '" data-ds="' + x.ds
                        + '" data-day="' + x.d + '">'
                        + (off ? '<span class="el-dayoff-blk" title="обязательный выходной"></span>' : '') + '</div>';
                }
                var col = colorById(s.location_id), eve = isEvening(s), future = x.ds > today;
                var bd = '1px solid rgba(0,0,0,.06)';
                if (x.ds === today) bd = '2px solid ' + ACCENT;
                if (off) bd = '2px solid ' + RED;
                var loc = locById(s.location_id);
                var tip = (loc ? (loc.short_name || loc.name) : '') + ' · ' + (eve ? 'вечер' : 'день')
                    + (s.start_time ? ' · ' + s.start_time : '') + (off ? ' · конфликт с выходным' : '');
                var blk = '<span class="el-blk" style="height:' + (eve ? '9px' : '16px')
                    + ';background:' + rgba(col, future ? 0.5 : 0.9) + ';border:' + bd + '"></span>';
                return '<div class="el-cell' + dayCls(x) + '" data-emp="' + dataEmp + '" data-ds="' + x.ds
                    + '" data-day="' + x.d + '" data-shift-id="' + esc(s.id) + '" title="' + esc(tip) + '">' + blk + '</div>';
            }).join('');

            var hours = Math.round(factMin / 60);
            var sColor = shifts > NORM_SHIFTS ? AMBER : (shifts < 10 ? '#a89e90' : '#5e8c4a');
            var flag = maxRun >= 6 ? '<span class="el-flag" title="' + maxRun + ' смен подряд">⚑</span>' : '';
            return '<div class="el-row"><div class="el-name"><span class="el-ini">' + esc(S.employeeLabel(emp.name))
                + '</span><span class="el-nm">' + esc(S.employeeShortName(emp.name)) + '</span>' + flag + '</div>'
                + '<div class="el-cells">' + cells + '</div>'
                + '<div class="el-gauge"><span class="el-g1">' + NORM_SHIFTS + '/<b style="color:' + sColor + '">' + shifts + '</b> см</span>'
                + '<span class="el-g2">' + NORM_HOURS + '/<b>' + hours + '</b> ч</span></div></div>';
        }).join('');

        // подвал «Покрытие точек»: дыра = точка без дневной смены (сегодня и вперёд)
        function covered(ds, locId) {
            return S.state.shifts.some(function (s) {
                return s.date === ds && s.location_id === locId && !isEvening(s);
            });
        }
        var holeCount = 0;
        var cov = days.map(function (x) {
            var future = x.ds >= today;
            var miss = [];
            var dots = locs.map(function (loc, i) {
                var ok = covered(x.ds, loc.id);
                if (!ok) { miss.push(loc.short_name || loc.name); if (future) holeCount++; }
                var st = ok ? 'background:' + locColor(loc, i) + ';border:none'
                    : (future ? 'background:#fff;border:1.5px solid ' + RED : 'background:#ece4d6;border:none');
                return '<span class="el-cdot" style="' + st + '"></span>';
            }).join('');
            var tip = (miss.length ? 'дыра: ' + miss.join(', ') : 'покрыто') + ' · ' + pad2(x.d) + '.' + pad2(month);
            return '<div class="el-cov' + dayCls(x) + '" title="' + esc(tip) + '"><span class="el-cgrid">' + dots + '</span></div>';
        }).join('');
        var footer = '<div class="el-row el-foot"><div class="el-name">Покрытие точек'
            + (holeCount ? '<span class="el-hole">' + holeCount + '</span>' : '') + '</div>'
            + '<div class="el-cells">' + cov + '</div><div class="el-gauge-h"></div></div>';

        var minW = 178 + dim * 38 + 104;
        host.innerHTML = '<div class="el-wrap"><div class="el-tbl" style="min-width:' + minW + 'px">'
            + head + rows + footer + '</div></div>';

        // подсветка наведения цветом кисти
        if (opts.brushColor) host.style.setProperty('--el-hover', rgba(opts.brushColor, 0.13));
        else host.style.removeProperty('--el-hover');

        // клик по номеру дня — денежная панель план/факт
        if (opts.onDayHeaderClick) {
            host.querySelectorAll('.el-dh[data-ds]').forEach(function (el) {
                el.addEventListener('click', function () { opts.onDayHeaderClick(el.dataset.ds); });
            });
        }
        // клик по клетке — кисть/ластик (логика на странице)
        if (opts.onCell) {
            host.querySelectorAll('.el-cell[data-emp]').forEach(function (el) {
                el.addEventListener('click', function () {
                    var k = el.dataset.emp, ds = el.dataset.ds, day = +el.dataset.day;
                    var emp = S.state.employees.filter(function (e) { return String(e.id || e.name) === k; })[0];
                    if (!emp) return;
                    var existing = S.state.shifts.filter(function (s) {
                        var m = emp.id ? s.employee_id === emp.id : s.employee_name === emp.name;
                        return m && s.date === ds;
                    });
                    var target = existing.filter(function (s) { return !isEvening(s); })[0] || existing[0] || null;
                    opts.onCell(emp, day, ds, target);
                });
            });
        }
    }

    // экспорт
    S.renderLanes = renderLanes;
    S.renderTodayBoard = renderTodayBoard;
    S.renderMyShifts = renderMyShifts;
    S.renderLegend = renderLegend;
    S.renderEditLanes = renderEditLanes;
    // помощники для редактора (та же ДНК)
    S.isEvening = isEvening;
    S.venueColor = locColor;
    S.colorById = colorById;
    // страница задаёт обработчик клика по смене (ввод факта)
    S.setScreenShiftClick = function (fn) { S._onScreenShiftClick = fn; };
})();

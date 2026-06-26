/* Общий модуль страниц графика смен (/schedule и /schedule/edit):
   API-клиент, состояние месяца, рендер сетки, форматтеры.
   Страничные скрипты (view.js / edit.js) подключаются после него. */

(function () {
    'use strict';

    var MONTH_NAMES = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ];
    var DAY_NAMES = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

    var state = {
        year: new Date().getFullYear(),
        month: new Date().getMonth() + 1, // 1..12
        locations: [],
        roles: [],
        employees: [],
        shifts: [],
        dayOffs: [],
        plans: null // {days: {...}, plan_formula} — только на странице редактора
    };

    // ==================== API ====================

    function api(url, options) {
        options = options || {};
        if (options.body && typeof options.body !== 'string') {
            options.body = JSON.stringify(options.body);
            options.headers = Object.assign(
                { 'Content-Type': 'application/json' }, options.headers || {});
        }
        return fetch(url, options).then(function (res) {
            if (!res.ok) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    throw new Error(data.error || ('HTTP ' + res.status));
                });
            }
            return res.json();
        });
    }

    // ==================== Форматтеры ====================

    function pad2(n) { return String(n).padStart(2, '0'); }

    function dateStr(year, month, day) {
        return year + '-' + pad2(month) + '-' + pad2(day);
    }

    function todayStr() {
        var t = new Date();
        return dateStr(t.getFullYear(), t.getMonth() + 1, t.getDate());
    }

    function formatDateHuman(ds) {
        var p = ds.split('-');
        return p[2] + '.' + p[1] + '.' + p[0];
    }

    function formatMoney(num) {
        return new Intl.NumberFormat('ru-RU').format(Math.round(num));
    }

    /* Экранирование для вставки внешних строк (имена из iiko) в HTML */
    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /* Минуты -> 'Ч:ММ' (например 630 -> '10:30') */
    function minutesToHhMm(minutes) {
        var h = Math.floor(minutes / 60);
        var m = minutes % 60;
        return h + ':' + pad2(m);
    }

    /* 'Ч:ММ' или 'Ч' или 'Ч,5' -> минуты; null если не распознано */
    function parseHoursInput(text) {
        text = (text || '').trim().replace(',', '.');
        if (!text) return null;
        var m = text.match(/^(\d{1,2}):([0-5]\d)$/);
        if (m) return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
        var f = text.match(/^(\d{1,2})(\.\d+)?$/);
        if (f) return Math.round(parseFloat(text) * 60);
        return null;
    }

    /* Короткая подпись сотрудника: short_label из реестра, иначе инициалы
       («Романов Юрий» -> «РЮ»), как в гугл-таблице владельца. */
    function employeeLabel(name) {
        var emp = state.employees.find(function (e) { return e.name === name; });
        if (emp && emp.short_label) return emp.short_label;
        var words = name.split(/\s+/).filter(Boolean);
        if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
        return name.slice(0, 2).toUpperCase();
    }

    function employeeShortName(name) {
        return name.split(/\s+/).slice(0, 2).join(' ');
    }

    /* Сотрудник реестра по стабильному id из iiko (v6). null, если не найден. */
    function getEmployeeById(id) {
        if (!id) return null;
        return state.employees.find(function (e) { return e.id === id; }) || null;
    }

    /* Каноническое имя смены: из реестра по employee_id (актуальное после
       переименования в iiko), иначе снимок employee_name. */
    function shiftDisplayName(shift) {
        var emp = getEmployeeById(shift.employee_id);
        return (emp && emp.name) || shift.employee_name;
    }

    /* Короткая метка смены: short_label из реестра по id, иначе инициалы имени. */
    function shiftLabel(shift) {
        var emp = getEmployeeById(shift.employee_id);
        if (emp && emp.short_label) return emp.short_label;
        return employeeLabel(shiftDisplayName(shift));
    }

    /* Журнал: 'YYYY-MM-DDTHH:MM:SS' -> 'DD.MM HH:MM'. Серверное время как есть,
       без пересчёта таймзоны (ts уже записан в серверном времени). */
    function formatAuditTs(ts) {
        if (!ts) return '';
        var m = String(ts).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
        return m ? (m[3] + '.' + m[2] + ' ' + m[4] + ':' + m[5]) : ts;
    }

    // ==================== Загрузка данных месяца ====================

    function loadDictionaries() {
        return Promise.all([
            api('/api/schedule/locations'),
            api('/api/schedule/roles'),
            api('/api/schedule/employees')
        ]).then(function (res) {
            state.locations = res[0];
            state.roles = res[1];
            state.employees = res[2];
        });
    }

    function loadMonthData() {
        var first = dateStr(state.year, state.month, 1);
        var lastDay = new Date(state.year, state.month, 0).getDate();
        var last = dateStr(state.year, state.month, lastDay);
        return Promise.all([
            api('/api/schedule/' + state.year + '/' + state.month),
            api('/api/schedule/dayoff?date_from=' + first + '&date_to=' + last)
        ]).then(function (res) {
            state.shifts = res[0];
            state.dayOffs = res[1];
        });
    }

    function getDayOffEmployees(ds) {
        return state.dayOffs
            .filter(function (r) { return ds >= r.date_from && ds <= r.date_to; })
            .map(function (r) { return r.employee_name; });
    }

    // ==================== Рендер сетки ====================

    /* Построить сетку месяца.
       opts: {
         gridEl, onChipClick(shift), onCellClick(dateStr, locationId, cellShifts),
         onDateClick(dateStr), showPlans (план дня под датой, только редактор),
         markHoles (подсветка будущих незакрытых ячеек)
       } */
    function renderGrid(opts) {
        var grid = opts.gridEl;
        var locations = state.locations;
        var daysInMonth = new Date(state.year, state.month, 0).getDate();
        var today = todayStr();

        grid.style.gridTemplateColumns = '92px repeat(' + locations.length + ', 1fr)';
        grid.innerHTML = '';

        var header = document.createElement('div');
        header.className = 'schedule-header';
        var dateHead = document.createElement('div');
        dateHead.textContent = 'Дата';
        header.appendChild(dateHead);
        locations.forEach(function (loc) {
            var h = document.createElement('div');
            h.textContent = loc.short_name || loc.name;
            h.title = loc.name;
            header.appendChild(h);
        });
        grid.appendChild(header);

        /* let, не var: ds/cellShifts захватываются обработчиками кликов —
           с var все ячейки получили бы последнюю дату месяца */
        for (let day = 1; day <= daysInMonth; day++) {
            const ds = dateStr(state.year, state.month, day);
            const dow = new Date(state.year, state.month - 1, day).getDay();
            const isWeekend = dow === 5 || dow === 6; // пт/сб — дни повышенного веса
            const isToday = ds === today;
            const dayOffEmps = getDayOffEmployees(ds);

            var dateCell = document.createElement('div');
            dateCell.className = 'schedule-cell date-cell'
                + (isWeekend ? ' weekend-col' : '')
                + (isToday ? ' today' : '');
            dateCell.dataset.date = ds;
            var planLine = '';
            if (opts.showPlans && state.plans && state.plans.days[ds]
                && state.plans.days[ds].plan_total !== null) {
                planLine = '<span class="day-plan">'
                    + formatMoney(state.plans.days[ds].plan_total) + '</span>';
            }
            dateCell.innerHTML =
                '<span class="day-name">' + DAY_NAMES[dow] + '</span>' +
                '<span class="day-number">' + pad2(day) + '.' + pad2(state.month) + '</span>' +
                planLine;
            if (opts.onDateClick) {
                dateCell.style.cursor = 'pointer';
                dateCell.addEventListener('click', opts.onDateClick.bind(null, ds));
            }
            grid.appendChild(dateCell);

            locations.forEach(function (loc) {
                var cell = document.createElement('div');
                var cellShifts = state.shifts.filter(function (s) {
                    return s.date === ds && s.location_id === loc.id;
                });

                var classes = 'schedule-cell shift-cell';
                if (isWeekend) classes += ' weekend-col';
                if (isToday) classes += ' today';
                /* Дыра — только будущее (включая сегодня): прошедшие пустые дни нейтральны */
                if (opts.markHoles && cellShifts.length === 0 && ds >= today) {
                    classes += ' hole';
                }
                cell.className = classes;
                cell.dataset.date = ds;
                cell.dataset.locationId = loc.id;

                var conflictNames = [];
                cellShifts.forEach(function (shift) {
                    var chip = buildChip(shift, dayOffEmps, opts.onChipClick);
                    cell.appendChild(chip);
                    if (dayOffEmps.indexOf(shift.employee_name) !== -1) {
                        conflictNames.push(employeeLabel(shift.employee_name));
                    }
                });

                if (conflictNames.length) {
                    var note = document.createElement('span');
                    note.className = 'conflict-note';
                    note.textContent = 'вых';
                    note.title = 'Просили выходной: ' + conflictNames.join(', ');
                    cell.appendChild(note);
                }

                if (opts.onCellClick) {
                    cell.addEventListener('click', function (e) {
                        if (e.target.closest('.shift-chip')) return;
                        opts.onCellClick(ds, loc.id, cellShifts);
                    });
                }

                grid.appendChild(cell);
            });
        }
    }

    function buildChip(shift, dayOffEmps, onChipClick) {
        var chip = document.createElement('div');
        var isConflict = dayOffEmps.indexOf(shift.employee_name) !== -1;
        chip.className = 'shift-chip' + (isConflict ? ' conflict' : '');
        /* Роль кодируется цветом левой полоски (см. .shift-chip в schedule.css),
           а не заливкой всего чипа — сетка остаётся спокойной. */
        chip.style.setProperty('--role-color', shift.role_color || 'var(--accent)');
        chip.dataset.shiftId = shift.id;

        /* Заполняем ячейку: имя целиком (а не двухбуквенная метка) + строка-мета.
           Мета всегда непустая: «День» / «с HH:MM» (тип смены) + факт часов, если
           проставлен. Раньше дневная смена показывала только инициалы — ячейка
           выглядела пустой. */
        var nameFull = shiftDisplayName(shift);
        var meta = '<span class="chip-when">'
            + (shift.start_time ? 'с ' + escapeHtml(shift.start_time) : 'День') + '</span>';
        if (shift.fact_minutes !== null && shift.fact_minutes !== undefined) {
            meta += '<span class="chip-fact">' + minutesToHhMm(shift.fact_minutes) + '</span>';
        }

        chip.title = nameFull + ' — ' + shift.role_name
            + (shift.start_time ? ', с ' + shift.start_time : '')
            + (shift.fact_minutes != null
                ? ', факт ' + minutesToHhMm(shift.fact_minutes) : '');
        chip.innerHTML =
            '<span class="chip-name">' + escapeHtml(employeeShortName(nameFull)) + '</span>'
            + '<span class="chip-meta">' + meta + '</span>';

        if (onChipClick) {
            chip.addEventListener('click', function (e) {
                e.stopPropagation();
                onChipClick(shift);
            });
        }
        return chip;
    }

    // ==================== Виджеты (общие для редактора и просмотра) ====================
    // Нагрузка и Пожелания (read-only) — money-free, общий рендер, чтобы редактор
    // и просмотр показывали одно и то же. Нагрузка — GET /api/schedule/widgets
    // (без iiko, без рублей). Денежная «План/Факт по дням» — только в редакторе
    // (см. edit.js), на странице барменов финансов нет.

    /* Нагрузка по сотрудникам: смены/норма (цвет по выполнению), часы факта,
       макс. серия подряд (флаг 5+), смены без факта. tbody — элемент <tbody>. */
    function renderLoad(tbody, rows, norm) {
        norm = norm || 15;
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="missing-fact">Смен в этом месяце нет</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (r) {
            var n = r.shifts_count;
            var shiftColor = n >= norm ? 'var(--success)'
                : (n < norm * 0.6 ? 'var(--warning)' : 'var(--text-primary)');
            var shiftsCell = '<strong style="color:' + shiftColor + '">' + n + '</strong>'
                + '<span style="color:var(--text-tertiary)"> / ' + norm + '</span>';
            var hours = r.fact_minutes > 0 ? minutesToHhMm(r.fact_minutes) : '0:00';
            var streak = r.max_streak || 0;
            var streakCell = streak >= 5
                ? '<span style="color:var(--danger);font-weight:600" title="'
                  + streak + ' смен подряд — переработка, стоит дать отдых">' + streak + '</span>'
                : '<span style="color:var(--text-tertiary)">' + (streak || '') + '</span>';
            var missing = r.missing_fact > 0
                ? '<span class="missing-fact">' + r.missing_fact + '</span>' : '';
            return '<tr>'
                + '<td title="' + escapeHtml(r.employee_name) + '">'
                + escapeHtml(employeeLabel(r.employee_name))
                + ' <span style="color:var(--text-tertiary)">'
                + escapeHtml(employeeShortName(r.employee_name)) + '</span></td>'
                + '<td>' + shiftsCell + '</td>'
                + '<td>' + hours + '</td>'
                + '<td>' + streakCell + '</td>'
                + '<td>' + missing + '</td>'
                + '</tr>';
        }).join('');
    }

    /* Пожелания (read-only, для страницы просмотра). wishes — [{employee_name, text}]. */
    function renderWishesReadonly(el, wishes) {
        if (!el) return;
        var nonEmpty = (wishes || []).filter(function (w) { return (w.text || '').trim(); });
        if (!nonEmpty.length) {
            el.innerHTML = '<div class="cov-empty">Пожеланий нет</div>';
            return;
        }
        el.innerHTML = nonEmpty.map(function (w) {
            return '<div class="wish-card wish-ro">'
                + '<div class="emp-name">' + escapeHtml(employeeLabel(w.employee_name))
                + ' ' + escapeHtml(employeeShortName(w.employee_name)) + '</div>'
                + '<div class="wish-text">' + escapeHtml(w.text).replace(/\n/g, '<br>') + '</div>'
                + '</div>';
        }).join('');
    }

    // ==================== Виджет «План / Факт по дням» (деньги) ====================
    // План выручки дня (веса дней), факт (живой iiko OLAP), % выполнения и кто стоял
    // на смене; клик по дню — разбивка по барам. Читает state.plans (GET /plans) +
    // state.shifts. Общий для редактора и просмотра (host передаётся снаружи).

    /* Бейдж % выполнения: >=100 зелёный, 85..99 янтарный, <85 красный, нет — тире. */
    function pfPctBadge(pct) {
        if (pct == null) return '<span class="pf-dim">&mdash;</span>';
        var cls = pct >= 100 ? 'good' : (pct >= 85 ? 'mid' : 'low');
        return '<span class="pf-badge pf-' + cls + '">' + pct + '%</span>';
    }

    /* Чип бармена: короткая метка (как в сетке), полное имя — в title. */
    function pfWhoChip(shift) {
        var title = shiftDisplayName(shift) + (shift.start_time ? ' — с ' + shift.start_time : '');
        return '<span class="pf-who" title="' + escapeHtml(title) + '">'
            + escapeHtml(shiftLabel(shift)) + '</span>';
    }

    /* Разбивка дня по барам: план/факт/% и кто на каждом баре. */
    function pfDetail(dayData, dayShifts) {
        var locs = (dayData && dayData.locations) || {};
        var rows = state.locations.map(function (loc) {
            var c = locs[loc.id] || {};
            var locShifts = dayShifts.filter(function (s) { return s.location_id === loc.id; });
            if (c.plan == null && c.fact == null && !locShifts.length) return '';
            var pct = (c.plan != null && c.plan > 0 && c.fact != null)
                ? Math.round(c.fact / c.plan * 100) : null;
            var who = locShifts.map(pfWhoChip).join('') || '<span class="pf-dim">нет смен</span>';
            return '<tr>'
                + '<td>' + escapeHtml(loc.short_name || loc.name) + '</td>'
                + '<td class="pf-num">' + (c.plan != null ? formatMoney(c.plan) : '&mdash;') + '</td>'
                + '<td class="pf-num">' + (c.fact != null ? formatMoney(c.fact) : '<span class="pf-dim">&mdash;</span>') + '</td>'
                + '<td class="pf-pct">' + pfPctBadge(pct) + '</td>'
                + '<td class="pf-chips">' + who + '</td>'
                + '</tr>';
        }).filter(Boolean).join('');
        return '<table class="pf-sub"><tbody>' + rows + '</tbody></table>';
    }

    // Выбранная точка в «План/Факт»: 'all' (агрегат) либо location_id. Сохраняется
    // между ре-рендерами (общая для редактора и просмотра — у каждого свой host,
    // но виджет на странице один).
    var pfScope = 'all';

    /* Таблица «План / Факт по дням». host — контейнер; данные из state.plans/shifts.
       Селектор сверху: «Все» (сумма точек) либо отдельная точка (план/факт и кто
       стоял именно на ней). */
    function renderPlanFact(host) {
        if (!host) return;
        var days = state.plans && state.plans.days;
        if (!days) { host.innerHTML = '<div class="pf-empty">Нет данных по плану</div>'; return; }

        if (pfScope !== 'all' && !state.locations.some(function (l) { return l.id === pfScope; })) {
            pfScope = 'all';
        }
        var loc = (pfScope === 'all') ? null
            : state.locations.find(function (l) { return l.id === pfScope; });
        var tabs = '<div class="pf-scope">'
            + '<button class="pf-tab' + (pfScope === 'all' ? ' active' : '') + '" data-scope="all">Все</button>'
            + state.locations.map(function (l) {
                return '<button class="pf-tab' + (pfScope === l.id ? ' active' : '')
                    + '" data-scope="' + l.id + '" title="' + escapeHtml(l.name) + '">'
                    + escapeHtml(l.short_name || l.name) + '</button>';
              }).join('')
            + '</div>';

        function wireTabs() {
            host.querySelectorAll('.pf-tab').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var s = btn.dataset.scope;
                    pfScope = (s === 'all') ? 'all' : parseInt(s, 10);
                    renderPlanFact(host);
                });
            });
        }

        var daysInMonth = new Date(state.year, state.month, 0).getDate();
        var shiftsByDay = {};
        state.shifts.forEach(function (s) {
            (shiftsByDay[s.date] = shiftsByDay[s.date] || []).push(s);
        });

        var body = [];
        var sumPlan = 0, sumFact = 0, planOfFactDays = 0;
        var anyPlan = false, anyFact = false;

        for (var day = 1; day <= daysInMonth; day++) {
            var ds = dateStr(state.year, state.month, day);
            var d = days[ds] || {};
            var allShifts = shiftsByDay[ds] || [];

            // Данные строки зависят от выбранной точки: «Все» — агрегат дня,
            // иначе — план/факт и смены конкретной точки.
            var plan, fact, rowShifts;
            if (pfScope === 'all') {
                plan = (d.plan_total != null) ? d.plan_total : null;
                fact = (d.fact_total != null) ? d.fact_total : null;
                rowShifts = allShifts;
            } else {
                var c = (d.locations && d.locations[pfScope]) || {};
                plan = (c.plan != null) ? c.plan : null;
                fact = (c.fact != null) ? c.fact : null;
                rowShifts = allShifts.filter(function (s) { return s.location_id === pfScope; });
            }
            // Пропускаем полностью пустую строку. День/точка с фактом без плана и
            // смен показываем — это сигнал (выручка была, а смен/плана нет).
            if (plan == null && fact == null && !rowShifts.length) continue;

            if (plan != null) { sumPlan += plan; anyPlan = true; }
            if (fact != null) { sumFact += fact; anyFact = true; }
            if (plan != null && fact != null) planOfFactDays += plan;

            var dow = new Date(state.year, state.month - 1, day).getDay();
            var weekend = (dow === 5 || dow === 6);
            var pct = (plan != null && plan > 0 && fact != null)
                ? Math.round(fact / plan * 100) : null;

            var seen = {}, chips = [];
            rowShifts.forEach(function (s) {
                var key = s.employee_id || s.employee_name;
                if (seen[key]) return;
                seen[key] = true;
                chips.push(pfWhoChip(s));
            });

            // Разворот по барам — только в режиме «Все» (в режиме точки разбивать нечего)
            var expandable = (pfScope === 'all');
            body.push(
                '<tr class="pf-day' + (expandable ? '' : ' pf-flat') + '" data-date="' + ds + '">'
                + '<td class="pf-date"><span class="pf-dow' + (weekend ? ' pf-we' : '') + '">'
                    + DAY_NAMES[dow] + '</span> ' + pad2(day) + '.' + pad2(state.month) + '</td>'
                + '<td class="pf-num">' + (plan != null ? formatMoney(plan) : '&mdash;') + '</td>'
                + '<td class="pf-num">' + (fact != null ? formatMoney(fact) : '<span class="pf-dim">&mdash;</span>') + '</td>'
                + '<td class="pf-pct">' + pfPctBadge(pct) + '</td>'
                + '<td class="pf-chips">' + (chips.join('') || '<span class="pf-dim">нет смен</span>') + '</td>'
                + '</tr>'
                + (expandable
                    ? '<tr class="pf-detail" data-detail="' + ds + '" hidden><td colspan="5">'
                      + pfDetail(d, allShifts) + '</td></tr>'
                    : '')
            );
        }

        if (!body.length) {
            host.innerHTML = tabs + '<div class="pf-empty">Нет планов и смен'
                + (loc ? ' по точке «' + escapeHtml(loc.short_name || loc.name) + '»' : '') + '</div>';
            wireTabs();
            return;
        }

        // Итоговый % — факт к плану только тех дней, где факт уже есть (как на
        // дашборде): иначе будущие дни с планом без факта занижали бы выполнение.
        var totalPct = (planOfFactDays > 0 && anyFact)
            ? Math.round(sumFact / planOfFactDays * 100) : null;
        var total = '<tr class="pf-total">'
            + '<td>Итого' + (loc ? ' · ' + escapeHtml(loc.short_name || loc.name) : '') + '</td>'
            + '<td class="pf-num">' + (anyPlan ? formatMoney(sumPlan) : '&mdash;') + '</td>'
            + '<td class="pf-num">' + (anyFact ? formatMoney(sumFact) : '&mdash;') + '</td>'
            + '<td class="pf-pct">' + pfPctBadge(totalPct) + '</td>'
            + '<td></td></tr>';

        host.innerHTML = tabs
            + '<table class="pf-table"><thead><tr>'
            + '<th>Дата</th><th class="pf-num">План</th><th class="pf-num">Факт</th>'
            + '<th class="pf-pct">%</th><th>Смена</th>'
            + '</tr></thead><tbody>' + body.join('') + total + '</tbody></table>';

        wireTabs();
        host.querySelectorAll('tr.pf-day:not(.pf-flat)').forEach(function (tr) {
            tr.addEventListener('click', function () {
                var detail = host.querySelector('tr.pf-detail[data-detail="' + tr.dataset.date + '"]');
                if (!detail) return;
                detail.hidden = !detail.hidden;
                tr.classList.toggle('open', !detail.hidden);
            });
        });
    }

    /* Мини-виджет «Выполнение плана»: позавчера / вчера / сегодня (агрегат по всем
       точкам). Берёт state.plans отображаемого месяца; дата вне него — «—». Сегодня
       помечаем «идёт» (факт неполный — день не закрыт). */
    function renderRecentCompletion(host) {
        if (!host) return;
        var days = state.plans && state.plans.days;
        if (!days) { host.innerHTML = '<div class="cov-empty">Нет данных</div>'; return; }
        var now = new Date();
        var defs = [
            { off: 2, label: 'Позавчера' },
            { off: 1, label: 'Вчера' },
            { off: 0, label: 'Сегодня' }
        ];
        host.innerHTML = defs.map(function (def) {
            var dt = new Date(now.getFullYear(), now.getMonth(), now.getDate() - def.off);
            var ds = dateStr(dt.getFullYear(), dt.getMonth() + 1, dt.getDate());
            var d = days[ds];
            var plan = (d && d.plan_total != null) ? d.plan_total : null;
            var fact = (d && d.fact_total != null) ? d.fact_total : null;
            var pct = (plan != null && plan > 0 && fact != null) ? Math.round(fact / plan * 100) : null;
            var dd = ds.slice(8) + '.' + ds.slice(5, 7);
            var badge = d ? pfPctBadge(pct) : '<span class="pf-dim">&mdash;</span>';
            var money;
            if (!d) {
                money = '<span class="rc-money pf-dim">не в этом месяце</span>';
            } else if (plan == null && fact == null) {
                money = '<span class="rc-money pf-dim">нет данных</span>';
            } else {
                money = '<span class="rc-money">' + (fact != null ? formatMoney(fact) : '—')
                    + ' / ' + (plan != null ? formatMoney(plan) : '—') + '</span>';
            }
            return '<div class="rc-item">'
                + '<div class="rc-head"><span class="rc-label">' + def.label
                + ' <span class="rc-date">' + dd + '</span></span>'
                + '<span class="rc-val">' + badge
                + (def.off === 0 ? '<span class="rc-live">идёт</span>' : '') + '</span></div>'
                + money
                + '</div>';
        }).join('');
    }

    // ==================== UI-мелочи ====================

    function updateMonthDisplay(el) {
        el.textContent = MONTH_NAMES[state.month - 1] + ' ' + state.year;
    }

    function shiftMonth(delta) {
        state.month += delta;
        if (state.month < 1) { state.month = 12; state.year--; }
        if (state.month > 12) { state.month = 1; state.year++; }
    }

    function showToast(msg, isError) {
        var toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.toggle('error', !!isError);
        toast.classList.add('show');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(function () { toast.classList.remove('show'); }, 2500);
    }

    function showLoading(show) {
        var el = document.getElementById('loading');
        if (el) el.style.display = show ? 'flex' : 'none';
    }

    window.Schedule = {
        state: state,
        api: api,
        MONTH_NAMES: MONTH_NAMES,
        DAY_NAMES: DAY_NAMES,
        dateStr: dateStr,
        todayStr: todayStr,
        formatDateHuman: formatDateHuman,
        formatMoney: formatMoney,
        minutesToHhMm: minutesToHhMm,
        parseHoursInput: parseHoursInput,
        employeeLabel: employeeLabel,
        employeeShortName: employeeShortName,
        getEmployeeById: getEmployeeById,
        shiftDisplayName: shiftDisplayName,
        shiftLabel: shiftLabel,
        renderLoad: renderLoad,
        renderPlanFact: renderPlanFact,
        renderRecentCompletion: renderRecentCompletion,
        renderWishesReadonly: renderWishesReadonly,
        formatAuditTs: formatAuditTs,
        escapeHtml: escapeHtml,
        loadDictionaries: loadDictionaries,
        loadMonthData: loadMonthData,
        getDayOffEmployees: getDayOffEmployees,
        renderGrid: renderGrid,
        updateMonthDisplay: updateMonthDisplay,
        shiftMonth: shiftMonth,
        showToast: showToast,
        showLoading: showLoading
    };
})();

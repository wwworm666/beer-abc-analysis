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

    /* Аббревиатура денег для плотной таблицы: 134400 -> «134к», 2.89М -> «2.9М».
       Точные рубли — в title ячейки. */
    function formatK(n) {
        if (n == null) return '&mdash;';
        n = Math.round(n);
        if (Math.abs(n) >= 1000000) return (Math.round(n / 100000) / 10) + 'М';
        if (Math.abs(n) >= 1000) return Math.round(n / 1000) + 'к';
        return String(n);
    }

    /* Разворот дня: кто работал на каждой точке (бармен). Деньги/% уже в строке. */
    function pfPeople(dayShifts) {
        var byLoc = {};
        dayShifts.forEach(function (s) { (byLoc[s.location_id] = byLoc[s.location_id] || []).push(s); });
        var rows = state.locations.map(function (loc) {
            var ls = byLoc[loc.id] || [];
            if (!ls.length) return '';
            return '<tr><td class="pf-pp-name">' + escapeHtml(loc.short_name || loc.name) + '</td>'
                + '<td>' + ls.map(pfWhoChip).join('') + '</td></tr>';
        }).filter(Boolean).join('');
        return rows ? '<table class="pf-pp"><tbody>' + rows + '</tbody></table>'
            : '<span class="pf-dim">смен в этот день нет</span>';
    }

    /* Таблица «План / Факт по дням»: ОДНА таблица — колонки по всем точкам (факт над
       планом), плюс «Итого» (день) и %. Без вкладок. Клик по строке дня — кто работал
       на каждой точке. host — контейнер; данные из state.plans/shifts. Месячную сводку
       пишем в .pf-summary заголовка карточки (видна, когда таблица свёрнута). */
    function renderPlanFact(host) {
        if (!host) return;
        var card = host.closest && host.closest('.section-card');
        var sumEl = card && card.querySelector('.pf-summary');
        if (sumEl) sumEl.textContent = '';
        var days = state.plans && state.plans.days;
        if (!days) { host.innerHTML = '<div class="pf-empty">Нет данных по плану</div>'; return; }

        var locs = state.locations;
        var daysInMonth = new Date(state.year, state.month, 0).getDate();
        var shiftsByDay = {};
        state.shifts.forEach(function (s) { (shiftsByDay[s.date] = shiftsByDay[s.date] || []).push(s); });

        // Ячейка точки: факт (цвет по %) над планом; «—» если нет данных
        function ttCell(plan, fact, name, isTotal) {
            var pct = (plan != null && plan > 0 && fact != null) ? Math.round(fact / plan * 100) : null;
            var lvl = pct == null ? '' : (pct >= 100 ? ' rc-good' : (pct >= 85 ? ' rc-mid' : ' rc-low'));
            var title = name + ': факт ' + (fact != null ? formatMoney(fact) : '—')
                + ' / план ' + (plan != null ? formatMoney(plan) : '—') + (pct != null ? ' (' + pct + '%)' : '');
            return '<td class="pf-tt' + (isTotal ? ' pf-tt-total' : '') + '" title="' + escapeHtml(title) + '">'
                + '<span class="pf-tt-f' + lvl + '">' + formatK(fact) + '</span>'
                + '<span class="pf-tt-p">' + formatK(plan) + '</span></td>';
        }

        var body = [];
        var sumPlan = 0, sumFact = 0, planOfFactDays = 0, anyPlan = false, anyFact = false;
        var ttSum = {};
        locs.forEach(function (L) { ttSum[L.id] = { p: 0, f: 0, hasP: false, hasF: false }; });

        for (var day = 1; day <= daysInMonth; day++) {
            var ds = dateStr(state.year, state.month, day);
            var d = days[ds] || {};
            var dl = d.locations || {};
            var dayShifts = shiftsByDay[ds] || [];
            var pt = (d.plan_total != null) ? d.plan_total : null;
            var ft = (d.fact_total != null) ? d.fact_total : null;
            if (pt == null && ft == null && !dayShifts.length) continue;

            if (pt != null) { sumPlan += pt; anyPlan = true; }
            if (ft != null) { sumFact += ft; anyFact = true; }
            if (pt != null && ft != null) planOfFactDays += pt;

            var dow = new Date(state.year, state.month - 1, day).getDay();
            var weekend = (dow === 5 || dow === 6);
            var dayPct = (pt != null && pt > 0 && ft != null) ? Math.round(ft / pt * 100) : null;

            var ttTds = locs.map(function (L) {
                var c = dl[L.id] || {};
                var p = (c.plan != null) ? c.plan : null;
                var f = (c.fact != null) ? c.fact : null;
                if (p != null) { ttSum[L.id].p += p; ttSum[L.id].hasP = true; }
                if (f != null) { ttSum[L.id].f += f; ttSum[L.id].hasF = true; }
                return ttCell(p, f, L.short_name || L.name, false);
            }).join('');

            body.push(
                '<tr class="pf-day" data-date="' + ds + '">'
                + '<td class="pf-date"><span class="pf-dow' + (weekend ? ' pf-we' : '') + '">'
                    + DAY_NAMES[dow] + '</span> ' + pad2(day) + '.' + pad2(state.month) + '</td>'
                + ttTds
                + ttCell(pt, ft, 'Итого день', true)
                + '<td class="pf-pct">' + pfPctBadge(dayPct) + '</td>'
                + '</tr>'
                + '<tr class="pf-detail" data-detail="' + ds + '" hidden><td colspan="'
                + (locs.length + 3) + '">' + pfPeople(dayShifts) + '</td></tr>'
            );
        }

        // Итоговый % — факт к плану только дней с фактом (как completion на дашборде)
        var totalPct = (planOfFactDays > 0 && anyFact) ? Math.round(sumFact / planOfFactDays * 100) : null;
        if (sumEl) {
            sumEl.textContent = body.length
                ? (anyFact ? formatMoney(sumFact) : '—') + ' / ' + (anyPlan ? formatMoney(sumPlan) : '—')
                  + (totalPct != null ? ' · ' + totalPct + '%' : '')
                : '';
        }

        if (!body.length) {
            host.innerHTML = '<div class="pf-empty">В этом месяце нет ни планов, ни смен</div>';
            return;
        }

        var headTt = locs.map(function (L) {
            return '<th class="pf-tt" title="' + escapeHtml(L.name) + '">'
                + escapeHtml(L.short_name || L.name) + '</th>';
        }).join('');
        var totalTt = locs.map(function (L) {
            var t = ttSum[L.id];
            return ttCell(t.hasP ? t.p : null, t.hasF ? t.f : null, L.short_name || L.name, true);
        }).join('');
        var totalRow = '<tr class="pf-total"><td>Итого</td>' + totalTt
            + ttCell(anyPlan ? sumPlan : null, anyFact ? sumFact : null, 'Итого месяц', true)
            + '<td class="pf-pct">' + pfPctBadge(totalPct) + '</td></tr>';

        host.innerHTML =
            '<table class="pf-table"><thead><tr>'
            + '<th>Дата</th>' + headTt + '<th class="pf-tt">Итого</th><th class="pf-pct">%</th>'
            + '</tr></thead><tbody>' + body.join('') + totalRow + '</tbody></table>';

        host.querySelectorAll('tr.pf-day').forEach(function (tr) {
            tr.addEventListener('click', function () {
                var detail = host.querySelector('tr.pf-detail[data-detail="' + tr.dataset.date + '"]');
                if (!detail) return;
                detail.hidden = !detail.hidden;
                tr.classList.toggle('open', !detail.hidden);
            });
        });
    }

    /* Мини-виджет «Выполнение плана»: матрица точки × 3 дня (позавчера/вчера/сегодня).
       Ячейка — % выполнения за день по точке (факт/план), цвет по уровню; строка «Все»
       снизу — агрегат. Берёт state.plans отображаемого месяца (даты вне него — «—»).
       Сегодня — последняя колонка (факт неполный, день не закрыт; см. подпись). */
    function renderRecentCompletion(host) {
        if (!host) return;
        var days = state.plans && state.plans.days;
        if (!days) { host.innerHTML = '<div class="cov-empty">Нет данных</div>'; return; }
        var now = new Date();
        var cols = [2, 1, 0].map(function (off) {
            var dt = new Date(now.getFullYear(), now.getMonth(), now.getDate() - off);
            return {
                off: off,
                d: days[dateStr(dt.getFullYear(), dt.getMonth() + 1, dt.getDate())],
                label: pad2(dt.getDate()) + '.' + pad2(dt.getMonth() + 1)
            };
        });

        // Ячейка %: цвет по уровню, «—» если плана/факта нет
        function cell(plan, fact, today) {
            var pct = (plan != null && plan > 0 && fact != null) ? Math.round(fact / plan * 100) : null;
            if (pct == null) return '<td class="rc-c pf-dim">&mdash;</td>';
            var lvl = pct >= 100 ? 'good' : (pct >= 85 ? 'mid' : 'low');
            return '<td class="rc-c rc-' + lvl + (today ? ' rc-today' : '') + '">' + pct + '%</td>';
        }

        var head = '<tr><th></th>' + cols.map(function (c) {
            return '<th class="rc-h' + (c.off === 0 ? ' rc-today' : '') + '">' + c.label + '</th>';
        }).join('') + '</tr>';

        var rows = state.locations.map(function (L) {
            var tds = cols.map(function (c) {
                var loc = (c.d && c.d.locations && c.d.locations[L.id]) || {};
                return cell(loc.plan != null ? loc.plan : null,
                            loc.fact != null ? loc.fact : null, c.off === 0);
            }).join('');
            return '<tr><td class="rc-name" title="' + escapeHtml(L.name) + '">'
                + escapeHtml(L.short_name || L.name) + '</td>' + tds + '</tr>';
        }).join('');

        var totalTds = cols.map(function (c) {
            return cell((c.d && c.d.plan_total != null) ? c.d.plan_total : null,
                        (c.d && c.d.fact_total != null) ? c.d.fact_total : null, c.off === 0);
        }).join('');

        host.innerHTML =
            '<table class="rc-table"><thead>' + head + '</thead><tbody>'
            + rows
            + '<tr class="rc-all"><td class="rc-name">Все</td>' + totalTds + '</tr>'
            + '</tbody></table>'
            + '<div class="rc-cap">позавчера &middot; вчера &middot; сегодня (сегодня &mdash; идёт)</div>';
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

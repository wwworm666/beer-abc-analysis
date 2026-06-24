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

        var badges = [];
        if (shift.start_time) {
            badges.push('<span class="chip-time">с ' + shift.start_time + '</span>');
        }
        if (shift.fact_minutes !== null && shift.fact_minutes !== undefined) {
            badges.push('<span class="chip-fact">' + minutesToHhMm(shift.fact_minutes) + '</span>');
        }

        chip.title = shift.employee_name + ' — ' + shift.role_name
            + (shift.start_time ? ', с ' + shift.start_time : '')
            + (shift.fact_minutes != null
                ? ', факт ' + minutesToHhMm(shift.fact_minutes) : '');
        chip.innerHTML =
            '<span class="chip-name">' + escapeHtml(employeeLabel(shift.employee_name)) + '</span>'
            + (badges.length ? '<span class="chip-badges">' + badges.join('') + '</span>' : '');

        if (onChipClick) {
            chip.addEventListener('click', function (e) {
                e.stopPropagation();
                onChipClick(shift);
            });
        }
        return chip;
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

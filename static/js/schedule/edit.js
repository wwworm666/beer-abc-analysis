/* Страница /schedule/edit — рабочий стол владельца.
   Кисть (сотрудник + пресет времени), ластик, предупреждения,
   панель план/факт дня, нагрузка по людям, сводка месяца, пожелания, реестр. */

(function () {
    'use strict';

    var S = window.Schedule;

    /* Смены двух типов: день (с 14:00, норма — start_time NULL, бейдж не
       показывается) и вечер (с 18:00 — второй бармен по умолчанию, роль
       меняется в модалке). Других времён нет; нестандарт — через модалку. */
    var TIME_PRESETS = [
        { key: 'day', label: 'День (с 14:00)', startTime: null, roleIndex: 0 },
        { key: 'evening', label: 'Вечер (с 18:00)', startTime: '18:00', roleIndex: 1 }
    ];

    var selectedEmployee = null;     // имя выбранного сотрудника (показ/подсказка)
    var selectedEmployeeId = null;   // стабильный id из iiko (v6) — ключ для смен
    var selectedPreset = TIME_PRESETS[0];
    var eraserMode = false;
    var selectedDate = null;
    var editingShiftId = null;
    var wishes = {};
    var wishTimers = {};
    var saving = false; // защита от двойных кликов кисти

    document.addEventListener('DOMContentLoaded', function () {
        document.getElementById('prevMonth').addEventListener('click', function () {
            S.shiftMonth(-1); closeDayPanel(); reload();
        });
        document.getElementById('nextMonth').addEventListener('click', function () {
            S.shiftMonth(1); closeDayPanel(); reload();
        });

        document.getElementById('eraserBtn').addEventListener('click', toggleEraser);
        document.getElementById('shiftForm').addEventListener('submit', onShiftFormSubmit);
        document.getElementById('shiftDelete').addEventListener('click', onShiftDelete);
        document.getElementById('shiftCancel').addEventListener('click', closeShiftModal);
        document.getElementById('empSyncBtn').addEventListener('click', syncEmployees);
        document.getElementById('empAdminToggle').addEventListener('click', function () {
            var body = document.getElementById('empAdminBody');
            body.style.display = body.style.display === 'none' ? '' : 'none';
        });
        document.getElementById('auditToggle').addEventListener('click', function () {
            var body = document.getElementById('auditBody');
            var opening = body.style.display === 'none';
            body.style.display = opening ? '' : 'none';
            if (opening) loadAudit();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                deselectAll();
                closeShiftModal();
            }
        });

        S.showLoading(true);
        S.loadDictionaries()
            .then(function () {
                if (!S.state.employees.length) {
                    // Первый запуск: реестр пуст — наполняем из iiko
                    return S.api('/api/schedule/employees/sync', { method: 'POST' })
                        .then(function () { return S.api('/api/schedule/employees'); })
                        .then(function (emps) { S.state.employees = emps; })
                        .catch(function () { /* iiko недоступен — реестр пополнится позже */ });
                }
            })
            .then(function () {
                renderToolbar();
                renderRoleOptions();
                return loadWishes();
            })
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
        return Promise.all([
            S.loadMonthData(),
            S.api('/api/schedule/plans/' + S.state.year + '/' + S.state.month)
                .then(function (p) { S.state.plans = p; })
        ]).then(function () {
            renderAll();
            return loadSummary();
        }).then(function () {
            return loadAudit();
        }).catch(function (err) {
            console.error(err);
            S.showToast('Ошибка загрузки месяца', true);
        }).then(function () { S.showLoading(false); });
    }

    function renderAll() {
        renderGrid();
        renderWarnings();
        S.renderPlanFact(document.getElementById('planFactBody'));
        S.renderRecentCompletion(document.getElementById('recentBody'));
        renderWishesBoard();
        renderEmployeesAdmin();
        if (selectedDate) renderDayPanel(selectedDate);
    }

    function renderGrid() {
        S.renderGrid({
            gridEl: document.getElementById('scheduleGrid'),
            markHoles: true,
            showPlans: true,
            onChipClick: onChipClick,
            onCellClick: onCellClick,
            onDateClick: toggleDayPanel
        });
    }

    // ==================== Тулбар кисти ====================

    function renderToolbar() {
        var cont = document.getElementById('employeeButtons');
        cont.innerHTML = '';
        S.state.employees.forEach(function (emp) {
            var btn = document.createElement('button');
            btn.className = 'emp-btn';
            btn.textContent = S.employeeLabel(emp.name);
            btn.title = emp.name;
            btn.dataset.empName = emp.name;
            btn.addEventListener('click', function () { selectEmployee(emp); });
            cont.appendChild(btn);
        });
        if (!S.state.employees.length) {
            cont.innerHTML = '<span class="paint-hint">Реестр пуст — нажми «Обновить из iiko» в блоке «Сотрудники»</span>';
        }

        var presetCont = document.getElementById('presetButtons');
        presetCont.innerHTML = '';
        TIME_PRESETS.forEach(function (preset) {
            var btn = document.createElement('button');
            btn.className = 'preset-btn' + (preset === selectedPreset ? ' selected' : '');
            btn.textContent = preset.label;
            btn.dataset.presetKey = preset.key;
            btn.addEventListener('click', function () { selectPreset(preset); });
            presetCont.appendChild(btn);
        });
    }

    function selectEmployee(emp) {
        if (selectedEmployee === emp.name) { deselectAll(); return; }
        selectedEmployee = emp.name;
        selectedEmployeeId = emp.id || null;
        eraserMode = false;
        document.querySelectorAll('.emp-btn').forEach(function (btn) {
            btn.classList.toggle('selected', btn.dataset.empName === emp.name);
        });
        document.getElementById('eraserBtn').classList.remove('selected');
        document.body.classList.add('paint-mode');
        document.body.classList.remove('eraser-mode');
        updateHint();
    }

    function selectPreset(preset) {
        selectedPreset = preset;
        document.querySelectorAll('.preset-btn').forEach(function (btn) {
            btn.classList.toggle('selected', btn.dataset.presetKey === preset.key);
        });
        updateHint();
    }

    function toggleEraser() {
        if (eraserMode) { deselectAll(); return; }
        eraserMode = true;
        selectedEmployee = null;
        document.querySelectorAll('.emp-btn').forEach(function (b) { b.classList.remove('selected'); });
        document.getElementById('eraserBtn').classList.add('selected');
        document.body.classList.remove('paint-mode');
        document.body.classList.add('eraser-mode');
        document.getElementById('paintHint').textContent = 'Ластик: кликай по сменам';
    }

    function deselectAll() {
        selectedEmployee = null;
        selectedEmployeeId = null;
        eraserMode = false;
        document.querySelectorAll('.emp-btn').forEach(function (b) { b.classList.remove('selected'); });
        document.getElementById('eraserBtn').classList.remove('selected');
        document.body.classList.remove('paint-mode', 'eraser-mode');
        document.getElementById('paintHint').textContent =
            'Выбери сотрудника и время, потом кликай по ячейкам';
    }

    function updateHint() {
        if (!selectedEmployee) return;
        var hint = S.employeeLabel(selectedEmployee) + ' / ' + selectedPreset.label
            + ' — кликай по ячейкам.';
        var wish = wishes[selectedEmployee];
        var el = document.getElementById('paintHint');
        el.innerHTML = '';
        el.appendChild(document.createTextNode(hint + ' '));
        if (wish) {
            var span = document.createElement('span');
            span.className = 'hint-wish';
            span.textContent = 'Пожелание: ' + wish;
            el.appendChild(span);
        }
    }

    // ==================== Кисть: клики по сетке ====================

    function roleForPreset(preset) {
        var roles = S.state.roles; // отсортированы по sort_order
        var idx = Math.min(preset.roleIndex, roles.length - 1);
        return roles[idx];
    }

    function onCellClick(ds, locationId, cellShifts) {
        if (!selectedEmployee || saving) return;

        var existing = cellShifts.find(function (s) {
            return selectedEmployeeId
                ? s.employee_id === selectedEmployeeId
                : s.employee_name === selectedEmployee;
        });

        var action;
        if (existing) {
            action = S.api('/api/schedule/shift/' + existing.id, { method: 'DELETE' })
                .then(function () { S.showToast('Удалено'); });
        } else {
            var dayOffEmps = S.getDayOffEmployees(ds);
            if (dayOffEmps.indexOf(selectedEmployee) !== -1) {
                var okGo = confirm(selectedEmployee + ' просил выходной на '
                    + S.formatDateHuman(ds) + '. Всё равно назначить?');
                if (!okGo) return;
            }
            var role = roleForPreset(selectedPreset);
            action = S.api('/api/schedule/shift', {
                method: 'POST',
                body: {
                    date: ds,
                    employee_name: selectedEmployee,
                    employee_id: selectedEmployeeId,
                    location_id: locationId,
                    role_id: role.id,
                    start_time: selectedPreset.startTime
                }
            }).then(function () { S.showToast('Назначено'); });
        }

        saving = true;
        action
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { saving = false; return reload(); });
    }

    function onChipClick(shift) {
        if (eraserMode) {
            if (saving) return;
            saving = true;
            S.api('/api/schedule/shift/' + shift.id, { method: 'DELETE' })
                .then(function () { S.showToast('Удалено'); })
                .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
                .then(function () { saving = false; return reload(); });
            return;
        }
        if (selectedEmployee) return; // в режиме кисти клики по чипам игнорируются
        openShiftModal(shift);
    }

    // ==================== Модалка смены ====================

    function renderRoleOptions() {
        var sel = document.getElementById('shiftRole');
        sel.innerHTML = S.state.roles.map(function (r) {
            return '<option value="' + r.id + '">' + r.name + '</option>';
        }).join('');
    }

    function openShiftModal(shift) {
        editingShiftId = shift.id;
        document.getElementById('shiftModalTitle').textContent =
            shift.employee_name + ' — ' + S.formatDateHuman(shift.date);
        document.getElementById('shiftRole').value = shift.role_id;
        document.getElementById('shiftStartTime').value = shift.start_time || '';

        var dayOffEmps = S.getDayOffEmployees(shift.date);
        document.getElementById('dayoffWarning').style.display =
            dayOffEmps.indexOf(shift.employee_name) !== -1 ? 'block' : 'none';

        document.getElementById('shiftModal').classList.add('active');
    }

    function closeShiftModal() {
        document.getElementById('shiftModal').classList.remove('active');
        editingShiftId = null;
    }

    function onShiftFormSubmit(e) {
        e.preventDefault();
        if (!editingShiftId) return;
        var startTime = document.getElementById('shiftStartTime').value.trim() || null;
        S.api('/api/schedule/shift/' + editingShiftId, {
            method: 'PUT',
            body: {
                role_id: parseInt(document.getElementById('shiftRole').value, 10),
                start_time: startTime
            }
        }).then(function () {
            closeShiftModal();
            S.showToast('Сохранено');
            reload();
        }).catch(function (err) {
            S.showToast('Ошибка: ' + err.message, true);
        });
    }

    function onShiftDelete() {
        if (!editingShiftId) return;
        S.api('/api/schedule/shift/' + editingShiftId, { method: 'DELETE' })
            .then(function () {
                closeShiftModal();
                S.showToast('Удалено');
                reload();
            })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); });
    }

    // ==================== Предупреждения ====================

    function renderWarnings() {
        var row = document.getElementById('warningsRow');
        row.innerHTML = '';
        var today = S.todayStr();
        var daysInMonth = new Date(S.state.year, S.state.month, 0).getDate();

        // Дыры: будущие даты (включая сегодня), точка без единой смены
        var holes = [];
        for (var day = 1; day <= daysInMonth; day++) {
            var ds = S.dateStr(S.state.year, S.state.month, day);
            if (ds < today) continue;
            S.state.locations.forEach(function (loc) {
                var has = S.state.shifts.some(function (s) {
                    return s.date === ds && s.location_id === loc.id;
                });
                if (!has) holes.push({ date: ds, loc: loc });
            });
        }

        // Конфликты: смена в день, на который сотрудник просил выходной
        var conflicts = S.state.shifts.filter(function (s) {
            return S.getDayOffEmployees(s.date).indexOf(s.employee_name) !== -1;
        });

        if (holes.length) {
            var holeItem = document.createElement('span');
            holeItem.className = 'warning-item';
            var preview = holes.slice(0, 4).map(function (h) {
                return parseInt(h.date.slice(8), 10) + ' ' + (h.loc.short_name || h.loc.name);
            }).join(', ');
            holeItem.textContent = 'Не закрыто: ' + holes.length
                + ' (' + preview + (holes.length > 4 ? ', ...' : '') + ')';
            holeItem.addEventListener('click', function () { scrollToCell(holes[0].date, holes[0].loc.id); });
            row.appendChild(holeItem);
        }

        if (conflicts.length) {
            var confItem = document.createElement('span');
            confItem.className = 'warning-item danger';
            confItem.textContent = 'Конфликты с выходными: ' + conflicts.length
                + ' (' + conflicts.slice(0, 3).map(function (c) {
                    return S.employeeLabel(c.employee_name) + ' ' + parseInt(c.date.slice(8), 10);
                }).join(', ') + (conflicts.length > 3 ? ', ...' : '') + ')';
            confItem.addEventListener('click', function () {
                scrollToCell(conflicts[0].date, conflicts[0].location_id);
            });
            row.appendChild(confItem);
        }
    }

    function scrollToCell(ds, locationId) {
        var cell = document.querySelector(
            '.shift-cell[data-date="' + ds + '"][data-location-id="' + locationId + '"]');
        if (cell) {
            cell.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    // ==================== Панель дня (план/факт) ====================

    function toggleDayPanel(ds) {
        if (selectedEmployee || eraserMode) return;
        var panel = document.getElementById('dayPanel');
        if (selectedDate === ds && panel.classList.contains('active')) {
            closeDayPanel();
        } else {
            selectedDate = ds;
            renderDayPanel(ds);
            panel.classList.add('active');
        }
    }

    function closeDayPanel() {
        selectedDate = null;
        document.getElementById('dayPanel').classList.remove('active');
    }

    function renderDayPanel(ds) {
        document.getElementById('dayPanelDate').textContent = S.formatDateHuman(ds);
        var grid = document.getElementById('dayPanelGrid');
        var dayData = (S.state.plans && S.state.plans.days[ds]) || { locations: {} };
        var planFormula = S.state.plans ? S.state.plans.plan_formula : '';

        grid.innerHTML = S.state.locations.map(function (loc) {
            var cell = dayData.locations[loc.id] || {};
            var planHtml, sourceHtml = '';
            if (cell.plan != null) {
                planHtml = '<span class="v" title="' + planFormula + '">'
                    + S.formatMoney(cell.plan) + '</span>';
                if (cell.plan_source === 'manual') {
                    sourceHtml = '<div class="plan-source">ручной план (устар.)</div>';
                } else {
                    sourceHtml = '<div class="plan-source">из весов дней</div>';
                }
            } else {
                planHtml = '<span class="v empty">нет плана</span>';
            }
            var factHtml = cell.fact != null
                ? '<span class="v fact">' + S.formatMoney(cell.fact) + '</span>'
                : '<span class="v empty">нет данных</span>';

            return '<div class="day-panel-card">'
                + '<div class="location">' + S.escapeHtml(loc.name) + '</div>'
                + '<div class="metric"><span class="k">План</span>' + planHtml + '</div>'
                + '<div class="metric"><span class="k">Факт</span>' + factHtml + '</div>'
                + sourceHtml
                + '</div>';
        }).join('');
    }

    // ==================== Виджет «Нагрузка» ====================
    // Money-free, общий с просмотром (Schedule.renderLoad). Данные — /widgets
    // (без iiko). Денежная «План/Факт по дням» рендерится отдельно (renderPlanFact)
    // из уже загруженного S.state.plans — без отдельного запроса.

    function loadSummary() {
        return S.api('/api/schedule/widgets/' + S.state.year + '/' + S.state.month)
            .then(function (w) {
                S.renderLoad(document.getElementById('loadTableBody'),
                             w.employees_load || [], w.shift_norm || 15);
            });
    }

    // Виджет «План / Факт по дням» (деньги): рендер — общий S.renderPlanFact
    // (в common.js), читает S.state.plans (/plans) + S.state.shifts. Тот же
    // виджет дублируется на страницу просмотра.

    // ==================== Пожелания ====================

    function loadWishes() {
        return S.api('/api/schedule/wishes').then(function (data) {
            wishes = {};
            data.forEach(function (w) { wishes[w.employee_name] = w.text; });
        }).catch(function () { wishes = {}; });
    }

    function renderWishesBoard() {
        var grid = document.getElementById('wishesGrid');
        grid.innerHTML = '';
        S.state.employees.forEach(function (emp) {
            var card = document.createElement('div');
            card.className = 'wish-card';
            var name = document.createElement('div');
            name.className = 'emp-name';
            name.textContent = S.employeeLabel(emp.name) + ' ' + S.employeeShortName(emp.name);
            var ta = document.createElement('textarea');
            ta.placeholder = '2,3 выходной\nбез понедельников';
            ta.value = wishes[emp.name] || '';
            ta.addEventListener('input', function () { saveWish(emp.name, ta.value); });
            card.appendChild(name);
            card.appendChild(ta);
            grid.appendChild(card);
        });
    }

    function saveWish(empName, text) {
        clearTimeout(wishTimers[empName]);
        wishTimers[empName] = setTimeout(function () {
            S.api('/api/schedule/wishes', {
                method: 'POST',
                body: { employee_name: empName, text: text }
            }).then(function () {
                wishes[empName] = text;
                if (selectedEmployee === empName) updateHint();
            }).catch(function () { S.showToast('Пожелание не сохранилось', true); });
        }, 500);
    }

    // ==================== Журнал изменений ====================
    // Кто что менял в графике (смены, факт часов, выходные) за выбранный месяц.
    // Грузим только когда панель раскрыта, и обновляем на каждом reload (после
    // любого изменения и при смене месяца).

    function loadAudit() {
        var body = document.getElementById('auditBody');
        if (!body || body.style.display === 'none') return; // панель скрыта — не дёргаем API
        return S.api('/api/schedule/audit/' + S.state.year + '/' + S.state.month + '?limit=200')
            .then(renderAudit)
            .catch(function () {
                document.getElementById('auditList').innerHTML =
                    '<div class="audit-empty">Не удалось загрузить историю</div>';
            });
    }

    function renderAudit(rows) {
        var list = document.getElementById('auditList');
        if (!rows || !rows.length) {
            list.innerHTML = '<div class="audit-empty">Изменений за этот месяц пока нет</div>';
            return;
        }
        list.innerHTML = rows.map(function (r) {
            return '<div class="audit-row">'
                + '<span class="audit-when">' + S.escapeHtml(S.formatAuditTs(r.ts)) + '</span>'
                + '<span class="audit-who">' + S.escapeHtml(r.actor_name || '—') + '</span>'
                + '<span class="audit-what">' + S.escapeHtml(r.summary) + '</span>'
                + '</div>';
        }).join('');
    }

    // ==================== Реестр сотрудников ====================

    function renderEmployeesAdmin() {
        S.api('/api/schedule/employees?all=1').then(function (allEmps) {
            var tbody = document.getElementById('empAdminBody').querySelector('tbody');
            tbody.innerHTML = '';
            allEmps.forEach(function (emp) {
                var tr = document.createElement('tr');
                if (!emp.active) tr.className = 'inactive-row';

                var tdName = document.createElement('td');
                tdName.textContent = emp.name;

                var tdLabel = document.createElement('td');
                var labelInput = document.createElement('input');
                labelInput.type = 'text';
                labelInput.maxLength = 4;
                labelInput.value = emp.short_label || '';
                labelInput.placeholder = S.employeeLabel(emp.name);
                labelInput.addEventListener('change', function () {
                    updateEmployee(emp.id, { short_label: labelInput.value });
                });
                tdLabel.appendChild(labelInput);

                var tdOrder = document.createElement('td');
                var orderInput = document.createElement('input');
                orderInput.type = 'number';
                orderInput.value = emp.sort_order != null ? emp.sort_order : 0;
                orderInput.addEventListener('change', function () {
                    updateEmployee(emp.id, { sort_order: parseInt(orderInput.value, 10) || 0 });
                });
                tdOrder.appendChild(orderInput);

                var tdActive = document.createElement('td');
                var activeInput = document.createElement('input');
                activeInput.type = 'checkbox';
                activeInput.checked = !!emp.active;
                activeInput.addEventListener('change', function () {
                    updateEmployee(emp.id, { active: activeInput.checked ? 1 : 0 });
                });
                tdActive.appendChild(activeInput);

                tr.appendChild(tdName);
                tr.appendChild(tdLabel);
                tr.appendChild(tdOrder);
                tr.appendChild(tdActive);
                tbody.appendChild(tr);
            });
        });
    }

    function updateEmployee(empId, fields) {
        if (!empId) {
            S.showToast('Сотрудник ещё не привязан к iiko — нажми «Обновить из iiko»', true);
            return;
        }
        S.api('/api/schedule/employee/' + encodeURIComponent(empId), {
            method: 'PUT',
            body: fields
        }).then(function () {
            return S.api('/api/schedule/employees');
        }).then(function (emps) {
            S.state.employees = emps;
            renderToolbar();
            renderAll();
            S.showToast('Сотрудник обновлён');
        }).catch(function (err) { S.showToast('Ошибка: ' + err.message, true); });
    }

    function syncEmployees() {
        var btn = document.getElementById('empSyncBtn');
        btn.disabled = true;
        S.api('/api/schedule/employees/sync', { method: 'POST' })
            .then(function (res) {
                var msg = 'iiko: добавлено ' + res.added + ', привязано смен '
                    + res.shifts_backfilled + ', убрано дублей ' + res.legacy_removed;
                var unmatched = res.unmatched || [];
                if (unmatched.length) {
                    msg += '. Не привязаны: '
                        + unmatched.map(function (u) { return u.name; }).join(', ');
                }
                S.showToast(msg, unmatched.length > 0);
                return S.api('/api/schedule/employees');
            })
            .then(function (emps) {
                S.state.employees = emps;
                renderToolbar();
                renderAll();
            })
            .catch(function (err) { S.showToast('Ошибка iiko: ' + err.message, true); })
            .then(function () { btn.disabled = false; });
    }
})();

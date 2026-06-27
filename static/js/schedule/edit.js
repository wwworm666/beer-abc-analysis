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

    // Кисть «полос по людям»: выбираем ТОЧКУ (бар) + день/вечер, затем кликаем по
    // клетке «сотрудник × день». Сотрудник берётся из строки клетки (не из кисти).
    var brushPoint = null;           // location_id активной точки
    var brushRole = 'day';           // 'day' | 'evening'
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
        document.getElementById('timeSeg').addEventListener('click', function (e) {
            var b = e.target.closest('[data-role]');
            if (b) setRole(b.dataset.role);
        });
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
        document.getElementById('planFactToggle').addEventListener('click', function () {
            var body = document.getElementById('planFactCollapse');
            body.style.display = body.style.display === 'none' ? '' : 'none';
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeShiftModal();
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
                updateHint();
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
        S.renderEditLanes(document.getElementById('scheduleGrid'), {
            onCell: onCell,
            onDayHeaderClick: toggleDayPanel,
            brushColor: eraserMode ? null : S.colorById(brushPoint)
        });
    }

    // ==================== Тулбар кисти ====================

    // Тулбар: чипы точек (бар) + сегмент день/вечер + ластик. Перерисовывает
    // активные состояния по brushPoint/brushRole/eraserMode на каждом вызове.
    function renderToolbar() {
        var pc = document.getElementById('pointChips');
        pc.innerHTML = '';
        if (!brushPoint && S.state.locations.length) brushPoint = S.state.locations[0].id;
        S.state.locations.forEach(function (loc, i) {
            var active = !eraserMode && brushPoint === loc.id;
            var color = S.venueColor(loc, i);
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'el-chip' + (active ? ' selected' : '');
            chip.dataset.locId = loc.id;
            chip.innerHTML = '<span class="el-chipdot"></span>'
                + S.escapeHtml(loc.short_name || loc.name);
            var dot = chip.querySelector('.el-chipdot');
            if (active) {
                chip.style.background = color;
                chip.style.borderColor = color;
                chip.style.color = '#fff';
                dot.style.background = 'rgba(255,255,255,.85)';
            } else {
                dot.style.background = color;
            }
            chip.addEventListener('click', function () { selectPoint(loc.id); });
            pc.appendChild(chip);
        });
        if (!S.state.locations.length) {
            pc.innerHTML = '<span class="paint-hint">Нет точек</span>';
        }

        document.querySelectorAll('#timeSeg .el-seg').forEach(function (b) {
            b.classList.toggle('selected', !eraserMode && b.dataset.role === brushRole);
        });
        document.getElementById('eraserBtn').classList.toggle('selected', eraserMode);
        document.body.classList.toggle('eraser-mode', eraserMode);
        document.body.classList.toggle('paint-mode', !eraserMode);
    }

    function selectPoint(locId) {
        brushPoint = locId;
        eraserMode = false;
        renderToolbar();
        renderGrid();      // обновить подсветку наведения цветом точки
        updateHint();
    }

    function setRole(role) {
        brushRole = role === 'evening' ? 'evening' : 'day';
        eraserMode = false;
        renderToolbar();
        updateHint();
    }

    function toggleEraser() {
        eraserMode = !eraserMode;
        renderToolbar();
        renderGrid();
        updateHint();
    }

    function presetForBrush() {
        return brushRole === 'evening' ? TIME_PRESETS[1] : TIME_PRESETS[0];
    }

    function updateHint() {
        var el = document.getElementById('paintHint');
        if (eraserMode) {
            el.textContent = 'Ластик: кликай по сменам, чтобы убрать';
            return;
        }
        var loc = S.state.locations.filter(function (l) { return l.id === brushPoint; })[0];
        var name = loc ? (loc.short_name || loc.name) : '—';
        el.textContent = 'Кисть: ' + name + ' · ' + (brushRole === 'evening' ? 'вечер' : 'день')
            + ' — кликай по клеткам «сотрудник × день»';
    }

    // ==================== Кисть: клики по сетке ====================

    function roleForPreset(preset) {
        var roles = S.state.roles; // отсортированы по sort_order
        var idx = Math.min(preset.roleIndex, roles.length - 1);
        return roles[idx];
    }

    // Клик по клетке «сотрудник × день». existing — отображаемая смена клетки
    // (или null). Ластик снимает; кисть на пустой — назначает; на занятой:
    // та же точка+роль — модалка тонкой правки, иначе — перекраска (снять+создать).
    function onCell(emp, day, ds, existing) {
        if (saving) return;
        if (eraserMode) {
            if (existing) deleteShift(existing.id);
            return;
        }
        if (existing) {
            var sameRole = (S.isEvening(existing) ? 'evening' : 'day') === brushRole;
            var samePoint = existing.location_id === brushPoint;
            if (samePoint && sameRole) { openShiftModal(existing); return; }
            replaceShift(existing, emp, ds);
            return;
        }
        createShift(emp, ds);
    }

    function confirmDayOff(emp, ds) {
        if (S.getDayOffEmployees(ds).indexOf(emp.name) === -1) return true;
        return confirm(emp.name + ' просил выходной на ' + S.formatDateHuman(ds)
            + '. Всё равно назначить?');
    }

    function postBody(emp, ds) {
        var preset = presetForBrush();
        var role = roleForPreset(preset);
        return {
            date: ds, employee_name: emp.name, employee_id: emp.id || null,
            location_id: brushPoint, role_id: role.id, start_time: preset.startTime
        };
    }

    function createShift(emp, ds) {
        if (!confirmDayOff(emp, ds)) return;
        saving = true;
        S.api('/api/schedule/shift', { method: 'POST', body: postBody(emp, ds) })
            .then(function () { S.showToast('Назначено'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { saving = false; return reload(); });
    }

    function replaceShift(existing, emp, ds) {
        if (!confirmDayOff(emp, ds)) return;
        saving = true;
        S.api('/api/schedule/shift/' + existing.id, { method: 'DELETE' })
            .then(function () { return S.api('/api/schedule/shift', { method: 'POST', body: postBody(emp, ds) }); })
            .then(function () { S.showToast('Перекрашено'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { saving = false; return reload(); });
    }

    function deleteShift(id) {
        saving = true;
        S.api('/api/schedule/shift/' + id, { method: 'DELETE' })
            .then(function () { S.showToast('Удалено'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { saving = false; return reload(); });
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

/* Страница /schedule — единый экран графика: просмотр + редактирование.
   «Полосы по людям» редактируемые: кисть назначает смены (точка + день/вечер),
   режим «Выходной» ставит/снимает выходной прямо в графике (смена этого дня
   снимается), ластик — снять смену. Клик по своей смене активной кистью —
   модалка (роль/время/факт). Мобильный «Мои смены» — личный: ввод факта и
   запрос выходного на выбранный день. Бывшая /schedule/edit слита сюда. */

(function () {
    'use strict';

    var S = window.Schedule;

    // День (норма — start_time NULL) и вечер (с 18:00, второй бармен). Нестандарт —
    // через модалку смены (произвольное время начала).
    var TIME_PRESETS = [
        { key: 'day', label: 'День (с 14:00)', startTime: null, roleIndex: 0 },
        { key: 'evening', label: 'Вечер (с 18:00)', startTime: '18:00', roleIndex: 1 }
    ];

    // Кисть «полос по людям»
    var brushPoint = null;        // location_id активной точки
    var brushRole = 'day';        // 'day' | 'evening'
    var brushMode = 'point';      // 'point' | 'eraser' | 'dayoff'

    var selectedDate = null;      // открытая денежная панель дня
    var editingShiftId = null;    // модалка смены (десктоп)
    var currentFactShift = null;  // модалка факта (мобильный)
    var wishes = {};
    var wishTimers = {};
    var saving = false;           // защита от двойных кликов

    document.addEventListener('DOMContentLoaded', function () {
        document.getElementById('prevMonth').addEventListener('click', function () {
            S.shiftMonth(-1); closeDayPanel(); reload();
        });
        document.getElementById('nextMonth').addEventListener('click', function () {
            S.shiftMonth(1); closeDayPanel(); reload();
        });

        document.getElementById('timeSeg').addEventListener('click', function (e) {
            var b = e.target.closest('[data-role]'); if (b) setRole(b.dataset.role);
        });
        document.getElementById('dayoffBtn').addEventListener('click', toggleDayoffBrush);
        document.getElementById('eraserBtn').addEventListener('click', toggleEraser);

        // План/Факт — кнопка в виджете «Сегодня вживую» (панель под бордом)
        document.getElementById('planFactToggle').addEventListener('click', function () {
            var panel = document.getElementById('planFactPanel');
            var open = panel.style.display === 'none';
            panel.style.display = open ? '' : 'none';
            this.classList.toggle('is-open', open);
        });
        // Единые сворачиваемые блоки (Пожелания / Сотрудники / Последние изменения)
        document.querySelectorAll('[data-fold-toggle]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var fold = btn.closest('.sc-fold');
                var body = fold.querySelector('.sc-fold-body');
                var open = body.hasAttribute('hidden');
                if (open) body.removeAttribute('hidden'); else body.setAttribute('hidden', '');
                fold.classList.toggle('is-open', open);
            });
        });
        document.getElementById('empSyncBtn').addEventListener('click', syncEmployees);

        // модалка смены (десктоп)
        document.getElementById('shiftForm').addEventListener('submit', onShiftFormSubmit);
        document.getElementById('shiftDelete').addEventListener('click', onShiftDelete);
        document.getElementById('shiftCancel').addEventListener('click', closeShiftModal);
        // модалка факта (мобильный)
        document.getElementById('factForm').addEventListener('submit', onFactSubmit);
        document.getElementById('factClear').addEventListener('click', onFactClear);
        document.getElementById('factCancel').addEventListener('click', closeFactModal);

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { closeShiftModal(); closeFactModal(); }
        });

        S.showLoading(true);
        S.loadDictionaries()
            .then(function () {
                if (!S.state.employees.length) {
                    // Первый запуск: реестр пуст — наполняем из iiko
                    return S.api('/api/schedule/employees/sync', { method: 'POST' })
                        .then(function () { return S.api('/api/schedule/employees'); })
                        .then(function (emps) { S.state.employees = emps; })
                        .catch(function () { /* iiko недоступен — пополнится позже */ });
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
                .catch(function (err) { console.error(err); S.state.plans = null; })
        ]).then(renderAll)
            .then(loadFeed)
            .catch(function (err) {
                console.error(err);
                S.showToast('Ошибка загрузки месяца', true);
            })
            .then(function () { S.showLoading(false); });
    }

    function renderAll() {
        // мобильный личный экран (ввод факта + запрос выходного)
        S.setScreenShiftClick(openFactModal);
        var emp = (document.body.dataset.empIiko || '').trim();
        S.renderMyShifts(document.getElementById('myShifts'),
            { employeeIikoId: emp || null, icsHref: emp ? '/schedule/cal.ics' : null,
              onDayOffToggle: onMobileDayOffToggle });
        // десктоп
        S.renderTodayBoard(document.getElementById('todayBoard'));
        renderLanes();
        S.renderLegend(document.getElementById('legend'));
        S.renderPlanFact(document.getElementById('planFactBody'));
        renderWishesBoard();
        renderEmployeesAdmin();
        if (selectedDate) renderDayPanel(selectedDate);
    }

    function renderLanes() {
        S.renderEditLanes(document.getElementById('lanes'), {
            onCell: onCell,
            onDayHeaderClick: toggleDayPanel,
            brushColor: brushMode === 'point' ? S.colorById(brushPoint)
                : (brushMode === 'dayoff' ? '#b0a99d' : null)
        });
    }

    // ==================== Тулбар кисти ====================

    function renderToolbar() {
        var pc = document.getElementById('pointChips');
        pc.innerHTML = '';
        if (!brushPoint && S.state.locations.length) brushPoint = S.state.locations[0].id;
        S.state.locations.forEach(function (loc, i) {
            var active = brushMode === 'point' && brushPoint === loc.id;
            var color = S.venueColor(loc, i);
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'el-chip' + (active ? ' selected' : '');
            chip.innerHTML = '<span class="el-chipdot"></span>'
                + S.escapeHtml(loc.short_name || loc.name);
            var dot = chip.querySelector('.el-chipdot');
            if (active) {
                chip.style.background = color; chip.style.borderColor = color;
                chip.style.color = '#fff'; dot.style.background = 'rgba(255,255,255,.85)';
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
            b.classList.toggle('selected', brushMode === 'point' && b.dataset.role === brushRole);
        });
        document.getElementById('dayoffBtn').classList.toggle('selected', brushMode === 'dayoff');
        document.getElementById('eraserBtn').classList.toggle('selected', brushMode === 'eraser');
        document.body.classList.toggle('eraser-mode', brushMode === 'eraser');
        document.body.classList.toggle('paint-mode', brushMode !== 'eraser');
    }

    function selectPoint(locId) { brushPoint = locId; brushMode = 'point'; renderToolbar(); renderLanes(); updateHint(); }
    function setRole(role) { brushRole = role === 'evening' ? 'evening' : 'day'; brushMode = 'point'; renderToolbar(); renderLanes(); updateHint(); }
    function toggleDayoffBrush() { brushMode = brushMode === 'dayoff' ? 'point' : 'dayoff'; renderToolbar(); renderLanes(); updateHint(); }
    function toggleEraser() { brushMode = brushMode === 'eraser' ? 'point' : 'eraser'; renderToolbar(); renderLanes(); updateHint(); }

    function updateHint() {
        var el = document.getElementById('paintHint');
        if (brushMode === 'eraser') { el.textContent = 'Ластик: клик по смене — снять'; return; }
        if (brushMode === 'dayoff') { el.textContent = 'Выходной: клик по клетке — поставить/снять (смена этого дня снимается)'; return; }
        var loc = S.state.locations.filter(function (l) { return l.id === brushPoint; })[0];
        var name = loc ? (loc.short_name || loc.name) : '—';
        el.textContent = 'Кисть: ' + name + ' · ' + (brushRole === 'evening' ? 'вечер' : 'день')
            + ' — клик по клетке «сотрудник × день»';
    }

    function roleForPreset(preset) {
        var roles = S.state.roles;
        var idx = Math.min(preset.roleIndex, roles.length - 1);
        return roles[idx];
    }
    function presetForBrush() { return brushRole === 'evening' ? TIME_PRESETS[1] : TIME_PRESETS[0]; }

    // ==================== Клик по клетке ====================

    function onCell(emp, day, ds, existing) {
        if (saving) return;
        if (brushMode === 'eraser') { if (existing) deleteShift(existing.id); return; }
        if (brushMode === 'dayoff') { toggleDayOff(emp, ds, existing); return; }
        // point
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
        var preset = presetForBrush(), role = roleForPreset(preset);
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

    // ==================== Выходные ====================
    // dayOffs хранятся диапазонами; кисть/кнопка работают однодневными запросами.

    function dayOffRequestFor(empName, ds) {
        return (S.state.dayOffs || []).filter(function (r) {
            return r.employee_name === empName && ds >= r.date_from && ds <= r.date_to;
        })[0];
    }

    // Десктоп: клик кистью «Выходной». Если выходной есть — снять; иначе поставить,
    // а смену этого дня (если есть) снять (решение владельца).
    function toggleDayOff(emp, ds, existing) {
        var req = dayOffRequestFor(emp.name, ds);
        if (req) {
            saving = true;
            S.api('/api/schedule/dayoff/' + req.id, { method: 'DELETE' })
                .then(function () { S.showToast('Выходной снят'); })
                .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
                .then(function () { saving = false; return reload(); });
            return;
        }
        saving = true;
        var chain = existing
            ? S.api('/api/schedule/shift/' + existing.id, { method: 'DELETE' })
            : Promise.resolve();
        chain
            .then(function () {
                return S.api('/api/schedule/dayoff', { method: 'POST',
                    body: { employee_name: emp.name, date_from: ds, date_to: ds } });
            })
            .then(function () { S.showToast(existing ? 'Выходной (смена снята)' : 'Выходной поставлен'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { saving = false; return reload(); });
    }

    // Мобильный: бармен запрашивает/снимает выходной на выбранный день. Это
    // ЗАЯВКА — смену не трогаем (конфликт увидит и разрулит владелец).
    function onMobileDayOffToggle(empName, ds, isOff) {
        if (saving) return;
        if (isOff) {
            var req = dayOffRequestFor(empName, ds);
            if (!req) return;
            saving = true;
            S.api('/api/schedule/dayoff/' + req.id, { method: 'DELETE' })
                .then(function () { S.showToast('Выходной отменён'); })
                .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
                .then(function () { saving = false; return reload(); });
        } else {
            saving = true;
            S.api('/api/schedule/dayoff', { method: 'POST',
                body: { employee_name: empName, date_from: ds, date_to: ds } })
                .then(function () { S.showToast('Выходной запрошен'); })
                .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
                .then(function () { saving = false; return reload(); });
        }
    }

    // ==================== Модалка смены (десктоп) ====================
    // Роль + плановое время + факт часов (владелец может править факт здесь).

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
        document.getElementById('shiftFact').value =
            shift.fact_minutes != null ? S.minutesToHhMm(shift.fact_minutes) : '';
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
        var roleId = parseInt(document.getElementById('shiftRole').value, 10);
        var factRaw = document.getElementById('shiftFact').value.trim();
        var factMin = null;
        if (factRaw) {
            factMin = S.parseHoursInput(factRaw);
            if (factMin === null || factMin < 0 || factMin > 1440) {
                S.showToast('Факт: введи часы как 10:30 или 10.5', true); return;
            }
        }
        var id = editingShiftId;
        S.api('/api/schedule/shift/' + id, { method: 'PUT', body: { role_id: roleId, start_time: startTime } })
            .then(function () { return S.api('/api/schedule/shift/' + id + '/fact', { method: 'PUT', body: { fact_minutes: factMin } }); })
            .then(function () { closeShiftModal(); S.showToast('Сохранено'); reload(); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); });
    }
    function onShiftDelete() {
        if (!editingShiftId) return;
        S.api('/api/schedule/shift/' + editingShiftId, { method: 'DELETE' })
            .then(function () { closeShiftModal(); S.showToast('Удалено'); reload(); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); });
    }

    // ==================== Модалка факта (мобильный) ====================

    function openFactModal(shift) {
        currentFactShift = shift;
        document.getElementById('factModalTitle').textContent =
            shift.employee_name + ' — ' + S.formatDateHuman(shift.date) + ' — ' + shift.location_name;
        var input = document.getElementById('factInput');
        input.value = shift.fact_minutes != null ? S.minutesToHhMm(shift.fact_minutes) : '';
        document.getElementById('factModal').classList.add('active');
        input.focus();
    }
    function closeFactModal() {
        document.getElementById('factModal').classList.remove('active');
        currentFactShift = null;
    }
    function onFactSubmit(e) {
        e.preventDefault();
        if (!currentFactShift) return;
        var minutes = S.parseHoursInput(document.getElementById('factInput').value);
        if (minutes === null || minutes < 0 || minutes > 1440) {
            S.showToast('Введи часы как 10:30 или 10.5', true); return;
        }
        S.api('/api/schedule/shift/' + currentFactShift.id + '/fact', { method: 'PUT', body: { fact_minutes: minutes } })
            .then(function () { closeFactModal(); S.showToast('Часы сохранены'); reload(); })
            .catch(function (err) { S.showToast('Не сохранилось: ' + err.message, true); });
    }
    function onFactClear() {
        if (!currentFactShift) return;
        S.api('/api/schedule/shift/' + currentFactShift.id + '/fact', { method: 'PUT', body: { fact_minutes: null } })
            .then(function () { closeFactModal(); S.showToast('Часы очищены'); reload(); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); });
    }

    // ==================== Денежная панель дня ====================
    // Открывается кликом по номеру дня в шапке полос. План — из весов дней,
    // факт — живой iiko OLAP. Деньги только тут (наружу барменам не идут).

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
                planHtml = '<span class="v" title="' + planFormula + '">' + S.formatMoney(cell.plan) + '</span>';
                sourceHtml = cell.plan_source === 'manual'
                    ? '<div class="plan-source">ручной план (устар.)</div>'
                    : '<div class="plan-source">из весов дней</div>';
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
                + sourceHtml + '</div>';
        }).join('');
    }

    // ==================== Пожелания (редактируемые) ====================

    function loadWishes() {
        return S.api('/api/schedule/wishes').then(function (data) {
            wishes = {};
            data.forEach(function (w) { wishes[w.employee_name] = w.text; });
        }).catch(function () { wishes = {}; });
    }
    // Тизер свёрнутого блока — короткая подпись «что внутри».
    function setTeaser(id, text) {
        var el = document.getElementById(id); if (el) el.textContent = text;
    }

    function renderWishesBoard() {
        var grid = document.getElementById('wishesGrid');
        grid.innerHTML = '';
        var filled = S.state.employees.filter(function (e) { return (wishes[e.name] || '').trim(); }).length;
        setTeaser('wishesTeaser', filled ? filled + ' заполнено' : 'пока пусто — что учесть при графике');
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
            S.api('/api/schedule/wishes', { method: 'POST', body: { employee_name: empName, text: text } })
                .then(function () { wishes[empName] = text; })
                .catch(function () { S.showToast('Пожелание не сохранилось', true); });
        }, 500);
    }

    // ==================== Реестр сотрудников ====================

    function renderEmployeesAdmin() {
        S.api('/api/schedule/employees?all=1').then(function (allEmps) {
            var tbody = document.getElementById('empAdminBody').querySelector('tbody');
            tbody.innerHTML = '';
            var active = allEmps.filter(function (e) { return e.active; }).length;
            setTeaser('empsTeaser', allEmps.length + ' в реестре · ' + active + ' активных');
            allEmps.forEach(function (emp) {
                var tr = document.createElement('tr');
                if (!emp.active) tr.className = 'inactive-row';

                var tdName = document.createElement('td');
                tdName.textContent = emp.name;

                var tdLabel = document.createElement('td');
                var labelInput = document.createElement('input');
                labelInput.type = 'text'; labelInput.maxLength = 4;
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

                tr.appendChild(tdName); tr.appendChild(tdLabel);
                tr.appendChild(tdOrder); tr.appendChild(tdActive);
                tbody.appendChild(tr);
            });
        });
    }
    function updateEmployee(empId, fields) {
        if (!empId) {
            S.showToast('Сотрудник ещё не привязан к iiko — нажми «Обновить из iiko»', true);
            return;
        }
        S.api('/api/schedule/employee/' + encodeURIComponent(empId), { method: 'PUT', body: fields })
            .then(function () { return S.api('/api/schedule/employees'); })
            .then(function (emps) {
                S.state.employees = emps;
                renderToolbar(); renderAll();
                S.showToast('Сотрудник обновлён');
            })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); });
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
                    msg += '. Не привязаны: ' + unmatched.map(function (u) { return u.name; }).join(', ');
                }
                S.showToast(msg, unmatched.length > 0);
                return S.api('/api/schedule/employees');
            })
            .then(function (emps) {
                S.state.employees = emps;
                renderToolbar(); renderAll();
            })
            .catch(function (err) { S.showToast('Ошибка iiko: ' + err.message, true); })
            .then(function () { btn.disabled = false; });
    }

    // ==================== Лента последних изменений ====================

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
            setTeaser('feedTeaser', 'изменений за месяц нет');
            return;
        }
        var f0 = rows[0];
        setTeaser('feedTeaser', (f0.actor_name || '—') + ' · ' + f0.summary);
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

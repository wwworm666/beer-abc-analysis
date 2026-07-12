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

    // Режим редактирования сетки. В просмотре кисть скрыта и клики по клеткам
    // ничего не меняют (исключает случайные правки). Выбор запоминается в браузере.
    var EDIT_MODE_KEY = 'schedule.editMode';
    var editMode = readEditMode();
    function readEditMode() {
        // По умолчанию ВЫКЛ: страница открывается в просмотре, правки — по кнопке.
        try { return localStorage.getItem(EDIT_MODE_KEY) === '1'; }
        catch (e) { return false; }
    }
    function saveEditMode(on) {
        try { localStorage.setItem(EDIT_MODE_KEY, on ? '1' : '0'); } catch (e) { /* приватный режим */ }
    }

    var selectedDate = null;      // открытая денежная панель дня
    var editingShiftId = null;    // модалка смены (десктоп)
    var editingShiftFactInitial = ''; // снимок поля «Факт» при открытии: не трогали — не шлём PUT /fact
    var editingShift = null;      // объект смены в десктоп-модалке (для кассы)
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
        document.getElementById('editModeToggle').addEventListener('click', toggleEditMode);

        // Мобильный: показать/скрыть полный график по сотрудникам (только просмотр).
        document.getElementById('mobileFullBtn').addEventListener('click', function () {
            document.body.classList.add('ms-fullview');
            window.scrollTo(0, 0);
        });
        document.getElementById('mobileBackBtn').addEventListener('click', function () {
            document.body.classList.remove('ms-fullview');
            window.scrollTo(0, 0);
        });

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
        document.getElementById('shiftClose').addEventListener('click', closeShiftModal);
        // модалка факта (мобильный)
        document.getElementById('factForm').addEventListener('submit', onFactSubmit);
        document.getElementById('factClose').addEventListener('click', closeFactModal);
        // Закрытие по тапу на затемнение (клик по самому оверлею, не по .modal внутри).
        document.getElementById('factModal').addEventListener('click', function (e) {
            if (e.target === this) closeFactModal();
        });
        document.getElementById('shiftModal').addEventListener('click', function (e) {
            if (e.target === this) closeShiftModal();
        });
        // касса: тумблеры «были траты / инкассация» показывают поля сумм
        wireCashToggles('fact');
        wireCashToggles('shift');

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
                renderEditMode();
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
                .catch(function (err) {
                    // не глушим молча: иначе сбой выглядит как «плана нет» и вводит в заблуждение
                    console.error(err); S.state.plans = null;
                    S.showToast('Не удалось загрузить план/факт', true);
                })
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
        renderCashHistory(document.getElementById('cashHistBody'));
        renderEmployeesAdmin();
        if (selectedDate) renderDayPanel(selectedDate);
    }

    // ==================== История кассы за месяц (read-only) ====================
    // Список сдач кассы по сменам месяца из уже загруженного state.shifts (без
    // нового запроса): дата, точка, бармен, траты (+заметка), инкассация, наличные
    // на конец. Итог месяца — суммы трат и инкассаций (наличные на конец —
    // остаток, не поток, не суммируем).
    function renderCashHistory(host) {
        if (!host) return;
        var rows = S.state.shifts.filter(function (s) {
            return s.cash_end_kop != null || s.cash_expense_kop != null
                || s.cash_collection_kop != null;
        }).slice().sort(function (a, b) {
            return a.date < b.date ? -1 : (a.date > b.date ? 1 : 0);
        });
        if (!rows.length) {
            setTeaser('cashTeaser', 'за месяц пусто');
            host.innerHTML = '<div class="cash-hist-empty">Кассу за этот месяц ещё не сдавали</div>';
            return;
        }
        var sumExp = 0, sumCol = 0;
        var body = rows.map(function (s) {
            var e = s.cash_expense_kop, c = s.cash_collection_kop, k = s.cash_end_kop;
            if (e != null) sumExp += e;
            if (c != null) sumCol += c;
            var loc = S.state.locations.filter(function (L) { return L.id === s.location_id; })[0];
            var locName = loc ? (loc.short_name || loc.name) : '';
            var expCell = e == null ? '<span class="ch-dim">&mdash;</span>'
                : S.kopToRubDisplay(e) + (e > 0 && s.cash_expense_note
                    ? ' <span class="ch-note" title="' + S.escapeHtml(s.cash_expense_note) + '">*</span>' : '');
            var colCell = c == null ? '<span class="ch-dim">&mdash;</span>' : S.kopToRubDisplay(c);
            var endCell = k == null ? '<span class="ch-dim">&mdash;</span>' : '<b>' + S.kopToRubDisplay(k) + '</b>';
            return '<tr>'
                + '<td>' + S.formatDateHuman(s.date).slice(0, 5) + '</td>'
                + '<td>' + S.escapeHtml(locName) + '</td>'
                + '<td>' + S.escapeHtml(S.employeeShortName(S.shiftDisplayName(s))) + '</td>'
                + '<td class="ch-num">' + expCell + '</td>'
                + '<td class="ch-num">' + colCell + '</td>'
                + '<td class="ch-num">' + endCell + '</td>'
                + '</tr>';
        }).join('');
        var total = '<tr class="ch-total"><td colspan="3">Итого за месяц</td>'
            + '<td class="ch-num">' + S.kopToRubDisplay(sumExp) + '</td>'
            + '<td class="ch-num">' + S.kopToRubDisplay(sumCol) + '</td>'
            + '<td class="ch-num">&mdash;</td></tr>';
        setTeaser('cashTeaser', rows.length + ' смен · инкассация ' + S.kopToRubDisplay(sumCol) + ' ₽');
        host.innerHTML = '<div class="cash-hist-wrap"><table class="cash-hist"><thead><tr>'
            + '<th>Дата</th><th>Точка</th><th>Бармен</th>'
            + '<th class="ch-num">Траты</th><th class="ch-num">Инкасс.</th><th class="ch-num">На конец</th>'
            + '</tr></thead><tbody>' + body + total + '</tbody></table></div>';
    }

    function renderLanes() {
        S.renderEditLanes(document.getElementById('lanes'), {
            onCell: onCell,
            onDayHeaderClick: toggleDayPanel,
            // в режиме просмотра не подсвечиваем клетки кистью (правка отключена)
            brushColor: !editMode ? null
                : (brushMode === 'point' ? S.colorById(brushPoint)
                    : (brushMode === 'dayoff' ? '#b0a99d' : null))
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
        // Курсоры/подсветку клеток включаем только в режиме редактирования.
        document.body.classList.toggle('eraser-mode', editMode && brushMode === 'eraser');
        document.body.classList.toggle('paint-mode', editMode && brushMode !== 'eraser');
    }

    // Режим редактирования: показать/скрыть тулбар кисти, переключить вид сетки,
    // обновить подпись кнопки. Сам рендер сетки (renderLanes) читает editMode через onCell.
    function renderEditMode() {
        var toolbar = document.getElementById('paintToolbar');
        if (toolbar) toolbar.style.display = editMode ? '' : 'none';
        var btn = document.getElementById('editModeToggle');
        if (btn) {
            btn.textContent = editMode ? 'Готово' : 'Редактировать';
            btn.classList.toggle('is-open', editMode);
        }
        document.body.classList.toggle('view-mode', !editMode);
        renderToolbar();
    }
    function toggleEditMode() {
        editMode = !editMode;
        saveEditMode(editMode);
        renderEditMode();
        renderLanes();
        updateHint();
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

    // existing — массив всех смен клетки (день и/или вечер). Слот определяется
    // активной кистью (brushRole): правим/перекрашиваем ровно ту смену, что и кисть,
    // а вторую (другого слота) не трогаем.
    function slotShift(list, role) {
        return (list || []).filter(function (s) {
            return (S.isEvening(s) ? 'evening' : 'day') === role;
        })[0] || null;
    }
    function onCell(emp, day, ds, existing) {
        var list = existing || [];
        if (!editMode) {
            // Режим просмотра: структуру не меняем, но по клику на смену открываем
            // ввод/правку факта часов (день в приоритете, как и отрисованный в клетке блок).
            var s = slotShift(list, 'day') || list[0] || null;
            if (s) openFactModal(s);
            return;
        }
        if (saving) return;
        if (brushMode === 'eraser') {
            // снять смену слота кисти; если такой нет — любую смену дня
            var toErase = slotShift(list, brushRole) || list[0] || null;
            if (toErase) deleteShift(toErase.id);
            return;
        }
        if (brushMode === 'dayoff') { toggleDayOff(emp, ds, list); return; }
        // point: работаем со сменой того же слота (день/вечер), что и кисть
        var slot = slotShift(list, brushRole);
        if (slot) {
            if (slot.location_id === brushPoint) { openShiftModal(slot); return; }
            replaceShift(slot, emp, ds);
            return;
        }
        createShift(emp, ds);   // в этом слоте смены нет — добавляем, вторую не трогаем
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
            .then(function () { return reload(); })
            .then(function () { saving = false; });
    }
    // Перекраска — один атомарный PUT (меняем точку/роль/время существующей смены),
    // а не DELETE+POST: при сбое второго шага смена не теряется, факт часов сохраняется.
    function replaceShift(existing, emp, ds) {
        if (!confirmDayOff(emp, ds)) return;
        var preset = presetForBrush(), role = roleForPreset(preset);
        saving = true;
        S.api('/api/schedule/shift/' + existing.id, { method: 'PUT', body: {
                location_id: brushPoint, role_id: role.id, start_time: preset.startTime
            } })
            .then(function () { S.showToast('Перекрашено'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { return reload(); })
            .then(function () { saving = false; });
    }
    function deleteShift(id) {
        saving = true;
        S.api('/api/schedule/shift/' + id, { method: 'DELETE' })
            .then(function () { S.showToast('Удалено'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { return reload(); })
            .then(function () { saving = false; });
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
                .then(function () { return reload(); })
                .then(function () { saving = false; });
            return;
        }
        saving = true;
        // existing — массив смен дня (день и/или вечер): снимаем все перед выходным
        var list = existing || [];
        var chain = Promise.resolve();
        list.forEach(function (s) {
            chain = chain.then(function () {
                return S.api('/api/schedule/shift/' + s.id, { method: 'DELETE' });
            });
        });
        chain
            .then(function () {
                return S.api('/api/schedule/dayoff', { method: 'POST',
                    body: { employee_name: emp.name, date_from: ds, date_to: ds } });
            })
            .then(function () { S.showToast(list.length ? 'Выходной (смена снята)' : 'Выходной поставлен'); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { return reload(); })
            .then(function () { saving = false; });
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
                .then(function () { return reload(); })
                .then(function () { saving = false; });
        } else {
            saving = true;
            S.api('/api/schedule/dayoff', { method: 'POST',
                body: { employee_name: empName, date_from: ds, date_to: ds } })
                .then(function () { S.showToast('Выходной запрошен'); })
                .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
                .then(function () { return reload(); })
                .then(function () { saving = false; });
        }
    }

    // ==================== Касса на смене (общее для обеих модалок) ====================
    // Показывается только для ДНЕВНОЙ смены (кассу сдаёт дневной бармен). В полях —
    // рубли; в данных смены (state) — копейки; API принимает рубли. Ручной ввод, без iiko.

    function cashEl(prefix, suffix) { return document.getElementById(prefix + suffix); }

    // Окно правок кассы — 72 часа от даты смены (день смены + 2 дня, лок с 00:00
    // 3-го дня). То же значение на сервере (routes/schedule.py); сервер авторитетен,
    // фронт заранее прячет поля и блокирует ввод.
    var CASH_EDIT_WINDOW_HOURS = 72;
    function cashLocked(shift) {
        if (!shift || !shift.date) return false;
        var p = String(shift.date).split('-');
        var deadline = new Date(+p[0], +p[1] - 1, +p[2], 0, 0, 0);
        deadline.setHours(deadline.getHours() + CASH_EDIT_WINDOW_HOURS);
        return new Date() > deadline;
    }

    // Тумблер «были траты / инкассация» -> показать/скрыть поле суммы.
    function wireCashToggles(prefix) {
        var expOn = cashEl(prefix, 'ExpenseOn');
        var colOn = cashEl(prefix, 'CollectionOn');
        if (expOn) expOn.addEventListener('change', function () {
            cashEl(prefix, 'ExpenseSub').hidden = !expOn.checked;
            if (expOn.checked) cashEl(prefix, 'ExpenseAmt').focus();
        });
        if (colOn) colOn.addEventListener('change', function () {
            cashEl(prefix, 'CollectionSub').hidden = !colOn.checked;
            if (colOn.checked) cashEl(prefix, 'CollectionAmt').focus();
        });
    }

    // Заполнить блок кассы из смены; спрятать для вечерней смены (isDay=false).
    function fillCashBlock(prefix, shift, isDay) {
        var block = cashEl(prefix, 'CashBlock');
        if (!block) return;
        block.style.display = isDay ? '' : 'none';
        if (!isDay) return;
        var exp = shift.cash_expense_kop, col = shift.cash_collection_kop, end = shift.cash_end_kop;
        var expOn = exp != null && exp > 0;
        var colOn = col != null && col > 0;
        cashEl(prefix, 'ExpenseOn').checked = expOn;
        cashEl(prefix, 'ExpenseSub').hidden = !expOn;
        cashEl(prefix, 'ExpenseAmt').value = expOn ? S.kopToRubInput(exp) : '';
        cashEl(prefix, 'ExpenseNote').value = shift.cash_expense_note || '';
        cashEl(prefix, 'CollectionOn').checked = colOn;
        cashEl(prefix, 'CollectionSub').hidden = !colOn;
        cashEl(prefix, 'CollectionAmt').value = colOn ? S.kopToRubInput(col) : '';
        cashEl(prefix, 'CashEnd').value = S.kopToRubInput(end);

        // Заморозка: касса старше окна — read-only. Поля блокируем, показываем
        // пометку. Значения остаются видны. Сервер тоже вернёт 403 при попытке.
        var locked = cashLocked(shift);
        var lockEl = cashEl(prefix, 'CashLocked');
        if (lockEl) {
            lockEl.hidden = !locked;
            if (locked) lockEl.textContent = 'Касса заморожена: правки только '
                + CASH_EDIT_WINDOW_HOURS + ' часа после смены. Значения только для просмотра.';
        }
        ['ExpenseOn', 'ExpenseAmt', 'ExpenseNote', 'CollectionOn', 'CollectionAmt', 'CashEnd']
            .forEach(function (f) { var el = cashEl(prefix, f); if (el) el.disabled = locked; });
    }

    // Прочитать и провалидировать поля кассы -> {ok, error, payload} (рубли).
    // Тумблер выкл -> 0; тумблер вкл, но пусто/<=0 -> ошибка.
    function readCashPayload(prefix) {
        var expense = 0, collection = 0;
        if (cashEl(prefix, 'ExpenseOn').checked) {
            expense = S.parseRubInput(cashEl(prefix, 'ExpenseAmt').value);
            if (expense == null || isNaN(expense) || expense <= 0)
                return { ok: false, error: 'Траты из кассы: укажи сумму больше 0' };
            if (!cashEl(prefix, 'ExpenseNote').value.trim())
                return { ok: false, error: 'Траты из кассы: укажи, на что потрачено' };
        }
        if (cashEl(prefix, 'CollectionOn').checked) {
            collection = S.parseRubInput(cashEl(prefix, 'CollectionAmt').value);
            if (collection == null || isNaN(collection) || collection <= 0)
                return { ok: false, error: 'Инкассация: укажи сумму больше 0' };
        }
        var end = S.parseRubInput(cashEl(prefix, 'CashEnd').value);  // null = не заполнено
        if (isNaN(end)) return { ok: false, error: 'Наличные на конец: только число' };
        return { ok: true, payload: {
            cash_expense: expense, cash_collection: collection, cash_end: end,
            cash_expense_note: cashEl(prefix, 'ExpenseNote').value.trim()
        } };
    }

    function cashHasInput(p) {
        return p.cash_expense > 0 || p.cash_collection > 0 || p.cash_end != null
            || (p.cash_expense_note || '') !== '';
    }
    function shiftHadCash(shift) {
        return shift.cash_end_kop != null || shift.cash_expense_kop != null
            || shift.cash_collection_kop != null;
    }

    // Разобрать блок кассы для сабмита -> {ok, error, body|null}.
    //   body=null — слать /cash не нужно (блок скрыт, либо пусто и раньше было пусто);
    //   body=obj  — PUT /cash (set при вводе, clear-нулями если стёрли ранее сданную).
    function readCashForSubmit(prefix, shift) {
        var block = cashEl(prefix, 'CashBlock');
        if (!block || block.style.display === 'none') return { ok: true, body: null };
        if (cashLocked(shift)) return { ok: true, body: null };  // заморожена — не шлём
        var res = readCashPayload(prefix);
        if (!res.ok) return res;
        if (!cashHasInput(res.payload)) {
            if (!shiftHadCash(shift)) return { ok: true, body: null };
            return { ok: true, body: { cash_expense: null, cash_collection: null,
                cash_end: null, cash_expense_note: '' } };
        }
        return { ok: true, body: res.payload };
    }
    function sendCash(shiftId, cash) {
        if (!cash.body) return Promise.resolve(true);
        return S.api('/api/schedule/shift/' + shiftId + '/cash', { method: 'PUT', body: cash.body });
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
        editingShift = shift;
        document.getElementById('shiftModalTitle').textContent =
            S.shiftDisplayName(shift) + ' — ' + S.formatDateHuman(shift.date);
        document.getElementById('shiftRole').value = shift.role_id;
        document.getElementById('shiftStartTime').value = shift.start_time || '';
        document.getElementById('shiftFact').value =
            shift.fact_minutes != null ? S.minutesToHhMm(shift.fact_minutes) : '';
        editingShiftFactInitial = document.getElementById('shiftFact').value;
        fillCashBlock('shift', shift, !S.isEvening(shift));
        var dayOffEmps = S.getDayOffEmployees(shift.date);
        document.getElementById('dayoffWarning').style.display =
            dayOffEmps.indexOf(shift.employee_name) !== -1 ? 'block' : 'none';
        document.getElementById('shiftModal').classList.add('active');
    }
    function closeShiftModal() {
        document.getElementById('shiftModal').classList.remove('active');
        editingShiftId = null;
        editingShift = null;
    }
    function onShiftFormSubmit(e) {
        e.preventDefault();
        if (!editingShiftId || saving) return;   // guard от двойного сабмита
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
        // касса (дневная смена) — валидируем ДО записи
        var cash = readCashForSubmit('shift', editingShift || {});
        if (!cash.ok) { S.showToast(cash.error, true); return; }
        var id = editingShiftId;
        // Поле «Факт» не меняли — PUT /fact не шлём: иначе stale-значение из модалки
        // затёрло бы факт, введённый барменом, пока модалка была открыта.
        var factChanged = factRaw !== editingShiftFactInitial;
        saving = true;
        S.api('/api/schedule/shift/' + id, { method: 'PUT', body: { role_id: roleId, start_time: startTime } })
            .then(function () {
                // Поле «Факт» не меняли — PUT /fact не шлём (иначе stale-значение
                // затёрло бы факт, введённый барменом, пока модалка была открыта).
                if (!factChanged) return;
                return S.api('/api/schedule/shift/' + id + '/fact', { method: 'PUT', body: { fact_minutes: factMin } });
            })
            .then(function () { return sendCash(id, cash); })
            .then(function () { closeShiftModal(); S.showToast('Сохранено'); return reload(); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { saving = false; });
    }
    function onShiftDelete() {
        if (!editingShiftId || saving) return;
        saving = true;
        S.api('/api/schedule/shift/' + editingShiftId, { method: 'DELETE' })
            .then(function () { closeShiftModal(); S.showToast('Удалено'); return reload(); })
            .catch(function (err) { S.showToast('Ошибка: ' + err.message, true); })
            .then(function () { saving = false; });
    }

    // ==================== Модалка факта (мобильный) ====================

    function openFactModal(shift) {
        currentFactShift = shift;
        document.getElementById('factModalTitle').textContent =
            S.shiftDisplayName(shift) + ' — ' + S.formatDateHuman(shift.date) + ' — ' + shift.location_name;
        var input = document.getElementById('factInput');
        input.value = shift.fact_minutes != null ? S.minutesToHhMm(shift.fact_minutes) : '';
        fillCashBlock('fact', shift, !S.isEvening(shift));
        document.getElementById('factModal').classList.add('active');
        input.focus();
    }
    function closeFactModal() {
        document.getElementById('factModal').classList.remove('active');
        currentFactShift = null;
    }
    function onFactSubmit(e) {
        e.preventDefault();
        if (!currentFactShift || saving) return;
        var minutes = S.parseHoursInput(document.getElementById('factInput').value);
        if (minutes === null || minutes < 0 || minutes > 1440) {
            S.showToast('Введи часы как 10:30 или 10.5', true); return;
        }
        // касса (дневная смена) — валидируем ДО записи
        var shift = currentFactShift;
        var cash = readCashForSubmit('fact', shift);
        if (!cash.ok) { S.showToast(cash.error, true); return; }
        saving = true;
        S.api('/api/schedule/shift/' + shift.id + '/fact', { method: 'PUT', body: { fact_minutes: minutes } })
            .then(function () { return sendCash(shift.id, cash); })
            .then(function () { closeFactModal(); S.showToast('Смена закрыта'); return reload(); })
            .catch(function (err) { S.showToast('Не сохранилось: ' + err.message, true); })
            .then(function () { saving = false; });
    }

    // ==================== Денежная панель дня ====================
    // Открывается кликом по номеру дня в шапке полос. План — из весов дней,
    // факт — живой iiko OLAP. Свёрнута по умолчанию, но доступна всем залогиненным
    // (права равные, финансовые данные открыты — ограничения «только владельцу» нет).

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
    // Дневная смена точки за день (кассу сдаёт дневной бармен). Если есть только
    // вечерняя — берём её (чтобы касса не потерялась). null, если смен нет.
    function dayShiftCashFor(ds, locId) {
        var list = S.state.shifts.filter(function (s) {
            return s.date === ds && s.location_id === locId;
        });
        return list.filter(function (s) { return !S.isEvening(s); })[0] || list[0] || null;
    }
    // Кассовые строки карточки дня (агрегат по бару): траты / инкассация / касса на
    // конец. Показываем только если в этот день на точке есть смена (есть кому сдавать).
    function cashRowsHtml(ds, locId) {
        var sh = dayShiftCashFor(ds, locId);
        if (!sh) return '';
        var e = sh.cash_expense_kop, c = sh.cash_collection_kop, k = sh.cash_end_kop;
        var expHtml = e == null ? '<span class="v empty">—</span>'
            : '<span class="v">' + S.kopToRubDisplay(e) + ' ₽</span>';
        var noteHtml = (e != null && e > 0 && sh.cash_expense_note)
            ? '<div class="cash-note">' + S.escapeHtml(sh.cash_expense_note) + '</div>' : '';
        var colHtml = c == null ? '<span class="v empty">—</span>'
            : '<span class="v">' + S.kopToRubDisplay(c) + ' ₽</span>';
        var endHtml = k == null ? '<span class="v cash-none">не сдана</span>'
            : '<span class="v fact">' + S.kopToRubDisplay(k) + ' ₽</span>';
        return '<div class="cash-divider"></div>'
            + '<div class="metric"><span class="k">Траты</span>' + expHtml + '</div>' + noteHtml
            + '<div class="metric"><span class="k">Инкассация</span>' + colHtml + '</div>'
            + '<div class="metric"><span class="k">Касса на конец</span>' + endHtml + '</div>';
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
                + sourceHtml
                + cashRowsHtml(ds, loc.id) + '</div>';
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
        }).catch(function (err) {
            // не оставляем промис без обработки: иначе реестр тихо не обновляется
            console.error(err);
            setTeaser('empsTeaser', 'не удалось загрузить реестр');
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
        btn.classList.add('is-loading');
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
            .then(function () { btn.disabled = false; btn.classList.remove('is-loading'); });
    }

    // ==================== Лента последних изменений ====================

    var FEED_DOT = {
        shift_create: '#2e9e5b', shift_update: '#d97706', shift_delete: '#dc2626',
        fact_set: '#2563eb', fact_clear: '#9aa0a6',
        dayoff_create: '#7c3aed', dayoff_delete: '#7c3aed',
        // деньги/ставки/реестр — отдельные цвета (изменения с финансовым весом)
        role_rate: '#b45309', revenue_set: '#0d9488',
        revenue_sync: '#0d9488', revenue_sync_month: '#0d9488',
        cash_set: '#0891b2', cash_clear: '#94a3b8',
        employee_update: '#6b7280', employees_sync: '#6b7280'
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

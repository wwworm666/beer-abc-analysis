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

        // Касса за месяц: вид, фильтр по точке, поиск, CSV и правка строки.
        // Всё через делегирование — таблица перерисовывается целиком, живые
        // слушатели на её кнопках пришлось бы навешивать заново каждый раз.
        document.getElementById('cashViewSeg').addEventListener('click', function (e) {
            var b = e.target.closest('[data-cash-view]');
            if (b) setCashView(b.dataset.cashView);
        });
        document.getElementById('cashLocSeg').addEventListener('click', function (e) {
            var b = e.target.closest('[data-cash-loc]');
            if (b) setCashLoc(b.dataset.cashLoc);
        });
        document.getElementById('cashSearch').addEventListener('input', function () {
            renderCashHistory(document.getElementById('cashHistBody'));
        });
        document.getElementById('cashHistBody').addEventListener('click', function (e) {
            var edit = e.target.closest('[data-cash-edit]');
            if (edit) { cashEdit(Number(edit.dataset.cashEdit)); return; }
            var save = e.target.closest('[data-cash-save]');
            if (save) { cashSave(Number(save.dataset.cashSave), save); return; }
            if (e.target.closest('[data-cash-cancel]')) cashCancel();
        });
        document.getElementById('cashCsvBtn').addEventListener('click', exportCashCsv);
        // стартовое состояние блока до загрузки месяца: подсветка вида + «Загрузка...»
        renderCashHistory(document.getElementById('cashHistBody'));

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
        loadCashRegister();
        renderEmployeesAdmin();
        if (selectedDate) renderDayPanel(selectedDate);
    }

    // ==================== Касса за месяц (регистр) ====================
    // Блок «Касса за месяц» — рабочий стол владельца/бухгалтера. Показывает смены
    // месяца вместе с ПРОБЕЛАМИ: день, за который кассу не сдали, автоматом
    // снимает премию «передача смены», и найти его надо до расчёта ЗП.
    //
    // Строки собирает СЕРВЕР — GET /api/schedule/cash-register/<год>/<месяц>
    // (core/cash_register.py): там же условие пробела, дословно то же, которое
    // обнуляет премию в расчёте. Дублировать это условие на клиенте нельзя —
    // разъедется. Фильтр по точке, поиск и виды работают по уже загруженным
    // строкам, без новых запросов.
    //
    // Правка суммы — PUT /api/schedule/cash-register/shift/<id>: только
    // администратору и БЕЗ окна 72 ч, которым заперта касса в модалке смены (в
    // этом и смысл: внести трату, всплывшую в чате через неделю). В той же форме
    // ставится штраф — без него внесение кассы задним числом ВЕРНУЛО бы бармену
    // премию 500 ₽ за день, который он не закрыл.
    //
    // Пять видов (выбор запоминается в браузере):
    //   «Сводная»    — смены с кассой + пробелы (рабочий вид);
    //   «Проблемы»   — только строки с флагами;
    //   «Все смены»  — все смены месяца, включая вечерние и будущие;
    //   «Траты»      — только траты, комментарий «на что» колонкой целиком;
    //   «Инкассации» — только сдачи инкассации.

    var CASH_VIEW_KEY = 'schedule.cashView';
    var CASH_VIEW_SLUG = { all: 'svodnaya', problems: 'problemy', shifts: 'vse-smeny',
                           expense: 'traty', collection: 'inkassacii' };
    var cashView = readCashView();
    var cashReg = null;        // ответ /api/schedule/cash-register целиком
    var cashLoc = 'all';       // фильтр по точке: 'all' | location_id
    var cashEditId = null;     // смена с открытой формой правки (одна за раз)
    var cashLoading = false;

    function readCashView() {
        try {
            var v = localStorage.getItem(CASH_VIEW_KEY);
            return CASH_VIEW_SLUG.hasOwnProperty(v) ? v : 'all';
        } catch (e) { return 'all'; }
    }
    function setCashView(v) {
        if (!CASH_VIEW_SLUG.hasOwnProperty(v) || v === cashView) return;
        cashView = v;
        cashEditId = null;
        try { localStorage.setItem(CASH_VIEW_KEY, v); } catch (e) { /* приватный режим */ }
        renderCashHistory(document.getElementById('cashHistBody'));
    }
    function setCashLoc(id) {
        cashLoc = id;
        cashEditId = null;
        renderCashHistory(document.getElementById('cashHistBody'));
    }

    // Регистр месяца. Зовётся из renderAll (после загрузки смен) и после правки.
    function loadCashRegister() {
        if (cashLoading) return Promise.resolve();
        cashLoading = true;
        return S.api('/api/schedule/cash-register/' + S.state.year + '/' + S.state.month)
            .then(function (data) {
                cashReg = data;
                // точка из прошлого месяца могла не встретиться в этом
                if (cashLoc !== 'all' && !(data.locations || [])
                        .some(function (L) { return String(L.id) === String(cashLoc); })) {
                    cashLoc = 'all';
                }
            })
            .catch(function (err) {
                console.error(err);
                cashReg = null;
                S.showToast('Касса за месяц не загрузилась', true);
            })
            .then(function () {
                cashLoading = false;
                renderCashHistory(document.getElementById('cashHistBody'));
            });
    }

    // Уведомление под панелью (не тост): чем закончилось сохранение. Держится до
    // следующего действия — его надо прочитать, а не поймать всплывашку.
    function setCashNotice(msg) {
        var el = document.getElementById('cashNotice');
        if (!el) return;
        el.textContent = msg || '';
        el.classList.toggle('is-on', !!msg);
    }

    // Имя для показа: из реестра по стабильному id (актуальное после
    // переименования в iiko), иначе снимок имени из смены — как S.shiftDisplayName.
    function cashRowName(r) {
        var emp = S.getEmployeeById(r.employee_id);
        return (emp && emp.name) || r.employee_name || '';
    }

    // Строки текущего вида: фильтр по точке -> вид -> поиск.
    function cashRows() {
        var rows = (cashReg && cashReg.rows) || [];
        if (cashLoc !== 'all') {
            rows = rows.filter(function (r) { return String(r.location_id) === String(cashLoc); });
        }
        if (cashView === 'problems') {
            rows = rows.filter(function (r) { return r.problems.length; });
        } else if (cashView === 'all') {
            rows = rows.filter(function (r) { return r.has_cash || r.problems.length; });
        } else if (cashView === 'expense') {
            // 0 = «трат не было», NULL = не заполнено — в частном виде не показываем
            rows = rows.filter(function (r) { return r.expense_kop > 0; });
        } else if (cashView === 'collection') {
            rows = rows.filter(function (r) { return r.collection_kop > 0; });
        }
        var q = (document.getElementById('cashSearch').value || '').trim().toLowerCase();
        if (q) {
            rows = rows.filter(function (r) {
                return cashRowName(r).toLowerCase().indexOf(q) !== -1
                    || (r.expense_note || '').toLowerCase().indexOf(q) !== -1
                    || (r.penalty_note || '').toLowerCase().indexOf(q) !== -1;
            });
        }
        return rows;
    }

    var CH_DASH = '<span class="ch-dim">&mdash;</span>';
    function chCell(kop) { return kop == null ? CH_DASH : S.kopToRubDisplay(kop); }
    function chDm(ds) { return ds.slice(8, 10) + '.' + ds.slice(5, 7); }

    // Правка задним числом: дата смены вышла из окна, в котором кассу правит
    // бармен. Тогда штраф в форме предлагается по умолчанию — сумму вносит
    // владелец, потому что бармен этого не сделал.
    function cashLateEdit(ds) {
        var hours = (cashReg && cashReg.edit_window_hours) || 72;
        return new Date(ds + 'T00:00:00').getTime() + hours * 3600e3 < Date.now();
    }

    function cashFlags(r) {
        var labels = (cashReg && cashReg.problem_labels) || {};
        var out = r.problems.map(function (p) {
            return '<span class="ch-flag' + (p === 'no_note' ? ' warn' : '') + '">'
                + S.escapeHtml(labels[p] || p) + '</span>';
        });
        if (r.penalized) {
            out.push('<span class="ch-flag" title="Премия за передачу смены за этот день снята'
                + (r.penalty_note ? '. Причина: ' + S.escapeHtml(r.penalty_note) : '')
                + '">штраф ' + ((cashReg && cashReg.handover_rate) || 500) + ' &#8381;</span>');
        }
        return out.join(' ');
    }

    // Открыта ли форма правки для этой строки. Проверка на null обязательна: у
    // строки-сироты (штраф без смены в графике) shift_id = null, и при закрытой
    // форме cashEditId тоже null — без неё форма раскрывалась бы сама собой.
    function cashIsEditing(r) {
        return r.shift_id != null && cashEditId === r.shift_id;
    }

    // Кнопка правки. У строки-сироты (штраф без смены в графике) править нечего:
    // кассу пишем в смену, а её нет — штраф снимается на странице ЗП.
    function cashActionCell(r) {
        if (!(cashReg && cashReg.can_edit) || r.shift_id == null) return '<td></td>';
        return '<td><button type="button" class="ch-edit" data-cash-edit="'
            + r.shift_id + '">' + (r.has_cash ? 'Правка' : 'Внести') + '</button></td>';
    }

    // Подытоги по точкам: строка «Итого <точка>» на каждую точку с операциями
    // (порядок появления в месяце). Одна точка — подытога нет, хватает общего итога.
    // labelSpan — colspan ячейки-подписи, tailCells — пустых ячеек после суммы.
    function cashSubtotalRows(rows, field, labelSpan, tailCells) {
        var sums = {}, order = [];
        rows.forEach(function (r) {
            var k = r.location_short || '—';
            if (!(k in sums)) { sums[k] = 0; order.push(k); }
            sums[k] += r[field];
        });
        if (order.length < 2) return '';
        var tail = new Array(tailCells + 1).join('<td></td>');
        return order.map(function (k) {
            return '<tr class="ch-sub"><td colspan="' + labelSpan + '">Итого ' + S.escapeHtml(k) + '</td>'
                + '<td class="ch-num">' + S.kopToRubDisplay(sums[k]) + '</td>' + tail + '</tr>';
        }).join('');
    }

    // Регистр («Сводная» / «Проблемы» / «Все смены»): все кассовые поля смены,
    // состояние строки и правка. 10 колонок.
    function cashTableRegister(rows) {
        var sumExp = 0, sumCol = 0;
        var body = rows.map(function (r) {
            sumExp += r.expense_kop || 0;
            sumCol += r.collection_kop || 0;
            var cls = [r.problems.length ? 'ch-problem' : '', r.evening ? 'ch-eve' : '']
                .filter(Boolean).join(' ');
            var row = '<tr class="' + cls + '">'
                + '<td>' + chDm(r.date) + '</td>'
                + '<td>' + (r.location_short ? S.escapeHtml(r.location_short) : CH_DASH) + '</td>'
                + '<td>' + S.escapeHtml(S.employeeShortName(cashRowName(r))) + '</td>'
                + '<td class="ch-dim">' + (r.shift_id == null ? '&mdash;'
                    : (r.evening ? 'вечер' : 'день')) + '</td>'
                + '<td class="ch-num">' + chCell(r.expense_kop) + '</td>'
                + '<td class="ch-comment">'
                + (r.expense_note ? S.escapeHtml(r.expense_note) : CH_DASH) + '</td>'
                + '<td class="ch-num">' + chCell(r.collection_kop) + '</td>'
                + '<td class="ch-num ch-end">' + chCell(r.end_kop) + '</td>'
                + '<td>' + (cashFlags(r) || CH_DASH) + '</td>'
                + cashActionCell(r) + '</tr>';
            return row + (cashIsEditing(r) ? cashFormRow(r, 10) : '');
        }).join('');
        var total = '<tr class="ch-total"><td colspan="4">Итого</td>'
            + '<td class="ch-num">' + S.kopToRubDisplay(sumExp) + '</td><td></td>'
            + '<td class="ch-num">' + S.kopToRubDisplay(sumCol) + '</td>'
            + '<td colspan="3"></td></tr>';
        return '<table class="cash-hist"><thead><tr>'
            + '<th>Дата</th><th>Точка</th><th>Бармен</th><th>Смена</th>'
            + '<th class="ch-num">Траты</th><th>На что</th>'
            + '<th class="ch-num">Инкасс.</th><th class="ch-num">На конец</th>'
            + '<th>Состояние</th><th></th>'
            + '</tr></thead><tbody>' + body + total + '</tbody></table>';
    }

    // «Траты»: дата / точка / бармен / сумма / на что (комментарий целиком).
    function cashTableExpense(rows) {
        var sum = 0;
        var body = rows.map(function (r) {
            sum += r.expense_kop;
            return '<tr class="' + (r.problems.length ? 'ch-problem' : '') + '">'
                + '<td>' + chDm(r.date) + '</td>'
                + '<td>' + S.escapeHtml(r.location_short) + '</td>'
                + '<td>' + S.escapeHtml(S.employeeShortName(cashRowName(r))) + '</td>'
                + '<td class="ch-num">' + S.kopToRubDisplay(r.expense_kop) + '</td>'
                + '<td class="ch-comment">'
                + (r.expense_note ? S.escapeHtml(r.expense_note) : CH_DASH) + '</td>'
                + cashActionCell(r) + '</tr>'
                + (cashIsEditing(r) ? cashFormRow(r, 6) : '');
        }).join('');
        var foot = cashSubtotalRows(rows, 'expense_kop', 3, 2)
            + '<tr class="ch-total"><td colspan="3">Итого за месяц (' + rows.length + ')</td>'
            + '<td class="ch-num">' + S.kopToRubDisplay(sum) + '</td><td colspan="2"></td></tr>';
        return '<table class="cash-hist"><thead><tr>'
            + '<th>Дата</th><th>Точка</th><th>Бармен</th>'
            + '<th class="ch-num">Сумма, &#8381;</th><th>На что</th><th></th>'
            + '</tr></thead><tbody>' + body + foot + '</tbody></table>';
    }

    // «Инкассации»: дата / точка / бармен / сумма.
    function cashTableCollection(rows) {
        var sum = 0;
        var body = rows.map(function (r) {
            sum += r.collection_kop;
            return '<tr class="' + (r.problems.length ? 'ch-problem' : '') + '">'
                + '<td>' + chDm(r.date) + '</td>'
                + '<td>' + S.escapeHtml(r.location_short) + '</td>'
                + '<td>' + S.escapeHtml(S.employeeShortName(cashRowName(r))) + '</td>'
                + '<td class="ch-num">' + S.kopToRubDisplay(r.collection_kop) + '</td>'
                + cashActionCell(r) + '</tr>'
                + (cashIsEditing(r) ? cashFormRow(r, 5) : '');
        }).join('');
        var foot = cashSubtotalRows(rows, 'collection_kop', 3, 1)
            + '<tr class="ch-total"><td colspan="3">Итого за месяц (' + rows.length + ')</td>'
            + '<td class="ch-num">' + S.kopToRubDisplay(sum) + '</td><td></td></tr>';
        return '<table class="cash-hist"><thead><tr>'
            + '<th>Дата</th><th>Точка</th><th>Бармен</th>'
            + '<th class="ch-num">Сумма, &#8381;</th><th></th>'
            + '</tr></thead><tbody>' + body + foot + '</tbody></table>';
    }

    // Форма правки — строка под записью. Штраф предлагается по умолчанию, если
    // день не закрыт кассой или правка идёт задним числом: и то и другое значит,
    // что бармен свою часть не сделал.
    function cashFormRow(r, cols) {
        var suggest = r.penalized || r.problems.indexOf('no_cash') !== -1 || cashLateEdit(r.date);
        var noteDefault = r.penalty_note
            || (r.problems.indexOf('no_cash') !== -1 ? 'касса не сдана, внесена задним числом'
                : 'касса исправлена задним числом');
        var rate = (cashReg && cashReg.handover_rate) || 500;
        return '<tr class="ch-form"><td colspan="' + cols + '">'
            + '<div class="ch-form-grid">'
            + '<label class="ch-field"><span>Траты, &#8381;</span>'
            + '<input type="text" id="chExp" value="' + S.kopToRubInput(r.expense_kop) + '"></label>'
            + '<label class="ch-field ch-field-wide"><span>На что</span>'
            + '<input type="text" id="chNote" maxlength="200" value="'
            + S.escapeHtml(r.expense_note || '') + '"></label>'
            + '<label class="ch-field"><span>Инкассация, &#8381;</span>'
            + '<input type="text" id="chCol" value="' + S.kopToRubInput(r.collection_kop) + '"></label>'
            + '<label class="ch-field"><span>Наличные на конец, &#8381;</span>'
            + '<input type="text" id="chEnd" value="' + S.kopToRubInput(r.end_kop) + '"></label>'
            + '</div>'
            + '<div class="ch-form-row">'
            + '<label class="ch-check"><input type="checkbox" id="chPen"'
            + (suggest ? ' checked' : '') + '> Штраф ' + rate + ' &#8381; — премия за передачу'
            + ' смены за ' + chDm(r.date) + ' не платится</label>'
            + '<input type="text" id="chPenNote" class="ch-pen-note" maxlength="200"'
            + ' placeholder="Причина штрафа" value="' + S.escapeHtml(noteDefault) + '">'
            + '</div>'
            + '<div class="ch-form-row">'
            + '<button type="button" class="btn" data-cash-save="' + r.shift_id + '">Сохранить</button>'
            + '<button type="button" class="btn btn-secondary" data-cash-cancel>Отмена</button>'
            + '<span class="ch-form-hint">Пустое поле — «не заполнено», 0 — «не было».'
            + ' Все три суммы пустые = касса смены очищена. Правка попадёт в журнал'
            + ' изменений с вашим именем.</span>'
            + '</div></td></tr>';
    }

    function cashEdit(shiftId) {
        cashEditId = cashEditId === shiftId ? null : shiftId;
        setCashNotice('');
        renderCashHistory(document.getElementById('cashHistBody'));
        var el = document.getElementById('chEnd');
        if (el) el.focus();
    }
    function cashCancel() {
        cashEditId = null;
        renderCashHistory(document.getElementById('cashHistBody'));
    }

    function cashSave(shiftId, btn) {
        if (btn.disabled) return;
        var read = function (id) {
            var raw = (document.getElementById(id).value || '').trim();
            if (!raw) return null;
            var v = S.parseRubInput(raw);
            return v;
        };
        var exp = read('chExp'), col = read('chCol'), end = read('chEnd');
        if ([exp, col, end].some(function (v) { return typeof v === 'number' && isNaN(v); })) {
            S.showToast('Суммы — числа в рублях, например 15340 или 350,50', true);
            return;
        }
        btn.disabled = true;
        S.api('/api/schedule/cash-register/shift/' + shiftId, {
            method: 'PUT',
            body: {
                cash_expense: exp, cash_collection: col, cash_end: end,
                cash_expense_note: document.getElementById('chNote').value || '',
                penalize: document.getElementById('chPen').checked,
                penalty_note: document.getElementById('chPenNote').value || ''
            }
        }).then(function (res) {
            cashEditId = null;
            // Месяц перечитываем целиком: пробел мог закрыться, а панель дня и
            // сетка показывают ту же кассу.
            return reload().then(function () {
                // Премия могла вернуться к другим сотрудникам этой точки за этот
                // день: касса дня закрылась, автоправило снова платит. Молчать
                // нельзя — это чужая ЗП, а штраф их не касается.
                setCashNotice((res.premium_restored_for || []).length
                    ? 'Касса за день закрыта — премия за передачу смены вернулась к: '
                        + res.premium_restored_for.join(', ')
                        + '. Если премия им не положена, проставьте штраф и по их сменам.'
                    : (res.cash_changed || res.penalty_changed
                        ? 'Сохранено. Премии на странице ЗП пересчитаются при следующем расчёте.'
                        : 'Изменений не было.'));
            });
        }).catch(function (err) {
            S.showToast(err.message || 'Не сохранено', true);
        }).then(function () { btn.disabled = false; });
    }

    function renderCashHistory(host) {
        if (!host) return;
        document.querySelectorAll('#cashViewSeg [data-cash-view]').forEach(function (b) {
            b.classList.toggle('selected', b.dataset.cashView === cashView);
        });
        if (!cashReg) {
            host.innerHTML = '<div class="cash-hist-empty">Загрузка...</div>';
            return;
        }

        // Чипы точек: «Все» + точки месяца, на чипе — число проблем этой точки
        // (видно, где искать, не переключая фильтр).
        var probByLoc = {}, totalProb = 0;
        (cashReg.rows || []).forEach(function (r) {
            if (!r.problems.length) return;
            totalProb++;
            probByLoc[r.location_id] = (probByLoc[r.location_id] || 0) + 1;
        });
        var chip = function (id, label, count) {
            return '<button type="button" class="ch-chip'
                + (String(cashLoc) === String(id) ? ' selected' : '') + '"'
                + ' data-cash-loc="' + id + '">' + S.escapeHtml(label)
                + (count ? ' <b>' + count + '</b>' : '') + '</button>';
        };
        document.getElementById('cashLocSeg').innerHTML =
            chip('all', 'Все точки', totalProb)
            + (cashReg.locations || []).map(function (L) {
                return chip(L.id, L.short || L.name, probByLoc[L.id] || 0);
            }).join('');

        var rows = cashRows();
        var sumExp = 0, sumCol = 0, nProb = 0, nPen = 0;
        rows.forEach(function (r) {
            sumExp += r.expense_kop || 0;
            sumCol += r.collection_kop || 0;
            if (r.problems.length) nProb++;
            if (r.penalized) nPen++;
        });
        document.getElementById('cashSummary').innerHTML =
            'Строк: <b>' + rows.length + '</b> &middot; траты <b>' + S.kopToRubDisplay(sumExp)
            + ' &#8381;</b> &middot; инкассации <b>' + S.kopToRubDisplay(sumCol)
            + ' &#8381;</b> &middot; проблем <b>' + nProb + '</b> &middot; штрафов <b>' + nPen + '</b>'
            + (cashReg.can_edit ? '' : ' &middot; правка доступна администратору');

        var t = cashReg.totals || {};
        setTeaser('cashTeaser', t.with_cash
            ? t.with_cash + ' смен · траты ' + S.kopToRubDisplay(t.expense_kop)
                + ' · инкасс. ' + S.kopToRubDisplay(t.collection_kop) + ' ₽'
                + (t.problems ? ' · проблем ' + t.problems : '')
            : 'за месяц пусто');

        if (!rows.length) {
            host.innerHTML = '<div class="cash-hist-empty">' + ({
                all: 'Кассу за этот месяц ещё не сдавали',
                problems: 'Проблем по кассе за этот месяц нет',
                shifts: 'Смен за этот месяц нет',
                expense: 'Трат из кассы за этот месяц не записано',
                collection: 'Инкассаций за этот месяц не записано'
            }[cashView]) + '</div>';
            return;
        }
        var table = cashView === 'expense' ? cashTableExpense(rows)
            : cashView === 'collection' ? cashTableCollection(rows)
                : cashTableRegister(rows);
        host.innerHTML = '<div class="cash-hist-wrap">' + table + '</div>';
    }

    // ==================== Выгрузка кассы в CSV (Excel) ====================
    // Текущий вид -> CSV: разделитель «;» (русская локаль Excel), UTF-8 BOM для
    // кириллицы, CRLF. Суммы — числом в рублях: запятая-десятичная, без
    // разделителей тысяч — Excel видит число и умеет SUM. Только строки данных,
    // без итогов: итоги считаются в Excel самостоятельно.

    function csvField(v) {
        v = String(v == null ? '' : v);
        // Ячейка с ведущим = + - @ (свободный текст заметки) получает апостроф-
        // префикс: иначе Excel считает её формулой («=закупка» -> ошибка имени)
        // или числом («+7900...» теряет плюс). Суммы/даты начинаются с цифры —
        // их префикс не касается. Апостроф Excel прячет, текст остаётся как есть.
        if (/^[=+@-]/.test(v)) v = "'" + v;
        return /[";\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    }
    // Копейки -> число для CSV: 1534025 -> '15340,25'; 500000 -> '5000'; null -> ''.
    function kopToRubCsv(kop) {
        if (kop == null) return '';
        var rub = Math.floor(kop / 100), c = kop % 100;
        return c === 0 ? String(rub) : rub + ',' + (c < 10 ? '0' : '') + c;
    }
    function exportCashCsv() {
        if (!cashReg) { S.showToast('Месяц ещё загружается, попробуй через секунду', true); return; }
        var rows = cashRows();
        if (!rows.length) { S.showToast('Выгружать нечего: таблица пуста', true); return; }
        var labels = cashReg.problem_labels || {};
        var lines;
        if (cashView === 'expense') {
            lines = [['Дата', 'Точка', 'Бармен', 'Трата из кассы, руб', 'На что']]
                .concat(rows.map(function (r) {
                    return [S.formatDateHuman(r.date), r.location_short, cashRowName(r),
                        kopToRubCsv(r.expense_kop), r.expense_note || ''];
                }));
        } else if (cashView === 'collection') {
            lines = [['Дата', 'Точка', 'Бармен', 'Инкассация, руб']]
                .concat(rows.map(function (r) {
                    return [S.formatDateHuman(r.date), r.location_short, cashRowName(r),
                        kopToRubCsv(r.collection_kop)];
                }));
        } else {
            lines = [['Дата', 'Точка', 'Бармен', 'Смена', 'Траты, руб', 'На что',
                      'Инкассация, руб', 'Наличные на конец, руб', 'Проблема',
                      'Штраф', 'Причина штрафа']]
                .concat(rows.map(function (r) {
                    return [S.formatDateHuman(r.date), r.location_short, cashRowName(r),
                        r.shift_id == null ? '' : (r.evening ? 'вечер' : 'день'),
                        kopToRubCsv(r.expense_kop), r.expense_note || '',
                        kopToRubCsv(r.collection_kop), kopToRubCsv(r.end_kop),
                        r.problems.map(function (p) { return labels[p] || p; }).join(', '),
                        r.penalized ? 'да' : '', r.penalty_note || ''];
                }));
        }
        var csv = '\ufeff' + lines.map(function (l) { return l.map(csvField).join(';'); }).join('\r\n');
        var m = S.state.month;
        var name = 'kassa-' + CASH_VIEW_SLUG[cashView] + '-' + S.state.year + '-' + (m < 10 ? '0' : '') + m + '.csv';
        var a = document.createElement('a');
        var url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
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

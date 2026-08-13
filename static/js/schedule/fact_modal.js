/* Модалка «часы + касса на смене» — общий модуль двух страниц.

   Живёт отдельно от контроллеров, потому что этот блок вводит ДЕНЬГИ (наличные
   в сейфе, траты, инкассация) и используется в трёх местах: модалка факта на
   /schedule, модалка смены на /schedule (десктоп, правка владельцем) и личная
   страница /me, где закрытие смены — главное действие бармена. Две копии одной
   валидации («траты без комментария нельзя», «окно правок 72 часа») разъехались
   бы, а разъехавшееся правило про кассу — это спор с барменом о деньгах.

   Подключать ПОСЛЕ common.js. Даёт на window.Schedule:
     S.cashLocked(shift)                       — заморожена ли касса смены
     S.wireCashToggles(prefix)                 — тумблеры «траты/инкассация»
     S.fillCashBlock(prefix, shift, isDay)     — заполнить поля из смены
     S.readCashForSubmit(prefix, shift)        — прочитать и провалидировать
     S.sendCash(shiftId, cash)                 — PUT /api/schedule/shift/<id>/cash
     S.factModal.init({ onSaved })             — привязать модалку факта (#fact*)
     S.factModal.open(shift) / .close()
   `prefix` — префикс id полей в разметке: 'fact' (#factCashEnd) или 'shift'.
*/
(function () {
    'use strict';
    var S = window.Schedule;
    if (!S) return;

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


    // ==================== Модалка факта: часы + касса ====================
    // Разметка — #factModal в шаблоне страницы (templates/schedule.html,
    // templates/me.html). Сохранение: PUT /fact, затем PUT /cash (если есть что
    // слать). Порядок важен: часы — обязательное поле, касса — вторичное, и
    // касса не должна отменять уже записанные часы.

    var currentShift = null;
    var saving = false;
    var onSavedCb = null;

    function open(shift) {
        currentShift = shift;
        document.getElementById('factModalTitle').textContent =
            S.shiftDisplayName(shift) + ' — ' + S.formatDateHuman(shift.date)
            + ' — ' + shift.location_name;
        var input = document.getElementById('factInput');
        input.value = shift.fact_minutes != null ? S.minutesToHhMm(shift.fact_minutes) : '';
        fillCashBlock('fact', shift, !S.isEvening(shift));
        document.getElementById('factModal').classList.add('active');
        input.focus();
    }

    function close() {
        document.getElementById('factModal').classList.remove('active');
        currentShift = null;
    }

    function onSubmit(e) {
        e.preventDefault();
        if (!currentShift || saving) return;
        var minutes = S.parseHoursInput(document.getElementById('factInput').value);
        if (minutes === null || minutes < 0 || minutes > 1440) {
            S.showToast('Введи часы как 10:30 или 10.5', true); return;
        }
        // касса (дневная смена) — валидируем ДО записи
        var shift = currentShift;
        var cash = readCashForSubmit('fact', shift);
        if (!cash.ok) { S.showToast(cash.error, true); return; }
        saving = true;
        S.api('/api/schedule/shift/' + shift.id + '/fact',
              { method: 'PUT', body: { fact_minutes: minutes } })
            .then(function () { return sendCash(shift.id, cash); })
            .then(function () {
                close();
                S.showToast('Смена закрыта');
                return onSavedCb ? onSavedCb() : null;
            })
            .catch(function (err) { S.showToast('Не сохранилось: ' + err.message, true); })
            .then(function () { saving = false; });
    }

    function init(opts) {
        opts = opts || {};
        onSavedCb = opts.onSaved || null;
        var modal = document.getElementById('factModal');
        if (!modal) return;   // страница без модалки — молча ничего не делаем
        wireCashToggles('fact');
        var closeBtn = document.getElementById('factClose');
        if (closeBtn) closeBtn.addEventListener('click', close);
        modal.addEventListener('click', function (e) {
            if (e.target === modal) close();
        });
        var form = document.getElementById('factForm');
        if (form) form.addEventListener('submit', onSubmit);
    }

    S.cashLocked = cashLocked;
    S.wireCashToggles = wireCashToggles;
    S.fillCashBlock = fillCashBlock;
    S.readCashForSubmit = readCashForSubmit;
    S.sendCash = sendCash;
    S.factModal = { init: init, open: open, close: close };
})();

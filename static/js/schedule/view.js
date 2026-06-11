/* Страница /schedule — просмотр графика (для барменов).
   Без финансовых данных. Клик по смене — ввод факта отработанных часов. */

(function () {
    'use strict';

    var S = window.Schedule;
    var currentShift = null;

    document.addEventListener('DOMContentLoaded', function () {
        document.getElementById('prevMonth').addEventListener('click', function () {
            S.shiftMonth(-1); reload();
        });
        document.getElementById('nextMonth').addEventListener('click', function () {
            S.shiftMonth(1); reload();
        });

        document.getElementById('factForm').addEventListener('submit', onFactSubmit);
        document.getElementById('factClear').addEventListener('click', onFactClear);
        document.getElementById('factCancel').addEventListener('click', closeFactModal);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeFactModal();
        });

        S.showLoading(true);
        S.loadDictionaries()
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
        return S.loadMonthData()
            .then(render)
            .catch(function (err) {
                console.error(err);
                S.showToast('Ошибка загрузки месяца', true);
            })
            .then(function () { S.showLoading(false); });
    }

    function render() {
        S.renderGrid({
            gridEl: document.getElementById('scheduleGrid'),
            markHoles: true,
            showPlans: false,
            onChipClick: openFactModal
        });
    }

    // ==================== Факт часов ====================
    // Вводится барменом руками в конце смены: смена может длиться дольше
    // кассовой, поэтому по API факт часов не вытащить. Это единственный
    // источник факта часов (зарплата, нагрузка).

    function openFactModal(shift) {
        currentShift = shift;
        document.getElementById('factModalTitle').textContent =
            shift.employee_name + ' — ' + S.formatDateHuman(shift.date)
            + ' — ' + shift.location_name;
        var input = document.getElementById('factInput');
        input.value = shift.fact_minutes != null
            ? S.minutesToHhMm(shift.fact_minutes) : '';
        document.getElementById('factModal').classList.add('active');
        input.focus();
    }

    function closeFactModal() {
        document.getElementById('factModal').classList.remove('active');
        currentShift = null;
    }

    function onFactSubmit(e) {
        e.preventDefault();
        if (!currentShift) return;
        var raw = document.getElementById('factInput').value;
        var minutes = S.parseHoursInput(raw);
        if (minutes === null || minutes < 0 || minutes > 1440) {
            S.showToast('Введи часы как 10:30 или 10.5', true);
            return;
        }
        S.api('/api/schedule/shift/' + currentShift.id + '/fact', {
            method: 'PUT',
            body: { fact_minutes: minutes }
        }).then(function () {
            closeFactModal();
            S.showToast('Часы сохранены');
            reload();
        }).catch(function (err) {
            S.showToast('Не сохранилось: ' + err.message, true);
        });
    }

    function onFactClear() {
        if (!currentShift) return;
        S.api('/api/schedule/shift/' + currentShift.id + '/fact', {
            method: 'PUT',
            body: { fact_minutes: null }
        }).then(function () {
            closeFactModal();
            S.showToast('Часы очищены');
            reload();
        }).catch(function (err) {
            S.showToast('Ошибка: ' + err.message, true);
        });
    }
})();

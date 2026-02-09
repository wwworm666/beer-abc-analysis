/**
 * Datepicker модуль (Flatpickr)
 * Управление выбором периодов через календарь
 */

import { state } from '../core/state.js';

let flatpickrInstance = null;

/**
 * Инициализация Flatpickr
 */
function initFlatpickr() {
    const input = document.getElementById('flexi-range-picker');
    if (!input || typeof flatpickr === 'undefined') {
        console.warn('Flatpickr не найден');
        return;
    }

    // Получаем даты прошлой недели для установки по умолчанию
    const defaultDates = getQuickPeriodDates('7');
    const defaultRange = defaultDates ? [
        defaultDates.dateFromRaw,
        defaultDates.dateToRaw
    ] : null;

    // Создаем экземпляр Flatpickr в режиме range
    flatpickrInstance = flatpickr(input, {
        mode: 'range',
        dateFormat: 'd.m.Y',
        locale: 'ru',  // Русская локаль (подключена через l10n/ru.js)
        maxDate: '2026-12-31',  // Разрешаем выбор будущих дат для просмотра планов
        defaultDate: defaultRange,  // Устанавливаем прошлую неделю по умолчанию
        onChange: function(selectedDates, dateStr, instance) {
            console.log('Flatpickr onChange:', selectedDates, dateStr);

            if (selectedDates.length === 2) {
                const dateFrom = formatDateForAPI(selectedDates[0]);
                const dateTo = formatDateForAPI(selectedDates[1]);

                const displayFrom = formatDateForDisplay(selectedDates[0]);
                const displayTo = formatDateForDisplay(selectedDates[1]);
                const label = `${displayFrom} - ${displayTo}`;

                console.log('Применяем период:', dateFrom, '-', dateTo);

                applyPeriod(dateFrom, dateTo, label);
            }
        }
    });

    console.log('Flatpickr инициализирован');

    // Если установлен defaultRange, применяем этот период сразу
    if (defaultDates) {
        console.log('Применяем дефолтный период:', defaultDates.from, '-', defaultDates.to);
        applyPeriod(defaultDates.from, defaultDates.to, defaultDates.label);
    }
}

/**
 * Форматирование даты в формат YYYY-MM-DD для API
 */
function formatDateForAPI(date) {
    const d = new Date(date);

    // Проверяем валидность даты
    if (isNaN(d.getTime())) {
        console.error('formatDateForAPI: Invalid date:', date);
        return null;
    }

    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * Форматирование даты в формат dd.MM.yyyy для отображения
 */
function formatDateForDisplay(date) {
    const d = new Date(date);

    if (isNaN(d.getTime())) {
        console.error('formatDateForDisplay: Invalid date:', date);
        return '';
    }

    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${day}.${month}.${year}`;
}

/**
 * Получить даты для быстрого периода
 */
function getQuickPeriodDates(period) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    let dateFrom, dateTo;

    switch(period) {
        case '7':
            // Прошлая неделя (пн-вс)
            const dayOfWeek = today.getDay(); // 0 = вс, 1 = пн, ..., 6 = сб
            const daysFromMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;

            // Понедельник прошлой недели
            dateFrom = new Date(today);
            dateFrom.setDate(today.getDate() - daysFromMonday - 7);

            // Воскресенье прошлой недели
            dateTo = new Date(dateFrom);
            dateTo.setDate(dateFrom.getDate() + 6);
            break;

        case 'prev-month':
            // Прошлый месяц (полностью)
            const prevMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            dateFrom = new Date(prevMonth);
            dateTo = new Date(today.getFullYear(), today.getMonth(), 0);
            break;

        default:
            return null;
    }

    return {
        from: formatDateForAPI(dateFrom),
        to: formatDateForAPI(dateTo),
        dateFromRaw: new Date(dateFrom),
        dateToRaw: new Date(dateTo),
        label: getQuickPeriodLabel(period, dateFrom, dateTo)
    };
}

/**
 * Получить человекочитаемое название периода
 */
function getQuickPeriodLabel(period, dateFrom, dateTo) {
    const formatDate = (d) => {
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
    };

    switch(period) {
        case '7':
            return `Прошлая неделя (${formatDate(dateFrom)} - ${formatDate(dateTo)})`;
        case 'prev-month':
            return `Прошлый месяц (${formatDate(dateFrom)} - ${formatDate(dateTo)})`;
        default:
            return '';
    }
}

/**
 * Применить выбранный период
 */
function applyPeriod(dateFrom, dateTo, label) {
    // Проверяем валидность дат
    if (!dateFrom || !dateTo || dateFrom === null || dateTo === null) {
        console.error('applyPeriod: Invalid dates:', dateFrom, dateTo);
        state.addMessage('error', 'Ошибка: невалидные даты');
        return;
    }

    console.log('Применяем период:', dateFrom, '-', dateTo);

    // Обновляем state
    state.setPeriod({
        key: 'custom',
        start: dateFrom,
        end: dateTo,
        label: label || `${dateFrom} - ${dateTo}`
    });

    // Показываем уведомление
    state.addMessage('success', `Период: ${label || dateFrom + ' - ' + dateTo}`);
}

/**
 * Главная функция инициализации модуля
 */
export function init() {
    console.log('Инициализация DatePicker модуля...');

    // Ждем пока Flatpickr библиотека загрузится
    if (typeof flatpickr !== 'undefined') {
        initFlatpickr();
    } else {
        // Fallback: ждем 500ms
        setTimeout(() => {
            if (typeof flatpickr !== 'undefined') {
                initFlatpickr();
            } else {
                console.error('Flatpickr библиотека не загрузилась');
            }
        }, 500);
    }
}

// Экспортируем для использования в других модулях
export const datepickerModule = {
    init
};

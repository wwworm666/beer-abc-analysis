/**
 * Модель периода дашборда — обёртка над общим ядром стандарта периодов.
 *
 * С 2026-11-01 арифметика дат, подписи и правила открытия живут в одном месте для всего
 * сайта: static/js/shared/period/period_core.js (window.KPeriod, зеркало core/periods.py,
 * docs/period-standard.md). Модули дашборда импортируют отсюда, как раньше.
 *
 * Отличия от прежней модели (до 2026-11-01): «сегодня» — учётный день бара с сервера
 * (window.DASHBOARD_PERIOD, рабочие сутки до 06:00 МСК), а не часы устройства; название
 * периода всегда с годом; смена шага берёт период, где лежит конец текущего.
 *
 * Ядро подключено обычным скриптом в templates/dashboard.html ДО модулей, поэтому к
 * моменту импорта window.KPeriod уже есть.
 */

const K = window.KPeriod;

export const GRANULARITIES = K.GRANULARITIES;
export const CUSTOM = K.CUSTOM;

export const startOfDay = K.startOfDay;
export const toISO = K.toISO;
export const fromISO = K.fromISO;
export const addDays = K.addDays;
export const addMonths = K.addMonths;
export const daysInMonth = K.daysInMonth;
export const daysBetweenInclusive = K.daysBetweenInclusive;
export const startOfWeek = K.startOfWeek;
export const isoWeekNumber = K.isoWeekNumber;

/** Учётный день бара с сервера (core/periods.page_config), а не часы устройства. */
export const today = K.today;

export const periodFor = K.periodFor;
export const customPeriod = K.customPeriod;
export const fromBounds = K.fromBounds;
export const shiftPeriod = K.shiftPeriod;
export const changeGranularity = K.changeGranularity;
export const detectGranularity = K.detectGranularity;
export const periodFromSelection = K.periodFromSelection;
export const periodTitle = K.periodTitle;
export const periodShort = K.periodShort;
export const periodSub = K.periodSub;
export const periodState = K.periodState;
export const progressBadge = K.progressBadge;
export const pluralDays = K.pluralDays;
export const monthYearOf = K.monthYearOf;
export const lastClosed = K.lastClosed;

/**
 * Период по умолчанию — ТЕКУЩАЯ неделя (пн–вс) по учётному дню с сервера: ответ владельца Р2
 * (2026-11-01) — без выбора везде текущий период шага страницы. Обычно дашборд получает период
 * из общей полосы (window.KStrip, то же правило на сервере — core/scope.page_default); эта
 * функция — запасной путь без полосы. План идущей недели — по прошедшим дням (вкладка «Выручка»).
 */
export function defaultPeriod() {
    return K.currentPeriod('week');
}

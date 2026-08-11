/**
 * Модель периода дашборда — чистые функции над датами, без DOM и без state.
 *
 * Единственный источник правды о том, что такое «день/неделя/месяц/год»,
 * как выглядит шаг стрелки и как период подписывается на экране.
 *
 * Правила (детерминированы, см. .claude/CLAUDE.md §1):
 *   day    — один календарный день
 *   week   — понедельник..воскресенье (ISO-8601, неделя начинается с пн)
 *   month  — 1-е..последнее число календарного месяца
 *   year   — 1 января..31 декабря календарного года
 *   custom — произвольный диапазон, выбранный в календаре руками
 *
 * Шаг стрелки: day +-1 день, week +-7 дней, month +-1 календарный месяц,
 * year +-1 календарный год, custom — сдвиг окна на собственную длину периода
 * (выбрал 10 дней -> листаешь по 10 дней).
 *
 * Все даты — ЛОКАЛЬНЫЕ, формат обмена 'YYYY-MM-DD', границы ИНКЛЮЗИВНЫЕ
 * (сдвиг end+1 для OLAP делает сервер, см. routes/dashboard.py и docs/lessons.md).
 * Объект Date здесь всегда нормализован на полночь локального дня.
 */

export const GRANULARITIES = ['day', 'week', 'month', 'year'];

/** Гранулярность, у которой нет своей кнопки: произвольный диапазон из календаря. */
export const CUSTOM = 'custom';

const MONTHS_NOMINATIVE = [
    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
];

const MONTHS_GENITIVE = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
];

const MONTHS_SHORT = [
    'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'
];

const WEEKDAYS_SHORT = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

// ============================================================
// Базовые операции над датами
// ============================================================

/** Нормализовать Date на полночь локального дня (копия, исходник не мутируется). */
export function startOfDay(date) {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    return d;
}

/** Сегодня, нормализованное на полночь. */
export function today() {
    return startOfDay(new Date());
}

/** Date -> 'YYYY-MM-DD' (локальные компоненты, без UTC-сдвига). */
export function toISO(date) {
    const d = startOfDay(date);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

/**
 * 'YYYY-MM-DD' -> Date (локальная полночь).
 * Через new Date(y, m, d), а НЕ new Date(строка): строковый ISO парсится как UTC
 * и в положительных таймзонах уезжает на день назад.
 */
export function fromISO(iso) {
    if (!iso || typeof iso !== 'string') return null;
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return isNaN(d.getTime()) ? null : d;
}

/** Прибавить дни (может быть отрицательным). */
export function addDays(date, days) {
    const d = startOfDay(date);
    d.setDate(d.getDate() + days);
    return d;
}

/**
 * Прибавить месяцы с зажимом числа: 31 января + 1 месяц = 28/29 февраля,
 * а не 2/3 марта (штатное поведение Date.setMonth переполняет месяц).
 */
export function addMonths(date, months) {
    const d = startOfDay(date);
    const day = d.getDate();
    d.setDate(1);
    d.setMonth(d.getMonth() + months);
    d.setDate(Math.min(day, daysInMonth(d.getFullYear(), d.getMonth())));
    return d;
}

/** Число дней в месяце (month — 0..11). */
export function daysInMonth(year, month) {
    return new Date(year, month + 1, 0).getDate();
}

/** Инклюзивное число календарных дней между двумя датами. */
export function daysBetweenInclusive(startDate, endDate) {
    const a = startOfDay(startDate).getTime();
    const b = startOfDay(endDate).getTime();
    // Округление снимает погрешность перехода на летнее время (сутки != 24ч).
    return Math.round((b - a) / 86400000) + 1;
}

/** Понедельник недели, содержащей дату (ISO: пн=начало, вс=конец). */
export function startOfWeek(date) {
    const d = startOfDay(date);
    const dow = d.getDay();              // 0=вс, 1=пн, ... 6=сб
    const shift = dow === 0 ? 6 : dow - 1; // сколько дней назад до понедельника
    return addDays(d, -shift);
}

/** Номер ISO-недели (1..53). */
export function isoWeekNumber(date) {
    // Четверг той же недели однозначно определяет ISO-год и номер недели: 4 января
    // по определению лежит в первой неделе, поэтому её четверг — точка отсчёта.
    const thursday = addDays(startOfWeek(date), 3);
    const firstThursday = addDays(startOfWeek(new Date(thursday.getFullYear(), 0, 4)), 3);
    // daysBetweenInclusive считает обе границы, здесь нужна чистая разница дней.
    const daysApart = daysBetweenInclusive(firstThursday, thursday) - 1;
    return Math.round(daysApart / 7) + 1;
}

// ============================================================
// Построение периода
// ============================================================

/**
 * Период выбранной гранулярности, содержащий якорную дату.
 *
 * @param {string} granularity — 'day' | 'week' | 'month' | 'year'
 * @param {Date} anchor — любая дата внутри искомого периода
 * @returns {{granularity: string, start: string, end: string}} границы инклюзивные
 */
export function periodFor(granularity, anchor) {
    const a = startOfDay(anchor);

    switch (granularity) {
        case 'day':
            return build('day', a, a);

        case 'week': {
            const start = startOfWeek(a);
            return build('week', start, addDays(start, 6));
        }

        case 'month': {
            const start = new Date(a.getFullYear(), a.getMonth(), 1);
            const end = new Date(a.getFullYear(), a.getMonth(), daysInMonth(a.getFullYear(), a.getMonth()));
            return build('month', start, end);
        }

        case 'year': {
            const start = new Date(a.getFullYear(), 0, 1);
            const end = new Date(a.getFullYear(), 11, 31);
            return build('year', start, end);
        }

        default:
            // Неизвестная гранулярность трактуется как один день — безопасный минимум.
            return build('day', a, a);
    }
}

/** Произвольный диапазон из календаря. Порядок дат нормализуется. */
export function customPeriod(startDate, endDate) {
    let s = startOfDay(startDate);
    let e = startOfDay(endDate);
    if (s > e) [s, e] = [e, s];
    return build(CUSTOM, s, e);
}

/**
 * Собрать объект периода в форме, которую ждёт state и все подписчики.
 *
 * key намеренно имеет формат 'YYYY-MM-DD_YYYY-MM-DD' (как WeeksGenerator.period_to_key):
 *   - совпадает с ключами недель из /api/weeks -> charts.js/trends.js продолжают
 *     находить неделю по ключу;
 *   - НЕ похож на ключ плана ('YYYY-MM' или 'venue_YYYY-MM'), поэтому запись
 *     комментария периода (routes/dashboard.py:756) физически не может попасть
 *     в боевой план;
 *   - безопасен для имени файла экспорта (core/export_manager.py:224).
 */
function build(granularity, startDate, endDate) {
    const start = toISO(startDate);
    const end = toISO(endDate);
    return {
        granularity,
        start,
        end,
        key: `${start}_${end}`,
        label: formatLabel(granularity, startDate, endDate)
    };
}

/**
 * Период по умолчанию — ПОСЛЕДНЯЯ ЗАВЕРШЁННАЯ неделя (пн-вс).
 *
 * Почему не текущая: у незавершённой недели факт есть лишь за прошедшие дни,
 * а план урезается пропорционально всему периоду — процент выполнения выглядит
 * провалом. Открываем на периоде, который уже закрыт и сравним с планом честно.
 */
export function defaultPeriod(now = today()) {
    return periodFor('week', addDays(startOfWeek(now), -7));
}

/** Период текущей гранулярности, содержащий сегодня. */
export function currentPeriodFor(granularity, now = today()) {
    if (granularity === CUSTOM) return null;
    return periodFor(granularity, now);
}

// ============================================================
// Навигация
// ============================================================

/**
 * Сдвинуть период на direction шагов своей гранулярности (-1 назад, +1 вперёд).
 * Для custom шаг равен длине самого периода.
 */
export function shiftPeriod(period, direction) {
    const start = fromISO(period.start);
    const end = fromISO(period.end);
    if (!start || !end) return period;

    switch (period.granularity) {
        case 'day':
            return periodFor('day', addDays(start, direction));
        case 'week':
            return periodFor('week', addDays(start, direction * 7));
        case 'month':
            return periodFor('month', addMonths(start, direction));
        case 'year':
            return periodFor('year', new Date(start.getFullYear() + direction, 0, 1));
        default: {
            const len = daysBetweenInclusive(start, end);
            return customPeriod(addDays(start, direction * len), addDays(end, direction * len));
        }
    }
}

/**
 * Сменить гранулярность, оставшись «примерно там же»: якорем берётся начало
 * текущего периода, но если период содержит сегодня — якорем становится сегодня
 * (иначе переход неделя->день с текущей недели уводил бы на понедельник).
 */
export function changeGranularity(period, granularity, now = today()) {
    const start = fromISO(period?.start) || now;
    const end = fromISO(period?.end) || now;
    const anchor = (now >= start && now <= end) ? now : start;
    return periodFor(granularity, anchor);
}

// ============================================================
// Подписи
// ============================================================

/** Человекочитаемая подпись периода для центральной части панели. */
export function formatLabel(granularity, startDate, endDate) {
    const s = startOfDay(startDate);
    const e = startOfDay(endDate);

    if (granularity === 'day') {
        return `${WEEKDAYS_SHORT[s.getDay()]}, ${s.getDate()} ${MONTHS_GENITIVE[s.getMonth()]} ${s.getFullYear()}`;
    }

    if (granularity === 'month') {
        return `${MONTHS_NOMINATIVE[s.getMonth()]} ${s.getFullYear()}`;
    }

    if (granularity === 'year') {
        return `${s.getFullYear()}`;
    }

    // week и custom — диапазон, схлопываем повторяющиеся месяц/год
    if (s.getFullYear() === e.getFullYear()) {
        if (s.getMonth() === e.getMonth()) {
            return `${s.getDate()} - ${e.getDate()} ${MONTHS_GENITIVE[s.getMonth()]} ${s.getFullYear()}`;
        }
        return `${s.getDate()} ${MONTHS_SHORT[s.getMonth()]} - ${e.getDate()} ${MONTHS_SHORT[e.getMonth()]} ${s.getFullYear()}`;
    }
    return `${s.getDate()} ${MONTHS_SHORT[s.getMonth()]} ${s.getFullYear()} - ` +
           `${e.getDate()} ${MONTHS_SHORT[e.getMonth()]} ${e.getFullYear()}`;
}

/** Вторая строка панели: сколько дней и (для недели) её номер. */
export function formatSubLabel(period) {
    const start = fromISO(period.start);
    const end = fromISO(period.end);
    if (!start || !end) return '';

    const days = daysBetweenInclusive(start, end);
    const dayWord = pluralDays(days);

    if (period.granularity === 'week') return `неделя ${isoWeekNumber(start)} · ${days} ${dayWord}`;
    if (period.granularity === CUSTOM) return `произвольный · ${days} ${dayWord}`;
    return `${days} ${dayWord}`;
}

/** Склонение слова «день» по числу. */
export function pluralDays(n) {
    const abs = Math.abs(n) % 100;
    const last = abs % 10;
    if (abs > 10 && abs < 20) return 'дней';
    if (last === 1) return 'день';
    if (last >= 2 && last <= 4) return 'дня';
    return 'дней';
}

// ============================================================
// Завершённость периода (защита от «периода, который ещё не прошёл»)
// ============================================================

/**
 * Насколько период прошёл на сегодняшний день.
 *
 * Считается по КАЛЕНДАРНЫМ дням; сегодняшний день считается прошедшим целиком
 * (данные за него неполные — касса ещё не закрыта). Это оценка «на глаз» для
 * предупреждения, а не основа расчётов: план урезается сервером по ВЗВЕШЕННЫМ
 * дням (пт/сб = 2.0, core/day_weights.py), поэтому доли расходятся — на коротких
 * периодах заметно. Бейдж существует, чтобы пользователь не принял недобор
 * незавершённого периода за провал плана.
 *
 * @returns {{elapsed: number, total: number, isComplete: boolean, isFuture: boolean}}
 */
export function periodProgress(period, now = today()) {
    const start = fromISO(period.start);
    const end = fromISO(period.end);
    if (!start || !end) return { elapsed: 0, total: 0, isComplete: true, isFuture: false };

    const total = daysBetweenInclusive(start, end);

    if (now > end) return { elapsed: total, total, isComplete: true, isFuture: false };
    if (now < start) return { elapsed: 0, total, isComplete: false, isFuture: true };

    return {
        elapsed: daysBetweenInclusive(start, now),
        total,
        isComplete: false,
        isFuture: false
    };
}

/** Текст бейджа незавершённого периода; null — период закрыт, бейдж не нужен. */
export function progressBadge(period, now = today()) {
    const p = periodProgress(period, now);
    if (p.isComplete) return null;
    if (p.isFuture) return 'период ещё не начался';
    return `прошло ${p.elapsed} из ${p.total} ${pluralDays(p.total)}`;
}

// ============================================================
// Распознавание периода, выбранного в календаре
// ============================================================

/**
 * Определить, совпадает ли произвольный диапазон с натуральными границами
 * какой-либо гранулярности. Нужно, чтобы выбор «01.08 - 31.08» в календаре
 * остался месяцем (со стрелками по месяцам), а не стал произвольным периодом.
 *
 * @returns {string|null} гранулярность или null, если диапазон произвольный
 */
export function detectGranularity(startDate, endDate) {
    const s = startOfDay(startDate);
    const e = startOfDay(endDate);
    for (const g of GRANULARITIES) {
        const p = periodFor(g, s);
        if (p.start === toISO(s) && p.end === toISO(e)) return g;
    }
    return null;
}

/**
 * Собрать период из выбора в календаре.
 * Один день при активной гранулярности week/month/year трактуется как ЯКОРЬ
 * (клик по 15 августа при активном «Месяц» = весь август), а не как один день.
 */
export function periodFromSelection(startDate, endDate, activeGranularity) {
    const s = startOfDay(startDate);
    const e = startOfDay(endDate || startDate);

    if (toISO(s) === toISO(e) && activeGranularity && activeGranularity !== CUSTOM
        && activeGranularity !== 'day') {
        return periodFor(activeGranularity, s);
    }

    const detected = detectGranularity(s, e);
    return detected ? periodFor(detected, s) : customPeriod(s, e);
}

/** Месяц ('01'..'12') и год (число) периода — для месячных вкладок. */
export function monthYearOf(period) {
    const start = fromISO(period.start);
    if (!start) return null;
    return {
        month: String(start.getMonth() + 1).padStart(2, '0'),
        year: start.getFullYear()
    };
}

/**
 * Ядро стандарта периодов на странице (docs/period-standard.md) — чистые функции над датами.
 *
 * Зеркало core/periods.py: те же шаги, подписи, состояния и правило «последний закрытый».
 * Обе стороны проверяются одним набором примеров (tests/fixtures/period_labels.json).
 *
 * Правила:
 *   - даты обмена 'YYYY-MM-DD', границы ВКЛЮЧИТЕЛЬНЫЕ; Date внутри — местная полночь;
 *   - шаги: day, week (ISO, пн–вс), month, quarter, year; иначе custom (свой период);
 *   - «сегодня» и последний полный день — с сервера (configure), а не часы устройства:
 *     у телефона может стоять другой часовой пояс, и рабочие сутки бара идут до 06:00 МСК;
 *   - состояние: complete (весь не позже последнего полного дня), partial («идёт»), future.
 *
 * Обычный скрипт без модулей: window.KPeriod; для Node-тестов — module.exports. Дашборд
 * (ES-модули) берёт то же через static/js/dashboard/core/period_model.js.
 */
(function (root, factory) {
    var api = factory();
    root.KPeriod = api;
    if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    var GRANULARITIES = ['day', 'week', 'month', 'quarter', 'year'];
    var CUSTOM = 'custom';
    var MONTHS_NOMINATIVE = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август',
        'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
    var MONTHS_GENITIVE = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
        'сентября', 'октября', 'ноября', 'декабря'];
    var MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    var QUARTER_ROMAN = ['I', 'II', 'III', 'IV'];
    var DASH = ' – ';   // тире диапазона — одно на сайт, как core/periods.DASH

    // ------------------------------------------------------------ даты

    function startOfDay(date) {
        var d = new Date(date);
        d.setHours(0, 0, 0, 0);
        return d;
    }
    function pad(n) { return String(n).padStart(2, '0'); }
    function toISO(date) {
        var d = startOfDay(date);
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }
    // new Date(y, m, d), а не new Date(строка): строка ISO читается как UTC и в Москве
    // уезжает на день назад (из-за этого «Сравнение» не находило неделю по воскресеньям).
    function fromISO(iso) {
        if (!iso || typeof iso !== 'string') return null;
        var m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!m) return null;
        var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
        if (isNaN(d.getTime()) || d.getMonth() !== Number(m[2]) - 1) return null;
        return d;
    }
    function addDays(date, days) {
        var d = startOfDay(date);
        d.setDate(d.getDate() + days);
        return d;
    }
    function daysInMonth(year, month) { return new Date(year, month + 1, 0).getDate(); }
    // 31 января + 1 месяц = 28/29 февраля, а не 2/3 марта.
    function addMonths(date, months) {
        var d = startOfDay(date);
        var day = d.getDate();
        d.setDate(1);
        d.setMonth(d.getMonth() + months);
        d.setDate(Math.min(day, daysInMonth(d.getFullYear(), d.getMonth())));
        return d;
    }
    function daysBetweenInclusive(a, b) {
        // Округление снимает погрешность перехода на летнее время (сутки не 24 ч).
        return Math.round((startOfDay(b).getTime() - startOfDay(a).getTime()) / 86400000) + 1;
    }
    function startOfWeek(date) {
        var d = startOfDay(date);
        var dow = d.getDay();
        return addDays(d, dow === 0 ? -6 : 1 - dow);
    }
    function isoWeekNumber(date) {
        var thursday = addDays(startOfWeek(date), 3);
        var firstThursday = addDays(startOfWeek(new Date(thursday.getFullYear(), 0, 4)), 3);
        return Math.round((daysBetweenInclusive(firstThursday, thursday) - 1) / 7) + 1;
    }
    function minDate(a, b) { return a <= b ? a : b; }
    // Дата из Date или 'YYYY-MM-DD'; пусто — null.
    function asDate(x) {
        if (!x) return null;
        return typeof x === 'string' ? fromISO(x) : startOfDay(x);
    }

    // ------------------------------------------------------------ часы страницы

    // Даты страницы с сервера (core/periods.page_config): today — учётный день, last_full_day —
    // последний полный день данных, max_date — последний доступный день. Без настройки —
    // часы устройства (запасной путь; страницы стандарта всегда настраивают).
    var clock = { today: null, lastFullDay: null, maxDate: null, dataStart: null };

    function configure(cfg) {
        cfg = cfg || {};
        clock.today = fromISO(cfg.today) || null;
        clock.lastFullDay = fromISO(cfg.last_full_day) || null;
        clock.maxDate = fromISO(cfg.max_date) || null;
        clock.dataStart = fromISO(cfg.data_start) || null;
    }
    function today() { return clock.today ? new Date(clock.today) : startOfDay(new Date()); }
    function lastFullDay() { return clock.lastFullDay ? new Date(clock.lastFullDay) : addDays(today(), -1); }
    function maxDate() { return clock.maxDate ? new Date(clock.maxDate) : today(); }
    function dataStart() { return clock.dataStart ? new Date(clock.dataStart) : null; }

    // ------------------------------------------------------------ период

    function build(granularity, s, e) {
        var start = toISO(s), end = toISO(e);
        return { granularity: granularity, start: start, end: end, key: start + '_' + end,
                 label: periodTitleOf(granularity, startOfDay(s), startOfDay(e)) };
    }
    function periodFor(granularity, anchor) {
        var a = startOfDay(anchor);
        switch (granularity) {
            case 'week': {
                var ws = startOfWeek(a);
                return build('week', ws, addDays(ws, 6));
            }
            case 'month':
                return build('month', new Date(a.getFullYear(), a.getMonth(), 1),
                    new Date(a.getFullYear(), a.getMonth(), daysInMonth(a.getFullYear(), a.getMonth())));
            case 'quarter': {
                var q = Math.floor(a.getMonth() / 3) * 3;
                return build('quarter', new Date(a.getFullYear(), q, 1),
                    new Date(a.getFullYear(), q + 2, daysInMonth(a.getFullYear(), q + 2)));
            }
            case 'year':
                return build('year', new Date(a.getFullYear(), 0, 1), new Date(a.getFullYear(), 11, 31));
            default:
                return build('day', a, a);
        }
    }
    function detectGranularity(startDate, endDate) {
        var s = startOfDay(startDate), e = startOfDay(endDate);
        for (var i = 0; i < GRANULARITIES.length; i++) {
            var p = periodFor(GRANULARITIES[i], s);
            if (p.start === toISO(s) && p.end === toISO(e)) return GRANULARITIES[i];
        }
        return null;
    }
    function customPeriod(startDate, endDate) {
        var s = startOfDay(startDate), e = startOfDay(endDate);
        if (s > e) { var t = s; s = e; e = t; }
        return build(CUSTOM, s, e);
    }
    // Период по границам: шаг определяется сам (1–31 окт — месяц).
    function fromBounds(startDate, endDate) {
        var s = startOfDay(startDate), e = startOfDay(endDate);
        if (s > e) { var t = s; s = e; e = t; }
        var g = detectGranularity(s, e);
        return g ? periodFor(g, s) : build(CUSTOM, s, e);
    }
    function shiftPeriod(period, direction) {
        var s = fromISO(period.start), e = fromISO(period.end);
        if (!s || !e) return period;
        switch (period.granularity) {
            case 'day': return periodFor('day', addDays(s, direction));
            case 'week': return periodFor('week', addDays(s, direction * 7));
            case 'month': return periodFor('month', addMonths(s, direction));
            case 'quarter': return periodFor('quarter', addMonths(s, direction * 3));
            case 'year': return periodFor('year', new Date(s.getFullYear() + direction, 0, 1));
            default: {
                var len = daysBetweenInclusive(s, e);
                return customPeriod(addDays(s, direction * len), addDays(e, direction * len));
            }
        }
    }
    // Последний закрытый период шага (правило отчётов): целиком не позже последнего полного дня.
    function lastClosed(granularity, lfd) {
        var day = asDate(lfd) || lastFullDay();
        var p = periodFor(granularity, day);
        return fromISO(p.end) <= day ? p : periodFor(granularity, addDays(fromISO(p.start), -1));
    }
    // Текущий период шага — где лежит последний доступный день (у живых данных — сегодня).
    function currentPeriod(granularity, max) {
        return periodFor(granularity, asDate(max) || maxDate());
    }
    // Последние n полных дней: ровно n дат, последняя — последний полный день.
    function lastDays(n, lfd) {
        var end = asDate(lfd) || lastFullDay();
        return fromBounds(addDays(end, -(n - 1)), end);
    }
    // Смена шага: период нового шага, где лежит конец текущего (у идущего — последний
    // доступный день). Из октября «по 29.10» в недели — неделя 26 окт – 1 ноя, а не неделя 1-го.
    function changeGranularity(period, granularity, max) {
        var end = fromISO(period && period.end) || maxDate();
        var limit = asDate(max) || maxDate();
        return periodFor(granularity, minDate(end, limit));
    }

    // ------------------------------------------------------------ состояние

    // Как core/periods.period_state: без max_date верх — последний полный день (если он
    // передан) или последний доступный день страницы.
    function bounds(lfd, max) {
        var full = asDate(lfd) || lastFullDay();
        var top = asDate(max) || (asDate(lfd) ? full : maxDate());
        return { full: full, top: top };
    }
    function periodState(period, lfd, max) {
        var s = fromISO(period.start), e = fromISO(period.end), b = bounds(lfd, max);
        if (s > b.top) return 'future';
        if (e <= b.full) return 'complete';
        return 'partial';
    }
    function cutoffOf(period, lfd, max) {
        var s = fromISO(period.start), e = fromISO(period.end), b = bounds(lfd, max);
        if (s > b.top) return null;
        return toISO(minDate(e, b.top));
    }

    // ------------------------------------------------------------ подписи

    function rangeTitle(s, e) {
        if (s.getFullYear() === e.getFullYear()) {
            if (s.getMonth() === e.getMonth()) {
                return s.getDate() + DASH + e.getDate() + ' ' + MONTHS_SHORT[s.getMonth()] + ' ' + s.getFullYear();
            }
            return s.getDate() + ' ' + MONTHS_SHORT[s.getMonth()] + DASH + e.getDate() + ' ' +
                MONTHS_SHORT[e.getMonth()] + ' ' + e.getFullYear();
        }
        return s.getDate() + ' ' + MONTHS_SHORT[s.getMonth()] + ' ' + s.getFullYear() + DASH +
            e.getDate() + ' ' + MONTHS_SHORT[e.getMonth()] + ' ' + e.getFullYear();
    }
    function capitalize(w) { return w.charAt(0).toUpperCase() + w.slice(1); }
    function periodTitleOf(g, s, e) {
        if (g === 'day') return s.getDate() + ' ' + MONTHS_GENITIVE[s.getMonth()] + ' ' + s.getFullYear();
        if (g === 'month') return capitalize(MONTHS_NOMINATIVE[s.getMonth()]) + ' ' + s.getFullYear();
        if (g === 'quarter') return QUARTER_ROMAN[Math.floor(s.getMonth() / 3)] + ' квартал ' + s.getFullYear();
        if (g === 'year') return String(s.getFullYear());
        return rangeTitle(s, e);
    }
    // Название — всегда с годом: «Октябрь 2026», «26 окт – 1 ноя 2026», «IV квартал 2026».
    function periodTitle(period) {
        var s = fromISO(period.start), e = fromISO(period.end);
        return s && e ? periodTitleOf(period.granularity, s, e) : '';
    }
    // Короткое название для заголовков карточек: «окт 26», «26.10–01.11».
    function periodShort(period) {
        var s = fromISO(period.start), e = fromISO(period.end);
        if (!s || !e) return '';
        var dm = function (d) { return pad(d.getDate()) + '.' + pad(d.getMonth() + 1); };
        var yy = function (d) { return String(d.getFullYear()).slice(2); };
        switch (period.granularity) {
            case 'day': return dm(s);
            case 'month': return MONTHS_SHORT[s.getMonth()] + ' ' + yy(s);
            case 'quarter': return QUARTER_ROMAN[Math.floor(s.getMonth() / 3)] + ' кв ' + yy(s);
            case 'year': return String(s.getFullYear());
            default: return dm(s) + '–' + dm(e);
        }
    }
    function pluralDays(n) {
        var abs = Math.abs(n) % 100, last = abs % 10;
        if (abs > 10 && abs < 20) return 'дней';
        if (last === 1) return 'день';
        if (last >= 2 && last <= 4) return 'дня';
        return 'дней';
    }
    // Вторая строка: номер недели или длина своего периода и «идёт, по ДД.ММ».
    function periodSub(period, lfd, max) {
        var parts = [];
        var s = fromISO(period.start), e = fromISO(period.end);
        if (!s || !e) return '';
        if (period.granularity === 'week') parts.push('неделя ' + isoWeekNumber(s));
        else if (period.granularity === CUSTOM) {
            var n = daysBetweenInclusive(s, e);
            parts.push(n + ' ' + pluralDays(n));
        }
        var st = periodState(period, lfd, max);
        if (st === 'partial') {
            var c = fromISO(cutoffOf(period, lfd, max));
            parts.push('идёт, по ' + pad(c.getDate()) + '.' + pad(c.getMonth() + 1));
        } else if (st === 'future') {
            parts.push('ещё не начался');
        }
        return parts.join(' · ');
    }

    // ------------------------------------------------------------ быстрый выбор

    // Общий список: страница берёт из него свой набор (по id). build() — от часов страницы.
    var QUICK = {
        today: { name: 'Сегодня', build: function () { return periodFor('day', today()); } },
        yesterday: { name: 'Вчера', build: function () { return periodFor('day', lastFullDay()); } },
        current_week: { name: 'Эта неделя', build: function () { return currentPeriod('week'); } },
        last_closed_week: { name: 'Прошлая неделя', build: function () { return lastClosed('week'); } },
        current_month: { name: 'Этот месяц', build: function () { return currentPeriod('month'); } },
        last_closed_month: { name: 'Прошлый месяц', build: function () { return lastClosed('month'); } },
        current_quarter: { name: 'Этот квартал', build: function () { return currentPeriod('quarter'); } },
        last_closed_quarter: { name: 'Прошлый квартал', build: function () { return lastClosed('quarter'); } },
        current_year: { name: 'Этот год', build: function () { return currentPeriod('year'); } },
        last_closed_year: { name: 'Прошлый год', build: function () { return lastClosed('year'); } },
        last7: { name: 'Последние 7 дней', build: function () { return lastDays(7); } },
        last30: { name: 'Последние 30 дней', build: function () { return lastDays(30); } },
        last90: { name: 'Последние 90 дней', build: function () { return lastDays(90); } },
        last180: { name: 'Последние 180 дней', build: function () { return lastDays(180); } },
        mtd: { name: 'С начала месяца', build: function () {
            var m = maxDate();
            return fromBounds(new Date(m.getFullYear(), m.getMonth(), 1), m);
        } },
        ytd: { name: 'С начала года', build: function () {
            var m = maxDate();
            return fromBounds(new Date(m.getFullYear(), 0, 1), m);
        } }
    };
    function matchQuick(period, ids) {
        if (!period) return null;
        for (var i = 0; i < ids.length; i++) {
            var q = QUICK[ids[i]];
            if (!q) continue;
            var c = q.build();
            if (c.start === period.start && c.end === period.end) return ids[i];
        }
        return null;
    }

    // ------------------------------------------------------------ адрес страницы

    // Период в адресе: ?date_from=&date_to= (включительно). Неверный — null.
    function readUrlPeriod(search) {
        var q = new URLSearchParams(search === undefined ? (root().location ? root().location.search : '') : search);
        var s = fromISO(q.get('date_from')), e = fromISO(q.get('date_to'));
        if (!s || !e) return null;
        return fromBounds(s, e);
    }
    function root() { return typeof window !== 'undefined' ? window : {}; }
    // Записать период (и бар) в адрес без новой записи истории: перезагрузка и
    // скопированная ссылка откроют то же. Остальные параметры и якорь сохраняются.
    function writeUrl(params) {
        var w = root();
        if (!w.history || !w.location) return;
        var q = new URLSearchParams(w.location.search);
        Object.keys(params).forEach(function (k) {
            var v = params[k];
            if (v === null || v === undefined || v === '') q.delete(k);
            else q.set(k, v);
        });
        var s = q.toString();
        w.history.replaceState(w.history.state, '', w.location.pathname + (s ? '?' + s : '') + w.location.hash);
    }
    function writeUrlPeriod(period) {
        writeUrl({ date_from: period ? period.start : null, date_to: period ? period.end : null });
    }

    // ------------------------------------------------------------ совместимость дашборда

    function progressBadge(period) {
        var st = periodState(period);
        if (st === 'complete') return null;
        if (st === 'future') return 'период ещё не начался';
        var s = fromISO(period.start), e = fromISO(period.end);
        var done = daysBetweenInclusive(s, fromISO(cutoffOf(period)));
        var total = daysBetweenInclusive(s, e);
        // После «из» — родительный падеж: «из 31 дня», «из 30 дней».
        var gen = (total % 10 === 1 && total % 100 !== 11) ? 'дня' : 'дней';
        return 'прошло ' + done + ' из ' + total + ' ' + gen;
    }
    function periodFromSelection(startDate, endDate, activeGranularity) {
        var s = startOfDay(startDate), e = startOfDay(endDate || startDate);
        if (toISO(s) === toISO(e) && activeGranularity && activeGranularity !== CUSTOM &&
            activeGranularity !== 'day') {
            return periodFor(activeGranularity, s);
        }
        return fromBounds(s, e);
    }
    function monthYearOf(period) {
        var s = fromISO(period.start);
        return s ? { month: pad(s.getMonth() + 1), year: s.getFullYear() } : null;
    }

    return {
        GRANULARITIES: GRANULARITIES, CUSTOM: CUSTOM, MONTHS_NOMINATIVE: MONTHS_NOMINATIVE,
        MONTHS_SHORT: MONTHS_SHORT, QUARTER_ROMAN: QUARTER_ROMAN, QUICK: QUICK,
        startOfDay: startOfDay, toISO: toISO, fromISO: fromISO, addDays: addDays, addMonths: addMonths,
        daysInMonth: daysInMonth, daysBetweenInclusive: daysBetweenInclusive, startOfWeek: startOfWeek,
        isoWeekNumber: isoWeekNumber,
        configure: configure, today: today, lastFullDay: lastFullDay, maxDate: maxDate, dataStart: dataStart,
        periodFor: periodFor, customPeriod: customPeriod, fromBounds: fromBounds,
        detectGranularity: detectGranularity, shiftPeriod: shiftPeriod, lastClosed: lastClosed,
        currentPeriod: currentPeriod, lastDays: lastDays, changeGranularity: changeGranularity,
        periodState: periodState, cutoffOf: cutoffOf, periodTitle: periodTitle, periodShort: periodShort,
        periodSub: periodSub, pluralDays: pluralDays, matchQuick: matchQuick,
        readUrlPeriod: readUrlPeriod, writeUrl: writeUrl, writeUrlPeriod: writeUrlPeriod,
        progressBadge: progressBadge, periodFromSelection: periodFromSelection, monthYearOf: monthYearOf
    };
});

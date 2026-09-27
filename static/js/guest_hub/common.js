/* Раздел «Гости» (/content-plan, /reviews, полоса на /guests) — общий модуль
   страниц: window.GH.

   Что здесь:
     - запросы к API (GH.api) с понятными ошибками по-русски;
     - справочники: бары, площадки, дни недели, месяцы;
     - форматирование дат, чисел и длительностей (без обращения к серверу);
     - общий фильтр бара между страницами раздела (localStorage 'gh.bar');
     - тосты (действие — ссылка или кнопка), диалоги подтверждения и ввода,
       выдвижная карточка, меню (стрелки ходят по пунктам, у края окна меню
       само прижимается вправо), переключатель-сегменты;
     - всплывающие подсказки по data-tip: мышью — по наведению и фокусу,
       пальцем — тапом по кружку «?» (.gh-help), повторный тап закрывает;
     - шапка (гамбургер) и полоса «требует внимания» (GH.loadAttention;
       GH.onAttention отдаёт её ответ страницам);
     - GH.api(..., {keepalive: true}) — сохранение при уходе со страницы.

   Правила расчётов (детерминированные, без Math.round-сюрпризов):
     - fmtNum округляет половину ВВЕРХ от нуля (как Decimal ROUND_HALF_UP на
       сервере): 2,45 -> 2,5; 1,005 -> 1,01 (по записи числа, а не по двоичному
       представлению), -2,5 -> −3;
     - fmtHours: меньше 1 ч -> «< 1 ч»; до 48 ч -> целые часы («5 ч»);
       от 48 ч -> целые сутки («3 д»). 48 ч — граница, после которой в часах
       теряется смысл («ответили через 71 ч» читается хуже, чем «3 д»);
     - mskNow: время Москвы через Intl (timeZone 'Europe/Moscow'); если Intl
       без поддержки зон — фиксированный сдвиг UTC+3 (в Москве нет перехода
       на летнее время с 2014 года);
     - день недели: 0 = понедельник ... 6 = воскресенье, как в Python и в API.

   Стиль: обычный IIFE, 'use strict', ES5 (var, function), без фреймворков. */
(function (root) {
    'use strict';

    var GH = {};
    var doc = typeof document !== 'undefined' ? document : null;

    // ==================== справочники ====================

    // Ключи — core/venues_config.PHYSICAL_VENUES; порядок — порядок показа.
    var BARS = [
        { key: 'bolshoy', name: 'Большой пр. В.О', short: 'ВО' },
        { key: 'ligovskiy', name: 'Лиговский', short: 'Лиг' },
        { key: 'kremenchugskaya', name: 'Кременчугская', short: 'Крем' },
        { key: 'varshavskaya', name: 'Варшавская', short: 'Вар' }
    ];
    GH.BARS = BARS;
    GH.CHANNEL_NAMES = { telegram: 'Telegram', instagram: 'Instagram', bot: 'Бот' };
    GH.CHANNEL_SHORT = { telegram: 'TG', instagram: 'IG', bot: 'Бот' };
    GH.TONES = ['muted', 'warning', 'accent', 'success', 'danger'];

    var MONTHS_NOM = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль',
                      'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    var MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                      'августа', 'сентября', 'октября', 'ноября', 'декабря'];
    var MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл',
                        'авг', 'сен', 'окт', 'ноя', 'дек'];
    var WEEKDAYS_LOWER = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
    GH.MONTHS = MONTHS_NOM;
    GH.WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

    var BAR_STORAGE_KEY = 'gh.bar';
    // Счётчики, которые показываются только когда больше нуля (спецификация, п. 3).
    var ATTN_HIDE_WHEN_ZERO = { delivery_errors: true, overdue: true };
    // Тон ненулевого счётчика: отзывы и просрочка — внимание, ошибки — опасность,
    // публикации сегодня — просто акцент (это не проблема, а план на день).
    var ATTN_TONE = {
        reviews_unanswered: 'warning',
        publications_today: 'accent',
        delivery_errors: 'danger',
        overdue: 'warning'
    };

    function byId(id) { return doc ? doc.getElementById(id) : null; }

    function findBar(key) {
        for (var i = 0; i < BARS.length; i++) {
            if (BARS[i].key === key) return BARS[i];
        }
        return null;
    }

    // '' / null — фильтр «все бары»; 'all' — размещение на всю сеть.
    GH.barName = function (key) {
        if (key === null || key === undefined || key === '') return 'Все бары';
        if (key === 'all') return 'Вся сеть';
        var bar = findBar(key);
        return bar ? bar.name : String(key);
    };
    GH.barShort = function (key) {
        if (key === null || key === undefined || key === '') return 'Все';
        if (key === 'all') return 'Сеть';
        var bar = findBar(key);
        return bar ? bar.short : String(key);
    };
    GH.isBar = function (key) { return !!findBar(key); };

    GH.toneClass = function (tone) {
        return 'gh-tone-' + (GH.TONES.indexOf(tone) >= 0 ? tone : 'muted');
    };

    // ==================== строки и числа ====================

    GH.esc = function (text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    };

    // «1 отзыв», «3 отзыва», «5 отзывов».
    GH.plural = function (n, one, few, many) {
        var abs = Math.abs(Math.round(Number(n) || 0)) % 100;
        var tail = abs % 10;
        if (abs > 10 && abs < 20) return many;
        if (tail > 1 && tail < 5) return few;
        if (tail === 1) return one;
        return many;
    };

    // Округление половины вверх (от нуля) по десятичной записи числа.
    // Сдвиг запятой делается через строку ('1.005' + 'e2' -> 100.5), а не
    // умножением (1.005 * 100 = 100.49999…), иначе 1,005 округлялось бы вниз.
    // Очень большие и очень малые числа JS пишет в экспоненте ('1e+21') —
    // строковый приём там не работает, и для них берётся обычное умножение
    // (на таких величинах ошибка двоичной дроби не видна в показанных знаках).
    function roundHalfUp(value, digits) {
        var d = digits || 0;
        var sign = value < 0 ? -1 : 1;
        var abs = Math.abs(value);
        var str = String(abs);
        var f = Math.pow(10, d);
        var rounded = NaN;
        if (str.indexOf('e') < 0) {
            rounded = Number(Math.round(Number(str + 'e' + d)) + 'e-' + d);
        }
        if (!isFinite(rounded)) rounded = Math.round(abs * f) / f;
        return sign * rounded;
    }
    GH.roundHalfUp = roundHalfUp;

    // Число с запятой и неразрывным пробелом между тысячами, ровно `digits`
    // знаков после запятой (4,0 — не 4): колонки чисел стоят ровно.
    // null / undefined / NaN -> «—». Минус типографский.
    GH.fmtNum = function (value, digits) {
        if (value === null || value === undefined || value === '') return '—';
        var num = Number(value);
        if (!isFinite(num)) return '—';
        var d = Math.max(0, Math.min(6, digits || 0));
        var r = roundHalfUp(num, d);
        var neg = r < 0;
        var parts = Math.abs(r).toFixed(d).split('.');
        var intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
        var out = intPart + (d > 0 ? ',' + parts[1] : '');
        if (neg && /[1-9]/.test(out)) out = '−' + out;
        return out;
    };

    GH.fmtHours = function (hours) {
        if (hours === null || hours === undefined || hours === '') return '—';
        var h = Number(hours);
        if (!isFinite(h)) return '—';
        if (h < 0) h = 0;
        if (h < 1) return '< 1 ч';
        if (h < 48) return roundHalfUp(h, 0) + ' ч';
        return roundHalfUp(h / 24, 0) + ' д';
    };

    // ==================== даты ====================

    function pad2(n) { return (n < 10 ? '0' : '') + n; }

    function parseDate(value) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''));
        if (!m) return null;
        var y = +m[1];
        var mo = +m[2];
        var d = +m[3];
        if (mo < 1 || mo > 12 || d < 1 || d > daysIn(y, mo)) return null;
        return { y: y, m: mo, d: d };
    }
    function parseMonth(value) {
        var m = /^(\d{4})-(\d{2})$/.exec(String(value || ''));
        if (!m) return null;
        var mo = +m[2];
        if (mo < 1 || mo > 12) return null;
        return { y: +m[1], m: mo };
    }
    function daysIn(y, m) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); }

    // 0 = понедельник ... 6 = воскресенье (как datetime.weekday() в Python).
    GH.weekday = function (iso) {
        var p = parseDate(iso);
        if (!p) return null;
        return (new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay() + 6) % 7;
    };
    GH.daysInMonth = function (ym) {
        var p = parseMonth(ym);
        return p ? daysIn(p.y, p.m) : null;
    };
    // '2026-10-09' + 3 -> '2026-10-12' (по календарю, без часовых поясов).
    GH.addDays = function (iso, n) {
        var p = parseDate(iso);
        if (!p) return null;
        var t = new Date(Date.UTC(p.y, p.m - 1, p.d + (Number(n) || 0)));
        return t.getUTCFullYear() + '-' + pad2(t.getUTCMonth() + 1) + '-' + pad2(t.getUTCDate());
    };

    // '2026-10-09' -> '9 октября' (withYear: '9 октября 2026').
    GH.fmtDate = function (iso, withYear) {
        if (!iso) return '';
        var p = parseDate(iso);
        if (!p) return String(iso);
        return p.d + ' ' + MONTHS_GEN[p.m - 1] + (withYear ? ' ' + p.y : '');
    };
    // '2026-10-09' -> '9 окт, пт'.
    GH.fmtDateShort = function (iso) {
        if (!iso) return '';
        var p = parseDate(iso);
        if (!p) return String(iso);
        return p.d + ' ' + MONTHS_SHORT[p.m - 1] + ', ' + WEEKDAYS_LOWER[GH.weekday(iso)];
    };
    // '2026-10-09T16:00' (также с пробелом или секундами) -> '9 октября, 16:00'.
    GH.fmtDateTime = function (value) {
        if (!value) return '';
        var m = /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(String(value));
        if (!m || !parseDate(m[1])) return String(value);
        return GH.fmtDate(m[1]) + (m[2] ? ', ' + m[2] + ':' + m[3] : '');
    };
    // '2026-10' -> 'Октябрь 2026'.
    GH.monthLabel = function (ym) {
        var p = parseMonth(ym);
        if (!p) return String(ym || '');
        return MONTHS_NOM[p.m - 1] + ' ' + p.y;
    };
    // ('2026-10', -1) -> '2026-09'; ('2026-12', 1) -> '2027-01'.
    GH.addMonths = function (ym, n) {
        var p = parseMonth(ym);
        if (!p) return null;
        var total = p.y * 12 + (p.m - 1) + (Number(n) || 0);
        var y = Math.floor(total / 12);
        return y + '-' + pad2(total - y * 12 + 1);
    };

    var mskFormatter = null;
    function mskParts(date) {
        try {
            if (!mskFormatter) {
                mskFormatter = new Intl.DateTimeFormat('en-GB', {
                    timeZone: 'Europe/Moscow', hourCycle: 'h23',
                    year: 'numeric', month: '2-digit', day: '2-digit',
                    hour: '2-digit', minute: '2-digit'
                });
            }
            var parts = mskFormatter.formatToParts(date);
            var out = {};
            for (var i = 0; i < parts.length; i++) out[parts[i].type] = parts[i].value;
            if (out.year && out.month && out.day && out.hour && out.minute) {
                return {
                    y: out.year, mo: out.month, d: out.day,
                    // Старые движки пишут полночь как «24».
                    h: out.hour === '24' ? '00' : out.hour, mi: out.minute
                };
            }
        } catch (e) { /* ниже — фиксированный UTC+3 */ }
        var t = new Date(date.getTime() + 3 * 3600 * 1000);
        return {
            y: String(t.getUTCFullYear()), mo: pad2(t.getUTCMonth() + 1), d: pad2(t.getUTCDate()),
            h: pad2(t.getUTCHours()), mi: pad2(t.getUTCMinutes())
        };
    }
    // -> {date: 'YYYY-MM-DD', time: 'HH:MM', month: 'YYYY-MM', datetime: 'YYYY-MM-DDTHH:MM'}
    GH.mskNow = function (date) {
        var p = mskParts(date instanceof Date ? date : new Date());
        var d = p.y + '-' + p.mo + '-' + p.d;
        var t = p.h + ':' + p.mi;
        return { date: d, time: t, month: p.y + '-' + p.mo, datetime: d + 'T' + t };
    };

    // ==================== хранилище браузера ====================
    // Любой доступ к localStorage — в try/catch: в приватном окне, при
    // заблокированных данных сайта или в превью он бросает исключение.

    function storageGet(key) {
        try {
            return root.localStorage ? root.localStorage.getItem(key) : null;
        } catch (e) {
            return null;
        }
    }
    function storageSet(key, value) {
        try {
            if (!root.localStorage) return false;
            if (value === null || value === undefined || value === '') {
                root.localStorage.removeItem(key);
            } else {
                root.localStorage.setItem(key, String(value));
            }
            return true;
        } catch (e) {
            return false;
        }
    }

    // Общий фильтр бара: '' = все бары. Неизвестное значение читается как ''.
    GH.getBar = function () {
        var v = storageGet(BAR_STORAGE_KEY);
        return findBar(v) ? v : '';
    };
    // Сохраняет выбор и сам обновляет полосу «требует внимания».
    GH.setBar = function (key) {
        var v = findBar(key) ? key : '';
        storageSet(BAR_STORAGE_KEY, v);
        if (byId('ghAttention')) GH.loadAttention();
        return v;
    };

    // ==================== API ====================

    function httpMessage(status) {
        if (status === 400) return 'Некорректный запрос';
        if (status === 401) return 'Требуется вход — обновите страницу';
        if (status === 403) return 'Недостаточно прав';
        if (status === 404) return 'Не найдено';
        if (status === 409) return 'Конфликт: данные уже изменились, обновите страницу';
        if (status === 413) return 'Файл слишком большой';
        if (status === 503) return 'Хранилище временно недоступно';
        if (status >= 500) return 'Ошибка сервера (код ' + status + ')';
        return 'Ошибка запроса (код ' + status + ')';
    }
    function apiError(message, status, data) {
        var err = new Error(message);
        err.status = status;
        err.data = data || null;
        err.code = (data && data.code) || null;
        return err;
    }

    // GH.api('GET', url) / GH.api('POST', url, {..}) / GH.api('POST', url, formData)
    // -> Promise<json>. Ошибка: Error(сообщение из {error} или по коду ответа)
    // с полями status (0 — нет связи), data (разобранное тело или null), code.
    //
    // Четвёртый аргумент необязателен: GH.api(method, url, body, {keepalive: true})
    // — запрос уходит с fetch keepalive. Нужен только для сохранения при уходе
    // со страницы (pagehide / вкладка скрыта): обычный fetch, начатый в этот
    // момент, браузер обрывает вместе со страницей (F5 терял последние
    // набранные символы), keepalive-запрос браузер доводит до сервера сам.
    // Ограничение платформы: тело keepalive-запроса — до 64 КБ суммарно на
    // страницу; тексты раздела (до 10 000 знаков) в него укладываются.
    GH.api = function (method, url, body, opts) {
        var init = {
            method: String(method || 'GET').toUpperCase(),
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
        };
        if (opts && opts.keepalive) init.keepalive = true;
        if (body !== undefined && body !== null) {
            if (typeof FormData !== 'undefined' && body instanceof FormData) {
                init.body = body;   // multipart: границу проставит браузер
            } else {
                init.headers['Content-Type'] = 'application/json';
                init.body = JSON.stringify(body);
            }
        }
        var netError = function () {
            throw apiError('Нет связи с сервером. Проверьте интернет и повторите.', 0, null);
        };
        return fetch(url, init).then(function (res) {
            return res.text().then(function (text) {
                var data = null;
                var parsed = false;
                if (text) {
                    try { data = JSON.parse(text); parsed = true; } catch (e) { data = null; }
                }
                if (!res.ok) {
                    var msg = data && typeof data.error === 'string' && data.error
                        ? data.error : httpMessage(res.status);
                    throw apiError(msg, res.status, parsed ? data : null);
                }
                if (!parsed) {
                    if (!text) return {};
                    throw apiError('Сервер ответил не в формате JSON', res.status, null);
                }
                return data;
            }, netError);
        }, netError);
    };

    // ==================== утилиты страницы ====================

    // Отложенный вызов (автосохранение): d(...) откладывает, d.flush() вызывает
    // сразу, если вызов ждёт, d.cancel() отменяет, d.pending() — ждёт ли.
    GH.debounce = function (fn, ms) {
        var timer = null;
        var lastArgs = null;
        var lastThis = null;
        function run() {
            timer = null;
            var args = lastArgs;
            lastArgs = null;
            return fn.apply(lastThis, args || []);
        }
        function debounced() {
            lastArgs = arguments;
            lastThis = this;
            if (timer) clearTimeout(timer);
            timer = setTimeout(run, ms);
        }
        debounced.flush = function () {
            if (!timer) return undefined;
            clearTimeout(timer);
            return run();
        };
        debounced.cancel = function () {
            if (timer) clearTimeout(timer);
            timer = null;
            lastArgs = null;
        };
        debounced.pending = function () { return !!timer; };
        return debounced;
    };

    // Копирование текста в буфер -> Promise<bool>. Запасной путь — скрытая
    // textarea и execCommand (старые браузеры и http без безопасного контекста).
    GH.copyText = function (text) {
        var value = String(text === null || text === undefined ? '' : text);
        function fallback() {
            if (!doc) return false;
            var ta = doc.createElement('textarea');
            ta.value = value;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.top = '-1000px';
            ta.style.opacity = '0';
            doc.body.appendChild(ta);
            ta.select();
            var ok = false;
            try { ok = doc.execCommand('copy'); } catch (e) { ok = false; }
            doc.body.removeChild(ta);
            return ok;
        }
        try {
            if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
                return root.navigator.clipboard.writeText(value).then(
                    function () { return true; },
                    function () { return fallback(); });
            }
        } catch (e) { /* ниже */ }
        return Promise.resolve(fallback());
    };

    // Параметры адреса: GH.params().get('month'); GH.setParams({open: id}) —
    // null / '' удаляют ключ; push=true добавляет запись в историю.
    GH.params = function () {
        try { return new URLSearchParams(root.location.search); } catch (e) { return new URLSearchParams(''); }
    };
    GH.setParams = function (values, push) {
        try {
            var p = new URLSearchParams(root.location.search);
            for (var k in values) {
                if (!Object.prototype.hasOwnProperty.call(values, k)) continue;
                var v = values[k];
                if (v === null || v === undefined || v === '') p.delete(k);
                else p.set(k, String(v));
            }
            var qs = p.toString();
            var url = root.location.pathname + (qs ? '?' + qs : '') + root.location.hash;
            root.history[push ? 'pushState' : 'replaceState'](null, '', url);
        } catch (e) { /* адрес не обновился — страница продолжает работать */ }
    };

    // ==================== слои: карточка и диалоги ====================
    // Стек открытых слоёв. Esc и Tab относятся к верхнему. Пока открыт хоть
    // один слой, на <html> висит gh-lock (страница под ним не прокручивается).

    var stack = [];
    var backdropEl = null;

    function isOpen(el) {
        for (var i = 0; i < stack.length; i++) if (stack[i].el === el) return true;
        return false;
    }
    function removeFromStack(el) {
        for (var i = stack.length - 1; i >= 0; i--) {
            if (stack[i].el === el) return stack.splice(i, 1)[0];
        }
        return null;
    }
    function syncLock() {
        if (!doc) return;
        var drawers = 0;
        for (var i = 0; i < stack.length; i++) if (stack[i].kind === 'drawer') drawers++;
        if (backdropEl) backdropEl.hidden = drawers === 0;
        if (stack.length) doc.documentElement.classList.add('gh-lock');
        else doc.documentElement.classList.remove('gh-lock');
        // По этому классу тосты уходят с нижней панели карточки (hub.css).
        if (drawers) doc.documentElement.classList.add('gh-drawer-open');
        else doc.documentElement.classList.remove('gh-drawer-open');
    }
    function ensureBackdrop() {
        if (backdropEl || !doc) return backdropEl;
        backdropEl = doc.createElement('div');
        backdropEl.className = 'gh-backdrop gh-scope';
        backdropEl.hidden = true;
        backdropEl.addEventListener('click', function () {
            for (var i = stack.length - 1; i >= 0; i--) {
                if (stack[i].kind === 'drawer') { GH.closeDrawer(stack[i].el); return; }
            }
        });
        doc.body.appendChild(backdropEl);
        return backdropEl;
    }
    function emit(el, name, detail) {
        try {
            var ev;
            if (typeof root.CustomEvent === 'function') {
                ev = new root.CustomEvent(name, { detail: detail });
            } else {
                ev = doc.createEvent('CustomEvent');
                ev.initCustomEvent(name, false, false, detail);
            }
            el.dispatchEvent(ev);
        } catch (e) { /* событие не критично */ }
    }
    function focusables(el) {
        var list = el.querySelectorAll(
            'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
            'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
        var out = [];
        for (var i = 0; i < list.length; i++) {
            if (list[i].getClientRects().length) out.push(list[i]);
        }
        return out;
    }
    function openLayer(el, kind, opts) {
        if (!el || isOpen(el)) return;
        var prev = doc.activeElement;
        el.hidden = false;
        el.setAttribute('aria-hidden', 'false');
        if (!el.hasAttribute('role')) el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        var focusEl = kind === 'modal' ? (el.querySelector('.gh-modal-box') || el) : el;
        if (!focusEl.hasAttribute('tabindex')) focusEl.setAttribute('tabindex', '-1');
        stack.push({ el: el, kind: kind, prevFocus: prev, onClose: opts && opts.onClose });
        syncLock();
        var auto = el.querySelector('[data-gh-autofocus]');
        try { (auto || focusEl).focus({ preventScroll: true }); } catch (e) { /* фокус не критичен */ }
        emit(el, 'gh:open', null);
    }
    function closeLayer(el, result) {
        var item = removeFromStack(el);
        if (!item) return;
        el.hidden = true;
        el.setAttribute('aria-hidden', 'true');
        syncLock();
        var prev = item.prevFocus;
        if (prev && prev.focus && doc.documentElement.contains(prev)) {
            try { prev.focus({ preventScroll: true }); } catch (e) { /* фокус не критичен */ }
        }
        if (typeof item.onClose === 'function') item.onClose(result);
        emit(el, 'gh:close', result === undefined ? null : result);
    }

    // Выдвижная карточка: <aside class="gh-drawer" id=".." hidden>. Затемнение
    // создаётся само. Одновременно открыта одна карточка: открытие новой
    // закрывает прежнюю. Закрывают: Esc, клик по затемнению, [data-gh-close]
    // внутри, GH.closeDrawer(el). При закрытии — opts.onClose() и событие
    // 'gh:close' на элементе (успеть сохранить черновик).
    GH.openDrawer = function (el, opts) {
        if (!el || !doc) return;
        ensureBackdrop();
        for (var i = stack.length - 1; i >= 0; i--) {
            if (stack[i].kind === 'drawer' && stack[i].el !== el) closeLayer(stack[i].el);
        }
        openLayer(el, 'drawer', opts);
    };
    GH.closeDrawer = function (el) {
        if (!el) {
            for (var i = stack.length - 1; i >= 0; i--) {
                if (stack[i].kind === 'drawer') { el = stack[i].el; break; }
            }
        }
        if (el) closeLayer(el);
    };
    // Диалог: <div class="gh-modal" id=".." hidden><div class="gh-modal-box">…
    // Закрывают: Esc, клик по затемнению мимо окна, [data-gh-close],
    // GH.closeModal(el, result). result уходит в opts.onClose(result).
    GH.openModal = function (el, opts) {
        if (!el || !doc) return;
        openLayer(el, 'modal', opts);
    };
    GH.closeModal = function (el, result) {
        if (!el) {
            for (var i = stack.length - 1; i >= 0; i--) {
                if (stack[i].kind === 'modal') { el = stack[i].el; break; }
            }
        }
        if (el) closeLayer(el, result);
    };
    GH.isLayerOpen = function () { return stack.length > 0; };

    var CLOSE_SVG = '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">' +
        '<path d="M2.5 2.5l7 7M9.5 2.5l-7 7" stroke-width="1.6" stroke-linecap="round"/></svg>';

    function buildDialog(title, bodyHtml, buttonsHtml) {
        var wrap = doc.createElement('div');
        wrap.className = 'gh-modal gh-scope';
        wrap.hidden = true;
        wrap.innerHTML =
            '<div class="gh-modal-box">' +
              '<div class="gh-modal-head"><h2 class="gh-modal-t">' + GH.esc(title) + '</h2></div>' +
              '<div class="gh-modal-body">' + bodyHtml + '</div>' +
              '<div class="gh-modal-foot">' + buttonsHtml + '</div>' +
            '</div>';
        doc.body.appendChild(wrap);
        return wrap;
    }
    function textHtml(text) {
        if (!text) return '';
        var parts = String(text).split(/\n{2,}/);
        var out = '';
        for (var i = 0; i < parts.length; i++) {
            out += '<p>' + GH.esc(parts[i]).replace(/\n/g, '<br>') + '</p>';
        }
        return out;
    }

    // GH.confirm({title, text, ok, cancel, danger}) -> Promise<bool>.
    // danger — кнопка подтверждения красная, фокус стоит на «Отмена».
    GH.confirm = function (opts) {
        opts = opts || {};
        if (!doc) return Promise.resolve(false);
        return new Promise(function (resolve) {
            var danger = !!opts.danger;
            var wrap = buildDialog(opts.title || 'Подтвердите действие', textHtml(opts.text),
                '<button type="button" class="gh-btn" data-act="no"' + (danger ? ' data-gh-autofocus' : '') + '>' +
                    GH.esc(opts.cancel || 'Отмена') + '</button>' +
                '<button type="button" class="gh-btn ' + (danger ? 'gh-btn-danger' : 'gh-btn-primary') + '" data-act="yes"' +
                    (danger ? '' : ' data-gh-autofocus') + '>' + GH.esc(opts.ok || 'Подтвердить') + '</button>');
            wrap.addEventListener('click', function (e) {
                var b = e.target.closest ? e.target.closest('[data-act]') : null;
                if (b) GH.closeModal(wrap, b.getAttribute('data-act') === 'yes');
            });
            GH.openModal(wrap, {
                onClose: function (result) {
                    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
                    resolve(result === true);
                }
            });
        });
    };

    // GH.prompt({title, label, value, placeholder, text, ok, multiline}) ->
    // Promise<string|null>: строка (может быть пустой) по «Готово»/Enter,
    // null по «Отмена», Esc или клику мимо окна.
    GH.prompt = function (opts) {
        opts = opts || {};
        if (!doc) return Promise.resolve(null);
        return new Promise(function (resolve) {
            var field = opts.multiline
                ? '<textarea class="gh-textarea" data-gh-autofocus rows="3"></textarea>'
                : '<input type="text" class="gh-input" data-gh-autofocus autocomplete="off">';
            var body = textHtml(opts.text) +
                '<label class="gh-field"' + (opts.text ? ' style="margin-top:12px"' : '') + '>' +
                  (opts.label ? '<span class="gh-field-cap">' + GH.esc(opts.label) + '</span>' : '') +
                  field +
                '</label>';
            var wrap = buildDialog(opts.title || 'Введите значение', body,
                '<button type="button" class="gh-btn" data-act="no">Отмена</button>' +
                '<button type="button" class="gh-btn gh-btn-primary" data-act="yes">' +
                    GH.esc(opts.ok || 'Готово') + '</button>');
            var input = wrap.querySelector('.gh-input, .gh-textarea');
            input.value = opts.value === null || opts.value === undefined ? '' : String(opts.value);
            if (opts.placeholder) input.setAttribute('placeholder', opts.placeholder);
            wrap.addEventListener('click', function (e) {
                var b = e.target.closest ? e.target.closest('[data-act]') : null;
                if (!b) return;
                GH.closeModal(wrap, b.getAttribute('data-act') === 'yes' ? input.value : null);
            });
            input.addEventListener('keydown', function (e) {
                // Enter подтверждает; в многострочном поле — Ctrl/Cmd+Enter.
                if (e.key === 'Enter' && (!opts.multiline || e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    GH.closeModal(wrap, input.value);
                }
            });
            GH.openModal(wrap, {
                onClose: function (result) {
                    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
                    resolve(typeof result === 'string' ? result : null);
                }
            });
        });
    };

    // ==================== тосты ====================

    var toastBox = null;
    var TOAST_MAX = 4;             // больше одновременно не держим: старые уходят
    var TOAST_MS = 4500;           // обычный тост
    var TOAST_MS_LONG = 8000;      // с действием или ошибкой: успеть прочитать и нажать

    function removeToast(t) {
        if (!t || t.getAttribute('data-out')) return;
        t.setAttribute('data-out', '1');
        t.classList.add('is-out');
        setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 220);
    }

    // GH.toast(msg, tone, {actionLabel, actionHref, onAction, timeout}) -> элемент тоста.
    // tone: muted | warning | accent | success | danger. timeout 0 — не скрывать.
    // Действие: ссылка (actionHref) или кнопка (onAction — функция; тост после
    // нажатия закрывается). Если заданы оба, работает ссылка.
    GH.toast = function (message, tone, opts) {
        opts = opts || {};
        if (!doc) return null;
        if (!toastBox || !toastBox.parentNode) {
            toastBox = doc.createElement('div');
            toastBox.className = 'gh-toasts gh-scope';
            toastBox.setAttribute('aria-live', 'polite');
            doc.body.appendChild(toastBox);
        }
        var t = doc.createElement('div');
        t.className = 'gh-toast ' + GH.toneClass(tone || 'muted');
        t.setAttribute('role', tone === 'danger' ? 'alert' : 'status');
        var html = '<div class="gh-toast-t">' + GH.esc(message) + '</div>';
        var actionKind = !opts.actionLabel ? ''
            : (opts.actionHref ? 'link' : (typeof opts.onAction === 'function' ? 'button' : ''));
        if (actionKind === 'link') {
            html += '<a class="gh-toast-a" href="' + GH.esc(opts.actionHref) + '">' +
                GH.esc(opts.actionLabel) + '</a>';
        } else if (actionKind === 'button') {
            html += '<button type="button" class="gh-toast-a">' + GH.esc(opts.actionLabel) + '</button>';
        }
        html += '<button type="button" class="gh-toast-x" aria-label="Закрыть">' + CLOSE_SVG + '</button>';
        t.innerHTML = html;
        toastBox.appendChild(t);
        while (toastBox.children.length > TOAST_MAX) toastBox.removeChild(toastBox.firstChild);

        var ms = opts.timeout !== undefined ? Number(opts.timeout)
            : (actionKind || tone === 'danger' ? TOAST_MS_LONG : TOAST_MS);
        var timer = null;
        function arm(delay) {
            if (!ms) return;
            timer = setTimeout(function () { removeToast(t); }, delay);
        }
        t.querySelector('.gh-toast-x').addEventListener('click', function () { removeToast(t); });
        if (actionKind === 'button') {
            t.querySelector('button.gh-toast-a').addEventListener('click', function () {
                removeToast(t);
                opts.onAction();
            });
        }
        // Пока курсор над тостом, он не исчезает.
        t.addEventListener('mouseenter', function () { if (timer) clearTimeout(timer); timer = null; });
        t.addEventListener('mouseleave', function () { arm(2000); });
        arm(ms);
        return t;
    };

    // ==================== меню ====================
    // <div class="gh-pick"><button class="gh-pick-btn" ...></button>
    //   <div class="gh-menu" hidden>…кнопки .gh-menu-item…</div></div>
    // GH.toggleMenu(menu, trigger) по клику на кнопку. Клик мимо меню и Esc
    // закрывают; клик по .gh-menu-item закрывает после обработчика страницы
    // (если у пункта нет data-gh-keep). На телефоне меню — лист снизу.

    var openMenu = null;           // {menu, trigger, flipped}
    var scrimEl = null;
    // Ширина, с которой меню — лист снизу (как @media в hub.css и base.css).
    var PHONE_MAX = 768;
    var EDGE_GAP = 8;              // отступ меню от края окна, px

    function isPhone() {
        var w = root.innerWidth || (doc && doc.documentElement.clientWidth) || 0;
        return w > 0 && w <= PHONE_MAX;
    }

    GH.openMenu = function (menu, trigger) {
        if (!menu || !doc) return;
        GH.closeMenus();
        menu.hidden = false;
        if (trigger) trigger.setAttribute('aria-expanded', 'true');
        openMenu = { menu: menu, trigger: trigger || null, flipped: false };
        // Меню у правого края полосы не должно вылезать за окно (иначе у
        // страницы появляется горизонтальная прокрутка): если правый край
        // меню дальше края окна — прижимаем его вправо (класс is-right).
        // Класс, поставленный страницей, не трогаем.
        if (!isPhone() && !menu.classList.contains('is-right')) {
            var vw = root.innerWidth || doc.documentElement.clientWidth;
            var r = menu.getBoundingClientRect();
            if (r.right > vw - EDGE_GAP) {
                menu.classList.add('is-right');
                openMenu.flipped = true;
            }
        }
        if (!scrimEl) {
            scrimEl = doc.createElement('div');
            scrimEl.className = 'gh-menu-scrim gh-scope';
            scrimEl.hidden = true;
            doc.body.appendChild(scrimEl);
        }
        scrimEl.hidden = false;
    };
    GH.closeMenus = function () {
        if (!openMenu) return;
        openMenu.menu.hidden = true;
        if (openMenu.flipped) openMenu.menu.classList.remove('is-right');
        if (openMenu.trigger) openMenu.trigger.setAttribute('aria-expanded', 'false');
        openMenu = null;
        if (scrimEl) scrimEl.hidden = true;
    };
    GH.isMenuOpen = function (menu) {
        return !!openMenu && (!menu || openMenu.menu === menu);
    };

    // Поле ввода внутри меню (например, даты своего периода) — стрелки его.
    function isTextField(el) {
        if (!el || !el.tagName) return false;
        var tag = el.tagName.toLowerCase();
        return tag === 'input' || tag === 'textarea' || tag === 'select' || !!el.isContentEditable;
    }

    // Стрелки вверх/вниз ходят по пунктам открытого меню (с клавиатуры).
    function moveMenuFocus(step) {
        var list = openMenu.menu.querySelectorAll('.gh-menu-item');
        var items = [];
        for (var i = 0; i < list.length; i++) {
            if (!list[i].disabled && list[i].getClientRects().length) items.push(list[i]);
        }
        if (!items.length) return;
        var at = items.indexOf(doc.activeElement);
        if (at < 0) {
            var on = openMenu.menu.querySelector('.gh-menu-item.is-on');
            at = on && items.indexOf(on) >= 0 ? items.indexOf(on) - step : (step > 0 ? -1 : 0);
        }
        var next = (at + step + items.length) % items.length;
        try { items[next].focus(); } catch (e) { /* фокус не критичен */ }
    }
    // -> true, если меню открылось; false, если закрылось.
    GH.toggleMenu = function (menu, trigger) {
        if (openMenu && openMenu.menu === menu) { GH.closeMenus(); return false; }
        GH.openMenu(menu, trigger);
        return true;
    };

    // ==================== сегменты ====================
    // <div class="gh-seg"><button class="gh-seg-btn is-on" data-value="table">…

    GH.setSeg = function (container, value) {
        if (!container) return;
        var btns = container.querySelectorAll('[data-value]');
        for (var i = 0; i < btns.length; i++) {
            var on = btns[i].getAttribute('data-value') === String(value);
            btns[i].classList.toggle('is-on', on);
            btns[i].setAttribute('aria-pressed', on ? 'true' : 'false');
        }
    };
    GH.bindSeg = function (container, onChange) {
        if (!container) return;
        container.addEventListener('click', function (e) {
            var b = e.target.closest ? e.target.closest('[data-value]') : null;
            if (!b || !container.contains(b) || b.disabled) return;
            if (b.classList.contains('is-on')) return;
            var v = b.getAttribute('data-value');
            GH.setSeg(container, v);
            if (typeof onChange === 'function') onChange(v, b);
        });
    };

    // ==================== подсказки ====================

    var tipEl = null;
    var tipFor = null;
    // Касание пальцем порождает ещё и «мышиные» mouseover и focus, а затем
    // click. Если бы подсказка показывалась по ним, тап по «?» сначала
    // открывал бы её, а click тут же закрывал. Поэтому после касания
    // наведение и фокус подсказку не трогают, а тап по «?» её переключает.
    // TOUCH_GRACE_MS — сколько после касания ещё приходят такие события
    // (браузеры шлют их сразу за touchend; 800 мс — с запасом на медленный
    // телефон).
    var TOUCH_GRACE_MS = 800;
    var lastTouchAt = 0;
    function recentTouch() { return Date.now() - lastTouchAt < TOUCH_GRACE_MS; }

    function placeTip(target) {
        var r = target.getBoundingClientRect();
        var vw = root.innerWidth || doc.documentElement.clientWidth;
        var vh = root.innerHeight || doc.documentElement.clientHeight;
        var tw = tipEl.offsetWidth;
        var th = tipEl.offsetHeight;
        var gap = 8;
        var top = r.top - th - gap;
        if (top < 8) top = r.bottom + gap;                 // сверху не влезает — снизу
        if (top + th > vh - 8) top = Math.max(8, vh - th - 8);
        var left = r.left + r.width / 2 - tw / 2;
        left = Math.max(8, Math.min(left, vw - tw - 8));
        tipEl.style.top = Math.round(top) + 'px';
        tipEl.style.left = Math.round(left) + 'px';
    }
    function showTip(target) {
        var text = target.getAttribute('data-tip');
        if (!text) return;
        if (!tipEl) {
            tipEl = doc.createElement('div');
            tipEl.className = 'gh-tipbox gh-scope';
            tipEl.id = 'ghTip';
            tipEl.setAttribute('role', 'tooltip');
            doc.body.appendChild(tipEl);
        }
        if (tipFor && tipFor !== target) tipFor.removeAttribute('aria-describedby');
        tipFor = target;
        tipEl.textContent = text;
        tipEl.hidden = false;
        tipEl.classList.remove('is-on');
        placeTip(target);
        tipEl.classList.add('is-on');
        target.setAttribute('aria-describedby', 'ghTip');
    }
    function hideTip() {
        if (!tipEl) return;
        tipEl.classList.remove('is-on');
        tipEl.hidden = true;
        if (tipFor) tipFor.removeAttribute('aria-describedby');
        tipFor = null;
    }
    GH.hideTip = hideTip;

    function tipTarget(node) {
        return node && node.closest ? node.closest('[data-tip]') : null;
    }

    // ==================== глобальные обработчики ====================

    var globalsInstalled = false;
    function installGlobals() {
        if (globalsInstalled || !doc) return;
        globalsInstalled = true;

        doc.addEventListener('keydown', function (e) {
            if (openMenu && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && !isTextField(doc.activeElement)) {
                e.preventDefault();
                moveMenuFocus(e.key === 'ArrowDown' ? 1 : -1);
                return;
            }
            if (e.key === 'Escape' || e.key === 'Esc') {
                hideTip();
                if (openMenu) {
                    // Фокус возвращается на кнопку, открывшую меню.
                    var trig = openMenu.trigger;
                    GH.closeMenus();
                    e.preventDefault();
                    if (trig && trig.focus) {
                        try { trig.focus({ preventScroll: true }); } catch (err) { /* не критично */ }
                    }
                    return;
                }
                var top = stack[stack.length - 1];
                if (top) {
                    e.preventDefault();
                    if (top.kind === 'drawer') GH.closeDrawer(top.el);
                    else GH.closeModal(top.el);
                }
                return;
            }
            if (e.key === 'Tab' && stack.length) {
                // Фокус не уходит из верхнего слоя.
                var layer = stack[stack.length - 1].el;
                var list = focusables(layer);
                if (!list.length) { e.preventDefault(); return; }
                var first = list[0];
                var last = list[list.length - 1];
                var active = doc.activeElement;
                if (!layer.contains(active)) { e.preventDefault(); first.focus(); return; }
                if (e.shiftKey && (active === first || list.indexOf(active) < 0)) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && active === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        });

        // Меню: клик мимо закрывает, клик по пункту — закрывает после
        // обработчика страницы (document — последний на пути всплытия).
        doc.addEventListener('click', function (e) {
            if (openMenu) {
                var t = e.target;
                var inMenu = openMenu.menu.contains(t);
                var onTrigger = openMenu.trigger && openMenu.trigger.contains(t);
                if (!inMenu && !onTrigger) {
                    GH.closeMenus();
                } else if (inMenu) {
                    var item = t.closest ? t.closest('.gh-menu-item') : null;
                    if (item && !item.hasAttribute('data-gh-keep')) GH.closeMenus();
                }
            }
            // [data-gh-close] внутри карточки или диалога закрывает его.
            var closer = e.target.closest ? e.target.closest('[data-gh-close]') : null;
            if (closer) {
                var layerEl = closer.closest('.gh-drawer, .gh-modal');
                if (layerEl && isOpen(layerEl)) {
                    if (layerEl.classList.contains('gh-drawer')) GH.closeDrawer(layerEl);
                    else GH.closeModal(layerEl);
                }
            }
            // Подсказка по тапу на «?» (на телефоне нет наведения): тап
            // открывает, повторный тап или тап мимо — закрывает. Мышью клик
            // по «?» подсказку только показывает (она уже видна по наведению).
            var help = e.target.closest ? e.target.closest('.gh-help[data-tip]') : null;
            if (help) {
                if (recentTouch() && tipFor === help) hideTip(); else showTip(help);
            } else if (tipFor && recentTouch()) {
                hideTip();
            }
        });

        function markTouch(e) {
            if (!e.pointerType || e.pointerType === 'touch' || e.pointerType === 'pen') {
                lastTouchAt = Date.now();
            }
        }
        if (typeof root.PointerEvent === 'function') {
            doc.addEventListener('pointerdown', markTouch, true);
        } else {
            doc.addEventListener('touchstart', markTouch, true);
        }

        // Клик по затемнению диалога мимо окна. Нажатие должно начаться на
        // затемнении: иначе выделение текста в поле, отпущенное снаружи,
        // закрыло бы диалог.
        var downOnModal = null;
        doc.addEventListener('mousedown', function (e) {
            var t = e.target;
            downOnModal = t && t.classList && t.classList.contains('gh-modal') ? t : null;
        });
        doc.addEventListener('mouseup', function (e) {
            var t = e.target;
            if (downOnModal && t === downOnModal && isOpen(t)) {
                var m = t;
                downOnModal = null;
                setTimeout(function () { GH.closeModal(m); }, 0);
            }
            downOnModal = null;
        });

        doc.addEventListener('mouseover', function (e) {
            if (recentTouch()) return;
            var t = tipTarget(e.target);
            if (t === tipFor) return;
            if (t) showTip(t); else hideTip();
        });
        doc.addEventListener('focusin', function (e) {
            if (recentTouch()) return;
            var t = tipTarget(e.target);
            if (t === tipFor) return;
            if (t) showTip(t); else hideTip();
        });
        doc.addEventListener('focusout', function () {
            if (recentTouch()) return;
            hideTip();
        });
        root.addEventListener('scroll', hideTip, true);
        root.addEventListener('resize', hideTip);
    }

    // ==================== шапка и «требует внимания» ====================

    // Гамбургер шапки раздела открывает общий сайдбар: клик пробрасывается на
    // скрытую кнопку #sidebar-toggle из shared/nav.html (как на /draft).
    GH.initHeader = function () {
        var burger = byId('ghBurger');
        if (!burger || burger.getAttribute('data-gh-bound')) return;
        burger.setAttribute('data-gh-bound', '1');
        burger.addEventListener('click', function () {
            var toggle = byId('sidebar-toggle');
            if (toggle) toggle.click();
        });
    };

    var attnGen = 0;
    // Последний успешный ответ полосы: {bar, data}; null — ещё не пришёл или
    // запрос упал. Страницам он нужен, чтобы сверить свои числа со счётчиком
    // (например, «Отзывы» показывают, сколько отзывов без ответа осталось за
    // другими месяцами), не запрашивая /api/guest-hub/attention второй раз.
    var attnLast = null;
    var attnListeners = [];
    function notifyAttention() {
        for (var i = 0; i < attnListeners.length; i++) {
            try {
                attnListeners[i](attnLast ? attnLast.data : null, attnLast ? attnLast.bar : null);
            } catch (e) { /* ошибка одной страницы не ломает полосу */ }
        }
    }
    // GH.onAttention(fn): fn(data|null, bar) после каждого ответа полосы (null —
    // ошибка). Если ответ уже есть — fn вызывается сразу с ним.
    GH.onAttention = function (fn) {
        if (typeof fn !== 'function') return;
        attnListeners.push(fn);
        if (attnLast) fn(attnLast.data, attnLast.bar);
    };
    function fillAttention(node, data) {
        var items = node.querySelectorAll('[data-attn]');
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var key = item.getAttribute('data-attn');
            var raw = data ? data[key] : null;
            var v = typeof raw === 'number' && isFinite(raw) ? raw : null;
            var n = item.querySelector('.gh-attn-n');
            if (n) n.textContent = v === null ? '—' : String(v);
            for (var k = 0; k < GH.TONES.length; k++) item.classList.remove('gh-tone-' + GH.TONES[k]);
            var hot = v !== null && v > 0;
            item.classList.toggle('is-hot', hot);
            if (hot) item.classList.add(GH.toneClass(ATTN_TONE[key]));
            if (ATTN_HIDE_WHEN_ZERO[key]) item.hidden = !hot;
            var label = item.querySelector('.gh-attn-l');
            if (label) item.setAttribute('aria-label', label.textContent + ': ' + (v === null ? 'нет данных' : v));
        }
    }

    // Заполняет #ghAttention из /api/guest-hub/attention?bar=<GH.getBar()>.
    // Ошибку не показывает: полоса просто скрывается. -> Promise<data|null>.
    // Страницы раздела зовут её после каждого успешного изменения (ответ,
    // пропуск, удаление, утверждение...), чтобы счётчики не отставали от списка.
    GH.loadAttention = function () {
        var node = byId('ghAttention');
        if (!node) return Promise.resolve(null);
        var my = ++attnGen;
        var bar = GH.getBar();
        var scope = node.querySelector('[data-attn-scope]');
        if (scope) scope.textContent = bar ? GH.barName(bar) : 'Вся сеть';
        return GH.api('GET', '/api/guest-hub/attention?bar=' + encodeURIComponent(bar)).then(
            function (data) {
                if (my !== attnGen) return data;
                fillAttention(node, data || {});
                node.classList.remove('is-loading');
                node.hidden = false;
                attnLast = { bar: bar, data: data || {} };
                notifyAttention();
                return data;
            },
            function () {
                if (my === attnGen) {
                    node.hidden = true;
                    attnLast = null;
                    notifyAttention();
                }
                return null;
            });
    };

    // ==================== запуск ====================

    function boot() {
        installGlobals();
        GH.initHeader();
        if (byId('ghAttention')) GH.loadAttention();
    }

    root.GH = GH;
    if (typeof module !== 'undefined' && module.exports) module.exports = GH;

    if (doc && typeof doc.addEventListener === 'function') {
        if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot);
        else boot();
    }
})(typeof window !== 'undefined' ? window : this);

/**
 * Общий выбор бара и периода на весь сайт (план единого виджета — docs/planning/period-widget-rollout.md,
 * раздел 3.5; сервер — core/scope.py).
 *
 * Выбрал бар или период на любой странице — все страницы открываются с ним. Хранится в cookie
 * браузера, чтобы сервер сразу рисовал полосу с выбором:
 *   - kultura_period = '<номер пользователя>:<YYYY-MM-DD>_<YYYY-MM-DD>', срок — час (ответ
 *     владельца Р1), продлевается при каждом открытии страницы с полосой (touchPeriod);
 *   - kultura_bar = '<номер пользователя>:<ключ бара|all>', срок — год.
 * Номер пользователя в значении: на общем компьютере чужой выбор не подхватывается. Вся сеть —
 * явным 'all': пустой ключ значил бы «не выбирали» и поднял бы старый ключ.
 *
 * Бар дублируется в localStorage 'kultura.bar' — его читает раздел «Гости» (GH.getBar), пока
 * его страницы не перешли на полосу. Порядок чтения бара: ?bar= в адресе (ссылка сильнее) ->
 * cookie -> 'kultura.bar' -> старые ключи страниц (dashboard_selected_venue, gh.bar).
 *
 * Обычный скрипт: window.KScope; для Node-тестов — module.exports. Настройки (номер
 * пользователя, имена cookie, сроки) — configure(window.KULTURA_SCOPE) из shared/nav.html.
 */
(function (root, factory) {
    var api = factory(root);
    root.KScope = api;
    if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis, function (root) {
    'use strict';

    var KEY = 'kultura.bar';
    var BARS = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'];
    var ISO = /^\d{4}-\d{2}-\d{2}$/;
    var cfg = {
        user: null,
        cookies: { period: 'kultura_period', bar: 'kultura_bar' },
        ttl: { period: 3600, bar: 365 * 24 * 3600 }
    };

    function configure(c) {
        c = c || {};
        if (c.user !== undefined && c.user !== null) cfg.user = c.user;
        if (c.cookies) cfg.cookies = { period: c.cookies.period || cfg.cookies.period, bar: c.cookies.bar || cfg.cookies.bar };
        if (c.ttl) cfg.ttl = { period: c.ttl.period || cfg.ttl.period, bar: c.ttl.bar || cfg.ttl.bar };
    }

    // ---------------------------------------------------------------- хранилища

    // Любой доступ к localStorage и cookie — в try/catch: в приватном окне они бросают исключение.
    function read(key) {
        try { return root.localStorage ? root.localStorage.getItem(key) : null; } catch (e) { return null; }
    }
    function write(key, value) {
        try {
            if (!root.localStorage) return;
            if (value) root.localStorage.setItem(key, value);
            else root.localStorage.removeItem(key);
        } catch (e) { /* приватное окно: выбор живёт до перезагрузки */ }
    }
    function readCookie(name) {
        try {
            var parts = (root.document && root.document.cookie ? root.document.cookie : '').split(';');
            for (var i = 0; i < parts.length; i++) {
                var p = parts[i].replace(/^\s+/, '');
                if (p.indexOf(name + '=') === 0) return decodeURIComponent(p.slice(name.length + 1));
            }
        } catch (e) { /* cookie недоступны */ }
        return null;
    }
    function writeCookie(name, value, maxAge) {
        try {
            if (!root.document) return;
            var secure = root.location && root.location.protocol === 'https:' ? '; Secure' : '';
            root.document.cookie = name + '=' + encodeURIComponent(value) + '; Max-Age=' + maxAge +
                '; Path=/; SameSite=Lax' + secure;
        } catch (e) { /* cookie недоступны */ }
    }
    // '<номер>:<значение>' этого пользователя -> значение; чужое или без номера -> null.
    function owned(raw) {
        if (!raw || cfg.user === null) return null;
        var at = raw.indexOf(':');
        if (at < 1 || raw.slice(0, at) !== String(cfg.user)) return null;
        return raw.slice(at + 1) || null;
    }

    // ---------------------------------------------------------------- бар

    // Ключ бара или '' (вся сеть); мусор — null.
    function normalize(raw) {
        if (raw === null || raw === undefined) return null;
        var v = String(raw).trim();
        if (v.charAt(0) === '"') {
            try { v = JSON.parse(v); } catch (e) { return null; }
        }
        if (v === '' || v === 'all') return '';
        return BARS.indexOf(v) >= 0 ? v : null;
    }
    function fromUrl() {
        try { return new URLSearchParams(root.location ? root.location.search : '').get('bar'); } catch (e) { return null; }
    }
    // Сохранённый выбор бара (без адреса страницы).
    function storedBar() {
        var candidates = [owned(readCookie(cfg.cookies.bar)), read(KEY), read('dashboard_selected_venue'), read('gh.bar')];
        for (var i = 0; i < candidates.length; i++) {
            var v = normalize(candidates[i]);
            if (v !== null) return v;
        }
        return '';
    }
    function getBar() {
        var v = normalize(fromUrl());
        return v !== null ? v : storedBar();
    }
    // Запомнить выбор для всего сайта и записать ?bar= в адрес (вся сеть — без параметра).
    function setBar(raw, opts) {
        var v = normalize(raw);
        if (v === null) v = '';
        if (cfg.user !== null) writeCookie(cfg.cookies.bar, cfg.user + ':' + (v || 'all'), cfg.ttl.bar);
        write(KEY, v || 'all');
        if (!opts || opts.url !== false) writeUrlBar(v);
        return v;
    }
    function writeUrlBar(v) {
        if (!root.history || !root.location) return;
        var q = new URLSearchParams(root.location.search);
        if (v) q.set('bar', v); else q.delete('bar');
        var s = q.toString();
        root.history.replaceState(root.history.state, '', root.location.pathname + (s ? '?' + s : '') + root.location.hash);
    }

    // ---------------------------------------------------------------- период

    // Выбранный период {start, end} (даты включительно) или null: нет, чужой, истёк, мусор.
    function getPeriod() {
        var v = owned(readCookie(cfg.cookies.period));
        if (!v) return null;
        var parts = v.split('_');
        if (parts.length !== 2 || !ISO.test(parts[0]) || !ISO.test(parts[1]) || parts[0] > parts[1]) return null;
        return { start: parts[0], end: parts[1] };
    }
    function setPeriod(period) {
        if (!period || cfg.user === null) return;
        writeCookie(cfg.cookies.period, cfg.user + ':' + period.start + '_' + period.end, cfg.ttl.period);
    }
    // Час считается с последнего открытия страницы: продлить срок выбранного периода.
    function touchPeriod() {
        var p = getPeriod();
        if (p) setPeriod(p);
        return p;
    }
    function resetPeriod() {
        writeCookie(cfg.cookies.period, '', 0);
    }

    // ---------------------------------------------------------------- другие вкладки

    // Выбор, сделанный в другой вкладке или до кнопки «Назад», подхватывается, когда к странице
    // возвращаются: fn({bar, period}) — только если что-то изменилось.
    function watch(fn) {
        var last = snapshotKey();
        function check() {
            if (root.document && root.document.visibilityState === 'hidden') return;
            var key = snapshotKey();
            if (key === last) return;
            last = key;
            fn({ bar: storedBar(), period: getPeriod() });
        }
        if (root.document && root.document.addEventListener) root.document.addEventListener('visibilitychange', check);
        if (root.addEventListener) {
            root.addEventListener('focus', check);
            root.addEventListener('pageshow', function (e) { if (e && e.persisted) check(); });
        }
        return {
            // Свой выбор на этой странице — не «чужое изменение».
            sync: function () { last = snapshotKey(); },
            check: check
        };
    }
    function snapshotKey() {
        var p = getPeriod();
        return storedBar() + '|' + (p ? p.start + '_' + p.end : '');
    }

    return {
        KEY: KEY, BARS: BARS, configure: configure, normalize: normalize,
        getBar: getBar, setBar: setBar, storedBar: storedBar,
        getPeriod: getPeriod, setPeriod: setPeriod, touchPeriod: touchPeriod, resetPeriod: resetPeriod,
        watch: watch, readCookie: readCookie
    };
});

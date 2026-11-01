/**
 * Выбор бара — один на весь сайт (стандарт периодов, раздел 6; решение владельца 2026-11-01).
 *
 * Выбрал Лиговский на любой странице — все страницы открываются на Лиговском, пока не сменишь.
 * Хранится в браузере под одним ключом 'kultura.bar' (ключ заведения или пусто — вся сеть).
 * Порядок: ?bar= в адресе (ссылка сильнее) -> 'kultura.bar' -> старые ключи страниц
 * (dashboard_selected_venue — JSON-строка, gh.bar — строка), чтобы при переходе на стандарт
 * выбор не потерялся. 'all' — синоним всей сети.
 *
 * Обычный скрипт: window.KScope; для Node-тестов — module.exports.
 */
(function (root, factory) {
    var api = factory(root);
    root.KScope = api;
    if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis, function (root) {
    'use strict';

    var KEY = 'kultura.bar';
    var BARS = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'];

    // Любой доступ к localStorage — в try/catch: в приватном окне он бросает исключение.
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

    function getBar() {
        var candidates = [fromUrl(), read(KEY), read('dashboard_selected_venue'), read('gh.bar')];
        for (var i = 0; i < candidates.length; i++) {
            var v = normalize(candidates[i]);
            if (v !== null) return v;
        }
        return '';
    }

    // Запомнить выбор для всего сайта и записать ?bar= в адрес (вся сеть — без параметра).
    function setBar(raw, opts) {
        var v = normalize(raw);
        if (v === null) v = '';
        // Вся сеть — явным 'all': пустой ключ значил бы «не выбирали» и поднял бы старый ключ.
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

    return { KEY: KEY, BARS: BARS, getBar: getBar, setBar: setBar, normalize: normalize };
});

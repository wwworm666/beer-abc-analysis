/* ===== kultura.os — логотип, который рисуется ===== */
/*
 * Бренд «KULTURA — GRID MOTION» (brand/kultura-grid-motion, решение владельца 2026-11-07): машинный
 * набор в фиксированных ячейках — «kultura» группами ku / lt / ura (0 / 180 / 420 / 700 мс),
 * окончание по букве раз в 160 мс; только буквы и фирменная оранжевая точка #FF4B0A, без курсора;
 * готовый текст не двигается, не плавает и не масштабируется. Формулы и тайминги — те же, что у
 * рендера (brand/kultura-grid-motion/source/grid.cjs: prefix, suffix, dot, os, rail, hero), буквы —
 * контуры IBM Plex Mono Medium оттуда же (только нужные: «kultura.os»).
 *
 * Где: элемент с атрибутом data-kultura-logo, внутри — <svg class="kultura-logo-svg"> (пустой —
 * рисует этот файл):
 *   wordmark — «kultura.os» в шапке (shared/nav.html): кегль 100, ячейка 60, базовая линия 77,
 *              viewBox 0 0 600 80; «kultura» печатается сразу, «.os» — через 0,3 с после точки;
 *   lockup   — знак «k.» и название, как в общей заставке (hero, фаза os, до 1,95 с): страницы
 *              входа и согласия MCP; viewBox 160 390 1080 270.
 * Буквы — цвет текста (currentColor: светлая и тёмная тема), точка и квадрат знака — оранжевые.
 * Рисуется один раз за сеанс браузера (sessionStorage kultura_logo_typed); дальше и при «уменьшить
 * движение» в системе — сразу готовый логотип.
 */
(function () {
    'use strict';
    // Подключается и общим меню (shared/nav.html), и некоторыми страницами сами.
    if (window.__kulturaLogo) return;
    window.__kulturaLogo = true;

    var FONT = {"units":1000,"glyphs":{"r":{"path":"M76 88H213V428H76V516H322V379H328Q335 406 348.0 431.0Q361 456 381.0 474.5Q401 493 430.0 504.5Q459 516 498 516H560V412H458Q398 412 360.0 376.5Q322 341 322 281V88H509V0H76Z"},"o":{"path":"M300 -12Q243 -12 197.5 7.0Q152 26 120.5 61.0Q89 96 72.0 146.0Q55 196 55 258Q55 320 72.0 370.0Q89 420 120.5 455.0Q152 490 197.5 509.0Q243 528 300 528Q357 528 402.5 509.0Q448 490 479.5 455.0Q511 420 528.0 370.0Q545 320 545 258Q545 196 528.0 146.0Q511 96 479.5 61.0Q448 26 402.5 7.0Q357 -12 300 -12ZM300 74Q360 74 395.5 110.5Q431 147 431 219V297Q431 369 395.5 405.5Q360 442 300 442Q240 442 204.5 405.5Q169 369 169 297V219Q169 147 204.5 110.5Q240 74 300 74Z"},"l":{"path":"M75 88H246V652H75V740H355V88H526V0H75Z"},"k":{"path":"M88 740H197V293H202L283 376L428 516H557L348 313L580 0H449L269 251L197 184V0H88Z"},".":{"path":"M300 -10Q252 -10 232.5 10.0Q213 30 213 59V85Q213 114 232.5 134.0Q252 154 300 154Q348 154 367.5 134.0Q387 114 387 85V59Q387 30 367.5 10.0Q348 -10 300 -10Z"},"s":{"path":"M301 -12Q217 -12 156.5 15.0Q96 42 59 87L126 147Q160 110 202.5 90.5Q245 71 303 71Q356 71 388.5 89.0Q421 107 421 145Q421 161 415.0 172.0Q409 183 398.0 190.0Q387 197 372.5 201.0Q358 205 342 207L260 220Q230 224 199.0 233.0Q168 242 143.5 258.5Q119 275 103.5 301.0Q88 327 88 367Q88 446 148.5 487.0Q209 528 308 528Q380 528 432.5 506.5Q485 485 520 447L459 383Q439 406 402.0 425.5Q365 445 304 445Q195 445 195 376Q195 343 218.5 330.5Q242 318 274 314L356 301Q387 296 417.5 288.0Q448 280 472.5 263.5Q497 247 512.5 221.0Q528 195 528 155Q528 77 467.5 32.5Q407 -12 301 -12Z"},"t":{"path":"M331 0Q263 0 231.0 36.5Q199 73 199 131V428H40V516H153Q182 516 194.0 527.5Q206 539 206 569V698H308V516H528V428H308V88H528V0Z"}," ":{"path":""},"u":{"path":"M407 88H402Q394 68 381.5 49.5Q369 31 351.0 17.5Q333 4 309.0 -4.0Q285 -12 253 -12Q175 -12 127.0 39.0Q79 90 79 184V516H188V200Q188 77 295 77Q316 77 336.0 82.5Q356 88 372.0 99.0Q388 110 397.5 126.5Q407 143 407 166V516H516V0H407Z"},"a":{"path":"M492 0Q445 0 421.5 24.0Q398 48 393 87H388Q373 40 333.5 14.0Q294 -12 233 -12Q154 -12 107.0 29.5Q60 71 60 144Q60 219 115.5 258.5Q171 298 286 298H385V338Q385 443 274 443Q224 443 193.0 423.5Q162 404 141 372L76 425Q98 467 150.0 497.5Q202 528 284 528Q382 528 438.0 481.0Q494 434 494 345V86H559V0ZM264 68Q317 68 351.0 92.0Q385 116 385 154V229H288Q170 229 170 158V138Q170 103 195.0 85.5Q220 68 264 68Z"}}};
    var O = '#FF4B0A';            // фирменный оранжевый (README набора)
    var C = 'currentColor';
    var TYPE_STEP = 0.16;         // окончание: буква раз в 160 мс
    var SESSION_KEY = 'kultura_logo_typed';

    function clamp(v) { return Math.max(0, Math.min(1, v)); }
    function prog(t, a, d) { return clamp((t - a) / d); }
    function lerp(a, b, v) { return a + (b - a) * v; }
    function N(v) { return +v.toFixed(3); }
    // Короткий разгон, ровный ход и торможение без перелёта (rail в grid.cjs).
    function rail(q) {
        q = clamp(q);
        var r = 0.22;
        if (q < r) return q * q / (2 * r * (1 - r));
        if (q > 1 - r) return 1 - (1 - q) * (1 - q) / (2 * r * (1 - r));
        return (q - r / 2) / (1 - r);
    }
    function rect(x, y, w, h, c) {
        return w > 0 && h > 0 ? '<rect x="' + N(x) + '" y="' + N(y) + '" width="' + N(w) + '" height="' + N(h) +
            '" fill="' + c + '"/>' : '';
    }
    function glyph(ch, x, y, size, c) {
        var g = FONT.glyphs[ch];
        if (!g) return '';
        var k = size / FONT.units;
        return '<path d="' + g.path + '" fill="' + c + '" transform="translate(' + N(x) + ' ' + N(y) + ') scale(' +
            N(k) + ' ' + N(-k) + ')"/>';
    }
    function run(str, x, y, size, c) {
        var s = '';
        for (var i = 0; i < str.length; i++) s += glyph(str.charAt(i), x + i * size * 0.6, y, size, c);
        return s;
    }
    // «kultura» целыми состояниями: пусто, ku, kult, kultura — буквы не двигаются и не проявляются.
    function prefix(x, y, size, c, t, start) {
        var age = t - start;
        if (age < 0) return '';
        var n = age >= 0.70 - 1e-7 ? 7 : age >= 0.42 - 1e-7 ? 4 : age >= 0.18 - 1e-7 ? 2 : 0;
        return run('kultura'.slice(0, n), x, y, size, c);
    }
    function suffix(str, x, y, size, c, t, start) {
        if (t < start) return '';
        var n = Math.min(str.length, Math.floor((t - start + 1e-7) / TYPE_STEP));
        return run(str.slice(0, n), x, y, size, c);
    }
    // Точка — оранжевый квадрат в восьмой ячейке, на базовой линии.
    function dot(x, y, size) { return rect(x + size * 0.21, y - size * 0.18, size * 0.18, size * 0.18, O); }

    // Шапка: «kultura» с 0 с, точка — вместе с последней группой (0,7 с), «os» — с 1,0 с.
    var WORD_SUFFIX_AT = 1.0;
    function wordmark(t) {
        var size = 100, y = 77;
        var s = prefix(0, y, size, C, t, 0);
        if (t >= 0.70) s += dot(7 * 0.6 * size, y, size);
        return s + suffix('os', 8 * 0.6 * size, y, size, C, t, WORD_SUFFIX_AT);
    }

    // Знак os (grid.cjs, os): буква k выезжает из-под маски за 0,52 с, оранжевый квадрат — на 0,58 с.
    function osMark(t, id) {
        var s = '';
        var a = rail(prog(t, 0, 0.52));
        if (a > 0) {
            s += '<defs><clipPath id="' + id + '">' + rect(70, 85, 178 * a, 220, '#fff') + '</clipPath></defs>' +
                '<g clip-path="url(#' + id + ')"><g transform="translate(' + N(24 * (1 - a)) + ' 0)">' +
                run('k', 82, 300, 265, C) + '</g></g>';
        }
        if (t >= 0.58) s += rect(264, 266, 34, 34, O);
        return s;
    }
    // Как начало общей заставки (grid.cjs, hero): оранжевый квадрат из центра уходит на место точки
    // (0,2–0,7 с), «kultura» печатается с 0,58 с, «os» и знак приземляются вместе на 1,90 с.
    var HERO = {x: 600, y: 580, size: 104, prefixAt: 0.58, land: 1.90};
    function lockup(t, id) {
        var x = HERO.x, y = HERO.y, size = HERO.size, periodX = x + 7 * 0.6 * size, s = '';
        if (t < 0.70) {
            var q = rail(prog(t, 0.20, 0.50));
            var cx = lerp(960, periodX + size * 0.3, q), cy = lerp(540, y - size * 0.09, q), w = lerp(40, size * 0.18, q);
            s += rect(cx - w / 2, cy - w / 2, w, w, O);
        } else {
            s += dot(periodX, y, size);
        }
        s += prefix(x, y, size, C, t, HERO.prefixAt);
        s += suffix('os', x + 8 * 0.6 * size, y, size, C, t, HERO.land - 2 * TYPE_STEP);
        var markAt = HERO.land - 0.58;
        if (t >= markAt) {
            s += '<g transform="translate(320 532) scale(1.12)"><g transform="translate(-200 -200)">' +
                osMark(t - markAt, id) + '</g></g>';
        }
        return s;
    }

    var VIEWS = {
        wordmark: {viewBox: '0 0 600 80', frame: wordmark, end: WORD_SUFFIX_AT + 2 * TYPE_STEP},
        lockup: {viewBox: '160 390 1080 270', frame: lockup, end: HERO.land + 0.05}
    };

    function reducedMotion() {
        try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }
        catch (e) { return false; }
    }
    function seen() {
        try { return sessionStorage.getItem(SESSION_KEY) === '1'; } catch (e) { return true; }
    }
    function remember() {
        try { sessionStorage.setItem(SESSION_KEY, '1'); } catch (e) { /* приватный режим: просто не запомним */ }
    }

    var counter = 0;
    function prepare(el) {
        var view = VIEWS[el.getAttribute('data-kultura-logo')] || VIEWS.wordmark;
        var svg = el.querySelector('svg.kultura-logo-svg');
        if (!svg) {
            svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('class', 'kultura-logo-svg');
            svg.setAttribute('role', 'img');
            svg.setAttribute('aria-label', 'kultura.os');
            el.appendChild(svg);
        }
        svg.setAttribute('viewBox', view.viewBox);
        return {svg: svg, view: view, id: 'kultura-logo-mask-' + (counter++)};
    }
    function draw(item, t) { item.svg.innerHTML = item.view.frame(t, item.id); }

    function init() {
        var nodes = document.querySelectorAll('[data-kultura-logo]:not([data-kultura-logo-ready])');
        if (!nodes.length) return;
        var animate = !reducedMotion() && !seen();
        var items = [];
        for (var i = 0; i < nodes.length; i++) {
            nodes[i].setAttribute('data-kultura-logo-ready', '1');
            var item = prepare(nodes[i]);
            if (animate) { draw(item, 0); items.push(item); } else { draw(item, item.view.end + 1); }
        }
        if (!items.length || !window.requestAnimationFrame) {
            items.forEach(function (it) { draw(it, it.view.end + 1); });
            return;
        }
        var start = null;
        function tick(now) {
            if (start === null) start = now;
            var t = (now - start) / 1000, done = true;
            items.forEach(function (it) {
                draw(it, Math.min(t, it.view.end + 0.01));
                if (t < it.view.end) done = false;
            });
            if (done) remember(); else window.requestAnimationFrame(tick);
        }
        window.requestAnimationFrame(tick);
    }

    // Кадры — для проверки (tests/test_kultura_logo.mjs) и отладки в консоли.
    window.KulturaLogo = {wordmark: wordmark, lockup: lockup, views: VIEWS, init: init};

    // Логотип стоит выше этого скрипта — рисуем сразу, без пустой вспышки; остальное — по готовности.
    init();
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
})();

/* Куб OLAP на странице «Конструктор отчётов» (/explorer): живая схема отчёта.

   Что это
       Сводная таблица — срез куба данных «строки × столбцы × период». Куб в карточке
       над таблицей показывает, что пользователь собирает, пока отчёт не построен, и
       «работает», пока iiko считает. Декорации без смысла здесь нет: каждая деталь куба
       повторяет раскладку в зонах.

   Как куб читает раскладку (update)
       высота (вертикальная ось)   — «Строки»: строки таблицы идут вниз;
       ширина (горизонтальная ось) — «Столбцы»: столбцы идут вправо;
       глубина                     — период: ось времени, всегда DEPTH слоя;
       слоёв по оси строк и столбцов — segments(число полей): нет полей — 1 (ось не
       делится), одно поле — 3, два и больше — 4. Это символ «ось разбита значениями
       поля», а не число значений: их до построения отчёта никто не знает;
       заливка ячеек — «Показатели»: нет показателей — пустой каркас;
       фильтры — плоскость среза: задний слой куба гаснет, число фильтров — в подписи.
       Цвета осей повторяются в подписи рядом с кубом (legend).

   Движение
       'idle'     — куб медленно покачивается;
       'building' — iiko считает: куб вращается, по ячейкам снизу вверх идёт волна
                    «наполнения». Прогресса в процентах нет: iiko его не сообщает;
       pivot      — поле переехало между «Строками» и «Столбцами»: куб поворачивается
                    на 90° вокруг оси глубины (pivot — «поворот»), потом делится заново;
       unfold     — ответ пришёл: первые UNFOLD_ROWS строк таблицы «ложатся» из глубины
                    по UNFOLD_STEP_MS мс. Таблица при этом уже нарисована — анимация
                    данные не задерживает.
       При системной настройке «уменьшить движение» (prefers-reduced-motion) — всё
       неподвижно, поворот и разворот не играются.

   Куб — чистый CSS 3D (transform-style: preserve-3d), без библиотек: 6 граней-сеток,
   до 80 ячеек. Цвета — токены --ex-axis-*, --ex-cube-* (static/explorer/explorer.css),
   поэтому тёмная тема работает сама. Для чтения с экрана куб скрыт (aria-hidden),
   подпись — обычный текст.
*/
(function () {
    'use strict';

    var DEPTH = 3;               // слоёв по оси периода
    var PIVOT_MS = 640;          // поворот при переносе поля (как transition в CSS)
    var UNFOLD_ROWS = 24;        // строк таблицы, которые «ложатся» из глубины
    var UNFOLD_STEP_MS = 18;     // задержка между соседними строками
    var UNFOLD_ROW_MS = 520;     // длительность одной строки (как .ex-unfold-row в CSS)
    var WAVE_STEP_MS = 140;      // шаг волны «наполнения» между слоями снизу вверх

    // Грани: какая ось идёт по столбцам и строкам сетки грани.
    var FACES = [
        { name: 'front', cols: 'x', rows: 'y' },
        { name: 'back', cols: 'x', rows: 'y' },
        { name: 'right', cols: 'z', rows: 'y' },
        { name: 'left', cols: 'z', rows: 'y' },
        { name: 'top', cols: 'x', rows: 'z' },
        { name: 'bottom', cols: 'x', rows: 'z' }
    ];

    function esc(text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function plural(n, one, few, many) {
        var abs = Math.abs(Math.round(n)) % 100;
        var tail = abs % 10;
        if (abs > 10 && abs < 20) return many;
        if (tail > 1 && tail < 5) return few;
        if (tail === 1) return one;
        return many;
    }

    // Слоёв по оси строк или столбцов: нет полей — 1, одно — 3, два и больше — 4.
    function segments(count) {
        return count <= 0 ? 1 : (count === 1 ? 3 : 4);
    }

    // Поле переехало из строк в столбцы или обратно — это pivot (поворот куба).
    function pivoted(prev, next) {
        if (!prev || !next) return false;
        var moved = function (from, to) {
            return from.some(function (id) { return to.indexOf(id) >= 0; });
        };
        return moved(prev.rows, next.columns) || moved(prev.columns, next.rows);
    }

    function motionAllowed() {
        return !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    // Слой глубины ячейки грани (0 — передний, DEPTH-1 — задний) и уровень снизу вверх
    // для волны. Направления осей граней — из их поворотов в CSS (right: rotateY(90deg)
    // ведёт свою ось x назад, left — вперёд; top: rotateX(90deg) ведёт ось y вперёд,
    // bottom — назад).
    function cellPlace(face, r, c, n) {
        var depth = 0;
        var level = n.y - 1 - r;
        if (face === 'back') depth = DEPTH - 1;
        else if (face === 'right') depth = c;
        else if (face === 'left') depth = DEPTH - 1 - c;
        else if (face === 'top') { depth = DEPTH - 1 - r; level = n.y; }
        else if (face === 'bottom') { depth = r; level = 0; }
        return { depth: depth, level: level };
    }

    // Подпись к кубу: оси теми же цветами, что линии на кубе, и то, что стоит в зонах.
    function legendHtml(schema) {
        var line = function (axis, key, names, joiner, extra) {
            var text = names.length ? names.join(joiner) : '';
            var full = text + (extra || '');
            return '<div class="ex-cube-li' + (names.length ? '' : ' is-empty') + '" data-axis="' + axis +
                '"><i class="ex-cube-mk"></i>' +
                '<span class="ex-cube-lk">' + key + '</span><span class="ex-cube-lv' +
                (names.length ? '' : ' is-empty') + '" title="' + esc(full || 'не выбраны') + '">' +
                (names.length ? esc(text) + (extra ? '<small>' + esc(extra) + '</small>' : '') : 'не выбраны') +
                '</span></div>';
        };
        var filters = schema.filters || 0;
        var slice = filters ? ' · срез: ' + filters + ' ' + plural(filters, 'фильтр', 'фильтра', 'фильтров') : '';
        return line('rows', 'Строки', schema.rows || [], ' › ') +
            line('columns', 'Столбцы', schema.columns || [], ' › ') +
            line('measures', 'Показатели', schema.measures || [], ', ') +
            line('time', 'Период', schema.period ? [schema.period] : [], '', slice);
    }

    function Cube(host, legendHost) {
        this.host = host;
        this.legendHost = legendHost || null;
        this.counts = null;
        this.turning = null;
        host.classList.add('ex-cube');
        host.setAttribute('aria-hidden', 'true');
        host.setAttribute('data-mode', 'idle');
        host.innerHTML = '<div class="ex-cube-scene"><div class="ex-cube-tilt"><div class="ex-cube-sway">' +
            '<div class="ex-cube-spin"><div class="ex-cube-body">' +
            FACES.map(function (f) { return '<div class="ex-cube-face" data-face="' + f.name + '"></div>'; }).join('') +
            '<div class="ex-cube-slice"></div>' +
            '<div class="ex-cube-axis" data-axis="rows"></div>' +
            '<div class="ex-cube-axis" data-axis="columns"></div>' +
            '<div class="ex-cube-axis" data-axis="time"></div>' +
            '</div></div></div></div></div>';
        this.body = host.querySelector('.ex-cube-body');
    }

    // Сетки граней заново — только когда меняется число слоёв.
    Cube.prototype.grid = function (n, animate) {
        var host = this.host;
        host.style.setProperty('--ex-cube-nx', n.x);
        host.style.setProperty('--ex-cube-ny', n.y);
        host.style.setProperty('--ex-cube-nz', n.z);
        FACES.forEach(function (face) {
            var cols = n[face.cols];
            var rows = n[face.rows];
            var html = '';
            for (var r = 0; r < rows; r++) {
                for (var c = 0; c < cols; c++) {
                    var place = cellPlace(face.name, r, c, n);
                    html += '<i class="ex-cube-cell' + (animate ? ' is-new' : '') + '"' +
                        (place.depth === DEPTH - 1 ? ' data-back' : '') +
                        ' style="--ex-cube-delay:' + (place.level * WAVE_STEP_MS + c * 40) + 'ms"></i>';
                }
            }
            host.querySelector('.ex-cube-face[data-face="' + face.name + '"]').innerHTML = html;
        });
        this.counts = n;
    };

    Cube.prototype.update = function (schema) {
        var rows = (schema.rows || []).length;
        var columns = (schema.columns || []).length;
        var n = { x: segments(columns), y: segments(rows), z: DEPTH };
        var same = this.counts && this.counts.x === n.x && this.counts.y === n.y;
        if (!same) this.grid(n, !!this.counts && motionAllowed());
        this.host.classList.toggle('is-hollow', !(schema.measures || []).length);
        this.host.classList.toggle('no-rows', !rows);
        this.host.classList.toggle('no-cols', !columns);
        this.host.classList.toggle('has-slice', (schema.filters || 0) > 0);
        if (this.legendHost) this.legendHost.innerHTML = legendHtml(schema);
    };

    // Строки и столбцы поменялись: повернуть куб на 90° вокруг оси глубины, затем
    // разделить заново уже по новой раскладке.
    Cube.prototype.pivot = function (schema) {
        var self = this;
        if (!motionAllowed() || !this.counts) { this.update(schema); return; }
        if (this.legendHost) this.legendHost.innerHTML = legendHtml(schema);
        this.pending = schema;
        if (this.turning) return;
        this.body.classList.add('is-pivot');
        this.turning = setTimeout(function () {
            self.body.classList.add('no-anim');
            self.body.classList.remove('is-pivot');
            self.update(self.pending);
            void self.body.offsetWidth;   // применить мгновенный возврат до включения перехода
            self.body.classList.remove('no-anim');
            self.turning = null;
        }, PIVOT_MS + 20);
    };

    Cube.prototype.setMode = function (mode) {
        this.host.setAttribute('data-mode', mode === 'building' ? 'building' : 'idle');
    };

    // Ответ пришёл: первые строки таблицы «ложатся» из глубины куба.
    function unfold(wrap) {
        if (!wrap || !motionAllowed()) return;
        var rows = wrap.querySelectorAll('tbody tr');
        var count = Math.min(rows.length, UNFOLD_ROWS);
        for (var i = 0; i < count; i++) {
            rows[i].classList.add('ex-unfold-row');
            rows[i].style.setProperty('--ex-unfold-i', i);
        }
        wrap.classList.add('ex-unfolding');
        setTimeout(function () {
            wrap.classList.remove('ex-unfolding');
            for (var j = 0; j < count; j++) {
                rows[j].classList.remove('ex-unfold-row');
                rows[j].style.removeProperty('--ex-unfold-i');
            }
        }, count * UNFOLD_STEP_MS + UNFOLD_ROW_MS + 60);
    }

    window.ExplorerCube = {
        create: function (host, legendHost) { return host ? new Cube(host, legendHost) : null; },
        segments: segments,
        pivoted: pivoted,
        legendHtml: legendHtml,
        motionAllowed: motionAllowed,
        unfold: unfold,
        DEPTH: DEPTH,
        PIVOT_MS: PIVOT_MS,
        UNFOLD_ROWS: UNFOLD_ROWS
    };
})();

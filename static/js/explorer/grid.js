/* Сводная таблица конструктора отчётов (/explorer).

   Рисует ответ POST /api/explorer/report с format=pivot (core/olap_constructor.py,
   build_pivot): дерево строк (группы по полям строк, листья), у каждого узла — значения
   по столбцам (c) и «Итого» по строке (t), у корня — итоги столбцов и общий итог.
   Числа здесь НЕ пересчитываются: итоги групп, столбцов и общий итог приходят с
   сервера (суммы — сложением строк, уникальные чеки и средние — итогами iiko).
   На клиенте только формат, сортировка готовых значений и доли.

   Доли («Доля в столбце», «Доля в строке») показываются только у показателей, которые
   складываются (kind 'sum'): у уникальных чеков и средних доля от итога не имеет
   смысла — части не складываются в итог, — поэтому там остаётся само значение.

   Экспорт: window.ExplorerGrid = { prepare, render, fmtDimText }.
*/
(function () {
    'use strict';

    var CHEVRON = '<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">' +
        '<path d="M3.5 2 6.5 5 3.5 8" stroke="currentColor" stroke-width="1.6" fill="none" ' +
        'stroke-linecap="round" stroke-linejoin="round"/></svg>';

    function esc(text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // ==================== формат ====================

    var formats = {};
    function numberFormat(min, max) {
        var key = min + ':' + max;
        if (!formats[key]) {
            formats[key] = new Intl.NumberFormat('ru-RU', {
                minimumFractionDigits: min, maximumFractionDigits: max
            });
        }
        return formats[key];
    }
    // Типографский минус, а не дефис: в одной колонке стоят и доходы, и расходы.
    function num(value, min, max) {
        return numberFormat(min, max).format(value).replace(/^-/, '−');
    }
    function pad2(n) { return (n < 10 ? '0' : '') + n; }
    function duration(seconds) {
        var sign = seconds < 0 ? '−' : '';
        var s = Math.round(Math.abs(seconds));
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        return sign + h + ':' + pad2(m) + ':' + pad2(s % 60);
    }
    function isoDate(text) {
        var m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(String(text));
        if (!m) return null;
        var d = m[3] + '.' + m[2] + '.' + m[1];
        return m[4] ? d + ' ' + m[4] + ':' + m[5] + (m[6] ? ':' + m[6] : '') : d;
    }

    // Значение показателя: деньги — 2 знака, количество — до 3, проценты iiko (доля 0..1)
    // — умножаются на 100, длительности — ч:мм:сс.
    function fmtMeasure(value, type) {
        if (value === null || value === undefined) return '—';
        if (typeof value === 'string') return esc(isoDate(value) || value);
        if (isNaN(value)) return '—';
        switch (type) {
            case 'MONEY': return num(value, 2, 2);
            case 'AMOUNT': return num(value, 0, 3);
            case 'INTEGER': return num(value, 0, 0);
            case 'PERCENT': return num(value * 100, 2, 2) + '%';
            case 'DURATION_IN_SECONDS': return duration(value);
            default: return num(value, 0, 2);
        }
    }

    function enumLabel(field, value) {
        if (!field || !field.enum) return null;
        for (var i = 0; i < field.enum.length; i++) {
            if (field.enum[i][0] === value) return field.enum[i][1];
        }
        return null;
    }

    // Подпись значения разреза текстом (для title, сортировки, заголовков).
    // iiko отдаёт два вида пустого: null — «(пусто)», "" — «(пустая строка)»; это разные
    // значения (фильтр по одному не ловит другое), поэтому и подписи разные.
    function fmtDimText(value, field) {
        if (value === null || value === undefined) return '(пусто)';
        if (value === '') return '(пустая строка)';
        var label = enumLabel(field, value);
        if (label) return label;
        if (field && (field.type === 'DATE' || field.type === 'DATETIME')) {
            return isoDate(value) || String(value);
        }
        return String(value);
    }
    function isEmptyDim(value) { return value === null || value === undefined || value === ''; }
    function fmtDimHtml(value, field) {
        if (isEmptyDim(value)) return '<span class="ex-empty-val">' + fmtDimText(value, field) + '</span>';
        return esc(fmtDimText(value, field));
    }

    // ==================== подготовка дерева ====================

    // Путь узла (ключ раскрытия), исходный порядок, глубина, число листьев.
    function prepare(result) {
        var tree = result.tree;
        function walk(node, path, depth) {
            node._p = path;
            node._d = depth;
            if (!node.ch) {
                node._n = 1;
                return 1;
            }
            var total = 0;
            for (var i = 0; i < node.ch.length; i++) {
                var child = node.ch[i];
                child._i = i;
                total += walk(child, path + '\u0001' + String(child.k), depth + 1);
            }
            node._n = total;
            return total;
        }
        walk(tree, '', 0);
        return result;
    }

    // ==================== сортировка ====================

    function cellValue(node, col, m) {
        if (col < 0) return node.t ? node.t[m] : null;
        if (!node.c || !node.c[col]) return null;
        return node.c[col][m];
    }

    // Пустые значения — в конце (пустая строка перед null, как на сервере), в любом
    // направлении сортировки: направление применяется только к непустым.
    function emptyRank(v) { return v === '' ? 1 : (v === null || v === undefined) ? 2 : 0; }

    function compareDims(a, b, field) {
        var ra = emptyRank(a), rb = emptyRank(b);
        if (ra || rb) return ra - rb;
        if (typeof a === 'number' && typeof b === 'number') return a - b;
        if (field && (field.type === 'DATE' || field.type === 'DATETIME')) {
            return String(a) < String(b) ? -1 : String(a) > String(b) ? 1 : 0;
        }
        return fmtDimText(a, field).localeCompare(fmtDimText(b, field), 'ru', { numeric: true });
    }

    function sortTree(node, sort, fields) {
        if (!node.ch) return;
        var rowField = fields.rows[node._d];
        node.ch.sort(function (x, y) {
            if (!sort) return x._i - y._i;
            if (sort.type === 'label') {
                if (emptyRank(x.k) || emptyRank(y.k)) return compareDims(x.k, y.k, rowField);
                return sort.dir * compareDims(x.k, y.k, rowField);
            }
            var a = cellValue(x, sort.col, sort.m);
            var b = cellValue(y, sort.col, sort.m);
            var an = typeof a === 'number', bn = typeof b === 'number';
            if (!an && !bn) return x._i - y._i;
            if (!an) return 1;          // пустые — всегда в конце, в любом направлении
            if (!bn) return -1;
            return sort.dir * (a - b);
        });
        for (var i = 0; i < node.ch.length; i++) sortTree(node.ch[i], sort, fields);
    }

    // ==================== отрисовка ====================

    function colLabel(key, fields) {
        var parts = [];
        for (var i = 0; i < key.length; i++) parts.push(fmtDimText(key[i], fields.columns[i]));
        return parts.join(' · ');
    }

    function sortMark(sort, col, m) {
        if (!sort || sort.type !== 'measure' || sort.col !== col || sort.m !== m) return '';
        return '<span class="ex-sort">' + (sort.dir < 0 ? '↓' : '↑') + '</span>';
    }

    function measureHeaders(fields, col, sort, shares, grouped) {
        var html = '';
        for (var m = 0; m < fields.measures.length; m++) {
            var f = fields.measures[m];
            var sorted = sort && sort.type === 'measure' && sort.col === col && sort.m === m;
            var shareNote = shares !== 'none' && f.kind === 'sum' ? ', доля' : '';
            var title = f.name + (f.kind === 'sum' ? ' — итоги сложением строк'
                : ' — итоги из iiko (не складываются)');
            html += '<th class="' + (m === 0 && grouped ? 'is-first ' : '') +
                (sorted ? 'is-sorted' : '') + '" data-col="' + col + '" data-m="' + m +
                '" title="' + esc(title + '. Нажмите, чтобы отсортировать') + '">' +
                esc(f.name) + esc(shareNote) + sortMark(sort, col, m) + '</th>';
        }
        return html;
    }

    function valueCell(node, root, col, m, field, shares, extra) {
        var value = cellValue(node, col, m);
        var cls = 'ex-num' + (extra || '');
        if (value === null || value === undefined) {
            return '<td class="' + cls + ' is-empty">—</td>';
        }
        if (shares !== 'none' && field.kind === 'sum' && typeof value === 'number') {
            var base = shares === 'col' ? cellValue(root, col, m) : cellValue(node, -1, m);
            if (typeof base === 'number' && base !== 0) {
                return '<td class="' + cls + '" title="' + esc(fmtMeasure(value, field.type)) + '">' +
                    num(value / base * 100, 1, 1) + '%</td>';
            }
            return '<td class="' + cls + ' is-empty">—</td>';
        }
        return '<td class="' + cls + '">' + fmtMeasure(value, field.type) + '</td>';
    }

    function rowCells(node, root, fields, columns, shares) {
        var html = '';
        var mcount = fields.measures.length;
        for (var col = 0; col < columns.length; col++) {
            for (var m = 0; m < mcount; m++) {
                html += valueCell(node, root, col, m, fields.measures[m], shares,
                                  m === 0 ? ' is-first' : '');
            }
        }
        for (var t = 0; t < mcount; t++) {
            html += valueCell(node, root, -1, t, fields.measures[t], shares,
                              (columns.length ? ' ex-total' : '') + (t === 0 && columns.length ? ' is-first' : ''));
        }
        return html;
    }

    /*  opts: shares ('none'|'col'|'row'), sort, expanded {путь: bool}, defaultOpen,
        maxRows — сколько строк рисовать. Возвращает {shown, visible}: сколько строк
        нарисовано и сколько их видно при текущем раскрытии. */
    function render(target, result, opts) {
        var fields = result.fields;
        var columns = result.columns || [];
        var root = result.tree;
        var shares = opts.shares || 'none';
        var sort = opts.sort || null;
        var expanded = opts.expanded || {};
        sortTree(root, sort, fields);

        function isOpen(node) {
            if (Object.prototype.hasOwnProperty.call(expanded, node._p)) return expanded[node._p];
            return opts.defaultOpen !== false;
        }

        var rowTitle = fields.rows.length
            ? fields.rows.map(function (f) { return f.name; }).join(' / ')
            : 'Итого';
        var labelSorted = sort && sort.type === 'label';
        var rh = '<th class="ex-rh' + (labelSorted ? ' is-sorted' : '') + '" data-sort="label"' +
            (columns.length ? ' rowspan="2"' : '') + ' title="Нажмите, чтобы отсортировать по названию">' +
            esc(rowTitle) + (labelSorted ? '<span class="ex-sort">' + (sort.dir < 0 ? '↓' : '↑') +
            '</span>' : '') + '</th>';
        var head = '';
        var mcount = fields.measures.length;
        if (columns.length) {
            head += '<tr>' + rh;
            for (var c = 0; c < columns.length; c++) {
                head += '<th class="ex-colkey" colspan="' + mcount + '">' +
                    esc(colLabel(columns[c], fields)) + '</th>';
            }
            head += '<th class="ex-colkey" colspan="' + mcount + '">Итого</th></tr><tr>';
            for (var c2 = 0; c2 < columns.length; c2++) head += measureHeaders(fields, c2, sort, shares, true);
            head += measureHeaders(fields, -1, sort, shares, true) + '</tr>';
        } else {
            head += '<tr>' + rh + measureHeaders(fields, -1, sort, shares, false) + '</tr>';
        }

        var body = [];
        var shown = 0;
        var visible = 0;
        var max = opts.maxRows || 2000;
        function walk(node) {
            var children = node.ch || [];
            for (var i = 0; i < children.length; i++) {
                var child = children[i];
                var field = fields.rows[child._d - 1];
                var group = !!child.ch;
                visible++;
                if (shown < max) {
                    shown++;
                    var indent = 12 + (child._d - 1) * 18;
                    var open = group && isOpen(child);
                    var toggle = group
                        ? '<button type="button" class="ex-tog' + (open ? ' is-open' : '') +
                          '" data-path="' + esc(child._p) + '" aria-label="' +
                          (open ? 'Свернуть' : 'Развернуть') + '">' + CHEVRON + '</button>'
                        : '<span class="ex-tog-pad"></span>';
                    var label = fmtDimText(child.k, field);
                    var count = group ? ' <span class="ex-share">(' + child._n + ')</span>' : '';
                    body.push('<tr' + (group ? ' class="is-group"' : '') + '><td class="ex-rh" style="padding-left:' +
                        indent + 'px" title="' + esc(label) + '">' + toggle + fmtDimHtml(child.k, field) +
                        count + '</td>' + rowCells(child, root, fields, columns, shares) + '</tr>');
                }
                if (group && isOpen(child)) walk(child);
            }
        }
        walk(root);

        var foot = '<tr><td class="ex-rh">Итого</td>' + rowCells(root, root, fields, columns, shares) + '</tr>';
        target.innerHTML = '<table class="ex-grid"><thead>' + head + '</thead><tbody>' +
            body.join('') + '</tbody><tfoot>' + foot + '</tfoot></table>';

        // Вторая строка шапки прилипает под первой: её высота — по факту отрисовки.
        var first = target.querySelector('thead tr');
        if (first && columns.length) {
            target.querySelector('table').style.setProperty('--ex-head1', first.offsetHeight + 'px');
        }
        return { shown: shown, visible: visible };
    }

    window.ExplorerGrid = { prepare: prepare, render: render, fmtDimText: fmtDimText,
                            fmtMeasure: fmtMeasure, enumLabel: enumLabel, isoDate: isoDate };
})();

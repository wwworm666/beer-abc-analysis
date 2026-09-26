/* Страница «Фасовка — ABC/XYZ и потери» (/packaging).

   Устроена как /draft (static/js/draft/draft.js) и по тем же причинам: всё
   содержимое приходит ОДНИМ ответом /api/packaging — сводка, корзины действий,
   все категории, все фасовки. Поэтому сортировка, поиск и карточки работают без
   запросов: считаются по уже полученному блоку.

   Числа на клиенте не пересчитываются нигде, кроме форматирования, ширины шкал
   и итогов отфильтрованного среза: доли, наценки и буквы приходят посчитанными
   сервером (core/packaging_analysis.py), чтобы страница, документация и тесты
   говорили одно и то же.
*/
(function () {
    'use strict';

    // ==================== состояние ====================

    var state = {
        bar: '',                 // '' = все бары («Общая»)
        preset: 'd30',
        from: null,
        to: null,
        data: null,              // ответ /api/packaging
        query: '',
        catSort: { key: 'TotalRevenue', dir: -1 },
        posSort: { key: 'TotalRevenue', dir: -1 },
        loading: false,
        bars: []
    };

    var el = {};

    // ==================== формат ====================

    // Типографский минус, а не дефис: в карточке рядом стоят деньги и проценты,
    // и два разных знака в соседних строках читаются как опечатка.
    function num(value, digits) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        return new Intl.NumberFormat('ru-RU', {
            minimumFractionDigits: 0,
            maximumFractionDigits: digits === undefined ? 2 : digits
        }).format(value).replace(/^-/, '−');
    }
    function fixed(value, digits) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        return new Intl.NumberFormat('ru-RU', {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits
        }).format(value).replace(/^-/, '−');
    }
    function money(value) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        return num(Math.round(value), 0) + ' ₽';
    }
    // Доли всегда с одним знаком после запятой (10,0%, а не 10%), иначе колонка
    // прыгает. Ноль знаков просят явно — там, где место дорого.
    function pct(value, digits) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        return fixed(value, digits === undefined ? 1 : digits) + '%';
    }
    // Наценка округляется ВНИЗ до показанного знака: буква и решение считаются от
    // точного числа, и 119,5% не должно печататься как «120%» рядом с буквой B и
    // группой «Низкая наценка» (пороги 120/100 целые, поэтому округление вниз
    // никогда не переводит число через порог). Эпсилон гасит хвосты float.
    function markupPct(value, digits) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        var d = digits === undefined ? 1 : digits;
        var f = Math.pow(10, d);
        return pct(Math.floor(value * f + 1e-9) / f, d);
    }
    function esc(text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function dateISO(d) {
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
               '-' + String(d.getDate()).padStart(2, '0');
    }
    function dateRu(iso, withYear) {
        if (!iso) return '';
        var p = String(iso).split('-');
        return p[2] + '.' + p[1] + (withYear ? '.' + p[0] : '');
    }
    function rangeLabel(from, to) {
        if (!from || !to) return '';
        return dateRu(from) + ' — ' + dateRu(to, true);
    }
    // «28 категорий», «450 позиций», «30 дней» — иначе подписи звучат как робот.
    function plural(n, one, few, many) {
        var abs = Math.abs(Math.round(n)) % 100;
        var tail = abs % 10;
        if (abs > 10 && abs < 20) return many;
        if (tail > 1 && tail < 5) return few;
        if (tail === 1) return one;
        return many;
    }

    // ==================== период ====================

    function startOfWeek(d) {
        var day = d.getDay();
        var shift = day === 0 ? 6 : day - 1;   // неделя с понедельника
        var start = new Date(d);
        start.setDate(d.getDate() - shift);
        start.setHours(0, 0, 0, 0);
        return start;
    }

    function presetRange(key) {
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        var from = new Date(today), to = new Date(today);

        if (key === 'week') {
            from = startOfWeek(today);
        } else if (key === 'prev_week') {
            var thisMonday = startOfWeek(today);
            from = new Date(thisMonday);
            from.setDate(thisMonday.getDate() - 7);
            to = new Date(from);
            to.setDate(from.getDate() + 6);
        } else if (key === 'month') {
            from = new Date(today.getFullYear(), today.getMonth(), 1);
        } else if (key === 'prev_month') {
            from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            to = new Date(today.getFullYear(), today.getMonth(), 0);
        } else if (key === 'd30' || key === 'd90' || key === 'd180') {
            // Скользящие «N дней» заканчиваются ВЧЕРА (с 2026-09-26): сегодняшний
            // день неполный, и с ним последняя неделя XYZ и её столбик в карточке
            // были занижены. «Текущая неделя» и «текущий месяц» включают сегодня
            // по смыслу и остаются как есть.
            var span = key === 'd30' ? 30 : (key === 'd90' ? 90 : 180);
            to.setDate(today.getDate() - 1);
            from = new Date(to);
            from.setDate(to.getDate() - (span - 1));
        } else {
            return null;
        }
        return { from: dateISO(from), to: dateISO(to) };
    }

    // Порядок пресетов: сверху те, на которых XYZ вообще считается. Прошлая
    // неделя стоит последней и подписана прямо в меню — на одной неделе третья
    // буква не считается ни у кого, и раньше страница открывалась именно на
    // таком периоде, молча отдавая анализ без XYZ.
    var PRESETS = [
        { key: 'd30', label: 'Последние 30 дней' },
        { key: 'prev_month', label: 'Прошлый месяц' },
        { key: 'month', label: 'Текущий месяц' },
        { key: 'd90', label: 'Последние 90 дней' },
        { key: 'd180', label: 'Последние 180 дней' },
        { key: 'week', label: 'Текущая неделя' },
        { key: 'prev_week', label: 'Прошлая неделя' }
    ];

    function presetLabel(key) {
        for (var i = 0; i < PRESETS.length; i++) {
            if (PRESETS[i].key === key) return PRESETS[i].label;
        }
        return 'Свой период';
    }

    function weeksIn(from, to) {
        if (!from || !to) return 0;
        var days = Math.round((new Date(to) - new Date(from)) / 86400000) + 1;
        return Math.floor(days / 7);
    }

    function applyPreset(key) {
        var range = presetRange(key);
        state.preset = key;
        if (range) { state.from = range.from; state.to = range.to; }
        syncPickers();
    }

    function syncPickers() {
        el.barLabel.textContent = state.bar || 'Общая';
        el.perLabel.textContent = presetLabel(state.preset);
        el.perHint.textContent = rangeLabel(state.from, state.to);
    }

    // ==================== меню фильтров ====================

    function closeMenus() {
        el.barMenu.hidden = true;
        el.perMenu.hidden = true;
        el.catch_.hidden = true;
    }
    function openMenu(menu) {
        closeMenus();
        menu.hidden = false;
        el.catch_.hidden = false;
    }

    function buildBarMenu(bars) {
        var html = '<button type="button" class="pk-menu-item' +
            (state.bar ? '' : ' is-on') + '" data-bar=""><span>Общая</span>' +
            '<span>все точки</span></button>';
        bars.forEach(function (bar) {
            html += '<button type="button" class="pk-menu-item' +
                (state.bar === bar ? ' is-on' : '') + '" data-bar="' + esc(bar) + '">' +
                '<span>' + esc(bar) + '</span><span></span></button>';
        });
        el.barMenu.innerHTML = html;
    }

    function buildPerMenu() {
        var html = '';
        PRESETS.forEach(function (preset) {
            var range = presetRange(preset.key);
            var weeks = weeksIn(range.from, range.to);
            html += '<button type="button" class="pk-menu-item' +
                (state.preset === preset.key ? ' is-on' : '') +
                '" data-preset="' + preset.key + '">' +
                '<span>' + esc(preset.label) + '</span>' +
                '<span>' + (weeks < 3 ? 'без XYZ' : esc(rangeLabel(range.from, range.to))) +
                '</span></button>';
        });
        html += '<div class="pk-menu-item pk-menu-custom">' +
            '<div class="pk-menu-cap">СВОЙ ПЕРИОД</div>' +
            '<div class="pk-menu-dates">' +
            '<input type="date" id="pkFrom" value="' + esc(state.from || '') + '">' +
            '<input type="date" id="pkTo" value="' + esc(state.to || '') + '">' +
            '<button type="button" class="pk-run sm" id="pkCustom">ОК</button></div></div>';
        el.perMenu.innerHTML = html;
    }

    // ==================== запрос ====================

    function showMessage(text, isError) {
        el.msg.hidden = false;
        el.msg.className = 'pk-msg' + (isError ? ' err' : '');
        el.msg.textContent = text;
    }

    // Что именно запрошено: бар и период. Ответ, пришедший после смены фильтра,
    // выбрасывается, и сразу уходит запрос по новому выбору.
    function requestKey() {
        return [state.bar, state.from, state.to].join('|');
    }

    function run() {
        // Идёт запрос — новый выбор не теряется: он запустится по завершении
        // текущего (см. ниже). До 2026-09-26 run() молча выходил, и кнопка бара
        // показывала одно, а таблицы — другое.
        if (state.loading) return;
        if (!state.from || !state.to) {
            showMessage('Выберите период', true);
            return;
        }
        var key = requestKey();
        state.loading = true;
        el.spin.hidden = false;
        el.runLabel.textContent = 'Считаю…';
        el.run.disabled = true;
        el.body.hidden = true;
        showMessage('Забираем из iiko продажи фасовки за период…');

        fetch('/api/packaging', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bar: state.bar, date_from: state.from, date_to: state.to })
        }).then(function (response) {
            return response.json().then(function (payload) {
                return { ok: response.ok, payload: payload, status: response.status };
            });
        }).then(function (result) {
            if (key !== requestKey()) return;       // фильтр сменился, ответ устарел
            if (!result.ok) {
                // Сервер присылает причину («Нет данных за выбранный период») —
                // показываем её, а не общее «ошибка запроса».
                throw new Error((result.payload && result.payload.error) ||
                                ('HTTP ' + result.status));
            }
            state.data = result.payload;
            state.query = '';
            el.search.value = '';
            render();
        }).catch(function (error) {
            if (key !== requestKey()) return;
            state.data = null;
            el.body.hidden = true;
            showMessage(error.message, true);
        }).then(function () {
            state.loading = false;
            el.spin.hidden = true;
            el.runLabel.textContent = 'Запустить анализ';
            el.run.disabled = false;
            if (key !== requestKey()) run();        // пока ждали, выбрали другое
        });
    }

    // ==================== отрисовка ====================

    function render() {
        var data = state.data;
        if (!data) return;
        el.msg.hidden = true;
        el.body.hidden = false;

        var period = data.period || {};
        var scope = data.bar_label + (data.scope === 'total'
            ? ' (' + (data.bars_in_scope || []).length + ' ' +
              plural((data.bars_in_scope || []).length, 'бар', 'бара', 'баров') + ')'
            : '');
        // Окно недель называется явно: период 30 дней не делится на 7, и без
        // этой подписи «4 полные недели» читается как «весь период покрыт».
        var weeksPart = period.weeks + ' ' +
            plural(period.weeks, 'полная неделя', 'полные недели', 'полных недель');
        if (period.weeks_from && period.weeks_from !== period.from) {
            weeksPart += ' (' + rangeLabel(period.weeks_from, period.weeks_to) + ')';
        }
        el.context.textContent = 'разрез: ' + scope + ' · ' +
            rangeLabel(period.from, period.to) + ' · ' + period.days + ' дн. · ' + weeksPart;

        if (data.xyz_available) {
            el.xyzChip.hidden = true;
        } else {
            el.xyzChip.hidden = false;
            el.xyzChip.textContent = 'XYZ не считается: нужно от ' +
                data.min_xyz_weeks + ' полных недель';
        }

        if (data.generated_at) {
            el.updated.hidden = false;
            el.updated.textContent = 'обновлено ' + data.generated_at;
        } else {
            el.updated.hidden = true;
        }

        renderSummary(data);
        renderBuckets(data);
        renderCategories();
        renderPositions();
        renderBalance(data);
        renderLosses(data);
        renderDiagnostics(data);
    }

    function tile(cap, value, unit, sub) {
        return '<div class="pk-tile"><div class="pk-tile-cap">' + esc(cap) + '</div>' +
            '<div class="pk-tile-v">' + value +
            (unit ? '<u> ' + esc(unit) + '</u>' : '') + '</div>' +
            '<div class="pk-tile-s">' + esc(sub) + '</div></div>';
    }

    function renderSummary(data) {
        var t = data.totals || {};
        var html = '';
        html += tile('ВЫРУЧКА', num(Math.round(t.revenue), 0), '₽',
            'фасовка, со скидками');
        html += tile('ПРОДАНО', num(t.qty, 0), 'шт',
            'бутылок и банок за период');
        html += tile('ПОЗИЦИЙ', num(t.sku, 0), '',
            t.sku + ' ' + plural(t.sku, 'фасовка', 'фасовки', 'фасовок') + ' в продаже');
        html += tile('КАТЕГОРИЙ', num(t.categories, 0), '',
            'все показаны ниже');
        html += tile('НАЦЕНКА', t.markup_percent === null ? '—'
                : markupPct(t.markup_percent, 1).replace('%', ''), '%',
            '(выручка − себестоимость) / себестоимость');
        html += tile('МАРЖА', num(Math.round(t.margin), 0), '₽',
            'выручка минус себестоимость');
        html += tile('СРЕДНЯЯ ЦЕНА', num(Math.round(t.price_per_unit), 0), '₽',
            'выручка / штуки');
        el.sum.innerHTML = html;
    }

    // Корзины действий: порядок и подписи повторяют core/abc_buckets.py.
    // Держать их синхронно важно — сервер присылает только ключ.
    // Группы решений приходят с сервера целиком (core/abc_buckets.py): имя,
    // действие, тон, счётчик, доля выручки, правило словами. Страница только
    // печатает — раньше долю выручки складывал JS, а имена жили в двух местах.
    function bucketCard(key) {
        var cards = (state.data && state.data.buckets) || [];
        for (var i = 0; i < cards.length; i++) {
            if (cards[i].key === key) return cards[i];
        }
        return null;
    }

    function renderBuckets(data) {
        var html = '';
        (data.buckets || []).forEach(function (bucket) {
            html += '<button type="button" class="pk-bucket" data-bucket="' + esc(bucket.key) + '">' +
                '<span class="pk-bucket-top"><span class="pk-led ' + esc(bucket.tone) + '"></span>' +
                '<span class="pk-bucket-n">' + esc(bucket.name) + '</span></span>' +
                '<div class="pk-bucket-v">' + bucket.count +
                '<u> ' + plural(bucket.count, 'позиция', 'позиции', 'позиций') + '</u></div>' +
                '<div class="pk-bucket-s">' + esc(bucket.action) + ' · ' +
                pct(bucket.revenue_share_percent, 1) + ' выручки</div></button>';
        });
        el.buckets.innerHTML = html;
    }

    function sortRows(rows, sort) {
        var copy = rows.slice();
        copy.sort(function (a, b) {
            var av = a[sort.key], bv = b[sort.key];
            // Позиции без значения («—», наценка не определена) всегда в конце,
            // в обе стороны сортировки. Раньше они подменялись на -Infinity и
            // при сортировке по возрастанию вставали первыми, как будто у них
            // худшая наценка — а у них её просто нет.
            var aMissing = av === null || av === undefined || isNaN(av);
            var bMissing = bv === null || bv === undefined || isNaN(bv);
            if (aMissing && bMissing) return 0;
            if (aMissing) return 1;
            if (bMissing) return -1;
            if (av === bv) return 0;
            return av > bv ? sort.dir : -sort.dir;
        });
        return copy;
    }

    function sortMark(sort, key) {
        return sort.key === key ? (sort.dir < 0 ? ' ↓' : ' ↑') : '';
    }

    function abcClass(letter) {
        return String(letter || '').charAt(0).toLowerCase();
    }

    function shareCell(percent, maxPercent) {
        var width = maxPercent > 0 ? Math.max(2, (percent / maxPercent) * 100) : 0;
        return '<span class="pk-share"><span class="pk-bar"><i style="width:' +
            width.toFixed(1) + '%"></i></span>' +
            '<span class="pk-share-v">' + pct(percent, 1) + '</span></span>';
    }

    // ---------- категории ----------

    function renderCategories() {
        var data = state.data;
        // ВСЕ категории разреза, без урезания: раньше здесь стоял срез первых
        // десяти, и таблица со сводкой под тем же заголовком показывала другое
        // количество, чем карточки над ней.
        var rows = sortRows(data.categories || [], state.catSort);
        var maxShare = rows.reduce(function (acc, c) {
            return Math.max(acc, c.RevenueSharePercent || 0);
        }, 0);
        var maxQtyShare = rows.reduce(function (acc, c) {
            return Math.max(acc, c.QtySharePercent || 0);
        }, 0);

        el.catCount.textContent = rows.length + ' ' +
            plural(rows.length, 'категория', 'категории', 'категорий') + ' · все';

        var html = '<div class="pk-row is-head">' +
            '<span class="pk-th">#</span>' +
            '<span class="pk-th">КАТЕГОРИЯ</span>' +
            '<span class="pk-th r s" data-sort="BeersCount">ПОЗИЦИЙ' +
                sortMark(state.catSort, 'BeersCount') + '</span>' +
            '<span class="pk-th r s" data-sort="TotalQty">ШТУК' +
                sortMark(state.catSort, 'TotalQty') + '</span>' +
            '<span class="pk-th r s" data-sort="TotalRevenue">ВЫРУЧКА' +
                sortMark(state.catSort, 'TotalRevenue') + '</span>' +
            // Только доля: накопленный процент в ячейку не влезает, и
            // заголовок, обещающий два числа при одном показанном, врёт.
            // Накопленный итог есть в карточке категории.
            '<span class="pk-th r s" data-sort="RevenueSharePercent">ДОЛЯ В ВЫРУЧКЕ' +
                sortMark(state.catSort, 'RevenueSharePercent') + '</span>' +
            '<span class="pk-th r s" data-sort="QtySharePercent">ДОЛЯ В ШТУКАХ' +
                sortMark(state.catSort, 'QtySharePercent') + '</span>' +
            '<span class="pk-th r s" data-sort="TotalMargin">МАРЖА' +
                sortMark(state.catSort, 'TotalMargin') + '</span>' +
            '<span class="pk-th r s" data-sort="MarkupPercent">НАЦЕНКА' +
                sortMark(state.catSort, 'MarkupPercent') + '</span>' +
            '<span class="pk-th c">ABC</span>' +
            '</div>';

        rows.forEach(function (cat, index) {
            html += '<div class="pk-row is-body" data-cat="' + esc(cat.Category) + '">' +
                '<span class="pk-rank">' + (index + 1) + '</span>' +
                '<span class="pk-name">' + esc(cat.Category) + '</span>' +
                '<span class="pk-num">' + cat.BeersCount + '</span>' +
                '<span class="pk-num">' + num(cat.TotalQty, 0) + '</span>' +
                '<span class="pk-num strong">' + money(cat.TotalRevenue) + '</span>' +
                shareCell(cat.RevenueSharePercent, maxShare) +
                shareCell(cat.QtySharePercent, maxQtyShare) +
                '<span class="pk-num">' + money(cat.TotalMargin) + '</span>' +
                '<span class="pk-num">' +
                    markupPct(cat.MarkupPercent, 0) + '</span>' +
                '<span class="pk-cell-c"><span class="pk-abc ' + abcClass(cat.ABC_Category) +
                    '">' + esc(cat.ABC_Category) + '</span></span>' +
                '</div>';
        });

        if (!rows.length) {
            html += '<div class="pk-empty">за период продаж фасовки не было</div>';
        } else {
            var t = state.data.totals || {};
            html += '<div class="pk-row is-total">' +
                '<span></span>' +
                '<span class="pk-total-n">Итого · ' + rows.length + ' ' +
                    plural(rows.length, 'категория', 'категории', 'категорий') + '</span>' +
                '<span class="pk-total-v">' + t.sku + '</span>' +
                '<span class="pk-total-v">' + num(t.qty, 0) + '</span>' +
                '<span class="pk-total-v strong">' + money(t.revenue) + '</span>' +
                '<span class="pk-total-v">100,0%</span>' +
                '<span class="pk-total-v">100,0%</span>' +
                '<span class="pk-total-v">' + money(t.margin) + '</span>' +
                '<span class="pk-total-v">' +
                    markupPct(t.markup_percent, 0) + '</span>' +
                '<span></span></div>';
        }
        el.cats.innerHTML = html;
    }

    // ---------- позиции ----------

    function renderPositions() {
        var data = state.data;
        var rows = data.positions || [];
        var query = state.query.trim().toLowerCase();
        if (query) {
            rows = rows.filter(function (p) {
                return String(p.Beer || '').toLowerCase().indexOf(query) >= 0 ||
                       String(p.Category || '').toLowerCase().indexOf(query) >= 0;
            });
        }
        rows = sortRows(rows, state.posSort);
        var maxShare = rows.reduce(function (acc, p) {
            return Math.max(acc, p.RevenueSharePercent || 0);
        }, 0);
        var maxQtyShare = rows.reduce(function (acc, p) {
            return Math.max(acc, p.QtySharePercent || 0);
        }, 0);

        var total = (data.positions || []).length;
        el.posCount.textContent = query
            ? rows.length + ' из ' + total
            : total + ' ' + plural(total, 'позиция', 'позиции', 'позиций');

        var html = '<div class="pk-row is-head">' +
            '<span class="pk-th">#</span>' +
            '<span class="pk-th">ФАСОВКА</span>' +
            '<span class="pk-th">КАТЕГОРИЯ</span>' +
            '<span class="pk-th r s" data-sort="TotalQty">ШТУК' +
                sortMark(state.posSort, 'TotalQty') + '</span>' +
            '<span class="pk-th r s" data-sort="TotalRevenue">ВЫРУЧКА' +
                sortMark(state.posSort, 'TotalRevenue') + '</span>' +
            '<span class="pk-th r s" data-sort="RevenueSharePercent">ДОЛЯ В ВЫРУЧКЕ' +
                sortMark(state.posSort, 'RevenueSharePercent') + '</span>' +
            '<span class="pk-th r s" data-sort="QtySharePercent">ДОЛЯ В ШТУКАХ' +
                sortMark(state.posSort, 'QtySharePercent') + '</span>' +
            '<span class="pk-th r s" data-sort="MarkupPercent">НАЦЕНКА' +
                sortMark(state.posSort, 'MarkupPercent') + '</span>' +
            // Колонки XYZ нет (с 2026-09-26): она повторяла третью букву кода.
            '<span class="pk-th c">ABC</span>' +
            '</div>';

        rows.forEach(function (p, index) {
            html += '<div class="pk-row is-body" data-pos="' + p.Id + '">' +
                '<span class="pk-rank">' + (index + 1) + '</span>' +
                '<span class="pk-name">' + esc(p.Beer) + '</span>' +
                '<span class="pk-sub">' + esc(p.Category) + '</span>' +
                '<span class="pk-num">' + num(p.TotalQty, 0) + '</span>' +
                '<span class="pk-num strong">' + money(p.TotalRevenue) + '</span>' +
                shareCell(p.RevenueSharePercent, maxShare) +
                shareCell(p.QtySharePercent, maxQtyShare) +
                '<span class="pk-num' + (p.MarkupPercent === null ? ' dash' : '') + '">' +
                    markupPct(p.MarkupPercent, 0) + '</span>' +
                '<span class="pk-cell-c"><span class="pk-abc ' + abcClass(p.ABC_Revenue) +
                    '">' + esc(p.ABC_Combined) + '</span></span>' +
                '</div>';
        });

        if (!rows.length) {
            html += '<div class="pk-empty">' + (total
                ? 'ничего не найдено — уточните запрос'
                : 'продаж фасовки за период нет — ниже только движения склада') + '</div>';
        } else {
            var sumQty = rows.reduce(function (a, p) { return a + p.TotalQty; }, 0);
            var sumRevenue = rows.reduce(function (a, p) { return a + p.TotalRevenue; }, 0);
            var sumCost = rows.reduce(function (a, p) { return a + p.TotalCost; }, 0);
            var sumShare = rows.reduce(function (a, p) { return a + p.RevenueSharePercent; }, 0);
            var sumQtyShare = rows.reduce(function (a, p) { return a + (p.QtySharePercent || 0); }, 0);
            html += '<div class="pk-row is-total">' +
                '<span></span>' +
                '<span class="pk-total-n">Итого · ' + rows.length + ' ' +
                    plural(rows.length, 'позиция', 'позиции', 'позиций') + '</span>' +
                '<span></span>' +
                '<span class="pk-total-v">' + num(sumQty, 0) + '</span>' +
                '<span class="pk-total-v strong">' + money(sumRevenue) + '</span>' +
                '<span class="pk-total-v">' + pct(sumShare, 1) + '</span>' +
                '<span class="pk-total-v">' + pct(sumQtyShare, 1) + '</span>' +
                '<span class="pk-total-v">' +
                    (sumCost > 0 ? markupPct((sumRevenue - sumCost) / sumCost * 100, 0) : '—') +
                    '</span>' +
                '<span></span></div>';
        }
        el.pos.innerHTML = html;
    }

    // ==================== баланс и расхождения ====================

    // Знак ставим сами: минус из Intl выглядит как дефис, а в балансе важно, что
    // строка расходная — даже при нуле («−0» у перемещений).
    function signed(magnitude, sign) {
        if (magnitude === null || magnitude === undefined || isNaN(magnitude)) return '—';
        return sign + qty(Math.abs(magnitude));
    }
    // Штуки: целые без дробной части («48»), дробь не прячется («0,5»). Столбик
    // «48,00», как у литров на /draft, для бутылок читался бы как ошибка.
    function qty(value) {
        return num(value, 2);
    }

    // Цвет плашки «% от продаж»: до 10% спокойный, до 30% янтарный, выше красный.
    // Пороги те же, что на /draft (там выведены из факта: 9,2% недостачи розлива
    // за 3,5 месяца). Для фасовки своего факта ещё нет — пересмотреть после
    // первого живого периода, это временная граница, а не вывод из данных.
    function lossTone(percent) {
        if (percent === null || percent === undefined || isNaN(percent)) return 'calm';
        if (percent >= 30) return 'bad';
        if (percent >= 10) return 'warn';
        return 'calm';
    }

    function balanceRow(label, value, sign, scale, tone, pill) {
        var width = scale > 0 ? Math.min(100, Math.abs(value) / scale * 100) : 0;
        return '<div class="pk-bal-row">' +
            '<span class="pk-bal-n">' + esc(label) + '</span>' +
            '<span class="pk-bal-track' + (tone ? ' ' + tone : '') + '">' +
                (Math.abs(value) > 0 ? '<i style="width:' + width.toFixed(1) + '%"></i>' : '') +
                '</span>' +
            '<span class="pk-bal-v ' + (Math.abs(value) < 0.005 ? 'zero' : (tone || '')) + '">' +
                signed(value, sign) + '</span>' +
            '<span>' + (pill || '') + '</span></div>';
    }

    function renderBalance(data) {
        var losses = data.losses || {};
        // Масштаб общий для всех полос: иначе списание 2 шт выглядит как продажа 1 800.
        var scale = Math.max(losses.sold || 0, losses.invoice_in || 0, 1);
        var html = '<div class="pk-card-h"><span class="pk-card-t">Баланс фасовки за период</span>' +
            '<span class="pk-card-s">склад iiko</span></div>';

        if (!losses.diagnostics || !losses.diagnostics.has_transactions) {
            html += '<div class="pk-empty" style="border-top:none">' +
                'проводки склада за период не пришли — баланса нет</div>';
            el.balance.innerHTML = html;
            return;
        }

        html += balanceRow('Приход по накладным', losses.invoice_in, '+', scale, 'ok');
        html += balanceRow('Перемещения · приход', losses.transfer_in, '+', scale, '');
        html += balanceRow('Перемещения · расход', losses.transfer_out, '−', scale, '');
        html += balanceRow('Продано через кассу', losses.sold, '−', scale, '');
        html += balanceRow('Списано актами', losses.writeoff, '−', scale, 'warn',
            losses.sold > 0 ? '<span class="pk-pill warn">' +
                pct(losses.writeoff_percent_of_sold, 1) + ' от продаж</span>' : '');
        // Нетто-излишек — не потеря: подпись, знак и цвет другие, иначе строка
        // «Недостача −4» читалась бы как пропажа, хотя остаток вырос.
        if (losses.inventory_net < 0) {
            html += balanceRow('Излишек по инвентаризациям', losses.inventory_net, '+', scale, 'ok',
                losses.sold > 0 ? '<span class="pk-pill ok">' +
                    pct(-losses.inventory_percent_of_sold, 1) + ' от продаж</span>' : '');
        } else {
            html += balanceRow('Недостача по инвентаризациям', losses.inventory_net, '−', scale, 'bad',
                losses.sold > 0 ? '<span class="pk-pill bad">' +
                    pct(losses.inventory_percent_of_sold, 1) + ' от продаж</span>' : '');
        }

        html += '<div class="pk-bal-total">' +
            '<span class="pk-bal-total-n">Изменение остатка фасовки</span>' +
            '<span class="pk-bal-lead"></span>' +
            '<span class="pk-bal-total-v">' +
            signed(losses.balance, losses.balance < 0 ? '−' : '+') + ' шт</span></div>' +
            // Формула словами и числами — требование CLAUDE.md пункт 1. Оба
            // итога (received, spent) приходят с сервера, здесь ничего не складывается.
            '<div class="pk-note">приход ' + qty(losses.received) +
            ' − расход ' + qty(losses.spent) +
            ' (продано ' + qty(losses.sold) + ' + акты ' + qty(losses.writeoff) +
            (losses.inventory_net < 0
                ? ' − излишек ' + qty(-losses.inventory_net)
                : ' + недостача ' + qty(losses.inventory_net)) +
            ' + перемещения ' + qty(losses.transfer_out) +
            ') · товар фасовки списывается при продаже сам, без техкарты</div>';
        el.balance.innerHTML = html;
    }

    // Недостача строки: по барам (сервер, с 2026-09-26) — в «Общей» излишек
    // одного бара не гасит недостачу другого. Показываем недостачу; если её нет,
    // а излишек есть — излишек со знаком плюс.
    function shortageCell(short, surplus) {
        if (short > 0) {
            return qty(short) + (surplus > 0
                ? '<i class="pk-loss-plus"> +' + qty(surplus) + '</i>' : '');
        }
        return surplus > 0 ? signed(surplus, '+') : '0';
    }

    function lossRow(row, maxLoss) {
        var loss = row.LossQty || 0;
        // Излишек (недостача с минусом) — не потеря: полосы у такой строки нет,
        // иначе красная засечка читалась бы как «тут пропало».
        var width = (maxLoss > 0 && loss > 0) ? Math.max(4, loss / maxLoss * 100) : 0;
        var linked = row.PositionId !== null && row.PositionId !== undefined;
        return '<div class="pk-loss-row' + (linked ? '' : ' is-static') + '"' +
            (linked ? ' data-pos="' + row.PositionId + '"' : '') + '>' +
            '<span class="pk-loss-n">' + esc(row.ProductName) + '</span>' +
            '<span class="pk-num">' + (row.WriteoffQty ? qty(row.WriteoffQty) : '0') + '</span>' +
            '<span class="pk-share">' +
                '<span class="pk-bar pk-loss-bar"><i style="width:' + width.toFixed(1) +
                '%"></i></span>' +
                '<span class="pk-loss-v">' +
                shortageCell(row.InventoryShortQty || 0, row.InventorySurplusQty || 0) +
                '</span></span>' +
            '<span class="pk-pill ' + lossTone(row.LossPercentOfSold) + '">' +
                (row.LossPercentOfSold === null || row.LossPercentOfSold === undefined
                    ? '—' : pct(row.LossPercentOfSold, 1)) + '</span>' +
            '</div>';
    }

    function renderLosses(data) {
        var losses = data.losses || {};
        var rows = losses.by_item || [];
        var totalLoss = rows.reduce(function (acc, row) { return acc + (row.LossQty || 0); }, 0);
        var maxLoss = rows.reduce(function (acc, row) { return Math.max(acc, row.LossQty || 0); }, 0);

        var html = '<div class="pk-card-h"><span class="pk-card-t">Где именно расхождения</span>' +
            '<span class="pk-card-s">' + rows.length + ' ' +
            plural(rows.length, 'позиция', 'позиции', 'позиций') + ' · ' + qty(totalLoss) +
            ' шт потерь</span></div>';

        if (!losses.diagnostics || !losses.diagnostics.has_transactions) {
            html += '<div class="pk-empty" style="border-top:none">' +
                'проводки склада за период не пришли — расхождений не видно</div>';
            el.losses.innerHTML = html;
            return;
        }
        if (!rows.length) {
            html += '<div class="pk-empty" style="border-top:none">' +
                'за период расхождений по фасовке не было</div>';
            el.losses.innerHTML = html;
            return;
        }

        html += '<div class="pk-loss-row is-head">' +
            '<span class="pk-th">ПОЗИЦИЯ</span>' +
            '<span class="pk-th r">АКТЫ</span>' +
            '<span class="pk-th r">НЕДОСТАЧА</span>' +
            '<span class="pk-th r">% ОТ ПРОДАЖ</span></div>';

        // Первые восемь видны сразу, остальные под раскрывашкой — как на /draft.
        var head = rows.slice(0, 8), tail = rows.slice(8);
        head.forEach(function (row) { html += lossRow(row, maxLoss); });

        if (tail.length) {
            var tailLoss = tail.reduce(function (acc, row) { return acc + (row.LossQty || 0); }, 0);
            html += '<details class="pk-more"><summary>ещё ' + tail.length + ' ' +
                plural(tail.length, 'позиция', 'позиции', 'позиций') + ' · ' + qty(tailLoss) +
                ' шт потерь' +
                '<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">' +
                '<path d="M2 3.5 5 6.5 8 3.5" stroke-width="1.6" fill="none" ' +
                'stroke-linecap="round" stroke-linejoin="round"/></svg></summary>';
            tail.forEach(function (row) { html += lossRow(row, maxLoss); });
            html += '</details>';
        }

        html += '<div class="pk-note">% — потери (акты + недостача) к проданному по складу · ' +
            'недостача считается по каждому бару: излишек одного бара не гасит недостачу ' +
            'другого · «+N» — излишек · ' +
            '«—» — позиция не продавалась · серые строки — товар склада, которого нет ' +
            'среди проданных позиций периода (нет продаж или другое имя в номенклатуре) · ' +
            'клик по строке открывает карточку</div>';
        el.losses.innerHTML = html;
    }

    function renderDiagnostics(data) {
        var losses = data.losses || {};
        var diag = losses.diagnostics || {};
        var parts = [];
        if (diag.has_transactions && Math.abs(diag.sold_delta || 0) > 0.005) {
            parts.push('по кассе продано ' + qty(diag.sold_by_register) + ' шт, по складу списано ' +
                qty(diag.sold_by_stock) + ' шт: разница ' +
                signed(diag.sold_delta, diag.sold_delta < 0 ? '−' : '+') +
                ' — граница учётного дня, наборы (в продажах набор — одна позиция, ' +
                'на складе списываются бутылки из него) или позиции без карточки склада');
        }
        if ((diag.non_piece_products || []).length) {
            parts.push('не в штуках, в баланс не вошли: ' +
                diag.non_piece_products.map(function (p) {
                    return esc(p.ProductName) + ' (расход ' + qty(p.Out) + ' ' + esc(p.Unit) +
                        (p.In ? ', приход ' + qty(p.In) + ' ' + esc(p.Unit) : '') + ')';
                }).join(', '));
        }
        var ignored = Object.keys(diag.ignored_types || {});
        if (ignored.length) {
            parts.push('проводки других типов (возвраты и т.п.) в баланс не входят: ' +
                ignored.map(function (k) {
                    var t = diag.ignored_types[k] || {};
                    return esc(k) + ' × ' + (t.rows || 0) + ' (расход ' + qty(t.out || 0) +
                        ', приход ' + qty(t.in || 0) + ' шт)';
                }).join(', '));
        }
        if (diag.unmatched_products) {
            parts.push(diag.unmatched_products + ' ' +
                plural(diag.unmatched_products, 'позиция склада не сопоставлена',
                    'позиции склада не сопоставлены', 'позиций склада не сопоставлено') +
                ' с продажами');
        }
        if (diag.has_transactions && diag.match_mode === 'name') {
            parts.push('связка склада с продажами — по названию: в продажах нет DishId');
        }
        el.diag.innerHTML = parts.length ? parts.join(' · ') : '';
    }

    // ==================== карточки ====================

    function cell(cap, value, extraClass) {
        return '<div class="pk-cell"><div class="pk-cell-cap">' + esc(cap) + '</div>' +
            '<div class="pk-cell-v' + (extraClass ? ' ' + extraClass : '') + '">' +
            value + '</div></div>';
    }

    function band(title, hint) {
        return '<div class="pk-sub-band"><span class="pk-sub-t">' + esc(title) + '</span>' +
            '<span class="pk-sub-line"></span>' +
            (hint ? '<span class="pk-sub-s">' + esc(hint) + '</span>' : '') + '</div>';
    }

    function openDrawer(html) {
        el.drawer.innerHTML = html;
        el.drawer.hidden = false;
        el.backdrop.hidden = false;
        el.drawer.scrollTop = 0;
    }
    function closeDrawer() {
        el.drawer.hidden = true;
        el.backdrop.hidden = true;
        el.drawer.innerHTML = '';
    }

    function drawerHead(title, subtitle) {
        return '<div class="pk-dr-head">' +
            '<div style="flex:1;min-width:0">' +
            '<div class="pk-dr-t">' + esc(title) + '</div>' +
            '<div class="pk-dr-s">' + esc(subtitle) + '</div></div>' +
            '<button type="button" class="pk-close" data-close aria-label="Закрыть">' +
            '<svg width="12" height="12" viewBox="0 0 12 12"><path d="M2.5 2.5 9.5 9.5 ' +
            'M9.5 2.5 2.5 9.5" stroke-width="1.6" stroke-linecap="round" fill="none"/></svg>' +
            '</button></div>';
    }

    function scopeLine() {
        var period = (state.data && state.data.period) || {};
        return 'разрез: ' + (state.data ? state.data.bar_label : '') + ' · ' +
            rangeLabel(period.from, period.to);
    }

    function positionById(id) {
        var rows = (state.data && state.data.positions) || [];
        for (var i = 0; i < rows.length; i++) {
            if (String(rows[i].Id) === String(id)) return rows[i];
        }
        return null;
    }

    // Мини-таблица позиций: в карточке категории и в списке корзины.
    function miniPositions(rows, title, hint) {
        if (!rows.length) return '';
        var maxShare = rows.reduce(function (acc, p) {
            return Math.max(acc, p.RevenueSharePercent || 0);
        }, 0);
        var html = band(title, hint);
        html += '<div class="pk-mini-row is-head">' +
            '<span class="pk-th">ФАСОВКА</span>' +
            '<span class="pk-th r">ШТУК</span>' +
            '<span class="pk-th r">ВЫРУЧКА</span>' +
            '<span class="pk-th c">ABC</span>' +
            '<span class="pk-th r">ДОЛЯ</span></div>';
        rows.forEach(function (p) {
            var width = maxShare > 0 ? Math.max(4, p.RevenueSharePercent / maxShare * 100) : 0;
            html += '<div class="pk-mini-row" data-pos="' + p.Id + '">' +
                '<span class="pk-name">' + esc(p.Beer) + '</span>' +
                '<span class="pk-num">' + num(p.TotalQty, 0) + '</span>' +
                '<span class="pk-num strong">' + money(p.TotalRevenue) + '</span>' +
                '<span class="pk-cell-c"><span class="pk-abc ' + abcClass(p.ABC_Revenue) +
                    '">' + esc(p.ABC_Combined) + '</span></span>' +
                '<span class="pk-share"><span class="pk-bar pk-mini-bar">' +
                '<i style="width:' + width.toFixed(1) + '%"></i></span>' +
                '<span class="pk-share-v">' + pct(p.RevenueSharePercent, 1) +
                '</span></span></div>';
        });
        return html;
    }

    // База, от которой посчитаны доли категорий. Сервер отдаёт её с 2026-09-26;
    // на старом ответе — та же сумма положительных выручек категорий здесь.
    function categoryBase() {
        var t = (state.data && state.data.totals) || {};
        if (typeof t.category_revenue_abc_base === 'number') return t.category_revenue_abc_base;
        return ((state.data && state.data.categories) || []).reduce(function (a, c) {
            return a + Math.max(c.TotalRevenue || 0, 0);
        }, 0);
    }

    function openCategory(name) {
        var data = state.data;
        if (!data) return;
        var cat = null;
        (data.categories || []).forEach(function (c) { if (c.Category === name) cat = c; });
        if (!cat) return;

        var members = (data.positions || []).filter(function (p) { return p.Category === name; });

        var html = '<div class="pk-dr-in">';
        html += drawerHead(cat.Category, scopeLine());

        html += band('ИТОГИ КАТЕГОРИИ');
        html += '<div class="pk-cells">' +
            cell('ВЫРУЧКА', money(cat.TotalRevenue)) +
            cell('ДОЛЯ В ВЫРУЧКЕ', pct(cat.RevenueSharePercent, 1)) +
            cell('НАКОПЛЕННЫМ ИТОГОМ', pct(cat.CumulativePercent, 1)) +
            cell('ПРОДАНО', num(cat.TotalQty, 0) + ' шт') +
            cell('МАРЖА', money(cat.TotalMargin)) +
            cell('НАЦЕНКА', markupPct(cat.MarkupPercent, 1),
                cat.MarkupPercent === null ? 'dash' : '') +
            '</div>';

        html += band('ABC КАТЕГОРИИ', 'место среди категорий разреза');
        html += '<div class="pk-abc-box"><div class="pk-abc-top">' +
            '<span class="pk-abc-big ' + abcClass(cat.ABC_Category) + '">' +
            esc(cat.ABC_Category) + '</span>' +
            '<span class="pk-abc-meta">' + pct(cat.RevenueSharePercent, 1) +
            ' от выручки разреза, накопленным итогом ' + pct(cat.CumulativePercent, 1) +
            '</span></div>' +
            '<div class="pk-abc-lines">' +
            abcLine('Выручка', cat.ABC_Category, revenueText(cat.ABC_Category),
                money(cat.TotalRevenue) + ' / ' +
                // База долей категорий — сумма положительных выручек КАТЕГОРИЙ, а
                // не позиций: при возврате внутри категории они разные, и деление
                // на базу позиций не давало напечатанный процент.
                money(categoryBase()) + ' = ' +
                pct(cat.RevenueSharePercent, 1) + ' · накоплено ' +
                pct(cat.CumulativePercent, 1)) +
            abcLine('Наценка', cat.ABC_Markup, markupText(cat.ABC_Markup),
                cat.MarkupPercent === null ? 'себестоимость нулевая — наценка не определена'
                    : '(' + money(cat.TotalRevenue) + ' − ' + money(cat.TotalRevenue - cat.TotalMargin) +
                      ') / ' + money(cat.TotalRevenue - cat.TotalMargin) + ' = ' +
                      markupPct(cat.MarkupPercent, 1)) +
            '</div></div>';

        html += miniPositions(members, 'ВСЕ ПОЗИЦИИ КАТЕГОРИИ',
            members.length + ' ' + plural(members.length, 'позиция', 'позиции', 'позиций') +
            ' · клик — карточка');

        html += '</div>';
        openDrawer(html);
    }

    function openBucket(key) {
        var data = state.data;
        if (!data) return;
        var info = bucketCard(key);
        if (!info) return;

        var members = (data.positions || []).filter(function (p) { return p.ABC_Bucket === key; });
        var margin = members.reduce(function (a, p) { return a + p.TotalMargin; }, 0);

        var html = '<div class="pk-dr-in">';
        html += drawerHead(info.name + ' — ' + info.action, scopeLine());

        html += band('ЧТО В ГРУППЕ');
        html += '<div class="pk-cells three">' +
            cell('ПОЗИЦИЙ', info.count) +
            cell('ВЫРУЧКА', money(info.revenue)) +
            cell('ДОЛЯ В ВЫРУЧКЕ', pct(info.revenue_share_percent, 1)) +
            '</div>';
        // Правило с числами и подсказка — с сервера (CLAUDE.md пункт 1).
        html += '<div class="pk-dr-note">' + esc(info.hint) + '</div>';
        html += '<div class="pk-formula">правило: ' + esc(info.rule) + '</div>';

        if (members.length) {
            html += miniPositions(members, 'ПОЗИЦИИ', 'маржа группы ' + money(margin));
        } else {
            html += '<div class="pk-empty">в этой группе сейчас нет позиций' +
                (info.verdict_ready === false
                    ? '; решение о выводе выносится по периоду от четырёх недель' : '') + '</div>';
        }

        html += '</div>';
        openDrawer(html);
    }

    function revenueText(letter) {
        if (letter === 'A') return 'входит в первые 80% накопленной выручки';
        if (letter === 'B') return 'следующие 15% выручки';
        if (letter === 'C') return 'последние 5% выручки';
        return 'не определено';
    }
    function markupText(letter) {
        if (letter === 'A') return 'наценка 120% и выше';
        if (letter === 'B') return 'наценка от 100% до 120%';
        if (letter === 'C') return 'наценка ниже 100%';
        return 'наценка не определена';
    }
    function marginText(letter) {
        if (letter === 'A') return 'входит в первые 80% накопленной маржи';
        if (letter === 'B') return 'следующие 15% маржи';
        if (letter === 'C') return 'последние 5% маржи';
        return 'не определено';
    }

    function abcLine(category, letter, text, formula) {
        return '<div class="pk-abc-line">' +
            '<span class="pk-abc-ltr ' + (letter ? abcClass(letter) : 'none') + '">' +
            esc(letter || '—') + '</span>' +
            '<span class="pk-abc-cat">' + esc(category) + '</span>' +
            '<span class="pk-abc-txt">' + esc(text || '') +
            (formula ? '<span class="pk-formula">' + esc(formula) + '</span>' : '') +
            '</span></div>';
    }

    // Недельный ряд продаж — то самое, из чего получилась буква XYZ.
    function weeksChart(series) {
        if (!series || !series.length) return '';
        var max = series.reduce(function (a, v) { return Math.max(a, v); }, 0);
        var html = '<div class="pk-weeks">';
        series.forEach(function (value, index) {
            var height = max > 0 ? Math.max(2, value / max * 54) : 2;
            html += '<div class="pk-week">' +
                '<span class="pk-week-v">' + (value ? num(value, 0) : '') + '</span>' +
                '<span class="pk-week-bar' + (value ? '' : ' zero') +
                '" style="height:' + height.toFixed(0) + 'px"></span>' +
                '<span class="pk-week-cap">н' + (index + 1) + '</span></div>';
        });
        return html + '</div>';
    }

    function xyzNote(p, data) {
        var tail = ' Считается по неделям с продажами: выборочное стандартное ' +
            'отклонение недельных штук делится на среднее.';
        if (p.XYZ_Category === 'X') {
            return 'Недельный объём предсказуем: разброс до 30%.' + tail;
        }
        if (p.XYZ_Category === 'Y') {
            return 'Умеренный разброс: от 30% до 60% недельного объёма.' + tail;
        }
        if (p.XYZ_Category === 'Z') {
            return 'Разброс свыше 60%: недельный объём может отличаться больше чем ' +
                'в полтора раза.' + tail;
        }
        if (p.XYZ_Reason === 'period') {
            return 'Категория не присвоена: в периоде ' + p.WeeksInPeriod +
                ' ' + plural(p.WeeksInPeriod, 'полная неделя', 'полные недели',
                    'полных недель') + ', нужно минимум ' + data.min_xyz_weeks + '.' + tail;
        }
        return 'Категория не присвоена: позиция продавалась ' + p.WeeksWithSales +
            ' ' + plural(p.WeeksWithSales, 'неделю', 'недели', 'недель') + ' из ' +
            p.WeeksInPeriod + ', для оценки стабильности нужно минимум ' +
            data.min_xyz_weeks + '. Прочерк честнее буквы: разовая продажа ' +
            'не описывает спрос.' + tail;
    }

    function openPosition(id) {
        var data = state.data;
        var p = positionById(id);
        if (!p || !data) return;
        var period = data.period || {};

        var html = '<div class="pk-dr-in">';
        html += drawerHead(p.Beer, p.Category + ' · ' + p.Country + ' · ' + scopeLine());

        html += band('ПРОДАЖИ');
        html += '<div class="pk-cells">' +
            cell('ПРОДАНО', num(p.TotalQty, 0) + ' шт') +
            cell('ДОЛЯ В ВЫРУЧКЕ', pct(p.RevenueSharePercent, 1)) +
            cell('НАКОПЛЕННЫМ ИТОГОМ', pct(p.RevenueCumulativePercent, 1)) +
            cell('НЕДЕЛЬ С ПРОДАЖАМИ', p.WeeksWithSales + ' из ' + p.WeeksInPeriod) +
            '</div>';
        if (p.QtyOutsideWeeks > 0) {
            // Иначе «0 недель с продажами» стоит прямо под собственной выручкой
            // позиции и выглядит поломкой страницы.
            html += '<div class="pk-dr-note">' + num(p.QtyOutsideWeeks, 0) +
                ' ' + plural(p.QtyOutsideWeeks, 'штука продана', 'штуки проданы',
                    'штук продано') +
                ' вне недельного окна ' + rangeLabel(period.weeks_from, period.weeks_to) +
                ': период не делится на целые недели, и остаток в XYZ не входит. ' +
                'В выручке и количестве выше эти продажи учтены полностью.</div>';
        }

        html += band('ДЕНЬГИ');
        html += '<div class="pk-cells three">' +
            cell('ВЫРУЧКА', money(p.TotalRevenue)) +
            cell('МАРЖА', money(p.TotalMargin)) +
            cell('НАЦЕНКА', markupPct(p.MarkupPercent, 1),
                p.MarkupPercent === null ? 'dash' : '') +
            cell('ЦЕНА ЗА ШТУКУ', money(p.PricePerUnit)) +
            cell('СЕБЕС. ЗА ШТУКУ', money(p.CostPerUnit)) +
            cell('СЕБЕСТОИМОСТЬ', money(p.TotalCost)) +
            '</div>';

        // Разрез по барам показываем только в «Общей»: в карточке одного бара
        // это была бы строка с тем же числом, что в шапке.
        if (data.scope === 'total' && (p.ByBar || []).length) {
            html += band('ПО БАРАМ', p.BarsPresent + ' из ' +
                (data.bars_in_scope || []).length);
            var maxBar = p.ByBar.reduce(function (a, b) {
                return Math.max(a, b.SharePercent || 0);
            }, 0);
            html += '<div class="pk-mini-row money is-head">' +
                '<span class="pk-th">БАР</span>' +
                '<span class="pk-th r">ШТУК</span>' +
                '<span class="pk-th r">ВЫРУЧКА</span>' +
                '<span class="pk-th r">МАРЖА</span>' +
                '<span class="pk-th r">ДОЛЯ</span></div>';
            p.ByBar.forEach(function (b) {
                var width = maxBar > 0 ? Math.max(4, b.SharePercent / maxBar * 100) : 0;
                html += '<div class="pk-mini-row money" style="cursor:default">' +
                    '<span class="pk-name">' + esc(b.Bar) + '</span>' +
                    '<span class="pk-num">' + num(b.Qty, 0) + '</span>' +
                    '<span class="pk-num strong">' + money(b.Revenue) + '</span>' +
                    '<span class="pk-num">' + money(b.Margin) + '</span>' +
                    '<span class="pk-share"><span class="pk-bar pk-mini-bar">' +
                    '<i style="width:' + width.toFixed(1) + '%"></i></span>' +
                    '<span class="pk-share-v">' + pct(b.SharePercent, 1) +
                    '</span></span></div>';
            });
        }

        // Проценты приходят с сервера (WriteoffPercentOfSold, InventoryPercentOfSold);
        // излишек — не потеря: своя подпись, знак плюс и спокойная плашка, как в
        // строке баланса, иначе «+3» рядом с «−25,0%» читалось бы двумя способами.
        // Недостача и излишек — по барам (сервер): ячейка показывает недостачу, а
        // если её нет — излишек; при обоих излишек назван в пояснении ниже.
        var shortQty = p.InventoryShortQty || 0;
        var surplusQty = p.InventorySurplusQty || 0;
        var surplus = shortQty <= 0 && surplusQty > 0;
        var invPct = surplus ? p.InventorySurplusPercentOfSold : p.InventoryShortPercentOfSold;
        var hasPct = invPct !== null && invPct !== undefined;
        html += band('ПОТЕРИ', 'к проданному по складу');
        html += '<div class="pk-cells three">' +
            cell('ПРОДАНО ПО СКЛАДУ', qty(p.SoldQtyStock) + ' шт') +
            '<div class="pk-cell"><div class="pk-cell-cap">СПИСАНО АКТАМИ</div>' +
            '<div class="pk-cell-row"><span class="pk-cell-v">' + qty(p.WriteoffQty) +
            '</span><span class="pk-pill ' + lossTone(p.WriteoffPercentOfSold) + '">' +
            (p.WriteoffPercentOfSold === null || p.WriteoffPercentOfSold === undefined
                ? '—' : pct(p.WriteoffPercentOfSold, 1)) + '</span></div></div>' +
            '<div class="pk-cell"><div class="pk-cell-cap">' +
            (surplus ? 'ИЗЛИШЕК ИНВЕНТ.' : 'НЕДОСТАЧА ИНВЕНТ.') + '</div>' +
            '<div class="pk-cell-row"><span class="pk-cell-v">' +
            (surplus ? signed(surplusQty, '+') : qty(shortQty)) +
            '</span><span class="pk-pill ' + (surplus ? 'ok' : lossTone(invPct)) + '">' +
            (!hasPct ? '—' : (surplus ? '+' : '') + pct(invPct, 1)) +
            '</span></div></div>' +
            '</div>';
        var lossNote;
        if (p.StockUnit && p.StockUnit !== 'шт') {
            lossNote = 'На складе товар учитывается в единице «' + esc(p.StockUnit) +
                '»: в баланс штук не входит, потери по нему не считаются.';
        } else if (p.SoldQtyStock > 0) {
            lossNote = 'Потери ' + qty(p.LossQty) + ' шт = акты ' + qty(p.WriteoffQty) +
                ' + недостача ' + qty(shortQty) + ' · ' +
                qty(p.LossQty) + ' / ' + qty(p.SoldQtyStock) + ' = ' +
                pct(p.LossPercentOfSold, 1) + ' от проданного по складу. ' +
                'По кассе продано ' + qty(p.TotalQty) + ' шт' +
                (Math.abs(p.TotalQty - p.SoldQtyStock) > 0.005
                    ? ' — расходится со складом на ' +
                      signed(p.SoldQtyStock - p.TotalQty, p.SoldQtyStock < p.TotalQty ? '−' : '+') +
                      ' (граница учётного дня, набор или товар без карточки склада).'
                    : '.') +
                (shortQty > 0 && surplusQty > 0
                    ? ' Ещё излишек ' + qty(surplusQty) + ' шт в других барах: недостачу он ' +
                      'не гасит — инвентаризация каждого бара отдельный пересчёт.'
                    : '');
        } else if (p.WriteoffQty > 0 || shortQty > 0 || surplusQty > 0) {
            lossNote = 'По складу за период не продано, но движения есть: акты ' + qty(p.WriteoffQty) +
                (surplus ? ', излишек ' + qty(surplusQty) : ' + недостача ' + qty(shortQty)) +
                ' — потери ' + qty(p.LossQty) + ' шт, процент к проданному не определён.';
        } else {
            lossNote = 'Движений по складу за период у позиции нет: проводки не пришли ' +
                'или товар не сопоставлен с продажами.';
        }
        html += '<div class="pk-dr-note">' + lossNote + '</div>';

        var totals = data.totals || {};
        html += band('ABC-АНАЛИЗ', 'три буквы: выручка, наценка, спрос');
        html += '<div class="pk-abc-box"><div class="pk-abc-top">' +
            '<span class="pk-abc-big ' + abcClass(p.ABC_Revenue) + '">' +
            esc(p.ABC_Combined) + '</span>' +
            '<span class="pk-abc-meta">' + esc(bucketNameOf(p.ABC_Bucket)) + '</span></div>' +
            '<div class="pk-abc-lines">' +
            abcLine('Выручка', p.ABC_Revenue, revenueText(p.ABC_Revenue),
                money(p.TotalRevenue) + ' / ' + money(totals.revenue_abc_base) + ' = ' +
                pct(p.RevenueSharePercent, 1) + ' · накоплено ' +
                pct(p.RevenueCumulativePercent, 1) + ' · база: весь ассортимент разреза, ' +
                totals.sku + ' поз.') +
            abcLine('Наценка', p.ABC_Markup, markupText(p.ABC_Markup),
                p.MarkupPercent === null
                    ? 'себестоимость нулевая — наценка не определена, буквы нет'
                    : '(' + money(p.TotalRevenue) + ' − ' + money(p.TotalCost) + ') / ' +
                      money(p.TotalCost) + ' = ' + markupPct(p.MarkupPercent, 1)) +
            abcLine('Спрос', p.XYZ_Category,
                p.XYZ_Category ? xyzShort(p.XYZ_Category) : 'данных не хватило',
                p.CoefficientOfVariation === null
                    ? 'недель с продажами ' + p.WeeksWithSales + ', нужно ' +
                      data.min_xyz_weeks
                    : 'коэффициент вариации ' + pct(p.CoefficientOfVariation, 1) +
                      ' по ' + p.WeeksWithSales + ' нед.') +
            '</div></div>';

        html += band('ВТОРАЯ ШКАЛА', 'место внутри своей категории');
        html += '<div class="pk-abc-box"><div class="pk-abc-lines" style="margin-top:0">' +
            abcLine('В категории', p.ABC_Revenue_InCategory,
                revenueText(p.ABC_Revenue_InCategory),
                money(p.TotalRevenue) + ' / ' + money(p.RevenueBaseInCategory) +
                ' (категория «' + p.Category + '») = ' +
                pct(p.RevenueShareInCategoryPercent, 1) + ' · накоплено ' +
                pct(p.RevenueCumulativeInCategoryPercent, 1)) +
            abcLine('Маржа', p.ABC_Margin, marginText(p.ABC_Margin),
                money(p.TotalMargin) + ' / ' + money(totals.margin_abc_base) + ' = ' +
                pct(p.MarginSharePercent, 1)) +
            '</div></div>';
        html += '<div class="pk-dr-note">Буква по выручке считается дважды и от разных ' +
            'баз: по всему ассортименту разреза и внутри своей категории. Обе верные, ' +
            'но означают разное — поэтому показаны обе, а не одна без пояснения. ' +
            'В знаменателе долей стоит сумма только ПОЛОЖИТЕЛЬНЫХ значений: возврат не ' +
            'увеличивает целое, долей которого он считается, поэтому база маржи может ' +
            'отличаться от итоговой маржи разреза.</div>';

        html += band('XYZ — СТАБИЛЬНОСТЬ СПРОСА');
        html += '<div class="pk-cells three">' +
            cell('КАТЕГОРИЯ', p.XYZ_Category || '—', p.XYZ_Category ? '' : 'dash') +
            cell('КОЭФФ. ВАРИАЦИИ',
                p.CoefficientOfVariation === null ? '—' : pct(p.CoefficientOfVariation, 1),
                p.CoefficientOfVariation === null ? 'dash' : '') +
            cell('НЕДЕЛЬ С ПРОДАЖАМИ', p.WeeksWithSales) +
            '</div>';
        if ((p.WeeklyQty || []).length) {
            html += weeksChart(p.WeeklyQty);
        }
        html += '<div class="pk-dr-note">' + esc(xyzNote(p, data)) + '</div>';

        html += '</div>';
        openDrawer(html);
    }

    function xyzShort(letter) {
        if (letter === 'X') return 'стабильный спрос, разброс до 30%';
        if (letter === 'Y') return 'умеренный разброс, 30–60%';
        return 'спрос скачет, разброс свыше 60%';
    }

    function bucketNameOf(key) {
        var card = bucketCard(key);
        return card ? card.name + ' · ' + card.action : 'группа не определена';
    }

    // ==================== события ====================

    function onTableClick(event) {
        var head = event.target.closest('.pk-th.s');
        if (head) {
            var isCats = !!head.closest('.pk-cats');
            var sort = isCats ? state.catSort : state.posSort;
            var key = head.dataset.sort;
            if (sort.key === key) { sort.dir = -sort.dir; } else { sort.key = key; sort.dir = -1; }
            if (isCats) { renderCategories(); } else { renderPositions(); }
            return;
        }
        var row = event.target.closest('[data-cat],[data-pos]');
        if (!row) return;
        if (row.dataset.cat !== undefined && row.dataset.cat !== null && row.dataset.cat !== '') {
            openCategory(row.dataset.cat);
        } else if (row.dataset.pos !== undefined) {
            openPosition(row.dataset.pos);
        }
    }

    function bind() {
        el.burger.addEventListener('click', function () {
            // Тот же сайдбар, что на остальных страницах: пробрасываем клик на
            // скрытую кнопку из shared/nav.html, чтобы не дублировать обработчик.
            var toggle = document.getElementById('sidebar-toggle');
            if (toggle) toggle.click();
        });

        el.barBtn.addEventListener('click', function () {
            if (!el.barMenu.hidden) { closeMenus(); return; }
            buildBarMenu(state.bars);
            openMenu(el.barMenu);
        });
        el.perBtn.addEventListener('click', function () {
            if (!el.perMenu.hidden) { closeMenus(); return; }
            buildPerMenu();
            openMenu(el.perMenu);
        });
        el.catch_.addEventListener('click', closeMenus);

        el.barMenu.addEventListener('click', function (event) {
            var item = event.target.closest('[data-bar]');
            if (!item) return;
            state.bar = item.dataset.bar;
            syncPickers();
            closeMenus();
            run();
        });
        el.perMenu.addEventListener('click', function (event) {
            var item = event.target.closest('[data-preset]');
            if (item) {
                applyPreset(item.dataset.preset);
                closeMenus();
                run();
                return;
            }
            if (event.target.id === 'pkCustom') {
                var from = document.getElementById('pkFrom').value;
                var to = document.getElementById('pkTo').value;
                if (!from || !to) return;
                if (from > to) { var swap = from; from = to; to = swap; }
                state.preset = 'custom';
                state.from = from;
                state.to = to;
                syncPickers();
                closeMenus();
                run();
            }
        });

        el.run.addEventListener('click', run);
        el.search.addEventListener('input', function () {
            state.query = el.search.value;
            if (state.data) renderPositions();
        });

        el.buckets.addEventListener('click', function (event) {
            var card = event.target.closest('[data-bucket]');
            if (card) openBucket(card.dataset.bucket);
        });
        el.cats.addEventListener('click', onTableClick);
        el.pos.addEventListener('click', onTableClick);
        el.losses.addEventListener('click', function (event) {
            var row = event.target.closest('[data-pos]');
            if (row) openPosition(row.dataset.pos);
        });
        el.drawer.addEventListener('click', function (event) {
            if (event.target.closest('[data-close]')) { closeDrawer(); return; }
            var row = event.target.closest('[data-pos]');
            if (row) openPosition(row.dataset.pos);
        });
        el.backdrop.addEventListener('click', closeDrawer);
        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') return;
            if (!el.drawer.hidden) { closeDrawer(); return; }
            closeMenus();
        });
    }

    function init() {
        el = {
            burger: document.getElementById('pkBurger'),
            barBtn: document.getElementById('pkBarBtn'),
            barMenu: document.getElementById('pkBarMenu'),
            barLabel: document.getElementById('pkBarLabel'),
            perBtn: document.getElementById('pkPerBtn'),
            perMenu: document.getElementById('pkPerMenu'),
            perLabel: document.getElementById('pkPerLabel'),
            perHint: document.getElementById('pkPerHint'),
            catch_: document.getElementById('pkCatch'),
            run: document.getElementById('pkRun'),
            runLabel: document.getElementById('pkRunLabel'),
            spin: document.getElementById('pkSpin'),
            context: document.getElementById('pkContext'),
            xyzChip: document.getElementById('pkXyzChip'),
            msg: document.getElementById('pkMsg'),
            body: document.getElementById('pkBody'),
            sum: document.getElementById('pkSum'),
            buckets: document.getElementById('pkBuckets'),
            catCount: document.getElementById('pkCatCount'),
            cats: document.getElementById('pkCats'),
            posCount: document.getElementById('pkPosCount'),
            search: document.getElementById('pkSearch'),
            pos: document.getElementById('pkPos'),
            updated: document.getElementById('pkUpdated'),
            balance: document.getElementById('pkBalance'),
            losses: document.getElementById('pkLosses'),
            diag: document.getElementById('pkDiag'),
            drawer: document.getElementById('pkDrawer'),
            backdrop: document.getElementById('pkBackdrop')
        };

        var barsNode = document.getElementById('pkBars');
        try {
            state.bars = JSON.parse(barsNode ? barsNode.textContent : '[]') || [];
        } catch (e) {
            state.bars = [];
        }

        applyPreset(state.preset);
        bind();
        run();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Для тестов отрисовки (tests/test_packaging_render.mjs): чистые функции и
    // рендер должны быть вызываемы вне браузера.
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { num: num, fixed: fixed, money: money, pct: pct, esc: esc,
                           plural: plural, presetRange: presetRange, weeksIn: weeksIn,
                           abcClass: abcClass, xyzNote: xyzNote,
                           lossTone: lossTone, signed: signed, qty: qty,
                           markupPct: markupPct };
    }
    if (typeof window !== 'undefined') {
        window.__packaging = { state: state, render: render, openPosition: openPosition,
                               openCategory: openCategory, openBucket: openBucket,
                               num: num, money: money, pct: pct, esc: esc, plural: plural,
                               abcClass: abcClass, weeksIn: weeksIn, lossTone: lossTone,
                               signed: signed, qty: qty, openBucket: openBucket,
                               markupPct: markupPct, presetRange: presetRange };
    }
})();

/* Страница «Кухня — ABC/XYZ и потери» (/kitchen).

   Клон «Фасовки» (static/js/packaging/packaging.js) про еду — решение владельца
   2026-09-27: «полное клонирование интерфейса, только про еду». Всё содержимое
   приходит ОДНИМ ответом /api/kitchen — сводка, группы решений, все категории,
   все позиции, баланс склада. Разметка и стили общие с фасовкой (классы pk-*,
   static/packaging/packaging.css), id узлов свои (kt*).

   Чем отличается от фасовки:
   - пороги наценки 180/150 (core/abc_thresholds.py, KITCHEN_MARKUP_*);
   - единица продаж — порции; соусы-модификаторы в позиции не входят и названы
     в диагностике;
   - баланс и расхождения — в рублях по закупке: на складе кухни лежат и товары
     «как есть», и ингредиенты блюд в разных единицах (core/kitchen_losses.py).

   Числа на клиенте не пересчитываются нигде, кроме форматирования, ширины шкал
   и итогов отфильтрованного среза: доли, наценки, буквы и рубли приходят
   посчитанными сервером (core/kitchen_analysis.py).
*/
(function () {
    'use strict';

    // ==================== состояние ====================

    var state = {
        bar: '',                 // '' = все бары («Общая»)
        preset: 'd30',
        from: null,
        to: null,
        data: null,              // ответ /api/kitchen
        model: null,             // модель общей раскладки (AbcView.fromKitchen)
        query: '',
        catSort: { key: 'TotalRevenue', dir: -1 },
        posSort: { key: 'TotalRevenue', dir: -1 },
        loading: false,
        bars: [],
        // Строк таблицы позиций на экране — как у фасовки: длинная лента не нужна.
        limit: 30
    };

    var el = {};
    // Строк таблицы за одно «Показать ещё».
    var ROWS_STEP = 30;
    // Общая раскладка страницы (static/js/shared/abc_view.js): вкладки, «Обзор»,
    // «Цены», бары. null — модуль не подключён (страница работает и без него).
    var view = null;

    // Пояснение расчёта — свёрнуто под стрелкой «Как считается» (CLAUDE.md, п. 1).
    function howNote(inner, cls) {
        return '<details class="av-how"><summary>Как считается</summary><div class="av-how-in">' +
            '<div class="' + (cls || 'pk-dr-note') + '">' + inner + '</div></div></details>';
    }

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
    // точного числа, и 179,5% не должно печататься как «180%» рядом с буквой B и
    // группой «Низкая наценка» (пороги 180/150 целые, поэтому округление вниз
    // никогда не переводит число через порог). Эпсилон 1e-9 процента — тот же
    // допуск, с которым сервер сравнивает наценку с порогом (snap_markup в
    // core/abc_thresholds.py): цена ровно на пороге печатается порогом и
    // получает старшую букву, а не «180%» рядом с B.
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
            '<input type="date" id="ktFrom" value="' + esc(state.from || '') + '">' +
            '<input type="date" id="ktTo" value="' + esc(state.to || '') + '">' +
            '<button type="button" class="pk-run sm" id="ktCustom">ОК</button></div></div>';
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
        showMessage('Забираем из iiko продажи кухни за период…');

        fetch('/api/kitchen', {
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
            state.limit = ROWS_STEP;
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

        state.model = window.AbcView ? window.AbcView.fromKitchen(data) : null;
        if (view && state.model) view.render(state.model);
        renderCategories();
        renderPositions();
        renderBalance(data);
        renderLosses(data);
        renderDiagnostics(data);
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
            '<span class="pk-th r s" data-sort="TotalQty">ПОРЦИЙ' +
                sortMark(state.catSort, 'TotalQty') + '</span>' +
            '<span class="pk-th r s" data-sort="TotalRevenue">ВЫРУЧКА' +
                sortMark(state.catSort, 'TotalRevenue') + '</span>' +
            // Только доля: накопленный процент в ячейку не влезает, и
            // заголовок, обещающий два числа при одном показанном, врёт.
            // Накопленный итог есть в карточке категории.
            '<span class="pk-th r s" data-sort="RevenueSharePercent">ДОЛЯ В ВЫРУЧКЕ' +
                sortMark(state.catSort, 'RevenueSharePercent') + '</span>' +
            '<span class="pk-th r s" data-sort="QtySharePercent">ДОЛЯ В ПОРЦИЯХ' +
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
            html += '<div class="pk-empty">за период продаж кухни не было</div>';
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
        // Группа решения: клик по группе на «Обзоре» или фильтр над таблицей.
        var bucket = view ? view.filter() : null;
        if (bucket) {
            rows = rows.filter(function (p) { return p.ABC_Bucket === bucket; });
        }
        rows = sortRows(rows, state.posSort);
        var maxShare = rows.reduce(function (acc, p) {
            return Math.max(acc, p.RevenueSharePercent || 0);
        }, 0);
        var maxQtyShare = rows.reduce(function (acc, p) {
            return Math.max(acc, p.QtySharePercent || 0);
        }, 0);

        var total = (data.positions || []).length;
        el.posCount.textContent = (query || bucket)
            ? rows.length + ' из ' + total
            : total + ' ' + plural(total, 'позиция', 'позиции', 'позиций');

        var html = '<div class="pk-row is-head">' +
            '<span class="pk-th">#</span>' +
            '<span class="pk-th">ПОЗИЦИЯ</span>' +
            '<span class="pk-th">КАТЕГОРИЯ</span>' +
            '<span class="pk-th r s" data-sort="TotalQty">ПОРЦИЙ' +
                sortMark(state.posSort, 'TotalQty') + '</span>' +
            '<span class="pk-th r s" data-sort="TotalRevenue">ВЫРУЧКА' +
                sortMark(state.posSort, 'TotalRevenue') + '</span>' +
            '<span class="pk-th r s" data-sort="RevenueSharePercent">ДОЛЯ В ВЫРУЧКЕ' +
                sortMark(state.posSort, 'RevenueSharePercent') + '</span>' +
            '<span class="pk-th r s" data-sort="QtySharePercent">ДОЛЯ В ПОРЦИЯХ' +
                sortMark(state.posSort, 'QtySharePercent') + '</span>' +
            '<span class="pk-th r s" data-sort="MarkupPercent">НАЦЕНКА' +
                sortMark(state.posSort, 'MarkupPercent') + '</span>' +
            // Колонки XYZ нет (с 2026-09-26): она повторяла третью букву кода.
            '<span class="pk-th c">ABC</span>' +
            '</div>';

        rows.slice(0, state.limit).forEach(function (p, index) {
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
                ? 'ничего не найдено — уточните запрос' + (bucket ? ' или снимите фильтр группы' : '')
                : 'продаж кухни за период нет — ниже только движения склада') + '</div>';
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
            // Итог — по всем строкам выборки, показаны первые state.limit.
            if (rows.length > state.limit) {
                html += '<button type="button" class="av-rows-more" data-more-rows>Показать ещё ' +
                    Math.min(ROWS_STEP, rows.length - state.limit) + ' · всего ' + rows.length + '</button>';
            }
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
    // Баланс кухни — рубли по закупке, целыми: копейки на сотнях тысяч только
    // мешают читать. Название осталось от фасовки, чтобы код двух страниц совпадал.
    function qty(value) {
        return num(Math.round(value), 0);
    }
    // Количество продукта в его единице («3,2 кг») — для подписи строки.
    function units(value, unit) {
        return num(value, 2) + (unit ? ' ' + unit : '');
    }

    // Цвет плашки «% от списанного»: до 10% спокойный, до 30% янтарный, выше
    // красный. Пороги те же, что у фасовки и розлива; для кухни своего факта
    // ещё нет — пересмотреть после первого живого периода.
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
            '<span class="pk-bal-v ' + (Math.abs(value) < 0.5 ? 'zero' : (tone || '')) + '">' +
                signed(value, sign) + '</span>' +
            '<span>' + (pill || '') + '</span></div>';
    }

    function renderBalance(data) {
        var losses = data.losses || {};
        var scale = Math.max(losses.sold || 0, losses.invoice_in || 0, 1);
        var html = '<div class="pk-card-h"><span class="pk-card-t">Баланс кухни за период</span>' +
            '<span class="pk-card-s">склад iiko · ₽ по закупке</span></div>';

        if (!losses.diagnostics || !losses.diagnostics.has_transactions) {
            html += '<div class="pk-empty" style="border-top:none">' +
                'проводки склада за период не пришли — баланса нет</div>';
            el.balance.innerHTML = html;
            return;
        }

        html += balanceRow('Приход по накладным', losses.invoice_in, '+', scale, 'ok');
        html += balanceRow('Перемещения · приход', losses.transfer_in, '+', scale, '');
        html += balanceRow('Перемещения · расход', losses.transfer_out, '−', scale, '');
        html += balanceRow('Списано при продаже', losses.sold, '−', scale, '');
        html += balanceRow('Списано актами', losses.writeoff, '−', scale, 'warn',
            losses.sold > 0 ? '<span class="pk-pill warn">' +
                pct(losses.writeoff_percent_of_sold, 1) + ' от продаж</span>' : '');
        // Нетто-излишек — не потеря: подпись, знак и цвет другие.
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
            '<span class="pk-bal-total-n">Изменение остатка кухни</span>' +
            '<span class="pk-bal-lead"></span>' +
            '<span class="pk-bal-total-v">' +
            signed(losses.balance, losses.balance < 0 ? '−' : '+') + ' ₽</span></div>' +
            // Формула словами и числами — CLAUDE.md пункт 1. Итоги (received,
            // spent) приходят с сервера, здесь ничего не складывается.
            howNote('приход ' + qty(losses.received) +
            ' − расход ' + qty(losses.spent) +
            ' (продано ' + qty(losses.sold) + ' + акты ' + qty(losses.writeoff) +
            (losses.inventory_net < 0
                ? ' − излишек ' + qty(-losses.inventory_net)
                : ' + недостача ' + qty(losses.inventory_net)) +
            ' + перемещения ' + qty(losses.transfer_out) +
            ') ₽ по закупке. Продано — себестоимость списанного при продаже по складу: ' +
            'у блюд это ингредиенты по техкартам, у товаров «как есть» — сам товар. ' +
            'Всё в рублях: на складе кухни продукты в кг, штуках и литрах, и сложить их ' +
            'можно только в деньгах.', 'pk-note');
        el.balance.innerHTML = html;
    }

    // Недостача строки по барам (сервер): в «Общей» излишек одного бара не гасит
    // недостачу другого. Показываем недостачу; если её нет, а излишек есть —
    // излишек со знаком плюс.
    function shortageCell(short, surplus) {
        if (short > 0) {
            return qty(short) + (surplus > 0
                ? '<i class="pk-loss-plus"> +' + qty(surplus) + '</i>' : '');
        }
        return surplus > 0 ? signed(surplus, '+') : '0';
    }

    // Подпись под названием продукта: количество в его единице и чей он.
    function lossSub(row) {
        var parts = [];
        if (row.WriteoffQty > 0) parts.push('акты ' + units(row.WriteoffQty, row.Unit));
        if (row.InventoryShortQty > 0) parts.push('недостача ' + units(row.InventoryShortQty, row.Unit));
        if (row.InventorySurplusQty > 0) parts.push('излишек ' + units(row.InventorySurplusQty, row.Unit));
        // Строка позиции кликается и так; метка нужна только ингредиенту.
        var linked = row.PositionId !== null && row.PositionId !== undefined;
        if (!linked) parts.push('ингредиент');
        return parts.length ? '<span class="av-rub">' + esc(parts.join(' · ')) + '</span>' : '';
    }

    function lossRow(row, maxLoss) {
        var loss = row.LossRub || 0;
        var width = (maxLoss > 0 && loss > 0) ? Math.max(4, loss / maxLoss * 100) : 0;
        var linked = row.PositionId !== null && row.PositionId !== undefined;
        return '<div class="pk-loss-row' + (linked ? '' : ' is-static') + '"' +
            (linked ? ' data-pos="' + row.PositionId + '"' : '') + '>' +
            '<span class="pk-loss-n">' + esc(row.ProductName) + lossSub(row) + '</span>' +
            '<span class="pk-num">' + (row.WriteoffRub ? qty(row.WriteoffRub) : '0') + '</span>' +
            '<span class="pk-share">' +
                '<span class="pk-bar pk-loss-bar"><i style="width:' + width.toFixed(1) +
                '%"></i></span>' +
                '<span class="pk-loss-v">' +
                shortageCell(row.InventoryShortRub || 0, row.InventorySurplusRub || 0) +
                '</span></span>' +
            '<span class="pk-pill ' + lossTone(row.LossPercentOfSold) + '">' +
                (row.LossPercentOfSold === null || row.LossPercentOfSold === undefined
                    ? '—' : pct(row.LossPercentOfSold, 1)) + '</span>' +
            '</div>';
    }

    function renderLosses(data) {
        var losses = data.losses || {};
        var rows = losses.by_item || [];
        var totalLoss = rows.reduce(function (acc, row) { return acc + (row.LossRub || 0); }, 0);
        var maxLoss = rows.reduce(function (acc, row) { return Math.max(acc, row.LossRub || 0); }, 0);

        var html = '<div class="pk-card-h"><span class="pk-card-t">Где именно расхождения</span>' +
            '<span class="pk-card-s">' + rows.length + ' ' +
            plural(rows.length, 'продукт', 'продукта', 'продуктов') + ' · ' + qty(totalLoss) +
            ' ₽ потерь по закупке</span></div>';

        if (!losses.diagnostics || !losses.diagnostics.has_transactions) {
            html += '<div class="pk-empty" style="border-top:none">' +
                'проводки склада за период не пришли — расхождений не видно</div>';
            el.losses.innerHTML = html;
            return;
        }
        if (!rows.length) {
            html += '<div class="pk-empty" style="border-top:none">' +
                'за период расхождений по кухне не было</div>';
            el.losses.innerHTML = html;
            return;
        }

        html += '<div class="pk-loss-row is-head">' +
            '<span class="pk-th">ПРОДУКТ</span>' +
            '<span class="pk-th r">АКТЫ, ₽</span>' +
            '<span class="pk-th r">НЕДОСТАЧА, ₽</span>' +
            '<span class="pk-th r">% ОТ ПРОДАЖ</span></div>';

        // Первые восемь видны сразу, остальные под раскрывашкой — как у фасовки.
        var head = rows.slice(0, 8), tail = rows.slice(8);
        head.forEach(function (row) { html += lossRow(row, maxLoss); });

        if (tail.length) {
            var tailLoss = tail.reduce(function (acc, row) { return acc + (row.LossRub || 0); }, 0);
            html += '<details class="pk-more"><summary>ещё ' + tail.length + ' ' +
                plural(tail.length, 'продукт', 'продукта', 'продуктов') + ' · ' + qty(tailLoss) +
                ' ₽ потерь' +
                '<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">' +
                '<path d="M2 3.5 5 6.5 8 3.5" stroke-width="1.6" fill="none" ' +
                'stroke-linecap="round" stroke-linejoin="round"/></svg></summary>';
            tail.forEach(function (row) { html += lossRow(row, maxLoss); });
            html += '</details>';
        }

        html += howNote('Суммы — рубли по закупке из проводок склада группы «ЕДА». ' +
            '% — потери (акты + недостача) к списанному при продаже этого продукта · ' +
            'недостача считается по каждому бару: излишек одного бара не гасит недостачу ' +
            'другого · «+N» — излишек · «—» — продукт при продаже не списывался · ' +
            'серые строки — ингредиенты блюд: своей позиции в продажах у них нет · ' +
            'клик по строке позиции открывает её карточку', 'pk-note');
        el.losses.innerHTML = html;
    }

    function renderDiagnostics(data) {
        var losses = data.losses || {};
        var diag = losses.diagnostics || {};
        var mods = data.modifiers || {};
        var parts = [];
        if (diag.has_transactions && diag.coverage_percent !== null && diag.coverage_percent !== undefined) {
            parts.push('склад группы «ЕДА» списал при продаже ' + qty(diag.sold_by_stock) +
                ' ₽ из ' + qty(diag.sold_cost_by_register) + ' ₽ закупки проданного по кассе (' +
                pct(diag.coverage_percent, 1) + '): ' +
                (diag.coverage_percent < 95
                    ? 'часть ингредиентов лежит в других группах номенклатуры или у блюд нет техкарты'
                    : 'разница — граница учётного дня и округления техкарт'));
        }
        if (mods.count) {
            parts.push('соусы-модификаторы не входят в позиции: ' + mods.count + ' ' +
                plural(mods.count, 'позиция', 'позиции', 'позиций') + ', отдано ' +
                num(mods.qty, 0) + ' порц. на ' + money(mods.cost) + ' по закупке (выручка ' +
                money(mods.revenue) + ')');
        }
        if (diag.has_transactions) {
            parts.push('продуктов склада с движением: ' + ((diag.linked_products || 0) + (diag.ingredient_products || 0)) +
                ', из них ' + (diag.linked_products || 0) + ' продаются как есть и связаны с позициями, ' +
                (diag.ingredient_products || 0) + ' — ингредиенты блюд');
        }
        var ignored = Object.keys(diag.ignored_types || {});
        if (ignored.length) {
            parts.push('проводки других типов (возвраты и т.п.) в баланс не входят: ' +
                ignored.map(function (k) {
                    var t = diag.ignored_types[k] || {};
                    return esc(k) + ' × ' + (t.rows || 0) + ' (расход ' + qty(t.out || 0) +
                        ' ₽, приход ' + qty(t.in || 0) + ' ₽)';
                }).join(', '));
        }
        if (diag.has_transactions && diag.match_mode === 'name') {
            parts.push('связка склада с продажами — по названию: в продажах нет DishId');
        }
        el.diag.innerHTML = parts.length ? parts.join(' · ') : '';
        // Раскрывашка «Диагностика данных» без содержимого не нужна.
        var diagBox = el.diag.closest ? el.diag.closest('details') : null;
        if (diagBox) diagBox.hidden = !parts.length;
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
            '<span class="pk-th">ПОЗИЦИЯ</span>' +
            '<span class="pk-th r">ПОРЦИЙ</span>' +
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
            cell('ПРОДАНО', num(cat.TotalQty, 0) + ' порц.') +
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
        html += howNote('правило: ' + esc(info.rule), 'pk-formula');

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
        // Пороги кухни: core/abc_thresholds.py, KITCHEN_MARKUP_A_MIN / _B_MIN.
        if (letter === 'A') return 'наценка 180% и выше';
        if (letter === 'B') return 'наценка от 150% до 180%';
        if (letter === 'C') return 'наценка ниже 150%';
        return 'наценка не определена';
    }
    function marginText(letter) {
        if (letter === 'A') return 'входит в первые 80% накопленной маржи';
        if (letter === 'B') return 'следующие 15% маржи';
        if (letter === 'C') return 'последние 5% маржи';
        return 'не определено';
    }

    function abcLine(category, letter, text, formula) {
        // Буквы нет — «?», как в коде таблицы (NO_LETTER в core/abc_thresholds.py),
        // а не прочерк: прочерк читается как «пусто», а пусто одно место из трёх.
        return '<div class="pk-abc-line">' +
            '<span class="pk-abc-ltr ' + (letter ? abcClass(letter) : 'none') + '">' +
            esc(letter || '?') + '</span>' +
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
            'отклонение недельных порций делится на среднее.';
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
        html += drawerHead(p.Beer, p.Category + ' · ' + scopeLine());

        html += band('ПРОДАЖИ');
        html += '<div class="pk-cells">' +
            cell('ПРОДАНО', num(p.TotalQty, 0) + ' порц.') +
            cell('ДОЛЯ В ВЫРУЧКЕ', pct(p.RevenueSharePercent, 1)) +
            cell('НАКОПЛЕННЫМ ИТОГОМ', pct(p.RevenueCumulativePercent, 1)) +
            cell('НЕДЕЛЬ С ПРОДАЖАМИ', p.WeeksWithSales + ' из ' + p.WeeksInPeriod) +
            '</div>';
        if (p.QtyOutsideWeeks > 0) {
            // Иначе «0 недель с продажами» стоит прямо под собственной выручкой
            // позиции и выглядит поломкой страницы.
            html += howNote(num(p.QtyOutsideWeeks, 0) +
                ' ' + plural(p.QtyOutsideWeeks, 'порция продана', 'порции проданы',
                    'порций продано') +
                ' вне недельного окна ' + rangeLabel(period.weeks_from, period.weeks_to) +
                ': период не делится на целые недели, и остаток в XYZ не входит. ' +
                'В выручке и количестве выше эти продажи учтены полностью.');
        }

        html += band('ДЕНЬГИ');
        html += '<div class="pk-cells three">' +
            cell('ВЫРУЧКА', money(p.TotalRevenue)) +
            cell('МАРЖА', money(p.TotalMargin)) +
            cell('НАЦЕНКА', markupPct(p.MarkupPercent, 1),
                p.MarkupPercent === null ? 'dash' : '') +
            cell('ЦЕНА ПОРЦИИ', money(p.PricePerUnit)) +
            cell('СЕБЕС. ПОРЦИИ', money(p.CostPerUnit)) +
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
                '<span class="pk-th r">ПОРЦИЙ</span>' +
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

        // Потери позиции — только у товаров, которые продаются как есть: они сами
        // лежат на складе. Блюдо готовится из ингредиентов, и его потери — это
        // потери продуктов во вкладке «Потери».
        var shortRub = p.InventoryShortRub || 0;
        var surplusRub = p.InventorySurplusRub || 0;
        var surplus = shortRub <= 0 && surplusRub > 0;
        var invPct = surplus ? p.InventorySurplusPercentOfSold : p.InventoryShortPercentOfSold;
        var hasPct = invPct !== null && invPct !== undefined;
        var hasStock = p.SoldCostStock > 0 || p.WriteoffRub > 0 || shortRub > 0 || surplusRub > 0;
        html += band('ПОТЕРИ', '₽ по закупке, к списанному при продаже');
        if (hasStock) {
            html += '<div class="pk-cells three">' +
                cell('СПИСАНО ПРИ ПРОДАЖЕ', money(p.SoldCostStock)) +
                '<div class="pk-cell"><div class="pk-cell-cap">СПИСАНО АКТАМИ</div>' +
                '<div class="pk-cell-row"><span class="pk-cell-v">' + money(p.WriteoffRub) +
                '</span><span class="pk-pill ' + lossTone(p.WriteoffPercentOfSold) + '">' +
                (p.WriteoffPercentOfSold === null || p.WriteoffPercentOfSold === undefined
                    ? '—' : pct(p.WriteoffPercentOfSold, 1)) + '</span></div></div>' +
                '<div class="pk-cell"><div class="pk-cell-cap">' +
                (surplus ? 'ИЗЛИШЕК ИНВЕНТ.' : 'НЕДОСТАЧА ИНВЕНТ.') + '</div>' +
                '<div class="pk-cell-row"><span class="pk-cell-v">' +
                (surplus ? '+' + money(surplusRub) : money(shortRub)) +
                '</span><span class="pk-pill ' + (surplus ? 'ok' : lossTone(invPct)) + '">' +
                (!hasPct ? '—' : (surplus ? '+' : '') + pct(invPct, 1)) +
                '</span></div></div>' +
                '</div>';
        }
        var lossNote;
        if (p.SoldCostStock > 0) {
            lossNote = 'Потери ' + money(p.LossRub) + ' = акты ' + money(p.WriteoffRub) +
                ' + недостача ' + money(shortRub) + ' · ' + money(p.LossRub) + ' / ' +
                money(p.SoldCostStock) + ' = ' + pct(p.LossPercentOfSold, 1) +
                ' от списанного при продаже по складу.' +
                (shortRub > 0 && surplusRub > 0
                    ? ' Ещё излишек ' + money(surplusRub) + ' в других барах: недостачу он ' +
                      'не гасит — инвентаризация каждого бара отдельный пересчёт.'
                    : '');
        } else if (hasStock) {
            lossNote = 'При продаже по складу не списывалось, но движения есть: акты ' +
                money(p.WriteoffRub) + (surplus ? ', излишек ' + money(surplusRub)
                    : ' + недостача ' + money(shortRub)) +
                ' — потери ' + money(p.LossRub) + ', процент не определён.';
        } else {
            lossNote = 'Позиция готовится из ингредиентов или не сопоставлена со складом: ' +
                'её потери — это потери продуктов во вкладке «Потери», по блюду их не посчитать.';
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
        html += howNote('Буква по выручке считается дважды и от разных ' +
            'баз: по всему ассортименту разреза и внутри своей категории. Обе верные, ' +
            'но означают разное — поэтому показаны обе, а не одна без пояснения. ' +
            'В знаменателе долей стоит сумма только ПОЛОЖИТЕЛЬНЫХ значений: возврат не ' +
            'увеличивает целое, долей которого он считается, поэтому база маржи может ' +
            'отличаться от итоговой маржи разреза.');

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
        html += howNote(esc(xyzNote(p, data)));

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
            if (event.target.id === 'ktCustom') {
                var from = document.getElementById('ktFrom').value;
                var to = document.getElementById('ktTo').value;
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
            state.limit = ROWS_STEP;
            if (state.data) renderPositions();
        });

        el.cats.addEventListener('click', onTableClick);
        el.pos.addEventListener('click', function (event) {
            if (event.target.closest('[data-more-rows]')) {
                state.limit += ROWS_STEP;
                renderPositions();
                return;
            }
            onTableClick(event);
        });
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
            burger: document.getElementById('ktBurger'),
            barBtn: document.getElementById('ktBarBtn'),
            barMenu: document.getElementById('ktBarMenu'),
            barLabel: document.getElementById('ktBarLabel'),
            perBtn: document.getElementById('ktPerBtn'),
            perMenu: document.getElementById('ktPerMenu'),
            perLabel: document.getElementById('ktPerLabel'),
            perHint: document.getElementById('ktPerHint'),
            catch_: document.getElementById('ktCatch'),
            run: document.getElementById('ktRun'),
            runLabel: document.getElementById('ktRunLabel'),
            spin: document.getElementById('ktSpin'),
            context: document.getElementById('ktContext'),
            xyzChip: document.getElementById('ktXyzChip'),
            msg: document.getElementById('ktMsg'),
            body: document.getElementById('ktBody'),
            tabs: document.getElementById('ktTabs'),
            overview: document.getElementById('ktOverview'),
            prices: document.getElementById('ktPrices'),
            barsView: document.getElementById('ktPanelBars'),
            filter: document.getElementById('ktFilter'),
            panelItems: document.getElementById('ktPanelItems'),
            panelCats: document.getElementById('ktPanelCats'),
            panelLosses: document.getElementById('ktPanelLosses'),
            catCount: document.getElementById('ktCatCount'),
            cats: document.getElementById('ktCats'),
            posCount: document.getElementById('ktPosCount'),
            search: document.getElementById('ktSearch'),
            pos: document.getElementById('ktPos'),
            updated: document.getElementById('ktUpdated'),
            balance: document.getElementById('ktBalance'),
            losses: document.getElementById('ktLosses'),
            diag: document.getElementById('ktDiag'),
            drawer: document.getElementById('ktDrawer'),
            backdrop: document.getElementById('ktBackdrop')
        };

        var barsNode = document.getElementById('ktBars');
        try {
            state.bars = JSON.parse(barsNode ? barsNode.textContent : '[]') || [];
        } catch (e) {
            state.bars = [];
        }

        // Вкладки, «Обзор», «Цены», бары — общий модуль; таблицы и карточки
        // рисует эта страница, модуль только открывает их по клику.
        if (window.AbcView && el.tabs) {
            view = window.AbcView.mount({
                tabs: el.tabs,
                panels: { overview: el.overview, items: el.panelItems, cats: el.panelCats,
                          prices: el.prices, losses: el.panelLosses, bars: el.barsView },
                boxes: { overview: el.overview, prices: el.prices, bars: el.barsView, chips: el.filter },
                open: { item: openPosition, rule: openBucket },
                filter: function () {
                    state.limit = ROWS_STEP;
                    if (state.data) renderPositions();
                }
            });
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

    // Для тестов отрисовки (tests/test_kitchen_render.mjs): чистые функции и
    // рендер должны быть вызываемы вне браузера.
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { num: num, fixed: fixed, money: money, pct: pct, esc: esc,
                           plural: plural, presetRange: presetRange, weeksIn: weeksIn,
                           abcClass: abcClass, xyzNote: xyzNote,
                           lossTone: lossTone, signed: signed, qty: qty, units: units,
                           markupPct: markupPct };
    }
    if (typeof window !== 'undefined') {
        window.__kitchen = { state: state, render: render, openPosition: openPosition,
                               view: function () { return view; },
                               openCategory: openCategory, openBucket: openBucket,
                               num: num, money: money, pct: pct, esc: esc, plural: plural,
                               abcClass: abcClass, weeksIn: weeksIn, lossTone: lossTone,
                               signed: signed, qty: qty, openBucket: openBucket,
                               markupPct: markupPct, presetRange: presetRange };
    }
})();

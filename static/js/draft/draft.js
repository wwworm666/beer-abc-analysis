/* Страница «Анализ проливов» (/draft) — сборка экрана по макету владельца
   (Claude Design, 2026-08-14).

   Всё содержимое приходит ОДНИМ ответом /api/draft-kegs: сводка, кеги, бармены,
   баланс склада. Поэтому сортировка, поиск и карточки работают без запросов —
   считаются по уже полученному блоку.

   Числа не пересчитываются на клиенте нигде, кроме форматирования и ширины
   шкал: доли, наценки и итоги приходят посчитанными сервером (core/draft_kegs.py),
   чтобы страница и документация говорили одно и то же.
*/
(function () {
    'use strict';

    // ==================== состояние ====================

    var state = {
        bar: '',                 // '' = все бары («Общая»)
        preset: 'prev_week',
        from: null,
        to: null,
        data: null,              // блок ответа /api/draft-kegs
        query: '',
        kegSort: { key: 'TotalLiters', dir: -1 },
        btSort: { key: 'TotalLiters', dir: -1 },
        loading: false
    };

    var el = {};

    // ==================== формат ====================

    // Хвостовые нули не показываем: 86,7 и 8, а не 86,70 и 8,00 — так в макете
    // выглядят литры и порции в таблицах.
    function num(value, digits) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        return new Intl.NumberFormat('ru-RU', {
            minimumFractionDigits: 0,
            maximumFractionDigits: digits === undefined ? 2 : digits
        }).format(value);
    }
    // Ровно столько знаков, сколько просили: в балансе и в потерях колонки должны
    // стоять столбиком, поэтому там 620,00 и 39,90.
    function fixed(value, digits) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        // Типографский минус вместо дефиса: рядом стоят наши собственные «−» в
        // балансе, и два разных знака в одной колонке выглядят как опечатка.
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
    // прыгает. Ноль знаков просят явно — там, где место дорого (таблицы, итоги).
    function pct(value, digits) {
        if (value === null || value === undefined || isNaN(value)) return '—';
        var d = digits === undefined ? 1 : digits;
        return fixed(value, d) + '%';
    }
    // Знак ставим сами: минус из Intl выглядит как дефис, а в балансе важно, что
    // строка расходная — даже когда сумма нулевая («−0,00» у перемещений).
    function signed(magnitude, sign, digits) {
        if (magnitude === null || magnitude === undefined || isNaN(magnitude)) return '—';
        return sign + fixed(Math.abs(magnitude), digits === undefined ? 2 : digits);
    }
    function esc(text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function initials(name) {
        var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
        if (!parts.length) return '—';
        if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
        return (parts[0][0] + parts[1][0]).toUpperCase();
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
    function daysBetween(from, to) {
        return Math.round((new Date(to) - new Date(from)) / 86400000) + 1;
    }
    // «26 кегов», «8 барменов», «7 дней» — без этого подписи звучат как робот.
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

        if (key === 'today') {
            /* от сегодня до сегодня */
        } else if (key === 'yesterday') {
            from.setDate(today.getDate() - 1);
            to = new Date(from);
        } else if (key === 'week') {
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
        } else if (key === 'd30') {
            from.setDate(today.getDate() - 29);
        } else if (key === 'd90') {
            from.setDate(today.getDate() - 89);
        } else {
            return null;
        }
        return { from: dateISO(from), to: dateISO(to) };
    }

    var PRESETS = [
        { key: 'prev_week', label: 'Прошлая неделя' },
        { key: 'week', label: 'Текущая неделя' },
        { key: 'yesterday', label: 'Вчера' },
        { key: 'today', label: 'Сегодня' },
        { key: 'prev_month', label: 'Прошлый месяц' },
        { key: 'month', label: 'Текущий месяц' },
        { key: 'd30', label: 'Последние 30 дней' },
        { key: 'd90', label: 'Последние 90 дней' }
    ];

    function presetLabel(key) {
        for (var i = 0; i < PRESETS.length; i++) {
            if (PRESETS[i].key === key) return PRESETS[i].label;
        }
        return 'Свой период';
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
        var html = '<button type="button" class="dr-menu-item' +
            (state.bar ? '' : ' is-on') + '" data-bar=""><span>Общая</span>' +
            '<span>все точки</span></button>';
        bars.forEach(function (bar) {
            html += '<button type="button" class="dr-menu-item' +
                (state.bar === bar ? ' is-on' : '') + '" data-bar="' + esc(bar) + '">' +
                '<span>' + esc(bar) + '</span><span></span></button>';
        });
        el.barMenu.innerHTML = html;
    }

    function buildPerMenu() {
        var html = '';
        PRESETS.forEach(function (preset) {
            var range = presetRange(preset.key);
            html += '<button type="button" class="dr-menu-item' +
                (state.preset === preset.key ? ' is-on' : '') +
                '" data-preset="' + preset.key + '">' +
                '<span>' + esc(preset.label) + '</span>' +
                '<span>' + esc(rangeLabel(range.from, range.to)) + '</span></button>';
        });
        // Свой период: пресеты закрывают обычные вопросы, но расчёт умеет любой
        // диапазон, и отнимать эту возможность у страницы нельзя.
        html += '<div class="dr-menu-item" style="display:block;cursor:default">' +
            '<div style="font:600 9.5px/1 var(--dr-mono);letter-spacing:.14em;' +
            'color:var(--dr-ink5);margin-bottom:7px">СВОЙ ПЕРИОД</div>' +
            '<div style="display:flex;gap:6px;align-items:center">' +
            '<input type="date" id="drFrom" value="' + esc(state.from || '') + '">' +
            '<input type="date" id="drTo" value="' + esc(state.to || '') + '">' +
            '<button type="button" class="dr-run" id="drCustom" ' +
            'style="height:30px;padding:0 14px">ОК</button></div></div>';
        el.perMenu.innerHTML = html;
    }

    // ==================== запрос ====================

    function showMessage(text, isError) {
        el.msg.hidden = false;
        el.msg.className = 'dr-msg' + (isError ? ' err' : '');
        el.msg.textContent = text;
    }

    function run() {
        if (state.loading) return;
        if (!state.from || !state.to) {
            showMessage('Выберите период', true);
            return;
        }
        state.loading = true;
        el.spin.hidden = false;
        el.runLabel.textContent = 'Считаю…';
        el.run.disabled = true;
        el.body.hidden = true;
        showMessage('Забираем данные из iiko: проводки по кегам, продажи, техкарты…');

        fetch('/api/draft-kegs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bar: state.bar, date_from: state.from, date_to: state.to })
        }).then(function (response) {
            return response.json().then(function (payload) {
                return { ok: response.ok, status: response.status, payload: payload };
            });
        }).then(function (result) {
            if (!result.ok) {
                // Сервер присылает причину («Нет данных за выбранный период») —
                // показываем её, а не общее «ошибка запроса».
                throw new Error((result.payload && result.payload.error) ||
                                ('HTTP ' + result.status));
            }
            var keys = Object.keys(result.payload || {});
            if (!keys.length) throw new Error('За выбранный период движения кегов не было');
            state.data = result.payload[keys[0]];
            state.query = '';
            el.search.value = '';
            render();
        }).catch(function (error) {
            state.data = null;
            el.body.hidden = true;
            showMessage(error.message, true);
        }).then(function () {
            state.loading = false;
            el.spin.hidden = true;
            el.runLabel.textContent = 'Запустить анализ';
            el.run.disabled = false;
        });
    }

    // ==================== отрисовка ====================

    function render() {
        var data = state.data;
        if (!data) return;
        el.msg.hidden = true;
        el.body.hidden = false;

        var period = data.period || {};
        el.context.textContent = 'разрез: ' + (state.bar || 'Общая') + ' · ' +
            rangeLabel(period.from, period.to) + ' · ' + period.days + ' дн.';
        if (data.generated_at) {
            el.updated.hidden = false;
            el.updated.textContent = 'обновлено ' + data.generated_at;
        } else {
            el.updated.hidden = true;
        }

        renderSummary(data);
        renderKegs();
        renderBartenders();
        renderBalance(data);
        renderLosses(data);
        renderDiagnostics(data);
    }

    function tile(cap, value, unit, sub) {
        return '<div class="dr-tile"><div class="dr-tile-cap">' + esc(cap) + '</div>' +
            '<div class="dr-tile-v">' + value +
            (unit ? '<u> ' + esc(unit) + '</u>' : '') + '</div>' +
            '<div class="dr-tile-s">' + esc(sub) + '</div></div>';
    }

    function renderSummary(data) {
        var period = data.period || {};
        var kegs = data.total_kegs || 0;
        var html = '';
        html += tile('ПРОДАНО', num(data.total_liters), 'л',
            kegs + ' ' + plural(kegs, 'кег', 'кега', 'кегов') + ' за ' + period.days +
            ' ' + plural(period.days, 'день', 'дня', 'дней'));
        html += tile('ВЫРУЧКА', num(Math.round(data.total_revenue), 0), '₽', 'разливное пиво');
        html += tile('ВСЕГО ПОРЦИЙ', num(data.total_portions), '', 'по кассе iiko');
        html += tile('ЦЕНА ЗА ЛИТР', num(Math.round(data.avg_price_per_liter), 0), '₽',
            'выручка / литры');
        html += tile('ОБЪЁМ ПОРЦИИ', num(data.avg_portion_liters, 3), 'л', 'литры / порции');
        html += tile('НАЦЕНКА',
            data.markup_percent === null ? '—' : num(data.markup_percent, 1), '%',
            'средняя по разрезу');
        var people = data.total_bartenders || 0;
        html += tile('БАРМЕНОВ', num(people, 0), '', 'пробивали проливы');
        el.sum.innerHTML = html;
    }

    function sortRows(rows, sort) {
        var copy = rows.slice();
        copy.sort(function (a, b) {
            var av = a[sort.key], bv = b[sort.key];
            if (av === null || av === undefined) av = -Infinity;
            if (bv === null || bv === undefined) bv = -Infinity;
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

    function shareCell(percent, maxPercent, wrapClass) {
        var width = maxPercent > 0 ? Math.max(2, (percent / maxPercent) * 100) : 0;
        return '<span class="dr-share"><span class="dr-bar' +
            (wrapClass ? ' ' + wrapClass : '') + '"><i style="width:' +
            width.toFixed(1) + '%"></i></span>' +
            '<span class="dr-share-v">' + pct(percent, 1) + '</span></span>';
    }

    function renderKegs() {
        var data = state.data;
        var rows = data.kegs || [];
        var query = state.query.trim().toLowerCase();
        if (query) {
            rows = rows.filter(function (keg) {
                return String(keg.KegName || '').toLowerCase().indexOf(query) >= 0;
            });
        }
        rows = sortRows(rows, state.kegSort);
        var maxShare = rows.reduce(function (acc, keg) {
            return Math.max(acc, keg.LitersSharePercent || 0);
        }, 0);

        var total = data.total_kegs || 0;
        el.kegCount.textContent = query
            ? rows.length + ' из ' + total
            : total + ' ' + plural(total, 'позиция', 'позиции', 'позиций');

        var html = '<div class="dr-row is-head">' +
            '<span class="dr-th">#</span>' +
            '<span class="dr-th">КЕГ</span>' +
            '<span class="dr-th r s" data-sort="TotalLiters">ЛИТРЫ' +
                sortMark(state.kegSort, 'TotalLiters') + '</span>' +
            '<span class="dr-th r s" data-sort="TotalPortions">ПОРЦИИ' +
                sortMark(state.kegSort, 'TotalPortions') + '</span>' +
            '<span class="dr-th r">ДОЛЯ ПО Л</span>' +
            '<span class="dr-th r s" data-sort="TotalRevenue">ВЫРУЧКА' +
                sortMark(state.kegSort, 'TotalRevenue') + '</span>' +
            '<span class="dr-th r s" data-sort="PricePerLiter">ЦЕНА/Л' +
                sortMark(state.kegSort, 'PricePerLiter') + '</span>' +
            '<span class="dr-th r s" data-sort="MarkupPercent">НАЦЕНКА' +
                sortMark(state.kegSort, 'MarkupPercent') + '</span>' +
            '<span class="dr-th c">ABC</span>' +
            '<span class="dr-th c">XYZ</span>' +
            '</div>';

        rows.forEach(function (keg, index) {
            html += '<div class="dr-row is-body" data-keg="' + esc(keg.KegId) + '">' +
                '<span class="dr-rank">' + (index + 1) + '</span>' +
                '<span class="dr-name">' + esc(keg.KegName) + '</span>' +
                '<span class="dr-num strong">' + num(keg.TotalLiters) + '</span>' +
                '<span class="dr-num">' + num(keg.TotalPortions) + '</span>' +
                shareCell(keg.LitersSharePercent, maxShare) +
                '<span class="dr-num strong">' + money(keg.TotalRevenue) + '</span>' +
                '<span class="dr-num">' + money(keg.PricePerLiter) + '</span>' +
                '<span class="dr-num">' +
                    (keg.MarkupPercent === null ? '—' : pct(keg.MarkupPercent, 0)) + '</span>' +
                '<span class="dr-cell-c"><span class="dr-abc ' + abcClass(keg.ABC_Combined) +
                    '">' + esc(keg.ABC_Combined) + '</span></span>' +
                '<span class="dr-xyz' + (keg.XYZ_Category ? ' has' : '') + '">' +
                    (keg.XYZ_Category ? esc(keg.XYZ_Category) : '—') + '</span>' +
                '</div>';
        });

        if (!rows.length) {
            html += '<div class="dr-empty">ничего не найдено — уточните запрос</div>';
        } else {
            var sumLiters = rows.reduce(function (a, k) { return a + k.TotalLiters; }, 0);
            var sumPortions = rows.reduce(function (a, k) { return a + k.TotalPortions; }, 0);
            var sumRevenue = rows.reduce(function (a, k) { return a + k.TotalRevenue; }, 0);
            var sumCost = rows.reduce(function (a, k) { return a + k.TotalCost; }, 0);
            var sumShare = rows.reduce(function (a, k) { return a + k.LitersSharePercent; }, 0);
            html += '<div class="dr-row is-total">' +
                '<span></span>' +
                '<span class="dr-total-n">Итого · ' + rows.length + ' ' +
                    plural(rows.length, 'кег', 'кега', 'кегов') + '</span>' +
                '<span class="dr-total-v strong">' + num(sumLiters) + '</span>' +
                '<span class="dr-total-v">' + num(sumPortions) + '</span>' +
                '<span class="dr-total-v">' + pct(sumShare, 0) + '</span>' +
                '<span class="dr-total-v strong">' + money(sumRevenue) + '</span>' +
                '<span class="dr-total-v">' +
                    money(sumLiters > 0 ? sumRevenue / sumLiters : 0) + '</span>' +
                '<span class="dr-total-v">' +
                    (sumCost > 0 ? pct((sumRevenue - sumCost) / sumCost * 100, 0) : '—') +
                    '</span>' +
                '<span></span><span></span></div>';
        }
        el.kegs.innerHTML = html;
    }

    function renderBartenders() {
        var rows = sortRows(state.data.bartenders || [], state.btSort);
        var maxShare = rows.reduce(function (acc, person) {
            return Math.max(acc, person.LitersSharePercent || 0);
        }, 0);

        var html = '<div class="dr-row is-head">' +
            '<span class="dr-th">#</span>' +
            '<span class="dr-th">БАРМЕН</span>' +
            '<span class="dr-th r s" data-sort="TotalLiters">ЛИТРЫ' +
                sortMark(state.btSort, 'TotalLiters') + '</span>' +
            '<span class="dr-th r">ДОЛЯ ПО Л</span>' +
            '<span class="dr-th r s" data-sort="TotalPortions">ПОРЦИИ' +
                sortMark(state.btSort, 'TotalPortions') + '</span>' +
            '<span class="dr-th r s" data-sort="KegsCount">КЕГОВ' +
                sortMark(state.btSort, 'KegsCount') + '</span>' +
            '<span class="dr-th r s" data-sort="TotalRevenue">ВЫРУЧКА' +
                sortMark(state.btSort, 'TotalRevenue') + '</span>' +
            '<span class="dr-th r s" data-sort="TotalMargin">МАРЖА' +
                sortMark(state.btSort, 'TotalMargin') + '</span>' +
            '<span class="dr-th r s" data-sort="MarkupPercent">НАЦЕНКА' +
                sortMark(state.btSort, 'MarkupPercent') + '</span>' +
            '<span class="dr-th r s" data-sort="PricePerLiter">ЦЕНА/Л' +
                sortMark(state.btSort, 'PricePerLiter') + '</span>' +
            '</div>';

        rows.forEach(function (person, index) {
            html += '<div class="dr-row is-body" data-bt="' + esc(person.Bartender) + '">' +
                '<span class="dr-rank">' + (index + 1) + '</span>' +
                '<span class="dr-name">' + esc(person.Bartender) + '</span>' +
                '<span class="dr-num strong">' + num(person.TotalLiters) + '</span>' +
                shareCell(person.LitersSharePercent, maxShare) +
                '<span class="dr-num">' + num(person.TotalPortions) + '</span>' +
                '<span class="dr-num">' + person.KegsCount + '</span>' +
                '<span class="dr-num strong">' + money(person.TotalRevenue) + '</span>' +
                '<span class="dr-num">' + money(person.TotalMargin) + '</span>' +
                '<span class="dr-num">' +
                    (person.MarkupPercent === null ? '—' : pct(person.MarkupPercent, 0)) +
                    '</span>' +
                '<span class="dr-num">' + money(person.PricePerLiter) + '</span>' +
                '</div>';
        });

        if (!rows.length) {
            html += '<div class="dr-empty">за период продаж разливного не было</div>';
        } else {
            var data = state.data;
            html += '<div class="dr-row is-total">' +
                '<span></span>' +
                '<span class="dr-total-n">Итого · ' + rows.length + ' ' +
                    plural(rows.length, 'бармен', 'бармена', 'барменов') + '</span>' +
                '<span class="dr-total-v strong">' + num(data.total_liters) + '</span>' +
                '<span class="dr-total-v">100%</span>' +
                '<span class="dr-total-v">' + num(data.total_portions) + '</span>' +
                '<span class="dr-total-v dash">—</span>' +
                '<span class="dr-total-v strong">' + money(data.total_revenue) + '</span>' +
                '<span class="dr-total-v">' + money(data.total_margin) + '</span>' +
                '<span class="dr-total-v">' +
                    (data.markup_percent === null ? '—' : pct(data.markup_percent, 0)) +
                    '</span>' +
                '<span class="dr-total-v">' + money(data.avg_price_per_liter) + '</span>' +
                '</div>';
        }
        el.bts.innerHTML = html;
    }

    function balanceRow(label, value, sign, scale, tone, pill) {
        var width = scale > 0 ? Math.min(100, Math.abs(value) / scale * 100) : 0;
        return '<div class="dr-bal-row">' +
            '<span class="dr-bal-n">' + esc(label) + '</span>' +
            '<span class="dr-bal-track' + (tone ? ' ' + tone : '') + '">' +
                (Math.abs(value) > 0 ? '<i style="width:' + width.toFixed(1) + '%"></i>' : '') +
                '</span>' +
            '<span class="dr-bal-v ' + (Math.abs(value) < 0.005 ? 'zero' : (tone || '')) + '">' +
                signed(value, sign) + '</span>' +
            '<span>' + (pill || '') + '</span></div>';
    }

    function renderBalance(data) {
        var losses = data.losses || {};
        // Масштаб общий для всех полос: иначе списание 6 л выглядит как продажа 770 л.
        var scale = Math.max(losses.sold || 0, losses.invoice_in || 0, 1);
        var html = '<div class="dr-card-h"><span class="dr-card-t">Баланс кегов за период</span>' +
            '<span class="dr-card-s">склад iiko</span></div>';

        html += balanceRow('Приход по накладным', losses.invoice_in, '+', scale, 'ok');
        html += balanceRow('Перемещения · приход', losses.transfer_in, '+', scale, '');
        html += balanceRow('Перемещения · расход', losses.transfer_out, '−', scale, '');
        html += balanceRow('Продано через кассу', losses.sold, '−', scale, '');
        html += balanceRow('Списано актами', losses.writeoff, '−', scale, 'warn',
            losses.sold > 0 ? '<span class="dr-pill warn">' +
                pct(losses.writeoff_percent_of_sold, 1) + ' от продаж</span>' : '');
        html += balanceRow('Недостача по инвентаризациям', losses.inventory_net, '−', scale, 'bad',
            losses.sold > 0 ? '<span class="dr-pill bad">' +
                pct(losses.inventory_percent_of_sold, 1) + ' от продаж</span>' : '');

        var spent = (losses.sold || 0) + (losses.writeoff || 0) +
                    (losses.inventory_net || 0) + (losses.transfer_out || 0);
        html += '<div class="dr-bal-total">' +
            '<span class="dr-bal-total-n">Изменение остатка кегов</span>' +
            '<span class="dr-bal-lead"></span>' +
            '<span class="dr-bal-total-v">' +
            signed(losses.balance, losses.balance < 0 ? '−' : '+') + ' л</span></div>' +
            '<div class="dr-note">приход ' + fixed(losses.invoice_in, 2) + ' − расход ' +
            fixed(spent, 2) + ' · списание по техкарте при продаже</div>';
        el.balance.innerHTML = html;
    }

    // Цвет плашки «% от продаж»: до 10% спокойный, до 30% янтарный, выше красный.
    // Пороги взяты от факта: за 3,5 месяца недостача по всем барам — 9,2% от
    // проданного, поэтому «до 10%» читается как обычный фон, а не как тревога.
    function lossTone(percent) {
        if (percent === null || percent === undefined) return 'calm';
        if (percent >= 30) return 'bad';
        if (percent >= 10) return 'warn';
        return 'calm';
    }

    function lossRow(row, maxLoss) {
        var loss = (row.WriteoffLiters || 0) + Math.max(row.InventoryNetLiters || 0, 0);
        var percent = row.SoldLiters > 0 ? loss / row.SoldLiters * 100 : null;
        // Излишек (недостача с минусом) — не потеря: полосы у такой строки нет,
        // иначе красная засечка читалась бы как «тут пропало».
        var width = (maxLoss > 0 && loss > 0) ? Math.max(4, loss / maxLoss * 100) : 0;
        return '<div class="dr-loss-row" data-keg="' + esc(row.KegId) + '">' +
            '<span class="dr-loss-n">' + esc(row.KegName) + '</span>' +
            '<span class="dr-num">' +
                (row.WriteoffLiters ? fixed(row.WriteoffLiters, 2) : '0') + '</span>' +
            '<span class="dr-share">' +
                '<span class="dr-bar dr-loss-bar"><i style="width:' + width.toFixed(1) +
                '%"></i></span>' +
                '<span class="dr-loss-v">' + fixed(row.InventoryNetLiters, 2) + '</span></span>' +
            '<span class="dr-pill ' + lossTone(percent) + '">' +
                (percent === null ? '—' : pct(percent, 1)) + '</span>' +
            '</div>';
    }

    function renderLosses(data) {
        var rows = (data.losses && data.losses.by_keg) || [];
        var totalLoss = rows.reduce(function (acc, row) {
            return acc + (row.WriteoffLiters || 0) + Math.max(row.InventoryNetLiters || 0, 0);
        }, 0);
        var maxLoss = rows.reduce(function (acc, row) {
            return Math.max(acc, (row.WriteoffLiters || 0) +
                Math.max(row.InventoryNetLiters || 0, 0));
        }, 0);

        var html = '<div class="dr-card-h"><span class="dr-card-t">Где именно расхождения</span>' +
            '<span class="dr-card-s">' + rows.length + ' ' +
            plural(rows.length, 'кег', 'кега', 'кегов') + ' · ' + num(totalLoss) +
            ' л потерь</span></div>';

        if (!rows.length) {
            html += '<div class="dr-empty" style="border-top:none">' +
                'за период расхождений по кегам не было</div>';
            el.losses.innerHTML = html;
            return;
        }

        html += '<div class="dr-loss-row is-head">' +
            '<span class="dr-th">КЕГ</span>' +
            '<span class="dr-th r">АКТЫ</span>' +
            '<span class="dr-th r">НЕДОСТАЧА</span>' +
            '<span class="dr-th r">% ОТ ПРОДАЖ</span></div>';

        var head = rows.slice(0, 8), tail = rows.slice(8);
        head.forEach(function (row) { html += lossRow(row, maxLoss); });

        if (tail.length) {
            var tailLoss = tail.reduce(function (acc, row) {
                return acc + (row.WriteoffLiters || 0) +
                    Math.max(row.InventoryNetLiters || 0, 0);
            }, 0);
            html += '<details class="dr-more"><summary>ещё ' + tail.length + ' ' +
                plural(tail.length, 'кег', 'кега', 'кегов') + ' · ' + num(tailLoss) +
                ' л потерь' +
                '<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">' +
                '<path d="M2 3.5 5 6.5 8 3.5" stroke-width="1.6" fill="none" ' +
                'stroke-linecap="round" stroke-linejoin="round"/></svg></summary>';
            tail.forEach(function (row) { html += lossRow(row, maxLoss); });
            html += '</details>';
        }

        html += '<div class="dr-note">% — потери (акты + недостача) к проданному по кегу · ' +
            '«—» — кег не продавался · клик по строке открывает карточку</div>';
        el.losses.innerHTML = html;
    }

    function renderDiagnostics(data) {
        var notes = data.bartender_notes || {};
        var parts = [];
        if (!data.xyz_available) {
            parts.push('XYZ не рассчитан: в периоде ' + data.xyz_buckets +
                ' ' + plural(data.xyz_buckets, 'полная неделя', 'полные недели',
                    'полных недель') + ', для оценки стабильности нужно минимум 3');
        }
        if (Math.abs(notes.unassigned_liters || 0) > 0.01) {
            parts.push('не отнесено ни к одному бармену ' +
                num(notes.unassigned_liters) + ' л: списание кега есть, а строки продаж ' +
                'под него нет (граница учётного дня)');
        }
        if ((notes.dishes_without_volume || []).length) {
            parts.push('позиции без нормы закладки в техкарте, их литры разошлись по ' +
                'остальным блюдам того же кега: ' +
                notes.dishes_without_volume.map(function (dish) {
                    return esc(dish.DishName) + ' (' + num(dish.Portions) + ' порц.)';
                }).join(', '));
        }
        if (notes.kegs_scaled) {
            parts.push('кегов, где техкарта разошлась с фактом списания больше чем на 1%: ' +
                notes.kegs_scaled + ', максимальное расхождение ' +
                pct(notes.max_factor_deviation_percent, 1));
        }
        if ((data.unmapped_dishes || []).length) {
            parts.push('позиции без связки с кегом, их деньги в таблицу не попали: ' +
                data.unmapped_dishes.map(function (dish) {
                    return esc(dish.DishName) + ' (' + money(dish.Revenue) + ')';
                }).join(', '));
        }
        el.diag.innerHTML = parts.length ? parts.join(' · ') : '';
    }

    // ==================== карточки ====================

    function cell(cap, value, extraClass) {
        return '<div class="dr-cell"><div class="dr-cell-cap">' + esc(cap) + '</div>' +
            '<div class="dr-cell-v' + (extraClass ? ' ' + extraClass : '') + '">' +
            value + '</div></div>';
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

    function drawerHead(title, subtitle, avatar) {
        return '<div class="dr-dr-head">' +
            (avatar ? '<span class="dr-dr-ava">' + esc(avatar) + '</span>' : '') +
            '<div style="flex:1;min-width:0">' +
            '<div class="dr-dr-t">' + esc(title) + '</div>' +
            '<div class="dr-dr-s">' + esc(subtitle) + '</div></div>' +
            '<button type="button" class="dr-close" data-close aria-label="Закрыть">' +
            '<svg width="12" height="12" viewBox="0 0 12 12"><path d="M2.5 2.5 9.5 9.5 ' +
            'M9.5 2.5 2.5 9.5" stroke-width="1.6" stroke-linecap="round" fill="none"/></svg>' +
            '</button></div>';
    }

    function sub(title, hint) {
        return '<div class="dr-sub"><span class="dr-sub-t">' + esc(title) + '</span>' +
            '<span class="dr-sub-line"></span>' +
            (hint ? '<span class="dr-sub-s">' + esc(hint) + '</span>' : '') + '</div>';
    }

    var ABC_TEXT = {
        Revenue: {
            A: 'входит в первые 80% накопленной выручки',
            B: 'следующие 15% выручки',
            C: 'последние 5% выручки'
        },
        Markup: { A: 'верхняя треть по наценке', B: 'середина', C: 'нижняя треть' },
        Margin: { A: 'верхняя треть по марже', B: 'середина', C: 'нижняя треть' }
    };

    function openKeg(kegId) {
        var kegs = (state.data && state.data.kegs) || [];
        var keg = null;
        for (var i = 0; i < kegs.length; i++) {
            if (kegs[i].KegId === kegId) { keg = kegs[i]; break; }
        }
        if (!keg) return;

        var period = state.data.period || {};
        var html = '<div class="dr-dr-in">';
        html += drawerHead(keg.KegName, 'разрез: ' + (state.bar || 'Общая') + ' · ' +
            rangeLabel(period.from, period.to));

        html += sub('ПРОДАЖИ');
        html += '<div class="dr-cells">' +
            cell('ПРОДАНО', num(keg.TotalLiters) + ' л') +
            cell('ПОРЦИЙ', num(keg.TotalPortions)) +
            cell('ДОЛЯ ПО ЛИТРАМ', pct(keg.LitersSharePercent, 1)) +
            cell('ДОЛЯ В ВЫРУЧКЕ', pct(keg.RevenueSharePercent, 1)) +
            cell('НА КРАНЕ', keg.WeeksWithSales + ' из ' + keg.WeeksInPeriod + ' нед.') +
            cell('ЛИТРОВ В НЕДЕЛЮ', num(keg.AvgLitersPerWeek)) +
            '</div>';

        html += sub('ДЕНЬГИ');
        html += '<div class="dr-cells three">' +
            cell('ВЫРУЧКА', money(keg.TotalRevenue)) +
            cell('МАРЖА', money(keg.TotalMargin)) +
            cell('НАЦЕНКА', keg.MarkupPercent === null ? '—' : pct(keg.MarkupPercent, 1),
                keg.MarkupPercent === null ? 'dash' : '') +
            '</div>';

        var people = keg.Bartenders || [];
        if (people.length) {
            html += sub('КТО НАЛИВАЛ', 'клик — карточка бармена');
            html += '<div class="dr-who-row is-head">' +
                '<span class="dr-th">БАРМЕН</span>' +
                '<span class="dr-th r">ЛИТРЫ</span>' +
                '<span class="dr-th r">ПОРЦ.</span>' +
                '<span class="dr-th r">ВЫРУЧКА</span>' +
                '<span class="dr-th r">ДОЛЯ КЕГА</span></div>';
            var maxShare = people.reduce(function (acc, p) {
                return Math.max(acc, p.SharePercent || 0);
            }, 0);
            people.forEach(function (person) {
                var width = maxShare > 0 ? Math.max(4, person.SharePercent / maxShare * 100) : 0;
                html += '<div class="dr-who-row" data-bt="' + esc(person.Bartender) + '">' +
                    '<span class="dr-name">' + esc(person.Bartender) + '</span>' +
                    '<span class="dr-num strong">' + num(person.Liters) + '</span>' +
                    '<span class="dr-num">' + num(person.Portions) + '</span>' +
                    '<span class="dr-num">' + money(person.Revenue) + '</span>' +
                    '<span class="dr-share"><span class="dr-bar dr-who-bar">' +
                    '<i style="width:' + width.toFixed(1) + '%"></i></span>' +
                    '<span class="dr-share-v">' + pct(person.SharePercent, 1) +
                    '</span></span></div>';
            });
        }

        var writeoffPct = keg.TotalLiters > 0 ? keg.WriteoffLiters / keg.TotalLiters * 100 : null;
        var shortPct = keg.TotalLiters > 0
            ? keg.InventoryNetLiters / keg.TotalLiters * 100 : null;
        html += sub('ПОТЕРИ', 'к проданному по кегу');
        html += '<div class="dr-cells two">' +
            '<div class="dr-cell"><div class="dr-cell-cap">СПИСАНО АКТАМИ</div>' +
            '<div class="dr-cell-row"><span class="dr-cell-v">' +
            fixed(keg.WriteoffLiters, 2) + '</span><span class="dr-pill ' +
            lossTone(writeoffPct) + '">' +
            (writeoffPct === null ? '—' : pct(writeoffPct, 1)) + '</span></div></div>' +
            '<div class="dr-cell"><div class="dr-cell-cap">НЕДОСТАЧА ИНВЕНТ.</div>' +
            '<div class="dr-cell-row"><span class="dr-cell-v">' +
            fixed(keg.InventoryNetLiters, 2) + '</span><span class="dr-pill ' +
            lossTone(shortPct) + '">' +
            (shortPct === null ? '—' : pct(shortPct, 1)) + '</span></div></div>' +
            '</div>';

        html += sub('ABC-АНАЛИЗ');
        html += '<div class="dr-abc-box"><div class="dr-abc-top">' +
            '<span class="dr-abc-big ' + abcClass(keg.ABC_Combined) + '">' +
            esc(keg.ABC_Combined) + '</span>' +
            '<span class="dr-abc-meta">' + pct(keg.RevenueSharePercent, 1) +
            ' от выручки разреза, накопленным итогом ' +
            pct(keg.RevenueCumulativePercent, 1) + '</span></div>' +
            '<div class="dr-abc-lines">' +
            abcLine('Выручка', keg.ABC_Revenue, ABC_TEXT.Revenue[keg.ABC_Revenue]) +
            abcLine('Наценка', keg.ABC_Markup, ABC_TEXT.Markup[keg.ABC_Markup] +
                (keg.MarkupPercent === null ? '' : ' (' + pct(keg.MarkupPercent, 1) + ')')) +
            abcLine('Маржа', keg.ABC_Margin, ABC_TEXT.Margin[keg.ABC_Margin] +
                ' (' + money(keg.TotalMargin) + ')') +
            '</div></div>';

        html += sub('XYZ — СТАБИЛЬНОСТЬ СПРОСА');
        html += '<div class="dr-cells three">' +
            cell('КАТЕГОРИЯ', keg.XYZ_Category || '—', keg.XYZ_Category ? '' : 'dash') +
            cell('КОЭФФ. ВАРИАЦИИ',
                keg.CoefficientOfVariation === null ? '—' : pct(keg.CoefficientOfVariation, 1),
                keg.CoefficientOfVariation === null ? 'dash' : '') +
            cell('НЕДЕЛЬ С ПРОДАЖАМИ', keg.WeeksWithSales) +
            '</div>';
        html += '<div class="dr-dr-note">' + xyzNote(keg) + '</div>';

        html += '</div>';
        openDrawer(html);
    }

    function abcLine(category, letter, text) {
        return '<div class="dr-abc-line">' +
            '<span class="dr-abc-ltr ' + abcClass(letter) + '">' + esc(letter) + '</span>' +
            '<span class="dr-abc-cat">' + esc(category) + '</span>' +
            '<span class="dr-abc-txt">' + esc(text || '') + '</span></div>';
    }

    function xyzNote(keg) {
        var tail = ' Считается по неделям на кране: стандартное отклонение недельных ' +
            'литров делится на среднее.';
        if (keg.XYZ_Category === 'X') {
            return 'Недельный объём предсказуем: разброс до 30%.' + tail;
        }
        if (keg.XYZ_Category === 'Y') {
            return 'Умеренный разброс: от 30% до 60% недельного объёма.' + tail;
        }
        if (keg.XYZ_Category === 'Z') {
            return 'Разброс свыше 60%: недельный объём может отличаться больше чем ' +
                'в полтора раза.' + tail;
        }
        if (keg.WeeksInPeriod < 3) {
            return 'Категория не присвоена: в периоде ' + keg.WeeksInPeriod +
                ' полных недель, нужно минимум 3.' + tail;
        }
        return 'Категория не присвоена: позиция была на кране ' + keg.WeeksWithSales +
            ' нед. из ' + keg.WeeksInPeriod + ', для оценки стабильности нужно минимум 3.' +
            tail;
    }

    function openBartender(name) {
        var list = (state.data && state.data.bartenders) || [];
        var person = null;
        for (var i = 0; i < list.length; i++) {
            if (list[i].Bartender === name) { person = list[i]; break; }
        }
        if (!person) return;

        var period = state.data.period || {};
        var html = '<div class="dr-dr-in">';
        html += drawerHead(person.Bartender,
            'поле «Авторизовал» в iiko · ' + rangeLabel(period.from, period.to),
            initials(person.Bartender));

        html += sub('НАЛИВ');
        html += '<div class="dr-cells">' +
            cell('ПРОЛИТО', num(person.TotalLiters) + ' л') +
            cell('ПОРЦИЙ', num(person.TotalPortions)) +
            cell('ДОЛЯ ПО ЛИТРАМ', pct(person.LitersSharePercent, 1)) +
            cell('ДОЛЯ В ВЫРУЧКЕ', pct(person.RevenueSharePercent, 1)) +
            cell('СРЕДНИЙ ОБЪЁМ ПОРЦИИ', num(person.AvgPortionLiters, 3) + ' л') +
            cell('КЕГОВ В ПРОДАЖАХ', person.KegsCount) +
            '</div>';

        html += sub('ДЕНЬГИ');
        html += '<div class="dr-cells two">' +
            cell('ВЫРУЧКА', money(person.TotalRevenue)) +
            cell('МАРЖА', money(person.TotalMargin)) +
            cell('НАЦЕНКА', person.MarkupPercent === null ? '—' : pct(person.MarkupPercent, 1),
                person.MarkupPercent === null ? 'dash' : '') +
            cell('ЦЕНА ЗА ЛИТР', money(person.PricePerLiter)) +
            '</div>';

        var kegs = person.kegs || [];
        if (kegs.length) {
            html += sub('ЧТО НАЛИВАЛ', 'клик — карточка кега');
            html += '<div class="dr-who-row is-head">' +
                '<span class="dr-th">КЕГ</span>' +
                '<span class="dr-th r">ЛИТРЫ</span>' +
                '<span class="dr-th r">ПОРЦ.</span>' +
                '<span class="dr-th r">ВЫРУЧКА</span>' +
                '<span class="dr-th r">ДОЛЯ</span></div>';
            var maxShare = kegs.reduce(function (acc, k) {
                return Math.max(acc, k.SharePercent || 0);
            }, 0);
            kegs.forEach(function (keg) {
                var width = maxShare > 0 ? Math.max(4, keg.SharePercent / maxShare * 100) : 0;
                html += '<div class="dr-who-row" data-keg="' + esc(keg.KegId) + '">' +
                    '<span class="dr-name">' + esc(keg.KegName) + '</span>' +
                    '<span class="dr-num strong">' + num(keg.Liters) + '</span>' +
                    '<span class="dr-num">' + num(keg.Portions) + '</span>' +
                    '<span class="dr-num">' + money(keg.Revenue) + '</span>' +
                    '<span class="dr-share"><span class="dr-bar dr-who-bar">' +
                    '<i style="width:' + width.toFixed(1) + '%"></i></span>' +
                    '<span class="dr-share-v">' + pct(keg.SharePercent, 1) +
                    '</span></span></div>';
            });
        }

        html += '</div>';
        openDrawer(html);
    }

    // ==================== события ====================

    function onTableClick(event) {
        var head = event.target.closest('.dr-th.s');
        if (head) {
            var table = head.closest('.dr-kegs') ? 'keg' : 'bt';
            var sort = table === 'keg' ? state.kegSort : state.btSort;
            var key = head.dataset.sort;
            if (sort.key === key) { sort.dir = -sort.dir; } else { sort.key = key; sort.dir = -1; }
            if (table === 'keg') { renderKegs(); } else { renderBartenders(); }
            return;
        }
        var row = event.target.closest('[data-keg],[data-bt]');
        if (!row) return;
        if (row.dataset.keg) { openKeg(row.dataset.keg); } else { openBartender(row.dataset.bt); }
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
            if (event.target.id === 'drCustom') {
                var from = document.getElementById('drFrom').value;
                var to = document.getElementById('drTo').value;
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
            if (state.data) renderKegs();
        });

        el.kegs.addEventListener('click', onTableClick);
        el.bts.addEventListener('click', onTableClick);
        el.losses.addEventListener('click', function (event) {
            var row = event.target.closest('[data-keg]');
            if (row) openKeg(row.dataset.keg);
        });
        el.drawer.addEventListener('click', function (event) {
            if (event.target.closest('[data-close]')) { closeDrawer(); return; }
            var row = event.target.closest('[data-keg],[data-bt]');
            if (!row) return;
            if (row.dataset.keg) { openKeg(row.dataset.keg); } else { openBartender(row.dataset.bt); }
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
            burger: document.getElementById('drBurger'),
            barBtn: document.getElementById('drBarBtn'),
            barMenu: document.getElementById('drBarMenu'),
            barLabel: document.getElementById('drBarLabel'),
            perBtn: document.getElementById('drPerBtn'),
            perMenu: document.getElementById('drPerMenu'),
            perLabel: document.getElementById('drPerLabel'),
            perHint: document.getElementById('drPerHint'),
            catch_: document.getElementById('drCatch'),
            run: document.getElementById('drRun'),
            runLabel: document.getElementById('drRunLabel'),
            spin: document.getElementById('drSpin'),
            context: document.getElementById('drContext'),
            updated: document.getElementById('drUpdated'),
            msg: document.getElementById('drMsg'),
            body: document.getElementById('drBody'),
            sum: document.getElementById('drSum'),
            kegCount: document.getElementById('drKegCount'),
            search: document.getElementById('drSearch'),
            kegs: document.getElementById('drKegs'),
            bts: document.getElementById('drBts'),
            balance: document.getElementById('drBalance'),
            losses: document.getElementById('drLosses'),
            diag: document.getElementById('drDiag'),
            drawer: document.getElementById('drDrawer'),
            backdrop: document.getElementById('drBackdrop')
        };

        var barsNode = document.getElementById('drBars');
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

    // Для тестов отрисовки (tests/test_draft_render.mjs): чистые функции и рендер
    // должны быть вызываемы вне браузера.
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { num: num, fixed: fixed, money: money, pct: pct, signed: signed, esc: esc,
                           plural: plural, presetRange: presetRange, lossTone: lossTone,
                           initials: initials };
    }
    if (typeof window !== 'undefined') {
        window.__draft = { state: state, render: render, openKeg: openKeg,
                           openBartender: openBartender, num: num, fixed: fixed,
                           money: money, pct: pct,
                           signed: signed, esc: esc, plural: plural, lossTone: lossTone,
                           initials: initials, presetRange: presetRange };
    }
})();

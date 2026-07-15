/* Вкладка «Товары»: анализ покупок (§9) и сочетаемость (§10). */

Guests.registerView('products', function (pane) {
    var G = Guests;
    var mode = pane.dataset.pmode || 'top';

    var MODES = [['top', 'Топ за период'], ['first', 'Первые покупки'],
                 ['repeat', 'Повторные'], ['trend', 'Динамика'], ['pairs', 'Сочетаемость']];

    function switcher() {
        return '<div class="sub-switch">' + MODES.map(function (m) {
            return '<button class="sub-btn' + (mode === m[0] ? ' active' : '') +
                '" data-pmode="' + m[0] + '">' + m[1] + '</button>';
        }).join('') + '</div>';
    }
    function bind() {
        pane.querySelectorAll('.sub-btn[data-pmode]').forEach(function (b) {
            b.addEventListener('click', function () {
                pane.dataset.pmode = b.dataset.pmode; render();
            });
        });
    }

    function renderTable(resp, title, helpKey, rankNote) {
        var items = resp.data.items;
        var html = switcher() + '<div class="gcard"><h3>' + title + G.helpIcon(helpKey) +
            '</h3><div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th>#</th><th>Товар</th><th class="num">Кол-во</th>' +
            '<th class="num">Выручка</th><th class="num">Гостей</th></tr></thead><tbody>';
        if (!items.length) html += '<tr><td colspan="5" class="dim">Нет данных за период</td></tr>';
        items.forEach(function (it, i) {
            html += '<tr><td class="dim">' + (i + 1) + '</td>' +
                '<td>' + G.esc(it.dish_name) + '</td>' +
                '<td class="num">' + G.fmtNum(it.amount) + '</td>' +
                '<td class="num">' + G.fmtMoney(it.revenue) + '</td>' +
                '<td class="num">' + G.fmtNum(it.guests) + '</td></tr>';
        });
        html += '</tbody></table></div>' +
            (rankNote ? '<div class="note-line">' + rankNote + '</div>' : '') + '</div>' +
            G.howBlock([helpKey, 'revenue']);
        pane.innerHTML = html;
        bind();
    }

    function render() {
        mode = pane.dataset.pmode || 'top';
        pane.innerHTML = '<div class="pane-loading">Загрузка…</div>';

        if (mode === 'pairs') {
            var scope = pane.dataset.pscope || 'lifetime';
            return G.api('/api/guests/product-pairs', { scope: scope }).then(function (resp) {
                var d = resp.data;
                var html = switcher() +
                    '<div class="gcard"><h3>Сочетаемость товаров' + G.helpIcon('pairs') + '</h3>' +
                    '<div class="sub-switch">' +
                    '<button class="sub-btn' + (scope === 'lifetime' ? ' active' : '') +
                    '" data-pscope="lifetime">За всю историю</button>' +
                    '<button class="sub-btn' + (scope === 'period' ? ' active' : '') +
                    '" data-pscope="period">За период</button></div>' +
                    '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
                    '<th>Пара</th><th class="num">Чеков вместе</th><th class="num">Поддержка</th>' +
                    '<th class="num">A→B</th><th class="num">B→A</th></tr></thead><tbody>';
                if (!d.pairs.length) html += '<tr><td colspan="5" class="dim">Нет данных</td></tr>';
                d.pairs.forEach(function (p) {
                    html += '<tr><td>' + G.esc(p.dish_a) + ' <span class="dim">+</span> ' +
                        G.esc(p.dish_b) + '</td>' +
                        '<td class="num"><b>' + G.fmtNum(p.checks) + '</b></td>' +
                        '<td class="num">' + G.fmtPct(p.support_pct) + '</td>' +
                        '<td class="num">' + G.fmtPct(p.confidence_a_to_b_pct) + '</td>' +
                        '<td class="num">' + G.fmtPct(p.confidence_b_to_a_pct) + '</td></tr>';
                });
                html += '</tbody></table></div>' +
                    '<div class="note-line">Чеков с 2+ разными позициями: ' +
                    G.fmtNum(d.checks_with_2plus_items) + '. A→B — доля чеков с товаром A, ' +
                    'где есть и B.</div></div>' + G.howBlock(['pairs', 'order']);
                pane.innerHTML = html;
                bind();
                pane.querySelectorAll('.sub-btn[data-pscope]').forEach(function (b) {
                    b.addEventListener('click', function () {
                        pane.dataset.pscope = b.dataset.pscope; render();
                    });
                });
            });
        }

        if (mode === 'trend') {
            return G.api('/api/guests/products', { mode: 'trend' }).then(function (resp) {
                var d = resp.data;
                var html = switcher() +
                    '<div class="gcard"><h3>Динамика популярности (топ-10 за 12 месяцев, шт)</h3>' +
                    '<div class="chart-box tall"><canvas id="trendChart"></canvas></div></div>' +
                    G.howBlock(['revenue']);
                pane.innerHTML = html;
                bind();
                if (!d.series.length) return;
                var pal = GCharts.palette();
                var colors = [pal.accent, pal.success, pal.warning, pal.danger, pal.text,
                              '#7C6BAF', '#4A90A4', '#B0803C', '#8A9A5B', '#A75D67'];
                GCharts.line('trendChart',
                    d.months.map(G.fmtMonth),
                    d.series.map(function (s, i) {
                        return { label: s.dish_name, data: s.points,
                                 borderColor: colors[i % colors.length],
                                 backgroundColor: colors[i % colors.length],
                                 tension: 0.3, pointRadius: 2 };
                    }), {});
            });
        }

        var titles = {
            top: ['Топ товаров за период', 'revenue', 'Сортировка по выручке.'],
            first: ['Первые покупки новых гостей', 'products_first',
                    'Что берут гости в день своего первого заказа (первый заказ в выбранном периоде).'],
            repeat: ['Повторные покупки', 'products_repeat',
                     'Позиции чеков после дня первого заказа гостя, внутри периода.']
        };
        var t = titles[mode];
        return G.api('/api/guests/products', { mode: mode }).then(function (resp) {
            renderTable(resp, t[0], t[1], t[2]);
        });
    }

    return render();
});

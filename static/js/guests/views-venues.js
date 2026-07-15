/* Вкладка «Точки» (ТЗ §11): первая/любимая точка, распределение, миграции. */

Guests.registerView('venues', function (pane) {
    var G = Guests;
    return G.api('/api/guests/venues').then(function (resp) {
        var d = resp.data;

        var html = '<div class="gcard-grid-2">';
        html += '<div class="gcard"><h3>Первая точка гостей' + G.helpIcon('first_store') +
            '</h3><div class="chart-box"><canvas id="firstStoreChart"></canvas></div></div>';
        html += '<div class="gcard"><h3>Любимая точка гостей' + G.helpIcon('favorite_store') +
            '</h3><div class="chart-box"><canvas id="favStoreChart"></canvas></div></div>';
        html += '</div>';

        html += '<div class="gcard"><h3>Распределение визитов по точкам</h3>' +
            '<div class="gtable-wrap"><table class="gtable"><thead><tr><th>Точка</th>' +
            '<th class="num">Визиты за период</th><th class="num">Доля</th>' +
            '<th class="num">Визиты за всю историю</th><th class="num">Доля</th>' +
            '</tr></thead><tbody>';
        var lifeByStore = {};
        d.distribution_lifetime.forEach(function (r) { lifeByStore[r.store] = r; });
        var seen = {};
        d.distribution_period.concat(d.distribution_lifetime).forEach(function (r) {
            if (seen[r.store]) return;
            seen[r.store] = true;
            var perRow = null;
            d.distribution_period.forEach(function (x) { if (x.store === r.store) perRow = x; });
            var lifeRow = lifeByStore[r.store];
            html += '<tr><td>' + G.esc(r.store_name) + '</td>' +
                '<td class="num">' + (perRow ? G.fmtNum(perRow.visits) : '—') + '</td>' +
                '<td class="num">' + (perRow ? G.fmtPct(perRow.share_pct) : '—') + '</td>' +
                '<td class="num">' + (lifeRow ? G.fmtNum(lifeRow.visits) : '—') + '</td>' +
                '<td class="num">' + (lifeRow ? G.fmtPct(lifeRow.share_pct) : '—') + '</td></tr>';
        });
        html += '</tbody></table></div></div>';

        html += '<div class="gcard"><h3>Миграции между точками' + G.helpIcon('migrations') +
            '</h3><div class="note-line" style="margin-bottom:10px">Гостей с визитами в 2+ бара: <b>' +
            G.fmtNum(d.multi_store_guests) + '</b> (' + G.fmtPct(d.multi_store_share_pct) +
            ' базы). Матрица: строка — первая точка, столбец — любимая.</div>';

        var stores = d.first_store.map(function (r) { return r.store; });
        var names = {};
        d.first_store.forEach(function (r) { names[r.store] = r.store_name; });
        html += '<div class="gtable-wrap"><table class="gtable"><thead><tr><th>Первая \\ Любимая</th>' +
            stores.map(function (s) { return '<th class="num">' + G.esc(names[s] || s) + '</th>'; }).join('') +
            '</tr></thead><tbody>';
        stores.forEach(function (fs) {
            var row = d.migration_matrix[fs] || {};
            var total = 0;
            stores.forEach(function (ts) { total += row[ts] || 0; });
            html += '<tr><td>' + G.esc(names[fs] || fs) + '</td>' +
                stores.map(function (ts) {
                    var n = row[ts] || 0;
                    var alpha = total ? Math.round(n / total * 55) : 0;
                    var diag = fs === ts ? ' dim' : '';
                    return '<td class="num' + diag + '" style="background: color-mix(in srgb, var(--accent) ' +
                        alpha + '%, transparent)">' + G.fmtNum(n) + '</td>';
                }).join('') + '</tr>';
        });
        html += '</tbody></table></div></div>';

        html += G.howBlock(['first_store', 'favorite_store', 'migrations', 'visit']);
        pane.innerHTML = html;

        var pal = GCharts.palette();
        GCharts.hbar('firstStoreChart',
            d.first_store.map(function (r) { return r.store_name; }),
            [{ label: 'Гостей', data: d.first_store.map(function (r) { return r.guests; }),
               backgroundColor: pal.accent, borderRadius: 4 }], {});
        GCharts.hbar('favStoreChart',
            d.favorite_store.map(function (r) { return r.store_name; }),
            [{ label: 'Гостей', data: d.favorite_store.map(function (r) { return r.guests; }),
               backgroundColor: pal.success, borderRadius: 4 }], {});
    });
});

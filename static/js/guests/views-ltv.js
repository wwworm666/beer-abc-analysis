/* Вкладка «LTV» (ТЗ §8): средний LTV, YTD-вариант, по точкам. */

Guests.registerView('ltv', function (pane) {
    var G = Guests;
    return G.api('/api/guests/ltv').then(function (resp) {
        var d = resp.data;
        var html = '<div class="metric-grid">' +
            G.metricCard('ltv', 'Средний LTV', G.fmtMoney(d.lifetime.avg_ltv),
                G.fmtNum(d.lifetime.guests) + ' гостей · ' + G.fmtMoney(d.lifetime.revenue) + ' всего') +
            G.metricCard('ytd_ltv', 'Выручка на гостя YTD',
                G.fmtMoney(d.ytd.avg_revenue_per_guest),
                G.fmtNum(d.ytd.guests) + ' гостей с визитами YTD') +
            '</div>';

        html += '<div class="gcard-grid-2">';
        html += '<div class="gcard"><h3>LTV по точкам' + G.helpIcon('first_store') +
            '</h3><div class="chart-box"><canvas id="ltvVenueChart"></canvas></div>' +
            '<div class="note-line">Гость закрепляется за точкой первого заказа.</div></div>';
        html += '<div class="gcard"><h3>Таблица по точкам</h3><div class="gtable-wrap">' +
            '<table class="gtable"><thead><tr><th>Точка</th><th class="num">Гостей</th>' +
            '<th class="num">LTV</th></tr></thead><tbody>';
        d.by_venue.forEach(function (v) {
            html += '<tr><td>' + G.esc(v.store_name) + '</td>' +
                '<td class="num">' + G.fmtNum(v.guests) + '</td>' +
                '<td class="num"><b>' + G.fmtMoney(v.ltv) + '</b></td></tr>';
        });
        html += '</tbody></table></div></div></div>';

        html += '<div class="note-line">LTV по когортам — на вкладке «Когорты» → «Доходы».</div>';
        html += G.howBlock(['ltv', 'ytd_ltv', 'first_store']);
        pane.innerHTML = html;

        GCharts.hbar('ltvVenueChart',
            d.by_venue.map(function (v) { return v.store_name; }),
            [{ label: 'LTV, ₽', data: d.by_venue.map(function (v) { return v.ltv; }),
               backgroundColor: GCharts.palette().accent, borderRadius: 4 }],
            {});
    });
});

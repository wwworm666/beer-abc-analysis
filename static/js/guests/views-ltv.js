/* Вкладка «LTV» (ТЗ §8): LTV на дату конца периода, из чего он состоит (средний чек ×
   чеков на гостя), ряд по периодам с разложением изменения, YTD и LTV по точкам. */

Guests.registerView('ltv', function (pane) {
    var G = Guests;

    function fmtRatio(n) {
        if (n === null || n === undefined) return '—';
        return n.toFixed(2).replace('.', ',');
    }
    // Изменение в рублях со знаком: «+614 ₽», «−400 ₽».
    function fmtSigned(n) {
        if (n === null || n === undefined) return '—';
        if (n > 0) return '+' + G.fmtMoney(n);
        if (n < 0) return '−' + G.fmtMoney(-n);
        return G.fmtMoney(0);
    }

    function seriesTable(rows, type) {
        var html = '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th>На конец периода</th><th class="num">LTV</th><th class="num">Изменение</th>' +
            '<th class="num">от чека</th><th class="num">от чеков на гостя</th>' +
            '<th class="num">Средний чек</th><th class="num">Чеков на гостя</th>' +
            '<th class="num">Гостей</th></tr></thead><tbody>';
        rows.slice().reverse().forEach(function (r) {
            if (r.state === 'future') return;
            var partial = r.state === 'partial';
            html += '<tr' + (partial ? ' class="row-partial"' : '') + '><td>' +
                G.periodShort(r.p_start, type) +
                (partial ? ' · по ' + G.fmtDate(r.asof).slice(0, 5) : '') + '</td>' +
                '<td class="num"><b>' + G.fmtMoney(r.ltv) + '</b></td>' +
                '<td class="num">' + fmtSigned(r.delta) + '</td>' +
                '<td class="num">' + fmtSigned(r.check_effect) + '</td>' +
                '<td class="num">' + fmtSigned(r.frequency_effect) + '</td>' +
                '<td class="num">' + G.fmtMoney(r.avg_check) + '</td>' +
                '<td class="num">' + fmtRatio(r.checks_per_guest) + '</td>' +
                '<td class="num">' + G.fmtNum(r.guests) + '</td></tr>';
        });
        return html + '</tbody></table></div>';
    }

    return G.api('/api/guests/ltv').then(function (resp) {
        var d = resp.data, meta = resp.meta;
        var type = meta.period_type;
        var life = d.lifetime;
        var series = d.series || [];
        // Посчитано по бару: LTV гостя в этом баре. Сравнение баров между собой
        // (LTV по точке первого заказа) есть только у всей сети — сервер отдаёт
        // пустой by_venue, как профиль баров на «Фасовке» и «Кухне».
        var byBar = !!meta.venue;
        var html = '<div class="metric-grid">' +
            G.metricCard('ltv', 'LTV на ' + G.fmtDate(d.asof), G.fmtMoney(life.avg_ltv),
                G.fmtNum(life.guests) + ' гостей · ' + G.fmtMoney(life.revenue) + ' всего') +
            G.metricCard('ltv_structure', 'Средний чек', G.fmtMoney(life.avg_check),
                'выручка / ' + G.fmtNum(life.checks) + ' чеков') +
            G.metricCard('ltv_structure', 'Чеков на гостя', fmtRatio(life.checks_per_guest),
                'LTV = средний чек × чеков на гостя') +
            G.metricCard('ytd_ltv', 'Выручка на гостя YTD',
                G.fmtMoney(d.ytd.avg_revenue_per_guest),
                G.fmtNum(d.ytd.guests) + ' гостей с визитами YTD') +
            '</div>' +
            G.howBlock(['ltv', 'ltv_structure', 'ytd_ltv'], meta);

        if (series.length) {
            html += '<div class="gcard"><h3>LTV по периодам' + G.helpIcon('ltv_change') +
                '</h3><div class="chart-box"><canvas id="ltvTrendChart"></canvas></div>' +
                seriesTable(series, type) + G.howBlock(['ltv_change'], meta) + '</div>';
        }

        if (byBar) {
            html += '<div class="note-line">Сравнение баров по LTV — при выборе «Все бары».</div>';
        } else {
            html += '<div class="gcard-grid-2">';
            html += '<div class="gcard"><h3>LTV по точкам' + G.helpIcon('ltv_venue') +
                '</h3><div class="chart-box"><canvas id="ltvVenueChart"></canvas></div>' +
                G.howBlock(['ltv_venue', 'first_store'], meta) + '</div>';
            html += '<div class="gcard"><h3>Таблица по точкам</h3><div class="gtable-wrap">' +
                '<table class="gtable"><thead><tr><th>Точка</th><th class="num">Гостей</th>' +
                '<th class="num">LTV</th></tr></thead><tbody>';
            d.by_venue.forEach(function (v) {
                html += '<tr><td>' + G.esc(v.store_name) + '</td>' +
                    '<td class="num">' + G.fmtNum(v.guests) + '</td>' +
                    '<td class="num"><b>' + G.fmtMoney(v.ltv) + '</b></td></tr>';
            });
            html += '</tbody></table></div></div></div>';
        }

        html += '<div class="note-line">LTV по когортам — на вкладке «Когорты» → «Доходы».</div>';
        pane.innerHTML = html;

        var pal = GCharts.palette();
        if (series.length) {
            GCharts.line('ltvTrendChart',
                series.map(function (r) { return G.periodShort(r.p_start, type); }),
                [{ label: 'LTV, ₽', data: series.map(function (r) { return r.ltv; }),
                   borderColor: pal.accent, backgroundColor: pal.accent, tension: 0.3,
                   pointRadius: 2 }],
                { beginAtZero: true });
        }
        if (byBar) return;
        GCharts.hbar('ltvVenueChart',
            d.by_venue.map(function (v) { return v.store_name; }),
            [{ label: 'LTV, ₽', data: d.by_venue.map(function (v) { return v.ltv; }),
               backgroundColor: pal.accent, borderRadius: 4 }],
            {});
    });
});

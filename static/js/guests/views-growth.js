/* Вкладка «Рост и динамика» (ТЗ §1 + §13): рост базы и помесячная динамика. */

Guests.registerView('growth', function (pane) {
    var G = Guests;
    return Promise.all([
        G.api('/api/guests/base-growth'),
        G.api('/api/guests/base-dynamics', { months: 24 })
    ]).then(function (results) {
        var growth = results[0].data;
        var dyn = results[1].data;
        var p = growth.period, y = growth.ytd;

        var html = '<div class="metric-grid">' +
            G.metricCard('registrations', 'Регистрации за период',
                G.fmtNum(p.registrations), 'YTD: ' + G.fmtNum(y.registrations)) +
            G.metricCard('first_orders', 'Первые заказы за период',
                G.fmtNum(p.first_orders), 'YTD: ' + G.fmtNum(y.first_orders)) +
            G.metricCard('conversion', 'Конверсия в заказ',
                p.conversion_pct === null ? '—' : G.fmtPct(p.conversion_pct),
                'YTD: ' + (y.conversion_pct === null ? '—' : G.fmtPct(y.conversion_pct))) +
            G.metricCard('avg_days_to_first', 'Дней до первого заказа',
                p.avg_days_to_first_order === null ? '—'
                    : String(p.avg_days_to_first_order).replace('.', ','),
                'YTD: ' + (y.avg_days_to_first_order === null ? '—'
                    : String(y.avg_days_to_first_order).replace('.', ','))) +
            G.metricCard('base_size', 'Размер базы', G.fmtNum(growth.lifetime.base_size),
                'все зарегистрированные с чеком') +
            '</div>';

        html += '<div class="gcard"><h3>Динамика базы по месяцам' +
            G.helpIcon('base_dynamics') +
            '</h3><div class="chart-box tall"><canvas id="dynChart"></canvas></div></div>';

        html += '<div class="gcard"><h3>Таблица динамики</h3><div class="gtable-wrap">' +
            '<table class="gtable"><thead><tr><th>Месяц</th>' +
            '<th class="num">Активные на начало</th><th class="num">Новые</th>' +
            '<th class="num">Реактивированные</th><th class="num">Ушедшие</th>' +
            '<th class="num">Активные на конец</th></tr></thead><tbody>';
        dyn.months.slice().reverse().forEach(function (m) {
            html += '<tr><td>' + G.fmtMonth(m.month) + '</td>' +
                '<td class="num">' + G.fmtNum(m.active_start) + '</td>' +
                '<td class="num delta-up">+' + G.fmtNum(m.new) + '</td>' +
                '<td class="num">+' + G.fmtNum(m.reactivated) + '</td>' +
                '<td class="num delta-down">-' + G.fmtNum(m.churned) + '</td>' +
                '<td class="num"><b>' + G.fmtNum(m.active_end) + '</b></td></tr>';
        });
        html += '</tbody></table></div></div>';

        html += G.howBlock(['registrations', 'first_orders', 'conversion',
                            'avg_days_to_first', 'base_dynamics']);
        pane.innerHTML = html;

        var pal = GCharts.palette();
        var labels = dyn.months.map(function (m) { return G.fmtMonth(m.month); });
        GCharts.bar('dynChart', labels, [
            { label: 'Новые', data: dyn.months.map(function (m) { return m.new; }),
              backgroundColor: pal.accent, stack: 'flow' },
            { label: 'Реактивированные', data: dyn.months.map(function (m) { return m.reactivated; }),
              backgroundColor: pal.success, stack: 'flow' },
            { label: 'Ушедшие', data: dyn.months.map(function (m) { return -m.churned; }),
              backgroundColor: pal.danger, stack: 'flow' },
            { label: 'Активные на конец', type: 'line', data: dyn.months.map(function (m) { return m.active_end; }),
              borderColor: pal.text, backgroundColor: pal.text, tension: 0.3, pointRadius: 2, stack: 'line' }
        ], { stacked: true });
    });
});

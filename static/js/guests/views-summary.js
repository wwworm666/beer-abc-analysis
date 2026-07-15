/* Вкладка «Сводка» (ТЗ §14): ключевые показатели базы гостей. */

Guests.registerView('summary', function (pane) {
    var G = Guests;
    return G.api('/api/guests/summary').then(function (resp) {
        var d = resp.data, meta = resp.meta;
        var conv = d.conversion_pct === null ? '—' : G.fmtPct(d.conversion_pct);
        var html = '<div class="metric-grid">' +
            G.metricCard('base_size', 'База гостей', G.fmtNum(d.base_size), 'за всю историю') +
            G.metricCard('active_guests', 'Активные', G.fmtNum(d.active_guests),
                'визит за 30 дней на ' + G.fmtDate(meta.asof)) +
            G.metricCard('registrations', 'Новые регистрации', G.fmtNum(d.registrations),
                'YTD: ' + G.fmtNum(d.registrations_ytd)) +
            G.metricCard('first_orders', 'Первые заказы', G.fmtNum(d.first_orders),
                'YTD: ' + G.fmtNum(d.first_orders_ytd)) +
            G.metricCard('conversion', 'Конверсия в заказ', conv,
                d.conversion_pct === null ? 'нет данных о регистрации' : 'справочно: источник видит только купивших') +
            G.metricCard('avg_frequency', 'Средняя частота', String(d.avg_frequency).replace('.', ','),
                'визитов на гостя за период') +
            G.metricCard('avg_check', 'Средний чек', G.fmtMoney(d.avg_check),
                'YTD: ' + G.fmtMoney(d.avg_check_ytd)) +
            G.metricCard('ltv', 'Средний LTV', G.fmtMoney(d.avg_ltv), 'на гостя за всю историю') +
            G.metricCard('revenue', 'Выручка по картам', G.fmtMoney(d.revenue_period),
                G.fmtNum(d.orders_period) + ' чеков за период') +
            '</div>';

        html += '<div class="gcard-grid-2">';
        html += '<div class="gcard"><h3>Активность базы' + G.helpIcon('activity_status') +
                '</h3><div class="chart-box"><canvas id="sumActivityChart"></canvas></div></div>';
        html += '<div class="gcard"><h3>Регистраций на точку' + G.helpIcon('regs_by_store') +
                '</h3><div class="gtable-wrap"><table class="gtable"><thead><tr>' +
                '<th>Точка</th><th class="num">Регистраций за период</th></tr></thead><tbody>';
        if (d.registrations_by_store.length === 0) {
            html += '<tr><td colspan="2" class="dim">Нет регистраций за период</td></tr>';
        }
        d.registrations_by_store.forEach(function (r) {
            html += '<tr><td>' + G.esc(r.store_name) + '</td><td class="num">' +
                G.fmtNum(r.count) + '</td></tr>';
        });
        html += '</tbody></table></div></div></div>';

        html += G.howBlock(['base_size', 'active_guests', 'registrations', 'first_orders',
                            'conversion', 'avg_frequency', 'avg_check', 'ltv', 'revenue',
                            'visit', 'order', 'coverage']);
        pane.innerHTML = html;

        var p = GCharts.palette();
        var segNames = { active: 'Active (до 30 дн)', sleeping: 'Sleeping (31-90)',
                         at_risk: 'At Risk (91-180)', lost: 'Lost (180+)' };
        GCharts.doughnut('sumActivityChart',
            d.activity_segments.map(function (s) { return segNames[s.segment] || s.segment; }),
            d.activity_segments.map(function (s) { return s.count; }),
            [p.success, p.warning, p.accent, p.danger]);
    });
});

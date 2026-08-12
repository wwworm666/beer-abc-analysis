/* Вкладка «Сводка» (ТЗ §14): ключевые показатели базы гостей. */

Guests.registerView('summary', function (pane) {
    var G = Guests;
    return G.api('/api/guests/summary').then(function (resp) {
        var d = resp.data, meta = resp.meta;
        var nv = d.never || {};

        // Регистрации и конверсия: если срез Orderia есть, знаменатель полный —
        // купившие плюс не купившие. Если нет, остаётся прежняя картина, где
        // источник видит только купивших, и конверсия обречена быть ~100%.
        var regsValue, regsSub, conv, convSub, neverValue, neverSub;
        if (nv.available) {
            regsValue = G.fmtNum(nv.registered_total);
            regsSub = 'купили ' + G.fmtNum(nv.bought) + ' · не купили ' + G.fmtNum(nv.never_period);
            conv = G.fmtPct(nv.conversion_pct);
            convSub = G.fmtNum(nv.bought) + ' из ' + G.fmtNum(nv.registered_total) + ' зарегистрированных';
            neverValue = G.fmtNum(nv.never_period);
            neverSub = 'всего в базе ' + G.fmtNum(nv.never_total);
        } else {
            regsValue = G.fmtNum(d.registrations);
            regsSub = 'только купившие · YTD: ' + G.fmtNum(d.registrations_ytd);
            conv = d.conversion_pct === null ? '—' : G.fmtPct(d.conversion_pct);
            convSub = d.conversion_pct === null
                ? 'нет данных о регистрации'
                : 'справочно: источник видит только купивших';
            neverValue = '—';
            neverSub = nv.source_status === 'error'
                ? 'данные Orderia недоступны'
                : (nv.source_status === 'never_run'
                    ? 'интеграция с Orderia не настроена'
                    : 'период старше данных Orderia');
        }

        var html = '<div class="metric-grid">' +
            G.metricCard('base_size', 'База гостей', G.fmtNum(d.base_size), 'за всю историю') +
            G.metricCard('active_guests', 'Активные', G.fmtNum(d.active_guests),
                'визит за 30 дней на ' + G.fmtDate(meta.asof)) +
            G.metricCard('registrations', 'Новые регистрации', regsValue, regsSub) +
            G.metricCard('first_orders', 'Первые заказы', G.fmtNum(d.first_orders),
                'YTD: ' + G.fmtNum(d.first_orders_ytd)) +
            G.metricCard('never_buyers', 'Не купили ни разу', neverValue, neverSub) +
            G.metricCard(nv.available ? 'never_conversion' : 'conversion',
                'Конверсия в заказ', conv, convSub) +
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
                            'never_buyers', nv.available ? 'never_conversion' : 'conversion',
                            'avg_frequency', 'avg_check', 'ltv', 'revenue',
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

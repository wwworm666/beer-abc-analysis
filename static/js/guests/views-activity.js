/* Вкладка «Активность и частота» (ТЗ §3 + §4). */

Guests.registerView('activity', function (pane) {
    var G = Guests;
    return Promise.all([
        G.api('/api/guests/activity'),
        G.api('/api/guests/frequency')
    ]).then(function (results) {
        var act = results[0].data;
        var freq = results[1].data;
        var segNames = { active: 'Active', sleeping: 'Sleeping', at_risk: 'At Risk', lost: 'Lost' };
        var segDesc = { active: 'визит за 30 дней', sleeping: '31-90 дней',
                        at_risk: '91-180 дней', lost: 'более 180 дней' };

        var html = '<div class="gcard"><h3>Статусы базы на ' + G.fmtDate(act.asof) +
            G.helpIcon('activity_status') + '</h3><div class="gtable-wrap">' +
            '<table class="gtable"><thead><tr><th>Сегмент</th><th>Определение</th>' +
            '<th class="num">Гостей</th><th class="num">Доля</th>' +
            '<th class="num">Прошлый период</th><th class="num">Изменение</th></tr></thead><tbody>';
        act.segments.forEach(function (s) {
            var deltaCls = s.delta > 0 ? 'delta-up' : (s.delta < 0 ? 'delta-down' : 'dim');
            if (s.segment === 'lost' || s.segment === 'at_risk') {
                deltaCls = s.delta > 0 ? 'delta-down' : (s.delta < 0 ? 'delta-up' : 'dim');
            }
            html += '<tr><td><span class="gbadge ' + s.segment + '">' +
                segNames[s.segment] + '</span></td>' +
                '<td class="dim">' + segDesc[s.segment] + '</td>' +
                '<td class="num"><b>' + G.fmtNum(s.count) + '</b></td>' +
                '<td class="num">' + G.fmtPct(s.share_pct) + '</td>' +
                '<td class="num dim">' + G.fmtNum(s.prev_count) + '</td>' +
                '<td class="num ' + deltaCls + '">' + (s.delta > 0 ? '+' : '') +
                G.fmtNum(s.delta) + '</td></tr>';
        });
        html += '</tbody></table></div>' +
            '<div class="note-line">Население: гости с первым заказом не позже даты среза. ' +
            'Сравнение — с тем же расчётом на конец предыдущего периода (' +
            G.fmtDate(act.prev_asof) + ').</div></div>';

        html += '<div class="gcard-grid-2">';
        html += '<div class="gcard"><h3>Частота визитов за период' + G.helpIcon('avg_frequency') +
            '</h3><div class="chart-box"><canvas id="freqChart"></canvas></div>' +
            '<div class="note-line">Гостей с визитами за период: <b>' +
            G.fmtNum(freq.period.guests_with_visits) + '</b> · визитов: <b>' +
            G.fmtNum(freq.period.total_visits) + '</b> · средняя частота: <b>' +
            String(freq.period.avg_visits_per_guest).replace('.', ',') + '</b></div></div>';

        html += '<div class="gcard"><h3>Частота YTD</h3><div class="gtable-wrap">' +
            '<table class="gtable"><thead><tr><th>Сегмент</th><th class="num">Гостей</th>' +
            '<th class="num">Доля</th></tr></thead><tbody>';
        freq.ytd.segments.forEach(function (s) {
            html += '<tr><td>' + s.segment + ' ' +
                (s.segment === '1' ? 'визит' : 'визитов') + '</td>' +
                '<td class="num">' + G.fmtNum(s.count) + '</td>' +
                '<td class="num">' + G.fmtPct(s.share_pct) + '</td></tr>';
        });
        html += '</tbody></table>' +
            '<div class="note-line">С начала года: гостей с визитами <b>' +
            G.fmtNum(freq.ytd.guests_with_visits) + '</b>, средняя частота <b>' +
            String(freq.ytd.avg_visits_per_guest).replace('.', ',') + '</b>.</div></div></div>';

        html += G.howBlock(['activity_status', 'visit', 'avg_frequency']);
        pane.innerHTML = html;

        var pal = GCharts.palette();
        GCharts.bar('freqChart',
            freq.period.segments.map(function (s) { return s.segment + (s.segment === '1' ? ' визит' : ' визитов'); }),
            [{ label: 'Гостей', data: freq.period.segments.map(function (s) { return s.count; }),
               backgroundColor: pal.accent, borderRadius: 6 }],
            {});
    });
});

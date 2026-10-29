/* Вкладка «Рост базы» (ТЗ §1): регистрации, первые заказы, конверсия — приток гостей.
   Баланс базы (новые, вернувшиеся, ушедшие) с 2026-10-27 — на вкладке «Отток» (§17). */

Guests.registerView('growth', function (pane) {
    var G = Guests;
    return G.api('/api/guests/base-growth').then(function (resp) {
        var growth = resp.data;
        var meta = resp.meta;
        var p = growth.period, y = growth.ytd;
        // Посчитано по бару: подписи говорят, к чему привязаны регистрации и
        // первые заказы — иначе число бара читается как «сетевое».
        var byBar = !!meta.venue;

        var html = '<div class="metric-grid">' +
            G.metricCard('registrations', 'Регистрации за период',
                G.fmtNum(p.registrations),
                (byBar ? 'за баром первой покупки · ' : '') + 'YTD: ' + G.fmtNum(y.registrations)) +
            G.metricCard('first_orders', 'Новые гости за период',
                G.fmtNum(p.first_orders),
                (byBar ? 'первый чек в баре · ' : '') + 'YTD: ' + G.fmtNum(y.first_orders)) +
            G.metricCard('conversion', 'Конверсия в заказ',
                p.conversion_pct === null ? '—' : G.fmtPct(p.conversion_pct),
                'YTD: ' + (y.conversion_pct === null ? '—' : G.fmtPct(y.conversion_pct))) +
            G.metricCard('avg_days_to_first', 'Дней до первого заказа',
                p.avg_days_to_first_order === null ? '—'
                    : String(p.avg_days_to_first_order).replace('.', ','),
                'YTD: ' + (y.avg_days_to_first_order === null ? '—'
                    : String(y.avg_days_to_first_order).replace('.', ','))) +
            G.metricCard('base_size', 'Размер базы', G.fmtNum(growth.lifetime.base_size),
                (byBar ? 'все, у кого был чек в баре' : 'купили хоть раз') + ' — на ' +
                G.fmtDate(meta.asof)) +
            '</div>';

        html += '<div class="note-line">Сколько гостей база теряет и сколько возвращается — ' +
            'на вкладке «Отток».</div>';

        html += G.howBlock(['registrations', 'first_orders', 'conversion',
                            'avg_days_to_first'], meta);
        pane.innerHTML = html;
    });
});

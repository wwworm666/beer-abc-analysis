/* Вкладка «Не купившие» (§15): карты Orderia без единого чека.

   Единственная вкладка раздела, где источник — не iiko: OLAP видит гостя только
   с первой покупкой, поэтому слой «карта выдана, покупок нет» приходит из
   внешней системы лояльности. Список сверяется с витриной, ложные срабатывания
   счётчика Orderia показываются отдельно и в выгрузку не попадают. */

Guests.registerView('never', function (pane) {
    var G = Guests;
    return G.api('/api/guests/never').then(function (resp) {
        var d = resp.data;
        var t = d.totals;

        // Источник не настроен или ни разу не отвечал — показываем причину,
        // а не пустые нули: пустой отчёт выглядел бы как «все покупают».
        if (!t.reported && d.source.status !== 'ok') {
            var reason = d.source.status === 'never_run'
                ? 'Интеграция с Orderia не настроена: нет ORDERIA_LOGIN / ORDERIA_PASSWORD в окружении.'
                : 'Последняя попытка обновления не удалась: ' + G.esc(d.source.error || 'причина неизвестна');
            pane.innerHTML = '<div class="gcard"><h3>Зарегистрировались, но не купили' +
                G.helpIcon('never_buyers') + '</h3><div class="note-line">' + reason +
                '</div></div>' + G.howBlock(['never_buyers']);
            return;
        }

        var fetched = d.source.fetched_at
            ? d.source.fetched_at.replace('T', ' ').slice(0, 16) : '—';

        var html = '<div class="metric-grid">';
        html += G.metricCard('never_buyers', 'Не купили ни разу', G.fmtNum(t.confirmed),
            'подтверждено витриной');
        html += G.metricCard('never_false_positive', 'Ложных срабатываний',
            G.fmtNum(t.false_positives),
            t.false_positives ? 'за ними ' + G.fmtMoney(t.fp_revenue) + ' выручки' : 'нет');
        html += G.metricCard('never_reach', 'Есть Telegram', G.fmtNum(t.reachable_telegram),
            t.confirmed ? G.fmtPct(100 * t.reachable_telegram / t.confirmed) + ' от подтверждённых' : '—');
        html += G.metricCard('never_conversion', 'Конверсия за период',
            d.period.conversion_available ? G.fmtPct(d.period.conversion_pct) : '—',
            d.period.conversion_available
                ? G.fmtNum(d.period.bought) + ' из ' + G.fmtNum(d.period.registered_total) + ' зарегистрированных'
                : 'период старше данных Orderia');
        html += '</div>';

        // --- динамика по месяцу регистрации ---
        html += '<div class="gcard"><h3>Когда зарегистрировались те, кто так и не купил' +
            G.helpIcon('never_buyers') + '</h3>' +
            '<div class="chart-box"><canvas id="neverChart"></canvas></div>' +
            '<div class="note-line">Срез Orderia от ' + G.esc(fetched) +
            ' · всего в источнике ' + G.fmtNum(t.reported) + ' карт' +
            (t.junk ? ' · отброшено мусорных записей: ' + G.fmtNum(t.junk) : '') +
            (d.coverage.from ? ' · данные с ' + G.fmtDate(d.coverage.from) : '') +
            '</div></div>';

        // --- ложные срабатывания ---
        if (d.false_positives.length) {
            html += '<div class="gcard"><h3>Числятся непокупавшими, но чеки есть' +
                G.helpIcon('never_false_positive') + '</h3>' +
                '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
                '<th>Карта в Orderia</th><th>Причина</th><th>Карта в iiko</th>' +
                '<th class="num">Чеков</th><th class="num">Выручка</th>' +
                '<th>Последняя покупка</th></tr></thead><tbody>';
            d.false_positives.forEach(function (f) {
                var kind = f.kind === 'same_card'
                    ? 'счётчик Orderia не сработал'
                    : 'покупки по другой карте';
                html += '<tr><td>' + G.esc(f.card_number) + '</td>' +
                    '<td class="dim">' + kind + '</td>' +
                    '<td class="dim">' + G.esc(f.iiko_card) + '</td>' +
                    '<td class="num">' + G.fmtNum(f.orders) + '</td>' +
                    '<td class="num">' + G.fmtMoney(f.revenue) + '</td>' +
                    '<td>' + G.fmtDate(f.last_visit_date) + '</td></tr>';
            });
            html += '</tbody></table></div>' +
                '<div class="note-line">Всего ' + G.fmtNum(t.false_positives) +
                ' (тот же номер карты: ' + G.fmtNum(t.fp_same_card) +
                ', другая карта: ' + G.fmtNum(t.fp_other_card) +
                '). Эти карты исключены из счётчика «не купили ни разу» и из выгрузки.</div></div>';
        }

        // --- выгрузка для реактивации ---
        html += '<div class="gcard"><h3>Выгрузка для реактивации</h3>' +
            '<div class="guest-search"><a class="sync-btn" href="/api/guests/never?period_type=' +
            G.state.periodType + '&anchor=' + resp.meta.p_end + '&export=csv">Скачать CSV</a></div>' +
            '<div class="note-line">В файл попадут только подтверждённые витриной карты (' +
            G.fmtNum(t.confirmed) + ') — без мусорных записей и без тех, кто на самом деле покупает. ' +
            'Колонки: карта, имя, телефон, Telegram ID, дата регистрации, бонусный баланс.</div></div>';

        html += G.howBlock(['never_buyers', 'never_false_positive', 'never_conversion', 'never_reach']);
        pane.innerHTML = html;

        var pal = GCharts.palette();
        GCharts.bar('neverChart',
            d.by_month.map(function (m) { return G.fmtMonth(m.month); }),
            [{ label: 'Зарегистрировались и не купили',
               data: d.by_month.map(function (m) { return m.count; }),
               backgroundColor: pal.warning, borderRadius: 6 }],
            {});
    });
});

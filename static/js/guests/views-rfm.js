/* Вкладка «RFM» (ТЗ §7): сегменты, список гостей, CSV-экспорт. */

Guests.registerView('rfm', function (pane) {
    var G = Guests;
    return G.api('/api/guests/rfm').then(function (resp) {
        var d = resp.data;
        var segTitles = {
            CHAMPIONS: 'Чемпионы', LOYAL: 'Лояльные', NEW: 'Новички',
            AT_RISK: 'Под риском', CHURNED: 'Уходящие', POTENTIAL: 'Потенциальные'
        };

        var html = '<div class="metric-grid">';
        d.segments.forEach(function (s) {
            html += G.metricCard('rfm', segTitles[s.segment] || s.segment,
                G.fmtNum(s.count),
                G.fmtPct(s.share_pct) + ' · ' + G.fmtMoney(s.revenue));
        });
        html += '</div>';

        html += '<div class="gcard"><h3>Гости в окне 12 месяцев (' +
            G.fmtNum(d.total_guests) + ')' + G.helpIcon('rfm') +
            '</h3><div class="guest-search"><input type="text" id="rfmFilter" ' +
            'placeholder="Фильтр по имени, телефону, сегменту"><a class="sync-btn" ' +
            'href="/api/guests/rfm?period_type=' + G.state.periodType +
            '&anchor=' + resp.meta.p_end + '&export=csv">Скачать CSV</a></div>' +
            '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th>Гость</th><th>Телефон</th><th class="num">Дней с визита</th>' +
            '<th class="num">Визитов (12 мес)</th><th class="num">Выручка (12 мес)</th>' +
            '<th>Сегмент</th></tr></thead><tbody id="rfmTbody"></tbody></table></div>' +
            '<div class="note-line" id="rfmMore"></div>' +
            '<div class="note-line">Пороги R: до ' + d.r_thresholds.join(' / ') +
            ' дней. Пороги F (визитов за окно 12 мес): ' + d.f_thresholds.join(' / ') +
            ' — постоянный (5+ в неделю) / частый (2+ в неделю) / раз в неделю / раз в месяц.</div></div>';

        html += G.howBlock(['rfm', 'visit', 'revenue']);
        pane.innerHTML = html;

        var PAGE = 50;
        var input = document.getElementById('rfmFilter');
        var tbody = document.getElementById('rfmTbody');
        var more = document.getElementById('rfmMore');

        function rowsFiltered() {
            var q = (input.value || '').trim().toLowerCase();
            if (!q) return d.guests;
            return d.guests.filter(function (g) {
                return (g.name || '').toLowerCase().indexOf(q) >= 0 ||
                       (g.phone || '').indexOf(q) >= 0 ||
                       (g.card_number || '').indexOf(q) >= 0 ||
                       (segTitles[g.segment] || g.segment).toLowerCase().indexOf(q) >= 0;
            });
        }
        function renderRows() {
            var rows = rowsFiltered();
            tbody.innerHTML = rows.slice(0, PAGE).map(function (g) {
                return '<tr><td>' + (G.esc(g.name) || '<span class="dim">без имени</span>') + '</td>' +
                    '<td class="dim">' + G.esc(g.phone) + '</td>' +
                    '<td class="num">' + G.fmtNum(g.recency_days) + '</td>' +
                    '<td class="num">' + G.fmtNum(g.frequency) + '</td>' +
                    '<td class="num">' + G.fmtMoney(g.monetary) + '</td>' +
                    '<td><span class="gbadge">' + (segTitles[g.segment] || g.segment) +
                    '</span></td></tr>';
            }).join('');
            more.textContent = rows.length > PAGE
                ? 'Показаны первые ' + PAGE + ' из ' + rows.length + ' — уточните фильтр или скачайте CSV.'
                : 'Гостей: ' + rows.length + '.';
        }
        input.addEventListener('input', renderRows);
        renderRows();
    });
});

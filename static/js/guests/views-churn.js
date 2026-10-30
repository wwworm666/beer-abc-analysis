/* Вкладка «Отток» (§17): гость жив, пока с последнего визита прошло не больше X дней.
   Отток за период, баланс базы по периодам и кто уходит. Порог X — подпереключатель
   вкладки (pane.dataset, как у «Когорт»); сервер считает все пороги разом и отдаёт один.
   С 2026-10-30 (статья Unisender о churn rate): ущерб от оттока в рублях, «Стали ходить
   реже» (скрытый отток, поимённо — /api/guests/churn-slowing) и подсказка к порогу. */

Guests.registerView('churn', function (pane) {
    var G = Guests;
    var DEFAULT_DAYS = 30;              // зеркало CHURN_DEAD_DAYS_DEFAULT (решение владельца)
    var CHOICES = [30, 60, 90, 180];    // зеркало CHURN_DEAD_DAYS_CHOICES; ответ несёт data.choices
    // Строк списка «Стали ходить реже» на экране — самые ценные по выручке; весь список — CSV.
    var SLOWING_LIMIT = 50;
    var LEAVER_NAMES = {
        '1': '1 визит — пришёл и не вернулся',
        '2-3': '2–3 визита',
        '4-8': '4–8 визитов',
        '9+': '9 визитов и больше'
    };

    function deadDays() {
        var v = parseInt(pane.dataset.deadDays || String(DEFAULT_DAYS), 10);
        return CHOICES.indexOf(v) >= 0 ? v : DEFAULT_DAYS;
    }

    function shortLabel(row, type) {
        return G.periodShort(row.p_start, type);
    }

    function activeIf(on) {
        return on ? ' active' : '';
    }

    function switcher(current, choices) {
        return '<div class="sub-switch"><span class="sub-label">Ушёл, если нет визита:</span>' +
            choices.map(function (x) {
                return '<button class="sub-btn' + activeIf(x === current) +
                    '" data-days="' + x + '">' + x + ' дней</button>';
            }).join('') + '</div>';
    }

    // Подсказка к порогу: какая доля возвратов за год случилась позже каждого порога —
    // столько «ушедших» этот порог потом увидит в «Вернулись после паузы».
    function thresholdHint(gaps, current, meta) {
        if (!gaps || !gaps.returns) return '';
        var parts = gaps.later_than.map(function (r) {
            var text = r.days + ' дн — ' + G.fmtPct(r.pct);
            return r.days === current ? '<b>' + text + '</b>' : text;
        });
        var days = {};
        gaps.percentiles.forEach(function (p) { days[p.pct] = p.days; });
        return '<div class="note-line churn-hint">Возвратов позже порога: ' + parts.join(' · ') +
            '. Половина гостей возвращается за ' + G.fmtNum(days[50]) + ' дн, 9 из 10 — за ' +
            G.fmtNum(days[90]) + ' дн.' + G.helpIcon('churn_threshold') + '</div>' +
            G.howBlock(['churn_threshold'], meta);
    }

    function leftCount(row) {
        return row.died + row.new_died;
    }

    function tiles(d, type) {
        var p = d.period;
        var prev = null;
        for (var i = d.series.length - 2; i >= 0; i--) {
            if (d.series[i].state === 'complete') { prev = d.series[i]; break; }
        }
        function prevNum(key) {
            return prev ? shortLabel(prev, type) + ': ' + G.fmtNum(prev[key]) : '';
        }
        var one = d.leavers.buckets.length ? d.leavers.buckets[0].count : 0;
        var churnSub = 'ушли ' + G.fmtNum(p.died) + ' из ' + G.fmtNum(p.start_alive) +
            ' живых на начало' +
            (prev ? ' · ' + shortLabel(prev, type) + ': ' + G.fmtPct(prev.churn_pct) : '');
        var slowingSub = p.slowing_base
            ? 'из ' + G.fmtNum(p.slowing_base) + ' ходивших раз в месяц и чаще (' +
              G.fmtPct(p.slowing_pct) + ')'
            : 'нет живых, кто ходил раз в месяц и чаще';
        var newbieValue = G.fmtPct(p.newbie_no_return_pct);
        var newbieSub;
        if (p.newbie_no_return_pct !== null) {
            newbieSub = G.fmtNum(p.newbie_no_return) + ' из ' + G.fmtNum(p.new) + ' новых';
        } else if (p.new) {
            newbieSub = 'созреет ' + G.fmtDate(p.newbie_matures_on);
        } else {
            newbieSub = 'новых нет';
        }
        // Два ряда по четыре: сверху потери (качество), снизу приток и база (количество).
        return '<div class="metric-grid metric-grid-4">' +
            G.metricCard('churn_rate', 'Отток за период', G.fmtPct(p.churn_pct), churnSub) +
            G.metricCard('churn_balance', 'Ушли', G.fmtNum(leftCount(p)),
                'из них после одного визита: ' + G.fmtNum(one)) +
            G.metricCard('churn_damage', 'Ущерб от оттока', G.fmtMoney(p.damage_month),
                'в месяц · в год: ' + G.fmtMoney(p.damage_year)) +
            G.metricCard('churn_slowing', 'Стали ходить реже', G.fmtNum(p.slowing), slowingSub) +
            G.metricCard('churn_balance', 'Новые гости', G.fmtNum(p.new), prevNum('new')) +
            G.metricCard('churn_balance', 'Вернулись после паузы', G.fmtNum(p.reactivated),
                prevNum('reactivated')) +
            G.metricCard('churn_balance', 'Живые на конец', G.fmtNum(p.end_alive),
                'на начало: ' + G.fmtNum(p.start_alive)) +
            G.metricCard('churn_newbie', 'Не вернулись после первого визита', newbieValue,
                newbieSub) +
            '</div>';
    }

    function balanceTable(rows, type) {
        var html = '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th>Период</th><th class="num">Живые на начало</th><th class="num">Новые гости</th>' +
            '<th class="num">Вернулись после паузы</th><th class="num">Ушли</th>' +
            '<th class="num">Живые на конец</th><th class="num">Отток</th>' +
            '<th class="num">Не вернулись после 1-го визита</th></tr></thead><tbody>';
        rows.slice().reverse().forEach(function (r) {
            if (r.state === 'future') return;
            var partial = r.state === 'partial';
            html += '<tr' + (partial ? ' class="row-partial"' : '') + '><td>' +
                shortLabel(r, type) + (partial ? ' · по ' + G.fmtDate(r.asof).slice(0, 5) : '') +
                '</td>' +
                '<td class="num">' + G.fmtNum(r.start_alive) + '</td>' +
                '<td class="num delta-up">+' + G.fmtNum(r.new) + '</td>' +
                '<td class="num">+' + G.fmtNum(r.reactivated) + '</td>' +
                '<td class="num delta-down">-' + G.fmtNum(leftCount(r)) + '</td>' +
                '<td class="num"><b>' + G.fmtNum(r.end_alive) + '</b></td>' +
                '<td class="num">' + G.fmtPct(r.churn_pct) + '</td>' +
                '<td class="num">' + G.fmtPct(r.newbie_no_return_pct) + '</td></tr>';
        });
        return html + '</tbody></table></div>';
    }

    function leaversTable(leavers) {
        if (!leavers.total) {
            return '<div class="note-line">За период никто не ушёл.</div>';
        }
        var html = '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th>Визитов за всю жизнь</th><th class="num">Гостей</th><th class="num">Доля</th>' +
            '<th class="num">Средний LTV</th><th class="num">Ущерб в месяц</th></tr></thead><tbody>';
        leavers.buckets.forEach(function (b) {
            html += '<tr><td>' + G.esc(LEAVER_NAMES[b.segment] || b.segment) + '</td>' +
                '<td class="num"><b>' + G.fmtNum(b.count) + '</b></td>' +
                '<td class="num">' + G.fmtPct(b.share_pct) + '</td>' +
                '<td class="num">' + G.fmtMoney(b.avg_ltv) + '</td>' +
                '<td class="num">' + G.fmtMoney(b.damage_month) + '</td></tr>';
        });
        return html + '</tbody></table></div>';
    }

    function slowingCard(list, days, meta) {
        var html = '<div class="gcard"><h3>Стали ходить реже · ' + G.fmtNum(list.total) +
            G.helpIcon('churn_slowing') + '</h3>';
        if (!list.total) {
            html += '<div class="note-line">Таких гостей нет.</div>';
        } else {
            var csvUrl = '/api/guests/churn-slowing?period_type=' + G.state.periodType +
                '&anchor=' + meta.p_end + (meta.venue ? '&store=' + encodeURIComponent(meta.venue) : '') +
                '&dead_days=' + days + '&export=csv';
            html += '<div class="guest-search"><div class="note-line">Ещё ходят, но вдвое реже, ' +
                'чем раньше. Сверху — самые ценные по выручке за 12 мес' +
                (list.total > list.returned
                    ? '; показаны ' + G.fmtNum(list.returned) + ' из ' + G.fmtNum(list.total)
                    : '') + '.</div>' +
                '<a class="sync-btn" href="' + csvUrl + '">Скачать CSV</a></div>' +
                '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
                '<th>Гость</th><th>Телефон</th><th class="num">Визитов: было → стало</th>' +
                '<th>Последний визит</th><th class="num">Выручка за 12 мес</th>' +
                '</tr></thead><tbody>';
            list.guests.forEach(function (g) {
                html += '<tr><td>' + G.esc(g.name || g.guest_id) + '</td>' +
                    '<td>' + G.esc(g.phone || '—') + '</td>' +
                    '<td class="num">' + G.fmtNum(g.visits_prev) + ' → ' + G.fmtNum(g.visits_recent) +
                    '</td>' +
                    '<td>' + G.fmtDate(g.last_visit) + '</td>' +
                    '<td class="num">' + G.fmtMoney(g.revenue_12m) + '</td></tr>';
            });
            html += '</tbody></table></div>';
        }
        return html + G.howBlock(['churn_slowing'], meta) + '</div>';
    }

    function drawCharts(rows, type) {
        var pal = GCharts.palette();
        var labels = rows.map(function (r) { return shortLabel(r, type); });
        // Неполный период занижает отток (смертей ещё не набралось) — на линии его нет,
        // число неполного периода видно в плитках и таблице с пометкой. «Стали ходить реже» —
        // снимок на дату среза, неполный период его не занижает: точка есть.
        GCharts.line('churnRateChart', labels, [
            { label: 'Отток базы, %',
              data: rows.map(function (r) { return r.state === 'complete' ? r.churn_pct : null; }),
              borderColor: pal.danger, backgroundColor: pal.danger, tension: 0.3, pointRadius: 2 },
            { label: 'Не вернулись после первого визита, %',
              data: rows.map(function (r) { return r.newbie_no_return_pct; }),
              borderColor: pal.warning, backgroundColor: pal.warning, tension: 0.3, pointRadius: 2 },
            // Прозрачная заливка — в легенде пустой пунктирный квадрат, а не серое пятно;
            // точки линии залиты отдельно (pointBackgroundColor).
            { label: 'Стали ходить реже, %',
              data: rows.map(function (r) { return r.state === 'future' ? null : r.slowing_pct; }),
              borderColor: pal.text, backgroundColor: 'transparent', pointBackgroundColor: pal.text,
              borderDash: [5, 4], tension: 0.3, pointRadius: 2 }
        ], { beginAtZero: true });
        GCharts.bar('churnFlowChart', labels, [
            { label: 'Новые гости', data: rows.map(function (r) { return r.new; }),
              backgroundColor: pal.accent, stack: 'flow' },
            { label: 'Вернулись после паузы', data: rows.map(function (r) { return r.reactivated; }),
              backgroundColor: pal.success, stack: 'flow' },
            { label: 'Ушли',
              data: rows.map(function (r) { return r.state === 'future' ? null : -leftCount(r); }),
              backgroundColor: pal.danger, stack: 'flow' },
            { label: 'Живые на конец', type: 'line',
              data: rows.map(function (r) { return r.end_alive; }),
              borderColor: pal.text, backgroundColor: pal.text, tension: 0.3, pointRadius: 2,
              stack: 'line' }
        ], { stacked: true });
    }

    function render() {
        var days = deadDays();
        return Promise.all([
            G.api('/api/guests/churn', { dead_days: days }),
            G.api('/api/guests/churn-slowing', { dead_days: days, limit: SLOWING_LIMIT })
        ]).then(function (answers) {
            var resp = answers[0];
            var list = answers[1].data;
            var d = resp.data, meta = resp.meta;
            var type = meta.period_type;
            var choices = d.choices && d.choices.length ? d.choices : CHOICES;
            var p = d.period;
            var html = switcher(d.dead_days, choices);

            if (!p) {
                html += '<div class="gcard"><div class="note-line">Данных для отчёта нет: ' +
                    'в витрине нет чеков за этот период.</div></div>';
            } else if (p.state === 'future') {
                html += '<div class="gcard"><div class="note-line">Период начался позже ' +
                    'последнего полного дня данных (' + G.fmtDate(d.data_to) + ') — считать ' +
                    'пока нечего.</div></div>';
            } else {
                html += thresholdHint(d.return_gaps, d.dead_days, meta);
                html += tiles(d, type);
                if (p.state === 'partial') {
                    html += '<div class="note-line">Период не закончен: данные по ' +
                        G.fmtDate(p.asof) + ' — последний полный день, витрина обновляется ' +
                        'ночью.</div>';
                }
            }

            if (p) {
                html += '<div class="gcard"><h3>Отток по периодам' + G.helpIcon('churn_rate') +
                    '</h3><div class="chart-box"><canvas id="churnRateChart"></canvas></div>' +
                    G.howBlock(['churn_alive', 'churn_rate', 'churn_newbie', 'churn_slowing'], meta) +
                    '</div>';

                html += '<div class="gcard"><h3>Баланс базы' + G.helpIcon('churn_balance') +
                    '</h3><div class="chart-box tall"><canvas id="churnFlowChart"></canvas></div>' +
                    balanceTable(d.series, type) +
                    G.howBlock(['churn_balance'], meta) + '</div>';
            }

            if (p && p.state !== 'future') {
                html += '<div class="gcard"><h3>Кто уходит · ' + shortLabel(p, type) +
                    G.helpIcon('churn_leavers') + '</h3>' + leaversTable(d.leavers) +
                    G.howBlock(['churn_leavers', 'churn_damage'], meta) + '</div>';
                html += slowingCard(list, d.dead_days, meta);
            }

            pane.innerHTML = html;
            pane.querySelectorAll('.sub-btn[data-days]').forEach(function (b) {
                b.addEventListener('click', function () {
                    pane.dataset.deadDays = b.dataset.days;
                    render().catch(function (e) {
                        pane.innerHTML = '<div class="pane-error">Ошибка: ' +
                            G.esc(e.message) + '</div>';
                    });
                });
            });
            if (p) drawCharts(d.series, type);
        });
    }

    return render();
});

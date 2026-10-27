/* Вкладка «Отток» (§17): гость жив, пока с последнего визита прошло не больше X дней.
   Отток за период, баланс базы по периодам и кто уходит. Порог X — подпереключатель
   вкладки (pane.dataset, как у «Когорт»); сервер считает все пороги разом и отдаёт один. */

Guests.registerView('churn', function (pane) {
    var G = Guests;
    var DEFAULT_DAYS = 30;              // зеркало CHURN_DEAD_DAYS_DEFAULT (решение владельца)
    var CHOICES = [30, 60, 90, 180];    // зеркало CHURN_DEAD_DAYS_CHOICES; ответ несёт data.choices
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

    function leftCount(row) {
        return row.died + row.new_died;
    }

    function tiles(d, type) {
        var p = d.period;
        var prev = null;
        for (var i = d.series.length - 2; i >= 0; i--) {
            if (d.series[i].state === 'complete') { prev = d.series[i]; break; }
        }
        var one = d.leavers.buckets.length ? d.leavers.buckets[0].count : 0;
        var churnSub = 'ушли ' + G.fmtNum(p.died) + ' из ' + G.fmtNum(p.start_alive) +
            ' живых на начало' +
            (prev ? ' · ' + shortLabel(prev, type) + ': ' + G.fmtPct(prev.churn_pct) : '');
        var newbieValue = G.fmtPct(p.newbie_no_return_pct);
        var newbieSub;
        if (p.newbie_no_return_pct !== null) {
            newbieSub = G.fmtNum(p.newbie_no_return) + ' из ' + G.fmtNum(p.new) + ' новых';
        } else if (p.new) {
            newbieSub = 'созреет ' + G.fmtDate(p.newbie_matures_on);
        } else {
            newbieSub = 'новых нет';
        }
        return '<div class="metric-grid">' +
            G.metricCard('churn_rate', 'Отток за период', G.fmtPct(p.churn_pct), churnSub) +
            G.metricCard('churn_balance', 'Ушли', G.fmtNum(leftCount(p)),
                'из них после одного визита: ' + G.fmtNum(one)) +
            G.metricCard('churn_balance', 'Новые', G.fmtNum(p.new),
                'вернулись после паузы: ' + G.fmtNum(p.reactivated)) +
            G.metricCard('churn_balance', 'Живые на конец', G.fmtNum(p.end_alive),
                'на начало: ' + G.fmtNum(p.start_alive)) +
            G.metricCard('churn_newbie', 'Не вернулись после первого визита', newbieValue,
                newbieSub) +
            '</div>';
    }

    function balanceTable(rows, type) {
        var html = '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th>Период</th><th class="num">Живые на начало</th><th class="num">Новые</th>' +
            '<th class="num">Вернулись</th><th class="num">Ушли</th>' +
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
            '<th class="num">Средний LTV</th></tr></thead><tbody>';
        leavers.buckets.forEach(function (b) {
            html += '<tr><td>' + G.esc(LEAVER_NAMES[b.segment] || b.segment) + '</td>' +
                '<td class="num"><b>' + G.fmtNum(b.count) + '</b></td>' +
                '<td class="num">' + G.fmtPct(b.share_pct) + '</td>' +
                '<td class="num">' + G.fmtMoney(b.avg_ltv) + '</td></tr>';
        });
        return html + '</tbody></table></div>';
    }

    function drawCharts(rows, type) {
        var pal = GCharts.palette();
        var labels = rows.map(function (r) { return shortLabel(r, type); });
        // Неполный период занижает отток (смертей ещё не набралось) — на линии его нет,
        // число неполного периода видно в плитках и таблице с пометкой.
        GCharts.line('churnRateChart', labels, [
            { label: 'Отток базы, %',
              data: rows.map(function (r) { return r.state === 'complete' ? r.churn_pct : null; }),
              borderColor: pal.danger, backgroundColor: pal.danger, tension: 0.3, pointRadius: 2 },
            { label: 'Не вернулись после первого визита, %',
              data: rows.map(function (r) { return r.newbie_no_return_pct; }),
              borderColor: pal.warning, backgroundColor: pal.warning, tension: 0.3, pointRadius: 2 }
        ], {});
        GCharts.bar('churnFlowChart', labels, [
            { label: 'Новые', data: rows.map(function (r) { return r.new; }),
              backgroundColor: pal.accent, stack: 'flow' },
            { label: 'Вернулись', data: rows.map(function (r) { return r.reactivated; }),
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
        return G.api('/api/guests/churn', { dead_days: days }).then(function (resp) {
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
                    G.howBlock(['churn_alive', 'churn_rate', 'churn_newbie'], meta) + '</div>';

                html += '<div class="gcard"><h3>Баланс базы' + G.helpIcon('churn_balance') +
                    '</h3><div class="chart-box tall"><canvas id="churnFlowChart"></canvas></div>' +
                    balanceTable(d.series, type) +
                    G.howBlock(['churn_balance'], meta) + '</div>';
            }

            if (p && p.state !== 'future') {
                html += '<div class="gcard"><h3>Кто уходит · ' + shortLabel(p, type) +
                    G.helpIcon('churn_leavers') + '</h3>' + leaversTable(d.leavers) +
                    G.howBlock(['churn_leavers'], meta) + '</div>';
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

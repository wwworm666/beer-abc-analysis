/* Вкладка «Отток» (§17): гость жив, пока с последнего визита прошло не больше X дней.
   Отток за период, баланс базы по периодам и кто уходит. Порог X — подпереключатель
   вкладки (pane.dataset, как у «Когорт»); сервер считает все пороги разом и отдаёт один.
   С 2026-10-30 (статья Unisender о churn rate): ущерб от оттока в рублях, «Стали ходить
   реже» (скрытый отток) и подсказка к порогу. Плитки с группами гостей и строки «Кто уходит»
   кликабельны: карточка списка показывает этих гостей поимённо (/api/guests/churn-guests).
   Список — сразу под плитками; длина графиков — кнопки «Графики за» (до «всё время»); при
   «Все бары» — «Бары рядом» и «Отток по барам»: тот же маршрут по каждому бару. */

Guests.registerView('churn', function (pane) {
    var G = Guests;
    var DEFAULT_DAYS = 30;              // зеркало CHURN_DEAD_DAYS_DEFAULT (решение владельца)
    var CHOICES = [30, 60, 90, 180];    // зеркало CHURN_DEAD_DAYS_CHOICES; ответ несёт data.choices
    // Строк списка гостей в ответе — самые ценные в группе; видно первые LIST_SHOW, остальные —
    // по кнопке; весь список — CSV.
    var LIST_LIMIT = 50;
    var LIST_SHOW = 10;
    // «Графики за»: подпись во времени -> periods маршрута. Значение по умолчанию у типа —
    // зеркало CHURN_SERIES_DEFAULT; 'all' — вся история (ряд обрезается по первому чеку сети
    // или бара). Плитки и списки от этой кнопки не зависят.
    var RANGES = {
        week: [['26', 'полгода'], ['52', '1 год'], ['104', '2 года'], ['all', 'всё время']],
        month: [['12', '1 год'], ['24', '2 года'], ['60', '5 лет'], ['all', 'всё время']],
        quarter: [['8', '2 года'], ['12', '3 года'], ['20', '5 лет'], ['all', 'всё время']],
        year: [['5', '5 лет'], ['8', '8 лет'], ['all', 'всё время']]
    };
    var RANGE_DEFAULT = { week: '26', month: '24', quarter: '12', year: '8' };
    var DEFAULT_GROUP = 'left';
    var OTHER_LIST = 'Другая группа — плитка вверху или строка «Кто уходит».';
    // Колонки списка: заголовок, число ли, ячейка.
    var COLS = {
        favorite_store: ['Любимая точка', false, function (g) { return G.esc(g.favorite_store_name || '—'); }],
        visits_total: ['Визитов за всё время', true, function (g) { return G.fmtNum(g.visits_total); }],
        first_visit: ['Первый визит', false, function (g) { return G.fmtDate(g.first_visit); }],
        last_visit: ['Последний визит', false, function (g) { return G.fmtDate(g.last_visit); }],
        damage_month: ['Ущерб в месяц', true, function (g) { return G.fmtMoney(g.damage_month); }],
        ltv: ['LTV', true, function (g) { return G.fmtMoney(g.ltv); }],
        pause_days: ['Пауза перед возвратом, дней', true, function (g) { return G.fmtNum(g.pause_days); }],
        visits_period: ['Визитов в периоде', true, function (g) { return G.fmtNum(g.visits_period); }],
        revenue_period: ['Выручка в периоде', true, function (g) { return G.fmtMoney(g.revenue_period); }],
        revenue_12m: ['Выручка за 12 мес', true, function (g) { return G.fmtMoney(g.revenue_12m); }],
        visits_change: ['Визитов: было → стало', true, function (g) {
            return G.fmtNum(g.visits_prev) + ' → ' + G.fmtNum(g.visits_recent);
        }]
    };
    // Группы плиток: заголовок списка, порядок, колонки и формулы «Как считается».
    var GROUPS = {
        left: { title: 'Ушли', order: 'по ущербу в месяц',
                cols: ['visits_total', 'last_visit', 'damage_month', 'ltv'],
                keys: ['churn_balance', 'churn_damage'] },
        reactivated: { title: 'Вернулись после паузы', order: 'по выручке в периоде',
                cols: ['pause_days', 'last_visit', 'visits_period', 'revenue_period'],
                keys: ['churn_balance'] },
        'new': { title: 'Новые гости', order: 'по выручке в периоде',
                cols: ['first_visit', 'visits_period', 'revenue_period'],
                keys: ['churn_balance'] },
        newbie_no_return: { title: 'Не вернулись после первого визита', order: 'по LTV',
                cols: ['first_visit', 'ltv'], keys: ['churn_newbie'] },
        slowing: { title: 'Стали ходить реже', order: 'по выручке за 12 мес',
                cols: ['visits_change', 'last_visit', 'revenue_12m'], keys: ['churn_slowing'] }
    };
    var LEAVER_NAMES = {
        '1': '1 визит — пришёл и не вернулся',
        '2-3': '2–3 визита',
        '4-8': '4–8 визитов',
        '9+': '9 визитов и больше'
    };

    function currentGroup() {
        var g = pane.dataset.group || DEFAULT_GROUP;
        return GROUPS[g] ? g : DEFAULT_GROUP;
    }

    function currentBucket() {
        return currentGroup() === 'left' ? (pane.dataset.bucket || '') : '';
    }

    // Плитка, по которой открывается список её гостей.
    function pick(group, html) {
        return '<div class="churn-pick' + activeIf(group === currentGroup() && !currentBucket()) +
            '" data-group="' + group + '" role="button" tabindex="0" title="Показать гостей">' +
            html + '</div>';
    }

    // Длина графиков: выбранная кнопка, пока тип периода тот же; иначе — по умолчанию для типа.
    function currentRange(type) {
        var list = RANGES[type] || RANGES.month;
        var v = pane.dataset.rangeType === type ? pane.dataset.range : '';
        var ok = list.some(function (r) { return r[0] === v; });
        return ok ? v : (RANGE_DEFAULT[type] || RANGE_DEFAULT.month);
    }

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

    function rangeSwitcher(type, current) {
        return '<div class="sub-switch"><span class="sub-label">Графики за:</span>' +
            (RANGES[type] || RANGES.month).map(function (r) {
                return '<button class="sub-btn' + activeIf(r[0] === current) +
                    '" data-range="' + r[0] + '">' + r[1] + '</button>';
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
            pick('left', G.metricCard('churn_balance', 'Ушли', G.fmtNum(leftCount(p)),
                'из них после одного визита: ' + G.fmtNum(one))) +
            pick('left', G.metricCard('churn_damage', 'Ущерб от оттока', G.fmtMoney(p.damage_month),
                'в месяц · в год: ' + G.fmtMoney(p.damage_year))) +
            pick('slowing', G.metricCard('churn_slowing', 'Стали ходить реже', G.fmtNum(p.slowing),
                slowingSub)) +
            pick('new', G.metricCard('churn_balance', 'Новые гости', G.fmtNum(p.new),
                prevNum('new'))) +
            pick('reactivated', G.metricCard('churn_balance', 'Вернулись после паузы',
                G.fmtNum(p.reactivated), prevNum('reactivated'))) +
            G.metricCard('churn_balance', 'Живые на конец', G.fmtNum(p.end_alive),
                'на начало: ' + G.fmtNum(p.start_alive)) +
            (p.newbie_no_return_pct !== null
                ? pick('newbie_no_return', G.metricCard('churn_newbie',
                    'Не вернулись после первого визита', newbieValue, newbieSub))
                : G.metricCard('churn_newbie', 'Не вернулись после первого визита', newbieValue,
                    newbieSub)) +
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
            var on = currentGroup() === 'left' && currentBucket() === b.segment;
            html += '<tr class="churn-bucket-pick' + activeIf(on) + '" data-bucket="' +
                G.esc(b.segment) + '" tabindex="0" title="Показать гостей">' +
                '<td>' + G.esc(LEAVER_NAMES[b.segment] || b.segment) + '</td>' +
                '<td class="num"><b>' + G.fmtNum(b.count) + '</b></td>' +
                '<td class="num">' + G.fmtPct(b.share_pct) + '</td>' +
                '<td class="num">' + G.fmtMoney(b.avg_ltv) + '</td>' +
                '<td class="num">' + G.fmtMoney(b.damage_month) + '</td></tr>';
        });
        return html + '</tbody></table></div>';
    }

    function listCard(list, days, meta) {
        var spec = GROUPS[list.group] || GROUPS[DEFAULT_GROUP];
        // По всей сети — любимая точка гостя: какой бар его возвращает. С баром не нужна.
        var cols = (meta.venue ? [] : ['favorite_store']).concat(spec.cols);
        var title = spec.title + (list.bucket ? ' · ' + (LEAVER_NAMES[list.bucket] || list.bucket) : '');
        var html = '<div class="gcard" id="churnList"><h3>' + G.esc(title) +
            (list.total !== null && list.total !== undefined ? ' · ' + G.fmtNum(list.total) : '') +
            G.helpIcon('churn_list') + '</h3>';
        if (!list.mature) {
            html += '<div class="note-line">Список появится ' + G.fmtDate(list.matures_on) +
                ': у последних новичков периода ещё не прошло ' + days + ' дней.</div>';
        } else if (!list.total) {
            html += '<div class="note-line">Таких гостей нет. ' + OTHER_LIST + '</div>';
        } else {
            var csvUrl = '/api/guests/churn-guests?period_type=' + G.state.periodType +
                '&anchor=' + meta.p_end + (meta.venue ? '&store=' + encodeURIComponent(meta.venue) : '') +
                '&group=' + list.group + '&dead_days=' + days +
                (list.bucket ? '&bucket=' + encodeURIComponent(list.bucket) : '') + '&export=csv';
            var more = list.guests.length - LIST_SHOW;
            html += '<div class="guest-search"><div class="note-line">Сверху — самые ценные: ' +
                spec.order + '; всего ' + G.fmtNum(list.total) + ', все с телефонами — в CSV. ' +
                OTHER_LIST + '</div>' +
                '<a class="sync-btn" href="' + csvUrl + '">Скачать CSV</a></div>' +
                '<div class="gtable-wrap"><table class="gtable"><thead><tr><th>Гость</th><th>Телефон</th>' +
                cols.map(function (c) {
                    return '<th' + (COLS[c][1] ? ' class="num"' : '') + '>' + COLS[c][0] + '</th>';
                }).join('') + '</tr></thead><tbody>';
            list.guests.forEach(function (g, i) {
                // Без имени в карте — как в RFM: номер уже стоит в колонке «Телефон».
                html += '<tr' + (i >= LIST_SHOW ? ' class="churn-more" hidden' : '') + '><td>' +
                    (G.esc(g.name) || '<span class="dim">без имени</span>') + '</td>' +
                    '<td>' + G.esc(g.phone || '—') + '</td>' +
                    cols.map(function (c) {
                        return '<td' + (COLS[c][1] ? ' class="num"' : '') + '>' + COLS[c][2](g) + '</td>';
                    }).join('') + '</tr>';
            });
            html += '</tbody></table></div>';
            if (more > 0) {
                html += '<button type="button" class="sync-btn churn-more-btn">Показать ещё ' +
                    G.fmtNum(more) + '</button>';
            }
        }
        return html + G.howBlock(['churn_list'].concat(spec.keys), meta) + '</div>';
    }

    function listParams(days) {
        var params = { group: currentGroup(), dead_days: days, limit: LIST_LIMIT };
        if (currentBucket()) params.bucket = currentBucket();
        return params;
    }

    // Клик по плитке или строке «Кто уходит»: список этих гостей, без перерисовки вкладки.
    function choose(group, bucket, meta) {
        pane.dataset.group = group;
        pane.dataset.bucket = bucket || '';
        pane.querySelectorAll('.churn-pick').forEach(function (el) {
            el.classList.toggle('active', !bucket && el.dataset.group === group);
        });
        pane.querySelectorAll('.churn-bucket-pick').forEach(function (el) {
            el.classList.toggle('active', !!bucket && el.dataset.bucket === bucket);
        });
        var days = deadDays();
        return G.api('/api/guests/churn-guests', listParams(days)).then(function (resp) {
            var card = pane.querySelector('#churnList');
            if (!card) return;
            card.outerHTML = listCard(resp.data, days, meta);
            bindMore();
            var fresh = pane.querySelector('#churnList');
            if (fresh && fresh.scrollIntoView) fresh.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }).catch(function (e) {
            var card = pane.querySelector('#churnList');
            if (card) card.innerHTML = '<div class="pane-error">Ошибка: ' + G.esc(e.message) + '</div>';
        });
    }

    // «Показать ещё»: остальные строки ответа (до LIST_LIMIT) — без нового запроса.
    function bindMore() {
        var btn = pane.querySelector('#churnList .churn-more-btn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            pane.querySelectorAll('#churnList .churn-more').forEach(function (tr) { tr.hidden = false; });
            btn.remove();
        });
    }

    function bindPicks(meta) {
        function onActivate(el, fn) {
            el.addEventListener('click', fn);
            el.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); }
            });
        }
        pane.querySelectorAll('.churn-pick').forEach(function (el) {
            onActivate(el, function () { choose(el.dataset.group, '', meta); });
        });
        pane.querySelectorAll('.churn-bucket-pick').forEach(function (el) {
            onActivate(el, function () { choose('left', el.dataset.bucket, meta); });
        });
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
        ], { beginAtZero: true, compactX: true });
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
        ], { stacked: true, compactX: true });
    }

    // «Бары рядом» (только «Все бары»): те же числа, что в плитках, по каждому бару и по сети;
    // под таблицей — столбики «Ушли / Новые / Вернулись» по барам.
    function barsCard(net, perBar, type, meta) {
        function row(name, q, total) {
            var cells = q && q.state !== 'future'
                ? [G.fmtPct(q.churn_pct), G.fmtNum(leftCount(q)), G.fmtMoney(q.damage_month),
                   G.fmtNum(q.slowing), G.fmtNum(q.new), G.fmtNum(q.reactivated),
                   G.fmtNum(q.end_alive), G.fmtPct(q.newbie_no_return_pct)]
                : ['—', '—', '—', '—', '—', '—', '—', '—'];
            return '<tr' + (total ? ' class="row-total"' : '') + '><td>' + G.esc(name) + '</td>' +
                cells.map(function (c) { return '<td class="num">' + c + '</td>'; }).join('') +
                '</tr>';
        }
        var html = '<div class="gcard"><h3>Бары рядом · ' + shortLabel(net.period, type) +
            G.helpIcon('churn_bars') + '</h3><div class="gtable-wrap"><table class="gtable churn-bars-table">' +
            '<thead><tr><th>Бар</th><th class="num">Отток</th><th class="num">Ушли</th>' +
            '<th class="num">Ущерб в месяц</th><th class="num">Стали ходить реже</th>' +
            '<th class="num">Новые гости</th><th class="num">Вернулись после паузы</th>' +
            '<th class="num">Живые на конец</th><th class="num">Не вернулись после 1-го визита</th>' +
            '</tr></thead><tbody>';
        perBar.forEach(function (b) { html += row(b.name, b.data && b.data.period, false); });
        return html + row('Вся сеть', net.period, true) + '</tbody></table></div>' +
            '<div class="note-line">Бары не складываются в сеть: гость нескольких баров считается ' +
            'в каждом.</div>' +
            '<div class="chart-box"><canvas id="churnBarsChart"></canvas></div>' +
            G.howBlock(['churn_bars', 'churn_balance'], meta) + '</div>';
    }

    // «Отток по барам» (только «Все бары»): малый график на бар, одна шкала и одна легенда.
    function barsTrendCard(perBar, meta) {
        var html = '<div class="gcard"><h3>Отток по барам' + G.helpIcon('churn_bars') + '</h3>' +
            '<div class="churn-legend">' +
            '<span class="churn-legend-item"><span class="churn-swatch churn-swatch-danger"></span>' +
            'Отток базы, %</span>' +
            '<span class="churn-legend-item"><span class="churn-swatch churn-swatch-warning"></span>' +
            'Не вернулись после первого визита, %</span></div><div class="churn-bars-grid">';
        perBar.forEach(function (b) {
            html += '<div class="churn-bar-cell"><div class="churn-bar-name">' + G.esc(b.name) +
                '</div><div class="chart-box short"><canvas id="churnBarChart-' + b.key +
                '"></canvas></div></div>';
        });
        return html + '</div>' +
            G.howBlock(['churn_bars', 'churn_rate', 'churn_newbie', 'churn_range'], meta) + '</div>';
    }

    function drawBarCharts(rows, perBar, type) {
        var pal = GCharts.palette();
        var shown = perBar.filter(function (b) { return b.data && b.data.period; });
        GCharts.bar('churnBarsChart', shown.map(function (b) { return b.name; }), [
            { label: 'Ушли', data: shown.map(function (b) { return leftCount(b.data.period); }),
              backgroundColor: pal.danger },
            { label: 'Новые гости', data: shown.map(function (b) { return b.data.period.new; }),
              backgroundColor: pal.accent },
            { label: 'Вернулись после паузы',
              data: shown.map(function (b) { return b.data.period.reactivated; }),
              backgroundColor: pal.success }
        ], {});
        // Ось X — периоды сети (самый длинный ряд); у бара, открытого позже, начало пустое.
        var labels = rows.map(function (r) { return shortLabel(r, type); });
        var lines = {};
        var top = 0;
        perBar.forEach(function (b) {
            var byStart = {};
            ((b.data && b.data.series) || []).forEach(function (r) { byStart[r.p_start] = r; });
            var churn = rows.map(function (r) {
                var q = byStart[r.p_start];
                return q && q.state === 'complete' ? q.churn_pct : null;
            });
            var newbie = rows.map(function (r) {
                var q = byStart[r.p_start];
                return q ? q.newbie_no_return_pct : null;
            });
            churn.concat(newbie).forEach(function (v) { if (v !== null && v > top) top = v; });
            lines[b.key] = [churn, newbie];
        });
        // Одна шкала на все бары: одинаковая высота линии — одинаковый процент.
        var yMax = Math.max(10, Math.ceil(top / 10) * 10);
        perBar.forEach(function (b) {
            GCharts.line('churnBarChart-' + b.key, labels, [
                { label: 'Отток базы, %', data: lines[b.key][0], borderColor: pal.danger,
                  backgroundColor: pal.danger, tension: 0.3, pointRadius: 1.5 },
                { label: 'Не вернулись после первого визита, %', data: lines[b.key][1],
                  borderColor: pal.warning, backgroundColor: pal.warning, tension: 0.3,
                  pointRadius: 1.5 }
            ], { beginAtZero: true, yMax: yMax, noLegend: true, compactX: true });
        });
    }

    function render() {
        var days = deadDays();
        var range = currentRange(G.state.periodType);
        // «Все бары»: тот же отчёт по каждому бару — для «Бары рядом» и «Отток по барам».
        var barList = G.state.bar ? [] : G.bars();
        var calls = [
            G.api('/api/guests/churn', { dead_days: days, periods: range }),
            G.api('/api/guests/churn-guests', listParams(days))
        ].concat(barList.map(function (b) {
            // Бар без ответа не роняет вкладку: в его строке прочерки.
            return G.api('/api/guests/churn', { dead_days: days, periods: range, store: b.key })
                .then(function (r) { return r.data; }, function () { return null; });
        }));
        return Promise.all(calls).then(function (answers) {
            var resp = answers[0];
            var list = answers[1].data;
            var d = resp.data, meta = resp.meta;
            var type = meta.period_type;
            var choices = d.choices && d.choices.length ? d.choices : CHOICES;
            var p = d.period;
            var perBar = barList.map(function (b, i) {
                return { key: b.key, name: b.name, data: answers[2 + i] };
            });
            var showBars = !meta.venue && perBar.length > 0 && p && p.state !== 'future';
            var html = '<div class="churn-switches">' + switcher(d.dead_days, choices) +
                rangeSwitcher(type, range) + '</div>';

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

            // Сначала — числа по барам и люди (кого вернуть), потом — графики по периодам.
            if (p && p.state !== 'future') {
                if (showBars) {
                    html += barsCard(d, perBar, type, meta);
                } else if (meta.venue) {
                    html += '<div class="note-line">Сравнение баров — при выборе «Все бары».</div>';
                }
                html += '<div class="gcard"><h3>Кто уходит · ' + shortLabel(p, type) +
                    G.helpIcon('churn_leavers') + '</h3>' + leaversTable(d.leavers) +
                    G.howBlock(['churn_leavers', 'churn_damage'], meta) + '</div>';
                html += listCard(list, d.dead_days, meta);
            }

            if (p) {
                html += '<div class="gcard"><h3>Отток по периодам' + G.helpIcon('churn_rate') +
                    '</h3><div class="chart-box"><canvas id="churnRateChart"></canvas></div>' +
                    G.howBlock(['churn_alive', 'churn_rate', 'churn_newbie', 'churn_slowing',
                                'churn_range'], meta) + '</div>';
                if (showBars) html += barsTrendCard(perBar, meta);
                html += '<div class="gcard"><h3>Баланс базы' + G.helpIcon('churn_balance') +
                    '</h3><div class="chart-box tall"><canvas id="churnFlowChart"></canvas></div>' +
                    balanceTable(d.series, type) +
                    G.howBlock(['churn_balance', 'churn_range'], meta) + '</div>';
            }

            pane.innerHTML = html;
            function rerender() {
                render().catch(function (e) {
                    pane.innerHTML = '<div class="pane-error">Ошибка: ' + G.esc(e.message) + '</div>';
                });
            }
            pane.querySelectorAll('.sub-btn[data-days]').forEach(function (b) {
                b.addEventListener('click', function () {
                    pane.dataset.deadDays = b.dataset.days;
                    rerender();
                });
            });
            pane.querySelectorAll('.sub-btn[data-range]').forEach(function (b) {
                b.addEventListener('click', function () {
                    pane.dataset.range = b.dataset.range;
                    pane.dataset.rangeType = type;
                    rerender();
                });
            });
            bindPicks(meta);
            bindMore();
            if (p) drawCharts(d.series, type);
            if (showBars) drawBarCharts(d.series, perBar, type);
        });
    }

    return render();
});

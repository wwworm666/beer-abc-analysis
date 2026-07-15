/* Вкладка «Когорты»: жизненный цикл (§2), возвраты (§5), доходы (§6).
   Подпереключатель разделов; heat-таблицы на CSS color-mix от --accent. */

Guests.registerView('cohorts', function (pane) {
    var G = Guests;
    var mode = pane.dataset.mode || 'lifecycle';

    function heatCell(pct, max) {
        if (pct === null || pct === undefined) return '<td class="heat dim">—</td>';
        var alpha = max > 0 ? Math.round(Math.min(pct / max, 1) * 55) : 0;
        return '<td class="heat" style="background: color-mix(in srgb, var(--accent) ' +
            alpha + '%, transparent)">' + G.fmtPct(pct) + '</td>';
    }

    function switcher() {
        var items = [['lifecycle', 'Жизненный цикл'], ['retention', 'Возвраты'], ['revenue', 'Доходы']];
        return '<div class="sub-switch">' + items.map(function (it) {
            return '<button class="sub-btn' + (mode === it[0] ? ' active' : '') +
                '" data-mode="' + it[0] + '">' + it[1] + '</button>';
        }).join('') + '</div>';
    }

    function bindSwitcher() {
        pane.querySelectorAll('.sub-btn[data-mode]').forEach(function (b) {
            b.addEventListener('click', function () {
                pane.dataset.mode = b.dataset.mode;
                render();
            });
        });
    }

    function renderLifecycle() {
        return G.api('/api/guests/cohorts/lifecycle').then(function (resp) {
            var d = resp.data;
            var basisNote = d.basis === 'first_order'
                ? '<div class="note-line">Дата регистрации из iiko недоступна — когорты считаются от первой покупки.</div>'
                : '';
            var html = switcher() +
                '<div class="gcard"><h3>Когорты жизненного цикла' + G.helpIcon('lifecycle_cohort') +
                '</h3><div class="gtable-wrap"><table class="gtable"><thead><tr>' +
                '<th>Когорта (месяц регистрации)</th><th class="num">Гостей</th>' +
                '<th class="num">1-й заказ</th><th class="num">2-й заказ</th>' +
                '<th class="num">5-й заказ</th><th class="num">Активны сейчас</th></tr></thead><tbody>';
            d.cohorts.forEach(function (c) {
                html += '<tr><td>' + G.fmtMonth(c.cohort) + '</td>' +
                    '<td class="num"><b>' + G.fmtNum(c.guests) + '</b></td>' +
                    heatCell(c.order1_pct, 100) + heatCell(c.order2_pct, 100) +
                    heatCell(c.order5_pct, 100) + heatCell(c.active_pct, 100) + '</tr>';
            });
            html += '</tbody></table></div>' + basisNote + '</div>' +
                G.howBlock(['lifecycle_cohort', 'order', 'activity_status']);
            pane.innerHTML = html;
            bindSwitcher();
        });
    }

    function renderRetention() {
        return G.api('/api/guests/retention', { basis: 'first_order' }).then(function (resp) {
            var d = resp.data;
            var html = switcher() +
                '<div class="gcard"><h3>Возвраты когорт (от первой покупки)' + G.helpIcon('retention') +
                '</h3><div class="gtable-wrap"><table class="gtable"><thead><tr>' +
                '<th>Когорта (месяц 1-й покупки)</th><th class="num">Гостей</th>' +
                d.windows.map(function (w) { return '<th class="num">через ' + w + ' дн</th>'; }).join('') +
                '</tr></thead><tbody>';
            d.cohorts.forEach(function (c) {
                html += '<tr><td>' + G.fmtMonth(c.cohort) + '</td>' +
                    '<td class="num"><b>' + G.fmtNum(c.guests) + '</b></td>' +
                    d.windows.map(function (w) { return heatCell(c.returned_pct[String(w)], 60); }).join('') +
                    '</tr>';
            });
            html += '</tbody></table></div>' +
                '<div class="note-line">Прочерк — когорта ещё не дозрела до окна ' +
                '(конец месяца когорты + окно позже даты среза).</div></div>' +
                G.howBlock(['retention', 'visit']);
            pane.innerHTML = html;
            bindSwitcher();
        });
    }

    function renderRevenue() {
        var basis = pane.dataset.basis || 'registration';
        var metric = pane.dataset.metric || 'revenue';
        return G.api('/api/guests/cohorts/revenue', { basis: basis }).then(function (resp) {
            var d = resp.data;
            var metricDefs = {
                revenue: ['Выручка', function (c) { return c.revenue; }, G.fmtMoney],
                orders: ['Заказы', function (c) { return c.orders; }, G.fmtNum],
                ltv: ['LTV', function (c) { return c.ltv; }, G.fmtMoney],
                guests: ['Гостей', function (c) { return c.guests; }, G.fmtNum]
            };
            var basisBtns = '<div class="sub-switch">' +
                '<button class="sub-btn' + (basis === 'registration' ? ' active' : '') +
                '" data-basis="registration">Когорта: регистрация</button>' +
                '<button class="sub-btn' + (basis === 'first_order' ? ' active' : '') +
                '" data-basis="first_order">Когорта: первая покупка</button></div>';
            var metricBtns = '<div class="sub-switch">' +
                Object.keys(metricDefs).map(function (mkey) {
                    return '<button class="sub-btn' + (metric === mkey ? ' active' : '') +
                        '" data-metric="' + mkey + '">' + metricDefs[mkey][0] + '</button>';
                }).join('') + '</div>';

            var html = switcher() +
                '<div class="gcard"><h3>Когортные доходы (накопительно за жизнь когорты)' +
                G.helpIcon('cohort_revenue') + '</h3>' + basisBtns + metricBtns +
                '<div class="chart-box tall"><canvas id="cohRevChart"></canvas></div>' +
                '<div class="gtable-wrap" style="margin-top:16px"><table class="gtable"><thead><tr>' +
                '<th>Когорта</th><th class="num">Гостей</th><th class="num">Выручка</th>' +
                '<th class="num">Заказы</th><th class="num">LTV</th></tr></thead><tbody>';
            d.cohorts.forEach(function (c) {
                html += '<tr><td>' + G.fmtMonth(c.cohort) + '</td>' +
                    '<td class="num">' + G.fmtNum(c.guests) + '</td>' +
                    '<td class="num">' + G.fmtMoney(c.revenue) + '</td>' +
                    '<td class="num">' + G.fmtNum(c.orders) + '</td>' +
                    '<td class="num">' + G.fmtMoney(c.ltv) + '</td></tr>';
            });
            html += '</tbody></table></div></div>' + G.howBlock(['cohort_revenue', 'ltv']);
            pane.innerHTML = html;
            bindSwitcher();
            pane.querySelectorAll('.sub-btn[data-basis]').forEach(function (b) {
                b.addEventListener('click', function () {
                    pane.dataset.basis = b.dataset.basis; render();
                });
            });
            pane.querySelectorAll('.sub-btn[data-metric]').forEach(function (b) {
                b.addEventListener('click', function () {
                    pane.dataset.metric = b.dataset.metric; render();
                });
            });

            var rows = d.cohorts.slice().reverse();
            var def = metricDefs[metric];
            GCharts.hbar('cohRevChart',
                rows.map(function (c) { return G.fmtMonth(c.cohort); }),
                [{ label: def[0], data: rows.map(def[1]),
                   backgroundColor: GCharts.palette().accent, borderRadius: 4 }],
                {});
        });
    }

    function render() {
        mode = pane.dataset.mode || 'lifecycle';
        pane.innerHTML = '<div class="pane-loading">Загрузка…</div>';
        if (mode === 'retention') return renderRetention();
        if (mode === 'revenue') return renderRevenue();
        return renderLifecycle();
    }

    return render();
});

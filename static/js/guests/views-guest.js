/* Вкладка «Гость» (ТЗ §12): поиск и карточка гостя — все три временных среза. */

Guests.registerView('guest', function (pane) {
    var G = Guests;
    var segTitles = {
        CHAMPIONS: 'Чемпион', LOYAL: 'Лояльный', NEW: 'Новичок',
        AT_RISK: 'Под риском', CHURNED: 'Уходящий', POTENTIAL: 'Потенциальный'
    };
    var statusTitles = { active: 'Active', sleeping: 'Sleeping', at_risk: 'At Risk', lost: 'Lost' };

    function shell() {
        pane.innerHTML =
            '<div class="guest-search"><input type="text" id="guestQ" ' +
            'placeholder="Телефон, номер карты или имя (минимум 2 символа)"></div>' +
            '<div class="search-results" id="guestHits"></div>' +
            '<div id="guestCard"></div>' +
            G.howBlock(['visit', 'order', 'revenue', 'ltv', 'rfm', 'activity_status',
                        'favorite_store']);
        var input = document.getElementById('guestQ');
        var t = null;
        input.addEventListener('input', function () {
            clearTimeout(t);
            t = setTimeout(function () { search(input.value); }, 300);
        });
        var saved = pane.dataset.guestId;
        if (saved) showCard(saved);
    }

    function search(q) {
        var hits = document.getElementById('guestHits');
        if ((q || '').trim().length < 2) { hits.innerHTML = ''; return; }
        fetch('/api/guests/search?q=' + encodeURIComponent(q.trim()))
            .then(function (r) { return r.json(); })
            .then(function (j) {
                hits.innerHTML = (j.guests || []).map(function (g) {
                    return '<div class="search-hit" data-gid="' + G.esc(g.guest_id) + '">' +
                        '<b>' + (G.esc(g.name) || 'Без имени') + '</b>' +
                        '<span class="dim">' + G.esc(g.phone) + '</span>' +
                        '<span class="dim">карта: ' + G.esc(g.card_number) + '</span>' +
                        '<span class="dim">визит: ' + G.fmtDate(g.last_visit_date) + '</span></div>';
                }).join('') || '<div class="note-line">Никого не нашлось</div>';
                hits.querySelectorAll('.search-hit').forEach(function (el) {
                    el.addEventListener('click', function () { showCard(el.dataset.gid); });
                });
            });
    }

    function showCard(guestId) {
        pane.dataset.guestId = guestId;
        var box = document.getElementById('guestCard');
        box.innerHTML = '<div class="pane-loading">Загрузка…</div>';
        G.api('/api/guests/guest/' + encodeURIComponent(guestId)).then(function (resp) {
            var d = resp.data, g = d.guest;
            var regSrc = g.registration_source === 'iiko'
                ? 'дата создания в iiko'
                : 'принята по первой покупке (в iiko даты нет)';

            var html = '<div class="gcard"><h3>' + (G.esc(g.name) || 'Гость без имени') +
                (d.activity_status ? ' <span class="gbadge ' + d.activity_status + '">' +
                    statusTitles[d.activity_status] + '</span>' : '') +
                (d.rfm ? ' <span class="gbadge">' + (segTitles[d.rfm.segment] || d.rfm.segment) +
                    '</span>' : '') + '</h3>' +
                '<div class="metric-grid">' +
                G.metricCard('registrations', 'Регистрация', G.fmtDate(g.registration_date), regSrc) +
                G.metricCard('first_orders', 'Первый заказ', G.fmtDate(g.first_order_date),
                    G.esc(g.first_order_store_name)) +
                G.metricCard('visit', 'Последний визит', G.fmtDate(g.last_visit_date),
                    'телефон: ' + G.esc(g.phone)) +
                G.metricCard('ltv', 'LTV', G.fmtMoney(d.ltv), 'выручка за всю историю') +
                G.metricCard('favorite_store', 'Любимая точка',
                    G.esc(d.favorite_store_name) || '—', 'по числу визитов') +
                (d.rfm ? G.metricCard('rfm', 'RFM (12 мес)',
                    'R' + d.rfm.r + ' F' + d.rfm.f,
                    d.rfm.frequency + ' визитов · ' + G.fmtMoney(d.rfm.monetary)) : '') +
                '</div></div>';

            html += '<div class="gcard"><h3>Показатели по срезам</h3><div class="gtable-wrap">' +
                '<table class="gtable"><thead><tr><th>Срез</th><th class="num">Заказы</th>' +
                '<th class="num">Визиты</th><th class="num">Выручка</th>' +
                '<th class="num">Средний чек</th></tr></thead><tbody>';
            [['Выбранный период', d.slices.period], ['С начала года', d.slices.ytd],
             ['За всё время', d.slices.lifetime]].forEach(function (row) {
                var s = row[1];
                html += '<tr><td>' + row[0] + '</td>' +
                    '<td class="num">' + G.fmtNum(s.orders) + '</td>' +
                    '<td class="num">' + G.fmtNum(s.visits) + '</td>' +
                    '<td class="num">' + G.fmtMoney(s.revenue) + '</td>' +
                    '<td class="num">' + G.fmtMoney(s.avg_check) + '</td></tr>';
            });
            html += '</tbody></table></div></div>';

            html += '<div class="gcard-grid-2">';
            html += '<div class="gcard"><h3>Любимые товары (топ-5 по количеству)</h3>' +
                '<div class="gtable-wrap"><table class="gtable"><thead><tr><th>Товар</th>' +
                '<th class="num">Кол-во</th><th class="num">Выручка</th></tr></thead><tbody>' +
                d.top_dishes.map(function (t) {
                    return '<tr><td>' + G.esc(t.dish_name) + '</td>' +
                        '<td class="num">' + G.fmtNum(t.amount) + '</td>' +
                        '<td class="num">' + G.fmtMoney(t.revenue) + '</td></tr>';
                }).join('') + '</tbody></table></div></div>';

            html += '<div class="gcard"><h3>Последние чеки</h3>' +
                '<div class="gtable-wrap"><table class="gtable"><thead><tr><th>Дата</th>' +
                '<th>Точка</th><th class="num">Сумма</th><th class="num">Скидка</th>' +
                '</tr></thead><tbody>' +
                d.recent_receipts.slice(0, 15).map(function (r) {
                    return '<tr><td>' + G.fmtDate(r.open_date) + '</td>' +
                        '<td>' + G.esc(r.store_name) + '</td>' +
                        '<td class="num">' + G.fmtMoney(r.revenue) + '</td>' +
                        '<td class="num dim">' + G.fmtMoney(r.discount) + '</td></tr>';
                }).join('') + '</tbody></table></div></div></div>';

            box.innerHTML = html;
        }).catch(function (e) {
            box.innerHTML = '<div class="pane-error">Ошибка: ' + G.esc(e.message) + '</div>';
        });
    }

    shell();
    return Promise.resolve();
});

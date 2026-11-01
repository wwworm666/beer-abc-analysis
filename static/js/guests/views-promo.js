/* Вкладка «Акции» — эффективность скидок и промо (бывшая страница /discounts).

   Единственная вкладка раздела, которая берёт данные ЖИВЫМ запросом в iiko, а не
   из витрины guests.db: витрина не хранит тип скидки (в receipts есть только
   сумма скидки, измерения ItemSaleEventDiscountType нет), поэтому отчёт по
   конкретной акции из неё не собрать.

   Период и бар — из общей полосы сайта, как у остальных вкладок (решение владельца
   2026-11-01; своих полей дат и «Точки» больше нет). Имя точки для iiko — по таблице баров
   сайта (KStrip.barInfo(ключ).iiko_name). Отличия от остальных вкладок:
   1. Считается сразу при открытии и при смене периода или бара (ответ Р5: «без нажатия
      кнопки ничего не показывается»), но только за период до PROMO_AUTO_MAX_DAYS дней:
      живой запрос в iiko за год идёт десятки секунд, а «Всё время», выбранное на другой
      странице, запустило бы многоминутный запрос. Длиннее — по кнопке.
   2. Свой кэш: загруженный ответ живёт в модульной переменной вместе с периодом и точкой, и
      возврат на вкладку с тем же выбором перерисовывает его из памяти без нового запроса.

   Что сюда сознательно НЕ перенесено со старой страницы (см. docs/discounts.md
   и запись в CHANGELOG): вторая таксономия сегментов по числу визитов и «доунат»
   по ней, «гистограмма recency» из карточек, модалка гостя, клиентский пересчёт
   RFM-сегментов и клиентский CSV — всё это либо дублировало каноничные вкладки
   RFM/Активность/Гость, либо было недостижимым мёртвым кодом. */

Guests.registerView('promo', function (pane) {
    var G = Guests;

    // Загруженный ответ и параметры, на которых он получен. Модульная область:
    // переживает переключение вкладок, но не перезагрузку страницы.
    if (!window.__promoState) {
        window.__promoState = { data: null, params: null, names: null, error: null };
    }
    var S = window.__promoState;
    // Сразу считается период не длиннее года (366 дней — с високосным); длиннее — по кнопке.
    var PROMO_AUTO_MAX_DAYS = 366;

    // --------------------------------------------------------- параметры
    // Живой OLAP ждёт имя точки iiko: оно берётся из таблицы баров сайта (полоса) и сверяется со
    // списком точек страницы (config.bars). Нет совпадения — все точки и подпись об этом, а не
    // запрос с именем, которого iiko не знает.
    function pageBar() {
        if (!G.state.bar) return { name: '', unknown: false };
        var strip = window.KStrip;
        var info = strip && strip.barInfo ? strip.barInfo(G.state.bar) : null;
        var name = info ? info.iiko_name : G.barName(G.state.bar);
        var known = (G.config.bars || []).indexOf(name) >= 0;
        return { name: known ? name : '', unknown: !known };
    }
    function current() {
        var bar = pageBar();
        return { from: G.state.period.start, to: G.state.period.end, bar: bar.name,
                 barUnknown: bar.unknown, promo: pane.dataset.ppromo || '' };
    }
    function days(p) {
        var a = new Date(p.from + 'T00:00:00'), b = new Date(p.to + 'T00:00:00');
        return Math.round((b - a) / 86400000) + 1;
    }
    function sameScope(a, b) {
        return !!a && !!b && a.from === b.from && a.to === b.to && a.bar === b.bar;
    }

    // --------------------------------------------------------- контролы
    // Акция — фильтр загруженного ответа (в запрос не уходит). busy — идёт запрос: выбор акции
    // заблокирован, список ещё не пришёл.
    function controls(p, busy) {
        var dis = busy ? ' disabled' : '';
        var promos = (S.names || []).map(function (n) {
            return '<option value="' + G.esc(n) + '"' +
                (p.promo === n ? ' selected' : '') + '>' + G.esc(n) + '</option>';
        }).join('');
        return '<div class="gcard promo-panel">' +
            '<div class="promo-controls">' +
              '<label class="promo-field"><span>Акция</span><select id="promoName"' + dis + '>' +
                '<option value="">Все акции</option>' + promos + '</select></label>' +
            '</div>' +
            '</div>';
    }

    function bind() {
        var promoSel = document.getElementById('promoName');
        if (promoSel) promoSel.addEventListener('change', function () {
            pane.dataset.ppromo = promoSel.value;
            if (S.data) render();
        });
        var btn = document.getElementById('promoLoad');
        if (btn) btn.addEventListener('click', function () { load(current()); });
    }

    // --------------------------------------------------------- загрузка
    // Отдельного запроса за списком акций нет намеренно. Во-первых, отчёт
    // /api/discount-analyze сам возвращает discount_names за запрошенный
    // диапазон и точку. Во-вторых, фильтр акции работает по УЖЕ загруженному
    // ответу (в запрос акция не передаётся вообще), поэтому выбирать её до
    // загрузки бессмысленно — а лишний вызов лез бы в iiko при открытии вкладки,
    // ровно то, чего эта вкладка обязана не делать.

    // Поколение запроса: побеждает последний запущенный запрос, а не последний
    // ответивший. Без этого быстрая смена периода в полосе могла показать данные
    // не того периода, который выбран.
    var gen = 0;

    function load(p) {
        var my = ++gen;
        S.error = null;
        pane.innerHTML = controls(p, true) +
            '<div class="gcard"><div class="pane-loading">Запрашиваю iiko за ' +
            G.fmtDate(p.from) + ' — ' + G.fmtDate(p.to) + ' (живой запрос, не витрина: ' +
            'десятки секунд)…</div></div>';
        bind();
        return G.post('/api/discount-analyze',
                      { bar: p.bar || null, date_from: p.from, date_to: p.to })
            .then(function (j) {
                if (my !== gen) return;            // ответ устаревшего запроса
                S.data = j;
                S.params = { from: p.from, to: p.to, bar: p.bar, barUnknown: p.barUnknown };
                if (j.discount_names) S.names = j.discount_names;
                // Выбранная акция могла исчезнуть из списка (сузили период или
                // выбрали другую точку) — иначе экран пустой, а в селекте выбор.
                if (p.promo && S.names.indexOf(p.promo) < 0) pane.dataset.ppromo = '';
                render();
            })
            .catch(function (e) {
                if (my !== gen) return;
                S.error = e.message;
                render();
            });
    }

    // --------------------------------------------------------- расчёты
    // Служебное имя сводного ведра «все акции» в ответе. Сервер считает его сам,
    // и это принципиально: тип скидки — измерение ПОЗИЦИИ чека, поэтому один чек
    // (пиво по одной акции, еда по другой) лежит в множествах обеих акций.
    // Сложить их количества на клиенте нельзя — чеки удвоятся, средний чек
    // упадёт вдвое. Именно так и было, пока сводку собирал клиент.
    var ALL = '__all__';

    function bucketOf(promo) {
        return promo || ALL;
    }

    function guestsOf(promo) {
        var d = S.data;
        if (!d || !d.discounts) return [];
        return (d.discounts[bucketOf(promo)] || []).slice();
    }

    // Позиции гостя. В сводном ведре их намеренно нет (не дублируем ответ), но
    // склеить их по акциям безопасно: у строки OLAP ровно один тип скидки,
    // поэтому дублей между ведрами не бывает.
    function dishesOf(promo, card) {
        var d = S.data;
        if (!d || !d.discounts) return [];
        if (promo) {
            var one = (d.discounts[promo] || []).filter(function (g) {
                return g.card_number === card;
            })[0];
            return (one && one.dishes) || [];
        }
        var out = [];
        Object.keys(d.discounts).forEach(function (name) {
            if (name === ALL) return;
            d.discounts[name].forEach(function (g) {
                if (g.card_number === card) out = out.concat(g.dishes || []);
            });
        });
        return out;
    }

    // Давность и частоту гостя считает СЕРВЕР — и для конкретной акции, и для
    // сводного ведра, по фактической длине запрошенного диапазона
    // (routes/analysis.py, period_days). Клиент их не пересчитывает: именно
    // клиентский пересчёт на старой странице делил на захардкоженные 180 дней,
    // из-за чего частота скакала от того, стоит ли фильтр по акции.

    function storesOf(promo) {
        var d = S.data;
        if (!d || !d.stores_summary) return [];
        return (d.stores_summary[bucketOf(promo)] || []).slice();
    }

    // Продажи без карты лояльности сервер складывает в ОДНУ запись с
    // card_number = 'Без карты'. Это не человек: у неё визиты почти каждый день,
    // и в счётчике гостей, средней давности и частоте она всё искажает.
    // Держим её отдельно и показываем строкой, а не в сегментации.
    var NO_CARD = 'Без карты';

    function splitNoCard(guests) {
        var real = [], noCard = null;
        guests.forEach(function (g) {
            if (g.card_number === NO_CARD) noCard = g;
            else real.push(g);
        });
        return { real: real, noCard: noCard };
    }

    function totals(stores) {
        // Считаем по сводке точек: она полнее гостевой, потому что включает и
        // продажи без карты. Значения приходят из сводного ведра сервера, где
        // чеки уже дедуплицированы по ключу «дата + точка + номер».
        var storeOrders = 0, storeSum = 0, storeDisc = 0;
        stores.forEach(function (s) {
            storeOrders += s.orders_count || 0;
            storeSum += s.sum_with_discount || 0;
            storeDisc += s.discount_sum || 0;
        });
        var full = storeSum + storeDisc;
        return {
            revenue_full: full,
            revenue_with_discount: storeSum,
            discount_given: storeDisc,
            depth_pct: full > 0 ? storeDisc / full * 100 : 0,
            avg_check: storeOrders > 0 ? storeSum / storeOrders : 0,
            orders: storeOrders
        };
    }

    // --------------------------------------------------------- отрисовка
    function render() {
        var p = current();
        var html = controls(p);

        // Ошибка показывается НАД данными, а не вместо них: сохранённый отчёт
        // остаётся доступен, иначе одна неудачная перезагрузка прятала уже
        // загруженные цифры до следующего успешного запроса.
        if (S.error) {
            html += '<div class="gcard"><div class="pane-error">Ошибка: ' +
                G.esc(S.error) + '</div></div>';
        }
        if (!S.data) {
            pane.innerHTML = html; bind(); return;
        }

        var split = splitNoCard(guestsOf(p.promo));
        var guests = split.real;
        var stores = storesOf(p.promo);
        var t = totals(stores);
        t.guests = guests.length;
        t.noCard = split.noCard;
        var rangeNote = 'Период: ' + G.fmtDate(S.params.from) + ' — ' +
            G.fmtDate(S.params.to) +
            (S.params.bar ? ' · точка: ' + G.esc(S.params.bar)
                : (S.params.barUnknown ? ' · все точки: бар не найден среди точек iiko' : ' · все точки')) +
            (p.promo ? ' · акция: ' + G.esc(p.promo) : ' · все акции');

        html += '<div class="metric-grid">' +
            G.metricCard('promo_revenue_full', 'Выручка без скидки',
                G.fmtMoney(t.revenue_full), 'что стоило бы по прайсу') +
            G.metricCard('promo_revenue', 'Выручка со скидкой',
                G.fmtMoney(t.revenue_with_discount), 'что заплатили гости') +
            G.metricCard('promo_given', 'Отдали скидками',
                G.fmtMoney(t.discount_given), 'разница') +
            G.metricCard('promo_depth', 'Глубина скидки',
                G.fmtPct(t.depth_pct), 'доля от выручки без скидки') +
            G.metricCard('promo_avg_check', 'Средний чек',
                G.fmtMoney(t.avg_check), G.fmtNum(t.orders) + ' чеков') +
            '</div>' +
            '<div class="note-line">' + rangeNote + '</div>';

        html += renderStores(stores, t);
        html += renderGuests(guests, t);
        html += G.howBlock(['promo_revenue_full', 'promo_given', 'promo_depth',
                            'promo_avg_check', 'promo_guests', 'order', 'visit']);
        pane.innerHTML = html;
        bind();
        bindStoreDrill();
        bindGuestTable(guests);

        if (stores.length > 1) {
            var pal = GCharts.palette();
            GCharts.bar('promoStoreChart',
                stores.map(function (s) { return s.store; }),
                [{ label: 'Отдали скидками', data: stores.map(function (s) { return s.discount_sum; }),
                   backgroundColor: pal.accent, borderRadius: 6 }],
                {});
        }
    }

    function renderStores(stores, t) {
        if (!stores.length) {
            return '<div class="gcard"><div class="note-line">За выбранный ' +
                'период по этой акции продаж со скидкой нет.</div></div>';
        }
        var rows = stores.map(function (s) {
            var full = s.sum_with_discount + s.discount_sum;
            return '<tr><td><button class="promo-drill" data-store="' +
                G.esc(s.store) + '">' + G.esc(s.store) + '</button></td>' +
                '<td class="num">' + G.fmtNum(s.orders_count) + '</td>' +
                '<td class="num">' + G.fmtNum(s.guests_count) + '</td>' +
                '<td class="num">' + G.fmtMoney(full) + '</td>' +
                '<td class="num">' + G.fmtMoney(s.sum_with_discount) + '</td>' +
                '<td class="num">' + G.fmtMoney(s.discount_sum) + '</td>' +
                '<td class="num">' + G.fmtPct(full > 0 ? s.discount_sum / full * 100 : 0) +
                '</td></tr>';
        }).join('');
        return '<div class="gcard"><h3>По точкам</h3>' +
            (stores.length > 1
                ? '<div class="chart-box"><canvas id="promoStoreChart"></canvas></div>' : '') +
            '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th>Точка</th><th class="num">Чеков</th>' +
            '<th class="num">Гостей' + G.helpIcon('promo_store_guests') + '</th>' +
            '<th class="num">Без скидки</th>' +
            '<th class="num">Со скидкой</th><th class="num">Отдали</th>' +
            '<th class="num">Глубина</th></tr></thead><tbody>' + rows +
            '</tbody></table></div>' +
            '<div class="note-line">Клик по точке — пересчитать всё по ней. ' +
            'Итого чеков: ' + G.fmtNum(t.orders) + '. Чеки считаются по ключу ' +
            '«дата + точка + номер», поэтому один номер в разные дни — два чека. ' +
            'Колонка «Гостей» — уникальные карты В ЭТОЙ точке, поэтому сумма по ' +
            'строкам больше общего числа гостей: кто ходил в два бара, посчитан ' +
            'в обоих.</div></div>';
    }

    function renderGuests(guests, t) {
        var noCardNote = t.noCard
            ? '<div class="note-line">Продажи без карты лояльности: ' +
              G.fmtMoney(t.noCard.sum_with_discount) + ' выручки, ' +
              G.fmtMoney(t.noCard.discount_sum) + ' скидок. Они не человек и в ' +
              'таблицу гостей, счётчик гостей и профиль не входят, но в метриках ' +
              'сверху и в разбивке по точкам учтены.</div>'
            : '';
        if (!guests.length) {
            return '<div class="gcard"><h3>Гости акции</h3><div class="note-line">' +
                'Ни один гость с картой лояльности не воспользовался акцией за ' +
                'этот период.</div>' + noCardNote + '</div>';
        }
        var profile = renderProfile(guests);
        return '<div class="gcard"><h3>Гости акции' + G.helpIcon('promo_guests') +
            '</h3>' + profile +
            '<div class="guest-search"><input type="text" id="promoFilter" ' +
            'placeholder="Фильтр по имени или номеру карты"></div>' +
            '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
            '<th class="num">№</th><th>Гость</th><th>Карта</th>' +
            '<th class="num">Визитов</th><th class="num">Чеков</th>' +
            '<th class="num">Выручка</th><th class="num">Скидка</th>' +
            '<th class="num">Ср. чек</th><th></th></tr></thead>' +
            '<tbody id="promoGuestRows"></tbody></table></div>' +
            '<div class="note-line" id="promoGuestNote"></div>' + noCardNote +
            '</div>';
    }

    // Таблица гостей рисуется отдельно: с поиском и кнопкой «показать всех».
    // Старая страница выводила всех сразу — при большом периоде это тысячи строк,
    // поэтому по умолчанию показываем 100 самых дорогих, но полный список
    // доступен в один клик, а не «обрезан навсегда».
    var PAGE = 100;

    function bindGuestTable(guests) {
        var tbody = document.getElementById('promoGuestRows');
        var note = document.getElementById('promoGuestNote');
        var input = document.getElementById('promoFilter');
        if (!tbody || !note) return;
        var showAll = pane.dataset.pall === '1';

        var sorted = guests.slice().sort(function (a, b) {
            return (b.sum_with_discount || 0) - (a.sum_with_discount || 0);
        });

        function filtered() {
            var q = ((input && input.value) || '').trim().toLowerCase();
            if (!q) return sorted;
            return sorted.filter(function (g) {
                return (g.customer_name || '').toLowerCase().indexOf(q) >= 0 ||
                       (g.card_number || '').toLowerCase().indexOf(q) >= 0;
            });
        }

        function draw() {
            var rows = filtered();
            var shown = showAll ? rows : rows.slice(0, PAGE);
            tbody.innerHTML = shown.map(function (g, i) {
                return '<tr><td class="num dim">' + (i + 1) + '</td>' +
                    '<td>' + (G.esc(g.customer_name) ||
                        '<span class="dim">без имени</span>') + '</td>' +
                    '<td class="dim">' + G.esc(g.card_number) + '</td>' +
                    '<td class="num">' + G.fmtNum(g.visits) + '</td>' +
                    '<td class="num">' + G.fmtNum(g.orders) + '</td>' +
                    '<td class="num">' + G.fmtMoney(g.sum_with_discount) + '</td>' +
                    '<td class="num">' + G.fmtMoney(g.discount_sum) + '</td>' +
                    '<td class="num">' + G.fmtMoney(g.avg_check) + '</td>' +
                    '<td><button class="promo-details" data-card="' +
                    G.esc(g.card_number) + '">блюда</button></td></tr>' +
                    '<tr class="promo-detail-row" data-for="' + G.esc(g.card_number) +
                    '" hidden><td colspan="9"></td></tr>';
            }).join('');
            note.innerHTML = 'Гостей: <b>' + G.fmtNum(rows.length) +
                '</b> (уникальные карты, не сумма по точкам)' +
                (!showAll && rows.length > PAGE
                    ? ' · показаны первые ' + PAGE + ' по выручке · ' +
                      '<button class="promo-details" id="promoShowAll">показать всех</button>'
                    : '') + '.';
            var all = document.getElementById('promoShowAll');
            if (all) all.addEventListener('click', function () {
                pane.dataset.pall = '1';
                showAll = true;
                draw();
            });
            bindGuestDetails();
        }

        if (input) input.addEventListener('input', draw);
        draw();
    }

    function renderProfile(guests) {
        var withRec = guests.filter(function (g) { return g.recency_days !== null; });
        if (!withRec.length) return '';
        var avgRec = withRec.reduce(function (s, g) { return s + g.recency_days; }, 0) / withRec.length;
        var churn = withRec.filter(function (g) { return g.recency_days > 60; }).length;
        var withFreq = guests.filter(function (g) { return g.frequency_per_week !== null; });
        var avgFreq = withFreq.length
            ? withFreq.reduce(function (s, g) { return s + g.frequency_per_week; }, 0) / withFreq.length
            : 0;
        return '<div class="metric-grid promo-profile">' +
            G.metricCard('promo_recency', 'Средняя давность',
                G.fmtNum(Math.round(avgRec)) + ' дн', 'с последнего визита до конца периода') +
            G.metricCard('promo_churn', 'Давно не были (60+ дн)',
                G.fmtPct(churn / withRec.length * 100), 'более 60 дней, ' +
                G.fmtNum(churn) + ' из ' + G.fmtNum(withRec.length)) +
            G.metricCard('promo_freq', 'Средняя частота',
                (Math.round(avgFreq * 100) / 100).toString().replace('.', ',') +
                ' виз/нед', 'внутри выбранного диапазона') +
            '</div>';
    }

    function bindStoreDrill() {
        pane.querySelectorAll('.promo-drill').forEach(function (b) {
            b.addEventListener('click', function () {
                // Точка — общий выбор бара сайта: её смена в полосе пересчитывает вкладку.
                var row = G.bars().filter(function (x) { return x.iiko_name === b.dataset.store; })[0];
                if (row) G.setBar(row.key);
            });
        });
    }

    function bindGuestDetails() {
        pane.querySelectorAll('.promo-details').forEach(function (b) {
            b.addEventListener('click', function () {
                var card = b.dataset.card;
                var row = pane.querySelector('.promo-detail-row[data-for="' +
                    (window.CSS && CSS.escape ? CSS.escape(card) : card) + '"]');
                if (!row) return;
                if (!row.hidden) { row.hidden = true; b.textContent = 'блюда'; return; }
                var cell = row.querySelector('td');
                if (!cell) return;
                cell.innerHTML = dishesTable(dishesOf(current().promo, card));
                row.hidden = false;
                b.textContent = 'скрыть';
            });
        });
    }

    function dishesTable(dishes) {
        if (!dishes || !dishes.length) {
            return '<div class="note-line">Позиции не пришли в ответе.</div>';
        }
        // Одна строка ответа = одна позиция чека, поэтому агрегируем по названию.
        var agg = {};
        dishes.forEach(function (d) {
            var a = agg[d.name] || (agg[d.name] = { name: d.name, count: 0, sum: 0, disc: 0 });
            a.count += 1;
            a.sum += d.sum_with_discount || 0;
            a.disc += d.discount_sum || 0;
        });
        var rows = Object.keys(agg).map(function (k) { return agg[k]; })
            .sort(function (a, b) { return b.disc - a.disc; })
            .map(function (a) {
                return '<tr><td>' + G.esc(a.name) + '</td>' +
                    '<td class="num">' + G.fmtNum(a.count) + '</td>' +
                    '<td class="num">' + G.fmtMoney(a.sum) + '</td>' +
                    '<td class="num">' + G.fmtMoney(a.disc) + '</td></tr>';
            }).join('');
        return '<div class="promo-dishes"><div class="gtable-wrap">' +
            '<table class="gtable"><thead><tr><th>Позиция</th>' +
            '<th class="num">Раз</th><th class="num">Выручка</th>' +
            '<th class="num">Скидка</th></tr></thead><tbody>' + rows +
            '</tbody></table></div></div>';
    }

    // Период длиннее PROMO_AUTO_MAX_DAYS: не считаем сами — кнопка с числом дней.
    function renderLong(p) {
        pane.innerHTML = controls(p) + '<div class="gcard"><div class="note-line">Акции считаются ' +
            'живым запросом в iiko: сразу — за период до ' + PROMO_AUTO_MAX_DAYS + ' дней. Выбран ' +
            'период ' + G.fmtNum(days(p)) + ' дней (' + G.fmtDate(p.from) + ' — ' + G.fmtDate(p.to) +
            ') — запрос займёт несколько минут.</div>' +
            '<button type="button" class="sync-btn" id="promoLoad">Посчитать за ' +
            G.fmtNum(days(p)) + ' дней</button></div>';
        bind();
    }

    // --------------------------------------------------------- вход
    // Тот же период и точка, что у загруженного ответа, — из памяти; иначе — запрос сразу
    // (период до PROMO_AUTO_MAX_DAYS дней) или кнопка (длиннее).
    var start = current();
    if (S.data && sameScope(S.params, start)) {
        render();
    } else if (days(start) > PROMO_AUTO_MAX_DAYS) {
        renderLong(start);
    } else {
        return load(start);
    }
});

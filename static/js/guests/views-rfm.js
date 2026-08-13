/* Вкладка «RFM» (ТЗ §7) — ЕДИНСТВЕННАЯ RFM-сегментация проекта.

   До слияния RFM жил в двух местах с разными моделями: здесь (окно 365 дней,
   пороги 260/104/52/12 визитов за год, гость = канонизированный телефон из
   витрины) и на странице /discounts (визиты в неделю за произвольный период,
   пороги 3/2/0,8/0,3, гость = сырой номер карты, плюс склеенный псевдогость
   «Без карты»). Цифры не совпадали. Канон — этот: пороги утверждены владельцем
   2026-07-18, считается по витрине без обращений к iiko.

   Со старой страницы сюда перенесены точечная диаграмма, гистограмма давности и
   фильтр по точке — всё, чего здесь не хватало. Клиентский пересчёт сегментов и
   клиентский CSV не перенесены: сегмент приходит с сервера по каждому гостю,
   выгрузка тоже серверная (единый источник истины). */

Guests.registerView('rfm', function (pane) {
    var G = Guests;
    // Порог, после которого точек на диаграмме столько, что она перестаёт
    // читаться, а браузер — тормозить. Прореживаем РОВНОМЕРНО и говорим об этом.
    var SCATTER_MAX = 2500;

    function venue() { return pane.dataset.rvenue || ''; }

    function render() {
        var v = venue();
        pane.innerHTML = '<div class="pane-loading">Загрузка…</div>';
        return G.api('/api/guests/rfm', v ? { store: v } : {}).then(function (resp) {
            var d = resp.data;
            var segTitles = {
                CHAMPIONS: 'Чемпионы', LOYAL: 'Лояльные', NEW: 'Новички',
                AT_RISK: 'Под риском', CHURNED: 'Уходящие', POTENTIAL: 'Потенциальные'
            };
            var pal = GCharts.palette();
            // Шесть РАЗЛИЧИМЫХ цветов: на точечной диаграмме сегменты кодируются
            // только цветом (размер занят выручкой), и одинаковый цвет у двух
            // содержательно противоположных сегментов делает легенду бесполезной.
            // «Новички» и «Под риском» раньше были оба --warning.
            var segColors = {
                CHAMPIONS: pal.success,
                LOYAL: pal.accent,
                NEW: '#2563EB',        // синий: свежий первый визит
                AT_RISK: pal.warning,  // янтарный: тревога
                CHURNED: pal.danger,
                POTENTIAL: pal.text
            };
            // Пояснение к каждому сегменту: раньше все шесть карточек открывали
            // один и тот же тултип про окно и пороги, а правило отнесения к
            // сегменту в интерфейсе не описывалось нигде.
            var segFormula = {
                CHAMPIONS: 'rfm_seg_champions', LOYAL: 'rfm_seg_loyal',
                NEW: 'rfm_seg_new', AT_RISK: 'rfm_seg_at_risk',
                CHURNED: 'rfm_seg_churned', POTENTIAL: 'rfm_seg_potential'
            };

            var html = venueSwitch(d);

            // Карточки сегментов кликабельны: клик подставляет сегмент в фильтр
            // таблицы. На старой странице это было, и без этого «увидел 120
            // уходящих» не превращается в «вот их список».
            html += '<div class="metric-grid">';
            d.segments.forEach(function (s) {
                var title = segTitles[s.segment] || s.segment;
                html += '<div class="rfm-seg-pick" data-seg="' + G.esc(title) + '">' +
                    G.metricCard(segFormula[s.segment] || 'rfm', title,
                        G.fmtNum(s.count),
                        G.fmtPct(s.share_pct) + ' · ' + G.fmtMoney(s.revenue)) +
                    '</div>';
            });
            html += '</div>';

            html += '<div class="note-line">Окно — 12 месяцев на дату среза (' +
                G.fmtDate(d.window_start) + ' — ' + G.fmtDate(d.asof) + '). ' +
                'Переключатель периода вверху сдвигает дату среза, длину окна он ' +
                'не меняет.' +
                (d.venue ? ' Точка: <b>' + G.esc(d.venue_name) + '</b> — R, F и M ' +
                    'считаются только по чекам этой точки, поэтому сумма по четырём ' +
                    'точкам больше сетевой: гость двух баров попадает в оба среза.'
                    : ' Считается по всей сети.') + '</div>';

            html += '<div class="gcard-grid-2">';
            html += '<div class="gcard"><h3>Давность последнего визита' +
                G.helpIcon('rfm_recency_hist') + '</h3>' +
                '<div class="chart-box"><canvas id="rfmRecencyChart"></canvas></div></div>';
            html += '<div class="gcard"><h3>Частота против давности' +
                G.helpIcon('rfm_scatter') + '</h3>' +
                '<div class="chart-box"><canvas id="rfmScatterChart"></canvas></div>' +
                '<div class="note-line" id="rfmScatterNote"></div></div>';
            html += '</div>';

            var csvUrl = '/api/guests/rfm?period_type=' + G.state.periodType +
                '&anchor=' + resp.meta.p_end + (d.venue ? '&store=' + encodeURIComponent(d.venue) : '') +
                '&export=csv';
            html += '<div class="gcard"><h3>Гости в окне 12 месяцев (' +
                G.fmtNum(d.total_guests) + ')' + G.helpIcon('rfm') +
                '</h3><div class="guest-search"><input type="text" id="rfmFilter" ' +
                'placeholder="Фильтр по имени, телефону, карте, сегменту">' +
                '<a class="sync-btn" href="' + csvUrl + '">Скачать CSV</a></div>' +
                '<div class="gtable-wrap"><table class="gtable"><thead><tr>' +
                '<th>Гость</th><th>Телефон</th><th>Карта</th>' +
                '<th>Последний визит</th><th class="num">Дней с визита</th>' +
                '<th class="num">Визитов (12 мес)</th><th class="num">Чеков</th>' +
                '<th class="num">Ср. чек</th><th class="num">Выручка (12 мес)</th>' +
                '<th>Сегмент</th></tr></thead><tbody id="rfmTbody"></tbody></table></div>' +
                '<div class="note-line" id="rfmMore"></div>' +
                '<div class="note-line">Пороги R: до ' + d.r_thresholds.join(' / ') +
                ' дней. Пороги F (визитов за окно 12 мес): ' + d.f_thresholds.join(' / ') +
                ' — постоянный (5+ в неделю) / частый (2+ в неделю) / раз в неделю / раз в месяц.</div></div>';

            html += G.howBlock(['rfm', 'rfm_recency_hist', 'rfm_scatter', 'visit', 'revenue']);
            pane.innerHTML = html;
            bindVenue();

            renderRecency(d, pal);
            renderScatter(d, segTitles, segColors);
            var table = bindTable(d, segTitles);
            bindSegmentPick(table);
        });
    }

    // Клик по карточке сегмента — фильтр таблицы по нему.
    function bindSegmentPick(table) {
        pane.querySelectorAll('.rfm-seg-pick').forEach(function (el) {
            el.addEventListener('click', function () {
                if (table) table.filterBy(el.dataset.seg);
            });
        });
    }

    function venueSwitch(d) {
        var v = d.venue || '';
        var items = [['', 'Вся сеть']].concat((d.venues || []).map(function (x) {
            return [x.key, x.name];
        }));
        return '<div class="sub-switch">' + items.map(function (it) {
            return '<button class="sub-btn' + (v === it[0] ? ' active' : '') +
                '" data-rvenue="' + G.esc(it[0]) + '">' + G.esc(it[1]) + '</button>';
        }).join('') + '</div>';
    }

    function bindVenue() {
        pane.querySelectorAll('.sub-btn[data-rvenue]').forEach(function (b) {
            b.addEventListener('click', function () {
                pane.dataset.rvenue = b.dataset.rvenue;
                // .catch обязателен: этот render() вызывается не из фреймворка,
                // и без обработчика отказ API оставил бы вкладку в «Загрузка…»
                // навсегда (ошибка ушла бы в unhandledrejection).
                render().catch(function (e) {
                    pane.innerHTML = '<div class="pane-error">Ошибка: ' +
                        G.esc(e.message) + '</div>';
                });
            });
        });
    }

    // Гистограмма давности по тем же порогам R, что и сегментация: иначе на
    // одном экране оказались бы две несовместимые шкалы дней.
    function renderRecency(d, pal) {
        var th = d.r_thresholds;   // [7, 14, 30, 60]
        // Последний бакет — строго БОЛЬШЕ последнего порога: сам порог попадает в
        // предыдущий бакет (условие r <= th[3]). Подпись «60+» это путала.
        var labels = ['0-' + th[0], (th[0] + 1) + '-' + th[1],
                      (th[1] + 1) + '-' + th[2], (th[2] + 1) + '-' + th[3],
                      (th[3] + 1) + ' и больше'];
        var buckets = [0, 0, 0, 0, 0];
        (d.guests || []).forEach(function (g) {
            var r = g.recency_days;
            if (r <= th[0]) buckets[0]++;
            else if (r <= th[1]) buckets[1]++;
            else if (r <= th[2]) buckets[2]++;
            else if (r <= th[3]) buckets[3]++;
            else buckets[4]++;
        });
        GCharts.bar('rfmRecencyChart', labels,
            [{ label: 'Гостей', data: buckets,
               backgroundColor: [pal.success, pal.success, pal.warning,
                                 pal.warning, pal.danger],
               borderRadius: 6 }],
            {});
    }

    function renderScatter(d, segTitles, segColors) {
        var guests = (d.guests || []).filter(function (g) { return g.frequency > 0; });
        var note = document.getElementById('rfmScatterNote');
        var shown = guests;
        var thinned = false;
        if (guests.length > SCATTER_MAX) {
            var step = Math.ceil(guests.length / SCATTER_MAX);
            shown = guests.filter(function (_, i) { return i % step === 0; });
            thinned = true;
        }
        // Радиус — выручка на визит, приведённая к 4..16 px.
        var perVisit = shown.map(function (g) { return g.monetary / g.frequency; });
        var maxPer = Math.max.apply(null, perVisit.concat([1]));
        var bySeg = {};
        shown.forEach(function (g, i) {
            var seg = g.segment;
            (bySeg[seg] || (bySeg[seg] = [])).push({
                x: g.frequency, y: g.recency_days,
                r: 4 + Math.round(perVisit[i] / maxPer * 12),
                _name: g.name || g.card_number || g.phone,
                _per: Math.round(perVisit[i])
            });
        });
        var datasets = Object.keys(bySeg).map(function (seg) {
            return {
                label: segTitles[seg] || seg,
                data: bySeg[seg],
                backgroundColor: (segColors[seg] || '#888') + 'cc'
            };
        });
        GCharts.scatter('rfmScatterChart', datasets, {
            xTitle: 'Визитов за 12 месяцев',
            yTitle: 'Дней с последнего визита',
            tooltip: function (ctx) {
                var p = ctx.raw;
                return p._name + ': ' + p.x + ' виз, ' + p.y + ' дн, ' +
                    p._per + ' ₽ за визит';
            }
        });
        if (note) {
            note.innerHTML = 'Размер точки — выручка за визит. ' +
                (thinned
                    ? 'Точек ' + G.fmtNum(guests.length) + ', на диаграмме показана ' +
                      'каждая ' + Math.ceil(guests.length / SCATTER_MAX) + '-я (' +
                      G.fmtNum(shown.length) + ') — иначе облако нечитаемо. ' +
                      'Таблица и CSV ниже содержат всех.'
                    : 'Показаны все ' + G.fmtNum(shown.length) + ' гостей с визитами в окне.');
        }
    }

    function bindTable(d, segTitles) {
        var PAGE = 50;
        var input = document.getElementById('rfmFilter');
        var tbody = document.getElementById('rfmTbody');
        var more = document.getElementById('rfmMore');
        if (!input || !tbody) return;

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
                    '<td class="dim">' + G.esc(g.card_number) + '</td>' +
                    '<td>' + G.fmtDate(g.last_visit) + '</td>' +
                    '<td class="num">' + G.fmtNum(g.recency_days) + '</td>' +
                    '<td class="num">' + G.fmtNum(g.frequency) + '</td>' +
                    '<td class="num">' + G.fmtNum(g.orders) + '</td>' +
                    '<td class="num">' + G.fmtMoney(g.avg_check) + '</td>' +
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
        return {
            filterBy: function (text) {
                input.value = text;
                renderRows();
                input.scrollIntoView({ block: 'center' });
            }
        };
    }

    return render();
});

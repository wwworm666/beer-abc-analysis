/* Блоки снимка на личной странице: деньги, KPI, показатели.

   Правило страницы (принцип №1 проекта, .claude/CLAUDE.md): у каждого числа
   видно, как оно посчитано. Причём тем виднее, чем дороже число человеку:

     - ДЕНЬГИ — формула стоит под каждой строкой ВСЕГДА, без раскрытий. Деньги
       единственная причина, по которой бармен откроет страницу дважды; спрятать
       формулу премии за «?» значит гарантировать вопрос «почему так мало» в
       чате вместо ответа на экране. Плюс на телефоне нет hover, а телефон здесь
       главный.
     - KPI — постоянный breakdown с подставленными числами и шкала 0..2 с
       подписанной целью: без риски на 1,0 шкала читается как «выполнил
       половину», хотя это «выполнил цель».
     - ПОКАЗАТЕЛИ — формула по тапу на «?»: их шестнадцать, и вечный текст под
       каждым превратил бы хвост страницы в простыню.

   Все тексты формул собираются ЗДЕСЬ и только здесь, чтобы формулировка в
   квитанции и в подсказке не разъехались.

   Подключать ПОСЛЕ common.js (нужны S.formatMoney/S.escapeHtml). */
(function () {
    'use strict';
    var S = window.Schedule;
    if (!S) return;

    var RUB = ' ₽';   // неразрывный пробел + знак рубля

    function esc(s) { return S.escapeHtml(s == null ? '' : String(s)); }
    function money(n) { return S.formatMoney(n || 0) + RUB; }
    // Числа с запятой как десятичным разделителем — как во всём приложении.
    function num(n, digits) {
        if (n == null || isNaN(n)) return '—';
        var d = digits == null ? 1 : digits;
        return (+n).toFixed(d).replace('.', ',').replace(/,0$/, '');
    }
    function pct(n, digits) { return n == null ? '—' : num(n, digits == null ? 1 : digits) + ' %'; }
    function plural(n, one, few, many) {
        var a = Math.abs(n) % 100, b = a % 10;
        if (a > 10 && a < 20) return many;
        if (b > 1 && b < 5) return few;
        if (b === 1) return one;
        return many;
    }
    function shifts(n) { return n + ' ' + plural(n, 'смена', 'смены', 'смен'); }

    // ==================== Деньги ====================

    function renderMoney(host, data) {
        var m = data.money;
        if (!m) { host.innerHTML = ''; return; }
        var rates = data.rates || {};
        var rows = [];

        // Часы по ролям: показываем каждую роль своей формулой, потому что
        // ставки разные («бармен» и «второй в смене»).
        var byRole = ((data.hours || {}).by_role) || [];
        rows.push(row('Часы по ставке', m.hours_pay, {
            formula: byRole.length
                ? byRole.map(function (r) {
                    return esc(r.role_name) + ' ' + num(r.hours) + ' ч x '
                        + money(r.rate_per_hour) + ' = ' + money(r.pay);
                }).join('<br>')
                : 'часы — из факта, который вы вводите в конце смены',
            note: 'часы берутся из факта смены, а не из кассовых смен iiko',
            excluded: (m.excluded_components || []).indexOf('hours_pay') !== -1
        }));

        var h = m.handover || {};
        rows.push(row('Приемка-передача смены', h.sum, {
            formula: money(h.rate) + ' x ' + shifts(h.paid_days || 0)
                + ' со сданной кассой (из ' + (h.base_days || 0) + ')',
            warn: h.unpaid_days
                ? shifts(h.unpaid_days) + ' без сданной кассы — не оплачены'
                : (h.manual_days ? shifts(h.manual_days) + ' со штрафом по кассе' : '')
        }));

        var dp = m.day_plan || {};
        rows.push(row('Премия за дневной план', dp.sum, {
            formula: money(dp.base_per_day) + ' x ' + shifts(dp.days_paid || 0)
                + ' с выручкой выше плана<br>+ '
                + num((dp.over_share || 0) * 100, 0) + '% от перевыполнения '
                + money(dp.overperformance),
            note: 'смены ниже плана в премию не входят'
        }));

        var k = m.kpi || {};
        rows.push(row('KPI-премия', k.sum, {
            formula: 'сумма по ' + ((data.kpi && data.kpi.items || []).length)
                + ' показателям, коэффициент смен ' + num(k.koef, 2),
            jump: 'Как считается — ниже, «Мои KPI»'
        }));

        var t = m.taxi || {};
        rows.push(row('Такси', t.sum, {
            formula: money(t.rate) + ' x ' + (t.day_shifts || 0) + ' '
                + plural(t.day_shifts || 0, 'полная дневная смена',
                         'полные дневные смены', 'полных дневных смен'),
            excluded: (m.excluded_components || []).indexOf('taxi') !== -1
        }));

        var l = m.late || {};
        if (l.count) {
            rows.push(row('Вычет дисциплина', -l.sum, {
                formula: l.count + ' ' + plural(l.count, 'опоздание', 'опоздания', 'опозданий')
                    + ': ' + lateSteps(l.count, l.step)
                    + (l.dates && l.dates.length ? '<br>' + l.dates.map(fmtDay).join(', ') : ''),
                note: 'штраф растёт на ' + money(l.step) + ' за каждое следующее',
                minus: true
            }));
        }

        var stamp = stampHtml(data);
        host.innerHTML = '<div class="me-card">' + stamp
            + '<div class="me-card-body">'
            + '<div class="me-h">Мои деньги<span class="me-h-sub">начислено на '
            + esc(fmtDay(data.today)) + '</span></div>'
            + '<div class="me-total-v">' + money(m.total) + '</div>'
            + '<div class="me-total-sub">за ' + shifts(m.shifts_count || 0)
            + ' из ' + ((data.norms || {}).shift_norm || '') + '</div>'
            + '<div class="me-rows">' + rows.join('') + '</div>'
            + '<div class="me-row is-total"><span class="me-row-n">Итого начислено</span>'
            + '<span class="me-row-v">' + money(m.total) + '</span></div>'
            + '<div class="me-note">' + esc((data.notes || {}).excel || '') + '<br>'
            + esc((data.notes || {}).accrued_to_date || '') + '</div>'
            + '</div></div>';
    }

    // Прогрессивный штраф: 250 + 500 + 750...
    function lateSteps(count, step) {
        var parts = [];
        for (var i = 1; i <= count && i <= 6; i++) parts.push(S.formatMoney(step * i));
        return parts.join(' + ') + RUB;
    }

    function row(name, value, opts) {
        opts = opts || {};
        var vClass = 'me-row-v' + (opts.minus ? ' is-minus' : '')
            + (opts.excluded ? ' is-excluded' : '');
        var lines = [];
        if (opts.formula) lines.push('<div class="me-row-f">' + opts.formula + '</div>');
        if (opts.warn) lines.push('<div class="me-row-f is-warn">' + esc(opts.warn) + '</div>');
        if (opts.note) lines.push('<div class="me-row-f">' + esc(opts.note) + '</div>');
        if (opts.jump) lines.push('<div class="me-row-f is-jump">' + esc(opts.jump) + '</div>');
        if (opts.excluded) {
            lines.push('<div class="me-row-f is-warn">в итог не включено: не удалось '
                + 'надёжно связать смены с вашим идентификатором</div>');
        }
        return '<div class="me-row"><span class="me-row-n">' + esc(name) + '</span>'
            + '<span class="' + vClass + '">' + money(value) + '</span></div>'
            + (lines.length ? '<div class="me-row-sub">' + lines.join('') + '</div>' : '');
    }

    // ==================== KPI ====================

    function renderKpi(host, data) {
        var kpi = data.kpi;
        if (!kpi) { host.innerHTML = ''; return; }
        if (kpi.status !== 'ok' || !(kpi.items || []).length) {
            host.innerHTML = '<div class="me-sub">Мои KPI</div>'
                + '<div class="me-empty">Цели на ' + esc(data.month_label || '')
                + ' не заданы или нет закрытых смен — KPI-премия за этот месяц не '
                + 'начисляется. Цели настраиваются на странице «Цели месяца».</div>';
            return;
        }
        var meta = data.kpi_meta || {};
        var maxRatio = meta.max_ratio || 2;
        var fund = meta.kpi_pool != null && meta.base_per_kpi != null
            ? money(meta.kpi_pool) + ' / ' + kpi.items.length + ' = '
              + money(meta.base_per_kpi) + ' за каждый показатель'
            : '';

        var cards = kpi.items.map(function (it) {
            return kpiCard(it, kpi, meta, maxRatio, data);
        }).join('');

        host.innerHTML = '<div class="me-sub" id="meKpiAnchor">Мои KPI</div>'
            + '<div class="me-card">' + stampHtml(data) + '<div class="me-card-body">'
            + (fund ? '<div class="me-kpi-fund">Фонд ' + fund + '</div>' : '')
            + '<div class="me-kpi-fund-sub">Коэффициент x' + num(kpi.koef, 2)
            + ' = ' + (kpi.total_shifts || 0) + ' ваших смен на точках с целями / '
            + (meta.norm_shifts || '') + '</div>'
            + '<div class="me-kpi-total">Итого KPI: ' + money(kpi.total_premium) + '</div>'
            + '</div></div>' + cards;
    }

    function kpiCard(it, kpi, meta, maxRatio, data) {
        var cat = (meta.metrics_catalog || {})[it.metric] || {};
        var unit = cat.unit || '';
        var dec = cat.decimals == null ? 1 : cat.decimals;
        var v = function (x) { return x == null ? '—' : num(x, dec) + (unit ? ' ' + unit : ''); };

        var ratio = it.ratio == null ? 0 : it.ratio;
        var fillPct = Math.max(0, Math.min(100, ratio / maxRatio * 100));
        var markPct = 1 / maxRatio * 100;

        // Текст формулы меняется по ситуации: у потолка проговариваем
        // ограничение, ниже минимума — что премии нет вообще. Молчаливый ноль
        // здесь читался бы как ошибка расчёта.
        var calc;
        if (it.min != null && it.fact != null && it.fact < it.min) {
            calc = 'Факт ' + v(it.fact) + ' ниже минимума ' + v(it.min)
                 + ' — множитель 0, премия 0' + RUB;
        } else {
            calc = 'Множитель = (факт − минимум) / (цель − минимум)<br>= ('
                 + num(it.fact, dec) + ' − ' + num(it.min, dec) + ') / ('
                 + num(it.target, dec) + ' − ' + num(it.min, dec) + ') = ' + num(ratio, 2);
            if (ratio >= maxRatio) {
                calc += '<br>Множитель ограничен диапазоном 0…' + num(maxRatio, 0);
            }
            calc += '<br>Премия = ' + num(ratio, 2) + ' x ' + money(meta.base_per_kpi)
                 + ' x ' + num(kpi.koef, 2) + ' = ' + money(it.premium);
        }

        var locs = kpi.shifts_per_location || {};
        var locRows = Object.keys(locs).map(function (name) {
            return '<div class="me-row"><span class="me-row-n">' + esc(name)
                + '</span><span class="me-row-v">' + shifts(locs[name]) + '</span></div>';
        }).join('');

        return '<div class="me-card"><div class="me-card-body">'
            + '<div class="me-kpi-head"><span class="me-kpi-name">' + esc(it.name)
            + '</span><span class="me-kpi-prem">' + money(it.premium)
            + '<span class="me-kpi-max"> / ' + money(meta.base_per_kpi) + '</span></span></div>'
            + '<div class="me-kpi-nums">'
            + kpiNum('факт', v(it.fact)) + kpiNum('цель', v(it.target))
            + kpiNum('минимум', v(it.min)) + kpiNum('множитель', 'x' + num(ratio, 2))
            + '</div>'
            + '<div class="me-kpi-bar"><span class="me-kpi-fill" style="width:' + fillPct
            + '%"></span><span class="me-kpi-mark" style="left:' + markPct + '%"></span></div>'
            + '<div class="me-kpi-scale"><span>0</span><span>цель</span><span>'
            + num(maxRatio, 0) + '</span></div>'
            + '<div class="me-kpi-calc">' + calc + '</div>'
            + (locRows ? fold('Цели взвешены по вашим сменам', locRows
                + '<div class="me-row-f">Где вы работали больше, та цель весит сильнее.</div>')
                : '')
            + '</div></div>';
    }

    function kpiNum(label, value) {
        return '<div class="me-kpi-num"><div class="me-kpi-num-l">' + esc(label)
            + '</div><div class="me-kpi-num-v">' + esc(value) + '</div></div>';
    }

    // ==================== Показатели ====================

    // Формулы показателей: числа подставляются, единицы указываются.
    // Формулировки согласованы с docs/salary-instruction.txt.
    function metricFormulas(m) {
        var f = {};
        f.avg_check = 'Средний чек = выручка / количество чеков = '
            + S.formatMoney(m.total_revenue) + ' / ' + (m.total_checks || 0)
            + ' = ' + money(m.avg_check);
        f.draft_share = 'Доля розлива = выручка разливного / вся выручка = '
            + S.formatMoney(m.draft_revenue) + ' / ' + S.formatMoney(m.total_revenue)
            + ' = ' + pct(m.draft_share);
        f.bottles_share = 'Доля фасовки = выручка фасовки / вся выручка = '
            + S.formatMoney(m.bottles_revenue) + ' / ' + S.formatMoney(m.total_revenue)
            + ' = ' + pct(m.bottles_share);
        f.kitchen_share = 'Доля кухни = выручка кухни / вся выручка = '
            + S.formatMoney(m.kitchen_revenue) + ' / ' + S.formatMoney(m.total_revenue)
            + ' = ' + pct(m.kitchen_share);
        f.other_share = 'Прочее — не напитки и не еда: наборы, чай, кофе, вода. '
            + 'Доли розлива, фасовки, кухни и прочего вместе дают 100%.';
        f.avg_markup = 'Средняя наценка взвешена по себестоимости: наценка каждой '
            + 'категории умножается на её себестоимость, сумма делится на общую '
            + 'себестоимость. Итог: ' + pct(m.avg_markup);
        f.discount_percent = 'Скидки = сумма скидок / выручка до скидок = '
            + S.formatMoney(m.discount_sum) + ' / '
            + S.formatMoney((m.total_revenue || 0) + (m.discount_sum || 0))
            + ' = ' + pct(m.discount_percent);
        f.revenue_per_shift = 'Выручка / смена = выручка / количество смен = '
            + S.formatMoney(m.total_revenue) + ' / ' + (m.shifts_count || 0)
            + ' = ' + money(m.revenue_per_shift);
        f.revenue_per_hour = 'Выручка / час = выручка / часы кассовых смен = '
            + S.formatMoney(m.total_revenue) + ' / ' + num(m.work_hours)
            + ' = ' + money(m.revenue_per_hour);
        f.plan_fact_percent = 'План / факт = выручка / план ваших смен = '
            + S.formatMoney(m.total_revenue) + ' / ' + S.formatMoney(m.plan_revenue)
            + ' = ' + pct(m.plan_fact_percent)
            + '. План смены — план точки на этот день; пятница и суббота весят 2x.';
        f.cancelled_count = 'Отмены и возвраты — сколько заказов было отменено или '
            + 'возвращено за месяц.';
        f.loyalty_cards_count = 'Новые карты лояльности — уникальные телефоны, '
            + 'впервые оформленные на ваших чеках.';
        f.late_count = 'Опоздания — сколько раз система зафиксировала опоздание. '
            + 'Штраф прогрессивный: 250, 500, 750 руб. и далее. Считается за факт '
            + 'опоздания, а не за смену.';
        f.total_checks = 'Чеки — количество уникальных заказов, пробитых под вами.';
        f.total_revenue = 'Выручка — сумма по закрытым чекам за месяц, после скидок.';
        return f;
    }

    function renderMetrics(host, data) {
        var m = data.metrics;
        if (!m) { host.innerHTML = ''; return; }
        if (m.status !== 'ok') {
            host.innerHTML = '<div class="me-sub">Мои показатели</div>'
                + '<div class="me-empty">Показатели продаж за ' + esc(data.month_label || '')
                + ' не посчитаны: не удалось однозначно сопоставить ваше имя с именем '
                + 'в отчётах продаж iiko. Нули здесь были бы обманом, поэтому '
                + 'показатели скрыты.</div>';
            return;
        }
        var f = metricFormulas(m);

        var tiles = [
            tile('Выручка', money(m.total_revenue), f.total_revenue),
            tile('Средний чек', money(m.avg_check), f.avg_check),
            tile('План / факт', pct(m.plan_fact_percent), f.plan_fact_percent)
        ].join('');

        var groups = [
            fold('Структура продаж', 'розлив ' + pct(m.draft_share), [
                mrow('Розлив', pct(m.draft_share), f.draft_share),
                mrow('Фасовка', pct(m.bottles_share), f.bottles_share),
                mrow('Кухня', pct(m.kitchen_share), f.kitchen_share),
                mrow('Прочее', pct(m.other_share), f.other_share)
            ].join('')),
            fold('Чеки и гости', (m.total_checks || 0) + ' чеков', [
                mrow('Чеков', String(m.total_checks || 0), f.total_checks),
                mrow('Скидки', pct(m.discount_percent), f.discount_percent),
                mrow('Отмены и возвраты', String(m.cancelled_count || 0), f.cancelled_count),
                mrow('Новые карты', String(m.loyalty_cards_count || 0), f.loyalty_cards_count)
            ].join('')),
            fold('Отдача и дисциплина', money(m.revenue_per_shift) + ' / смена', [
                mrow('Выручка / смена', money(m.revenue_per_shift), f.revenue_per_shift),
                mrow('Выручка / час', money(m.revenue_per_hour), f.revenue_per_hour),
                mrow('Средняя наценка', pct(m.avg_markup), f.avg_markup),
                mrow('Опоздания', String(m.late_count || 0), f.late_count)
            ].join(''))
        ];
        var top = (m.top_beers || []).slice(0, 7);
        if (top.length) {
            groups.push(fold('Топ сортов пива', esc(top[0].name || ''),
                top.map(function (b) {
                    return '<div class="me-row"><span class="me-row-n">' + esc(b.name)
                        + '</span><span class="me-row-v">' + money(b.revenue) + '</span></div>';
                }).join('')));
        }

        host.innerHTML = '<div class="me-sub">Мои показатели</div>'
            + '<div class="me-card">' + stampHtml(data) + '<div class="me-card-body">'
            + '<div class="me-tiles">' + tiles + '</div>'
            + '<div class="me-folds">' + groups.join('') + '</div>'
            + '</div></div>';
    }

    function tile(label, value, formula) {
        return '<div class="me-tile"><div class="me-tile-l">' + esc(label)
            + help(formula) + '</div><div class="me-tile-v">' + esc(value) + '</div>'
            + formulaBox(formula) + '</div>';
    }

    function mrow(label, value, formula) {
        return '<div class="me-mrow"><div class="me-row">'
            + '<span class="me-row-n">' + esc(label) + help(formula) + '</span>'
            + '<span class="me-row-v">' + esc(value) + '</span></div>'
            + formulaBox(formula) + '</div>';
    }

    // Кружок «?»: кнопка, а не span — на телефоне нет hover, и title не открыть.
    function help(formula) {
        if (!formula) return '';
        return ' <button type="button" class="me-help" data-help aria-expanded="false"'
            + ' title="' + esc(stripTags(formula)) + '">?</button>';
    }
    function formulaBox(formula) {
        if (!formula) return '';
        return '<div class="me-formula" hidden>' + formula + '</div>';
    }
    function stripTags(s) { return String(s).replace(/<[^>]*>/g, ' '); }

    // Сворачиваемый блок — тот же паттерн, что .sc-fold на /schedule.
    function fold(title, subOrBody, maybeBody) {
        var sub = maybeBody === undefined ? '' : subOrBody;
        var body = maybeBody === undefined ? subOrBody : maybeBody;
        return '<div class="sc-fold"><button type="button" class="sc-fold-head" data-fold-toggle>'
            + '<span class="sc-fold-title">' + esc(title) + '</span>'
            + '<span class="sc-fold-sub">' + sub + '</span>'
            + '<span class="sc-fold-chev">&#9662;</span></button>'
            + '<div class="sc-fold-body" hidden>' + body + '</div></div>';
    }

    // ==================== Общее ====================

    function stampHtml(data) {
        var snap = data.snapshot || {};
        if (!snap.refreshed_at) return '';
        var cls = 'me-stamp' + (snap.stale ? ' is-stale' : '');
        var text = 'данные на ' + fmtStamp(snap.refreshed_at)
            + (snap.stale ? ' — давно не обновлялись' : '');
        return '<div class="' + cls + '">' + esc(text) + '</div>';
    }

    function fmtStamp(iso) {
        if (!iso || iso.length < 16) return '';
        return iso.slice(8, 10) + '.' + iso.slice(5, 7) + ', ' + iso.slice(11, 16);
    }
    function fmtDay(iso) {
        if (!iso || iso.length < 10) return '';
        return iso.slice(8, 10) + '.' + iso.slice(5, 7);
    }

    // Драйвер раскрытий: одна делегированная привязка на контейнер, а не по
    // слушателю на каждую кнопку — блоки перерисовываются целиком.
    function bindDisclosures(root) {
        if (!root || root._meBound) return;
        root._meBound = true;
        root.addEventListener('click', function (e) {
            var help = e.target.closest && e.target.closest('[data-help]');
            if (help) {
                var box = help.closest('.me-tile, .me-mrow');
                var formula = box && box.querySelector('.me-formula');
                if (formula) {
                    var open = formula.hidden;
                    formula.hidden = !open;
                    help.setAttribute('aria-expanded', open ? 'true' : 'false');
                }
                return;
            }
            var head = e.target.closest && e.target.closest('[data-fold-toggle]');
            if (head) {
                var fold = head.parentElement;
                var b = fold.querySelector('.sc-fold-body');
                if (b) { b.hidden = !b.hidden; fold.classList.toggle('is-open', !b.hidden); }
            }
        });
    }

    window.Me = window.Me || {};
    window.Me.snapshot = {
        renderMoney: renderMoney,
        renderKpi: renderKpi,
        renderMetrics: renderMetrics,
        bindDisclosures: bindDisclosures,
        fmtStamp: fmtStamp
    };
})();

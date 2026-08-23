/* Блоки снимка на личной странице: деньги, KPI, показатели.

   Оформление — по макету владельца (Claude Design «Личный кабинет»): строка
   «название — точечный лидер — сумма — шеврон», раскрывающаяся в блок формулы;
   карточка на каждый KPI с четырьмя числами и шкалой множителя; показатели
   тремя большими плитками и сгруппированными карточками.

   Принцип №1 проекта (.claude/CLAUDE.md) выполняется через раскрытия: у каждого
   числа есть формула с подставленными значениями. Раскрытие — это <details>,
   то есть тап, а не hover: на телефоне hover недоступен, а телефон здесь
   главный. Все тексты формул собираются ЗДЕСЬ и только здесь, чтобы
   формулировка в квитанции и в подсказке не разъехалась.

   Подключать ПОСЛЕ common.js (нужны S.formatMoney/S.escapeHtml). */
(function () {
    'use strict';
    var S = window.Schedule;
    if (!S) return;

    var RUB = ' ₽';   // неразрывный пробел + знак рубля

    function esc(s) { return S.escapeHtml(s == null ? '' : String(s)); }
    function money(n) { return S.formatMoney(n || 0) + RUB; }
    function num(n, digits) {
        if (n == null || isNaN(n)) return '—';
        var d = digits == null ? 1 : digits;
        return (+n).toFixed(d).replace('.', ',').replace(/,0$/, '');
    }
    function pct(n, d) { return n == null ? '—' : num(n, d == null ? 1 : d) + ' %'; }
    function plural(n, one, few, many) {
        var a = Math.abs(n) % 100, b = a % 10;
        if (a > 10 && a < 20) return many;
        if (b > 1 && b < 5) return few;
        if (b === 1) return one;
        return many;
    }
    function shifts(n) { return n + ' ' + plural(n, 'смена', 'смены', 'смен'); }
    function zero(v) { return !v ? ' is-zero' : ''; }

    // Шеврон раскрытия — общий для всех строк.
    var CHV = '<svg class="me-chv" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">'
        + '<path d="M2 3.5 5 6.5 8 3.5" stroke="currentColor" stroke-width="1.6" fill="none"'
        + ' stroke-linecap="round" stroke-linejoin="round" opacity=".55"/></svg>';

    // Строка «название ... сумма» с раскрытием в формулу.
    function row(name, valueHtml, boxHtml, opts) {
        opts = opts || {};
        return '<details class="me-row"' + (opts.open ? ' open' : '') + '>'
            + '<summary>'
            + (opts.swatch ? '<span class="me-swatch" style="background:' + opts.swatch + '"></span>' : '')
            + '<span class="me-row-n">' + esc(name) + '</span>'
            + '<span class="me-row-lead"></span>'
            + '<span class="me-row-v' + (opts.cls || '') + '">' + valueHtml + '</span>'
            + CHV + '</summary>'
            + '<div class="me-box">' + boxHtml + '</div></details>';
    }
    function boxSub(text) { return '<div class="me-box-sub">' + esc(text) + '</div>'; }
    function boxWarn(text) { return '<div class="me-box-warn">' + esc(text) + '</div>'; }

    // ==================== Деньги ====================

    function renderMoney(host, data) {
        var m = data.money;
        if (!m) { host.innerHTML = ''; return; }
        var rows = [];

        // Часы по ролям: у каждой роли своя ставка, поэтому своя строка формулы.
        var byRole = ((data.hours || {}).by_role) || [];
        var hoursExcluded = (m.excluded_components || []).indexOf('hours_pay') !== -1;
        rows.push(row('Часы по ставке', money(m.hours_pay),
            (byRole.length
                ? byRole.map(function (r) {
                    return esc(r.role_name) + ' ' + num(r.hours) + ' ч x '
                        + money(r.rate_per_hour) + ' = ' + money(r.pay);
                }).join('<br>')
                : 'часы — из факта, который вы вводите в конце смены')
            + boxSub('часы берутся из факта смены, а не из кассовых смен iiko')
            + (hoursExcluded ? boxWarn('В итог не включено: не удалось надёжно связать '
                + 'смены с вашим идентификатором') : ''),
            { cls: hoursExcluded ? ' is-excluded' : zero(m.hours_pay) }));

        var h = m.handover || {};
        rows.push(row('Приемка-передача смены', money(h.sum),
            money(h.rate) + ' x ' + shifts(h.paid_days || 0)
            + ' со сданной кассой (из ' + (h.base_days || 0) + ')'
            + (h.unpaid_days
                ? boxWarn(shifts(h.unpaid_days) + ' без сданной кассы — не оплачены')
                : (h.manual_days
                    ? boxWarn(shifts(h.manual_days) + ' со штрафом по кассе')
                    : '')),
            { cls: zero(h.sum) }));

        var dp = m.day_plan || {};
        rows.push(row('Премия за дневной план', money(dp.sum),
            money(dp.base_per_day) + ' x ' + shifts(dp.days_paid || 0)
            + ' с выручкой выше плана<br>+ ' + num((dp.over_share || 0) * 100, 0)
            + '% от перевыполнения ' + money(dp.overperformance)
            + boxSub('смены ниже плана в премию не входят'),
            { cls: zero(dp.sum) }));

        var k = m.kpi || {};
        var kpiCount = ((data.kpi && data.kpi.items) || []).length;
        rows.push(row('KPI-премия', money(k.sum),
            'сумма по ' + kpiCount + ' ' + plural(kpiCount, 'показателю', 'показателям', 'показателям')
            + ', коэффициент смен ' + num(k.koef, 2)
            + '<div class="me-box-sub"><a href="#meKpi">Как считается — ниже, «Мои KPI»</a></div>',
            { cls: zero(k.sum) }));

        var t = m.taxi || {};
        var taxiExcluded = (m.excluded_components || []).indexOf('taxi') !== -1;
        rows.push(row('Такси', money(t.sum),
            money(t.rate) + ' x ' + (t.day_shifts || 0) + ' '
            + plural(t.day_shifts || 0, 'полная дневная смена', 'полные дневные смены',
                     'полных дневных смен')
            + (taxiExcluded ? boxWarn('В итог не включено: смены не связаны с вашим '
                + 'идентификатором') : ''),
            { cls: taxiExcluded ? ' is-excluded' : zero(t.sum) }));

        var l = m.late || {};
        if (l.count) {
            rows.push(row('Вычет дисциплина', '&minus;' + money(l.sum),
                l.count + ' ' + plural(l.count, 'опоздание', 'опоздания', 'опозданий')
                + ': ' + lateSteps(l.count, l.step)
                + (l.dates && l.dates.length ? '<br>' + l.dates.map(fmtDay).join(', ') : '')
                + boxSub('штраф растёт на ' + money(l.step) + ' за каждое следующее'),
                { cls: ' is-minus' }));
        }

        var norm = (data.norms || {}).shift_norm || 0;
        var done = m.shifts_count || 0;
        var progress = norm ? Math.min(100, Math.round(done / norm * 100)) : 0;

        // Заголовок секции — полоса, как у KPI и показателей ниже. В шапке
        // карточки он был единственным на всю колонку и не давал левой колонке
        // завести свою полосу «Приёмка бара», не сбив первые карточки с одной
        // линии. Дата начисления встала в тот же слот, где у «Снимка» стоит
        // время: справа, мелким моноширинным.
        host.innerHTML = '<div class="me-band me-band-sub">'
            + '<span class="me-band-t">Мои деньги</span>'
            + '<span class="me-band-line"></span>'
            + '<span class="me-band-ts">начислено на ' + esc(fmtDay(data.today))
            + '</span></div>'
            + '<div class="me-card">'
            + staleHtml(data)
            + '<div class="me-total">' + money(m.total) + '</div>'
            + '<div class="me-total-sub"><span class="me-total-sub-t">за ' + shifts(done)
            + (norm ? ' из ' + norm : '') + '</span>'
            + (norm ? '<span class="me-mini-bar"><span style="width:' + progress
                + '%"></span></span>' : '')
            + '</div>'
            + '<div class="me-rows">' + rows.join('') + '</div>'
            + '<div class="me-sum"><span class="me-sum-n">Итого начислено</span>'
            + '<span class="me-card-sp"></span>'
            + '<span class="me-sum-v">' + money(m.total) + '</span></div>'
            + '<p class="me-fine">' + esc((data.notes || {}).excel || '') + '</p>'
            + '</div>';
    }

    // Прогрессивный штраф: 250 + 500 + 750...
    function lateSteps(count, step) {
        var parts = [];
        for (var i = 1; i <= count && i <= 6; i++) parts.push(S.formatMoney(step * i));
        return parts.join(' + ') + RUB;
    }

    // ==================== KPI ====================

    function renderKpi(host, data) {
        var kpi = data.kpi;
        if (!kpi) { host.innerHTML = ''; return; }
        var band = '<div class="me-band me-band-sub"><span class="me-band-t">Мои KPI</span>'
            + '<span class="me-band-line"></span></div>';

        if (kpi.status !== 'ok' || !(kpi.items || []).length) {
            host.innerHTML = band + '<div class="me-empty">Цели на '
                + esc(data.month_label || 'этот месяц') + ' не заданы или нет закрытых смен — '
                + 'KPI-премия за этот месяц не начисляется. Цели настраиваются на странице '
                + '<a href="/goals">Цели месяца</a>.</div>';
            return;
        }

        var meta = data.kpi_meta || {};
        var maxRatio = meta.max_ratio || 2;
        var perKpi = meta.base_per_kpi;
        var fundBox = (meta.kpi_pool != null && perKpi != null
                ? 'Фонд ' + money(meta.kpi_pool) + ' / ' + kpi.items.length + ' = '
                  + money(perKpi) + ' за каждый показатель<br>'
                : '')
            + 'Коэффициент x' + num(kpi.koef, 2) + ' = ' + (kpi.total_shifts || 0)
            + ' ваших смен на точках с целями / ' + (meta.norm_shifts || '')
            + boxSub('Премия показателя = множитель x ' + money(perKpi)
                     + ' x ' + num(kpi.koef, 2));

        var total = '<div class="me-card me-kpi-total">'
            + row('Итого KPI', money(kpi.total_premium), fundBox) + '</div>';

        var cards = kpi.items.map(function (it) {
            return kpiCard(it, kpi, meta, maxRatio);
        }).join('');

        host.innerHTML = band + total + '<div class="me-kpi-grid">' + cards + '</div>';
    }

    function kpiCard(it, kpi, meta, maxRatio) {
        var cat = (meta.metrics_catalog || {})[it.metric] || {};
        var unit = cat.unit || '';
        var dec = cat.decimals == null ? 1 : cat.decimals;
        var v = function (x) { return x == null ? '—' : num(x, dec) + (unit ? ' ' + unit : ''); };

        var ratio = it.ratio == null ? 0 : it.ratio;
        var fill = Math.max(0, Math.min(100, ratio / maxRatio * 100));
        var mark = 1 / maxRatio * 100;

        // Вердикт словами: молчаливый ноль читается как ошибка расчёта.
        var verdict, mulCls = '';
        if (it.min != null && it.fact != null && it.fact < it.min) {
            verdict = '<div class="me-verdict is-warn">Ниже минимума — премия не начисляется</div>';
            mulCls = ' is-bad';
        } else if (ratio >= maxRatio) {
            verdict = '<div class="me-verdict is-ok">Выше цели — множитель на максимуме</div>';
            mulCls = ' is-ok';
        } else if (ratio >= 1) {
            verdict = '<div class="me-verdict is-ok">Цель выполнена</div>';
            mulCls = ' is-ok';
        } else {
            verdict = '<div class="me-verdict is-plain">Между минимумом и целью — премия частичная</div>';
        }

        // Формула с подставленными числами.
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
        var locRows = Object.keys(locs).map(function (n) {
            return '<div class="me-box-row"><span>' + esc(n) + '</span><span class="sp"></span>'
                + '<span>' + shifts(locs[n]) + '</span></div>';
        }).join('');

        return '<div class="me-card me-kpi-card">'
            + '<div class="me-card-h"><span class="me-kpi-name">' + esc(it.name) + '</span>'
            + '<span class="me-card-sp"></span>'
            + '<span class="me-kpi-prem' + zero(it.premium) + '">' + money(it.premium)
            + ' <span class="me-kpi-max">/ ' + money(meta.base_per_kpi) + '</span></span></div>'
            + '<div class="me-kpi-nums">'
            + kpiNum('факт', v(it.fact)) + kpiNum('цель', v(it.target))
            + kpiNum('минимум', v(it.min)) + kpiNum('множитель', 'x' + num(ratio, 2), mulCls)
            + '</div>'
            + '<div class="me-scale"><span class="me-scale-fill" style="width:' + fill + '%"></span>'
            + '<span class="me-scale-mark" style="left:' + mark + '%"></span></div>'
            + '<div class="me-scale-legend"><span>0</span><span>цель</span><span>'
            + num(maxRatio, 0) + '</span></div>'
            + verdict
            + '<details class="me-how"><summary>КАК ПОСЧИТАНО' + CHV + '</summary>'
            + '<div class="me-box">' + calc + locRows
            + boxSub('Цели взвешены по вашим сменам: где вы работали больше, та цель весит сильнее.')
            + '</div></details>'
            + '</div>';
    }

    function kpiNum(label, value, cls) {
        return '<div class="me-kpi-num"><div class="me-kpi-num-l">' + esc(label.toUpperCase())
            + '</div><div class="me-kpi-num-v' + (cls || '') + '">' + esc(value) + '</div></div>';
    }

    // ==================== Показатели ====================

    // Формулы показателей: числа подставлены, единицы указаны. Формулировки
    // согласованы с docs/salary-instruction.txt.
    function metricFormulas(m) {
        var f = {};
        f.total_revenue = 'Выручка — сумма по закрытым чекам за месяц, после скидок.';
        f.avg_check = 'Средний чек = выручка / количество чеков = '
            + S.formatMoney(m.total_revenue) + ' / ' + (m.total_checks || 0)
            + ' = ' + money(m.avg_check);
        f.plan_fact_percent = 'План / факт = выручка / план ваших смен = '
            + S.formatMoney(m.total_revenue) + ' / ' + S.formatMoney(m.plan_revenue)
            + ' = ' + pct(m.plan_fact_percent)
            + boxSub('План смены — план точки на этот день; пятница и суббота весят 2x.');
        f.draft_share = 'Доля розлива = выручка разливного / вся выручка = '
            + S.formatMoney(m.draft_revenue) + ' / ' + S.formatMoney(m.total_revenue)
            + ' = ' + pct(m.draft_share);
        f.bottles_share = 'Доля фасовки = выручка фасовки / вся выручка = '
            + S.formatMoney(m.bottles_revenue) + ' / ' + S.formatMoney(m.total_revenue)
            + ' = ' + pct(m.bottles_share);
        f.kitchen_share = 'Доля кухни = выручка кухни / вся выручка = '
            + S.formatMoney(m.kitchen_revenue) + ' / ' + S.formatMoney(m.total_revenue)
            + ' = ' + pct(m.kitchen_share);
        f.other_share = 'Прочее — не напитки и не еда: наборы, чай, кофе, вода. Доли розлива, '
            + 'фасовки, кухни и прочего вместе дают 100%.';
        f.total_checks = 'Чеки — количество уникальных заказов, пробитых под вами.';
        f.discount_percent = 'Скидки = сумма скидок / выручка до скидок = '
            + S.formatMoney(m.discount_sum) + ' / '
            + S.formatMoney((m.total_revenue || 0) + (m.discount_sum || 0))
            + ' = ' + pct(m.discount_percent);
        f.cancelled_count = 'Отмены и возвраты — сколько заказов было отменено или возвращено '
            + 'за месяц.';
        f.loyalty_cards_count = 'Новые карты лояльности — уникальные телефоны, впервые '
            + 'оформленные на ваших чеках.';
        f.revenue_per_shift = 'Выручка / смена = выручка / количество смен = '
            + S.formatMoney(m.total_revenue) + ' / ' + (m.shifts_count || 0)
            + ' = ' + money(m.revenue_per_shift);
        f.revenue_per_hour = 'Выручка / час = выручка / часы кассовых смен = '
            + S.formatMoney(m.total_revenue) + ' / ' + num(m.work_hours)
            + ' = ' + money(m.revenue_per_hour);
        f.avg_markup = 'Средняя наценка взвешена по себестоимости: наценка каждой категории '
            + 'умножается на её себестоимость, сумма делится на общую себестоимость. Итог: '
            + pct(m.avg_markup);
        f.late_count = 'Опоздания — сколько раз система зафиксировала опоздание. Штраф '
            + 'прогрессивный: 250, 500, 750 руб. и далее. Считается за факт опоздания, а не '
            + 'за смену.';
        return f;
    }

    function renderMetrics(host, data) {
        var m = data.metrics;
        var band = '<div class="me-band me-band-sub"><span class="me-band-t">Мои показатели</span>'
            + '<span class="me-band-line"></span></div>';
        if (!m) { host.innerHTML = ''; return; }
        if (m.status !== 'ok') {
            host.innerHTML = band + '<div class="me-empty">Показатели продаж за '
                + esc(data.month_label || 'этот месяц') + ' не посчитаны: не удалось однозначно '
                + 'сопоставить ваше имя с именем в отчётах продаж iiko. Нули здесь были бы '
                + 'обманом, поэтому показатели скрыты.</div>';
            return;
        }
        var f = metricFormulas(m);

        var big = [
            bigTile('Выручка', money(m.total_revenue), f.total_revenue),
            bigTile('Средний чек', money(m.avg_check), f.avg_check),
            bigTile('План / факт', pct(m.plan_fact_percent), f.plan_fact_percent)
        ].join('');

        // Структура продаж — сложенная полоса + расшифровка по строкам.
        var parts = [
            { n: 'Розлив', v: m.draft_share, c: 'var(--me-accent)', f: f.draft_share },
            { n: 'Фасовка', v: m.bottles_share, c: '#D3B471', f: f.bottles_share },
            { n: 'Кухня', v: m.kitchen_share, c: '#C8B9A4', f: f.kitchen_share },
            { n: 'Прочее', v: m.other_share, c: 'var(--me-track)', f: f.other_share }
        ];
        var stack = '<div class="me-stack">' + parts.map(function (p) {
            return '<span style="width:' + Math.max(0, p.v || 0) + '%;background:' + p.c + '"></span>';
        }).join('') + '</div>';
        var structure = group('Структура продаж', 'розлив ' + pct(m.draft_share),
            stack + parts.map(function (p) {
                return row(p.n, pct(p.v), p.f,
                    { cls: zero(p.v), swatch: p.c });
            }).join(''));

        var guests = group('Чеки и гости', (m.total_checks || 0) + ' '
            + plural(m.total_checks || 0, 'чек', 'чека', 'чеков'), [
            row('Чеков', String(m.total_checks || 0), f.total_checks, { cls: zero(m.total_checks) }),
            row('Скидки', pct(m.discount_percent), f.discount_percent, { cls: zero(m.discount_percent) }),
            row('Отмены и возвраты', String(m.cancelled_count || 0), f.cancelled_count,
                { cls: zero(m.cancelled_count) }),
            row('Новые карты', String(m.loyalty_cards_count || 0), f.loyalty_cards_count,
                { cls: zero(m.loyalty_cards_count) })
        ].join(''));

        var output = group('Отдача и дисциплина', money(m.revenue_per_shift) + ' / смена', [
            row('Выручка / смена', money(m.revenue_per_shift), f.revenue_per_shift,
                { cls: zero(m.revenue_per_shift) }),
            row('Выручка / час', money(m.revenue_per_hour), f.revenue_per_hour,
                { cls: zero(m.revenue_per_hour) }),
            row('Средняя наценка', pct(m.avg_markup), f.avg_markup, { cls: zero(m.avg_markup) }),
            row('Опоздания', String(m.late_count || 0), f.late_count,
                { cls: m.late_count ? ' is-minus' : ' is-zero' })
        ].join(''));

        var groups = [structure, guests, output];
        var top = (m.top_beers || []).slice(0, 7);
        if (top.length) {
            var max = Math.max.apply(null, top.map(function (b) { return b.revenue || 0; })) || 1;
            groups.push('<div class="me-card me-group">'
                + '<div class="me-group-h"><span class="me-group-t">Топ сортов пива</span>'
                + '<span class="me-card-sp"></span>'
                + '<span class="me-card-note">по выручке</span></div>'
                + top.map(function (b) {
                    return '<div class="me-beer"><div class="me-beer-top">'
                        + '<span class="me-beer-n">' + esc(b.name) + '</span>'
                        + '<span class="me-card-sp"></span>'
                        + '<span class="me-beer-v">' + money(b.revenue) + '</span></div>'
                        + '<div class="me-beer-bar"><span style="width:'
                        + Math.round((b.revenue || 0) / max * 100) + '%"></span></div></div>';
                }).join('')
                + '</div>');
        }

        host.innerHTML = band
            + '<div class="me-tiles-big">' + big + '</div>'
            + '<div class="me-groups">' + groups.join('') + '</div>';
    }

    function bigTile(label, value, formula) {
        return '<details class="me-card me-tile-b"><summary>'
            + '<span class="me-tile-b-top"><span class="me-tile-b-l">'
            + esc(label.toUpperCase()) + '</span><span class="me-card-sp"></span>' + CHV + '</span>'
            + '<span class="me-tile-b-v">' + esc(value) + '</span></summary>'
            + '<div class="me-box">' + formula + '</div></details>';
    }

    function group(title, note, body) {
        return '<div class="me-card me-group">'
            + '<div class="me-group-h"><span class="me-group-t">' + esc(title) + '</span>'
            + '<span class="me-card-sp"></span>'
            + '<span class="me-card-note">' + esc(note) + '</span></div>'
            + body + '</div>';
    }

    // ==================== Плитки месяца (живые) ====================

    function renderMonthTiles(host, summary, norms) {
        if (!host || !summary) return;
        norms = norms || {};
        var sn = summary.shiftNorm || norms.shift_norm || '';
        var hn = summary.hoursNorm || norms.hours_norm || '';
        var over = sn && summary.shifts > sn;
        host.innerHTML =
            tileS('смены', summary.shifts + '<span class="den">/' + sn + '</span>', over)
            + tileS('часы', summary.hours + '<span class="den">/' + hn + '</span>')
            + tileS('без факта', String(summary.noFact), summary.noFact > 0);
    }

    function tileS(label, valueHtml, warn) {
        return '<div class="me-tile-s"><div class="me-tile-s-l">' + esc(label.toUpperCase())
            + '</div><div class="me-tile-s-v' + (warn ? ' is-warn' : '') + '">'
            + valueHtml + '</div></div>';
    }

    // ==================== Общее ====================

    // Дату снимка показывает полоса-заголовок «Снимок». В карточке пишем
    // только про устаревание: это предупреждение, а не повтор даты.
    function staleHtml(data) {
        var snap = data.snapshot || {};
        if (!snap.stale || !snap.refreshed_at) return '';
        return '<div class="me-stamp is-stale">данные на ' + esc(fmtStamp(snap.refreshed_at))
            + ' — давно не обновлялись</div>';
    }

    function fmtStamp(iso) {
        if (!iso || iso.length < 16) return '';
        return iso.slice(8, 10) + '.' + iso.slice(5, 7) + ', ' + iso.slice(11, 16);
    }
    function fmtDay(iso) {
        if (!iso || iso.length < 10) return '';
        return iso.slice(8, 10) + '.' + iso.slice(5, 7);
    }

    window.Me = window.Me || {};
    window.Me.snapshot = {
        renderMoney: renderMoney,
        renderKpi: renderKpi,
        renderMetrics: renderMetrics,
        renderMonthTiles: renderMonthTiles,
        fmtStamp: fmtStamp
    };
})();

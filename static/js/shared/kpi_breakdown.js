/* Расчёт KPI-премии одним блоком — ОДИН рендер для /me и страницы ЗП.

   Сверху чек (деньги): множитель × тариф по каждому показателю, сумма,
   коэффициент смен одной строкой, итог. Под ним по «линейке» на показатель
   (откуда множитель): отметки ×0 / ×1 / ×2 и маркер факта.

   Ничего не считает заново. Множители, премии, коэффициент и итог приходят
   готовыми из core/kpi_calculator.py (/api/kpi-calculate или снимок /me).
   Здесь только представление:
     - у штучных KPI («на смену») цели и факт показаны на НОРМУ смен:
       цель за смену × норма, факт ÷ смены × норма. Множитель от этого не
       меняется: (f − min) / (цель − min) не зависит от масштаба;
     - положение маркера на линейке: k = (факт − мин) / (цель − мин);
     - подсказка «пока месяц идёт»: сколько ещё продать за оставшиеся смены
       графика, чтобы к концу месяца выйти на ×1 и на ×max.

   Геометрия линейки. Домен = [мин − ½ шага; мин + (max + ½) шага], где шаг =
   цель − мин. Тогда ×0, ×1, ×2 при max = 2 стоят на 1/6, 1/2 и 5/6 ширины у
   ЛЮБОГО показателя, и двигается только маркер. Маркер за пределами домена
   прижимается к краю со стрелкой.

   Округление (детерминированно): множитель в чеке — 4 знака (как хранит
   расчёт), на карточке — 2; деньги — до рубля; значения на линейке — по
   знакам метрики (% — 1 знак, шт/₽ — целые, «на норму» — до 1 знака), в
   формуле — на знак больше, но не больше 2.

   Подключение: <script src="/static/js/shared/kpi_breakdown.js"> + стили
   /static/shared/kpi_breakdown.css. Вызов: KpiBreakdown.render(host, model).
   model: {
     title, total, koef, totalShifts, allShifts, norm, pool, basePerKpi,
     maxRatio, shiftsPerLocation: {точка: смен}, catalog: AVAILABLE_METRICS,
     dishesNotFound: [], plan: {open: bool, shifts: смен по графику} | null,
     items: [строка KPI расчёта: name, metric, per_shift, fact, fact_raw,
             shifts_divisor, target, min, capped_ratio (или ratio),
             intermediate_premium, no_targets, no_dishes, dishes, dish_facts,
             location_targets]
   } */
(function () {
    'use strict';

    var NBSP = ' ';

    // ---------- форматирование ----------
    function nf(x, minDec, maxDec) {
        return new Intl.NumberFormat('ru-RU', {
            minimumFractionDigits: minDec, maximumFractionDigits: maxDec
        }).format(x || 0);
    }
    function money(x) { return nf(Math.round(x || 0), 0, 0) + NBSP + '₽'; }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function plural(n, one, few, many) {
        var t = Math.abs(n) % 100, o = t % 10;
        if (t > 10 && t < 20) return many;
        if (o === 1) return one;
        if (o >= 2 && o <= 4) return few;
        return many;
    }
    // «за 12 смен», «за 1 смену»
    function shiftsAcc(n) { return n + NBSP + plural(n, 'смену', 'смены', 'смен'); }
    // «ещё 3 смены», «12 смен из нормы»
    function shiftsNom(n) { return n + NBSP + plural(n, 'смена', 'смены', 'смен'); }

    // Единица и знаки значения на линейке.
    function unitOf(it, catalog) {
        return ((catalog || {})[it.metric] || {}).unit || '';
    }
    function decOf(it, catalog, perShift) {
        var unit = unitOf(it, catalog);
        if (unit === '₽') return 0;
        if (perShift) return 1;
        var d = ((catalog || {})[it.metric] || {}).decimals;
        return d == null ? 1 : d;
    }
    function val(x, unit, dec) {
        return nf(x, 0, dec) + (unit ? NBSP + unit : '');
    }

    // ---------- модель одной линейки ----------
    function rulerOf(it, model) {
        var norm = model.norm || 15;
        var maxRatio = model.maxRatio || 2;
        var n = it.shifts_divisor || 0;
        var perShift = !!(it.per_shift && n > 0);
        var scale = perShift ? norm : 1;
        var v0 = (it.min || 0) * scale;
        var v1 = (it.target || 0) * scale;
        var span = v1 - v0;
        var f = perShift ? (it.fact_raw || 0) / n * norm : (it.fact || 0);
        var k = span !== 0 ? (f - v0) / span : null;
        return {
            perShift: perShift, norm: norm, maxRatio: maxRatio, n: n,
            v0: v0, v1: v1, v2: v0 + maxRatio * span, span: span, f: f, k: k,
            unit: unitOf(it, model.catalog), dec: decOf(it, model.catalog, perShift)
        };
    }
    function pos(k, maxRatio) {
        var c = Math.max(-0.5, Math.min(maxRatio + 0.5, k));
        return (c + 0.5) / (maxRatio + 1) * 100;
    }
    function pct(x) { return (Math.round(x * 100) / 100) + '%'; }

    function rulerHtml(r) {
        var m = r.maxRatio;
        var p0 = pos(0, m);
        var pf = pos(r.k, m);
        var fillTo = pos(Math.max(0, Math.min(m, r.k)), m);
        var ticks = '', labs = '';
        var marks = [[0, r.v0], [1, r.v1], [m, r.v2]];
        marks.forEach(function (mk) {
            var p = pos(mk[0], m);
            // Отметка за нулём (у «меньше — лучше» ×2 бывает отрицательной) недостижима
            var shown = mk[1] < 0 ? '—' : val(mk[1], r.unit, r.dec);
            ticks += '<span class="kb-tick" style="left:' + pct(p) + '"></span>';
            labs += '<span class="kb-lab" style="left:' + pct(p) + '"><span class="kb-lab-x">×'
                + nf(mk[0], 0, 2) + '</span><span class="kb-lab-v">' + esc(shown) + '</span></span>';
        });
        var youCls = pf < 8 ? ' is-left' : (pf > 92 ? ' is-right' : '');
        var arrowL = r.k < -0.5 ? '◂ ' : '';
        var arrowR = r.k > m + 0.5 ? ' ▸' : '';
        return '<div class="kb-ruler">'
            + labs
            + '<div class="kb-track">'
            + '<span class="kb-dead" style="width:' + pct(p0) + '"></span>'
            + (fillTo > p0 ? '<span class="kb-fill" style="left:' + pct(p0) + ';width:'
                + pct(fillTo - p0) + '"></span>' : '')
            + ticks
            + '<span class="kb-mark" style="left:' + pct(pf) + '"></span>'
            + '</div>'
            + '<span class="kb-you' + youCls + '" style="left:' + pct(pf) + '">'
            + arrowL + esc(val(r.f, r.unit, r.dec)) + arrowR + '</span>'
            + '</div>';
    }

    // ---------- тексты карточки ----------
    function factLine(it, r) {
        if (!r.perShift) {
            return 'Факт: <b>' + esc(val(it.fact, r.unit, r.dec)) + '</b>';
        }
        var raw = val(it.fact_raw, r.unit, r.dec);
        if (r.n === r.norm) {
            return 'Факт: <b>' + esc(raw) + '</b> за ' + esc(shiftsAcc(r.n));
        }
        return 'Факт: <b>' + esc(raw) + '</b> за ' + esc(shiftsAcc(r.n)) + '. Цели заданы на '
            + esc(shiftsAcc(r.norm)) + ', поэтому факт пересчитан на ' + r.norm + ': <b>'
            + esc(nf(it.fact_raw, 0, 2)) + ' ÷ ' + r.n + ' × ' + r.norm + ' = '
            + esc(val(r.f, r.unit, r.dec)) + '</b>';
    }

    function explainHtml(it, r, model, ratio) {
        var d = Math.min(2, r.dec + 1);
        var u = r.unit;
        var base = model.basePerKpi || 0;
        var m = r.maxRatio;
        var per = r.perShift ? ' на ' + r.norm + ' смен' : '';
        var f = nf(r.f, 0, d), a = nf(r.v0, 0, d), b = nf(r.v1, 0, d);
        var v = function (x) { return '<span class="kb-n">' + esc(val(x, u, r.dec)) + '</span>'; };
        var out;
        if (r.span > 0) {
            out = (r.perShift ? 'Меньше ' : 'Ниже ') + v(r.v0) + per + ' — премии нет. '
                + v(r.v1) + ' — полные ' + money(base) + ', от ' + v(r.v2) + ' — '
                + money(base * m) + '. ';
            if (r.k < 0) {
                out += 'Факт ' + esc(val(r.f, u, r.dec)) + ' ниже ' + esc(val(r.v0, u, r.dec))
                    + ' — множитель 0.';
            } else {
                out += 'Между отметками — пропорционально: <span class="kb-n">(' + f + ' − ' + a
                    + ') ÷ (' + b + ' − ' + a + ') = '
                    + (r.k > m ? nf(r.k, 2, 2) + '</span>, но множитель не больше ' + nf(m, 0, 2) + '.'
                               : nf(ratio, 2, 2) + '</span>.');
            }
        } else {
            // «Меньше — лучше»: минимум (потолок) выше цели
            out = 'Больше ' + v(r.v0) + per + ' — премии нет. ' + v(r.v1) + ' — полные '
                + money(base) + (r.v2 >= 0 ? ', до ' + v(r.v2) + ' — ' + money(base * m) : '') + '. ';
            if (r.k < 0) {
                out += 'Факт ' + esc(val(r.f, u, r.dec)) + ' выше ' + esc(val(r.v0, u, r.dec))
                    + ' — множитель 0.';
            } else {
                out += 'Между отметками — пропорционально: <span class="kb-n">(' + a + ' − ' + f
                    + ') ÷ (' + a + ' − ' + b + ') = '
                    + (r.k > m ? nf(r.k, 2, 2) + '</span>, но множитель не больше ' + nf(m, 0, 2) + '.'
                               : nf(ratio, 2, 2) + '</span>.');
            }
        }
        return '<div class="kb-explain">' + out + '</div>';
    }

    // Округление месячной цели — по знакам метрики: штуки и рубли целые.
    function roundGoal(x, it, catalog) {
        var d = ((catalog || {})[it.metric] || {}).decimals;
        var p = Math.pow(10, d == null ? 0 : d);
        return Math.round(x * p) / p;
    }

    function hintHtml(it, r, model) {
        var plan = model.plan;
        if (!plan || !plan.open || !r.perShift || !(r.span > 0)) return '';
        var total = Math.max(plan.shifts || 0, r.n);
        var left = total - r.n;
        if (left <= 0) return '';
        var m = r.maxRatio;
        var done = it.fact_raw || 0;
        var goal1 = roundGoal((it.target || 0) * total, it, model.catalog);
        var goal2 = roundGoal(((it.min || 0) + m * ((it.target || 0) - (it.min || 0))) * total,
                              it, model.catalog);
        var need1 = goal1 - done, need2 = goal2 - done;
        var q = function (x) { return '<b>' + esc(val(x, r.unit, r.dec)) + '</b>'; };
        var text = 'По графику у вас ещё ' + esc(shiftsNom(left)) + '. ';
        if (need2 <= 0) {
            text += 'На ×' + nf(m, 0, 2) + ' к концу месяца уже хватает.';
        } else if (need1 <= 0) {
            text += 'На ×1 к концу месяца уже хватает, для ×' + nf(m, 0, 2) + ' нужно ещё '
                + q(need2) + '.';
        } else {
            text += 'Чтобы к концу месяца было ×1, нужно ещё ' + q(need1) + ' (всего '
                + esc(val(goal1, r.unit, r.dec)) + ' за ' + esc(shiftsAcc(total)) + '), для ×'
                + nf(m, 0, 2) + ' — ещё ' + q(need2) + '.';
        }
        return '<div class="kb-hint"><span class="kb-hint-t">Пока месяц идёт</span>' + text + '</div>';
    }

    // Таблица «цели по точкам» — откуда взвешенные минимум и цель.
    function locationsHtml(it, r, model) {
        var lt = it.location_targets;
        if (!lt || !Object.keys(lt).length) return '';
        var s = r.perShift ? r.norm : 1;
        var spl = model.shiftsPerLocation || {};
        var names = Object.keys(spl).sort(function (a, b) { return spl[b] - spl[a]; });
        Object.keys(lt).forEach(function (n) { if (names.indexOf(n) === -1) names.push(n); });
        var rows = '', inShifts = 0, targets = {}, mins = {};
        names.forEach(function (n) {
            var t = lt[n];
            var cnt = t ? (t.shifts || 0) : (spl[n] || 0);
            if (t) {
                inShifts += cnt;
                targets[t.target * s] = 1;
                mins[t.min * s] = 1;
                rows += '<tr><td>' + esc(n) + '</td><td>' + cnt + '</td><td>'
                    + esc(val(t.min * s, r.unit, r.dec)) + '</td><td>'
                    + esc(val(t.target * s, r.unit, r.dec)) + '</td></tr>';
            } else {
                rows += '<tr class="is-off"><td>' + esc(n) + '</td><td>' + cnt
                    + '</td><td colspan="2">цели нет, не считается</td></tr>';
            }
        });
        var d = Math.min(2, r.dec + 1);
        // «на 15 смен» — в заголовке раскрытия, а не в шапке столбцов: иначе
        // таблица не помещается в ширину телефона
        var per = r.perShift ? ', на ' + r.norm + ' смен' : '';
        var formula;
        if (Object.keys(targets).length <= 1 && Object.keys(mins).length <= 1) {
            formula = 'Цели одинаковые на всех ваших точках.';
        } else {
            var part = function (field) {
                var terms = names.filter(function (n) { return lt[n]; }).map(function (n) {
                    return lt[n].shifts + ' × ' + nf(lt[n][field] * s, 0, d);
                });
                return '(' + terms.join(' + ') + ') ÷ ' + inShifts;
            };
            formula = 'цель = ' + part('target') + ' = ' + nf(r.v1, 0, d)
                + '<br>минимум = ' + part('min') + ' = ' + nf(r.v0, 0, d);
        }
        return '<details class="kb-more"><summary>Цели по точкам' + per + '</summary>'
            + '<div class="kb-tbl-wrap"><table class="kb-tbl"><thead><tr><th>Точка</th><th>Смены</th>'
            + '<th>Минимум</th><th>Цель</th></tr></thead><tbody>' + rows
            + '<tr class="is-sum"><td>По вашим сменам</td><td>' + inShifts + '</td><td>'
            + esc(val(r.v0, r.unit, r.dec)) + '</td><td>' + esc(val(r.v1, r.unit, r.dec))
            + '</td></tr></tbody></table></div>'
            + '<div class="kb-formula">' + formula + '</div></details>';
    }

    function dishesHtml(it, r, model) {
        if (!it.dishes || !it.dishes.length) return '';
        var missing = (model.dishesNotFound || []).map(function (d) {
            return String(d).trim().toLowerCase();
        });
        var facts = it.dish_facts || {};
        var anyMissing = false;
        var rows = it.dishes.map(function (d) {
            var gone = missing.indexOf(String(d).trim().toLowerCase()) !== -1;
            if (gone) anyMissing = true;
            return '<tr' + (gone ? ' class="is-warn"' : '') + '><td>' + esc(d) + '</td><td>'
                + (gone ? 'нет в продажах' : esc(nf(facts[d] || 0, 0, 2))) + '</td></tr>';
        }).join('');
        var total = r.perShift ? it.fact_raw : it.fact;
        return '<details class="kb-more"' + (anyMissing ? ' open' : '') + '><summary>Из чего '
            + esc(nf(total, 0, 2)) + '</summary>'
            + '<div class="kb-tbl-wrap"><table class="kb-tbl"><thead><tr><th>Блюдо</th><th>Продано</th>'
            + '</tr></thead><tbody>' + rows + '<tr class="is-sum"><td>Всего</td><td>'
            + esc(nf(total, 0, 2)) + '</td></tr></tbody></table></div>'
            + (anyMissing ? '<div class="kb-warn">Блюдо не продавалось ни у кого за период — '
                + 'скорее всего, его переименовали в iiko. Проверьте название в настройке целей.</div>' : '')
            + '</details>';
    }

    function ratioOf(it) {
        return it.capped_ratio != null ? it.capped_ratio : (it.ratio || 0);
    }

    function cardHtml(it, model) {
        var r = rulerOf(it, model);
        var ratio = ratioOf(it);
        var multCls = it.no_targets || it.no_dishes || ratio <= 0 ? ' is-zero'
            : (ratio >= 1 ? ' is-ok' : '');
        var body;
        if (it.no_targets) {
            body = '<div class="kb-warn">На ваших точках цели по этому показателю не заданы — '
                + 'премия по нему не начисляется.</div>';
        } else if (it.no_dishes) {
            body = '<div class="kb-warn">Блюда для этого показателя не выбраны — премия по нему '
                + 'не начисляется. Их выбирают в настройке KPI-целей.</div>';
        } else if (r.span === 0) {
            body = '<div class="kb-fact">' + factLine(it, r) + '</div>'
                + '<div class="kb-explain">Цель ' + esc(val(r.v1, r.unit, r.dec))
                + (r.perShift ? ' на ' + r.norm + ' смен' : '') + ': не ниже цели — ×'
                + nf(r.maxRatio, 0, 2) + ', ниже — ×0.</div>';
        } else {
            body = '<div class="kb-fact">' + factLine(it, r) + '</div>'
                + (r.perShift ? '<div class="kb-unit">Шкала: ' + esc(r.unit) + ' на '
                    + esc(shiftsAcc(r.norm)) + '</div>' : '')
                + rulerHtml(r)
                + explainHtml(it, r, model, ratio)
                + hintHtml(it, r, model);
        }
        return '<section class="kb-card">'
            + '<div class="kb-head"><span class="kb-name">' + esc(it.name) + '</span>'
            + '<span class="kb-mult' + multCls + '">×' + nf(ratio, 2, 2) + '</span></div>'
            + body
            + (it.no_targets ? '' : locationsHtml(it, r, model))
            + dishesHtml(it, r, model)
            + '</section>';
    }

    function receiptHtml(model) {
        var items = model.items || [];
        var base = model.basePerKpi || 0;
        var sum = 0;
        var lines = items.map(function (it) {
            var inter = it.intermediate_premium || 0;
            sum += inter;
            var f = it.no_targets ? 'цели не заданы'
                : (it.no_dishes ? 'блюда не выбраны'
                    : '×' + nf(ratioOf(it), 0, 4) + ' × ' + money(base));
            return '<div class="kb-line"><span class="kb-l-n">' + esc(it.name) + '</span>'
                + '<span class="kb-l-f">' + f + '</span>'
                + '<span class="kb-l-m">' + money(inter) + '</span></div>';
        }).join('');
        var norm = model.norm || 15;
        var t = model.totalShifts || 0;
        var koef = nf(model.koef || 0, 2, 2);
        var off = (model.allShifts || 0) - t;
        var koefNote = shiftsNom(t) + ' из нормы ' + norm
            + (off > 0 ? '; ещё ' + off + ' на точках без целей не считаются' : '');
        var n = items.length;
        var foot = (model.pool != null
                ? 'Фонд ' + money(model.pool) + ' делится поровну на ' + n + ' '
                  + plural(n, 'показатель', 'показателя', 'показателей') + ': '
                : 'По каждому показателю ')
            + money(base) + ' за множитель ×1. Множитель от 0 до ' + nf(model.maxRatio || 2, 0, 2)
            + '. У коэффициента смен потолка нет. В чеке множитель с четырьмя знаками, как в '
            + 'расчёте; суммы округлены до рубля.';
        return '<section class="kb-card kb-receipt">'
            + '<div class="kb-total"><span class="kb-total-n">' + esc(model.title || 'KPI-премия')
            + '</span><span class="kb-total-v">' + money(model.total) + '</span></div>'
            + '<div class="kb-lines">' + lines
            + '<div class="kb-line is-sub"><span class="kb-l-n">Сумма по показателям</span>'
            + '<span class="kb-l-f"></span><span class="kb-l-m">' + money(sum) + '</span></div>'
            + '<div class="kb-line is-koef"><span class="kb-l-n">Коэффициент смен<small>'
            + esc(koefNote) + '</small></span><span class="kb-l-f">' + t + ' ÷ ' + norm
            + '</span><span class="kb-l-m">×' + koef + '</span></div>'
            + '<div class="kb-line is-grand"><span class="kb-l-n">KPI-премия</span>'
            + '<span class="kb-l-f">' + money(sum) + ' × ' + koef + '</span>'
            + '<span class="kb-l-m">' + money(model.total) + '</span></div>'
            + '</div><div class="kb-foot">' + foot + '</div></section>';
    }

    function render(host, model) {
        if (!host) return;
        host.innerHTML = '<div class="kb">' + receiptHtml(model)
            + (model.items || []).map(function (it) { return cardHtml(it, model); }).join('')
            + '</div>';
    }

    window.KpiBreakdown = {
        render: render,
        // для тестов
        _rulerOf: rulerOf,
        _pos: pos
    };
})();

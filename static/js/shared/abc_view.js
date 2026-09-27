/* Общая раскладка страниц «Розлив» (/draft) и «Фасовка» (/packaging): вкладки,
   «Обзор», «Цены», сравнение барменов, профиль баров, рубли в потерях.

   Страница по-прежнему сама грузит данные, рисует таблицы и карточки. Этот
   модуль получает тот же ответ API, приводит его к общей модели (fromDraft /
   fromPackaging) и рисует новые блоки строками разметки — как draft.js, чтобы
   их можно было проверить в Node без браузера (tests/test_abc_view.mjs).

   Все числа — из ответа API, формулы — в «Как считается» у своего блока
   (CLAUDE.md, п. 1: пояснения свёрнуты). Документация: docs/draft.md,
   docs/abc-xyz-analysis.md, раздел «Раскладка страницы». */
(function () {
    'use strict';

    // Меньше стольких продаж цена не описывает позицию: одна скидка переворачивает
    // наценку. То же число, что MIN_SALES_FOR_VERDICT в core/abc_thresholds.py.
    var MIN_SALES = 5;
    // Профиль баров: отличие доли категории от сети, процентных пункта. 2 п.п. в баре
    // за 30 дней — около 10 бутылок (число печатается на экране), меньше — разброс;
    // от 5 п.п. — насыщенная заливка. Категорий в таблице — первые 10 по выручке.
    var HEAT_WEAK = 2, HEAT_STRONG = 5, HEAT_TOP = 10;
    // Строк списка «Где поднять цену» за раз.
    var PRICE_STEP = 12;
    // Порядок групп в полосе «Выручка по решениям»: янтарные группы не стоят рядом.
    var BUCKET_ORDER = ['core', 'low_markup', 'new', 'weak', 'few', 'check'];
    var BUCKET_SHORT = { core: 'Основа', low_markup: 'Поднять цену', 'new': 'Новинка',
                         weak: 'Слабые продажи', few: 'Мало продаж', check: 'Сверить учёт' };
    var DAYS = ['день', 'дня', 'дней'];

    // ---------------- формат ----------------
    var NF = {};
    function nf(v, d) {
        d = d || 0;
        if (!NF[d]) NF[d] = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d });
        return NF[d].format(v).replace(/^-/, '−');
    }
    function rub(v) { return nf(Math.round(v)) + ' ₽'; }
    function srub(v) {
        var r = Math.round(v);
        return (r > 0 ? '+' : r < 0 ? '−' : '') + nf(Math.abs(r)) + ' ₽';
    }
    function pct(v, d) { return nf(v, d === undefined ? 1 : d) + '%'; }
    function spct(v, d) { return (v > 0 ? '+' : v < 0 ? '−' : '') + nf(Math.abs(v), d === undefined ? 1 : d) + '%'; }
    // Наценка вниз до знака, как markupPct страниц: 249,96% не печатается «250%».
    function mk(v) { return pct(Math.floor(v * 10 + 1e-9) / 10, 1); }
    // snap_markup из core/abc_thresholds.py: доля с 9 знаками, без хвостов float.
    function snap(share) { return Math.round(share * 1e9) / 1e9; }
    function plural(n, w) {
        var a = Math.abs(n) % 100, b = a % 10;
        return w[(a > 10 && a < 20) ? 2 : b === 1 ? 0 : (b >= 2 && b <= 4) ? 1 : 2];
    }
    function cnt(n, w) { return nf(n) + ' ' + plural(n, w); }
    function thousands(v) { return nf(Math.round(v / 1000)) + ' тыс ₽'; }
    function median(xs) {
        var s = xs.slice().sort(function (a, b) { return a - b; }), n = s.length;
        return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null;
    }
    function byName(a, b) { return String(a).localeCompare(String(b), 'ru'); }
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function tipAttr(lines) { return ' data-tip="' + esc(lines.join('\n')) + '"'; }
    function shortKeg(name) { return String(name || '').replace(/^КЕГ\s+/i, ''); }
    function periodWords(M) { var n = M.period.days; return n ? 'за ' + cnt(n, DAYS) : 'за период'; }

    // ---------------- модель ----------------
    function fromDraft(d) {
        d = d || {};
        var L = d.losses || {};
        var M = {
            key: 'draft', unit: 'л', qd: 1, per: '0,5 л', perK: 0.5, perWord: 'литра',
            aMin: 2.5, bMin: 2.0, salesWord: 'порций', itemsWord: 'Кеги',
            area: 'розлива', unitOne: 'литра', unitMany: 'литры по складу',
            qtyNote: 'Литры — расход кегов со склада по данным iiko: списание по техкарте при продаже. Акты и недостача сюда не входят — они во вкладке «Потери».',
            priceNote: 'Цена 0,5 л — выручка с литра × 0,5', goods: ['порции', 'порций', 'порций'],
            catNote: 'у кегов одного стиля обычно общая логика цены',
            nom: ['кег', 'кега', 'кегов'], gen: ['кега', 'кегов', 'кегов'],
            period: d.period || {}, scope: null, barNames: [],
            totals: { revenue: d.total_revenue || 0, cost: d.total_cost || 0, margin: d.total_margin || 0,
                      qty: d.total_liters || 0, sales: d.total_portions || 0, markup: d.markup_percent,
                      count: d.total_kegs || 0, cats: d.total_categories || 0, unitPrice: d.avg_price_per_liter || 0 },
            items: (d.kegs || []).map(function (k) {
                return { id: k.KegId, name: shortKeg(k.KegName), full: k.KegName, cat: k.Category || '',
                    revenue: k.TotalRevenue || 0, cost: k.TotalCost || 0, qty: k.TotalLiters || 0,
                    sales: k.TotalPortions || 0, markup: k.MarkupPercent, share: k.RevenueSharePercent || 0,
                    code: k.ABC_Combined, bucket: k.ABC_Bucket, byBar: [] };
            }),
            buckets: d.buckets || [],
            losses: lossModel(L, (L.by_keg || []).map(function (r) {
                return { id: r.KegId, name: shortKeg(r.KegName), sold: r.SoldLiters || 0, loss: r.LossLiters || 0 };
            })),
            people: d.bartenders || []
        };
        return index(M);
    }

    function fromPackaging(d) {
        d = d || {};
        var L = d.losses || {}, T = d.totals || {};
        var M = {
            key: 'pack', unit: 'шт', qd: 0, per: 'бутылка', perK: 1, perWord: 'штуки',
            aMin: 1.2, bMin: 1.0, salesWord: 'штук', itemsWord: 'Позиции',
            area: 'фасовки', unitOne: 'бутылки', unitMany: 'проданные штуки',
            qtyNote: 'Штуки — продажи по кассе iiko: товар фасовки списывается со склада при продаже сам. Акты и недостача сюда не входят — они во вкладке «Потери».',
            priceNote: 'Цена бутылки — выручка на бутылку', goods: ['бутылки', 'бутылок', 'бутылок'],
            catNote: 'у бутылок одного стиля обычно общая логика цены',
            nom: ['позиция', 'позиции', 'позиций'], gen: ['позиции', 'позиций', 'позиций'],
            period: d.period || {}, scope: d.scope || null, barNames: d.bars_in_scope || [],
            totals: { revenue: T.revenue || 0, cost: T.cost || 0, margin: T.margin || 0, qty: T.qty || 0,
                      sales: T.qty || 0, markup: T.markup_percent, count: T.sku || 0, cats: T.categories || 0,
                      unitPrice: T.price_per_unit || 0 },
            items: (d.positions || []).map(function (p) {
                return { id: p.Id, name: p.Beer, full: p.Beer, cat: p.Category || '',
                    revenue: p.TotalRevenue || 0, cost: p.TotalCost || 0, qty: p.TotalQty || 0,
                    sales: p.TotalQty || 0, markup: p.MarkupPercent, share: p.RevenueSharePercent || 0,
                    code: p.ABC_Combined, bucket: p.ABC_Bucket,
                    byBar: (p.ByBar || []).map(function (b) {
                        return { bar: b.Bar, qty: b.Qty || 0, revenue: b.Revenue || 0, cost: b.Cost || 0 };
                    }) };
            }),
            buckets: d.buckets || [],
            losses: lossModel(L, (L.by_item || []).map(function (r) {
                return { id: r.PositionId, name: r.ProductName, sold: r.SoldQty || 0, loss: r.LossQty || 0 };
            })),
            people: []
        };
        return index(M);
    }

    // Кухня (/kitchen): клон фасовки про еду. Отличия — пороги 180/150, слова и
    // потери: сервер отдаёт их сразу в рублях по закупке (core/kitchen_losses.py),
    // строки расхождений — продукты склада, в том числе ингредиенты блюд.
    function fromKitchen(d) {
        var M = fromPackaging(d);
        var L = (d && d.losses) || {};
        M.key = 'kitchen';
        M.unit = 'порц.';
        M.per = 'порция';
        M.perWord = 'порции';
        M.aMin = 1.8;
        M.bMin = 1.5;
        M.area = 'кухни';
        M.unitOne = 'порции';
        M.unitMany = 'проданные порции';
        M.qtyNote = 'Порции — продажи по кассе iiko. Соусы-модификаторы, которые отдают к блюдам, в позиции не входят. Акты и недостача — во вкладке «Потери», в рублях по закупке.';
        M.priceNote = 'Цена порции — выручка на порцию';
        M.goods = ['порции', 'порций', 'порций'];
        M.catNote = 'у блюд одной категории обычно общая логика цены';
        M.lossRub = true;
        M.losses = lossModel(L, (L.by_item || []).map(function (r) {
            return { id: r.ProductId, name: r.ProductName, sold: r.SoldRub || 0, loss: r.LossRub || 0 };
        }));
        return M;
    }

    function lossModel(L, rows) {
        return { sold: L.sold || 0, wo: L.writeoff || 0, invNet: L.inventory_net || 0,
                 invPct: L.inventory_percent_of_sold, rows: rows };
    }
    function index(M) {
        M.byId = {};
        M.items.forEach(function (it) { M.byId[it.id] = it; });
        return M;
    }

    // ---------------- расчёты ----------------
    // Недобор до минимума сети: закупка × (1 + минимум) − выручка по каждой позиции
    // с наценкой ниже минимума и продажами от MIN_SALES, кроме «Сверить учёт».
    function priceGap(M) {
        var rows = M.items.filter(function (it) {
            return it.bucket !== 'check' && it.markup !== null && it.markup !== undefined &&
                it.cost > 0 && it.qty > 0 && it.sales >= MIN_SALES && snap(it.markup / 100) < M.aMin;
        }).map(function (it) {
            var need = it.cost * (1 + M.aMin);
            return { it: it, up: need - it.revenue, now: it.revenue / it.qty * M.perK, need: need / it.qty * M.perK };
        }).sort(function (a, b) { return b.up - a.up || byName(a.it.name, b.it.name); });
        var total = rows.reduce(function (s, x) { return s + x.up; }, 0);
        var acc = 0, half = rows.length;
        for (var i = 0; i < rows.length; i++) {
            acc += rows[i].up;
            if (acc >= total / 2) { half = i + 1; break; }
        }
        return { rows: rows, total: total, half: half };
    }

    // Недостача в рублях: единицы недостачи × средняя закупка (и выручка) единицы
    // за период. Нетто: излишек в балансе недостачу уменьшает.
    // У кухни недостача приходит сразу в рублях по закупке; по цене продажи — та
    // же сумма × выручка / закупка кухни за период.
    function shortage(M) {
        var T = M.totals, L = M.losses;
        if (M.lossRub) {
            return { qty: L.invNet, cost: L.invNet, price: T.cost > 0 ? L.invNet * T.revenue / T.cost : 0, pct: L.invPct };
        }
        if (!(T.qty > 0)) return null;
        return { qty: L.invNet, cost: L.invNet * T.cost / T.qty, price: L.invNet * T.revenue / T.qty, pct: L.invPct };
    }

    // Рубли по строкам расхождений: потери × закупка единицы этой позиции; у
    // позиции без продаж в периоде — средняя закупка единицы за период.
    function lossRubles(M) {
        var avg = M.totals.qty > 0 ? M.totals.cost / M.totals.qty : 0;
        var byId = {}, total = 0;
        if (M.lossRub) {
            M.losses.rows.forEach(function (r) { byId[r.id] = { rub: r.loss, byAvg: false }; total += r.loss; });
            return { byId: byId, total: total };
        }
        M.losses.rows.forEach(function (r) {
            var it = M.byId[r.id];
            var own = it && it.qty > 0;
            var v = r.loss * (own ? it.cost / it.qty : avg);
            byId[r.id] = { rub: v, byAvg: !own };
            total += v;
        });
        return { byId: byId, total: total };
    }

    // Бармены на одних и тех же кегах: выручка бармена против литров бармена по
    // каждому кегу × средней выручки с литра этого кега в разрезе.
    function bartenders(M) {
        if (M.key !== 'draft' || !M.people.length) return null;
        var price = {};
        M.items.forEach(function (it) { if (it.qty > 0) price[it.id] = it.revenue / it.qty; });
        var net = M.totals.unitPrice;
        var rows = M.people.map(function (b) {
            var exp = 0, act = 0, L = 0;
            (b.kegs || []).forEach(function (x) {
                if (price[x.KegId] === undefined) return;
                exp += x.Liters * price[x.KegId];
                act += x.Revenue;
                L += x.Liters;
            });
            if (!(exp > 0) || !(L > 0)) return null;
            return { name: b.Bartender, exp: exp, act: act, L: L, idx: (act / exp - 1) * 100, diff: act - exp,
                     raw: net ? (b.PricePerLiter / net - 1) * 100 : null, actPL: act / L, expPL: exp / L };
        }).filter(Boolean).sort(function (a, b) { return a.idx - b.idx || byName(a.name, b.name); });
        var neg = rows.filter(function (r) { return r.diff < 0; });
        return { rows: rows, neg: neg, negSum: neg.reduce(function (s, r) { return s + r.diff; }, 0) };
    }

    // Цена против закупки единицы; трети кегов по закупке, медианы наценки и маржи.
    function priceCost(M) {
        var pts = M.items.filter(function (it) {
            return it.bucket !== 'check' && it.markup !== null && it.markup !== undefined &&
                it.cost > 0 && it.qty > 0 && it.sales >= MIN_SALES;
        }).map(function (it) {
            return { it: it, x: it.cost / it.qty, y: it.revenue / it.qty, v: it.qty, u: snap(it.markup / 100) < M.aMin };
        });
        var sorted = pts.slice().sort(function (a, b) { return a.x - b.x; });
        var t = Math.floor(sorted.length / 3);
        var lo = sorted.slice(0, t), hi = sorted.slice(sorted.length - t);
        function part(g, edge) {
            return { edge: edge, mk: median(g.map(function (p) { return p.it.markup; })),
                     mg: median(g.map(function (p) { return p.y - p.x; })) };
        }
        return { pts: pts, lo: t ? part(lo, lo[lo.length - 1].x) : null, hi: t ? part(hi, hi[0].x) : null };
    }

    function isUnc(name) { return /^Без категории/.test(String(name || '')); }

    // Профиль баров фасовки и кухни (разрез «Общая»): доля категории в выручке бара против
    // сети; наценка бара; цена тех же позиций к средней по сети.
    function barProfile(M) {
        if (M.key === 'draft' || M.scope !== 'total' || M.barNames.length < 2) return null;
        var bars = M.barNames.slice();
        var rev = {}, cost = {}, qty = {}, exp = {}, cell = {}, catRev = {};
        bars.forEach(function (b) { rev[b] = 0; cost[b] = 0; qty[b] = 0; exp[b] = 0; });
        M.items.forEach(function (it) {
            var unit = it.qty > 0 ? it.revenue / it.qty : null;
            it.byBar.forEach(function (x) {
                if (!(x.bar in rev)) return;
                rev[x.bar] += x.revenue; cost[x.bar] += x.cost; qty[x.bar] += x.qty;
                if (unit !== null) exp[x.bar] += x.qty * unit;
                var k = it.cat + '\u0000' + x.bar;
                cell[k] = (cell[k] || 0) + x.revenue;
                catRev[it.cat] = (catRev[it.cat] || 0) + x.revenue;
            });
        });
        var total = bars.reduce(function (a, b) { return a + rev[b]; }, 0);
        if (!(total > 0)) return null;
        function row(name, members) {
            var net = members.reduce(function (a, c) { return a + catRev[c]; }, 0) / total * 100;
            return { name: name, net: net, cells: bars.map(function (b) {
                var r = members.reduce(function (a, c) { return a + (cell[c + '\u0000' + b] || 0); }, 0);
                var share = rev[b] > 0 ? r / rev[b] * 100 : 0;
                return { bar: b, rub: r, share: share, dev: share - net };
            }) };
        }
        var cats = Object.keys(catRev).filter(function (c) { return !isUnc(c); })
            .sort(function (a, b) { return catRev[b] - catRev[a] || byName(a, b); });
        var unc = Object.keys(catRev).filter(isUnc);
        var rows = cats.slice(0, HEAT_TOP).map(function (c) { return row(c, [c]); });
        var extra = [];
        if (unc.length) extra.push(row(unc.join(', '), unc));
        if (cats.length > HEAT_TOP) {
            extra.push(row('Остальные ' + cnt(cats.length - HEAT_TOP, ['категория', 'категории', 'категорий']),
                cats.slice(HEAT_TOP)));
        }
        var info = bars.map(function (b, bi) {
            var best = null;
            rows.forEach(function (r) {
                var c = r.cells[bi];
                if (!best || Math.abs(c.dev) > Math.abs(best.c.dev)) best = { r: r, c: c };
            });
            return { bar: b, rev: rev[b], share: rev[b] / total * 100,
                     markup: cost[b] > 0 ? (rev[b] - cost[b]) / cost[b] * 100 : null,
                     price: exp[b] > 0 ? (rev[b] / exp[b] - 1) * 100 : null, best: best };
        });
        var totalQty = bars.reduce(function (a, b) { return a + qty[b]; }, 0);
        return { bars: bars, rows: rows, extra: extra, info: info,
                 uncCount: M.items.filter(function (it) { return isUnc(it.cat); }).length,
                 bottles: totalQty > 0 ? HEAT_WEAK / 100 * (total / bars.length) / (total / totalQty) : null };
    }

    // ---------------- куски разметки ----------------
    function how(parts, title) {
        return '<details class="av-how"><summary>' + esc(title || 'Как считается') + '</summary><div class="av-how-in">' +
            parts.filter(Boolean).map(function (p) {
                if (Array.isArray(p)) return '<ul>' + p.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
                return '<p>' + esc(p) + '</p>';
            }).join('') + '</div></details>';
    }
    function codeBadge(code) {
        var c = String(code || '???');
        var first = c.charAt(0).toLowerCase();
        return '<span class="av-abc' + (/[abc]/.test(first) ? ' ' + first : '') + '">' + esc(c) + '</span>';
    }
    function bar(share, cls) {
        return '<span class="av-bar"><i class="' + (cls || '') + '" style="width:' +
            Math.max(1, Math.min(100, share)).toFixed(1) + '%"></i></span>';
    }
    function split(parts) {
        var total = parts.reduce(function (a, p) { return a + Math.max(0, p.v); }, 0);
        return '<div class="av-split" role="img" aria-label="' + esc(parts.map(function (p) {
            return p.label + ' ' + pct(total > 0 ? p.v / total * 100 : 0);
        }).join(', ')) + '">' + parts.filter(function (p) { return p.v > 0; }).map(function (p) {
            return '<i class="' + p.cls + '" style="flex-grow:' + p.v + '"' + tipAttr(p.tip) + '></i>';
        }).join('') + '</div>';
    }
    var ICONS = {
        tag: 'M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8ZM7.5 7.5h.01', loss: 'M12 3v12m0 0-4-4m4 4 4-4M5 21h14',
        people: 'M16 19v-1a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v1M10 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6M20 19v-1a4 4 0 0 0-3-3.9M15 4.1a3 3 0 0 1 0 5.8',
        check: 'M12 8v5m0 3h.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0',
        chev: 'm9 6 6 6-6 6'
    };
    function icon(name, size) {
        var s = size || 18;
        return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' +
            ICONS[name] + '"/></svg>';
    }
    function cardHead(title, sub) {
        return '<div class="av-card-h"><h3 class="av-card-t">' + esc(title) + '</h3>' +
            (sub ? '<span class="av-card-s">' + esc(sub) + '</span>' : '') + '</div>';
    }

    // ======================= ОБЗОР =======================
    function overviewHtml(M) {
        var T = M.totals, sh = shortage(M), pg = priceGap(M), bt = bartenders(M);
        var minPct = M.aMin * 100;
        var marginShare = T.revenue > 0 ? T.margin / T.revenue * 100 : 0;
        var below = T.markup !== null && T.markup !== undefined && snap(T.markup / 100) < M.aMin;
        var scaleMax = Math.max(minPct * 1.6, (T.markup || 0) * 1.15);
        var html = '';

        // Маржа и показатели
        html += '<section class="av-card"><div class="av-hero">' +
            '<div class="av-hero-l">' +
                '<div><div class="av-label">Маржа ' + esc(periodWords(M)) + '</div>' +
                '<div class="av-big">' + nf(Math.round(T.margin)) + '<small>₽</small></div>' +
                '<div class="av-sub">с выручки ' + rub(T.revenue) + ' · ' + pct(marginShare) +
                    ' остаётся после закупки</div></div>' +
                split([
                    { v: T.margin, cls: 'av-c-margin', label: 'маржа', tip: [rub(T.margin), 'маржа · ' + pct(marginShare) + ' выручки'] },
                    { v: T.cost, cls: 'av-c-cost', label: 'закупка', tip: [rub(T.cost), 'закупка · ' + pct(100 - marginShare) + ' выручки'] }
                ]) +
                '<div class="av-keys"><span><i class="av-dot av-c-margin"></i>Маржа <b>' + rub(T.margin) + '</b></span>' +
                '<span><i class="av-dot av-c-cost"></i>Закупка <b>' + rub(T.cost) + '</b></span>' +
                '<span>Выручка <b>' + rub(T.revenue) + '</b></span></div>' +
            '</div><div class="av-kv av-hero-r">' +
                '<div class="av-kv-r"><span class="av-kv-l">Наценка</span>' +
                    '<span class="av-kv-v' + (below ? ' av-under' : '') + '">' + (T.markup === null || T.markup === undefined ? '—' : mk(T.markup)) + '</span>' +
                    '<div class="av-meter" role="img" aria-label="наценка ' + esc(T.markup === null || T.markup === undefined ? '—' : mk(T.markup)) +
                        ', минимум ' + nf(minPct) + '%"><i class="' + (below ? 'av-c-low_markup' : 'av-c-core') + '" style="width:' +
                        Math.min(100, (T.markup || 0) / scaleMax * 100).toFixed(1) + '%"></i><b style="left:' +
                        (minPct / scaleMax * 100).toFixed(1) + '%"></b></div>' +
                    '<span class="av-kv-s">' + (below ? 'ниже' : 'не ниже') + ' минимума сети ' + nf(minPct) + '% · черта — минимум</span></div>' +
                '<div class="av-kv-r"><span class="av-kv-l">Продано</span><span class="av-kv-v">' + nf(Math.round(T.qty)) + ' ' + M.unit + '</span>' +
                    '<span class="av-kv-s">' + (M.key === 'draft' ? nf(T.sales) + ' порций · ' + cnt(T.count, M.nom)
                        : cnt(T.count, M.nom) + ' · ' + cnt(T.cats, ['категория', 'категории', 'категорий'])) + '</span></div>' +
                '<div class="av-kv-r"><span class="av-kv-l">Выручка с ' + M.unitOne + '</span>' +
                    '<span class="av-kv-v">' + rub(T.unitPrice) + '</span>' +
                    '<span class="av-kv-s">выручка / ' + (M.key === 'draft' ? 'литры' : M.key === 'kitchen' ? 'порции' : 'штуки') + '</span></div>' +
            '</div></div>' +
            how(['Маржа = выручка − закупка. Выручка — по кассе iiko, уже со скидками. Закупка — себестоимость проданного по данным iiko.',
                'Наценка = (выручка − закупка) / закупка. Минимум сети — ' + nf(minPct) + '% для ' +
                    M.area + ' (решение владельца, core/abc_thresholds.py). Число печатается с округлением вниз, чтобы 249,96% не выглядело как «250%».',
                'Выручка с ' + M.unitOne + ' = выручка / ' + M.unitMany + '.',
                M.qtyNote]) +
            '</section>';

        // Где деньги
        var rows = '';
        function lrow(ic, tone, title, sub, val, valTone, note, go, filter) {
            return '<button type="button" class="av-lg" data-go="' + go + '"' + (filter ? ' data-filter="' + filter + '"' : '') + '>' +
                '<span class="av-lg-ic ' + tone + '">' + icon(ic, 18) + '</span>' +
                '<span><span class="av-lg-t">' + esc(title) + '</span><span class="av-lg-s">' + esc(sub) + '</span></span>' +
                '<span class="av-lg-v"><b class="' + valTone + '">' + esc(val) + '</b><span>' + esc(note) + '</span></span>' +
                '<span class="av-chev">' + icon('chev', 16) + '</span></button>';
        }
        if (pg.rows.length) {
            // Недобор — упущенная выручка, поэтому со знаком минус и красным, как потери:
            // «+» читался как заработок.
            rows += lrow('tag', 'neg', 'Цены ниже минимума сети',
                cnt(pg.rows.length, M.nom) + ' с наценкой ниже ' + nf(minPct) + '% · половину дают ' + nf(pg.half),
                srub(-pg.total), 'av-neg', 'недополучено при том же объёме', 'prices');
        }
        if (sh && sh.qty > 0) {
            rows += lrow('loss', 'neg', 'Недостача по инвентаризации',
                M.lossRub ? pct(sh.pct) + ' от списанного при продаже по складу'
                          : nf(sh.qty, M.qd) + ' ' + M.unit + ' · ' + pct(sh.pct) + ' от продаж',
                srub(-sh.cost), 'av-neg', 'по закупке', 'losses');
        }
        if (bt && bt.neg.length) {
            rows += lrow('people', 'neg', 'Бармены ниже средней на тех же кегах',
                nf(bt.neg.length) + ' из ' + nf(bt.rows.length) + ' · сильнее всех ' + bt.rows[0].name + ', ' + spct(bt.rows[0].idx),
                srub(bt.negSum), 'av-neg', 'к средней цене литра', 'people');
        }
        var chk = M.buckets.filter(function (b) { return b.key === 'check'; })[0];
        if (chk && chk.count > 0) {
            rows += lrow('check', 'check', 'Сверить учёт', cnt(chk.count, M.nom) +
                ': себестоимость не задана или наценка ниже ' + nf(M.bMin * 50) + '%',
                rub(chk.revenue), '', 'выручки без надёжной наценки', 'items', 'check');
        }
        html += '<section class="av-card">' + cardHead('Где деньги', periodWords(M)) +
            (rows ? '<div class="av-ledger">' + rows + '</div>'
                  : '<p class="av-lead">Цены не ниже минимума, недостачи нет' + (M.key === 'draft' ? ', бармены на уровне средней' : '') + '.</p>') +
            how([
                'Цены: недополучено = закупка × ' + nf(1 + M.aMin, 1) + ' − выручка по каждой позиции с наценкой ниже ' + nf(minPct) +
                    '% и продажами от ' + MIN_SALES + ' ' + M.salesWord + ', без «Сверить учёт». Считается при том же объёме, поэтому это верхняя граница.',
                M.lossRub ? 'Недостача: сумма инвентаризаций по закупке из проводок склада группы «ЕДА» (продукты и ингредиенты вместе), нетто по сети: излишек уменьшает недостачу.'
                          : 'Недостача: ' + M.unit + ' недостачи × средняя закупка ' + M.perWord + ' за период. Недостача считается по каждому бару: излишек одного бара не гасит недостачу другого.',
                M.key === 'draft' ? 'Бармены: выручка бармена против того, что дали бы те же литры тех же кегов по средней выручке с литра в разрезе.' : null,
                chk && chk.count > 0 ? '«Сверить учёт» — позиции без себестоимости или с наценкой ниже половины порога B: так в сети не продают, это учёт.' : null
            ]) + '</section>';

        // Решения и лидеры
        var bs = {};
        M.buckets.forEach(function (b) { bs[b.key] = b; });
        var order = BUCKET_ORDER.filter(function (k) { return bs[k]; });
        var alloc = split(order.map(function (k) {
            var b = bs[k];
            return { v: b.revenue, cls: 'av-c-' + k, label: b.name, tip: [pct(b.revenue_share_percent) + ' выручки', b.name + ' · ' + cnt(b.count, M.nom)] };
        }));
        var list = order.map(function (k) {
            var b = bs[k];
            var open = b.count > 0;
            return '<' + (open ? 'button type="button" data-go="items" data-filter="' + k + '"' : 'div') +
                ' class="av-li av-li-b' + (open ? '' : ' is-dim') + '">' +
                '<span class="av-li-n"><span class="av-li-t"><i class="av-dot av-c-' + k + '"></i>' + esc(b.name) + '</span>' +
                '<span class="av-li-s">' + esc(b.action) + '</span></span>' +
                '<span class="av-li-v">' + cnt(b.count, M.nom) + '</span>' +
                '<span class="av-li-v av-w64">' + pct(b.revenue_share_percent) + '</span></' + (open ? 'button' : 'div') + '>';
        }).join('');
        var top = M.items.slice().sort(function (a, b) { return b.revenue - a.revenue; }).slice(0, 6);
        var maxS = top.length ? top[0].share : 1;
        var leaders = top.map(function (it) {
            return '<button type="button" class="av-li" data-item="' + esc(it.id) + '">' +
                '<span class="av-li-n"><span class="av-li-t">' + esc(it.name) + '</span>' +
                '<span class="av-li-s">' + codeBadge(it.code) + ' ' + esc(it.cat) + '</span></span>' +
                bar(maxS > 0 ? it.share / maxS * 100 : 0) +
                '<span class="av-li-v">' + rub(it.revenue) + '<small>' + pct(it.share) + ' выручки</small></span></button>';
        }).join('');
        html += '<div class="av-row av-two">' +
            '<section class="av-card">' + cardHead('Выручка по решениям', cnt(T.count, M.nom)) + alloc +
                '<div class="av-list">' + list + '</div>' +
                how(['Каждая позиция ровно в одной группе. Клик по группе открывает её позиции.',
                    order.map(function (k) { return bs[k].name + ' — ' + bs[k].rule + '.'; }),
                    'Порядок проверки: «Сверить учёт», новинки, мало продаж, слабые продажи, низкая наценка; остальное — основа выручки. Решение «вывести» выносится только по периоду от четырёх недель.',
                    'Третья буква кода — стабильность спроса — в решении не участвует: она говорит, как планировать запас, а не что делать с позицией.']) +
            '</section>' +
            '<section class="av-card">' + cardHead('Лидеры выручки') +
                '<div class="av-list">' + leaders + '</div>' +
                '<button type="button" class="av-link" data-go="items">Все ' + cnt(T.count, M.nom) + ' ' + icon('chev', 14) + '</button>' +
            '</section></div>';
        return html;
    }

    // ======================= ЦЕНЫ =======================
    function pricesHtml(M, shown) {
        var pg = priceGap(M);
        var minPct = nf(M.aMin * 100) + '%', mult = nf(1 + M.aMin, 1);
        shown = shown || PRICE_STEP;
        var html = '<section class="av-card"><div class="av-label">Недополучено из-за цен ниже минимума сети ' + minPct + '</div>' +
            '<div class="av-big av-neg">' + srub(-pg.total) + '</div>' +
            '<p class="av-lead">' + esc(periodWords(M)) + ' при том же объёме продаж · <b>' + cnt(pg.rows.length, M.nom) +
            '</b> ниже минимума' + (pg.rows.length > 1 ? ' · половину суммы дают ' + (pg.half === 1 ? 'один ' + M.nom[0] : 'первые ' + nf(pg.half)) : '') + '.</p>' +
            how(['Недополучено по позиции = закупка × ' + mult + ' − выручка: столько не хватило до цены по минимуму. Наценка ' + minPct + ' означает цену в ' + mult + ' раза выше закупки.',
                M.priceNote + ', уже со скидками.',
                'Считается при том же объёме, поэтому это верхняя граница: после подорожания продаж может стать меньше.',
                'Не входят позиции из «Сверить учёт» и с продажами меньше ' + MIN_SALES + ' ' + M.salesWord + '.']) + '</section>';

        var max = pg.rows.length ? pg.rows[0].up : 1;
        var list = '';
        pg.rows.slice(0, shown).forEach(function (x, i) {
            list += '<button type="button" class="av-li" data-item="' + esc(x.it.id) + '">' +
                '<span class="av-li-n"><span class="av-li-t">' + esc(x.it.name) + '</span>' +
                '<span class="av-li-s">' + esc(M.per) + ': ' + nf(x.now) + ' → ' + rub(x.need) + ' · наценка ' + mk(x.it.markup) + '</span></span>' +
                bar(max > 0 ? x.up / max * 100 : 0, 'bad') +
                '<span class="av-li-v av-neg">' + srub(-x.up) + '</span></button>';
            if (i + 1 === pg.half && pg.half < Math.min(shown, pg.rows.length)) {
                list += '<div class="av-split-line">выше — половина суммы</div>';
            }
        });
        if (!pg.rows.length) list = '<p class="av-lead">У всех позиций с продажами от ' + MIN_SALES + ' ' + M.salesWord + ' наценка не ниже минимума.</p>';
        var more = pg.rows.length > shown
            ? '<button type="button" class="av-more" data-more="' + (shown + PRICE_STEP) + '">Показать ещё ' +
              nf(Math.min(PRICE_STEP, pg.rows.length - shown)) + '</button>' : '';
        html += '<div class="av-row av-two"><section class="av-card">' + cardHead('Где поднять цену', 'больше всего недополучено') +
            '<div class="av-list">' + list + '</div>' + more + '</section>';

        if (M.key === 'draft') {
            var sp = priceCost(M);
            var nU = sp.pts.filter(function (p) { return p.u; }).length;
            html += '<section class="av-card">' + cardHead('Цена против закупки', 'почему ниже минимума так много') +
                (sp.lo && sp.hi ? '<p class="av-lead">Самая дешёвая в закупке треть кегов наценена на <b>' + mk(sp.lo.mk) +
                    '</b>, самая дорогая — на <b>' + mk(sp.hi.mk) + '</b>. ' +
                    (sp.hi.mk < sp.lo.mk ? 'Цена растёт медленнее закупки. ' : 'Наценка от закупки почти не зависит. ') +
                    (sp.hi.mg > sp.lo.mg ? 'Зато с литра дорогие зарабатывают больше: ' + rub(sp.hi.mg) + ' против ' + rub(sp.lo.mg) + '.'
                                         : 'С литра дешёвые зарабатывают не меньше: ' + rub(sp.lo.mg) + ' против ' + rub(sp.hi.mg) + '.') + '</p>' : '') +
                '<div class="av-keys"><span><i class="av-sw u"></i>ниже минимума <b>' + nf(nU) + '</b></span>' +
                '<span><i class="av-sw r"></i>не ниже <b>' + nf(sp.pts.length - nU) + '</b></span><span>размер — литры</span></div>' +
                '<div class="av-chart" data-chart="price-cost"></div>' +
                how(['Точка — кег с продажами от ' + MIN_SALES + ' порций. По горизонтали закупка литра, по вертикали выручка с литра со скидками.',
                    'Линия — минимум сети: цена = ' + mult + ' × закупка; всё, что под ней, наценено ниже ' + minPct + '.',
                    'Трети — по закупке литра; «наценена на» — медиана трети. Маржа с литра = выручка с литра − закупка литра.']) +
                '</section>';
        } else {
            var byCat = {};
            pg.rows.forEach(function (x) {
                var c = byCat[x.it.cat] || (byCat[x.it.cat] = { up: 0, n: 0 });
                c.up += x.up;
                c.n++;
            });
            var cl = Object.keys(byCat).map(function (k) { return { cat: k, up: byCat[k].up, n: byCat[k].n }; })
                .sort(function (a, b) { return b.up - a.up || byName(a.cat, b.cat); });
            var mx = cl.length ? cl[0].up : 1;
            html += '<section class="av-card">' + cardHead('По категориям', 'где недополучено больше всего') + '<div class="av-list">' +
                cl.slice(0, 10).map(function (x) {
                    return '<div class="av-li"><span class="av-li-n"><span class="av-li-t">' + esc(x.cat) + '</span>' +
                        '<span class="av-li-s">' + cnt(x.n, M.nom) + ' ниже ' + minPct + '</span></span>' +
                        bar(mx > 0 ? x.up / mx * 100 : 0, 'bad') + '<span class="av-li-v av-neg">' + srub(-x.up) + '</span></div>';
                }).join('') + '</div>' +
                (cl.length > 10 ? '<div class="av-sub">ещё ' + cnt(cl.length - 10, ['категория', 'категории', 'категорий']) + ' — ' +
                    srub(-cl.slice(10).reduce(function (a, x) { return a + x.up; }, 0)) + '</div>' : '') +
                how(['Сумма недополученного по позициям категории. Пересматривать цены удобнее категорией: ' + M.catNote + '.']) +
                '</section>';
        }
        return html + '</div>';
    }

    function niceStep(span, count) {
        var raw = span / count, p = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), f = raw / p;
        return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
    }
    function niceDomain(min, max, count) {
        var st = niceStep(Math.max(max - min, 1), count);
        return { lo: Math.floor(min / st) * st, hi: Math.ceil(max / st) * st, st: st };
    }

    // Точечный график «цена против закупки»: SVG строкой под ширину контейнера.
    function scatterSvg(M, width) {
        var sp = priceCost(M);
        var pts = sp.pts;
        if (pts.length < 3) return '<p class="av-lead">Мало кегов с продажами от ' + MIN_SALES + ' порций: сравнивать не с чем.</p>';
        var W = Math.max(300, Math.round(width || 560)), narrow = W < 460;
        var Ht = Math.round(Math.min(340, Math.max(250, W * 0.58)));
        var m = { l: 46, r: 12, t: 20, b: 34 };
        var xs = pts.map(function (p) { return p.x; }), ys = pts.map(function (p) { return p.y; });
        var dx = niceDomain(Math.min.apply(null, xs) * 0.9, Math.max.apply(null, xs) * 1.04, narrow ? 4 : 6);
        var dy = niceDomain(Math.min.apply(null, ys) * 0.9, Math.max.apply(null, ys) * 1.04, 5);
        var x0 = m.l, x1 = W - m.r, y0 = Ht - m.b, y1 = m.t;
        function X(v) { return x0 + (v - dx.lo) / (dx.hi - dx.lo) * (x1 - x0); }
        function Y(v) { return y0 - (v - dy.lo) / (dy.hi - dy.lo) * (y0 - y1); }
        function f1(v) { return v.toFixed(1); }
        var svg = '<svg viewBox="0 0 ' + W + ' ' + Ht + '" width="' + W + '" height="' + Ht + '" role="img" ' +
            'aria-label="Выручка с литра против закупки литра по кегам; линия — минимум сети">';
        for (var gy = dy.lo; gy <= dy.hi + 1e-9; gy += dy.st) {
            svg += '<line x1="' + x0 + '" x2="' + x1 + '" y1="' + f1(Y(gy)) + '" y2="' + f1(Y(gy)) + '" class="' + (gy === dy.lo ? 'av-bl' : 'av-gl') + '"/>' +
                '<text x="' + (x0 - 7) + '" y="' + f1(Y(gy) + 3.5) + '" text-anchor="end" class="av-ax">' + nf(gy) + '</text>';
        }
        for (var gx = dx.lo; gx <= dx.hi + 1e-9; gx += dx.st) {
            svg += '<text x="' + f1(X(gx)) + '" y="' + (y0 + 15) + '" text-anchor="middle" class="av-ax">' + nf(gx) + '</text>';
        }
        svg += '<text x="' + (x0 - 7) + '" y="' + (y1 - 7) + '" class="av-ax-t">выручка с литра, ₽</text>' +
            '<text x="' + x1 + '" y="' + (Ht - 3) + '" text-anchor="end" class="av-ax-t">закупка литра, ₽</text>';
        var k = 1 + M.aMin;
        var lx0 = Math.max(dx.lo, dy.lo / k), lx1 = Math.min(dx.hi, dy.hi / k);
        if (lx1 > lx0) {
            var zone = [[X(lx0), Y(k * lx0)], [X(lx1), Y(k * lx1)]];
            if (lx1 < dx.hi) zone.push([x1, y1]);
            zone.push([x1, y0], [X(lx0), y0]);
            svg += '<polygon points="' + zone.map(function (p) { return f1(p[0]) + ',' + f1(p[1]); }).join(' ') + '" class="av-zone"/>' +
                '<line x1="' + f1(X(lx0)) + '" y1="' + f1(Y(k * lx0)) + '" x2="' + f1(X(lx1)) + '" y2="' + f1(Y(k * lx1)) + '" class="av-minl"/>';
            var lbl = 'минимум ' + nf(M.aMin * 100) + '%', lw = lbl.length * 6.3;
            svg += lx1 < dx.hi
                ? '<text x="' + f1(Math.min(x1 - lw / 2, Math.max(x0 + 130 + lw / 2, X(lx1)))) + '" y="' + (y1 - 7) + '" text-anchor="middle" class="av-minlbl">' + lbl + '</text>'
                : '<text x="' + (x1 - 4) + '" y="' + f1(Y(k * lx1) + 14) + '" text-anchor="end" class="av-minlbl">' + lbl + '</text>';
        }
        var vmax = Math.max.apply(null, pts.map(function (p) { return p.v; }));
        function R(p) { return 3.5 + 8 * Math.sqrt(p.v / vmax); }
        var order = pts.slice().sort(function (a, b) { return b.v - a.v; });
        order.forEach(function (p) {
            svg += '<circle cx="' + f1(X(p.x)) + '" cy="' + f1(Y(p.y)) + '" r="' + f1(R(p)) + '" class="av-pt ' + (p.u ? 'u' : 'r') + '"/>';
        });
        // Подписи выборочно: самый продаваемый, самый дорогой в закупке, самый большой недобор.
        var picks = [];
        function pick(p) { if (p && picks.indexOf(p) < 0) picks.push(p); }
        pick(order[0]);
        pick(pts.slice().sort(function (a, b) { return b.x - a.x; })[0]);
        pick(pts.filter(function (p) { return p.u; }).sort(function (a, b) {
            return (b.it.cost * k - b.it.revenue) - (a.it.cost * k - a.it.revenue);
        })[0]);
        if (narrow) picks = picks.slice(0, 2);
        var boxes = [];
        picks.forEach(function (p) {
            var name = p.it.name.replace(/,?\s*\d+([,.]\d+)?\s*л\.?\s*$/i, '');
            var w = name.length * 6.1, cx = X(p.x), cy = Y(p.y), rr = R(p);
            var right = cx + rr + 6 + w < x1, tx = right ? cx + rr + 6 : cx - rr - 6;
            var bx = right ? [tx, cy - 9, tx + w, cy + 5] : [tx - w, cy - 9, tx, cy + 5];
            if (boxes.some(function (b) { return !(bx[2] < b[0] || bx[0] > b[2] || bx[3] < b[1] || bx[1] > b[3]); })) return;
            boxes.push(bx);
            svg += '<text x="' + f1(tx) + '" y="' + f1(cy + 3.5) + '" text-anchor="' + (right ? 'start' : 'end') + '" class="av-plbl">' + esc(name) + '</text>';
        });
        // Зоны наведения больше точки: 24 px минимум, клик открывает карточку кега.
        order.slice().reverse().forEach(function (p) {
            svg += '<circle cx="' + f1(X(p.x)) + '" cy="' + f1(Y(p.y)) + '" r="' + f1(Math.max(12, R(p) + 6)) + '" class="av-hit" data-item="' +
                esc(p.it.id) + '"' + tipAttr([rub(p.y) + ' за литр', p.it.full || p.it.name, 'закупка ' + rub(p.x) + ' · наценка ' + mk(p.it.markup),
                    'маржа с литра ' + rub(p.y - p.x), 'продано ' + nf(p.v, 1) + ' л']) + '/>';
        });
        return svg + '</svg>';
    }

    // ======================= БАРМЕНЫ (розлив) =======================
    function peopleHtml(M) {
        var bt = bartenders(M);
        if (!bt || bt.rows.length < 2) return '';
        var lim = Math.max(1, Math.ceil(Math.max.apply(null, bt.rows.map(function (r) { return Math.abs(r.idx); }))));
        var g = bt.rows.slice().sort(function (a, b) { return Math.abs(b.raw - b.idx) - Math.abs(a.raw - a.idx); })[0];
        var rows = bt.rows.map(function (r) {
            return '<button type="button" class="av-li av-li-d" data-person="' + esc(r.name) + '">' +
                '<span class="av-li-n"><span class="av-li-t">' + esc(r.name) + '</span>' +
                '<span class="av-li-s">' + nf(r.L, 1) + ' л · ' + rub(r.actPL) + ' за литр, на тех же кегах по средней ' + rub(r.expPL) + '</span></span>' +
                '<span class="av-dtrack"><i class="' + (r.idx < 0 ? 'n' : 'p') + '" style="width:' + (Math.abs(r.idx) / lim * 50).toFixed(1) + '%"></i></span>' +
                '<span class="av-li-v' + (r.diff < 0 ? ' av-neg' : '') + '">' + spct(r.idx) + '<small>' + srub(r.diff) + '</small></span></button>';
        }).join('');
        return '<section class="av-card">' + cardHead('Выручка с литра против средней на тех же кегах', periodWords(M)) +
            (bt.neg.length ? '<p class="av-lead"><b>' + nf(bt.neg.length) + ' из ' + nf(bt.rows.length) + '</b> получили с литра меньше, чем дали бы те же кеги по средней цене. ' +
                'Вместе <b>' + srub(bt.negSum) + '</b>; сильнее всех — ' + esc(bt.rows[0].name) + ', ' + spct(bt.rows[0].idx) + '.</p>'
                : '<p class="av-lead">На тех же кегах никто не получил с литра меньше средней.</p>') +
            '<div class="av-dscale"><span></span><span class="av-dscale-in"><span>−' + nf(lim) + '%</span><span>средняя</span><span>+' + nf(lim) + '%</span></span><i></i></div>' +
            '<div class="av-list">' + rows + '</div>' +
            how(['Ожидаемая выручка = литры бармена по каждому кегу × средняя выручка с литра этого кега в разрезе. Так сравнение не зависит от того, какие сорта бармен наливал.',
                g && g.raw !== null && Math.abs(g.raw - g.idx) >= 0.05 ? 'В таблице ниже цена литра без этой поправки. Пример: ' + g.name + ' — ' + spct(g.raw) +
                    ' к средней цене литра, а на тех же кегах ' + spct(g.idx) + '.' : null,
                'Отклонение — повод разобраться, а не вывод: так выглядят скидки, happy hour в смену, разные цены в барах и доля маленьких порций (литр в 0,25 л дороже).']) +
            '</section>';
    }

    // ======================= БАРЫ (фасовка и кухня) =======================
    function heatClass(dev) {
        var a = Math.abs(dev);
        if (a < HEAT_WEAK) return 'h-0';
        return (dev > 0 ? 'h-o' : 'h-u') + (a >= HEAT_STRONG ? '2' : '1');
    }
    function times(a, b) { return b > 0 ? nf(a / b, 1) : '—'; }
    function barsHtml(M) {
        var sp = barProfile(M);
        if (!sp) return '';
        var html = '<div class="av-row av-four">' + sp.info.map(function (i) {
            var b = i.best;
            var below = i.markup !== null && snap(i.markup / 100) < M.aMin;
            return '<section class="av-card"><div class="av-label">' + esc(i.bar) + '</div>' +
                '<div class="av-mid">' + nf(Math.round(i.rev)) + '<small>₽</small></div>' +
                '<div class="av-kv">' +
                '<div class="av-kv-r"><span class="av-kv-l">Доля сети</span><span class="av-kv-v">' + pct(i.share) + '</span></div>' +
                '<div class="av-kv-r"><span class="av-kv-l">Наценка</span><span class="av-kv-v' + (below ? ' av-under' : '') + '">' +
                    (i.markup === null ? '—' : mk(i.markup)) + '</span></div>' +
                '<div class="av-kv-r"><span class="av-kv-l">Цена ' + M.unitOne + ' к сети</span><span class="av-kv-v">' + (i.price === null ? '—' : spct(i.price)) + '</span></div>' +
                '</div>' +
                (b && Math.abs(b.c.dev) >= HEAT_WEAK ? '<div class="av-sub">Отличие: <b>' + esc(b.r.name.replace(/\s*\(Ф\)\s*$/, '')) + '</b> ' +
                    (b.c.dev > 0 ? 'в ' + times(b.c.share, b.r.net) + ' раза чаще сети'
                        // Доля 0% — «в N раз реже» не посчитать: бар эту категорию не берёт.
                        : b.c.share > 0 ? 'в ' + times(b.r.net, b.c.share) + ' раза реже сети'
                        : 'не берут, в сети ' + pct(b.r.net)) + '</div>' : '') +
                '</section>';
        }).join('') + '</div>';
        var mks = sp.info.filter(function (i) { return i.markup !== null; }).sort(function (a, b) { return a.markup - b.markup; });
        var pr = sp.info.filter(function (i) { return i.price !== null; }).map(function (i) { return i.price; });
        var head = '<tr><th>Категория</th>' + sp.info.map(function (i) { return '<th>' + esc(i.bar) + '</th>'; }).join('') + '<th>Сеть</th></tr>';
        var body = sp.rows.concat(sp.extra).map(function (r, ri) {
            var ctx = ri >= sp.rows.length;
            return '<tr' + (ctx ? ' class="ctx"' : '') + '><th scope="row" title="' + esc(r.name) + '">' + esc(r.name) + '</th>' +
                r.cells.map(function (c) {
                    return '<td class="' + (ctx ? '' : heatClass(c.dev)) + '"' + tipAttr([pct(c.share) + ' выручки ' + M.area + ' бара', c.bar + ' · ' + r.name,
                        rub(c.rub) + ' · по сети ' + pct(r.net),
                        Math.abs(c.dev) < 0.05 ? 'как в среднем по сети' : 'на ' + nf(Math.abs(c.dev), 1) + ' п.п. ' + (c.dev > 0 ? 'больше' : 'меньше') + ', чем в среднем']) +
                        '>' + pct(c.share) + '</td>';
                }).join('') + '<td class="net">' + pct(r.net) + '</td></tr>';
        }).join('');
        html += '<section class="av-card">' + cardHead('Что берут в каждом баре', 'доля категории в выручке ' + M.area + ' бара') +
            (mks.length > 1 && pr.length ? '<p class="av-lead">Наценка по барам — от <b>' + mk(mks[0].markup) + '</b> (' + esc(mks[0].bar) + ') до <b>' +
                mk(mks[mks.length - 1].markup) + '</b> (' + esc(mks[mks.length - 1].bar) + '). Одни и те же ' + (M.key === 'kitchen' ? 'позиции' : 'бутылки') + ' стоят почти одинаково: от ' +
                spct(Math.min.apply(null, pr)) + ' до ' + spct(Math.max.apply(null, pr)) + ' к средней. Разницу даёт набор покупок.</p>' : '') +
            '<div class="av-keys"><span><i class="av-sw h-o2"></i>чаще сети от ' + HEAT_STRONG + ' п.п.</span><span><i class="av-sw h-o1"></i>' +
                HEAT_WEAK + '–' + HEAT_STRONG + ' п.п. чаще</span><span><i class="av-sw h-0"></i>как в сети</span><span><i class="av-sw h-u1"></i>' +
                HEAT_WEAK + '–' + HEAT_STRONG + ' п.п. реже</span><span><i class="av-sw h-u2"></i>реже от ' + HEAT_STRONG + ' п.п.</span></div>' +
            '<div class="av-scroll"><table class="av-heat"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>' +
            how(['Доля категории в выручке ' + M.area + ' бара за период; «Сеть» — та же доля по всем барам.',
                'Цвет — отличие от сети в процентных пунктах' + (sp.bottles ? ': ' + HEAT_WEAK + ' п.п. в баре — около ' +
                    cnt(Math.round(sp.bottles), M.goods) + ' за период, меньше — обычный разброс.' : '.'),
                'Цена ' + M.unitOne + ' к сети — выручка бара против тех же ' + M.goods[2] + ' по средней цене сети.',
                'Две нижние строки без заливки: «Без категории» — ' + cnt(sp.uncCount, ['позиция', 'позиции', 'позиций']) +
                    ' без стиля в номенклатуре iiko, а в сборной строке разные стили смешаны.']) +
            '</section>';
        return html;
    }

    // ======================= фильтр таблицы по группе =======================
    function chipsHtml(M, active) {
        var bs = {};
        M.buckets.forEach(function (b) { bs[b.key] = b; });
        var html = '<button type="button" class="av-chip" data-filter="all" aria-pressed="' + (!active ? 'true' : 'false') + '">Все <span class="n">' +
            nf(M.items.length) + '</span></button>';
        BUCKET_ORDER.forEach(function (k) {
            var b = bs[k];
            if (!b) return;
            html += '<button type="button" class="av-chip" data-filter="' + k + '" aria-pressed="' + (active === k ? 'true' : 'false') + '"' +
                (b.count ? '' : ' disabled') + '><i class="av-dot av-c-' + k + '"></i>' + esc(BUCKET_SHORT[k]) +
                ' <span class="n">' + nf(b.count) + '</span></button>';
        });
        if (active && bs[active]) {
            html += '<button type="button" class="av-link" data-rule="' + active + '">Правило группы ' + icon('chev', 14) + '</button>';
        }
        return html;
    }

    // Строка «недостача в деньгах» для карточки баланса страницы.
    function shortageLineHtml(M, cls) {
        var sh = shortage(M);
        if (!sh || !(sh.qty > 0)) return '';
        return '<div class="' + cls + '"' + tipAttr([rub(sh.cost) + ' по закупке',
            nf(sh.qty, M.qd) + ' ' + M.unit + ' × средняя закупка ' + M.perWord + ' за период',
            'по цене продажи — сколько принесло бы это, если бы его продали']) + '>недостача в деньгах: <b>≈ ' +
            rub(sh.cost) + '</b> по закупке · <b>' + rub(sh.price) + '</b> по цене продажи</div>';
    }

    // ======================= вкладки и связка со страницей =======================
    function tabsFor(M) {
        var sh = shortage(M), pg = priceGap(M);
        var t = [
            { id: 'overview', title: 'Обзор' },
            { id: 'items', title: M.itemsWord, n: nf(M.totals.count) },
            { id: 'cats', title: 'Категории', n: nf(M.totals.cats) },
            { id: 'prices', title: 'Цены', n: pg.rows.length ? '−' + thousands(pg.total) : '', neg: true },
            { id: 'losses', title: 'Потери', n: sh && sh.qty > 0 ? '−' + thousands(sh.cost) : '', neg: true }
        ];
        if (M.key === 'draft') t.push({ id: 'people', title: 'Бармены', n: nf(M.people.length) });
        if (barProfile(M)) t.push({ id: 'bars', title: 'Бары', n: nf(M.barNames.length) });
        return t;
    }
    function tabsHtml(M, active) {
        return tabsFor(M).map(function (t) {
            return '<button type="button" class="av-tab" role="tab" data-tab="' + t.id + '" aria-selected="' + (t.id === active ? 'true' : 'false') + '">' +
                esc(t.title) + (t.n ? '<span class="n' + (t.neg ? ' neg' : '') + '">' + esc(t.n) + '</span>' : '') + '</button>';
        }).join('');
    }

    // cfg: { tabs: элемент полосы вкладок, panels: {id: элемент}, boxes: {overview, prices, people, bars, chips},
    //        open: { item(id), person(name), rule(bucket) }, filter(bucket|null) }
    function mount(cfg) {
        var st = { cfg: cfg, M: null, tab: 'overview', filter: null, priceShown: PRICE_STEP, width: 0 };
        var hash = String((window.location && window.location.hash) || '').replace('#', '');
        if (cfg.panels[hash]) st.tab = hash;

        function show(tab, scroll) {
            if (!cfg.panels[tab] || (st.M && !tabsFor(st.M).some(function (t) { return t.id === tab; }))) tab = 'overview';
            st.tab = tab;
            Object.keys(cfg.panels).forEach(function (k) { cfg.panels[k].hidden = k !== tab; });
            if (st.M) cfg.tabs.innerHTML = tabsHtml(st.M, tab);
            try { if (window.history && window.history.replaceState) window.history.replaceState(null, '', '#' + tab); } catch (e) { /* без истории */ }
            if (tab === 'prices') drawScatter();
            if (scroll && cfg.tabs.getBoundingClientRect && window.scrollTo) {
                var top = cfg.tabs.getBoundingClientRect().top + (window.pageYOffset || 0) - 4;
                if ((window.pageYOffset || 0) > top) window.scrollTo(0, top);
            }
            hideTip();
        }
        function setFilter(key) {
            st.filter = key && key !== 'all' ? key : null;
            if (st.M && cfg.boxes.chips) cfg.boxes.chips.innerHTML = chipsHtml(st.M, st.filter);
            if (cfg.filter) cfg.filter(st.filter);
        }
        function drawScatter() {
            if (!st.M || st.M.key !== 'draft' || !cfg.boxes.prices || !cfg.boxes.prices.querySelector) return;
            var node = cfg.boxes.prices.querySelector('[data-chart="price-cost"]');
            if (!node) return;
            var w = node.clientWidth || 560;
            node.innerHTML = scatterSvg(st.M, w);
            st.width = w;
        }
        function onClick(e) {
            var t = e && e.target && e.target.closest ? e.target : null;
            if (!t) return;
            var el = t.closest('[data-tab]');
            if (el) { show(el.getAttribute('data-tab'), true); return; }
            // Переход в другую вкладку; группа решения — сразу с фильтром таблицы.
            el = t.closest('[data-go]');
            if (el) {
                var f = el.getAttribute('data-filter');
                if (f) setFilter(f);
                else if (el.getAttribute('data-go') === 'items') setFilter(null);
                show(el.getAttribute('data-go'), true);
                return;
            }
            // Фильтр над таблицей позиций.
            el = t.closest('[data-filter]');
            if (el) { setFilter(el.getAttribute('data-filter')); return; }
            el = t.closest('[data-more]');
            if (el) { st.priceShown = +el.getAttribute('data-more'); cfg.boxes.prices.innerHTML = pricesHtml(st.M, st.priceShown); drawScatter(); return; }
            el = t.closest('[data-rule]');
            if (el && cfg.open.rule) { cfg.open.rule(el.getAttribute('data-rule')); return; }
            el = t.closest('[data-item]');
            if (el && cfg.open.item) { hideTip(); cfg.open.item(el.getAttribute('data-item')); return; }
            el = t.closest('[data-person]');
            if (el && cfg.open.person) { hideTip(); cfg.open.person(el.getAttribute('data-person')); }
        }
        [cfg.tabs].concat(Object.keys(cfg.boxes).map(function (k) { return cfg.boxes[k]; })).forEach(function (node) {
            if (!node || !node.addEventListener) return;
            node.addEventListener('click', onClick);
            node.addEventListener('mousemove', onHover);
            node.addEventListener('mouseleave', hideTip);
        });
        if (window.addEventListener) {
            window.addEventListener('resize', function () {
                if (st.tab === 'prices' && cfg.boxes.prices && cfg.boxes.prices.querySelector) {
                    var node = cfg.boxes.prices.querySelector('[data-chart="price-cost"]');
                    if (node && node.clientWidth && node.clientWidth !== st.width) drawScatter();
                }
            });
            window.addEventListener('hashchange', function () {
                var h = String(window.location.hash || '').replace('#', '');
                if (h && h !== st.tab && cfg.panels[h]) show(h, false);
            });
        }

        return {
            render: function (M) {
                st.M = M;
                st.priceShown = PRICE_STEP;
                if (st.filter && !M.buckets.some(function (b) { return b.key === st.filter && b.count > 0; })) st.filter = null;
                cfg.boxes.overview.innerHTML = overviewHtml(M);
                cfg.boxes.prices.innerHTML = pricesHtml(M, st.priceShown);
                if (cfg.boxes.people) cfg.boxes.people.innerHTML = peopleHtml(M);
                if (cfg.boxes.bars) cfg.boxes.bars.innerHTML = barsHtml(M);
                if (cfg.boxes.chips) cfg.boxes.chips.innerHTML = chipsHtml(M, st.filter);
                show(st.tab, false);
            },
            show: show,
            filter: function () { return st.filter; },
            setFilter: setFilter,
            tab: function () { return st.tab; }
        };
    }

    // ---------------- подсказка ----------------
    var tipEl = null;
    function onHover(e) {
        var t = e && e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
        if (!t) { hideTip(); return; }
        if (!tipEl) {
            if (!document.createElement) return;
            tipEl = document.createElement('div');
            tipEl.className = 'av-tip';
            tipEl.setAttribute('role', 'tooltip');
            document.body.appendChild(tipEl);
        }
        var lines = String(t.getAttribute('data-tip') || '').split('\n');
        tipEl.innerHTML = lines.map(function (l, i) { return '<div class="' + (i ? 'av-tip-n' : 'av-tip-v') + '">' + esc(l) + '</div>'; }).join('');
        tipEl.hidden = false;
        var x = e.pageX + 14, y = e.pageY + 14;
        var right = window.pageXOffset + document.documentElement.clientWidth - 8;
        var bottom = window.pageYOffset + window.innerHeight - 8;
        if (x + tipEl.offsetWidth > right) x = Math.max(window.pageXOffset + 8, e.pageX - tipEl.offsetWidth - 14);
        if (y + tipEl.offsetHeight > bottom) y = e.pageY - tipEl.offsetHeight - 14;
        tipEl.style.left = x + 'px';
        tipEl.style.top = y + 'px';
    }
    function hideTip() { if (tipEl) tipEl.hidden = true; }

    window.AbcView = {
        MIN_SALES: MIN_SALES, fromKitchen: fromKitchen, BUCKET_ORDER: BUCKET_ORDER,
        fromDraft: fromDraft, fromPackaging: fromPackaging,
        priceGap: priceGap, shortage: shortage, lossRubles: lossRubles, bartenders: bartenders,
        priceCost: priceCost, barProfile: barProfile,
        overviewHtml: overviewHtml, pricesHtml: pricesHtml, peopleHtml: peopleHtml, barsHtml: barsHtml,
        scatterSvg: scatterSvg, chipsHtml: chipsHtml, tabsFor: tabsFor, tabsHtml: tabsHtml,
        shortageLineHtml: shortageLineHtml, how: how, mount: mount, rub: rub
    };
})();

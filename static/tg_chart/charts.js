/* Графики бота @MCPkulturabot: описание графика (kultura_bot/charts/spec.py) -> карточка с ECharts.
 *
 * Один модуль на три места: мини-приложение (app.js), dev-страница (dev.js) и PNG для
 * чата (png.js через kultura_bot/charts/png.py). Поэтому картинка в чате и интерактивная
 * версия совпадают по цветам, подписям и раскладке.
 *
 * window.TgChart:
 *   mount(container, spec, opts)  карточка: заголовок, переключатели, график, «Как
 *                                 считается», таблица, подвал. opts.mode: app | dev | png
 *   buildOption(spec, st, palette, width, mode)  опция ECharts без DOM (тесты)
 *   initialState(spec), fmt, calc, fontsReady()
 *
 * Правила расчёта (они же — в «Как считается» на карточке и в docs/tg-miniapp.md):
 *   изменение, %  = (текущий − база) / |база| × 100, один знак; база 0 или нет — не считается
 *   итог          = сумма значений без пропусков (null); только если additive
 *   доля          = значение / итог всех категорий × 100, до целого; меньше 0,5 — «меньше 1%»
 *   подпись       = значение / scale; при scale > 1 — до целого (меньше 10 — один знак)
 *   точно         = значение с decimals знаками (подсказка, таблица)
 */
(function (root) {
  'use strict';

  const FONT = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
  const CHAR_PX = 7.3;          // ширина символа 12px IBM Plex Mono: влезает ли подпись в столбик
  const ROW_PX = { rating: 40, stack: 56 };   // высота строки рейтинга и стека (как в прототипе)
  const HEAD_PX = { rating: 26, stack: 28 };  // запас сверху под подпись первой строки
  const PERIODS_PX = 290;
  const DAYS_PX = 300;
  const ZOOM_MIN_POINTS = 15;   // зум по периоду — от 15 дней: две недели читаются и так
  const PRESET_MIN_POINTS = 32; // кнопки «30 дн / 7 дн» — когда дней больше месяца
  const PRESET_DAYS = [30, 7];
  const PCT_UNDER_LABEL_MAX = 6; // изменение в % под подписью столбика — при 6 категориях и меньше

  // Ключ цвета из описания -> токен CSS (tg_chart.css). Ink — цвет подписи внутри заливки.
  const COLOR_TOKEN = {
    accent: 'ev', base: 'base', greige: 'greige', other: 'other',
    part_light: 'chk-ev', part_dark: 'chk-rest',
    bolshoy: 'vo', ligovskiy: 'lig', kremenchugskaya: 'krem', varshavskaya: 'var',
  };
  const TWO_PARTS = ['part_light', 'part_dark'];
  const CYCLE = ['accent', 'varshavskaya', 'ligovskiy', 'kremenchugskaya', 'bolshoy', 'greige', 'part_dark', 'other'];
  const TOKENS = ['ink', 'ink-2', 'muted', 'grid', 'hover', 'card', 'track', 'up', 'down', 'tip', 'tip-line',
    'tip-shadow'].concat(...Object.values(COLOR_TOKEN).map(t => [t, t + '-ink']));
  const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
  const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
  const VALUE_LABEL = { '₽': 'Рубли', 'л': 'Литры', 'шт': 'Штуки', 'шт.': 'Штуки' };

  /* ---------------- форматирование ---------------- */

  const nfCache = {};
  function nfAbs(v, d) {
    const f = nfCache[d] || (nfCache[d] = new Intl.NumberFormat('ru-RU',
      { minimumFractionDigits: d, maximumFractionDigits: d }));
    return f.format(Math.abs(v));
  }
  const roundTo = (v, d) => Math.round(v * Math.pow(10, d)) / Math.pow(10, d);
  function num(v, d) {
    if (v == null) return '—';
    return (roundTo(v, d) < 0 ? '−' : '') + nfAbs(v, d);
  }
  function signed(v, d) {
    if (v == null) return '—';
    const r = roundTo(v, d);
    return (r > 0 ? '+' : r < 0 ? '−' : '') + nfAbs(v, d);
  }
  function plural(n, forms) {
    if (!Number.isInteger(n)) return forms[1];      // дробное: «2,5 литра»
    const a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b === 1) return forms[0];
    if (b > 1 && b < 5) return forms[1];
    return forms[2];
  }
  function unitFor(spec, v) {
    const forms = spec.unit_forms || [];
    return forms.length === 3 && v != null ? plural(roundTo(v, spec.decimals), forms) : spec.unit;
  }
  const exact = (spec, v) => (v == null ? '—' : num(v, spec.decimals) + ' ' + unitFor(spec, v));
  const exactSigned = (spec, v) => (v == null ? '—' : signed(v, spec.decimals) + ' ' + unitFor(spec, Math.abs(v)));
  function scaledUnit(spec) {
    if (spec.scale === 1000) return 'тыс. ' + spec.unit;
    if (spec.scale === 1000000) return 'млн ' + spec.unit;
    return spec.unit;
  }
  function scaledDecimals(spec, x) {
    if (spec.scale === 1) return spec.decimals;
    return Math.abs(x) >= 10 || Number.isInteger(x) ? 0 : 1;
  }
  function short(spec, v) {          // подпись на графике: в единицах scale, без единицы
    if (v == null) return '—';
    const x = v / spec.scale;
    return num(x, scaledDecimals(spec, x));
  }
  function shortUnit(spec, v) {      // подпись с единицей: без деления — со склонением («54 порции»)
    if (v == null) return '—';
    return spec.scale === 1 ? exact(spec, v) : short(spec, v) + ' ' + scaledUnit(spec);
  }
  const pctText = (p, arrow) => (p == null ? '—' : (arrow ? (roundTo(p, 1) >= 0 ? '▲ ' : '▼ ') : '') + signed(p, 1) + '%');

  function parseDay(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
    if (!m) return null;
    const y = +m[1], mo = +m[2], d = +m[3];
    return { y, mo, d, wd: new Date(Date.UTC(y, mo - 1, d)).getUTCDay() };
  }
  function dayShort(s) { const p = parseDay(s); return p ? p.d + ' ' + MONTHS[p.mo - 1] : s; }
  function dayLong(s) {
    const p = parseDay(s);
    return p ? WEEKDAYS[p.wd] + ', ' + p.d + ' ' + MONTHS[p.mo - 1] + ' ' + p.y : s;
  }
  function dayRange(a, b) {
    const pa = parseDay(a), pb = parseDay(b);
    if (!pa || !pb) return a + ' – ' + b;
    const right = pb.d + ' ' + MONTHS[pb.mo - 1] + ' ' + pb.y;
    if (a === b) return right;
    return pa.d + ' ' + MONTHS[pa.mo - 1] + (pa.y !== pb.y ? ' ' + pa.y : '') + ' – ' + right;
  }
  function dataAt(iso) {             // сервер приводит data_at к +03:00 — часы и есть МСК
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || '');
    return m ? +m[3] + ' ' + MONTHS[+m[2] - 1] + ' ' + m[1] + ', ' + m[4] + ':' + m[5] + ' МСК' : '';
  }
  function valueLabel(spec) {
    if (VALUE_LABEL[spec.unit]) return VALUE_LABEL[spec.unit];
    const forms = spec.unit_forms || [];
    if (forms.length === 3) return forms[1].charAt(0).toUpperCase() + forms[1].slice(1);
    return 'Значения';
  }
  const richSafe = s => String(s).replace(/[{}|]/g, ch => (ch === '{' ? '(' : ch === '}' ? ')' : '/'));

  /* ---------------- расчёты (без DOM) ---------------- */

  function pct(cur, base) {
    if (cur == null || base == null || base === 0) return null;
    return (cur - base) / Math.abs(base) * 100;
  }
  function sum(values) {
    let s = 0, any = false;
    for (const v of values) if (v != null) { s += v; any = true; }
    return any ? s : null;
  }
  const byRole = (spec, role) => spec.series.find(s => s.role === role);
  const isParts = spec => spec.series.every(s => s.role === 'part');
  function cmpDesc(a, b) {
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    return b - a;
  }

  function colorKeys(spec) {
    const used = new Set(spec.series.map(s => s.color).filter(Boolean));
    const cycle = CYCLE.filter(k => !used.has(k));
    const parts = spec.series.filter(s => s.role === 'part');
    const plain = spec.series.filter(s => s.role === 'value' && !s.color);
    const twoParts = TWO_PARTS.filter(k => !used.has(k));
    const out = {};
    for (const s of spec.series) {
      if (s.color) out[s.key] = s.color;
      else if (s.role === 'current') out[s.key] = 'accent';
      else if (s.role === 'base') out[s.key] = spec.kind === 'days' ? 'greige' : 'base';
      else if (s.role === 'part') out[s.key] = (parts.length <= 2 && twoParts.shift()) || cycle.shift() || 'greige';
      else if (spec.kind === 'rating') out[s.key] = 'greige';
      else if (plain.length === 1 && !byRole(spec, 'current')) out[s.key] = 'accent';
      else out[s.key] = cycle.shift() || 'greige';
      const at = cycle.indexOf(out[s.key]);     // цвет занят — дальше по кругу не повторяется
      if (at >= 0) cycle.splice(at, 1);
    }
    return out;
  }

  function initialState(spec) {
    const show = {};
    for (const s of spec.series) show[s.key] = true;
    return { group: 'all', order: 'report', values: 'abs', show, zoom: { start: 0, end: spec.categories.length - 1 } };
  }

  function ratingRows(spec, st) {
    const data = spec.series[0].data;
    let rows = spec.categories.map((c, i) => ({ i, c, v: data[i] }));
    const g = spec.groups.find(x => x.key === st.group);
    if (g) rows = rows.filter(r => r.c.tag && g.tags.includes(r.c.tag));
    return rows;
  }
  function groupTotal(spec, g) {
    const data = spec.series[0].data;
    return sum(spec.categories.map((c, i) => (!g || (c.tag && g.tags.includes(c.tag)) ? data[i] : null)));
  }
  function ungrouped(spec) {
    const tagged = new Set(spec.groups.flatMap(g => g.tags));
    return spec.categories.map((c, i) => ({ c, v: spec.series[0].data[i] })).filter(r => !r.c.tag || !tagged.has(r.c.tag));
  }

  function periodRows(spec, st) {
    const cur = byRole(spec, 'current'), base = byRole(spec, 'base');
    let rows = spec.categories.map((c, i) => {
      const a = cur.data[i], b = base.data[i];
      return { i, c, cur: a, base: b, diff: a != null && b != null ? a - b : null, pct: pct(a, b) };
    });
    if (st.order === 'delta') {
      const key = st.values === 'pct' ? 'pct' : 'diff';
      rows = rows.slice().sort((x, y) => cmpDesc(x[key], y[key]) || x.i - y.i);
    }
    return rows;
  }

  const visibleParts = (spec, st) => spec.series.filter(s => st.show[s.key]);
  function rowTotal(spec, st, i) { return sum(visibleParts(spec, st).map(s => s.data[i])); }
  function baseIndex(spec) { return spec.base_category == null ? -1 : spec.base_category; }

  function windowTotals(spec, st) {    // итоги серий в окне зума (ряд по дням)
    const out = {};
    for (const s of spec.series) out[s.key] = sum(s.data.slice(st.zoom.start, st.zoom.end + 1));
    return out;
  }
  function daysCount(s, st) {
    let n = 0;
    for (let i = st.zoom.start; i <= st.zoom.end; i++) if (s.data[i] != null) n++;
    return n;
  }

  /* ---------------- общие куски опции ECharts ---------------- */

  function tipBox(title, lines, foot) {
    const doc = root.document;
    const box = doc.createElement('div');
    box.className = 'tip';
    const t = doc.createElement('div');
    t.className = 'tip-t';
    t.textContent = title;
    box.appendChild(t);
    for (const l of lines) {
      const row = doc.createElement('div');
      row.className = 'tip-r';
      const key = doc.createElement('span');
      key.className = 'tip-k';
      key.style.background = l.color;
      const v = doc.createElement('b');
      v.className = 'tip-v';
      v.textContent = l.value;
      const lab = doc.createElement('span');
      lab.className = 'tip-l';
      lab.textContent = l.label || '';
      row.append(key, v, lab);
      box.appendChild(row);
    }
    for (const f of [].concat(foot || []).filter(Boolean)) {
      const div = doc.createElement('div');
      div.className = 'tip-f';
      if (typeof f === 'string') div.textContent = f;
      else {
        div.append(f.text);
        if (f.delta) {
          const span = doc.createElement('span');
          span.className = f.up ? 'up' : 'down';
          span.textContent = f.delta;
          div.append(' ', span);
        }
      }
      box.appendChild(div);
    }
    return box;
  }

  function baseOpt(ctx) {
    const anim = ctx.mode !== 'png' && !ctx.reducedMotion;
    return {
      animation: anim,
      animationDuration: 650,
      animationDurationUpdate: 450,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicInOut',
      textStyle: { fontFamily: FONT, color: ctx.P.ink },
    };
  }
  // Описание для экранного диктора: непустые части через точку («Заголовок. Период. Вывод.»)
  const aria = (...parts) => ({ enabled: true, label: { description: parts.filter(Boolean).join('. ') + '.' } });
  function tipCfg(ctx, extra) {
    const P = ctx.P;
    if (ctx.mode === 'png') return { show: false };
    return Object.assign({
      trigger: 'axis',
      confine: true,
      triggerOn: 'mousemove|click',
      transitionDuration: 0.1,
      backgroundColor: P.tip,
      borderColor: P.tipLine,
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { fontFamily: FONT, fontSize: 12, color: P.ink },
      extraCssText: 'border-radius:12px;box-shadow:0 10px 28px ' + P.tipShadow + ';',
      axisPointer: { type: 'shadow', z: 0, shadowStyle: { color: P.hover, opacity: 1 } },
    }, extra);
  }
  const axisText = (P, extra) => Object.assign({ fontFamily: FONT, fontSize: 11, color: P.ink2 }, extra);
  const fits = (px, text) => px >= text.length * CHAR_PX + 12;
  const textPx = text => String(text).length * CHAR_PX;
  function stackRadius(values, k, r) {    // скругление только у крайних непустых частей строки
    const nz = values.filter(x => x.v > 0).map(x => x.k);
    if (!nz.includes(k)) return 0;
    const first = nz[0] === k, last = nz[nz.length - 1] === k;
    return [first ? r : 0, last ? r : 0, last ? r : 0, first ? r : 0];
  }
  // Невидимая полоса во всю ширину, которая несёт только подпись над строкой
  // (имя слева, итог справа) — приём прототипа для рейтинга и стека.
  function rowLabel(id, rows, max, barWidth, side, text, P, extraLabel) {
    return {
      id, type: 'bar', barWidth, barGap: '-100%', silent: true, animation: false,
      emphasis: { disabled: true },
      itemStyle: { color: 'rgba(0,0,0,0)' },
      data: rows.map(r => ({ value: max, label: extraLabel ? extraLabel(r) : {} })),
      label: {
        show: true,
        position: side === 'left' ? [0, -7] : ['100%', -7],
        align: side,
        verticalAlign: 'bottom',
        fontFamily: FONT,
        fontSize: 12,
        fontWeight: side === 'right' ? 700 : 400,
        color: P.ink,
        overflow: 'truncate',
        ellipsis: '…',
        formatter: p => text(rows[p.dataIndex]),
      },
    };
  }
  const baseFoot = (spec, i, value, baseValue) => {
    const b = baseIndex(spec);
    if (b < 0) return null;
    if (i === b) return 'Точка отсчёта';
    if (value == null || baseValue == null) return null;
    const p = pct(value, baseValue);
    return { text: 'К ' + spec.categories[b].label, delta: exactSigned(spec, value - baseValue) +
      (p != null ? ' (' + signed(p, 1) + '%)' : ''), up: value - baseValue >= 0 };
  };

  /* ---------------- виды графиков ---------------- */

  const KINDS = {};

  // 1. Рейтинг полосами: строка = категория, полоса на дорожке, имя слева, значение справа.
  KINDS.rating = {
    height: (spec, st) => ratingRows(spec, st).length * ROW_PX.rating + HEAD_PX.rating,
    option(ctx) {
      const { spec, st, P, w } = ctx;
      const s = spec.series[0];
      const rows = ratingRows(spec, st);
      const max = Math.max(1e-9, ...rows.map(r => r.v));
      const total = sum(s.data);
      const grouped = spec.groups.length > 0;
      const loose = r => grouped && !r.c.tag;
      const color = r => (loose(r) ? P.other : ctx.color(s.key));
      const name = r => (r.c.tag ? r.c.label + ' · ' + r.c.tag : r.c.label);
      const value = r => short(spec, r.v);
      const top = rows.slice().sort((a, b) => b.v - a.v)[0];
      const share = v => {
        if (!spec.additive || !total) return '';
        const p = Math.round(v / total * 100);
        const of = (spec.unit_forms || []).length === 3 ? 'всех ' + spec.unit_forms[2] : 'от итога';
        return (p < 1 && v > 0 ? 'меньше 1% ' : p + '% ') + of;
      };
      const b = baseIndex(spec);
      return Object.assign(baseOpt(ctx), {
        aria: aria(spec.title, spec.subtitle, top ? 'Больше всего — ' + name(top) + ': ' + exact(spec, top.v) : ''),
        grid: { left: 0, right: 0, top: 22, bottom: 4 },
        xAxis: { type: 'value', max, show: false },
        yAxis: { type: 'category', inverse: true, show: false, data: rows.map((r, k) => String(k)) },
        tooltip: tipCfg(ctx, {
          formatter: ps => {
            const r = rows[ps[0].dataIndex];
            return tipBox(name(r), [{ color: color(r), value: exact(spec, r.v), label: share(r.v) }],
              [baseFoot(spec, r.i, r.v, b >= 0 ? s.data[b] : null), r.c.note]);
          },
        }),
        series: [
          {
            id: 'r-track', type: 'bar', barWidth: 8, barGap: '-100%', silent: true, animation: false,
            emphasis: { disabled: true },
            itemStyle: { color: P.track, borderRadius: 4 },
            data: rows.map(r => ({
              value: max,
              label: { color: loose(r) ? P.ink2 : P.ink, width: Math.max(40, w - textPx(value(r)) - 18) },
            })),
            label: {
              show: true, position: [0, -7], align: 'left', verticalAlign: 'bottom', overflow: 'truncate',
              ellipsis: '…', fontFamily: FONT, fontSize: 12, formatter: p => name(rows[p.dataIndex]),
            },
          },
          rowLabel('r-val', rows, max, 8, 'right', value, P),
          {
            id: 'r-bar', type: 'bar', barWidth: 8, barGap: '-100%',
            itemStyle: { borderRadius: 4 },
            data: rows.map(r => ({ value: r.v, itemStyle: { color: color(r) } })),
          },
        ],
      });
    },
  };

  // 2. Два периода столбиками: база (серая) слева, текущий (акцент) справа; режим «%».
  KINDS.periods = {
    height: () => PERIODS_PX,
    option(ctx) {
      const { spec, st, P, w } = ctx;
      const curS = byRole(spec, 'current'), baseS = byRole(spec, 'base');
      const rows = periodRows(spec, st);
      const n = rows.length;
      const slot = Math.max(10, (w - 44) / n);
      const pctMode = st.values === 'pct';
      const showCur = pctMode || st.show[curS.key], showBase = pctMode || st.show[baseS.key];
      const swatch = c => ({ width: 10, height: 10, borderRadius: 3, backgroundColor: c });
      const txt = (color, extra) => Object.assign({ fontFamily: FONT, fontSize: 11, color, lineHeight: 15 }, extra);
      const rich = { n: txt(P.ink), up: txt(P.up, { fontWeight: 700 }), dn: txt(P.down, { fontWeight: 700 }) };
      for (const key of Object.keys(COLOR_TOKEN)) rich['sw_' + key] = swatch(ctx.colorOf(key));
      const pctUnder = !pctMode && showCur && showBase && n <= PCT_UNDER_LABEL_MAX;
      const xAxis = {
        type: 'category', data: rows.map((r, k) => String(k)),
        axisTick: { show: false },
        axisLine: { onZero: true, lineStyle: { color: P.grid } },
        axisLabel: {
          interval: 0, margin: 10, rich,
          formatter: (v, k) => {
            const r = rows[k];
            const lines = richSafe(r.c.short || r.c.label).split('\n');
            const head = lines.map((line, j) => (j === 0 && r.c.color ? '{sw_' + r.c.color + '| }{n| ' + line + '}' : '{n|' + line + '}'));
            if (pctUnder && r.pct != null) head.push('{' + (roundTo(r.pct, 1) >= 0 ? 'up' : 'dn') + '|' + pctText(r.pct, true) + '}');
            return head.join('\n');
          },
        },
      };
      const tooltip = tipCfg(ctx, {
        formatter: ps => {
          const r = rows[ps[0].dataIndex];
          const lines = [];
          if (showCur) lines.push({ color: ctx.color(curS.key), value: exact(spec, r.cur), label: curS.name });
          if (showBase) lines.push({ color: ctx.color(baseS.key), value: exact(spec, r.base), label: baseS.name });
          let foot = null;
          if (r.diff != null && showCur && showBase) {
            foot = { text: 'Разница', delta: exactSigned(spec, r.diff) + (r.pct != null ? ' (' + signed(r.pct, 1) + '%)' : ''), up: r.diff >= 0 };
          }
          const zeroBase = r.base === 0 && r.cur != null ? 'В базе 0 — изменение в % не считается' : null;
          return tipBox(r.c.label, lines, [foot, zeroBase, r.c.note]);
        },
      });
      // containLabel меряет многострочную подпись rich-текста как одну строку:
      // остальные строки (вторая строка имени, процент) добавляем отступом снизу.
      const lines = Math.max(...rows.map(r => (r.c.short || r.c.label).split('\n').length)) +
        (pctUnder && rows.some(r => r.pct != null) ? 1 : 0);
      const common = Object.assign(baseOpt(ctx), {
        aria: aria(spec.title, spec.subtitle, curS.name + ' к ' + baseS.name),
        grid: { left: 0, right: 4, top: 24, bottom: (lines - 1) * 15 + 2, containLabel: true },
        xAxis, tooltip,
      });
      if (!pctMode) {
        const bw = Math.max(6, Math.min(22, Math.round(slot * 0.3)));
        // Подпись над столбиком шире ячейки категории — подписи убираем у всех: наложенные
        // числа не читаются, а точные значения есть в подсказке и таблице.
        const labelled = rows.every(r => textPx(short(spec, r.cur)) + 4 <= slot && textPx(short(spec, r.base)) + 4 <= slot);
        const label = { show: labelled, position: 'top', distance: 5, fontFamily: FONT, fontSize: 12, fontWeight: 600, color: P.ink,
          formatter: p => short(spec, p.value) };
        const series = [];
        if (st.show[baseS.key]) series.push({
          id: 'p-base', type: 'bar', barWidth: bw, barGap: '15%',
          itemStyle: { color: ctx.color(baseS.key), borderRadius: [4, 4, 0, 0] },
          data: rows.map(r => (r.base == null ? '-' : r.base)),
          label: st.show[curS.key] ? { show: false } : label,
        });
        if (st.show[curS.key]) series.push({
          id: 'p-cur', type: 'bar', barWidth: bw, barGap: '15%',
          itemStyle: { color: ctx.color(curS.key), borderRadius: [4, 4, 0, 0] },
          data: rows.map(r => (r.cur == null ? '-' : r.cur)),
          label,
        });
        return Object.assign(common, {
          yAxis: { type: 'value', splitNumber: 3, axisLabel: axisText(P, { formatter: v => short(spec, v) }),
            splitLine: { lineStyle: { color: P.grid } } },
          series,
        });
      }
      // Полная подпись «▼ −63,6%» шире столбика — тогда у всех короткая «−64%» (до целого,
      // меньше 10% — один знак); точный процент — в подсказке и таблице.
      const full = rows.every(r => r.pct == null || textPx(pctText(r.pct, true)) + 4 <= slot);
      const pctLabel = p => {
        const r = roundTo(p, 1);
        if (r === 0) return '0%';
        return full ? pctText(p, true) : signed(p, Math.abs(p) >= 10 ? 0 : 1) + '%';
      };
      const tone = p => (roundTo(p, 1) > 0 ? P.up : roundTo(p, 1) < 0 ? P.down : P.ink2);
      return Object.assign(common, {
        yAxis: {
          // запас 16% сверху и снизу — под подписи над и под столбиками; 4 деления, а не 3:
          // иначе шаг 100% раздувает ось до ±200% при данных около ±100%
          type: 'value', splitNumber: 4, boundaryGap: ['16%', '16%'],
          axisLabel: axisText(P, { formatter: v => (v === 0 ? '0' : signed(v, 0) + '%') }),
          splitLine: { lineStyle: { color: P.grid } },
        },
        series: [{
          id: 'p-pct', type: 'bar', barWidth: Math.max(8, Math.min(24, Math.round(slot * 0.4))),
          data: rows.map(r => (r.pct == null ? {
            // нет базы: столбика нет, над нулём — прочерк (причина — в подсказке)
            value: 0, itemStyle: { color: 'rgba(0,0,0,0)' },
            label: { position: 'top', color: P.muted, formatter: '—' },
          } : {
            value: r.pct,
            itemStyle: { color: tone(r.pct), borderRadius: r.pct >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] },
            label: { position: r.pct >= 0 ? 'top' : 'bottom', color: tone(r.pct) },
          })),
          label: { show: true, distance: 5, fontFamily: FONT, fontSize: 12, fontWeight: 700, formatter: p => pctLabel(p.value) },
          markLine: {
            silent: true, symbol: 'none', animation: false, label: { show: false },
            lineStyle: { color: P.ink2, width: 1, type: 'solid' }, data: [{ yAxis: 0 }],
          },
        }],
      });
    },
  };

  // 3. Стек по частям: строка = категория, части подряд, итог строки справа.
  KINDS.stack = {
    height: spec => spec.categories.length * ROW_PX.stack + HEAD_PX.stack,
    option(ctx) {
      const { spec, st, P, w } = ctx;
      const parts = visibleParts(spec, st);
      const rows = spec.categories.map((c, i) => ({ i, c, total: rowTotal(spec, st, i) }));
      const max = Math.max(1e-9, ...rows.map(r => r.total || 0));
      const totalText = r => short(spec, r.total);
      const b = baseIndex(spec);
      return Object.assign(baseOpt(ctx), {
        aria: aria(spec.title, spec.subtitle, rows.map(r => r.c.label + ': ' + exact(spec, r.total)).join('; ')),
        grid: { left: 0, right: 0, top: 24, bottom: 4 },
        xAxis: { type: 'value', max, show: false },
        yAxis: { type: 'category', inverse: true, show: false, data: rows.map((r, k) => String(k)) },
        tooltip: tipCfg(ctx, {
          formatter: ps => {
            const r = rows[ps[0].dataIndex];
            return tipBox(r.c.label + ' · ' + exact(spec, r.total),
              parts.map(s => ({ color: ctx.color(s.key), value: exact(spec, s.data[r.i]), label: s.name })),
              [baseFoot(spec, r.i, r.total, b >= 0 ? rows[b].total : null), r.c.note]);
          },
        }),
        series: [
          rowLabel('s-name', rows, max, 22, 'left', r => r.c.label, P,
            r => ({ width: Math.max(40, w - textPx(totalText(r)) - 18) })),
          rowLabel('s-total', rows, max, 22, 'right', totalText, P),
          ...parts.map(s => ({
            id: 's-' + s.key, type: 'bar', stack: 'parts', barWidth: 22, barGap: '-100%',
            data: rows.map(r => {
              const v = s.data[r.i];
              if (!(v > 0)) return '-';
              const values = parts.map(x => ({ k: x.key, v: x.data[r.i] }));
              return {
                value: v,
                itemStyle: { color: ctx.color(s.key), borderRadius: stackRadius(values, s.key, 6), borderColor: P.card, borderWidth: 1 },
                label: { show: fits(v / max * w, short(spec, v)) },
              };
            }),
            label: { position: 'inside', fontFamily: FONT, fontSize: 12, fontWeight: 600, color: ctx.ink(s.key),
              formatter: p => short(spec, p.value) },
          })),
        ],
      });
    },
  };

  // 4. Ряд по дням: столбики (одна серия, стек частей) или линии (несколько серий); зум.
  KINDS.days = {
    height: () => DAYS_PX,
    option(ctx) {
      const { spec, st, P } = ctx;
      const labels = spec.categories.map(c => c.label);
      const n = labels.length;
      const series = spec.series.filter(s => st.show[s.key]);
      const parts = isParts(spec);
      const lines = !parts && spec.series.length > 1;
      const zoom = ctx.mode !== 'png' && n >= ZOOM_MIN_POINTS;
      const cur = byRole(spec, 'current'), base = byRole(spec, 'base');
      const out = series.map(s => {
        const c = ctx.color(s.key);
        if (lines) {
          return {
            id: 'd-' + s.key, type: 'line', data: s.data.map(v => (v == null ? '-' : v)),
            showSymbol: n <= 31, symbol: 'circle', symbolSize: 5, connectNulls: false,
            lineStyle: { width: 2, color: c, type: s.role === 'base' ? 'dashed' : 'solid' },
            itemStyle: { color: c },
          };
        }
        return {
          id: 'd-' + s.key, type: 'bar', stack: parts ? 'parts' : undefined, barMaxWidth: 16,
          data: s.data.map(v => (v == null ? '-' : v)),
          itemStyle: { color: c, borderRadius: parts ? 0 : [3, 3, 0, 0] },
        };
      });
      const opt = Object.assign(baseOpt(ctx), {
        aria: aria(spec.title, spec.subtitle, dayRange(labels[0], labels[n - 1])),
        grid: { left: 0, right: 8, top: 16, bottom: zoom ? 44 : 0, containLabel: true },
        xAxis: {
          type: 'category', data: labels, boundaryGap: !lines,
          axisTick: { show: false }, axisLine: { lineStyle: { color: P.grid } },
          axisLabel: axisText(P, { hideOverlap: true, formatter: v => dayShort(v) }),
        },
        yAxis: { type: 'value', splitNumber: 3, axisLabel: axisText(P, { formatter: v => short(spec, v) }),
          splitLine: { lineStyle: { color: P.grid } } },
        tooltip: tipCfg(ctx, {
          axisPointer: lines ? { type: 'line', lineStyle: { color: P.muted, width: 1 } }
            : { type: 'shadow', z: 0, shadowStyle: { color: P.hover, opacity: 1 } },
          formatter: ps => {
            const i = ps[0].dataIndex;
            const rowsT = series.map(s => ({ color: ctx.color(s.key), value: exact(spec, s.data[i]), label: s.name }));
            const foot = [];
            if (parts && series.length > 1) foot.push('Всего: ' + exact(spec, sum(series.map(s => s.data[i]))));
            if (cur && base && st.show[cur.key] && st.show[base.key]) {
              const a = cur.data[i], bv = base.data[i];
              if (a != null && bv != null) {
                const p = pct(a, bv);
                foot.push({ text: 'К ' + base.name, delta: exactSigned(spec, a - bv) + (p != null ? ' (' + signed(p, 1) + '%)' : ''), up: a - bv >= 0 });
              }
            }
            const note = spec.categories[i].note;
            if (note) foot.push(note);
            return tipBox(dayLong(labels[i]), rowsT, foot);
          },
        }),
        series: out,
      });
      if (zoom) {
        opt.dataZoom = [
          { type: 'inside', startValue: st.zoom.start, endValue: st.zoom.end, minValueSpan: 6,
            zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false, preventDefaultMouseMove: false },
          { type: 'slider', startValue: st.zoom.start, endValue: st.zoom.end, minValueSpan: 6, height: 18, bottom: 6,
            left: 6, right: 10, brushSelect: false, showDetail: false, borderColor: P.grid, backgroundColor: 'rgba(0,0,0,0)',
            fillerColor: P.hover, textStyle: { color: P.muted, fontFamily: FONT },
            dataBackground: { lineStyle: { color: P.muted, opacity: 0.5 }, areaStyle: { color: P.muted, opacity: 0.12 } },
            selectedDataBackground: { lineStyle: { color: ctx.colorOf('accent') }, areaStyle: { color: ctx.colorOf('accent'), opacity: 0.18 } },
            handleStyle: { color: P.card, borderColor: P.muted }, moveHandleStyle: { color: P.muted, opacity: 0.35 },
            emphasis: { handleStyle: { borderColor: P.ink2 }, moveHandleStyle: { color: P.ink2, opacity: 0.5 } } },
        ];
      }
      return opt;
    },
  };

  function buildOption(spec, st, palette, width, mode, extra) {
    const keys = colorKeys(spec);
    const tokenOf = key => palette[camel(COLOR_TOKEN[key] || 'greige')];
    const ctx = Object.assign({
      spec, st, P: palette, w: Math.max(200, width || 380), mode: mode || 'app',
      colorOf: tokenOf,
      color: seriesKey => tokenOf(keys[seriesKey]),
      ink: seriesKey => palette[camel((COLOR_TOKEN[keys[seriesKey]] || 'greige') + '-ink')] || palette.ink,
    }, extra || {});
    return KINDS[spec.kind].option(ctx);
  }

  /* ---------------- таблица и «Как считается» ---------------- */

  function table(spec) {
    const ex = v => (v == null ? '—' : num(v, spec.decimals));
    const caption = 'Точные значения, ' + spec.unit;
    if (spec.kind === 'rating') {
      const s = spec.series[0], total = sum(s.data);
      const tags = spec.categories.some(c => c.tag);
      const head = ['Позиция'].concat(tags ? ['Метка'] : [], [s.name], spec.additive ? ['Доля'] : []);
      const rows = spec.categories.map((c, i) => [c.label].concat(tags ? [c.tag || '—'] : [], [ex(s.data[i])],
        spec.additive ? [total ? nfAbs(s.data[i] / total * 100, 1) + '%' : '—'] : []));
      const foot = spec.additive ? ['Всего'].concat(tags ? [''] : [], [ex(total)], ['100%']) : null;
      return { caption, head, rows, foot };
    }
    if (spec.kind === 'periods') {
      const cur = byRole(spec, 'current'), base = byRole(spec, 'base');
      const head = ['Категория', base.name, cur.name, 'Разница', 'Изм., %'];
      const rows = periodRows(spec, { order: 'report' }).map(r => [r.c.label, ex(r.base), ex(r.cur),
        r.diff == null ? '—' : signed(r.diff, spec.decimals), pctText(r.pct)]);
      let foot = null;
      if (spec.additive) {
        const a = sum(cur.data), b = sum(base.data);
        foot = ['Всего', ex(b), ex(a), a != null && b != null ? signed(a - b, spec.decimals) : '—', pctText(pct(a, b))];
      }
      return { caption, head, rows, foot };
    }
    if (spec.kind === 'stack') {
      const head = ['Категория'].concat(spec.series.map(s => s.name), ['Всего']);
      const rows = spec.categories.map((c, i) => [c.label].concat(spec.series.map(s => ex(s.data[i])),
        [ex(sum(spec.series.map(s => s.data[i])))]));
      const foot = spec.additive ? ['Всего'].concat(spec.series.map(s => ex(sum(s.data))),
        [ex(sum(spec.series.map(s => sum(s.data))))]) : null;
      return { caption, head, rows, foot };
    }
    const head = ['Дата'].concat(spec.series.map(s => s.name));
    const rows = spec.categories.map((c, i) => [dayLong(c.label)].concat(spec.series.map(s => ex(s.data[i]))));
    const foot = spec.additive ? ['Всего'].concat(spec.series.map(s => ex(sum(s.data)))) : null;
    return { caption, head, rows, foot };
  }

  function howText(spec) {
    const out = [];
    if (spec.kind === 'rating') {
      out.push('Полоса — значение позиции; самая длинная — максимум среди показанных.');
      if (spec.additive) out.push('Доля = значение / сумма всех позиций × 100, до целого процента.');
      if (spec.groups.length) out.push('Кнопки групп показывают позиции с метками группы; число на кнопке — сумма группы. Позиции без метки есть только во «Всё».');
    } else if (spec.kind === 'periods') {
      out.push('Изменение, % = (текущий − база) / база × 100, один знак после запятой. Если в базе 0 или нет данных, процент не считается.');
      out.push('«По изменению» — по убыванию разницы (в режиме процентов — по убыванию процента); «Как в отчёте» — порядок из отчёта.');
      if (spec.additive) out.push('Итог периода — сумма категорий; изменение итога считается так же.');
    } else if (spec.kind === 'stack') {
      out.push('Итог строки — сумма показанных частей; выключенная в легенде часть из итога уходит.');
      if (spec.base_category != null) out.push('Разница в подсказке — итог строки минус итог строки «' + spec.categories[spec.base_category].label + '».');
    } else {
      out.push('Итоги под графиком — за дни в окне зума: сумма значений; в среднем — сумма / число дней с данными.');
      if (byRole(spec, 'current') && byRole(spec, 'base')) out.push('Изменение, % = (' + byRole(spec, 'current').name + ' − ' + byRole(spec, 'base').name + ') / ' + byRole(spec, 'base').name + ' × 100.');
    }
    if (!spec.additive) out.push('Значения не складываются (средние, цены или доли), поэтому общих итогов нет.');
    if (spec.scale > 1) out.push('Подписи на графике — в ' + scaledUnit(spec) + ': значение / ' + nfAbs(spec.scale, 0) + ', до целого (меньше 10 — один знак). В подсказке и таблице — точные значения.');
    out.push('Точные значения — с ' + spec.decimals + ' ' + plural(spec.decimals, ['знаком', 'знаками', 'знаками']) + ' после запятой.');
    return out;
  }

  /* ---------------- DOM ---------------- */

  const camel = s => s.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase());
  function palette() {
    const cs = root.getComputedStyle(root.document.documentElement);
    const P = {};
    for (const t of TOKENS) P[camel(t)] = cs.getPropertyValue('--' + t).trim();
    return P;
  }
  function h(tag, cls, text) {
    const e = root.document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function fontsReady(timeoutMs) {
    const doc = root.document;
    const load = doc.fonts && doc.fonts.load
      ? Promise.all(['400', '500', '600', '700'].map(wt => doc.fonts.load(wt + ' 12px "IBM Plex Mono"', 'Литры 0123')))
      : Promise.resolve();
    return Promise.race([load, new Promise(r => setTimeout(r, timeoutMs || 2500))]).catch(() => {});
  }

  function mount(container, spec, opts) {
    opts = opts || {};
    const mode = opts.mode || 'app';
    const interactive = mode !== 'png';
    const st = initialState(spec);
    const keys = colorKeys(spec);
    const reducedMotion = !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const select = () => { if (opts.onSelect) opts.onSelect(); };
    const toast = msg => { if (opts.toast) opts.toast(msg); };

    const card = h('section', 'card');
    if (opts.id) card.id = opts.id;
    const head = h('div');
    const h2 = h('h2');
    h2.append(h('span', null, spec.title));
    if (spec.subtitle) h2.append(h('span', 'card-sub', spec.subtitle));
    head.append(h2);
    if (spec.note) head.append(h('p', 'note', spec.note));
    const controls = h('div', 'controls');
    const hint = h('p', 'hint');
    hint.hidden = true;
    const sumLine = h('p', 'sum');
    sumLine.hidden = true;
    const plot = h('div', 'plot');
    const unit = h('div', 'unit', scaledUnit(spec));
    const chartEl = h('div', 'chart');
    plot.append(unit, chartEl);
    card.append(head, controls, hint, plot, sumLine);

    let tableBox = null;
    if (interactive) {
      const how = h('details', 'fold how-box');
      how.append(h('summary', null, 'Как считается'));
      const howBody = h('div', 'how');
      for (const p of howText(spec)) howBody.append(h('p', null, p));
      how.append(howBody);
      tableBox = h('details', 'fold tbl');
      tableBox.append(h('summary', null, 'Таблица'));
      const wrap = h('div', 'tbl-wrap');
      wrap.append(buildTable(table(spec)));
      tableBox.append(wrap);
      card.append(how, tableBox);
    }
    const foot = h('footer', 'foot');
    const src = [spec.source, spec.data_at ? 'данные на ' + dataAt(spec.data_at) : ''].filter(Boolean).join(' · ');
    foot.append(h('span', null, src), h('span', 'logo', 'КУЛЬТУРА'));
    card.append(foot);
    container.append(card);

    // ---- переключатели ----
    const syncs = [];
    function segmented(label, options, get, set) {
      const box = h('div', 'seg');
      box.setAttribute('role', 'group');
      box.setAttribute('aria-label', label);
      const buttons = options.map(o => {
        const b = h('button');
        b.type = 'button';
        b.append(root.document.createTextNode(o.label));
        if (o.note) b.append(' ', h('small', null, o.note));
        b.addEventListener('click', () => {
          if (get() === o.value) return;
          set(o.value);
          sync();
          select();
          render();
        });
        box.append(b);
        return b;
      });
      function sync() { buttons.forEach((b, i) => b.setAttribute('aria-pressed', String(get() === options[i].value))); }
      sync();
      syncs.push(sync);
      controls.append(box);
      return box;
    }
    const legendItems = [];
    function legend(label, series, noteFor) {
      const box = h('div', 'legend');
      box.setAttribute('aria-label', label);
      for (const s of series) {
        const b = interactive ? h('button', 'lg') : h('span', 'lg');
        if (interactive) b.type = 'button';
        if (spec.kind === 'days' && spec.series.length > 1 && !isParts(spec)) {
          b.classList.add('lg-line');                       // линии — образец линией, база — пунктиром
          if (s.role === 'base') b.classList.add('lg-dash');
        }
        const sw = h('span', 'lg-sw');
        sw.style.setProperty('--c', 'var(--' + COLOR_TOKEN[keys[s.key]] + ')');
        const note = h('small');
        b.append(sw, root.document.createTextNode(s.name), note);
        const sync = () => {
          if (interactive) b.setAttribute('aria-pressed', String(!!st.show[s.key]));
          const t = noteFor ? noteFor(s) : '';
          note.textContent = t ? ' ' + t : '';
        };
        if (interactive) {
          b.addEventListener('click', () => {
            const on = series.filter(x => st.show[x.key]);
            if (st.show[s.key] && on.length === 1) { toast('Одна серия должна остаться на графике'); return; }
            st.show[s.key] = !st.show[s.key];
            select();
            render();
          });
        }
        legendItems.push(sync);
        box.append(b);
      }
      controls.append(box);
      return box;
    }

    let legendBox = null;
    const totalNote = s => (spec.additive ? shortUnit(spec, sum(s.data)) : '');
    if (spec.kind === 'rating' && spec.groups.length && interactive) {
      const all = spec.additive ? short(spec, groupTotal(spec, null)) : '';
      segmented('Что показать', [{ value: 'all', label: 'Всё', note: all }].concat(spec.groups.map(g => ({
        value: g.key, label: g.label, note: spec.additive ? short(spec, groupTotal(spec, g)) : '',
      }))), () => st.group, v => { st.group = v; });
    }
    if (spec.kind === 'periods') {
      if (interactive) {
        segmented('Порядок', [{ value: 'report', label: 'Как в отчёте' }, { value: 'delta', label: 'По изменению' }],
          () => st.order, v => { st.order = v; });
        segmented('Единицы', [{ value: 'abs', label: valueLabel(spec) }, { value: 'pct', label: 'Проценты' }],
          () => st.values, v => { st.values = v; });
      }
      legendBox = legend('Периоды на графике', [byRole(spec, 'current'), byRole(spec, 'base')], totalNote);
    }
    if (spec.kind === 'stack' && spec.series.length > 1) legendBox = legend('Части', spec.series, totalNote);
    if (spec.kind === 'days') {
      const n = spec.categories.length;
      if (interactive && n >= PRESET_MIN_POINTS) {
        const presets = [{ value: 'all', label: 'Весь период' }].concat(PRESET_DAYS.filter(d => d < n).map(d => ({ value: String(d), label: d + ' дн' })));
        segmented('Период', presets, () => zoomPreset(), v => {
          st.zoom = v === 'all' ? { start: 0, end: n - 1 } : { start: n - +v, end: n - 1 };
        });
      }
      if (spec.series.length > 1) {
        legendBox = legend('Серии', spec.series, s => {
          if (!spec.additive) return '';
          return shortUnit(spec, windowTotals(spec, st)[s.key]);
        });
      }
    }
    function zoomPreset() {
      const n = spec.categories.length;
      if (st.zoom.start === 0 && st.zoom.end === n - 1) return 'all';
      for (const d of PRESET_DAYS) if (st.zoom.end === n - 1 && st.zoom.start === n - d) return String(d);
      return '';
    }

    // ---- подписи под переключателями ----
    function updateText() {
      for (const sync of syncs) sync();
      for (const sync of legendItems) sync();
      if (legendBox) legendBox.hidden = spec.kind === 'periods' && st.values === 'pct';
      unit.textContent = spec.kind === 'periods' && st.values === 'pct'
        ? '% к ' + byRole(spec, 'base').name : scaledUnit(spec);
      // рейтинг: что не попало в группу
      hint.hidden = true;
      if (spec.kind === 'rating' && st.group !== 'all') {
        const left = ungrouped(spec);
        if (left.length) {
          hint.textContent = 'Без группы: ' + left.map(r => r.c.label).join(', ') + ' — ' + exact(spec, sum(left.map(r => r.v))) + '; в этом виде их нет.';
          hint.hidden = false;
        }
      }
      sumLine.hidden = true;
      const text = summary();
      if (text) { sumLine.textContent = text; sumLine.hidden = false; }
    }
    function summary() {
      if (!spec.additive) {
        if (spec.kind === 'days' && spec.categories.length >= ZOOM_MIN_POINTS && interactive) {
          return dayRange(spec.categories[st.zoom.start].label, spec.categories[st.zoom.end].label);
        }
        return '';
      }
      if (spec.kind === 'periods') {
        const cur = byRole(spec, 'current'), base = byRole(spec, 'base');
        const a = sum(cur.data), b = sum(base.data);
        if (st.values === 'abs' && !(st.show[cur.key] && st.show[base.key])) return '';
        return 'Итого: ' + shortUnit(spec, a) + ' к ' + shortUnit(spec, b) + (pct(a, b) != null ? ', ' + pctText(pct(a, b)) : '');
      }
      if (spec.kind === 'stack') {
        const total = sum(spec.categories.map((c, i) => rowTotal(spec, st, i)));
        return 'Итого по строкам: ' + exact(spec, total);
      }
      if (spec.kind === 'days') {
        const range = dayRange(spec.categories[st.zoom.start].label, spec.categories[st.zoom.end].label);
        const totals = windowTotals(spec, st);
        const cur = byRole(spec, 'current'), base = byRole(spec, 'base');
        if (cur && base && st.show[cur.key] && st.show[base.key]) {
          const p = pct(totals[cur.key], totals[base.key]);
          return range + ': ' + exact(spec, totals[cur.key]) + ' к ' + exact(spec, totals[base.key]) + (p != null ? ', ' + pctText(p) : '');
        }
        const shown = spec.series.filter(s => st.show[s.key]);
        if (isParts(spec) || shown.length === 1) {
          const total = isParts(spec) ? sum(shown.map(s => totals[s.key])) : totals[shown[0].key];
          const days = Math.max(...shown.map(s => daysCount(s, st)));
          return range + ': ' + exact(spec, total) + (days ? ', в среднем ' + exact(spec, total / days) + ' в день' : '');
        }
        return range;
      }
      return '';
    }

    // ---- ECharts ----
    let inst = null;
    let lastW = 0;
    function render(full) {
      updateText();
      if (!inst) return;
      const hgt = KINDS[spec.kind].height(spec, st) + 'px';
      if (chartEl.style.height !== hgt) { chartEl.style.height = hgt; inst.resize(); }
      const option = buildOption(spec, st, palette(), chartEl.clientWidth, mode, { reducedMotion });
      inst.setOption(option, full ? { notMerge: true } : { replaceMerge: ['series', 'dataZoom'] });
    }

    const echarts = root.echarts;
    if (!echarts) {
      chartEl.classList.add('chart--fail');
      chartEl.textContent = 'График не загрузился. Цифры — в таблице ниже.';
      if (tableBox) tableBox.open = true;
      updateText();
      if (opts.onRendered) opts.onRendered();
      return { retheme() {}, destroy() {} };
    }
    chartEl.style.height = KINDS[spec.kind].height(spec, st) + 'px';
    inst = echarts.init(chartEl, null, { renderer: 'svg' });
    lastW = Math.round(chartEl.clientWidth);
    if (opts.onRendered) inst.on('finished', () => opts.onRendered(inst));
    inst.on('datazoom', () => {
      const dz = (inst.getOption().dataZoom || [])[0];
      if (!dz || dz.startValue == null) return;
      st.zoom = { start: dz.startValue, end: dz.endValue };
      updateText();
    });
    render(true);

    let ro = null;
    if (root.ResizeObserver && interactive) {
      ro = new root.ResizeObserver(entries => {
        for (const e of entries) {
          const w = Math.round(e.contentRect.width);
          if (w === lastW) continue;
          lastW = w;
          inst.resize();
          render(false);
        }
      });
      ro.observe(chartEl);
    }
    const hideTip = e => { if (!chartEl.contains(e.target)) inst.dispatchAction({ type: 'hideTip' }); };
    if (interactive) root.document.addEventListener('pointerdown', hideTip, { passive: true });

    return {
      el: card,
      chart: inst,
      state: st,
      retheme() { render(true); },
      destroy() {
        if (ro) ro.disconnect();
        root.document.removeEventListener('pointerdown', hideTip);
        inst.dispose();
      },
    };
  }

  function buildTable(t) {
    const tbl = h('table');
    tbl.append(h('caption', null, t.caption));
    const thead = h('thead'), tr = h('tr');
    for (const x of t.head) { const th = h('th', null, x); th.scope = 'col'; tr.append(th); }
    thead.append(tr);
    const tbody = h('tbody');
    for (const r of t.rows) {
      const row = h('tr');
      for (const x of r) row.append(h('td', null, x));
      tbody.append(row);
    }
    tbl.append(thead, tbody);
    if (t.foot) {
      const tfoot = h('tfoot'), row = h('tr');
      for (const x of t.foot) row.append(h('td', null, x));
      tfoot.append(row);
      tbl.append(tfoot);
    }
    return tbl;
  }

  const api = {
    mount, buildOption, initialState, fontsReady, table, howText, colorKeys,
    fmt: { num, signed, plural, exact, exactSigned, short, shortUnit, scaledUnit, pctText, dayShort, dayLong, dayRange, dataAt, valueLabel },
    calc: { pct, sum, ratingRows, groupTotal, ungrouped, periodRows, rowTotal, windowTotals },
    KINDS: Object.keys(KINDS),
  };
  root.TgChart = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);

/* Отчёт и записка «Как считается» бота @MCPkulturabot (kultura_bot/charts/reports.py).
 *
 * Один модуль на два места: мини-приложение (app.js — id вида rep_…) и страница сайта
 * /tg/report/<id> (site.js). Данные — reports.view(): тексты уже переведены сервером из
 * Markdown бота в HTML (kultura_bot/engine/formatting.to_html: всё экранировано, разметка
 * только своя — b, i, code, pre, a, blockquote), поэтому их можно вставить как разметку.
 * Графики разделов — TgChart.mount, те же карточки, что у «Открыть интерактивно».
 *
 * window.TgReport:
 *   mount(container, view, opts)  страница: заголовок, источник и время, выжимка, разделы
 *                                 (текст, график, таблица, свёрнутое «Как считается»),
 *                                 общее «Как считается». opts: toast, onSelect,
 *                                 share — кнопка «Ссылка для браузера» (app.js, site.js):
 *                                   {link, expiresAt, create() -> url, revoke(), send(url, title)|null,
 *                                    sendLabel}; sharedUntil — страница открыта по ссылке (/r/<код>):
 *                                   кнопки нет, в шапке — до какого дня ссылка работает
 *
 * Ссылка для браузера (2026-10-28): https://beerkultura.ru/r/<код> — та же страница без входа,
 * для человека без чата с ботом и без входа на сайт. Её делает и закрывает владелец здесь же.
 *
 * Раздел с графиком: заголовок графика не показывается (вывод уже в заголовке раздела, карточка
 * начинается с подзаголовка), а «Как считается» раздела уходит в «Как считается» карточки —
 * одно на раздел. Тексты — с неразрывными пробелами в числах (TgChart.fmt.nb).
 *   cellText(value)               ячейка таблицы: число по-русски (разряды, минус −), null — «—»
 */
(function (root) {
  'use strict';

  const NF = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });

  const nb = text => (root.TgChart && root.TgChart.fmt && root.TgChart.fmt.nb ? root.TgChart.fmt.nb(text) : text);

  function h(tag, cls, text) {
    const e = root.document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = nb(text);
    return e;
  }
  function markup(tag, cls, html) {
    const e = h(tag, cls);
    // HTML от сервера: formatting.to_html, всё экранировано. Перевод строки сразу после цитаты
    // или кода в white-space: pre-wrap дал бы лишнюю пустую строку под блоком — убираем один.
    e.innerHTML = (html || '').replace(/(<\/blockquote>|<\/pre>)\n/g, '$1');
    for (const a of e.querySelectorAll('a[href]')) {
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
    }
    return e;
  }
  function cellText(v) {
    if (v == null) return '—';
    if (typeof v === 'number') return (v < 0 ? '−' : '') + NF.format(Math.abs(v));
    return String(v);
  }
  function dataAt(iso) {
    return root.TgChart && root.TgChart.fmt ? root.TgChart.fmt.dataAt(iso) : (iso || '');
  }

  function table(t) {
    const wrap = h('div', 'rep-tbl');
    const scroll = h('div', 'tbl-wrap');
    const tbl = h('table');
    const thead = h('thead'), tr = h('tr');
    for (const col of t.columns) {
      const th = h('th', col.align === 'right' ? 'num' : null, col.label);
      th.scope = 'col';
      tr.append(th);
    }
    thead.append(tr);
    const tbody = h('tbody');
    for (const row of t.rows) {
      const r = h('tr');
      row.forEach((v, i) => r.append(h('td', t.columns[i].align === 'right' ? 'num' : null, cellText(v))));
      tbody.append(r);
    }
    tbl.append(thead, tbody);
    scroll.append(tbl);
    wrap.append(scroll);
    if (t.note) wrap.append(h('p', 'rep-tbl-note', t.note));
    return wrap;
  }

  function how(html, label) {
    const d = h('details', 'rep-how');
    d.append(h('summary', null, label || 'Как считается'), markup('div', 'rep-text', html));
    return d;
  }

  function day(iso) {
    try {
      return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric',
                                                         timeZone: 'Europe/Moscow' }).replace(' г.', '');
    } catch (e) { return ''; }
  }

  async function copyText(text, input) {
    try {
      await root.navigator.clipboard.writeText(text);
      return true;
    } catch (e) { /* в WebView Telegram буфер бывает закрыт — запасной путь ниже */ }
    try {
      input.focus();
      input.select();
      input.setSelectionRange(0, text.length);
      return root.document.execCommand('copy');
    } catch (e) { return false; }
  }

  // «Ссылка для браузера»: сделать (та же, если есть), скопировать, отправить, закрыть.
  function shareBar(share, title, toast) {
    const box = h('div', 'rep-share');
    const main = h('button', 'rep-share-btn');
    main.type = 'button';
    const panel = h('div', 'rep-share-panel');
    panel.hidden = true;
    const input = h('input', 'rep-share-url');
    input.readOnly = true;
    input.setAttribute('aria-label', 'Ссылка для браузера');
    const actions = h('div', 'rep-share-actions');
    const copyBtn = h('button', null, 'Скопировать');
    const sendBtn = share.send ? h('button', null, share.sendLabel || 'Отправить') : null;
    const closeBtn = h('button', 'rep-share-close', 'Закрыть ссылку');
    [copyBtn, sendBtn, closeBtn].filter(Boolean).forEach(b => { b.type = 'button'; actions.append(b); });
    const until = share.expiresAt ? day(share.expiresAt) : '';
    const note = h('p', 'rep-share-note', 'Откроет любой, у кого есть ссылка, без входа' +
      (until ? ' — до ' + until : '') + '. Закрыть её можно здесь же.');
    panel.append(input, actions, note);
    box.append(main, panel);
    let link = share.link || '';
    let busy = false;

    function sync() {
      main.textContent = link ? 'Ссылка для браузера · открыта' : 'Ссылка для браузера';
      main.setAttribute('aria-expanded', String(!panel.hidden));
      input.value = link;
    }
    const say = msg => { if (toast) toast(msg); };
    main.addEventListener('click', async () => {
      if (busy) return;
      if (link) { panel.hidden = !panel.hidden; sync(); return; }
      busy = true;
      main.textContent = 'Делаю ссылку…';
      try {
        link = await share.create();
        panel.hidden = false;
      } catch (e) {
        say(e && e.message ? e.message : 'Ссылку сделать не удалось');
      }
      busy = false;
      sync();
    });
    copyBtn.addEventListener('click', async () => {
      say(await copyText(link, input) ? 'Ссылка скопирована' : 'Выделите ссылку и скопируйте');
    });
    if (sendBtn) sendBtn.addEventListener('click', () => share.send(link, title));
    closeBtn.addEventListener('click', async () => {
      if (busy) return;
      busy = true;
      try {
        await share.revoke();
        link = '';
        panel.hidden = true;
        say('Ссылка закрыта: по ней отчёт больше не откроется');
      } catch (e) {
        say(e && e.message ? e.message : 'Закрыть ссылку не удалось');
      }
      busy = false;
      sync();
    });
    sync();
    return box;
  }

  function mount(container, view, opts) {
    opts = opts || {};
    const art = h('article', 'rep');
    const head = h('header', 'rep-head');
    head.append(h('h1', null, view.title));
    const meta = [view.source, view.data_at ? 'данные на ' + dataAt(view.data_at) : '',
                  opts.sharedUntil ? 'ссылка работает до ' + day(opts.sharedUntil) : ''].filter(Boolean).join(' · ');
    if (meta) head.append(h('p', 'rep-meta', meta));
    if (opts.share) head.append(shareBar(opts.share, view.title, opts.toast));
    art.append(head);

    const charts = [];
    if (view.kind === 'note') {
      art.append(markup('div', 'rep-text rep-note', view.how_html));
    } else {
      if (view.summary_html) art.append(markup('div', 'rep-summary rep-text', view.summary_html));
      (view.sections || []).forEach((s, i) => {
        const sec = h('section', 'rep-sec');
        sec.id = 's' + (i + 1);
        sec.append(h('h2', null, s.heading));
        if (s.html) sec.append(markup('div', 'rep-text', s.html));
        const withCard = s.chart && root.TgChart;
        if (s.chart) {
          const box = h('div', 'rep-chart');
          sec.append(box);
          charts.push({ box, spec: s.chart, n: i + 1,
                        howNode: withCard && s.how_html ? markup('div', 'rep-text', s.how_html) : null });
        }
        if (s.table) sec.append(table(s.table));
        if (s.how_html && !withCard) sec.append(how(s.how_html));
        art.append(sec);
      });
      if (view.how_html) art.append(how(view.how_html, 'Как считается — весь отчёт'));
    }
    container.append(art);

    const mounted = [];
    if (root.TgChart) {
      for (const c of charts) {
        mounted.push(root.TgChart.mount(c.box, c.spec, {
          mode: 'app', id: 'chart-' + c.n, toast: opts.toast, onSelect: opts.onSelect,
          hideTitle: true, howNode: c.howNode,
        }));
      }
    } else {
      for (const c of charts) c.box.append(h('p', 'rep-meta', 'График не загрузился.'));
    }
    return {
      el: art,
      retheme() { mounted.forEach(m => m.retheme()); },
    };
  }

  root.TgReport = { mount, cellText };
})(typeof window !== 'undefined' ? window : globalThis);

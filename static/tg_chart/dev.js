/* dev-страница мини-приложения (/tg/chart/dev, только при FLASK_DEBUG): графики-фикстуры
 * (kultura_bot/charts/fixtures.py) в обеих темах — сверить вид с прототипом и с PNG.
 * ?png=1 — карточки в виде для картинки (без переключателей и подсказок). */
(function () {
  'use strict';

  const root = document.documentElement;
  const payload = JSON.parse(document.getElementById('tg-chart-data').textContent);
  const cardsEl = document.getElementById('cards');
  const toastEl = document.getElementById('toast');
  const pngView = payload.view === 'png-preview';
  const mounted = [];
  const KEY = 'tg-chart-dev-theme';

  let toastTimer = 0;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2400);
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // Полоса над карточками: тема (День / Ночь), вид (интерактивный / как PNG), ссылки.
  const bar = el('div', 'dev-bar');
  const left = el('span', null, pngView ? 'Вид PNG-картинки' : 'Графики-фикстуры прототипа');
  const seg = el('span', 'seg');
  seg.setAttribute('role', 'group');
  seg.setAttribute('aria-label', 'Тема');
  const effective = () => root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const buttons = [['light', 'День'], ['dark', 'Ночь']].map(([value, label]) => {
    const b = el('button', null, label);
    b.type = 'button';
    b.addEventListener('click', () => {
      root.dataset.theme = value;
      try { localStorage.setItem(KEY, value); } catch (e) { /* без памяти темы */ }
      sync();
      mounted.forEach(m => m.retheme());
    });
    seg.append(b);
    return [value, b];
  });
  function sync() { buttons.forEach(([value, b]) => b.setAttribute('aria-pressed', String(effective() === value))); }
  const view = el('a', null, pngView ? 'Интерактивный вид' : 'Вид PNG');
  view.href = pngView ? '?' : '?png=1';
  bar.append(left, seg, view);
  const nav = el('nav', 'dev-nav');
  nav.setAttribute('aria-label', 'Графики');
  for (const c of payload.charts) {
    const a = el('a', null, c.chart.title.replace(/^Пример: /, ''));
    a.href = '#' + c.name;
    nav.append(a);
    const png = el('a', null, 'PNG');
    png.href = '/tg/chart/dev/' + c.name + '.png';
    png.target = '_blank';
    nav.append(png);
  }
  cardsEl.before(bar, nav);

  try {
    const saved = localStorage.getItem(KEY);
    if (!root.dataset.theme && (saved === 'light' || saved === 'dark')) root.dataset.theme = saved;
  } catch (e) { /* без памяти темы */ }
  sync();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { sync(); mounted.forEach(m => m.retheme()); });

  TgChart.fontsReady().then(() => {
    for (const c of payload.charts) {
      mounted.push(TgChart.mount(cardsEl, c.chart, { mode: pngView ? 'png' : 'dev', id: c.name, toast }));
    }
  });
})();

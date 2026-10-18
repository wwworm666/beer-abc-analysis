/* Мини-приложение «Графики» (/tg/chart): Telegram -> initData -> /api/tg/charts/<id> -> карточка.
 *
 * Откуда id графика: ?id=<id> (кнопка web_app в личке) или start_param (прямая ссылка
 * t.me/<бот>/<short_name>?startapp=<id> из группы). initData — из Telegram.WebApp; если
 * официальный скрипт не загрузился (telegram.org недоступен), — из #tgWebAppData в адресе:
 * клиент Telegram кладёт туда те же данные. Без initData страница просит открыть её из
 * Telegram. Тема — Telegram.WebApp.colorScheme и событие themeChanged. */
(function () {
  'use strict';

  const ID_RE = /^[A-Za-z0-9_-]{16,64}$/;
  const root = document.documentElement;
  const tg = window.Telegram && window.Telegram.WebApp;
  const hash = new URLSearchParams((location.hash || '').replace(/^#/, ''));
  const stateEl = document.getElementById('state');
  const cardsEl = document.getElementById('cards');
  const toastEl = document.getElementById('toast');
  const payload = readPayload();
  const initData = (tg && tg.initData) || hash.get('tgWebAppData') || '';
  const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param)
    || hash.get('tgWebAppStartParam') || paramOf(initData, 'start_param');
  const chartId = new URLSearchParams(location.search).get('id') || startParam || '';
  let card = null;

  function readPayload() {
    try { return JSON.parse(document.getElementById('tg-chart-data').textContent) || {}; } catch (e) { return {}; }
  }
  function paramOf(query, name) {
    try { return new URLSearchParams(query).get(name) || ''; } catch (e) { return ''; }
  }
  const atLeast = v => !!(tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v));

  /* ---- тема ---- */
  function luminance(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return 1;
    const n = parseInt(m[1], 16);
    const ch = [n >> 16, (n >> 8) & 255, n & 255].map(c => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  }
  function scheme() {
    if (tg && tg.colorScheme) return tg.colorScheme;
    try {
      const p = JSON.parse(hash.get('tgWebAppThemeParams') || '{}');
      if (p.bg_color) return luminance(p.bg_color) < 0.2 ? 'dark' : 'light';
    } catch (e) { /* параметры темы битые — берём системную */ }
    return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function applyTheme() {
    root.dataset.theme = scheme() === 'dark' ? 'dark' : 'light';
    const bg = getComputedStyle(root).getPropertyValue('--page').trim();
    try {
      if (atLeast('6.1')) tg.setBackgroundColor(bg);
      if (atLeast('6.9')) tg.setHeaderColor(bg);       // цвет #RRGGBB в шапке — с Bot API 6.9
    } catch (e) { /* старый клиент: шапка остаётся цвета Telegram */ }
    if (card) card.retheme();
  }

  function haptic() {
    try { if (atLeast('6.1')) tg.HapticFeedback.selectionChanged(); } catch (e) { /* без отклика */ }
  }
  let toastTimer = 0;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2400);
  }

  /* ---- состояния ---- */
  function show(title, text, code) {
    stateEl.textContent = '';
    const b = document.createElement('b');
    b.textContent = title;
    stateEl.append(b, document.createTextNode(text || ''));
    if (code) {
      const c = document.createElement('code');
      c.textContent = code;
      stateEl.append(' ', c);
    }
    stateEl.hidden = false;
  }

  async function load() {
    if (!initData) {
      show('Откройте из Telegram', 'Это мини-приложение бота @' + (payload.bot || 'MCPkulturabot') +
        ': нажмите «Открыть интерактивно» под графиком в чате.');
      return;
    }
    if (!ID_RE.test(chartId)) {
      show('В ссылке нет графика', 'Откройте график кнопкой «Открыть интерактивно» под картинкой в чате.');
      return;
    }
    show('Загружаю график…', '');
    let resp, body = {};
    try {
      resp = await fetch('/api/tg/charts/' + encodeURIComponent(chartId), {
        headers: { Authorization: 'tma ' + initData }, cache: 'no-store', credentials: 'omit',
      });
      body = await resp.json().catch(() => ({}));
    } catch (e) {
      show('Нет связи с сервером', 'Проверьте интернет и откройте график заново.');
      return;
    }
    if (resp.ok && body.chart) {
      await TgChart.fontsReady();
      stateEl.hidden = true;
      card = TgChart.mount(cardsEl, body.chart, { mode: 'app', id: 'card', onSelect: haptic, toast });
      return;
    }
    if (resp.status === 403) {
      show('Нет доступа к графикам', 'Передайте владельцу свой Telegram ID — он добавит вас в список:', String(body.user_id || ''));
    } else if (resp.status === 404) {
      show('График не найден', 'Графики хранятся 90 дней. Попросите бота прислать его заново.');
    } else if (resp.status === 401) {
      show('Сессия Telegram устарела', 'Закройте мини-приложение и откройте график из чата ещё раз.');
    } else {
      show('График не открылся', body.error || ('Ошибка сервера ' + resp.status));
    }
  }

  applyTheme();
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (atLeast('7.7')) tg.disableVerticalSwipes();   // свайп по графику не сворачивает окно
      tg.onEvent('themeChanged', applyTheme);
    } catch (e) { /* клиент без этих методов — страница работает и так */ }
  } else if (window.matchMedia) {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
  }
  load();
})();

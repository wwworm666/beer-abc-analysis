/* Отчёт или записка «Как считается» страницей сайта (/tg/report/<id>, routes/tg_miniapp.py).
 * Вход — обычный вход сайта; данные уже в странице (payload.report), тема — системная.
 * Та же страница по ссылке для браузера (/r/<код>, payload.shared) — без входа и без кнопки
 * ссылки; ссылку закрыли или срок истёк (payload.gone) — «Ссылка не работает». */
(function () {
  'use strict';

  const root = document.documentElement;
  const cardsEl = document.getElementById('cards');
  const toastEl = document.getElementById('toast');
  let payload = {};
  try { payload = JSON.parse(document.getElementById('tg-chart-data').textContent) || {}; } catch (e) { /* пусто */ }
  let toastTimer = 0;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2400);
  }
  if (payload.gone) {                     // /r/<код>: ссылку закрыли или срок отчёта истёк
    const box = document.createElement('div');
    box.className = 'state';
    const b = document.createElement('b');
    b.textContent = 'Ссылка не работает';
    box.append(b, document.createTextNode('Её закрыли или отчёт удалён: отчёты хранятся 90 дней. ' +
      'Попросите прислать новую ссылку.'));
    cardsEl.append(box);
    return;
  }
  if (!payload.report) return;
  root.classList.add('is-report');

  // Ссылка для браузера — у страницы сайта (вход сайта); на странице по ссылке её нет.
  function call(method) {
    return fetch('/api/tg/reports/' + encodeURIComponent(payload.report.id) + '/link', {
      method, cache: 'no-store', credentials: 'same-origin',
    }).then(async resp => {
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(body.error || ('Ошибка сервера ' + resp.status));
      return body;
    });
  }
  const opts = { toast };
  if (payload.shared) {
    opts.sharedUntil = payload.expires_at;
  } else if (payload.report.id) {
    opts.share = {
      link: payload.link || '', expiresAt: payload.expires_at || '',
      create: () => call('POST').then(body => body.link),
      revoke: () => call('DELETE'),
      send: navigator.share ? (url, title) => navigator.share({ url, title }).catch(() => {}) : null,
      sendLabel: 'Поделиться',
    };
  }
  TgChart.fontsReady().then(() => {
    const page = TgReport.mount(cardsEl, payload.report, opts);
    if (window.matchMedia) {
      matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => page.retheme());
    }
  });
})();

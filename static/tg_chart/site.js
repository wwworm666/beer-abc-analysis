/* Отчёт или записка «Как считается» страницей сайта (/tg/report/<id>, routes/tg_miniapp.py).
 * Вход — обычный вход сайта; данные уже в странице (payload.report), тема — системная. */
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
  if (!payload.report) return;
  root.classList.add('is-report');
  TgChart.fontsReady().then(() => {
    const page = TgReport.mount(cardsEl, payload.report, { toast });
    if (window.matchMedia) {
      matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => page.retheme());
    }
  });
})();

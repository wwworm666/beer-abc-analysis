/* PNG-режим (core/tg_chart_png.py): одна карточка без переключателей, подсказок и анимации.
 * Когда ECharts дорисовал график, ставит window.__tgChartReady = true — Chromium делает снимок #card. */
(function () {
  'use strict';

  const FALLBACK_MS = 3000;   // если ECharts не прислал «finished» — снимаем всё равно
  const payload = JSON.parse(document.getElementById('tg-chart-data').textContent);
  let done = false;
  function finish() {
    if (done) return;
    done = true;
    // два кадра: SVG уже в DOM, браузер успел его разложить
    requestAnimationFrame(() => requestAnimationFrame(() => { window.__tgChartReady = true; }));
  }
  TgChart.fontsReady(4000).then(() => {
    TgChart.mount(document.getElementById('cards'), payload.chart, { mode: 'png', id: 'card', onRendered: finish });
    setTimeout(finish, FALLBACK_MS);
  });
})();

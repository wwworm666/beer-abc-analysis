/* Обёртки Chart.js для раздела «Гости»: цвета из переменных дизайн-системы,
   автоматическое уничтожение старых графиков при перерисовке вкладки. */

window.GCharts = (function () {
    'use strict';

    var registry = {}; // canvasId -> Chart

    function cssVar(name, fallback) {
        var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    }
    function palette() {
        return {
            accent: cssVar('--accent', '#D97757'),
            success: cssVar('--success', '#059669'),
            warning: cssVar('--warning', '#D97706'),
            danger: cssVar('--danger', '#DC2626'),
            text: cssVar('--text-secondary', '#666666'),
            grid: cssVar('--border-color', '#E8E6E3')
        };
    }
    function baseOptions() {
        var p = palette();
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: p.text, font: { family: 'IBM Plex Mono' }, boxWidth: 12 } },
                tooltip: { titleFont: { family: 'IBM Plex Mono' }, bodyFont: { family: 'IBM Plex Mono' } }
            },
            scales: {
                x: { ticks: { color: p.text, font: { family: 'IBM Plex Mono', size: 10 } },
                     grid: { color: 'transparent' } },
                y: { ticks: { color: p.text, font: { family: 'IBM Plex Mono', size: 10 } },
                     grid: { color: p.grid } }
            }
        };
    }
    function make(canvasId, config) {
        if (registry[canvasId]) { registry[canvasId].destroy(); delete registry[canvasId]; }
        var el = document.getElementById(canvasId);
        if (!el) return null;
        var chart = new Chart(el.getContext('2d'), config);
        registry[canvasId] = chart;
        return chart;
    }

    function bar(canvasId, labels, datasets, extraOpts) {
        var opts = baseOptions();
        extraOpts = extraOpts || {};
        if (extraOpts.stacked) {
            opts.scales.x.stacked = true;
            opts.scales.y.stacked = true;
            delete extraOpts.stacked;
        }
        Object.assign(opts, extraOpts);
        return make(canvasId, { type: 'bar', data: { labels: labels, datasets: datasets }, options: opts });
    }
    function hbar(canvasId, labels, datasets, extraOpts) {
        var opts = baseOptions();
        opts.indexAxis = 'y';
        opts.scales = {
            x: { ticks: { color: palette().text, font: { family: 'IBM Plex Mono', size: 10 } },
                 grid: { color: palette().grid } },
            y: { ticks: { color: palette().text, font: { family: 'IBM Plex Mono', size: 10 } },
                 grid: { color: 'transparent' } }
        };
        Object.assign(opts, extraOpts || {});
        return make(canvasId, { type: 'bar', data: { labels: labels, datasets: datasets }, options: opts });
    }
    function line(canvasId, labels, datasets, extraOpts) {
        var opts = baseOptions();
        Object.assign(opts, extraOpts || {});
        return make(canvasId, { type: 'line', data: { labels: labels, datasets: datasets }, options: opts });
    }
    function doughnut(canvasId, labels, values, colors) {
        var p = palette();
        var opts = {
            responsive: true, maintainAspectRatio: false, cutout: '62%',
            plugins: { legend: { position: 'right',
                labels: { color: p.text, font: { family: 'IBM Plex Mono', size: 11 }, boxWidth: 12 } } }
        };
        return make(canvasId, {
            type: 'doughnut',
            data: { labels: labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
            options: opts
        });
    }

    return { palette: palette, bar: bar, hbar: hbar, line: line, doughnut: doughnut };
})();

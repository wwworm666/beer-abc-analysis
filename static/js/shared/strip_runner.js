/**
 * Загрузка страницы по полосе «Бар и период» — считать сразу, без кнопок «Рассчитать»
 * (ответ владельца Р5, 2026-11-01; план единого виджета — docs/planning/period-widget-rollout.md,
 * раздел 3.7). Тяжёлые страницы (зарплата, сотрудники, цели, график) ходят в iiko от секунд до
 * минуты, поэтому:
 *   - серия изменений даёт один запрос после паузы (schedule — debounce, по умолчанию 350 мс);
 *   - устаревший ответ отбрасывается: у каждого запуска свой номер, рисуется только последний;
 *     прежний запрос браузера отменяется (AbortController), чтобы не держать соединения;
 *   - пока идёт расчёт, это видно: onStart зовётся сразу при изменении, ещё до паузы, —
 *     страница пишет «Считаю зарплату за октябрь 2026…».
 *
 *   var runner = KStripRunner.create({
 *       delay: 350,
 *       run: function (signal) { return fetch(url, { signal: signal }).then(...); },  // Promise
 *       onStart: function () { ... },          // показать, что считается
 *       onDone: function (result) { ... },     // только для последнего запуска
 *       onError: function (err) { ... },       // только для последнего запуска; отмена — не ошибка
 *       onFinally: function () { ... }         // после последнего запуска (спрятать «Считаю…»)
 *   });
 *   runner.now();       // сразу — открытие страницы
 *   runner.schedule();  // после паузы — изменение в полосе или на странице
 *   runner.cancel();    // забыть ожидание и идущий запуск
 *   runner.busy();      // true, пока ждём паузу или ответ
 *
 * Обычный скрипт без модулей: window.KStripRunner; для Node-тестов — module.exports.
 */
(function (root, factory) {
    var api = factory();
    root.KStripRunner = api;
    if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    var DEFAULT_DELAY_MS = 350;   // пауза после последнего изменения (план, раздел 3.7)

    function isAbort(err) {
        return !!err && (err.name === 'AbortError' || err.code === 20);
    }

    function create(opts) {
        opts = opts || {};
        var delay = typeof opts.delay === 'number' ? opts.delay : DEFAULT_DELAY_MS;
        var seq = 0;            // номер последнего запуска; ответ с другим номером устарел
        var timer = null;
        var controller = null;
        var inFlight = false;

        function call(name, arg) {
            if (typeof opts[name] !== 'function') return;
            try { opts[name](arg); } catch (e) { if (typeof console !== 'undefined') console.error(e); }
        }

        function abortPrevious() {
            if (controller) {
                try { controller.abort(); } catch (e) { /* старый браузер */ }
            }
            controller = null;
        }

        function start() {
            timer = null;
            var my = ++seq;
            abortPrevious();
            controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
            inFlight = true;
            call('onStart');
            var promise;
            try {
                promise = Promise.resolve(opts.run(controller ? controller.signal : undefined));
            } catch (e) {
                promise = Promise.reject(e);
            }
            return promise.then(function (result) {
                if (my !== seq) return;
                call('onDone', result);
            }, function (err) {
                if (my !== seq || isAbort(err)) return;
                call('onError', err);
            }).then(function () {
                if (my !== seq) return;
                inFlight = false;
                controller = null;
                call('onFinally');
            });
        }

        return {
            now: function () {
                clearTimeout(timer);
                return start();
            },
            schedule: function () {
                clearTimeout(timer);
                seq++;                 // ответ идущего запуска уже не нужен
                abortPrevious();
                inFlight = false;
                call('onStart');
                timer = setTimeout(start, delay);
            },
            cancel: function () {
                clearTimeout(timer);
                timer = null;
                seq++;
                abortPrevious();
                inFlight = false;
            },
            busy: function () { return timer !== null || inFlight; }
        };
    }

    return { create: create, DEFAULT_DELAY_MS: DEFAULT_DELAY_MS, isAbort: isAbort };
});

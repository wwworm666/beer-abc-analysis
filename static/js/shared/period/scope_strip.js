/**
 * Полоса «Бар и период» — одна на всех страницах с данными (templates/shared/scope_strip.html,
 * план единого виджета — docs/planning/period-widget-rollout.md, разделы 3.1–3.6).
 *
 * Сервер рисует полосу уже с выбором (core/scope.build_strip: ссылка -> cookie -> правило
 * страницы), поэтому при переходе между страницами она не мигает. Этот скрипт оживляет её:
 *   - период — общий элемент (period_picker.js) в разметке сервера;
 *   - бар — меню «Все бары» и четыре бара (одна подпись на сайт, ответ Р6);
 *   - выбор пишется в cookie (scope.js) и адрес страницы, полоса коротко подсвечивается —
 *     видно, что выбор применён ко всему сайту;
 *   - «Сбросить выбор» — страница возвращается к своему правилу (текущий период шага, Р2);
 *   - выбор из другой вкладки подхватывается, когда к странице возвращаются.
 *
 * Страница слушает изменения:
 *   KStrip.onChange(function (e) { e.type: 'period' | 'bar'; e.period, e.bar; e.cause: 'user' | 'reset' | 'external' });
 *   KStrip.get()                       -> {bar, period}
 *   KStrip.showPeriod(period)          -> показать период, не меняя общий выбор (показ — не выбор)
 *   KStrip.setBar(ключ)                -> сменить бар из кода страницы (сохраняется для сайта)
 *   KStrip.setPeriod(период)           -> выбрать период из кода страницы (как выбор в элементе)
 *   KStrip.barInfo(ключ)               -> {key, name, short, iiko_name, bar_id} или null
 *
 * Режим бара (cfg.barMode): all — «Все бары» и бары; single — страница «по одному бару»: при
 * «Все бары» на сайте сервер показывает последний бар таких страниц с подписью (ответ Р4), выбор
 * здесь сохраняется и как общий бар, и как последний бар таких страниц; none — бар не выбирается.
 *   KStrip.setSteps(steps, причина)    -> шаги вкладки
 *   KStrip.setNote(текст)              -> подпись в полосе («по месяцам — показан октябрь 2026»)
 *
 * Обычный скрипт после period_core.js, scope.js и period_picker.js.
 */
(function (root) {
    'use strict';

    var cfg = root.KULTURA_STRIP;
    var K = root.KPeriod;
    var S = root.KScope;
    var stripEl = root.document && root.document.getElementById('kultura-strip');
    if (!cfg || !K || !S || !root.KPeriodPicker || !stripEl) return;

    var APPLIED_MS = 700;   // подсветка полосы после выбора (period.css: .ks--applied)

    K.configure(cfg.clock);
    S.configure({ user: cfg.user, cookies: cfg.cookies, ttl: cfg.ttl });

    function toPeriod(p) {
        return p ? K.fromBounds(K.fromISO(p.start), K.fromISO(p.end)) : null;
    }

    var state = { bar: cfg.bar || '', period: toPeriod(cfg.period) };
    var listeners = [];
    var appliedTimer = null;

    // Ссылка с периодом и баром делает их текущим выбором; иначе — продлить час выбранного периода.
    if (cfg.chosenSource === 'url' && cfg.chosen) S.setPeriod(cfg.chosen);
    else S.touchPeriod();
    if (cfg.barSource === 'url') S.setBar(state.bar, { url: false });
    // Адрес показывает выбранный период — ссылку можно скопировать. Без выбора адрес чистый, а
    // у помесячной страницы в адрес не идёт показанный месяц: по ссылке он стал бы выбором.
    if (cfg.chosen && cfg.mode === 'report') K.writeUrlPeriod(toPeriod(cfg.chosen));

    function emit(e) {
        listeners.slice().forEach(function (fn) {
            try { fn(e); } catch (err) { if (root.console) root.console.error(err); }
        });
    }
    function applied() {
        stripEl.classList.remove('ks--applied');
        void stripEl.offsetWidth;   // перезапуск подсветки при серии выборов
        stripEl.classList.add('ks--applied');
        clearTimeout(appliedTimer);
        appliedTimer = setTimeout(function () { stripEl.classList.remove('ks--applied'); }, APPLIED_MS);
    }

    // ---------------------------------------------------------------- период

    var noteEl = root.document.getElementById('ks-note');
    function setNote(text) {
        if (!noteEl) return;
        noteEl.textContent = text || '';
        noteEl.hidden = !text;
    }

    var periodEl = root.document.getElementById('ks-period');
    var picker = root.KPeriodPicker.mount(periodEl, {
        variant: 'strip',
        steps: cfg.steps,
        quick: cfg.quick || K.SITE_QUICK,
        value: state.period || K.currentPeriod('week'),
        allowFuture: !!cfg.allowFuture,
        maxDays: cfg.maxDays || null,
        maxReason: cfg.maxReason || null,
        freshness: cfg.freshness || null,
        disabled: cfg.mode === 'now',
        disabledSub: 'данные на сейчас',
        onChange: function (period) {
            state.period = period;
            S.setPeriod(period);
            K.writeUrlPeriod(period);
            setNote('');
            watcher.sync();
            applied();
            emit({ type: 'period', period: period, bar: state.bar, cause: 'user' });
        },
        onReset: function () {
            S.resetPeriod();
            K.writeUrlPeriod(null);
            var period = toPeriod(cfg.default);
            state.period = period;
            picker.set(period, { silent: true });
            setNote('');
            watcher.sync();
            applied();
            emit({ type: 'period', period: period, bar: state.bar, cause: 'reset' });
        }
    });

    // ---------------------------------------------------------------- бар

    var barTrigger = root.document.getElementById('ks-bar-trigger');
    var barMenu = root.document.getElementById('ks-bar-menu');
    var barName = root.document.getElementById('ks-bar-name');
    var barHint = root.document.getElementById('ks-bar-hint');
    var backdrop = root.document.getElementById('ks-backdrop');

    function barLabel(key) {
        for (var i = 0; i < cfg.bars.length; i++) {
            if (cfg.bars[i].key === key) return { name: cfg.bars[i].name, hint: cfg.bars[i].short };
        }
        return { name: cfg.allLabel, hint: cfg.allHint };
    }
    function renderBar() {
        if (cfg.barMode === 'none') return;   // подпись страницы без баров рисует сервер
        var label = barLabel(state.bar);
        if (barName) barName.textContent = label.name;
        if (barHint) barHint.textContent = label.hint;
        if (!barMenu) return;
        Array.prototype.forEach.call(barMenu.querySelectorAll('[data-bar]'), function (item) {
            var on = item.getAttribute('data-bar') === state.bar;
            item.classList.toggle('active', on);
            item.setAttribute('aria-selected', on ? 'true' : 'false');
        });
    }
    function closeBarMenu() {
        if (!barMenu || barMenu.classList.contains('hidden')) return;
        barMenu.classList.add('hidden');
        if (backdrop) backdrop.classList.add('hidden');
        if (barTrigger) barTrigger.setAttribute('aria-expanded', 'false');
    }
    function openBarMenu() {
        picker.close();
        // Другие списки полосы (выгрузка страницы) закрываются: открыт один список.
        Array.prototype.forEach.call(stripEl.querySelectorAll('.fb-menu'), function (m) {
            if (m !== barMenu) m.classList.add('hidden');
        });
        barMenu.classList.remove('hidden');
        if (backdrop) backdrop.classList.remove('hidden');
        barTrigger.setAttribute('aria-expanded', 'true');
        var stripRect = stripEl.getBoundingClientRect();
        var tRect = barTrigger.getBoundingClientRect();
        barMenu.style.setProperty('--fb-menu-left', Math.max(0, Math.round(tRect.left - stripRect.left)) + 'px');
    }
    function chooseBar(key, cause) {
        var v = S.normalize(key);
        if (v === null) v = '';
        // Страница «по одному бару» не показывает всю сеть: остаётся её бар (подпись — с сервера).
        if (cfg.barMode === 'single' && !v) return;
        if (cause === 'user') {
            v = S.setBar(v);
            if (cfg.barMode === 'single') S.setBarSingle(v);
            setNote('');
        }
        var changed = v !== state.bar;
        state.bar = v;
        renderBar();
        if (!changed) return;
        if (cause === 'user') watcher.sync();
        applied();
        emit({ type: 'bar', bar: v, period: state.period, cause: cause });
    }
    if (barTrigger && barMenu && cfg.barMode !== 'none') {
        barTrigger.addEventListener('click', function (e) {
            e.stopPropagation();
            if (barMenu.classList.contains('hidden')) openBarMenu(); else closeBarMenu();
        });
        barMenu.addEventListener('click', function (e) {
            e.stopPropagation();
            var item = e.target.closest('[data-bar]');
            if (!item) return;
            closeBarMenu();
            chooseBar(item.getAttribute('data-bar'), 'user');
        });
        if (backdrop) backdrop.addEventListener('click', closeBarMenu);
        root.document.addEventListener('click', function (e) {
            if (!barMenu.contains(e.target) && e.target !== barTrigger) closeBarMenu();
        });
        root.document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeBarMenu();
        });
    }

    // ---------------------------------------------------------------- другие вкладки

    var watcher = S.watch(function (snap) {
        if (snap.bar !== state.bar && cfg.barMode !== 'none') chooseBar(snap.bar, 'external');
        var next = snap.period ? toPeriod(snap.period) : toPeriod(cfg.default);
        if (cfg.mode === 'monthly' && next && next.granularity !== 'month') next = K.monthOf(next);
        if (cfg.mode !== 'now' && next && (!state.period || next.key !== state.period.key)) {
            state.period = next;
            picker.set(next, { silent: true });
            applied();
            emit({ type: 'period', period: next, bar: state.bar, cause: 'external' });
        }
    });

    root.KStrip = {
        get: function () { return { bar: state.bar, period: state.period }; },
        onChange: function (fn) { listeners.push(fn); },
        picker: picker,
        // Показать период, не трогая общий выбор и адрес (вкладка «Планы» показывает месяц недели).
        showPeriod: function (period) {
            state.period = period;
            picker.set(period, { silent: true });
        },
        // Сменить бар из кода страницы — как выбор в меню: сохраняется для всего сайта.
        setBar: function (key) { chooseBar(key, 'user'); },
        // Выбрать период из кода страницы (открыт сохранённый отчёт, «Открыть последний период с
        // данными») — как выбор в элементе: сохраняется для сайта и пишется в адрес.
        setPeriod: function (period) { picker.set(period); },
        barInfo: function (key) {
            for (var i = 0; i < cfg.bars.length; i++) if (cfg.bars[i].key === key) return cfg.bars[i];
            return null;
        },
        setSteps: function (steps, note) { picker.setSteps(steps, note); },
        setNote: setNote,
        config: cfg
    };
})(typeof window !== 'undefined' ? window : globalThis);

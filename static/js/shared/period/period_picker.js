/**
 * Элемент «Период» — один на сайте (docs/period-standard.md, раздел 4; план единого виджета —
 * docs/planning/period-widget-rollout.md, разделы 3.3–3.4). Основа — шапка дашборда.
 *
 *   [‹]  [календарь  Октябрь 2026  идёт, по 29.10  ▾]  [›]
 *
 * Название всегда с годом, неполный период подписан текстом (не только подсказкой при
 * наведении). Стрелки шагают на период текущего шага (свой период — на его длину) и выключены
 * на границах данных; клавиши ← → ведут себя как стрелки. По нажатию на название — панель (на
 * телефоне — лист снизу): шаг (день, неделя, месяц, год — кварталов нет), сетка периодов шага,
 * быстрый выбор, «Свой период», свежесть данных, «Сбросить выбор».
 *
 * «Свой период»: поля «с ДД.ММ.ГГГГ по ДД.ММ.ГГГГ» — вводятся цифрами, точки ставятся сами,
 * вставка «01.03.2024 – 31.10.2026» заполняет оба поля, ошибки — текстом под полями, Enter или
 * «Показать» применяет. Ниже — календарь: на компьютере два месяца, на телефоне один; нажатие на
 * название месяца открывает сетку месяцев и лет. Два нажатия по дням применяют период сразу.
 * Длина не ограничена; предел ставит только страница (maxDays) и пишет почему (maxReason).
 *
 * Арифметика дат — static/js/shared/period/period_core.js (window.KPeriod), здесь только DOM.
 *
 *   var picker = KPeriodPicker.mount(container, {
 *       steps: ['day', 'week', 'month', 'year', 'custom'],
 *       quick: KPeriod.SITE_QUICK,     // страница прячет то, что не умеет
 *       value: KPeriod.currentPeriod('week'),
 *       allowFuture: false,            // страницы планирования — true
 *       urlSync: true,                 // ?date_from=&date_to= в адресе
 *       maxDays: 366, maxReason: '…',  // только тяжёлые страницы
 *       freshness: 'Данные по 31.10',
 *       onChange: function (period) { ... },
 *       onReset: function () { ... }   // кнопка «Сбросить выбор» в панели
 *   });
 *   picker.get(); picker.set(period, {silent: true}); picker.setSteps(['month', 'year'], 'причина');
 *
 * disabled: true — страница «на сейчас»: вместо периода серая надпись (disabledTitle,
 * disabledSub), стрелок и панели нет.
 */
(function (root) {
    'use strict';

    var K = root.KPeriod;
    var STEP_NAMES = { day: 'День', week: 'Неделя', month: 'Месяц', year: 'Год' };
    var DEFAULT_STEPS = ['day', 'week', 'month', 'year', 'custom'];
    var WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    var MONTHS_FULL = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август',
        'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    var WEEKS_PER_PAGE = 10;
    var SLIDE_MS = 240;          // анимация названия при шаге стрелкой (period.css: .kp--slide-*)
    var ICON_CAL = '<svg class="kp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/>' +
        '<line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/></svg>';
    var ICON_CARET = '<svg class="kp-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';
    var ICON_PREV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" ' +
        'stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>';
    var ICON_NEXT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" ' +
        'stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>';

    function esc(s) {
        return String(s === null || s === undefined ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function samePeriod(a, b) { return !!a && !!b && a.start === b.start && a.end === b.end; }
    // Телефон — лист снизу и один месяц календаря (как @media в period.css).
    function isPhone() {
        return !!(root.matchMedia && root.matchMedia('(max-width: 768px)').matches);
    }

    function Picker(container, opts) {
        this.root = container;
        this.opts = opts || {};
        this.steps = (this.opts.steps || DEFAULT_STEPS).slice();
        this.stepNote = '';
        this.quick = this.opts.quick || K.SITE_QUICK;
        this.committed = this.opts.value || K.currentPeriod('week');
        this.view = this.committed;     // показан в шапке, ещё не применён (стрелки)
        this.timer = null;
        this.slideTimer = null;
        this.open = false;
        this.panelStep = null;          // шаг, выбранный в панели
        this.cursor = null;             // год сетки месяцев или конец списка недель
        this.calendar = null;           // {month: Date, mode: 'single'|'range', from: Date|null, jump: год|null}
        this.typed = null;              // поля своего периода: {from: 'ДД.ММ.ГГГГ', to: '…'}
        this.typedError = '';
        this.build();
        this.render();
        this.bindKeys();
    }

    Picker.prototype.build = function () {
        this.root.classList.add('kp');
        if (this.opts.variant === 'strip') this.root.classList.add('kp--strip');
        if (this.opts.disabled) this.root.classList.add('kp--disabled');
        this.root.innerHTML =
            '<button type="button" class="kp-arrow kp-prev" aria-label="Предыдущий период">' + ICON_PREV + '</button>' +
            '<button type="button" class="kp-trigger" aria-haspopup="dialog" aria-expanded="false">' + ICON_CAL +
            '<span class="kp-title"></span><span class="kp-sub"></span>' +
            // Короткие название и вторая строка — для полосы на телефоне (period.css, до 480 px).
            '<span class="kp-title-c"></span><span class="kp-sub-c"></span>' + ICON_CARET + '</button>' +
            '<button type="button" class="kp-arrow kp-next" aria-label="Следующий период">' + ICON_NEXT + '</button>' +
            '<div class="kp-backdrop" hidden></div>' +
            '<div class="kp-panel" role="dialog" aria-label="Выбор периода" hidden></div>';
        this.btnPrev = this.root.querySelector('.kp-prev');
        this.btnNext = this.root.querySelector('.kp-next');
        this.trigger = this.root.querySelector('.kp-trigger');
        this.titleEl = this.root.querySelector('.kp-title');
        this.subEl = this.root.querySelector('.kp-sub');
        this.titleCEl = this.root.querySelector('.kp-title-c');
        this.subCEl = this.root.querySelector('.kp-sub-c');
        this.backdrop = this.root.querySelector('.kp-backdrop');
        this.panel = this.root.querySelector('.kp-panel');
        var self = this;
        if (this.opts.disabled) {
            // Страница «на сейчас»: период не выбирается, стрелок нет.
            this.btnPrev.hidden = true;
            this.btnNext.hidden = true;
            this.trigger.disabled = true;
            this.trigger.removeAttribute('aria-haspopup');
            return;
        }
        this.btnPrev.addEventListener('click', function () { self.navigate(-1); });
        this.btnNext.addEventListener('click', function () { self.navigate(1); });
        this.trigger.addEventListener('click', function () { self.toggle(); });
        this.backdrop.addEventListener('click', function () { self.close(); });
        this.panel.addEventListener('click', function (e) { self.onPanelClick(e); });
        this.panel.addEventListener('input', function (e) { self.onInput(e); });
        this.panel.addEventListener('paste', function (e) { self.onPaste(e); });
        this.panel.addEventListener('keydown', function (e) { self.onPanelKey(e); });
        this.outside = function (e) {
            if (self.open && !self.root.contains(e.target)) self.close();
        };
        document.addEventListener('click', this.outside);
    };

    // ------------------------------------------------------------ границы

    Picker.prototype.maxDay = function () { return this.opts.allowFuture ? null : K.maxDate(); };
    Picker.prototype.minDay = function () { return K.dataStart(); };
    Picker.prototype.isDisabled = function (p) {
        var max = this.maxDay(), min = this.minDay();
        if (max && K.fromISO(p.start) > max) return true;
        if (min && K.fromISO(p.end) < min) return true;
        return false;
    };
    Picker.prototype.allows = function (p) {
        return this.steps.indexOf(p.granularity) >= 0;
    };
    Picker.prototype.tooLong = function (p) {
        var max = this.opts.maxDays;
        return !!max && K.daysBetweenInclusive(K.fromISO(p.start), K.fromISO(p.end)) > max;
    };
    Picker.prototype.rangeOpts = function () {
        return { allowFuture: !!this.opts.allowFuture, maxDays: this.opts.maxDays, maxReason: this.opts.maxReason };
    };

    // ------------------------------------------------------------ выбор и применение

    Picker.prototype.get = function () { return this.committed; };

    Picker.prototype.set = function (period, o) {
        if (!period) return;
        clearTimeout(this.timer);
        this.timer = null;
        this.view = period;
        if (o && o.silent) {
            this.committed = period;
            if (this.opts.urlSync) K.writeUrlPeriod(period);
            this.render();
            return;
        }
        this.commit(period);
    };

    // Стрелки — с паузой: подпись меняется сразу, дорогой запрос уходит один за серию шагов.
    Picker.prototype.pick = function (period, immediate) {
        this.view = period;
        this.render();
        clearTimeout(this.timer);
        var self = this;
        if (immediate) {
            this.timer = null;
            this.commit(period);
        } else {
            this.timer = setTimeout(function () { self.timer = null; self.commit(self.view); },
                this.opts.debounceMs === undefined ? 350 : this.opts.debounceMs);
        }
    };

    Picker.prototype.commit = function (period) {
        var changed = !samePeriod(this.committed, period) || this.committed.granularity !== period.granularity;
        this.committed = period;
        this.view = period;
        this.render();
        if (this.opts.urlSync) K.writeUrlPeriod(period);
        if (changed && typeof this.opts.onChange === 'function') this.opts.onChange(period);
    };

    Picker.prototype.navigate = function (dir) {
        if (this.opts.disabled) return;
        var next = K.shiftPeriod(this.view, dir);
        if (this.isDisabled(next)) return;
        this.slide(dir);
        this.pick(next, false);
    };

    // Название едет в сторону стрелки (period.css); при «уменьшить движение» CSS анимацию снимает.
    Picker.prototype.slide = function (dir) {
        var cls = dir < 0 ? 'kp--slide-prev' : 'kp--slide-next';
        var rootEl = this.root;
        rootEl.classList.remove('kp--slide-prev', 'kp--slide-next');
        void rootEl.offsetWidth;   // перезапуск анимации при серии шагов
        rootEl.classList.add(cls);
        clearTimeout(this.slideTimer);
        this.slideTimer = setTimeout(function () { rootEl.classList.remove(cls); }, SLIDE_MS);
    };

    // Шаги, доступные странице (вкладке). note — видимая причина, почему других нет.
    Picker.prototype.setSteps = function (steps, note) {
        this.steps = steps.slice();
        this.stepNote = note || '';
        if (this.open) this.renderPanel();
    };

    // ------------------------------------------------------------ шапка

    Picker.prototype.render = function () {
        if (this.opts.disabled) {
            this.setTitle(this.opts.disabledTitle || 'Сейчас', this.opts.disabledSub || '',
                          this.opts.disabledTitle || 'Сейчас');
            return;
        }
        var p = this.view;
        this.setTitle(K.periodTitle(p), K.periodSub(p), K.periodTitleCompact(p));
        this.root.classList.toggle('kp--partial', K.periodState(p) === 'partial');
        this.btnPrev.disabled = this.isDisabled(K.shiftPeriod(p, -1));
        this.btnNext.disabled = this.isDisabled(K.shiftPeriod(p, 1));
    };

    // Название и вторая строка — полные и короткие (полоса на телефоне показывает короткие).
    Picker.prototype.setTitle = function (title, sub, titleCompact) {
        this.titleEl.textContent = title;
        this.subEl.textContent = sub;
        this.subEl.hidden = !sub;
        var subC = K.periodSubCompact(sub);
        this.titleCEl.textContent = titleCompact;
        this.subCEl.textContent = subC;
        this.subCEl.hidden = !subC;
    };

    // ------------------------------------------------------------ панель

    Picker.prototype.toggle = function () { if (this.open) this.close(); else this.openPanel(); };

    Picker.prototype.openPanel = function () {
        if (this.opts.disabled) return;
        this.open = true;
        var g = this.view.granularity;
        this.panelStep = (g !== K.CUSTOM && this.steps.indexOf(g) >= 0) ? g : this.firstStep();
        this.cursor = null;
        this.calendar = null;
        this.typed = null;
        this.typedError = '';
        // Свой период открывается сразу полями с его датами.
        if (g === K.CUSTOM && this.steps.indexOf(K.CUSTOM) >= 0) this.enterCustom();
        this.renderPanel();
        this.panel.hidden = false;
        this.backdrop.hidden = false;
        this.trigger.setAttribute('aria-expanded', 'true');
        this.root.classList.add('kp--open');
    };

    Picker.prototype.close = function () {
        if (!this.open) return;
        this.open = false;
        this.panel.hidden = true;
        this.backdrop.hidden = true;
        this.trigger.setAttribute('aria-expanded', 'false');
        this.root.classList.remove('kp--open');
    };

    Picker.prototype.firstStep = function () {
        for (var i = 0; i < this.steps.length; i++) if (this.steps[i] !== K.CUSTOM) return this.steps[i];
        return 'day';
    };

    Picker.prototype.enterCustom = function () {
        this.typed = { from: K.formatTyped(this.committed.start), to: K.formatTyped(this.committed.end) };
        this.typedError = '';
        this.calendar = null;
    };

    Picker.prototype.renderPanel = function () {
        var html = '<span class="kp-grab" aria-hidden="true"></span>';
        var visibleSteps = this.steps.filter(function (s) { return s !== K.CUSTOM; });
        var custom = !!this.typed;
        if (visibleSteps.length > 1) {
            html += '<div class="kp-steps" role="group" aria-label="Шаг">' + visibleSteps.map(function (s) {
                return '<button type="button" class="kp-step' + (s === this.panelStep && !custom ? ' active' : '') +
                    '" data-step="' + s + '">' + STEP_NAMES[s] + '</button>';
            }, this).join('') + '</div>';
        }
        if (this.stepNote) html += '<div class="kp-note">' + esc(this.stepNote) + '</div>';
        if (custom) {
            html += this.renderCustom();
        } else {
            html += this.renderGrid();
            html += this.renderQuick();
            if (this.steps.indexOf(K.CUSTOM) >= 0) {
                html += '<button type="button" class="kp-custom" data-action="custom">Свой период — ввести даты' +
                    '<span aria-hidden="true">&rsaquo;</span></button>';
            }
        }
        var fresh = typeof this.opts.freshness === 'function' ? this.opts.freshness() : this.opts.freshness;
        var reset = typeof this.opts.onReset === 'function';
        if (fresh || reset) {
            html += '<div class="kp-foot">' + (fresh ? '<span class="kp-fresh">' + esc(fresh) + '</span>' : '<span></span>') +
                (reset ? '<button type="button" class="kp-reset" data-action="reset">Сбросить выбор</button>' : '') +
                '</div>';
        }
        // Два месяца календаря шире обычной панели (только компьютер).
        this.panel.classList.toggle('kp-panel--wide', custom && !isPhone());
        this.panel.innerHTML = html;
    };

    Picker.prototype.item = function (p, label, extra) {
        var cls = 'kp-cell' + (samePeriod(p, this.committed) ? ' active' : '') +
            (K.periodState(p) === 'partial' ? ' partial' : '');
        var disabled = this.isDisabled(p) || this.tooLong(p);
        return '<button type="button" class="' + cls + '" data-from="' + p.start + '" data-to="' + p.end + '"' +
            (disabled ? ' disabled' : '') + '>' + esc(label) + (extra ? '<small>' + esc(extra) + '</small>' : '') + '</button>';
    };

    Picker.prototype.anchorDay = function () {
        var end = K.fromISO(this.view.end);
        var max = this.maxDay();
        return max && end > max ? max : end;
    };

    Picker.prototype.renderGrid = function () {
        var step = this.panelStep, html = '', i;
        if (step === 'day') {
            if (!this.calendar || this.calendar.mode !== 'single') this.calendar = null;
            return this.renderCalendar('single');
        }
        if (step === 'week') {
            var endWeek = this.cursor ? K.fromISO(this.cursor) : K.startOfWeek(this.anchorDay());
            html += '<div class="kp-nav"><button type="button" class="kp-nav-btn" data-action="weeks-back" aria-label="Раньше">&lsaquo;</button>' +
                '<span>Недели</span><button type="button" class="kp-nav-btn" data-action="weeks-fwd" aria-label="Позже">&rsaquo;</button></div>';
            html += '<div class="kp-list">';
            for (i = 0; i < WEEKS_PER_PAGE; i++) {
                var w = K.periodFor('week', K.addDays(endWeek, -7 * i));
                html += this.item(w, K.periodTitle(w), K.periodSub(w));
            }
            return html + '</div>';
        }
        if (step === 'month') {
            var year = this.cursor ? Number(this.cursor) : this.anchorDay().getFullYear();
            html += '<div class="kp-nav"><button type="button" class="kp-nav-btn" data-action="year-back" aria-label="Предыдущий год">&lsaquo;</button>' +
                '<span>' + year + '</span><button type="button" class="kp-nav-btn" data-action="year-fwd" aria-label="Следующий год">&rsaquo;</button></div>';
            html += '<div class="kp-grid kp-grid--month">';
            for (i = 0; i < 12; i++) {
                var p = K.periodFor('month', new Date(year, i, 1));
                html += this.item(p, MONTHS_FULL[i], K.periodState(p) === 'partial' ? 'идёт' : '');
            }
            return html + '</div>';
        }
        // Годы: от первого года данных (или 9 лет назад) до года последнего доступного дня.
        var top = this.anchorDay().getFullYear();
        var max = this.maxDay();
        if (max) top = Math.max(top, max.getFullYear());
        var min = this.minDay();
        var bottom = min ? min.getFullYear() : top - 9;
        html += '<div class="kp-grid kp-grid--year">';
        for (i = top; i >= bottom; i--) {
            var y = K.periodFor('year', new Date(i, 0, 1));
            html += this.item(y, String(i), K.periodState(y) === 'partial' ? 'идёт' : '');
        }
        return html + '</div>';
    };

    Picker.prototype.renderQuick = function () {
        var self = this;
        var items = this.quick.map(function (id) {
            var q = K.QUICK[id];
            var p = q ? q.build() : null;
            if (!p || !self.allows(p) || self.isDisabled(p) || self.tooLong(p)) return '';
            return '<button type="button" class="kp-chip' + (samePeriod(p, self.committed) ? ' active' : '') +
                '" data-from="' + p.start + '" data-to="' + p.end + '">' + esc(q.name) + '</button>';
        }).join('');
        return items ? '<div class="kp-quick" aria-label="Быстрый выбор">' + items + '</div>' : '';
    };

    // ------------------------------------------------------------ свой период

    Picker.prototype.renderCustom = function () {
        var t = this.typed;
        var html = '<div class="kp-typed">' +
            '<label class="kp-in-wrap"><span>С</span><input class="kp-in" data-edge="from" type="text" inputmode="numeric" ' +
            'autocomplete="off" spellcheck="false" maxlength="10" placeholder="ДД.ММ.ГГГГ" aria-label="Первый день" value="' +
            esc(t.from) + '"></label>' +
            '<label class="kp-in-wrap"><span>по</span><input class="kp-in" data-edge="to" type="text" inputmode="numeric" ' +
            'autocomplete="off" spellcheck="false" maxlength="10" placeholder="ДД.ММ.ГГГГ" aria-label="Последний день" value="' +
            esc(t.to) + '"></label>' +
            '<button type="button" class="kp-apply" data-action="apply">Показать</button></div>' +
            '<div class="kp-error" role="alert">' + esc(this.typedError) + '</div>';
        html += this.renderCalendar('range');
        return html + '<button type="button" class="kp-custom kp-cal-back" data-action="cal-close">&lsaquo; Назад</button>';
    };

    // Ошибка текстом — только когда обе даты набраны: пока человек печатает, не ругаемся. Верные
    // даты календарь показывает сразу (конец — в правом месяце), поля при этом не перерисовываются
    // и не теряют курсор.
    Picker.prototype.liveCheck = function () {
        var t = this.typed;
        var complete = function (v) { return !!K.parseTyped(v) || String(v || '').replace(/\D/g, '').length >= 8; };
        var err = (complete(t.from) && complete(t.to)) ? K.validateRange(t.from, t.to, this.rangeOpts()) : '';
        this.typedError = err || '';
        var box = this.panel.querySelector('.kp-error');
        if (box) box.textContent = this.typedError;
        var s = K.parseTyped(t.from), e = K.parseTyped(t.to);
        var cal = this.panel.querySelector('.kp-cal');
        if (!s || !e || s > e || !this.calendar || !cal) return;
        var two = this.calendar.mode === 'range' && !isPhone();
        var endMonth = new Date(e.getFullYear(), e.getMonth(), 1);
        this.calendar.month = two ? K.addMonths(endMonth, -1) : endMonth;
        this.calendar.from = null;
        this.calendar.jump = null;
        var holder = document.createElement('div');
        holder.innerHTML = this.renderCalendar('range');
        cal.parentNode.replaceChild(holder.firstChild, cal);
    };

    Picker.prototype.applyTyped = function () {
        var t = this.typed;
        var err = K.validateRange(t.from, t.to, this.rangeOpts());
        if (err) {
            this.typedError = err;
            var box = this.panel.querySelector('.kp-error');
            if (box) box.textContent = err;
            var field = this.panel.querySelector('.kp-in[data-edge="' + (K.parseTyped(t.from) ? 'to' : 'from') + '"]');
            if (field) field.focus();
            return;
        }
        this.choose(K.fromBounds(K.parseTyped(t.from), K.parseTyped(t.to)));
    };

    Picker.prototype.onInput = function (e) {
        var t = e.target;
        if (!this.typed || !t.classList || !t.classList.contains('kp-in')) return;
        var masked = K.maskTyped(t.value);
        if (masked !== t.value) t.value = masked;
        this.typed[t.dataset.edge] = t.value;
        this.liveCheck();
    };

    // Вставка «01.03.2024 – 31.10.2026» в любое поле заполняет оба.
    Picker.prototype.onPaste = function (e) {
        var t = e.target;
        if (!this.typed || !t.classList || !t.classList.contains('kp-in')) return;
        var text = e.clipboardData ? e.clipboardData.getData('text') : '';
        var range = K.parseTypedRange(text);
        if (!range) return;
        e.preventDefault();
        this.typed = { from: K.formatTyped(range[0]), to: K.formatTyped(range[1]) };
        var from = this.panel.querySelector('.kp-in[data-edge="from"]');
        var to = this.panel.querySelector('.kp-in[data-edge="to"]');
        if (from) from.value = this.typed.from;
        if (to) to.value = this.typed.to;
        this.liveCheck();
    };

    Picker.prototype.onPanelKey = function (e) {
        if (e.key === 'Enter' && this.typed && e.target.classList && e.target.classList.contains('kp-in')) {
            e.preventDefault();
            this.applyTyped();
        }
    };

    // ------------------------------------------------------------ календарь

    Picker.prototype.renderCalendar = function (mode) {
        var two = mode === 'range' && !isPhone();
        if (!this.calendar || this.calendar.mode !== mode) {
            var a = mode === 'range' ? K.fromISO(this.committed.end) : this.anchorDay();
            var max = this.maxDay();
            if (max && a > max) a = max;
            var first = new Date(a.getFullYear(), a.getMonth(), 1);
            // Два месяца: выбранный конец — в правом.
            this.calendar = { month: two ? K.addMonths(first, -1) : first, mode: mode, from: null, jump: null };
        }
        var cal = this.calendar;
        if (cal.jump !== null) return this.renderJump();
        var months = two ? [cal.month, K.addMonths(cal.month, 1)] : [cal.month];
        var last = months[months.length - 1];
        var title = months.length === 1
            ? MONTHS_FULL[cal.month.getMonth()] + ' ' + cal.month.getFullYear()
            : MONTHS_FULL[cal.month.getMonth()] + (cal.month.getFullYear() !== last.getFullYear() ? ' ' + cal.month.getFullYear() : '') +
              ' – ' + MONTHS_FULL[last.getMonth()] + ' ' + last.getFullYear();
        var html = '<div class="kp-cal" data-mode="' + cal.mode + '">';
        html += '<div class="kp-nav"><button type="button" class="kp-nav-btn" data-action="cal-back" aria-label="Предыдущий месяц">&lsaquo;</button>' +
            '<button type="button" class="kp-nav-title" data-action="jump" aria-label="Выбрать месяц и год">' + esc(title) +
            '<span class="kp-nav-caret" aria-hidden="true">&#9662;</span></button>' +
            '<button type="button" class="kp-nav-btn" data-action="cal-fwd" aria-label="Следующий месяц">&rsaquo;</button></div>';
        if (cal.mode === 'range') {
            html += '<div class="kp-cal-hint">' + (cal.from ? 'Выберите последний день' : 'Выберите первый день — или введите даты цифрами') + '</div>';
        }
        html += '<div class="kp-cals' + (months.length === 2 ? ' kp-cals--two' : '') + '">';
        for (var i = 0; i < months.length; i++) html += this.renderMonth(months[i], months.length === 2);
        return html + '</div></div>';
    };

    Picker.prototype.selection = function () {
        var cal = this.calendar;
        if (cal && cal.from) return { from: cal.from, to: null };
        if (this.typed) {
            var s = K.parseTyped(this.typed.from), e = K.parseTyped(this.typed.to);
            if (s && e && s <= e) return { from: s, to: e };
            if (s) return { from: s, to: null };
        }
        return { from: K.fromISO(this.committed.start), to: K.fromISO(this.committed.end) };
    };

    Picker.prototype.renderMonth = function (m, named) {
        var html = '<div class="kp-month">' + (named ? '<div class="kp-month-name">' + MONTHS_FULL[m.getMonth()] + ' ' +
            m.getFullYear() + '</div>' : '') + '<div class="kp-cal-grid">' + WEEKDAYS.map(function (w) {
                return '<span class="kp-cal-wd">' + w + '</span>';
            }).join('');
        var first = K.startOfWeek(m);
        var sel = this.selection();
        var fromIso = sel.from ? K.toISO(sel.from) : '', toIso = sel.to ? K.toISO(sel.to) : '';
        var max = this.maxDay(), min = this.minDay();
        for (var i = 0; i < 42; i++) {
            var day = K.addDays(first, i);
            var iso = K.toISO(day);
            var out = day.getMonth() !== m.getMonth();
            var cls = 'kp-day' + (out ? ' out' : '');
            if (!out && toIso && iso >= fromIso && iso <= toIso) cls += ' in';
            if (!out && (iso === fromIso || iso === toIso)) cls += ' edge';
            var off = (max && day > max) || (min && day < min);
            html += '<button type="button" class="' + cls + '" data-day="' + iso + '"' + (off ? ' disabled' : '') +
                (out ? ' tabindex="-1"' : '') + '>' + day.getDate() + '</button>';
        }
        return html + '</div></div>';
    };

    // Сетка месяцев года — прыжок календаря на 2023 год в два нажатия.
    Picker.prototype.renderJump = function () {
        var y = this.calendar.jump;
        var min = this.minDay(), max = this.maxDay();
        var html = '<div class="kp-jump"><div class="kp-nav">' +
            '<button type="button" class="kp-nav-btn" data-action="jump-year-back" aria-label="Предыдущий год"' +
            (min && y <= min.getFullYear() ? ' disabled' : '') + '>&lsaquo;</button><span>' + y + '</span>' +
            '<button type="button" class="kp-nav-btn" data-action="jump-year-fwd" aria-label="Следующий год"' +
            (max && y >= max.getFullYear() ? ' disabled' : '') + '>&rsaquo;</button></div>' +
            '<div class="kp-grid kp-grid--month">';
        for (var i = 0; i < 12; i++) {
            var start = new Date(y, i, 1), end = new Date(y, i, K.daysInMonth(y, i));
            var off = (max && start > max) || (min && end < min);
            html += '<button type="button" class="kp-cell" data-jump-month="' + i + '"' + (off ? ' disabled' : '') + '>' +
                MONTHS_FULL[i] + '</button>';
        }
        return html + '</div><button type="button" class="kp-custom kp-cal-back" data-action="jump-close">&lsaquo; К календарю</button></div>';
    };

    // ------------------------------------------------------------ клики в панели

    Picker.prototype.onPanelClick = function (e) {
        // Панель перерисовывается по клику, и цель клика исчезает из документа раньше, чем
        // событие дойдёт до document: проверка «клик вне элемента» закрыла бы панель.
        e.stopPropagation();
        var t = e.target.closest('button');
        if (!t || t.disabled) return;
        var action = t.dataset.action;
        if (t.dataset.step) {
            this.panelStep = t.dataset.step;
            this.cursor = null;
            this.calendar = null;
            this.typed = null;
            this.renderPanel();
            return;
        }
        if (t.dataset.from) {
            this.choose(K.fromBounds(K.fromISO(t.dataset.from), K.fromISO(t.dataset.to)));
            return;
        }
        if (t.dataset.day) {
            this.onDay(K.fromISO(t.dataset.day));
            return;
        }
        if (t.dataset.jumpMonth !== undefined) {
            var m = new Date(this.calendar.jump, Number(t.dataset.jumpMonth), 1);
            this.calendar.month = m;
            this.calendar.jump = null;
            this.renderPanel();
            return;
        }
        if (action === 'custom') {
            this.enterCustom();
            this.renderPanel();
            var field = this.panel.querySelector('.kp-in[data-edge="from"]');
            if (field && !isPhone()) field.focus();
        } else if (action === 'apply') {
            this.applyTyped();
        } else if (action === 'reset') {
            this.close();
            this.opts.onReset();
        } else if (action === 'cal-close') {
            this.calendar = null;
            this.typed = null;
            this.renderPanel();
        } else if (action === 'cal-back' || action === 'cal-fwd') {
            this.calendar.month = K.addMonths(this.calendar.month, action === 'cal-back' ? -1 : 1);
            this.renderPanel();
        } else if (action === 'jump') {
            this.calendar.jump = this.calendar.month.getFullYear();
            this.renderPanel();
        } else if (action === 'jump-year-back' || action === 'jump-year-fwd') {
            this.calendar.jump += action === 'jump-year-back' ? -1 : 1;
            this.renderPanel();
        } else if (action === 'jump-close') {
            this.calendar.jump = null;
            this.renderPanel();
        } else if (action === 'year-back' || action === 'year-fwd') {
            var y = this.cursor ? Number(this.cursor) : this.anchorDay().getFullYear();
            this.cursor = String(y + (action === 'year-back' ? -1 : 1));
            this.renderPanel();
        } else if (action === 'weeks-back' || action === 'weeks-fwd') {
            var end = this.cursor ? K.fromISO(this.cursor) : K.startOfWeek(this.anchorDay());
            this.cursor = K.toISO(K.addDays(end, (action === 'weeks-back' ? -7 : 7) * WEEKS_PER_PAGE));
            this.renderPanel();
        }
    };

    Picker.prototype.onDay = function (day) {
        var cal = this.calendar;
        if (!cal || cal.mode === 'single') {
            this.choose(K.periodFor('day', day));
            return;
        }
        if (!cal.from) {
            cal.from = day;
            this.typed = { from: K.formatTyped(day), to: '' };
            this.typedError = '';
            this.renderPanel();
            return;
        }
        var a = cal.from, b = day;
        if (b < a) { var swap = a; a = b; b = swap; }
        cal.from = null;
        this.typed = { from: K.formatTyped(a), to: K.formatTyped(b) };
        var err = K.validateRange(this.typed.from, this.typed.to, this.rangeOpts());
        if (err) {
            this.typedError = err;
            this.renderPanel();
            return;
        }
        this.choose(K.fromBounds(a, b));
    };

    Picker.prototype.choose = function (period) {
        if (!this.allows(period)) {
            this.stepNoteFlash('Такой период здесь недоступен' + (this.stepNote ? ': ' + this.stepNote : ''));
            return;
        }
        this.close();
        this.pick(period, true);
        this.trigger.focus();
    };

    Picker.prototype.stepNoteFlash = function (text) {
        var note = this.panel.querySelector('.kp-note');
        if (!note) {
            note = document.createElement('div');
            note.className = 'kp-note';
            this.panel.insertBefore(note, this.panel.firstChild.nextSibling);
        }
        note.textContent = text;
    };

    // ------------------------------------------------------------ клавиши

    Picker.prototype.bindKeys = function () {
        var self = this;
        this.keys = function (e) {
            if (self.opts.disabled) return;
            if (e.key === 'Escape' && self.open) {
                self.close();
                self.trigger.focus();
                return;
            }
            if (self.open || e.altKey || e.ctrlKey || e.metaKey) return;
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            var t = e.target, tag = t && t.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) return;
            // Скрытый элемент (вкладка без периода) клавиши не забирает.
            if (!self.root.offsetParent) return;
            e.preventDefault();
            self.navigate(e.key === 'ArrowLeft' ? -1 : 1);   // те же ограничения, что у стрелок
        };
        document.addEventListener('keydown', this.keys);
    };

    Picker.prototype.destroy = function () {
        clearTimeout(this.timer);
        clearTimeout(this.slideTimer);
        document.removeEventListener('keydown', this.keys);
        if (this.outside) document.removeEventListener('click', this.outside);
        this.root.innerHTML = '';
        this.root.classList.remove('kp', 'kp--strip', 'kp--open', 'kp--partial', 'kp--disabled',
            'kp--slide-prev', 'kp--slide-next');
    };

    root.KPeriodPicker = {
        mount: function (container, opts) { return new Picker(container, opts); }
    };
})(typeof window !== 'undefined' ? window : globalThis);

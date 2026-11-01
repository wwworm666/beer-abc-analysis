/**
 * Элемент «Период» — один на сайте (docs/period-standard.md, раздел 4). Основа — шапка дашборда.
 *
 *   [‹]  [календарь  Октябрь 2026  идёт, по 29.10  ▾]  [›]
 *
 * Название всегда с годом, неполный период подписан текстом (не только подсказкой при
 * наведении). Стрелки шагают на период текущего шага и выключены на границах данных;
 * клавиши ← → ведут себя как стрелки. По нажатию на название — панель (на телефоне — лист
 * снизу): шаг, сетка периодов шага, быстрый выбор, «Свой период» (календарь внутри панели,
 * без внешних библиотек), свежесть данных.
 *
 * Арифметика дат — static/js/shared/period/period_core.js (window.KPeriod), здесь только DOM.
 *
 *   var picker = KPeriodPicker.mount(container, {
 *       steps: ['day', 'week', 'month', 'quarter', 'year', 'custom'],
 *       quick: ['last_closed_week', 'current_week', 'last_closed_month', 'current_month'],
 *       value: KPeriod.lastClosed('week'),
 *       allowFuture: false,       // страницы планирования — true
 *       urlSync: true,            // ?date_from=&date_to= в адресе
 *       freshness: 'Данные по 31.10',
 *       onChange: function (period) { ... }
 *   });
 *   picker.get(); picker.set(period, {silent: true}); picker.setSteps(['month', 'year'], 'причина');
 */
(function (root) {
    'use strict';

    var K = root.KPeriod;
    var STEP_NAMES = { day: 'День', week: 'Неделя', month: 'Месяц', quarter: 'Квартал', year: 'Год' };
    var WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    var MONTHS_FULL = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август',
        'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    var WEEKS_PER_PAGE = 10;
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

    function Picker(container, opts) {
        this.root = container;
        this.opts = opts || {};
        this.steps = (this.opts.steps || ['day', 'week', 'month', 'quarter', 'year', 'custom']).slice();
        this.stepNote = '';
        this.quick = this.opts.quick || [];
        this.committed = this.opts.value || K.lastClosed('week');
        this.view = this.committed;     // показан в шапке, ещё не применён (стрелки)
        this.timer = null;
        this.open = false;
        this.panelStep = null;          // шаг, выбранный в панели
        this.cursor = null;             // год сетки месяцев/кварталов или конец списка недель
        this.calendar = null;           // {month: Date, mode: 'single'|'range', from: Date|null}
        this.build();
        this.render();
        this.bindKeys();
    }

    Picker.prototype.build = function () {
        this.root.classList.add('kp');
        if (this.opts.variant === 'strip') this.root.classList.add('kp--strip');
        this.root.innerHTML =
            '<button type="button" class="kp-arrow kp-prev" aria-label="Предыдущий период">' + ICON_PREV + '</button>' +
            '<button type="button" class="kp-trigger" aria-haspopup="dialog" aria-expanded="false">' + ICON_CAL +
            '<span class="kp-title"></span><span class="kp-sub"></span>' + ICON_CARET + '</button>' +
            '<button type="button" class="kp-arrow kp-next" aria-label="Следующий период">' + ICON_NEXT + '</button>' +
            '<div class="kp-backdrop" hidden></div>' +
            '<div class="kp-panel" role="dialog" aria-label="Выбор периода" hidden></div>';
        this.btnPrev = this.root.querySelector('.kp-prev');
        this.btnNext = this.root.querySelector('.kp-next');
        this.trigger = this.root.querySelector('.kp-trigger');
        this.titleEl = this.root.querySelector('.kp-title');
        this.subEl = this.root.querySelector('.kp-sub');
        this.backdrop = this.root.querySelector('.kp-backdrop');
        this.panel = this.root.querySelector('.kp-panel');
        var self = this;
        this.btnPrev.addEventListener('click', function () { self.navigate(-1); });
        this.btnNext.addEventListener('click', function () { self.navigate(1); });
        this.trigger.addEventListener('click', function () { self.toggle(); });
        this.backdrop.addEventListener('click', function () { self.close(); });
        this.panel.addEventListener('click', function (e) { self.onPanelClick(e); });
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
        var next = K.shiftPeriod(this.view, dir);
        if (this.isDisabled(next)) return;
        this.pick(next, false);
    };

    // Шаги, доступные странице (вкладке). note — видимая причина, почему других нет.
    Picker.prototype.setSteps = function (steps, note) {
        this.steps = steps.slice();
        this.stepNote = note || '';
        if (this.open) this.renderPanel();
    };

    // ------------------------------------------------------------ шапка

    Picker.prototype.render = function () {
        var p = this.view;
        this.titleEl.textContent = K.periodTitle(p);
        var sub = K.periodSub(p);
        this.subEl.textContent = sub;
        this.subEl.hidden = !sub;
        this.root.classList.toggle('kp--partial', K.periodState(p) === 'partial');
        this.btnPrev.disabled = this.isDisabled(K.shiftPeriod(p, -1));
        this.btnNext.disabled = this.isDisabled(K.shiftPeriod(p, 1));
    };

    // ------------------------------------------------------------ панель

    Picker.prototype.toggle = function () { if (this.open) this.close(); else this.openPanel(); };

    Picker.prototype.openPanel = function () {
        this.open = true;
        var g = this.view.granularity;
        this.panelStep = (g !== K.CUSTOM && this.steps.indexOf(g) >= 0) ? g : this.firstStep();
        this.cursor = null;
        this.calendar = null;
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

    Picker.prototype.renderPanel = function () {
        var html = '<span class="kp-grab" aria-hidden="true"></span>';
        var visibleSteps = this.steps.filter(function (s) { return s !== K.CUSTOM; });
        var custom = !!(this.calendar && this.calendar.mode === 'range');
        if (visibleSteps.length > 1) {
            html += '<div class="kp-steps" role="group" aria-label="Шаг">' + visibleSteps.map(function (s) {
                return '<button type="button" class="kp-step' + (s === this.panelStep && !custom ? ' active' : '') +
                    '" data-step="' + s + '">' + STEP_NAMES[s] + '</button>';
            }, this).join('') + '</div>';
        }
        if (this.stepNote) html += '<div class="kp-note">' + esc(this.stepNote) + '</div>';
        if (custom) {
            html += this.renderCalendar();
        } else {
            html += this.renderGrid();
            html += this.renderQuick();
            if (this.steps.indexOf(K.CUSTOM) >= 0) {
                html += '<button type="button" class="kp-custom" data-action="custom">Свой период<span aria-hidden="true">&rsaquo;</span></button>';
            }
        }
        var fresh = typeof this.opts.freshness === 'function' ? this.opts.freshness() : this.opts.freshness;
        if (fresh) html += '<div class="kp-fresh">' + esc(fresh) + '</div>';
        this.panel.innerHTML = html;
    };

    Picker.prototype.item = function (p, label, extra) {
        var cls = 'kp-cell' + (samePeriod(p, this.committed) ? ' active' : '') +
            (K.periodState(p) === 'partial' ? ' partial' : '');
        var disabled = this.isDisabled(p);
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
                var sub = K.periodSub(w);
                html += this.item(w, K.periodTitle(w), sub);
            }
            return html + '</div>';
        }
        if (step === 'month' || step === 'quarter') {
            var year = this.cursor ? Number(this.cursor) : this.anchorDay().getFullYear();
            html += '<div class="kp-nav"><button type="button" class="kp-nav-btn" data-action="year-back" aria-label="Предыдущий год">&lsaquo;</button>' +
                '<span>' + year + '</span><button type="button" class="kp-nav-btn" data-action="year-fwd" aria-label="Следующий год">&rsaquo;</button></div>';
            html += '<div class="kp-grid kp-grid--' + step + '">';
            var n = step === 'month' ? 12 : 4;
            for (i = 0; i < n; i++) {
                var p = K.periodFor(step, new Date(year, step === 'month' ? i : i * 3, 1));
                html += this.item(p, step === 'month' ? MONTHS_FULL[i] : K.QUARTER_ROMAN[i] + ' квартал',
                    K.periodState(p) === 'partial' ? 'идёт' : '');
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
            if (!q) return '';
            var p = q.build();
            if (!self.allows(p) || self.isDisabled(p)) return '';
            return '<button type="button" class="kp-chip' + (samePeriod(p, self.committed) ? ' active' : '') +
                '" data-from="' + p.start + '" data-to="' + p.end + '">' + esc(q.name) + '</button>';
        }).join('');
        return items ? '<div class="kp-quick" aria-label="Быстрый выбор">' + items + '</div>' : '';
    };

    // ------------------------------------------------------------ календарь

    Picker.prototype.renderCalendar = function (mode) {
        if (!this.calendar) {
            var a = this.anchorDay();
            this.calendar = { month: new Date(a.getFullYear(), a.getMonth(), 1), mode: mode || 'range', from: null };
        }
        var cal = this.calendar;
        var m = cal.month;
        var html = '<div class="kp-cal" data-mode="' + cal.mode + '">';
        html += '<div class="kp-nav"><button type="button" class="kp-nav-btn" data-action="cal-back" aria-label="Предыдущий месяц">&lsaquo;</button>' +
            '<span>' + MONTHS_FULL[m.getMonth()] + ' ' + m.getFullYear() + '</span>' +
            '<button type="button" class="kp-nav-btn" data-action="cal-fwd" aria-label="Следующий месяц">&rsaquo;</button></div>';
        if (cal.mode === 'range') {
            html += '<div class="kp-cal-hint">' + (cal.from ? 'Выберите последний день' : 'Выберите первый день') + '</div>';
        }
        html += '<div class="kp-cal-grid">' + WEEKDAYS.map(function (w) {
            return '<span class="kp-cal-wd">' + w + '</span>';
        }).join('');
        var first = K.startOfWeek(m);
        var selFrom = cal.from || K.fromISO(this.committed.start);
        var selTo = cal.from ? null : K.fromISO(this.committed.end);
        var max = this.maxDay(), min = this.minDay();
        for (var i = 0; i < 42; i++) {
            var day = K.addDays(first, i);
            var iso = K.toISO(day);
            var cls = 'kp-day' + (day.getMonth() !== m.getMonth() ? ' out' : '');
            if (selTo && day >= selFrom && day <= selTo) cls += ' in';
            if (K.toISO(selFrom) === iso || (selTo && K.toISO(selTo) === iso)) cls += ' edge';
            var off = (max && day > max) || (min && day < min);
            html += '<button type="button" class="' + cls + '" data-day="' + iso + '"' + (off ? ' disabled' : '') +
                '>' + day.getDate() + '</button>';
        }
        html += '</div>';
        html += '<button type="button" class="kp-custom kp-cal-back" data-action="cal-close">&lsaquo; Назад</button></div>';
        return html;
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
        if (action === 'custom') {
            this.calendar = null;
            this.renderCalendarInPanel('range');
        } else if (action === 'cal-close') {
            this.calendar = null;
            this.renderPanel();
        } else if (action === 'cal-back' || action === 'cal-fwd') {
            this.calendar.month = K.addMonths(this.calendar.month, action === 'cal-back' ? -1 : 1);
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

    Picker.prototype.renderCalendarInPanel = function (mode) {
        var a = this.anchorDay();
        this.calendar = { month: new Date(a.getFullYear(), a.getMonth(), 1), mode: mode, from: null };
        this.renderPanel();
    };

    Picker.prototype.onDay = function (day) {
        var cal = this.calendar;
        if (!cal || cal.mode === 'single') {
            this.choose(K.periodFor('day', day));
            return;
        }
        if (!cal.from) {
            cal.from = day;
            this.renderPanel();
            return;
        }
        var period = K.periodFromSelection(cal.from, day, null);
        cal.from = null;
        this.choose(period);
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
        document.removeEventListener('keydown', this.keys);
        document.removeEventListener('click', this.outside);
        this.root.innerHTML = '';
        this.root.classList.remove('kp', 'kp--strip', 'kp--open', 'kp--partial');
    };

    root.KPeriodPicker = {
        mount: function (container, opts) { return new Picker(container, opts); }
    };
})(typeof window !== 'undefined' ? window : globalThis);

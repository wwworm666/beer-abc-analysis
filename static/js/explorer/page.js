/* Конструктор отчётов (/explorer) — конструктор OLAP-отчётов iiko в сервисе.

   Что делает страница: пользователь собирает отчёт как в iikoOffice — тип отчёта,
   поля в «Строки», «Столбцы», «Показатели» и «Фильтры» (перетаскиванием или кнопками), —
   и сервер строит сводную по данным iiko (POST /api/explorer/report, format=pivot).
   Отчёт строится сам (с 2026-11-01, ответ владельца Р5): сразу при открытии, через
   секунду после правки полей и фильтров, через 350 мс после смены бара или периода.
   Кнопки «Построить» нет; после ошибки в карточке сообщения — «Повторить».

   Бар и период — общая полоса сайта «Бар и период» (window.KStrip, план единого
   виджета docs/planning/period-widget-rollout.md, этап 3): своего меню периода нет,
   в запрос идут date_from/date_to полосы. Бар из полосы становится фильтром отчёта
   по полю бара его типа (boot.bar_fields = core/olap_catalog.BAR_FIELD: Store.Name у
   продаж, Account.Name у проводок); свой фильтр отчёта по этому полю сильнее; у типа
   без поля бара отчёт строится по всей сети, и это подписано. Открытый сохранённый
   отчёт делает свой период общим выбором (KStrip.setPeriod).

   Каталог полей — живой список iiko (GET /api/explorer/columns). Отчёт можно выгрузить
   в Excel, сохранить в сервисе и открыть снова, а также открыть отчёт, сохранённый в
   iikoOffice.

   Числа на клиенте не считаются (см. static/js/explorer/grid.js): итоги приходят с
   сервера. Страница всегда шлёт include_deleted=true, а фильтры «не удалено» показывает
   обычными фишками (их добавляет шаблон нового отчёта о продажах, как в iikoOffice) —
   так видно, что именно отфильтровано, и фильтр можно снять.

   Черновик отчёта (последняя раскладка) помнится в localStorage этого браузера —
   только удобство: без него страница открывается с отчётом по умолчанию. Периода в
   черновике нет (с 2026-11-01): период — общий выбор полосы.
*/
(function () {
    'use strict';

    var boot = JSON.parse(document.getElementById('exBoot').textContent || '{}');
    var Grid = window.ExplorerGrid;
    var Cube = window.ExplorerCube;   // куб OLAP — схема раскладки (static/js/explorer/cube.js)
    var LS_KEY = 'explorer.draft.v1';
    var ZONES = ['rows', 'columns', 'measures'];
    var ZONE_TITLES = { rows: 'строки', columns: 'столбцы', measures: 'показатели', filters: 'фильтры' };
    var TYPE_BADGES = {
        DATE: 'дата', DATETIME: 'время', MONEY: '₽', AMOUNT: 'кол.', PERCENT: '%', INTEGER: 'число',
        ENUM: 'список', STRING: 'текст', ID: 'id', ID_STRING: 'id', DURATION_IN_SECONDS: 'длит.',
        OBJECT: 'объект'
    };
    // Раскрывать все группы, пока листьев не больше этого: иначе — только верхний уровень.
    var OPEN_ALL_MAX_LEAVES = 1500;
    // Строк таблицы за раз: DOM на десятках тысяч строк заметно тормозит.
    var ROWS_STEP = 2000;
    // Пауза перед построением (ответ владельца Р5 — «считать сразу, без кнопок»): серия правок
    // полей и фильтров — одно построение через секунду; смена бара или периода — через 350 мс.
    var EDIT_PAUSE_MS = 1000;
    var STRIP_PAUSE_MS = 350;
    // Пресеты сервера «текущего» периода: у сервера они по сегодня (this_week — пн..сегодня), у
    // полосы — целые неделя, месяц, год с пометкой «идёт». Совпадают по началу и шагу.
    var CURRENT_PRESETS = { this_week: 'week', this_month: 'month', this_year: 'year' };
    // Без полосы (её скрипты не загрузились) — прошлая неделя пресетом сервера, как раньше.
    var FALLBACK_PRESET = 'last_week';
    var K = window.KPeriod || null;
    var Strip = window.KStrip || null;

    var state = {
        type: 'SALES',
        catalogs: {},
        rows: [], columns: [], measures: [], filters: [],
        saved: null,             // {id, name} — открытый сохранённый отчёт
        origin: null,            // подпись «откуда отчёт» (iikoOffice)
        result: null,
        resultKey: null,
        building: false,
        rebuild: false,          // построить заново сразу после текущего построения
        buildTimer: null,        // отложенное построение (пауза после правки или выбора в полосе)
        unfold: false,           // свежий ответ: строки таблицы «ложатся» из куба
        shares: 'none',
        sort: null,
        expanded: {},
        defaultOpen: true,
        maxRows: ROWS_STEP,
        search: '',
        openGroups: {},
        pendingZone: null,       // телефон: зона, для которой открыт лист полей
        drag: null
    };
    var el = {};

    // ==================== мелочи ====================

    function esc(text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function $(id) { return document.getElementById(id); }
    function plural(n, one, few, many) {
        var abs = Math.abs(Math.round(n)) % 100;
        var tail = abs % 10;
        if (abs > 10 && abs < 20) return many;
        if (tail > 1 && tail < 5) return few;
        if (tail === 1) return one;
        return many;
    }
    function ruDate(iso) {
        if (!iso) return '';
        var p = String(iso).split('-');
        return p[2] + '.' + p[1] + '.' + p[0];
    }
    function isNarrow() { return window.matchMedia('(max-width: 900px)').matches; }

    var toastTimer = null;
    function toast(text, ms) {
        el.toast.textContent = text;
        el.toast.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { el.toast.hidden = true; }, ms || 3800);
    }

    function api(method, url, body) {
        var init = { method: method, headers: { 'Accept': 'application/json' }, credentials: 'same-origin' };
        if (body !== undefined) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(body);
        }
        return fetch(url, init).then(function (response) {
            return response.text().then(function (text) {
                var data = null;
                try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
                if (!response.ok) {
                    var error = new Error((data && data.error) ||
                        ('Сервер ответил ' + response.status + (text && !data ? ': ' + text.slice(0, 200) : '')));
                    error.code = data && data.code;
                    error.status = response.status;
                    error.data = data;
                    throw error;
                }
                return data;
            });
        });
    }

    // ==================== каталог полей ====================

    function catalog() { return state.catalogs[state.type] || null; }
    function fieldOf(id) {
        var cat = catalog();
        return cat ? cat.byId[id] || null : null;
    }
    function fieldName(id) {
        var f = fieldOf(id);
        return f ? f.name : id;
    }

    function loadCatalog(type) {
        if (state.catalogs[type]) return Promise.resolve(state.catalogs[type]);
        if (type === state.type) {
            el.fieldList.innerHTML = '<div class="ex-empty-list">Загружаю список полей из iiko…</div>';
        }
        return api('GET', '/api/explorer/columns?report_type=' + encodeURIComponent(type))
            .then(function (data) {
                data.byId = {};
                data.fields.forEach(function (f) { data.byId[f.id] = f; });
                state.catalogs[type] = data;
                return data;
            });
    }

    // ==================== конфигурация ====================

    function guardFilters(type) {
        if ((boot.guarded_types || []).indexOf(type) < 0) return [];
        return JSON.parse(JSON.stringify(boot.guard_filters || []));
    }

    // ---- период: общий выбор полосы «Бар и период» ----

    function presetRow(id) {
        return (boot.periods || []).filter(function (p) { return p.id === id; })[0] || null;
    }
    // Период запроса: {from, to, title, period}. Полоса есть — её период; нет — запасной пресет.
    function periodDates() {
        var p = Strip ? Strip.get().period : null;
        if (p) return { from: p.start, to: p.end, period: p, title: K ? K.periodTitle(p) : ruDate(p.start) + ' — ' + ruDate(p.end) };
        var row = presetRow(FALLBACK_PRESET);
        return row ? { from: row.date_from, to: row.date_to, title: row.title, preset: FALLBACK_PRESET } : null;
    }
    // Пресет сервера с теми же датами: так сохранённый отчёт «Прошлая неделя» остаётся
    // относительным — при открытии даты пересчитаются (пресеты — синонимы быстрого выбора).
    function presetOf(dates) {
        if (!dates) return null;
        if (dates.preset) return dates.preset;
        var rows = boot.periods || [];
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            if (row.date_from !== dates.from) continue;
            // Те же даты — тот же пресет («С начала года» = this_year); «текущий» пресет — ещё и
            // целая неделя, месяц или год полосы с тем же началом.
            var step = CURRENT_PRESETS[row.id];
            if (row.date_to === dates.to || (step && dates.period && dates.period.granularity === step)) return row.id;
        }
        return null;
    }
    // Период сохранённого отчёта -> период полосы. Пресет — даты на сегодня из таблицы сервера;
    // «текущий» пресет — целый период шага (неделя пн–вс «идёт, по …»), как его рисует полоса.
    function stripPeriodOf(p) {
        if (!p || !K) return null;
        if (p.preset) {
            var row = presetRow(p.preset);
            if (!row) return null;
            if (CURRENT_PRESETS[p.preset]) return K.currentPeriod(CURRENT_PRESETS[p.preset]);
            return K.fromBounds(K.fromISO(row.date_from), K.fromISO(row.date_to));
        }
        var from = K.fromISO(String(p.from || '').slice(0, 10)), to = K.fromISO(String(p.to || '').slice(0, 10));
        return from && to && from <= to ? K.fromBounds(from, to) : null;
    }
    // Открыт сохранённый отчёт (или отчёт iikoOffice со своим периодом): его период становится
    // общим выбором сайта — как выбор в полосе (сохраняется на час и пишется в адрес).
    function applyReportPeriod(p) {
        var next = stripPeriodOf(p);
        if (!next || !Strip || !Strip.setPeriod) return;
        var cur = Strip.get().period;
        if (cur && cur.start === next.start && cur.end === next.end) return;
        Strip.setPeriod(next);
    }

    // ---- бар: фильтр отчёта по полю бара его типа ----

    // {state: 'all' | 'applied' | 'own' | 'network', label, field, fieldName, value}
    //   all — в полосе «Все бары»; applied — фильтр бара уйдёт в запрос; own — в отчёте свой
    //   фильтр по полю бара (он сильнее полосы); network — у типа отчёта поля бара нет.
    function barScope() {
        var bar = Strip ? Strip.get().bar : '';
        if (!bar) return { state: 'all' };
        var info = (Strip.barInfo && Strip.barInfo(bar)) || {};
        var label = info.name || bar;
        var field = (boot.bar_fields || {})[state.type] || null;
        var cat = catalog();
        var f = field && cat ? cat.byId[field] : null;
        if (!field || (cat && (!f || f.blocked || f.filter_op !== 'values'))) return { state: 'network', label: label };
        var fieldName = f ? f.name : field;
        if (state.filters.some(function (flt) { return flt.field === field; })) {
            return { state: 'own', label: label, field: field, fieldName: fieldName };
        }
        return { state: 'applied', label: label, field: field, fieldName: fieldName, value: info.iiko_name || label };
    }

    // Раскладка отчёта без периода: её помнит черновик (период — общий выбор полосы).
    function layoutConfig() {
        return {
            report_type: state.type,
            rows: state.rows.slice(),
            columns: state.columns.slice(),
            measures: state.measures.slice(),
            filters: JSON.parse(JSON.stringify(state.filters)),
            include_deleted: true
        };
    }
    // Заявка для сохранения отчёта: раскладка и период полосы — пресетом, если даты совпали с
    // пресетом сервера, иначе датами. Бар полосы не сохраняется: он общий выбор сайта.
    function currentConfig() {
        var config = layoutConfig();
        var dates = periodDates() || {};
        var preset = presetOf(dates);
        config.period = preset ? { preset: preset } : { from: dates.from, to: dates.to };
        return config;
    }

    // Заявка запроса: фильтр бара из полосы добавляется к фильтрам отчёта (в черновик и
    // сохранённый отчёт он не попадает), период — даты полосы.
    function requestPayload(format) {
        var bar = barScope();
        var filters = state.filters.slice();
        if (bar.state === 'applied') filters.push({ field: bar.field, op: 'in', values: [bar.value] });
        var payload = {
            report_type: state.type,
            rows: state.rows, columns: state.columns, measures: state.measures,
            filters: filters, include_deleted: true
        };
        if (format) payload.format = format;
        var dates = periodDates() || {};
        if (dates.preset) payload.period = dates.preset;
        else { payload.date_from = dates.from; payload.date_to = dates.to; }
        return payload;
    }

    // Что построено: раскладка, период и бар. Сменилось — отчёт устарел и перестроится.
    function configKey() { return JSON.stringify(requestPayload('pivot')); }

    function persist() {
        try {
            localStorage.setItem(LS_KEY, JSON.stringify({ config: layoutConfig(), saved: state.saved }));
        } catch (e) { /* приватный режим или запрет хранилища: черновик просто не запомнится */ }
    }
    function restoreDraft() {
        try {
            var raw = localStorage.getItem(LS_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    // Применить конфигурацию (сохранённый отчёт, отчёт iikoOffice, черновик).
    // Поля, которых нет в каталоге этого сервера, отбрасываются с пояснением.
    function applyConfig(config, meta) {
        var type = String(config.report_type || 'SALES').toUpperCase();
        var known = (boot.report_types || []).some(function (t) { return t.id === type; });
        if (!known) {
            toast('Тип отчёта «' + type + '» конструктор не строит.');
            return Promise.resolve(false);
        }
        state.type = type;
        return loadCatalog(type).then(function (cat) {
            var dropped = [];
            function keep(list, test) {
                return (list || []).filter(function (id) {
                    var f = cat.byId[id];
                    var ok = f && !f.blocked && test(f);
                    if (!ok) dropped.push((f && f.name) || id);
                    return ok;
                });
            }
            state.rows = keep(config.rows, function (f) { return f.group; });
            state.columns = keep(config.columns, function (f) { return f.group && state.rows.indexOf(f.id) < 0; });
            state.measures = keep(config.measures, function (f) {
                return f.agg && state.rows.indexOf(f.id) < 0 && state.columns.indexOf(f.id) < 0;
            });
            state.filters = (config.filters || []).filter(function (flt) {
                var f = cat.byId[flt.field];
                var ok = f && !f.blocked && f.filter_op;
                if (!ok) dropped.push((f && f.name) || flt.field);
                return ok;
            });
            // Без include_deleted=true (отчёт, сохранённый агентом) «не удалено» ставит сервер
            // сам (ReportSpec.guards). Страница всегда шлёт true — поэтому те же фильтры
            // становятся фишками, иначе цифры на странице разошлись бы с цифрами агента.
            if (config.include_deleted !== true) {
                var own = {};
                state.filters.forEach(function (flt) { own[flt.field] = true; });
                guardFilters(type).forEach(function (guard) {
                    if (!own[guard.field] && cat.byId[guard.field]) state.filters.push(guard);
                });
            }
            // Период отчёта сюда не относится: сохранённый отчёт делает его общим выбором
            // (applyReportPeriod), черновик периода не хранит.
            state.saved = meta && meta.saved ? meta.saved : null;
            state.origin = meta && meta.origin ? meta.origin : null;
            state.search = '';
            el.fieldSearch.value = '';
            renderAll();
            persist();
            if (dropped.length) {
                toast('Не перенесены поля, которых нет в каталоге iiko или которые недоступны: ' +
                      dropped.join(', ') + '.', 7000);
            }
            return true;
        });
    }

    // ==================== панель полей ====================

    function usedIds() {
        var used = {};
        state.rows.concat(state.columns, state.measures).forEach(function (id) { used[id] = true; });
        state.filters.forEach(function (f) { used[f.field] = true; });
        return used;
    }

    function fieldButton(f, used) {
        var badge = TYPE_BADGES[f.type] || f.type.toLowerCase();
        var hint = f.blocked ? 'недоступно' : (f.hint || '');
        return '<button type="button" class="ex-field' + (used[f.id] ? ' is-used' : '') +
            (f.blocked ? ' is-blocked' : '') + '" data-id="' + esc(f.id) + '"' +
            (f.blocked ? '' : ' draggable="true"') + ' title="' + esc(f.name + ' · ' + f.id) + '">' +
            '<span class="ex-field-n">' + esc(f.name) +
            (hint ? '<span class="ex-field-h">' + esc(hint) + '</span>' : '') + '</span>' +
            '<span class="ex-field-t">' + esc(badge) + (f.agg ? ' Σ' : '') + '</span></button>';
    }

    function renderFields() {
        var cat = catalog();
        if (!cat) return;
        var used = usedIds();
        el.fieldsSrc.textContent = cat.field_count + ' ' + plural(cat.field_count, 'поле', 'поля', 'полей') +
            (cat.source !== 'live' ? ' · запасная копия' : '');
        el.fieldsSrc.title = cat.source !== 'live'
            ? 'iiko не отдал живой список полей (' + (cat.live_error || '') + '). Показана копия от ' + cat.fetched_at + '.'
            : 'Живой список полей iiko на ' + cat.fetched_at;
        var query = state.search.trim().toLowerCase();
        var html = '';
        if (query) {
            var found = cat.fields.filter(function (f) {
                return f.name.toLowerCase().indexOf(query) >= 0 || f.id.toLowerCase().indexOf(query) >= 0 ||
                    (f.tags || []).some(function (t) { return t.toLowerCase().indexOf(query) >= 0; });
            });
            html = found.length
                ? found.map(function (f) { return fieldButton(f, used); }).join('')
                : '<div class="ex-empty-list">Ничего не найдено. Ищется по названию, id поля и категории.</div>';
        } else {
            (cat.groups || []).forEach(function (group, index) {
                var open = Object.prototype.hasOwnProperty.call(state.openGroups, group.title)
                    ? state.openGroups[group.title] : index === 0;
                html += '<details class="ex-group" data-group="' + esc(group.title) + '"' + (open ? ' open' : '') + '>' +
                    '<summary>' + esc(group.title) + '<span class="ex-group-n">' + group.ids.length + '</span></summary>' +
                    group.ids.map(function (id) { return fieldButton(cat.byId[id], used); }).join('') + '</details>';
            });
        }
        el.fieldList.innerHTML = html;
    }

    // ==================== зоны ====================

    function filterSummary(flt) {
        var f = fieldOf(flt.field);
        if (flt.op === 'in' || flt.op === 'not_in') {
            var labels = (flt.values || []).map(function (v) {
                return v === null ? '(пусто)' : Grid.fmtDimText(v, f);
            });
            var text = labels.slice(0, 2).join(', ') + (labels.length > 2 ? ' +' + (labels.length - 2) : '');
            return (flt.op === 'not_in' ? 'кроме ' : '') + text;
        }
        var from = flt.op === 'date_range' ? Grid.isoDate(flt.from) : flt.from;
        var to = flt.op === 'date_range' ? Grid.isoDate(flt.to) : flt.to;
        return 'от ' + from + ' до ' + to;
    }

    function chip(zone, id, index, count) {
        var f = fieldOf(id);
        var name = f ? f.name : id;
        var title = name;
        if (zone === 'measures' && f) {
            title += f.kind === 'sum' ? ' — итоги сложением строк' : ' — итоги считает iiko (не складываются)';
        }
        return '<span class="ex-chip" draggable="true" data-zone="' + zone + '" data-index="' + index + '" data-id="' +
            esc(id) + '" title="' + esc(title) + '"><span class="ex-chip-t">' + esc(name) + '</span>' +
            (index > 0 ? '<button type="button" data-act="left" aria-label="Левее">‹</button>' : '') +
            (index < count - 1 ? '<button type="button" data-act="right" aria-label="Правее">›</button>' : '') +
            '<button type="button" data-act="remove" aria-label="Убрать">×</button></span>';
    }

    function renderZones() {
        var limits = boot.limits || {};
        ZONES.forEach(function (zone) {
            var list = state[zone];
            var body = el.zoneBody[zone];
            body.innerHTML = list.length
                ? list.map(function (id, i) { return chip(zone, id, i, list.length); }).join('')
                : '<span class="ex-zone-hint">' + (zone === 'measures'
                    ? 'Перетащите сюда суммы, количества, чеки…'
                    : 'Перетащите поле или нажмите на него в списке') + '</span>';
            el.zoneCount[zone].textContent = list.length ? list.length + ' из ' + limits[zone] : '';
        });
        var filters = state.filters;
        el.zoneBody.filters.innerHTML = filters.length
            ? filters.map(function (flt, i) {
                return '<span class="ex-chip ex-chip-filter" data-zone="filters" data-index="' + i + '" data-id="' +
                    esc(flt.field) + '" title="Нажмите, чтобы изменить"><span class="ex-chip-t">' + esc(fieldName(flt.field)) +
                    ': <small>' + esc(filterSummary(flt)) + '</small></span>' +
                    '<button type="button" data-act="remove" aria-label="Убрать фильтр">×</button></span>';
            }).join('')
            : '<span class="ex-zone-hint">Без фильтров — все данные за период</span>';
        el.zoneCount.filters.textContent = filters.length ? String(filters.length) : '';
    }

    // ==================== шапка, период, контекст ====================

    function typeTitle(type) {
        var t = (boot.report_types || []).filter(function (x) { return x.id === type; })[0];
        return t ? t.title : type;
    }

    function renderBar() {
        el.typeLabel.textContent = typeTitle(state.type);
    }

    function renderContext() {
        var parts = [];
        if (state.saved) parts.push('<span class="ex-tag">Отчёт: <b>' + esc(state.saved.name) + '</b></span>');
        else if (state.origin) parts.push('<span class="ex-tag">' + esc(state.origin) + '</span>');
        else parts.push('<span class="ex-tag">Новый отчёт</span>');
        // Бар из полосы: каким фильтром он стал или почему не применён.
        var bar = barScope();
        if (bar.state === 'applied') {
            parts.push('<span class="ex-tag">Бар: <b>' + esc(bar.label) + '</b> — фильтр «' + esc(bar.fieldName) + '»</span>');
        } else if (bar.state === 'own') {
            parts.push('<span class="ex-tag is-warn">Бар из полосы (' + esc(bar.label) + ') не применён: в отчёте свой фильтр «' +
                esc(bar.fieldName) + '»</span>');
        } else if (bar.state === 'network') {
            parts.push('<span class="ex-tag is-warn">«' + esc(typeTitle(state.type)) + '» — по всей сети: поля бара у этого отчёта нет</span>');
        }
        var stale = state.result && state.resultKey !== configKey();
        if (stale) parts.push('<span class="ex-tag is-warn">Параметры изменились — перестраиваю</span>');
        if (state.result && state.result.meta) {
            var meta = state.result.meta;
            parts.push('<span class="ex-tag">Данные iiko на ' + esc(meta.fetched_at || '—') +
                (meta.cached ? ' · из кэша (до 10 мин)' : '') + '</span>');
        }
        el.context.innerHTML = parts.join('');
        el.result.classList.toggle('is-stale', !!stale);
    }

    function renderAll() {
        renderBar();
        renderFields();
        renderZones();
        renderContext();
        renderCube();
        if (!state.result) showIdle();
    }

    function changed() {
        renderZones();
        renderFields();
        renderContext();
        renderCube();
        persist();
        if (!state.result) showIdle();
        scheduleBuild(EDIT_PAUSE_MS);
    }

    // Куб OLAP повторяет раскладку зон (правила — в static/js/explorer/cube.js). Поле
    // переехало между строками и столбцами при видимом кубе — он поворачивается (pivot).
    var cubeLayout = null;
    function renderCube() {
        if (!el.cube) return;
        var schema = {
            rows: state.rows.map(fieldName), columns: state.columns.map(fieldName),
            measures: state.measures.map(fieldName), filters: state.filters.length,
            period: (periodDates() || {}).title || ''
        };
        var layout = { rows: state.rows.slice(), columns: state.columns.slice() };
        var turn = !el.msg.hidden && Cube.pivoted(cubeLayout, layout);
        cubeLayout = layout;
        if (turn) el.cube.pivot(schema);
        else el.cube.update(schema);
    }

    // Карточка сообщения: kind 'cube' — сборка, готовность и построение (с кубом),
    // 'error' — ошибка (без куба).
    function setMsg(kind, html) {
        el.msg.hidden = false;
        el.msg.className = 'ex-msg ex-card' + (kind === 'error' ? ' is-error' : (el.cube ? ' is-cube' : ''));
        el.msgBody.innerHTML = html;
    }

    // ==================== меню ====================

    function closeMenus() {
        el.typeMenu.hidden = true;
        el.catcher.hidden = true;
    }
    function openMenu(menu) {
        closeMenus();
        closePop();
        menu.hidden = false;
        el.catcher.hidden = false;
    }

    function buildTypeMenu() {
        el.typeMenu.innerHTML = (boot.report_types || []).map(function (t) {
            return '<button type="button" class="ex-mi' + (t.id === state.type ? ' is-on' : '') + '" data-type="' +
                esc(t.id) + '"><span class="ex-mi-t">' + esc(t.title) + '<span class="ex-mi-sub">' +
                esc(t.hint) + '</span></span></button>';
        }).join('');
    }

    function changeType(type) {
        closeMenus();
        if (type === state.type) return;
        var hasFields = state.rows.length || state.columns.length || state.measures.length;
        var go = function () {
            state.type = type;
            state.rows = []; state.columns = []; state.measures = [];
            state.filters = guardFilters(type);
            state.saved = null; state.origin = null;
            state.result = null; state.resultKey = null;
            el.result.hidden = true;
            loadCatalog(type).then(function () { renderAll(); persist(); })
                .catch(function (err) { showError(err); });
            renderBar();
        };
        if (!hasFields) { go(); return; }
        confirmBox('Сменить тип отчёта на «' + typeTitle(type) + '»?',
                   'У типов разные поля: строки, столбцы, показатели и фильтры очистятся.', 'Сменить')
            .then(function (ok) { if (ok) go(); });
    }

    // ==================== добавление полей ====================

    function checkAdd(zone, f) {
        if (!f) return 'Поле не найдено в каталоге.';
        if (f.blocked) return f.blocked;
        var limits = boot.limits || {};
        if (zone === 'rows' || zone === 'columns') {
            if (!f.group) return 'Это показатель: его место — в «Показателях».';
            if (state.measures.indexOf(f.id) >= 0) return 'Поле уже в показателях: iiko не отдаёт одно поле и разрезом, и показателем.';
            if (state[zone].length >= limits[zone] && state[zone].indexOf(f.id) < 0) {
                return 'В «' + (zone === 'rows' ? 'Строках' : 'Столбцах') + '» не больше ' + limits[zone] + ' полей.';
            }
        } else if (zone === 'measures') {
            if (!f.agg) return 'Это не показатель: поставьте поле в строки или столбцы.';
            if (state.rows.indexOf(f.id) >= 0 || state.columns.indexOf(f.id) >= 0) {
                return 'Поле уже в строках или столбцах: iiko не отдаёт одно поле и разрезом, и показателем.';
            }
            if (state.measures.length >= limits.measures && state.measures.indexOf(f.id) < 0) {
                return 'Показателей не больше ' + limits.measures + '.';
            }
        } else if (zone === 'filters') {
            if (!f.filter_op) return f.filter_note || 'По этому полю фильтр нельзя.';
        }
        return null;
    }

    function addField(zone, id, index) {
        var f = fieldOf(id);
        var problem = checkAdd(zone, f);
        if (problem) { toast(problem, 5000); return false; }
        if (zone === 'filters') {
            var existing = -1;
            state.filters.forEach(function (flt, i) { if (flt.field === id) existing = i; });
            openFilterEditor(id, existing >= 0 ? existing : null);
            return true;
        }
        // Поле переезжает между строками и столбцами, а не дублируется.
        ['rows', 'columns'].forEach(function (z) {
            if (z !== zone) {
                var at = state[z].indexOf(id);
                if (at >= 0) state[z].splice(at, 1);
            }
        });
        var list = state[zone];
        var current = list.indexOf(id);
        if (current >= 0) list.splice(current, 1);
        if (index === undefined || index === null || index > list.length) index = list.length;
        if (current >= 0 && current < index) index -= 1;
        list.splice(Math.max(0, index), 0, id);
        changed();
        return true;
    }

    function removeFromZone(zone, index) {
        if (zone === 'filters') state.filters.splice(index, 1);
        else state[zone].splice(index, 1);
        changed();
    }

    function moveInZone(zone, index, delta) {
        var list = state[zone];
        var target = index + delta;
        if (target < 0 || target >= list.length) return;
        var item = list.splice(index, 1)[0];
        list.splice(target, 0, item);
        changed();
    }

    // ==================== поповер поля ====================

    function closePop() {
        el.pop.hidden = true;
        el.pop.innerHTML = '';
    }

    function openFieldPop(id, anchor) {
        var f = fieldOf(id);
        if (!f) return;
        closeMenus();
        var actions = [['rows', 'В строки'], ['columns', 'В столбцы'], ['measures', 'В показатели'], ['filters', 'Фильтр…']];
        var html = '<div class="ex-pop-h"><div class="ex-pop-n">' + esc(f.name) + '</div><div class="ex-pop-id">' +
            esc(f.id) + ' · ' + esc(f.type) + '</div></div>';
        actions.forEach(function (a) {
            var problem = checkAdd(a[0], f);
            html += '<button type="button" class="ex-mi" data-add="' + a[0] + '"' + (problem ? ' disabled title="' + esc(problem) + '"' : '') +
                '><span class="ex-mi-t">' + a[1] + '</span></button>';
        });
        var notes = [];
        if (f.blocked) notes.push(f.blocked);
        if (f.hint) notes.push(f.hint);
        if (f.agg) notes.push(f.kind === 'sum' ? 'Итоги — сложением строк.' : 'Итоги считает iiko: значения не складываются (уникальные, средние, проценты).');
        if (!f.filter_op && f.filter_note && !f.blocked) notes.push('Фильтр: ' + f.filter_note);
        if (notes.length) html += '<div class="ex-pop-note">' + notes.map(esc).join('<br>') + '</div>';
        el.pop.innerHTML = html;
        el.pop.dataset.id = id;
        el.pop.hidden = false;
        var rect = anchor.getBoundingClientRect();
        var width = el.pop.offsetWidth;
        var height = el.pop.offsetHeight;
        var left = Math.min(rect.right + 8, window.innerWidth - width - 8);
        if (left < 8) left = 8;
        var top = Math.min(rect.top, window.innerHeight - height - 8);
        if (top < 8) top = 8;
        if (isNarrow()) { left = Math.max(8, (window.innerWidth - width) / 2); top = Math.max(8, rect.top - height - 8); }
        el.pop.style.left = left + 'px';
        el.pop.style.top = top + 'px';
    }

    // ==================== модальные окна ====================

    var modalClose = null;
    // Каждое окно — новый узел внутри #exModal, и обработчики окна вешаются на него.
    // С закрытием узел уходит вместе с ними: обработчики прошлого окна (фильтр, «Открыть»)
    // не срабатывают в следующем, а запоздавший ответ сервера пишет в отсоединённый узел.
    function openModal(title, subtitle, bodyHtml, footHtml, onClose) {
        closeMenus();
        closePop();
        var box = document.createElement('div');
        box.className = 'ex-modal-in';
        box.innerHTML = '<div class="ex-modal-h"><div class="ex-modal-t">' + esc(title) +
            (subtitle ? '<span class="ex-modal-s">' + esc(subtitle) + '</span>' : '') + '</div>' +
            '<button type="button" class="ex-x" data-close aria-label="Закрыть">×</button></div>' +
            '<div class="ex-modal-b">' + bodyHtml + '</div>' +
            (footHtml ? '<div class="ex-modal-f">' + footHtml + '</div>' : '');
        el.modal.innerHTML = '';
        el.modal.appendChild(box);
        el.modal.hidden = false;
        el.modalBack.hidden = false;
        modalClose = onClose || null;
        var focus = box.querySelector('input, button:not([data-close])');
        if (focus) focus.focus();
        return box;
    }
    function closeModal(result) {
        if (el.modal.hidden) return;
        el.modal.hidden = true;
        el.modalBack.hidden = true;
        el.modal.innerHTML = '';
        var fn = modalClose;
        modalClose = null;
        if (fn) fn(result);
    }

    function confirmBox(title, text, okLabel) {
        return new Promise(function (resolve) {
            var modal = openModal(title, '', '<p class="ex-note">' + esc(text) + '</p>',
                '<span class="ex-grow"></span><button type="button" class="ex-btn" data-close>Отмена</button>' +
                '<button type="button" class="ex-run" data-ok>' + esc(okLabel || 'Да') + '</button>',
                function (result) { resolve(result === true); });
            modal.querySelector('[data-ok]').addEventListener('click', function () { closeModal(true); });
        });
    }

    // ==================== редактор фильтра ====================

    function openFilterEditor(id, index) {
        var f = fieldOf(id);
        if (!f || !f.filter_op) return;
        var existing = index !== null && index !== undefined ? state.filters[index] : null;
        var dates = periodDates() || {};
        if (f.filter_op === 'values') {
            openValuesEditor(f, existing, index, dates);
        } else {
            openRangeEditor(f, existing, index);
        }
    }

    function saveFilter(filter, index) {
        if (index !== null && index !== undefined) state.filters[index] = filter;
        else state.filters.push(filter);
        closeModal();
        changed();
    }

    function removeButton(index) {
        return index !== null && index !== undefined
            ? '<button type="button" class="ex-btn" data-remove>Убрать фильтр</button>' : '';
    }

    function openValuesEditor(f, existing, index, dates) {
        var selected = {};
        (existing ? existing.values : []).forEach(function (v) { selected[JSON.stringify(v)] = v; });
        var mode = existing ? existing.op : 'in';
        var values = [];
        var body = '<div class="ex-row"><span class="ex-seg" data-mode>' +
            '<button type="button" data-op="in"' + (mode === 'in' ? ' class="is-on"' : '') + '>Только выбранные</button>' +
            '<button type="button" data-op="not_in"' + (mode === 'not_in' ? ' class="is-on"' : '') + '>Все, кроме выбранных</button></span></div>' +
            '<input type="search" class="ex-search" data-q placeholder="найти значение…" autocomplete="off">' +
            '<div class="ex-row"><button type="button" class="ex-link" data-all>Выбрать все видимые</button>' +
            '<button type="button" class="ex-link" data-none>Снять все</button><span class="ex-grow"></span>' +
            '<span class="ex-note" data-count></span></div>' +
            '<div class="ex-values" data-list><div class="ex-note">Загружаю значения за ' +
            esc(ruDate(dates.from)) + ' — ' + esc(ruDate(dates.to)) + '…</div></div>' +
            '<div class="ex-row"><input type="text" class="ex-input" data-manual placeholder="добавить значение вручную" ' +
            'style="flex:1"><button type="button" class="ex-btn" data-add-manual>Добавить</button></div>';
        var foot = removeButton(index) + '<span class="ex-grow"></span><button type="button" class="ex-btn" data-close>Отмена</button>' +
            '<button type="button" class="ex-run" data-apply>Применить</button>';
        var modal = openModal('Фильтр: ' + f.name, 'Список — значения из iiko за выбранный период.', body, foot);
        var list = modal.querySelector('[data-list]');
        var query = modal.querySelector('[data-q]');

        function count() {
            var n = Object.keys(selected).length;
            modal.querySelector('[data-count]').textContent = 'выбрано: ' + n;
            modal.querySelector('[data-apply]').disabled = n === 0;
        }
        function draw() {
            var q = query.value.trim().toLowerCase();
            var html = '';
            var shown = 0;
            values.forEach(function (item) {
                var label = item.label;
                if (q && label.toLowerCase().indexOf(q) < 0 && String(item.value).toLowerCase().indexOf(q) < 0) return;
                shown++;
                var key = JSON.stringify(item.value);
                html += '<label class="ex-check"><input type="checkbox" data-key="' + esc(key) + '"' +
                    (Object.prototype.hasOwnProperty.call(selected, key) ? ' checked' : '') + '><span>' + esc(label) +
                    '</span>' + (item.code ? '<small>' + esc(item.code) + '</small>' : '') + '</label>';
            });
            list.innerHTML = html || '<div class="ex-note">Нет значений' + (q ? ' по запросу' : ' за период') + '.</div>';
            count();
        }
        function addValue(value, label, code) {
            var key = JSON.stringify(value);
            if (!values.some(function (v) { return JSON.stringify(v.value) === key; })) {
                values.push({ value: value, label: label, code: code });
            }
        }
        var params = 'report_type=' + encodeURIComponent(state.type) + '&field=' + encodeURIComponent(f.id);
        if (dates.preset) params += '&period=' + encodeURIComponent(dates.preset);
        else params += '&date_from=' + encodeURIComponent(dates.from) + '&date_to=' + encodeURIComponent(dates.to);
        api('GET', '/api/explorer/values?' + params).then(function (data) {
            if (data.has_empty) addValue(null, '(пусто)');
            data.values.forEach(function (item) {
                addValue(item.value, item.label, item.label !== String(item.value) ? String(item.value) : '');
            });
            Object.keys(selected).forEach(function (key) {
                var v = selected[key];
                addValue(v, v === null ? '(пусто)' : Grid.fmtDimText(v, f));
            });
            if (data.truncated) {
                list.insertAdjacentHTML('beforebegin', '<div class="ex-note">Показаны первые ' + data.values.length +
                    ' из ' + data.total + ' — уточните поиском или добавьте значение вручную.</div>');
            }
            draw();
        }).catch(function (err) {
            Object.keys(selected).forEach(function (key) {
                var v = selected[key];
                addValue(v, v === null ? '(пусто)' : Grid.fmtDimText(v, f));
            });
            draw();
            list.insertAdjacentHTML('afterbegin', '<div class="ex-note is-error">Список из iiko не загрузился: ' +
                esc(err.message) + ' Значение можно добавить вручную.</div>');
        });

        modal.addEventListener('click', function (event) {
            var target = event.target;
            if (target.closest('[data-op]')) {
                mode = target.closest('[data-op]').dataset.op;
                modal.querySelectorAll('[data-op]').forEach(function (b) { b.classList.toggle('is-on', b.dataset.op === mode); });
            } else if (target.closest('[data-all]')) {
                modal.querySelectorAll('[data-key]').forEach(function (box) { selected[box.dataset.key] = JSON.parse(box.dataset.key); });
                draw();
            } else if (target.closest('[data-none]')) {
                selected = {};
                draw();
            } else if (target.closest('[data-add-manual]')) {
                var input = modal.querySelector('[data-manual]');
                var text = input.value.trim();
                if (!text) return;
                addValue(text, text);
                selected[JSON.stringify(text)] = text;
                input.value = '';
                draw();
            } else if (target.closest('[data-remove]')) {
                state.filters.splice(index, 1);
                closeModal();
                changed();
            } else if (target.closest('[data-apply]')) {
                var chosen = Object.keys(selected).map(function (key) { return selected[key]; });
                if (!chosen.length) return;
                saveFilter({ field: f.id, op: mode, values: chosen }, index);
            }
        });
        modal.addEventListener('change', function (event) {
            var box = event.target.closest('[data-key]');
            if (!box) return;
            if (box.checked) selected[box.dataset.key] = JSON.parse(box.dataset.key);
            else delete selected[box.dataset.key];
            count();
        });
        query.addEventListener('input', draw);
    }

    function openRangeEditor(f, existing, index) {
        var isDate = f.filter_op === 'date_range';
        var from = existing ? existing.from : '';
        var to = existing ? existing.to : '';
        if (isDate) {
            from = from ? String(from).slice(0, 16) : '';
            to = to ? String(to).slice(0, 16) : '';
        }
        var type = isDate ? (f.type === 'DATE' ? 'date' : 'datetime-local') : 'number';
        if (isDate && f.type === 'DATE') { from = from.slice(0, 10); to = to.slice(0, 10); }
        var includeLow = existing ? existing.include_low !== false : true;
        var includeHigh = existing ? existing.include_high !== false : true;
        var body = '<div class="ex-row"><span class="ex-label">ОТ</span><input class="ex-input" data-from type="' + type +
            '" step="any" value="' + esc(from) + '" style="flex:1"></div>' +
            '<label class="ex-check"><input type="checkbox" data-il' + (includeLow ? ' checked' : '') + '><span>включая нижнюю границу</span></label>' +
            '<div class="ex-row"><span class="ex-label">ДО</span><input class="ex-input" data-to type="' + type +
            '" step="any" value="' + esc(to) + '" style="flex:1"></div>' +
            '<label class="ex-check"><input type="checkbox" data-ih' + (includeHigh ? ' checked' : '') + '><span>включая верхнюю границу</span></label>' +
            '<p class="ex-note" data-err></p>';
        var foot = removeButton(index) + '<span class="ex-grow"></span><button type="button" class="ex-btn" data-close>Отмена</button>' +
            '<button type="button" class="ex-run" data-apply>Применить</button>';
        var modal = openModal('Фильтр: ' + f.name, isDate ? 'Диапазон дат и времени.' : 'Диапазон значений.', body, foot);
        modal.addEventListener('click', function (event) {
            if (event.target.closest('[data-remove]')) {
                state.filters.splice(index, 1);
                closeModal();
                changed();
                return;
            }
            if (!event.target.closest('[data-apply]')) return;
            var low = modal.querySelector('[data-from]').value;
            var high = modal.querySelector('[data-to]').value;
            var err = modal.querySelector('[data-err]');
            if (low === '' || high === '') { err.textContent = 'Заполните обе границы.'; err.classList.add('is-error'); return; }
            var filter = {
                field: f.id, op: f.filter_op,
                from: isDate ? low : Number(low), to: isDate ? high : Number(high),
                include_low: modal.querySelector('[data-il]').checked,
                include_high: modal.querySelector('[data-ih]').checked
            };
            if (!isDate && (isNaN(filter.from) || isNaN(filter.to))) { err.textContent = 'Нужны числа.'; err.classList.add('is-error'); return; }
            if (filter.to < filter.from) { err.textContent = '«До» меньше «от».'; err.classList.add('is-error'); return; }
            saveFilter(filter, index);
        });
    }

    // ==================== построение ====================

    function setBuilding(on) {
        state.building = on;
    }

    function ready() {
        return (state.rows.length || state.columns.length) && state.measures.length;
    }

    function showIdle() {
        if (state.building) return;
        setMsg('cube', '<span class="ex-msg-t">Соберите отчёт</span>Перетащите поля из списка слева в «Строки», ' +
            '«Столбцы» и «Показатели» или нажмите на поле. Отчёт построится сам, как только в нём будут поле и ' +
            'показатель.');
        if (el.cube) el.cube.setMode('idle');
    }

    // Текст ошибки: сервер прислал причину — она (тайм-аут iiko сервер называет сам: «iiko не
    // ответил за 120 с. Сузьте период…», core/olap_client.py); ответа нет совсем или прокси не
    // дождался сервера (5xx без JSON) — просьба сократить период.
    function errorText(err) {
        if (err.data && err.data.error) return err.data.error;
        if (!err.status || err.status >= 500) return 'iiko не успел ответить — сократите период';
        return err.message;
    }

    function showError(err) {
        var extra = '';
        if (err.code === 'too_many_rows' || err.code === 'too_many_cells') {
            extra = '<br><button type="button" class="ex-btn" data-export>Выгрузить в Excel</button>';
        } else if (err.status === 401) {
            extra = '<br><a class="ex-btn" href="/login?next=/explorer">Войти заново</a>';
        } else if (err.status !== 400) {
            // Кнопки «Построить» нет: после сбоя (iiko не ответил, сеть) — повтор того же отчёта.
            extra = '<br><button type="button" class="ex-btn" data-retry>Повторить</button>';
        }
        setMsg('error', '<span class="ex-msg-t">Отчёт не построен</span>' + esc(errorText(err)) + extra);
    }

    // Построить через паузу: серия правок или шагов полосы — одно построение (Р5). Отчёт без поля
    // или показателя не строится — на его месте подсказка «Соберите отчёт».
    function scheduleBuild(ms) {
        clearTimeout(state.buildTimer);
        state.buildTimer = null;
        if (!ready()) {
            if (!state.building) { state.result = null; state.resultKey = null; el.result.hidden = true; showIdle(); }
            return;
        }
        if (state.result && state.resultKey === configKey() && !state.building) return;   // уже построен
        state.buildTimer = setTimeout(function () { state.buildTimer = null; build(); }, ms || 0);
    }

    function build(manual) {
        clearTimeout(state.buildTimer);
        state.buildTimer = null;
        if (state.building) {
            // Отчёт поменяли, пока строился прошлый: построить новый сразу после, а ответ
            // прошлого не показывать — он уже не про то, что на экране.
            state.rebuild = true;
            return;
        }
        if (!state.rows.length && !state.columns.length) {
            if (manual) toast('Добавьте хотя бы одно поле в строки или столбцы.');
            showIdle();
            return;
        }
        if (!state.measures.length) {
            if (manual) toast('Добавьте хотя бы один показатель.');
            showIdle();
            return;
        }
        var key = configKey();
        setBuilding(true);
        renderContext();
        setMsg('cube', '<span class="ex-msg-t">Строю отчёт за ' + esc((periodDates() || {}).title || 'период') +
            '…</span>Сервер запрашивает данные у iiko. Большие отчёты за год строятся до минуты.');
        if (el.cube) el.cube.setMode('building');
        api('POST', '/api/explorer/report', requestPayload('pivot')).then(function (data) {
            if (state.rebuild) return;
            state.result = Grid.prepare(data);
            state.resultKey = key;
            state.sort = null;
            state.expanded = {};
            state.defaultOpen = (data.leaf_count || 0) <= OPEN_ALL_MAX_LEAVES;
            state.maxRows = ROWS_STEP;
            state.unfold = true;
            el.msg.hidden = true;
            renderResult();
            renderContext();
        }).catch(function (err) {
            if (state.rebuild) return;
            state.result = null;
            el.result.hidden = true;
            showError(err);
            renderContext();
        }).then(function () {
            setBuilding(false);
            if (state.rebuild) {
                state.rebuild = false;
                build();
            }
        });
    }

    function renderResult() {
        var result = state.result;
        if (!result) return;
        el.result.hidden = false;
        var fields = result.fields;
        // Пустой ответ iiko — прямое сообщение вместо таблицы из одной строки «Итого —».
        var empty = fields.rows.length ? !(result.tree.ch && result.tree.ch.length) : !result.columns.length;
        var shown = { shown: 0, visible: 0 };
        if (empty) {
            el.gridWrap.innerHTML = '<div class="ex-msg"><span class="ex-msg-t">Нет данных</span>За ' +
                esc(ruDate(result.meta.date_from)) + ' — ' + esc(ruDate(result.meta.date_to)) + ' в iiko нет строк с ' +
                'такими фильтрами. Проверьте период и фильтры (в том числе «не удалено»).</div>';
        } else {
            shown = Grid.render(el.gridWrap, result, {
                shares: state.shares, sort: state.sort, expanded: state.expanded,
                defaultOpen: state.defaultOpen, maxRows: state.maxRows
            });
            // Только свежий ответ: сортировка, раскрытие групп и «Показать ещё» — без анимации.
            if (state.unfold && Cube) Cube.unfold(el.gridWrap);
        }
        state.unfold = false;
        var leaves = result.leaf_count || 0;
        var parts = [];
        if (fields.rows.length) parts.push(leaves + ' ' + plural(leaves, 'строка', 'строки', 'строк'));
        if (result.columns.length) parts.push(result.columns.length + ' ' + plural(result.columns.length, 'столбец', 'столбца', 'столбцов'));
        var meta = result.meta;
        parts.push(ruDate(meta.date_from) + ' — ' + ruDate(meta.date_to));
        el.resultT.textContent = parts.join(' · ');
        el.shares.querySelectorAll('[data-share]').forEach(function (b) { b.classList.toggle('is-on', b.dataset.share === state.shares); });
        el.shares.hidden = empty;
        var hasGroups = !empty && fields.rows.length > 1;
        el.expand.hidden = !hasGroups;
        el.collapse.hidden = !hasGroups;
        if (shown.visible > shown.shown) {
            el.more.hidden = false;
            el.more.innerHTML = 'Показаны первые ' + shown.shown + ' строк из ' + shown.visible + '. ' +
                '<button type="button" class="ex-link" data-more>Показать ещё ' + ROWS_STEP + '</button> или ' +
                '<button type="button" class="ex-link" data-export>выгрузить в Excel</button>.';
        } else {
            el.more.hidden = true;
        }
        el.warnings.innerHTML = (result.warnings || []).map(function (w) {
            return '<div class="ex-warn">' + esc(w) + '</div>';
        }).join('');
        el.how.innerHTML = howHtml(result);
        renderContext();
    }

    function howHtml(result) {
        var meta = result.meta;
        var fields = result.fields;
        var names = function (ids) {
            return ids.map(function (id) {
                var f = fields.measures.filter(function (m) { return m.id === id; })[0];
                return '«' + esc(f ? f.name : id) + '»';
            }).join(', ');
        };
        var html = '<p><b>Период:</b> ' + esc(ruDate(meta.date_from)) + ' — ' + esc(ruDate(meta.date_to)) +
            ' включительно' + (meta.period_title ? ' (' + esc(meta.period_title) + ')' : '') + ', по полю «' +
            esc(meta.date_field_name) + '». В iiko уходит граница «до ' + esc(ruDate(meta.date_to_exclusive)) +
            '»: iiko её не включает, поэтому к последнему дню прибавляется день.</p>';
        html += '<p><b>Фильтры:</b> ' + (meta.filters.length ? '</p><ul>' + meta.filters.map(function (f) {
            return '<li>' + esc(f) + '</li>';
        }).join('') + '</ul>' : 'нет.</p>');
        if (meta.totals.sum.length) {
            html += '<p><b>Итоги сложением строк:</b> ' + names(meta.totals.sum) + ' — итог группы, столбца и отчёта = сумма его строк.</p>';
        }
        if (meta.totals.server.length) {
            html += '<p><b>Итоги из iiko:</b> ' + names(meta.totals.server) + ' — уникальные чеки, средние и проценты ' +
                'нельзя складывать (чек с пивом и едой попал бы в итог дважды), поэтому итоги считает сам iiko ' +
                '(buildSummary), как в iikoOffice.</p>';
        }
        html += '<p><b>Доли:</b> переключатель над таблицей показывает долю строки в итоге столбца или долю столбца в ' +
            'итоге строки — только у показателей, которые складываются.</p>';
        html += '<p><b>Запросы к iiko</b> (POST /v2/reports/olap). Строки и столбцы уходят одним списком ' +
            'группировки, раскладка по столбцам — на сервере сервиса.</p>';
        meta.requests.forEach(function (r) {
            html += '<p>' + esc(r.name) + ' — ' + esc(r.purpose) + ':</p><pre class="ex-code">' +
                esc(JSON.stringify(r.body, null, 2)) + '</pre>';
        });
        html += '<p>Данные iiko на ' + esc(meta.fetched_at || '—') + ' МСК' + (meta.cached ? ' (из кэша сервера, не старше 10 минут)' : '') +
            '. ' + (meta.catalog_note ? esc(meta.catalog_note) : 'Каталог полей — живой список iiko.') + '</p>';
        return html;
    }

    // ==================== Excel ====================

    function exportExcel() {
        if (!state.rows.length && !state.columns.length) { toast('Добавьте поле в строки или столбцы.'); return; }
        if (!state.measures.length) { toast('Добавьте показатель.'); return; }
        el.excel.disabled = true;
        toast('Готовлю Excel — строю отчёт в iiko…', 60000);
        fetch('/api/explorer/export', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestPayload(null))
        }).then(function (response) {
            if (!response.ok) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    throw new Error(data.error || ('Сервер ответил ' + response.status));
                });
            }
            var disposition = response.headers.get('Content-Disposition') || '';
            var match = /filename="([^"]+)"/.exec(disposition);
            return response.blob().then(function (blob) {
                var url = URL.createObjectURL(blob);
                var link = document.createElement('a');
                link.href = url;
                link.download = match ? match[1] : 'olap.xlsx';
                document.body.appendChild(link);
                link.click();
                link.remove();
                setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
                toast('Файл сохранён: ' + link.download);
            });
        }).catch(function (err) {
            toast('Excel не выгружен: ' + err.message, 7000);
        }).then(function () { el.excel.disabled = false; });
    }

    // ==================== сохранение и открытие ====================

    // «Сумма со скидкой, Чеков · Группа блюда 1-го уровня / Со склада» — черновик имени.
    function suggestName() {
        var parts = state.measures.slice(0, 2).map(fieldName);
        var by = state.rows.concat(state.columns).slice(0, 3).map(fieldName);
        return (parts.join(', ') + (by.length ? ' · ' + by.join(' / ') : '')).slice(0, 120);
    }

    function openSave() {
        if (!state.measures.length || (!state.rows.length && !state.columns.length)) {
            toast('Сначала соберите отчёт: поля в строки или столбцы и показатель.');
            return;
        }
        var saved = state.saved;
        var saveDates = periodDates() || {};
        var savePreset = presetOf(saveDates);
        var body = '<input type="text" class="ex-input" data-name maxlength="120" value="' +
            esc(saved ? saved.name : suggestName()) + '" aria-label="Название отчёта">' +
            (saved ? '<label class="ex-check"><input type="checkbox" data-new><span>Сохранить как новый отчёт ' +
                '(«' + esc(saved.name) + '» не изменится)</span></label>' : '') +
            '<p class="ex-note">Сохраняются поля, фильтры и период полосы' + (savePreset
                ? ' — как «' + esc((presetRow(savePreset) || {}).title || savePreset) + '»: при открытии даты пересчитаются.'
                : ' — как даты ' + esc(ruDate(saveDates.from)) + ' — ' + esc(ruDate(saveDates.to)) + '.') +
            ' При открытии период отчёта станет общим выбором сайта; бар не сохраняется — отчёт строится по ' +
            'бару, выбранному в полосе. Данные при открытии строятся заново из iiko.</p>' +
            '<p class="ex-note is-error" data-err></p>';
        var foot = '<span class="ex-grow"></span><button type="button" class="ex-btn" data-close>Отмена</button>' +
            '<button type="button" class="ex-run" data-ok>Сохранить</button>';
        var modal = openModal(saved ? 'Сохранить отчёт' : 'Сохранить новый отчёт', '', body, foot);
        modal.querySelector('[data-ok]').addEventListener('click', function () {
            var name = modal.querySelector('[data-name]').value.trim();
            var asNew = modal.querySelector('[data-new]') && modal.querySelector('[data-new]').checked;
            if (!name) { modal.querySelector('[data-err]').textContent = 'Введите название.'; return; }
            var payload = { name: name, config: currentConfig() };
            if (saved && !asNew) payload.id = saved.id;
            api('POST', '/api/explorer/saved', payload).then(function (data) {
                state.saved = { id: data.report.id, name: data.report.name };
                state.origin = null;
                closeModal();
                setUrlReport(data.report.id);
                persist();
                renderContext();
                toast('Отчёт «' + data.report.name + '» сохранён.');
            }).catch(function (err) {
                modal.querySelector('[data-err]').textContent = err.message;
            });
        });
    }

    function setUrlReport(id) {
        try {
            var url = new URL(window.location.href);
            if (id) url.searchParams.set('report', id);
            else url.searchParams.delete('report');
            window.history.replaceState(null, '', url.toString());
        } catch (e) { /* старый браузер: ссылка просто не обновится */ }
    }

    function periodText(config) {
        var p = config.period;
        if (!p) return '';
        if (p.preset) {
            var found = (boot.periods || []).filter(function (x) { return x.id === p.preset; })[0];
            return found ? found.title : p.preset;
        }
        return ruDate(p.from) + ' — ' + ruDate(p.to);
    }

    function openOpen() {
        var body = '<div class="ex-row"><span class="ex-seg" data-tabs>' +
            '<button type="button" data-tab="saved" class="is-on">Сохранённые в сервисе</button>' +
            '<button type="button" data-tab="iiko">Из iikoOffice</button></span></div>' +
            '<div data-pane><div class="ex-note">Загружаю…</div></div>';
        var modal = openModal('Открыть отчёт', '', body, '');
        var pane = modal.querySelector('[data-pane]');
        var tab = 'saved';
        var cache = {};

        function drawSaved(reports) {
            if (!reports.length) {
                pane.innerHTML = '<div class="ex-note">Сохранённых отчётов пока нет. Соберите отчёт и нажмите «Сохранить».</div>';
                return;
            }
            pane.innerHTML = reports.map(function (r) {
                return '<div class="ex-saved-row"><button type="button" class="ex-list-item" data-open="' + esc(r.id) + '">' +
                    '<span class="ex-list-t">' + esc(r.name) + '<span class="ex-list-s">' + esc(typeTitle(r.config.report_type)) +
                    ' · ' + esc(periodText(r.config)) + ' · изменён ' + esc(r.updated_at || '') + ', ' + esc(r.updated_by || '') +
                    '</span></span></button><button type="button" class="ex-x ex-list-del" data-del="' + esc(r.id) +
                    '" aria-label="Удалить" title="Удалить отчёт">×</button></div>';
            }).join('');
        }
        function drawIiko(data) {
            var presets = data.presets || [];
            if (!presets.length) {
                pane.innerHTML = '<div class="ex-note">В iikoOffice нет сохранённых OLAP-отчётов. Соберите отчёт в ' +
                    'iikoOffice («OLAP-отчёт по продажам» → «Сохранить») — он появится здесь.</div>';
                return;
            }
            pane.innerHTML = '<div class="ex-note">Список iiko на ' + esc(data.fetched_at || '') + '. Отчёт откроется ' +
                'с фильтрами как в iikoOffice; период — из отчёта или текущий.</div>' + presets.map(function (p, i) {
                return '<button type="button" class="ex-list-item" data-preset="' + i + '"' + (p.supported ? '' : ' disabled') + '>' +
                    '<span class="ex-list-t">' + esc(p.name) + '<span class="ex-list-s">' + esc(typeTitle(p.report_type)) +
                    (p.config.period ? ' · ' + esc(periodText(p.config)) : '') +
                    (p.notes.length ? ' · ' + esc(p.notes.join('; ')) : '') + '</span></span></button>';
            }).join('');
        }
        function load() {
            // Вкладка запоминается на момент запроса: медленный ответ /presets, пришедший
            // после переключения на «Сохранённые», не ляжет в чужую вкладку.
            var requested = tab;
            pane.innerHTML = '<div class="ex-note">Загружаю' + (requested === 'iiko' ? ' список из iiko' : '') + '…</div>';
            var url = requested === 'saved' ? '/api/explorer/saved' : '/api/explorer/presets';
            api('GET', url).then(function (data) {
                cache[requested] = data;
                if (tab !== requested) return;
                if (requested === 'saved') drawSaved(data.reports || []);
                else drawIiko(data);
            }).catch(function (err) {
                if (tab !== requested) return;
                pane.innerHTML = '<div class="ex-note is-error">' + esc(err.message) + '</div>';
            });
        }
        load();

        modal.addEventListener('click', function (event) {
            var t = event.target;
            var tabBtn = t.closest('[data-tab]');
            if (tabBtn) {
                tab = tabBtn.dataset.tab;
                modal.querySelectorAll('[data-tab]').forEach(function (b) { b.classList.toggle('is-on', b.dataset.tab === tab); });
                load();
                return;
            }
            var openBtn = t.closest('[data-open]');
            if (openBtn) {
                var report = (cache.saved.reports || []).filter(function (r) { return r.id === openBtn.dataset.open; })[0];
                if (!report) return;
                closeModal();
                resetResult();
                applyConfig(report.config, { saved: { id: report.id, name: report.name } }).then(function (ok) {
                    if (!ok) return;
                    setUrlReport(report.id);
                    applyReportPeriod(report.config.period);
                    scheduleBuild(0);
                });
                return;
            }
            var delBtn = t.closest('[data-del]');
            if (delBtn) {
                var id = delBtn.dataset.del;
                var victim = (cache.saved.reports || []).filter(function (r) { return r.id === id; })[0];
                if (!victim || !window.confirm('Удалить отчёт «' + victim.name + '»? Данные iiko не затрагиваются.')) return;
                api('DELETE', '/api/explorer/saved/' + encodeURIComponent(id)).then(function () {
                    if (state.saved && state.saved.id === id) { state.saved = null; setUrlReport(null); renderContext(); persist(); }
                    toast('Отчёт удалён.');
                    load();
                }).catch(function (err) { toast(err.message, 6000); });
                return;
            }
            var presetBtn = t.closest('[data-preset]');
            if (presetBtn && !presetBtn.disabled) {
                var preset = cache.iiko.presets[Number(presetBtn.dataset.preset)];
                closeModal();
                resetResult();
                var config = JSON.parse(JSON.stringify(preset.config));
                applyConfig(config, { origin: 'Из iikoOffice: «' + preset.name + '»' }).then(function (ok) {
                    if (!ok) return;
                    setUrlReport(null);
                    // Период отчёта iikoOffice, если он в нём есть, — общий выбор; нет — период полосы.
                    if (config.period) applyReportPeriod(config.period);
                    scheduleBuild(0);
                    if (preset.notes.length) toast('Перенесено не всё: ' + preset.notes.join('; ') + '.', 7000);
                });
            }
        });
    }

    function resetResult() {
        state.result = null;
        state.resultKey = null;
        el.result.hidden = true;
    }

    // ==================== перетаскивание ====================

    function dropIndex(zone, event) {
        var chips = Array.prototype.slice.call(el.zoneBody[zone].querySelectorAll('.ex-chip'));
        for (var i = 0; i < chips.length; i++) {
            var rect = chips[i].getBoundingClientRect();
            var sameLine = event.clientY >= rect.top && event.clientY <= rect.bottom;
            if ((sameLine && event.clientX < rect.left + rect.width / 2) || event.clientY < rect.top) return i;
        }
        return chips.length;
    }

    // Перенос поля в другую зону (перетаскиванием): поле сначала снимается с прежнего
    // места, затем проверяется для новой зоны; не подошло — всё возвращается как было.
    function moveField(drag, zone, index) {
        var backup = { rows: state.rows.slice(), columns: state.columns.slice(), measures: state.measures.slice() };
        if (drag.from && drag.from !== zone) {
            var at = state[drag.from].indexOf(drag.id);
            if (at >= 0) state[drag.from].splice(at, 1);
        }
        var problem = checkAdd(zone, fieldOf(drag.id));
        if (problem) {
            state.rows = backup.rows;
            state.columns = backup.columns;
            state.measures = backup.measures;
            toast(problem, 5000);
            return;
        }
        addField(zone, drag.id, index);
    }

    function bindDrag() {
        document.addEventListener('dragstart', function (event) {
            var field = event.target.closest && event.target.closest('.ex-field[draggable="true"]');
            var chipEl = event.target.closest && event.target.closest('.ex-chip[draggable="true"]');
            if (field) {
                state.drag = { id: field.dataset.id, from: null };
            } else if (chipEl) {
                state.drag = { id: chipEl.dataset.id, from: chipEl.dataset.zone, index: Number(chipEl.dataset.index) };
                chipEl.classList.add('is-dragging');
            } else {
                return;
            }
            try { event.dataTransfer.setData('text/plain', state.drag.id); } catch (e) { /* IE */ }
            event.dataTransfer.effectAllowed = 'move';
        });
        document.addEventListener('dragend', function () {
            state.drag = null;
            document.querySelectorAll('.ex-chip.is-dragging').forEach(function (c) { c.classList.remove('is-dragging'); });
            document.querySelectorAll('.ex-zone.is-drop').forEach(function (z) { z.classList.remove('is-drop'); });
        });
        document.querySelectorAll('.ex-zone').forEach(function (zoneEl) {
            var zone = zoneEl.dataset.zone;
            zoneEl.addEventListener('dragover', function (event) {
                if (!state.drag) return;
                event.preventDefault();
                zoneEl.classList.add('is-drop');
            });
            zoneEl.addEventListener('dragleave', function (event) {
                if (!zoneEl.contains(event.relatedTarget)) zoneEl.classList.remove('is-drop');
            });
            zoneEl.addEventListener('drop', function (event) {
                event.preventDefault();
                zoneEl.classList.remove('is-drop');
                var drag = state.drag;
                state.drag = null;
                if (!drag) return;
                if (zone === 'filters') {
                    if (drag.from === 'filters') return;
                    addField('filters', drag.id);
                    return;
                }
                var index = dropIndex(zone, event);
                if (drag.from === zone) {
                    var list = state[zone];
                    var item = list.splice(drag.index, 1)[0];
                    if (drag.index < index) index -= 1;
                    list.splice(index, 0, item);
                    changed();
                    return;
                }
                if (drag.from === 'filters') return;
                moveField(drag, zone, index);
            });
        });
    }

    // ==================== события ====================

    function bind() {
        el.catcher.addEventListener('click', closeMenus);
        el.typeBtn.addEventListener('click', function () {
            if (!el.typeMenu.hidden) { closeMenus(); return; }
            buildTypeMenu();
            openMenu(el.typeMenu);
        });
        el.typeMenu.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-type]');
            if (btn) changeType(btn.dataset.type);
        });
        el.excel.addEventListener('click', exportExcel);
        el.save.addEventListener('click', openSave);
        el.open.addEventListener('click', openOpen);

        el.fieldSearch.addEventListener('input', function () {
            state.search = el.fieldSearch.value;
            renderFields();
        });
        el.fieldList.addEventListener('toggle', function (event) {
            var group = event.target.closest && event.target.closest('.ex-group');
            if (group) state.openGroups[group.dataset.group] = group.open;
        }, true);
        el.fieldList.addEventListener('click', function (event) {
            var btn = event.target.closest('.ex-field');
            if (!btn) return;
            if (state.pendingZone) {
                var zone = state.pendingZone;
                if (addField(zone, btn.dataset.id)) {
                    state.pendingZone = null;
                    el.fields.classList.remove('is-open');
                }
                return;
            }
            openFieldPop(btn.dataset.id, btn);
        });
        el.pop.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-add]');
            if (!btn || btn.disabled) return;
            var id = el.pop.dataset.id;
            closePop();
            addField(btn.dataset.add, id);
            if (isNarrow()) el.fields.classList.remove('is-open');
        });
        document.querySelectorAll('.ex-zone-body').forEach(function (body) {
            body.addEventListener('click', function (event) {
                var chipEl = event.target.closest('.ex-chip');
                if (!chipEl) return;
                var zone = chipEl.dataset.zone;
                var index = Number(chipEl.dataset.index);
                var act = event.target.closest('button') && event.target.closest('button').dataset.act;
                if (act === 'remove') { removeFromZone(zone, index); return; }
                if (act === 'left') { moveInZone(zone, index, -1); return; }
                if (act === 'right') { moveInZone(zone, index, 1); return; }
                if (zone === 'filters') openFilterEditor(chipEl.dataset.id, index);
            });
        });
        document.querySelectorAll('[data-add]').forEach(function (btn) {
            if (!btn.classList.contains('ex-zone-add')) return;
            btn.addEventListener('click', function () {
                state.pendingZone = btn.dataset.add;
                el.fields.classList.add('is-open');
                toast('Выберите поле для зоны «' + ZONE_TITLES[state.pendingZone] + '».', 2500);
            });
        });
        el.fieldsClose.addEventListener('click', function () {
            state.pendingZone = null;
            el.fields.classList.remove('is-open');
        });

        el.shares.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-share]');
            if (!btn) return;
            state.shares = btn.dataset.share;
            renderResult();
        });
        el.expand.addEventListener('click', function () {
            state.defaultOpen = true;
            state.expanded = {};
            renderResult();
        });
        el.collapse.addEventListener('click', function () {
            state.defaultOpen = false;
            state.expanded = {};
            renderResult();
        });
        el.gridWrap.addEventListener('click', function (event) {
            var tog = event.target.closest('.ex-tog');
            if (tog) {
                var path = tog.dataset.path;
                var open = tog.classList.contains('is-open');
                state.expanded[path] = !open;
                renderResult();
                return;
            }
            var th = event.target.closest('thead th');
            if (!th || th.classList.contains('ex-colkey')) return;
            if (th.dataset.sort === 'label') {
                state.sort = state.sort && state.sort.type === 'label'
                    ? (state.sort.dir === 1 ? { type: 'label', dir: -1 } : null)
                    : { type: 'label', dir: 1 };
            } else if (th.dataset.m !== undefined) {
                var col = Number(th.dataset.col);
                var m = Number(th.dataset.m);
                var same = state.sort && state.sort.type === 'measure' && state.sort.col === col && state.sort.m === m;
                state.sort = same ? (state.sort.dir === -1 ? { type: 'measure', col: col, m: m, dir: 1 } : null)
                    : { type: 'measure', col: col, m: m, dir: -1 };
            }
            renderResult();
        });
        el.result.addEventListener('click', function (event) {
            if (event.target.closest('[data-more]')) {
                state.maxRows += ROWS_STEP;
                renderResult();
            } else if (event.target.closest('[data-export]')) {
                exportExcel();
            }
        });
        el.msg.addEventListener('click', function (event) {
            if (event.target.closest('[data-export]')) exportExcel();
            else if (event.target.closest('[data-retry]')) build(true);
        });
        el.modalBack.addEventListener('click', function () { closeModal(); });
        el.modal.addEventListener('click', function (event) {
            if (event.target.closest('[data-close]')) closeModal();
        });
        document.addEventListener('click', function (event) {
            if (!el.pop.hidden && !el.pop.contains(event.target) && !event.target.closest('.ex-field')) closePop();
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeMenus();
                closePop();
                closeModal();
                if (el.fields.classList.contains('is-open')) {
                    state.pendingZone = null;
                    el.fields.classList.remove('is-open');
                }
            } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && el.modal.hidden) {
                build(true);   // построить сейчас, не дожидаясь паузы
            }
        });
        bindDrag();
    }

    // ==================== старт ====================

    function init() {
        el = {
            catcher: $('exCatch'),
            typeBtn: $('exTypeBtn'), typeLabel: $('exTypeLabel'), typeMenu: $('exTypeMenu'),
            open: $('exOpenBtn'), save: $('exSaveBtn'), excel: $('exExcelBtn'),
            context: $('exContext'), fields: $('exFields'), fieldsSrc: $('exFieldsSrc'),
            fieldsClose: $('exFieldsClose'), fieldSearch: $('exFieldSearch'), fieldList: $('exFieldList'),
            msg: $('exMsg'), msgBody: $('exMsgBody'),
            result: $('exResult'), resultT: $('exResultT'), shares: $('exShares'),
            expand: $('exExpand'), collapse: $('exCollapse'), gridWrap: $('exGridWrap'),
            more: $('exMore'), warnings: $('exWarnings'), how: $('exHow'),
            pop: $('exPop'), modal: $('exModal'), modalBack: $('exModalBack'), toast: $('exToast'),
            zoneBody: {}, zoneCount: {}
        };
        ['rows', 'columns', 'measures', 'filters'].forEach(function (zone) {
            el.zoneBody[zone] = document.querySelector('[data-body="' + zone + '"]');
            el.zoneCount[zone] = document.querySelector('[data-count="' + zone + '"]');
        });
        // Без cube.js (не загрузился) страница работает как раньше — без куба.
        el.cube = Cube ? Cube.create($('exCube'), $('exCubeLegend')) : null;
        bind();

        var reportId = null;
        try { reportId = new URL(window.location.href).searchParams.get('report'); } catch (e) { reportId = null; }
        var draft = restoreDraft();
        var start;
        if (reportId) {
            start = api('GET', '/api/explorer/saved').then(function (data) {
                var report = (data.reports || []).filter(function (r) { return r.id === reportId; })[0];
                if (!report) {
                    toast('Сохранённый отчёт по ссылке не найден — открыт отчёт по умолчанию.', 6000);
                    setUrlReport(null);
                    return applyConfig(boot.default, null);
                }
                // Ссылка на отчёт: его период — общий выбор, если в адресе нет своего периода.
                return applyConfig(report.config, { saved: { id: report.id, name: report.name } }).then(function (ok) {
                    if (ok && !hasUrlPeriod()) applyReportPeriod(report.config.period);
                    return ok;
                });
            });
        } else if (draft && draft.config) {
            start = applyConfig(draft.config, draft.saved ? { saved: draft.saved } : null);
        } else {
            start = applyConfig(boot.default, null);
        }
        // Тяжёлая страница считает сразу при открытии (Р5); смена бара или периода в полосе —
        // новое построение после паузы.
        Promise.resolve(start).then(function () {
            scheduleBuild(0);
        }).catch(function (err) {
            el.fieldList.innerHTML = '<div class="ex-empty-list">Список полей не загрузился: ' + esc(err.message) + '</div>';
            showError(err);
        });
        if (Strip && Strip.onChange) {
            Strip.onChange(function () {
                renderContext();
                renderCube();
                scheduleBuild(STRIP_PAUSE_MS);
            });
        }
        renderBar();
    }

    function hasUrlPeriod() {
        try {
            var q = new URL(window.location.href).searchParams;
            return !!(q.get('date_from') && q.get('date_to'));
        } catch (e) { return false; }
    }

    // Для теста исполнения (tests/test_explorer_runtime.mjs): связка с полосой и построение.
    window.__explorer = {
        state: state, periodDates: periodDates, presetOf: presetOf, stripPeriodOf: stripPeriodOf,
        applyReportPeriod: applyReportPeriod, barScope: barScope, requestPayload: requestPayload,
        currentConfig: currentConfig, layoutConfig: layoutConfig, changed: changed
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

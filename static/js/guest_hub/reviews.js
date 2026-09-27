/* Страница «Отзывы» (/reviews) раздела «Гости».

   Что делает: список отзывов с Яндекс Карт и из бота, ответ на каждый,
   пять карточек показателей (вся сеть и четыре бара), добавление и правка
   отзыва вручную, «Сделать материалом» для контент-плана.

   Интеграций на этом этапе нет: отзывы вносятся руками, ответ никуда не
   уходит — его копируют и публикуют в источнике сами (об этом говорит
   подпись под каждым ответом).

   Источник истины — сервер (core/guest_reviews.py, routes/reviews.py):
     - показатели (count, avg_rating, unanswered_pct, median_response_hours,
       oldest_unanswered_hours) и формулы к ним приходят готовыми в ответе
       GET /api/reviews (metrics, formulas) — здесь они только печатаются;
     - age_hours / response_hours у каждого отзыва тоже считает сервер;
     - порядок списка задаёт сервер (без ответа — от самого давнего, затем
       остальные — от новых к старым), клиент его не пересортировывает;
     - проверку полей делает сервер, его сообщение показывается как есть.
   Клиент только форматирует: длительность в часах/сутках (правило —
   у waitText), числа с запятой (GH.fmtNum, округление половины вверх).

   Параметры адреса: ?month=YYYY-MM | all, ?status=new|answered|skipped,
   ?source=yandex|bot, ?rating=low|mid|high|none. Бар — общий фильтр раздела
   (GH.getBar / GH.setBar, localStorage 'gh.bar'), в адрес не пишется.
   Период по умолчанию (нет ?month) — текущий месяц, но у «Без ответа»
   (?status=new) — «За всё время»: отзыв, ждущий ответа, важен любой давности.
   Счётчик полосы «Отзывы без ответа» ведёт сюда же: ?status=new&month=all.

   После каждого изменения (ответ, пропуск, возврат, материал, добавление,
   правка, удаление) обновляются и список, и полоса «требует внимания»
   (afterChange -> GH.loadAttention). При выбранном месяце под заголовком
   списка видно, сколько отзывов без ответа осталось за другими месяцами
   (правило — у elsewhereCount).

   Стиль: IIFE, 'use strict', ES5 (var, function), как static/js/draft/draft.js.
   Зависит от static/js/guest_hub/common.js (window.GH) — подключается раньше. */
(function () {
    'use strict';

    var GH = window.GH;

    // ==================== константы ====================

    // Эндпоинты — routes/reviews.py. <id> подставляет apiUrl().
    var API = {
        list: '/api/reviews',
        item: '/api/reviews/<id>',
        reply: '/api/reviews/<id>/reply',
        action: '/api/reviews/<id>/action',
        toMaterial: '/api/reviews/<id>/to-material'
    };

    // Срок ответа: отзыв без ответа дольше 48 ч (двое суток) отмечается
    // оранжевым (спецификация раздела, п. 5). Та же граница делит показ
    // длительности: до 48 ч — часы, дальше — сутки.
    var WAIT_WARN_HOURS = 48;
    // Пауза после последнего нажатия клавиши, после которой черновик ответа
    // уходит на сервер: реже — теряется набранное при закрытии вкладки, чаще —
    // запрос на каждую букву.
    var DRAFT_SAVE_MS = 800;
    // Лимиты полей — те же, что в core/guest_reviews.py.
    var MAX_REPLY_LEN = 4000;   // MAX_REPLY_LEN: внутри лимита сообщения Telegram 4096
    var MAX_TEXT_LEN = 5000;    // MAX_TEXT_LEN
    // Меню периода: текущий месяц и 11 прошлых — ровно год назад.
    var MONTH_MENU_COUNT = 12;
    // Первый месяц, который принимает сервер (YEAR_MIN = 2020).
    var MONTH_MIN = '2020-01';
    // Сколько держится подсветка карточки после действия.
    var FLASH_MS = 1600;
    // Поиск гостя в «Маркетинге» (/api/guests/search) ищет ПОДСТРОКОЙ по
    // телефону, номеру карты и имени. Телефон там хранится одними цифрами и
    // часто с лишней ведущей 7 (779211234567 — особенность выгрузки iiko),
    // поэтому «+7 921 123-45-67» как есть не найдётся. Последние 10 цифр —
    // номер без кода страны (российский формат) — входят подстрокой в любую
    // форму записи и находят гостя.
    var PHONE_TAIL_DIGITS = 10;
    // Поиск в «Маркетинге» начинается с 2 символов (короче он не ищет).
    var GUEST_QUERY_MIN = 2;

    // Запасной справочник источников до первого ответа сервера (там — sources).
    var SOURCES_FALLBACK = [
        { key: 'yandex', name: 'Яндекс Карты' },
        { key: 'bot', name: 'Бот' }
    ];
    // Корзины оценки — RATING_BUCKETS в core/guest_reviews.py.
    var RATING_OPTS = [
        { key: '', name: 'Все оценки', label: 'Все' },
        { key: 'low', name: '1–2', hint: 'низкие' },
        { key: 'mid', name: '3', hint: 'средние' },
        { key: 'high', name: '4–5', hint: 'высокие' },
        { key: 'none', name: 'Без оценки', hint: 'только бот' }
    ];
    var STATUS_OPTS = [
        { key: '', name: 'Все статусы', label: 'Все' },
        { key: 'new', name: 'Без ответа' },
        { key: 'answered', name: 'Отвечены' },
        { key: 'skipped', name: 'Без ответа по решению' }
    ];
    var STATUS_KEYS = ['new', 'answered', 'skipped'];
    // Класс карточки по статусу: у ждущих ответа — полоска слева, у оставленных
    // без ответа по решению — приглушённый текст. У отвеченных своего класса нет.
    var STATUS_CLASS = { 'new': 'is-new', answered: '', skipped: 'is-skipped' };
    // Тон пипсов оценки — по тем же корзинам: 1–2 низкие, 3 средняя, 4–5 высокие.
    var RATING_TONE = { 1: 'danger', 2: 'danger', 3: 'warning', 4: 'success', 5: 'success' };
    var RATING_WORD = { danger: 'низкая', warning: 'средняя', success: 'высокая' };

    // Черновик ответа хранится как набран (сервер его не обрезает), и поле
    // должно показать его так же. Парсер HTML выбрасывает ОДИН перевод строки
    // сразу после <textarea> («удобство для авторов» из стандарта HTML), и
    // черновик, начатый с пустой строки, терял бы её при каждой перерисовке.
    // Свой перевод строки перед текстом съедается вместо неё.
    var TA_LEAD = '\n';

    var DOTS_SVG = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">' +
        '<circle cx="3" cy="7" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="11" cy="7" r="1.3"/></svg>';

    // ==================== состояние ====================

    var state = {
        month: null,        // 'YYYY-MM'
        all: false,         // «За всё время»
        bar: '',            // '' — все бары
        source: '',
        rating: '',
        status: '',
        data: null,         // ответ GET /api/reviews
        gen: 0,             // номер запроса: опоздавший ответ отбрасывается
        drafts: {},         // id -> текст черновика ответа, набранный здесь
        draftState: {},     // id -> {kind: 'saving'|'saved'|'error', msg}
        editing: {},        // id -> текст правки ответа (у отвеченных)
        flash: null,        // id карточки для подсветки после действия
        dlg: null,          // открытый диалог отзыва
        attn: null,         // последний ответ полосы: {data, bar} (GH.onAttention)
        busy: false         // список грузится (его числа ещё старые)
    };
    var savers = {};        // id -> отложенное сохранение черновика (GH.debounce)
    var chains = {};        // id -> Promise: запросы по одному отзыву идут по очереди
    var el = {};

    function byId(id) { return document.getElementById(id); }

    // ==================== API ====================

    function apiUrl(key, id, qs) {
        var url = API[key].replace('<id>', encodeURIComponent(id || ''));
        return qs ? url + '?' + qs : url;
    }
    // opts — четвёртый аргумент GH.api ({keepalive: true} при уходе со страницы).
    function call(method, key, id, body, qs, opts) {
        return GH.api(method, apiUrl(key, id, qs), body, opts);
    }
    // Запросы по одному отзыву — строго по очереди (черновик, затем ответ).
    function queue(id, fn) {
        var prev = chains[id] || Promise.resolve();
        var next = prev.then(fn, fn);
        chains[id] = next.then(function () { return null; }, function () { return null; });
        return next;
    }

    // ==================== формат ====================

    function formulas() {
        return (state.data && state.data.formulas) || {};
    }
    function sources() {
        return (state.data && state.data.sources) || SOURCES_FALLBACK;
    }
    function sourceName(key) {
        var list = sources();
        for (var i = 0; i < list.length; i++) if (list[i].key === key) return list[i].name;
        return key || '';
    }
    function optName(opts, key, short) {
        for (var i = 0; i < opts.length; i++) {
            if (opts[i].key === key) return short && opts[i].label ? opts[i].label : opts[i].name;
        }
        return '';
    }
    function nowInfo() {
        return GH.mskNow();
    }
    // '2026-09-25T18:30' -> '25 сентября, 18:30'; год — только если не текущий.
    function fmtWhen(dt) {
        if (!dt) return '';
        var d = String(dt).slice(0, 10);
        var t = String(dt).slice(11, 16);
        var withYear = d.slice(0, 4) !== nowInfo().date.slice(0, 4);
        return GH.fmtDate(d, withYear) + (t ? ', ' + t : '');
    }
    // Часы с одним знаком без «,0»: 5 ч, 5,5 ч, 50 ч. Значение уже округлено
    // сервером до 0,1 — здесь только запятая.
    function hoursText(h) {
        if (h === null || h === undefined) return '—';
        return GH.fmtNum(h, 1).replace(/,0$/, '') + ' ч';
    }
    // Длительность словами. Правило: меньше часа — «меньше часа»; до 48 ч —
    // полные часы (вниз: 5,9 ч -> 5 ч); от 48 ч — полные сутки (вниз:
    // 71 ч -> 2 дня). Вниз — чтобы «2 дня» значило «прошло не меньше двух суток».
    function waitText(h) {
        var v = Number(h) || 0;
        if (v < 1) return 'меньше часа';
        if (v < WAIT_WARN_HOURS) return Math.floor(v) + ' ч';
        var days = Math.floor(v / 24);
        return days + ' ' + GH.plural(days, 'день', 'дня', 'дней');
    }
    function reviewsWord(n) {
        return n + ' ' + GH.plural(n, 'отзыв', 'отзыва', 'отзывов');
    }
    function periodLabel() {
        return state.all ? 'За всё время' : GH.monthLabel(state.month);
    }
    function findReview(id) {
        var list = (state.data && state.data.reviews) || [];
        for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
        return null;
    }
    function cardEl(id) {
        var cards = el.list.querySelectorAll('.gh-rv-card');
        for (var i = 0; i < cards.length; i++) {
            if (cards[i].getAttribute('data-id') === id) return cards[i];
        }
        return null;
    }

    // ==================== адрес и фильтры ====================

    function validMonth(v) {
        return /^\d{4}-(0[1-9]|1[0-2])$/.test(v || '') && v >= MONTH_MIN;
    }
    function readUrl() {
        var p = GH.params();
        var month = p.get('month') || '';
        var cur = nowInfo().month;
        var status = p.get('status') || '';
        state.status = STATUS_KEYS.indexOf(status) >= 0 ? status : '';
        // Без ?month «Без ответа» открывается за всё время: ждущий ответа отзыв
        // важен любой давности, а месяц по умолчанию прятал бы отзывы прошлых
        // месяцев (1-го числа — все вчерашние). Остальные статусы — текущий месяц.
        state.all = month === 'all' || (!month && state.status === 'new');
        state.month = validMonth(month) && month <= cur ? month : cur;
        var source = p.get('source') || '';
        state.source = source === 'yandex' || source === 'bot' ? source : '';
        var rating = p.get('rating') || '';
        state.rating = optName(RATING_OPTS, rating) && rating ? rating : '';
        state.bar = GH.getBar();
    }
    function syncUrl() {
        var cur = nowInfo().month;
        // Текущий месяц в адрес не пишется (он и так по умолчанию) — кроме
        // «Без ответа»: там по умолчанию «За всё время» (см. readUrl), и без
        // явного month обновление страницы сменило бы выбранный период.
        var implicitMonth = state.month === cur && state.status !== 'new';
        GH.setParams({
            month: state.all ? 'all' : (implicitMonth ? null : state.month),
            status: state.status || null,
            source: state.source || null,
            rating: state.rating || null
        });
    }
    function query() {
        var p = [];
        if (state.all) p.push('all=1');
        else p.push('month=' + encodeURIComponent(state.month));
        if (state.bar) p.push('bar=' + encodeURIComponent(state.bar));
        if (state.source) p.push('source=' + encodeURIComponent(state.source));
        if (state.rating) p.push('rating=' + encodeURIComponent(state.rating));
        if (state.status) p.push('status=' + encodeURIComponent(state.status));
        return p.join('&');
    }
    function hasListFilters() {
        return !!(state.bar || state.source || state.rating || state.status);
    }

    // ==================== загрузка ====================

    function load() {
        var my = ++state.gen;
        if (!state.data) {
            el.msg.hidden = false;
            el.msg.className = 'gh-msg';
            el.msg.textContent = 'Загрузка отзывов…';
        }
        el.list.setAttribute('aria-busy', 'true');
        state.busy = true;
        renderElsewhere();
        return call('GET', 'list', null, null, query()).then(function (data) {
            if (my !== state.gen) return;
            state.data = data || {};
            state.busy = false;
            el.banner.hidden = true;
            el.msg.hidden = true;
            el.list.removeAttribute('aria-busy');
            render();
        }, function (err) {
            if (my !== state.gen) return;
            state.busy = false;
            el.list.removeAttribute('aria-busy');
            renderElsewhere();
            showBanner(err);
            if (!state.data) {
                el.msg.hidden = false;
                el.msg.className = 'gh-msg is-err';
                el.msg.textContent = 'Отзывы не загрузились: ' + err.message;
            }
        });
    }
    function showBanner(err) {
        var text = err && err.message ? err.message : 'Ошибка загрузки';
        if (!/[.!?]$/.test(text)) text += '.';
        if (err && err.status === 503) {
            text += ' Файл не перезаписывается, данные целы. Сообщите администратору.';
        }
        el.bannerText.textContent = text;
        el.banner.hidden = false;
    }
    // После любого успешного изменения: полоса «требует внимания» и список
    // перечитываются оба (счётчик «Отзывы без ответа» не должен отставать).
    // Прежний ответ полосы забывается: пока не пришёл новый, подсказка
    // «ещё N за другие месяцы» не сравнивает новые числа списка со старыми.
    function afterChange(id) {
        if (id) state.flash = id;
        state.attn = null;
        GH.loadAttention();
        return load();
    }

    // ==================== отрисовка ====================

    function render() {
        renderPickers();
        renderScope();
        renderTiles();
        renderElsewhere();
        renderList();
    }

    function renderPickers() {
        var cur = nowInfo().month;
        el.monthLabel.textContent = periodLabel();
        el.prev.disabled = state.all || state.month <= MONTH_MIN;
        el.next.disabled = state.all || state.month >= cur;
        el.barLabel.textContent = GH.barName(state.bar);
        el.sourceLabel.textContent = state.source ? sourceName(state.source) : 'Все';
        el.ratingLabel.textContent = optName(RATING_OPTS, state.rating, true);
        el.statusLabel.textContent = optName(STATUS_OPTS, state.status, true);
        var f = formulas();
        if (f.period) el.monthBtn.setAttribute('data-tip', f.period);
        if (f.rating_filter) el.ratingBtn.setAttribute('data-tip', f.rating_filter);
    }

    function renderScope() {
        var f = formulas();
        el.scope.textContent = periodLabel() + ' · ' + (state.source ? sourceName(state.source) : 'все источники');
        el.scope.setAttribute('data-tip', 'Показатели считаются по периоду и источнику. Фильтры бара, оценки ' +
            'и статуса на них не влияют, чтобы карточки баров оставались сравнимыми.');
        var help = [f.count, f.avg_rating, f.unanswered_pct, f.median_response_hours]
            .filter(Boolean).join('\n\n');
        if (help) el.metricsHelp.setAttribute('data-tip', help);
        var sortTip = [f.sort, f.period].filter(Boolean).join('\n\n');
        if (sortTip) el.sortHelp.setAttribute('data-tip', sortTip);
    }

    function tileHtml(key, title, m) {
        m = m || {};
        var f = formulas();
        var on = state.bar === key;
        var count = m.count || 0;
        var avg = m.avg_rating;
        var tip = key
            ? (on ? 'Показаны отзывы бара «' + title + '». Нажмите ещё раз, чтобы показать все бары.'
                  : 'Нажмите, чтобы показать отзывы только бара «' + title + '».')
            : 'Вся сеть: все четыре бара. Нажмите, чтобы снять фильтр бара.';
        var avgTip = (f.avg_rating || '') + '\n\nЗдесь: ' + (m.rated || 0) + ' с оценкой из ' + reviewsWord(count) + '.';
        var countTip = (f.count || '') + '\n\nЗдесь: без ответа ' + (m.unanswered || 0) +
            ', отвечено ' + (m.answered || 0) + ', без ответа по решению ' + (m.skipped || 0) + '.';
        var pctTip = (f.unanswered_pct || '') + '\n\nЗдесь: ' + (m.unanswered || 0) + ' из ' + count + '.';
        if (m.oldest_unanswered_hours !== null && m.oldest_unanswered_hours !== undefined) {
            pctTip += '\n' + (f.oldest_unanswered_hours || 'Дольше всех ждёт') +
                '\nЗдесь: ' + hoursText(m.oldest_unanswered_hours) + '.';
        }
        var medTip = (f.median_response_hours || '') + '\n\nЗдесь: отвеченных отзывов ' + (m.answered || 0) + '.';
        var pct = m.unanswered_pct;
        var warn = (m.unanswered || 0) > 0;
        return '<button type="button" class="gh-tile gh-rv-tile' + (on ? ' is-on' : '') + '" data-bar="' + GH.esc(key) +
                '" aria-pressed="' + (on ? 'true' : 'false') + '" data-tip="' + GH.esc(tip) + '">' +
            '<span class="gh-tile-cap">' + GH.esc(title) + '</span>' +
            '<span class="gh-tile-v' + (avg === null || avg === undefined ? ' is-dash' : '') + '" data-tip="' + GH.esc(avgTip) + '">' +
                (avg === null || avg === undefined ? '—' : GH.fmtNum(avg, 1) + '<u> из 5</u>') + '</span>' +
            '<span class="gh-rv-tl" data-tip="' + GH.esc(countTip) + '"><b>' + count + '</b> ' +
                GH.plural(count, 'отзыв', 'отзыва', 'отзывов') + '</span>' +
            '<span class="gh-rv-tl' + (warn ? ' is-warn' : '') + '" data-tip="' + GH.esc(pctTip) + '">без ответа <b>' +
                (pct === null || pct === undefined ? '—' : pct + '%') + '</b></span>' +
            '<span class="gh-rv-tl" data-tip="' + GH.esc(medTip) + '">медиана ответа <b>' +
                hoursText(m.median_response_hours) + '</b></span>' +
        '</button>';
    }

    function renderTiles() {
        var metrics = (state.data && state.data.metrics) || {};
        var byBar = metrics.by_bar || {};
        var html = tileHtml('', 'Вся сеть', metrics.total);
        for (var i = 0; i < GH.BARS.length; i++) {
            var b = GH.BARS[i];
            html += tileHtml(b.key, b.name, byBar[b.key]);
        }
        el.tiles.innerHTML = html;
    }

    function ratingHtml(r) {
        var f = formulas();
        if (r.rating === null || r.rating === undefined) {
            return '<span class="gh-rv-rate is-none" data-tip="' + GH.esc('Гость не поставил оценку (бывает только в боте). ' +
                'Средняя оценка считается без таких отзывов.') + '">без оценки</span>';
        }
        var n = Number(r.rating);
        var tone = RATING_TONE[n] || 'muted';
        var pips = '';
        for (var i = 1; i <= 5; i++) pips += '<i' + (i <= n ? ' class="is-on"' : '') + '></i>';
        var tip = 'Оценка ' + n + ' из 5 — ' + (RATING_WORD[tone] || '') + '.' +
            (f.rating_filter ? '\n' + f.rating_filter : '');
        return '<span class="gh-rv-rate ' + GH.toneClass(tone) + '" data-tip="' + GH.esc(tip) + '">' +
            '<span class="gh-rv-pips" aria-hidden="true">' + pips + '</span>' +
            '<b>' + n + ' из 5</b></span>';
    }

    function statusHtml(r) {
        var f = formulas();
        var now = state.data && state.data.now;
        if (r.status === 'new') {
            var h = Number(r.age_hours) || 0;
            var late = h >= WAIT_WARN_HOURS;
            var tip = 'Ждёт ответа ' + hoursText(r.age_hours) + ' = сейчас (' + fmtWhen(now) + ') − дата отзыва (' +
                fmtWhen(r.created_at) + '), по Москве.\nДо 48 ч показываются полные часы, от 48 ч — полные сутки. ' +
                'Срок ответа — 48 ч (двое суток): после него отметка оранжевая.';
            return '<span class="gh-badge ' + GH.toneClass(late ? 'warning' : 'accent') + '" data-tip="' + GH.esc(tip) + '">' +
                'без ответа ' + waitText(h) + '</span>';
        }
        if (r.status === 'answered') {
            var rh = r.response_hours;
            var rtip = (f.response_hours || 'Время ответа') + '\nЗдесь: ' + hoursText(rh) + ' = ответ (' +
                fmtWhen(r.reply && r.reply.at) + ') − отзыв (' + fmtWhen(r.created_at) + ').';
            var label = rh === null || rh === undefined ? 'отвечен'
                : (Number(rh) < 1 ? 'ответ в течение часа' : 'ответ за ' + waitText(rh));
            return '<span class="gh-badge ' + GH.toneClass('success') + '" data-tip="' + GH.esc(rtip) + '">' + label + '</span>';
        }
        return '<span class="gh-badge ' + GH.toneClass('muted') + '" data-tip="' + GH.esc(f.skipped ||
            'Без ответа по решению') + '">без ответа по решению</span>';
    }

    function menuHtml(r) {
        if (r.origin !== 'manual') return '';
        return '<div class="gh-rv-more">' +
            '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm gh-btn-icon" data-act="menu" ' +
                'aria-haspopup="menu" aria-expanded="false" aria-label="Действия с отзывом">' + DOTS_SVG + '</button>' +
            '<div class="gh-menu is-right gh-rv-menu" role="menu" hidden>' +
                '<div class="gh-menu-grab"></div>' +
                '<button type="button" class="gh-menu-item" role="menuitem" data-act="edit"><span>Изменить</span></button>' +
                '<button type="button" class="gh-menu-item is-danger" role="menuitem" data-act="delete"><span>Удалить</span></button>' +
            '</div>' +
        '</div>';
    }

    // Запрос для поиска гостя в «Маркетинге»: у телефона — последние
    // PHONE_TAIL_DIGITS цифр (почему — у константы; цифр меньше — все цифры);
    // телефона нет — Telegram как записан. Короче GUEST_QUERY_MIN знаков — ''
    // (такой запрос поиск не выполнит; ссылка тогда ведёт без него).
    function guestQuery(guest) {
        if (!guest) return '';
        var digits = String(guest.phone || '').replace(/\D/g, '');
        if (digits.length >= GUEST_QUERY_MIN) return digits.slice(-PHONE_TAIL_DIGITS);
        var tg = String(guest.telegram || '').trim();
        return tg.length >= GUEST_QUERY_MIN ? tg : '';
    }

    // Строка «Гость» под текстом отзыва. Контакт есть только у отзывов из бота
    // (телефон / Telegram) — по нему ссылка ведёт в «Маркетинг»
    // (/guests?q=<запрос>#guest: вкладка «Гость» сама подставит запрос в поиск,
    // static/js/guests/views-guest.js). Яндекс Карты контакт автора не
    // передают — об этом честно пишет приглушённая строка.
    function guestHtml(r) {
        if (r.source === 'yandex') {
            return '<p class="gh-rv-noguest">Яндекс Карты не передают контакт гостя — ' +
                'связать отзыв с карточкой гостя в «Маркетинге» нельзя.</p>';
        }
        if (r.source !== 'bot' || !r.guest) return '';
        var parts = [];
        if (r.guest.phone) {
            var tel = String(r.guest.phone).replace(/[^\d+]/g, '');
            parts.push('<a class="gh-rv-tel" href="tel:' + GH.esc(tel) + '">' + GH.esc(r.guest.phone) + '</a>');
        }
        if (r.guest.telegram) parts.push('<span class="gh-rv-tg">' + GH.esc(r.guest.telegram) + '</span>');
        if (!parts.length) return '';
        var q = guestQuery(r.guest);
        var byPhone = String(r.guest.phone || '').replace(/\D/g, '').length >= GUEST_QUERY_MIN;
        var tip = !q
            ? 'Раздел «Маркетинг», вкладка «Гость»: найдите гостя по телефону или имени и посмотрите его визиты.'
            : byPhone
                ? 'Раздел «Маркетинг», вкладка «Гость»: поиск откроется сразу по телефону гостя (последние ' +
                  PHONE_TAIL_DIGITS + ' цифр — так номер находится в базе гостей). Выберите гостя в результатах, ' +
                  'чтобы увидеть его визиты.'
                : 'Раздел «Маркетинг», вкладка «Гость»: поиск откроется по Telegram гостя. База гостей ищет по ' +
                  'телефону, карте и имени — по Telegram гость может не найтись.';
        var href = '/guests' + (q ? '?q=' + encodeURIComponent(q) : '') + '#guest';
        return '<div class="gh-rv-guest">' +
            '<span class="gh-rv-guest-cap">Гость</span>' +
            '<span class="gh-rv-guest-v">' + parts.join('<span class="gh-rv-dot" aria-hidden="true">·</span>') + '</span>' +
            '<a class="gh-link gh-rv-guest-a" href="' + GH.esc(href) + '" data-tip="' + GH.esc(tip) + '">Открыть в Маркетинге</a>' +
        '</div>';
    }

    // Связь с материалом контент-плана. material_exists приходит с сервера:
    //   true  — материал на месте: ссылка на него; второй материал из того же
    //           отзыва не сделать (сервер ответит 409);
    //   false — материал удалили в контент-плане: пометка «Материал удалён» и
    //           снова кнопка «Сделать материалом» (сервер создаст новый и
    //           перепривяжет к нему отзыв);
    //   null  — контент-план сейчас недоступен, проверить нельзя: ссылка
    //           остаётся, без ошибки; в подсказке — что проверка не удалась.
    // Поля нет (ответ старого сервера) — как true.
    function materialHtml(r) {
        var gone = '';
        if (r.material_id && r.material_exists === false) {
            gone = '<span class="gh-rv-mat-gone" data-tip="' +
                GH.esc('Материал, сделанный из этого отзыва, удалили в контент-плане. Можно сделать новый.') +
                '">Материал удалён</span>';
        } else if (r.material_id) {
            var linkTip = r.material_exists === null
                ? 'Из этого отзыва сделан материал контент-плана. Контент-план сейчас не отвечает — ' +
                  'проверить, что материал на месте, не получилось.'
                : 'Из этого отзыва уже сделан материал контент-плана. Второй из того же отзыва не сделать, ' +
                  'пока этот материал есть в плане.';
            return '<a class="gh-link gh-rv-mat" href="/content-plan?open=' + encodeURIComponent(r.material_id) + '" data-tip="' +
                GH.esc(linkTip) + '">Материал в контент-плане</a>';
        }
        if (!r.text) {
            return gone + '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-act="material" aria-disabled="true" data-tip="' +
                GH.esc('У отзыва нет текста — материал из него не сделать.') + '">Сделать материалом</button>';
        }
        return gone + '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-act="material" data-tip="' +
            GH.esc('Создать в контент-плане материал «Отзыв гостя — ' + GH.barShort(r.bar) + '» с цитатой отзыва. ' +
                'Ничего не публикуется: материал появится черновиком без даты.') + '">Сделать материалом</button>';
    }

    function draftStateHtml(id) {
        var s = state.draftState[id];
        if (!s) return '<span class="gh-save" data-save></span>';
        if (s.kind === 'saving') return '<span class="gh-save is-saving" data-save>Черновик сохраняется…</span>';
        if (s.kind === 'saved') return '<span class="gh-save is-saved" data-save>Черновик сохранён</span>';
        return '<span class="gh-save is-error" data-save title="' + GH.esc(s.msg || '') + '">Черновик не сохранён</span>';
    }

    function counterHtml(len) {
        return '<span class="gh-counter' + (len > MAX_REPLY_LEN ? ' is-over' : '') + '" data-counter data-tip="' +
            GH.esc('Лимит ответа ' + MAX_REPLY_LEN + ' знаков — с запасом внутри лимита сообщения Telegram (4096), ' +
                'чтобы ответ гостю из бота потом ушёл одним сообщением.') + '">' + len + ' / ' + MAX_REPLY_LEN + '</span>';
    }

    function historyHtml(r) {
        var out = '';
        if (r.reply && r.reply.text) {
            out += '<div class="gh-rv-hist">' +
                '<div class="gh-rv-hist-h">Прежний ответ · ' + GH.esc(r.reply.by || '') + ', ' + GH.esc(fmtWhen(r.reply.at)) +
                    ' <button type="button" class="gh-link gh-rv-hist-a" data-act="use-prev">Взять за основу</button></div>' +
                '<div class="gh-rv-hist-t">' + GH.esc(r.reply.text) + '</div>' +
            '</div>';
        }
        if (r.skip_reason) {
            out += '<div class="gh-rv-hist"><div class="gh-rv-hist-h">Раньше оставляли без ответа</div>' +
                '<div class="gh-rv-hist-t">' + GH.esc(r.skip_reason) + '</div></div>';
        }
        return out;
    }

    function replyHtml(r) {
        var id = r.id;
        if (r.status === 'new') {
            var draft = state.drafts[id] !== undefined ? state.drafts[id] : (r.reply_draft || '');
            return '<div class="gh-rv-reply">' +
                historyHtml(r) +
                '<div class="gh-rv-caprow"><span class="gh-field-cap">Ответ</span>' + draftStateHtml(id) +
                    counterHtml(draft.length) + '</div>' +
                '<textarea class="gh-textarea gh-rv-ta' + (draft ? ' is-filled' : '') + '" data-draft rows="2" maxlength="' + MAX_REPLY_LEN +
                    '" aria-label="Ответ на отзыв" placeholder="Ответ гостю. Черновик сохраняется сам.">' + TA_LEAD +
                    GH.esc(draft) + '</textarea>' +
                '<div class="gh-rv-actions">' +
                    '<button type="button" class="gh-btn gh-btn-primary gh-btn-sm" data-act="reply" data-tip="' +
                        GH.esc('Отзыв станет отвеченным (Ctrl+Enter в поле — то же самое). Ответ никуда не отправляется: ' +
                            'после сохранения скопируйте его и опубликуйте в источнике.') + '">Сохранить ответ</button>' +
                    '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-act="skip">Оставить без ответа</button>' +
                    '<span class="gh-grow"></span>' +
                    materialHtml(r) +
                '</div>' +
            '</div>';
        }
        if (r.status === 'answered' && r.reply) {
            var meta = 'Сохранил ' + (r.reply.by || '—') + ', ' + fmtWhen(r.reply.at);
            if (r.reply.edited_at) meta += ' · изменён ' + fmtWhen(r.reply.edited_at) + (r.reply.edited_by ? ' (' + r.reply.edited_by + ')' : '');
            var editing = state.editing[id] !== undefined;
            var body = editing
                ? '<textarea class="gh-textarea gh-rv-ta is-filled" data-edit rows="4" maxlength="' + MAX_REPLY_LEN +
                    '" aria-label="Правка ответа">' + TA_LEAD + GH.esc(state.editing[id]) + '</textarea>' +
                  '<div class="gh-rv-actions">' +
                    '<button type="button" class="gh-btn gh-btn-primary gh-btn-sm" data-act="save-edit">Сохранить правку</button>' +
                    '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-act="cancel-edit">Отмена</button>' +
                    '<span class="gh-grow"></span>' +
                    '<span class="gh-rv-hint">Время ответа не изменится: считается от первого сохранения.</span>' +
                  '</div>'
                : '<div class="gh-rv-reply-t">' + GH.esc(r.reply.text) + '</div>' +
                  '<p class="gh-rv-send">Отправка в источник не подключена — скопируйте ответ и опубликуйте вручную</p>' +
                  '<div class="gh-rv-actions">' +
                    '<button type="button" class="gh-btn gh-btn-sm" data-act="copy">Скопировать</button>' +
                    '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-act="edit-reply">Изменить ответ</button>' +
                    '<button type="button" class="gh-btn gh-btn-ghost gh-btn-sm" data-act="reopen">Вернуть в работу</button>' +
                    '<span class="gh-grow"></span>' +
                    materialHtml(r) +
                  '</div>';
            return '<div class="gh-rv-reply">' +
                '<div class="gh-rv-caprow"><span class="gh-field-cap">Ответ</span>' +
                    '<span class="gh-rv-reply-meta">' + GH.esc(meta) + '</span></div>' +
                body +
            '</div>';
        }
        // skipped
        return '<div class="gh-rv-reply">' +
            '<div class="gh-rv-skip"><span class="gh-field-cap">Без ответа по решению</span>' +
                '<span class="gh-rv-skip-t">' + (r.skip_reason ? 'Причина: ' + GH.esc(r.skip_reason)
                    : '<span class="gh-muted">Причина не указана</span>') + '</span></div>' +
            '<div class="gh-rv-actions">' +
                '<button type="button" class="gh-btn gh-btn-sm" data-act="reopen">Вернуть в работу</button>' +
                '<span class="gh-grow"></span>' +
                materialHtml(r) +
            '</div>' +
        '</div>';
    }

    function cardHtml(r) {
        var classes = ['gh-rv-card'];
        if (STATUS_CLASS[r.status]) classes.push(STATUS_CLASS[r.status]);
        if (r.status === 'new' && Number(r.age_hours) >= WAIT_WARN_HOURS) classes.push('is-late');
        if (state.flash === r.id) classes.push('is-flash');
        var cls = classes.join(' ');
        var added = r.origin === 'manual'
            ? 'Внесён вручную: ' + (r.added_by || '—') + ', ' + fmtWhen(r.added_at)
            : 'Загружен из источника ' + fmtWhen(r.added_at);
        var author = r.author
            ? '<span class="gh-rv-author">' + GH.esc(r.author) + '</span>'
            : '<span class="gh-rv-author is-anon">Без имени</span>';
        var text = r.text
            ? '<div class="gh-rv-text">' + GH.esc(r.text) + '</div>'
            : '<div class="gh-rv-text is-empty">Текста нет — только оценка.</div>';
        return '<article class="' + cls + '" data-id="' + GH.esc(r.id) + '">' +
            '<div class="gh-rv-top">' +
                '<div class="gh-rv-meta">' +
                    '<span class="gh-badge">' + GH.esc(sourceName(r.source)) + '</span>' +
                    '<span class="gh-rv-bar" data-tip="' + GH.esc(GH.barName(r.bar)) + '">' + GH.esc(GH.barShort(r.bar)) + '</span>' +
                    ratingHtml(r) +
                    author +
                    '<span class="gh-rv-date" data-tip="' + GH.esc('Дата отзыва, по Москве. ' + added + '.') + '">' +
                        GH.esc(fmtWhen(r.created_at)) + '</span>' +
                '</div>' +
                '<div class="gh-rv-side">' + statusHtml(r) + menuHtml(r) + '</div>' +
            '</div>' +
            text +
            guestHtml(r) +
            replyHtml(r) +
        '</article>';
    }

    function renderList() {
        GH.closeMenus();
        var reviews = (state.data && state.data.reviews) || [];
        // Фокус и курсор в поле ответа переживают перерисовку.
        var active = document.activeElement;
        var keep = null;
        if (active && el.list.contains(active) && active.tagName === 'TEXTAREA') {
            var card = active.closest('.gh-rv-card');
            keep = {
                id: card ? card.getAttribute('data-id') : null,
                attr: active.hasAttribute('data-edit') ? 'data-edit' : 'data-draft',
                start: active.selectionStart,
                end: active.selectionEnd
            };
        }
        var html = '';
        for (var i = 0; i < reviews.length; i++) html += cardHtml(reviews[i]);
        el.list.innerHTML = html;
        el.count.textContent = reviewsWord(reviews.length) + (hasListFilters() ? ' по фильтрам' : '');
        renderEmpty(reviews.length);
        if (keep && keep.id) {
            var c = cardEl(keep.id);
            var ta = c ? c.querySelector('[' + keep.attr + ']') : null;
            if (ta) {
                try { ta.focus({ preventScroll: true }); ta.setSelectionRange(keep.start, keep.end); } catch (e) { /* не критично */ }
            }
        }
        if (state.flash) {
            var flashId = state.flash;
            state.flash = null;
            setTimeout(function () {
                var c2 = cardEl(flashId);
                if (c2) c2.classList.remove('is-flash');
            }, FLASH_MS);
        }
    }

    function renderEmpty(shown) {
        if (shown || !state.data) {
            el.empty.hidden = true;
            return;
        }
        var total = (state.data.metrics && state.data.metrics.total) || {};
        var noneAtAll = !(total.count > 0) && !state.source;
        if (noneAtAll) {
            el.emptyTitle.textContent = state.all ? 'Отзывов пока нет' : 'Отзывов за период нет';
            el.emptyText.textContent = 'Подключение Яндекс Карт и бота будет позже — пока отзывы можно добавить вручную.';
        } else {
            el.emptyTitle.textContent = 'Под выбранные фильтры отзывов нет';
            el.emptyText.textContent = (state.all ? 'Отзывы есть' : 'За ' + GH.monthLabel(state.month).toLowerCase() +
                ' отзывы есть') + ', но фильтры бара, источника, оценки или статуса их скрывают.';
        }
        el.emptyReset.hidden = !hasListFilters();
        el.empty.hidden = false;
    }

    // Сколько отзывов без ответа НЕ попало в показанный месяц.
    //   другие = «Отзывы без ответа» из полосы (все даты; бар — общий фильтр)
    //            − без ответа за показанный месяц по тому же бару
    //              (metrics.by_bar[бар].unanswered или metrics.total.unanswered).
    // Считается, только когда числа сравнимы:
    //   - выбран месяц (у «За всё время» других месяцев нет);
    //   - нет фильтра источника: счётчик полосы источник не учитывает, а
    //     показатели страницы — учитывают;
    //   - ответ полосы — для того же бара, что выбран на странице;
    //   - оба ответа свежие: список не грузится, а после изменения полоса уже
    //     ответила заново (afterChange забывает прежний ответ). Иначе новое
    //     число сравнилось бы со старым и мелькнула бы ложная подсказка.
    // Фильтры оценки и статуса на расчёт не влияют: показатели страницы их не
    // учитывают. Разница меньше нуля (данные разошлись на миг) -> 0, подсказки нет.
    function elsewhereCount() {
        if (state.all || state.source || state.busy || !state.data || !state.attn) return null;
        if (state.attn.bar !== state.bar) return null;
        var total = state.attn.data && state.attn.data.reviews_unanswered;
        if (typeof total !== 'number' || !isFinite(total)) return null;
        var metrics = state.data.metrics || {};
        var m = state.bar ? (metrics.by_bar || {})[state.bar] : metrics.total;
        if (!m || typeof m.unanswered !== 'number') return null;
        return { total: total, here: m.unanswered, other: Math.max(0, total - m.unanswered) };
    }

    function renderElsewhere() {
        if (!el.elsewhere) return;
        var c = elsewhereCount();
        var n = c ? c.other : 0;
        el.elsewhere.hidden = n <= 0;
        if (n <= 0) return;
        var where = state.bar ? ', бар «' + GH.barName(state.bar) + '»' : '';
        el.elsewhereText.textContent = 'Ещё ' + n + ' ' + GH.plural(n, 'отзыв', 'отзыва', 'отзывов') +
            ' без ответа — за другие месяцы' + where + '.';
        el.elsewhere.setAttribute('data-tip', 'Без ответа за любую дату: ' + c.total +
            ' (счётчик «Отзывы без ответа» в полосе сверху). За ' + periodLabel().toLowerCase() + ' — ' + c.here +
            '. Разница ' + c.total + ' − ' + c.here + ' = ' + n + ' — отзывы других месяцев, в этом списке их нет.');
    }

    // Точечная перерисовка одной карточки (правка ответа, черновик).
    function rerenderCard(id) {
        var r = findReview(id);
        var c = cardEl(id);
        if (!r || !c) return null;
        GH.closeMenus();
        var tmp = document.createElement('div');
        tmp.innerHTML = cardHtml(r);
        var fresh = tmp.firstChild;
        c.parentNode.replaceChild(fresh, c);
        return fresh;
    }

    // ==================== меню фильтров ====================

    function menuItem(value, label, on, hint) {
        return '<button type="button" class="gh-menu-item' + (on ? ' is-on' : '') + '" role="menuitemradio" aria-checked="' +
            (on ? 'true' : 'false') + '" data-value="' + GH.esc(value) + '"><span>' + GH.esc(label) + '</span>' +
            (hint ? '<span class="gh-menu-hint">' + GH.esc(hint) + '</span>' : '') + '</button>';
    }
    function optionsMenu(cap, opts, current) {
        var html = '<div class="gh-menu-grab"></div><div class="gh-menu-cap">' + GH.esc(cap) + '</div>';
        for (var i = 0; i < opts.length; i++) {
            html += menuItem(opts[i].key, opts[i].name, opts[i].key === current, opts[i].hint);
        }
        return html;
    }

    var PICKERS = {
        month: {
            btn: 'rvMonthBtn', menu: 'rvMonthMenu',
            build: function () {
                var cur = nowInfo().month;
                var html = '<div class="gh-menu-grab"></div><div class="gh-menu-cap">Период</div>' +
                    menuItem('all', 'За всё время', state.all, 'без дат') + '<div class="gh-menu-sep"></div>';
                var seen = false;
                for (var i = 0; i < MONTH_MENU_COUNT; i++) {
                    var m = GH.addMonths(cur, -i);
                    if (m < MONTH_MIN) break;
                    var on = !state.all && m === state.month;
                    if (on) seen = true;
                    html += menuItem(m, GH.monthLabel(m), on, i === 0 ? 'текущий' : '');
                }
                if (!state.all && !seen) html += menuItem(state.month, GH.monthLabel(state.month), true, '');
                return html;
            },
            apply: function (v) {
                if (v === 'all') { state.all = true; }
                else if (validMonth(v)) { state.all = false; state.month = v; }
            }
        },
        bar: {
            btn: 'rvBarBtn', menu: 'rvBarMenu',
            build: function () {
                var opts = [{ key: '', name: 'Все бары', hint: 'вся сеть' }];
                for (var i = 0; i < GH.BARS.length; i++) {
                    opts.push({ key: GH.BARS[i].key, name: GH.BARS[i].name, hint: GH.BARS[i].short });
                }
                return optionsMenu('Бар', opts, state.bar);
            },
            apply: function (v) { state.bar = GH.setBar(v); }
        },
        source: {
            btn: 'rvSourceBtn', menu: 'rvSourceMenu',
            build: function () {
                var opts = [{ key: '', name: 'Все источники' }].concat(sources());
                return optionsMenu('Источник', opts, state.source);
            },
            apply: function (v) { state.source = v === 'yandex' || v === 'bot' ? v : ''; }
        },
        rating: {
            btn: 'rvRatingBtn', menu: 'rvRatingMenu',
            build: function () { return optionsMenu('Оценка', RATING_OPTS, state.rating); },
            apply: function (v) { state.rating = optName(RATING_OPTS, v) ? v : ''; }
        },
        status: {
            btn: 'rvStatusBtn', menu: 'rvStatusMenu',
            build: function () { return optionsMenu('Статус', STATUS_OPTS, state.status); },
            apply: function (v) { state.status = STATUS_KEYS.indexOf(v) >= 0 && v ? v : ''; }
        }
    };

    function bindPicker(name) {
        var p = PICKERS[name];
        var btn = byId(p.btn);
        var menu = byId(p.menu);
        btn.addEventListener('click', function () {
            menu.innerHTML = p.build();
            GH.toggleMenu(menu, btn);
        });
        menu.addEventListener('click', function (e) {
            var item = e.target.closest ? e.target.closest('[data-value]') : null;
            if (!item) return;
            p.apply(item.getAttribute('data-value'));
            onFiltersChanged();
        });
    }

    function onFiltersChanged() {
        syncUrl();
        renderPickers();
        load();
    }

    function shiftMonth(delta) {
        if (state.all) return;
        var m = GH.addMonths(state.month, delta);
        if (!validMonth(m) || m > nowInfo().month) return;
        state.month = m;
        onFiltersChanged();
    }

    // ==================== черновики ====================

    function setDraftState(id, kind, msg) {
        state.draftState[id] = kind ? { kind: kind, msg: msg || '' } : null;
        var c = cardEl(id);
        var node = c ? c.querySelector('[data-save]') : null;
        if (!node) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = draftStateHtml(id);
        node.parentNode.replaceChild(tmp.firstChild, node);
    }
    // Черновик уходит на сервер как набран — с пробелами и переводами строк
    // по краям: сервер его тоже не обрезает (обрезается только сам ответ при
    // «Сохранить ответ»), иначе текст, дописанный после перезагрузки,
    // приклеивался бы к прошлой фразе без пробела.
    // leaving = true — сохранение при уходе со страницы (pagehide / вкладка
    // скрыта): запрос идёт с keepalive (обычный fetch браузер обрывает вместе
    // со страницей) и СРАЗУ, мимо очереди отзыва: в очереди он ждал бы ответа
    // на предыдущий запрос, а ответа уже не будет — страница выгружается, и
    // черновик не ушёл бы вовсе. Черновик — «последний выигрывает»; ответ
    // (POST reply) в этот момент ждать не может: doReply отменяет сохранение.
    function saveDraft(id, leaving) {
        var text = state.drafts[id];
        if (text === undefined) return Promise.resolve(null);
        setDraftState(id, 'saving');
        var send = function () {
            return call('PATCH', 'item', id, { reply_draft: text }, null, leaving ? { keepalive: true } : undefined);
        };
        return (leaving ? send() : queue(id, send)).then(function (res) {
            var r = findReview(id);
            if (r && res && res.review) r.reply_draft = res.review.reply_draft;
            if (state.drafts[id] === text) setDraftState(id, 'saved');
            return res;
        }, function (err) {
            setDraftState(id, 'error', err.message);
            return null;
        });
    }
    function saver(id) {
        if (!savers[id]) savers[id] = GH.debounce(function () { return saveDraft(id); }, DRAFT_SAVE_MS);
        return savers[id];
    }
    // Уход со страницы: всё, что ждёт паузы в наборе, уходит сразу с keepalive.
    function flushAll() {
        for (var id in savers) {
            if (Object.prototype.hasOwnProperty.call(savers, id) && savers[id].pending()) {
                savers[id].cancel();
                saveDraft(id, true);
            }
        }
    }
    function updateCounter(ta) {
        var c = ta.closest('.gh-rv-card');
        var node = c ? c.querySelector('[data-counter]') : null;
        if (!node) return;
        var len = ta.value.length;
        node.textContent = len + ' / ' + MAX_REPLY_LEN;
        node.classList.toggle('is-over', len > MAX_REPLY_LEN);
    }

    // ==================== действия с отзывом ====================

    function setBusy(btn, busy) {
        if (!btn) return;
        btn.disabled = !!busy;
        btn.setAttribute('aria-busy', busy ? 'true' : 'false');
    }
    function fail(err) {
        GH.toast(err && err.message ? err.message : 'Не получилось', 'danger');
    }

    function doReply(id, text, btn) {
        if (!String(text || '').trim()) {
            GH.toast('Напишите текст ответа', 'warning');
            return;
        }
        if (savers[id]) savers[id].cancel();
        setBusy(btn, true);
        queue(id, function () {
            return call('POST', 'reply', id, { text: text });
        }).then(function () {
            delete state.drafts[id];
            delete state.draftState[id];
            delete state.editing[id];
            GH.toast('Ответ сохранён. Отправка в источник не подключена — скопируйте ответ и опубликуйте вручную.', 'success');
            afterChange(id);
        }, function (err) {
            setBusy(btn, false);
            fail(err);
        });
    }

    function doSkip(id) {
        if (savers[id]) savers[id].flush();
        GH.prompt({
            title: 'Оставить без ответа',
            text: 'Отзыв уйдёт из «Без ответа» и перестанет учитываться в доле без ответа. ' +
                'Вернуть его в работу можно в любой момент.',
            label: 'Причина (необязательно)',
            placeholder: 'Например: спам или отзыв не о нашем баре',
            multiline: true,
            ok: 'Оставить без ответа'
        }).then(function (reason) {
            if (reason === null) return;
            queue(id, function () {
                return call('POST', 'action', id, { action: 'skip', reason: reason });
            }).then(function () {
                GH.toast('Отзыв оставлен без ответа', 'muted');
                afterChange(id);
            }, fail);
        });
    }

    function doReopen(id) {
        var r = findReview(id);
        var ask = r && r.status === 'answered'
            ? GH.confirm({
                title: 'Вернуть отзыв в работу?',
                text: 'Отзыв снова попадёт в «Без ответа». Сохранённый ответ останется для истории, ' +
                    'а новый ответ заменит его — время ответа посчитается заново.',
                ok: 'Вернуть в работу'
            })
            : Promise.resolve(true);
        ask.then(function (ok) {
            if (!ok) return;
            queue(id, function () {
                return call('POST', 'action', id, { action: 'reopen' });
            }).then(function () {
                GH.toast('Отзыв снова ждёт ответа', 'accent');
                afterChange(id);
            }, fail);
        });
    }

    function materialLink(materialId, month) {
        return '/content-plan?' + (month ? 'month=' + encodeURIComponent(month) + '&' : '') +
            'open=' + encodeURIComponent(materialId);
    }

    function doMaterial(id, btn) {
        var r = findReview(id);
        if (!r || !r.text) {
            GH.toast('У отзыва нет текста — материал из него не сделать', 'warning');
            return;
        }
        setBusy(btn, true);
        call('POST', 'toMaterial', id, {}).then(function (res) {
            GH.toast('Материал «Отзыв гостя — ' + GH.barShort(r.bar) + '» создан в контент-плане черновиком', 'success', {
                actionLabel: 'Открыть в контент-плане',
                actionHref: materialLink(res.material_id, res.month)
            });
            afterChange(id);
        }, function (err) {
            setBusy(btn, false);
            if (err.status === 409 && err.data && err.data.material_id) {
                GH.toast('Материал из этого отзыва уже есть', 'muted', {
                    actionLabel: 'Открыть в контент-плане',
                    actionHref: materialLink(err.data.material_id, null)
                });
                afterChange(id);
                return;
            }
            fail(err);
        });
    }

    function doCopy(id) {
        var r = findReview(id);
        if (!r || !r.reply) return;
        GH.copyText(r.reply.text).then(function (ok) {
            GH.toast(ok ? 'Ответ скопирован — вставьте его в источнике' : 'Не удалось скопировать — выделите текст вручную',
                ok ? 'success' : 'danger');
        });
    }

    function doDelete(id) {
        var r = findReview(id);
        if (!r) return;
        GH.confirm({
            title: 'Удалить отзыв?',
            text: 'Отзыв ' + (r.author ? '«' + r.author + '» ' : '') + 'от ' + fmtWhen(r.created_at) +
                ' исчезнет из списка и из показателей. Отменить нельзя.',
            ok: 'Удалить',
            danger: true
        }).then(function (ok) {
            if (!ok) return;
            if (savers[id]) savers[id].cancel();
            queue(id, function () {
                return call('DELETE', 'item', id);
            }).then(function () {
                delete state.drafts[id];
                GH.toast('Отзыв удалён', 'muted');
                afterChange(null);
            }, fail);
        });
    }

    function startEditReply(id) {
        var r = findReview(id);
        if (!r || !r.reply) return;
        state.editing[id] = r.reply.text;
        var c = rerenderCard(id);
        var ta = c ? c.querySelector('[data-edit]') : null;
        if (ta) {
            try { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); } catch (e) { /* не критично */ }
        }
    }

    function onListClick(e) {
        var t = e.target.closest ? e.target.closest('[data-act]') : null;
        if (!t || !el.list.contains(t)) return;
        var card = t.closest('.gh-rv-card');
        var id = card ? card.getAttribute('data-id') : null;
        if (!id) return;
        var act = t.getAttribute('data-act');
        if (t.getAttribute('aria-disabled') === 'true') {
            e.preventDefault();
            if (act === 'material') GH.toast('У отзыва нет текста — материал из него не сделать', 'warning');
            return;
        }
        if (act === 'menu') {
            var menu = t.parentNode.querySelector('.gh-menu');
            if (menu) GH.toggleMenu(menu, t);
            return;
        }
        if (act === 'reply') {
            var ta = card.querySelector('[data-draft]');
            doReply(id, ta ? ta.value : '', t);
        } else if (act === 'save-edit') {
            var ed = card.querySelector('[data-edit]');
            doReply(id, ed ? ed.value : '', t);
        } else if (act === 'cancel-edit') {
            delete state.editing[id];
            rerenderCard(id);
        } else if (act === 'edit-reply') {
            startEditReply(id);
        } else if (act === 'skip') {
            doSkip(id);
        } else if (act === 'reopen') {
            doReopen(id);
        } else if (act === 'material') {
            doMaterial(id, t);
        } else if (act === 'copy') {
            doCopy(id);
        } else if (act === 'use-prev') {
            var r = findReview(id);
            var draftTa = card.querySelector('[data-draft]');
            if (r && r.reply && draftTa) {
                draftTa.value = r.reply.text;
                state.drafts[id] = draftTa.value;
                updateCounter(draftTa);
                saver(id)();
                draftTa.focus();
            }
        } else if (act === 'edit') {
            openDialog(findReview(id));
        } else if (act === 'delete') {
            doDelete(id);
        }
    }

    function onListInput(e) {
        var ta = e.target;
        if (!ta || ta.tagName !== 'TEXTAREA') return;
        var card = ta.closest('.gh-rv-card');
        var id = card ? card.getAttribute('data-id') : null;
        if (!id) return;
        updateCounter(ta);
        ta.classList.toggle('is-filled', ta.value.length > 0);
        if (ta.hasAttribute('data-draft')) {
            state.drafts[id] = ta.value;
            saver(id)();
        } else if (ta.hasAttribute('data-edit')) {
            state.editing[id] = ta.value;
        }
    }

    function onListKey(e) {
        if (e.key !== 'Enter' || !(e.ctrlKey || e.metaKey)) return;
        var ta = e.target;
        if (!ta || ta.tagName !== 'TEXTAREA') return;
        var card = ta.closest('.gh-rv-card');
        if (!card) return;
        var btn = card.querySelector(ta.hasAttribute('data-edit') ? '[data-act="save-edit"]' : '[data-act="reply"]');
        if (btn && !btn.disabled) {
            e.preventDefault();
            btn.click();
        }
    }

    function onListBlur(e) {
        var ta = e.target;
        if (!ta || !ta.hasAttribute || !ta.hasAttribute('data-draft')) return;
        var card = ta.closest('.gh-rv-card');
        var id = card ? card.getAttribute('data-id') : null;
        if (id && savers[id] && savers[id].pending()) savers[id].flush();
    }

    // ==================== диалог отзыва ====================

    function barRadiosHtml(selected) {
        var html = '';
        for (var i = 0; i < GH.BARS.length; i++) {
            var b = GH.BARS[i];
            html += '<label class="gh-check"><input type="radio" name="rvFBarRadio" value="' + GH.esc(b.key) + '"' +
                (b.key === selected ? ' checked' : '') + '><span>' + GH.esc(b.name) + '</span></label>';
        }
        return html;
    }
    function selectedBar() {
        var input = el.fBar.querySelector('input:checked');
        return input ? input.value : '';
    }

    function applySourceUi(source) {
        var bot = source === 'bot';
        el.fGuest.hidden = !bot;
        el.fRatingNone.hidden = !bot;
        if (!bot && state.dlg && state.dlg.rating === 'none') {
            state.dlg.rating = '';
            GH.setSeg(el.fRating, '');
        }
        el.fRatingHint.textContent = bot
            ? 'В боте оценка необязательна: «без оценки», если гость написал только текст.'
            : 'На Яндекс Картах отзыв без оценки не оставить — оценка обязательна.';
    }

    function updateTextCount() {
        var len = el.fText.value.length;
        el.fTextCount.textContent = len + ' / ' + MAX_TEXT_LEN;
        el.fTextCount.classList.toggle('is-over', len > MAX_TEXT_LEN);
    }

    function dialogError(msg) {
        el.dlgErr.textContent = msg || '';
        el.dlgErr.hidden = !msg;
    }

    function openDialog(review) {
        var now = nowInfo();
        var edit = !!review;
        var source = edit ? review.source : (state.source || 'yandex');
        state.dlg = {
            mode: edit ? 'edit' : 'add',
            id: edit ? review.id : null,
            origin: edit ? review.origin : 'manual',
            source: source,
            rating: edit ? (review.rating === null || review.rating === undefined ? 'none' : String(review.rating)) : ''
        };
        el.dlgTitle.textContent = edit ? 'Изменить отзыв' : 'Новый отзыв';
        el.dlgSave.textContent = edit ? 'Сохранить' : 'Добавить';
        el.dlgSave.disabled = false;
        GH.setSeg(el.fSource, source);
        var lockSource = edit && review.origin !== 'manual';
        var srcBtns = el.fSource.querySelectorAll('[data-value]');
        for (var i = 0; i < srcBtns.length; i++) srcBtns[i].disabled = lockSource;
        el.fSourceHint.hidden = !lockSource;
        el.fBar.innerHTML = barRadiosHtml(edit ? review.bar : state.bar);
        GH.setSeg(el.fRating, state.dlg.rating);
        el.fAuthor.value = edit ? (review.author || '') : '';
        var created = edit ? String(review.created_at || '') : now.datetime;
        el.fDate.value = created.slice(0, 10);
        el.fTime.value = created.slice(11, 16);
        el.fDate.max = now.date;
        el.fText.value = edit ? (review.text || '') : '';
        updateTextCount();
        var guest = edit && review.guest ? review.guest : {};
        el.fPhone.value = guest.phone || '';
        el.fTelegram.value = guest.telegram || '';
        applySourceUi(source);
        dialogError('');
        GH.openModal(el.dlg, { onClose: function () { state.dlg = null; } });
    }

    function saveDialog() {
        var dlg = state.dlg;
        if (!dlg) return;
        var date = el.fDate.value;
        var time = el.fTime.value;
        if (date && !time) { dialogError('Укажите время отзыва'); el.fTime.focus(); return; }
        if (!date && time) { dialogError('Укажите дату отзыва'); el.fDate.focus(); return; }
        var body = {
            bar: selectedBar(),
            rating: dlg.rating === '' || dlg.rating === 'none' ? null : Number(dlg.rating),
            author: el.fAuthor.value,
            text: el.fText.value
        };
        if (date && time) body.created_at = date + 'T' + time;
        else if (dlg.mode === 'edit') body.created_at = '';
        if (dlg.mode === 'add' || dlg.origin === 'manual') body.source = dlg.source;
        if (dlg.source === 'bot') body.guest = { phone: el.fPhone.value, telegram: el.fTelegram.value };
        dialogError('');
        el.dlgSave.disabled = true;
        var req = dlg.mode === 'edit'
            ? call('PATCH', 'item', dlg.id, body)
            : call('POST', 'list', null, body);
        req.then(function (res) {
            var r = res && res.review;
            GH.closeModal(el.dlg);
            var month = r && r.created_at ? r.created_at.slice(0, 7) : null;
            if (dlg.mode === 'add' && month && !state.all && month !== state.month) {
                GH.toast('Отзыв добавлен за ' + GH.monthLabel(month).toLowerCase() + ' — сейчас показан другой месяц', 'success', {
                    actionLabel: 'Показать',
                    actionHref: '/reviews?month=' + encodeURIComponent(month)
                });
            } else {
                GH.toast(dlg.mode === 'edit' ? 'Отзыв сохранён' : 'Отзыв добавлен', 'success');
            }
            afterChange(r ? r.id : null);
        }, function (err) {
            el.dlgSave.disabled = false;
            dialogError(err.message);
        });
    }

    // ==================== запуск ====================

    function init() {
        if (!GH) return;
        var ids = {
            prev: 'rvPrev', next: 'rvNext', monthBtn: 'rvMonthBtn', monthLabel: 'rvMonthLabel',
            barLabel: 'rvBarLabel', sourceLabel: 'rvSourceLabel', ratingBtn: 'rvRatingBtn',
            ratingLabel: 'rvRatingLabel', statusLabel: 'rvStatusLabel', add: 'rvAdd',
            banner: 'rvBanner', bannerText: 'rvBannerText', retry: 'rvRetry',
            scope: 'rvScope', metricsHelp: 'rvMetricsHelp', tiles: 'rvTiles',
            sortHelp: 'rvSortHelp', count: 'rvCount', msg: 'rvMsg', list: 'rvList',
            empty: 'rvEmpty', emptyTitle: 'rvEmptyTitle', emptyText: 'rvEmptyText',
            emptyReset: 'rvEmptyReset', emptyAdd: 'rvEmptyAdd',
            elsewhere: 'rvElsewhere', elsewhereText: 'rvElsewhereText', elsewhereShow: 'rvElsewhereShow',
            dlg: 'rvDlg', dlgTitle: 'rvDlgTitle', form: 'rvForm', dlgSave: 'rvDlgSave', dlgErr: 'rvDlgErr',
            fSource: 'rvFSource', fSourceHint: 'rvFSourceHint', fBar: 'rvFBar', fRating: 'rvFRating',
            fRatingNone: 'rvFRatingNone', fRatingHint: 'rvFRatingHint', fAuthor: 'rvFAuthor',
            fDate: 'rvFDate', fTime: 'rvFTime', fText: 'rvFText', fTextCount: 'rvFTextCount',
            fGuest: 'rvFGuest', fPhone: 'rvFPhone', fTelegram: 'rvFTelegram'
        };
        for (var k in ids) {
            if (Object.prototype.hasOwnProperty.call(ids, k)) el[k] = byId(ids[k]);
        }

        readUrl();
        syncUrl();
        for (var name in PICKERS) {
            if (Object.prototype.hasOwnProperty.call(PICKERS, name)) bindPicker(name);
        }
        el.prev.addEventListener('click', function () { shiftMonth(-1); });
        el.next.addEventListener('click', function () { shiftMonth(1); });
        el.add.addEventListener('click', function () { openDialog(null); });
        el.emptyAdd.addEventListener('click', function () { openDialog(null); });
        el.emptyReset.addEventListener('click', function () {
            state.source = '';
            state.rating = '';
            state.status = '';
            state.bar = GH.setBar('');
            onFiltersChanged();
        });
        el.retry.addEventListener('click', function () { load(); });
        // «Показать все без ответа»: за всё время, только без ответа. Фильтр
        // оценки снимается — число в подсказке посчитано без него.
        el.elsewhereShow.addEventListener('click', function () {
            state.all = true;
            state.status = 'new';
            state.rating = '';
            onFiltersChanged();
        });
        // Ответ полосы «требует внимания» (её грузит common.js) нужен подсказке
        // «ещё N без ответа за другие месяцы».
        GH.onAttention(function (data, bar) {
            state.attn = data ? { data: data, bar: bar } : null;
            renderElsewhere();
        });

        el.tiles.addEventListener('click', function (e) {
            var tile = e.target.closest ? e.target.closest('[data-bar]') : null;
            if (!tile) return;
            var key = tile.getAttribute('data-bar');
            // Повторный клик по выбранному бару снимает фильтр.
            state.bar = GH.setBar(key && key === state.bar ? '' : key);
            onFiltersChanged();
        });

        el.list.addEventListener('click', onListClick);
        el.list.addEventListener('input', onListInput);
        el.list.addEventListener('keydown', onListKey);
        el.list.addEventListener('focusout', onListBlur);

        GH.bindSeg(el.fSource, function (v) {
            if (!state.dlg) return;
            state.dlg.source = v;
            applySourceUi(v);
        });
        GH.bindSeg(el.fRating, function (v) {
            if (state.dlg) state.dlg.rating = v;
        });
        el.fText.addEventListener('input', updateTextCount);
        el.form.addEventListener('submit', function (e) {
            e.preventDefault();
            saveDialog();
        });

        // Черновики не теряются при уходе со страницы или сворачивании вкладки:
        // flushAll шлёт их с keepalive (см. saveDraft).
        window.addEventListener('pagehide', flushAll);
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden') flushAll();
        });

        renderPickers();
        load();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

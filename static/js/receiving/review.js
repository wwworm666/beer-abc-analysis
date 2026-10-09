/* Страница «Разбор приёмок» (/receiving/review): очередь бухгалтерии.

   Данные — GET /api/receiving/review (routes/receiving.py), решения бухгалтера —
   PUT /api/receiving/review/<gtin>, «Поиск в iiko» — GET /api/receiving/products,
   «Обновить из iiko» — POST /api/receiving/barcodes/refresh и опрос
   /api/receiving/barcodes/status, подробности приёмки — GET /api/receiving/<id>,
   «Удалить приёмку» — DELETE /api/receiving/<id>. Какие приёмки разбирать — выбор
   вверху страницы (несколько сразу, адрес ?receipt=12,15).
   Панель «Поиск в iiko» одна: открывается под строкой, которая её позвала, или под
   шапкой таблицы для поиска без строки (findInIiko, openIikoFree, closeIiko).
   Статусы, счётчики вкладок и порядок строк считает сервер
   (core/receiving_store.list_review); здесь только показ и действия — второй копии
   правил на странице нет.

   Всё, что пришло из iiko и Честного знака, попадает в DOM только через textContent
   (innerHTML в файле не используется). Экспорт для тестов — window.__rvReview
   (tests/test_receiving_review_runtime.mjs). */
(function () {
    'use strict';

    // ==================== Константы ====================

    const API_REVIEW = '/api/receiving/review';
    const API_PRODUCTS = '/api/receiving/products';
    const API_REFRESH = '/api/receiving/barcodes/refresh';
    const API_STATUS = '/api/receiving/barcodes/status';
    const API_RECEIPT = '/api/receiving/';
    // Ссылки на фото накладных отдаёт сервер; ставим в href только свои пути.
    const INVOICE_PREFIX = '/api/receiving/invoice/';

    // Шаг опроса хода обновления индекса: обновление — несколько запросов к iiko и
    // длится минуты; 4 с показывают конец почти сразу и не нагружают сервер.
    const POLL_MS = 4000;
    // Подряд неудачных опросов (нет связи, ошибка сервера), после которых опрос
    // останавливается с сообщением: 5 x 4 с = 20 с без ответа — уже не мигание сети.
    const POLL_FAIL_MAX = 5;
    // Пауза в наборе поиска перед запросом: не слать запрос на каждую букву.
    const SEARCH_DEBOUNCE_MS = 300;
    // Строк за запрос — как умолчание маршрута (200). Очередь бухгалтерии — десятки
    // строк; если больше, страница просит уточнить поиск или выбрать приёмку.
    const LIST_LIMIT = 200;
    // Результатов «Поиска в iiko» (маршрут принимает 1..100, по умолчанию 20).
    const IIKO_LIMIT = 20;
    // Минимальная длина запроса «Поиска в iiko» — как PRODUCTS_MIN_Q в маршруте.
    const IIKO_MIN_Q = 2;
    // Сколько слов названия ЧЗ подставляет «Найти в iiko»: поиск требует, чтобы ВСЕ
    // слова запроса были в имени карточки, и третье слово чаще обнуляет поиск, чем
    // уточняет его.
    const KEYWORDS_MAX = 2;
    // Слово короче 3 букв — шум (MIN_WORD_LEN в core/receiving_index.py).
    const MIN_WORD_LEN = 3;
    // Заметка — до 500 символов (NOTE_LIMIT в core/receiving_store.py).
    const NOTE_LIMIT = 500;
    // Сколько приёмок перечислить под количеством в строке; остальные — «ещё N».
    const RECEIPTS_SHOWN = 3;
    // Вернулись на вкладку позже, чем через минуту, — перечитать список: страницу
    // держат открытой часами, а приёмки закрываются в течение дня.
    const RELOAD_AFTER_MS = 60000;
    // Уведомление: обычное 4 с, ошибка 8 с — её дочитывают (как на /taps).
    const TOAST_MS = 4000;
    const TOAST_BAD_MS = 8000;
    // Уведомление с кнопкой («Вернуть» после «Сделано» и «Не нужно») — 8 с: успеть
    // нажать «Вернуть». Пока кнопка в фокусе, уведомление не прячется.
    const TOAST_ACTION_MS = 8000;
    // Колонок таблицы: позиция, кол-во, карточки iiko, поставщик и заметка, решение.
    // На всю ширину — пустая строка и строка с «Поиском в iiko» под позицией (colSpan).
    const COLS = 5;
    // Индекс старше 26 ч — утренняя сборка (07:30 МСК) не прошла: то же правило, что у
    // сервера при старте (STARTUP_MAX_AGE_HOURS = 26 в core/receiving_scheduler.py).
    // Тогда кнопка «Обновить из iiko» выделяется, а у даты индекса — пометка.
    const INDEX_STALE_MIN = 26 * 60;
    // Сколько держится надпись «Скопировано» на кнопке.
    const FLASH_MS = 1500;
    // Номера приёмок в ?receipt= — до 9 цифр каждый (как r\d{1,9} в именах фото
    // накладных), несколько через запятую: выбор приёмок для разбора.
    const RECEIPT_PARAM_RE = /(?:^\?|&)receipt=(\d{1,9}(?:,\d{1,9})*)(?:&|$)/;
    // Сколько приёмок выбрать разом — REVIEW_RECEIPTS_MAX маршрута (RECEIPT_FILTER_MAX хранилища).
    const PICK_MAX = 50;
    const POSITION_WORDS = ['позиция', 'позиции', 'позиций'];

    // Стоп-слова «похожей карточки» — копия STOP_WORDS из core/receiving_index.py
    // (паритет проверяет tests/test_receiving_review_render.mjs): общие слова
    // названий пива не помогают найти карточку, а только обнуляют поиск.
    const STOP_WORDS = new Set([
        'пиво', 'пивной', 'напиток', 'светлое', 'темное', 'полутемное',
        'фильтрованное', 'нефильтрованное', 'пастеризованное', 'непастеризованное',
        'осветленное', 'неосветленное', 'бут', 'бутылка', 'банка', 'кег', 'кега',
        'стекло', 'пэт', 'алк', 'безалкогольное',
        'светлый', 'темный', 'фильтрованный', 'нефильтрованный', 'пастеризованный',
        'непастеризованный', 'осветленный', 'неосветленный', 'безалкогольный',
        'традиционный', 'газированный', 'игристый', 'фруктовый', 'медовуха',
    ]);
    // Объём одним словом («30л», «500мл»; VOLUME_WORD_RE в индексе) в запрос «Найти в iiko»
    // не идёт: поиск ищет слова подстрокой, а объём в карточках пишут по-разному («30 л»).
    const VOLUME_WORD_RE = /^\d+(?:мл|л|ml|l)$/;

    // Вкладки: что запросить у сервера (state, status) и какой счётчик показать.
    const TABS = [
        { id: 'open', label: 'К разбору', state: 'open', status: '' },
        { id: 'new', label: 'Новые', state: 'open', status: 'new' },
        { id: 'similar', label: 'Похожие', state: 'open', status: 'similar' },
        { id: 'restore', label: 'Восстановить', state: 'open', status: 'restore' },
        { id: 'duplicate', label: 'Дубли', state: 'open', status: 'duplicate' },
        { id: 'closed', label: 'Закрытые', state: 'closed', status: '' },
        { id: 'all', label: 'Все', state: 'all', status: '' },
    ];

    const STATUS_LABELS = {
        new: 'Новая',
        similar: 'Похожая карточка',
        restore: 'Удалена или в архиве',
        duplicate: 'Дубль штрихкода',
        found: 'Есть в iiko',
    };
    // Цвет таблетки: зелёный — делать нечего, жёлтый — поправить карточку,
    // акцент — завести новую (синего в дизайн-системе нет, см. review.css).
    const STATUS_TONE = { found: 'ok', restore: 'warn', duplicate: 'warn', similar: 'warn', new: 'new' };
    const RESOLUTION_LABELS = {
        found: 'Сразу была в iiko',
        auto: 'Нашлась сама',
        done: 'Сделано',
        not_needed: 'Не нужно',
    };
    const STATE_DONE_TEXT = { done: 'Сделано', not_needed: 'Не нужно', open: 'Возвращена в разбор' };
    // Поставщика выбирают там, где карточку заводят или восстанавливают.
    const SUPPLIER_STATUSES = new Set(['new', 'similar', 'restore']);
    // «Скопировать для iiko» — там, где карточку заводят (или дописывают штрихкод).
    const COPY_STATUSES = new Set(['new', 'similar']);
    const CHZ_SOURCES = {
        cache: 'кэш сервиса',
        stock: 'выгрузка остатков ЧЗ',
        product_info: 'карточка товара ЧЗ (product/info)',
    };
    const PROCESS = {
        none: { label: 'сверка не запускалась', cls: '' },
        pending: { label: 'ждёт сверки', cls: 'is-wait' },
        running: { label: 'сверяется с iiko', cls: 'is-wait' },
        done: { label: 'сверена', cls: 'is-done' },
        error: { label: 'ошибка сверки', cls: 'is-error' },
    };
    const SCAN_REASONS = {
        empty: 'пустой код',
        too_long: 'слишком длинный код',
        unsupported: 'код не распознан',
        bad_check_digit: 'прочитан с ошибкой',
        sscc: 'код короба или паллеты',
    };

    // ==================== Состояние ====================

    const state = {
        tab: 'open',
        q: '',
        picked: [],           // выбранные приёмки: ?receipt=12,15, выбор вверху, «Показать позиции»
        loadedPicked: [],     // выбор, для которого пришёл последний ответ (receipts — по нему)
        data: null,           // последний ответ /api/receiving/review
        rows: [],
        index: null,
        job: null,
        suppliers: [],
        receipts: [],
        loading: false,
        error: '',
        loadedAt: 0,
        seq: 0,               // номер последнего запроса списка: устаревшие ответы отбрасываются
        busy: {},             // gtin -> true, пока уходит смена состояния строки
        queues: {},           // gtin -> цепочка PUT этой строки (заметка раньше «Сделано»)
        refreshStarting: false,
        polling: false,
        pollTimer: null,
        pollFails: 0,
        searchTimer: null,
        // gtin: где открыта панель «Поиск в iiko» — null закрыта, '' без строки (под
        // шапкой таблицы), GTIN — под этой строкой.
        iiko: { q: '', seq: 0, cards: null, gtin: null },
        receiptDetails: {},   // id -> {open, data, loading, failed}: подробности приёмки
        deleting: {},         // id -> true, пока уходит удаление приёмки
    };
    // Узлы, которые строятся один раз (вкладки), элементы строк по GTIN, панель «Поиск
    // в iiko» (iiko) и строка таблицы, в которой она стоит под позицией (findTr).
    // Панель держим ссылкой: отцепленный от страницы узел getElementById не находит.
    const nodes = { tabs: null, rows: {}, notes: {}, iiko: null, findTr: null };

    // ==================== Помощники ====================

    const $ = (id) => document.getElementById(id);

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function clear(node) { node.textContent = ''; }

    function plural(n, forms) {
        const abs = Math.abs(Number(n) || 0) % 100;
        const last = abs % 10;
        if (abs > 10 && abs < 20) return forms[2];
        if (last === 1) return forms[0];
        if (last >= 2 && last <= 4) return forms[1];
        return forms[2];
    }

    // Разряды — неразрывным пробелом: «12 345» не переносится по строкам.
    function fmtInt(n) {
        return String(Math.round(Number(n) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    }

    // Метки сервера уже московские (+03:00): берём цифры как есть, без Date, чтобы
    // часовой пояс браузера не сдвинул время.
    function fmtStamp(iso, withYear) {
        const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso || ''));
        if (!m) return '';
        return m[3] + '.' + m[2] + (withYear ? '.' + m[1] : '') + ' ' + m[4] + ':' + m[5];
    }

    function fmtTime(iso) {
        const m = /T(\d{2}):(\d{2})/.exec(String(iso || ''));
        return m ? m[1] + ':' + m[2] : '';
    }

    const fold = (value) => String(value || '').toLowerCase().replace(/ё/g, 'е');

    function rowTitle(row) {
        const chz = (row && row.chz) || {};
        return chz.name || chz.full_name || (row && row.barcode) || '';
    }

    async function request(method, url, body) {
        const options = {
            method: method,
            cache: 'no-store',
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        };
        if (body !== undefined) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }
        const response = await fetch(url, options);
        let data = {};
        try { data = await response.json(); } catch (error) { data = {}; }
        return { ok: response.ok, status: response.status, data: data || {} };
    }

    function errorText(res, fallback) {
        if (res.status === 401) return 'Сессия истекла — войдите снова';
        return (res.data && res.data.error) || (fallback + ' (HTTP ' + res.status + ')');
    }

    let toastTimer = null;
    // action — {label, run}: кнопка в уведомлении («Вернуть» после решения по строке).
    // Срабатывает один раз: щелчок прячет уведомление и только потом выполняет действие;
    // следующее уведомление заменяет текст вместе с кнопкой.
    function toast(text, bad, action) {
        const node = $('rvToast');
        node.textContent = text;
        node.classList.toggle('is-bad', Boolean(bad));
        if (action) {
            const button = el('button', 'rv-toast-act', action.label);
            button.type = 'button';
            let used = false;
            button.addEventListener('click', () => {
                if (used) return;
                used = true;
                clearTimeout(toastTimer);
                node.hidden = true;
                action.run();
            });
            node.appendChild(button);
        }
        node.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(hideToast, action ? TOAST_ACTION_MS : bad ? TOAST_BAD_MS : TOAST_MS);
    }

    // Кнопка уведомления в фокусе (дошли до неё клавиатурой) — подождать ещё TOAST_MS,
    // а не прятать кнопку из-под фокуса.
    function hideToast() {
        const node = $('rvToast');
        const active = document.activeElement;
        if (active && active.parentNode === node && !node.hidden) {
            toastTimer = setTimeout(hideToast, TOAST_MS);
            return;
        }
        node.hidden = true;
    }

    // Подпись кнопки возвращается к исходной, даже если нажали дважды подряд
    // (иначе вторая вспышка запоминала «Скопировано» как исходную, ревью 2026-10-03).
    function flash(button, label) {
        if (!button.dataset.label) button.dataset.label = button.textContent;
        clearTimeout(button.flashTimer);
        button.textContent = label;
        button.flashTimer = setTimeout(() => { button.textContent = button.dataset.label; }, FLASH_MS);
    }

    function showError(text) {
        state.error = text || '';
        const node = $('rvError');
        node.textContent = state.error;
        node.hidden = !state.error;
    }

    function scrollToNode(node) {
        if (node && typeof node.scrollIntoView === 'function') {
            node.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    // ==================== Загрузка списка ====================

    function tabById(id) {
        return TABS.find((tab) => tab.id === id) || TABS[0];
    }

    function listUrl() {
        const tab = tabById(state.tab);
        const params = ['state=' + tab.state];
        if (tab.status) params.push('status=' + tab.status);
        if (state.picked.length) params.push('receipt_id=' + state.picked.join(','));
        if (state.q) params.push('q=' + encodeURIComponent(state.q));
        params.push('limit=' + LIST_LIMIT);
        return API_REVIEW + '?' + params.join('&');
    }

    function applyData(data) {
        state.data = data;
        state.rows = Array.isArray(data.rows) ? data.rows : [];
        state.index = data.index || null;
        state.job = data.job || null;
        state.suppliers = Array.isArray(data.suppliers) ? data.suppliers : [];
        state.receipts = Array.isArray(data.receipts) ? data.receipts : [];
    }

    // Фильтр, сменённый во время загрузки, не теряется: каждый запрос получает номер,
    // ответ на устаревший запрос отбрасывается (docs/lessons.md).
    async function load() {
        const seq = ++state.seq;
        const picked = state.picked.slice();
        state.loading = true;
        renderCount();
        let res;
        try {
            res = await request('GET', listUrl());
        } catch (error) {
            if (seq !== state.seq) return;
            state.loading = false;
            showError('Нет связи с сервером — список не обновлён');
            renderCount();
            if (!state.data) renderRows();
            return;
        }
        if (seq !== state.seq) return;
        state.loading = false;
        if (!res.ok) {
            showError(errorText(res, 'Не удалось загрузить разбор'));
            renderCount();
            if (!state.data) renderRows();
            return;
        }
        showError('');
        state.loadedAt = Date.now();
        // Заметка, которую сейчас набирают, переживает автообновление списка (конец
        // обновления индекса, возврат на вкладку): текст и фокус возвращаются в новую
        // строку, сохранится она как обычно — по уходу из поля (ревью 2026-10-03).
        const typing = draftNotes();
        applyData(res.data);
        state.loadedPicked = picked;
        render();
        restoreNotes(typing);
        // Индекс обновляет кто-то другой (утреннее обновление, вторая вкладка, закрытие
        // приёмки) — показываем ход и перечитаем список, когда закончится.
        if (state.job && state.job.running) startPolling();
    }

    // ==================== Рендер ====================

    function render() {
        renderIndex();
        renderPicker();
        renderTabs();
        renderCount();
        renderRows();
        renderReceipts();
    }

    // Индекс iiko: 'missing' — не собран, 'stale' — старше INDEX_STALE_MIN, иначе 'ok'.
    // Возраст неизвестен (age_minutes null) — 'ok': без даты сборки индекс уже 'missing'.
    function indexState() {
        const info = state.index;
        if (!info || !info.built_at) return 'missing';
        const age = Number(info.age_minutes);
        return Number.isFinite(age) && age > INDEX_STALE_MIN ? 'stale' : 'ok';
    }

    function renderIndex() {
        const node = $('rvIndex');
        const info = state.index;
        const mode = indexState();
        if (mode !== 'missing') {
            const products = (info.counts && info.counts.products) || 0;
            node.textContent = 'Индекс iiko: ' + fmtStamp(info.built_at, true) + ', '
                + fmtInt(products) + ' ' + plural(products, ['карточка', 'карточки', 'карточек'])
                + (mode === 'stale' ? ' — утреннее обновление не прошло' : '');
        } else {
            node.textContent = 'Индекс iiko ещё не собран — нажмите «Обновить из iiko»';
        }
        node.classList.toggle('is-missing', mode === 'missing');
        node.classList.toggle('is-stale', mode === 'stale');
        renderIndexDiag();
        renderJob();
    }

    // Диагностика индекса — внутри «Как считается» шапки таблицы.
    function renderIndexDiag() {
        const node = $('rvIndexDiag');
        if (!node) return;
        const info = state.index;
        if (!info || !info.counts) { node.textContent = ''; return; }
        const c = info.counts;
        const parts = [
            'В индексе ' + fmtInt(c.products) + ' ' + plural(c.products, ['карточка', 'карточки', 'карточек'])
                + ', со штрихкодом ' + fmtInt(c.with_barcodes),
            'разных штрихкодов ' + fmtInt(c.gtins),
            'удалённых ' + fmtInt(c.deleted) + ', в архиве ' + fmtInt(c.archived),
            'штрихкодов на двух и более актуальных карточках ' + fmtInt(c.duplicates),
        ];
        const source = info.source === 'v2+xml'
            ? 'штрихкоды из XML-выгрузки номенклатуры iiko'
            : 'штрихкоды из API номенклатуры iiko';
        node.textContent = parts.join('; ') + '. Источник: ' + source + '.';
    }

    function renderJob() {
        const node = $('rvJob');
        const job = state.job || {};
        const running = Boolean(state.polling || job.running);
        let text = '';
        let bad = false;
        if (running) {
            text = 'Обновляется из iiko' + (job.started_at ? ' с ' + fmtTime(job.started_at) : '')
                + ' — список перечитается сам';
        } else if (job.error) {
            text = 'Последнее обновление не удалось'
                + (job.finished_at ? ' (' + fmtStamp(job.finished_at) + ')' : '') + ': ' + job.error;
            bad = true;
        }
        node.textContent = text;
        node.hidden = !text;
        node.classList.toggle('is-bad', bad);

        const busy = running || state.refreshStarting;
        // Кнопка нужна редко (индекс собирается сам) и обычно тихая; выделяется цветом,
        // когда без неё не обойтись: индекса нет, он устарел или обновление не удалось.
        const urgent = !busy && (indexState() !== 'ok' || Boolean(job.error));
        const button = $('rvRefresh');
        button.disabled = busy;
        button.classList.toggle('is-busy', busy);
        button.classList.toggle('rv-btn-primary', urgent);
        button.classList.toggle('rv-btn-ghost', !urgent);
        $('rvRefreshLabel').textContent = busy ? 'Обновляем...' : 'Обновить из iiko';
    }

    function tabCounts() {
        const c = state.data && state.data.counts;
        if (!c) return {};
        const open = c.open || {};
        const openTotal = c.open_total || 0;
        const closedTotal = c.closed_total || 0;
        return {
            open: openTotal,
            new: open.new || 0,
            similar: open.similar || 0,
            restore: open.restore || 0,
            duplicate: open.duplicate || 0,
            closed: closedTotal,
            all: openTotal + closedTotal,
        };
    }

    function renderTabs() {
        const box = $('rvTabs');
        if (!nodes.tabs) {
            nodes.tabs = {};
            TABS.forEach((tab) => {
                const button = el('button', 'rv-tab');
                button.type = 'button';
                button.dataset.tab = tab.id;
                button.appendChild(el('span', '', tab.label));
                const count = el('span', 'rv-tab-n', '');
                button.appendChild(count);
                button.addEventListener('click', () => setTab(tab.id));
                box.appendChild(button);
                nodes.tabs[tab.id] = { button: button, count: count };
            });
        }
        const counts = tabCounts();
        TABS.forEach((tab) => {
            const item = nodes.tabs[tab.id];
            const active = tab.id === state.tab;
            item.button.classList.toggle('is-active', active);
            item.button.setAttribute('aria-pressed', active ? 'true' : 'false');
            const n = counts[tab.id];
            item.count.textContent = n === undefined ? '' : fmtInt(n);
            item.count.classList.toggle('has-items', Boolean(n));
        });
    }

    // ==================== Выбор приёмок ====================

    function pickedHas(id) {
        return state.picked.indexOf(Number(id)) !== -1;
    }

    // Приёмку есть что разбирать: закрыта, позиции есть, а разобрана не полностью
    // (сервер: reviewed=false — сверка не прошла, строки не заведены или есть открытые).
    function needsReview(r) {
        return Boolean(r) && r.status === 'closed' && !r.reviewed && Number((r.counts || {}).gtins) > 0;
    }

    // Подпись на приёмке в выборе: сколько её позиций ещё к разбору или почему их не видно.
    // Приёмку выбрали после последнего ответа сервера (ещё грузится или загрузка не
    // удалась) — её данных нет не потому, что её нет.
    function pickedLoaded(id) {
        return Boolean(state.data) && state.loadedPicked.indexOf(Number(id)) !== -1;
    }

    function pickNote(r, id) {
        if (!r) return pickedLoaded(id) ? { text: 'не найдена', cls: 'is-error' } : { text: '', cls: '' };
        if (r.status !== 'closed') return { text: 'не завершена', cls: 'is-wait' };
        if (r.process_state === 'error') return { text: 'ошибка сверки', cls: 'is-error' };
        if (r.process_state !== 'done') return { text: 'сверяется', cls: 'is-wait' };
        if (r.reviewed || !Number((r.counts || {}).gtins)) return { text: 'разобрана', cls: '' };
        return { text: fmtInt((r.review || {}).open) + ' к разбору', cls: '' };
    }

    function pickNode(id, r) {
        const on = pickedHas(id);
        const button = el('button', 'rv-chip' + (on ? ' is-on' : ''));
        button.type = 'button';
        button.dataset.receipt = String(id);
        button.setAttribute('aria-pressed', on ? 'true' : 'false');
        const day = r ? fmtStamp(r.closed_at || r.created_at).slice(0, 5) : '';
        button.appendChild(el('span', '', '№' + id + (day ? ' · ' + day : '')));
        const note = pickNote(r, id);
        button.appendChild(el('span', 'rv-chip-n' + (note.cls ? ' ' + note.cls : ''), note.text));
        if (r) {
            const c = r.counts || {};
            button.title = 'Приёмка №' + id + ': ' + [fmtStamp(r.closed_at || r.created_at), r.closed_by || r.created_by]
                .filter(Boolean).join(', ') + '; ' + fmtInt(c.units) + ' шт., ' + fmtInt(c.gtins) + ' '
                + plural(c.gtins, POSITION_WORDS);
        }
        button.addEventListener('click', () => togglePick(id));
        return button;
    }

    function renderPicker() {
        const box = $('rvPickList');
        // Чипы строятся заново: фокус клавиатуры возвращается на тот же чип (как у заметок).
        const active = document.activeElement;
        const focusKey = active && active.parentNode === box && active.dataset ? active.dataset.receipt : null;
        clear(box);
        const known = {};
        state.receipts.forEach((r) => { known[Number(r.id)] = r; });
        const ids = state.receipts.filter((r) => needsReview(r) || pickedHas(r.id)).map((r) => Number(r.id));
        state.picked.forEach((id) => { if (ids.indexOf(id) === -1) ids.push(id); });

        const all = el('button', 'rv-chip' + (state.picked.length ? '' : ' is-on'), 'Все приёмки');
        all.type = 'button';
        all.dataset.receipt = 'all';
        all.setAttribute('aria-pressed', state.picked.length ? 'false' : 'true');
        all.addEventListener('click', () => setPicked([]));
        box.appendChild(all);
        ids.forEach((id) => box.appendChild(pickNode(id, known[id] || null)));
        if (focusKey) {
            const again = box.children ? Array.prototype.find.call(box.children, (n) => n.dataset && n.dataset.receipt === focusKey) : null;
            // preventScroll: автообновление списка (возврат во вкладку, конец обновления
            // индекса) не прокручивает страницу обратно к чипу (ревью 2026-10-04).
            if (again && typeof again.focus === 'function') again.focus({ preventScroll: true });
        }

        const waiting = state.receipts.filter(needsReview).length;
        let sub = '';
        if (state.picked.length === 1) {
            sub = 'выбрана приёмка №' + state.picked[0] + ' — показаны только её позиции';
        } else if (state.picked.length) {
            sub = 'выбрано приёмок: ' + state.picked.length + ' — показаны только их позиции';
        } else if (state.data) {
            sub = waiting ? 'неразобранных ' + fmtInt(waiting) : 'неразобранных приёмок нет';
        }
        $('rvPickSub').textContent = sub;
        renderPickPhotos();
    }

    // Выбрана ровно одна приёмка (ссылка из Telegram, «Показать позиции») — под выбором
    // строка с фото её накладной: по накладной бухгалтер выбирает поставщика, и ради
    // неё не надо листать до «Истории приёмок». Подробности приёмки — общий загрузчик
    // с «Историей приёмок» (loadReceiptDetails: один запрос на приёмку).
    function renderPickPhotos() {
        const node = $('rvPickPhotos');
        clear(node);
        const id = state.picked.length === 1 ? state.picked[0] : 0;
        const r = id ? state.receipts.find((x) => Number(x.id) === id) : null;
        if (!r) {
            node.hidden = true;
            return;
        }
        node.hidden = false;
        const label = 'Накладная №' + id + ':';
        const entry = state.receiptDetails[id];
        const links = entry && entry.data ? invoiceLinks(entry.data, false) : [];
        if (!Number((r.counts || {}).invoices) || (entry && entry.data && !links.length)) {
            node.appendChild(el('span', 'rv-muted', 'Фото накладной в приёмке №' + id + ' нет'));
        } else if (links.length) {
            node.appendChild(el('span', '', label));
            links.forEach((link) => node.appendChild(link));
        } else if (entry && entry.failed && !entry.loading) {
            node.appendChild(el('span', '', label + ' не загрузилась'));
        } else {
            node.appendChild(el('span', '', label + ' загрузка...'));
            loadReceiptDetails(id);
        }
    }

    function renderCount() {
        const node = $('rvCount');
        if (state.loading) { node.textContent = 'Загрузка...'; return; }
        if (!state.data) { node.textContent = ''; return; }
        const total = Number(state.data.total) || 0;
        const shown = state.rows.length;
        node.textContent = (total > shown ? fmtInt(shown) + ' из ' : '') + fmtInt(total) + ' '
            + plural(total, ['строка', 'строки', 'строк']);
    }

    function emptyText() {
        if (!state.data) return state.error ? 'Список не загружен' : 'Загрузка...';
        if (state.q) return 'По запросу «' + state.q + '» ничего не нашлось';
        const reason = pickedReason();
        if (reason) return reason;
        let scope = '';
        if (state.picked.length === 1) scope = 'В приёмке №' + state.picked[0] + ' ';
        else if (state.picked.length > 1) scope = 'В выбранных приёмках ';
        if (state.tab === 'closed') return (scope || 'Пока ') + 'закрытых строк нет';
        if (state.tab === 'all') {
            return scope ? scope + 'строк разбора нет'
                : 'Строк разбора пока нет: они появляются после закрытия приёмки';
        }
        const tab = tabById(state.tab);
        if (tab.status) return (scope || '') + 'Строк со статусом «' + STATUS_LABELS[tab.status] + '» нет';
        const nothing = 'разбирать нечего: всё принятое есть в iiko';
        return scope ? scope + nothing : 'Р' + nothing.slice(1);
    }

    // Пустая таблица по выбранным приёмкам: их строк нет, потому что сверка ещё идёт или
    // не прошла, приёмка не завершена или её нет, — а не потому, что «всё есть в iiko».
    function pickedReason() {
        if (!state.picked.length) return '';
        const known = {};
        state.receipts.forEach((r) => { known[Number(r.id)] = r; });
        const notes = [];
        state.picked.forEach((id) => {
            const r = known[id];
            if (!r) {
                if (pickedLoaded(id)) notes.push('Приёмки №' + id + ' нет — удалена или номер неверный');
            } else if (r.status !== 'closed') {
                notes.push('Приёмка №' + id + ' ещё не завершена');
            } else if (r.process_state === 'error') {
                notes.push('Сверка приёмки №' + id + ' с iiko не прошла' + (r.process_note ? ': ' + r.process_note : ''));
            } else if (r.process_state !== 'done') {
                notes.push('Приёмка №' + id + ' ещё сверяется с iiko — позиции появятся после сверки');
            }
        });
        return notes.join('. ');
    }

    function renderRows() {
        const body = $('rvRows');
        const query = $('rvIikoQ');
        // Запрос «Поиска в iiko» набирают прямо сейчас — после перерисовки фокус вернётся
        // в то же поле (узел тот же, текст в нём остаётся).
        const wasTyping = document.activeElement === query;
        // Панель «Поиск в iiko» — домой до очистки таблицы: иначе она уйдёт из страницы
        // вместе со строкой под позицией (ниже она встанет под свою строку снова). Уже
        // дома — не трогаем: перенос узла снимает фокус с поля.
        const home = $('rvIikoHome');
        if (nodes.iiko.parentNode !== home) home.appendChild(nodes.iiko);
        clear(body);
        nodes.findTr = null;
        nodes.rows = {};
        nodes.notes = {};
        if (!state.rows.length) {
            const tr = el('tr', 'rv-tr-empty');
            const td = el('td');
            td.colSpan = COLS;
            td.appendChild(el('div', 'rv-empty', emptyText()));
            tr.appendChild(td);
            body.appendChild(tr);
        } else {
            state.rows.forEach((row) => {
                body.appendChild(rowNode(row));
                if (row.gtin === state.iiko.gtin) {
                    nodes.findTr = findDrawer();
                    body.appendChild(nodes.findTr);
                }
            });
        }
        // Строка, под которой стоял поиск, ушла из списка («Сделано», другая вкладка,
        // её закрыл другой бухгалтер) — поиск закрывается вместе с ней.
        if (state.iiko.gtin && !nodes.findTr) closeIiko(false);
        if (wasTyping && !nodes.iiko.hidden && typeof query.focus === 'function') query.focus({ preventScroll: true });
        const more = $('rvMore');
        const total = state.data ? Number(state.data.total) || 0 : 0;
        if (total > state.rows.length) {
            more.textContent = 'Показаны первые ' + fmtInt(state.rows.length) + ' из ' + fmtInt(total)
                + ' — уточните поиск или выберите приёмку';
            more.hidden = false;
        } else {
            more.textContent = '';
            more.hidden = true;
        }
    }

    // Пять колонок: позиция (статус, название, коды, «Найти в iiko»), кол-во, карточки
    // iiko, поставщик и заметка, решение. Классы на каждой ячейке — не для красоты: на
    // телефоне строка таблицы становится карточкой (review.css), и раскладка адресует
    // ячейки по смыслу, а не по nth-child.
    function rowNode(row) {
        const tr = el('tr', 'rv-row');
        tr.dataset.gtin = row.gtin;
        if (row.state === 'closed') tr.classList.add('is-closed');
        if (state.iiko.gtin === row.gtin) tr.classList.add('is-finding');
        nodes.rows[row.gtin] = { tr: tr, actions: [], find: null };
        tr.appendChild(positionCell(row));
        tr.appendChild(qtyCell(row));
        tr.appendChild(cardsCell(row));
        tr.appendChild(editCell(row));
        tr.appendChild(actionsCell(row));
        markBusy(row.gtin, Boolean(state.busy[row.gtin]));
        return tr;
    }

    // Верх ячейки позиции: таблетка статуса, у закрытой — чем и кем закрыта, у открытой
    // повторно — сколько раз возвращалась в разбор.
    function statusLine(row) {
        const box = el('div', 'rv-pos-top');
        box.appendChild(el('span', 'rv-pill is-' + (STATUS_TONE[row.status] || 'warn'),
            STATUS_LABELS[row.status] || row.status));
        if (row.state === 'closed') {
            const res = el('div', 'rv-res');
            res.appendChild(el('b', '', RESOLUTION_LABELS[row.resolution] || 'Закрыта'));
            const who = [row.resolved_by, fmtStamp(row.resolved_at)].filter(Boolean).join(', ');
            if (who) res.appendChild(el('span', '', ' · ' + who));
            box.appendChild(res);
        } else if (Number(row.reopened) > 0) {
            const n = Number(row.reopened);
            box.appendChild(el('div', 'rv-again', 'вернулась в разбор'
                + (n > 1 ? ': ' + n + ' ' + plural(n, ['раз', 'раза', 'раз']) : '')));
        }
        return box;
    }

    function codeNode(label, value) {
        const node = el('span', 'rv-code');
        node.appendChild(el('span', '', label + ' '));
        node.appendChild(el('b', '', value));
        return node;
    }

    function positionCell(row) {
        const td = el('td', 'rv-td-pos');
        td.appendChild(statusLine(row));
        const chz = row.chz || {};
        const name = chz.name || chz.full_name || '';
        const title = el('div', 'rv-name' + (name ? '' : ' is-none'),
            name || (row.status === 'new' ? 'нет данных ЧЗ — похожие не проверены, сначала найдите в iiko' : 'нет данных ЧЗ'));
        if (name && chz.source) title.title = 'Название из Честного знака: ' + (CHZ_SOURCES[chz.source] || chz.source);
        td.appendChild(title);
        const meta = [chz.brand, chz.product_group, chz.volume].filter(Boolean).join(' · ');
        if (meta) td.appendChild(el('div', 'rv-meta', meta));
        const codes = el('div', 'rv-codes');
        codes.appendChild(codeNode('штрихкод для iiko', row.barcode || row.gtin));
        if (row.barcode && row.barcode !== row.gtin) codes.appendChild(codeNode('GTIN', row.gtin));
        td.appendChild(codes);
        if (row.state === 'open') td.appendChild(toolsLine(row));
        return td;
    }

    function linkButton(text, action) {
        const button = el('button', 'rv-link', text);
        button.type = 'button';
        button.dataset.action = action;
        return button;
    }

    function setFindLabel(button, open) {
        button.textContent = open ? 'Скрыть поиск' : 'Найти в iiko';
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    // Инструменты открытой строки — ссылками под кодами, у всех строк на одном месте:
    // «Найти в iiko» первым (он есть у каждой открытой), «Скопировать для iiko» — там,
    // где карточку заводят. Решение по строке — отдельной колонкой справа.
    function toolsLine(row) {
        const box = el('div', 'rv-pos-acts');
        const find = linkButton('', 'find');
        find.setAttribute('aria-controls', 'rvIiko');
        setFindLabel(find, state.iiko.gtin === row.gtin);
        find.title = 'Поискать карточку в iiko по словам названия — поиск откроется под строкой';
        find.addEventListener('click', () => findInIiko(row));
        nodes.rows[row.gtin].find = find;
        box.appendChild(find);
        if (COPY_STATUSES.has(row.status)) {
            const copy = linkButton('Скопировать для iiko', 'copy');
            copy.title = 'Название, бренд, штрихкод, GTIN, поставщик, объём и группа ЧЗ построчно';
            copy.addEventListener('click', () => copyForIiko(row, copy));
            box.appendChild(copy);
        }
        return box;
    }

    function receiptLink(id, text) {
        const number = Number(id);
        const link = el('a', 'rv-rc-link', text);
        link.setAttribute('href', '/receiving/review?receipt=' + number);
        link.title = 'Показать только позиции приёмки №' + number;
        link.addEventListener('click', (event) => {
            // Ctrl/Cmd/Shift-щелчок — новая вкладка браузера, как у обычной ссылки.
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.button === 1) return;
            event.preventDefault();
            setReceipt(number, true);
        });
        return link;
    }

    function qtyCell(row) {
        const td = el('td', 'rv-td-qty');
        td.appendChild(el('div', 'rv-qty', fmtInt(row.qty) + ' шт.'));
        const receipts = Array.isArray(row.receipts) ? row.receipts : [];
        if (receipts.length) {
            const list = el('div', 'rv-rcs');
            receipts.slice(0, RECEIPTS_SHOWN).forEach((r) => {
                list.appendChild(receiptLink(r.id, '№' + Number(r.id) + ' · ' + fmtInt(r.qty) + ' шт.'));
            });
            if (receipts.length > RECEIPTS_SHOWN) {
                list.appendChild(el('span', 'rv-muted', 'ещё ' + (receipts.length - RECEIPTS_SHOWN)));
            }
            td.appendChild(list);
        }
        return td;
    }

    function flagNodes(card) {
        const out = [];
        if (card.deleted) out.push(el('span', 'rv-flag', 'удалена'));
        if (card.archived) out.push(el('span', 'rv-flag', 'в архиве'));
        if (card.keg) out.push(el('span', 'rv-flag is-plain', 'кега'));
        return out;
    }

    function cardNode(card, scored) {
        const box = el('div', 'rv-card-i');
        const head = el('div');
        head.appendChild(el('span', 'rv-card-n', card.name || 'без названия'));
        flagNodes(card).forEach((flag) => head.appendChild(flag));
        box.appendChild(head);
        const meta = [card.num ? 'арт. ' + card.num : '', card.group,
                      card.supplier ? 'поставщик ' + card.supplier : ''].filter(Boolean).join(' · ');
        if (meta) box.appendChild(el('div', 'rv-card-m', meta));
        if (scored && card.pack) {
            // Мультипак: отсканирован код упаковки, а это карточка единицы внутри неё.
            box.appendChild(el('div', 'rv-score', 'единица этой упаковки'
                + (card.pack_units ? ' (в упаковке ' + card.pack_units + ' шт.)' : '')
                + ' — привяжите штрихкод упаковки к ней фасовкой'));
        } else if (scored && card.score) {
            box.appendChild(el('div', 'rv-score', 'совпало слов: ' + card.score));
        }
        return box;
    }

    // Карточки iiko: у «похожей» — кандидаты по названию (со счётом), у остальных —
    // карточки с этим штрихкодом (удалённые и архивные помечены).
    function cardsCell(row) {
        const td = el('td', 'rv-td-cards');
        const scored = row.status === 'similar';
        const items = (scored ? row.candidates : row.cards) || [];
        if (!items.length) {
            td.appendChild(el('div', 'rv-none', row.status === 'new' ? 'карточки нет' : 'карточек нет'));
            return td;
        }
        const list = el('div', 'rv-cards');
        if (scored) list.appendChild(el('div', 'rv-card-m', 'похожие по названию:'));
        items.forEach((card) => list.appendChild(cardNode(card || {}, scored)));
        td.appendChild(list);
        return td;
    }

    function option(value, text) {
        const node = el('option', '', text);
        node.value = value;
        return node;
    }

    // «Поставщик и заметка» — одна колонка: сначала поставщик (выбор или текст), под
    // ним заметка. Первый .rv-saved ячейки — статус поставщика.
    function editCell(row) {
        const td = el('td', 'rv-td-edit');
        const box = el('div', 'rv-edit');
        box.appendChild(supplierBlock(row));
        box.appendChild(noteBlock(row));
        td.appendChild(box);
        return td;
    }

    function supplierBlock(row) {
        const box = el('div', 'rv-edit-sup');
        const editable = row.state === 'open' && SUPPLIER_STATUSES.has(row.status);
        if (!editable) {
            if (row.supplier) {
                box.appendChild(el('div', '', row.supplier));
            } else if (row.supplier_hint) {
                box.appendChild(el('div', '', row.supplier_hint));
                box.appendChild(el('div', 'rv-sup-hint', 'категория карточки iiko'));
            } else {
                box.appendChild(el('div', 'rv-none', 'не указан'));
            }
            return box;
        }
        const select = el('select', 'rv-sel');
        select.setAttribute('aria-label', 'Поставщик: ' + (rowTitle(row) || row.gtin));
        select.appendChild(option('', 'Поставщик...'));
        const names = state.suppliers.slice();
        // Выбранный раньше поставщик, которого уже нет в справочнике, всё равно виден.
        if (row.supplier && names.indexOf(row.supplier) === -1) names.unshift(row.supplier);
        names.forEach((name) => select.appendChild(option(name, name)));
        select.value = row.supplier || '';
        const status = el('div', 'rv-saved');
        status.hidden = true;
        select.addEventListener('change', () => saveSupplier(row, select, status));
        box.appendChild(select);
        if (row.supplier_hint && row.supplier_hint !== row.supplier) {
            box.appendChild(el('div', 'rv-sup-hint', 'у карточки iiko: ' + row.supplier_hint));
        }
        box.appendChild(status);
        return box;
    }

    // Незаписанные заметки: {gtin: текст} и в каком поле фокус.
    function draftNotes() {
        const out = { values: {}, focused: null };
        Object.keys(nodes.notes).forEach((gtin) => {
            const item = nodes.notes[gtin];
            const value = String(item.input.value || '');
            if (value.trim() !== (item.row.note || '')) out.values[gtin] = value;
            if (document.activeElement === item.input) out.focused = gtin;
        });
        return out;
    }

    function restoreNotes(typing) {
        Object.keys(typing.values).forEach((gtin) => {
            if (nodes.notes[gtin]) nodes.notes[gtin].input.value = typing.values[gtin];
        });
        const item = typing.focused && nodes.notes[typing.focused];
        if (item && typeof item.input.focus === 'function') item.input.focus();
    }

    function noteBlock(row) {
        const box = el('div', 'rv-edit-note');
        const input = el('input', 'rv-input rv-input-note');
        nodes.notes[row.gtin] = { input: input, row: row };
        input.type = 'text';
        input.maxLength = NOTE_LIMIT;
        input.value = row.note || '';
        input.placeholder = 'Заметка';
        input.setAttribute('aria-label', 'Заметка: ' + (rowTitle(row) || row.gtin));
        const status = el('div', 'rv-saved');
        status.hidden = true;
        // Сохраняется по уходу из поля (change), Enter — то же самое.
        input.addEventListener('change', () => saveNote(row, input, status));
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                if (typeof input.blur === 'function') input.blur();
            }
        });
        box.appendChild(input);
        box.appendChild(status);
        return box;
    }

    function actionButton(text, action, extra) {
        const button = el('button', 'rv-btn rv-btn-sm' + (extra ? ' ' + extra : ''), text);
        button.type = 'button';
        button.dataset.action = action;
        return button;
    }

    // Колонка «Решение»: у открытой строки «Сделано» и «Не нужно» столбиком, у закрытой —
    // «Вернуть в разбор». На узком экране колонка прилипает к правому краю таблицы.
    function actionsCell(row) {
        const td = el('td', 'rv-td-act');
        const box = el('div', 'rv-acts');
        const holder = nodes.rows[row.gtin];
        if (row.state === 'open') {
            const done = actionButton('Сделано', 'done', 'rv-btn-primary');
            done.title = 'Карточку завели или поправили в iiko — закрыть строку';
            done.addEventListener('click', () => setRowState(row, 'done'));
            const skip = actionButton('Не нужно', 'not_needed');
            skip.title = 'Заводить не нужно — закрыть строку, при следующих приёмках она не вернётся';
            skip.addEventListener('click', () => setRowState(row, 'not_needed'));
            box.appendChild(done);
            box.appendChild(skip);
            holder.actions.push(done, skip);
        } else {
            const back = actionButton('Вернуть в разбор', 'open');
            back.addEventListener('click', () => setRowState(row, 'open'));
            box.appendChild(back);
            holder.actions.push(back);
        }
        td.appendChild(box);
        return td;
    }

    function markBusy(gtin, busy) {
        const holder = nodes.rows[gtin];
        if (!holder) return;
        holder.tr.classList.toggle('is-busy', busy);
        holder.actions.forEach((button) => {
            button.disabled = busy;
            button.classList.toggle('is-busy', busy);
        });
    }

    // ==================== Действия со строкой ====================

    // Все PUT одной строки идут по очереди: заметка, сохранённая по уходу из поля,
    // уходит раньше щелчка «Сделано» по той же строке и не теряется.
    function enqueue(gtin, task) {
        const previous = state.queues[gtin] || Promise.resolve();
        const next = previous.then(task, task);
        state.queues[gtin] = next;
        next.then(() => { if (state.queues[gtin] === next) delete state.queues[gtin]; });
        return next;
    }

    // Обновить строку на месте: обработчики держат ссылку на объект строки.
    function mergeRow(fresh) {
        if (!fresh || !fresh.gtin) return;
        const row = state.rows.find((item) => item.gtin === fresh.gtin);
        if (row) Object.assign(row, fresh);
    }

    // -> строка с сервера или null (ошибку уже показали).
    function putRow(row, body) {
        return enqueue(row.gtin, async () => {
            let res;
            try {
                res = await request('PUT', API_REVIEW + '/' + encodeURIComponent(row.gtin), body);
            } catch (error) {
                toast('Нет связи с сервером — изменение не сохранено', true);
                return null;
            }
            if (!res.ok) {
                toast(errorText(res, 'Не удалось сохранить'), true);
                if (res.status === 404) load();
                return null;
            }
            const fresh = res.data && res.data.row;
            mergeRow(fresh);
            return fresh || null;
        });
    }

    function showSaved(node, text, bad) {
        node.textContent = text;
        node.classList.toggle('is-bad', Boolean(bad));
        node.hidden = false;
    }

    async function saveSupplier(row, select, status) {
        const previous = row.supplier || '';
        const value = select.value || '';
        if (value === previous) return;
        const fresh = await putRow(row, { supplier: value });
        if (!fresh) {
            select.value = previous;
            showSaved(status, 'не сохранено', true);
            return;
        }
        select.value = fresh.supplier || '';
        showSaved(status, fresh.supplier ? 'сохранено' : 'поставщик снят');
    }

    async function saveNote(row, input, status) {
        const value = String(input.value || '').trim().slice(0, NOTE_LIMIT);
        if (value === (row.note || '')) return;
        const fresh = await putRow(row, { note: value });
        if (!fresh) {
            showSaved(status, 'не сохранено', true);
            return;
        }
        input.value = fresh.note || '';
        showSaved(status, 'сохранено');
    }

    async function setRowState(row, value) {
        if (state.busy[row.gtin]) return;
        state.busy[row.gtin] = true;
        markBusy(row.gtin, true);
        let fresh = null;
        try {
            fresh = await putRow(row, { state: value });
        } finally {
            delete state.busy[row.gtin];
            markBusy(row.gtin, false);
        }
        if (!fresh) return;
        // Решение по ошибке отменяется из уведомления: «Вернуть» — то же, что «Вернуть в
        // разбор» на вкладке «Закрытые» (и так же снимает с приёмки отметку «разобрана»).
        const undo = value === 'open' ? null
            : { label: 'Вернуть', run: () => setRowState(fresh, 'open') };
        toast(STATE_DONE_TEXT[value] + ': ' + (rowTitle(fresh) || fresh.gtin), false, undo);
        // Строка ушла с вкладки, счётчики сменились — перечитать список целиком.
        await load();
    }

    // Текст для заведения карточки в iiko: поле на строку, пустое — без значения.
    function buildCopyText(row) {
        const chz = row.chz || {};
        const lines = [
            ['Название', chz.name || chz.full_name],
            ['Бренд', chz.brand],
            ['Штрихкод', row.barcode || row.gtin],
            ['GTIN', row.gtin],
            ['Поставщик', row.supplier || row.supplier_hint],
            ['Объём', chz.volume],
            ['Группа ЧЗ', chz.product_group],
        ];
        // Мультипак: строка про упаковку (в ЧЗ это групповая упаковка с GTIN единицы).
        if (chz.main_gtin) lines.push(['Упаковка', (chz.pack_units ? chz.pack_units + ' шт. ' : '') + 'товара GTIN ' + chz.main_gtin]);
        return lines.map((pair) => (pair[0] + ': ' + (pair[1] || '')).trim()).join('\n');
    }

    // Без HTTPS (или без разрешения) Clipboard API нет — копируем через скрытое поле.
    function fallbackCopy(text) {
        const area = el('textarea', 'rv-offscreen');
        area.value = text;
        area.setAttribute('readonly', '');
        document.body.appendChild(area);
        if (typeof area.select === 'function') area.select();
        let copied = false;
        try { copied = Boolean(document.execCommand('copy')); } catch (error) { copied = false; }
        document.body.removeChild(area);
        return copied;
    }

    function copyToClipboard(text) {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            return navigator.clipboard.writeText(text).then(() => true, () => fallbackCopy(text));
        }
        return Promise.resolve(fallbackCopy(text));
    }

    async function copyForIiko(row, button) {
        const copied = await copyToClipboard(buildCopyText(row));
        if (copied) flash(button, 'Скопировано');
        else toast('Не удалось скопировать: браузер не дал доступ к буферу обмена', true);
    }

    // Значимые слова названия — правила «похожей карточки» (core/receiving_index._name_words):
    // нижний регистр, ё -> е, знаки -> пробел, от 3 букв, не из одних цифр, без стоп-слов,
    // без повторов. Два отличия — поиск в iiko ищет слова запроса подстрокой в имени
    // карточки: объём («30л») не берётся, мягкий и твёрдый знак остаются.
    function keywords(text) {
        const words = [];
        fold(text).replace(/[^\p{L}\p{N}_\s]+/gu, ' ').split(/\s+/).forEach((word) => {
            if (word.length < MIN_WORD_LEN || /^\d+$/.test(word) || STOP_WORDS.has(word)) return;
            if (VOLUME_WORD_RE.test(word)) return;
            if (words.indexOf(word) === -1) words.push(word);
        });
        return words;
    }

    function searchQueryFor(row) {
        const chz = row.chz || {};
        const words = keywords(chz.name || chz.full_name || '').slice(0, KEYWORDS_MAX);
        return words.length ? words.join(' ') : String(row.barcode || row.gtin || '');
    }

    // ==================== Панель «Поиск в iiko» ====================

    // Мышь или тачпад: курсор сразу в поле запроса, запрос выделен — его можно сразу
    // сократить. На сенсорном экране не фокусируем: клавиатура закрыла бы результаты.
    function finePointer() {
        return typeof window.matchMedia === 'function'
            && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    }

    // Новый поиск: прежние результаты и сообщение убраны, поздний ответ прежнего
    // запроса отбрасывается (номер запроса — как у списка).
    function resetIiko() {
        ++state.iiko.seq;
        state.iiko.cards = null;
        renderIikoResults([]);
        iikoMessage('', false);
    }

    // Строка таблицы под позицией: в ней панель на всю ширину. Без data-gtin — это не
    // строка разбора.
    function findDrawer() {
        const tr = el('tr', 'rv-find-tr');
        const td = el('td', 'rv-find-td');
        td.colSpan = COLS;
        td.appendChild(nodes.iiko);
        tr.appendChild(td);
        return tr;
    }

    // «Найти в iiko» в строке: панель встаёт прямо под строку, строка и её «Сделано»
    // остаются на экране. Второй щелчок по той же строке закрывает поиск.
    function findInIiko(row) {
        if (state.iiko.gtin === row.gtin) {
            closeIiko(true);
            return Promise.resolve();
        }
        closeIiko(false);
        const holder = nodes.rows[row.gtin];
        const q = searchQueryFor(row);
        // Строки нет в таблице (вызов не из строки) — поиск без строки, под шапкой.
        state.iiko.gtin = holder ? row.gtin : '';
        resetIiko();
        const input = $('rvIikoQ');
        input.value = q;
        if (holder) {
            nodes.findTr = findDrawer();
            holder.tr.parentNode.insertBefore(nodes.findTr, holder.tr.nextSibling);
            holder.tr.classList.add('is-finding');
            if (holder.find) setFindLabel(holder.find, true);
        } else {
            $('rvIikoHome').appendChild(nodes.iiko);
            $('rvIikoOpen').setAttribute('aria-expanded', 'true');
        }
        nodes.iiko.hidden = false;
        if (finePointer() && typeof input.focus === 'function') {
            input.focus({ preventScroll: true });
            input.select();
        }
        // Одна прокрутка, пока результатов нет и панель низкая: 'nearest' сдвигает
        // страницу, только если панель не видна, — строка остаётся на экране.
        if (typeof nodes.iiko.scrollIntoView === 'function') {
            nodes.iiko.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        return searchIiko(q);
    }

    // «Поиск в iiko» над таблицей: пустая панель под шапкой, курсор в поле — поиск без
    // строки. Второй щелчок закрывает.
    function openIikoFree() {
        if (state.iiko.gtin === '') {
            closeIiko(true);
            return;
        }
        closeIiko(false);
        state.iiko.gtin = '';
        resetIiko();
        const input = $('rvIikoQ');
        input.value = '';
        $('rvIikoHome').appendChild(nodes.iiko);
        nodes.iiko.hidden = false;
        $('rvIikoOpen').setAttribute('aria-expanded', 'true');
        if (typeof input.focus === 'function') input.focus();
    }

    // Закрыть панель: она возвращается домой (под шапку) и прячется, строка под позицией
    // убирается. returnFocus — фокус на кнопку, которая её открыла («Скрыть», Esc,
    // второй щелчок); без него — когда панель закрывает сама страница.
    function closeIiko(returnFocus) {
        const gtin = state.iiko.gtin;
        if (gtin === null) return;
        const holder = gtin ? nodes.rows[gtin] : null;
        ++state.iiko.seq;
        $('rvIikoHome').appendChild(nodes.iiko);
        nodes.iiko.hidden = true;
        if (nodes.findTr && nodes.findTr.parentNode) nodes.findTr.parentNode.removeChild(nodes.findTr);
        nodes.findTr = null;
        state.iiko.gtin = null;
        if (holder) {
            holder.tr.classList.remove('is-finding');
            if (holder.find) setFindLabel(holder.find, false);
        }
        $('rvIikoOpen').setAttribute('aria-expanded', 'false');
        if (!returnFocus) return;
        const opener = gtin ? holder && holder.find : $('rvIikoOpen');
        if (opener && typeof opener.focus === 'function') opener.focus({ preventScroll: true });
    }

    // ==================== Поиск в iiko ====================

    function iikoMessage(text, bad) {
        const node = $('rvIikoMsg');
        node.textContent = text || '';
        node.classList.toggle('is-bad', Boolean(bad));
        node.hidden = !text;
    }

    function hitNode(card) {
        const box = el('div', 'rv-hit');
        const head = el('div');
        head.appendChild(el('span', 'rv-hit-n', card.name || 'без названия'));
        flagNodes(card).forEach((flag) => head.appendChild(flag));
        box.appendChild(head);
        const meta = [card.num ? 'арт. ' + card.num : '', card.group,
                      card.supplier ? 'поставщик ' + card.supplier : '',
                      card.unit ? 'ед. ' + card.unit : ''].filter(Boolean).join(' · ');
        if (meta) box.appendChild(el('div', 'rv-hit-m', meta));
        const barcodes = Array.isArray(card.barcodes) ? card.barcodes : [];
        box.appendChild(el('div', 'rv-hit-b',
            barcodes.length ? 'штрихкоды: ' + barcodes.join(', ') : 'штрихкодов нет'));
        return box;
    }

    function renderIikoResults(cards) {
        const box = $('rvIikoResults');
        clear(box);
        (cards || []).forEach((card) => box.appendChild(hitNode(card || {})));
    }

    async function searchIiko(raw) {
        const q = String(raw || '').trim();
        const seq = ++state.iiko.seq;
        if (q.length < IIKO_MIN_Q) {
            state.iiko.cards = null;
            renderIikoResults([]);
            iikoMessage('Введите хотя бы ' + IIKO_MIN_Q + ' символа', false);
            return;
        }
        iikoMessage('Ищем...', false);
        let res;
        try {
            res = await request('GET', API_PRODUCTS + '?q=' + encodeURIComponent(q) + '&limit=' + IIKO_LIMIT);
        } catch (error) {
            if (seq !== state.iiko.seq) return;
            iikoMessage('Нет связи с сервером', true);
            return;
        }
        if (seq !== state.iiko.seq) return;
        if (!res.ok) {
            state.iiko.cards = null;
            renderIikoResults([]);
            iikoMessage(errorText(res, 'Поиск не удался'), true);
            return;
        }
        const cards = Array.isArray(res.data.cards) ? res.data.cards : [];
        state.iiko.q = q;
        state.iiko.cards = cards;
        renderIikoResults(cards);
        if (!cards.length) {
            iikoMessage('Ничего не нашлось — попробуйте одно слово, артикул или штрихкод', false);
        } else if (cards.length >= IIKO_LIMIT) {
            iikoMessage('Показаны первые ' + IIKO_LIMIT + ' карточек — уточните запрос', false);
        } else {
            iikoMessage('Найдено: ' + cards.length, false);
        }
        const info = res.data.index;
        $('rvIikoInfo').textContent = info && info.built_at ? 'индекс от ' + fmtStamp(info.built_at, true) : '';
    }

    // ==================== Обновление индекса iiko ====================

    async function startRefresh() {
        if (state.polling || state.refreshStarting) return;
        state.refreshStarting = true;
        renderJob();
        let res;
        try {
            res = await request('POST', API_REFRESH);
        } catch (error) {
            state.refreshStarting = false;
            renderJob();
            toast('Нет связи с сервером — обновление не запущено', true);
            return;
        }
        state.refreshStarting = false;
        const status = res.data && res.data.status;
        if (status === 'started' || status === 'already_running') {
            const job = state.job || {};
            state.job = Object.assign({}, job, {
                running: true,
                error: '',
                started_at: job.running ? job.started_at : '',
            });
            if (status === 'already_running') toast('Индекс уже обновляется — ждём, когда закончится');
            startPolling();
            return;
        }
        state.job = Object.assign({}, state.job || {}, {
            running: false,
            error: errorText(res, 'Обновление не запустилось'),
            finished_at: '',
        });
        renderJob();
        toast(state.job.error, true);
    }

    function startPolling() {
        if (state.polling) return;
        state.polling = true;
        state.pollFails = 0;
        renderJob();
        schedulePoll();
    }

    function stopPolling() {
        state.polling = false;
        clearTimeout(state.pollTimer);
        state.pollTimer = null;
    }

    function schedulePoll() {
        clearTimeout(state.pollTimer);
        state.pollTimer = setTimeout(pollOnce, POLL_MS);
    }

    async function pollOnce() {
        state.pollTimer = null;
        if (!state.polling) return;
        let res = null;
        try { res = await request('GET', API_STATUS); } catch (error) { res = null; }
        if (!state.polling) return;
        if (!res || !res.ok) {
            state.pollFails += 1;
            if (state.pollFails >= POLL_FAIL_MAX) {
                stopPolling();
                state.job = Object.assign({}, state.job || {}, {
                    running: false,
                    error: 'не удалось узнать ход обновления — обновите страницу позже',
                    finished_at: '',
                });
                renderJob();
                return;
            }
            schedulePoll();
            return;
        }
        state.pollFails = 0;
        state.index = res.data.index || null;
        state.job = res.data.job || {};
        if (state.job.running) {
            renderIndex();
            schedulePoll();
            return;
        }
        stopPolling();
        renderIndex();
        if (state.job.error) toast('Индекс iiko не обновился: ' + state.job.error, true);
        else toast('Индекс iiko обновлён, открытые строки пересверены');
        await load();
    }

    // ==================== Фильтры ====================

    function setTab(id) {
        state.tab = tabById(id).id;
        renderTabs();
        return load();
    }

    function syncUrl() {
        if (!window.history || typeof window.history.replaceState !== 'function') return;
        const url = location.pathname + (state.picked.length ? '?receipt=' + state.picked.join(',') : '');
        try { window.history.replaceState(null, '', url); } catch (error) { /* адрес не главное */ }
    }

    // Номера без повторов, только положительные, не больше PICK_MAX.
    function cleanIds(ids) {
        const out = [];
        (ids || []).forEach((id) => {
            const number = Number(id);
            if (number > 0 && Number.isInteger(number) && out.indexOf(number) === -1 && out.length < PICK_MAX) {
                out.push(number);
            }
        });
        return out;
    }

    // Выбрать приёмки для разбора (пусто — все) и перечитать список.
    function setPicked(ids, scroll) {
        state.picked = cleanIds(ids);
        syncUrl();
        renderPicker();
        renderReceipts();
        if (scroll) scrollToNode($('rvTabs'));
        return load();
    }

    // Одна приёмка вместо выбора («Показать позиции», ссылка в строке); null — все.
    function setReceipt(id, scroll) {
        const number = Number(id);
        return setPicked(number > 0 ? [number] : [], scroll);
    }

    // Щелчок по приёмке в выборе: добавить в выбор или убрать из него.
    function togglePick(id) {
        const number = Number(id);
        if (pickedHas(number)) return setPicked(state.picked.filter((x) => x !== number));
        if (state.picked.length >= PICK_MAX) {
            toast('Разом можно выбрать не больше ' + PICK_MAX + ' приёмок', true);
            return Promise.resolve();
        }
        return setPicked(state.picked.concat([number]));
    }

    function onSearchInput() {
        clearTimeout(state.searchTimer);
        state.searchTimer = setTimeout(() => {
            state.searchTimer = null;
            const q = String($('rvSearch').value || '').trim();
            if (q === state.q) return;
            state.q = q;
            load();
        }, SEARCH_DEBOUNCE_MS);
    }

    function receiptsFromUrl() {
        const m = RECEIPT_PARAM_RE.exec(String(location.search || ''));
        return m ? cleanIds(m[1].split(',')) : [];
    }

    // ==================== История приёмок ====================

    // Прогресс разбора приёмки (сервер: review — open/closed/missing по её позициям).
    function receiptProgress(r) {
        const review = r.review;
        const total = Number((r.counts || {}).gtins) || 0;
        if (!review || !total) return '';
        if (r.reviewed) return 'разобрана';
        const parts = [];
        if (review.open) parts.push('к разбору ' + fmtInt(review.open) + ' из ' + fmtInt(total));
        if (review.missing) parts.push('не сверено ' + fmtInt(review.missing));
        return parts.join(' · ');
    }

    function deleteQuestion(r) {
        const c = r.counts || {};
        const who = [fmtStamp(r.closed_at || r.created_at), r.closed_by || r.created_by].filter(Boolean).join(', ');
        const what = [fmtInt(c.units) + ' шт.', fmtInt(c.gtins) + ' ' + plural(c.gtins, POSITION_WORDS)];
        if (c.invoices) what.push('фото накладных ' + fmtInt(c.invoices));
        return 'Удалить приёмку №' + Number(r.id) + (who ? ' (' + who + ')' : '') + '?\n\n'
            + 'Удалятся её сканы (' + what.join(', ') + ') и строки разбора, которых нет в других '
            + 'приёмках, вместе с решениями по ним. Вернуть нельзя.';
    }

    // «Удалить приёмку»: подтверждение, DELETE, затем список перечитывается.
    async function deleteReceipt(r) {
        const id = Number(r.id);
        if (state.deleting[id]) return;
        if (!window.confirm(deleteQuestion(r))) return;
        state.deleting[id] = true;
        renderReceipts();
        let res;
        try {
            res = await request('DELETE', API_RECEIPT + id);
        } catch (error) {
            delete state.deleting[id];
            renderReceipts();
            toast('Нет связи с сервером — приёмка не удалена', true);
            return;
        }
        delete state.deleting[id];
        if (res.ok || res.status === 404) {
            const rows = Number(res.data && res.data.rows_deleted) || 0;
            toast(res.ok ? 'Приёмка №' + id + ' удалена' + (rows ? '; убрано из разбора позиций: ' + fmtInt(rows) : '')
                : 'Приёмки №' + id + ' уже нет');
            delete state.receiptDetails[id];
            // Из списка — сразу: и до ответа на перечитывание, и если оно не удастся.
            state.receipts = state.receipts.filter((x) => Number(x.id) !== id);
            if (pickedHas(id)) {
                await setPicked(state.picked.filter((x) => x !== id));
                return;
            }
            renderPicker();
            renderReceipts();
            await load();
            return;
        }
        renderReceipts();
        toast(errorText(res, 'Не удалось удалить приёмку'), true);
        // 409: приёмку успели разобрать полностью — перечитать, кнопка пропадёт.
        if (res.status === 409) await load();
    }

    // Приёмка в истории — две строки: № · когда и кто · сверка · штуки и позиции; ниже
    // прогресс разбора и ссылки («Удалить приёмку» — отдельно, справа). Ошибка сверки и
    // заметка приёмщика — своими строками между ними.
    function receiptNode(r) {
        const c = r.counts || {};
        const box = el('div', 'rv-rc' + (pickedHas(r.id) ? ' is-current' : ''));
        const head = el('div', 'rv-rc-head');
        head.appendChild(el('span', 'rv-rc-no', '№' + Number(r.id)));
        const when = [fmtStamp(r.closed_at || r.created_at), r.closed_by || r.created_by].filter(Boolean).join(' · ');
        if (when) head.appendChild(el('span', 'rv-rc-when', when));
        const proc = PROCESS[r.process_state] || PROCESS.none;
        head.appendChild(el('span', 'rv-rc-proc' + (proc.cls ? ' ' + proc.cls : ''), proc.label));
        const facts = [fmtInt(c.units) + ' шт.',
                       fmtInt(c.gtins) + ' ' + plural(c.gtins, POSITION_WORDS)];
        if (c.rejected) facts.push('отклонено ' + fmtInt(c.rejected));
        if (c.repeats) facts.push('повторов ' + fmtInt(c.repeats));
        if (c.invoices) facts.push('фото накладных ' + fmtInt(c.invoices));
        head.appendChild(el('span', 'rv-rc-facts', facts.join(' · ')));
        box.appendChild(head);

        if (r.process_note) {
            box.appendChild(el('div', 'rv-rc-note' + (r.process_state === 'error' ? ' is-bad' : ''), r.process_note));
        }
        if (r.note) box.appendChild(el('div', 'rv-rc-note', 'Заметка приёмщика: ' + r.note));

        const actions = el('div', 'rv-rc-act');
        const progress = receiptProgress(r);
        if (progress) actions.appendChild(el('span', 'rv-rc-prog' + (r.reviewed ? ' is-done' : ''), progress));
        const show = el('button', 'rv-link', 'Показать позиции');
        show.type = 'button';
        show.dataset.action = 'receipt';
        show.addEventListener('click', () => setReceipt(r.id, true));
        actions.appendChild(show);
        const details = el('div', 'rv-rc-more');
        details.hidden = true;
        if (c.invoices || c.rejected) {
            const entry = state.receiptDetails[r.id];
            const more = el('button', 'rv-link', '');
            more.type = 'button';
            more.dataset.action = 'details';
            more.addEventListener('click', () => toggleReceiptDetails(r.id, details, more));
            actions.appendChild(more);
            setDetailsLabel(more, Boolean(entry && entry.open));
            if (entry && entry.open && entry.data) {
                details.hidden = false;
                renderReceiptDetails(details, entry.data);
            }
        }
        // Удалить — только завершённую, разобранную не полностью (решает сервер: can_delete).
        if (r.can_delete) {
            const busy = Boolean(state.deleting[Number(r.id)]);
            const del = el('button', 'rv-link rv-link-bad', busy ? 'Удаляем...' : 'Удалить приёмку');
            del.type = 'button';
            del.dataset.action = 'delete';
            del.disabled = busy;
            del.addEventListener('click', () => deleteReceipt(r));
            actions.appendChild(del);
        }
        box.appendChild(actions);
        box.appendChild(details);
        return box;
    }

    function setDetailsLabel(button, open) {
        button.textContent = open ? 'Скрыть фото и сканы' : 'Фото и отклонённые сканы';
    }

    function renderReceipts() {
        const box = $('rvReceipts');
        clear(box);
        if (!state.receipts.length) {
            box.appendChild(el('p', 'rv-msg', state.data ? 'Закрытых приёмок пока нет' : ''));
            return;
        }
        state.receipts.forEach((r) => box.appendChild(receiptNode(r)));
    }

    // Ссылки на фото накладных приёмки — только на свои пути (INVOICE_PREFIX), в новой
    // вкладке. withTime — подпись со временем съёмки (в «Истории приёмок»).
    function invoiceLinks(data, withTime) {
        const invoices = Array.isArray(data.invoices) ? data.invoices : [];
        const links = [];
        invoices.forEach((invoice, i) => {
            const url = String((invoice && invoice.url) || '');
            if (url.indexOf(INVOICE_PREFIX) !== 0) return;
            const link = el('a', '', 'Фото ' + (i + 1)
                + (withTime && invoice.uploaded_at ? ' · ' + fmtStamp(invoice.uploaded_at) : ''));
            link.setAttribute('href', url);
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener');
            links.push(link);
        });
        return links;
    }

    function renderReceiptDetails(holder, data) {
        clear(holder);
        const links = invoiceLinks(data, true);
        if (links.length) {
            holder.appendChild(el('div', 'rv-rc-sub', 'Фото накладных'));
            const list = el('div', 'rv-rc-photos');
            links.forEach((link) => list.appendChild(link));
            holder.appendChild(list);
        }
        const recent = Array.isArray(data.recent) ? data.recent : [];
        const rejected = recent.filter((scan) => scan && !scan.accepted && scan.reason !== 'repeat');
        if (rejected.length) {
            holder.appendChild(el('div', 'rv-rc-sub', 'Отклонённые среди последних сканов'));
            rejected.forEach((scan) => {
                const text = [fmtTime(scan.scanned_at), SCAN_REASONS[scan.reason] || 'код не распознан',
                              scan.raw_short].filter(Boolean).join(' · ');
                holder.appendChild(el('div', 'rv-rc-scan', text));
            });
        }
        if (!links.length && !rejected.length) {
            holder.appendChild(el('div', 'rv-muted', 'Фото и отклонённых сканов среди последних нет'));
        }
    }

    // Подробности приёмки (фото накладных, последние сканы) — один запрос на приёмку за
    // жизнь страницы: их ждут и строка «Накладная» под выбором приёмок, и «История
    // приёмок». Неудача запоминается (failed): строка под выбором не перезапрашивает
    // её на каждой перерисовке; retry — повтор по щелчку «Фото и отклонённые сканы».
    function loadReceiptDetails(id, retry) {
        const entry = state.receiptDetails[id] || (state.receiptDetails[id] = { open: false, data: null });
        if (entry.data || (entry.failed && !retry)) return Promise.resolve(entry);
        if (entry.loading) return entry.loading;
        entry.failed = '';
        entry.loading = (async () => {
            let res = null;
            try {
                res = await request('GET', API_RECEIPT + Number(id));
            } catch (error) {
                res = null;
            }
            entry.loading = null;
            if (res && res.ok) entry.data = res.data;
            else entry.failed = res ? errorText(res, 'Не удалось загрузить приёмку') : 'Нет связи с сервером';
            // Строка «Накладная» ждёт эту приёмку — показать фото (или что не загрузились).
            if (state.picked.length === 1 && state.picked[0] === Number(id)) renderPickPhotos();
            return entry;
        })();
        return entry.loading;
    }

    async function toggleReceiptDetails(id, holder, button) {
        const entry = state.receiptDetails[id] || (state.receiptDetails[id] = { open: false, data: null });
        entry.open = !entry.open;
        holder.hidden = !entry.open;
        setDetailsLabel(button, entry.open);
        if (!entry.open) return;
        if (entry.data) { renderReceiptDetails(holder, entry.data); return; }
        holder.textContent = 'Загрузка...';
        await loadReceiptDetails(id, true);
        if (!entry.open) return;
        if (entry.data) renderReceiptDetails(holder, entry.data);
        else holder.textContent = entry.failed;
    }

    // ==================== Старт ====================

    function init() {
        state.picked = receiptsFromUrl();
        nodes.iiko = $('rvIiko');
        $('rvSearch').addEventListener('input', onSearchInput);
        $('rvRefresh').addEventListener('click', startRefresh);
        $('rvIikoOpen').addEventListener('click', () => openIikoFree());
        $('rvIikoClose').addEventListener('click', () => closeIiko(true));
        // Esc внутри панели закрывает поиск (меню сайта ловит Esc, только когда открыто).
        nodes.iiko.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            closeIiko(true);
        });
        $('rvIikoForm').addEventListener('submit', (event) => {
            event.preventDefault();
            searchIiko($('rvIikoQ').value);
        });
        document.addEventListener('visibilitychange', () => {
            if (document.hidden || state.loading || state.polling) return;
            if (Date.now() - state.loadedAt > RELOAD_AFTER_MS) load();
        });
        render();
        load();
    }

    window.__rvReview = {
        state: state,
        render: render,
        load: load,
        setTab: setTab,
        setReceipt: setReceipt,
        setPicked: setPicked,
        togglePick: togglePick,
        deleteReceipt: deleteReceipt,
        startRefresh: startRefresh,
        searchIiko: searchIiko,
        findInIiko: findInIiko,
        openIikoFree: openIikoFree,
        closeIiko: closeIiko,
        buildCopyText: buildCopyText,
        searchQueryFor: searchQueryFor,
        keywords: keywords,
        listUrl: listUrl,
        TABS: TABS,
        STATUS_LABELS: STATUS_LABELS,
        STOP_WORDS: STOP_WORDS,
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

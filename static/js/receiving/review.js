/* Страница «Разбор приёмок» (/receiving/review): очередь бухгалтерии.

   Данные — GET /api/receiving/review (routes/receiving.py), решения бухгалтера —
   PUT /api/receiving/review/<gtin>, «Поиск в iiko» — GET /api/receiving/products,
   «Обновить из iiko» — POST /api/receiving/barcodes/refresh и опрос
   /api/receiving/barcodes/status, подробности приёмки — GET /api/receiving/<id>.
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
    // Сколько держится надпись «Скопировано» на кнопке.
    const FLASH_MS = 1500;
    // Номер приёмки в ?receipt= — до 9 цифр (как r\d{1,9} в именах фото накладных).
    const RECEIPT_PARAM_RE = /(?:^\?|&)receipt=(\d{1,9})(?:&|$)/;

    // Стоп-слова «похожей карточки» — копия STOP_WORDS из core/receiving_index.py
    // (паритет проверяет tests/test_receiving_review_render.mjs): общие слова
    // названий пива не помогают найти карточку, а только обнуляют поиск.
    const STOP_WORDS = new Set([
        'пиво', 'пивной', 'напиток', 'светлое', 'темное', 'полутемное',
        'фильтрованное', 'нефильтрованное', 'пастеризованное', 'непастеризованное',
        'осветленное', 'неосветленное', 'бут', 'бутылка', 'банка', 'кег', 'кега',
        'стекло', 'пэт', 'алк', 'безалкогольное',
    ]);

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
        receipt: null,        // номер приёмки из ?receipt= (или «Показать позиции»)
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
        iiko: { q: '', seq: 0, cards: null },
        receiptDetails: {},   // id -> {open, data}
    };
    // Узлы, которые строятся один раз (вкладки), и элементы строк по GTIN.
    const nodes = { tabs: null, rows: {} };

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
    function toast(text, bad) {
        const node = $('rvToast');
        node.textContent = text;
        node.classList.toggle('is-bad', Boolean(bad));
        node.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { node.hidden = true; }, bad ? TOAST_BAD_MS : TOAST_MS);
    }

    function flash(button, label) {
        const old = button.textContent;
        button.textContent = label;
        setTimeout(() => { button.textContent = old; }, FLASH_MS);
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
        if (state.receipt) params.push('receipt_id=' + state.receipt);
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
        applyData(res.data);
        render();
        // Индекс обновляет кто-то другой (утреннее обновление, вторая вкладка, закрытие
        // приёмки) — показываем ход и перечитаем список, когда закончится.
        if (state.job && state.job.running) startPolling();
    }

    // ==================== Рендер ====================

    function render() {
        renderIndex();
        renderTabs();
        renderFilter();
        renderCount();
        renderRows();
        renderReceipts();
    }

    function renderIndex() {
        const node = $('rvIndex');
        const info = state.index;
        if (info && info.built_at) {
            const products = (info.counts && info.counts.products) || 0;
            node.textContent = 'Индекс iiko: ' + fmtStamp(info.built_at, true) + ', '
                + fmtInt(products) + ' ' + plural(products, ['карточка', 'карточки', 'карточек']);
            node.classList.remove('is-missing');
        } else {
            node.textContent = 'Индекс iiko ещё не собран — нажмите «Обновить из iiko»';
            node.classList.add('is-missing');
        }
        renderIndexDiag();
        renderJob();
    }

    // Диагностика индекса — внутри «Как считается» шапки.
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
        const button = $('rvRefresh');
        button.disabled = busy;
        button.classList.toggle('is-busy', busy);
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

    function renderFilter() {
        $('rvReceiptChip').hidden = !state.receipt;
        $('rvReceiptLabel').textContent = state.receipt ? 'Приёмка №' + state.receipt : '';
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
        const scope = state.receipt ? 'В приёмке №' + state.receipt + ' ' : '';
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

    function renderRows() {
        const body = $('rvRows');
        clear(body);
        nodes.rows = {};
        if (!state.rows.length) {
            const tr = el('tr', 'rv-tr-empty');
            const td = el('td');
            td.colSpan = 7;
            td.appendChild(el('div', 'rv-empty', emptyText()));
            tr.appendChild(td);
            body.appendChild(tr);
        } else {
            state.rows.forEach((row) => body.appendChild(rowNode(row)));
        }
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

    // Классы на каждой ячейке — не для красоты: на телефоне строка таблицы становится
    // карточкой (review.css), и раскладка адресует ячейки по смыслу, а не по nth-child.
    function rowNode(row) {
        const tr = el('tr', 'rv-row');
        tr.dataset.gtin = row.gtin;
        if (row.state === 'closed') tr.classList.add('is-closed');
        nodes.rows[row.gtin] = { tr: tr, actions: [] };
        tr.appendChild(statusCell(row));
        tr.appendChild(positionCell(row));
        tr.appendChild(qtyCell(row));
        tr.appendChild(cardsCell(row));
        tr.appendChild(supplierCell(row));
        tr.appendChild(noteCell(row));
        tr.appendChild(actionsCell(row));
        markBusy(row.gtin, Boolean(state.busy[row.gtin]));
        return tr;
    }

    function statusCell(row) {
        const td = el('td', 'rv-td-st');
        td.appendChild(el('span', 'rv-pill is-' + (STATUS_TONE[row.status] || 'warn'),
            STATUS_LABELS[row.status] || row.status));
        if (row.state === 'closed') {
            const res = el('div', 'rv-res');
            res.appendChild(el('b', '', RESOLUTION_LABELS[row.resolution] || 'Закрыта'));
            const who = [row.resolved_by, fmtStamp(row.resolved_at)].filter(Boolean).join(', ');
            if (who) res.appendChild(el('span', '', ' · ' + who));
            td.appendChild(res);
        } else if (Number(row.reopened) > 0) {
            const n = Number(row.reopened);
            td.appendChild(el('div', 'rv-again', 'вернулась в разбор'
                + (n > 1 ? ': ' + n + ' ' + plural(n, ['раз', 'раза', 'раз']) : '')));
        }
        return td;
    }

    function codeNode(label, value) {
        const node = el('span', 'rv-code');
        node.appendChild(el('span', '', label + ' '));
        node.appendChild(el('b', '', value));
        return node;
    }

    function positionCell(row) {
        const td = el('td', 'rv-td-pos');
        const chz = row.chz || {};
        const name = chz.name || chz.full_name || '';
        const title = el('div', 'rv-name' + (name ? '' : ' is-none'), name || 'нет данных ЧЗ');
        if (name && chz.source) title.title = 'Название из Честного знака: ' + (CHZ_SOURCES[chz.source] || chz.source);
        td.appendChild(title);
        const meta = [chz.brand, chz.product_group, chz.volume].filter(Boolean).join(' · ');
        if (meta) td.appendChild(el('div', 'rv-meta', meta));
        const codes = el('div', 'rv-codes');
        codes.appendChild(codeNode('штрихкод для iiko', row.barcode || row.gtin));
        if (row.barcode && row.barcode !== row.gtin) codes.appendChild(codeNode('GTIN', row.gtin));
        td.appendChild(codes);
        return td;
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
        if (scored && card.score) box.appendChild(el('div', 'rv-score', 'совпало слов: ' + card.score));
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

    function supplierCell(row) {
        const td = el('td', 'rv-td-sup');
        const editable = row.state === 'open' && SUPPLIER_STATUSES.has(row.status);
        if (!editable) {
            if (row.supplier) {
                td.appendChild(el('div', '', row.supplier));
            } else if (row.supplier_hint) {
                td.appendChild(el('div', '', row.supplier_hint));
                td.appendChild(el('div', 'rv-sup-hint', 'категория карточки iiko'));
            } else {
                td.appendChild(el('div', 'rv-none', 'не указан'));
            }
            return td;
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
        td.appendChild(select);
        if (row.supplier_hint && row.supplier_hint !== row.supplier) {
            td.appendChild(el('div', 'rv-sup-hint', 'у карточки iiko: ' + row.supplier_hint));
        }
        td.appendChild(status);
        return td;
    }

    function noteCell(row) {
        const td = el('td', 'rv-td-note');
        const input = el('input', 'rv-input rv-input-note');
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
        td.appendChild(input);
        td.appendChild(status);
        return td;
    }

    function actionButton(text, action, extra) {
        const button = el('button', 'rv-btn rv-btn-sm' + (extra ? ' ' + extra : ''), text);
        button.type = 'button';
        button.dataset.action = action;
        return button;
    }

    function actionsCell(row) {
        const td = el('td', 'rv-td-act');
        const box = el('div', 'rv-acts');
        const holder = nodes.rows[row.gtin];
        if (row.state === 'open') {
            if (COPY_STATUSES.has(row.status)) {
                const copy = actionButton('Скопировать для iiko', 'copy');
                copy.title = 'Название, бренд, штрихкод, GTIN, поставщик, объём и группа ЧЗ построчно';
                copy.addEventListener('click', () => copyForIiko(row, copy));
                box.appendChild(copy);
            }
            const find = actionButton('Найти в iiko', 'find');
            find.title = 'Поискать карточку по словам названия в блоке «Поиск в iiko»';
            find.addEventListener('click', () => findInIiko(row));
            box.appendChild(find);
            const pair = el('div', 'rv-acts-row');
            const done = actionButton('Сделано', 'done', 'rv-btn-primary');
            done.title = 'Карточку завели или поправили в iiko — закрыть строку';
            done.addEventListener('click', () => setRowState(row, 'done'));
            const skip = actionButton('Не нужно', 'not_needed');
            skip.title = 'Заводить не нужно — закрыть строку, при следующих приёмках она не вернётся';
            skip.addEventListener('click', () => setRowState(row, 'not_needed'));
            pair.appendChild(done);
            pair.appendChild(skip);
            box.appendChild(pair);
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
        toast(STATE_DONE_TEXT[value] + ': ' + (rowTitle(fresh) || fresh.gtin));
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

    // Значимые слова названия — те же правила, что у «похожей карточки»
    // (core/receiving_index._name_words): нижний регистр, ё -> е, знаки -> пробел,
    // от 3 букв, не из одних цифр, без стоп-слов, без повторов.
    function keywords(text) {
        const words = [];
        fold(text).replace(/[^\p{L}\p{N}_\s]+/gu, ' ').split(/\s+/).forEach((word) => {
            if (word.length < MIN_WORD_LEN || /^\d+$/.test(word) || STOP_WORDS.has(word)) return;
            if (words.indexOf(word) === -1) words.push(word);
        });
        return words;
    }

    function searchQueryFor(row) {
        const chz = row.chz || {};
        const words = keywords(chz.name || chz.full_name || '').slice(0, KEYWORDS_MAX);
        return words.length ? words.join(' ') : String(row.barcode || row.gtin || '');
    }

    function findInIiko(row) {
        const q = searchQueryFor(row);
        $('rvIikoQ').value = q;
        scrollToNode($('rvIiko'));
        return searchIiko(q);
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
        const url = location.pathname + (state.receipt ? '?receipt=' + state.receipt : '');
        try { window.history.replaceState(null, '', url); } catch (error) { /* адрес не главное */ }
    }

    function setReceipt(id, scroll) {
        const number = Number(id);
        state.receipt = number > 0 ? number : null;
        syncUrl();
        renderFilter();
        renderReceipts();
        if (scroll) scrollToNode($('rvTabs'));
        return load();
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

    function receiptFromUrl() {
        const m = RECEIPT_PARAM_RE.exec(String(location.search || ''));
        const number = m ? Number(m[1]) : 0;
        return number > 0 ? number : null;
    }

    // ==================== Приёмки ====================

    function receiptNode(r) {
        const c = r.counts || {};
        const box = el('div', 'rv-rc' + (state.receipt === r.id ? ' is-current' : ''));
        const head = el('div', 'rv-rc-head');
        head.appendChild(el('span', 'rv-rc-no', '№' + Number(r.id)));
        const when = [fmtStamp(r.closed_at || r.created_at), r.closed_by || r.created_by].filter(Boolean).join(' · ');
        if (when) head.appendChild(el('span', 'rv-rc-when', when));
        const proc = PROCESS[r.process_state] || PROCESS.none;
        head.appendChild(el('span', 'rv-rc-proc' + (proc.cls ? ' ' + proc.cls : ''), proc.label));
        box.appendChild(head);

        const facts = [fmtInt(c.units) + ' шт.',
                       fmtInt(c.gtins) + ' ' + plural(c.gtins, ['позиция', 'позиции', 'позиций'])];
        if (c.rejected) facts.push('отклонено ' + fmtInt(c.rejected));
        if (c.repeats) facts.push('повторов ' + fmtInt(c.repeats));
        if (c.invoices) facts.push('фото накладных ' + fmtInt(c.invoices));
        box.appendChild(el('div', 'rv-rc-facts', facts.join(' · ')));
        if (r.process_note) {
            box.appendChild(el('div', 'rv-rc-note' + (r.process_state === 'error' ? ' is-bad' : ''), r.process_note));
        }
        if (r.note) box.appendChild(el('div', 'rv-rc-note', 'Заметка приёмщика: ' + r.note));

        const actions = el('div', 'rv-rc-act');
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

    function renderReceiptDetails(holder, data) {
        clear(holder);
        const invoices = Array.isArray(data.invoices) ? data.invoices : [];
        const links = [];
        invoices.forEach((invoice, i) => {
            const url = String((invoice && invoice.url) || '');
            if (url.indexOf(INVOICE_PREFIX) !== 0) return;
            const link = el('a', '', 'Фото ' + (i + 1)
                + (invoice.uploaded_at ? ' · ' + fmtStamp(invoice.uploaded_at) : ''));
            link.setAttribute('href', url);
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener');
            links.push(link);
        });
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

    async function toggleReceiptDetails(id, holder, button) {
        const entry = state.receiptDetails[id] || (state.receiptDetails[id] = { open: false, data: null });
        entry.open = !entry.open;
        holder.hidden = !entry.open;
        setDetailsLabel(button, entry.open);
        if (!entry.open) return;
        if (entry.data) { renderReceiptDetails(holder, entry.data); return; }
        holder.textContent = 'Загрузка...';
        let res;
        try {
            res = await request('GET', API_RECEIPT + Number(id));
        } catch (error) {
            holder.textContent = 'Нет связи с сервером';
            return;
        }
        if (!res.ok) { holder.textContent = errorText(res, 'Не удалось загрузить приёмку'); return; }
        entry.data = res.data;
        if (entry.open) renderReceiptDetails(holder, res.data);
    }

    // ==================== Старт ====================

    function init() {
        state.receipt = receiptFromUrl();
        $('rvSearch').addEventListener('input', onSearchInput);
        $('rvReceiptClear').addEventListener('click', () => setReceipt(null));
        $('rvRefresh').addEventListener('click', startRefresh);
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
        startRefresh: startRefresh,
        searchIiko: searchIiko,
        findInIiko: findInIiko,
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

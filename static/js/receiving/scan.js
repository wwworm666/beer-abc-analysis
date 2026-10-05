/* Экран приёмщика РЦ: /receiving (templates/receiving.html, static/receiving/scan.css).

   Что делает. Приёмщик открывает приёмку («Новая приёмка» или «Продолжить»),
   сканирует каждую бутылку, банку и кегу камерой телефона (или ручным сканером),
   фотографирует накладную и нажимает «Завершить» — сервер сверяет коды с iiko в
   фоне, итог разбирает бухгалтерия на /receiving/review. API — routes/receiving.py,
   документация — docs/receiving.md.

   На РЦ сканируют только телефоном (решение владельца 2026-10-03): камера — основной
   путь. Детектор кодов — встроенный BarcodeDetector или библиотека-полифил из
   static/libs (своя копия: склад не зависит от доступности CDN). Камера видит в
   кадре сразу и DataMatrix, и обычный штрихкод той же бутылки или упаковки — правила
   «штрихкод не дублирует код ЧЗ» у onCameraCode.

   Ручной сканер печатает «как клавиатура», а поля ввода на экране нет (поле в
   фокусе открыло бы клавиатуру телефона). Поэтому код собирается из keydown на
   window в фазе захвата по event.code — физической клавише, а не символу: при
   русской раскладке сканер «печатает» кириллицу, а event.code остаётся KeyA.
   Пока идёт сбор, нажатие гасится (preventDefault + stopPropagation), иначе буква
   «m» серийного номера открывала бы меню (горячая клавиша в shared/nav.html).

   Связь на складе плохая, поэтому каждый скан сначала ложится в очередь в
   localStorage (с client_id) и только потом уходит на сервер — по одному, по
   порядку. Сервер по client_id не посчитает повтор запроса дважды. Сигнал
   («принято», «уже посчитана», «не распознан») звучит сразу по разбору в браузере
   (window.RcCodes из codes.js — порт core/receiving_codes.py); ответ сервера главнее:
   если он не совпал, счётчик поправляется и звучит сигнал ещё раз.

   Окно (подтверждение «Завершить», ввод цифр) открывается и поверх камеры: «Завершить» и
   «Ввести цифры» есть в нижнем ряду камеры. Пока окно открыто, камера коды не читает
   (tickCamera смотрит на state.sheet — отдельного флага паузы нет): иначе поздний кадр
   через handleCode отменил бы завершение. «Завершить» при неотправленных сканах окно
   открывает и ждёт очередь: «Завершить приёмку» включается, когда очередь пуста, а
   приёмку закрывает только нажатие (renderFinishSheet).

   Данные в DOM попадают только через textContent (без innerHTML): коды со сканера
   и имена из базы — недоверенные строки. Для тестов наружу — window.__rcScan. */
(function () {
    'use strict';

    const root = document.getElementById('rc');
    if (!root) return;

    // ==================== Константы ====================

    const PAGE = '/receiving';
    const API = '/api/receiving';
    const REVIEW_PAGE = '/receiving/review';

    // Очередь неотправленных сканов в localStorage; v1 — формат элемента очереди.
    // Меняется формат — новый ключ (старый браузер не прочитает чужое).
    const QUEUE_KEY = 'rc.queue.v1';
    // Снимок открытой приёмки (счётчики, ключи DataMatrix, последние сканы): после
    // перезагрузки без связи экран открывается по нему, и сканировать можно дальше.
    const SNAPSHOT_KEY = 'rc.receipt.v1';

    // Сканер печатает символ за 5-30 мс; человек на клавиатуре — 100+ мс. Пауза
    // больше 80 мс при непустом буфере значит «это набор руками»: буфер начинается
    // заново, а Enter после такой паузы кодом не считается.
    const SCAN_GAP_MS = 80;
    // Короче 4 символов — случайное нажатие, а не код (самый короткий код на
    // товаре — EAN-8, 8 цифр; запас — для обрезанного чтения, чтобы оно дало
    // «не распознан», а не тишину).
    const MIN_CODE_LEN = 4;
    // Код без Enter/Tab в конце (сканер без суффикса) считается законченным после паузы
    // 300 мс: сканер печатает символы через 5-30 мс, 300 мс — уже точно конец кода.
    const SCAN_IDLE_MS = 300;
    // Сколько после такого кода глотать запоздавший Enter/Tab сканера (1 с).
    const SCAN_SWALLOW_MS = 1000;
    // Буфер не растёт бесконечно (зажатая клавиша): длиннее предела разбора
    // (MAX_CODE_LEN = 512) код всё равно «не распознан».
    const MAX_BUFFER = 513;
    const GS = '\x1d';   // разделитель групп GS1 (FNC1): сканер шлёт его как Ctrl+]

    // Повтор отправки после обрыва связи: 2, 5, 10, затем каждые 30 с (а также сразу
    // по событиям online и возврату на вкладку). Чаще — греть телефон впустую.
    const RETRY_DELAYS_MS = [2000, 5000, 10000, 30000];
    // Запрос скана без ответа дольше 15 с — считаем, что связи нет; повтор пойдёт
    // с тем же client_id, и сервер не посчитает скан дважды.
    const SEND_TIMEOUT_MS = 15000;
    // Загрузка приёмки и списка: 20 с, дальше — открыть по снимку из телефона.
    const LOAD_TIMEOUT_MS = 20000;
    // Фото накладной по мобильной сети (до 8 МБ): до 2 минут.
    const PHOTO_TIMEOUT_MS = 120000;

    // Фото накладной: 2400 px по длинной стороне — мелкий текст накладной ещё
    // читается; JPEG 0.85 — около 1 МБ, с запасом меньше предела сервера 8 МБ.
    const PHOTO_MAX_SIDE = 2400;
    const PHOTO_QUALITY = 0.85;

    // Камера — основной путь: на РЦ сканируют телефоном.
    const CAMERA_FORMATS = ['data_matrix', 'ean_13', 'ean_8', 'upc_a'];
    // Полифил BarcodeDetector (barcode-detector 2.3.1 + zxing-wasm 1.3.4): своя копия в
    // static/libs — версия в пути, поэтому месячный кэш статики не мешает обновлению.
    // CDN — запасной источник, если своя копия почему-то не загрузилась.
    const CAMERA_POLYFILL_DIR = '/static/libs/barcode-detector-2.3.1/';
    const CAMERA_POLYFILLS = [
        { url: CAMERA_POLYFILL_DIR + 'pure.js', wasm: CAMERA_POLYFILL_DIR + 'zxing_reader.wasm' },
        { url: 'https://cdn.jsdelivr.net/npm/barcode-detector@2.3.1/dist/es/pure.min.js', wasm: '' },
    ];
    // Видео с камеры: 1920x1080 «желательно» — мелкий DataMatrix на крышке читается
    // с 15-20 см; телефон без такого режима отдаст ближайший.
    const CAMERA_VIDEO = { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } };
    // Пауза между проверками кадра: не чаще 5 раз в секунду — чаще телефон греется, реже —
    // заметная задержка. Следующий кадр берётся после разбора текущего, поэтому на
    // медленном телефоне проверок меньше (разбор 1920x1080 занимает десятки мс).
    const CAMERA_TICK_MS = 200;
    // Код в кадре виден много кадров подряд: тот же код считается снова, только если
    // его не было видно 2,5 с (окно скользит, пока код в кадре — иначе EAN, который
    // считается каждый раз, насчитал бы бутылку несколько раз).
    const CAMERA_REPEAT_MS = 2500;
    // Обычный штрихкод (EAN) и DataMatrix одной бутылки часто попадают в кадр вместе.
    // Штрихкод с камеры ждёт 0,8 с: прочитан за это время код ЧЗ того же товара или
    // любой код ЧЗ в одном кадре с ним — штрихкод не считается (та же бутылка или
    // плёнка упаковки поверх банок). Правила целиком — у onCameraCode.
    const CAMERA_EAN_WAIT_MS = 800;
    // Модуль распознавания полифила (.wasm, 0,9 МБ) грузится при первом включении камеры:
    // по медленной сети 3G — до 20 с. Не загрузился за 30 с — следующий источник.
    const CAMERA_POLYFILL_LOAD_MS = 30000;
    // Столько разборов кадра подряд с ошибкой — и на экране камеры подсказка (около 3 с).
    const CAMERA_FAILS_HINT = 15;

    // Сигналы: высокий короткий — принято; два коротких — уже посчитана; низкий
    // длинный — не распознан. Частоты в Гц, at и ms — в миллисекундах.
    const TONES = {
        ok: [{ freq: 1760, at: 0, ms: 80, wave: 'square' }],
        repeat: [{ freq: 1320, at: 0, ms: 70, wave: 'square' }, { freq: 1320, at: 140, ms: 70, wave: 'square' }],
        bad: [{ freq: 220, at: 0, ms: 450, wave: 'sawtooth' }],
    };
    // Громкость 0.15: квадратная волна громкая, так слышно на складе и не режет ухо.
    const TONE_GAIN = 0.15;
    // Вибрация, мс: короткая — принято, двойная — повтор, длинная — ошибка.
    const VIBRATION = { ok: 30, repeat: [40, 60, 40], bad: 300 };
    // Вспышка рамки счётчика после скана.
    const FLASH_MS = 700;
    const FLASH_CLASSES = ['is-flash-ok', 'is-flash-repeat', 'is-flash-bad'];

    const TOAST_MS = 4000;
    const TOAST_BAD_MS = 8000;
    // Фокус в окне ставится после того, как оно показано (иначе браузер его не берёт).
    const SHEET_FOCUS_DELAY_MS = 50;
    // Последние сканы: показываем 8, в снимке храним 20 (как recent_scans сервера).
    const RECENT_SHOWN = 8;
    const RECENT_KEEP = 20;
    // Короткий вид кода в списке — первые 60 символов (как raw_short сервера).
    const RAW_SHORT_LEN = 60;

    // client_id: то же правило, что у маршрута (8..64 символа: латиница, цифры, дефис).
    const CLIENT_ID_RE = /^[A-Za-z0-9-]{8,64}$/;
    const RECEIPT_PARAM_RE = /^[0-9]{1,9}$/;

    const EMPTY_COUNTS = { units: 0, gtins: 0, rejected: 0, repeats: 0, invoices: 0 };
    const POSITION_WORDS = ['позиция', 'позиции', 'позиций'];

    // Раскладка US: что печатает клавиша с Shift и без. Цифры с Shift — символы над ними.
    const SHIFTED_DIGITS = ')!@#$%^&*(';
    const PUNCT = {
        Minus: ['-', '_'], Equal: ['=', '+'], BracketLeft: ['[', '{'], BracketRight: [']', '}'],
        Semicolon: [';', ':'], Quote: ["'", '"'], Comma: [',', '<'], Period: ['.', '>'],
        Slash: ['/', '?'], Backslash: ['\\', '|'], Backquote: ['`', '~'], Space: [' ', ' '],
        NumpadDecimal: ['.', '.'], NumpadAdd: ['+', '+'], NumpadSubtract: ['-', '-'],
        NumpadMultiply: ['*', '*'], NumpadDivide: ['/', '/'],
    };
    // Конец кода: сканер дописывает Enter (или Tab, смотря как настроен).
    const END_CODES = ['Enter', 'NumpadEnter', 'Tab'];

    // Результат отправки одного элемента очереди: идти к следующему или остановиться.
    const NEXT = 'next';
    const STOP = 'stop';

    // ==================== Состояние ====================

    const state = {
        view: 'start',          // start | scan | done
        receipt: null,          // receipt dict сервера (открытая приёмка на экране)
        counts: Object.assign({}, EMPTY_COUNTS),   // серверные счётчики этой приёмки
        countsTicket: 0,        // номер запроса, чьи счётчики сейчас на экране
        ticket: 0,              // счётчик запросов: ответ старого запроса не затирает новый
        gtins: new Set(),       // GTIN, уже известные серверу в этой приёмке
        dmKeys: new Set(),      // ключи посчитанных DataMatrix (сервер + очередь)
        recent: [],             // последние сканы сервера (новые сверху)
        invoices: [],
        queue: [],              // неотправленные сканы (копия localStorage)
        removed: new Set(),     // client_id, ушедшие из очереди в этой вкладке
        open: [],               // открытые приёмки (стартовый экран)
        openLoaded: false,
        openTicket: 0,          // последний запрос списка: ответ старого не рисуется
        startError: '',
        done: null,             // приёмка, переданная в разбор (экран «готово»)
        last: null,             // {tone, message, gtin, raw, at} — последний скан
        authRequired: false,
        offline: false,
        stale: false,           // экран открыт по снимку из телефона
        storageBroken: false,
        flushing: null,         // промис текущей отправки очереди
        retryTimer: null,
        retryIndex: 0,
        busy: {},
        sheet: null,            // открытое окно {kind, onOk, ...}
        scanner: { buffer: '', last: 0, idle: null, swallowUntil: 0 },
        nav: 0,                 // номер перехода между экранами: ответ про прежний экран не переключает текущий
    };

    // hint — подсказка в окне камеры {text, last}: держится, пока state.last тот же, то есть
    // до следующего результата скана (renderCamera её не затирает).
    const cam = { open: false, stream: null, track: null, detector: null, timer: null, seen: new Map(), torch: false,
        attempt: 0, dm: new Map(), eans: new Map(), counted: new Map(), wake: null, fails: 0, hint: null };
    // Загруженный полифил: {Detector, formats}. Один на страницу — повторная настройка
    // модуля распознавания перезагрузила бы .wasm при каждом включении камеры.
    let polyfill = null;

    const $ = (id) => document.getElementById(id);

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    function clock() {
        return (typeof performance !== 'undefined' && performance && typeof performance.now === 'function')
            ? performance.now() : Date.now();
    }

    function plural(n, forms) {
        const mod10 = n % 10;
        const mod100 = n % 100;
        if (mod10 === 1 && mod100 !== 11) return forms[0];
        if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
        return forms[2];
    }

    function timeText(iso) {
        const moment = new Date(iso);
        if (!iso || Number.isNaN(moment.getTime())) return '';
        return moment.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function dateTimeText(iso) {
        const moment = new Date(iso);
        if (!iso || Number.isNaN(moment.getTime())) return '';
        return moment.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function shortRaw(code) {
        return String(code || '').split(GS).join(' ').trim().slice(0, RAW_SHORT_LEN);
    }

    // ==================== Сеть ====================

    // Ответ {ok, status, data}; HTTP-ошибка не бросает (очереди нужен код ответа),
    // бросает только обрыв связи и таймаут — так «нет связи» отличается от отказа.
    async function request(method, url, body, timeoutMs) {
        const options = { method, cache: 'no-store', credentials: 'same-origin', headers: { Accept: 'application/json' } };
        if (body !== undefined) {
            if (typeof FormData !== 'undefined' && body instanceof FormData) {
                options.body = body;
            } else {
                options.headers['Content-Type'] = 'application/json';
                options.body = JSON.stringify(body);
            }
        }
        let timer = null;
        if (timeoutMs && typeof AbortController === 'function') {
            const controller = new AbortController();
            options.signal = controller.signal;
            timer = setTimeout(() => controller.abort(), timeoutMs);
        }
        try {
            const response = await fetch(url, options);
            let data = {};
            try { data = await response.json(); } catch (error) { data = {}; }
            return { ok: response.ok, status: response.status, data: data && typeof data === 'object' ? data : {} };
        } finally {
            if (timer) clearTimeout(timer);
        }
    }

    function errorText(res, fallback) {
        return (res && res.data && typeof res.data.error === 'string' && res.data.error) || fallback;
    }

    // ==================== Уведомление ====================

    let toastTimer = null;
    function toast(text, bad) {
        const node = $('rc-toast');
        node.textContent = text;
        node.classList.toggle('is-bad', Boolean(bad));
        node.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { node.hidden = true; }, bad ? TOAST_BAD_MS : TOAST_MS);
    }

    // ==================== Сигналы: звук, вибрация, вспышка ====================

    let audio = null;
    function audioContext() {
        if (audio) return audio;
        const Ctor = window.AudioContext || window.webkitAudioContext;
        if (!Ctor) return null;
        try { audio = new Ctor(); } catch (error) { audio = null; }
        return audio;
    }

    // Браузер пускает звук только после жеста пользователя: разблокируем по первому
    // касанию или клавише (нажатие сканера тоже жест).
    function unlockAudio() {
        const ctx = audioContext();
        if (ctx && ctx.state === 'suspended' && typeof ctx.resume === 'function') {
            try { Promise.resolve(ctx.resume()).catch(() => {}); } catch (error) { /* без звука */ }
        }
    }

    function beep(kind) {
        const tones = TONES[kind];
        const ctx = tones && audioContext();
        if (!ctx) return;
        try {
            const start = ctx.currentTime || 0;
            for (const tone of tones) {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                const from = start + tone.at / 1000;
                const to = from + tone.ms / 1000;
                osc.type = tone.wave;
                osc.frequency.value = tone.freq;
                gain.gain.setValueAtTime(TONE_GAIN, from);
                // Плавный спад в конце: без него динамик щёлкает.
                gain.gain.exponentialRampToValueAtTime(0.001, to);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(from);
                osc.stop(to);
            }
        } catch (error) { /* звук — не главное: вибрация и цвет остаются */ }
    }

    function vibrate(kind) {
        if (!navigator.vibrate || VIBRATION[kind] === undefined) return;
        try { navigator.vibrate(VIBRATION[kind]); } catch (error) { /* нет вибромотора */ }
    }

    let flashTimer = null;
    function flash(kind) {
        const nodes = [$('rc-counter'), $('rc-cam')];
        for (const node of nodes) {
            if (!node) continue;
            FLASH_CLASSES.forEach((name) => node.classList.remove(name));
            node.classList.add('is-flash-' + kind);
        }
        clearTimeout(flashTimer);
        flashTimer = setTimeout(() => {
            for (const node of nodes) if (node) FLASH_CLASSES.forEach((name) => node.classList.remove(name));
        }, FLASH_MS);
    }

    function signal(kind) {
        if (!TONES[kind]) return;
        beep(kind);
        vibrate(kind);
        flash(kind);
    }

    // ==================== Очередь сканов (localStorage) ====================

    function validItem(item) {
        return Boolean(item) && typeof item === 'object'
            && typeof item.client_id === 'string' && CLIENT_ID_RE.test(item.client_id)
            && Number.isInteger(item.receipt_id) && item.receipt_id > 0
            && typeof item.code === 'string';
    }

    function readStoredQueue() {
        let raw = null;
        try {
            raw = localStorage.getItem(QUEUE_KEY);
        } catch (error) {
            state.storageBroken = true;
            return [];
        }
        if (!raw) return [];
        let list = null;
        try { list = JSON.parse(raw); } catch (error) { list = null; }
        return Array.isArray(list) ? list.filter(validItem) : [];
    }

    // Записать очередь. Сначала подобрать сканы, которые положила другая вкладка
    // (иначе запись этой вкладки их бы стёрла); ушедшие отсюда не воскрешаются.
    function saveQueue() {
        const known = new Set(state.queue.map((item) => item.client_id));
        let adopted = false;
        for (const item of readStoredQueue()) {
            if (known.has(item.client_id) || state.removed.has(item.client_id)) continue;
            state.queue.push(item);
            known.add(item.client_id);
            adopted = true;
        }
        if (adopted) state.queue.sort((a, b) => (a.at || 0) - (b.at || 0));
        try {
            localStorage.setItem(QUEUE_KEY, JSON.stringify(state.queue));
            state.storageBroken = false;
        } catch (error) {
            state.storageBroken = true;
        }
    }

    function removeItem(item) {
        const index = state.queue.indexOf(item);
        if (index !== -1) state.queue.splice(index, 1);
        state.removed.add(item.client_id);
        saveQueue();
    }

    function queueOf(receiptId) {
        return state.queue.filter((item) => item.receipt_id === receiptId);
    }

    function pendingFor(receiptId) {
        return queueOf(receiptId).length;
    }

    // Неотправленные сканы приёмки для плашки «Не отправлено: N» — одна подпись на экране
    // и в окне камеры; bad — нет связи или нужен вход (плашка красная).
    function pendingInfo(receiptId) {
        const n = pendingFor(receiptId);
        const text = n
            ? 'Не отправлено: ' + n + (state.authRequired ? ', нужен вход' : (state.offline ? ', нет связи' : ''))
            : '';
        return { n, text, bad: n > 0 && (state.offline || state.authRequired) };
    }

    // Посчитан ли скан очереди в телефоне: принят разбором браузера и не отменён.
    function countsLocally(item) {
        return item.local === 'accepted' && !item.undo;
    }

    let clientSeq = 0;
    function newClientId() {
        const cryptoApi = window.crypto;
        try {
            if (cryptoApi && typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID();
        } catch (error) { /* randomUUID есть только на HTTPS — ниже запасной путь */ }
        let hex = '';
        try {
            if (cryptoApi && typeof cryptoApi.getRandomValues === 'function') {
                const bytes = cryptoApi.getRandomValues(new Uint8Array(12));
                for (const byte of bytes) hex += (byte + 256).toString(16).slice(1);
            }
        } catch (error) { hex = ''; }
        while (hex.length < 24) hex += Math.floor(Math.random() * 16).toString(16);
        // Счётчик вкладки: два скана в одну миллисекунду не совпадут, даже если
        // случайная часть слабая.
        clientSeq += 1;
        return 'rc-' + Date.now().toString(36) + '-' + clientSeq.toString(36) + '-' + hex;
    }

    // ==================== Снимок приёмки (работа без связи после перезагрузки) ====================

    function saveSnapshot() {
        if (!state.receipt) return;
        const snapshot = {
            id: state.receipt.id,
            receipt: state.receipt,
            counts: state.counts,
            gtins: Array.from(state.gtins),
            dm_keys: Array.from(state.dmKeys),
            recent: state.recent.slice(0, RECENT_KEEP),
            invoices: state.invoices,
            saved_at: Date.now(),
        };
        try { localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot)); } catch (error) { /* без снимка экран не откроется без связи */ }
    }

    function readSnapshot(id) {
        try {
            const snapshot = JSON.parse(localStorage.getItem(SNAPSHOT_KEY) || 'null');
            return snapshot && snapshot.id === id && snapshot.receipt ? snapshot : null;
        } catch (error) {
            return null;
        }
    }

    function forgetSnapshot(id) {
        if (!readSnapshot(id)) return;
        try { localStorage.removeItem(SNAPSHOT_KEY); } catch (error) { /* не страшно: снимок проверяется по id */ }
    }

    // ==================== Счётчики ====================

    function displayUnits() {
        if (!state.receipt) return 0;
        let units = state.counts.units || 0;
        for (const item of queueOf(state.receipt.id)) {
            if (countsLocally(item)) units += 1;
            // Отменённый скан, который сервер уже посчитал, но ещё не удалил.
            else if (item.undo && item.scan_id) units -= 1;
        }
        return Math.max(0, units);
    }

    function displayGtins() {
        if (!state.receipt) return 0;
        const extra = new Set();
        for (const item of queueOf(state.receipt.id)) {
            if (countsLocally(item) && item.gtin && !state.gtins.has(item.gtin)) extra.add(item.gtin);
        }
        return (state.counts.gtins || 0) + extra.size;
    }

    function applyCounts(counts, ticket) {
        if (!counts || ticket < state.countsTicket) return;
        state.countsTicket = ticket;
        state.counts = Object.assign({}, EMPTY_COUNTS, counts);
    }

    function isCurrent(receiptId) {
        return Boolean(state.receipt) && state.receipt.id === receiptId;
    }

    // ==================== Приёмка: загрузка, новая, экраны ====================

    function applyReceipt(data, ticket, fromSnapshot) {
        const same = isCurrent(data.receipt.id);
        state.receipt = data.receipt;
        if (!same || ticket >= state.countsTicket) {
            state.countsTicket = ticket;
            state.counts = Object.assign({}, EMPTY_COUNTS, data.counts || data.receipt.counts || {});
        }
        const gtins = Array.isArray(data.gtins) ? data.gtins
            : (Array.isArray(data.lines) ? data.lines.map((line) => line && line.gtin) : []);
        state.gtins = new Set(gtins.filter(Boolean));
        state.dmKeys = new Set(Array.isArray(data.dm_keys) ? data.dm_keys : []);
        for (const item of queueOf(data.receipt.id)) {
            if (countsLocally(item) && item.kind === 'datamatrix' && item.key) state.dmKeys.add(item.key);
        }
        state.recent = Array.isArray(data.recent) ? data.recent.slice(0, RECENT_KEEP) : [];
        state.invoices = Array.isArray(data.invoices) ? data.invoices.slice() : [];
        state.stale = Boolean(fromSnapshot);
        if (!same) state.last = null;
    }

    function setUrl(receiptId) {
        const target = receiptId ? PAGE + '?r=' + receiptId : PAGE;
        try {
            if (location.pathname + location.search !== target) history.replaceState(null, '', target);
        } catch (error) { /* адрес — удобство: без него экран работает */ }
    }

    function showStart() {
        state.nav += 1;
        state.view = 'start';
        state.receipt = null;
        state.stale = false;
        closeCamera();
        closeSheet();
        setUrl(null);
        render();
        return loadOpenList();
    }

    function showScan() {
        state.view = 'scan';
        state.startError = '';
        setUrl(state.receipt.id);
        render();
    }

    function showDone(receipt) {
        state.nav += 1;
        state.view = 'done';
        state.done = receipt;
        state.receipt = null;
        state.last = null;
        closeCamera();
        closeSheet();
        setUrl(null);
        render();
    }

    async function loadOpenList() {
        const ticket = ++state.ticket;
        state.openTicket = ticket;
        let res = null;
        try { res = await request('GET', API + '?status=open', undefined, LOAD_TIMEOUT_MS); } catch (error) { res = null; }
        if (state.openTicket !== ticket) return;
        if (res && res.ok) {
            state.open = Array.isArray(res.data.receipts) ? res.data.receipts : [];
            state.openLoaded = true;
            state.startError = '';
            state.authRequired = false;
        } else if (res && res.status === 401) {
            state.authRequired = true;
        } else {
            state.startError = res ? errorText(res, 'Сервер не ответил') + ' — список открытых приёмок не загрузился'
                : 'Нет связи — список открытых приёмок не загрузился';
        }
        if (state.view === 'start') render();
    }

    // Открыть приёмку на экране сканирования. Без связи (или с истёкшей сессией) —
    // по снимку из телефона, если он про эту приёмку: сканы копятся в очереди.
    async function loadReceipt(id, options) {
        const quiet = Boolean(options && options.quiet);
        // Тихая перезагрузка — про текущий экран; открытие — новый переход.
        const nav = quiet ? state.nav : ++state.nav;
        const ticket = ++state.ticket;
        let res = null;
        try { res = await request('GET', API + '/' + id, undefined, LOAD_TIMEOUT_MS); } catch (error) { res = null; }
        // Пока ждали ответа, приёмщик ушёл с этого экрана (новая приёмка, «Все приёмки»,
        // другая приёмка): поздний ответ про прежнюю приёмку экран не переключает и сканы
        // не уводит в неё (ревью 2026-10-03).
        if (state.nav !== nav) return false;
        if (quiet && !(state.view === 'scan' && isCurrent(id))) return false;

        if (res && res.ok && res.data && res.data.receipt) {
            state.authRequired = false;
            state.offline = false;
            if (res.data.receipt.status !== 'open') {
                forgetSnapshot(id);
                if (!quiet) toast('Приёмка №' + id + ' уже закрыта — сканировать в неё нельзя', true);
                await showStart();
                return false;
            }
            applyReceipt(res.data, ticket, false);
            saveSnapshot();
            showScan();
            return true;
        }
        if (res && res.status === 404) {
            forgetSnapshot(id);
            if (!quiet) toast('Приёмка №' + id + ' не найдена', true);
            await showStart();
            return false;
        }
        if (res && res.status === 401) state.authRequired = true;
        else state.offline = true;

        if (state.view === 'scan' && isCurrent(id)) {
            // Уже на экране — оставляем то, что есть, только помечаем.
            state.stale = true;
            render();
            return true;
        }
        const snapshot = readSnapshot(id);
        if (snapshot) {
            applyReceipt(snapshot, ticket, true);
            showScan();
            return true;
        }
        await showStart();
        if (!quiet) {
            // После showStart: загрузка списка сбрасывает прошлую ошибку.
            state.startError = (res && res.status === 401)
                ? 'Сессия истекла — войдите снова, чтобы открыть приёмку №' + id
                : (res ? errorText(res, 'Сервер не ответил') : 'Нет связи')
                    + ' — приёмку №' + id + ' открыть не получилось. Сканы в телефоне сохранены.';
            render();
        }
        return false;
    }

    async function startNew(button) {
        await act('new', button, async () => {
            let res = null;
            try { res = await request('POST', API, {}, LOAD_TIMEOUT_MS); } catch (error) { res = null; }
            if (!res) {
                toast('Нет связи — новую приёмку открыть не получилось. Повторите, когда появится связь.', true);
                return;
            }
            if (res.status === 401) {
                state.authRequired = true;
                render();
                toast('Сессия истекла — войдите снова', true);
                return;
            }
            if (!res.ok || !res.data.receipt) {
                toast(errorText(res, 'Не получилось открыть приёмку'), true);
                return;
            }
            state.authRequired = false;
            state.nav += 1;
            const receipt = res.data.receipt;
            applyReceipt({ receipt, lines: [], recent: [], invoices: [], dm_keys: [] }, ++state.ticket, false);
            saveSnapshot();
            showScan();
            toast('Приёмка №' + receipt.id + ' открыта — сканируйте');
        });
    }

    // ==================== Скан: сигнал, очередь, отправка ====================

    function parseLocal(raw) {
        const codes = window.RcCodes;
        if (!codes || typeof codes.parseCode !== 'function') return null;
        try { return codes.parseCode(raw); } catch (error) { return null; }
    }

    const TONE_OF = { accepted: 'ok', repeat: 'repeat', rejected: 'bad', unknown: 'wait' };
    const REPEAT_MESSAGE = 'Уже посчитана';
    const UNREADABLE_MESSAGE = 'Код не распознан — повторите';

    // Один прочитанный код (сканер, камера или ввод вручную) -> очередь + сигнал.
    function handleCode(raw, source) {
        const code = String(raw === undefined || raw === null ? '' : raw);
        if (state.view !== 'scan' || !state.receipt) {
            signal('bad');
            toast(state.view === 'done'
                ? 'Приёмка уже передана в разбор. Нажмите «Новая приёмка», чтобы сканировать дальше.'
                : 'Сначала нажмите «Новая приёмка» или продолжите открытую', true);
            return null;
        }
        if (state.busy.finish) {
            // «Завершить» уже ушло на сервер: скан в закрываемую приёмку не запишется.
            signal('bad');
            toast('Приёмка завершается — этот скан не записан. Дождитесь ответа сервера.', true);
            return null;
        }
        if (state.sheet && state.sheet.kind === 'finish') {
            closeSheet();
            toast('Завершение отменено: идёт сканирование');
        }
        const parsed = parseLocal(code);
        let local = 'unknown';
        if (parsed && !parsed.ok) local = 'rejected';
        else if (parsed && parsed.kind === 'datamatrix' && state.dmKeys.has(parsed.key)) local = 'repeat';
        else if (parsed) local = 'accepted';
        if (local === 'accepted' && parsed.kind === 'datamatrix') state.dmKeys.add(parsed.key);

        const message = local === 'repeat' ? REPEAT_MESSAGE
            : (local === 'unknown' ? 'Код отправлен на проверку' : parsed.message);
        const item = {
            client_id: newClientId(),
            receipt_id: state.receipt.id,
            code,
            source,
            client_time: new Date().toISOString(),
            at: Date.now(),
            local,
            kind: parsed ? parsed.kind : '',
            gtin: parsed && parsed.gtin ? parsed.gtin : '',
            key: parsed && parsed.ok ? parsed.key : '',
            message,
            tries: 0,
        };
        // В очередь (и в localStorage) — ДО отправки: обрыв связи скан не теряет.
        state.queue.push(item);
        saveQueue();
        state.last = { tone: TONE_OF[local], message, gtin: item.gtin, raw: code, at: item.client_time, client_id: item.client_id };
        signal(TONE_OF[local]);
        render();
        flush();
        return item;
    }

    function flush() {
        if (state.flushing) return state.flushing;
        clearRetry();
        state.flushing = (async () => {
            try {
                for (;;) {
                    const item = state.queue[0];
                    if (!item) break;
                    const outcome = await sendItem(item);
                    if (outcome === STOP) break;
                }
            } catch (error) {
                console.warn('[RC] очередь сканов', error);
            } finally {
                state.flushing = null;
            }
            if (state.queue.length) {
                scheduleRetry();
            } else {
                state.retryIndex = 0;
                state.offline = false;
                if (state.stale && state.view === 'scan' && state.receipt) loadReceipt(state.receipt.id, { quiet: true });
            }
            render();
        })();
        return state.flushing;
    }

    function scheduleRetry() {
        if (state.retryTimer || !state.queue.length) return;
        const delay = RETRY_DELAYS_MS[Math.min(state.retryIndex, RETRY_DELAYS_MS.length - 1)];
        state.retryIndex += 1;
        state.retryTimer = setTimeout(() => {
            state.retryTimer = null;
            flush();
        }, delay);
    }

    function clearRetry() {
        if (!state.retryTimer) return;
        clearTimeout(state.retryTimer);
        state.retryTimer = null;
    }

    async function sendItem(item) {
        if (item.undo && item.scan_id) return deleteUndone(item);
        item.tries = (item.tries || 0) + 1;   // до отправки: «мог дойти до сервера»
        saveQueue();
        const ticket = ++state.ticket;
        let res;
        try {
            res = await request('POST', API + '/' + item.receipt_id + '/scan', {
                code: item.code,
                client_id: item.client_id,
                source: item.source,
                client_time: item.client_time,
            }, SEND_TIMEOUT_MS);
        } catch (error) {
            state.offline = true;
            render();
            return STOP;
        }
        if (res.status === 401) {
            state.authRequired = true;
            state.offline = false;
            render();
            return STOP;
        }
        state.authRequired = false;
        if (res.ok) {
            state.offline = false;
            state.retryIndex = 0;
            return onScanSaved(item, res.data || {}, ticket);
        }
        if (res.status === 409) return rescueClosed(item.receipt_id, res.data && res.data.code === 'receipt_deleted');
        if (res.status === 404) {
            dropReceipt(item.receipt_id, res);
            return NEXT;
        }
        if (res.status >= 500 || res.status === 408 || res.status === 429 || res.status === 0) {
            // Сервер занят или недоступен — как обрыв связи: скан остаётся в очереди.
            state.offline = true;
            render();
            return STOP;
        }
        // 400: этот скан сервер не примет никогда — выбросить его, остальные слать дальше.
        removeItem(item);
        if (isCurrent(item.receipt_id) && item.kind === 'datamatrix' && item.key && countsLocally(item)) {
            state.dmKeys.delete(item.key);
        }
        toast('Скан не принят сервером: ' + errorText(res, 'ошибка ' + res.status), true);
        render();
        return NEXT;
    }

    async function onScanSaved(item, data, ticket) {
        const current = isCurrent(item.receipt_id);
        if (current) applyCounts(data.counts, ticket);
        if (item.undo) {
            // Отменённый скан, который мог дойти до сервера: если сервер его посчитал —
            // удалить там же (повтор client_id вернул тот же scan_id).
            if (data.result === 'accepted' && data.scan_id) {
                item.scan_id = data.scan_id;
                saveQueue();
                return deleteUndone(item);
            }
            removeItem(item);
            render();
            return NEXT;
        }
        removeItem(item);
        // Камера может отозвать этот скан позже (retractCameraEan) — нужен id на сервере.
        if (data.result === 'accepted' && data.scan_id) item.saved_scan_id = data.scan_id;
        if (current) {
            if (data.result === 'accepted' && data.gtin) state.gtins.add(data.gtin);
            rememberRecent(item, data);
            correctLocal(item, data);
            saveSnapshot();
        }
        render();
        return NEXT;
    }

    function rememberRecent(item, data) {
        if (!data.scan_id || state.recent.some((scan) => scan.id === data.scan_id)) return;
        state.recent.unshift({
            id: data.scan_id,
            gtin: data.gtin || null,
            kind: data.kind || item.kind,
            accepted: data.result === 'accepted',
            reason: data.result === 'repeat' ? 'repeat' : '',
            raw_short: shortRaw(item.code),
            scanned_at: item.client_time,
            source: item.source,
            by: '',
        });
        if (state.recent.length > RECENT_KEEP) state.recent.length = RECENT_KEEP;
    }

    // Ответ сервера главнее разбора в браузере: не совпал — поправить ключи и сигнал.
    function correctLocal(item, data) {
        const server = data.result;
        if (!server || server === item.local) return;
        if (item.kind === 'datamatrix' && item.key) {
            if (server === 'accepted' || server === 'repeat') state.dmKeys.add(item.key);
            else if (item.local === 'accepted') state.dmKeys.delete(item.key);
        }
        const tone = TONE_OF[server] || 'bad';
        const message = server === 'repeat' ? (data.message || REPEAT_MESSAGE)
            : (data.message || (server === 'accepted' ? 'Принято' : UNREADABLE_MESSAGE));
        const latest = Boolean(state.last) && state.last.client_id === item.client_id;
        if (latest) {
            state.last = { tone, message, gtin: data.gtin || item.gtin, raw: item.code, at: item.client_time, client_id: item.client_id };
        }
        // Сигнал — если счётчик стал меньше, чем приёмщик услышал (или сигнала не было).
        if (item.local === 'accepted' || item.local === 'unknown') {
            signal(tone);
            if (!latest && tone !== 'ok') toast('Скан ' + timeText(item.client_time) + ': ' + message, tone === 'bad');
        }
    }

    // 409 на скан: приёмку закрыли (другой телефон или бухгалтер) или удалили в «Разборе
    // приёмок» (code receipt_deleted), а в этом телефоне остались её неотправленные сканы
    // (приёмщик был без связи). Сканы не выбрасываются:
    // открывается новая приёмка, и они уходят в неё (ревью 2026-10-03: «сканы не теряются
    // при обрыве связи»). Новую приёмку открыть не вышло (нет связи) — сканы ждут в
    // очереди, следующая отправка попробует снова.
    async function rescueClosed(oldId, deleted) {
        const items = queueOf(oldId).filter((item) => !item.undo);
        if (!items.length) {
            dropReceipt(oldId, { status: 409, deleted: deleted });
            return NEXT;
        }
        let res = null;
        try {
            res = await request('POST', API, { note: (deleted ? 'Сканы после удаления приёмки №' : 'Сканы после закрытия приёмки №') + oldId }, LOAD_TIMEOUT_MS);
        } catch (error) {
            res = null;
        }
        if (!res || res.status >= 500) {
            state.offline = true;
            render();
            return STOP;
        }
        if (res.status === 401) {
            state.authRequired = true;
            render();
            return STOP;
        }
        if (!res.ok || !res.data || !res.data.receipt) {
            dropReceipt(oldId, { status: 409, deleted: deleted });
            return NEXT;
        }
        const fresh = res.data.receipt;
        for (const item of queueOf(oldId)) {
            if (item.undo) {
                const index = state.queue.indexOf(item);
                if (index !== -1) state.queue.splice(index, 1);
                state.removed.add(item.client_id);
            } else {
                item.receipt_id = fresh.id;
                item.tries = 0;
            }
        }
        saveQueue();
        const moved = items.length;
        if (isCurrent(oldId)) {
            forgetSnapshot(oldId);
            state.nav += 1;
            applyReceipt({ receipt: fresh, lines: [], recent: [], invoices: [], dm_keys: [] }, ++state.ticket, false);
            saveSnapshot();
            showScan();
        }
        signal('repeat');
        toast('Приёмку №' + oldId + (deleted ? ' удалили' : ' уже закрыли') + ' — неотправленные сканы из телефона (' + moved
            + ') перенесены в новую приёмку №' + fresh.id, true);
        render();
        return NEXT;
    }

    // 404 на скан (и 409 без сканов к переносу): приёмки нет — её сканы больше не записать.
    function dropReceipt(receiptId, res) {
        const items = queueOf(receiptId);
        for (const item of items) {
            const index = state.queue.indexOf(item);
            if (index !== -1) state.queue.splice(index, 1);
            state.removed.add(item.client_id);
        }
        saveQueue();
        const lost = items.filter((item) => !item.undo).length;
        const why = res.deleted ? 'удалена' : (res.status === 409 ? 'уже закрыта' : 'не найдена');
        const tail = lost ? ' — не записано сканов из телефона: ' + lost : '';
        signal('bad');
        toast('Приёмка №' + receiptId + ' ' + why + tail, true);
        if (isCurrent(receiptId)) loadReceipt(receiptId, { quiet: true });
        else render();
    }

    async function deleteUndone(item) {
        const ticket = ++state.ticket;
        let res;
        try {
            res = await request('DELETE', API + '/' + item.receipt_id + '/scans/' + item.scan_id, undefined, SEND_TIMEOUT_MS);
        } catch (error) {
            state.offline = true;
            render();
            return STOP;
        }
        if (res.status === 401) {
            state.authRequired = true;
            render();
            return STOP;
        }
        if (res.status >= 500) {
            state.offline = true;
            render();
            return STOP;
        }
        // 409: приёмку закрыли или удалили — отмену не применить, а неотправленные сканы
        // этой приёмки (они могут стоять в очереди после отмены) переносятся в новую.
        if (res.status === 409) return rescueClosed(item.receipt_id, res.data && res.data.code === 'receipt_deleted');
        // 200 — удалён; 404 — уже удалён (или приёмки нет); прочее — повторять бессмысленно.
        removeItem(item);
        if (isCurrent(item.receipt_id)) {
            if (res.ok) applyCounts(res.data.counts, ticket);
            state.recent = state.recent.filter((scan) => scan.id !== item.scan_id);
            saveSnapshot();
        }
        render();
        return NEXT;
    }

    // ==================== Ручной сканер: сбор кода из нажатий ====================

    function isTyping(target) {
        if (!target) return false;
        if (target.isContentEditable) return true;
        const tag = String(target.tagName || '').toLowerCase();
        if (tag === 'textarea' || tag === 'select') return true;
        if (tag !== 'input') return false;
        const type = String(target.type || 'text').toLowerCase();
        return ['button', 'submit', 'reset', 'checkbox', 'radio', 'file', 'range', 'color', 'image'].indexOf(type) === -1;
    }

    // Символ по физической клавише (раскладка US); null — клавиша не печатная.
    function charFor(event) {
        const code = String(event.code || '');
        const shift = Boolean(event.shiftKey);
        let match = /^Key([A-Z])$/.exec(code);
        if (match) return shift ? match[1] : match[1].toLowerCase();
        match = /^Digit([0-9])$/.exec(code);
        if (match) return shift ? SHIFTED_DIGITS[Number(match[1])] : match[1];
        match = /^Numpad([0-9])$/.exec(code);
        if (match) return match[1];
        if (Object.prototype.hasOwnProperty.call(PUNCT, code)) return PUNCT[code][shift ? 1 : 0];
        // Клавиша без известного code (часть Android-клавиатур): берём сам символ —
        // кириллицу разбор кода всё равно переведёт в латиницу.
        const key = event.key;
        if (typeof key === 'string' && key.length === 1 && key >= ' ') return key;
        return null;
    }

    function onKeyDown(event) {
        unlockAudio();
        if (event.isComposing || event.keyCode === 229) return;    // идёт ввод через IME
        if (isTyping(event.target)) return;                          // поле «ввести вручную»
        const scanner = state.scanner;
        const now = clock();
        const code = String(event.code || '');

        if (END_CODES.indexOf(code) !== -1 || event.key === 'Enter') {
            if (!scanner.buffer) {
                // Код уже ушёл по паузе (сканер без суффикса или Enter опоздал): этот Enter —
                // хвост сканера, а не нажатие кнопки в фокусе («Отменить последний»).
                if (now < scanner.swallowUntil) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                return;
            }
            const fresh = now - scanner.last <= SCAN_GAP_MS;
            const text = takeBuffer();
            // В буфере только быстрые подряд символы (пауза больше SCAN_GAP_MS его сбрасывает),
            // поэтому код от MIN_CODE_LEN символов — серия сканера, даже если Enter опоздал;
            // такой Enter не должен нажать кнопку в фокусе (ревью 2026-10-03). Одна буква,
            // набранная руками, и Enter после паузы — обычное нажатие, его не трогаем.
            if (text.length < MIN_CODE_LEN) {
                if (fresh) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            handleCode(text, 'scanner');
            return;
        }

        const isGs = (event.ctrlKey && code === 'BracketRight') || event.key === GS;
        if (!isGs && (event.ctrlKey || event.altKey || event.metaKey)) return;   // Ctrl+R и прочее — браузеру
        const ch = isGs ? GS : charFor(event);
        if (ch === null) return;                                     // Shift, стрелки, Escape
        if (scanner.buffer && now - scanner.last > SCAN_GAP_MS) takeBuffer();
        if (!scanner.buffer && ch === ' ') return;                   // пробел по кнопке — не начало кода
        if (scanner.buffer.length < MAX_BUFFER) scanner.buffer += ch;
        scanner.last = now;
        armIdle();
        event.preventDefault();
        event.stopPropagation();
    }

    // Забрать буфер сканера (и снять таймер паузы).
    function takeBuffer() {
        const scanner = state.scanner;
        const text = scanner.buffer;
        scanner.buffer = '';
        clearTimeout(scanner.idle);
        scanner.idle = null;
        return text;
    }

    // Сканер без суффикса Enter/Tab: код заканчивается паузой. Пауза SCAN_IDLE_MS после
    // быстрой серии от MIN_CODE_LEN символов — код готов; Enter, если всё-таки придёт
    // позже, проглатывается (SCAN_SWALLOW_MS), чтобы не нажать кнопку в фокусе.
    function armIdle() {
        const scanner = state.scanner;
        clearTimeout(scanner.idle);
        scanner.idle = setTimeout(() => {
            scanner.idle = null;
            if (scanner.buffer.length < MIN_CODE_LEN) {
                scanner.buffer = '';
                return;
            }
            const text = takeBuffer();
            scanner.swallowUntil = clock() + SCAN_SWALLOW_MS;
            handleCode(text, 'scanner');
        }, SCAN_IDLE_MS);
    }

    // ==================== Отменить последний ====================

    async function undoLast(button) {
        if (state.view !== 'scan' || !state.receipt) return;
        const receiptId = state.receipt.id;
        // 1. Последний посчитанный скан ещё в телефоне.
        const queued = queueOf(receiptId);
        for (let i = queued.length - 1; i >= 0; i -= 1) {
            const item = queued[i];
            if (item.undo || (item.local !== 'accepted' && item.local !== 'unknown')) continue;
            if (item.kind === 'datamatrix' && item.key) state.dmKeys.delete(item.key);
            if (item.tries > 0) {
                // Запрос уже уходил: сервер мог его записать — отправить и удалить там.
                item.undo = true;
                saveQueue();
            } else {
                removeItem(item);
            }
            state.last = { tone: 'wait', message: 'Последний скан отменён', gtin: item.gtin, raw: item.code, at: item.client_time };
            render();
            toast('Отменён скан ' + (item.gtin || shortRaw(item.code)));
            flush();
            return;
        }
        // 2. Последний принятый скан на сервере.
        const last = state.recent.find((scan) => scan.accepted);
        if (!last) {
            toast('Отменять нечего: посчитанных сканов нет');
            return;
        }
        await act('undo', button, async () => {
            const ticket = ++state.ticket;
            let res = null;
            try { res = await request('DELETE', API + '/' + receiptId + '/scans/' + last.id, undefined, SEND_TIMEOUT_MS); } catch (error) { res = null; }
            if (!res) {
                toast('Нет связи — отмена не выполнена. Повторите, когда появится связь.', true);
                return;
            }
            if (res.status === 401) {
                state.authRequired = true;
                render();
                toast('Сессия истекла — войдите снова', true);
                return;
            }
            if (res.ok) {
                applyCounts(res.data.counts, ticket);
                state.recent = state.recent.filter((scan) => scan.id !== last.id);
                state.last = { tone: 'wait', message: 'Последний скан отменён', gtin: last.gtin, raw: last.raw_short, at: last.scanned_at };
                render();
                toast('Отменён скан ' + (last.gtin || last.raw_short || ''));
                await loadReceipt(receiptId, { quiet: true });   // ключи DataMatrix и позиции — с сервера
                return;
            }
            if (res.status === 404 || res.status === 409) {
                toast(errorText(res, 'Скан уже отменён'), true);
                await loadReceipt(receiptId, { quiet: true });
                return;
            }
            toast(errorText(res, 'Не получилось отменить скан'), true);
        });
    }

    // ==================== Завершить ====================

    // «Завершить» на экране и в окне камеры. Окно открывается и при неотправленных сканах:
    // с камеры последний скан почти всегда ещё в пути, отказ выглядел бы сломанной кнопкой.
    // Окно ждёт очередь (renderFinishSheet), отправка — сразу, не дожидаясь паузы повтора.
    function requestFinish() {
        if (state.view !== 'scan' || !state.receipt) return false;
        if (state.busy.undo) {
            toast('Идёт отмена скана — дождитесь её и завершите ещё раз', true);
            return false;
        }
        const receiptId = state.receipt.id;
        openSheet({
            kind: 'finish',
            receiptId,
            title: 'Завершить приёмку №' + receiptId + '?',
            ok: 'Завершить приёмку',
            tone: 'ok',
            onOk: doFinish,
        });
        renderFinishSheet();
        if (pendingFor(receiptId)) flush();
        return true;
    }

    // Окно «Завершить» по состоянию: счётчик, ожидание неотправленных сканов, напоминание
    // о фото накладной. Вызывается из render() — только читает состояние: очередь не
    // отправляет и приёмку не завершает (закрывает её только нажатие «Завершить приёмку»).
    function renderFinishSheet() {
        const sheet = state.sheet;
        if (!sheet || sheet.kind !== 'finish') return;
        if (state.view !== 'scan' || !state.receipt || state.receipt.id !== sheet.receiptId) {
            closeSheet();          // приёмка сменилась (rescueClosed перенёс сканы в новую)
            return;
        }
        const units = displayUnits();
        const gtins = displayGtins();
        $('rc-sheet-text').textContent = 'Посчитано: ' + units + ' шт., ' + gtins + ' ' + plural(gtins, POSITION_WORDS)
            + '. После завершения сканировать в неё нельзя — позиции уйдут в разбор бухгалтерии.';
        const waiting = pendingFor(sheet.receiptId);
        const wait = $('rc-sheet-wait');
        wait.hidden = !waiting;
        wait.classList.toggle('is-bad', waiting > 0 && (state.offline || state.authRequired));
        let waitText = '';
        if (waiting && state.authRequired) {
            waitText = 'Сессия истекла — в телефоне ждут отправки сканов: ' + waiting + '. Войдите снова, и они уйдут.';
        } else if (waiting && state.offline) {
            waitText = 'Нет связи — в телефоне ждут отправки сканов: ' + waiting + '. Завершить можно, когда они уйдут.';
        } else if (waiting) {
            waitText = 'Отправляю сканы из телефона: ' + waiting + '…';
        }
        $('rc-sheet-wait-text').textContent = waitText;
        $('rc-sheet-retry').hidden = !(waiting && state.offline && !state.authRequired);
        const login = $('rc-sheet-login');
        login.hidden = !(waiting && state.authRequired);
        login.setAttribute('href', loginHref());
        $('rc-sheet-note').hidden = state.invoices.length > 0;
        $('rc-sheet-cancel').textContent = cam.open ? 'Продолжить сканирование' : 'Отмена';
        // Пока очередь не пуста или «Завершить» уже в пути — кнопка выключена.
        $('rc-sheet-ok').disabled = waiting > 0 || Boolean(state.busy.finish);
    }

    // «Сфотографировать» в окне «Завершить»: окно и камера закрываются в том же нажатии,
    // что открывает выбор фото, — поток камеры отпущен до того, как откроется системная камера.
    function startInvoicePhoto() {
        closeSheet();
        closeCamera();
        $('rc-photo-input').click();
    }

    async function doFinish(button) {
        if (!state.receipt) return;
        const receiptId = state.receipt.id;
        // Окно про прежнюю приёмку (сканы уже перенесли в новую) — не завершать ни ту, ни другую.
        if (state.sheet && state.sheet.receiptId !== undefined && state.sheet.receiptId !== receiptId) {
            closeSheet();
            return;
        }
        await act('finish', button, async () => {
            if (state.busy.undo) {
                closeSheet();
                toast('Идёт отмена скана — дождитесь её и завершите ещё раз', true);
                return;
            }
            if (pendingFor(receiptId)) {
                closeSheet();
                toast('Есть неотправленные сканы — дождитесь связи', true);
                flush();
                return;
            }
            let res = null;
            try { res = await request('POST', API + '/' + receiptId + '/close', {}, LOAD_TIMEOUT_MS); } catch (error) { res = null; }
            if (!res) {
                toast('Нет связи — приёмка не завершена. Повторите, когда появится связь.', true);
                return;
            }
            if (res.status === 401) {
                state.authRequired = true;
                closeSheet();
                closeCamera();     // под камерой — «Сессия истекла… Войдите снова»: её надо видеть
                render();
                toast('Сессия истекла — войдите снова', true);
                return;
            }
            if (res.status === 404) {
                closeSheet();
                forgetSnapshot(receiptId);
                toast('Приёмка №' + receiptId + ' не найдена', true);
                await showStart();
                return;
            }
            if (!res.ok || !res.data.receipt) {
                toast(errorText(res, 'Не получилось завершить приёмку'), true);
                return;
            }
            forgetSnapshot(receiptId);
            showDone(res.data.receipt);
        });
    }

    // ==================== Ввод вручную ====================

    function openManual() {
        if (state.view !== 'scan' || !state.receipt) return;
        openSheet({
            kind: 'manual',
            title: 'Ввести цифры штрихкода',
            text: 'Цифры под полосками штрихкода (EAN, 8-14 цифр). Код Честного знака руками не вводится — сканируйте его камерой.',
            ok: 'Добавить',
            input: true,
            onOk: submitManual,
        });
    }

    function submitManual() {
        const input = $('rc-sheet-input');
        const value = String(input.value || '').trim();
        if (!value) {
            toast('Введите цифры штрихкода', true);
            return;
        }
        closeSheet();
        handleCode(value, 'manual');
    }

    // ==================== Окно ====================

    // Окно (лист снизу). options: kind, title, text, ok — подпись кнопки, danger (красная) или
    // tone 'ok' (зелёная), cancel — подпись отмены, input — поле цифр, onOk.
    function openSheet(options) {
        state.sheet = options;
        $('rc-sheet-title').textContent = options.title;
        $('rc-sheet-text').textContent = options.text || '';
        const input = $('rc-sheet-input');
        input.hidden = !options.input;
        input.value = '';
        const ok = $('rc-sheet-ok');
        ok.textContent = options.ok || 'Готово';
        ok.disabled = false;
        ok.classList.toggle('rc-btn-danger', Boolean(options.danger));
        ok.classList.toggle('rc-btn-ok', !options.danger && options.tone === 'ok');
        ok.classList.toggle('rc-btn-primary', !options.danger && options.tone !== 'ok');
        $('rc-sheet-cancel').textContent = options.cancel || 'Отмена';
        $('rc-sheet-wait').hidden = true;
        $('rc-sheet-note').hidden = true;
        $('rc-sheet-wrap').hidden = false;
        // rc-sheet-on — уведомления сверху, а не на кнопках окна (scan.css).
        document.documentElement.classList.add('rc-lock', 'rc-sheet-on');
        if (cam.open) {
            // Окно поверх камеры: камера коды не читает (tickCamera). Штрихкод, ещё ждавший
            // CAMERA_EAN_WAIT_MS без сигнала «принято», не считается — как при закрытии камеры.
            cam.eans.clear();
            // Код, ушедший из кадра раньше CAMERA_REPEAT_MS до окна, забыт сейчас: после окна
            // (closeSheet) «как не уходивший» остаётся только код, бывший в кадре до окна.
            const now = clock();
            for (const [code, at] of cam.seen) if (now - at > CAMERA_REPEAT_MS) cam.seen.delete(code);
            $('rc-cam').inert = true;
        }
        // Фокус — на «Отмене» (или на поле): случайный Enter не завершит приёмку.
        setTimeout(() => {
            const target = options.input ? input : $('rc-sheet-cancel');
            if (state.sheet === options && target && typeof target.focus === 'function') target.focus();
        }, SHEET_FOCUS_DELAY_MS);
    }

    function closeSheet() {
        if (!state.sheet) return;
        state.sheet = null;
        $('rc-sheet-wrap').hidden = true;
        document.documentElement.classList.remove('rc-sheet-on');
        $('rc-cam').inert = false;
        if (cam.open) {
            // Камера читает снова со следующей проверки кадра (поток не перезапускается). Код,
            // бывший в кадре до окна, — как не уходивший из кадра: снова считается, только если
            // его не видно CAMERA_REPEAT_MS (иначе банка перед камерой посчиталась бы дважды).
            // Прокрутку не возвращаем: под окном — камера.
            const now = clock();
            for (const code of cam.seen.keys()) cam.seen.set(code, now);
        } else {
            document.documentElement.classList.remove('rc-lock');
        }
        const input = $('rc-sheet-input');
        if (input && typeof input.blur === 'function') input.blur();
    }

    // ==================== Фото накладной ====================

    // Файл -> JPEG не больше PHOTO_MAX_SIDE по длинной стороне. Не вышло (нет canvas,
    // не декодировался формат) — отдаём исходный файл: сервер проверит сигнатуру и
    // размер сам. Молча терять фото нельзя. Приём — static/js/me/acceptance.js.
    function shrinkPhoto(file) {
        return loadBitmap(file).then((img) => {
            const w = img.width;
            const h = img.height;
            const k = Math.min(1, PHOTO_MAX_SIDE / Math.max(w, h));
            const canvas = document.createElement('canvas');
            canvas.width = Math.max(1, Math.round(w * k));
            canvas.height = Math.max(1, Math.round(h * k));
            canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
            if (img.close) img.close();
            return new Promise((resolve) => {
                canvas.toBlob((blob) => resolve(blob || file), 'image/jpeg', PHOTO_QUALITY);
            });
        }).catch((error) => {
            console.warn('[RC] фото не уменьшилось, шлём как есть', error);
            return file;
        });
    }

    // createImageBitmap с imageOrientation применяет EXIF-поворот при декодировании:
    // снимок с телефона не ляжет на бок. Где его нет — обычный <img>.
    function loadBitmap(file) {
        if (typeof createImageBitmap === 'function') {
            try {
                return createImageBitmap(file, { imageOrientation: 'from-image' }).catch(() => loadViaImg(file));
            } catch (error) { /* старая сигнатура без options — вниз, на <img> */ }
        }
        return loadViaImg(file);
    }

    function loadViaImg(file) {
        return new Promise((resolve, reject) => {
            if (typeof Image !== 'function' || typeof URL === 'undefined' || !URL.createObjectURL) {
                reject(new Error('no image decoder'));
                return;
            }
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode')); };
            img.src = url;
        });
    }

    async function uploadPhoto(file) {
        if (!file || !state.receipt) return;
        const receiptId = state.receipt.id;
        await act('photo', $('rc-photo'), async () => {
            toast('Отправляю фото накладной…');
            const blob = await shrinkPhoto(file);
            const form = new FormData();
            form.append('photo', blob, 'invoice.jpg');
            let res = null;
            try { res = await request('POST', API + '/' + receiptId + '/invoice', form, PHOTO_TIMEOUT_MS); } catch (error) { res = null; }
            if (!res) {
                toast('Нет связи — фото не отправлено. Сделайте снимок ещё раз, когда появится связь.', true);
                return;
            }
            if (res.status === 401) {
                state.authRequired = true;
                render();
                toast('Сессия истекла — войдите снова', true);
                return;
            }
            if (!res.ok) {
                toast(errorText(res, 'Фото не сохранилось'), true);
                return;
            }
            if (isCurrent(receiptId)) {
                state.invoices = Array.isArray(res.data.invoices) ? res.data.invoices
                    : state.invoices.concat(res.data.invoice ? [res.data.invoice] : []);
                state.counts.invoices = state.invoices.length;
                saveSnapshot();
                render();
            }
            toast('Фото накладной сохранено');
        });
    }

    function confirmDeleteInvoice(invoice) {
        openSheet({
            kind: 'invoice',
            title: 'Удалить фото накладной?',
            text: 'Фото пропадёт из приёмки. Если снимок нечёткий — удалите его и сделайте новый.',
            ok: 'Удалить',
            danger: true,
            onOk: (button) => deleteInvoice(invoice, button),
        });
    }

    async function deleteInvoice(invoice, button) {
        if (!state.receipt) return;
        const receiptId = state.receipt.id;
        await act('invoice', button, async () => {
            let res = null;
            try {
                res = await request('DELETE', API + '/' + receiptId + '/invoice/' + encodeURIComponent(invoice.name), undefined, LOAD_TIMEOUT_MS);
            } catch (error) { res = null; }
            if (!res) {
                toast('Нет связи — фото не удалено', true);
                return;
            }
            if (res.status === 401) {
                state.authRequired = true;
                closeSheet();
                render();
                toast('Сессия истекла — войдите снова', true);
                return;
            }
            if (res.ok || res.status === 404) {
                state.invoices = Array.isArray(res.data.invoices) ? res.data.invoices
                    : state.invoices.filter((item) => item.name !== invoice.name);
                state.counts.invoices = state.invoices.length;
                closeSheet();
                saveSnapshot();
                render();
                toast(res.ok ? 'Фото удалено' : 'Фото уже удалено');
                return;
            }
            toast(errorText(res, 'Не получилось удалить фото'), true);
        });
    }

    // ==================== Камера ====================

    function cameraError(error) {
        const name = error && error.name;
        if (name === 'NotAllowedError' || name === 'SecurityError') return 'Нет доступа к камере — разрешите его в настройках браузера';
        if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'Камера не найдена';
        if (error && error.code === 'polyfill_failed') return 'Не загрузился модуль распознавания кодов — проверьте интернет и откройте камеру ещё раз (или введите код вручную)';
        if (error && error.code === 'no_detector') return 'Этот браузер не читает коды с камеры — обновите Safari или Chrome либо введите код вручную';
        return 'Камера не включилась' + (error && error.message ? ': ' + error.message : '');
    }

    // Детектор кодов: встроенный BarcodeDetector (Chrome на Android), а если он не
    // умеет DataMatrix (iPhone, Chrome на компьютере) — библиотека-полифил с тем же API
    // (loadPolyfill: своя копия, затем CDN).
    async function createDetector() {
        let Detector = window.BarcodeDetector;
        let formats = [];
        if (Detector && typeof Detector.getSupportedFormats === 'function') {
            try {
                const supported = await Detector.getSupportedFormats();
                formats = CAMERA_FORMATS.filter((format) => supported.indexOf(format) !== -1);
            } catch (error) { formats = []; }
        }
        if (!Detector || formats.indexOf('data_matrix') === -1) {
            const loaded = await loadPolyfill();
            Detector = loaded.Detector;
            formats = loaded.formats;
        }
        if (!Detector || !formats.length) {
            const error = new Error('no detector');
            error.code = 'no_detector';
            throw error;
        }
        return new Detector({ formats });
    }

    // Полифил по очереди из CAMERA_POLYFILLS. Модуль распознавания (.wasm) полифил
    // грузит лениво, при первом разборе кадра, и его сбой виден только как ошибка
    // detect(): поэтому сразу разбираем пустую картинку — не загрузился .wasm, значит
    // источник не годится и пробуем следующий (иначе камера молча ничего не читала бы).
    // Удачный полифил запоминается на страницу; неудачный — нет: следующее включение
    // камеры заново настроит модуль, и .wasm скачается ещё раз.
    async function loadPolyfill() {
        if (polyfill) return polyfill;
        let failed = typeof WebAssembly === 'object' && WebAssembly !== null;
        if (!failed) {
            // Старый браузер без WebAssembly: полифил в нём не работает, интернет ни при чём.
            const error = new Error('no webassembly');
            error.code = 'no_detector';
            throw error;
        }
        failed = false;
        for (const source of CAMERA_POLYFILLS) {
            try {
                const module = await import(source.url);
                if (!module || !module.BarcodeDetector) continue;
                if (source.wasm && typeof module.setZXingModuleOverrides === 'function') {
                    // Движок распознавания (.wasm) — рядом со своей копией, а не с CDN.
                    const wasm = source.wasm;
                    module.setZXingModuleOverrides({
                        locateFile: (file, prefix) => (/\.wasm$/.test(file) ? wasm : prefix + file),
                    });
                }
                setCamStatus('Загружаю модуль распознавания…');
                await probeDetector(module.BarcodeDetector);
                polyfill = { Detector: module.BarcodeDetector, formats: CAMERA_FORMATS.slice() };
                return polyfill;
            } catch (error) {
                failed = true;       // не загрузился — следующий источник
            }
        }
        const error = new Error('polyfill');
        error.code = failed ? 'polyfill_failed' : 'no_detector';
        throw error;
    }

    function probeDetector(Detector) {
        if (typeof ImageData !== 'function') return Promise.resolve();
        const probe = new Detector({ formats: ['data_matrix'] });
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('polyfill timeout')), CAMERA_POLYFILL_LOAD_MS);
            Promise.resolve()
                .then(() => probe.detect(new ImageData(1, 1)))
                .then(() => { clearTimeout(timer); resolve(); }, (error) => { clearTimeout(timer); reject(error); });
        });
    }

    async function openCamera() {
        if (cam.open || state.view !== 'scan') return;
        const media = navigator.mediaDevices;
        if (!media || typeof media.getUserMedia !== 'function') {
            toast('Камера недоступна в этом браузере (нужен HTTPS и разрешение)', true);
            return;
        }
        cam.open = true;
        const attempt = ++cam.attempt;
        const alive = () => cam.open && cam.attempt === attempt;
        cam.seen = new Map();
        cam.dm = new Map();
        cam.eans = new Map();
        cam.counted = new Map();
        cam.fails = 0;
        $('rc-cam-wrap').hidden = false;
        $('rc-torch').hidden = true;
        document.documentElement.classList.add('rc-lock', 'rc-cam-on');
        setCamStatus('Включаю камеру…');          // заодно рисует окно камеры (renderCamera)
        try {
            const detector = await createDetector();
            if (!alive()) return;                                    // закрыли, пока грузился детектор
            cam.detector = detector;
            const stream = await media.getUserMedia({ video: CAMERA_VIDEO, audio: false });
            if (!alive()) {
                // Камеру закрыли (или открыли заново), пока ждали разрешения: этот поток лишний.
                stream.getTracks().forEach((track) => track.stop());
                return;
            }
            cam.stream = stream;
            const video = $('rc-video');
            video.srcObject = stream;
            try { await video.play(); } catch (error) { /* autoplay muted — видео пойдёт само */ }
            cam.track = stream.getVideoTracks()[0] || null;
            const caps = cam.track && typeof cam.track.getCapabilities === 'function' ? cam.track.getCapabilities() : {};
            $('rc-torch').hidden = !(caps && caps.torch);
            setCamStatus('Наведите камеру на код');
            keepAwake(attempt);
            tickCamera();
        } catch (error) {
            if (!alive()) return;
            closeCamera();
            toast(cameraError(error), true);
        }
    }

    // Проверка кадра — одна цепочка на включение камеры: следующая проверка ставится в конце
    // текущей. Пока открыто окно (state.sheet), кадр не разбирается — цепочка только ждёт.
    function tickCamera() {
        if (!cam.open || !cam.detector) return;
        if (state.sheet) {
            cam.timer = setTimeout(tickCamera, CAMERA_TICK_MS);
            return;
        }
        // Номер включения: разбор, начатый до закрытия камеры, не продолжает цепочку после
        // нового включения (иначе кадры проверяли бы две цепочки сразу).
        const attempt = cam.attempt;
        const video = $('rc-video');
        const ready = video.readyState === undefined || video.readyState >= 2;
        new Promise((resolve) => resolve(ready ? cam.detector.detect(video) : []))
            .then((found) => {
                // Кадр разобрался уже после открытия окна (или после закрытия камеры) — не в
                // счёт: поздний код через handleCode отменил бы окно «Завершить».
                if (!cam.open || cam.attempt !== attempt || state.sheet) return;
                cam.fails = 0;
                const codes = (found || []).filter((item) => item && item.rawValue).map((item) => String(item.rawValue));
                const frameHasDm = codes.some((code) => {
                    const parsed = parseLocal(code);
                    return Boolean(parsed && parsed.ok && parsed.kind === 'datamatrix');
                });
                for (const code of codes) onCameraCode(code, frameHasDm);
                settleCameraEans();
            })
            .catch(() => {
                // Кадр не разобрался — следующий. Много подряд — модуль распознавания сломан
                // (оборвалась загрузка, телефон выгрузил память): подсказать, а не молчать.
                if (cam.attempt !== attempt) return;
                cam.fails += 1;
                if (cam.open && cam.fails === CAMERA_FAILS_HINT) {
                    setCamStatus('Камера не читает коды — закройте её и откройте снова');
                }
            })
            .then(() => {
                if (cam.open && cam.attempt === attempt) cam.timer = setTimeout(tickCamera, CAMERA_TICK_MS);
            });
    }

    // Код с камеры. Камера видит сразу всё, что в кадре: DataMatrix и штрихкод (EAN)
    // одной бутылки, плёнку упаковки поверх банок. Правила, чтобы одна бутылка не стала
    // двумя штуками (frameHasDm — в этом же кадре прочитан хоть один код ЧЗ):
    // 1. Код, который не уходит из кадра, считается один раз (CAMERA_REPEAT_MS).
    // 2. Код ЧЗ (DataMatrix) считается сразу.
    // 3. Штрихкод не считается, если: он в одном кадре с любым кодом ЧЗ (та же бутылка
    //    или плёнка упаковки поверх банок); код ЧЗ того же GTIN виден за последние
    //    CAMERA_REPEAT_MS; у товара в этой приёмке уже есть коды ЧЗ (маркированный товар
    //    считается только по ним — подсказка на экране камеры).
    // 4. Иначе штрихкод ждёт CAMERA_EAN_WAIT_MS (settleCameraEans): за это время появился
    //    код ЧЗ того же GTIN или код ЧЗ в одном кадре с ним — не считается, нет — считается.
    //    Немаркированный товар после бутылки считается: кода ЧЗ рядом с ним нет.
    // 5. Штрихкод уже посчитан, а не позже CAMERA_REPEAT_MS прочитан код ЧЗ того же GTIN
    //    или код ЧЗ в одном кадре с ним — штрихкод отзывается (retractCameraEan): малый
    //    DataMatrix читается позже крупного штрихкода, а это та же бутылка.
    function onCameraCode(raw, frameHasDm) {
        const now = clock();
        const parsed = parseLocal(raw);
        const gtin = parsed && parsed.ok && parsed.gtin ? parsed.gtin : '';
        const isEan = Boolean(gtin) && parsed.kind === 'ean';
        if (gtin && parsed.kind === 'datamatrix') {
            cam.dm.set(gtin, now);
            for (const [code, pending] of cam.eans) if (pending.gtin === gtin) cam.eans.delete(code);
            retractCounted(gtin, now);
        }
        if (isEan && frameHasDm) {
            cam.eans.delete(raw);                               // ждал — но рядом код ЧЗ
            retractCounted(gtin, now);
        }
        for (const [key, at] of cam.dm) if (now - at > CAMERA_REPEAT_MS) cam.dm.delete(key);
        for (const [key, counted] of cam.counted) if (now - counted.at > CAMERA_REPEAT_MS) cam.counted.delete(key);
        const seenAt = cam.seen.get(raw);
        cam.seen.set(raw, now);     // окно скользит, пока код в кадре
        for (const [code, at] of cam.seen) if (now - at > CAMERA_REPEAT_MS) cam.seen.delete(code);
        if (seenAt !== undefined && now - seenAt < CAMERA_REPEAT_MS) return;
        if (isEan) {
            if (frameHasDm || cam.dm.has(gtin)) return;         // рядом код ЧЗ — это не отдельная штука
            if (markedInReceipt(gtin)) {
                setCamStatus('Штрихкод не считается: у товара есть код Честного знака — наведите на него');
                return;
            }
            cam.eans.set(raw, { gtin, at: now });               // решится в settleCameraEans
            return;
        }
        handleCode(raw, 'camera');
    }

    // Посчитанный камерой штрихкод этого GTIN не старше CAMERA_REPEAT_MS — отозвать.
    function retractCounted(gtin, now) {
        const counted = cam.counted.get(gtin);
        if (!counted) return;
        cam.counted.delete(gtin);
        if (now - counted.at <= CAMERA_REPEAT_MS) retractCameraEan(counted.item);
    }

    // Штрихкоды, прождавшие CAMERA_EAN_WAIT_MS без кода ЧЗ рядом, — в счёт.
    function settleCameraEans() {
        if (!cam.open || !cam.eans.size) return;
        const now = clock();
        for (const [code, pending] of cam.eans) {
            if (now - pending.at < CAMERA_EAN_WAIT_MS) continue;
            cam.eans.delete(code);
            if (cam.dm.has(pending.gtin)) continue;
            const item = handleCode(code, 'camera');
            if (item && item.local === 'accepted') cam.counted.set(pending.gtin, { item, at: clock() });
            if (!cam.open) return;                               // скан закрыл камеру (приёмку закрыли)
        }
    }

    // В этой приёмке уже есть принятые коды ЧЗ этого GTIN (ключ DataMatrix — «GTIN|серия»).
    function markedInReceipt(gtin) {
        const prefix = gtin + '|';
        for (const key of state.dmKeys) if (String(key).indexOf(prefix) === 0) return true;
        return false;
    }

    // Отозвать штрихкод, посчитанный камерой (правило 5 у onCameraCode): как «Отменить
    // последний», но для этого скана. Ещё в очереди — убрать (или пометить отменённым,
    // если запрос уже уходил); уже на сервере — в очередь задание удалить его там.
    function retractCameraEan(item) {
        if (!item || item.undo) return;
        if (state.queue.indexOf(item) !== -1) {
            if (item.tries > 0) {
                item.undo = true;
                saveQueue();
            } else {
                removeItem(item);
            }
        } else if (item.saved_scan_id) {
            state.queue.push(Object.assign({}, item, {
                client_id: newClientId(), undo: true, scan_id: item.saved_scan_id, tries: 1, at: Date.now(),
            }));
            saveQueue();
        } else {
            return;                  // сервер этот скан не посчитал — отзывать нечего
        }
        render();
        flush();
    }

    // Экран не гаснет, пока открыта камера (Wake Lock; где его нет — как раньше).
    function keepAwake(attempt) {
        const wakeLock = navigator.wakeLock;
        if (!wakeLock || typeof wakeLock.request !== 'function' || cam.wake) return;
        Promise.resolve()
            .then(() => wakeLock.request('screen'))
            .then((sentinel) => {
                if (cam.open && cam.attempt === attempt && !cam.wake) cam.wake = sentinel;
                else if (sentinel && typeof sentinel.release === 'function') sentinel.release().catch(() => {});
            })
            .catch(() => { /* не дали (энергосбережение) — экран погаснет по таймеру телефона */ });
    }

    function releaseWake() {
        const sentinel = cam.wake;
        cam.wake = null;
        if (sentinel && typeof sentinel.release === 'function') {
            try { Promise.resolve(sentinel.release()).catch(() => {}); } catch (error) { /* уже снят */ }
        }
    }

    function closeCamera() {
        if (!cam.open && !cam.stream) return;
        cam.open = false;
        cam.attempt += 1;          // незавершённое включение увидит, что его отменили
        clearTimeout(cam.timer);
        cam.timer = null;
        if (cam.stream) cam.stream.getTracks().forEach((track) => { try { track.stop(); } catch (error) { /* уже остановлен */ } });
        cam.stream = null;
        cam.track = null;
        cam.torch = false;
        cam.eans.clear();          // штрихкод без сигнала «принято» не посчитан — приёмщик видел это
        cam.dm.clear();
        cam.counted.clear();
        cam.hint = null;
        releaseWake();
        const video = $('rc-video');
        if (video) video.srcObject = null;
        $('rc-cam-wrap').hidden = true;
        $('rc-torch').setAttribute('aria-pressed', 'false');
        document.documentElement.classList.remove('rc-cam-on');
        if (!state.sheet) document.documentElement.classList.remove('rc-lock');
    }

    function toggleTorch() {
        if (!cam.track || typeof cam.track.applyConstraints !== 'function') return;
        const next = !cam.torch;
        cam.track.applyConstraints({ advanced: [{ torch: next }] })
            .then(() => {
                cam.torch = next;
                $('rc-torch').setAttribute('aria-pressed', next ? 'true' : 'false');
            })
            .catch(() => toast('Фонарик не включился', true));
    }

    // Подсказка в окне камеры («Включаю камеру…», «Штрихкод не считается…», «Камера не читает
    // коды…»): держится до следующего результата скана, а не до следующей отрисовки.
    function setCamStatus(text) {
        cam.hint = { text, last: state.last };
        renderCamera();
    }

    // ==================== Кнопки: защита от двойного нажатия ====================

    async function act(key, button, run) {
        if (state.busy[key]) return;
        state.busy[key] = true;
        if (button) {
            button.disabled = true;
            button.classList.add('is-busy');
        }
        try {
            await run();
        } catch (error) {
            console.warn('[RC]', error);
            toast('Не получилось: ' + ((error && error.message) || 'ошибка'), true);
        } finally {
            state.busy[key] = false;
            if (button) {
                button.disabled = false;
                button.classList.remove('is-busy');
            }
        }
    }

    // ==================== Отрисовка ====================

    function loginHref() {
        const next = state.receipt ? PAGE + '?r=' + state.receipt.id : PAGE;
        return '/login?next=' + encodeURIComponent(next);
    }

    function render() {
        $('rc-start').hidden = state.view !== 'start';
        $('rc-scan').hidden = state.view !== 'scan';
        $('rc-done').hidden = state.view !== 'done';
        $('rc-auth').hidden = !state.authRequired;
        $('rc-login').setAttribute('href', loginHref());
        $('rc-storage').hidden = !state.storageBroken;
        if (state.view === 'start') renderStart();
        else if (state.view === 'scan') renderScan();
        else renderDone();
        renderCamera();
        renderFinishSheet();
    }

    function renderStart() {
        const waiting = state.queue.length;
        const pendingNode = $('rc-start-pending');
        pendingNode.hidden = !waiting;
        pendingNode.textContent = waiting
            ? 'Не отправлено сканов из телефона: ' + waiting + '. Они уйдут на сервер, когда появится связь.'
            : '';
        const errorNode = $('rc-start-error');
        errorNode.hidden = !state.startError;
        errorNode.textContent = state.startError;

        const list = $('rc-open-list');
        list.textContent = '';
        for (const receipt of state.open) {
            const row = el('div', 'rc-open-row');
            const info = el('div', 'rc-open-info');
            info.appendChild(el('span', 'rc-open-title', 'Приёмка №' + receipt.id));
            const started = dateTimeText(receipt.created_at);
            info.appendChild(el('span', 'rc-open-meta',
                'начата ' + started + (receipt.created_by ? ', ' + receipt.created_by : '')));
            const counts = Object.assign({}, EMPTY_COUNTS, receipt.counts || {});
            const line = el('span', 'rc-open-counts',
                counts.units + ' шт., ' + counts.gtins + ' ' + plural(counts.gtins, POSITION_WORDS));
            const queued = pendingFor(receipt.id);
            if (queued) line.appendChild(el('em', null, ', в телефоне ещё ' + queued));
            info.appendChild(line);
            // Обычная кнопка: главная (оранжевая) на экране одна — «Новая приёмка».
            const button = el('button', 'rc-btn', 'Продолжить');
            button.type = 'button';
            button.addEventListener('click', () => act('open', button, () => loadReceipt(receipt.id)));
            row.appendChild(info);
            row.appendChild(button);
            list.appendChild(row);
        }
        $('rc-open-empty').hidden = !state.openLoaded || state.open.length > 0;
        $('rc-open-count').textContent = state.openLoaded ? String(state.open.length) : 'загрузка…';
    }

    function renderScan() {
        const receipt = state.receipt;
        $('rc-title').textContent = 'Приёмка №' + receipt.id;
        const started = dateTimeText(receipt.created_at);
        $('rc-meta').textContent = (started ? 'начата ' + started : '') + (receipt.created_by ? ', ' + receipt.created_by : '');
        $('rc-units').textContent = String(displayUnits());
        const gtins = displayGtins();
        $('rc-gtins').textContent = String(gtins);
        $('rc-gtins-label').textContent = plural(gtins, POSITION_WORDS);

        const pending = pendingInfo(receipt.id);
        const pendingNode = $('rc-pending');
        pendingNode.hidden = !pending.n;
        pendingNode.textContent = pending.text;
        pendingNode.classList.toggle('is-bad', pending.bad);

        const status = $('rc-status');
        const last = state.last;
        status.textContent = last ? last.message : 'Сканируйте товар';
        status.classList.toggle('is-ok', Boolean(last) && last.tone === 'ok');
        status.classList.toggle('is-repeat', Boolean(last) && last.tone === 'repeat');
        status.classList.toggle('is-bad', Boolean(last) && last.tone === 'bad');
        $('rc-last').textContent = last
            ? (last.gtin ? 'GTIN ' + last.gtin : shortRaw(last.raw)) + (last.at ? ', ' + timeText(last.at) : '')
            : '';
        $('rc-offline').hidden = !state.stale;

        renderInvoices();
        renderRecent();
    }

    function renderInvoices() {
        const box = $('rc-invoices-box');
        box.hidden = !state.invoices.length;
        $('rc-invoices-count').textContent = state.invoices.length ? String(state.invoices.length) : '';
        const list = $('rc-invoices');
        list.textContent = '';
        state.invoices.forEach((invoice, index) => {
            const row = el('div', 'rc-invoice');
            const link = el('a', null, 'Фото ' + (index + 1));
            link.setAttribute('href', API + '/invoice/' + encodeURIComponent(invoice.name));
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener');
            row.appendChild(link);
            row.appendChild(el('span', 'rc-invoice-time', timeText(invoice.uploaded_at)));
            const remove = el('button', 'rc-link-btn', 'Удалить');
            remove.type = 'button';
            remove.addEventListener('click', () => confirmDeleteInvoice(invoice));
            row.appendChild(remove);
            list.appendChild(row);
        });
    }

    function queuedTag(item) {
        if (item.undo) return ['Отменяется', 'is-wait'];
        if (item.local === 'rejected') return ['Не распознан', 'is-bad'];
        if (item.local === 'repeat') return ['Повтор', 'is-repeat'];
        return ['В телефоне', 'is-wait'];
    }

    function serverTag(scan) {
        if (scan.accepted) return ['Принят', 'is-ok'];
        if (scan.reason === 'repeat') return ['Повтор', 'is-repeat'];
        return ['Не распознан', 'is-bad'];
    }

    function renderRecent() {
        const rows = [];
        const queued = queueOf(state.receipt.id);
        for (let i = queued.length - 1; i >= 0; i -= 1) {
            const item = queued[i];
            rows.push({ at: item.client_time, tag: queuedTag(item), code: item.gtin || shortRaw(item.code) });
        }
        for (const scan of state.recent) {
            rows.push({ at: scan.scanned_at, tag: serverTag(scan), code: scan.gtin || scan.raw_short || '' });
        }
        const list = $('rc-recent');
        list.textContent = '';
        for (const row of rows.slice(0, RECENT_SHOWN)) {
            const node = el('div', 'rc-row');
            node.appendChild(el('span', 'rc-row-time', timeText(row.at)));
            node.appendChild(el('span', 'rc-tag ' + row.tag[1], row.tag[0]));
            node.appendChild(el('span', 'rc-row-code', row.code));
            list.appendChild(node);
        }
        $('rc-recent-empty').hidden = rows.length > 0;
        const parts = [];
        if (state.counts.rejected) parts.push('не распознано: ' + state.counts.rejected);
        if (state.counts.repeats) parts.push('повторов: ' + state.counts.repeats);
        $('rc-recent-count').textContent = parts.join(', ');
    }

    function renderDone() {
        const receipt = state.done || { id: '', counts: EMPTY_COUNTS };
        const counts = Object.assign({}, EMPTY_COUNTS, receipt.counts || {});
        $('rc-done-title').textContent = 'Приёмка №' + receipt.id + ' передана в разбор';
        $('rc-done-text').textContent = 'Посчитано: ' + counts.units + ' шт., ' + counts.gtins + ' '
            + plural(counts.gtins, POSITION_WORDS) + '. Сервер сверяет коды с iiko — итог появится в «Разборе приёмок».';
        $('rc-done-review').setAttribute('href', REVIEW_PAGE + '?receipt=' + receipt.id);
    }

    function renderCamera() {
        if (!cam.open || !state.receipt) return;
        $('rc-cam-title').textContent = 'Приёмка №' + state.receipt.id;
        $('rc-cam-units').textContent = displayUnits() + ' шт.';
        const gtins = displayGtins();
        $('rc-cam-gtins').textContent = gtins + ' ' + plural(gtins, POSITION_WORDS);
        const pending = pendingInfo(state.receipt.id);
        const pendingNode = $('rc-cam-pending');
        pendingNode.hidden = !pending.n;
        pendingNode.textContent = pending.text;
        pendingNode.classList.toggle('is-bad', pending.bad);
        // Плашка результата: цвет — только у результата скана, подсказка — без заливки.
        const last = state.last;
        const hint = cam.hint && cam.hint.last === last ? cam.hint.text : '';
        const tone = !hint && last ? last.tone : '';
        const status = $('rc-cam-status');
        status.textContent = hint || (last ? last.message : 'Наведите камеру на код');
        status.classList.toggle('is-ok', tone === 'ok');
        status.classList.toggle('is-repeat', tone === 'repeat');
        status.classList.toggle('is-bad', tone === 'bad');
    }

    // ==================== Запуск ====================

    function bind() {
        window.addEventListener('keydown', onKeyDown, true);
        window.addEventListener('pointerdown', unlockAudio, { passive: true });
        window.addEventListener('touchstart', unlockAudio, { passive: true });
        // iOS Safari разрешает звук только из обработчика «полного» жеста (touchend, click).
        window.addEventListener('touchend', unlockAudio, { passive: true, capture: true });
        window.addEventListener('click', (event) => {
            unlockAudio();
            // Кнопка, нажатая пальцем или мышью, не держит фокус: Enter сканера не нажмёт её
            // ещё раз (клик с клавиатуры, detail 0, фокус сохраняет — для доступности).
            const button = event.target && event.target.closest ? event.target.closest('button') : null;
            if (button && event.detail > 0) setTimeout(() => button.blur(), 0);
        }, true);

        $('rc-new').addEventListener('click', () => startNew($('rc-new')));
        $('rc-done-new').addEventListener('click', () => startNew($('rc-done-new')));
        $('rc-done-back').addEventListener('click', () => { showStart(); });
        $('rc-back').addEventListener('click', () => { showStart(); });
        $('rc-camera').addEventListener('click', () => { unlockAudio(); openCamera(); });
        $('rc-photo').addEventListener('click', () => $('rc-photo-input').click());
        $('rc-photo-input').addEventListener('change', () => {
            const input = $('rc-photo-input');
            const file = input.files && input.files[0];
            input.value = '';
            if (file) uploadPhoto(file);
        });
        $('rc-undo').addEventListener('click', () => undoLast($('rc-undo')));
        $('rc-finish').addEventListener('click', () => requestFinish());
        $('rc-manual').addEventListener('click', () => openManual());

        $('rc-sheet-ok').addEventListener('click', () => {
            if (state.sheet && typeof state.sheet.onOk === 'function') state.sheet.onOk($('rc-sheet-ok'));
        });
        $('rc-sheet-cancel').addEventListener('click', () => closeSheet());
        $('rc-sheet-wrap').addEventListener('click', (event) => {
            if (event.target === $('rc-sheet-wrap')) closeSheet();
        });
        $('rc-sheet-retry').addEventListener('click', () => flush());
        $('rc-sheet-photo').addEventListener('click', () => startInvoicePhoto());
        $('rc-sheet-input').addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && state.sheet && state.sheet.kind === 'manual') {
                event.preventDefault();
                submitManual();
            }
        });
        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            if (state.sheet) closeSheet();
            else if (cam.open) closeCamera();
        });

        $('rc-cam-close').addEventListener('click', () => closeCamera());
        $('rc-cam-manual').addEventListener('click', () => openManual());
        $('rc-cam-undo').addEventListener('click', () => undoLast($('rc-cam-undo')));
        $('rc-cam-finish').addEventListener('click', () => requestFinish());
        $('rc-torch').addEventListener('click', () => toggleTorch());

        window.addEventListener('online', () => {
            state.offline = false;
            flush();
        });
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                closeCamera();     // камеру отпускаем: телефон ушёл в карман или в другое приложение
                return;
            }
            flush();
        });
        window.addEventListener('pagehide', () => closeCamera());
    }

    function receiptFromUrl() {
        let raw = '';
        try { raw = new URLSearchParams(location.search).get('r') || ''; } catch (error) { raw = ''; }
        return RECEIPT_PARAM_RE.test(raw) ? Number(raw) : 0;
    }

    async function boot() {
        state.queue = readStoredQueue();
        bind();
        const receiptId = receiptFromUrl();
        // Сначала приёмка, потом очередь: иначе ответ GET мог бы затереть счётчики,
        // уже пришедшие с ответом на скан.
        if (receiptId) await loadReceipt(receiptId);
        else await showStart();
        if (state.queue.length) flush();
    }

    window.__rcScan = {
        state,
        cam,
        ready: null,
        handleCode,
        onKeyDown,
        flush,
        undoLast,
        requestFinish,
        doFinish,
        startNew,
        loadReceipt,
        loadOpenList,
        uploadPhoto,
        openCamera,
        closeCamera,
        onCameraCode,
        openManual,
        submitManual,
        displayUnits,
        displayGtins,
        pendingFor,
        render,
        charFor,
        constants: {
            QUEUE_KEY, SNAPSHOT_KEY, SCAN_GAP_MS, MIN_CODE_LEN, RETRY_DELAYS_MS, CAMERA_REPEAT_MS, CAMERA_EAN_WAIT_MS,
            CAMERA_VIDEO, CAMERA_POLYFILLS, CAMERA_POLYFILL_LOAD_MS, CAMERA_FAILS_HINT,
            PHOTO_MAX_SIDE, PHOTO_QUALITY, TONES, VIBRATION,
        },
    };
    window.__rcScan.ready = boot().catch((error) => console.warn('[RC] запуск', error));
})();

/* Разбор кода со сканера на приёмке РЦ — JS-порт core/receiving_codes.py: window.RcCodes.

   Зачем в браузере. Приёмщик получает сигнал «принято / не то» сразу после
   скана, ещё до ответа сервера (сеть на складе бывает плохой, сканы стоят в
   очереди). Сервер всё равно разбирает код заново и его ответ главнее.

   Контракт тот же, что у Python (правила и примеры — в докстринге модуля):
     RcCodes.parseCode(raw) -> {ok, kind, gtin, serial, key, code, reason, message}
     RcCodes.gtinCheckOk(g) -> bool      контрольная цифра GS1 для 14 цифр
     RcCodes.barcodeForIiko(g) -> str    EAN-8 / EAN-13 / GTIN-14 для карточки iiko
   Паритет держит общая фикстура tests/fixtures/receiving_codes.json
   (tests/test_receiving_codes.py и tests/test_receiving_codes.mjs), плюс
   случайные строки в pytest сравниваются с Node побайтно.

   Нормализация (по порядку): обрезать пробелы/\t/\r/\n по краям -> длина больше
   MAX_CODE_LEN кодовых точек = too_long -> есть кириллица = раскладка ЙЦУКЕН
   переводится в US QWERTY -> «␝» = GS, ведущие GS убрать -> префикс сканера
   ]d2/]E0/]Q3/]C1 убрать -> «(01)…(21)…» = 01 + GTIN + 21 + серийник + GS.

   Длины и срезы — в кодовых точках (Array.from), как len() в Python: символ вне
   BMP в UTF-16 занимает две позиции, и без этого ключ и граница too_long
   разъехались бы с сервером.

   Стиль: IIFE, 'use strict', var и function, без модулей; в Node — module.exports. */
(function (root) {
    'use strict';

    // --- пределы ---
    var MAX_CODE_LEN = 512;   // длиннее — мусор: ЕГАИС PDF417 ~150, DataMatrix пива ~31-45
    var KEY_LEN = 200;        // ключ нераспознанного кода — только для диагностики

    // --- виды кода и причины отказа ---
    var KIND = {
        DATAMATRIX: 'datamatrix',   // 01 + GTIN + 21 + серийник: экземпляр бутылки
        EAN: 'ean',                 // GTIN без серийника: EAN-8/13, UPC-A, GTIN-14
        SSCC: 'sscc',               // код короба или паллеты
        UNKNOWN: 'unknown',
        EMPTY: 'empty'
    };
    var REASON = {
        EMPTY: 'empty',
        TOO_LONG: 'too_long',
        SSCC: 'sscc',
        BAD_CHECK: 'bad_check_digit',
        UNSUPPORTED: 'unsupported'
    };

    // --- тексты для приёмщика ---
    var MSG_OK = 'Принято';
    var MSG_UNREADABLE = 'Код не распознан — повторите';
    var MSG_BAD_CHECK = 'Код прочитан с ошибкой — повторите';
    var MSG_SSCC = 'Код короба или паллеты — отсканируйте бутылку';
    var MESSAGES = {};
    MESSAGES[REASON.EMPTY] = MSG_UNREADABLE;
    MESSAGES[REASON.TOO_LONG] = MSG_UNREADABLE;
    MESSAGES[REASON.UNSUPPORTED] = MSG_UNREADABLE;
    MESSAGES[REASON.BAD_CHECK] = MSG_BAD_CHECK;
    MESSAGES[REASON.SSCC] = MSG_SSCC;

    // --- структура GS1 ---
    var GS = '\x1d';                   // разделитель групп (FNC1)
    var GS_PICTURE = '\u241d';         // «␝» — так GS приходит от части сканеров
    var AI_SSCC = '00';
    var AI_GTIN = '01';
    var AI_SERIAL = '21';
    var AI_CRYPTO = '93';         // код проверки Честного ЗНАКа (у пива 4 символа)
    var GTIN_LEN = 14;
    var EAN_LENGTHS = [8, 12, 13, 14];   // EAN-8, UPC-A, EAN-13, GTIN-14
    var SSCC_LEN = 20;                   // '00' + 18 цифр
    var GTIN_END = AI_GTIN.length + GTIN_LEN;          // 16
    var SERIAL_START = GTIN_END + AI_SERIAL.length;    // 18
    var CRYPTO_TAIL_LEN = 6;                           // '93' + 4 символа
    var MIN_TAIL_FOR_CRYPTO = CRYPTO_TAIL_LEN + 1;     // от серийника остаётся хотя бы 1 символ
    var EAN8_PREFIX = '000000';          // 14 - 8 = 6 ведущих нулей
    var EAN8_LEN = 8;
    var EAN13_LEN = 13;
    var ZEROS = '00000000000000';        // для zfill до 14

    // --- раскладка ЙЦУКЕН -> US QWERTY (символ той же клавиши), как в Python ---
    var LAYOUT_PAIRS = [
        ['ё', '`'], ['Ё', '~'],
        ['йцукенгшщзхъ', 'qwertyuiop[]'],
        ['ЙЦУКЕНГШЩЗХЪ', 'QWERTYUIOP{}'],
        ['фывапролджэ', "asdfghjkl;'"],
        ['ФЫВАПРОЛДЖЭ', 'ASDFGHJKL:"'],
        ['ячсмитьбю.', 'zxcvbnm,./'],
        ['ЯЧСМИТЬБЮ,', 'ZXCVBNM<>?'],
        ['"№;:?', '@#$^&'],    // Shift+2, 3, 4, 6, 7
        ['/', '|']             // Shift+\
    ];
    var RU_TO_EN = {};
    LAYOUT_PAIRS.forEach(function (pair) {
        for (var i = 0; i < pair[0].length; i++) RU_TO_EN[pair[0].charAt(i)] = pair[1].charAt(i);
    });

    var DIGITS_RE = /^[0-9]+$/;
    var GTIN14_RE = /^[0-9]{14}$/;
    var CYRILLIC_RE = /[\u0400-\u04ff]/;
    var SYMBOLOGY_RE = /^\][A-Za-z][0-9]/;
    var HRI_SSCC_RE = /^\(00\)([0-9]{18})$/;
    var HRI_GTIN_RE = /^\(01\)([0-9]{14})([\s\S]*)$/;
    var HRI_SERIAL_PREFIX = '(21)';
    var GS1_TAIL_RE = /^[\x1d\x21-\x7e]+$/;   // GS + печатный ASCII без пробела
    var LEADING_GS_RE = /^\x1d+/;
    var EDGE_WS = ' \t\r\n';   // что срезаем по краям (сканер дописывает Enter/Tab)

    /** Первые n кодовых точек строки (как s[:n] в Python). */
    function cpHead(s, n) {
        if (s.length <= n) return s;            // UTF-16 единиц не больше n — точек тоже
        return Array.from(s).slice(0, n).join('');
    }

    /** Длиннее MAX_CODE_LEN кодовых точек (как len(s) > MAX_CODE_LEN в Python)? */
    function tooLong(s) {
        if (s.length <= MAX_CODE_LEN) return false;   // UTF-16 единиц не больше — точек тоже
        return Array.from(s).length > MAX_CODE_LEN;
    }

    /** Как str.strip(' \t\r\n') в Python. Циклом, а не /\s+$/: регулярка на длинной
        строке пробелов с символом в конце работает квадратично. */
    function stripEdges(s) {
        var start = 0;
        var end = s.length;
        while (start < end && EDGE_WS.indexOf(s.charAt(start)) !== -1) start++;
        while (end > start && EDGE_WS.indexOf(s.charAt(end - 1)) !== -1) end--;
        return s.slice(start, end);
    }

    function zfill14(s) {
        return s.length >= GTIN_LEN ? s : (ZEROS + s).slice(-GTIN_LEN);
    }

    function gtinCheckOk(gtin14) {
        if (typeof gtin14 !== 'string' || !GTIN14_RE.test(gtin14)) return false;
        var total = 0;
        for (var i = 0; i < GTIN_LEN - 1; i++) {
            total += Number(gtin14.charAt(i)) * (i % 2 === 0 ? 3 : 1);
        }
        return (10 - total % 10) % 10 === Number(gtin14.charAt(GTIN_LEN - 1));
    }

    function barcodeForIiko(gtin14) {
        var s = gtin14 == null ? '' : stripEdges(String(gtin14));
        if (!DIGITS_RE.test(s) || s.length > GTIN_LEN) return s;
        s = zfill14(s);
        if (s.indexOf(EAN8_PREFIX) === 0) return s.slice(-EAN8_LEN);
        if (s.charAt(0) === '0') return s.slice(-EAN13_LEN);
        return s;
    }

    function result(ok, kind, gtin, serial, key, code, reason) {
        return {
            ok: ok,
            kind: kind,
            gtin: gtin,
            serial: serial,
            key: key,
            code: code,
            reason: reason,
            message: ok ? MSG_OK : MESSAGES[reason]
        };
    }

    function fail(kind, reason, code) {
        return result(false, kind, null, null, cpHead(code, KEY_LEN), code, reason);
    }

    function translateLayout(text) {
        var out = '';
        for (var i = 0; i < text.length; i++) {
            var ch = text.charAt(i);
            out += Object.prototype.hasOwnProperty.call(RU_TO_EN, ch) ? RU_TO_EN[ch] : ch;
        }
        return out;
    }

    function fromHumanReadable(code) {
        var m = HRI_SSCC_RE.exec(code);
        if (m) return AI_SSCC + m[1];
        m = HRI_GTIN_RE.exec(code);
        if (!m) return code;
        var gtin = m[1];
        var rest = m[2];
        if (!rest) return AI_GTIN + gtin;
        if (rest.indexOf(HRI_SERIAL_PREFIX) === 0) {
            var serial = rest.slice(HRI_SERIAL_PREFIX.length).split('(')[0];
            if (serial) return AI_GTIN + gtin + AI_SERIAL + serial + GS;
        }
        return code;
    }

    function normalize(text) {
        if (CYRILLIC_RE.test(text)) text = translateLayout(text);
        text = text.split(GS_PICTURE).join(GS).replace(LEADING_GS_RE, '');
        var m = SYMBOLOGY_RE.exec(text);
        if (m) text = text.slice(m[0].length).replace(LEADING_GS_RE, '');
        return fromHumanReadable(text);
    }

    function serialFromTail(tail) {
        var gs = tail.indexOf(GS);
        if (gs !== -1) return tail.slice(0, gs);
        if (tail.length >= MIN_TAIL_FOR_CRYPTO
                && tail.slice(-CRYPTO_TAIL_LEN, -CRYPTO_TAIL_LEN + 2) === AI_CRYPTO) {
            return tail.slice(0, -CRYPTO_TAIL_LEN);
        }
        return tail;
    }

    function classifyGs1(code) {
        // Сюда попадают только строки «01 + 14 цифр + …»; хвост проверяется на
        // ASCII до срезов, поэтому срезы в UTF-16 совпадают с Python.
        var gtin = code.slice(AI_GTIN.length, GTIN_END);
        var rest = code.slice(GTIN_END);
        var serial = null;
        var kind;
        if (!rest) {
            kind = KIND.EAN;
        } else if (rest.indexOf(AI_SERIAL) === 0 && GS1_TAIL_RE.test(rest)) {
            serial = serialFromTail(code.slice(SERIAL_START));
            kind = serial ? KIND.DATAMATRIX : KIND.UNKNOWN;
        } else {
            kind = KIND.UNKNOWN;
        }
        if (!gtinCheckOk(gtin)) return fail(kind, REASON.BAD_CHECK, code);
        if (kind === KIND.UNKNOWN) return fail(kind, REASON.UNSUPPORTED, code);
        if (kind === KIND.EAN) return result(true, KIND.EAN, gtin, null, gtin, code, '');
        return result(true, KIND.DATAMATRIX, gtin, serial, gtin + '|' + serial, code, '');
    }

    function classify(code) {
        if (DIGITS_RE.test(code)) {
            var n = code.length;
            if (EAN_LENGTHS.indexOf(n) !== -1) {
                var gtin = zfill14(code);
                if (!gtinCheckOk(gtin)) return fail(KIND.EAN, REASON.BAD_CHECK, code);
                return result(true, KIND.EAN, gtin, null, gtin, code, '');
            }
            if (n === SSCC_LEN && code.indexOf(AI_SSCC) === 0) return fail(KIND.SSCC, REASON.SSCC, code);
        }
        if (code.indexOf(AI_GTIN) === 0 && GTIN14_RE.test(code.slice(AI_GTIN.length, GTIN_END))) {
            return classifyGs1(code);
        }
        return fail(KIND.UNKNOWN, REASON.UNSUPPORTED, code);
    }

    function parseCode(raw) {
        var text = raw == null ? '' : String(raw);
        text = stripEdges(text);
        if (!text) return fail(KIND.EMPTY, REASON.EMPTY, '');
        if (tooLong(text)) return fail(KIND.UNKNOWN, REASON.TOO_LONG, cpHead(text, MAX_CODE_LEN));
        var code = normalize(text);
        if (!code) return fail(KIND.EMPTY, REASON.EMPTY, '');
        return classify(code);
    }

    var api = {
        parseCode: parseCode,
        gtinCheckOk: gtinCheckOk,
        barcodeForIiko: barcodeForIiko,
        MAX_CODE_LEN: MAX_CODE_LEN,
        KEY_LEN: KEY_LEN,
        GS: GS,
        KIND: KIND,
        REASON: REASON,
        MESSAGES: MESSAGES,
        MSG_OK: MSG_OK
    };

    root.RcCodes = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : this);

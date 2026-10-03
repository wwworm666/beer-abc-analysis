"""Разбор кода со сканера на приёмке РЦ: DataMatrix Честного ЗНАКа, EAN/UPC, SSCC.

Что это. Чистые функции без Flask, диска и сети: на вход — строка, которую
прислал ручной сканер, камера или ввели руками; на выход — словарь с видом кода,
GTIN, серийным номером и ключом дедупликации. Тот же разбор работает в браузере
приёмщика (static/js/receiving/codes.js, объект RcCodes) — мгновенный сигнал
«принято / не то» ещё до ответа сервера. Паритет двух реализаций держит общая
фикстура tests/fixtures/receiving_codes.json: её прогоняют и pytest, и Node.

Почему нужна нормализация. Ручной сканер — «клавиатура»: он печатает код
нажатиями клавиш, поэтому строка приходит искажённой:
- включена русская раскладка — латиница серийника приходит кириллицей
  («GLTP» → «ПДЕЗ»), знаки на других клавишах («/» → «.»);
- разделитель групп GS (FNC1, \\x1d) теряется, приходит символом «␝» (U+241D)
  или стоит первым символом;
- сканер с включённым AIM-идентификатором дописывает в начало «]d2» (DataMatrix),
  «]E0» (EAN-13), «]Q3» (QR), «]C1» (GS1-128);
- с этикетки код могут ввести в человекочитаемом виде «(01)…(21)…».

Как (по порядку; JS-порт повторяет шаг в шаг):
1. None → ''; str(); убрать пробелы, \\t, \\r, \\n по краям. Пусто → empty.
2. Длиннее MAX_CODE_LEN символов (кодовых точек) → too_long.
3. Есть кириллица → вся строка переводится из раскладки ЙЦУКЕН в US QWERTY
   посимвольно (та же физическая клавиша). Цифры не трогаются.
4. «␝» → GS; ведущие GS (FNC1) убираются.
5. Префикс идентификатора символики ]<буква><цифра> убирается (и GS после него).
6. Человекочитаемый вид: «(01)<14 цифр>(21)<серийник>…» → 01 + GTIN + 21 +
   серийник + GS (серийник — до следующей «(» или конца; GS в конце закрывает
   серийник, как в настоящем коде, и делает разбор идемпотентным);
   «(01)<14 цифр>» → 01 + GTIN; «(00)<18 цифр>» → 00 + 18 цифр (SSCC).
   После нормализации пусто (например, прислали один «␝») → empty.

Классификация:
- только цифры длиной 8, 12, 13, 14 (EAN-8, UPC-A, EAN-13, GTIN-14) → GTIN =
  zfill(14); контрольная цифра верна → ean, иначе bad_check_digit;
- только цифры, 20 знаков, начинается с 00 → sscc (код короба/паллеты, не ok);
- 01 + 14 цифр: неверная контрольная цифра GTIN → bad_check_digit; дальше
  «21» + непустой серийник → datamatrix; ровно 16 знаков (GTIN без серийника) →
  ean; иначе unsupported. Серийник: до первого GS; GS нет и хвост после 21
  не короче MIN_TAIL_FOR_CRYPTO, а code[-6:-4] == '93' → без последних 6
  символов (криптохвост 93 + 4 символа, сканер потерял GS); иначе весь хвост.
  Хвост DataMatrix — только печатный ASCII и GS (набор символов GS1); другое
  (символы вне ASCII, пробел внутри) → unsupported;
- всё прочее (QR, ЕГАИС, URL) → unsupported.

Результат: {'ok', 'kind', 'gtin', 'serial', 'key', 'code', 'reason', 'message'}.
- gtin (14 цифр) и serial заполнены только у принятых кодов (ok), иначе None:
  GTIN с неверной контрольной цифрой ненадёжен и в подсчёт не идёт;
- key — ключ дедупликации: DataMatrix → 'gtin|serial' (одна бутылка — один
  ключ), EAN → gtin (каждый скан — ещё одна штука), прочее → code[:KEY_LEN];
- kind у отказа: empty → 'empty'; too_long и unsupported → 'unknown';
  sscc → 'sscc'; bad_check_digit — вид, который был бы у кода с верной цифрой
  ('ean', 'datamatrix' или 'unknown');
- code — нормализованная строка; у too_long — первые MAX_CODE_LEN символов;
- message — короткий текст для экрана приёмщика.

Длины считаются в кодовых точках Unicode (len() в Python); JS-порт считает так
же (Array.from), а не в UTF-16, иначе символ вне BMP дал бы расхождение.
"""
import re
from typing import Optional

# --- пределы ---------------------------------------------------------------
MAX_CODE_LEN = 512   # длиннее — мусор: ЕГАИС PDF417 ~150 символов, DataMatrix пива ~31-45
KEY_LEN = 200        # ключ нераспознанного кода — только для диагностики; 200 символов
                     # различают коды и не раздувают БД

# --- виды кода (kind) --------------------------------------------------------
KIND_DATAMATRIX = 'datamatrix'   # 01 + GTIN + 21 + серийник: экземпляр бутылки
KIND_EAN = 'ean'                 # GTIN без серийника: EAN-8/13, UPC-A, GTIN-14
KIND_SSCC = 'sscc'               # код транспортной упаковки (короб, паллета)
KIND_UNKNOWN = 'unknown'         # не распознан
KIND_EMPTY = 'empty'             # пустая строка

# --- причины отказа (reason; '' у принятых) ---------------------------------
REASON_EMPTY = 'empty'
REASON_TOO_LONG = 'too_long'
REASON_SSCC = 'sscc'
REASON_BAD_CHECK = 'bad_check_digit'
REASON_UNSUPPORTED = 'unsupported'

# --- тексты для приёмщика -----------------------------------------------------
MSG_OK = 'Принято'
MSG_UNREADABLE = 'Код не распознан — повторите'
MSG_BAD_CHECK = 'Код прочитан с ошибкой — повторите'
MSG_SSCC = 'Код короба или паллеты — отсканируйте бутылку'
MESSAGES = {
    REASON_EMPTY: MSG_UNREADABLE,
    REASON_TOO_LONG: MSG_UNREADABLE,
    REASON_UNSUPPORTED: MSG_UNREADABLE,
    REASON_BAD_CHECK: MSG_BAD_CHECK,
    REASON_SSCC: MSG_SSCC,
}

# --- структура GS1 ------------------------------------------------------------
GS = '\x1d'                 # разделитель групп (FNC1) — ASCII 29
GS_PICTURE = '\u241d'       # «␝» — так GS приходит от части сканеров и при копировании
AI_SSCC = '00'              # идентификатор применения: SSCC (18 цифр)
AI_GTIN = '01'              # GTIN (ровно 14 цифр, фиксированная длина)
AI_SERIAL = '21'            # серийный номер экземпляра (переменная длина, до GS)
AI_CRYPTO = '93'            # код проверки Честного ЗНАКа (у пива — 4 символа)
GTIN_LEN = 14
EAN_LENGTHS = (8, 12, 13, 14)        # EAN-8, UPC-A, EAN-13, GTIN-14 — дополняются нулями до 14
SSCC_LEN = 20                        # '00' + 18 цифр SSCC
GTIN_END = len(AI_GTIN) + GTIN_LEN   # 16: где кончается «01 + GTIN»
SERIAL_START = GTIN_END + len(AI_SERIAL)   # 18: где начинается серийник
CRYPTO_TAIL_LEN = 6                  # '93' + 4 символа кода проверки
MIN_TAIL_FOR_CRYPTO = CRYPTO_TAIL_LEN + 1  # 7: отрезать криптохвост, только если от
                                           # серийника останется хотя бы 1 символ
EAN8_PREFIX = '000000'               # 14 - 8 = 6 ведущих нулей: GTIN — это EAN-8
EAN8_LEN = 8
EAN13_LEN = 13

_EDGE_WS = ' \t\r\n'   # что срезаем по краям (сканер дописывает Enter/Tab)

# --- раскладка ЙЦУКЕН → US QWERTY: символ той же физической клавиши ----------
# Буквы и знаки на буквенных клавишах (х ъ ж э б ю ё), а также знаки, которые
# в русской раскладке стоят на других местах: Shift+2 «"» (в US «@»), Shift+3
# «№» («#»), Shift+4 «;» («$»), Shift+6 «:» («^»), Shift+7 «?» («&»), клавиша
# «/» даёт «.», Shift+«/» — «,» («?»), Shift+«\» — «/» («|»). Без знаков серийник
# с «/», «?» или «&» в русской раскладке давал бы другой ключ, чем в латинской.
_LAYOUT_PAIRS = (
    ('ё', '`'), ('Ё', '~'),
    ('йцукенгшщзхъ', 'qwertyuiop[]'),
    ('ЙЦУКЕНГШЩЗХЪ', 'QWERTYUIOP{}'),
    ('фывапролджэ', "asdfghjkl;'"),
    ('ФЫВАПРОЛДЖЭ', 'ASDFGHJKL:"'),
    ('ячсмитьбю.', 'zxcvbnm,./'),
    ('ЯЧСМИТЬБЮ,', 'ZXCVBNM<>?'),
    ('"№;:?', '@#$^&'),
    ('/', '|'),
)
_RU_TO_EN = {}
for _ru, _en in _LAYOUT_PAIRS:
    assert len(_ru) == len(_en), (_ru, _en)
    for _r, _e in zip(_ru, _en):
        _RU_TO_EN[ord(_r)] = _e
del _ru, _en, _r, _e

# Регулярки только с явными ASCII-классами: \d в Python ловит и арабские,
# и деванагари-цифры, а JS-порт — нет.
_DIGITS_RE = re.compile(r'[0-9]+')
_GTIN14_RE = re.compile(r'[0-9]{14}')
_CYRILLIC_RE = re.compile('[\u0400-\u04ff]')
_SYMBOLOGY_RE = re.compile(r'\][A-Za-z][0-9]')
_HRI_SSCC_RE = re.compile(r'\(00\)([0-9]{18})')
_HRI_GTIN_RE = re.compile(r'\(01\)([0-9]{14})(.*)', re.S)
_HRI_SERIAL_PREFIX = '(21)'
_GS1_TAIL_RE = re.compile('[\x1d\x21-\x7e]+')   # GS + печатный ASCII без пробела


def gtin_check_ok(gtin14) -> bool:
    """Контрольная цифра GS1 (mod 10) для GTIN из ровно 14 цифр.

    Веса слева направо 3, 1, 3, … по первым 13 цифрам; контрольная =
    (10 - сумма % 10) % 10. Пример: 04610093628430 → сумма 0*3 + 4 + 6*3 + 1 +
    0*3 + 0 + 9*3 + 3 + 6*3 + 2 + 8*3 + 4 + 3*3 = 110, контрольная
    (10 - 110 % 10) % 10 = 0 — совпадает с последней цифрой.
    Не строка или не 14 цифр → False.
    """
    if not isinstance(gtin14, str) or not _GTIN14_RE.fullmatch(gtin14):
        return False
    total = 0
    for i, ch in enumerate(gtin14[:GTIN_LEN - 1]):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10 == int(gtin14[GTIN_LEN - 1])


def barcode_for_iiko(gtin14) -> str:
    """Штрихкод для карточки iiko из GTIN: тот вид, что печатают на этикетке.

    GTIN начинается с 000000 → последние 8 цифр (EAN-8); с 0 → последние 13
    (EAN-13, в том числе UPC-A с ведущим нулём); иначе все 14 (GTIN-14).
    Короче 14 цифр — сначала дополняется нулями слева. Не цифры или длиннее
    14 — возвращается как есть (после обрезки пробелов): показать, но не портить.
    """
    s = '' if gtin14 is None else str(gtin14).strip(_EDGE_WS)
    if not _DIGITS_RE.fullmatch(s) or len(s) > GTIN_LEN:
        return s
    s = s.zfill(GTIN_LEN)
    if s.startswith(EAN8_PREFIX):
        return s[-EAN8_LEN:]
    if s.startswith('0'):
        return s[-EAN13_LEN:]
    return s


def _result(ok: bool, kind: str, gtin: Optional[str], serial: Optional[str],
            key: str, code: str, reason: str) -> dict:
    return {
        'ok': ok,
        'kind': kind,
        'gtin': gtin,
        'serial': serial,
        'key': key,
        'code': code,
        'reason': reason,
        'message': MSG_OK if ok else MESSAGES[reason],
    }


def _fail(kind: str, reason: str, code: str) -> dict:
    return _result(False, kind, None, None, code[:KEY_LEN], code, reason)


def _normalize(text: str) -> str:
    """Шаги 3-6 нормализации (см. модульный докстринг)."""
    if _CYRILLIC_RE.search(text):
        text = text.translate(_RU_TO_EN)
    text = text.replace(GS_PICTURE, GS).lstrip(GS)
    m = _SYMBOLOGY_RE.match(text)
    if m:
        text = text[m.end():].lstrip(GS)
    return _from_human_readable(text)


def _from_human_readable(code: str) -> str:
    """«(01)GTIN(21)SERIAL…» → «01GTIN21SERIAL<GS>»; «(00)…» → «00…»; иначе как есть."""
    m = _HRI_SSCC_RE.fullmatch(code)
    if m:
        return AI_SSCC + m.group(1)
    m = _HRI_GTIN_RE.fullmatch(code)
    if not m:
        return code
    gtin, rest = m.group(1), m.group(2)
    if not rest:
        return AI_GTIN + gtin
    if rest.startswith(_HRI_SERIAL_PREFIX):
        serial = rest[len(_HRI_SERIAL_PREFIX):].split('(', 1)[0]
        if serial:
            return AI_GTIN + gtin + AI_SERIAL + serial + GS
    return code


def _serial_from_tail(tail: str) -> str:
    """Серийник из хвоста после «21»: до GS; без GS — без криптохвоста «93»+4."""
    if GS in tail:
        return tail.split(GS, 1)[0]
    if len(tail) >= MIN_TAIL_FOR_CRYPTO and tail[-CRYPTO_TAIL_LEN:-CRYPTO_TAIL_LEN + 2] == AI_CRYPTO:
        return tail[:-CRYPTO_TAIL_LEN]
    return tail


def _classify_gs1(code: str) -> dict:
    """Код «01 + 14 цифр + …»: DataMatrix, GTIN без серийника или неподдержанный."""
    gtin = code[len(AI_GTIN):GTIN_END]
    rest = code[GTIN_END:]
    serial = None
    if not rest:
        kind = KIND_EAN
    elif rest.startswith(AI_SERIAL) and _GS1_TAIL_RE.fullmatch(rest):
        serial = _serial_from_tail(code[SERIAL_START:])
        kind = KIND_DATAMATRIX if serial else KIND_UNKNOWN
    else:
        kind = KIND_UNKNOWN
    if not gtin_check_ok(gtin):
        return _fail(kind, REASON_BAD_CHECK, code)
    if kind == KIND_UNKNOWN:
        return _fail(kind, REASON_UNSUPPORTED, code)
    if kind == KIND_EAN:
        return _result(True, KIND_EAN, gtin, None, gtin, code, '')
    return _result(True, KIND_DATAMATRIX, gtin, serial, gtin + '|' + serial, code, '')


def _classify(code: str) -> dict:
    if _DIGITS_RE.fullmatch(code):
        n = len(code)
        if n in EAN_LENGTHS:
            gtin = code.zfill(GTIN_LEN)
            if not gtin_check_ok(gtin):
                return _fail(KIND_EAN, REASON_BAD_CHECK, code)
            return _result(True, KIND_EAN, gtin, None, gtin, code, '')
        if n == SSCC_LEN and code.startswith(AI_SSCC):
            return _fail(KIND_SSCC, REASON_SSCC, code)
    if code.startswith(AI_GTIN) and _GTIN14_RE.fullmatch(code[len(AI_GTIN):GTIN_END]):
        return _classify_gs1(code)
    return _fail(KIND_UNKNOWN, REASON_UNSUPPORTED, code)


def parse_code(raw) -> dict:
    """Разобрать код со сканера (правила — в модульном докстринге).

    Возвращает dict ровно с ключами ok, kind, gtin, serial, key, code, reason,
    message. Примеры:
        parse_code('4610093628430')
          → ok, kind 'ean', gtin '04610093628430', key '04610093628430'
        parse_code(']d2010461009362843021GLTP9kqZn5QRt\\x1d93dGVz')
          → ok, kind 'datamatrix', serial 'GLTP9kqZn5QRt',
            key '04610093628430|GLTP9kqZn5QRt'
        parse_code('00146012340000000018')
          → не ok, kind 'sscc', message 'Код короба или паллеты — …'
    """
    text = '' if raw is None else str(raw)
    text = text.strip(_EDGE_WS)
    if not text:
        return _fail(KIND_EMPTY, REASON_EMPTY, '')
    if len(text) > MAX_CODE_LEN:
        return _fail(KIND_UNKNOWN, REASON_TOO_LONG, text[:MAX_CODE_LEN])
    code = _normalize(text)
    if not code:
        return _fail(KIND_EMPTY, REASON_EMPTY, '')
    return _classify(code)

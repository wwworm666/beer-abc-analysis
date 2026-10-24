"""Сорт в посте: сверка строки про сорт с кранами бара перед выходом и замена снятого сорта.

## Что это

Пост рубрики «История» кончается строкой про сорт на кране этого бара:
«Сегодня на шестом кране «Культуры» — Black Sheep Irish Stout, ирландский стаут, 4%.»
Пост пишут за недели до выхода, а кеги меняются каждую неделю. В октябре 2026 вышел пост
про пиво, которого в тот момент на кране уже не было. Решение владельца 2026-10-23:
«Если пива нет на кране, мы не просто ставим пост на паузу, а быстро переписываем под
нужный и отправляем. Пост точно должен выйти по пиву, но если согласованный сорт сняли,
то мы меняем на другой».

Поэтому перед выходом готовой публикации в Telegram-канал бара отправщик сверяет строку про
сорт с кранами этого бара и сам переписывает её, если сорта нет. Экран показывает то же
заранее, по кранам на сейчас (поле beer_info размещения).

## Файлы

| Файл | Роль |
|---|---|
| core/content_beer.py | этот модуль: какие сорта в строке, на кране ли они, чем заменить |
| core/content_plan.py | состояние у размещения (beer_info), «Поставить сорт» вручную (set_beer) |
| core/content_publisher.py | сверка перед отправкой (build_post), запись замены в журнал |
| core/taplist_post.py | имя сорта, стиль по-русски, крепость — как в «Таплисте пятницы» |

## Как работает

1. **Строка про сорт** — последний абзац поста (бриф: финал «Истории» — сорт на кране этого
   бара). Абзацы разделяет пустая строка.
2. **Какие сорта в ней** — по именам известных сортов: краны всех баров сейчас и карточки
   реестра Untappd (core/untappd_registry). Имена сорта: как в таплисте («Riegele Feines
   Urhell»), название Untappd («Feines Urhell» — только если в нём два слова и больше или
   не меньше 7 знаков: одно короткое слово вроде «Helles» встречается и просто как стиль) и
   имя кеги iiko без «КЕГ» и объёма. Сравнение без учёта регистра, «ё» = «е», знаки
   препинания — как пробел, только целыми словами. Имена короче 4 знаков не ищутся.
3. **Состояние** (`state`):

| state | Когда | Что уходит |
|---|---|---|
| `none` | в последнем абзаце нет известного сорта | пост как есть |
| `on_tap` | все сорта из строки стоят на кранах бара | пост как есть |
| `moved` | сорт на кране, но номер крана в строке другой | номер в строке исправлен |
| `swap` | сорт сняли с крана | строка собрана заново под сорт с кранов бара |
| `no_beer` | сорт сняли, а заменить нечем | публикация остановлена: ошибка с причиной |
| `no_data` | краны не прочитались | пост как есть, в журнале — «сорт не проверен» |

4. **Чем заменить** — первый подходящий уровень (`LEVELS`), среди активных кранов бара:
   - `kept` — в строке было два сорта и один остался: строка — про оставшийся;
   - `same_style` — тот же стиль Untappd («Stout - Irish Dry»);
   - `same_family` — то же семейство стилей Untappd (часть до « - »: «Stout»);
   - `same_group` — та же группа (`STYLE_GROUPS`: тёмное, лагер, пшеничное, кислое,
     хмелевое, бельгийское светлое, особое);
   - `any` — любое пиво с карточкой Untappd. Сидр, медовуха и квас — только вместо
     того же напитка (`DRINK_KINDS`): к посту про стаут сидр не подставляется.
   Среди подходящих: с проверенной карточкой Untappd, затем подключённый позже всех
   (дольше простоит), затем меньший номер крана. Нет ни одного — `no_beer`.
5. **Новая строка** (`beer_line`):
   «Сегодня на {номер крана словом} кране «{бар}» — {пивоварня и название}, {стиль}, {крепость}%.»
   Имя, стиль по-русски и крепость — как в «Таплисте пятницы» (core/taplist_post); пустые
   части опускаются. Номер крана словом — 1..24 (`TAP_ORDINALS`, на ВО 24 крана), дальше —
   «на кране № N». Бар — `BAR_POST_NAMES`.
6. **Номер крана в строке** (`moved`) ищется в трёх видах: «на шестом кране», «на 6-м
   кране», «кране № 6». Если сорт переехал, меняется только номер, остальной текст
   строки остаётся. Номер не найден — строка остаётся как есть.

Пример: пост на Лиговский кончается «Сегодня на восьмом кране «Культуры Каск» — Riegele
Feines Urhell, хеллес из Аугсбурга, 4,7%…». Ко дню выхода Riegele сняли, на пятом кране —
Festhaus Helles (тот же стиль «Lager - Helles»). Уйдёт: «Сегодня на пятом кране «Культуры
Каск» — Festhaus Helles, светлый лагер, 4,5%.»

## Changelog

- 2026-10-23 — модуль создан: сверка строки про сорт с кранами перед выходом и замена
  снятого сорта (решение владельца).
"""
import re
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from core import taplist_post
from core.taplist import full_taplist

# Как бар назван в строке «Сегодня на N кране «…»». Лиговский — «Культура Каск» (бриф,
# раздел бара: «Бар называется «Культура Каск»»), остальные — «Культура», как в
# утверждённых владельцем постах октября 2026.
BAR_POST_NAMES = {'bolshoy': 'Культуры', 'ligovskiy': 'Культуры Каск',
                  'kremenchugskaya': 'Культуры', 'varshavskaya': 'Культуры'}

# Номер крана словом в предложном падеже: «на шестом кране». 24 — кранов на ВО (больше
# всех в сети); дальше — «на кране № N».
TAP_ORDINALS = ('первом', 'втором', 'третьем', 'четвёртом', 'пятом', 'шестом', 'седьмом', 'восьмом',
                'девятом', 'десятом', 'одиннадцатом', 'двенадцатом', 'тринадцатом', 'четырнадцатом',
                'пятнадцатом', 'шестнадцатом', 'семнадцатом', 'восемнадцатом', 'девятнадцатом', 'двадцатом',
                'двадцать первом', 'двадцать втором', 'двадцать третьем', 'двадцать четвёртом')

# Группы стилей для уровня same_group: семейство Untappd (часть стиля до « - ») -> группа.
# Семейства — все, что есть в словаре стилей (resources/taplist_post_names.json, 39 на
# 2026-10-23); новое семейство без группы просто пропускает этот уровень (тест словаря
# напоминает дописать). Сидр, медовуха и квас — не пиво: они в DRINK_KINDS.
STYLE_GROUPS = {
    'dark': ('тёмное', ('Stout', 'Porter', 'Brown Ale', 'Mild', 'Belgian Dubbel', 'Belgian Quadrupel',
                        'Belgian Strong Dark Ale', 'Old / Stock Ale', 'Barleywine', 'Winter Ale',
                        'Historical Beer')),
    'lager': ('лагер', ('Lager', 'Pilsner', 'Märzen', 'Festbier', 'Kellerbier / Zwickelbier', 'Bock',
                        'California Common', 'Kölsch')),
    'wheat': ('пшеничное', ('Wheat Beer',)),
    'sour': ('кислое', ('Sour', 'Lambic')),
    'hoppy': ('хмелевое', ('IPA', 'Pale Ale', 'Bitter', 'Blonde / Golden Ale', 'Red Ale')),
    'belgian': ('бельгийское светлое', ('Belgian Blonde', 'Belgian Strong Golden Ale', 'Belgian Tripel',
                                        'Farmhouse Ale')),
    'special': ('особое', ('Fruit Beer', 'Honey Beer', 'Pumpkin / Yam Beer')),
}
# Стили, чья группа не совпадает с группой семейства: тёмные лагеры — к тёмному,
# пшеничные боки — к пшеничному.
STYLE_GROUP_EXCEPTIONS = {
    'Lager - Munich Dunkel': 'dark',
    'Lager - Tmavé (Czech Dark)': 'dark',
    'Kellerbier / Zwickelbier - Dunkel': 'dark',
    'Bock - Weizenbock': 'wheat',
    'Bock - Weizendoppelbock': 'wheat',
}
# Не пиво: заменяется только тем же напитком (семейство Untappd -> вид напитка).
DRINK_KINDS = {'Cider': 'cider', 'Mead': 'mead', 'Kvass': 'kvass'}
BEER_KIND = 'beer'
# Мусор реестра вместо стиля («Brewed by …»): семейства нет.
_JUNK_STYLE_PREFIX = 'Brewed by'

LEVELS = {
    'kept': 'оставшийся сорт из строки',
    'same_style': 'тот же стиль',
    'same_family': 'похожий стиль',
    'same_group': 'та же группа: {group}',
    'any': 'другой стиль',
}
STATES = ('none', 'on_tap', 'moved', 'swap', 'no_beer', 'no_data')
# Состояния, при которых в посте что-то меняется или он не уйдёт — их экран выделяет.
ALERT_STATES = ('moved', 'swap', 'no_beer')

NAME_MIN = 4            # имя короче 4 знаков не ищется: «IPA», «Bock» — слова, а не сорта
ALIAS_MIN = 7           # название Untappd без пивоварни — от 7 знаков или от двух слов

_PARAGRAPH_RE = re.compile(r'\n[ \t]*\n')
_NON_WORD_RE = re.compile(r'[\W_]+', re.UNICODE)


def norm(text) -> str:
    """Для сравнения имён: без регистра, «ё» = «е», знаки препинания — пробел."""
    value = str(text or '').casefold().replace('ё', 'е')
    return ' '.join(_NON_WORD_RE.sub(' ', value).split())


def last_paragraph(text: str) -> Optional[Tuple[int, int]]:
    """(начало, конец) последнего непустого абзаца в text или None (текста нет)."""
    text = text or ''
    end = len(text.rstrip())
    if end == 0:
        return None
    start = 0
    for match in _PARAGRAPH_RE.finditer(text, 0, end):
        start = match.end()
    while start < end and text[start] in ' \t\n':
        start += 1
    return start, end


def body_of(text: str) -> str:
    """Текст без последнего абзаца, если абзацев больше одного (строка про сорт у
    каждого бара своя), иначе весь текст; нормализован для сравнения (`norm`)."""
    span = last_paragraph(text)
    if span is None:
        return ''
    head = (text or '')[:span[0]]
    return norm(head) if head.strip() else norm(text)


# ---------------------------------------------------------------------------
# Номер крана словом и в строке
# ---------------------------------------------------------------------------

def tap_phrase(number) -> str:
    """«на шестом кране» (1..24) или «на кране № 30» / «на кране № A»."""
    try:
        value = int(number)
    except (TypeError, ValueError):
        return f'на кране № {number}'
    if 1 <= value <= len(TAP_ORDINALS):
        return f'на {TAP_ORDINALS[value - 1]} кране'
    return f'на кране № {value}'


_ORDINAL_INDEX = {}
for _i, _word in enumerate(TAP_ORDINALS):
    _ORDINAL_INDEX[_word] = _i + 1
    _ORDINAL_INDEX[_word.replace('ё', 'е')] = _i + 1
_ORDINAL_ALT = '|'.join(sorted((re.escape(w) for w in _ORDINAL_INDEX), key=len, reverse=True))
_TAP_WORD_RE = re.compile(r'на\s+(' + _ORDINAL_ALT + r')\s+кране', re.IGNORECASE)
_TAP_DIGIT_RE = re.compile(r'на\s+(\d{1,2})\s*-?\s*м\s+кране', re.IGNORECASE)
_TAP_SIGN_RE = re.compile(r'кран[еау]?\s*№\s*(\d{1,2})', re.IGNORECASE)


def find_tap(line: str) -> Optional[dict]:
    """Номер крана в строке: {number, start, end, form: word|digit|sign} или None."""
    for regex, form in ((_TAP_WORD_RE, 'word'), (_TAP_DIGIT_RE, 'digit'), (_TAP_SIGN_RE, 'sign')):
        match = regex.search(line or '')
        if not match:
            continue
        raw = match.group(1)
        number = _ORDINAL_INDEX.get(' '.join(raw.lower().split())) if form == 'word' else int(raw)
        if number:
            return {'number': number, 'start': match.start(), 'end': match.end(), 'form': form}
    return None


def replace_tap(line: str, found: dict, number) -> str:
    """Строка с другим номером крана в том же виде, что был."""
    if found['form'] == 'word':
        new = tap_phrase(number)
    elif found['form'] == 'digit':
        new = f'на {number}-м кране'
    else:
        new = f'кране № {number}'
    return line[:found['start']] + new + line[found['end']:]


# ---------------------------------------------------------------------------
# Стили: семейство, группа, вид напитка
# ---------------------------------------------------------------------------

def style_family(style) -> str:
    """Семейство стиля Untappd: часть до « - » («Stout - Irish Dry» -> «Stout»); '' — нет стиля."""
    value = ' '.join(str(style or '').split())
    if not value or value.startswith(_JUNK_STYLE_PREFIX):
        return ''
    return value.split(' - ', 1)[0].strip()


_GROUP_OF_FAMILY = {family: key for key, (_name, families) in STYLE_GROUPS.items() for family in families}


def style_group(style) -> Optional[str]:
    """Группа стиля (ключ STYLE_GROUPS) или None."""
    value = ' '.join(str(style or '').split())
    if value in STYLE_GROUP_EXCEPTIONS:
        return STYLE_GROUP_EXCEPTIONS[value]
    return _GROUP_OF_FAMILY.get(style_family(value))


def drink_kind(style) -> str:
    """Вид напитка: cider, mead, kvass или beer (и неизвестный стиль)."""
    return DRINK_KINDS.get(style_family(style), BEER_KIND)


# ---------------------------------------------------------------------------
# Краны и известные сорта
# ---------------------------------------------------------------------------

class TapsContext:
    """Краны и реестр на один момент: строки бара, ключ сорта, известные имена.

    snapshot / registry — как у «Таплиста пятницы» (core/content_plan.load_live_data);
    bar_ids — ключ бара -> id в таплисте (bar1..bar4); date_text — дата для текста о
    свежести кранов; error — краны не прочитались (тогда состояние no_data)."""

    def __init__(self, snapshot=None, registry=None, bar_ids=None, names=None,
                 now: Optional[datetime] = None, date_text: Optional[Callable] = None,
                 error: Optional[str] = None):
        self.snapshot = snapshot or {}
        self.registry = registry or {}
        self.bar_ids = dict(bar_ids or {})
        self.now = now
        self.date_text = date_text or (lambda moment: moment.strftime('%d.%m'))
        self.error = error
        self._names = names
        self._key = taplist_post.beer_key_fn(self.registry) if not error else None
        self._rows: Dict[str, List[dict]] = {}
        self._entries: Optional[List[dict]] = None

    @property
    def names(self) -> dict:
        if self._names is None:
            self._names = taplist_post.load_names()
        return self._names

    def key(self, row: dict) -> str:
        return self._key(row.get('iiko_product_id'), row.get('iiko_name')) if self._key else ''

    def rows(self, bar: str) -> List[dict]:
        """Активные краны бара по номеру (core.taplist.full_taplist); нет бара — []."""
        if bar not in self._rows:
            bar_id = self.bar_ids.get(bar)
            rows: List[dict] = []
            if bar_id and bar_id in self.snapshot:
                rows = sorted(full_taplist(self.snapshot, self.registry, bar_id, active_only=True),
                              key=taplist_post.tap_order)
            self._rows[bar] = rows
        return self._rows[bar]

    def stale(self, bar: str) -> Optional[str]:
        """Текст «краны бара не обновлялись N дней» (как стоп таплиста) или None."""
        bar_id = self.bar_ids.get(bar)
        if self.error or not bar_id or bar_id not in self.snapshot or self.now is None:
            return None
        return taplist_post.stale_problem(self.snapshot[bar_id], self.now, self.date_text)

    def entries(self) -> List[dict]:
        """Известные сорта: [{key, names (нормализованные), row}] — краны всех баров и
        карточки реестра. row — данные для строки (имя, стиль, крепость)."""
        if self._entries is None:
            self._entries = self._build_entries()
        return self._entries

    def _build_entries(self) -> List[dict]:
        names = self.names
        by_key: Dict[str, dict] = {}

        def add(key, row, labels):
            if not key:
                return
            entry = by_key.setdefault(key, {'key': key, 'names': [], 'row': row})
            for label in labels:
                value = norm(label)
                if len(value) >= NAME_MIN and not value.isdigit() and value not in entry['names']:
                    entry['names'].append(value)

        def alias(name) -> List[str]:
            value = norm(name)
            return [name] if len(value.split()) >= 2 or len(value) >= ALIAS_MIN else []

        for bar in self.bar_ids:
            for row in self.rows(bar):
                labels = [taplist_post.post_name(row, names)] + alias(row.get('beer_name'))
                if not row.get('mapped'):
                    labels.append(taplist_post.iiko_display(row.get('iiko_name')))
                add(self.key(row), row, labels)
        for bid, card in (self.registry.get('beers') or {}).items():
            if not isinstance(card, dict) or not card.get('beer_name'):
                continue
            row = {'untappd_beer_id': str(bid), 'beer_name': card.get('beer_name'), 'brewery': card.get('brewery'),
                   'style': card.get('style'), 'abv': card.get('abv_percent'), 'untappd_url': card.get('url'),
                   'mapped': True}
            add(f'untappd:{bid}', row, [taplist_post.post_name(row, names)] + alias(card.get('beer_name')))
        for product in (self.registry.get('products') or {}).values():
            bid = product.get('untappd_beer_id') if isinstance(product, dict) else None
            if bid and f'untappd:{bid}' in by_key and product.get('status') == 'verified':
                add(f'untappd:{bid}', None, [taplist_post.iiko_display(product.get('iiko_name'))])
        return list(by_key.values())

    def mentions(self, line: str, bar: Optional[str] = None) -> List[dict]:
        """Сорта, упомянутые в строке, по порядку: [entry]. Совпадения не перекрываются:
        из пересекающихся остаётся самое длинное (при равной длине — сорт с кранов бара)."""
        hay = ' ' + norm(line) + ' '
        here = {self.key(row) for row in self.rows(bar)} if bar else set()
        found = []
        for entry in self.entries():
            best = None
            for name in entry['names']:
                pos = hay.find(' ' + name + ' ')
                if pos >= 0 and (best is None or len(name) > best[1] - best[0]):
                    best = (pos + 1, pos + 1 + len(name))
            if best:
                found.append((best[0], best[1], entry))
        found.sort(key=lambda f: (f[0] - f[1], 0 if f[2]['key'] in here else 1, f[0]))
        kept: List[tuple] = []
        for item in found:
            if any(item[0] < other[1] and other[0] < item[1] for other in kept):
                continue
            kept.append(item)
        kept.sort(key=lambda f: f[0])
        return [item[2] for item in kept]


# ---------------------------------------------------------------------------
# Строка про сорт и выбор замены
# ---------------------------------------------------------------------------

def beer_name(row: dict, names: dict) -> str:
    """Пивоварня и название — как в таплисте."""
    return taplist_post.post_name(row, names)


def beer_line(row: dict, bar: str, names: dict) -> str:
    """«Сегодня на шестом кране «Культуры» — {имя}, {стиль}, {крепость}%.» (пустые части
    опускаются)."""
    parts = [beer_name(row, names)]
    style = taplist_post.style_ru(row.get('style'), names)
    if style:
        parts.append(style)
    abv = taplist_post.format_abv(row.get('abv')) if row.get('abv') else None
    if abv and abv != '0':
        parts.append(f'{abv}%')
    where = BAR_POST_NAMES.get(bar, 'Культуры')
    return f'Сегодня {tap_phrase(row.get("tap_number"))} «{where}» — {", ".join(parts)}.'


def _started(row: dict) -> float:
    moment = taplist_post.parse_moment(row.get('started_at')) if row.get('started_at') else None
    return moment.timestamp() if moment else float('-inf')


def _rank(row: dict):
    """Порядок среди подходящих: с карточкой Untappd, подключён позже, меньший номер."""
    return (0 if row.get('mapped') else 1, -_started(row), taplist_post.tap_order(row))


def pick_replacement(style, rows: List[dict], skip_keys, key: Callable[[dict], str]) -> Tuple[Optional[dict], Optional[str]]:
    """Замена снятому сорту стиля style среди rows -> (строка крана, уровень) или (None, None)."""
    candidates = [row for row in rows if key(row) not in skip_keys]
    kind = drink_kind(style)
    family = style_family(style)
    group = style_group(style)
    tests = []
    if family:
        tests.append(('same_style', lambda row: ' '.join(str(row.get('style') or '').split())
                      == ' '.join(str(style).split())))
        tests.append(('same_family', lambda row: style_family(row.get('style')) == family))
    if group:
        tests.append(('same_group', lambda row: style_group(row.get('style')) == group))
    tests.append(('any', lambda row: bool(row.get('mapped')) and bool(style_family(row.get('style')))
                  and drink_kind(row.get('style')) == kind))
    for level, test in tests:
        fit = sorted((row for row in candidates if test(row)), key=_rank)
        if fit:
            return fit[0], level
    return None, None


def level_text(level: Optional[str], style=None) -> str:
    if level == 'same_group':
        group = style_group(style)
        return LEVELS['same_group'].format(group=STYLE_GROUPS[group][0] if group else '')
    return LEVELS.get(level or '', '')


def _beer_view(entry: dict, names: dict, on_rows: List[dict]) -> dict:
    row = entry.get('row') or {}
    name = beer_name(on_rows[0], names) if on_rows else (beer_name(row, names) if row else entry['names'][0])
    return {'key': entry['key'], 'name': name, 'style': (on_rows[0] if on_rows else row).get('style'),
            'on_tap': bool(on_rows), 'tap': on_rows[0].get('tap_number') if on_rows else None,
            'taps': [r.get('tap_number') for r in on_rows]}


def _row_view(row: dict, names: dict, level: str, style=None) -> dict:
    return {'name': beer_name(row, names), 'style': row.get('style'),
            'style_ru': taplist_post.style_ru(row.get('style'), names), 'abv': row.get('abv'),
            'tap': row.get('tap_number'), 'untappd_url': row.get('untappd_url'),
            'level': level, 'level_text': level_text(level, style)}


def check_post(text: str, bar: str, ctx: Optional[TapsContext]) -> dict:
    """Сверить строку про сорт (последний абзац text) с кранами бара bar.

    -> {state, line, new_line, text, beers, replacement, note, done, stale}: text — что уйдёт
    (у moved и swap — с новой строкой, иначе как было); beers — сорта из строки
    [{key, name, style, on_tap, tap, taps}]; replacement — чем заменили (swap):
    {name, style, style_ru, abv, tap, untappd_url, level, level_text}; note — пояснение
    для экрана (что будет); done — то же в прошедшем времени для журнала отправки; stale —
    краны бара давно не обновлялись (проверка может ошибаться) или None."""
    text = text or ''
    result = {'state': 'none', 'line': '', 'new_line': None, 'text': text, 'beers': [],
              'replacement': None, 'note': '', 'done': '', 'stale': None}
    span = last_paragraph(text)
    if span is None:
        result['note'] = 'Текста нет — сорт не проверяется'
        return result
    start, end = span
    line = text[start:end]
    result['line'] = line
    if ctx is None or ctx.error:
        result.update(state='no_data', note='Краны бара не прочитались — сорт в посте не проверен')
        return result
    try:
        mentioned = ctx.mentions(line, bar)
        rows = ctx.rows(bar)
    except Exception as e:  # noqa: BLE001 — сбой данных кранов не роняет экран и отправку
        print(f'[CONTENT_BEER] check failed: {e!r}')
        result.update(state='no_data', note='Краны бара не прочитались — сорт в посте не проверен')
        return result
    result['stale'] = ctx.stale(bar)
    if not mentioned:
        result['note'] = 'В последнем абзаце нет сорта с кранов — пост уйдёт как есть'
        return result
    names = ctx.names
    on: Dict[str, List[dict]] = {}
    for row in rows:
        on.setdefault(ctx.key(row), []).append(row)
    beers = [_beer_view(entry, names, on.get(entry['key'], [])) for entry in mentioned]
    result['beers'] = beers
    gone = [b for b in beers if not b['on_tap']]

    def finish(state, new_line, note, replacement=None, done=None):
        result.update(state=state, note=note, replacement=replacement, done=done or note)
        if new_line is not None and new_line != line:
            result['new_line'] = new_line
            result['text'] = text[:start] + new_line + text[end:]
        return result

    if not gone:
        if len(beers) == 1:
            found = find_tap(line)
            taps = [str(t) for t in beers[0]['taps']]
            if found and str(found['number']) not in taps:
                new_tap = beers[0]['tap']
                return finish('moved', replace_tap(line, found, new_tap),
                              f'«{beers[0]["name"]}» теперь на кране {new_tap}, а не {found["number"]}: '
                              'номер в посте поправится при выходе',
                              done=f'«{beers[0]["name"]}» стоял на кране {new_tap}, а не {found["number"]}: '
                                   'номер в посте исправлен')
            return finish('on_tap', None, f'«{beers[0]["name"]}» на кране {beers[0]["tap"]}')
        return finish('on_tap', None, 'Все сорта из строки на кранах: '
                      + ', '.join(f'«{b["name"]}» (кран {b["tap"]})' for b in beers))
    gone_names = ', '.join(f'«{b["name"]}»' for b in gone)
    remaining = [b for b in beers if b['on_tap']]
    if remaining:
        row = on[remaining[0]['key']][0]
        repl = _row_view(row, names, 'kept')
        return finish('swap', beer_line(row, bar, names),
                      f'{gone_names} сняли с крана: в посте останется «{repl["name"]}» (кран {repl["tap"]})', repl,
                      done=f'{gone_names} сняли с крана: пост вышел про «{repl["name"]}» (кран {repl["tap"]})')
    style = gone[0]['style']
    row, level = pick_replacement(style, rows, {b['key'] for b in beers}, ctx.key)
    if row is None:
        return finish('no_beer', None,
                      f'{gone_names} сняли с крана, а пива для замены на кранах бара нет — '
                      'выберите сорт в карточке, иначе пост не уйдёт')
    repl = _row_view(row, names, level, style)
    return finish('swap', beer_line(row, bar, names),
                  f'{gone_names} сняли с крана: в посте будет «{repl["name"]}» '
                  f'(кран {repl["tap"]}, {repl["level_text"]})', repl,
                  done=f'{gone_names} сняли с крана: пост вышел с «{repl["name"]}» '
                       f'(кран {repl["tap"]}, {repl["level_text"]})')


def adapt_to_bar(text: str, bar: str, ctx: Optional[TapsContext]) -> Tuple[str, Optional[dict]]:
    """Строка про сорт под краны другого бара (повтор поста в канале другого бара):
    тот же сорт, если он стоит на кранах bar (на любом кране), иначе замена по уровням
    `pick_replacement`. -> (текст, {name, tap, level, level_text}) или (текст как был, None) —
    в последнем абзаце нет сорта, кранов нет или заменить нечем (сверка будет при выходе)."""
    span = last_paragraph(text or '')
    if span is None or ctx is None or ctx.error:
        return text, None
    start, end = span
    try:
        mentioned = ctx.mentions(text[start:end], bar)
        rows = ctx.rows(bar)
    except Exception as e:  # noqa: BLE001 — без кранов копия остаётся как есть
        print(f'[CONTENT_BEER] adapt failed: {e!r}')
        return text, None
    if not mentioned:
        return text, None
    keys = {entry['key'] for entry in mentioned}
    row, level = next(((r, 'same_beer') for r in rows if ctx.key(r) in keys), (None, None))
    style = (mentioned[0].get('row') or {}).get('style')
    if row is None:
        row, level = pick_replacement(style, rows, keys, ctx.key)
    if row is None:
        return text, None
    line = beer_line(row, bar, ctx.names)
    info = {'name': beer_name(row, ctx.names), 'tap': row.get('tap_number'), 'level': level,
            'level_text': 'тот же сорт' if level == 'same_beer' else level_text(level, style)}
    return text[:start] + line + text[end:], info


def public_view(check: dict) -> dict:
    """beer_info для ответа API: без итогового текста (он есть в effective_text)."""
    return {key: check.get(key) for key in ('state', 'line', 'new_line', 'beers', 'replacement', 'note',
                                            'stale')}

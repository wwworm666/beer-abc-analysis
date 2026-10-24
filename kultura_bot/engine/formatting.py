"""Ответ модели (Markdown) -> сообщения Telegram (HTML).

Модель пишет привычный Markdown; Telegram понимает свой HTML (parse_mode=HTML):
<b>, <i>, <code>, <pre>, <a href>. Что переводится:

    ```…```              -> <pre>…</pre>   (моноширинно, у Telegram там «копировать»)
    `код`                -> <code>код</code>
    **жирный**           -> <b>жирный</b>
    *курсив*             -> <i>курсив</i>  (только внутри строки; «* пункт» — это список)
    [текст](https://…)   -> <a href="https://…">текст</a>
    # Заголовок          -> <b>Заголовок</b>
    - пункт / * пункт    -> • пункт
    строки таблицы | … | -> <pre>…</pre>   (если модель забыла про ```)
    > строка             -> <blockquote>…</blockquote>             (подряд идущие — одна цитата)
    >> строка            -> <blockquote expandable>…</blockquote>  (свёрнутая цитата)

Цитата — блок цифр («Подпись · значение · %») или текст гостя: в отличие от ```,
пропорциональный шрифт и перенос по словам, на телефоне ничего не съезжает. Внутри
цитаты — строчная разметка и пункты; цитаты не вкладываются (Telegram не разрешает).

Всё остальное экранируется (&, <, >): текст модели не может сломать разметку.

Длинный ответ режется на части не длиннее LIMIT символов по абзацам, блок кода не
разрывается посередине без нужды (а если он сам длиннее части — режется по строкам и
закрывается/открывается заново); длинный абзац или цитата — по строкам, каждая строка
сохраняет свой знак цитаты. Telegram отказал в разметке — то же сообщение уходит
простым текстом (plain).

## «Как считается» (split_how)

Решение владельца 2026-10-24: пояснение расчёта не занимает места в ответе. Модель пишет
его последним блоком свёрнутой цитаты, первая строка — «Как считается»:

    >> Как считается
    >> % плана = факт / план × 100; …

split_how вырезает этот блок; сервер бота сохраняет его запиской на сайте и ставит
ссылку (with_link — в конец последней строки) или кнопку. Сайт не ответил — блок остаётся
в ответе свёрнутой цитатой.
"""
import html
import re
from typing import List

LIMIT = 3500           # Telegram принимает 4096 символов текста; запас на теги и переводы строк
TELEGRAM_MAX = 4096    # предел Telegram на одно сообщение

# ```язык\n…``` — строка языка только если за ней перевод строки: «```ls -la```» — это код «ls -la».
_FENCE_RE = re.compile(r'```(?:[^\n`]*\n)?(.*?)```', re.S)
_INLINE_CODE_RE = re.compile(r'`([^`\n]+)`')
_BOLD_RE = re.compile(r'\*\*(?=\S)(.+?)(?<=\S)\*\*')
_ITALIC_RE = re.compile(r'(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])')
_LINK_RE = re.compile(r'\[([^\]\n]+)\]\((https?://[^)\s]+)\)')
_HEADING_RE = re.compile(r'^#{1,6}\s+(.+?)\s*#*\s*$')
_BULLET_RE = re.compile(r'^(\s*)[-*]\s+')
_TABLE_LINE_RE = re.compile(r'^\s*\|.*\|\s*$')
_TABLE_RULE_RE = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')
_QUOTE_RE = re.compile(r'^\s*(>>?)(?: |$)')             # «> текст» или «>> текст» (пробел после знака;
#                                                          отступ слева — тоже цитата: модель копирует его из примеров)
_TAG_RE = re.compile(r'<[^>]+>')
_HOW_HEAD_RE = re.compile(r'^[\s#*_«"]*как\s+считается[\s*_»"]*(?:[:.—–-][\s*_»"]*)?', re.I)


def safe_url(url: str) -> bool:
    """Ссылка http(s), которую браузер откроет там же, где она «написана»: без «user:pass@» и без
    знаков " < > \\ (https://beerkultura.ru:x@evil.example открывает evil.example)."""
    from urllib.parse import urlsplit
    if any(ch in url for ch in '"<>\\'):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    return parts.scheme in ('http', 'https') and bool(host) and '@' not in parts.netloc


def _inline(text: str) -> str:
    """Экранировать и перевести разметку внутри строки (код — первым: внутри него не трогаем)."""
    parts = _INLINE_CODE_RE.split(text)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(f'<code>{html.escape(part, quote=False)}</code>')
            continue
        links = []

        def keep_link(match):
            links.append((match.group(1), match.group(2)))
            return f'\x00{len(links) - 1}\x00'

        piece = _LINK_RE.sub(keep_link, part)
        piece = html.escape(piece, quote=False)
        piece = _BOLD_RE.sub(r'<b>\1</b>', piece)
        piece = _ITALIC_RE.sub(r'<i>\1</i>', piece)

        def put_link(match):
            label, url = links[int(match.group(1))]
            if not safe_url(url):
                # Ссылку, которую браузер откроет не там, где она «написана» (user@host, кавычки),
                # не делаем: остаются подпись и адрес текстом.
                return f'{html.escape(label, quote=False)} ({html.escape(url, quote=False)})'
            return f'<a href="{html.escape(url, quote=True)}">{html.escape(label, quote=False)}</a>'

        out.append(re.sub(r'\x00(\d+)\x00', put_link, piece))
    return ''.join(out)


def _line(line: str) -> str:
    """Одна строка текста -> HTML: заголовок, пункт или строчная разметка."""
    heading = _HEADING_RE.match(line)
    if heading:
        return f'<b>{_inline(heading.group(1))}</b>'
    bullet = _BULLET_RE.match(line)
    if bullet:
        return f'{bullet.group(1)}• {_inline(line[bullet.end():])}'
    return _inline(line)


def quote_kind(line: str) -> str:
    """'>>' — строка свёрнутой цитаты, '>' — цитаты, '' — не цитата."""
    match = _QUOTE_RE.match(line)
    return match.group(1) if match else ''


def _unquote(line: str) -> str:
    match = _QUOTE_RE.match(line)
    return line[match.end():] if match else line


def _text_block(text: str) -> str:
    """Текст вне блоков кода -> HTML: заголовки, списки, таблицы, цитаты, строчная разметка."""
    lines = text.split('\n')
    out: List[str] = []
    table: List[str] = []
    quote: List[str] = []
    quote_type = ''

    def flush_table():
        if table:
            rows = [r for r in table if not _TABLE_RULE_RE.match(r)]
            out.append('<pre>' + html.escape('\n'.join(rows), quote=False) + '</pre>')
            table.clear()

    def flush_quote():
        nonlocal quote_type
        if quote:
            opener = '<blockquote expandable>' if quote_type == '>>' else '<blockquote>'
            body = '\n'.join(_line(q) for q in quote).strip('\n')
            out.append(f'{opener}{body}</blockquote>')
            quote.clear()
        quote_type = ''

    for line in lines:
        kind = quote_kind(line)
        if kind:
            if kind != quote_type:
                flush_table()
                flush_quote()
                quote_type = kind
            quote.append(_unquote(line))
            continue
        flush_quote()
        if _TABLE_LINE_RE.match(line) or (table and _TABLE_RULE_RE.match(line)):
            table.append(line.strip())
            continue
        flush_table()
        out.append(_line(line))
    flush_table()
    flush_quote()
    return '\n'.join(out)


def to_html(markdown: str) -> str:
    """Markdown модели -> HTML Telegram."""
    out = []
    pos = 0
    for match in _FENCE_RE.finditer(markdown):
        out.append(_text_block(markdown[pos:match.start()]))
        code = match.group(1).rstrip('\n')
        out.append('<pre>' + html.escape(code, quote=False) + '</pre>')
        pos = match.end()
    out.append(_text_block(markdown[pos:]))
    return re.sub(r'\n{3,}', '\n\n', ''.join(out)).strip()


def plain(markdown: str) -> str:
    """Запасной вариант без разметки: снять ```, звёздочки и знаки цитат, оставить текст как есть."""
    text = re.sub(r'```(?:[^\n`]*\n)?', '', markdown)
    text = text.replace('**', '')
    text = _LINK_RE.sub(r'\1: \2', text)
    text = '\n'.join(_unquote(line) for line in text.split('\n'))
    return text.strip()


def visible_len(text_html: str) -> int:
    """Длина HTML Telegram так, как её считает Telegram: после разбора сущностей (без тегов) и в
    единицах UTF-16 — символ вне BMP (эмодзи из текста гостя) считается за два."""
    text = html.unescape(_TAG_RE.sub('', text_html or ''))
    return len(text.encode('utf-16-le')) // 2


def split_how(markdown: str):
    """Вырезать из ответа блоки «Как считается» (свёрнутые цитаты «>> Как считается …»).

    Вернуть (ответ без блоков, их текст в Markdown без знаков цитаты и строк-заголовков; если
    блоков несколько — например, бот передал отчёты двух агентов, — тексты через пустую
    строку). Блоков нет — (ответ как есть, '')."""
    lines = (markdown or '').split('\n')
    blocks = []                                   # (начало, конец) подряд идущих строк «>>»
    start = None
    for i, line in enumerate(lines + ['']):
        if i < len(lines) and quote_kind(line) == '>>':
            if start is None:
                start = i
        elif start is not None:
            blocks.append((start, i))
            start = None
    bodies, cut = [], set()
    for begin, end in blocks:
        first = _unquote(lines[begin]).strip()
        head = _HOW_HEAD_RE.match(first)
        if not head:
            continue
        body = [_unquote(line) for line in lines[begin + 1:end]]
        rest = first[head.end():].strip()
        if rest:
            body.insert(0, rest)
        text = '\n'.join(body).strip()
        if text:
            bodies.append(text)
        cut.update(range(begin, end))
    if not cut:
        return (markdown or '').strip(), ''
    visible = '\n'.join(line for i, line in enumerate(lines) if i not in cut)
    return re.sub(r'\n{3,}', '\n\n', visible).strip(), '\n\n'.join(bodies)


def truncate_utf16(text: str, limit: int) -> str:
    """Обрезать до limit единиц UTF-16 (так считает Telegram), не разрывая символ."""
    if len(text.encode('utf-16-le')) // 2 <= limit:
        return text
    out, used = [], 0
    for ch in text:
        size = 2 if ord(ch) > 0xFFFF else 1
        if used + size > limit:
            break
        out.append(ch)
        used += size
    return ''.join(out)


def with_link(markdown: str, text: str, url: str) -> str:
    """Дописать ссылку [text](url) в конец последней строки ответа (ни строки места), а если
    ответ кончается кодом, таблицей или цитатой — отдельной строкой."""
    body = (markdown or '').rstrip()
    link = f'[{text}]({url})'
    if not body:
        return link
    last = body.split('\n')[-1]
    if body.endswith('```') or quote_kind(last) or _TABLE_LINE_RE.match(last) or _HEADING_RE.match(last):
        return f'{body}\n{link}'
    joiner = ' ' if last.rstrip('*_ ').endswith(('.', '!', '?', '…', ':')) else ' · '
    return f'{body}{joiner}{link}'


def _split_code(block: str, limit: int) -> List[str]:
    """Блок ``` длиннее части — по строкам, каждая часть снова в ```; строка длиннее части
    режется на куски (иначе часть вышла бы за предел Telegram и не ушла)."""
    match = re.match(r'(```(?:[^\n`]*\n)?)(.*?)(```)\s*$', block, re.S)
    opener, body = (match.group(1), match.group(2)) if match else ('```\n', block)
    if not opener.endswith('\n'):
        opener += '\n'
    width = max(1, limit - len(opener) - 4)
    lines: List[str] = []
    for line in body.rstrip('\n').split('\n'):
        lines += [line[i:i + width] for i in range(0, len(line), width)] or ['']
    chunks, current = [], ''
    for line in lines:
        candidate = current + line + '\n'
        if current and len(opener) + len(candidate) + 3 > limit:
            chunks.append(opener + current + '```')
            current = line + '\n'
        else:
            current = candidate
    if current:
        chunks.append(opener + current + '```')
    return chunks


def _split_lines(piece: str, limit: int) -> List[str]:
    """Абзац или цитата длиннее части — по строкам (строка цитаты сохраняет свой знак «>»);
    строка длиннее части — кусками."""
    chunks: List[str] = []
    current = ''
    for line in piece.split('\n'):
        prefix = '>> ' if quote_kind(line) == '>>' else '> ' if quote_kind(line) else ''
        step = limit - len(prefix)
        pieces = [line] if len(line) <= limit else \
            [line[:limit]] + [prefix + line[i:i + step] for i in range(limit, len(line), step)]
        for sub in pieces:
            candidate = f'{current}\n{sub}' if current else sub
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sub
    if current:
        chunks.append(current)
    return chunks


def split(markdown: str, limit: int = LIMIT) -> List[str]:
    """Разрезать Markdown на части не длиннее limit: по абзацам, блоки кода целиком."""
    markdown = (markdown or '').strip()
    if len(markdown) <= limit:
        return [markdown] if markdown else []
    pieces: List[str] = []
    pos = 0
    for match in re.finditer(r'```.*?```', markdown, re.S):
        pieces += [p for p in re.split(r'\n{2,}', markdown[pos:match.start()]) if p.strip()]
        pieces.append(match.group(0))
        pos = match.end()
    pieces += [p for p in re.split(r'\n{2,}', markdown[pos:]) if p.strip()]

    parts: List[str] = []
    current = ''
    for piece in pieces:
        if len(piece) > limit:
            subpieces = _split_code(piece, limit) if piece.startswith('```') else _split_lines(piece, limit)
        else:
            subpieces = [piece]
        for sub in subpieces:
            candidate = f'{current}\n\n{sub}' if current else sub
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    parts.append(current)
                current = sub
    if current:
        parts.append(current)
    return parts

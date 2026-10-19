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

Всё остальное экранируется (&, <, >): текст модели не может сломать разметку.

Длинный ответ режется на части не длиннее LIMIT символов по абзацам, блок кода не
разрывается посередине без нужды (а если он сам длиннее части — режется по строкам и
закрывается/открывается заново). Telegram отказал в разметке — то же сообщение уходит
простым текстом (plain).
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
            return f'<a href="{html.escape(url, quote=True)}">{html.escape(label, quote=False)}</a>'

        out.append(re.sub(r'\x00(\d+)\x00', put_link, piece))
    return ''.join(out)


def _text_block(text: str) -> str:
    """Текст вне блоков кода -> HTML: заголовки, списки, таблицы, строчная разметка."""
    lines = text.split('\n')
    out: List[str] = []
    table: List[str] = []

    def flush_table():
        if table:
            rows = [r for r in table if not _TABLE_RULE_RE.match(r)]
            out.append('<pre>' + html.escape('\n'.join(rows), quote=False) + '</pre>')
            table.clear()

    for line in lines:
        if _TABLE_LINE_RE.match(line) or (table and _TABLE_RULE_RE.match(line)):
            table.append(line.strip())
            continue
        flush_table()
        heading = _HEADING_RE.match(line)
        if heading:
            out.append(f'<b>{_inline(heading.group(1))}</b>')
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            out.append(f'{bullet.group(1)}• {_inline(line[bullet.end():])}')
            continue
        out.append(_inline(line))
    flush_table()
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
    """Запасной вариант без разметки: снять ``` и звёздочки, оставить текст как есть."""
    text = re.sub(r'```(?:[^\n`]*\n)?', '', markdown)
    text = text.replace('**', '')
    return text.strip()


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
            subpieces = (_split_code(piece, limit) if piece.startswith('```') else
                         [piece[i:i + limit] for i in range(0, len(piece), limit)])
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

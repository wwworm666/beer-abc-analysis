"""Богатые сообщения Telegram (Bot API 10.1, sendRichMessage): ответ модели (Markdown) -> блоки.

## Что это

Решение владельца 2026-11-06 («Мне очень нравится. Давай делать»): ответ бота — одно богатое
сообщение. Внутри — то, что раньше было только на страницах сайта: заголовок, настоящая
таблица, раскрывающийся блок «Как считается», картинка графика, подвал со временем данных,
кнопки следующего шага. Telegram рисует их сам, как статьи Instant View.

Модель пишет тот же Markdown, что и для обычных сообщений (formatting.py); этот модуль
переводит его в список блоков InputRichMessage.blocks (поле blocks, а не html: структура
блоков описана в спецификации Bot API полностью, разметка html — нет). Общий модуль сервера
бота (текстовые ответы, engine/service.py) и сайта (графики и выжимки отчётов,
kultura_bot/charts/send.py); кода сайта не импортирует.

## Как переводится

    ## Лид                     -> heading (size: # 2, ## 3, ### 4, #### и мельче 5)
    строка текста               -> paragraph (каждая строка — свой абзац: перевод строки внутри
                                   абзаца Telegram может склеить)
    - пункт / * пункт / • пункт -> list (подряд идущие пункты — один список)
    1. пункт                    -> list с номерами (value, type «1»)
    | a | b |  (таблица)        -> table: строка над «|---|» — заголовки; выравнивание из «:--:»,
                                   иначе колонка чисел — вправо; полосами, компактно
    > строка                    -> blockquote (подряд идущие — одна цитата)
    >> строка                   -> details (первая строка — заголовок) или expandable_blockquote
    ```код```                   -> pre
    ---                         -> divider
    *строка курсивом* в конце   -> footer (время данных, строка цены)
    [[Текст]] отдельной строкой -> кнопки следующего шага (split_buttons в formatting.py)

Внутри строки: **жирный**, *курсив*, `код`, ==маркер== (выделение — цвета внутри сообщения
нет), [текст](https://…) — ссылка (небезопасный адрес — текстом, formatting.safe_url).
Пробелы в числах — неразрывные (formatting.nbsp).

«Как считается» (formatting.split_how) — блок details в конце, свёрнутый: решение владельца
2026-09-27 «пояснения свёрнуты по умолчанию» — теперь прямо в сообщении, без записки на сайте.

## Пределы

Своё сообщение не длиннее MAX_CHARS видимых символов и MAX_BLOCKS блоков (вложенные
считаются), в таблице не больше MAX_TABLE_COLS колонок (шире — моноширинным блоком). Больше —
RichError: вызывающий шлёт обычным сообщением (оно режется на части).
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from kultura_bot.engine import formatting

MAX_CHARS = 30000           # видимого текста; предел Telegram больше — запас на разметку
MAX_BLOCKS = 400            # блоков вместе с вложенными (у Telegram — 500)
MAX_TABLE_COLS = 12         # колонок таблицы (у Telegram — 20); шире на телефоне не читается
HOW_SUMMARY = 'Как считается'
HEADING_SIZE = {1: 2, 2: 3, 3: 4}          # «#» -> 2 … «####» и мельче -> 5

_INLINE_RE = re.compile(
    r'`(?P<code>[^`\n]+)`'
    r'|\[(?P<label>[^\]\n]+)\]\((?P<url>https?://[^)\s]+)\)'
    r'|\*\*(?=\S)(?P<bold>.+?)(?<=\S)\*\*'
    r'|==(?=\S)(?P<mark>.+?)(?<=\S)=='
    r'|(?<![\w*])\*(?=\S)(?P<italic>[^*\n]+?)(?<=\S)\*(?![\w*])'
    r'|(?<![\w_])_(?=\S)(?P<italic2>[^_\n]+?)(?<=\S)_(?![\w_])')
_HEADING_RE = re.compile(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$')
_BULLET_RE = re.compile(r'^\s*(?:[-*•])\s+(.*)$')
_NUMBERED_RE = re.compile(r'^\s*(\d{1,3})[.)]\s+(.*)$')
_TABLE_LINE_RE = re.compile(r'^\s*\|.*\|\s*$')
_TABLE_RULE_RE = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$')
_DIVIDER_RE = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$')
_FOOTER_RE = re.compile(r'^\s*(?:\*(?!\*)(?P<a>[^*\n]+?)\*|_(?!_)(?P<b>[^_\n]+?)_)\s*$')
_NUMBER_CELL_RE = re.compile(r'^[−+\-–]?\s?\d[\d\s .,]*\s?(?:%|‰|₽|тыс\.?(?:\s?₽)?|млн(?:\s?₽)?|п\.\s?п\.|л|шт|ч)?$')
_FENCE_RE = re.compile(r'```(?:[^\n`]*\n)?(.*?)```', re.S)


class RichError(ValueError):
    """Ответ не собрать богатым сообщением (велик): слать обычным."""


# ------------------------------------------------------------------ строка -> RichText

def _simplify(parts: List[Any]) -> Any:
    """Список частей -> RichText: одна строка — строкой, один объект — объектом."""
    merged: List[Any] = []
    for part in parts:
        if part == '' or part == []:
            continue
        if isinstance(part, str) and merged and isinstance(merged[-1], str):
            merged[-1] += part
        else:
            merged.append(part)
    if not merged:
        return ''
    return merged[0] if len(merged) == 1 else merged


def inline(text: str) -> Any:
    """Строка Markdown -> RichText (строка, объект или список)."""
    text = text or ''
    parts: List[Any] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > pos:
            parts.append(formatting.nbsp(text[pos:match.start()]))
        pos = match.end()
        if match.group('code') is not None:
            parts.append({'type': 'code', 'text': match.group('code')})
        elif match.group('url') is not None:
            label, url = match.group('label'), match.group('url')
            if formatting.safe_url(url):
                parts.append({'type': 'url', 'text': inline(label), 'url': url})
            else:
                # Адрес, который откроет не то, что написано (user@host, кавычки), — текстом.
                parts.append(formatting.nbsp(f'{label} ({url})'))
        elif match.group('bold') is not None:
            parts.append({'type': 'bold', 'text': inline(match.group('bold'))})
        elif match.group('mark') is not None:
            parts.append({'type': 'marked', 'text': inline(match.group('mark'))})
        else:
            inner = match.group('italic') if match.group('italic') is not None else match.group('italic2')
            parts.append({'type': 'italic', 'text': inline(inner)})
    if pos < len(text):
        parts.append(formatting.nbsp(text[pos:]))
    return _simplify(parts)


def _rich_str(node: Any) -> str:
    """RichText -> строка без разметки."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return ''.join(_rich_str(item) for item in node)
    if isinstance(node, dict):
        return _rich_str(node.get('text', ''))
    return ''


def plain_text(value: Any) -> str:
    """Видимый текст блоков (своих и полученных — RichMessage.blocks), строками: для пределов, журнала
    и ответа на сообщение бота (в reply_to_message у богатого сообщения нет поля text). Таблица —
    строками «a | b», пункты — «- », цитата — «> », раскрывашка — заголовок и текст с отступом."""
    lines: List[str] = []

    def block(node: Any, prefix: str = '') -> None:
        if isinstance(node, list):
            for item in node:
                block(item, prefix)
            return
        if not isinstance(node, dict):
            if isinstance(node, str) and node.strip():
                lines.append(prefix + node)
            return
        kind = node.get('type')
        if kind == 'table':
            for row in node.get('cells') or []:
                lines.append(prefix + ' | '.join(_rich_str((c or {}).get('text', '')) for c in row or []))
        elif kind == 'list':
            for item in node.get('items') or []:
                for n, sub in enumerate((item or {}).get('blocks') or []):
                    block(sub, prefix + ('- ' if n == 0 else '  '))
        elif kind == 'blockquote':
            block(node.get('blocks') or [], prefix + '> ')
        elif kind == 'details':
            lines.append(prefix + _rich_str(node.get('summary', '')))
            block(node.get('blocks') or [], prefix + '  ')
        elif kind == 'buttons':
            lines.append(prefix + ' '.join(f'[{_rich_str(b.get("text", ""))}]' for b in node.get('buttons') or []
                                           if isinstance(b, dict)))
        elif kind in ('photo', 'animation', 'video', 'collage', 'slideshow', 'map', 'document', 'audio'):
            lines.append(prefix + '[картинка]' if kind == 'photo' else prefix + f'[{kind}]')
        elif kind == 'divider':
            lines.append(prefix + '—')
        elif 'text' in node:
            lines.append(prefix + _rich_str(node.get('text')))
        elif 'blocks' in node:
            block(node.get('blocks') or [], prefix)

    block(value)
    return '\n'.join(line.rstrip() for line in lines if line.strip()).strip()


# ------------------------------------------------------------------ блоки

def paragraph(text: str) -> Dict[str, Any]:
    return {'type': 'paragraph', 'text': inline(text)}


def heading(text: str, level: int = 2) -> Dict[str, Any]:
    return {'type': 'heading', 'text': inline(text), 'size': HEADING_SIZE.get(level, 5)}


def footer(text: str) -> Dict[str, Any]:
    return {'type': 'footer', 'text': inline(text)}


def details(summary: str, blocks: List[Dict[str, Any]], is_open: bool = False) -> Dict[str, Any]:
    out = {'type': 'details', 'summary': inline(summary), 'blocks': blocks or [paragraph(summary)]}
    if is_open:
        out['is_open'] = True
    return out


def thinking(text: str) -> Dict[str, Any]:
    """«Думаю…» в черновике (sendRichMessageDraft): в сообщениях такого блока не бывает."""
    return {'type': 'thinking', 'text': inline(text)}


def photo(attach_name: str) -> Dict[str, Any]:
    """Картинка внутри сообщения: файл уходит тем же запросом (multipart, attach://<имя>)."""
    return {'type': 'photo', 'photo': {'type': 'photo', 'media': f'attach://{attach_name}'}}


def buttons(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Ряд кнопок внутри сообщения (до 8): {text, url | web_app | callback_data}."""
    return {'type': 'buttons', 'buttons': list(items)[:8]}


def _is_rule(line: str) -> bool:
    """Строка «|---|:-:|» под заголовками. Ячейки из одного «-» без двоеточий — это прочерки в данных."""
    return bool(_TABLE_RULE_RE.match(line)) and ('--' in line or ':' in line)


def _cells(line: str) -> List[str]:
    body = line.strip()
    if body.startswith('|'):
        body = body[1:]
    if body.endswith('|'):
        body = body[:-1]
    return [cell.strip() for cell in body.split('|')]


def _rule_aligns(line: str) -> List[Optional[str]]:
    out: List[Optional[str]] = []
    for cell in _cells(line):
        left, right = cell.startswith(':'), cell.endswith(':')
        out.append('center' if left and right else 'right' if right else 'left' if left else None)
    return out


def _bare(cell: str) -> str:
    """Текст ячейки без разметки — чтобы узнать число."""
    return re.sub(r'[*_=`]', '', cell).strip()


def table(lines: List[str]) -> Dict[str, Any]:
    """Строки таблицы Markdown -> блок table (или pre, если колонок больше MAX_TABLE_COLS)."""
    rule_at = next((i for i, line in enumerate(lines) if _is_rule(line)), None)
    aligns: List[Optional[str]] = _rule_aligns(lines[rule_at]) if rule_at is not None else []
    header_rows = rule_at if rule_at is not None and rule_at > 0 else 0
    rows = [_cells(line) for i, line in enumerate(lines) if i != rule_at]
    width = max((len(r) for r in rows), default=0)
    if width > MAX_TABLE_COLS:
        return {'type': 'pre', 'text': '\n'.join(line.strip() for line in lines if not _is_rule(line))}
    body = rows[header_rows:]
    for col in range(width):
        if col < len(aligns) and aligns[col]:
            continue
        values = [_bare(r[col]) for r in body if col < len(r) and _bare(r[col])]
        numeric = bool(values) and sum(1 for v in values if _NUMBER_CELL_RE.match(v)) * 10 >= len(values) * 6
        if col >= len(aligns):
            aligns.append(None)
        aligns[col] = 'right' if numeric and col > 0 else 'left'
    cells = []
    for n, row in enumerate(rows):
        out_row = []
        for col in range(width):
            raw = row[col] if col < len(row) else ''
            # Пустая ячейка — неразрывный пробел: без text Telegram прячет ячейку, пустую строку может не принять.
            cell: Dict[str, Any] = {'text': inline(raw) if raw.strip() else formatting.NBSP,
                                    'align': aligns[col] or 'left', 'valign': 'middle'}
            if n < header_rows:
                cell['is_header'] = True
            out_row.append(cell)
        cells.append(out_row)
    return {'type': 'table', 'cells': cells, 'is_striped': True, 'is_compact': True}


def _list(items: List[Tuple[Optional[int], str]]) -> Dict[str, Any]:
    out = []
    for number, text in items:
        item: Dict[str, Any] = {'blocks': [paragraph(text)]}
        if number is not None:
            item['value'], item['type'] = number, '1'
        out.append(item)
    return {'type': 'list', 'items': out}


def _quote(kind: str, lines: List[str]) -> Dict[str, Any]:
    lines = [line for line in lines]
    while lines and not lines[-1].strip():
        lines.pop()
    if kind == '>>':
        if len(lines) == 1:
            return {'type': 'expandable_blockquote', 'text': inline(lines[0])}
        return details(lines[0].strip() or '…', [paragraph(line) for line in lines[1:] if line.strip()])
    return {'type': 'blockquote', 'blocks': [paragraph(line) for line in lines if line.strip()] or
            [paragraph(formatting.NBSP)]}


def _text_blocks(text: str) -> List[Dict[str, Any]]:
    """Текст вне ``` -> блоки."""
    out: List[Dict[str, Any]] = []
    table_lines: List[str] = []
    quote_lines: List[str] = []
    quote_type = ''
    items: List[Tuple[Optional[int], str]] = []

    def flush_table():
        if table_lines:
            out.append(table(list(table_lines)))
            table_lines.clear()

    def flush_quote():
        nonlocal quote_type
        if quote_lines:
            out.append(_quote(quote_type, list(quote_lines)))
            quote_lines.clear()
        quote_type = ''

    def flush_items():
        if items:
            out.append(_list(list(items)))
            items.clear()

    for line in text.split('\n'):
        kind = formatting.quote_kind(line)
        if kind:
            flush_table()
            flush_items()
            if kind != quote_type:
                flush_quote()
                quote_type = kind
            quote_lines.append(re.sub(r'^\s*>>?(?: |$)', '', line, count=1))
            continue
        flush_quote()
        if _TABLE_LINE_RE.match(line) or (table_lines and _is_rule(line)):
            flush_items()
            table_lines.append(line)
            continue
        flush_table()
        bullet = _BULLET_RE.match(line)
        numbered = None if bullet else _NUMBERED_RE.match(line)
        if bullet or numbered:
            if numbered and items and items[-1][0] is None:
                flush_items()
            items.append((None, bullet.group(1)) if bullet else (int(numbered.group(1)), numbered.group(2)))
            continue
        flush_items()
        if not line.strip():
            continue
        head = _HEADING_RE.match(line)
        if head:
            out.append(heading(head.group(2), len(head.group(1))))
        elif _DIVIDER_RE.match(line):
            out.append({'type': 'divider'})
        else:
            out.append(paragraph(line.strip()))
    flush_table()
    flush_quote()
    flush_items()
    return out


def blocks_from_markdown(markdown: str) -> List[Dict[str, Any]]:
    """Markdown модели -> блоки (без кнопок, подвала и «Как считается» — их собирает message)."""
    markdown = (markdown or '').replace('\r', '')
    out: List[Dict[str, Any]] = []
    pos = 0
    for match in _FENCE_RE.finditer(markdown):
        out += _text_blocks(markdown[pos:match.start()])
        out.append({'type': 'pre', 'text': match.group(1).rstrip('\n')})
        pos = match.end()
    out += _text_blocks(markdown[pos:])
    return out


def _footer_lines(markdown: str) -> Tuple[str, List[str]]:
    """Строки курсивом в самом конце ответа (время данных, строка цены) -> текст подвала."""
    lines = (markdown or '').rstrip().split('\n')
    tail: List[str] = []
    while lines:
        last = lines[-1]
        if not last.strip():
            lines.pop()
            continue
        match = _FOOTER_RE.match(last)
        if not match:
            break
        tail.insert(0, match.group('a') or match.group('b'))
        lines.pop()
    return '\n'.join(lines), tail


def count_blocks(blocks: Any) -> int:
    """Блоки вместе с вложенными (пункты списков и раскрывашки)."""
    total = 0
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        total += 1
        total += count_blocks(block.get('blocks'))
        for item in block.get('items') or []:
            total += count_blocks(item.get('blocks'))
    return total


def message(markdown: str, *, how: str = '', button_rows: Optional[List[Dict[str, Any]]] = None,
            photo_name: str = '') -> Dict[str, Any]:
    """Ответ -> InputRichMessage {blocks}.

    how — «Как считается» (Markdown, уже вырезанный split_how): свёрнутым блоком в конце;
    button_rows — кнопки (готовые объекты RichMessageButton) одним рядом последним блоком;
    photo_name — картинка (attach://<имя>): после первого заголовка, а без него — первой.
    Велико — RichError."""
    body, tail = _footer_lines(markdown)
    blocks = blocks_from_markdown(body)
    if photo_name:
        at = 1 if blocks and blocks[0].get('type') == 'heading' else 0
        blocks.insert(at, photo(photo_name))
    if how and how.strip():
        blocks.append(details(HOW_SUMMARY, blocks_from_markdown(how)))
    blocks += [footer(line) for line in tail]
    if button_rows:
        blocks.append(buttons(button_rows))
    if not blocks:
        raise RichError('пустой ответ')
    if count_blocks(blocks) > MAX_BLOCKS:
        raise RichError(f'больше {MAX_BLOCKS} блоков')
    if len(plain_text(blocks)) > MAX_CHARS:
        raise RichError(f'длиннее {MAX_CHARS} знаков')
    return {'blocks': blocks}


def draft(text: str, detail: str = '') -> Dict[str, Any]:
    """Черновик «бот работает»: блок «Думаю…» и строка под ним."""
    blocks = [thinking(text)]
    if detail:
        blocks.append(paragraph(detail))
    return {'blocks': blocks}

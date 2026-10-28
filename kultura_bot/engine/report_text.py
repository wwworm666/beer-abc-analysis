"""Страница отчёта из текста ответа — запасной путь режима отчёта.

## Зачем

Решение владельца 2026-10-24: большой вопрос (/report, «отчёт: …») — ответ страницей, в чате —
выжимка с кнопкой «Открыть отчёт». Страницу собирает модель инструментом common_report_send.
2026-10-28 «/report» пришёл обычным сообщением: модель ответила текстом (сама или упёршись в
предел), и бот отправил текст как есть. Теперь сервер бота (service.finish_report) сначала
просит модель оформить ответ отчётом, а если и это не помогло — собирает страницу сам из
текста здесь: в режиме отчёта ответ всегда уходит страницей.

## Как собирается

    «Как считается»   все блоки «>> Как считается» (formatting.split_how) -> how отчёта
    заголовок         первая непустая строка без разметки (#, **, _), до TITLE_MAX; пустая —
                      вопрос человека; нет и его — «Отчёт»
    выжимка           начало ответа целыми абзацами до первого заголовка, не длиннее
                      SUMMARY_TARGET знаков (первый абзац длиннее — обрезается по слову с «…»)
    разделы           остальное, по строкам-заголовкам («# …», «**Целая строка жирным**»; первая
                      строка — лид, не заголовок);
                      строка-«заголовок» без текста под ней («**Дальше: …**») остаётся текстом
                      в конце предыдущего раздела; текст до первого заголовка — раздел
                      «Подробно»; раздел длиннее TEXT_MAX —
                      частями «(продолжение)»; разделов больше SECTIONS_MAX — хвост в последнем.
                      Ответ целиком ушёл в выжимку — один раздел «Ответ целиком»
    источник          SOURCE; время данных не ставится (время сборки — не время выгрузки)

Пределы — как в kultura_bot/charts/reports.py (сервер бота код сайта не импортирует; равенство
проверяет tests/test_kultura_bot.py).
"""
import re
from typing import Any, Dict, List, Tuple

from kultura_bot.engine import formatting

TITLE_MAX = 120
HEADING_MAX = 120
TEXT_MAX = 8000
HOW_MAX = 6000
SECTIONS_MAX = 20
SUMMARY_TARGET = 900          # выжимка в чате — сообщение под кнопкой: коротко, как пузырь
SOURCE = 'данные сайта'
AUTO_NOTE = 'Страницу собрал бот из текста ответа: модель не оформила отчёт сама.'

_HEADING_RE = re.compile(r'^\s*#{1,6}\s+(.+?)\s*#*\s*$')
_BOLD_LINE_RE = re.compile(r'^\s*\*\*([^*\n]{2,160}?)\*\*\s*:?\s*$')
_MARKUP_RE = re.compile(r'[*_`#>]+')


def _plain_line(line: str) -> str:
    """Строка без разметки Markdown: «**Итог:** 5» -> «Итог: 5»."""
    return re.sub(r'\s+', ' ', _MARKUP_RE.sub('', line)).strip()


def _cut(text: str, limit: int) -> str:
    """Не длиннее limit: по последнему пробелу, с «…»."""
    if len(text) <= limit:
        return text
    head = text[:limit - 1]
    space = head.rfind(' ')
    return (head[:space] if space > limit // 2 else head).rstrip(' ,;:—–-') + '…'


def _heading(line: str) -> str:
    """Строка-заголовок -> его текст; не заголовок -> ''."""
    match = _HEADING_RE.match(line) or _BOLD_LINE_RE.match(line)
    return _plain_line(match.group(1)) if match else ''


def _split_sections(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Текст -> (то, что до первого заголовка; [(заголовок, текст раздела)])."""
    head: List[str] = []
    sections: List[Tuple[str, List[str]]] = []
    for line in text.split('\n'):
        # Первая строка — лид («**Неделя …: 4 412 тыс. ₽ …**», правило «Как отвечать»), а не заголовок раздела.
        title = _heading(line) if any(h.strip() for h in head) or sections else ''
        if title:
            sections.append((title, []))
        elif sections:
            sections[-1][1].append(line)
        else:
            head.append(line)
    return '\n'.join(head).strip(), [(t, '\n'.join(body).strip()) for t, body in sections]


def _summary(lead: str) -> Tuple[str, str]:
    """Начало ответа -> (выжимка, остаток): целыми абзацами до SUMMARY_TARGET знаков."""
    paragraphs = [p for p in re.split(r'\n\s*\n', lead) if p.strip()]
    taken: List[str] = []
    size = 0
    while paragraphs and (not taken or size + len(paragraphs[0]) <= SUMMARY_TARGET):
        size += len(paragraphs[0]) + 2
        taken.append(paragraphs.pop(0))
    summary = '\n\n'.join(taken).strip()
    if len(summary) > SUMMARY_TARGET:            # первый абзац сам длиннее — обрезаем, остальное в разделе
        rest = summary
        summary = _cut(formatting.plain(summary), SUMMARY_TARGET)
        return summary, '\n\n'.join([rest] + paragraphs).strip()
    return summary, '\n\n'.join(paragraphs).strip()


def _parts(heading: str, text: str) -> List[Dict[str, Any]]:
    """Раздел длиннее TEXT_MAX -> части по абзацам «(продолжение)»."""
    out: List[Dict[str, Any]] = []
    chunk = ''
    for paragraph in re.split(r'(\n\s*\n)', text):
        if chunk and len(chunk) + len(paragraph) > TEXT_MAX:
            out.append(chunk.strip())
            chunk = ''
        while len(paragraph) > TEXT_MAX:             # один абзац длиннее раздела — по строкам/знакам
            out.append(paragraph[:TEXT_MAX].strip())
            paragraph = paragraph[TEXT_MAX:]
        chunk += paragraph
    if chunk.strip():
        out.append(chunk.strip())
    name = _cut(heading, HEADING_MAX)
    return [{'heading': name if i == 0 else _cut(f'{heading} (продолжение)', HEADING_MAX), 'text': part}
            for i, part in enumerate(out)]


def build(answer: str, question: str = '') -> Dict[str, Any]:
    """Текст ответа (Markdown бота) -> отчёт в формате common_report_send."""
    visible, how = formatting.split_how(answer or '')
    visible = visible.strip()
    first = next((ln for ln in visible.split('\n') if ln.strip()), '')
    title = _cut(_plain_line(first), TITLE_MAX) or _cut(_plain_line(question), TITLE_MAX) or 'Отчёт'
    lead, headed = _split_sections(visible)
    summary, rest = _summary(lead)
    if not summary:                                   # ответ начался сразу с заголовка
        summary = _cut(formatting.plain(visible), SUMMARY_TARGET) or title
    sections: List[Dict[str, Any]] = []
    if rest:
        sections += _parts('Подробно', rest)
    for heading, body in headed:
        if body:
            sections += _parts(heading, body)
        elif sections and len(sections[-1]['text']) + len(heading) + 6 <= TEXT_MAX:
            # Строка жирным без текста под ней («**Дальше: проверить …**») — не заголовок, а вывод:
            # остаётся текстом в конце предыдущего раздела.
            sections[-1]['text'] += f'\n\n**{heading}**'
        else:
            sections += _parts('Подробно', f'**{heading}**')
    if not sections:
        sections = _parts('Ответ целиком', visible or summary)
    if len(sections) > SECTIONS_MAX:                  # хвост — в последний раздел (с его частями)
        tail = sections[SECTIONS_MAX - 1:]
        merged = '\n\n'.join(f'**{s["heading"]}**\n{s["text"]}' for s in tail)
        sections = sections[:SECTIONS_MAX - 1] + [{'heading': tail[0]['heading'], 'text': _cut(merged, TEXT_MAX)}]
    report_how = '\n\n'.join(filter(None, [how.strip(), AUTO_NOTE]))
    return {'title': title, 'summary': summary, 'sections': sections, 'how': _cut(report_how, HOW_MAX),
            'source': SOURCE}

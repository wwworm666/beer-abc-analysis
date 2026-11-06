"""
Богатые сообщения бота @MCPkulturabot (kultura_bot/engine/rich.py, решение владельца 2026-11-06):
ответ модели (Markdown) -> блоки InputRichMessage (Bot API 10.1), кнопки следующего шага
(kultura_bot/engine/formatting.py) и примеры для /rich (kultura_bot/rich_demo.py).

Что проверяется:
- строка: жирный, курсив, код, маркер, ссылка (небезопасная — текстом), неразрывные пробелы;
- блоки: заголовки и их размеры, абзац на строку, списки (с номерами и без), цитата,
  «>>» — раскрывашка или свёрнутая цитата, код, разделитель;
- таблица: строка над «|---|» — заголовки, колонка чисел вправо, первая — влево, выравнивание
  из «:--:», жирный итог, шире MAX_TABLE_COLS — моноширинным блоком;
- сообщение: «Как считается» — свёрнутый блок в конце, строки курсивом в конце — подвал (и
  строка цены), кнопки — последним блоком, картинка — после первого заголовка; пустое и
  слишком длинное — RichError (шлём прежним видом);
- текст блоков для ответа на сообщение (plain_text): таблица строками, пункты, раскрывашка;
- кнопки: строка «[[…]]» — кнопки, не текст; не больше трёх, повторы один раз, callback_data не
  длиннее 64 байт; в прежнем виде — ряд под сообщением, ниже уже стоящих кнопок; «==x==» в
  прежнем виде — жирным, в простом тексте — без знаков;
- примеры /rich собираются, проходят пределы, кнопки примеров — подсказки, а не вопросы; график
  примера — верное описание.

Запуск: `py -3 -m pytest tests/test_kultura_bot_rich.py`.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from kultura_bot import rich_demo  # noqa: E402
from kultura_bot.engine import formatting, rich  # noqa: E402

NB = ' '


def kinds(blocks):
    return [b['type'] for b in blocks]


# ------------------------------------------------------------------ строка

def test_inline_marks():
    assert rich.inline('просто текст') == 'просто текст'
    assert rich.inline('**жирный**') == {'type': 'bold', 'text': 'жирный'}
    assert rich.inline('до *курсив* после') == ['до ', {'type': 'italic', 'text': 'курсив'}, ' после']
    assert rich.inline('_курсив_') == {'type': 'italic', 'text': 'курсив'}
    assert rich.inline('`код **не жирный**`') == {'type': 'code', 'text': 'код **не жирный**'}
    assert rich.inline('==89%==') == {'type': 'marked', 'text': '89%'}
    assert rich.inline('**[сайт](https://beerkultura.ru)**') == {
        'type': 'bold', 'text': {'type': 'url', 'text': 'сайт', 'url': 'https://beerkultura.ru'}}


def test_inline_unsafe_link_stays_text_and_numbers_get_nbsp():
    out = rich.inline('[сайт](https://beerkultura.ru:x@evil.example)')
    assert out == 'сайт (https://beerkultura.ru:x@evil.example)'
    assert rich.inline('1 412 тыс. ₽') == f'1{NB}412{NB}тыс.{NB}₽'
    # «*» в начале строки — это пункт списка, а не курсив (блоки разбирают его раньше)
    assert kinds(rich.blocks_from_markdown('* пункт')) == ['list']


# ------------------------------------------------------------------ блоки

def test_headings_paragraphs_lists_quotes_code():
    md = '\n'.join([
        '# Большой', '## Лид', '### Подраздел', '#### Мелкий',
        'строка один', 'строка два', '',
        '- а', '* б', '• в',
        '1. первый', '2. второй',
        '> цитата', '> вторая строка',
        '---',
        '```', 'код', '```',
    ])
    blocks = rich.blocks_from_markdown(md)
    assert kinds(blocks) == ['heading'] * 4 + ['paragraph', 'paragraph', 'list', 'list', 'blockquote', 'divider', 'pre']
    assert [b['size'] for b in blocks[:4]] == [2, 3, 4, 5]
    bullets, numbered = blocks[6], blocks[7]
    assert [i['blocks'][0]['text'] for i in bullets['items']] == ['а', 'б', 'в']
    assert all('value' not in i for i in bullets['items'])
    assert [(i['value'], i['type']) for i in numbered['items']] == [(1, '1'), (2, '1')]
    assert [b['text'] for b in blocks[8]['blocks']] == ['цитата', 'вторая строка']
    assert blocks[10] == {'type': 'pre', 'text': 'код'}


def test_double_quote_is_details_or_expandable():
    blocks = rich.blocks_from_markdown('>> Отзыв гостя\n>> Пиво отличное\n>> Персонал вежлив')
    assert blocks == [{'type': 'details', 'summary': 'Отзыв гостя',
                       'blocks': [{'type': 'paragraph', 'text': 'Пиво отличное'},
                                  {'type': 'paragraph', 'text': 'Персонал вежлив'}]}]
    assert rich.blocks_from_markdown('>> одна строка') == [{'type': 'expandable_blockquote', 'text': 'одна строка'}]


def test_table_headers_alignment_and_total():
    md = '\n'.join([
        '| Бар | тыс. ₽ | % плана | заметка |',
        '|---|---|:-:|---|',
        '| Лиговский | 1 412 | 104% | пятница +71 |',
        '| Кременчугская | 1 101 | ==89%== | вторник −29 |',
        '| **Все бары** | **4 412** | **98%** | |',
    ])
    [table] = rich.blocks_from_markdown(md)
    assert table['type'] == 'table' and table['is_striped'] and table['is_compact']
    header, first, second, total = table['cells']
    assert all(c.get('is_header') for c in header) and not any(c.get('is_header') for c in first)
    assert [c['align'] for c in header] == ['left', 'right', 'center', 'left']
    assert all(c['valign'] == 'middle' for row in table['cells'] for c in row)
    assert first[1]['text'] == f'1{NB}412'
    assert second[2]['text'] == {'type': 'marked', 'text': '89%'}
    assert total[0]['text'] == {'type': 'bold', 'text': 'Все бары'} and total[3]['text'] == NB, 'пустая — nbsp'


def test_table_without_rule_and_too_wide():
    [table] = rich.blocks_from_markdown('| a | 1 |\n| b | 2 |')
    assert not any(c.get('is_header') for row in table['cells'] for c in row)
    assert [c['align'] for c in table['cells'][0]] == ['left', 'right']
    wide = '| ' + ' | '.join(str(n) for n in range(rich.MAX_TABLE_COLS + 1)) + ' |'
    [block] = rich.blocks_from_markdown(wide)
    assert block['type'] == 'pre' and block['text'] == wide


# ------------------------------------------------------------------ сообщение

def test_message_how_footer_buttons_photo():
    md = '## Лид\nстрока\n\n*iiko · данные на 3 ноя, 09:12 МСК*\n*Ответ обошёлся в $0.42 (запросов к модели: 3).*'
    buttons = formatting.ask_buttons(['По дням'])
    message = rich.message(md, how='% плана = факт / план × 100.', button_rows=buttons, photo_name='chart')
    blocks = message['blocks']
    assert kinds(blocks) == ['heading', 'photo', 'paragraph', 'details', 'footer', 'footer', 'buttons']
    assert blocks[1] == {'type': 'photo', 'photo': {'type': 'photo', 'media': 'attach://chart'}}
    how = blocks[3]
    assert how['summary'] == rich.HOW_SUMMARY and not how.get('is_open')
    assert how['blocks'] == [{'type': 'paragraph', 'text': '% плана = факт / план × 100.'}]
    assert blocks[4]['text'] == 'iiko · данные на 3 ноя, 09:12 МСК'
    assert blocks[6] == {'type': 'buttons', 'buttons': [{'text': 'По дням', 'callback_data': 'ask:По дням'}]}
    # без заголовка картинка — первой
    assert kinds(rich.message('текст', photo_name='cover')['blocks']) == ['photo', 'paragraph']


def test_message_limits():
    with pytest.raises(rich.RichError):
        rich.message('')
    with pytest.raises(rich.RichError):
        rich.message('слово ' * (rich.MAX_CHARS // 5))
    with pytest.raises(rich.RichError):
        rich.message('\n'.join(f'- пункт {n}' for n in range(rich.MAX_BLOCKS)))
    assert rich.message('', how='только пояснение')['blocks'][0]['type'] == 'details'


def test_plain_text_reads_blocks_back():
    md = '## Лид\n\n| Бар | % |\n|---|---|\n| Лиговский | 104% |\n\n- пункт\n\n> цитата'
    text = rich.plain_text(rich.message(md, how='формула', button_rows=formatting.ask_buttons(['По дням']))['blocks'])
    assert text.split('\n') == ['Лид', 'Бар | %', 'Лиговский | 104%', '- пункт', '> цитата', 'Как считается',
                                '  формула', '[По дням]']


def test_draft_block():
    assert rich.draft('Думаю…', '0:12 · меньше минуты осталось') == {'blocks': [
        {'type': 'thinking', 'text': 'Думаю…'},
        {'type': 'paragraph', 'text': '0:12 · меньше минуты осталось'}]}


# ------------------------------------------------------------------ кнопки и маркер

def test_split_buttons():
    text, found = formatting.split_buttons('Ответ.\n\n[[По дням]] · [[По сотрудникам]] [[По дням]]\n[[Ещё]] [[Пятая]]')
    assert text == 'Ответ.' and found == ['По дням', 'По сотрудникам', 'Ещё']
    # «[[…]]» внутри строки текста — не кнопка
    assert formatting.split_buttons('нажмите [[тут]] потом') == ('нажмите [[тут]] потом', [])
    long_label = 'Очень длинная кнопка про выручку по всем барам'
    _, [label] = formatting.split_buttons(f'[[{long_label}]]')
    assert len(label) <= formatting.BUTTON_TEXT_MAX and long_label.startswith(label)


def test_ask_data_fits_callback_limit():
    data = formatting.ask_data('Ж' * 40)
    assert data.startswith(formatting.ASK_PREFIX) and len(data.encode('utf-8')) <= 64
    assert formatting.ask_data('По дням') == 'ask:По дням'


def test_button_markup_goes_below_existing_buttons():
    how = {'inline_keyboard': [[{'text': 'Как считается', 'url': 'https://t.me/x'}]]}
    markup = formatting.button_markup(['По дням'], how)
    assert markup['inline_keyboard'] == [[{'text': 'Как считается', 'url': 'https://t.me/x'}],
                                         [{'text': 'По дням', 'callback_data': 'ask:По дням'}]]
    assert formatting.button_markup([], None) is None
    assert how['inline_keyboard'] == [[{'text': 'Как считается', 'url': 'https://t.me/x'}]], 'исходное не меняется'


def test_mark_in_plain_view():
    assert formatting.to_html('==89%==') == '<b>89%</b>'
    assert formatting.plain('==89%== плана') == '89% плана'


# ------------------------------------------------------------------ примеры /rich

@pytest.mark.parametrize('sample, labels', [(rich_demo.WEEK, rich_demo.WEEK_BUTTONS),
                                            (rich_demo.PEOPLE, rich_demo.PEOPLE_BUTTONS)])
def test_demo_samples_build(sample, labels):
    visible, how = formatting.split_how(sample)
    message = rich.message(visible, how=how, button_rows=rich_demo.demo_buttons(labels))
    blocks = message['blocks']
    assert blocks[0]['type'] == 'paragraph' and 'условные' in rich.plain_text(blocks[0])
    assert 'heading' in kinds(blocks) and 'table' in kinds(blocks) and 'details' in kinds(blocks)
    assert kinds(blocks)[-2:] == ['footer', 'buttons']
    assert all(b['callback_data'].startswith(rich_demo.DEMO_PREFIX) for b in blocks[-1]['buttons'])
    assert all(label in rich_demo.DEMO_HINTS for label in labels)


def test_demo_chart_is_valid():
    from kultura_bot.charts import spec
    normalized = spec.normalize(rich_demo.CHART_SPEC)
    assert normalized['kind'] == 'periods' and len(normalized['categories']) == 7
    fact, plan = (s['data'] for s in normalized['series'])
    assert sum(fact) == 4_412_000 and sum(plan) == 4_497_000
    message = rich.message(rich_demo.CHART_CAPTION, how=rich_demo.CHART_HOW, photo_name='chart')
    assert kinds(message['blocks'])[:3] == ['paragraph', 'heading', 'photo'] or \
        kinds(message['blocks'])[:2] == ['photo', 'paragraph']

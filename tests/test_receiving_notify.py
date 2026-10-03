"""Тесты сообщения бухгалтерии о приёмке на РЦ (core/receiving_notify.py). Сети нет.

В Telegram ничего не уходит: отправитель и очередь досылки — фейки (send/queue),
токен бота и чаты — фиктивные, только в окружении теста (monkeypatch).
Что проверяется:
- текст: заголовок с номером, кто и когда закрыл, штуки и позиции, счёт по
  статусам (только ненулевые), порядок списка (статус, штуки в ЭТОЙ приёмке,
  название), название ЧЗ или GTIN, обрезка длинного названия, не больше
  MAX_LISTED позиций и строка «И ещё N», ссылка на разбор с фильтром приёмки;
  HTML экранирован, эмодзи и «•» нет, found в сообщение не попадает;
- пропуски с причиной и без отправки: RECEIVING_NOTIFY=0, нет токена, нет чатов,
  нет позиций new/similar/restore (одни дубли);
- отправка: чаты из RECEIVING_NOTIFY_CHAT_IDS без повторов, явные chats,
  недоставленное -> очередь досылки с датой и временем МСК; DRY-RUN — только
  первому чату, с пометкой, без очереди;
- транспорт по умолчанию: open_check_bot._send_with_retries и
  open_check_pending.add(target='receiving');
- фоновая отправка: поток-демон, сбой не роняет поток;
- грамматика Python 3.10.
"""
import os
import re
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import msk_time  # noqa: E402
from core import receiving_notify as rn  # noqa: E402

EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF☀-➿️]')
NOW = datetime(2026, 10, 3, 14, 7, tzinfo=msk_time.MOSCOW_TZ)

RECEIPT = {
    'id': 12, 'status': 'closed', 'note': '', 'created_at': '2026-10-03T13:00:00+03:00',
    'created_by': 'Иван', 'closed_at': '2026-10-03T14:05:00+03:00', 'closed_by': 'Иван',
    'process_state': 'running', 'processed_at': None, 'process_note': '',
    'counts': {'units': 340, 'gtins': 18, 'rejected': 2, 'repeats': 5, 'invoices': 1},
}


def _row(gtin, status, name='', qty=1, receipt_id=12, other=None, full_name=''):
    receipts = [{'id': receipt_id, 'qty': qty, 'closed_at': '2026-10-03T14:05:00+03:00'}]
    if other:
        receipts.append({'id': 3, 'qty': other, 'closed_at': '2026-10-01T10:00:00+03:00'})
    chz = {'name': name, 'brand': '', 'full_name': full_name, 'product_group': 'beer',
           'volume': '', 'package_type': '', 'source': 'cache'} if (name or full_name) else {}
    return {'gtin': gtin, 'barcode': gtin[1:], 'status': status, 'state': 'open', 'resolution': '',
            'cards': [], 'candidates': [], 'chz': chz, 'supplier': '', 'supplier_hint': '',
            'note': '', 'qty': qty + (other or 0), 'receipts': receipts}


class FakeSender:
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.calls = []

    def __call__(self, chats, text):
        self.calls.append((list(chats), text))
        failed = [c for c in chats if c in self.fail]
        return {'sent': len(chats) - len(failed), 'failed': failed}


class FakeQueue:
    def __init__(self):
        self.calls = []

    def __call__(self, date_str, text, chats, first_try):
        self.calls.append((date_str, text, list(chats), first_try))


@pytest.fixture
def env(monkeypatch):
    """Настроенный бот: токен, два чата, выключатель не тронут, не DRY-RUN; часы МСК."""
    monkeypatch.setenv('TELEGRAM_OPEN_CHECK_BOT_TOKEN', '123:test-token')
    monkeypatch.setenv(rn.ENV_CHATS, '111, 222')
    monkeypatch.delenv(rn.ENV_SWITCH, raising=False)
    monkeypatch.delenv('OPEN_CHECK_DRY_RUN', raising=False)
    monkeypatch.setattr(msk_time, 'now', lambda: NOW)
    return monkeypatch


# ----------------------------------------------------------------- текст

def test_message_header_counts_and_link():
    rows = [_row('04610093628430', 'new', 'Пиво FH Helles', qty=24),
            _row('04600000000017', 'restore', 'Сидр', qty=12),
            _row('04600000000024', 'similar', 'Эль', qty=6)]
    text = rn.format_receipt_message(RECEIPT, rows)
    lines = text.split('\n')
    assert lines[0] == '<b>Приёмка на РЦ №12: нужен разбор</b>'
    assert lines[1] == 'Закрыта: 3 октября 2026, 14:05, Иван'
    assert lines[2] == 'Принято: 340 шт., позиций: 18'
    assert lines[3] == 'К разбору: новых 1, похожих 1, восстановить 1'   # дублей 0 — не пишем
    assert lines[-1] == 'https://beerkultura.ru/receiving/review?receipt=12'
    assert '- Пиво FH Helles — новая, 24 шт.' in lines
    assert '- Эль — похожая карточка, 6 шт.' in lines
    assert '- Сидр — удалена или в архиве, 12 шт.' in lines


def test_message_order_status_then_qty_then_name():
    rows = [_row('04600000000031', 'duplicate', 'Б дубль', qty=50),
            _row('04600000000048', 'new', 'Я новая', qty=5),
            _row('04600000000055', 'new', 'А новая', qty=5),
            _row('04600000000062', 'new', 'Б новая', qty=30),
            _row('04600000000079', 'restore', 'В архиве', qty=100),
            _row('04600000000086', 'similar', 'Похожая', qty=1)]
    listed = [ln for ln in rn.format_receipt_message(RECEIPT, rows).split('\n') if ln.startswith('- ')]
    assert listed == ['- Б новая — новая, 30 шт.', '- А новая — новая, 5 шт.',
                      '- Я новая — новая, 5 шт.', '- Похожая — похожая карточка, 1 шт.',
                      '- В архиве — удалена или в архиве, 100 шт.',
                      '- Б дубль — дубль штрихкода, 50 шт.']
    assert 'К разбору: новых 3, похожих 1, восстановить 1, дублей 1' in rn.format_receipt_message(RECEIPT, rows)


def test_message_qty_of_this_receipt_and_fallbacks():
    rows = [_row('04600000000093', 'new', 'Портер', qty=7, other=100),     # 100 шт. — в приёмке №3
            _row('04600000000109', 'new', '', qty=3),                       # нет данных ЧЗ -> GTIN
            _row('04600000000116', 'new', '', qty=2, full_name='Полное имя ЧЗ')]
    rows.append({'gtin': '04600000000123', 'status': 'new', 'chz': None, 'qty': 4})  # без receipts
    text = rn.format_receipt_message(RECEIPT, rows)
    assert '- Портер — новая, 7 шт.' in text
    # Без названия ЧЗ похожие не искались — бухгалтеру пометка (ревью 2026-10-03).
    assert '- 04600000000109 — новая (нет названия ЧЗ, похожие не проверены), 3 шт.' in text
    assert '- Полное имя ЧЗ — новая, 2 шт.' in text
    assert '- 04600000000123 — новая (нет названия ЧЗ, похожие не проверены), 4 шт.' in text


def test_message_marks_group_pack():
    row = _row('04600000000154', 'similar', 'Пиво Хеллес 6 банок', qty=2)
    row['chz'].update(main_gtin='04600000000011', pack_units='6', level='inner-pack')
    text = rn.format_receipt_message(RECEIPT, [row])
    assert '- Пиво Хеллес 6 банок — похожая карточка (групповая упаковка по 6 шт.), 2 шт.' in text


def test_message_escapes_html_and_has_no_emoji():
    receipt = dict(RECEIPT, closed_by='Иван <b>&</b>')
    rows = [_row('04600000000130', 'new', 'Пиво <script>alert(1)</script> & «Ко»', qty=1),
            _row('04600000000147', 'similar', 'IPA \U0001F37A', qty=1)]
    text = rn.format_receipt_message(receipt, rows)
    assert '<script>' not in text and '&lt;script&gt;' in text
    assert 'Иван &lt;b&gt;&amp;&lt;/b&gt;' in text
    assert '&amp; «Ко»' in text
    # Разметка — только заголовок <b>...</b>
    tags = re.findall(r'<[^>]+>', text)
    assert tags == ['<b>', '</b>']
    # Шаблон без эмодзи и без «•» (эмодзи из данных ЧЗ — не наш текст, но шаблон чистый)
    template = rn.format_receipt_message(RECEIPT, [_row('04600000000154', 'new', 'Пиво', qty=1)])
    assert not EMOJI_RE.search(template)
    assert '•' not in template


def test_message_cuts_long_name_and_limits_list():
    long_name = 'Пиво ' + 'очень длинное название ' * 10
    rows = [_row('046000000%05d' % i, 'new', long_name if i == 0 else 'Позиция %02d' % i, qty=100 - i)
            for i in range(rn.MAX_LISTED + 3)]
    text = rn.format_receipt_message(RECEIPT, rows)
    listed = [ln for ln in text.split('\n') if ln.startswith('- ')]
    assert len(listed) == rn.MAX_LISTED
    first = listed[0]
    title = first[2:first.index(' — ')]
    assert len(title) == rn.NAME_LEN and title.endswith('…')
    assert 'И ещё 3 — на странице разбора.' in text
    assert 'К разбору: новых 13' in text
    assert len(text) < 4096


def test_message_skips_found_and_unknown_close_time():
    receipt = dict(RECEIPT, closed_at=None, closed_by='')
    rows = [_row('04600000000161', 'found', 'Есть в iiko', qty=9),
            _row('04600000000178', 'new', 'Новая', qty=1), 'мусор', None]
    text = rn.format_receipt_message(receipt, rows)
    assert 'Есть в iiko' not in text
    assert 'Закрыта' not in text
    assert 'К разбору: новых 1' in text


def test_fmt_when():
    assert rn._fmt_when('2026-01-05T09:03:00+03:00') == '5 января 2026, 09:03'
    assert rn._fmt_when('') == ''
    assert rn._fmt_when('вчера') == ''
    assert rn._fmt_when('2026-13-01T10:00:00+03:00') == ''


# ----------------------------------------------------------------- пропуски

def test_skip_when_switched_off(env):
    env.setenv(rn.ENV_SWITCH, '0')
    send, queue = FakeSender(), FakeQueue()
    res = rn.notify_receipt(RECEIPT, [_row('04600000000185', 'new', 'X')], send=send, queue=queue)
    assert res == {'sent': 0, 'failed': [], 'skipped': 'disabled'}
    assert send.calls == [] and queue.calls == []


def test_skip_without_token(env):
    env.setenv('TELEGRAM_OPEN_CHECK_BOT_TOKEN', '  ')
    send = FakeSender()
    res = rn.notify_receipt(RECEIPT, [_row('04600000000185', 'new', 'X')], send=send, queue=FakeQueue())
    assert res['skipped'] == 'no_token' and send.calls == []


def test_skip_without_chats(env):
    env.setenv(rn.ENV_CHATS, ' , ')
    send = FakeSender()
    res = rn.notify_receipt(RECEIPT, [_row('04600000000185', 'new', 'X')], send=send, queue=FakeQueue())
    assert res['skipped'] == 'no_recipients' and send.calls == []
    res = rn.notify_receipt(RECEIPT, [_row('04600000000185', 'new', 'X')], send=send, chats=[])
    assert res['skipped'] == 'no_recipients' and send.calls == []


def test_skip_when_only_duplicates_or_found(env):
    send = FakeSender()
    rows = [_row('04600000000192', 'duplicate', 'Дубль'), _row('04600000000208', 'found', 'Есть')]
    res = rn.notify_receipt(RECEIPT, rows, send=send, queue=FakeQueue())
    assert res['skipped'] == 'nothing_to_report' and send.calls == []
    assert rn.notify_receipt(RECEIPT, [], send=send)['skipped'] == 'nothing_to_report'


def test_switch_values_other_than_zero_send(env):
    for value in ('1', '', 'yes'):
        env.setenv(rn.ENV_SWITCH, value)
        send = FakeSender()
        res = rn.notify_receipt(RECEIPT, [_row('04600000000215', 'restore', 'X')], send=send,
                                queue=FakeQueue())
        assert res['skipped'] is None and res['sent'] == 2


# ----------------------------------------------------------------- отправка

def test_send_to_env_chats_and_queue_failures(env):
    env.setenv(rn.ENV_CHATS, '111, 222,111,, -100500')
    send, queue = FakeSender(fail={'222'}), FakeQueue()
    rows = [_row('04600000000222', 'new', 'Новая', qty=2), _row('04600000000239', 'duplicate', 'Д')]
    res = rn.notify_receipt(RECEIPT, rows, send=send, queue=queue)
    assert res == {'sent': 2, 'failed': ['222'], 'skipped': None}
    assert len(send.calls) == 1
    chats, text = send.calls[0]
    assert chats == ['111', '222', '-100500']
    assert text == rn.format_receipt_message(RECEIPT, rows)
    assert queue.calls == [('2026-10-03', text, ['222'], '14:07')]


def test_all_delivered_no_queue(env):
    send, queue = FakeSender(), FakeQueue()
    res = rn.notify_receipt(RECEIPT, [_row('04600000000246', 'similar', 'X')], send=send, queue=queue)
    assert res == {'sent': 2, 'failed': [], 'skipped': None}
    assert queue.calls == []


def test_explicit_chats_override_env(env):
    send = FakeSender()
    res = rn.notify_receipt(RECEIPT, [_row('04600000000253', 'new', 'X')], send=send,
                            queue=FakeQueue(), chats=['999'])
    assert res['sent'] == 1 and send.calls[0][0] == ['999']


def test_dry_run_first_chat_only_marked_and_not_queued(env):
    env.setenv('OPEN_CHECK_DRY_RUN', '1')
    send, queue = FakeSender(fail={'111'}), FakeQueue()
    res = rn.notify_receipt(RECEIPT, [_row('04600000000260', 'new', 'X')], send=send, queue=queue)
    assert res == {'sent': 0, 'failed': ['111'], 'skipped': None}
    chats, text = send.calls[0]
    assert chats == ['111']
    assert text.startswith('[DRY-RUN] <b>Приёмка на РЦ №12')
    assert queue.calls == []


def test_send_result_garbage_is_tolerated(env):
    res = rn.notify_receipt(RECEIPT, [_row('04600000000277', 'new', 'X')],
                            send=lambda chats, text: None, queue=FakeQueue())
    assert res == {'sent': 0, 'failed': [], 'skipped': None}


def test_recipients_from_env(monkeypatch):
    monkeypatch.setenv(rn.ENV_CHATS, ' 1, 2,,1 , -100 ')
    assert rn.recipients() == ['1', '2', '-100']
    monkeypatch.setenv(rn.ENV_CHATS, '')
    assert rn.recipients() == []


def test_default_transport_and_queue(env):
    from core import open_check_bot, open_check_pending
    sent, queued = [], []

    def fake_send(recipients, text, *args, **kwargs):
        sent.append((list(recipients), text))
        return {'sent': 1, 'failed': ['222']}

    def fake_add(date_str, text, chats, target, first_try):
        queued.append((date_str, chats, target, first_try))

    env.setattr(open_check_bot, '_send_with_retries', fake_send)
    env.setattr(open_check_pending, 'add', fake_add)
    res = rn.notify_receipt(RECEIPT, [_row('04600000000284', 'new', 'X')])
    assert res == {'sent': 1, 'failed': ['222'], 'skipped': None}
    assert sent[0][0] == ['111', '222']
    assert queued == [('2026-10-03', ['222'], 'receiving', '14:07')]


# ----------------------------------------------------------------- фон

def test_notify_in_background_runs_daemon_thread(monkeypatch):
    calls = []
    monkeypatch.setattr(rn, 'notify_receipt', lambda receipt, rows: calls.append((receipt, rows)) or {})
    rows = [_row('04600000000291', 'new', 'X')]
    thread = rn.notify_receipt_in_background(RECEIPT, rows)
    thread.join(5)
    assert not thread.is_alive()
    assert thread.daemon and thread.name == 'receiving-notify-12'
    assert calls == [(RECEIPT, rows)]


def test_notify_in_background_survives_errors(monkeypatch):
    def boom(receipt, rows):
        raise RuntimeError('telegram down')

    monkeypatch.setattr(rn, 'notify_receipt', boom)
    thread = rn.notify_receipt_in_background(RECEIPT, [])
    thread.join(5)
    assert not thread.is_alive()


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль должен разбираться грамматикой 3.10."""
    import ast
    src = open(rn.__file__, encoding='utf-8').read()
    ast.parse(src, feature_version=(3, 10))
    assert not EMOJI_RE.search(src)
    assert '•' not in src


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))

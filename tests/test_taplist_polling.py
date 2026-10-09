"""Очередь и разбор команд таплист-бота, подписка гостей и отзывы через бота. Сети нет.

Первые тесты — краны (как раньше, без изменений). Дальше:
- план диалога (чистая plan_update): подписка, выбор баров, телефон, отписка, отзыв,
  таймаут диалога, my_chat_member, только личный чат, битые кнопки;
- исполнение (handle_update) с поддельным Telegram (FakeApi), временной базой
  подписчиков, временной витриной гостей и временным файлом отзывов: что уходит гостю
  (тексты, кнопки, без parse_mode), что пишется в базу и в отзывы, лимит отзывов,
  сбои хранилищ, уведомление владельцу (core/review_notify) видит отзыв из бота.
Настоящий api_call и requests.post подменены на «упасть при вызове» — сеть исключена.
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import msk_time
from core import taplist_polling as tp
from core.guest_reviews import ReviewStore
from core.guest_store import GuestStore
from core.guest_subscribers import CONSENT_TEXT, CONSENT_VERSION, SubscriberStore
from core.taplist_polling import WebhookConflict, consume_batch, plan_update


def test_empty_and_error_keep_offset():
    assert consume_batch(None, 7, lambda upd: None) == 7
    assert consume_batch({'ok': False, 'error_code': 500}, 7, lambda upd: None) == 7
    assert consume_batch({'ok': True, 'result': []}, None, lambda upd: None) is None


def test_offset_moves_past_every_update():
    seen = []
    offset = consume_batch(
        {'ok': True, 'result': [{'update_id': 4, 'message': {}}, {'update_id': 5}]},
        None,
        seen.append,
    )
    assert offset == 6
    assert [item['update_id'] for item in seen] == [4, 5]


def test_bad_update_does_not_stall_the_queue():
    seen = []
    errors = []

    def feed(upd):
        seen.append(upd['update_id'])
        if upd['update_id'] == 1:
            raise RuntimeError('boom')

    offset = consume_batch(
        {'ok': True, 'result': [{'update_id': 1}, {'update_id': 2}]},
        0,
        feed,
        errors.append,
    )
    assert offset == 3
    assert seen == [1, 2]
    assert len(errors) == 1


def test_webhook_conflict_does_not_move_offset():
    with pytest.raises(WebhookConflict):
        consume_batch({'ok': False, 'error_code': 409, 'description': 'conflict'}, 3, lambda upd: None)


def test_start_and_button_plan_without_network():
    assert plan_update({'message': {'chat': {'id': 5}, 'text': '/start@kult_taplist_bot'}}) == [
        {'op': 'menu', 'chat_id': 5},
    ]
    assert plan_update({'message': {'chat': {'id': 5}, 'text': '/taplist2'}}) == [
        {'op': 'taplist', 'chat_id': 5, 'bar_id': 'bar2'},
    ]
    assert plan_update({
        'callback_query': {
            'id': 'cb',
            'data': 'taplist_all',
            'message': {'chat': {'id': 5}},
        },
    }) == [
        {'op': 'ack', 'callback_id': 'cb'},
        {'op': 'taplist', 'chat_id': 5, 'bar_id': None},
    ]
    assert plan_update({'message': {'chat': {'id': 5}, 'text': 'привет'}}) == []


# ================================================================= подписка и отзывы

MSK = msk_time.MOSCOW_TZ
CHAT = 555                       # личный чат = id пользователя
ANNA = {'id': CHAT, 'first_name': 'Анна', 'last_name': 'Петрова', 'username': 'anna_p'}
USER = {'user_id': CHAT, 'username': 'anna_p', 'first_name': 'Анна', 'last_name': 'Петрова'}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Ни одного настоящего вызова Telegram: боевой api_call, отправитель бота владельца и
    requests.post падают, фоновое уведомление об отзыве не запускается.

    Почему так строго: импорт любого routes.* (его делает tests/test_guest_reviews.py при
    сборе тестов) загружает .env с боевыми токенами в окружение всего процесса pytest.
    Фоновый поток, переживший тест, иначе мог бы уйти в настоящий Telegram после того,
    как подмены теста уже сняты."""
    import requests
    import core.open_check_bot as ocb_mod
    import core.open_check_telegram as oct_mod
    import core.review_notify as rn_mod

    def boom(*args, **kwargs):
        raise AssertionError('real network call in a test')
    monkeypatch.setattr(oct_mod, 'api_call', boom)
    monkeypatch.setattr(ocb_mod, '_send_with_retries', boom)
    monkeypatch.setattr(rn_mod, 'notify_review_in_background', lambda review_id: None)
    monkeypatch.setattr(requests, 'post', boom)
    monkeypatch.setattr(requests.Session, 'post', boom)


def pm(text=None, message_id=10, contact=None, date=None, chat_type='private', chat_id=CHAT, sender=None):
    msg = {'message_id': message_id, 'chat': {'id': chat_id, 'type': chat_type}, 'from': sender or ANNA}
    if text is not None:
        msg['text'] = text
    if contact is not None:
        msg['contact'] = contact
    if date is not None:
        msg['date'] = date
    return {'message': msg}


def cb(data, message_id=20, chat_type='private', chat_id=CHAT, cb_id='q'):
    return {'callback_query': {'id': cb_id, 'data': data, 'from': ANNA,
                               'message': {'message_id': message_id, 'chat': {'id': chat_id, 'type': chat_type}}}}


ACK = {'op': 'ack', 'callback_id': 'q'}
AGREE = 'sub_agree:' + CONSENT_VERSION        # «Согласен» под текущим текстом согласия


def say(text, chat_id=CHAT):
    return {'op': 'say', 'chat_id': chat_id, 'text': text}


# ----------------------------------------------------------------- план

def test_taplist_plans_unchanged_in_private_chat():
    assert plan_update(pm('/start')) == [{'op': 'menu', 'chat_id': CHAT}]
    assert plan_update(pm('/taplist3')) == [{'op': 'taplist', 'chat_id': CHAT, 'bar_id': 'bar3'}]
    assert plan_update(cb('taplist_bar1')) == [ACK, {'op': 'taplist', 'chat_id': CHAT, 'bar_id': 'bar1'}]
    assert plan_update(pm('привет')) == [say(tp.TEXT_HINT)]          # подсказка, а не молчание
    assert plan_update(pm('привет'), signup=False) == [say(tp.TEXT_HINT_CLOSED)]
    assert plan_update(pm('/whatever')) == [{'op': 'menu', 'chat_id': CHAT}]


def test_guest_actions_only_in_private_chat():
    group = -100500
    assert plan_update(cb('sub_start', chat_type='group', chat_id=group)) == [ACK, say(tp.TEXT_PRIVATE_ONLY, group)]
    assert plan_update(cb('rv:b:1', chat_type='supergroup', chat_id=group)) == [ACK, say(tp.TEXT_PRIVATE_ONLY, group)]
    assert plan_update(pm('/subscribe', chat_type='group', chat_id=group)) == [say(tp.TEXT_PRIVATE_ONLY, group)]
    assert plan_update(pm('/stop@kult_taplist_bot', chat_type='group', chat_id=group)) == [
        say(tp.TEXT_PRIVATE_ONLY, group)]
    assert plan_update(pm('/start subscribe', chat_type='group', chat_id=group)) == [{'op': 'menu', 'chat_id': group}]
    assert plan_update(pm(contact={'phone_number': '79991234567', 'user_id': CHAT}, chat_type='group',
                          chat_id=group)) == []
    assert tp.menu_keyboard(True, guest_buttons=False) == tp.bar_keyboard()


def test_subscription_plan():
    assert plan_update(cb('sub_start')) == [ACK, {'op': 'sub_offer', 'chat_id': CHAT}]
    assert plan_update(pm('/subscribe')) == [{'op': 'sub_offer', 'chat_id': CHAT}]
    assert plan_update(pm('/start subscribe')) == [{'op': 'sub_offer', 'chat_id': CHAT}]
    assert plan_update(cb(AGREE)) == [ACK, {'op': 'sub_agree', 'chat_id': CHAT, 'user': USER,
                                             'version': CONSENT_VERSION}]
    assert plan_update(cb('sub_later')) == [ACK, say(tp.TEXT_SUB_LATER)]
    assert plan_update(cb('sb:0:1', message_id=3)) == [
        ACK, {'op': 'sub_bars', 'chat_id': CHAT, 'message_id': 3, 'bars': ['ligovskiy']}]
    assert plan_update(cb('sb:2:1', message_id=3)) == [
        ACK, {'op': 'sub_bars', 'chat_id': CHAT, 'message_id': 3, 'bars': []}]
    assert plan_update(cb('sb:2:a', message_id=3)) == [
        ACK, {'op': 'sub_bars', 'chat_id': CHAT, 'message_id': 3, 'bars': []}]
    assert plan_update(cb('sb:0:a')) == [ACK]                        # уже «Все бары» — нечего перерисовывать
    assert plan_update(cb('sb:10:ok', message_id=3)) == [
        ACK, {'op': 'sub_bars_done', 'chat_id': CHAT, 'message_id': 3, 'bars': ['ligovskiy', 'varshavskaya']}]
    assert plan_update(cb('sub_stop')) == [ACK, {'op': 'unsubscribe', 'chat_id': CHAT}]
    assert plan_update(pm('/stop')) == [{'op': 'unsubscribe', 'chat_id': CHAT}]
    assert plan_update(pm('/unsubscribe')) == [{'op': 'unsubscribe', 'chat_id': CHAT}]


def test_malformed_buttons_only_ack():
    for data in ('sb:99:1', 'sb:0:7', 'sb:x:ok', 'sb:0', 'sb:1:2:3', 'sb:٣:ok', 'sb: 2:ok', 'sb:-1:ok',
                 'rv:r:0:9', 'rv:r:0:0', 'rv:b:4',
                 'rv:b:-1', 'rv:zz', 'rv:r:1', 'rv:s:\u0663:4', 'sub_nope'):
        assert plan_update(cb(data)) == [ACK], data


def test_phone_step_plan():
    dialog = {'flow': 'sub_phone'}
    own = {'phone_number': '79991234567', 'user_id': CHAT, 'first_name': 'Анна'}
    assert plan_update(pm(contact=own), dialog) == [{'op': 'sub_phone', 'chat_id': CHAT, 'phone': '79991234567'}]
    assert plan_update(pm(contact=own)) == [{'op': 'sub_phone', 'chat_id': CHAT, 'phone': '79991234567'}]
    assert plan_update(pm(contact=dict(own, user_id=777)), dialog) == [say(tp.TEXT_SUB_PHONE_NOT_OWN)]
    assert plan_update(pm(contact={'phone_number': '79991234567'}), dialog) == [say(tp.TEXT_SUB_PHONE_NOT_OWN)]
    assert plan_update(pm('Пропустить'), dialog) == [{'op': 'sub_phone_skip', 'chat_id': CHAT}]
    assert plan_update(pm('+7 999 123 45 67'), dialog) == [say(tp.TEXT_SUB_PHONE_HINT)]
    assert plan_update(pm('/start'), dialog) == [{'op': 'sub_phone_skip', 'chat_id': CHAT},
                                                 {'op': 'dialog_clear', 'chat_id': CHAT},
                                                 {'op': 'menu', 'chat_id': CHAT}]
    assert plan_update(pm('/stop'), dialog) == [{'op': 'dialog_clear', 'chat_id': CHAT},
                                                {'op': 'unsubscribe', 'chat_id': CHAT}]
    assert plan_update(pm('Пропустить')) == [say(tp.TEXT_HINT)]       # без диалога — подсказка
    expired = {'flow': 'sub_phone', 'expired': True}                  # «Пропустить» после таймаута
    assert plan_update(pm('Пропустить'), expired) == [{'op': 'sub_phone_skip', 'chat_id': CHAT}]
    assert plan_update(pm('что-то'), expired) == [say(tp.TEXT_HINT)]


def test_review_plan():
    assert plan_update(cb('rev_start')) == [ACK, {'op': 'rev_start', 'chat_id': CHAT}]
    assert plan_update(pm('/review')) == [{'op': 'rev_start', 'chat_id': CHAT}]
    assert plan_update(pm('/start review')) == [{'op': 'rev_start', 'chat_id': CHAT}]
    assert plan_update(pm('/start review_varshavskaya')) == [
        {'op': 'rev_bar', 'chat_id': CHAT, 'message_id': None, 'bar': 'varshavskaya'}]
    assert plan_update(pm('/start review_nowhere')) == [{'op': 'menu', 'chat_id': CHAT}]
    assert plan_update(cb('rv:b:1', message_id=30)) == [
        ACK, {'op': 'rev_bar', 'chat_id': CHAT, 'message_id': 30, 'bar': 'ligovskiy'}]
    state = {'flow': 'review_text', 'bar': 'ligovskiy', 'rating': 4, 'prompt_message_id': 30}
    assert plan_update(cb('rv:r:1:4', message_id=30)) == [
        ACK, {'op': 'rev_rating', 'chat_id': CHAT, 'message_id': 30, 'bar': 'ligovskiy', 'rating': 4},
        {'op': 'dialog_set', 'chat_id': CHAT, 'state': state}]
    text = pm('Отличное пиво <b>', message_id=31, date=1790000000)
    assert plan_update(text, state) == [
        {'op': 'rev_save', 'chat_id': CHAT, 'message_id': 31, 'prompt_message_id': 30, 'bar': 'ligovskiy',
         'rating': 4, 'text': 'Отличное пиво <b>', 'date': 1790000000, 'user': USER},
        {'op': 'dialog_clear', 'chat_id': CHAT}]
    assert plan_update(pm(None, message_id=32), state) == [say(tp.TEXT_REV_TEXT_ONLY)]   # стикер, фото
    assert plan_update(cb('rv:s:1:4', message_id=30), state) == [
        ACK, {'op': 'rev_save', 'chat_id': CHAT, 'message_id': 30, 'prompt_message_id': 30, 'bar': 'ligovskiy',
              'rating': 4, 'text': '', 'date': None, 'user': USER},
        {'op': 'dialog_clear', 'chat_id': CHAT}]
    assert plan_update(cb('rv:s:1:4', message_id=29), state) == [ACK, say(tp.TEXT_REV_STALE)]
    assert plan_update(cb('rv:s:1:4', message_id=30)) == [ACK, say(tp.TEXT_REV_STALE)]
    assert plan_update(cb('rv:x', message_id=30), state) == [
        ACK, {'op': 'dialog_clear', 'chat_id': CHAT}, {'op': 'rev_cancel', 'chat_id': CHAT, 'message_id': 30}]
    assert plan_update(pm('/start'), state) == [{'op': 'dialog_clear', 'chat_id': CHAT},
                                                {'op': 'menu', 'chat_id': CHAT}]
    expired = dict(state, expired=True)
    assert plan_update(pm('Поздний отзыв'), expired) == [
        say(tp.TEXT_REV_EXPIRED.format(duration='30 минут'))]
    assert plan_update(cb('rv:s:1:4', message_id=30), expired) == [ACK, say(tp.TEXT_REV_STALE)]
    assert plan_update(pm('привет')) == [say(tp.TEXT_HINT)]


def test_member_updates():
    def upd(status, chat_type='private'):
        return {'my_chat_member': {'chat': {'id': CHAT, 'type': chat_type},
                                   'new_chat_member': {'status': status}}}
    assert plan_update(upd('kicked')) == [{'op': 'blocked', 'chat_id': CHAT}]
    assert plan_update(upd('member')) == [{'op': 'unblocked', 'chat_id': CHAT}]
    assert plan_update(upd('kicked', 'group')) == [] and plan_update(upd('left')) == []
    assert tp.update_chat_id(upd('kicked')) == CHAT and tp.update_chat_id(cb('x')) == CHAT
    assert tp.update_chat_id(pm('x')) == CHAT and tp.update_chat_id({}) is None


def test_dialog_store_timeout_and_forget():
    t0 = datetime(2026, 9, 28, 12, 0, tzinfo=MSK)
    ds = tp.DialogStore()
    ds.set(1, {'flow': 'review_text'}, t0)
    assert ds.get(1, t0 + timedelta(minutes=30)) == {'flow': 'review_text'}
    assert ds.get(1, t0 + timedelta(minutes=31)) == {'flow': 'review_text', 'expired': True}
    assert ds.get(1, t0 + timedelta(minutes=32)) is None               # «время вышло» — один раз
    ds.set(2, {'flow': 'sub_phone'}, t0)
    assert ds.get(2, t0 + timedelta(hours=25)) is None                 # старше суток — забыт молча
    ds.set(3, {'flow': 'sub_phone'}, t0)
    ds.clear(3)
    assert ds.get(3, t0) is None


def test_keyboards_and_commands():
    kb = tp.bars_select_keyboard([])['inline_keyboard']
    assert kb[0] == [{'text': 'Большой пр. В.О', 'callback_data': 'sb:0:0'}]
    assert kb[4] == [{'text': '✓ Все бары', 'callback_data': 'sb:0:a'}]
    assert kb[5] == [{'text': 'Готово', 'callback_data': 'sb:0:ok'}]
    kb = tp.bars_select_keyboard(['ligovskiy'])['inline_keyboard']
    assert kb[1] == [{'text': '✓ Лиговский', 'callback_data': 'sb:2:1'}] and kb[4][0]['text'] == 'Все бары'
    assert tp.bars_select_keyboard(['?'])['inline_keyboard'][4][0]['text'] == '✓ Все бары'
    phone = tp.phone_keyboard()
    assert phone['keyboard'][0][0] == {'text': 'Поделиться телефоном', 'request_contact': True}
    assert phone['one_time_keyboard'] is True
    menu = [b['callback_data'] for row in tp.menu_keyboard(False)['inline_keyboard'] for b in row]
    assert menu[:5] == ['taplist_bar1', 'taplist_bar2', 'taplist_bar3', 'taplist_bar4', 'taplist_all']
    assert menu[5:] == ['sub_start', 'rev_start']
    assert [b['callback_data'] for row in tp.menu_keyboard(True)['inline_keyboard'] for b in row][5] == 'sub_stop'
    everything = [tp.bars_select_keyboard(['bolshoy', 'varshavskaya']), tp.review_bar_keyboard(),
                  tp.rating_keyboard(3), tp.review_text_keyboard(3, 5), tp.consent_keyboard(), tp.menu_keyboard()]
    for keyboard in everything:
        for row in keyboard['inline_keyboard']:
            for button in row:
                assert len(button['callback_data'].encode('utf-8')) <= 64
    names = [c['command'] for c in tp._COMMANDS]
    assert {'subscribe', 'review', 'stop'} <= set(names) and names[:7] == [
        'start', 'taplist', 'taplist1', 'taplist2', 'taplist3', 'taplist4', 'taplistall']
    assert 'my_chat_member' in tp.ALLOWED_UPDATES
    assert tp._plural(1, 'а', 'б', 'в') == 'а' and tp._plural(3, 'а', 'б', 'в') == 'б'
    assert tp._plural(11, 'а', 'б', 'в') == 'в' and tp._plural(22, 'а', 'б', 'в') == 'б'


def test_all_guest_texts_plain():
    texts = [v for k, v in vars(tp).items() if k.startswith(('TEXT_', 'BTN_'))] + [CONSENT_TEXT]
    for text in texts:
        assert not any(ord(ch) > 0xFFFF for ch in text), text             # без эмодзи
        assert '<' not in text, text                                      # без HTML-разметки


# ----------------------------------------------------------------- исполнение

class FakeApi:
    """Поддельный Telegram: запоминает вызовы, sendMessage отдаёт новый message_id."""

    def __init__(self):
        self.calls = []
        self._next = 1000

    def __call__(self, method, payload):
        self.calls.append((method, json.loads(json.dumps(payload))))
        if method == 'sendMessage':
            self._next += 1
            return {'ok': True, 'result': {'message_id': self._next}}
        return {'ok': True, 'result': True}

    def last(self, method=None):
        return [p for m, p in self.calls if method is None or m == method][-1]


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def _guests_db(folder, guests=()):
    path = os.path.join(str(folder), 'guests.db')
    GuestStore(path)
    conn = sqlite3.connect(path)
    conn.executemany("INSERT INTO guests (guest_id, phone, last_visit_date, updated_at) VALUES (?, ?, ?, 'x')",
                     list(guests))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def bot(tmp_path):
    """Бот на подделках: Telegram — FakeApi, базы — временные, запись гостей включена
    (switch.on), уведомления владельцу — в список notified (настоящий фоновый поток
    не запускается)."""
    clock = Clock(datetime(2026, 9, 28, 12, 0, tzinfo=MSK))
    guests = _guests_db(tmp_path, [('79991234567', '79991234567', '2026-09-20')])
    subs = SubscriberStore(str(tmp_path / 'subs.db'), guests_db_path=guests, clock=clock)
    reviews = ReviewStore(str(tmp_path / 'reviews.json'), clock=clock)
    api = FakeApi()
    switch = SimpleNamespace(on=True)
    notified = []
    ctx = tp.BotContext('fake-token', api=api, subs=subs, reviews=reviews, dialogs=tp.DialogStore(), clock=clock,
                        signup=lambda: switch.on, notify=notified.append)
    return SimpleNamespace(ctx=ctx, api=api, subs=subs, reviews=reviews, clock=clock, switch=switch,
                           notified=notified, run=lambda upd: tp.handle_update(upd, ctx))


def _buttons(payload):
    markup = payload.get('reply_markup') or {}
    return [b for row in markup.get('inline_keyboard', []) for b in row]


def test_subscription_flow_end_to_end(bot):
    bot.run(pm('/start'))
    menu = bot.api.last('sendMessage')
    assert menu['text'] == 'Нажми бар:' and [b['text'] for b in _buttons(menu)][5:] == [
        'Подписаться на новости', 'Оставить отзыв']
    bot.run(cb('sub_start', message_id=1))
    assert bot.api.calls[-2] == ('answerCallbackQuery', {'callback_query_id': 'q'})
    consent = bot.api.last('sendMessage')
    assert consent['text'] == CONSENT_TEXT and [b['callback_data'] for b in _buttons(consent)] == [
        AGREE, 'sub_later']
    assert bot.subs.get(CHAT) is None                                    # до «Согласен» — ничего не пишем
    bot.run(cb(AGREE, message_id=2))
    row = bot.subs.get(CHAT)
    assert row['subscribed'] and row['consent_at'] == '2026-09-28T12:00:00' and row['username'] == 'anna_p'
    prompt = bot.api.last('sendMessage')
    assert prompt['text'] == tp.TEXT_SUB_BARS and _buttons(prompt)[4]['text'] == '✓ Все бары'
    bot.run(cb('sb:0:1', message_id=3))
    bot.run(cb('sb:2:3', message_id=3))
    marks = [b['text'] for b in _buttons(bot.api.last('editMessageReplyMarkup'))]
    assert marks[:5] == ['Большой пр. В.О', '✓ Лиговский', 'Кременчугская', '✓ Варшавская', 'Все бары']
    assert bot.subs.get(CHAT)['bars'] == []                             # сохраняется только по «Готово»
    bot.run(cb('sb:10:ok', message_id=3))
    assert bot.subs.get(CHAT)['bars'] == ['ligovskiy', 'varshavskaya']
    saved = bot.api.last('editMessageText')
    assert saved == {'chat_id': CHAT, 'message_id': 3, 'text': 'Бары для новостей: Лиговский, Варшавская.',
                     'disable_web_page_preview': True}                   # кнопки выбора убраны
    ask = bot.api.last('sendMessage')
    assert ask['text'] == tp.TEXT_SUB_PHONE and ask['reply_markup']['keyboard'][0][0]['request_contact'] is True
    bot.run(pm(contact={'phone_number': '+7 999 123-45-67', 'user_id': CHAT, 'first_name': 'Анна'}))
    row = bot.subs.get(CHAT)
    assert row['phone'] == '79991234567' and row['guest_id'] == '79991234567'
    done = bot.api.last('sendMessage')
    assert done['reply_markup'] == {'remove_keyboard': True}
    assert done['text'] == 'Телефон сохранён.\n\n' + tp.TEXT_SUB_DONE.format(bars='Лиговский, Варшавская')
    bot.run(pm('/start'))
    assert [b['text'] for b in _buttons(bot.api.last('sendMessage'))][5] == 'Отписаться от новостей'
    assert not any('parse_mode' in p for _, p in bot.api.calls)          # тексты гостю — без разметки


def test_skip_phone_then_stop(bot):
    bot.run(cb(AGREE, message_id=2))
    bot.run(cb('sb:0:ok', message_id=3))
    bot.run(pm('Пропустить'))
    done = bot.api.last('sendMessage')
    assert done['text'] == tp.TEXT_SUB_DONE.format(bars='все бары') and done['reply_markup'] == {'remove_keyboard': True}
    assert bot.subs.get(CHAT)['phone'] is None and bot.ctx.dialogs.get(CHAT, bot.clock()) is None
    bot.subs.set_phone(CHAT, '79991234567')
    bot.run(pm('/stop'))
    row = bot.subs.get(CHAT)
    assert not row['subscribed'] and row['phone'] is None and row['guest_id'] is None
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_UNSUB_DONE
    bot.run(cb('sub_stop'))
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_UNSUB_NOT


def test_command_during_phone_step_closes_subscription(bot):
    bot.run(cb(AGREE, message_id=2))
    bot.run(cb('sb:0:ok', message_id=3))
    n = len(bot.api.calls)
    bot.run(pm('/start'))
    sent = [p for m, p in bot.api.calls[n:] if m == 'sendMessage']
    assert sent[0]['text'] == tp.TEXT_SUB_DONE.format(bars='все бары')
    assert sent[0]['reply_markup'] == {'remove_keyboard': True} and sent[1]['text'] == 'Нажми бар:'


def test_phone_without_subscription_not_stored(bot):
    bot.run(pm(contact={'phone_number': '79991234567', 'user_id': CHAT}))
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_SUB_PHONE_NO_SUB
    assert bot.subs.get(CHAT) is None


def test_subscribed_guest_can_change_bars(bot):
    bot.subs.subscribe(CHAT, first_name='Анна')
    bot.subs.set_bars(CHAT, ['bolshoy'])
    bot.run(pm('/subscribe'))
    offer = bot.api.last('sendMessage')
    assert offer['text'] == tp.TEXT_SUB_ALREADY.format(bars='Большой пр. В.О')
    assert _buttons(offer)[0] == {'text': '✓ Большой пр. В.О', 'callback_data': 'sb:1:0'}


def test_review_with_text_end_to_end(bot):
    bot.run(cb('rev_start', message_id=40))
    ask_bar = bot.api.last('sendMessage')
    assert ask_bar['text'] == tp.TEXT_REV_BAR and len(_buttons(ask_bar)) == 5
    bot.run(cb('rv:b:1', message_id=41))
    rating = bot.api.last('editMessageText')
    assert rating['text'] == 'Лиговский: оцените визит от 1 до 5, где 5 — отлично.'
    assert [b['text'] for b in _buttons(rating)] == ['1', '2', '3', '4', '5', 'Отмена']
    bot.run(cb('rv:r:1:2', message_id=41))
    assert bot.api.last('editMessageText')['text'] == tp.TEXT_REV_TEXT.format(bar='Лиговский', rating=2)
    sent_at = int(datetime(2026, 9, 28, 11, 58, 30, tzinfo=MSK).timestamp())
    bot.run(pm('Долго ждали <b>пиво</b> & шумно', message_id=42, date=sent_at))
    [review] = bot.reviews.all()
    assert review['source'] == 'bot' and review['origin'] == 'import' and review['external_id'] == 'tg:555:42'
    assert review['bar'] == 'ligovskiy' and review['rating'] == 2 and review['status'] == 'new'
    assert review['text'] == 'Долго ждали <b>пиво</b> & шумно'           # текст гостя — как есть (данные)
    assert review['created_at'] == '2026-09-28T11:58' and review['author'] == 'Анна Петрова'
    assert review['guest'] == {'phone': '', 'telegram': '@anna_p'} and review['added_by'] == tp.REVIEW_ADDED_BY
    assert bot.api.calls[-2] == ('editMessageText', {'chat_id': CHAT, 'message_id': 41,
                                                     'text': 'Лиговский, оценка 2 из 5.',
                                                     'disable_web_page_preview': True})
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_REV_THANKS
    bot.run(cb('rv:s:1:2', message_id=41))                               # старая кнопка — второго отзыва нет
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_REV_STALE and len(bot.reviews.all()) == 1
    bot.run(pm('И ещё одно'))                                            # диалог закрыт — просто текст
    assert len(bot.reviews.all()) == 1
    assert not any('parse_mode' in p for _, p in bot.api.calls)


def test_rating_only_review_with_subscriber_phone(bot):
    bot.subs.subscribe(CHAT, first_name='Анна')
    bot.subs.set_phone(CHAT, '89991234567')
    bot.run(cb('rv:b:0', message_id=50))
    bot.run(cb('rv:r:0:5', message_id=50))
    bot.run(cb('rv:s:0:5', message_id=50))
    [review] = bot.reviews.all()
    assert review['text'] == '' and review['rating'] == 5 and review['external_id'] == 'tg:555:50'
    assert review['guest'] == {'phone': '+79991234567', 'telegram': '@anna_p'}
    assert review['created_at'] == '2026-09-28T12:00'
    assert bot.api.last('editMessageText')['text'] == 'Большой пр. В.О, оценка 5 из 5.\n\n' + tp.TEXT_REV_THANKS


def test_review_deep_link_and_cancel(bot):
    bot.run(pm('/start review_kremenchugskaya'))
    first = bot.api.last('sendMessage')
    assert first['text'].startswith('Кременчугская: оцените визит')
    bot.run(cb('rv:x', message_id=60))
    assert bot.api.last('editMessageText')['text'] == tp.TEXT_REV_CANCELLED and bot.reviews.all() == []


def _save(bot, message_id, text='Хорошо'):
    tp._execute([{'op': 'rev_save', 'chat_id': CHAT, 'message_id': message_id, 'prompt_message_id': message_id - 1,
                  'bar': 'bolshoy', 'rating': 4, 'text': text, 'date': None, 'user': USER}],
                'fake-token', None, bot.ctx)


def test_duplicate_review_is_idempotent(bot):
    _save(bot, 61)
    _save(bot, 61)
    assert len(bot.reviews.all()) == 1 and bot.api.last('sendMessage')['text'] == tp.TEXT_REV_DUPLICATE


def test_daily_review_limit(bot):
    for i in range(tp.REVIEW_DAILY_LIMIT):
        _save(bot, 70 + i * 2)
    assert len(bot.reviews.all()) == 3
    limit = tp.TEXT_REV_LIMIT.format(count='3 отзыва')
    bot.run(cb('rev_start', message_id=80))
    assert bot.api.last('sendMessage')['text'] == limit
    bot.run(pm('/start review_bolshoy'))
    assert bot.api.last('sendMessage')['text'] == limit
    _save(bot, 90)
    assert len(bot.reviews.all()) == 3 and bot.api.last('sendMessage')['text'] == limit
    bot.clock.value += timedelta(days=1)
    bot.run(cb('rev_start', message_id=91))
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_REV_BAR


def test_broken_review_file_is_not_overwritten(bot):
    with open(bot.reviews.data_file, 'w', encoding='utf-8') as f:
        f.write('{broken')
    _save(bot, 95)
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_REV_FAILED
    with open(bot.reviews.data_file, encoding='utf-8') as f:
        assert f.read() == '{broken'


def test_block_unblock_and_touch(bot):
    bot.subs.subscribe(CHAT, first_name='Анна')
    member = {'my_chat_member': {'chat': {'id': CHAT, 'type': 'private'}, 'new_chat_member': {'status': 'kicked'}}}
    bot.run(member)
    assert bot.subs.get(CHAT)['blocked_at'] == '2026-09-28T12:00:00' and bot.api.calls == []
    bot.run(pm('/start'))                                                # написал снова — доступен
    assert bot.subs.get(CHAT)['blocked_at'] is None
    bot.subs.mark_blocked(CHAT)
    member['my_chat_member']['new_chat_member']['status'] = 'member'
    bot.run(member)
    assert bot.subs.get(CHAT)['blocked_at'] is None


class BrokenSubs:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise RuntimeError('database is locked')
        return fail


def test_broken_subscriber_base_does_not_break_taplist_menu(bot):
    bot.ctx._subs = BrokenSubs()
    bot.run(pm('/start'))
    menu = bot.api.last('sendMessage')
    assert menu['text'] == 'Нажми бар:' and _buttons(menu)[5]['callback_data'] == 'sub_start'
    bot.run(cb(AGREE))
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_ERROR


def test_group_menu_has_only_taps(bot):
    bot.run(pm('/start', chat_type='group', chat_id=-100500))
    assert bot.api.last('sendMessage')['reply_markup'] == tp.bar_keyboard()


def test_taplist_messages_unchanged(bot, monkeypatch):
    """Краны уходят как раньше: по сообщению на бар, HTML-разметка таплиста включена."""
    import core.taps_manager as taps_mod
    monkeypatch.setattr(taps_mod, 'TapsManager', lambda data_file=None: object())
    monkeypatch.setattr(tp, '_render_taplist', lambda bid, manager: '<b>%s</b>' % tp.BAR_NAMES[bid])
    bot.run(cb('taplist_all'))
    sent = [p for m, p in bot.api.calls if m == 'sendMessage']
    assert [p['text'] for p in sent] == ['<b>%s</b>' % name for name in tp.BAR_NAMES.values()]
    assert all(p['parse_mode'] == 'HTML' for p in sent)
    bot.run(pm('/taplist2'))
    assert bot.api.last('sendMessage')['text'] == '<b>Лиговский</b>'


def test_taplist_from_registry_not_by_similar_name(bot, monkeypatch):
    """Регрессия 2026-10-04: бот брал сорт из старого справочника по похожему названию и у
    «КЕГ ФестХаус Хеллес» давал ссылку на Festhaus Weissbier. Теперь — реестр Untappd по GUID
    товара и строки «Таплиста пятницы» (core/taplist_post.bar_message_html)."""
    import core.taps_manager as taps_mod
    helles = 'ba7ede81-1cf1-4155-a756-e100d51df438'                  # КЕГ ФестХаус Хеллес в реестре

    class Manager:
        def get_snapshot(self, catalog=None):
            assert helles in catalog                                  # каталог — из реестра
            return {'bar2': {'name': 'Лиговский', 'taps': [
                {'tap_number': 5, 'status': 'active', 'current_beer': 'КЕГ ФестХаус Хеллес',
                 'iiko_product_id': helles, 'started_at': '2026-06-12T04:35:43+03:00',
                 'history': [{'timestamp': '2026-06-12T04:35:43+03:00', 'action': 'start',
                              'beer_name': 'КЕГ ФестХаус Хеллес', 'iiko_product_id': helles}]}]}}

    monkeypatch.setattr(taps_mod, 'TapsManager', lambda data_file=None: Manager())
    bot.run(pm('/taplist2'))
    sent = bot.api.last('sendMessage')
    assert sent['parse_mode'] == 'HTML' and sent['disable_web_page_preview'] is True
    assert sent['text'] == ('<b>Лиговский</b>\n\n5. <a href="https://untappd.com/b/festhaus-helles/6240484">'
                            'Festhaus Helles</a> — светлый лагер, 4,5%')


def test_taplist_data_failure_is_reported(bot, monkeypatch):
    import core.taps_manager as taps_mod
    from core import taplist_post

    def broken(*args, **kwargs):
        raise RuntimeError('реестр не читается')

    monkeypatch.setattr(taps_mod, 'TapsManager', lambda data_file=None: object())
    monkeypatch.setattr(taplist_post, 'bar_message_html', broken)
    bot.run(pm('/taplist3'))
    sent = bot.api.last('sendMessage')
    assert sent['text'] == tp.TEXT_TAPLIST_ERROR and 'parse_mode' not in sent


def test_review_fields_limits():
    long_name = {'user_id': 1, 'username': None, 'first_name': 'Я' * 100, 'last_name': 'Б' * 100}
    now = datetime(2026, 9, 28, 12, 0, 59, tzinfo=MSK)
    fields = tp.review_fields({'chat_id': 1, 'message_id': 7, 'bar': 'bolshoy', 'rating': 3, 'text': '  ок  ',
                               'date': None, 'user': long_name}, {'subscribed': False, 'phone': '79990000000'}, now)
    assert len(fields['author']) == 120 and fields['guest'] == {'telegram': '1', 'phone': ''}
    assert fields['text'] == 'ок' and fields['created_at'] == '2026-09-28T12:00' and fields['external_id'] == 'tg:1:7'


def test_bot_review_reaches_owner_notification(bot):
    from core import review_notify as rn
    bot.run(cb('rv:b:2', message_id=41))
    bot.run(cb('rv:r:2:1', message_id=41))
    bot.run(pm('Грязно <script>alert(1)</script>', message_id=42,
               date=int(datetime(2026, 9, 28, 11, 0, tzinfo=MSK).timestamp())))
    found = rn.candidates(bot.reviews.all(), '2026-09-28T00:00')
    assert [r['external_id'] for r in found] == ['tg:555:42']
    message = rn.format_review(found[0])
    assert 'низкая оценка' in message and 'Бот · оценка 1 из 5' in message and 'Кременчугская' in message
    # Бот персонала открыт для подписки: ни текста, ни имени, ни ника гостя.
    for private in ('Грязно', 'script', 'Анна', 'Петрова', 'anna_p'):
        assert private not in message, private
    assert message.endswith('https://beerkultura.ru/reviews?source=bot&month=all')


# ----------------------------------------------------------------- выключатель записи гостей

MENU_OFF = {'op': 'menu', 'chat_id': CHAT, 'signup': False}


def test_signup_off_plan():
    assert plan_update(pm('/start'), signup=False) == [MENU_OFF]
    for text in ('/subscribe', '/review', '/news', '/start subscribe', '/start review', '/start review_ligovskiy',
                 '/whatever'):
        assert plan_update(pm(text), signup=False) == [MENU_OFF], text
    assert plan_update(cb('sub_start'), signup=False) == [ACK, MENU_OFF]
    assert plan_update(cb('rev_start'), signup=False) == [ACK, MENU_OFF]
    # Отписка — всегда.
    assert plan_update(pm('/stop'), signup=False) == [{'op': 'unsubscribe', 'chat_id': CHAT}]
    assert plan_update(cb('sub_stop'), signup=False) == [ACK, {'op': 'unsubscribe', 'chat_id': CHAT}]
    # Начатое при включённом — доходит до конца, но только из ЖИВОГО шага диалога этого чата.
    consent, review = {'flow': 'consent', 'version': CONSENT_VERSION}, {'flow': 'review'}
    assert plan_update(cb(AGREE), consent, signup=False) == [
        ACK, {'op': 'sub_agree', 'chat_id': CHAT, 'user': USER, 'version': CONSENT_VERSION}]
    assert plan_update(cb('sb:0:1', message_id=3), signup=False)[1]['op'] == 'sub_bars'
    assert plan_update(cb('sb:0:ok', message_id=3), signup=False)[1]['op'] == 'sub_bars_done'
    assert plan_update(cb('rv:b:1', message_id=30), review, signup=False)[1]['op'] == 'rev_bar'
    assert plan_update(cb('rv:r:1:4', message_id=30), review, signup=False)[1]['op'] == 'rev_rating'
    state = {'flow': 'review_text', 'bar': 'ligovskiy', 'rating': 4, 'prompt_message_id': 30}
    assert plan_update(pm('Отлично'), state, signup=False)[0]['op'] == 'rev_save'
    assert plan_update(cb('rv:s:1:4', message_id=30), state, signup=False)[1]['op'] == 'rev_save'
    own = {'phone_number': '79991234567', 'user_id': CHAT}
    assert plan_update(pm(contact=own), {'flow': 'sub_phone'}, signup=False)[0]['op'] == 'sub_phone'
    # Краны — как всегда.
    assert plan_update(pm('/taplist2'), signup=False) == [{'op': 'taplist', 'chat_id': CHAT, 'bar_id': 'bar2'}]
    assert plan_update(cb('taplist_all'), signup=False) == [ACK, {'op': 'taplist', 'chat_id': CHAT, 'bar_id': None}]


def test_signup_off_menu_keyboards():
    assert tp.menu_keyboard(False, signup=False) == tp.bar_keyboard()
    rows = tp.menu_keyboard(True, signup=False)['inline_keyboard']
    assert [b['callback_data'] for row in rows for b in row][5:] == ['sub_stop']
    assert tp.menu_keyboard(True, guest_buttons=False, signup=False) == tp.bar_keyboard()


def test_signup_off_end_to_end(bot):
    bot.switch.on = False
    bot.run(pm('/start'))
    assert bot.api.last('sendMessage')['reply_markup'] == tp.bar_keyboard()      # не подписан — только краны
    for text in ('/subscribe', '/review', '/start review_bolshoy', '/start subscribe'):
        bot.run(pm(text))
        sent = bot.api.last('sendMessage')
        assert sent['text'] == 'Нажми бар:' and sent['reply_markup'] == tp.bar_keyboard(), text
    bot.run(cb('rev_start', message_id=5))
    assert bot.api.last('sendMessage')['reply_markup'] == tp.bar_keyboard() and bot.reviews.all() == []
    # Согласие, показанное при включённом, можно довести до конца.
    bot.switch.on = True
    bot.run(pm('/subscribe'))                      # показано согласие — живой шаг «consent»
    bot.switch.on = False
    bot.run(cb(AGREE, message_id=2))
    assert bot.subs.is_subscribed(CHAT)
    bot.run(pm('/start'))
    buttons = [b['callback_data'] for b in _buttons(bot.api.last('sendMessage'))]
    assert buttons[5:] == ['sub_stop']            # подписанному — «Отписаться»: её обещает текст согласия
    bot.run(cb('sub_stop'))
    assert not bot.subs.is_subscribed(CHAT) and bot.api.last('sendMessage')['text'] == tp.TEXT_UNSUB_DONE_CLOSED
    bot.run(pm('/stop'))
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_UNSUB_NOT_CLOSED
    # Включили снова — входы работают без перезапуска.
    bot.switch.on = True
    bot.run(pm('/subscribe'))
    assert bot.api.last('sendMessage')['text'] == CONSENT_TEXT


def test_signup_enabled_now_reads_content_channels(monkeypatch):
    import sys
    import types
    monkeypatch.setitem(sys.modules, 'core.content_channels', None)          # модуля нет
    assert tp.signup_enabled_now() is False
    fake = types.ModuleType('core.content_channels')
    monkeypatch.setitem(sys.modules, 'core.content_channels', fake)          # модуль есть, функции нет
    assert tp.signup_enabled_now() is False
    fake.bot_signup_enabled = lambda: True
    assert tp.signup_enabled_now() is True and tp.BotContext('t').signup_enabled() is True

    def boom():
        raise RuntimeError('настройки не читаются')
    fake.bot_signup_enabled = boom
    assert tp.signup_enabled_now() is False and tp.BotContext('t').signup_enabled() is False
    fake.bot_signup_enabled = lambda: False
    assert tp.signup_enabled_now() is False
    assert tp.BotContext('t', signup=boom).signup_enabled() is False


# ----------------------------------------------------------------- уведомление владельцу

def test_owner_notified_right_after_bot_review(bot):
    bot.run(cb('rv:b:1', message_id=41))
    bot.run(cb('rv:r:1:2', message_id=41))
    bot.run(pm('Долго ждали', message_id=42, date=int(datetime(2026, 9, 28, 11, 0, tzinfo=MSK).timestamp())))
    [review] = bot.reviews.all()
    assert bot.notified == [review['id']]
    _save(bot, 42)                                    # тот же external_id (дубль) — уведомления нет
    assert bot.notified == [review['id']]
    _save(bot, 50)
    _save(bot, 52)
    _save(bot, 54)                                    # четвёртый за день — лимит, отзыва и уведомления нет
    assert len(bot.reviews.all()) == 3 and len(bot.notified) == 3


def test_notify_failure_does_not_break_guest_reply(bot):
    def boom(review_id):
        raise RuntimeError('нет связи')
    bot.ctx._notify = boom
    _save(bot, 61)
    assert len(bot.reviews.all()) == 1
    texts = [p['text'] for m, p in bot.api.calls if m == 'sendMessage']
    assert texts[-1] == tp.TEXT_REV_THANKS and tp.TEXT_ERROR not in texts


def test_broken_review_file_no_notification(bot):
    with open(bot.reviews.data_file, 'w', encoding='utf-8') as f:
        f.write('{broken')
    _save(bot, 70)
    assert bot.notified == []


def test_default_notify_starts_background_sender(monkeypatch):
    import core.review_notify as rn
    started = []
    monkeypatch.setattr(rn, 'notify_review_in_background', started.append)
    tp.BotContext('t').notify_review('r_1')
    assert started == ['r_1']


# ----------------------------------------------------------------- проверка 2026-09-28

def test_command_name_whitespace_only_text():
    """П. 12: текст из одних пробелов (неразрывный, U+3000) — не IndexError, а не команда."""
    for text in (' ', '　', ' ', '\t\n', ''):
        assert tp.command_name(text) == '', repr(text)
    assert tp.command_name(' /start@kult_taplist_bot x') == 'start'


def test_odd_updates_never_raise(bot):
    """П. 12 и проба p9: странные, но настоящие апдейты проходят handle_update без исключений."""
    cases = [pm(' '), pm('　'), pm('/'), pm(None, message_id=11), pm('/start review_%00'),
             pm('/start subscribe extra'), pm('/' + 'a' * 5000), cb('rv:'), cb('sb::ok'),
             {'callback_query': {'id': 'q', 'data': AGREE, 'from': ANNA}},
             {'callback_query': {'id': 'q', 'data': 'sb:1:ok', 'from': ANNA,
                                 'message': {'chat': {'id': CHAT, 'type': 'private'}}}},
             {'message': {'message_id': 1, 'chat': {'id': CHAT, 'type': 'private'}, 'text': '/review'}}]
    for upd in cases:
        tp.handle_update(upd, bot.ctx)
    hints = [p['text'] for m, p in bot.api.calls if m == 'sendMessage' and p['text'] == tp.TEXT_HINT]
    assert len(hints) >= 3                                # пробелы и стикер — подсказка, не молчание


def test_commands_follow_signup_switch():
    """П. 4: меню команд Telegram — без /subscribe и /review, пока запись выключена;
    выключатель сверяется не чаще раза в минуту, меню переотправляется только при смене."""
    off = [c['command'] for c in tp.commands_for(False)]
    on = [c['command'] for c in tp.commands_for(True)]
    assert 'subscribe' not in off and 'review' not in off and 'stop' in off and 'start' in off
    assert {'subscribe', 'review', 'stop'} <= set(on)
    switch, now, sent, swept = SimpleNamespace(on=False), SimpleNamespace(t=1000.0), [], []
    ctx = tp.BotContext('t', signup=lambda: switch.on, sweep=lambda: swept.append(now.t))
    house = tp.Housekeeping(ctx, lambda commands: sent.append([c['command'] for c in commands]) or {'ok': True},
                            clock=lambda: now.t)
    house.tick()
    assert sent == [off] and swept == [1000.0]            # при старте — меню и первый подбор
    switch.on = True
    now.t += 30
    house.tick()
    assert len(sent) == 1                                 # раньше минуты выключатель не сверяется
    now.t += 31
    house.tick()
    assert sent[-1] == on and len(sent) == 2
    now.t += 61
    house.tick()
    assert len(sent) == 2                                 # не менялся — Telegram не дёргаем
    failing = tp.Housekeeping(ctx, lambda commands: None, clock=lambda: now.t)
    failing.tick()
    assert failing.published is None                      # не удалось — повторит при следующей сверке


def test_sweep_every_ten_minutes():
    """П. 7: подбор отзывов из бота без уведомления — раз в 10 минут из цикла опроса."""
    now, swept = SimpleNamespace(t=0.0), []
    ctx = tp.BotContext('t', signup=lambda: False, sweep=lambda: swept.append(now.t))
    house = tp.Housekeeping(ctx, lambda commands: {'ok': True}, clock=lambda: now.t)
    for t in (0, 300, 599, 600, 900, 1200):
        now.t = float(t)
        house.tick()
    assert swept == [0.0, 600.0, 1200.0]

    def boom():
        raise RuntimeError('подбор упал')
    broken = tp.Housekeeping(tp.BotContext('t', signup=lambda: False, sweep=boom), lambda c: {'ok': True})
    broken.tick()                                         # сбой подбора не роняет опрос


def test_review_text_survives_worker_recycle(bot):
    """П. 6: шаг «ждём текст отзыва» хранится в базе подписчиков: после перезапуска
    воркера (новый процесс — новый BotContext) текст всё равно становится отзывом."""
    bot.ctx.dialogs = tp.PersistentDialogStore(lambda: bot.subs)
    bot.run(cb('rv:b:1', message_id=41))
    bot.run(cb('rv:r:1:2', message_id=41))
    recycled = tp.BotContext('fake-token', api=bot.api, subs=bot.subs, reviews=bot.reviews, clock=bot.clock,
                             signup=lambda: True, notify=bot.notified.append)
    assert isinstance(recycled.dialogs, tp.PersistentDialogStore)   # по умолчанию — в базе
    tp.handle_update(pm('Долго ждали пиво', message_id=42, date=1790000000), recycled)
    [review] = bot.reviews.all()
    assert review['text'] == 'Долго ждали пиво' and review['bar'] == 'ligovskiy' and bot.notified == [review['id']]
    # Таймаут тот же: через 31 минуту шаг истёк — «время вышло», потом подсказка.
    tp.handle_update(cb('rv:r:1:3', message_id=50), recycled)
    bot.clock.value += timedelta(minutes=31)
    tp.handle_update(pm('поздно', message_id=51), recycled)
    assert bot.api.last('sendMessage')['text'].startswith('Время на отзыв вышло')
    tp.handle_update(pm('ещё', message_id=52), recycled)
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_HINT and len(bot.reviews.all()) == 1


def test_persistent_dialogs_fall_back_to_memory():
    """База подписчиков не отвечает — шаг диалога держится в памяти, бот отвечает."""
    def broken():
        raise RuntimeError('database is locked')
    store = tp.PersistentDialogStore(broken)
    t0 = datetime(2026, 9, 28, 12, 0, tzinfo=MSK)
    store.set(1, {'flow': 'sub_phone'}, t0)
    assert store.get(1, t0 + timedelta(minutes=1)) == {'flow': 'sub_phone'}
    store.clear(1)
    assert store.get(1, t0) is None


def test_switch_off_crafted_buttons_rejected(bot):
    """П. 9б и проба p10: при выключенной записи «Согласен» и кнопки отзыва без живого
    шага диалога этого чата ведут в меню — ни отзыва, ни подписки."""
    bot.switch.on = False
    bot.run(pm('/start'))
    for data in ('rv:r:2:1', 'rv:b:0', 'rv:s:0:5', 'rv:x', AGREE, 'sub_agree'):
        bot.run(cb(data, message_id=1001))
        assert bot.api.last('sendMessage')['reply_markup'] == tp.bar_keyboard(), data
    bot.run(pm('Спам-отзыв', message_id=5, date=1790000000))
    assert bot.reviews.all() == [] and bot.notified == [] and bot.subs.get(CHAT) is None
    assert bot.api.last('sendMessage')['text'] == tp.TEXT_HINT_CLOSED
    # Шаг, начатый при включённом, остаётся живым и доходит до конца.
    bot.switch.on = True
    bot.run(cb('rev_start', message_id=60))
    bot.switch.on = False
    bot.run(cb('rv:b:0', message_id=61))
    bot.run(cb('rv:r:0:4', message_id=61))
    bot.run(pm('Хорошо', message_id=62, date=1790000000))
    assert len(bot.reviews.all()) == 1


def test_outdated_consent_button_shows_text_again(bot):
    """П. 10: «Согласен» под старым (или неизвестным) текстом согласия не подписывает —
    бот показывает текущий текст заново; подписка пишет версию из кнопки."""
    assert tp.consent_keyboard()['inline_keyboard'][0][0]['callback_data'] == 'sub_agree:' + CONSENT_VERSION
    for data in ('sub_agree', 'sub_agree:2020-01-01'):
        assert plan_update(cb(data)) == [ACK, {'op': 'sub_offer', 'chat_id': CHAT, 'outdated': True}], data
        bot.run(cb(data, message_id=2))
        assert bot.subs.get(CHAT) is None
        sent = bot.api.last('sendMessage')
        assert sent['text'] == tp.TEXT_CONSENT_UPDATED + '\n\n' + CONSENT_TEXT
        assert _buttons(sent)[0]['callback_data'] == AGREE
    bot.run(cb(AGREE, message_id=3))
    assert bot.subs.get(CHAT)['consent_text_version'] == CONSENT_VERSION


def test_stop_clears_phone_in_reviews(bot):
    """П. 3 и проба p2: /stop обещает «телефон удалён» — он стирается и в отзывах гостя."""
    bot.run(cb(AGREE, message_id=2))
    bot.run(cb('sb:0:ok', message_id=3))
    bot.run(pm(contact={'phone_number': '+7 999 123-45-67', 'user_id': CHAT}))
    bot.run(cb('rv:b:1', message_id=41))
    bot.run(cb('rv:r:1:2', message_id=41))
    bot.run(pm('Долго ждали', message_id=42, date=1790000000))
    assert [r['guest'] for r in bot.reviews.all()] == [{'phone': '+79991234567', 'telegram': '@anna_p'}]
    bot.run(pm('/stop', message_id=43))
    assert bot.subs.get(CHAT)['phone'] is None
    assert [r['guest'] for r in bot.reviews.all()] == [{'phone': '', 'telegram': '@anna_p'}]


def test_foreign_contact_phone_not_rewritten(bot, tmp_path):
    """П. 5 и проба p3: армянский номер из контакта Telegram сохраняется как есть, без
    привязки к чужой (казахстанской) карте гостя; в отзыв — тот же номер."""
    (tmp_path / 'kz').mkdir()
    bot.subs.guests_db_path = _guests_db(tmp_path / 'kz', [('77477123456', '77477123456', '2026-09-25')])
    bot.run(cb(AGREE, message_id=2))
    bot.run(cb('sb:0:ok', message_id=3))
    bot.run(pm(contact={'phone_number': '37477123456', 'user_id': CHAT}))
    row = bot.subs.get(CHAT)
    assert row['phone'] == '+37477123456' and row['guest_id'] is None
    assert bot.subs.recipients('bot_recent_30') == []
    bot.run(cb('rv:b:0', message_id=50))
    bot.run(cb('rv:r:0:1', message_id=50))
    bot.run(pm('Ужасно', message_id=51, date=1790000000))
    assert bot.reviews.all()[0]['guest']['phone'] == '+37477123456'


def test_py310_compatible_syntax():
    import ast
    ast.parse(open(tp.__file__, encoding='utf-8').read(), feature_version=(3, 10))

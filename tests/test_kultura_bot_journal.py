"""
Журнал вопросов и ответов бота @MCPkulturabot и сторож (решение владельца 2026-11-06, «подготовим к
выпуску в прод»): сервер бота (kultura_bot/engine/journal.py, service), сайт (kultura_bot/journal.py,
routes/bot_journal.py, /api/bot/journal*), инструмент common_bot_journal, страница в браузере,
сторож (kultura_bot/watchdog.py).

Что проверяется:
- запись о работе: вопрос, ответ, кто, вид, расход, вызовы инструментов с аргументами и ошибками,
  карточки, сообщения ответа, вид оформления; при ошибке, «Остановить» и пределе — что увидел человек;
- доставка: запись сразу уходит сайту; сайт не ответил — ждёт и уходит позже; отвергнутая — не
  застревает; реакция под сообщением — на сайт;
- сайт: проверка записи, повтор по uid не теряет оценку, срок хранения, оценка реакцией (плохая важнее
  хорошей, снятая реакция), фильтры (период, кто, итог, оценка, поиск по-русски без регистра), итоги,
  страницы, запись целиком, удаление, CSV; API только по ключу сервера бота и только администратору;
  инструмент — только на полном коннекторе /mcp;
- страница в Chromium: итоги, строки, подробности по нажатию с вызовами, удаление с подтверждением;
- сторож: молчание дольше 10 минут — одно сообщение, повтор не дублирует, напоминание через 6 часов,
  «снова отвечает»; ошибка Claude — сразу; error/conflict — через 5 минут; пауза и нет настройки —
  молчит; отправка не удалась — следующая проверка пробует снова; два воркера — одно сообщение.

Запуск: `py -3 -m pytest tests/test_kultura_bot_journal.py`.
"""
import importlib.util
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from kultura_bot import settings as bot_settings  # noqa: E402
from kultura_bot.engine import journal as engine_journal, tools  # noqa: E402
from kultura_bot.engine.site import SiteError  # noqa: E402
from test_kultura_bot import (BOT_AUTHOR, OWNER_TG, bot, env, message, resp, text, use)  # noqa: E402,F401

MSK = timezone(timedelta(hours=3))


# ------------------------------------------------------------------ сервер бота

def test_answer_is_journaled_with_calls_and_delivery(bot):
    bot.client.script += [resp(use('common_whoami', {'x': 'y' * 500}, 't1'), stop='tool_use'),
                          resp(text('Итог: 98% плана.\n\n>> Как считается\n>> факт / план.'))]
    bot.svc.handle_update(message('как прошла неделя?'))
    [record] = bot.env.site.journal_records
    assert record['question'] == 'как прошла неделя?' and record['status'] == 'done'
    assert record['answer'].startswith('Итог: 98% плана.') and 'Как считается' in record['answer']
    assert (record['login'], record['name'], record['chat_id']) == ('owner', 'Владелец', OWNER_TG)
    assert record['mode'] == 'answer' and record['source'] == 'message' and record['format'] == 'plain'
    assert record['messages'] == [1] and record['steps'] == 2 and record['tool_calls'] == 1
    [call] = record['calls']
    assert call['name'] == 'common_whoami' and call['ok'] is True and len(call['args']) <= engine_journal.ARGS_MAX
    assert record['asked_at'].endswith('+03:00') and record['seconds'] >= 0 and len(record['uid']) == 32
    assert bot.env.store.outbox_count() == 0, 'принятая сайтом запись из очереди ушла'


def test_failed_tool_and_card_are_in_the_record(bot):
    bot.env.site.results['analytics_sales'] = {'content': [text('Ошибка HTTP 400: date_from — нужна дата')],
                                               'isError': True}
    bot.client.script += [resp(use('analytics_sales', {'date_from': 'вчера'}, 't1'), stop='tool_use'),
                          resp(use('common_chart_send', {'chart': {'title': 'Выручка'}, 'caption': 'Подпись'}, 't2'),
                               stop='tool_use'),
                          resp(text(''))]
    bot.svc.handle_update(message('график выручки'))
    [record] = bot.env.site.journal_records
    first, second = record['calls']
    assert first['ok'] is False and first['error'].startswith('Ошибка HTTP 400')
    assert second['name'] == 'common_chart_send' and second['ok'] is True
    [card] = record['cards']
    assert (card['tool'], card['title'], card['caption']) == ('common_chart_send', 'Выручка', 'Подпись')


def test_errors_stop_and_budget_record_what_the_person_saw(bot):
    import anthropic
    from test_kultura_bot import api_error
    bot.client.script += [api_error(anthropic.AuthenticationError, 401, 'invalid x-api-key')]
    bot.svc.handle_update(message('вопрос'))
    record = bot.env.site.journal_records[-1]
    assert record['status'] == 'error' and record['error'].startswith('auth:') and record['answer']

    bot.env.site.down = True                       # права из кэша — вопрос в очереди, а перед ответом сайт молчит
    bot.svc.handle_update(message('ещё вопрос'))
    bot.env.site.down = False
    assert bot.env.store.outbox_count() == 1, 'сайт не ответил — запись ждёт'
    bot.svc.journal_retry_at = 0
    bot.svc.flush_journal()
    record = bot.env.site.journal_records[-1]
    assert record['status'] == 'error' and record['error'].startswith('site:') and bot.env.store.outbox_count() == 0


def test_outbox_waits_retries_and_drops_rejected(bot):
    bot.env.site.journal_error = SiteError('offline', 'Сайт не отвечает')
    bot.client.script += [resp(text('Ответ.'))]
    bot.svc.handle_update(message('вопрос'))
    assert bot.env.store.outbox_count() == 1 and bot.tg.sent[-1][1] == 'Ответ.', 'ответ ушёл, запись ждёт'
    bot.svc.flush_journal()
    assert bot.env.store.outbox_count() == 1, 'повтор не раньше FLUSH_RETRY_S'
    bot.env.site.journal_error = None
    bot.svc.journal_retry_at = 0
    bot.svc.report(force=True)
    assert bot.env.store.outbox_count() == 0 and len(bot.env.site.journal_records) == 1, 'с отчётом сайту — ушла'
    [pending] = [r for r in [bot.env.site.journal_records[-1]]]
    bot.env.site.journal_rejects.add('f' * 32)
    bot.env.store.outbox_add(dict(pending, uid='f' * 32))
    bot.svc.flush_journal(force=True)
    assert bot.env.store.outbox_count() == 0, 'отвергнутая запись не застревает'


def test_outbox_has_a_cap(env):
    from kultura_bot.engine import store as store_module
    env.monkeypatch.setattr(store_module, 'OUTBOX_MAX', 3)
    for n in range(5):
        env.store.outbox_add({'uid': f'{n:032x}'}, now=1000 + n)
    assert env.store.outbox_count() == 3
    assert [r['uid'] for r in env.store.outbox_batch(10)] == [f'{n:032x}' for n in (2, 3, 4)], 'старые выброшены'


def test_journal_can_be_switched_off(bot):
    bot.env.monkeypatch.setattr(bot_settings, 'JOURNAL', False)
    bot.client.script += [resp(text('Ответ.'))]
    bot.svc.handle_update(message('вопрос'))
    assert bot.env.site.journal_records == [] and bot.env.store.outbox_count() == 0


def test_reaction_goes_to_the_journal(bot):
    bot.svc.handle_update({'update_id': 3, 'message_reaction': {
        'chat': {'id': int(OWNER_TG), 'type': 'private'}, 'message_id': 701, 'user': {'id': int(OWNER_TG)},
        'date': 1, 'old_reaction': [],
        'new_reaction': [{'type': 'emoji', 'emoji': '\U0001F44E'}, {'type': 'custom_emoji', 'custom_emoji_id': '1'}]}})
    assert bot.env.site.feedback == [(OWNER_TG, 701, OWNER_TG, ['\U0001F44E', 'custom'])]
    bot.svc.handle_update({'update_id': 4, 'message_reaction': {
        'chat': {'id': int(OWNER_TG)}, 'message_id': 701, 'user': {'id': 1, 'is_bot': True}, 'new_reaction': []}})
    assert len(bot.env.site.feedback) == 1, 'реакции ботов не считаются'


def test_button_question_and_help_mention_the_journal(bot):
    from kultura_bot.engine import service
    assert 'журнале на сайте' in service.HELP_TEXT and 'пальцем вниз' in service.HELP_TEXT
    bot.client.script += [resp(text('По дням: …'))]
    bot.svc.handle_update({'update_id': 5, 'callback_query': {
        'id': 'cb', 'from': {'id': int(OWNER_TG)}, 'chat_instance': 'x', 'data': 'ask:По дням',
        'message': {'message_id': 70, 'chat': {'id': int(OWNER_TG), 'type': 'private'}, 'from': BOT_AUTHOR,
                    'text': 'Неделя: 98%'}}})
    record = bot.env.site.journal_records[-1]
    assert record['source'] == 'button' and record['question'] == 'По дням' and record['reply_to'] == {'message_id': 70}


# ------------------------------------------------------------------ сайт: хранилище

@pytest.fixture
def site_db(tmp_path, monkeypatch):
    from core.mcp import db
    db.set_db_path(str(tmp_path / 'mcp.db'))
    monkeypatch.setattr(bot_settings, 'JOURNAL_KEEP_DAYS', 365)
    yield
    db.set_db_path(None)


def record(**extra):
    base = {'uid': uuid.uuid4().hex, 'job_id': 1, 'asked_at': datetime.now(MSK).isoformat(timespec='seconds'),
            'finished_at': datetime.now(MSK).isoformat(timespec='seconds'), 'chat_id': '555', 'chat_type': 'private',
            'tg_user_id': '555', 'login': 'owner', 'name': 'Владелец', 'mode': 'answer', 'source': 'message',
            'question': 'Как прошла неделя на Кременчугской?', 'answer': 'Итог: 98% плана.', 'messages': [701],
            'status': 'done', 'error': '', 'cost_usd': 0.42, 'seconds': 51.2, 'steps': 4, 'tool_calls': 2,
            'calls': [{'name': 'analytics_compare_periods', 'args': '{"days":7}', 'seconds': 3.1, 'ok': True}],
            'cards': [], 'format': 'rich', 'notes': [], 'model': 'claude-opus-5-5'}
    base.update(extra)
    return base


def test_save_validates_and_keeps_rating_on_resend(site_db):
    from kultura_bot import journal
    good = record()
    result = journal.save([good, record(uid='bad'), record(status='weird'), record(asked_at='вчера'), 'не объект'])
    assert result['saved'] == [good['uid']] and len(result['rejected']) == 4
    assert journal.set_feedback('555', 701, '555', ['\U0001F44E']) is True
    journal.save([dict(good, answer='Итог: 98% плана (уточнено).')])
    stored = journal.get(good['uid'])
    assert stored['answer'].endswith('(уточнено).') and stored['rating'] == 'bad', 'повтор по uid не теряет оценку'
    assert stored['calls'][0]['name'] == 'analytics_compare_periods'
    with pytest.raises(journal.JournalError):
        journal.save([record() for _ in range(journal.BATCH_MAX + 1)])
    menu, odd = record(source='menu'), record(source='чужое')
    journal.save([menu, odd])
    assert journal.get(menu['uid'])['source'] == 'menu', 'вопрос из меню раздела (2026-11-06)'
    assert journal.get(odd['uid'])['source'] == 'message'


def test_retention_and_caps(site_db):
    from kultura_bot import journal
    old = record(asked_at=(datetime.now(MSK) - timedelta(days=400)).isoformat(timespec='seconds'), messages=[9])
    huge = record(question='в' * 20000, answer='о' * 60000, calls=[{'name': 'x', 'args': 'a' * 300}] * 2000)
    journal.save([old])
    journal.save([huge])
    assert journal.get(old['uid']) is None and journal.set_feedback('555', 9, '555', ['x']) is False, 'старше года — удалена'
    stored = journal.get(huge['uid'])
    assert len(stored['question']) == journal.QUESTION_MAX and len(stored['answer']) == journal.ANSWER_MAX
    assert stored.get('trimmed') and len(stored['calls']) <= 20


def test_rating_by_reactions(site_db):
    from kultura_bot import journal
    journal.save([record(messages=[1]), record(messages=[2]), record(messages=[3])])
    journal.set_feedback('555', 1, '555', ['\U0001F44D'])
    journal.set_feedback('555', 1, '777', ['\U0001F44E'])
    journal.set_feedback('555', 2, '555', ['❤️'])
    journal.set_feedback('555', 3, '555', ['\U0001F914'])
    ratings = {item['uid']: item['rating'] for item in journal.query({'days': 1})['items']}
    assert sorted(ratings.values()) == ['bad', 'good', 'other'], 'плохая важнее хорошей; сердце с селектором — хорошая'
    journal.set_feedback('555', 3, '555', [])
    assert journal.query({'days': 1, 'rating': 'other'})['items'] == [], 'снятая реакция снимает оценку'


def test_query_filters_stats_and_pages(site_db):
    from kultura_bot import journal
    journal.save([record(question='Выручка на КРЕМЕНЧУГСКОЙ', login='owner'),
                  record(question='Зарплата за октябрь', login='anna', name='Анна', status='error', error='auth: ключ',
                         answer='Anthropic не принял ключ'),
                  record(question='Отчёт по пиву', status='stopped', mode='report'),
                  record(question='Долгий вопрос', status='budget', cost_usd=2.0)])
    everything = journal.query({'days': 7})
    assert everything['stats']['count'] == 4 and everything['stats']['errors'] == 1
    assert everything['stats']['stopped'] == 1 and everything['stats']['budget'] == 1
    assert everything['stats']['cost_usd'] == round(0.42 * 3 + 2.0, 2)
    assert {p['login'] for p in everything['people']} == {'owner', 'anna'}
    assert [i['question'] for i in journal.query({'q': 'кременчугской'})['items']] == ['Выручка на КРЕМЕНЧУГСКОЙ']
    assert len(journal.query({'status': 'problems'})['items']) == 3
    assert [i['login'] for i in journal.query({'login': 'anna'})['items']] == ['anna']
    assert journal.query({'q': '50%_'})['items'] == [], 'знаки LIKE в поиске — буквально'
    first = journal.query({'limit': 2})
    second = journal.query({'limit': 2, 'offset': 2})
    assert len(first['items']) == 2 and len(second['items']) == 2
    assert not {i['uid'] for i in first['items']} & {i['uid'] for i in second['items']}
    for bad in ({'status': 'x'}, {'rating': 'x'}, {'days': 'много'}, {'limit': 'x'}):
        with pytest.raises(journal.JournalError):
            journal.query(bad)


def test_delete_and_csv(site_db):
    from kultura_bot import journal
    one = record(question='Вопрос; с точкой с запятой', cost_usd=1.5)
    journal.save([one])
    text_csv = journal.csv_text({'days': 7})
    assert text_csv.startswith('﻿Когда;Логин;Кто') and '"Вопрос; с точкой с запятой"' in text_csv
    assert ';1,5000;' in text_csv
    assert journal.delete(one['uid']) is True and journal.get(one['uid']) is None and journal.delete(one['uid']) is False
    assert journal.set_feedback('555', 701, '555', ['x']) is False, 'с записью ушли и её сообщения'


# ------------------------------------------------------------------ сайт: API и инструмент

@pytest.fixture
def web(site_db, monkeypatch):
    """Flask с API бота и журналом; администратор — подменой входа."""
    from flask import Flask
    from core import auth_guard
    from routes.bot_api import bot_api_bp
    from routes.bot_journal import bot_journal_bp
    app = Flask('journal_test', template_folder=os.path.join(ROOT, 'templates'),
                static_folder=os.path.join(ROOT, 'static'))
    app.register_blueprint(bot_api_bp)
    app.register_blueprint(bot_journal_bp)
    app.jinja_env.globals['app_version'] = 'test'
    user = {'value': {'id': 1, 'login': 'owner', 'display_name': 'Владелец', 'is_admin': True}}
    monkeypatch.setattr(auth_guard, '_load_user', lambda: user['value'])
    engine = SimpleNamespace(token_id='st_engine')
    from kultura_bot import site_api
    monkeypatch.setattr(site_api, 'verify_engine', lambda raw: engine if raw == 'kmcp_engine' else None)
    return SimpleNamespace(app=app, client=app.test_client(), user=user)


def test_engine_api_saves_and_rates(web):
    one = record()
    headers = {'Authorization': 'Bearer kmcp_engine'}
    assert web.client.post('/api/bot/journal', json={'records': [one]}).status_code == 401
    r = web.client.post('/api/bot/journal', json={'records': [one]}, headers=headers)
    assert r.status_code == 200 and r.get_json() == {'saved': [one['uid']], 'rejected': []}
    assert r.headers['Cache-Control'] == 'no-store'
    assert web.client.post('/api/bot/journal', json={'records': 'x'}, headers=headers).status_code == 400
    r = web.client.post('/api/bot/journal/feedback', headers=headers,
                        json={'chat_id': '555', 'message_id': 701, 'tg_user_id': '555', 'reactions': ['\U0001F44E']})
    assert r.get_json() == {'found': True}
    r = web.client.post('/api/bot/journal/feedback', headers=headers,
                        json={'chat_id': '555', 'message_id': 'x', 'tg_user_id': '555', 'reactions': []})
    assert r.status_code == 400


def test_admin_api_page_and_permissions(web):
    from kultura_bot import journal
    one = record()
    journal.save([one])
    r = web.client.get('/api/admin/bot/journal?days=7&status=done')
    assert r.status_code == 200 and r.get_json()['items'][0]['uid'] == one['uid']
    r = web.client.get(f'/api/admin/bot/journal?uid={one["uid"]}')
    assert r.get_json()['record']['calls'][0]['name'] == 'analytics_compare_periods'
    assert web.client.get('/api/admin/bot/journal?uid=' + 'a' * 32).status_code == 404
    assert web.client.get('/api/admin/bot/journal?status=x').status_code == 400
    r = web.client.get('/api/admin/bot/journal.csv?days=7')
    assert r.status_code == 200 and r.mimetype == 'text/csv' and 'bot-journal.csv' in r.headers['Content-Disposition']
    page = web.client.get('/admin/bot/journal')
    assert page.status_code == 200 and 'Вопросы и ответы' in page.get_data(as_text=True)
    assert web.client.delete(f'/api/admin/bot/journal/{one["uid"]}').get_json() == {'ok': True}
    assert web.client.delete(f'/api/admin/bot/journal/{one["uid"]}').status_code == 404
    web.user['value'] = dict(web.user['value'], is_admin=False)
    assert web.client.get('/api/admin/bot/journal', headers={'Accept': 'application/json'}).status_code == 403
    web.user['value'] = None
    assert web.client.get('/api/admin/bot/journal', headers={'Accept': 'application/json'}).status_code == 401


def test_endpoints_are_public_for_engine_and_closed_to_agents():
    from core.auth_guard import PUBLIC_ENDPOINTS
    from core.mcp import registry
    assert {'bot_api.journal_save', 'bot_api.journal_feedback'} <= PUBLIC_ENDPOINTS
    assert not any(e.startswith('bot_journal.') for e in PUBLIC_ENDPOINTS), 'журнал — только со входом администратора'
    exclusions = registry.exclusions()
    for pair in (('POST', '/api/bot/journal'), ('POST', '/api/bot/journal/feedback'), ('GET', '/api/admin/bot/journal'),
                 ('GET', '/api/admin/bot/journal.csv'), ('DELETE', '/api/admin/bot/journal/<uid>')):
        assert pair in exclusions, pair
    assert 'следы своей работы' in exclusions[('DELETE', '/api/admin/bot/journal/<uid>')]


def test_mcp_tool_only_on_full_connector(site_db, monkeypatch):
    from core.mcp import bridge
    from core.mcp.bridge import ToolError
    from core.mcp.tools import common
    from kultura_bot import journal
    one = record()
    journal.save([one])
    spec = {t.name: t for t in common.TOOLS}['common_bot_journal']
    assert spec.read_only and spec.domain == 'common'
    monkeypatch.setattr(bridge, 'current_call', lambda: SimpleNamespace(connector=None, mode='read'))
    out = common._bot_journal({'days': 7}, None)
    assert out['items'][0]['uid'] == one['uid']
    assert common._bot_journal({'uid': one['uid']}, None)['record']['question'] == one['question']
    with pytest.raises(ToolError, match='Записи нет'):
        common._bot_journal({'uid': 'b' * 32}, None)
    with pytest.raises(ToolError, match='status'):
        common._bot_journal({'status': 'x'}, None)
    monkeypatch.setattr(bridge, 'current_call', lambda: SimpleNamespace(connector='staff', mode='full'))
    with pytest.raises(ToolError, match='полном коннекторе'):
        common._bot_journal({}, None)


def test_engine_client_talks_to_real_routes(web):
    """Настоящий клиент сервера бота (engine/site.py) -> маршруты сайта в этом же процессе."""
    import requests
    from test_kultura_bot_site import BASE, FlaskAdapter
    from kultura_bot.engine.site import Site
    adapter = FlaskAdapter(web.app)

    def session_factory():
        session = requests.Session()
        session.trust_env = False
        session.mount('https://', adapter)
        return session

    site = Site(BASE, 'kmcp_engine', session_factory=session_factory)
    one = record()
    assert site.journal([one]) == {'saved': [one['uid']], 'rejected': []}
    assert site.journal_feedback('555', 701, '555', ['\U0001F44D']) == {'found': True}
    with pytest.raises(SiteError):
        Site(BASE, 'kmcp_wrong', session_factory=session_factory).journal([one])


# ------------------------------------------------------------------ страница в браузере

CHROMIUM = os.environ.get('TG_CHART_CHROMIUM') or '/opt/pw-browsers/chromium'
browser_only = pytest.mark.skipif(importlib.util.find_spec('playwright') is None or not os.path.exists(CHROMIUM),
                                  reason='Playwright или Chromium не установлены')


@browser_only
def test_page_in_browser(web):
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    from kultura_bot import journal
    bad = record(question='Почему план Кременчугской 89%?', answer='Потому что пятница.',
                 calls=[{'name': 'analytics_sales', 'args': '{"bar":"kremenchugskaya"}', 'seconds': 2.5, 'ok': False,
                         'error': 'Ошибка HTTP 400: нет даты'}])
    journal.save([bad, record(question='Выручка вчера', login='anna', name='Анна', status='error', error='site: x')])
    journal.set_feedback('555', 701, '555', ['\U0001F44E'])
    srv = make_server('127.0.0.1', 0, web.app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
            page = browser.new_page(viewport={'width': 390, 'height': 900})
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.goto(f'http://127.0.0.1:{srv.server_port}/admin/bot/journal')
            page.wait_for_selector('#journalRows tr')
            assert '2 вопроса' in page.inner_text('#journalStats') and 'плохих оценок 1' in page.inner_text('#journalStats')
            assert page.locator('#journalRows tr.bj-row').count() == 2
            assert page.locator('#jLogin option').count() == 3, 'все + два человека'
            page.locator('#journalRows tr.bj-row', has_text='Кременчугской').click()
            page.wait_for_selector('.bj-detail')
            detail = page.inner_text('.bj-detail')
            assert 'Потому что пятница.' in detail and 'analytics_sales' in detail and 'нет даты' in detail
            page.select_option('#jStatus', 'problems')
            page.wait_for_function("document.querySelectorAll('#journalRows tr.bj-row').length === 1")
            assert 'Выручка вчера' in page.inner_text('#journalRows')
            assert 'status=problems' in page.get_attribute('#jCsv', 'href')
            page.locator('#journalRows tr.bj-row').first.click()
            page.wait_for_selector('.bj-detail button')
            page.click('.bj-detail button:has-text("Удалить запись")')
            page.click('.bj-detail button:has-text("Удалить")')
            page.wait_for_selector('#journalEmpty:not([hidden])')
            assert page.evaluate('document.documentElement.scrollWidth') <= 390 + 1, 'страница не шире телефона'
            assert errors == []
            browser.close()
    finally:
        srv.shutdown()
    assert len(journal.query({'days': 7})['items']) == 1


# ------------------------------------------------------------------ сторож

@pytest.fixture
def dog(site_db, monkeypatch):
    from kultura_bot import watchdog
    monkeypatch.setattr(bot_settings, 'WATCHDOG', True)
    monkeypatch.setattr(bot_settings, 'WATCHDOG_SILENT_MINUTES', 10)
    monkeypatch.setattr(bot_settings, 'WATCHDOG_REMIND_HOURS', 6)
    sent = []

    def check(now, status, configured=True, ok=True):
        return watchdog.check_once(now, status=status, configured=configured,
                                   send=lambda message: sent.append(message) or ok)
    return SimpleNamespace(check=check, sent=sent, watchdog=watchdog)


def running(at_ts, **extra):
    return dict({'state': 'running', 'detail': 'бот слушает Telegram', 'claude_error': '', 'at_ts': at_ts}, **extra)


def test_watchdog_silence_alerts_once_reminds_and_recovers(dog):
    t0 = 1_800_000_000
    assert dog.check(t0, running(t0 - 60)) == '' and dog.sent == []
    assert dog.check(t0 + 600, running(t0)) == '', 'ровно 10 минут — ещё не беда'
    assert dog.check(t0 + 660, running(t0)) == 'alert'
    assert 'не присылает отчёт' in dog.sent[-1] and 'journalctl -u kultura-bot' in dog.sent[-1]
    assert dog.check(t0 + 720, running(t0)) == '', 'второй воркер (или следующая минута) — не дублирует'
    assert dog.check(t0 + 660 + 6 * 3600, running(t0)) == 'remind' and dog.sent[-1].startswith('Напоминание:')
    assert dog.check(t0 + 7 * 3600, running(t0 + 7 * 3600 - 30)) == 'recovered'
    assert dog.sent[-1] == dog.watchdog.RECOVERED_TEXT and len(dog.sent) == 3
    assert dog.check(t0 + 7 * 3600 + 60, running(t0 + 7 * 3600)) == ''


def test_watchdog_claude_error_state_and_quiet_cases(dog):
    t0 = 1_800_000_000
    assert dog.check(t0, running(t0, claude_error='Anthropic: закончились средства на счёте')) == 'alert'
    assert 'закончились средства' in dog.sent[-1]
    assert dog.check(t0 + 60, running(t0 + 60)) == 'recovered'
    status = running(t0 + 120, state='conflict', detail='токеном бота пользуется другая программа')
    assert dog.check(t0 + 120, status) == '', 'error/conflict — не сразу'
    assert dog.check(t0 + 120 + dog.watchdog.STATE_AFTER_S, status) == 'alert' and 'другая программа' in dog.sent[-1]
    dog.check(t0 + 1000, running(t0 + 1000))
    count = len(dog.sent)
    assert dog.check(t0 + 99_999, running(t0), configured=False) == '' and len(dog.sent) == count, \
        'пауза, нет ключа или сервер не установлен — молчит'


def test_watchdog_retries_when_send_fails_and_can_be_off(dog, monkeypatch):
    t0 = 1_800_000_000
    assert dog.check(t0 + 700, running(t0), ok=False) == ''
    assert dog.check(t0 + 760, running(t0)) == 'alert', 'не ушло — следующая проверка пробует снова'
    monkeypatch.setattr(bot_settings, 'WATCHDOG', False)
    assert dog.check(t0 + 99_999, running(t0)) == ''


def test_watchdog_problem_texts():
    from kultura_bot import watchdog
    now = 1_800_000_000
    assert watchdog.problem(running(now), configured=True, now=now) == ('', '')
    assert watchdog.problem({'state': 'error', 'detail': 'Telegram: 502', 'at_ts': now}, configured=True, now=now) == \
        ('state', 'Бот @MCPkulturabot: Telegram: 502')
    assert watchdog.problem({'state': 'stopped', 'at_ts': 0}, configured=True, now=now) == ('', ''), \
        'сервер бота ни разу не отчитался — это «не установлен», а не беда'

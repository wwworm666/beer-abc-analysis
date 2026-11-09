"""
Страница kultura.research на сайте (решение владельца 2026-11-09): вопросы боту из браузера — краткий ответ
или Research, беседы сохраняются. Сайт кладёт вопрос в очередь (kultura_bot/web.py), отвечает сервер бота
тем же кодом, что в Telegram (kultura_bot/engine/service.answer + WebOut).

Что проверяется:
- очередь на сайте: проверка вопроса, беседы не смешиваются между людьми, в беседе — по одному вопросу,
  предел вопросов в работе; сервер бота берёт старый вопрос, права — ещё раз; ход работы и «Остановить»;
  график и отчёт ложатся в вопрос (та же проверка описаний, что у Telegram) и хранятся целиком; итог;
  молчание сервера дольше STALE_S — ошибка, поздний итог её заменяет; прошлые ответы беседы — серверу бота;
- маршруты: страница и API — только администратору, POST — только JSON; API сервера бота — только по его
  ключу; настоящий клиент сервера бота (engine/site.py) с маршрутами сайта;
- сервер бота: вопрос с сайта идёт тем же путём (те же инструменты), график — на сайт, а не в Telegram,
  «Как считается» и кнопки — полями итога, строка цены — данными; отчёт; «Остановить» со страницы;
  диалог начат заново — прошлые ответы беседы перед вопросом; предел на человека общий с Telegram;
  беседы сайта не попадают в чистку меню и в «повторите вопрос» Telegram;
- страница в Chromium: пустая беседа — логотип набирается, панель бесед скрыта и выезжает по кнопке,
  три готовых вопроса с подсказками; глубина ответа — меню справа («Ответ» / «Исследование»), молния
  быстрого режима с подсказкой; вопрос, ход работы, ответ с графиком и отчётом, «Как считается»
  свёрнуто, кнопок следующего шага нет, беседа по адресу, телефон без горизонтальной прокрутки, готовый
  вопрос задаётся нажатием.

Запуск: `py -3 -m pytest tests/test_research_page.py`.
"""
import copy
import importlib.util
import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from kultura_bot import settings as bot_settings  # noqa: E402
from kultura_bot.charts.fixtures import BELGIUM, REVENUE  # noqa: E402
from kultura_bot.engine import service, tools  # noqa: E402
from test_kultura_bot import OWNER_TG, bot, env, resp, text, use  # noqa: E402,F401

ADMIN = {'id': 1, 'login': 'owner', 'display_name': 'Владелец', 'is_admin': True, 'active': True}
ANNA = {'id': 2, 'login': 'anna', 'display_name': 'Анна', 'is_admin': True, 'active': True}
REPORT = {'title': 'Бельгия: +58% к августу', 'summary': '**Итог:** бельгийское пиво выросло.\n\n[[По барам]]',
          'sections': [{'heading': 'Раздел: литры', 'text': 'Текст раздела.', 'chart': BELGIUM,
                        'table': {'columns': ['Бар', 'Литры'], 'rows': [['Большой', 120.5], ['Лиговский', 98]]},
                        'how': 'Литры по чекам.'}],
          'how': 'Общие правила.', 'source': 'iiko'}


@pytest.fixture
def site_db(tmp_path, monkeypatch):
    from core.mcp import db
    from kultura_bot import web
    from kultura_bot import web_files
    db.set_db_path(str(tmp_path / 'mcp.db'))
    files_dir = str(tmp_path / 'research_files')
    monkeypatch.setattr(web_files, '_DIR_OVERRIDE', files_dir)
    users = {1: dict(ADMIN), 2: dict(ANNA)}
    monkeypatch.setattr(web, '_is_admin', lambda uid: users.get(int(uid)) if users.get(int(uid), {}).get('is_admin')
                        else None)
    monkeypatch.setattr(web, '_expired_at', 0.0)
    yield SimpleNamespace(users=users, files_dir=files_dir)
    db.set_db_path(None)


# ------------------------------------------------------------------ файлы для проверок

def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode('ascii')


def png_bytes(size=(40, 30)) -> bytes:
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', size, (250, 120, 30)).save(out, 'PNG')
    return out.getvalue()


def xlsx_bytes() -> bytes:
    import io
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = 'Остатки'
    for row in (['Позиция', 'Остаток', 'Цена'], ['IPA', 12.5, 230], ['Стаут', None, 310]):
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


# ------------------------------------------------------------------ очередь на сайте

def test_ask_validates_and_keeps_people_apart(site_db):
    from kultura_bot import web
    for bad, kwargs, error in (('', {}, 'Напишите вопрос'), ('x' * 8001, {}, 'длиннее 8000'),
                               ('Вопрос', {'mode': 'long'}, 'mode'), ('Вопрос', {'thread_id': 'tNOTMINE00000000'},
                                                                          'Нет такой беседы')):
        with pytest.raises(web.WebError, match=error):
            web.ask(ADMIN, bad, **kwargs)
    first = web.ask(ADMIN, '  Выручка вчера по барам  ')
    assert first['status'] == 'queued' and first['active'] and first['question'] == 'Выручка вчера по барам'
    assert web.valid_id(first['id'], 'q') and web.valid_id(first['thread_id'], 't') and first['mode'] == 'answer'
    with pytest.raises(web.WebError, match='бот ещё отвечает'):
        web.ask(ADMIN, 'И ещё', thread_id=first['thread_id'])
    with pytest.raises(web.WebError, match='Нет такой беседы'):
        web.ask(ANNA, 'Чужая беседа', thread_id=first['thread_id'])
    assert web.get(2, first['id']) is None and web.thread(2, first['thread_id']) is None and web.threads(2) == []
    web.ask(ADMIN, 'Второй', mode='report')
    web.ask(ADMIN, 'Третий')
    with pytest.raises(web.WebError, match='Уже идут 3'):
        web.ask(ADMIN, 'Четвёртый')
    listed = web.threads(1)
    assert [t['title'] for t in listed][-1] == 'Выручка вчера по барам' and all(t['active'] for t in listed)
    assert [t['reports'] for t in listed if t['title'] == 'Второй'] == [1]


def test_engine_takes_question_and_page_sees_everything(site_db):
    from kultura_bot import web
    from kultura_bot.charts import reports
    asked = web.ask(ADMIN, 'Сравни бельгийское пиво с августом', mode='report')
    job = web.claim()
    assert job['id'] == asked['id'] and job['chat_id'] == 'web:' + asked['thread_id'] and job['mode'] == 'report'
    assert job['actor'] == {'user_id': 1, 'login': 'owner', 'display_name': 'Владелец'} and job['history'] == []
    assert web.claim() is None, 'вопрос уже взят'
    assert web.beat(asked['id'], 'Собираю отчёт · 0:05\nСейчас: думаю — 3 с') == {'stop': False, 'gone': False}
    running = web.get(1, asked['id'])
    assert running['status'] == 'running' and running['progress'].startswith('Собираю отчёт')

    bad = web.add_card(asked['id'], web.CHART_TOOL, {'chart': {'kind': 'pie'}})
    assert bad['isError'] and 'Описание графика' in bad['content'][0]['text']
    chart = web.add_card(asked['id'], web.CHART_TOOL, {
        'chart': REVENUE, 'caption': '**Выручка** выросла.\n\n>> Как считается\n>> Сумма чеков за день.\n\n[[По дням]]',
        'how': 'Источник — iiko.'})
    assert not chart['isError'] and json.loads(chart['content'][0]['text'])['format'] == 'web'
    report = web.add_card(asked['id'], web.REPORT_TOOL, {'report': copy.deepcopy(REPORT)})
    report_id = json.loads(report['content'][0]['text'])['report_id']
    assert reports.get(report_id) is not None, 'отчёт — и в tg_reports: отдельная страница и ссылка для браузера'
    assert web.finish(asked['id'], {'status': 'done', 'answer': '**Итог:** 5 тыс. ₽ <script>x</script>',
                                    'how': 'Формула: сумма.', 'ask': ['Дальше', 'Дальше', ''], 'cost_usd': 0.4237,
                                    'steps': 6, 'fast_steps': 0}) == {'ok': True, 'status': 'done'}
    done = web.get(1, asked['id'])
    assert done['status'] == 'done' and not done['active'] and done['progress'] == ''
    assert '<b>Итог:</b>' in done['answer_html'] and '&lt;script&gt;' in done['answer_html'], 'разметка — только своя'
    assert done['how_html'] == 'Формула: сумма.' and done['ask'] == ['Дальше']
    assert done['cost']['line'] == 'Ответ обошёлся в $0.42 (запросов к модели: 6).'
    chart_card, report_card = done['cards']
    assert chart_card['kind'] == 'chart' and chart_card['spec']['title'] == REVENUE['title']
    assert '<b>Выручка</b>' in chart_card['caption_html'] and 'Как считается' not in chart_card['caption_html']
    assert 'Сумма чеков за день.' in chart_card['how_html'] and 'Источник — iiko.' in chart_card['how_html']
    assert chart_card['ask'] == ['По дням'], '«[[…]]» в подписи — кнопка, а не текст'
    assert report_card['kind'] == 'report' and report_card['page'] == f'/tg/report/{report_id}'
    assert report_card['view']['title'] == REPORT['title'] and report_card['ask'] == ['По барам']
    assert report_card['view']['sections'][0]['table']['rows'][0] == ['Большой', 120.5]
    assert web.finish(asked['id'], {'status': 'error'}) == {'ok': False, 'status': 'done'}, 'итог — один раз'
    reports.delete(report_id)                       # прошло 90 дней: в tg_reports отчёта нет
    kept = web.get(1, asked['id'])['cards'][1]
    assert kept['view']['title'] == REPORT['title'] and kept['page'] is None, 'в вопросе отчёт хранится целиком'
    beat = web.beat(asked['id'], 'поздно')
    assert beat == {'stop': True, 'gone': True}, 'вопрос закрыт — работать незачем'


def test_stop_stale_history_and_access(site_db):
    from kultura_bot import web
    queued = web.ask(ADMIN, 'В очереди')
    assert web.stop(1, queued['id'])['status'] == 'stopped' and web.claim() is None, 'в очереди — сразу закрыт'

    first = web.ask(ADMIN, 'Как прошёл сентябрь?', mode='report')
    web.claim()
    web.add_card(first['id'], web.REPORT_TOOL, {'report': copy.deepcopy(REPORT)})
    web.finish(first['id'], {'status': 'done', 'answer': '', 'steps': 3, 'cost_usd': 1.2})
    second = web.ask(ADMIN, 'Добавь октябрь', thread_id=first['thread_id'], mode='report')
    job = web.claim()
    assert job['id'] == second['id'] and len(job['history']) == 1
    past = job['history'][0]
    assert past['question'] == 'Как прошёл сентябрь?' and past['reports'][0]['title'] == REPORT['title']
    assert 'Раздел: литры' in past['report_text'] and 'Большой' in past['report_text'], 'последний отчёт — целиком'
    stopping = web.stop(1, second['id'])
    assert stopping['status'] == 'taken' and stopping['stopping'], 'в работе — остановит сервер бота'
    assert web.beat(second['id'], 'Отвечаю')['stop'] is True
    web.finish(second['id'], {'status': 'stopped', 'shown': 'Остановил.', 'steps': 1, 'cost_usd': 0.05})
    assert web.get(1, second['id'])['shown'] == 'Остановил.'

    silent = web.ask(ADMIN, 'Сервер замолчит')
    web.claim()
    assert web.expire_stale(time.time() + web.STALE_S + 1, force=True) == 1
    stale = web.get(1, silent['id'])
    assert stale['status'] == 'error' and stale['shown'] == web.STALE_TEXT
    assert web.finish(silent['id'], {'status': 'done', 'answer': 'Всё же ответ', 'steps': 2})['ok'], \
        'поздний итог важнее ошибки ожидания'
    assert web.get(1, silent['id'])['answer_html'] == 'Всё же ответ'

    site_db.users[1]['is_admin'] = False
    revoked = web.ask(ADMIN, 'Админство сняли')
    assert web.claim() is None
    assert web.get(1, revoked['id'])['status'] == 'error' and web.get(1, revoked['id'])['shown'] == web.NO_ACCESS_TEXT
    assert web.delete_thread(1, first['thread_id']) and web.thread(1, first['thread_id']) is None
    assert not web.delete_thread(2, silent['thread_id']), 'чужую беседу не удалить'


def test_engine_state_for_the_banner(site_db, monkeypatch):
    from kultura_bot import credentials, store, web
    monkeypatch.setattr(credentials, 'paused', lambda: True)
    assert 'на паузе' in web.engine_state()['text']
    monkeypatch.setattr(credentials, 'paused', lambda: False)
    monkeypatch.setattr(credentials, 'anthropic_key', lambda: '')
    assert 'Нет ключа' in web.engine_state()['text']
    monkeypatch.setattr(credentials, 'anthropic_key', lambda: 'sk-ant-x')
    monkeypatch.setattr(store, 'get_status', lambda: {'state': 'running', 'at_ts': time.time() - 30})
    assert web.engine_state() == {'ok': True, 'text': ''}
    monkeypatch.setattr(store, 'get_status', lambda: {'state': 'running', 'at_ts': time.time() - 3600})
    assert 'не на связи' in web.engine_state()['text']


# ------------------------------------------------------------------ маршруты

@pytest.fixture
def web_app(site_db, monkeypatch):
    from flask import Flask
    from core import auth_guard
    from kultura_bot import site_api
    from routes.bot_api import bot_api_bp
    from routes.research import research_bp
    from routes.tg_miniapp import tg_miniapp_bp
    app = Flask('research_test', template_folder=os.path.join(ROOT, 'templates'),
                static_folder=os.path.join(ROOT, 'static'))
    app.register_blueprint(research_bp)
    app.register_blueprint(bot_api_bp)
    app.register_blueprint(tg_miniapp_bp)
    app.jinja_env.globals['app_version'] = 'test'
    user = {'value': dict(ADMIN)}
    monkeypatch.setattr(auth_guard, '_load_user', lambda: user['value'])
    monkeypatch.setattr(auth_guard, 'current_user', lambda: user['value'])
    import routes.research as research_routes
    monkeypatch.setattr(research_routes, 'current_user', lambda: user['value'])
    engine = SimpleNamespace(token_id='st_engine')
    monkeypatch.setattr(site_api, 'verify_engine', lambda raw: engine if raw == 'kmcp_engine' else None)
    return SimpleNamespace(app=app, client=app.test_client(), user=user, users=site_db.users)


ENGINE = {'Authorization': 'Bearer kmcp_engine'}


def test_page_and_api_are_for_admins_and_json_only(web_app):
    c = web_app.client
    page = c.get('/research')
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'kultura.research' in body and 'id="rsInput"' in body and '/static/js/research.js?v=test' in body
    assert '$2.00 на вопрос' in body and '$5.00' in body and 'до $2<' in body and 'до $5<' in body, \
        'числа — из настроек бота'
    # Снимок владельца (2026-11-09, второй): глубина ответа — оба названия по-русски, меню справа, как выбор
    # усилия у моделей; молния — «до 2,5 раза быстрее, в 2 раза дороже» (FAST_SPEEDUP_UP_TO,
    # FAST_PRICE_MULTIPLIER; владелец написал наоборот — цифры из прайса Anthropic).
    assert '>Ответ<' in body and '>Исследование<' in body and '>Research<' not in body and 'rsMode' not in body
    assert body.index('id="rsFast"') < body.index('id="rsEffortBtn"') < body.index('id="rsSend"'), \
        'молния слева, глубина ответа — справа у кнопки «Спросить»'
    assert 'Быстро: до 2,5 раза быстрее,' in body and 'но в 2 раза дороже — только для этого вопроса' in body
    assert 'sidebar-link' not in body and 'dashboard/styles' not in body and 'admin_mcp.css' not in body, \
        'свой дизайн (2026-11-09): без меню, шапки и стилей сайта'
    # Правки владельца по снимку (2026-11-09): заголовка и плашки нет, логотип набирается; готовые вопросы —
    # три сложных среза с подсказками (WEB_SUGGESTIONS), без вкладок.
    assert 'Что посчитать?' not in body and 'rx-hero-kicker' not in body and 'данные сети' not in body
    assert 'data-kultura-logo="research"' in body and '/static/logo.js?v=test' in body
    assert body.index('data-kultura-logo="research"') < body.index('/static/logo.js'), 'скрипт — сразу за логотипом'
    assert 'class="rx-main is-empty"' in body
    shown = [item for item in bot_settings.WEB_SUGGESTIONS if f'data-question="{item["question"]}"' in body]
    assert len(shown) == 3 and all(item['hint'] in body for item in shown), 'три случайных из списка'
    assert body.count('class="rx-sq"') == 3 and 'role="tab"' not in body
    assert 'id="rsAttach"' in body and 'type="file"' in body and 'data-files-max="5"' in body, 'файлы — скрепкой'
    assert 'Ваша история — только ваша' in body
    assert 'title="Новая беседа" hidden>' in body, '«+» в пустой беседе не мелькает до скрипта'
    opened = c.get('/research?t=t' + 'A' * 16).get_data(as_text=True)
    assert 'class="rx-main"' in opened and 'title="Новая беседа">' in opened, \
        'беседа по ссылке не рисуется сначала пустой'
    assert '<html lang="ru" data-theme="light">' in body and 'content="light only"' in body, \
        'только светлая тема — «никаких тёмных тем никогда» (2026-11-09)'
    assert '/static/research/kultura-research-mark.svg' in body, 'знак — из набора бренда'
    css = open(os.path.join(ROOT, 'static', 'research.css'), encoding='utf-8').read()
    assert 'prefers-color-scheme: dark' not in css and '[data-theme="dark"]' not in css, 'тёмных правил нет'
    assert "'IBM Plex Sans'" in css and "'IBM Plex Mono'" in css, 'шрифты — IBM Plex, как у сайта'
    import re as _re
    tokens, _, rest = css.partition('html, body {')
    assert not _re.findall(r'#[0-9A-Fa-f]{3,8}\b', rest.replace('#000 0%', '')), 'цвета — только в блоке токенов'
    r = c.post('/api/research/ask', data={'question': 'форма'})
    assert r.status_code == 400 and 'JSON' in r.get_json()['error'], 'форма с чужого сайта не пройдёт'
    asked = c.post('/api/research/ask', json={'question': 'Выручка вчера', 'mode': 'answer', 'fast': True}).get_json()
    q = asked['question']
    assert q['status'] == 'queued' and q['fast'] is True
    listing = c.get('/api/research/threads').get_json()
    assert listing['threads'][0]['id'] == q['thread_id'] and listing['fast'] is True
    assert listing['suggestions'] == [{'question': x['question'], 'hint': x['hint']} for x in bot_settings.WEB_SUGGESTIONS]
    assert 'engine' in listing and c.get('/api/research/threads').headers['Cache-Control'] == 'no-store'
    assert c.get(f'/api/research/threads/{q["thread_id"]}').get_json()['thread']['questions'][0]['id'] == q['id']
    assert c.get(f'/api/research/questions/{q["id"]}').get_json()['question']['status'] == 'queued'
    assert c.post(f'/api/research/questions/{q["id"]}/stop', json={}).get_json()['question']['status'] == 'stopped'
    assert c.get('/api/research/questions/qNOTFOUND0000000').status_code == 404
    assert c.delete(f'/api/research/threads/{q["thread_id"]}').get_json() == {'ok': True}
    assert c.delete(f'/api/research/threads/{q["thread_id"]}').status_code == 404
    web_app.user['value'] = dict(ADMIN, is_admin=False)
    assert c.get('/api/research/threads').status_code == 403 and c.get('/research').status_code == 403
    assert c.post('/api/research/ask', json={'question': 'x'}).status_code == 403


def test_ready_questions_are_deep_slices_three_at_random():
    """Снимки владельца (2026-11-09): «оставляем три вопроса, но реально сложных, неочевидных — не базовые
    метрики, как цифры из дашборда»; «придумай ещё 10 в таком же стиле и чередуй их случайным образом при
    открытии страницы». Вопрос уходит боту целиком, подсказка — одна строка под ним."""
    import random
    from routes import research as research_routes
    items = bot_settings.WEB_SUGGESTIONS
    assert len(items) == 13 and len({x['question'] for x in items}) == 13 and bot_settings.WEB_SUGGESTIONS_SHOWN == 3
    picks = {tuple(x['question'] for x in research_routes._pick_suggestions(random.Random(seed))) for seed in range(12)}
    assert all(len(pick) == 3 and len(set(pick)) == 3 for pick in picks)
    assert len(picks) > 3, 'при каждом открытии — другие три'
    assert {q for pick in picks for q in pick} <= {x['question'] for x in items}
    menu = {q for item in bot_settings.MENU for q in item.get('questions', ())}
    for item in items:
        assert item['question'] not in menu, 'не вопрос из меню разделов: там — базовые срезы'
        assert 60 <= len(item['question']) <= 180, 'разбор с периодом и разрезом, но читается в 2–3 строки'
        assert 3 <= len(item['hint']) <= 60
    assert bot_settings.FAST_SPEEDUP_UP_TO == 2.5 and bot_settings.FAST_PRICE_MULTIPLIER == 2.0


def test_files_are_checked_by_content_and_prepared_for_the_bot(site_db, monkeypatch):
    """Файлы к вопросу (2026-11-09, «кнопка добавить картинку, PDF и т. д.»): тип — по содержимому; боту —
    картинка (большая — уменьшенной копией), PDF, текст таблицы; неизвестное — отказ с тем, что принимается."""
    import zipfile, io
    from kultura_bot import web_files
    ready = web_files.prepare([{'name': 'фото.png', 'data': _b64(png_bytes())},
                               {'name': 'панорама.png', 'data': _b64(png_bytes((3000, 600)))},
                               {'name': 'C:\\Users\\x\\Накладная.pdf', 'data': _b64(PDF)},
                               {'name': 'Остатки.xlsx', 'data': _b64(xlsx_bytes())},
                               {'name': 'выгрузка.csv', 'data': _b64('Позиция;Остаток\nIPA;12\n'.encode('cp1251'))}])
    assert [(f['name'], f['kind'], f['ext']) for f in ready] == [
        ('фото.png', 'image', 'png'), ('панорама.png', 'image', 'png'), ('Накладная.pdf', 'pdf', 'pdf'),
        ('Остатки.xlsx', 'table', 'xlsx'), ('выгрузка.csv', 'table', 'csv')]
    assert ready[0]['bot_data'] is None, 'маленькая картинка — боту как есть'
    from PIL import Image
    small = Image.open(io.BytesIO(ready[1]['bot_data']))
    assert ready[1]['bot_ext'] == 'jpg' and max(small.size) == bot_settings.WEB_IMAGE_MAX_SIDE, 'большая — уменьшена'
    sheet = ready[3]['bot_data'].decode('utf-8')
    assert 'Файл «Остатки.xlsx» (Excel)' in sheet and 'Лист «Остатки»' in sheet and 'IPA;12.5;230' in sheet
    assert 'Позиция;Остаток' in ready[4]['bot_data'].decode('utf-8'), 'CSV из Excel в cp1251 — читается'
    docx = io.BytesIO()
    with zipfile.ZipFile(docx, 'w') as archive:
        archive.writestr('word/document.xml', '<w/>')
    for raw, error in ((b'\x00\x00\x00\x18ftypheic' + b'\x00' * 16, 'HEIC'), (docx.getvalue(), 'Word'),
                       (b'MZ\x90\x00binary', 'не читаю'), (b'', 'пустой')):
        with pytest.raises(web_files.FileError, match=error):
            web_files.prepare([{'name': 'x.bin', 'data': _b64(raw)}])
    with pytest.raises(web_files.FileError, match='повреждённым'):
        web_files.prepare([{'name': 'x.pdf', 'data': 'не base64!'}])
    with pytest.raises(web_files.FileError, match='Не больше 5'):
        web_files.prepare([{'name': f'{i}.pdf', 'data': _b64(PDF)} for i in range(6)])
    monkeypatch.setattr(bot_settings, 'WEB_FILES_TOTAL_MAX_BYTES', len(PDF) + 10)
    with pytest.raises(web_files.FileError, match='вместе'):
        web_files.prepare([{'name': 'a.pdf', 'data': _b64(PDF)}, {'name': 'b.pdf', 'data': _b64(PDF)}])
    monkeypatch.setattr(bot_settings, 'WEB_FILE_MAX_BYTES', 10)
    with pytest.raises(web_files.FileError, match='больше'):
        web_files.prepare([{'name': 'a.pdf', 'data': _b64(PDF)}])


def test_files_go_with_the_question_and_stay_with_its_owner(site_db):
    """Файлы лежат у нас (диск сайта), видит их только тот, кто приложил; серверу бота — пока вопрос в работе;
    в истории беседы — имена; удаляются вместе с беседой; несостоявшийся вопрос файлов не оставляет."""
    from kultura_bot import web
    files = [{'name': 'Накладная.pdf', 'data': _b64(PDF)}, {'name': 'фото.png', 'data': _b64(png_bytes())},
             {'name': 'Остатки.xlsx', 'data': _b64(xlsx_bytes())}]
    q = web.ask(ADMIN, 'Сверь накладную с остатками', files=files)
    assert [(f['name'], f['kind'], f['url']) for f in q['files']] == [
        ('Накладная.pdf', 'pdf', f'/api/research/files/{q["id"]}/0'), ('фото.png', 'image', f'/api/research/files/{q["id"]}/1'),
        ('Остатки.xlsx', 'table', f'/api/research/files/{q["id"]}/2')]
    assert sorted(os.listdir(os.path.join(site_db.files_dir, q['id']))) == ['0.pdf', '1.png', '2.bot.txt', '2.xlsx']
    assert web.user_file(1, q['id'], 0)['data'] == PDF and web.user_file(2, q['id'], 0) is None, 'чужому — нет'
    assert web.engine_file(q['id'], 0) is None, 'пока вопрос в очереди, сервер бота файл не берёт'
    job = web.claim()
    assert [(f['name'], f['kind'], f['mime']) for f in job['files']] == [
        ('Накладная.pdf', 'pdf', 'application/pdf'), ('фото.png', 'image', 'image/png'),
        ('Остатки.xlsx', 'table', 'text/plain; charset=utf-8')]
    assert 'IPA;12.5' in web.engine_file(q['id'], 2)['data'].decode('utf-8'), 'боту — текст таблицы'
    assert web.engine_file(q['id'], 7) is None
    web.finish(q['id'], {'status': 'done', 'answer': 'Расхождений нет.', 'steps': 2, 'cost_usd': 0.3})
    follow = web.ask(ADMIN, 'А по второй накладной?', thread_id=q['thread_id'])
    job = web.claim()
    assert job['id'] == follow['id'] and job['files'] == []
    assert job['history'][0]['files'] == 'Накладная.pdf (PDF), фото.png (картинка), Остатки.xlsx (таблица)'
    before = set(os.listdir(site_db.files_dir))
    with pytest.raises(web.WebError, match='ещё отвечает'):
        web.ask(ADMIN, 'Третий', thread_id=q['thread_id'], files=files[:1])
    assert set(os.listdir(site_db.files_dir)) == before, 'вопрос не записан — файлов нет'
    assert web.delete_thread(1, q['thread_id']) is True
    assert not os.path.exists(os.path.join(site_db.files_dir, q['id'])) and web.user_file(1, q['id'], 0) is None


def test_old_table_gets_the_files_column(tmp_path, monkeypatch):
    """Таблица вопросов, созданная до файлов (2026-11-09), получает колонку files сама — старые вопросы
    открываются как были."""
    import sqlite3
    from core.mcp import db
    from kultura_bot import web
    path = str(tmp_path / 'old.db')
    old = [line for line in web.SCHEMA[0].splitlines() if 'files' not in line]
    old[-2] = old[-2].rstrip(',')
    conn = sqlite3.connect(path)
    conn.execute('\n'.join(old))
    conn.execute("INSERT INTO bot_web_questions (id, thread_id, user_id, login, name, question, mode, status, "
                 "asked_ts) VALUES ('q" + 'C' * 16 + "', 't" + 'C' * 16 + "', 1, 'owner', 'В', 'Старый', 'answer', "
                 "'done', 1)")
    conn.commit()
    conn.close()
    db.set_db_path(path)
    monkeypatch.setattr(web, '_expired_at', 0.0)
    try:
        assert web.get(1, 'q' + 'C' * 16)['files'] == [] and web.thread(1, 't' + 'C' * 16)['questions']
    finally:
        db.set_db_path(None)


def test_engine_api_needs_the_engine_key(web_app):
    c = web_app.client
    q = c.post('/api/research/ask', json={'question': 'Остатки'}).get_json()['question']
    assert c.get('/api/bot/web/next').status_code == 401
    assert c.post(f'/api/bot/web/{q["id"]}/finish', json={'status': 'done'}).status_code == 401
    job = c.get('/api/bot/web/next', headers=ENGINE).get_json()['job']
    assert job['id'] == q['id'] and c.get('/api/bot/web/next', headers=ENGINE).get_json() == {'job': None}
    assert c.post(f'/api/bot/web/{q["id"]}/beat', json={'progress': 'Отвечаю'}, headers=ENGINE).get_json() == \
        {'stop': False, 'gone': False}
    card = c.post(f'/api/bot/web/{q["id"]}/card', json={'tool': tools.CHART_TOOL, 'args': {'chart': BELGIUM}},
                  headers=ENGINE).get_json()
    assert card['isError'] is False
    assert c.post(f'/api/bot/web/{q["id"]}/card', json={'tool': 'common_notify_owner', 'args': {}},
                  headers=ENGINE).status_code == 400
    assert c.post('/api/bot/web/bad/finish', json={'status': 'done'}, headers=ENGINE).status_code == 400
    assert c.post(f'/api/bot/web/{q["id"]}/finish', json={'status': 'weird'}, headers=ENGINE).status_code == 400
    assert c.post(f'/api/bot/web/{q["id"]}/finish', json={'status': 'done', 'answer': 'Ок', 'steps': 2},
                  headers=ENGINE).get_json() == {'ok': True, 'status': 'done'}
    page = c.get(f'/api/research/questions/{q["id"]}').get_json()['question']
    assert page['answer_html'] == 'Ок' and page['cards'][0]['spec']['title'] == BELGIUM['title']


def test_file_routes_are_for_the_owner_and_the_engine(web_app):
    c = web_app.client
    asked = c.post('/api/research/ask', json={'question': 'Что в накладной?', 'files': [
        {'name': 'Накладная.pdf', 'data': _b64(PDF)}, {'name': 'Остатки.xlsx', 'data': _b64(xlsx_bytes())}]})
    assert asked.status_code == 200, asked.get_json()
    q = asked.get_json()['question']
    r = c.get(f'/api/research/files/{q["id"]}/0')
    assert r.status_code == 200 and r.data == PDF and r.mimetype == 'application/pdf'
    assert r.headers['Content-Disposition'].startswith('inline;') and r.headers['X-Content-Type-Options'] == 'nosniff'
    assert "filename*=UTF-8''" in r.headers['Content-Disposition'] and 'private' in r.headers['Cache-Control']
    assert c.get(f'/api/research/files/{q["id"]}/1').headers['Content-Disposition'].startswith('attachment;')
    assert c.get(f'/api/research/files/{q["id"]}/5').status_code == 404
    assert c.get(f'/api/bot/web/{q["id"]}/files/0').status_code == 401, 'серверу бота — только с ключом'
    assert c.get(f'/api/bot/web/{q["id"]}/files/0', headers=ENGINE).status_code == 404, 'вопрос ещё в очереди'
    assert c.get('/api/bot/web/next', headers=ENGINE).get_json()['job']['files'][1]['kind'] == 'table'
    r = c.get(f'/api/bot/web/{q["id"]}/files/1', headers=ENGINE)
    assert r.status_code == 200 and 'Лист «Остатки»' in r.get_data(as_text=True) and r.headers['Cache-Control'] == 'no-store'
    bad = c.post('/api/research/ask', json={'question': 'x', 'files': [{'name': 'a.exe', 'data': _b64(b'MZ\x90')}]})
    assert bad.status_code == 400 and 'не читаю' in bad.get_json()['error']
    web_app.user['value'] = dict(ANNA)
    assert c.get(f'/api/research/files/{q["id"]}/0').status_code == 404, 'чужому — как будто файла нет'


def test_web_report_page_is_only_for_the_thread_owner(web_app):
    """«История у каждого своя» (2026-11-09): отчёт из беседы сайта открывает только её хозяин — даже другой
    администратор, знающий адрес, получает 404; ссылку для браузера делает тоже только хозяин."""
    c = web_app.client
    q = c.post('/api/research/ask', json={'question': 'Бельгия', 'mode': 'report'}).get_json()['question']
    job = c.get('/api/bot/web/next', headers=ENGINE).get_json()['job']
    card = c.post(f'/api/bot/web/{job["id"]}/card', headers=ENGINE,
                  json={'tool': tools.REPORT_TOOL, 'args': {'report': copy.deepcopy(REPORT)}}).get_json()
    report_id = json.loads(card['content'][0]['text'])['report_id']
    assert c.get(f'/tg/report/{report_id}').status_code == 200
    assert c.post(f'/api/tg/reports/{report_id}/link').status_code == 200
    web_app.user['value'] = dict(ANNA)
    assert c.get(f'/tg/report/{report_id}').status_code == 404
    assert c.post(f'/api/tg/reports/{report_id}/link').status_code == 404
    web_app.user['value'] = dict(ADMIN)
    assert c.delete(f'/api/research/threads/{q["thread_id"]}').get_json() == {'ok': True}
    assert c.get(f'/tg/report/{report_id}').status_code == 404, 'беседу удалили — отчёт ничей'


def test_engine_client_talks_to_real_routes(web_app):
    """Настоящий клиент сервера бота (engine/site.py) -> маршруты сайта в этом же процессе."""
    import requests
    from test_kultura_bot_site import BASE, FlaskAdapter
    from kultura_bot.engine.site import Site
    adapter = FlaskAdapter(web_app.app)

    def session_factory():
        session = requests.Session()
        session.trust_env = False
        session.mount('https://', adapter)
        return session

    site = Site(BASE, 'kmcp_engine', session_factory=session_factory)
    q = web_app.client.post('/api/research/ask', json={'question': 'Смены на неделю'}).get_json()['question']
    job = site.web_next()
    assert job['id'] == q['id'] and service.Service.web_job(job)['chat_id'] == 'web:' + q['thread_id']
    assert site.web_beat(q['id'], 'Отвечаю') == {'stop': False, 'gone': False}
    assert site.web_card(q['id'], tools.REPORT_TOOL, {'report': copy.deepcopy(REPORT)})['isError'] is False
    assert site.web_finish(q['id'], {'status': 'done', 'answer': 'Готово.', 'steps': 1}) == {'ok': True,
                                                                                         'status': 'done'}
    assert site.web_next() is None


# ------------------------------------------------------------------ сервер бота

QID = 'q' + 'A' * 16
TID = 't' + 'B' * 16


def web_job(qid=QID, tid=TID, **extra):
    job = {'id': qid, 'thread_id': tid, 'chat_id': 'web:' + tid, 'question': 'Выручка вчера по барам',
           'mode': 'answer', 'fast': False, 'asked_ts': time.time() - 5, 'history': [],
           'actor': {'user_id': 1, 'login': 'owner', 'display_name': 'Владелец'}}
    job.update(extra)
    return job


def test_web_question_goes_the_same_way_but_to_the_site(bot):
    site = bot.env.site
    site.web_queue.append(web_job())
    bot.client.script += [
        resp(use(tools.CHART_TOOL, {'chart': copy.deepcopy(BELGIUM), 'caption': 'Подпись', 'chat_id': '999'}),
             stop='tool_use'),
        resp(text('**Итог:** 5 тыс. ₽\n\n>> Как считается\n>> Сумма за день.\n\n[[По дням]]'))]
    assert bot.svc.take_web_job() is True
    assert site.web_cards == [(QID, tools.CHART_TOOL, {'chart': BELGIUM, 'caption': 'Подпись', 'chat_id': '999'})]
    assert not [c for c in site.calls if c[0] == tools.CHART_TOOL], 'график — на сайт, а не в Telegram'
    assert bot.tg.sent == [], 'в Telegram ничего'
    first = bot.client.calls[0]['messages'][-1]['content'][0]['text']
    assert 'спрашивают со страницы сайта kultura.research' in first and first.endswith('Выручка вчера по барам')
    assert 'speed' not in bot.client.calls[0], 'обычная скорость'
    qid, body = site.web_finished[-1]
    assert qid == QID and body['status'] == 'done' and body['answer'] == '**Итог:** 5 тыс. ₽'
    assert body['how'] == 'Сумма за день.' and body['ask'] == ['По дням'] and body['steps'] == 2
    assert body['cost_usd'] > 0 and body['fast_steps'] == 0 and body['error'] == '' and body['shown'] == ''
    assert site.web_beats and site.web_beats[0][0] == QID and site.web_beats[0][1].startswith('Отвечаю')
    record = site.journal_records[-1]
    assert (record['chat_id'], record['chat_type'], record['source'], record['format']) == \
        ('web:' + TID, 'web', 'web', 'web')
    assert record['login'] == 'owner' and record['tg_user_id'] == '' and record['cards'][0]['chart_id'] == 'w1'
    assert bot.env.store.get_dialog('web:' + TID) is not None, 'беседа — свой диалог, как чат'
    assert bot.env.store.spent_by('user:1') == pytest.approx(record['cost_usd'], abs=1e-4), \
        'предел на человека — общий с Telegram'
    assert 'web:' + TID not in bot.env.store.known_chats(), 'беседы сайта — не чаты Telegram (меню не чистим)'


def test_web_question_files_reach_the_model(bot):
    """Файлы вопроса с сайта — модели, как фото и PDF из Telegram: PDF — документом, картинка — картинкой,
    таблица — текстом; имена — строкой к вопросу; не скачался — пометка под ответом."""
    import base64
    site = bot.env.site
    site.web_files[(QID, 0)] = PDF
    site.web_files[(QID, 1)] = png_bytes()
    site.web_files[(QID, 2)] = 'Файл «Остатки.xlsx» (Excel):\nЛист «Остатки»:\nIPA;12.5'.encode('utf-8')
    site.web_queue.append(web_job(files=[
        {'n': 0, 'name': 'Накладная.pdf', 'kind': 'pdf', 'mime': 'application/pdf', 'size': len(PDF)},
        {'n': 1, 'name': 'фото.png', 'kind': 'image', 'mime': 'image/png', 'size': 100},
        {'n': 2, 'name': 'Остатки.xlsx', 'kind': 'table', 'mime': 'text/plain; charset=utf-8', 'size': 40},
        {'n': 3, 'name': 'нет.pdf', 'kind': 'pdf', 'mime': 'application/pdf', 'size': 10},
        {'n': 'x', 'name': 'плохой', 'kind': 'pdf'}]))
    bot.client.script += [resp(text('Расхождений нет.'))]
    assert bot.svc.take_web_job() is True
    content = bot.client.calls[0]['messages'][-1]['content']
    assert content[0]['text'].endswith('[Приложены файлы: Накладная.pdf (PDF), фото.png (картинка), '
                                       'Остатки.xlsx (таблица), нет.pdf (PDF)]')
    assert [b['type'] for b in content[1:]] == ['document', 'image', 'text']
    assert base64.b64decode(content[1]['source']['data']) == PDF and content[2]['source']['media_type'] == 'image/png'
    assert 'IPA;12.5' in content[3]['text']
    qid, body = site.web_finished[-1]
    assert body['status'] == 'done' and 'Файл «нет.pdf» не скачался' in body['notice']
    block = service.web_history_block([{'question': 'Сверь', 'files': 'Накладная.pdf (PDF)', 'answer': 'Да.'}])
    assert 'К вопросу были приложены файлы: Накладная.pdf (PDF)' in block


def test_web_report_stop_and_history(bot):
    site = bot.env.site
    from test_kultura_bot import report_args
    site.web_queue.append(web_job(mode='report', question='Как прошёл сентябрь'))
    bot.client.script += [resp(use(tools.REPORT_TOOL, report_args(), 'r1'), stop='tool_use'),
                          resp(text('Отчёт отправлен.'))]
    bot.svc.take_web_job()
    assert 'режим: отчёт' in bot.client.calls[0]['messages'][-1]['content'][0]['text']
    assert site.web_cards[-1][1] == tools.REPORT_TOOL
    assert site.web_finished[-1][1]['answer'] == '' and site.web_finished[-1][1]['status'] == 'done', \
        'ответ — страница отчёта, текст после неё не нужен'

    stopped = 'q' + 'S' * 16
    site.web_stop.add(stopped)
    calls = len(bot.client.calls)
    site.web_queue.append(web_job(qid=stopped, tid='t' + 'S' * 16))
    bot.svc.take_web_job()
    assert len(bot.client.calls) == calls, 'нажали «Остановить» — модель не спрашивали'
    assert site.web_finished[-1] == (stopped, {'status': 'stopped', 'error': '', 'shown': service.STOPPED_TEXT,
                                              'cost_usd': 0.0, 'steps': 0, 'fast_steps': 0})

    later = 'q' + 'H' * 16
    history = [{'question': 'Прошлый вопрос', 'mode': 'answer', 'answer': 'Прошлый ответ: 98% плана.',
                'reports': [], 'charts': [{'title': 'Выручка', 'caption': 'Подпись графика'}]}]
    site.web_queue.append(web_job(qid=later, tid='t' + 'H' * 16, question='А за неделю?', history=history))
    bot.client.script += [resp(text('За неделю — 97%.'))]
    bot.svc.take_web_job()
    asked = bot.client.calls[-1]['messages'][-1]['content'][0]['text']
    assert '[Ответ на сообщение бота — продолжение беседы на странице сайта' in asked
    assert 'Прошлый ответ: 98% плана.' in asked and 'График «Выручка»: Подпись графика' in asked
    assert asked.endswith('А за неделю?')


def test_web_jobs_wait_for_a_free_slot_and_bad_jobs_are_closed(bot, monkeypatch):
    site = bot.env.site
    monkeypatch.setattr(bot_settings, 'MAX_PARALLEL_DIALOGS', 2)
    site.web_queue.append(web_job())
    bot.svc.busy.update({'1', '2'})
    assert bot.svc.take_web_job() is False and len(site.web_queue) == 1, 'мест нет — вопрос ждёт на сайте'
    bot.svc.busy.clear()
    site.web_queue[0]['chat_id'] = '555'                 # беседа сайта — только web:t…
    assert bot.svc.take_web_job() is True
    assert site.web_finished[-1][0] == QID and site.web_finished[-1][1]['status'] == 'error'
    assert bot.tg.sent == []
    assert service.Service.web_job(web_job(actor={'login': 'x'})) is None, 'без id администратора — нет'


def test_interrupted_web_question_is_not_sent_to_telegram(bot):
    bot.env.store.start_job('web:' + TID, '', status='queued')
    bot.env.store.start_job(OWNER_TG, OWNER_TG, status='queued')
    bot.svc._interrupted_checked = False
    bot.svc.ready()
    chats = [chat for chat, *_ in bot.tg.sent]
    assert chats == [OWNER_TG], '«повторите вопрос» — только в Telegram; вопрос с сайта закроет сайт'


def test_old_site_dialogs_are_pruned(env):
    env.store.save_dialog('web:' + TID, 'f', 'start', [{'role': 'user', 'content': []}], 1, now=time.time() - 3 * 3600)
    env.store.save_dialog('web:t' + 'N' * 16, 'f', 'start', [], 1)
    env.store.save_dialog(OWNER_TG, 'f', 'start', [], 1, now=time.time() - 3 * 3600)
    assert env.store.prune_dialogs('web:', bot_settings.DIALOG_IDLE_MINUTES * 60) == 1
    assert env.store.get_dialog('web:' + TID) is None and env.store.get_dialog('web:t' + 'N' * 16) is not None
    assert env.store.get_dialog(OWNER_TG) is not None, 'чаты Telegram не трогаем'


def test_web_loop_waits_while_paused(bot):
    bot.svc.config['paused'] = True
    assert bot.svc.web_ready() is False
    bot.svc.config['paused'] = False
    assert bot.svc.web_ready() is True


# ------------------------------------------------------------------ страница в браузере

CHROMIUM = os.environ.get('TG_CHART_CHROMIUM') or '/opt/pw-browsers/chromium'
browser_only = pytest.mark.skipif(importlib.util.find_spec('playwright') is None or not os.path.exists(CHROMIUM),
                                  reason='Playwright или Chromium не установлены')
SHOTS = os.environ.get('RESEARCH_SHOTS')         # папка для снимков страницы (ручная проверка вида)


@browser_only
def test_page_in_browser(web_app, monkeypatch):
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    from kultura_bot import web
    monkeypatch.setattr(web, 'engine_state', lambda now=None: {'ok': True, 'text': ''})
    engine = web_app.app.test_client()
    srv = make_server('127.0.0.1', 0, web_app.app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 860}, device_scale_factor=2 if SHOTS else 1)
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.goto(base + '/research')
            page.wait_for_selector('.rx-main.is-empty #rsInput')
            # Логотип набирается: «kultura» — 7 букв, «research» — 8, точка — оранжевый квадрат.
            page.wait_for_function("document.querySelectorAll('#rsStart .kultura-logo-svg path').length === 15")
            assert page.locator('#rsStart .kultura-logo-svg rect[fill="#FF4B0A"]').count() == 1
            assert page.get_attribute('#rsStart .kultura-logo-svg', 'aria-label') == 'kultura.research'
            assert page.locator('.sidebar, .rx-hero-kicker').count() == 0
            assert not page.is_visible('#rsNew'), 'беседы — за краем, пока не открыть (решение владельца)'
            assert page.is_visible('#rsSideToggle') and not page.is_visible('#rsNewTop')
            assert page.locator('.rx-sq:visible').count() == 3, 'три готовых вопроса'
            pool = {x['question']: x['hint'] for x in bot_settings.WEB_SUGGESTIONS}
            first = page.get_attribute('.rx-sq >> nth=0', 'data-question')
            assert first in pool and pool[first] in page.inner_text('#rsSuggest'), 'случайные — из списка'
            assert page.is_disabled('#rsSend'), 'пустой вопрос не отправить'
            # Молния: подсказка при наведении, включение — свечение (aria-pressed).
            assert not page.is_visible('#rsFastTip')
            page.hover('#rsFast')
            page.wait_for_selector('#rsFastTip', state='visible')
            assert 'до 2,5 раза быстрее' in page.inner_text('#rsFastTip')
            page.click('#rsFast')
            assert page.get_attribute('#rsFast', 'aria-pressed') == 'true'
            page.wait_for_function("getComputedStyle(document.querySelector('#rsFast')).color === 'rgb(255, 75, 10)'")
            page.click('#rsFast')
            assert page.get_attribute('#rsFast', 'aria-pressed') == 'false'
            # Глубина ответа: меню справа, выбранное — галочкой, Esc закрывает.
            assert page.inner_text('#rsEffortBtn').strip() == 'Ответ' and not page.is_visible('#rsEffortMenu')
            page.click('#rsEffortBtn')
            page.wait_for_selector('#rsEffortMenu', state='visible')
            assert page.get_attribute('#rsEffortBtn', 'aria-expanded') == 'true'
            assert page.get_attribute('#rsEffortMenu [data-mode="answer"]', 'aria-checked') == 'true'
            assert 'несколько минут' in page.inner_text('#rsEffortMenu')
            page.keyboard.press('Escape')
            page.wait_for_selector('#rsEffortMenu', state='hidden')
            assert page.evaluate('document.activeElement.id') == 'rsEffortBtn', 'фокус — обратно на кнопку'
            if SHOTS:
                page.screenshot(path=os.path.join(SHOTS, 'research-empty.png'))
            page.click('#rsSideToggle')
            page.wait_for_selector('.rx-app.is-side-open')
            page.wait_for_function("document.activeElement && document.activeElement.id === 'rsNew'")
            page.keyboard.press('Escape')
            page.wait_for_selector('.rx-app:not(.is-side-open)')
            assert page.evaluate('document.activeElement.id') == 'rsSideToggle', 'фокус — обратно на кнопку'
            page.click('#rsEffortBtn')
            page.click('#rsEffortMenu [data-mode="report"]')
            assert page.inner_text('#rsEffortBtn').strip() == 'Исследование' and not page.is_visible('#rsEffortMenu')
            # Файлы: скрепкой — карточки над текстом; лишний — крестиком; неизвестный тип — отказ сразу.
            page.set_input_files('#rsFileInput', files=[
                {'name': 'Накладная.pdf', 'mimeType': 'application/pdf', 'buffer': PDF},
                {'name': 'фото.png', 'mimeType': 'image/png', 'buffer': png_bytes()}])
            page.wait_for_function("document.querySelectorAll('#rsFiles .rx-file').length === 2")
            assert 'Что сделать с файлами' in page.get_attribute('#rsInput', 'placeholder')
            assert page.locator('#rsFiles .rx-file-thumb').count() == 1, 'у картинки — миниатюра'
            page.click('#rsFiles .rx-file:has-text("фото.png") .rx-file-x')
            assert page.locator('#rsFiles .rx-file').count() == 1
            page.set_input_files('#rsFileInput', files=[{'name': 'a.exe', 'mimeType': 'application/octet-stream',
                                                         'buffer': b'MZ'}])
            assert 'не читаю' in page.inner_text('#rsError') and page.locator('#rsFiles .rx-file').count() == 1
            if SHOTS:
                page.fill('#rsInput', 'Сверь накладную с остатками')
                page.locator('.rx-composer').screenshot(path=os.path.join(SHOTS, 'research-files.png'))
            page.fill('#rsInput', 'Как бельгийское пиво в сентябре против августа?')
            page.keyboard.press('Enter')
            page.wait_for_selector('.rx-turn .rx-run')
            assert page.locator('#rsFiles .rx-file').count() == 0 and page.is_hidden('#rsFiles'), 'ушли с вопросом'
            assert page.inner_text('.rx-q-files') .strip().startswith('PDF')
            assert page.get_attribute('.rx-q-files a', 'href').startswith('/api/research/files/q')
            assert 'В очереди' in page.text_content('.rx-turn') and 'ИССЛЕДОВАНИЕ' in page.inner_text('.rx-q-meta')
            assert page.get_attribute('#rsSend', 'aria-label') == 'Остановить', 'пока бот отвечает — «Остановить»'
            assert not page.locator('.rx-main.is-empty').count()
            job = engine.get('/api/bot/web/next', headers=ENGINE).get_json()['job']
            assert job['mode'] == 'report' and [f['name'] for f in job['files']] == ['Накладная.pdf']
            engine.post(f'/api/bot/web/{job["id"]}/beat', headers=ENGINE,
                        json={'progress': 'Собираю отчёт · 0:42\n▰▰▰▱▱▱▱▱▱▱ ≈ 2 мин осталось\nСейчас: «Сравнение '
                                          'периодов» — 12 с\nСделано: 4 шага, 2 запроса данных · $0.61 из $5.00'})
            page.wait_for_function("[...document.querySelectorAll('.rx-run-line')]"
                                   ".some(e => e.textContent.includes('Сравнение периодов'))")
            assert page.text_content('.rx-run .rx-shimmer') == 'Собираю отчёт' and page.inner_text('.rx-clock') == '0:42'
            assert page.evaluate("document.querySelector('.rx-meter span').style.width") == '30%'
            if SHOTS:
                page.screenshot(path=os.path.join(SHOTS, 'research-progress.png'))
            engine.post(f'/api/bot/web/{job["id"]}/card', headers=ENGINE,
                        json={'tool': tools.CHART_TOOL, 'args': {'chart': BELGIUM, 'caption': '**Бельгия:** +58% к '
                                                                  'августу.', 'how': 'Литры по чекам.'}})
            engine.post(f'/api/bot/web/{job["id"]}/card', headers=ENGINE,
                        json={'tool': tools.REPORT_TOOL, 'args': {'report': copy.deepcopy(REPORT)}})
            engine.post(f'/api/bot/web/{job["id"]}/finish', headers=ENGINE,
                        json={'status': 'done', 'answer': '', 'how': '', 'ask': ['Разбей по барам'],
                              'cost_usd': 1.84, 'steps': 14, 'fast_steps': 0})
            page.wait_for_selector('.rx-report .rep h1')
            page.wait_for_selector('.rx-card .card canvas, .rx-card .card svg')
            answer = page.inner_text('.rx-turn .rx-a')
            assert REPORT['title'] in answer and '$1.84 · 14 запросов к модели' in answer
            assert 'Разбей по барам' not in answer, 'кнопок следующего шага нет (решение владельца)'
            assert page.locator('.rx-turn .rx-a details[open]').count() == 0, '«Как считается» — свёрнуто'
            assert page.get_attribute('.rx-report-foot a', 'href').startswith('/tg/report/')
            assert page.get_attribute('#rsSend', 'aria-label') == 'Спросить'
            listed = page.text_content('#rsThreads')            # панель закрыта — текст разметки
            assert 'Как бельгийское пиво' in listed and 'сегодня' in listed.lower(), 'беседы — по дням'
            if SHOTS:
                page.wait_for_timeout(700)
                page.evaluate("document.querySelector('.rx-turn').scrollIntoView({block: 'start'})")
                page.screenshot(path=os.path.join(SHOTS, 'research-desktop.png'))
                page.evaluate("document.querySelector('.rx-report').scrollIntoView({block: 'start'})")
                page.screenshot(path=os.path.join(SHOTS, 'research-report.png'))
            page.fill('#rsInput', 'Разбей по барам')
            page.keyboard.press('Enter')
            page.wait_for_function("document.querySelectorAll('.rx-turn').length === 2")
            follow = engine.get('/api/bot/web/next', headers=ENGINE).get_json()['job']
            assert follow['thread_id'] == job['thread_id'] and follow['history'], 'вопрос — продолжение беседы'
            assert follow['mode'] == 'report', 'вид ответа остаётся выбранным'
            page.click('#rsSend')                                  # «Остановить»
            page.wait_for_function("[...document.querySelectorAll('.rx-run-line')]"
                                   ".some(e => e.textContent.includes('Останавливаю'))")
            engine.post(f'/api/bot/web/{follow["id"]}/finish', headers=ENGINE,
                        json={'status': 'stopped', 'shown': 'Остановил. Уточните вопрос — отвечу заново.'})
            page.wait_for_selector('.rx-turn:last-child .rx-fail')
            url = page.url
            assert '?t=' + job['thread_id'] in url, 'беседа — в адресе'

            phone = browser.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=2 if SHOTS else 1)
            phone.on('pageerror', lambda exc: errors.append(str(exc)))
            phone.goto(url)
            phone.wait_for_selector('.rx-report .rep h1')
            assert phone.evaluate('document.documentElement.scrollWidth') <= 390 + 1, 'страница не шире телефона'
            assert not phone.is_visible('.rx-side .rx-new') or phone.evaluate(
                "document.querySelector('.rx-side').getBoundingClientRect().right <= 0"), 'беседы — за краем'
            if SHOTS:
                phone.wait_for_timeout(900)                    # появление ответа и прокрутка к нему
                phone.screenshot(path=os.path.join(SHOTS, 'research-phone.png'))
            phone.click('#rsSideToggle')
            phone.wait_for_selector('.rx-app.is-side-open')
            phone.wait_for_timeout(350)
            if SHOTS:
                phone.screenshot(path=os.path.join(SHOTS, 'research-phone-threads.png'))
            phone.click('#rsScrim', position={'x': 370, 'y': 400})
            phone.wait_for_selector('.rx-app:not(.is-side-open)')
            phone.goto(base + '/research')
            phone.wait_for_function("document.querySelectorAll('#rsStart .kultura-logo-svg path').length === 15")
            assert phone.evaluate('document.documentElement.scrollWidth') <= 390 + 1
            if SHOTS:
                phone.screenshot(path=os.path.join(SHOTS, 'research-phone-empty.png'))
            page.click('#rsDelete')
            page.click('#rsHeadActions .rx-pill-danger')
            page.wait_for_selector('.rx-main.is-empty')
            # Беседа снова пустая — логотип набирается заново.
            page.wait_for_function("document.querySelectorAll('#rsStart .kultura-logo-svg path').length < 15")
            page.wait_for_function("document.querySelectorAll('#rsStart .kultura-logo-svg path').length === 15")
            # Готовый вопрос — сразу вопрос боту, с выбранной глубиной и молнией; набранный текст остаётся.
            page.click('#rsEffortBtn')
            page.click('#rsEffortMenu [data-mode="answer"]')
            page.click('#rsFast')
            page.fill('#rsInput', 'черновик')
            deep = page.get_attribute('.rx-sq >> nth=2', 'data-question')
            page.locator('.rx-sq').nth(2).click()
            page.wait_for_selector('.rx-turn .rx-run')
            assert page.inner_text('.rx-q-text') == deep and page.input_value('#rsInput') == 'черновик'
            assert 'БЫСТРО' in page.inner_text('.rx-q-meta')
            assert page.get_attribute('#rsFast', 'aria-pressed') == 'false', 'молния — только для этого вопроса'
            ready = engine.get('/api/bot/web/next', headers=ENGINE).get_json()['job']
            assert ready['question'] == deep and ready['mode'] == 'answer' and ready['fast'] is True
            engine.post(f'/api/bot/web/{ready["id"]}/finish', headers=ENGINE,
                        json={'status': 'done', 'answer': 'Кега IPA — на 2 дня.', 'cost_usd': 0.12, 'steps': 3})
            page.wait_for_selector('.rx-turn .rx-prose')
            page.click('#rsDelete')
            page.click('#rsHeadActions .rx-pill-danger')
            page.wait_for_selector('.rx-main.is-empty')
            assert errors == []
            browser.close()
    finally:
        srv.shutdown()
    assert web.threads(1) == []

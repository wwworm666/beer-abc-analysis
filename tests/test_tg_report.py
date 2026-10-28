"""
Отчёты и «Как считается» (решения владельца 2026-10-24): kultura_bot/charts/reports.py,
send.send_report и send.send_chart(how=…), страницы и API (routes/tg_miniapp.py), записка от
сервера бота (POST /api/bot/note), инструмент common_report_send, ссылки (kultura_bot/links.py).

Что проверяется:
- формат отчёта: разделы, графики (тот же формат, что у common_chart_send), таблицы,
  тексты Markdown; ошибки называют поле; выжимка и заголовок — полным фильтром ссылок, тексты
  страницы — узким (имена полей вроде metrics.avg_rating не портятся, явные чужие адреса
  вырезаются); запись не больше предела;
- хранилище: id rep_ + 22 шестнадцатеричных знака, срок 90 дней, суточный предел;
- отправка отчёта: обложка — первый график (фото, выжимка подписью HTML) или сообщение без
  графиков; кнопка «Открыть отчёт»: личка — web_app, группа — t.me (короткое имя) или
  страница сайта; длинная выжимка — ошибка до записи; Telegram отказал — запись удалена,
  ответа нет — запись остаётся; разметку не разобрал — простым текстом;
- график с подписью-ответом и how: подпись Markdown -> HTML с переводами строк, длина по
  видимому тексту; how — записка, ссылка в конце подписи или кнопка рядом с «Открыть
  интерактивно»;
- API /api/tg/reports/<id>: initData и участие в чате, как у графика; страница сайта
  /tg/report/<id> — только после входа в сайт, не кэшируется;
- POST /api/bot/note — только ключ сервера бота; инструмент common_report_send — в полном
  режиме, ошибки текстом.

Запуск: `py -3 -m pytest tests/test_tg_report.py`.
"""
import copy
import json
import os
import sys
import tempfile
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core.mcp import db  # noqa: E402
from kultura_bot import links, settings as bot_settings  # noqa: E402
from kultura_bot.charts import access as tg_chart_access, reports, send as tg_send, spec as tg_charts  # noqa: E402
from kultura_bot.charts.fixtures import FIXTURES  # noqa: E402
from test_tg_miniapp import GROUP, OWNER, STRANGER, TOKEN, FakeMembers, init_data, make_app  # noqa: E402

PNG = b'\x89PNG\r\n\x1a\nfake'
CHAT = str(OWNER)
NB = '\u00a0'                    # неразрывный пробел в числах (formatting.nbsp)

REPORT = {
    'title': 'Бельгия в ивент: +58,0% к августу',
    'summary': '**Бельгия в ивент 2–13 сен: 327 тыс. ₽, +58,0% к 19–30 авг.**\n\n'
               '> Квак · +136 · новый\n> Барбе Руби · +23\n\nПодробности — в отчёте.',
    'sections': [
        {'heading': 'Весь рост дал Квак', 'text': 'Без Квака шесть сортов — **191 к 207 тыс. ₽**, −7,7%.',
         'chart': dict(FIXTURES)['belgium'],
         'how': 'Изменение = (ивент − база) / база × 100; поле metrics.avg_rating не трогаем.'},
        {'heading': 'Точные значения', 'table': {
            'columns': ['Сорт', 'Ивент, ₽', {'label': 'Август, ₽', 'align': 'right'}],
            'rows': [['Квак', 136000, 0], ['Палм', 55000, 68000], ['Гулден Драк', None, 17000]],
            'note': 'Выручка со скидкой'}},
    ],
    'how': 'analytics_explorer_report, фильтр DishForeignName; см. https://evil.example/phish',
    'source': 'iiko',
    'data_at': '2026-09-14T00:58:00+03:00',
}


def full_filter(text):
    from core.mcp.tools.common import _strip_foreign_links
    return _strip_foreign_links(text)


def page_filter(text):
    from core.mcp.tools.common import strip_foreign_urls
    return strip_foreign_urls(text)


class FakeTelegram:
    """sendPhoto и sendMessage Telegram: ответы по очереди (по умолчанию — «отправлено»)."""

    def __init__(self):
        self.calls = []
        self.replies = []
        self.outcomes = []

    def _reply(self, outcome):
        if self.outcomes:
            value = self.outcomes.pop(0)
            if value:
                outcome.append(value)
        return self.replies.pop(0) if self.replies else {'ok': True, 'result': {'message_id': 76 + len(self.calls)}}

    def photo(self, fields, png, token, outcome):
        self.calls.append(('photo', dict(fields)))
        return self._reply(outcome)

    def message(self, payload, token, outcome):
        self.calls.append(('message', copy.deepcopy(payload)))
        return self._reply(outcome)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    db.set_db_path(str(tmp_path / 'mcp.db'))
    tg_chart_access.clear_cache()
    monkeypatch.setenv('TELEGRAM_MCP_BOT_TOKEN', TOKEN)
    monkeypatch.setattr(bot_settings, 'CHART_BUTTON', True)
    monkeypatch.setattr(bot_settings, 'MINIAPP_SHORT_NAME', '')
    monkeypatch.setattr(tg_send, 'notify_chat_id', lambda: '')
    rendered = []
    monkeypatch.setattr(tg_send, '_render', lambda spec: rendered.append(spec) or PNG)
    tg = FakeTelegram()
    monkeypatch.setattr(tg_send, '_transport', tg.photo)
    monkeypatch.setattr(tg_send, '_transport_message', tg.message)
    yield {'tg': tg, 'rendered': rendered, 'monkeypatch': monkeypatch}
    tg_chart_access.clear_cache()
    db.set_db_path(None)


def rows():
    reports._ensure()
    with db.read() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM tg_reports ORDER BY created_ts')]


# ------------------------------------------------------------------ формат

def test_report_normalizes_and_filters_by_destination():
    body = reports.normalize_report(REPORT, text_filter=full_filter, page_filter=page_filter)
    assert body['kind'] == 'report' and body['title'] == REPORT['title'] and len(body['sections']) == 2
    assert body['sections'][0]['chart']['kind'] == 'periods', 'график раздела — тот же формат, что у графиков'
    assert 'metrics.avg_rating' in body['sections'][0]['how'], 'имена полей на странице не портятся'
    assert body['how'].endswith('см. [ссылка удалена]'), 'явный чужой адрес вырезан'
    table = body['sections'][1]['table']
    assert [c['align'] for c in table['columns']] == ['left', 'right', 'right'], 'числовые колонки — вправо'
    assert table['rows'][2] == ['Гулден Драк', None, 17000] and table['note'] == 'Выручка со скидкой'
    assert body['summary'].count('\n') == 5, 'строки выжимки сохраняются'
    assert body['data_at'] == '2026-09-14T00:58:00+03:00'


@pytest.mark.parametrize('patch, message', [
    ({'sections': []}, 'sections: список от 1 до 20'),
    ({'summary': '  '}, 'summary: обязательное поле'),
    ({'extra': 1}, 'неизвестные поля отчёта: extra'),
    ({'sections': [{'heading': 'Пусто'}]}, 'sections[0]: нужен хотя бы text, chart или table'),
    ({'sections': [{'heading': 'Г', 'chart': {'kind': 'pie'}}]}, 'sections[0].chart: '),
    ({'sections': [{'heading': 'Т', 'table': {'columns': ['a', 'b'], 'rows': [[1]]}}]},
     'sections[0].table.rows[0]: список из 2 ячеек'),
    ({'sections': [{'heading': 'Т', 'table': {'columns': ['a'], 'rows': [[True]]}}]},
     'sections[0].table.rows[0][0]: ячейка — строка, число или null'),
    ({'sections': [{'heading': 'Г', 'chart': dict(FIXTURES)['check']}] * 9}, 'не больше 8 графиков'),
])
def test_bad_reports_name_the_field(patch, message):
    raw = dict(REPORT, **patch)
    raw = {k: v for k, v in raw.items() if k != 'extra'} | ({'extra': 1} if 'extra' in patch else {})
    with pytest.raises(reports.ReportError) as err:
        reports.normalize_report(raw)
    assert message in str(err.value)


def test_note_and_size_limit():
    note = reports.normalize_note('>> лишнее\n\n\n\nформула = 1 + 1   ', page_filter=page_filter)
    assert note == {'kind': 'note', 'title': 'Как считается', 'text': '>> лишнее\n\nформула = 1 + 1',
                    'data_at': note['data_at']}
    with pytest.raises(reports.ReportError):
        reports.normalize_note('   ')
    table = {'columns': [f'к{i}' for i in range(12)], 'rows': [['я' * 100] * 12 for _ in range(300)]}
    big = dict(REPORT, sections=[{'heading': 'Большая таблица', 'table': table}])
    with pytest.raises(reports.ReportError, match='запись больше 400 КБ'):
        reports.normalize_report(big)


def test_store_ids_ttl_and_limit(setup):
    body = reports.normalize_report(REPORT)
    saved = reports.create(body, chat_id=CHAT, token_id='st_x')
    assert links.REPORT_ID_RE.fullmatch(saved['id']) and len(saved['id']) == 26
    assert reports.valid_id(saved['id']) and not reports.valid_id('A' * 22) and not tg_charts.get(saved['id'])
    assert reports.get(saved['id'])['body'] == body
    assert reports.get(saved['id'], now_ts=time.time() + 91 * 86400) is None, 'через 90 дней не отдаётся'
    reports.create(reports.normalize_note('x'), daily_limit=5)
    with pytest.raises(reports.ReportLimitError):
        reports.create(reports.normalize_note('x'), daily_limit=2)


# ------------------------------------------------------------------ отправка отчёта

def test_report_with_chart_goes_as_cover_photo(setup):
    result = tg_send.send_report(REPORT, chat_id=CHAT, token_id='st_x', text_filter=full_filter,
                                 page_filter=page_filter)
    kind, fields = setup['tg'].calls[0]
    assert kind == 'photo' and fields['parse_mode'] == 'HTML'
    assert fields['caption'].startswith(f'<b>Бельгия в ивент 2–13 сен: 327{NB}тыс.{NB}₽, +58,0% к 19–30 авг.</b>\n\n'
                                        '<blockquote>Квак · +136 · новый\nБарбе Руби · +23</blockquote>')
    assert setup['rendered'][0]['title'] == 'Бельгия на розливе', 'обложка — первый график отчёта'
    markup = json.loads(fields['reply_markup'])
    assert markup == {'inline_keyboard': [[{'text': 'Открыть отчёт', 'web_app': {
        'url': f'https://beerkultura.ru/tg/chart?id={result["report_id"]}'}}]]}
    stored = reports.get(result['report_id'])
    assert (stored['chat_id'], stored['sent'], stored['message_id'], stored['token_id']) == (CHAT, 1, 77, 'st_x')
    assert result['url'] == f'https://beerkultura.ru/tg/report/{result["report_id"]}' and result['cover'] is True


def test_report_without_chart_is_a_message_and_group_buttons(setup):
    mp = setup['monkeypatch']
    plain = dict(REPORT, sections=[REPORT['sections'][1]])
    result = tg_send.send_report(plain, chat_id=GROUP)
    kind, payload = setup['tg'].calls[0]
    assert kind == 'message' and payload['parse_mode'] == 'HTML' and payload['link_preview_options'] == {
        'is_disabled': True}
    assert payload['reply_markup'] == {'inline_keyboard': [[{'text': 'Открыть отчёт', 'url': links.site_page(
        result['report_id'])}]]}, 'группа без короткого имени — страница сайта'
    mp.setattr(bot_settings, 'MINIAPP_SHORT_NAME', 'app')
    result = tg_send.send_report(plain, chat_id=GROUP)
    assert setup['tg'].calls[1][1]['reply_markup']['inline_keyboard'][0][0]['url'] == \
        f'https://t.me/MCPkulturabot/app?startapp={result["report_id"]}'


def test_report_errors_and_cleanup(setup):
    tg = setup['tg']
    long_summary = dict(REPORT, summary='я' * 1100)
    with pytest.raises(tg_send.ChartSendError, match='summary длиннее 1024'):
        tg_send.send_report(long_summary, chat_id=CHAT)
    assert rows() == [] and tg.calls == [], 'длинная выжимка — ошибка до записи и отправки'
    tg.replies = [{'ok': False, 'description': 'Bad Request: chat not found'}]
    with pytest.raises(tg_send.ChartSendError, match='chat not found'):
        tg_send.send_report(REPORT, chat_id=CHAT)
    assert rows() == [], 'Telegram отказал — запись удалена'
    tg.replies, tg.outcomes = [None], ['unknown']
    with pytest.raises(tg_send.ChartSendError, match='Статус неизвестен'):
        tg_send.send_report(REPORT, chat_id=CHAT)
    assert len(rows()) == 1, 'ответа нет — запись остаётся: сообщение могло дойти, кнопка должна работать'
    tg.replies = [{'ok': False, 'description': "Bad Request: can't parse entities"}]
    tg_send.send_report(REPORT, chat_id=CHAT)
    last = tg.calls[-1][1]
    assert 'parse_mode' not in last and last['caption'].startswith('Бельгия в ивент 2–13 сен'), \
        'разметку не разобрал — простым текстом'


# ------------------------------------------------------------------ график: подпись-ответ и «Как считается»

def test_chart_caption_is_markdown_answer_and_how_goes_behind_button(setup):
    caption = '**Бельгия +58,0% к августу.**\n\n> Квак · +136\n> Палм · −13\n\nМогу показать по порциям.'
    result = tg_send.send_chart(dict(FIXTURES)['belgium'], chat_id=CHAT, caption=caption,
                                how='доля = 136 / 327 = 42%; metrics.avg_rating', page_filter=page_filter)
    fields = setup['tg'].calls[0][1]
    assert fields['caption'] == ('<b>Бельгия +58,0% к августу.</b>\n\n<blockquote>Квак · +136\nПалм · −13'
                                 '</blockquote>\n\nМогу показать по порциям.'), 'переводы строк сохраняются'
    how_id = result['how']['id']
    assert result['how']['shown_as'] == 'button'
    row = json.loads(fields['reply_markup'])['inline_keyboard'][0]
    assert [b['text'] for b in row] == ['Открыть интерактивно', 'Как считается'], 'кнопки рядом, один ряд'
    assert row[1]['web_app']['url'] == f'https://beerkultura.ru/tg/chart?id={how_id}'
    note = reports.get(how_id)
    assert note['body']['kind'] == 'note' and 'metrics.avg_rating' in note['body']['text'] and note['sent'] == 1


def test_chart_how_link_with_short_name_and_in_group(setup):
    mp = setup['monkeypatch']
    mp.setattr(bot_settings, 'MINIAPP_SHORT_NAME', 'app')
    result = tg_send.send_chart(dict(FIXTURES)['check'], chat_id=CHAT, caption='Итог: +83 ₽ на чек.', how='формула')
    fields = setup['tg'].calls[0][1]
    how_id = result['how']['id']
    assert fields['caption'] == (f'Итог: +83{NB}₽ на чек. <a href="https://t.me/MCPkulturabot/app?startapp={how_id}">'
                                 'Как считается</a>'), 'ссылка в конце последней строки — ни строки места'
    assert result['how']['shown_as'] == 'link'
    assert len(json.loads(fields['reply_markup'])['inline_keyboard'][0]) == 1, 'кнопка — только «Открыть интерактивно»'
    mp.setattr(bot_settings, 'MINIAPP_SHORT_NAME', '')
    result = tg_send.send_chart(dict(FIXTURES)['check'], chat_id=GROUP, caption='Итог.', how='формула')
    fields = setup['tg'].calls[1][1]
    assert links.site_page(result['how']['id']) in fields['caption'] and 'reply_markup' not in fields, \
        'группа без короткого имени — ссылка на страницу сайта, кнопки графика нет'


def test_chart_caption_limit_counts_visible_text(setup):
    caption = '**' + 'я' * 1000 + '**'
    tg_send.send_chart(dict(FIXTURES)['check'], chat_id=CHAT, caption=caption)      # 1000 знаков без тегов
    with pytest.raises(tg_send.ChartSendError, match='caption длиннее 1024 знаков без разметки'):
        tg_send.send_chart(dict(FIXTURES)['check'], chat_id=CHAT, caption='я' * 1100)
    assert len(tg_charts.get(tg_send.send_chart(dict(FIXTURES)['check'], chat_id=CHAT)['chart_id'])['spec']) > 0


# ------------------------------------------------------------------ страницы и API

def get_report(client, report_id, data=None):
    headers = {} if data is None else {'Authorization': f'tma {data}'}
    return client.get(f'/api/tg/reports/{report_id}', headers=headers)


def test_report_api_checks_init_data_and_membership(setup, monkeypatch):
    body = reports.normalize_report(REPORT, page_filter=page_filter)
    rid = reports.create(body, chat_id=CHAT)['id']
    client = make_app().test_client()
    assert get_report(client, rid).status_code == 401
    assert get_report(client, rid, init_data(token='other')).get_json()['code'] == 'init_data_invalid'
    assert get_report(client, 'rep_' + '0' * 22, init_data()).get_json()['code'] == 'report_not_found'
    resp = get_report(client, rid, init_data(user_id=STRANGER))
    assert resp.status_code == 403 and resp.get_json()['code'] == 'not_allowed'
    resp = get_report(client, rid, init_data())
    assert resp.status_code == 200 and resp.headers['Cache-Control'] == 'no-store'
    view = resp.get_json()['report']
    assert view['kind'] == 'report' and view['summary_html'].startswith('<b>Бельгия в ивент')
    assert view['sections'][0]['html'] == f'Без Квака шесть сортов — <b>191 к 207{NB}тыс.{NB}₽</b>, −7,7%.'
    assert view['sections'][0]['chart']['kind'] == 'periods' and view['sections'][1]['table']['rows'][0][1] == 136000
    group_note = reports.create(reports.normalize_note('формула'), chat_id=GROUP)['id']
    monkeypatch.setattr(tg_chart_access, '_get_chat_member', FakeMembers({(GROUP, OWNER): 'member'}))
    assert get_report(client, group_note, init_data()).get_json()['report'] == {
        'id': group_note, 'kind': 'note', 'title': 'Как считается', 'how_html': 'формула',
        'data_at': None, 'created_at': reports.get(group_note)['created_at']}, 'у записки нет «данные на»: её время — сборка'
    assert get_report(client, group_note, init_data(user_id=STRANGER)).status_code == 403


def test_site_page_needs_site_login(setup):
    from core import auth_manager as am
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)
    mgr = am.AuthManager(db_path=path)
    am._auth_manager = mgr
    mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True)
    from routes.auth import auth_bp
    app = make_app()
    app.register_blueprint(auth_bp)
    rid = reports.create(reports.normalize_report(REPORT), chat_id=CHAT)['id']
    client = app.test_client()
    resp = client.get(f'/tg/report/{rid}')
    assert resp.status_code == 302 and '/login' in resp.headers['Location'], 'без входа — страница входа'
    client.post('/login', data={'login': 'owner', 'password': 'ownerpass'})
    resp = client.get(f'/tg/report/{rid}')
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200 and resp.headers['Cache-Control'] == 'private, no-store'
    assert 'data-mode="site"' in page and '/static/tg_chart/report.js' in page and '/static/tg_chart/site.js' in page
    assert 'telegram-web-app.js' not in page and 'Content-Security-Policy' in resp.headers
    assert '<title>Бельгия в ивент: +58,0% к августу · Культура</title>' in page
    assert client.get('/tg/report/rep_' + '0' * 22).status_code == 404


def link_call(client, method, report_id, data=None):
    headers = {} if data is None else {'Authorization': f'tma {data}'}
    return client.open(f'/api/tg/reports/{report_id}/link', method=method, headers=headers)


def test_browser_link_made_by_chat_member_opens_without_login(setup, monkeypatch):
    """2026-10-28, решение владельца: «полный отчёт доступен по ссылке в браузере, ровно в таком же
    дизайне». Ссылку делает участник чата отчёта (initData) — та же при повторе; открывает её любой без
    входа: тот же шаблон и site.js, без id записи, не кэшируется и не индексируется; закрыли — 404."""
    rid = reports.create(reports.normalize_report(REPORT, page_filter=page_filter), chat_id=CHAT)['id']
    client = make_app().test_client()
    assert link_call(client, 'POST', rid).status_code == 401, 'без initData и без входа — нельзя'
    assert link_call(client, 'POST', 'rep_' + '0' * 22).status_code == 401, 'без входа не узнать, есть ли запись'
    resp = link_call(client, 'POST', rid, init_data(user_id=STRANGER))
    assert resp.status_code == 403 and resp.get_json()['code'] == 'not_allowed'
    assert reports.link_token(rid) is None, 'чужой ссылку не сделал'
    resp = link_call(client, 'POST', rid, init_data())
    link = resp.get_json()['link']
    assert resp.status_code == 200 and link.startswith('https://beerkultura.ru/r/') and resp.headers['Cache-Control'] == 'no-store'
    token = link.rsplit('/', 1)[1]
    assert reports.LINK_TOKEN_RE.fullmatch(token) and token not in rid
    assert link_call(client, 'POST', rid, init_data()).get_json()['link'] == link, 'повтор — та же ссылка'
    assert get_report(client, rid, init_data()).get_json()['link'] == link, 'страница видит, что ссылка открыта'

    page = client.get(f'/r/{token}')
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and 'data-mode="site"' in html and '/static/tg_chart/site.js' in html
    assert '<title>Бельгия в ивент: +58,0% к августу · Культура</title>' in html
    assert page.headers['Cache-Control'] == 'private, no-store' and page.headers['X-Robots-Tag'] == 'noindex, nofollow'
    assert page.headers['Referrer-Policy'] == 'no-referrer' and 'Content-Security-Policy' in page.headers
    assert rid not in html and '"shared": true' in html and 'telegram-web-app.js' not in html

    assert link_call(client, 'DELETE', rid, init_data(user_id=STRANGER)).status_code == 403
    assert link_call(client, 'DELETE', rid, init_data()).get_json() == {'link': ''}
    gone = client.get(f'/r/{token}')
    assert gone.status_code == 404 and '"gone": true' in gone.get_data(as_text=True), 'закрыли — не открывается'
    new = link_call(client, 'POST', rid, init_data()).get_json()['link']
    assert new != link, 'после закрытия — новая ссылка'
    assert client.get('/r/' + 'x' * 22).status_code == 404 and client.get('/r/короткий').status_code == 404


def test_browser_link_dies_with_the_report_and_site_login_can_make_it(setup, monkeypatch):
    from core import auth_manager as am
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)
    mgr = am.AuthManager(db_path=path)
    am._auth_manager = mgr
    mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True)
    from routes.auth import auth_bp
    app = make_app()
    app.register_blueprint(auth_bp)
    rid = reports.create(reports.normalize_report(REPORT), chat_id=CHAT)['id']
    client = app.test_client()
    client.post('/login', data={'login': 'owner', 'password': 'ownerpass'})
    resp = link_call(client, 'POST', rid)
    assert resp.status_code == 200, 'вошедший в сайт делает ссылку со страницы /tg/report/<id>'
    page = client.get(f'/tg/report/{rid}').get_data(as_text=True)
    assert resp.get_json()['link'] in page, 'страница сайта видит открытую ссылку'
    token = resp.get_json()['link'].rsplit('/', 1)[1]
    with db.read() as conn:
        assert conn.execute('SELECT created_by FROM tg_report_links WHERE token=?', (token,)).fetchone()[0] == 'site:owner'
    assert reports.by_link(token, now_ts=time.time() + reports.TTL_DAYS * 86400 + 60) is None, 'срок отчёта — срок ссылки'
    reports.delete(rid)
    assert client.get(f'/r/{token}').status_code == 404 and reports.link_token(rid) is None


def test_bot_note_api_only_for_engine_key(setup, monkeypatch):
    from flask import Flask
    from routes.bot_api import bot_api_bp
    from kultura_bot import site_api
    app = Flask('bot_api_note_test')
    app.register_blueprint(bot_api_bp)
    principal = type('P', (), {'token_id': 'st_engine'})()
    monkeypatch.setattr(site_api, 'verify_engine', lambda raw: principal if raw == 'kmcp_engine' else None)
    client = app.test_client()
    assert client.post('/api/bot/note', json={'chat_id': CHAT, 'text': 'x'}).status_code == 401
    auth = {'Authorization': 'Bearer kmcp_engine'}
    assert client.post('/api/bot/note', json={'chat_id': 'abc', 'text': 'x'}, headers=auth).status_code == 400
    assert client.post('/api/bot/note', json={'chat_id': CHAT, 'text': '  '}, headers=auth).status_code == 400
    resp = client.post('/api/bot/note', json={'chat_id': GROUP, 'text': 'доля = 42%; metrics.avg_rating; '
                                                                         'https://evil.example/x'}, headers=auth)
    assert resp.status_code == 200 and resp.headers['Cache-Control'] == 'no-store'
    note = reports.get(resp.get_json()['id'])
    assert (note['chat_id'], note['token_id'], note['kind']) == (GROUP, 'st_engine', 'note')
    assert note['body']['text'] == 'доля = 42%; metrics.avg_rating; [ссылка удалена]'


def test_report_tool_in_full_mode_only_and_errors_are_text(setup):
    from core.mcp import registry
    from core.mcp.spec import allowed_in_mode
    registry.use_modules(None)
    spec = {t.name: t for t in registry.all_tools()}['common_report_send']
    assert spec.destructive and spec.open_world and not spec.read_only
    assert allowed_in_mode(spec, 'full') and not allowed_in_mode(spec, 'read') and not allowed_in_mode(spec, 'draft')
    assert spec.input_schema['properties']['report']['properties']['sections']['items']['properties']['chart'] \
        is spec.input_schema['properties']['report']['properties']['sections']['items']['properties']['chart']
    from core.mcp.bridge import ToolError
    from core.mcp.tools.common import _report_send
    principal = type('P', (), {'token_id': 'st_x'})()
    with pytest.raises(ToolError, match='Отчёт: sections'):
        _report_send({'report': dict(REPORT, sections=[]), 'chat_id': CHAT}, principal)
    result = _report_send({'report': REPORT, 'chat_id': CHAT}, principal)
    assert result['report_id'].startswith('rep_') and result['message_id'] == 77
    chart_tool = {t.name: t for t in registry.all_tools()}['common_chart_send']
    assert 'how' in chart_tool.input_schema['properties']


# ------------------------------------------------------------------ замечания независимой проверки 2026-10-24

@pytest.mark.parametrize('link', ['https://beerkultura.ru:x@evil.example/login', 'https://beerkultura.ru:443@evil.example',
                                  'https://"@evil.example/login', 'https://<@evil.example/login',
                                  'https://beerkultura.ru"@evil.example/login'])
def test_filters_and_page_see_the_real_host(setup, link):
    for flt in (full_filter, page_filter):
        assert 'evil.example' not in flt(f'[Войти]({link})') and 'evil.example' not in flt(link), (flt, link)
    raw = dict(REPORT, sections=[{'heading': 'Р', 'text': f'[Войти]({link})', 'how': link}])
    view = reports.view({'id': 'rep_' + '0' * 22, 'created_at': '', 'body': reports.normalize_report(
        raw, text_filter=full_filter, page_filter=page_filter)})
    assert 'evil.example' not in json.dumps(view), 'ни ссылкой, ни текстом'


def test_title_on_page_and_how_from_summary_and_caption(setup):
    raw = dict(REPORT, title='A.Le Coq: +40% к августу',
               summary='**Итог +58,0%.**\n\n>> Как считается\n>> (327 − 207) / 207')
    result = tg_send.send_report(raw, chat_id=CHAT, text_filter=full_filter, page_filter=page_filter)
    body = reports.get(result['report_id'])['body']
    assert body['title'] == 'A.Le Coq: +40% к августу', 'заголовок только на странице — узкий фильтр'
    assert body['summary'] == '**Итог +58,0%.**' and body['how'].endswith('(327 − 207) / 207')
    assert 'Как считается' not in setup['tg'].calls[-1][1]['caption']
    result = tg_send.send_chart(dict(FIXTURES)['check'], chat_id=CHAT,
                                caption='Итог +83 ₽.\n\n>> Как считается\n>> 1 509 − 1 426 = 83')
    assert setup['tg'].calls[-1][1]['caption'] == f'Итог +83{NB}₽.'
    assert reports.get(result['how']['id'])['body']['text'] == '1 509 − 1 426 = 83', 'блок из подписи — запиской'


def test_plain_fallback_keeps_how_link_whole(setup):
    mp, tg = setup['monkeypatch'], setup['tg']
    mp.setattr(bot_settings, 'MINIAPP_SHORT_NAME', 'app')
    tg.replies = [{'ok': False, 'description': "Bad Request: can't parse entities"}]
    result = tg_send.send_chart(dict(FIXTURES)['check'], chat_id=CHAT, caption='Итог.', how='формула')
    caption = tg.calls[-1][1]['caption']
    assert caption == f'Итог.\nКак считается: https://t.me/MCPkulturabot/app?startapp={result["how"]["id"]}'
    tg.replies = [{'ok': False, 'description': "Bad Request: can't parse entities"}]
    long_caption = 'я' * 985 + '.'          # со ссылкой в HTML влезает (1000), простым текстом с адресом — нет
    result = tg_send.send_chart(dict(FIXTURES)['check'], chat_id=CHAT, caption=long_caption, how='формула')
    fields = tg.calls[-1][1]
    assert 'Как считается' not in fields['caption'] and len(fields['caption']) <= 1024
    assert [b['text'] for b in json.loads(fields['reply_markup'])['inline_keyboard'][0]][-1] == 'Как считается', \
        'ссылка не влезла в простую подпись — кнопкой, а не обрезанным адресом'


def test_report_data_time_is_never_build_time():
    """Решение 2026-10-25: время сборки за время данных не выдаём. Не передано — самое раннее
    время графиков, где оно указано; график без своего времени не в счёт; нет ни одного — нет."""
    base = {'title': 'Итог', 'summary': 'Итог.', 'source': 'iiko'}
    belgium, check = dict(FIXTURES)['belgium'], dict(FIXTURES)['check']     # 14 сен и 28 сен
    no_time = {k: v for k, v in check.items() if k != 'data_at'}
    two = dict(base, sections=[{'heading': 'Чек', 'chart': check}, {'heading': 'Бельгия', 'chart': belgium},
                               {'heading': 'Без времени', 'chart': no_time}])
    assert reports.normalize_report(two)['data_at'] == '2026-09-14T00:58:00+03:00', 'самое раннее из графиков'
    only_untimed = dict(base, sections=[{'heading': 'Без времени', 'chart': no_time}])
    assert reports.normalize_report(only_untimed)['data_at'] is None, 'время отправки графика — не время данных'
    text_only = dict(base, sections=[{'heading': 'Текст', 'text': 'Итог.'}])
    assert reports.normalize_report(text_only)['data_at'] is None
    assert reports.normalize_report(dict(text_only, data_at='2026-10-01T09:00'))['data_at'] == '2026-10-01T09:00:00+03:00'
    with pytest.raises(reports.ReportError):
        reports.normalize_report(dict(text_only, data_at='вчера'))
    rid = reports.create(reports.normalize_report(text_only), chat_id=CHAT)['id']
    assert reports.view(reports.get(rid))['data_at'] is None


def test_view_titles_keep_numbers_together():
    """Заголовок отчёта и разделов — с неразрывными пробелами: «−24 тыс. ₽» не рвётся переносом."""
    raw = {'title': 'Сеть −24 тыс. ₽ (1 931 тыс. ₽)', 'summary': 'Итог.', 'source': 'iiko',
           'sections': [{'heading': 'Кременчугская 503 тыс. ₽, −16,4 %', 'text': 'Чек 1 509 ₽.'}]}
    rid = reports.create(reports.normalize_report(raw), chat_id=CHAT)['id']
    view = reports.view(reports.get(rid))
    assert view['title'] == f'Сеть −24{NB}тыс.{NB}₽ (1{NB}931{NB}тыс.{NB}₽)'
    assert view['sections'][0]['heading'] == f'Кременчугская 503{NB}тыс.{NB}₽, −16,4{NB}%'
    assert view['sections'][0]['html'] == f'Чек 1{NB}509{NB}₽.'
    assert reports.get(rid)['body']['title'] == 'Сеть −24 тыс. ₽ (1 931 тыс. ₽)', 'хранится как прислано'

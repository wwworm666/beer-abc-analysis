"""
Мини-приложение Telegram «Графики» (routes/tg_miniapp.py, core/tg_webapp_auth.py, core/tg_charts.py).

Что проверяется:
- initData: правильная подпись проходит; подделанное поле, чужой токен, выброшенная из
  строки проверки signature, старая (больше суток) и «из будущего» auth_date, повтор поля,
  битый hash — отказ. Подпись в тестах считается своей реализацией по документации
  Telegram, а не функцией модуля, — иначе тест проверял бы код сам собой;
- API /api/tg/charts/<id>: 200 с описанием; 401 без заголовка, с чужой схемой, с
  подделкой и с просроченной initData; 403 человеку не из списка (с его id в ответе);
  404 на неизвестный, битый и просроченный id; 503 без токена бота; initData не попадает
  в журнал; ответ не кэшируется;
- страница /tg/chart открыта без входа на сайт, подключает официальный
  telegram-web-app.js, локальные ECharts и шрифт, отдаёт CSP; dev-страница и PNG фикстуры —
  только в debug;
- хранилище: id из secrets.token_urlsafe (22 символа), срок 90 дней, просроченное не
  отдаётся и вычищается;
- формат описания: ошибки называют поле, умолчания scale/decimals, фильтр текста.

Запуск: `py -3 -m pytest tests/test_tg_miniapp.py`.
"""
import hashlib
import hmac
import json
import logging
import os
import sys
import time
from urllib.parse import urlencode

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from flask import Flask  # noqa: E402

from core import tg_charts, tg_webapp_auth  # noqa: E402
from core.mcp import db  # noqa: E402
from core.tg_chart_fixtures import FIXTURES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = 'test-mcp-bot-token'
OWNER = 670033096
STRANGER = 111222333


def telegram_hash(fields, token):
    """Подпись так, как её описывает Telegram: секрет = HMAC(ключ "WebAppData", токен),
    hash = hex(HMAC(секрет, строка проверки)); в строке проверки все поля, кроме hash."""
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()) if k != 'hash')
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def init_data(user_id=OWNER, auth_date=None, token=TOKEN, start_param=None, signature=True, tamper=None):
    fields = {
        'auth_date': str(int(time.time()) if auth_date is None else auth_date),
        'query_id': 'AAHdF6IQAAAAAN0XohDhrOrc',
        'user': json.dumps({'id': user_id, 'first_name': 'Анна', 'username': 'anna'}, ensure_ascii=False,
                           separators=(',', ':')),
    }
    if signature:
        fields['signature'] = 'Zm9vYmFyLXNpZ25hdHVyZS1lZDI1NTE5LXRlc3Q'
    if start_param:
        fields['start_param'] = start_param
    fields['hash'] = telegram_hash(fields, token)
    if tamper:
        fields.update(tamper)
    return urlencode(fields)


@pytest.fixture
def store(tmp_path):
    db.set_db_path(str(tmp_path / 'mcp.db'))
    yield
    db.set_db_path(None)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('TELEGRAM_MCP_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('TG_MINIAPP_ALLOWED_IDS', f'{OWNER}, 5550001')


def make_app(debug=False):
    from core.auth_guard import init_auth
    from routes.tg_miniapp import tg_miniapp_bp
    app = Flask('tg_miniapp_test', template_folder=os.path.join(ROOT, 'templates'),
                static_folder=os.path.join(ROOT, 'static'))
    app.register_blueprint(tg_miniapp_bp)
    app.jinja_env.globals['app_version'] = 'abc1234'
    init_auth(app)              # глобальный гейт сайта: страница и API обязаны быть открыты без входа
    app.debug = debug
    return app


def saved_chart(name='belgium'):
    return tg_charts.create(tg_charts.normalize(dict(FIXTURES)[name]), chat_id=str(OWNER))['id']


def get(client, chart_id, data=None, scheme='tma'):
    headers = {} if data is None else {'Authorization': f'{scheme} {data}'}
    return client.get(f'/api/tg/charts/{chart_id}', headers=headers)


# ------------------------------------------------------------------ initData

def test_valid_init_data_with_signature_passes():
    data = init_data(start_param='abc_DEF-123')
    viewer = tg_webapp_auth.validate(data, TOKEN)
    assert viewer['user_id'] == OWNER and viewer['user']['first_name'] == 'Анна'
    assert viewer['start_param'] == 'abc_DEF-123'
    assert tg_webapp_auth.validate(init_data(signature=False), TOKEN)['user_id'] == OWNER, 'старый формат без signature'


def test_signature_stays_in_data_check_string():
    """Из строки проверки убирается только hash: подпись, посчитанная без signature, не проходит."""
    fields = {'auth_date': str(int(time.time())), 'user': json.dumps({'id': OWNER}), 'signature': 'c2lnbmF0dXJl'}
    without = {k: v for k, v in fields.items() if k != 'signature'}
    fields['hash'] = telegram_hash(without, TOKEN)
    with pytest.raises(tg_webapp_auth.InitDataError) as err:
        tg_webapp_auth.validate(urlencode(fields), TOKEN)
    assert err.value.code == 'bad_hash'


@pytest.mark.parametrize('data, code', [
    (init_data(tamper={'user': json.dumps({'id': STRANGER, 'first_name': 'Анна'})}), 'bad_hash'),   # подменён человек
    (init_data(tamper={'auth_date': str(int(time.time()) + 10)}), 'bad_hash'),                  # подменено время
    (init_data(token='other-bot-token'), 'bad_hash'),                                           # подпись другого бота
    (init_data(tamper={'hash': 'A' * 64}), 'bad_hash'),                                         # не hex в нижнем регистре
    (init_data(tamper={'hash': 'не hex'}), 'bad_hash'),
    (init_data() + '&hash=' + '0' * 64, 'malformed'),                                           # повтор поля
    ('auth_date=1&user=%7B%7D', 'bad_hash'),                                                    # без hash
    ('не строка запроса', 'malformed'),
    ('', 'missing'),
])
def test_forged_init_data_is_refused(data, code):
    with pytest.raises(tg_webapp_auth.InitDataError) as err:
        tg_webapp_auth.validate(data, TOKEN)
    assert err.value.code == code


def test_expired_and_future_init_data_are_refused():
    now = time.time()
    day = tg_webapp_auth.INIT_DATA_MAX_AGE_S
    assert tg_webapp_auth.validate(init_data(auth_date=int(now) - day + 60), TOKEN, now=now)['user_id'] == OWNER
    with pytest.raises(tg_webapp_auth.InitDataError) as err:
        tg_webapp_auth.validate(init_data(auth_date=int(now) - day - 1), TOKEN, now=now)
    assert err.value.code == 'expired'
    with pytest.raises(tg_webapp_auth.InitDataError) as err:
        tg_webapp_auth.validate(init_data(auth_date=int(now) + 3600), TOKEN, now=now)
    assert err.value.code == 'expired'


def test_init_data_without_user_is_refused():
    fields = {'auth_date': str(int(time.time())), 'query_id': 'q'}
    fields['hash'] = telegram_hash(fields, TOKEN)
    with pytest.raises(tg_webapp_auth.InitDataError) as err:
        tg_webapp_auth.validate(urlencode(fields), TOKEN)
    assert err.value.code == 'no_user'


def test_allowed_ids_and_header_parsing(monkeypatch):
    monkeypatch.setenv('TG_MINIAPP_ALLOWED_IDS', ' 670033096,5550001 ; -100123, abc, ２２, 7')
    assert tg_webapp_auth.allowed_user_ids() == {670033096, 5550001, 7}, 'группы, мусор и не-ASCII цифры — мимо'
    monkeypatch.delenv('TG_MINIAPP_ALLOWED_IDS')
    assert tg_webapp_auth.allowed_user_ids() == frozenset()
    assert tg_webapp_auth.init_data_from_header('tma a=1&b=2') == 'a=1&b=2'
    assert tg_webapp_auth.init_data_from_header('TMA a=1') == 'a=1'
    assert tg_webapp_auth.init_data_from_header('Bearer a=1') == ''
    assert tg_webapp_auth.init_data_from_header(None) == ''


# ------------------------------------------------------------------ API

def test_api_returns_chart_to_allowed_user(store, env):
    chart_id = saved_chart('revenue')
    client = make_app().test_client()
    resp = get(client, chart_id, init_data())
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['chart']['title'] == 'Выручка · 2–13 сен к 19–30 авг 2026'
    assert body['chart']['series'][0]['data'] == [534000, 514000, 503000, 380000], 'точные значения, без округления'
    assert body['expires_at'] > body['created_at']
    assert resp.headers['Cache-Control'] == 'no-store' and 'Authorization' in resp.headers['Vary']


def test_api_status_codes(store, env, monkeypatch):
    chart_id = saved_chart()
    client = make_app().test_client()
    # 401: нет initData, чужая схема, подделка, просрочка
    for resp, code in ((get(client, chart_id), 'init_data_missing'),
                       (get(client, chart_id, init_data(), scheme='Bearer'), 'init_data_missing'),
                       (get(client, chart_id, init_data(token='other')), 'init_data_invalid'),
                       (get(client, chart_id, init_data(tamper={'user': json.dumps({'id': OWNER})})), 'init_data_invalid'),
                       (get(client, chart_id, init_data(auth_date=int(time.time()) - 2 * 86400)), 'init_data_expired')):
        assert resp.status_code == 401 and resp.get_json()['code'] == code, (code, resp.get_json())
    # 403: подпись верна, но человека нет в списке — его id в ответе, чтобы передать владельцу
    resp = get(client, chart_id, init_data(user_id=STRANGER))
    assert resp.status_code == 403 and resp.get_json() == {
        'error': 'Нет доступа к графикам: передайте владельцу свой Telegram ID', 'code': 'not_allowed',
        'user_id': STRANGER}
    # 404: неизвестный, битый и просроченный id
    for bad in ('A' * 22, 'short', 'x' * 65, chart_id[:-1] + ('A' if chart_id[-1] != 'A' else 'B')):
        resp = get(client, bad, init_data())
        assert resp.status_code == 404 and resp.get_json()['code'] == 'chart_not_found', bad
    with monkeypatch.context() as m:                             # через 90 дней срок вышел
        m.setattr(time, 'time', lambda: 4_000_000_000)
        resp = get(client, chart_id, init_data(auth_date=4_000_000_000 - 5))
        assert resp.status_code == 404 and resp.get_json()['code'] == 'chart_not_found'
    # 503: на сервере нет токена — проверить подпись нечем (без initData всё равно 401)
    monkeypatch.delenv('TELEGRAM_MCP_BOT_TOKEN')
    assert get(client, chart_id, init_data()).status_code == 503
    assert get(client, chart_id).status_code == 401


def test_api_never_logs_init_data(store, env, caplog):
    chart_id = saved_chart()
    client = make_app().test_client()
    good, forged, stranger = init_data(), init_data(token='other'), init_data(user_id=STRANGER)
    with caplog.at_level(logging.DEBUG):
        for data in (good, forged, stranger):
            get(client, chart_id, data)
    text = caplog.text
    for data in (good, forged, stranger):
        assert data not in text
        assert data.rsplit('hash=', 1)[1] not in text, 'подпись не пишется даже кусками'
    assert 'query_id' not in text and 'AAHdF6IQ' not in text


# ------------------------------------------------------------------ страницы

def test_page_is_public_and_loads_official_script_and_local_assets(store):
    client = make_app().test_client()
    resp = client.get('/tg/chart?id=abc')
    assert resp.status_code == 200, 'страница открыта без входа на сайт'
    html = resp.get_data(as_text=True)
    assert '<script src="https://telegram.org/js/telegram-web-app.js"></script>' in html
    assert '/static/libs/echarts-5.5.1/echarts.min.js' in html and '/static/tg_chart/app.js?v=abc1234' in html
    assert 'cdn.' not in html and 'googleapis' not in html, 'ECharts и шрифт — свои, без внешних CDN'
    assert "script-src 'self' https://telegram.org" in resp.headers['Content-Security-Policy']
    assert resp.headers['Referrer-Policy'] == 'no-referrer'
    for path in ('static/libs/echarts-5.5.1/echarts.min.js', 'static/tg_chart/charts.js', 'static/tg_chart/app.js',
                 'static/tg_chart/tg_chart.css', 'static/fonts/ibm-plex-mono/IBMPlexMono-Regular.subset.woff2',
                 'static/fonts/ibm-plex-mono/IBMPlexMono-Bold.subset.woff2'):
        assert os.path.isfile(os.path.join(ROOT, path)), path
    api = client.get('/api/tg/charts/' + 'A' * 22)
    assert api.status_code == 401 and api.get_json()['code'] == 'init_data_missing', 'гейт сайта не перехватывает API'


def test_echarts_vendored_version():
    with open(os.path.join(ROOT, 'static/libs/echarts-5.5.1/echarts.min.js'), encoding='utf-8') as f:
        text = f.read()
    assert '"5.5.1"' in text, 'в static лежит ECharts 5.5.1'


def test_dev_pages_only_in_debug(store):
    prod = make_app(debug=False).test_client()
    assert prod.get('/tg/chart/dev').status_code == 404
    assert prod.get('/tg/chart/dev/belgium.png').status_code == 404
    dev = make_app(debug=True).test_client()
    resp = dev.get('/tg/chart/dev?theme=dark')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-theme="dark"' in html and 'telegram-web-app.js' not in html
    payload = json.loads(html.split('id="tg-chart-data">', 1)[1].split('</script>', 1)[0])
    assert [c['name'] for c in payload['charts']] == ['liters', 'belgium', 'check', 'revenue', 'desserts', 'days']
    assert dev.get('/tg/chart/dev/nope.png').status_code == 404


# ------------------------------------------------------------------ хранилище

def test_store_ids_ttl_and_purge(store):
    spec = tg_charts.normalize(dict(FIXTURES)['check'])
    rec = tg_charts.create(spec, chat_id='-1001', token_id='st_1')
    assert len(rec['id']) == 22 and tg_charts.valid_chart_id(rec['id']) and not tg_charts.valid_chart_id(rec['id'] + '\n')
    other = tg_charts.create(spec)
    assert other['id'] != rec['id']
    row = tg_charts.get(rec['id'])
    assert row['spec'] == spec and row['chat_id'] == '-1001' and row['token_id'] == 'st_1' and row['sent'] == 0
    assert row['expires_ts'] - row['created_ts'] == 90 * 86400
    assert tg_charts.get(rec['id'], now_ts=row['expires_ts']) is None, 'в последнюю секунду срока уже нет'
    tg_charts.mark_sent(rec['id'], 42)
    assert tg_charts.get(rec['id'])['message_id'] == 42 and tg_charts.get(rec['id'])['sent'] == 1
    # новая запись вычищает просроченные
    with db.write() as conn:
        conn.execute('UPDATE tg_charts SET expires_ts=1 WHERE id=?', (other['id'],))
    tg_charts.create(spec)
    with db.read() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM tg_charts WHERE id=?', (other['id'],)).fetchone()['n'] == 0
    tg_charts.delete(rec['id'])
    assert tg_charts.get(rec['id']) is None


def test_store_daily_limit(store):
    spec = tg_charts.normalize(dict(FIXTURES)['check'])
    tg_charts.create(spec, daily_limit=2)
    tg_charts.create(spec, daily_limit=2)
    with pytest.raises(tg_charts.ChartLimitError):
        tg_charts.create(spec, daily_limit=2)


# ------------------------------------------------------------------ формат описания

def test_fixtures_normalize_with_documented_defaults():
    specs = {name: tg_charts.normalize(raw) for name, raw in FIXTURES}
    assert specs['liters']['decimals'] == 1 and specs['liters']['scale'] == 1
    assert specs['belgium']['scale'] == 1000 and specs['belgium']['decimals'] == 0, 'рубли от 100 000 — в тысячах'
    assert specs['check']['scale'] == 1 and specs['check']['base_category'] == 0 and specs['check']['additive'] is False
    assert specs['desserts']['unit_forms'] == ['порция', 'порции', 'порций']
    assert specs['liters']['groups'][1] == {'key': 'g1', 'label': 'Фасовка', 'tags': ['бут', 'ж/б']}
    assert specs['days']['categories'][0] == {'label': '2026-07-01'} and len(specs['days']['categories']) == 92
    assert [s['key'] for s in specs['revenue']['series']] == ['s0', 's1']
    assert specs['belgium']['data_at'] == '2026-09-14T00:58:00+03:00'
    utc = tg_charts.normalize(dict(dict(FIXTURES)['belgium'], data_at='2026-09-13T21:58:00Z'))
    assert utc['data_at'] == '2026-09-14T00:58:00+03:00', 'UTC переводится в МСК'
    naive = tg_charts.normalize(dict(dict(FIXTURES)['belgium'], data_at='2026-09-14T00:58'))
    assert naive['data_at'] == '2026-09-14T00:58:00+03:00', 'без пояса — МСК'


def test_defaults_rules():
    assert tg_charts.default_decimals([252.9, 28.7, 13]) == 1
    assert tg_charts.default_decimals([0.33, 1.5]) == 2
    assert tg_charts.default_decimals([406.70000000000005]) == 2, 'хвост арифметики обрезан до 2 знаков'
    assert tg_charts.default_scale('₽', [99_999]) == 1
    assert tg_charts.default_scale('₽', [-100_000]) == 1000
    assert tg_charts.default_scale('₽', [250_000_000]) == 1_000_000
    assert tg_charts.default_scale('л', [5_000_000]) == 1


@pytest.mark.parametrize('patch, message', [
    ({'kind': 'pie'}, 'kind'),
    ({'title': '   '}, 'title: обязательное поле'),
    ({'source': ''}, 'source: обязательное поле'),
    ({'series': [{'name': 'a', 'role': 'current', 'data': [1, 2, 3, 4, 5, 6, 7]}]}, 'нужно 2'),
    ({'series': [{'name': 'a', 'role': 'current', 'data': [1] * 7}, {'name': 'b', 'role': 'part', 'data': [1] * 7}]},
     'role=current'),
    ({'series': [{'name': 'a', 'role': 'current', 'data': [1] * 6}, {'name': 'b', 'role': 'base', 'data': [1] * 7}]},
     '6 значений, а категорий 7'),
    ({'series': [{'name': 'a', 'role': 'current', 'data': [1] * 6 + [float('nan')]},
                 {'name': 'b', 'role': 'base', 'data': [1] * 7}]}, 'конечным'),
    ({'series': [{'name': 'a', 'role': 'current', 'data': [1] * 6 + [True]},
                 {'name': 'b', 'role': 'base', 'data': [1] * 7}]}, 'число или null'),
    ({'series': [{'name': 'a', 'role': 'current', 'data': [1] * 6 + [2e12]},
                 {'name': 'b', 'role': 'base', 'data': [1] * 7}]}, 'единицы'),
    ({'categories': ['a'] * 7}, 'повторяются'),
    ({'categories': ['a'] * 13}, 'не больше 12'),
    ({'scale': 100}, 'scale'),
    ({'decimals': 5}, 'decimals'),
    ({'groups': [{'label': 'Кран', 'tags': ['кран']}]}, 'только у рейтинга'),
    ({'base_category': 'Квак'}, 'только у rating и stack'),
    ({'data_at': 'вчера'}, 'ISO 8601'),
    ({'unit_forms': ['порция']}, 'три формы'),
    ({'colour': 'red'}, 'лишние поля'),
])
def test_bad_specs_name_the_field(patch, message):
    raw = dict(FIXTURES)['belgium']
    with pytest.raises(tg_charts.ChartSpecError) as err:
        tg_charts.normalize(dict(raw, **patch))
    assert message in str(err.value), str(err.value)


def test_kind_specific_rules():
    liters = dict(FIXTURES)['liters']
    with pytest.raises(tg_charts.ChartSpecError, match='null нельзя'):
        tg_charts.normalize(dict(liters, series=[dict(liters['series'][0], data=[None] + liters['series'][0]['data'][1:])]))
    with pytest.raises(tg_charts.ChartSpecError, match='не меньше 0'):
        tg_charts.normalize(dict(liters, series=[dict(liters['series'][0], data=[-1] + liters['series'][0]['data'][1:])]))
    with pytest.raises(tg_charts.ChartSpecError, match='нет категорий с метками'):
        tg_charts.normalize(dict(liters, groups=[{'label': 'Кеги', 'tags': ['кега']}]))
    days = dict(FIXTURES)['days']
    with pytest.raises(tg_charts.ChartSpecError, match='по возрастанию'):
        tg_charts.normalize(dict(days, categories=list(reversed(days['categories']))))
    with pytest.raises(tg_charts.ChartSpecError, match='такой даты нет'):
        tg_charts.normalize(dict(days, categories=['2026-02-30'] + days['categories'][1:]))
    with pytest.raises(tg_charts.ChartSpecError, match='YYYY-MM-DD'):
        tg_charts.normalize(dict(days, categories=['1 июля'] + days['categories'][1:]))
    # один сорт на кране и в бутылке — разные категории (различает метка)
    two = dict(liters, categories=[{'label': 'Квак', 'tag': 'кран'}, {'label': 'Квак', 'tag': 'бут'}],
               series=[{'name': 'Литры', 'role': 'value', 'data': [3, 2]}],
               groups=[{'label': 'Кран', 'tags': ['кран']}])
    assert len(tg_charts.normalize(two)['categories']) == 2


def test_text_filter_applies_to_every_string():
    raw = dict(FIXTURES)['revenue']
    raw = dict(raw, title='Выручка http://evil.example/login', note='см. evil.example',
               categories=[dict(raw['categories'][0], note='зайди на evil.example')] + raw['categories'][1:])
    spec = tg_charts.normalize(raw, text_filter=lambda t: t.replace('evil.example', '[ссылка удалена]'))
    assert 'evil' not in json.dumps(spec, ensure_ascii=False)
    assert spec['categories'][0]['note'] == 'зайди на [ссылка удалена]'

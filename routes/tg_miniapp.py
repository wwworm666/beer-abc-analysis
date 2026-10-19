"""Мини-приложение Telegram «Графики» бота @MCPkulturabot (docs/tg-miniapp.md).

    GET /tg/chart                  страница мини-приложения; данных в ней нет — их
                                   приносит API по initData
    GET /api/tg/charts/<chart_id>  описание графика; только с заголовком
                                   Authorization: tma <initData>
    GET /tg/chart/dev              только при debug: графики-фикстуры прототипа
                                   (kultura_bot/charts/fixtures.py) в обеих темах
    GET /tg/chart/dev/<name>.png   только при debug: PNG фикстуры тем же рендером,
                                   что уходит в Telegram

Ответы API (порядок проверок — такой, чтобы без входа ничего не узнать):
    401 {code: init_data_missing}    нет заголовка или он пустой
    503 {code: not_configured}       нет токена бота (/admin/mcp или TELEGRAM_MCP_BOT_TOKEN)
    401 {code: init_data_invalid}    подпись не сходится, строка битая, нет пользователя
    401 {code: init_data_expired}    auth_date старше суток (или из будущего)
    404 {code: chart_not_found}      нет такого id или прошло 90 дней
    403 {code: not_allowed}          человек не в чате, куда отправлен график (kultura_bot/charts/access.py)
    503 {code: access_check_failed}  Telegram не ответил на проверку участия в группе
    200 {chart, created_at, expires_at}

Все четыре эндпоинта — в PUBLIC_ENDPOINTS (core/auth_guard.py): у Telegram нет
cookie сайта, API проверяет initData сам. initData в журнал не пишется. Токен бота —
на странице «Доступ агентов» (kultura_bot/credentials.py, API /api/admin/mcp/bot в
routes/mcp.py, только администратор); кнопка и прочее — kultura_bot/settings.py.
"""
import io
import logging
from datetime import datetime

from flask import Blueprint, abort, current_app, jsonify, make_response, render_template, request, send_file

from core import msk_time
from kultura_bot import credentials
from kultura_bot.charts import access as chart_access, spec as chart_spec, webapp_auth
from kultura_bot.charts.fixtures import FIXTURES

log = logging.getLogger('tg-charts')

tg_miniapp_bp = Blueprint('tg_miniapp', __name__)

# Скрипты — только свои и официальный telegram-web-app.js; стили ECharts пишет
# в атрибуты style, поэтому 'unsafe-inline' для стилей. Данные графика — JSON
# в <script type="application/json">: он не исполняется и под CSP не попадает.
PAGE_CSP = ("default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'none'")

_INIT_DATA_CODES = {'missing': 'init_data_missing', 'expired': 'init_data_expired'}


def _page(html: str):
    resp = make_response(html)
    resp.headers['Content-Security-Policy'] = PAGE_CSP
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


def _api_error(status: int, code: str, message: str, **extra):
    resp = jsonify(dict({'error': message, 'code': code}, **extra))
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Vary'] = 'Authorization'
    return resp


@tg_miniapp_bp.route('/tg/chart')
def chart_page():
    return _page(render_template('tg_chart.html', mode='app', payload={'bot': credentials.bot_username()}))


@tg_miniapp_bp.route('/api/tg/charts/<chart_id>')
def chart_api(chart_id):
    init_data = webapp_auth.init_data_from_header(request.headers.get('Authorization'))
    if not init_data:
        return _api_error(401, 'init_data_missing', 'Откройте график из Telegram')
    token = credentials.bot_token()
    if not token:
        return _api_error(503, 'not_configured', 'Мини-приложение не настроено на сервере')
    try:
        viewer = webapp_auth.validate(init_data, token)
    except webapp_auth.InitDataError as exc:
        code = _INIT_DATA_CODES.get(exc.code, 'init_data_invalid')
        log.info('[TG-CHART] 401 %s', code)
        return _api_error(401, code, str(exc))
    record = chart_spec.get(chart_id)
    if record is None:
        return _api_error(404, 'chart_not_found', 'График не найден или срок хранения (90 дней) истёк')
    try:
        allowed = chart_access.can_view(record['chat_id'], viewer['user_id'], token)
    except chart_access.AccessCheckError:
        return _api_error(503, 'access_check_failed', 'Не удалось проверить, что вы в чате: Telegram не ответил. '
                          'Попробуйте ещё раз')
    if not allowed:
        log.info('[TG-CHART] 403 пользователь %s не в чате графика', viewer['user_id'])
        return _api_error(403, 'not_allowed', 'График открывают участники чата, куда бот его прислал')
    expires_at = datetime.fromtimestamp(record['expires_ts'], msk_time.MOSCOW_TZ).isoformat(timespec='seconds')
    resp = jsonify({'chart': record['spec'], 'created_at': record['created_at'], 'expires_at': expires_at})
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Vary'] = 'Authorization'
    return resp


def _fixtures():
    return [{'name': name, 'chart': chart_spec.normalize(raw)} for name, raw in FIXTURES]


@tg_miniapp_bp.route('/tg/chart/dev')
def chart_dev():
    if not current_app.debug:
        abort(404)
    theme = request.args.get('theme') if request.args.get('theme') in ('light', 'dark') else None
    mode = 'png-preview' if request.args.get('png') == '1' else 'dev'
    return _page(render_template('tg_chart.html', mode='dev', theme=theme,
                                 payload={'charts': _fixtures(), 'view': mode}))


@tg_miniapp_bp.route('/tg/chart/dev/<name>.png')
def chart_dev_png(name):
    if not current_app.debug:
        abort(404)
    raw = dict(FIXTURES).get(name)
    if raw is None:
        abort(404)
    from kultura_bot.charts import png as chart_png
    theme = 'dark' if request.args.get('theme') == 'dark' else 'light'
    png = chart_png.render_png(chart_spec.normalize(raw), theme=theme)
    return send_file(io.BytesIO(png), mimetype='image/png', download_name=f'{name}.png')

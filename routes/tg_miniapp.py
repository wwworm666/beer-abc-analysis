"""Мини-приложение Telegram «Графики» бота @MCPkulturabot (docs/tg-miniapp.md).

    GET /tg/chart                  страница мини-приложения; данных в ней нет — их
                                   приносит API по initData. ?id= (или start_param) —
                                   id графика или отчёта/записки (rep_…, kultura_bot/links.py)
    GET /api/tg/charts/<chart_id>  описание графика; только с заголовком
                                   Authorization: tma <initData>
    GET /api/tg/reports/<report_id>  отчёт или записка «Как считается» (kultura_bot/charts/
                                   reports.py) — те же проверки, что у графика
    GET /tg/report/<report_id>     та же запись страницей сайта — обычный вход сайта
                                   (запас для групп без короткого имени мини-приложения
                                   и для компьютера); без входа — страница входа
    POST|DELETE /api/tg/reports/<report_id>/link
                                   ссылка для браузера (2026-10-28): сделать (та же, если
                                   уже есть) или закрыть. Кто: администратор сайта (вход
                                   сайта) или участник чата записи, подключённый к боту
                                   (initData + kultura_bot/access.actor_for) — тот, кому бот
                                   отвечает; остальные участники группы — 403 not_owner
    GET /r/<token>                 запись по ссылке для браузера — без входа, тот же дизайн,
                                   что у страницы сайта; закрыли или истёк срок — 404
    GET /tg/chart/dev              только при debug: графики-фикстуры прототипа
                                   (kultura_bot/charts/fixtures.py) в обеих темах
    GET /tg/chart/dev/<name>.png   только при debug: PNG фикстуры тем же рендером,
                                   что уходит в Telegram

Ответы API (порядок проверок — такой, чтобы без входа ничего не узнать):
    401 {code: init_data_missing}    нет заголовка или он пустой
    503 {code: not_configured}       нет токена бота (/admin/mcp или TELEGRAM_MCP_BOT_TOKEN)
    401 {code: init_data_invalid}    подпись не сходится, строка битая, нет пользователя
    401 {code: init_data_expired}    auth_date старше суток (или из будущего)
    404 {code: chart_not_found}      нет такого id или прошло 90 дней (у отчётов — report_not_found)
    403 {code: not_allowed}          человек не в чате, куда отправлен график (kultura_bot/charts/access.py)
    503 {code: access_check_failed}  Telegram не ответил на проверку участия в группе
    200 {chart, created_at, expires_at}

Страница мини-приложения, оба API и dev-страницы — в PUBLIC_ENDPOINTS (core/auth_guard.py):
у Telegram нет cookie сайта, API проверяет initData сам. /tg/report/<id> — не публичная:
её открывает только вошедший в сайт. /r/<token> открыт всем, у кого есть ссылка (код —
128 бит, отдельный от id; ссылку делает и закрывает только администратор). initData и коды
ссылок этот модуль в журнал не пишет; путь /r/<код> видят журналы доступа gunicorn и Caddy
на сервере сайта (как любой адрес запроса). Токен бота —
на странице «Доступ агентов» (kultura_bot/credentials.py, API /api/admin/mcp/bot в
routes/mcp.py, только администратор); кнопка и прочее — kultura_bot/settings.py.
"""
import io
import logging
from datetime import datetime

from flask import Blueprint, abort, current_app, jsonify, make_response, render_template, request, send_file

from core import msk_time
from kultura_bot import credentials
from kultura_bot.charts import access as chart_access, reports, spec as chart_spec, webapp_auth
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
NOT_OWNER_TEXT = ('Ссылку для браузера делает и закрывает администратор: тот, кто подключён к боту на странице '
                  '«Доступ агентов»')


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


def _auth(what: str):
    """initData из заголовка -> (viewer, token, None) или (None, None, ответ-ошибка)."""
    init_data = webapp_auth.init_data_from_header(request.headers.get('Authorization'))
    if not init_data:
        return None, None, _api_error(401, 'init_data_missing', f'Откройте {what} из Telegram')
    token = credentials.bot_token()
    if not token:
        return None, None, _api_error(503, 'not_configured', 'Мини-приложение не настроено на сервере')
    try:
        viewer = webapp_auth.validate(init_data, token)
    except webapp_auth.InitDataError as exc:
        code = _INIT_DATA_CODES.get(exc.code, 'init_data_invalid')
        log.info('[TG-CHART] 401 %s', code)
        return None, None, _api_error(401, code, str(exc))
    return viewer, token, None


def _member_error(chat_id: str, viewer, token: str, what: str):
    """None — человек в чате записи; иначе ответ-ошибка (403 или 503)."""
    try:
        allowed = chart_access.can_view(chat_id, viewer['user_id'], token)
    except chart_access.AccessCheckError:
        return _api_error(503, 'access_check_failed', 'Не удалось проверить, что вы в чате: Telegram не ответил. '
                          'Попробуйте ещё раз')
    if not allowed:
        log.info('[TG-CHART] 403 пользователь %s не в чате записи', viewer['user_id'])
        return _api_error(403, 'not_allowed', f'{what} открывают участники чата, куда бот его прислал')
    return None


def _json(payload):
    resp = jsonify(payload)
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Vary'] = 'Authorization'
    return resp


def _expires(record) -> str:
    return datetime.fromtimestamp(record['expires_ts'], msk_time.MOSCOW_TZ).isoformat(timespec='seconds')


@tg_miniapp_bp.route('/api/tg/charts/<chart_id>')
def chart_api(chart_id):
    viewer, token, error = _auth('график')
    if error is not None:
        return error
    record = chart_spec.get(chart_id)
    if record is None:
        return _api_error(404, 'chart_not_found', 'График не найден или срок хранения (90 дней) истёк')
    error = _member_error(record['chat_id'], viewer, token, 'График')
    if error is not None:
        return error
    return _json({'chart': record['spec'], 'created_at': record['created_at'], 'expires_at': _expires(record)})


@tg_miniapp_bp.route('/api/tg/reports/<report_id>')
def report_api(report_id):
    viewer, token, error = _auth('отчёт')
    if error is not None:
        return error
    record = reports.get(report_id)
    if record is None:
        return _api_error(404, 'report_not_found', 'Отчёт не найден или срок хранения (90 дней) истёк')
    error = _member_error(record['chat_id'], viewer, token, 'Отчёт')
    if error is not None:
        return error
    can_share = _bot_user(viewer)
    return _json({'report': reports.view(record), 'expires_at': _expires(record),
                  'link': _link(record) if can_share else '', 'can_share': can_share})


def _bot_user(viewer) -> bool:
    """Человек из Telegram подключён к боту (администратор сайта, kultura_bot/access.py): только он
    делает и закрывает ссылку для браузера — участник группы, вышедший из неё, не унесёт доступ."""
    from kultura_bot import access as bot_access
    return bot_access.actor_for(str(viewer['user_id'])) is not None


def _link(record) -> str:
    """Действующая ссылка для браузера записи или ''."""
    token = reports.link_token(record['id'])
    return reports.link_url(token) if token else ''


def _link_access(report_id: str):
    """Кто просит ссылку для браузера: вошедший в сайт (страница /tg/report/<id>) или участник чата
    записи (мини-приложение, initData). -> (запись, кто, None) или (None, None, ответ-ошибка).
    Без входа сначала проверяется initData: не войдя, нельзя узнать даже, есть ли такая запись."""
    from core.auth_guard import current_user
    user = current_user()
    if user:
        if not user.get('is_admin'):
            return None, None, _api_error(403, 'not_owner', NOT_OWNER_TEXT)
        record = reports.get(report_id)
        if record is None:
            return None, None, _api_error(404, 'report_not_found', 'Отчёт не найден или срок хранения (90 дней) истёк')
        return record, 'site:' + str(user.get('login') or user.get('id') or ''), None
    viewer, token, error = _auth('отчёт')
    if error is not None:
        return None, None, error
    record = reports.get(report_id)
    if record is None:
        return None, None, _api_error(404, 'report_not_found', 'Отчёт не найден или срок хранения (90 дней) истёк')
    error = _member_error(record['chat_id'], viewer, token, 'Отчёт')
    if error is not None:
        return None, None, error
    if not _bot_user(viewer):
        return None, None, _api_error(403, 'not_owner', NOT_OWNER_TEXT)
    return record, f'tg:{viewer["user_id"]}', None


@tg_miniapp_bp.route('/api/tg/reports/<report_id>/link', methods=['POST', 'DELETE'])
def report_link(report_id):
    """Ссылка для браузера: POST — сделать (есть — та же), DELETE — закрыть."""
    record, who, error = _link_access(report_id)
    if error is not None:
        return error
    if request.method == 'DELETE':
        reports.drop_link(record['id'])
        log.info('[TG-REPORT] ссылка для браузера закрыта: %s (%s)', record['id'], who)
        return _json({'link': ''})
    try:
        token = reports.make_link(record['id'], by=who)
    except reports.ReportError as exc:          # запись истекла между проверкой и записью
        return _api_error(404, 'report_not_found', str(exc))
    log.info('[TG-REPORT] ссылка для браузера: %s (%s)', record['id'], who)
    return _json({'link': reports.link_url(token), 'expires_at': _expires(record)})


@tg_miniapp_bp.route('/r/<token>')
def shared_report(token):
    """Запись по ссылке для браузера: без входа, тот же шаблон и site.js, что у /tg/report/<id>."""
    record = reports.by_link(token)
    if record is None:
        resp = _page(render_template('tg_chart.html', mode='site', payload={'gone': True},
                                     title='Ссылка не работает'))
        resp.status_code = 404
    else:
        payload = {'report': reports.view(record, shared=True), 'expires_at': _expires(record), 'shared': True}
        resp = _page(render_template('tg_chart.html', mode='site', payload=payload,
                                     title=record['body'].get('title') or 'Отчёт'))
    resp.headers['Cache-Control'] = 'private, no-store'      # цифры владельца: ни браузер, ни прокси не хранят
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow'      # ссылку не индексируют, даже если она где-то всплыла
    return resp


@tg_miniapp_bp.route('/tg/report/<report_id>')
def report_page(report_id):
    """Отчёт или записка страницей сайта: вход — обычный вход сайта (гейт core/auth_guard)."""
    record = reports.get(report_id)
    if record is None:
        abort(404)
    from core.auth_guard import current_user
    can_share = bool((current_user() or {}).get('is_admin'))
    payload = {'report': reports.view(record), 'expires_at': _expires(record),
               'link': _link(record) if can_share else '', 'can_share': can_share}
    resp = _page(render_template('tg_chart.html', mode='site', payload=payload,
                                 title=record['body'].get('title') or 'Отчёт'))
    resp.headers['Cache-Control'] = 'private, no-store'      # цифры владельца: браузер не хранит
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

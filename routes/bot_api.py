"""API для сервера бота @MCPkulturabot (Амстердам): настройки, привязки, отчёт.

Сайт к Anthropic не обращается (он в России, где API Anthropic недоступен): разговор ведёт
сервер бота (kultura_bot/engine/) и спрашивает сайт здесь. Вход — только по ключу сервера
бота в заголовке Authorization: Bearer kmcp_… (kultura_bot/site_api.verify_engine); другие
MCP-токены сюда не пускают: агент не получает секреты бота. Сессии сайта не нужно —
эндпоинты в core/auth_guard.PUBLIC_ENDPOINTS, агенту по MCP закрыты (EXCLUDED в
core/mcp/tools/common.py).

    GET  /api/bot/config                {telegram: {token, username}, anthropic_key, paused}
    POST /api/bot/link                  {code, tg_user_id, tg_name} -> {ok, text}
    GET  /api/bot/actor/<tg_user_id>    {actor: {tg_user_id, user_id, login, display_name} | null}
    POST /api/bot/report                {status, usage} -> {ok}
    POST /api/bot/note                  {chat_id, text, title?} -> {id, expires_at}
                                        записка «Как считается» к ответу (kultura_bot/charts/
                                        reports.py): сервер бота вырезает её из ответа модели и
                                        ставит в сообщении ссылку (kultura_bot/links.py)
    GET  /api/bot/replied?chat_id=&message_id=
                                        {found: {kind: report|chart, id, title, text} | null} —
                                        что было в сообщении бота, на которое человек ответил в
                                        Telegram (продолжение работы, 2026-10-29): отчёт или
                                        график этого чата текстом для модели (reports.reply_context)

401 — нет ключа или не тот; 400 — ошибка ввода. Ответы не кэшируются (Cache-Control:
no-store): в config — секреты.
"""
import logging

from flask import Blueprint, jsonify, request

from core.mcp.auth import bearer_token
from kultura_bot import access, credentials, settings, site_api

log = logging.getLogger(__name__)

bot_api_bp = Blueprint('bot_api', __name__)

MAX_BODY_BYTES = 256 * 1024
TG_NAME_MAX = 100


def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _error(status: int, text: str):
    return _no_store(jsonify({'error': text})), status


def _engine():
    """Principal сервера бота или None."""
    return site_api.verify_engine(bearer_token(request))


def _denied():
    return _error(401, 'Нужен ключ сервера бота: на странице «Доступ агентов» выпустите команду установки')


def _body():
    if (request.content_length or 0) > MAX_BODY_BYTES:
        raise ValueError('Слишком большое тело запроса')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('Тело запроса — объект JSON')
    return data


@bot_api_bp.route('/api/bot/config', methods=['GET'])
def config():
    if _engine() is None:
        return _denied()
    return _no_store(jsonify(credentials.engine_view()))


@bot_api_bp.route('/api/bot/link', methods=['POST'])
def link():
    if _engine() is None:
        return _denied()
    try:
        data = _body()
        code, tg_user_id = str(data.get('code') or '').strip(), str(data.get('tg_user_id') or '').strip()
        if not tg_user_id.isdigit() or len(code) > 64:
            raise ValueError('Нужны code и tg_user_id (число)')
    except ValueError as exc:
        return _error(400, str(exc))
    answer = access.link_by_code(code, tg_user_id, str(data.get('tg_name') or '')[:TG_NAME_MAX])
    return _no_store(jsonify(answer))


@bot_api_bp.route('/api/bot/actor/<tg_user_id>', methods=['GET'])
def actor(tg_user_id):
    if _engine() is None:
        return _denied()
    if not tg_user_id.isdigit():
        return _error(400, 'tg_user_id — число')
    return _no_store(jsonify({'actor': access.actor_for(tg_user_id)}))


@bot_api_bp.route('/api/bot/report', methods=['POST'])
def report():
    if _engine() is None:
        return _denied()
    try:
        site_api.accept_report(_body())
    except ValueError as exc:
        return _error(400, str(exc))
    return _no_store(jsonify({'ok': True}))


@bot_api_bp.route('/api/bot/replied')
def replied():
    """Отчёт или график, который бот отправил сообщением message_id в чат chat_id, — текстом для модели."""
    if _engine() is None:
        return _denied()
    from kultura_bot.charts import reports
    chat_id = str(request.args.get('chat_id') or '').strip()
    message_id = str(request.args.get('message_id') or '').strip()
    if not chat_id.lstrip('-').isdigit() or len(chat_id) > 21:
        return _error(400, 'chat_id — число (у групп со знаком минус)')
    if not message_id.isdigit() or len(message_id) > 12:
        return _error(400, 'message_id — число')
    return _no_store(jsonify({'found': reports.reply_context(chat_id, int(message_id))}))


@bot_api_bp.route('/api/bot/note', methods=['POST'])
def note():
    principal = _engine()
    if principal is None:
        return _denied()
    from core.mcp.tools.common import strip_foreign_urls
    from kultura_bot.charts import reports
    try:
        data = _body()
        chat_id = str(data.get('chat_id') or '').strip()
        if not chat_id.lstrip('-').isdigit() or len(chat_id) > 21:
            raise ValueError('chat_id — число (у групп со знаком минус)')
        body = reports.normalize_note(data.get('text'), title=data.get('title'), page_filter=strip_foreign_urls)
    except (ValueError, reports.ReportError) as exc:
        return _error(400, str(exc))
    try:
        record = reports.create(body, chat_id=chat_id, token_id=principal.token_id,
                                daily_limit=settings.REPORT_DAILY_LIMIT)
    except reports.ReportLimitError as exc:
        return _error(429, f'Не больше {settings.REPORT_DAILY_LIMIT} записок и отчётов в сутки — сегодня уже '
                           f'{exc.used}')
    return _no_store(jsonify({'id': record['id'], 'expires_at': record['expires_at']}))

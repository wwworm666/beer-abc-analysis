"""API для сервера бота @MCPkulturabot (Амстердам): настройки, привязки, отчёт.

Сайт к Anthropic не обращается (он в России, где API Anthropic недоступен): разговор ведёт
сервер бота (kultura_bot/engine/) и спрашивает сайт здесь. Вход — только по ключу сервера
бота в заголовке Authorization: Bearer kmcp_… (kultura_bot/site_api.verify_engine); другие
MCP-токены сюда не пускают: агент не получает секреты бота. Сессии сайта не нужно —
эндпоинты в core/auth_guard.PUBLIC_ENDPOINTS, агенту по MCP закрыты (EXCLUDED в
core/mcp/tools/common.py).

    GET  /api/bot/config                {telegram: {token, username}, anthropic_key, paused}
    POST /api/bot/link                  {code, tg_user_id, tg_name} -> {ok, text}
    GET  /api/bot/actor/<tg_user_id>?username=&name=
                                        {actor: {tg_user_id, user_id, login, display_name, guest?} | null}:
                                        администратор сайта или человек из settings.TELEGRAM_USERNAMES
                                        (user_id null, login '@ник', guest true; kultura_bot/access.py)
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
    GET  /api/bot/chat-format?chat_id=  {format: rich|plain|null, rich: bool} — вид ответов в чате
                                        (2026-11-06, команда /rich бота): выбор чата, итог с учётом
                                        умолчания и выключателя (kultura_bot/store.chat_rich)
    POST /api/bot/chat-format           {chat_id, format: rich|plain, tg_user_id} -> {ok, format, rich}
    POST /api/bot/rich-demo             {chat_id} -> {message_id, chart_id} — пример графика богатым
                                        сообщением для /rich (kultura_bot/rich_demo.py): картинки рисует сайт
    POST /api/bot/journal               {records: [...]} -> {saved: [uid], rejected: [{uid, error}]} —
                                        журнал вопросов и ответов (kultura_bot/journal.py, 2026-11-06)
    POST /api/bot/journal/feedback      {chat_id, message_id, tg_user_id, reactions} -> {found} —
                                        реакция человека на сообщение бота: оценка записи журнала

Вопросы со страницы сайта /research (2026-11-09, kultura_bot/web.py): сервер бота берёт их, как
сообщения Telegram, и отвечает тем же кодом; графики и отчёт ложатся в вопрос, а не в Telegram.

    GET  /api/bot/web/next              {job: {id, thread_id, chat_id, question, mode, fast, actor,
                                        history} | null} — следующий вопрос (сервер берёт, когда есть
                                        свободное место)
    POST /api/bot/web/<qid>/beat        {progress} -> {stop, gone} — ход работы для страницы; в ответ —
                                        нажали ли «Остановить» (или вопрос уже закрыт)
    POST /api/bot/web/<qid>/card        {tool, args} -> ответ инструмента {content, isError} — график
                                        (common_chart_send) или отчёт (common_report_send) вопроса
    POST /api/bot/web/<qid>/finish      {status, answer, how, notice, ask, shown, error, cost_usd, steps,
                                        fast_steps} -> {ok, status}

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
    # Ник и имя из сообщения: по ним сайт впервые узнаёт человека из settings.TELEGRAM_USERNAMES
    # (kultura_bot/access.guest_for); кривой ник просто не подойдёт.
    username = str(request.args.get('username') or '')[:64]
    tg_name = str(request.args.get('name') or '')[:TG_NAME_MAX]
    return _no_store(jsonify({'actor': access.actor_for(tg_user_id, username, tg_name)}))


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


def _chat_id(value) -> str:
    chat_id = str(value or '').strip()
    if not chat_id.lstrip('-').isdigit() or len(chat_id) > 21:
        raise ValueError('chat_id — число (у групп со знаком минус)')
    return chat_id


@bot_api_bp.route('/api/bot/chat-format', methods=['GET'])
def chat_format_get():
    """Вид ответов в чате: выбор (/rich) и итог — слать ли богатые сообщения."""
    if _engine() is None:
        return _denied()
    from kultura_bot import store
    try:
        chat_id = _chat_id(request.args.get('chat_id'))
    except ValueError as exc:
        return _error(400, str(exc))
    return _no_store(jsonify({'format': store.get_chat_format(chat_id), 'rich': store.chat_rich(chat_id)}))


@bot_api_bp.route('/api/bot/chat-format', methods=['POST'])
def chat_format_set():
    """Запомнить выбор вида ответов (кнопка под примерами /rich)."""
    if _engine() is None:
        return _denied()
    from kultura_bot import store
    try:
        data = _body()
        chat_id = _chat_id(data.get('chat_id'))
        fmt = str(data.get('format') or '')
        by = str(data.get('tg_user_id') or '')[:20]
        store.set_chat_format(chat_id, fmt, by=by)
    except ValueError as exc:
        return _error(400, str(exc))
    log.info('[BOT] вид ответов в чате %s: %s (выбрал %s)', chat_id, fmt, by or '—')
    return _no_store(jsonify({'ok': True, 'format': fmt, 'rich': store.chat_rich(chat_id)}))


@bot_api_bp.route('/api/bot/rich-demo', methods=['POST'])
def rich_demo():
    """Пример графика богатым сообщением (команда /rich): рисует и шлёт сайт — у него браузер для картинок."""
    principal = _engine()
    if principal is None:
        return _denied()
    from core.mcp.tools.common import _strip_foreign_links
    from kultura_bot import rich_demo as demo
    from kultura_bot.charts import send as chart_send
    try:
        chat_id = _chat_id(_body().get('chat_id'))
    except ValueError as exc:
        return _error(400, str(exc))
    try:
        sent = chart_send.send_chart(demo.CHART_SPEC, chat_id=chat_id, caption=demo.CHART_CAPTION, how=demo.CHART_HOW,
                                     token_id=principal.token_id, text_filter=_strip_foreign_links, rich=True,
                                     rich_fallback=False)
    except chart_send.ChartSendError as exc:
        return _error(502, str(exc))
    return _no_store(jsonify({'message_id': sent.get('message_id'), 'chart_id': sent.get('chart_id'),
                              'format': sent.get('format')}))


# ------------------------------------------------------------------ вопросы со страницы сайта

@bot_api_bp.route('/api/bot/web/next', methods=['GET'])
def web_next():
    """Следующий вопрос со страницы /research (или null)."""
    if _engine() is None:
        return _denied()
    from kultura_bot import web
    return _no_store(jsonify({'job': web.claim()}))


@bot_api_bp.route('/api/bot/web/<qid>/beat', methods=['POST'])
def web_beat(qid):
    """Ход работы над вопросом -> страница; в ответ — нажали ли «Остановить»."""
    if _engine() is None:
        return _denied()
    from kultura_bot import web
    try:
        progress = _body().get('progress')
    except ValueError as exc:
        return _error(400, str(exc))
    return _no_store(jsonify(web.beat(qid, progress)))


@bot_api_bp.route('/api/bot/web/<qid>/card', methods=['POST'])
def web_card(qid):
    """График или отчёт вопроса с сайта: та же проверка, что у отправки в Telegram, но карточка
    ложится в вопрос. Ошибка проверки — ответ инструмента с isError (модель исправит)."""
    principal = _engine()
    if principal is None:
        return _denied()
    from core.mcp.tools.common import _strip_foreign_links, strip_foreign_urls
    from kultura_bot import web
    try:
        data = _body()
        result = web.add_card(qid, str(data.get('tool') or ''), data.get('args'), token_id=principal.token_id,
                              text_filter=_strip_foreign_links, page_filter=strip_foreign_urls)
    except (ValueError, web.WebError) as exc:
        return _error(400, str(exc))
    return _no_store(jsonify(result))


@bot_api_bp.route('/api/bot/web/<qid>/files/<int:n>', methods=['GET'])
def web_file(qid, n):
    """Файл вопроса с сайта — серверу бота, пока вопрос в работе: картинка (уменьшенная, если была
    велика), PDF или текст таблицы (kultura_bot/web_files.py)."""
    if _engine() is None:
        return _denied()
    from flask import Response
    from kultura_bot import web
    found = web.engine_file(qid, n)
    if found is None:
        return _error(404, 'Файла нет: вопрос закрыт или удалён')
    resp = Response(found['data'], mimetype=found['mime'])
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bot_api_bp.route('/api/bot/web/<qid>/finish', methods=['POST'])
def web_finish(qid):
    """Итог вопроса: ответ, «Как считается», кнопки следующего шага, расход или текст ошибки."""
    if _engine() is None:
        return _denied()
    from kultura_bot import web
    try:
        result = web.finish(qid, _body())
    except (ValueError, web.WebError) as exc:
        return _error(400, str(exc))
    return _no_store(jsonify(result))


@bot_api_bp.route('/api/bot/journal', methods=['POST'])
def journal_save():
    """Записи журнала вопросов и ответов от сервера бота (пачкой; повтор по uid безопасен)."""
    if _engine() is None:
        return _denied()
    from kultura_bot import journal
    try:
        result = journal.save(_body().get('records'))
    except (ValueError, journal.JournalError) as exc:
        return _error(400, str(exc))
    return _no_store(jsonify(result))


@bot_api_bp.route('/api/bot/journal/feedback', methods=['POST'])
def journal_feedback():
    """Реакция под сообщением бота -> оценка записи журнала."""
    if _engine() is None:
        return _denied()
    from kultura_bot import journal
    try:
        data = _body()
        message_id = data.get('message_id')
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise ValueError('message_id — число')
        found = journal.set_feedback(str(data.get('chat_id') or ''), message_id, str(data.get('tg_user_id') or ''),
                                     data.get('reactions'))
    except (ValueError, journal.JournalError) as exc:
        return _error(400, str(exc))
    return _no_store(jsonify({'found': found}))

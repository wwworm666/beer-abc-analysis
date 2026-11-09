"""Журнал вопросов и ответов бота @MCPkulturabot: страница и API администратора (2026-11-06).

Записи присылает сервер бота (POST /api/bot/journal, routes/bot_api.py); хранит
kultura_bot/journal.py. Здесь — только чтение и удаление, только администратор сайта
(@admin_required). Каждому — только свои вопросы (решение владельца 2026-11-09: «история у каждого
своя, между клиентами не передаём»): чужая запись — как будто её нет (404), удалить можно только свою.
Владелец сайта (первый действующий администратор, core/auth_manager.owner_id) видит вопросы всех: «сделай,
чтобы я видел журнал всех пользователей» (2026-11-09).

    GET    /admin/bot/journal                    страница (templates/admin_bot_journal.html)
    GET    /api/admin/bot/journal                список с итогами: days, login, status, rating, q,
                                                 limit, offset; с uid — запись целиком
    GET    /api/admin/bot/journal.csv            выгрузка выбранного для таблицы (до 5000 строк)
    DELETE /api/admin/bot/journal/<uid>          удалить запись (например, в вопрос попало лишнее)

Агентам тот же список — инструментом common_bot_journal (core/mcp/tools/common.py, только на полном
коннекторе /mcp, только записи владельца токена); выгрузка и удаление — только человеком на странице.
У самого бота этого инструмента нет (settings.HIDDEN_TOOLS).
"""
from flask import Blueprint, Response, jsonify, render_template, request

from core.auth_guard import admin_required, current_user

bot_journal_bp = Blueprint('bot_journal', __name__)


def _own():
    """Чьи записи видит вошедший: владелец сайта — всех (None), остальные — только свои (логин сайта — тот
    же, что в записи журнала)."""
    from kultura_bot import journal
    user = current_user() or {}
    return journal.scope_for(user.get('id'), user.get('login'))


def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bot_journal_bp.route('/admin/bot/journal', methods=['GET'])
@admin_required
def journal_page():
    from kultura_bot import journal
    return render_template('admin_bot_journal.html', keep_days=journal.keep_days(), sees_all=_own() is None)


@bot_journal_bp.route('/api/admin/bot/journal', methods=['GET'])
@admin_required
def journal_list():
    from kultura_bot import journal
    uid = (request.args.get('uid') or '').strip()
    if uid:
        record = journal.get(uid, only_login=_own())
        if record is None:
            return _no_store(jsonify({'error': 'Записи нет: удалена или срок хранения вышел'})), 404
        return _no_store(jsonify({'record': record}))
    try:
        return _no_store(jsonify(journal.query(request.args.to_dict(), only_login=_own())))
    except journal.JournalError as exc:
        return _no_store(jsonify({'error': str(exc)})), 400


@bot_journal_bp.route('/api/admin/bot/journal.csv', methods=['GET'])
@admin_required
def journal_csv():
    from kultura_bot import journal
    try:
        text = journal.csv_text(request.args.to_dict(), only_login=_own())
    except journal.JournalError as exc:
        return _no_store(jsonify({'error': str(exc)})), 400
    resp = Response(text, mimetype='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = 'attachment; filename="bot-journal.csv"'
    return _no_store(resp)


@bot_journal_bp.route('/api/admin/bot/journal/<uid>', methods=['DELETE'])
@admin_required
def journal_delete(uid):
    from kultura_bot import journal
    if not journal.delete(uid, only_login=_own()):
        return _no_store(jsonify({'error': 'Записи нет'})), 404
    return _no_store(jsonify({'ok': True}))

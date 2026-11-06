"""Журнал вопросов и ответов бота @MCPkulturabot: страница и API администратора (2026-11-06).

Записи присылает сервер бота (POST /api/bot/journal, routes/bot_api.py); хранит
kultura_bot/journal.py. Здесь — только чтение и удаление, только администратор сайта
(@admin_required): в журнале цифры сети, зарплаты и вопросы других администраторов.

    GET    /admin/bot/journal                    страница (templates/admin_bot_journal.html)
    GET    /api/admin/bot/journal                список с итогами: days, login, status, rating, q,
                                                 limit, offset; с uid — запись целиком
    GET    /api/admin/bot/journal.csv            выгрузка выбранного для таблицы (до 5000 строк)
    DELETE /api/admin/bot/journal/<uid>          удалить запись (например, в вопрос попало лишнее)

Агентам владельца тот же список — инструментом common_bot_journal (core/mcp/tools/common.py,
только на полном коннекторе /mcp); выгрузка и удаление — только человеком на странице.
"""
from flask import Blueprint, Response, jsonify, render_template, request

from core.auth_guard import admin_required

bot_journal_bp = Blueprint('bot_journal', __name__)


def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bot_journal_bp.route('/admin/bot/journal', methods=['GET'])
@admin_required
def journal_page():
    from kultura_bot import journal
    return render_template('admin_bot_journal.html', keep_days=journal.keep_days())


@bot_journal_bp.route('/api/admin/bot/journal', methods=['GET'])
@admin_required
def journal_list():
    from kultura_bot import journal
    uid = (request.args.get('uid') or '').strip()
    if uid:
        record = journal.get(uid)
        if record is None:
            return _no_store(jsonify({'error': 'Записи нет: удалена или срок хранения вышел'})), 404
        return _no_store(jsonify({'record': record}))
    try:
        return _no_store(jsonify(journal.query(request.args.to_dict())))
    except journal.JournalError as exc:
        return _no_store(jsonify({'error': str(exc)})), 400


@bot_journal_bp.route('/api/admin/bot/journal.csv', methods=['GET'])
@admin_required
def journal_csv():
    from kultura_bot import journal
    try:
        text = journal.csv_text(request.args.to_dict())
    except journal.JournalError as exc:
        return _no_store(jsonify({'error': str(exc)})), 400
    resp = Response(text, mimetype='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = 'attachment; filename="bot-journal.csv"'
    return _no_store(resp)


@bot_journal_bp.route('/api/admin/bot/journal/<uid>', methods=['DELETE'])
@admin_required
def journal_delete(uid):
    from kultura_bot import journal
    if not journal.delete(uid):
        return _no_store(jsonify({'error': 'Записи нет'})), 404
    return _no_store(jsonify({'ok': True}))

"""Страница kultura.research на сайте: вопросы боту из браузера (решение владельца 2026-11-09).

Вопрос уходит в очередь (kultura_bot/web.py); отвечает сервер бота в Амстердаме тем же кодом, что в
Telegram, — сайт к Claude не обращается. Только администратор сайта (@admin_required), как у бота;
каждый видит только свои беседы.

    GET    /research                              страница (templates/research.html)
    GET    /api/research/threads                  {threads, engine, fast, suggestions} — беседы, отвечает ли
                                                  сервер бота, есть ли быстрый режим, все готовые вопросы с
                                                  подсказками (страница показывает три случайных)
    GET    /api/research/threads/<thread_id>      {thread: {id, questions}} — беседа целиком
    DELETE /api/research/threads/<thread_id>      удалить беседу
    POST   /api/research/ask                      {question, mode: answer|report, fast, thread_id?, files?} ->
                                                  {question}; files — [{name, data: base64}] (картинки, PDF,
                                                  Excel, CSV, текст — kultura_bot/web_files.py)
    GET    /api/research/files/<qid>/<n>          файл вопроса — только тому, кто его приложил
    GET    /api/research/questions/<qid>          {question} — страница опрашивает раз в 2 с, пока он в работе
    POST   /api/research/questions/<qid>/stop     «Остановить» -> {question}

Тела POST — только JSON (заголовок Content-Type: application/json): форма с чужого сайта так не
отправит, а cookie сайта — SameSite=Lax (core/auth_guard.py). Агентам по MCP эти маршруты закрыты
(EXCLUDED в core/mcp/tools/common.py): спросить бота из агента — двойной расход Claude.
"""
import random
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, render_template, request

from core.auth_guard import admin_required, current_user

research_bp = Blueprint('research', __name__)

MAX_BODY_BYTES = 64 * 1024
FILE_INLINE = ('image', 'pdf')            # в браузере — открыть; остальное (Excel, CSV, текст) — скачать


def _ask_max_bytes() -> int:
    """Тело вопроса с файлами: все файлы в base64 (+ треть) и запас на текст и поля."""
    from kultura_bot import settings
    return int(settings.WEB_FILES_TOTAL_MAX_BYTES) * 4 // 3 + 256 * 1024


def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _error(status: int, text: str):
    return _no_store(jsonify({'error': text})), status


def _body(limit: int = MAX_BODY_BYTES):
    if (request.content_length or 0) > limit:
        raise ValueError('Слишком большое тело запроса')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('Тело запроса — объект JSON')
    return data


def _suggestions():
    """Все готовые вопросы (kultura_bot/settings.WEB_SUGGESTIONS): {question, hint}."""
    from kultura_bot import settings
    return [{'question': item['question'], 'hint': item.get('hint', '')} for item in settings.WEB_SUGGESTIONS]


def _pick_suggestions(rng=random):
    """Три (WEB_SUGGESTIONS_SHOWN) случайных вопроса — при каждом открытии страницы другие (решение владельца
    2026-11-09: «чередуй их случайным образом при открытии страницы»)."""
    from kultura_bot import settings
    pool = _suggestions()
    return rng.sample(pool, min(int(settings.WEB_SUGGESTIONS_SHOWN), len(pool)))


def _mb(value) -> str:
    return ('%g' % (int(value) / (1024 * 1024))).replace('.', ',')


def _times(value) -> str:
    """Множитель для текста: 2.0 -> «2», 2.5 -> «2,5»."""
    return ('%g' % float(value)).replace('.', ',')


@research_bp.route('/research', methods=['GET'])
@admin_required
def research_page():
    from kultura_bot import settings
    # Числа для «Как работает» — из настроек бота, а не из текста страницы. has_thread — открыта беседа
    # по ссылке (?t=): страница не рисуется сначала пустой (само значение в разметку не попадает).
    return render_template('research.html', question_budget=settings.QUESTION_BUDGET_USD,
                           report_budget=settings.REPORT_BUDGET_USD, user_budget=settings.USER_DAILY_BUDGET_USD,
                           fast_mode=settings.FAST_MODE, idle_minutes=settings.DIALOG_IDLE_MINUTES,
                           fast_speedup=_times(settings.FAST_SPEEDUP_UP_TO),
                           fast_price=_times(settings.FAST_PRICE_MULTIPLIER),
                           files_max=settings.WEB_FILES_MAX, file_max_bytes=settings.WEB_FILE_MAX_BYTES,
                           files_total_bytes=settings.WEB_FILES_TOTAL_MAX_BYTES,
                           file_max_mb=_mb(settings.WEB_FILE_MAX_BYTES), files_total_mb=_mb(settings.WEB_FILES_TOTAL_MAX_BYTES),
                           suggestions=_pick_suggestions(), has_thread=bool(request.args.get('t')))


@research_bp.route('/api/research/threads', methods=['GET'])
@admin_required
def research_threads():
    from kultura_bot import settings, web
    user = current_user()
    return _no_store(jsonify({'threads': web.threads(int(user['id'])), 'engine': web.engine_state(),
                              'fast': bool(settings.FAST_MODE), 'suggestions': _suggestions()}))


@research_bp.route('/api/research/threads/<thread_id>', methods=['GET'])
@admin_required
def research_thread(thread_id):
    from kultura_bot import web
    found = web.thread(int(current_user()['id']), thread_id)
    if found is None:
        return _error(404, 'Беседы нет: удалена или чужая')
    return _no_store(jsonify({'thread': found}))


@research_bp.route('/api/research/threads/<thread_id>', methods=['DELETE'])
@admin_required
def research_thread_delete(thread_id):
    from kultura_bot import web
    if not web.delete_thread(int(current_user()['id']), thread_id):
        return _error(404, 'Беседы нет')
    return _no_store(jsonify({'ok': True}))


@research_bp.route('/api/research/ask', methods=['POST'])
@admin_required
def research_ask():
    from kultura_bot import settings, web
    try:
        data = _body(_ask_max_bytes())
        question = web.ask(current_user(), data.get('question'), mode=data.get('mode') or 'answer',
                           fast=bool(data.get('fast')) and settings.FAST_MODE, thread_id=data.get('thread_id'),
                           files=data.get('files'))
    except (ValueError, web.WebError) as exc:
        return _error(400, str(exc))
    return _no_store(jsonify({'question': question}))


@research_bp.route('/api/research/files/<qid>/<int:n>', methods=['GET'])
@admin_required
def research_file(qid, n):
    """Файл вопроса — только тому, кто его приложил (чужой — 404, как будто его нет). Картинка и PDF
    открываются в браузере, таблица и текст скачиваются; тип — тот, что сайт определил сам."""
    from kultura_bot import web
    found = web.user_file(int(current_user()['id']), qid, n)
    if found is None:
        return _error(404, 'Файла нет: беседу удалили')
    resp = Response(found['data'], mimetype=found['mime'])
    disposition = 'inline' if found['kind'] in FILE_INLINE else 'attachment'
    resp.headers['Content-Disposition'] = f"{disposition}; filename*=UTF-8''{quote(found['name'])}"
    resp.headers['Cache-Control'] = 'private, max-age=86400'      # файл вопроса не меняется
    resp.headers['X-Content-Type-Options'] = 'nosniff'      # тип — наш (картинка, PDF, таблица, текст), не угадывать
    return resp


@research_bp.route('/api/research/questions/<qid>', methods=['GET'])
@admin_required
def research_question(qid):
    from kultura_bot import web
    found = web.get(int(current_user()['id']), qid)
    if found is None:
        return _error(404, 'Вопроса нет: беседу удалили')
    return _no_store(jsonify({'question': found}))


@research_bp.route('/api/research/questions/<qid>/stop', methods=['POST'])
@admin_required
def research_stop(qid):
    from kultura_bot import web
    found = web.stop(int(current_user()['id']), qid)
    if found is None:
        return _error(404, 'Вопроса нет')
    return _no_store(jsonify({'question': found}))

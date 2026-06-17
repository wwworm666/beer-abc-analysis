"""Эндпоинты open-check бота.

1. Ручной запуск ежедневной проверки:
   POST /api/admin/open-check/run-now
   Headers: X-Remote-Pass: <REMOTE_PASS>

2. Telegram webhook (команды /start, /status + кнопка подписки):
   POST /telegram/openbot/webhook           — точка входа для Telegram
   GET  /telegram/openbot/setup-webhook     — зарегистрировать webhook (1 раз после деплоя)
   GET  /telegram/openbot/webhook-info      — диагностика
   POST /telegram/openbot/delete-webhook    — снять webhook

В проде команды забираются через long-polling (webhook не доставляется из-за
ТСПУ, см. core/open_check_polling.py); эти эндпоинты — запасной путь.

Бот реализован на чистом requests (см. core/open_check_telegram.py), поэтому
async/run_async не нужен.
"""
import os

from flask import Blueprint, jsonify, request

from core.open_check_bot import run_check

open_check_bp = Blueprint('open_check', __name__)

_WEBHOOK_PATH = '/telegram/openbot/webhook'


@open_check_bp.route('/api/admin/open-check/run-now', methods=['POST'])
def open_check_run_now():
    expected = os.environ.get('REMOTE_PASS')
    if not expected:
        return jsonify({'error': 'REMOTE_PASS не настроен на сервере'}), 503
    if request.headers.get('X-Remote-Pass') != expected:
        return jsonify({'error': 'forbidden'}), 403
    try:
        result = run_check()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@open_check_bp.route(_WEBHOOK_PATH, methods=['POST'])
def openbot_webhook():
    from core import open_check_telegram as tg

    if not os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN'):
        return jsonify({'error': 'bot not configured'}), 503

    # Проверка секрета (Telegram присылает его в заголовке)
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != tg.webhook_secret():
        return jsonify({'error': 'forbidden'}), 403

    update = request.get_json(silent=True)
    if not update:
        return jsonify({'ok': True})  # пустой апдейт — игнор, но 200

    try:
        tg.handle_update(update)
    except Exception as e:
        print(f"[OPENBOT WEBHOOK ERROR] {e}")
        import traceback
        traceback.print_exc()
    # Telegram'у всегда отвечаем 200, иначе он будет ретраить
    return jsonify({'ok': True})


@open_check_bp.route('/telegram/openbot/setup-webhook', methods=['GET', 'POST'])
def openbot_setup_webhook():
    from core import open_check_telegram as tg

    if not os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN'):
        return jsonify({'error': 'bot not configured'}), 503

    base_url = (request.args.get('base_url')
                or os.environ.get('API_BASE_URL')
                or os.environ.get('RENDER_EXTERNAL_URL')
                or request.url_root.rstrip('/'))
    webhook_url = f"{base_url}{_WEBHOOK_PATH}"

    res = tg.set_webhook(webhook_url)
    tg.set_my_commands()
    ok = bool(res and res.get('ok'))
    return jsonify({
        'success': ok,
        'webhook_url': webhook_url,
        'telegram_response': res,
    }), (200 if ok else 500)


@open_check_bp.route('/telegram/openbot/webhook-info', methods=['GET'])
def openbot_webhook_info():
    from core import open_check_telegram as tg
    if not os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN'):
        return jsonify({'error': 'bot not configured'}), 503
    return jsonify(tg.get_webhook_info() or {'error': 'no response'})


@open_check_bp.route('/telegram/openbot/delete-webhook', methods=['POST'])
def openbot_delete_webhook():
    from core import open_check_telegram as tg
    if not os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN'):
        return jsonify({'error': 'bot not configured'}), 503
    return jsonify(tg.delete_webhook() or {'error': 'no response'})

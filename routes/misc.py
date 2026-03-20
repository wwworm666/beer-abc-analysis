from flask import Blueprint, request, jsonify, render_template
import asyncio
import os
import json
import re
from core.olap_reports import OlapReports
from extensions import TAPS_DATA_PATH, TELEGRAM_BOT_ENABLED

misc_bp = Blueprint('misc', __name__)


@misc_bp.route('/api/test', methods=['GET', 'POST'])
def test_endpoint():
    """Тестовый endpoint"""
    print("[TEST] Test endpoint called!")
    return jsonify({'status': 'ok', 'message': 'Test successful'})

@misc_bp.route('/api/connection-status', methods=['GET'])
def connection_status():
    """API endpoint для проверки подключения к iiko API"""
    try:
        olap = OlapReports()
        is_connected = olap.connect()
        if is_connected:
            olap.disconnect()
            return jsonify({
                'status': 'connected',
                'message': 'Подключение к iiko API успешно'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Не удалось подключиться к iiko API'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка подключения: {str(e)}'
        }), 500


@misc_bp.route('/wiki')
def wiki():
    """Вики — документация системы (один markdown-файл → HTML-секции)"""
    import markdown

    wiki_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wiki', 'content.md')
    with open(wiki_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Разбиваем по заголовкам первого уровня (# Заголовок)
    parts = re.split(r'^# ', content, flags=re.MULTILINE)
    sections = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        title = part.split('\n', 1)[0].strip()
        body = part.split('\n', 1)[1] if '\n' in part else ''
        # ID из заголовка: кириллица → транслит не нужен, используем маппинг
        section_id = _wiki_slug(title)
        html_content = markdown.markdown(body, extensions=['tables', 'fenced_code'])
        sections.append({'id': section_id, 'title': title, 'html': html_content})

    return render_template('wiki.html', sections=sections)


# Маппинг заголовков вики → anchor id
_WIKI_SLUGS = {
    'О системе': 'about',
    'Дашборд': 'dashboard',
    'Дашборд сотрудника': 'employee',
    'ABC/XYZ анализ': 'abc-xyz',
    'Анализ проливов': 'draft',
    'Анализ акций': 'discounts',
    'Мониторинг кранов': 'taps',
    'Инструкция для барменов': 'taps-bartender',
    'Заказы и остатки': 'stocks',
    'График': 'schedule',
    'Расчёт премий': 'bonus',
    'Telegram-бот': 'telegram',
}


def _wiki_slug(title):
    """Возвращает anchor id для заголовка вики-секции."""
    return _WIKI_SLUGS.get(title, title.lower().replace(' ', '-'))


@misc_bp.route('/test_modules')
def test_modules():
    """Route to serve test_modules.html"""
    return render_template('test_modules.html')


@misc_bp.route('/api/debug/taps-data')
def debug_taps_data():
    """DEBUG: Показать содержимое файла taps_data.json"""
    try:
        info = {
            'file_path': TAPS_DATA_PATH,
            'file_exists': os.path.exists(TAPS_DATA_PATH),
            'file_size': os.path.getsize(TAPS_DATA_PATH) if os.path.exists(TAPS_DATA_PATH) else 0
        }

        if os.path.exists(TAPS_DATA_PATH):
            with open(TAPS_DATA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Показываем структуру первого уровня
            info['top_level_keys'] = list(data.keys()) if isinstance(data, dict) else f'Not a dict: {type(data)}'
            info['data_type'] = str(type(data))

            # Показываем полную структуру одного крана
            if isinstance(data, dict) and data:
                first_bar_key = list(data.keys())[0]
                first_bar = data[first_bar_key]

                info['structure'] = {
                    'bar_keys': list(first_bar.keys()) if isinstance(first_bar, dict) else 'not a dict'
                }

                # Если есть поле taps
                if isinstance(first_bar, dict) and 'taps' in first_bar:
                    taps = first_bar['taps']
                    if isinstance(taps, dict) and taps:
                        first_tap_key = list(taps.keys())[0]
                        first_tap = taps[first_tap_key]

                        info['tap_sample'] = {
                            'bar': first_bar_key,
                            'tap_number': first_tap_key,
                            'tap_data': first_tap
                        }

        return jsonify(info)

    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


# ============================================================
# TELEGRAM BOT WEBHOOK ENDPOINTS
# ============================================================

def run_async(coro):
    """Безопасный запуск асинхронной функции из синхронного контекста"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


@misc_bp.route('/telegram/webhook', methods=['POST'])
def telegram_webhook_handler():
    """
    Webhook endpoint для Telegram бота.
    Telegram отправляет сюда все обновления.
    """
    if not TELEGRAM_BOT_ENABLED:
        return jsonify({'error': 'Telegram bot not enabled'}), 503

    try:
        import telegram_webhook
        update_data = request.get_json()
        if not update_data:
            return jsonify({'error': 'No data'}), 400

        # Обрабатываем update асинхронно
        result = run_async(telegram_webhook.process_telegram_update(update_data))

        return jsonify({'ok': result})
    except Exception as e:
        print(f"[TELEGRAM WEBHOOK ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@misc_bp.route('/telegram/setup-webhook', methods=['POST', 'GET'])
def setup_telegram_webhook():
    """
    Установить webhook URL для Telegram бота.
    Вызывается один раз после деплоя на Render.
    """
    if not TELEGRAM_BOT_ENABLED:
        return jsonify({'error': 'Telegram bot not enabled'}), 503

    try:
        import telegram_webhook
        # Получаем базовый URL из запроса или используем Render URL
        if request.method == 'POST' and request.is_json:
            data = request.get_json() or {}
            base_url = data.get('base_url')
        else:
            base_url = request.args.get('base_url')

        if not base_url:
            # Пытаемся определить URL автоматически
            base_url = os.environ.get('RENDER_EXTERNAL_URL')
            if not base_url:
                # Если Render URL не найден, используем URL из запроса
                base_url = request.url_root.rstrip('/')

        webhook_url = f"{base_url}/telegram/webhook"

        result = run_async(telegram_webhook.set_webhook(webhook_url))

        if result:
            return jsonify({
                'success': True,
                'webhook_url': webhook_url,
                'message': 'Webhook установлен успешно'
            })
        else:
            return jsonify({'error': 'Failed to set webhook'}), 500

    except Exception as e:
        print(f"[TELEGRAM SETUP ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@misc_bp.route('/telegram/webhook-info', methods=['GET'])
def get_telegram_webhook_info():
    """Получить информацию о текущем webhook"""
    if not TELEGRAM_BOT_ENABLED:
        return jsonify({'error': 'Telegram bot not enabled'}), 503

    try:
        import telegram_webhook
        info = run_async(telegram_webhook.get_webhook_info())

        if info:
            return jsonify({
                'success': True,
                'webhook_info': info
            })
        else:
            return jsonify({'error': 'Failed to get webhook info'}), 500

    except Exception as e:
        print(f"[TELEGRAM INFO ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@misc_bp.route('/telegram/delete-webhook', methods=['POST'])
def delete_telegram_webhook():
    """
    Удалить webhook (для переключения обратно на polling режим).
    Используется для локальной разработки.
    """
    if not TELEGRAM_BOT_ENABLED:
        return jsonify({'error': 'Telegram bot not enabled'}), 503

    try:
        import telegram_webhook
        result = run_async(telegram_webhook.delete_webhook())

        if result:
            return jsonify({
                'success': True,
                'message': 'Webhook удален. Теперь можно использовать polling режим.'
            })
        else:
            return jsonify({'error': 'Failed to delete webhook'}), 500

    except Exception as e:
        print(f"[TELEGRAM DELETE ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

from flask import Flask, send_from_directory
from routes import register_blueprints
import subprocess
from datetime import datetime
import extensions

def get_git_commit_hash():
    """Получить короткий хеш текущего git commit для версионирования"""
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode('ascii').strip()
    except Exception:
        return datetime.now().strftime('%Y%m%d%H%M')


app = Flask(__name__)

# Версия приложения (git hash)
APP_VERSION = get_git_commit_hash()
extensions.APP_VERSION = APP_VERSION

# Делаем версию доступной во всех шаблонах
app.jinja_env.globals['app_version'] = APP_VERSION

# Регистрируем все blueprints
register_blueprints(app)


@app.route('/static/manifest.json')
def serve_manifest():
    """Отдача manifest.json для PWA"""
    return send_from_directory('static', 'manifest.json')


# Запустить ежедневный авторефреш ЧЗ (если REMOTE_PASS настроен)
from core.chz_scheduler import start_scheduler
start_scheduler()

# Запустить ежедневную проверку открытых смен (если TELEGRAM_OPEN_CHECK_BOT_TOKEN настроен)
from core.open_check_scheduler import start_scheduler as start_open_check_scheduler
start_open_check_scheduler()


if __name__ == '__main__':
    # Под gunicorn эта ветка не исполняется — это только для локального запуска `python app.py`.
    # FLASK_DEBUG=1 включает debug-режим; в production оставляем выключенным.
    import os as _os
    debug_mode = _os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)

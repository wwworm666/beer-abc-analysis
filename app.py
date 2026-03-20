from flask import Flask
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

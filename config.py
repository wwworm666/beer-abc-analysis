# Конфигурация для подключения к iiko API
import os
import secrets
from dotenv import load_dotenv

# Загружаем .env из директории проекта (не из cwd)
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Данные для подключения (из .env)
IIKO_SERVER = os.getenv("IIKO_SERVER", "first-federation.iiko.it")
IIKO_PORT = os.getenv("IIKO_PORT", "443")
IIKO_LOGIN = os.getenv("IIKO_LOGIN")
IIKO_PASSWORD = os.getenv("IIKO_PASSWORD")

# Базовый URL для API
IIKO_BASE_URL = f"https://{IIKO_SERVER}:{IIKO_PORT}/resto/api"


# --- Авторизация: стабильный SECRET_KEY для подписи сессионных cookie ---

def _persistent_dir():
    """Каталог для persistent-данных. Зеркалит core/shifts_manager и extensions:
    на проде это том /kultura (переживает редеплой), локально — папка data/."""
    if os.path.isdir('/kultura'):
        return '/kultura'
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_secret_key() -> bytes:
    """Стабильный ключ подписи сессионных cookie («вход один раз»).

    Приоритет:
    1. env SECRET_KEY — для явного управления ключом в проде;
    2. персистентный файл {persistent}/secret_key — генерируется ОДИН раз и
       переживает рестарты/редеплои (том /kultura). Именно он обеспечивает, что
       плашка входа не появляется на каждый заход;
    3. если файла нет — сгенерировать и записать (создание эксклюзивное, чтобы
       два gunicorn-воркера на первом старте не записали разные ключи).

    Стабильность ключа критична: при его смене все cookie-сессии становятся
    недействительными и всех разлогинивает.
    """
    env_key = os.getenv('SECRET_KEY')
    if env_key:
        return env_key.encode('utf-8') if isinstance(env_key, str) else env_key

    key_path = os.path.join(_persistent_dir(), 'secret_key')
    # Быстрый путь: файл уже есть.
    try:
        with open(key_path, 'rb') as f:
            data = f.read().strip()
        if data:
            return data
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[CONFIG WARNING] Не удалось прочитать {key_path}: {e}")

    # Создание эксклюзивное: гонку первого старта (2 воркера) выигрывает один,
    # проигравший ловит FileExistsError и перечитывает уже записанный ключ.
    key = secrets.token_hex(32).encode('ascii')
    try:
        fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, key)
        finally:
            os.close(fd)
        print(f"[CONFIG] Сгенерирован новый SECRET_KEY -> {key_path}")
        return key
    except FileExistsError:
        with open(key_path, 'rb') as f:
            return f.read().strip()
    except Exception as e:
        # Fail loud при старте, а не тихо отдавать эфемерный ключ: иначе при каждом
        # рестарте генерировался бы новый ключ и всех молча разлогинивало бы.
        # Тот же том держит auth.db, так что неписабельность — это сломанный деплой,
        # который надо чинить, а не маскировать. Обход — задать SECRET_KEY в .env.
        raise RuntimeError(
            f"Не удалось сохранить SECRET_KEY в {key_path}: {e}. "
            f"Проверьте права на каталог данных или задайте SECRET_KEY в окружении."
        )


SECRET_KEY = get_secret_key()

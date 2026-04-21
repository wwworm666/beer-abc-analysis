# Конфигурация для подключения к iiko API
import os
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

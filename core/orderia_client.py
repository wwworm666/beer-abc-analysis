"""Клиент внешней системы лояльности Orderia (раздел /cashapi/).

Зачем: Orderia — единственный известный источник СПРАВОЧНИКА карт. Серверный API
iiko справочника гостей не отдаёт, гость появляется в витрине только с первой
покупкой (docs/guests.md), поэтому слой «карта выдана, покупок нет» без Orderia
невидим в принципе.

Что берём: `never.php` — карты, зарегистрированные и ни разу не совершившие
покупку. Эндпоинт НЕ принимает параметров (проверено 2026-08-12 девятью
вариантами: limit/offset/count/page/id/date_from/from+to/start) — всегда полный
дамп массива. Ответ ~380 байт на карту, приходит за ~50 мс, так что суточный
опрос ничего не стоит и кэш не нужен.

Все значения в ответе — СТРОКИ, включая числовые (PHP json_encode без
JSON_NUMERIC_CHECK). Приведение типов — обязанность потребителя.

Без ORDERIA_LOGIN/ORDERIA_PASSWORD в .env фича просто выключена (как Tuya):
is_configured() отдаёт False, синк не стартует, вкладка показывает подсказку.

Локальная ловушка: под включённым VPN/DPI-обходом хост недоступен и запрос висит
до таймаута. С прод-сервера открывается штатно.

Полный разбор формата и ловушек данных: docs/technical/ORDERIA_CASHAPI.md
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

BASE_URL_DEFAULT = "https://loyalty.orderia.ru/cashapi/"

# Таймаут запроса. Живой ответ приходит за ~50 мс; 20 с — с большим запасом на
# случай, когда хост закрыт туннелем и соединение просто висит.
HTTP_TIMEOUT_S = 20

# Ожидаемые поля записи (для валидации ответа: не подсунули ли нам HTML/ошибку).
REQUIRED_FIELDS = ('id', 'cardnum', 'phone', 'last_date')


# Причина последней неудачи, человеческим языком — она уезжает в БД и
# показывается на вкладке «Не купившие». Логи остаются в транслите, как во всём
# проекте, а пользователю нужен читаемый текст.
_LAST_ERROR = None


def last_error():
    """Причина последней неудачной попытки (или None, если её не было)."""
    return _LAST_ERROR


def _fail(user_message, log_message):
    global _LAST_ERROR
    _LAST_ERROR = user_message
    print(f"[ORDERIA] {log_message}")
    return None


def _base_url():
    raw = os.getenv("ORDERIA_BASE_URL") or BASE_URL_DEFAULT
    return raw.rstrip('/') + '/'


def _credentials():
    return os.getenv("ORDERIA_LOGIN"), os.getenv("ORDERIA_PASSWORD")


def is_configured():
    """Заданы ли креды. False — интеграция выключена, синк не стартует."""
    login, password = _credentials()
    return bool(login and password)


def fetch_never_cards():
    """Карты без единой покупки: список dict как есть от Orderia.

    Возвращает список (может быть пустым) при успехе; None при любой ошибке —
    сети, авторизации, некорректном JSON. None означает «данные не получены»,
    и вызывающий обязан НЕ трогать уже сохранённый срез: пустой список от
    сломанного эндпоинта иначе затёр бы витрину нулём.
    """
    global _LAST_ERROR
    if not is_configured():
        return _fail("Не заданы ORDERIA_LOGIN и ORDERIA_PASSWORD в окружении.",
                     "ORDERIA_LOGIN/ORDERIA_PASSWORD ne zadany — propusk")

    login, password = _credentials()
    url = _base_url() + "never.php"
    try:
        resp = requests.get(url, auth=(login, password), timeout=HTTP_TIMEOUT_S)
    except requests.RequestException as e:
        return _fail(f"Запрос к Orderia не удался: {type(e).__name__}. "
                     "Проверьте сеть; локально хост закрыт под VPN.",
                     f"zapros ne udalsya: {type(e).__name__}: {e}")

    if resp.status_code == 404:
        # Случилось 2026-08-12: эндпоинт перестал существовать за один день.
        return _fail(
            f"Эндпоинт не найден (HTTP 404): {url}. Похоже, адрес изменился на "
            "стороне Orderia — нужен актуальный путь (задаётся через "
            "ORDERIA_BASE_URL без правок кода).",
            f"HTTP 404 na {url}")
    if resp.status_code in (401, 403):
        return _fail(
            f"Orderia отказала в доступе (HTTP {resp.status_code}) — вероятно, "
            "сменились логин или пароль.",
            f"HTTP {resp.status_code} na {url}")
    if resp.status_code != 200:
        return _fail(f"Orderia ответила HTTP {resp.status_code}.",
                     f"HTTP {resp.status_code} na {url}")

    try:
        data = resp.json()
    except ValueError as e:
        return _fail("Ответ Orderia не является JSON.", f"otvet ne JSON: {e}")

    if not isinstance(data, list):
        return _fail(f"Ожидали массив карт, пришло {type(data).__name__}.",
                     f"ozhidali massiv, prishlo {type(data).__name__}")

    # Страховка от «200 OK со страницей-заглушкой»: у первой записи должны быть
    # ожидаемые поля. Пустой массив — валидный ответ (все карты что-то купили).
    if data:
        first = data[0]
        if not isinstance(first, dict) or not all(f in first for f in REQUIRED_FIELDS):
            return _fail(
                "Структура ответа не похожа на never.php — данные не приняты.",
                "struktura otveta ne pohozha na never.php — propusk")

    _LAST_ERROR = None
    return data

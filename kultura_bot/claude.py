"""Связь с Claude API (Anthropic): клиент, разбор ошибок, проверка ключа, цена ответа.

Ключ и прокси — со страницы «Доступ агентов» (kultura_bot/credentials.py); модель и
цены — kultura_bot/settings.py. Клиент — официальный SDK `anthropic` (1.x, на httpx2).

Прокси нужен, если Anthropic не пускает сервер из его страны: тогда все запросы бота к
API идут через прокси (DefaultHttpxClient(proxy=…)), Telegram и сайт — напрямую.

Ошибки API превращаются в короткий текст для человека (describe_error): бот пишет его в
чат, страница — в строку состояния. Ключ и прокси в тексты ошибок не попадают: тексты API
их не содержат, а всё, что пришло из чужого исключения, проходит scrub — ключ, адрес прокси
и пароль из него заменяются на «***».
"""
import threading
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlsplit

from kultura_bot import settings

# Таймаут одного запроса к API: шаг модели с инструментами на medium укладывается в
# минуту-две; 10 минут — умолчание SDK и запас на тяжёлые шаги. Повторы при 429/5xx и
# обрывах связи делает сам SDK (max_retries).
REQUEST_TIMEOUT_S = 600
MAX_RETRIES = 2
CHECK_TIMEOUT_S = 20          # проверка ключа на странице: человек ждёт ответа

_CLIENTS: Dict[Tuple[str, str], Any] = {}
_CLIENTS_LOCK = threading.Lock()


def make_client(api_key: str, proxy: str = '', *, timeout: float = REQUEST_TIMEOUT_S,
                max_retries: int = MAX_RETRIES):
    """Новый клиент Anthropic (с прокси, если задан)."""
    import anthropic
    kwargs: Dict[str, Any] = {'api_key': api_key, 'timeout': timeout, 'max_retries': max_retries}
    if proxy:
        kwargs['http_client'] = anthropic.DefaultHttpxClient(proxy=proxy)
    return anthropic.Anthropic(**kwargs)


def client_for(api_key: str, proxy: str = ''):
    """Общий клиент на пару (ключ, прокси): пул соединений переиспользуется между вопросами."""
    key = (api_key, proxy)
    with _CLIENTS_LOCK:
        client = _CLIENTS.get(key)
        if client is None:
            for old in _CLIENTS.values():       # ключ сменили — старый пул закрываем
                try:
                    old.close()
                except Exception:  # noqa: BLE001
                    pass
            _CLIENTS.clear()
            client = _CLIENTS[key] = make_client(api_key, proxy)
        return client


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """Заменить в тексте секреты на «***»: ключ, адрес прокси и пароль из адреса."""
    values = []
    for value in secrets:
        if not value:
            continue
        values.append(value)
        if '://' in value:
            try:
                password = urlsplit(value).password
            except ValueError:
                password = None
            if password:
                values.append(password)
    for value in sorted(values, key=len, reverse=True):
        if len(value) >= 4:
            text = text.replace(value, '***')
    return text


def describe_error(exc: BaseException, secrets: Iterable[str] = ()) -> Tuple[str, str]:
    """(вид, текст для человека) без секретов из secrets. Виды: auth, denied, billing, rate,
    overloaded, server, bad_request, offline, other."""
    kind, text = _describe(exc)
    return kind, scrub(text, secrets)


def _describe(exc: BaseException) -> Tuple[str, str]:
    import anthropic
    page = settings.ADMIN_PAGE_URL
    if isinstance(exc, anthropic.AuthenticationError):
        return 'auth', (f'Anthropic не принял ключ API (401). Новый ключ — в консоли Anthropic, вставить на '
                        f'странице {page}, раздел «Бот @{settings.BOT_USERNAME}».')
    if isinstance(exc, anthropic.PermissionDeniedError):
        return 'denied', (f'Anthropic отказал серверу (403): {_message(exc)}. Если сервер в стране, где API '
                          f'недоступен, нужен прокси — поле «Прокси» на странице {page}.')
    if isinstance(exc, anthropic.RateLimitError):
        return 'rate', 'Anthropic ограничил частоту запросов (429). Повторите через минуту.'
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, 'status_code', 0) or 0
        text = _message(exc)
        if status == 529 or 'overloaded' in text.lower():
            return 'overloaded', 'Claude сейчас перегружен (529). Повторите через пару минут.'
        if status >= 500:
            return 'server', f'Сбой на стороне Anthropic ({status}). Повторите через пару минут.'
        if 'credit balance' in text.lower() or 'billing' in text.lower():
            return 'billing', (f'На счёте Anthropic кончились деньги: {text}. Пополнить — в консоли Anthropic '
                               f'(Billing).')
        return 'bad_request', f'Anthropic вернул ошибку {status}: {text}'
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return 'offline', (f'Нет связи с Anthropic ({type(exc).__name__}). Если сервер в стране, где API '
                           f'недоступен, нужен прокси — поле «Прокси» на странице {page}.')
    return 'other', f'{type(exc).__name__}: {exc}'


def _message(exc: BaseException) -> str:
    text = str(getattr(exc, 'message', '') or exc)
    return text[:300]


def check_key(api_key: str, proxy: str = '') -> Tuple[str, str]:
    """Живая проверка ключа: список моделей (бесплатный запрос). ('ok', имя модели) или (вид, текст)."""
    try:
        client = make_client(api_key, proxy, timeout=CHECK_TIMEOUT_S, max_retries=0)
        try:
            page = client.models.list(limit=1)
            first = next(iter(page.data), None)
            return 'ok', getattr(first, 'id', '') or ''
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 — любой сбой -> текст для страницы
        return describe_error(exc, secrets=(api_key, proxy))


def prices_for(model: Optional[str]) -> Tuple[float, float, float, float]:
    """Цены модели за 1 млн токенов (вход, выход, чтение кэша, запись кэша).

    Имя модели в ответе может быть с датой (claude-opus-5-5-20261001): берётся самое длинное
    совпавшее начало, чтобы claude-opus-5-5 не посчитался как claude-opus-5."""
    names = [name for name in settings.PRICES_PER_MTOK if model and str(model).startswith(name)]
    if names:
        return settings.PRICES_PER_MTOK[max(names, key=len)]
    return settings.PRICES_PER_MTOK.get(settings.MODEL, (0.0, 0.0, 0.0, 0.0))


def cost_usd(model: Optional[str], usage: Dict[str, int]) -> float:
    """Цена шага по токенам из usage ответа: вход + выход + кэш (чтение и запись)."""
    price_in, price_out, price_read, price_write = prices_for(model)
    total = (usage.get('input_tokens', 0) * price_in + usage.get('output_tokens', 0) * price_out
             + usage.get('cache_read_input_tokens', 0) * price_read
             + usage.get('cache_creation_input_tokens', 0) * price_write)
    return round(total / 1_000_000, 6)

"""Хук gunicorn: при старте приложения передать Caddy актуальный Caddyfile.

Gunicorn сам читает ./gunicorn.conf.py из рабочей папки (/app в образе); флаги
запуска остаются в Dockerfile (CMD). when_ready срабатывает один раз при старте
мастер-процесса, то есть после каждого деплоя.

Зачем: деплой пересоздаёт только контейнер app, а Caddy (beer-caddy) читает свой
Caddyfile лишь при перезапуске, к тому же файл смонтирован отдельно и после
`git pull` контейнер видит старую версию. Обе службы в сети хоста, поэтому app
отдаёт Caddyfile из своего образа в admin API Caddy (127.0.0.1:2019, POST /load).
Caddy проверяет конфиг целиком: неверный отклоняет и остаётся на прежнем, тот же
самый не перезагружает. Подробности — docs/guides/deploy.md.
"""
import urllib.error
import urllib.request
from pathlib import Path

CADDYFILE = Path(__file__).resolve().with_name('Caddyfile')
# Admin API Caddy по умолчанию слушает localhost:2019 и принимает Host 127.0.0.1:2019.
CADDY_LOAD_URL = 'http://127.0.0.1:2019/load'
# Приём конфига занимает миллисекунды; 10 с — с запасом, и старт приложения
# (хук выполняется до запуска воркеров) не задерживается дольше.
CADDY_TIMEOUT = 10
# Сколько байт ответа Caddy об ошибке писать в лог: причина отказа умещается.
ERROR_BODY_LIMIT = 500


def apply_caddyfile(log, opener=None):
    """POST Caddyfile в Caddy. True — Caddy принял. Ошибка не мешает старту приложения."""
    # Без прокси: адрес локальный, а переменные HTTP(S)_PROXY из .env сюда не относятся.
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        request = urllib.request.Request(
            CADDY_LOAD_URL, data=CADDYFILE.read_bytes(), method='POST',
            headers={'Content-Type': 'text/caddyfile'})
        with opener.open(request, timeout=CADDY_TIMEOUT) as response:
            log.info('Caddyfile передан в Caddy: HTTP %s', response.status)
            return True
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:ERROR_BODY_LIMIT].decode('utf-8', 'replace')
        log.warning('Caddy отклонил Caddyfile (HTTP %s): %s. Работает прежний конфиг.',
                    exc.code, detail)
    except Exception as exc:  # старт приложения важнее перенастройки Caddy
        log.warning('Caddyfile не передан в Caddy (%s). Работает прежний конфиг.', exc)
    return False


def when_ready(server):
    apply_caddyfile(server.log)

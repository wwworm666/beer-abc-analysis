"""Запуск сервера бота: python -m kultura_bot (на сервере — systemd-служба kultura-bot).

Переменные окружения (на сервере — файл /etc/kultura-bot.env, его пишет установка):

    KULTURA_BOT_KEY    ключ сервера бота — выпускает страница «Доступ агентов»
                       («Команда установки»); обязателен
    KULTURA_SITE_URL   адрес сайта; по умолчанию settings.SITE_URL
    KULTURA_BOT_DATA   папка своей базы (bot.db); по умолчанию ./data
                       (служба: /var/lib/kultura-bot)

Остальное (токен Telegram, ключ Anthropic, пауза) сервер берёт у сайта. Журнал — в
stdout (journalctl -u kultura-bot). SIGTERM (остановка службы) — начатые ответы
доводятся до конца, затем выход.
"""
import logging
import os
import signal
import sys

from kultura_bot import settings
from kultura_bot.engine.service import Service
from kultura_bot.engine.site import Site
from kultura_bot.engine.store import Store

log = logging.getLogger('kultura-bot')


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    key = (os.environ.get('KULTURA_BOT_KEY') or '').strip()
    if not key:
        print('Нет KULTURA_BOT_KEY: выпустите команду установки на странице «Доступ агентов» '
              f'({settings.ADMIN_PAGE_URL}) и выполните её на сервере.', file=sys.stderr)
        return 2
    site_url = (os.environ.get('KULTURA_SITE_URL') or settings.SITE_URL).strip()
    data_dir = (os.environ.get('KULTURA_BOT_DATA') or os.path.join(os.getcwd(), 'data')).strip()
    store = Store(os.path.join(data_dir, 'bot.db'))
    service = Service(Site(site_url, key), store)

    def stop(signum, frame):  # noqa: ARG001
        log.info('[BOT] сигнал %s — останавливаюсь', signum)
        service.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info('[BOT] сервер бота запущен: сайт %s, база %s', site_url, store.path)
    service.run_forever()
    store.close()
    return 0

"""
Transmission RPC — отправка торрентов на роутер.
"""
import base64
from transmission_rpc import Client
from torrent_bot.config import (
    TRANSMISSION_HOST, TRANSMISSION_PORT,
    TRANSMISSION_USER, TRANSMISSION_PASS
)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(
            host=TRANSMISSION_HOST,
            port=TRANSMISSION_PORT,
            username=TRANSMISSION_USER or None,
            password=TRANSMISSION_PASS or None,
        )
    return _client


def add_torrent(release):
    """
    Добавить торрент в Transmission.
    release — dict с полями: magnet, topic_id, tracker.

    Стратегия:
    1. Если есть magnet — используем его
    2. Иначе скачиваем .torrent файл с трекера и отправляем как base64
    """
    tc = _get_client()

    # Вариант 1: magnet link
    if release.get('magnet'):
        tc.add_torrent(release['magnet'])
        return

    # Вариант 2: скачать .torrent файл с трекера
    torrent_bytes = _download_torrent_file(release)
    if torrent_bytes:
        tc.add_torrent(base64.b64encode(torrent_bytes).decode('ascii'))
        return

    raise RuntimeError("Нет magnet-ссылки и не удалось скачать .torrent файл")


def _download_torrent_file(release):
    """Скачать .torrent файл с трекера."""
    tracker = release.get('tracker', '')
    topic_id = release.get('topic_id', '')

    if not topic_id:
        return None

    if tracker == 'rutracker':
        from torrent_bot.trackers.rutracker import get_client
        return get_client().get_torrent_file(topic_id)
    elif tracker == 'kinozal':
        from torrent_bot.trackers.kinozal import get_client
        return get_client().get_torrent_file(topic_id)

    return None


def get_torrents():
    """Получить список активных торрентов."""
    tc = _get_client()
    torrents = tc.get_torrents()
    return [
        {
            'name': t.name,
            'progress': t.progress,
            'status': t.status,
            'eta': str(t.eta) if t.eta else '?',
        }
        for t in torrents
    ]

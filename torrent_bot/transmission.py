"""
Transmission — управление торрентами через transmission-remote CLI.
"""
import os
import subprocess
import tempfile
from torrent_bot.config import TRANSMISSION_HOST, TRANSMISSION_PORT, TRANSMISSION_USER, TRANSMISSION_PASS


def _remote(*args):
    cmd = ['transmission-remote', f'{TRANSMISSION_HOST}:{TRANSMISSION_PORT}']
    if TRANSMISSION_USER:
        cmd += ['-n', f'{TRANSMISSION_USER}:{TRANSMISSION_PASS}']
    cmd += list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def add_torrent(release):
    torrent_bytes = _download_torrent_file(release)
    if not torrent_bytes:
        raise RuntimeError("Не удалось скачать .torrent файл")
    fd, path = tempfile.mkstemp(suffix='.torrent')
    try:
        os.write(fd, torrent_bytes)
        os.close(fd)
        _remote('-a', path)
    finally:
        os.unlink(path)


def _download_torrent_file(release):
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
    """Получить список торрентов с ID."""
    out = _remote('-l')
    torrents = []
    lines = out.strip().split('\n')
    if len(lines) < 2:
        return torrents
    for line in lines[1:-1]:  # skip header and summary
        parts = line.split()
        if len(parts) >= 9:
            tid = parts[0].rstrip('*')
            try:
                tid = int(tid)
            except ValueError:
                continue
            pct = parts[1].replace('%', '')
            try:
                pct = int(float(pct))
            except ValueError:
                pct = 0
            size = f"{parts[2]} {parts[3]}" if len(parts) > 3 else '?'
            status = parts[7] if len(parts) > 7 else '?'
            name = ' '.join(parts[8:])
            torrents.append({
                'id': tid,
                'name': name,
                'progress': pct,
                'status': status,
                'size': size,
                'eta': parts[4] if len(parts) > 4 else '?',
            })
    return torrents


def remove_torrent(torrent_id, delete_data=True):
    """Удалить торрент. delete_data=True удаляет и файлы."""
    if delete_data:
        _remote('-t', str(torrent_id), '--remove-and-delete')
    else:
        _remote('-t', str(torrent_id), '--remove')

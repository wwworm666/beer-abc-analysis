"""
Rutracker — авторизация и поиск раздач.
"""
import re
import requests
from bs4 import BeautifulSoup
from torrent_bot.config import RUTRACKER_USER, RUTRACKER_PASS

BASE_URL = 'https://rutracker.org/forum'
LOGIN_URL = f'{BASE_URL}/login.php'
SEARCH_URL = f'{BASE_URL}/tracker.php'


class RutrackerClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        })
        self._logged_in = False

    def login(self):
        if not RUTRACKER_USER or not RUTRACKER_PASS:
            print("Rutracker: credentials not set")
            return False
        try:
            resp = self.session.post(LOGIN_URL, data={
                'login_username': RUTRACKER_USER,
                'login_password': RUTRACKER_PASS,
                'login': 'Вход',
            })
            self._logged_in = 'bb_session' in self.session.cookies.get_dict()
            if not self._logged_in:
                print("Rutracker: login failed (no session cookie)")
            return self._logged_in
        except Exception as e:
            print(f"Rutracker login error: {e}")
            return False

    def search(self, query):
        """Поиск раздач. Возвращает список dict."""
        if not self._logged_in and not self.login():
            return []

        try:
            resp = self.session.get(SEARCH_URL, params={
                'nm': query,
                'o': 10,   # сортировка по сидам
                's': 2,    # по убыванию
            }, timeout=15)
            resp.encoding = 'utf-8'
            return self._parse_results(resp.text)
        except Exception as e:
            print(f"Rutracker search error: {e}")
            return []

    def get_torrent_file(self, topic_id):
        """Скачать .torrent файл (bytes) по topic_id."""
        if not self._logged_in and not self.login():
            return None
        try:
            resp = self.session.get(
                f'{BASE_URL}/dl.php',
                params={'t': topic_id},
                timeout=15
            )
            if resp.status_code == 200 and len(resp.content) > 100:
                return resp.content
            return None
        except Exception:
            return None

    def _parse_results(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        rows = soup.select('#tor-tbl tbody tr')
        for row in rows[:20]:
            try:
                # Название и ссылка на тему
                title_el = row.select_one('.t-title a')
                if not title_el:
                    title_el = row.select_one('.tLink')
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                href = title_el.get('href', '')
                topic_id = self._extract_topic_id(href)

                # Размер
                size_el = row.select_one('.tor-size u')
                if size_el:
                    size_bytes = int(size_el.get_text(strip=True))
                    size = self._format_size(size_bytes)
                else:
                    size_el = row.select_one('.tor-size')
                    size = size_el.get_text(strip=True) if size_el else '?'

                # Сиды
                seeds_el = row.select_one('.seedmed') or row.select_one('b.seedmed')
                seeds = int(seeds_el.get_text(strip=True)) if seeds_el else 0

                # Личи
                leech_el = row.select_one('.leechmed') or row.select_one('b.leechmed')
                leeches = int(leech_el.get_text(strip=True)) if leech_el else 0

                results.append({
                    'title': title,
                    'size': size,
                    'seeds': seeds,
                    'leeches': leeches,
                    'topic_id': topic_id,
                    'tracker': 'rutracker',
                    'magnet': None,  # получим при скачивании
                    'quality': None,  # заполнит LLM
                })
            except Exception:
                continue

        return results

    @staticmethod
    def _extract_topic_id(href):
        match = re.search(r't=(\d+)', href)
        return match.group(1) if match else ''

    @staticmethod
    def _format_size(size_bytes):
        if size_bytes > 1024**3:
            return f"{size_bytes / 1024**3:.1f} GB"
        elif size_bytes > 1024**2:
            return f"{size_bytes / 1024**2:.0f} MB"
        return f"{size_bytes} B"


# Синглтон — переиспользуем сессию между запросами
_client = None

def get_client():
    global _client
    if _client is None:
        _client = RutrackerClient()
    return _client

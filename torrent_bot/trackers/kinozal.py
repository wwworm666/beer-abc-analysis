"""
Kinozal.tv — авторизация и поиск раздач.
"""
import re
import requests
from bs4 import BeautifulSoup
from torrent_bot.config import KINOZAL_USER, KINOZAL_PASS

BASE_URL = 'https://kinozal.tv'
LOGIN_URL = f'{BASE_URL}/takelogin.php'
SEARCH_URL = f'{BASE_URL}/browse.php'
DL_URL = 'https://dl.kinozal.tv/download.php'


class KinozalClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        })
        self._logged_in = False

    def login(self):
        if not KINOZAL_USER or not KINOZAL_PASS:
            print("Kinozal: credentials not set")
            return False
        try:
            resp = self.session.post(LOGIN_URL, data={
                'username': KINOZAL_USER,
                'password': KINOZAL_PASS,
            }, allow_redirects=True)
            # Kinozal ставит uid cookie при успешном входе
            cookies = self.session.cookies.get_dict()
            self._logged_in = 'uid' in cookies or 'pass' in cookies
            if not self._logged_in:
                print("Kinozal: login failed (no session cookie)")
            return self._logged_in
        except Exception as e:
            print(f"Kinozal login error: {e}")
            return False

    def search(self, query):
        """Поиск раздач. Возвращает список dict."""
        if not self._logged_in and not self.login():
            return []

        try:
            resp = self.session.get(SEARCH_URL, params={
                's': query,
                'g': 0,     # все жанры
                'c': 1002,  # категория: фильмы
                'v': 0,     # все качества
                'd': 0,     # все даты
                'w': 0,     # все недели
                't': 0,     # все
            }, timeout=15)
            resp.encoding = 'windows-1251'
            return self._parse_results(resp.text)
        except Exception as e:
            print(f"Kinozal search error: {e}")
            return []

    def get_torrent_file(self, torrent_id):
        """Скачать .torrent файл (bytes)."""
        if not self._logged_in and not self.login():
            return None
        try:
            resp = self.session.get(
                DL_URL,
                params={'id': torrent_id},
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

        # Kinozal: таблица результатов
        rows = soup.select('.bx1 table tr')
        if not rows:
            rows = soup.select('table.t_peer tr')

        for row in rows[:20]:
            try:
                # Название и ссылка
                title_el = row.select_one('td.nam a')
                if not title_el:
                    title_el = row.select_one('a.r1')
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                href = title_el.get('href', '')
                torrent_id = self._extract_id(href)

                # Размер — обычно в одной из ячеек
                cells = row.select('td')
                size = '?'
                seeds = 0
                leeches = 0

                for cell in cells:
                    text = cell.get_text(strip=True)
                    # Размер (содержит GB, MB, ГБ, МБ)
                    if re.search(r'\d+\.?\d*\s*(GB|MB|ГБ|МБ|Gb|Mb)', text):
                        size = text
                    # Сиды (класс или зелёный цвет)
                    cl = ' '.join(cell.get('class', []))
                    if 'sl_s' in cl or 'seed' in cl.lower():
                        try:
                            seeds = int(re.search(r'\d+', text).group())
                        except (AttributeError, ValueError):
                            pass
                    if 'sl_p' in cl or 'leech' in cl.lower():
                        try:
                            leeches = int(re.search(r'\d+', text).group())
                        except (AttributeError, ValueError):
                            pass

                # Попытка найти сиды/личи по цвету текста
                if seeds == 0:
                    green = row.select_one('td font[color="#16a085"], td.sl_s')
                    if green:
                        try:
                            seeds = int(re.search(r'\d+', green.get_text()).group())
                        except (AttributeError, ValueError):
                            pass

                results.append({
                    'title': title,
                    'size': size,
                    'seeds': seeds,
                    'leeches': leeches,
                    'topic_id': torrent_id,
                    'tracker': 'kinozal',
                    'magnet': None,
                    'quality': None,
                })
            except Exception:
                continue

        return results

    @staticmethod
    def _extract_id(href):
        match = re.search(r'id=(\d+)', href)
        return match.group(1) if match else ''


# Синглтон
_client = None

def get_client():
    global _client
    if _client is None:
        _client = KinozalClient()
    return _client

"""PNG-карточка графика: та же страница мини-приложения в Chromium без сети.

## Как работает

1. Шаблон templates/tg_chart.html в режиме png собирается с описанием графика
   внутри (JSON) — те же static/tg_chart/charts.js и ECharts, что в мини-приложении,
   поэтому картинка в чате и интерактивная версия совпадают по цветам и раскладке.
2. Chromium (Playwright; в прод-образе mcr.microsoft.com/playwright/python он есть)
   открывает страницу по выдуманному адресу RENDER_ORIGIN. Все запросы
   перехватываются: документ — из памяти, /static/... — с диска, остальное
   отклоняется. Наружу страница не ходит, сам сервис по HTTP не дёргается.
3. Страница ставит window.__tgChartReady = true, когда шрифт загружен и ECharts
   дорисовал график без анимации; снимок — только карточка #card.

## Размер

Ширина карточки CARD_WIDTH_PX = 430 (ширина телефона, как у PNG-карточек бота),
масштаб DEVICE_SCALE = 3: картинка 1290 px по ширине — чёткая на любом телефоне.
Telegram хранит фото не больше PHOTO_LONG_SIDE_MAX = 2560 px по длинной стороне:
высокую карточку (длинный рейтинг) уменьшаем сами (Pillow, LANCZOS) — так
резче, чем пережмёт Telegram.

Одновременно рисуется одна картинка на процесс (RENDER_LOCK): Chromium занимает
~150 МБ, а воркеру gunicorn нужна память и для сайта. Второй вызов ждёт до
RENDER_WAIT_S секунд.

Chromium — тот, что поставил Playwright (в прод-образе версия совпадает с пакетом).
TG_CHART_CHROMIUM — путь к другому исполняемому файлу (локальная разработка, тесты).
"""
import io
import json
import mimetypes
import os
import threading
from typing import Any, Dict
from urllib.parse import urlsplit

from core.storage_paths import BASE_DIR

CARD_WIDTH_PX = 430
DEVICE_SCALE = 3
PHOTO_LONG_SIDE_MAX = 2560
VIEWPORT_HEIGHT_PX = 900          # высота окна; карточка выше снимается целиком
READY_TIMEOUT_MS = 20000          # шрифт + ECharts; на проде ~1 с
RENDER_WAIT_S = 60
RENDER_ORIGIN = 'http://tg-chart.render'
PAGE_PATH = '/tg/chart'
CHROMIUM_ENV = 'TG_CHART_CHROMIUM'

STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

RENDER_LOCK = threading.Lock()


class RenderError(RuntimeError):
    """Картинка не нарисована."""


def page_html(spec: Dict[str, Any], theme: str = 'light') -> str:
    """HTML страницы в режиме png (Jinja без приложения: рендер зовут и вне запроса)."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from markupsafe import Markup

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(['html']))
    # Тот же фильтр tojson, что у Flask: <, >, & и ' экранируются — JSON безопасен в <script>.
    env.filters['tojson'] = lambda value: Markup(json.dumps(value, ensure_ascii=False)
                                                 .replace('<', '\\u003c').replace('>', '\\u003e')
                                                 .replace('&', '\\u0026').replace("'", '\\u0027'))
    # app_version в шаблоне — только для сброса кэша браузера (?v=); здесь кэша нет.
    return env.get_template('tg_chart.html').render(mode='png', theme=theme, payload={'chart': spec},
                                                    app_version='png')


def _static_file(path: str):
    rel = path[len('/static/'):]
    full = os.path.realpath(os.path.join(STATIC_DIR, rel))
    if not full.startswith(os.path.realpath(STATIC_DIR) + os.sep) or not os.path.isfile(full):
        return None
    return full


def _shrink(png: bytes) -> bytes:
    """Уменьшить до PHOTO_LONG_SIDE_MAX по длинной стороне, если картинка больше."""
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        width, height = image.size
        longest = max(width, height)
        if longest <= PHOTO_LONG_SIDE_MAX:
            return png
        factor = PHOTO_LONG_SIDE_MAX / longest
        resized = image.resize((max(1, round(width * factor)), max(1, round(height * factor))), Image.LANCZOS)
        out = io.BytesIO()
        resized.save(out, format='PNG', optimize=True)
        return out.getvalue()


def render_png(spec: Dict[str, Any], theme: str = 'light') -> bytes:
    """PNG карточки графика (описание — уже после core/tg_charts.normalize)."""
    html = page_html(spec, theme=theme)
    if not RENDER_LOCK.acquire(timeout=RENDER_WAIT_S):
        raise RenderError('уже рисуется другая картинка — повторите через минуту')
    try:
        return _shrink(_render(html))
    finally:
        RENDER_LOCK.release()


def _render(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    errors = []

    def handle(route):
        url = urlsplit(route.request.url)
        if f'{url.scheme}://{url.netloc}' != RENDER_ORIGIN:
            return route.abort()
        if url.path == PAGE_PATH:
            return route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html)
        if url.path.startswith('/static/'):
            full = _static_file(url.path)
            if full:
                content_type = mimetypes.guess_type(full)[0] or 'application/octet-stream'
                if full.endswith('.woff2'):
                    content_type = 'font/woff2'
                with open(full, 'rb') as f:
                    return route.fulfill(status=200, content_type=content_type, body=f.read())
        return route.abort()

    executable = (os.environ.get(CHROMIUM_ENV) or '').strip() or None
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        try:
            context = browser.new_context(viewport={'width': CARD_WIDTH_PX, 'height': VIEWPORT_HEIGHT_PX},
                                          device_scale_factor=DEVICE_SCALE)
            page = context.new_page()
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.route('**/*', handle)
            page.goto(RENDER_ORIGIN + PAGE_PATH, wait_until='load')
            try:
                page.wait_for_function('window.__tgChartReady === true', timeout=READY_TIMEOUT_MS)
            except Exception as exc:  # noqa: BLE001
                detail = '; '.join(errors) or type(exc).__name__
                raise RenderError(f'страница графика не дорисовалась: {detail}') from None
            if errors:
                raise RenderError('ошибка на странице графика: ' + '; '.join(errors))
            return page.locator('#card').screenshot(type='png', animations='disabled')
        finally:
            browser.close()

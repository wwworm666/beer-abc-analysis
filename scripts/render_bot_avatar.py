"""Собрать аватарку бота kultura.os: kultura_bot/assets/avatar.svg -> avatar.jpg (640×640).

Зачем: сервер бота ставит аватарку сам (settings.BOT_AVATAR, engine/service.sync_profile ->
Bot API setMyProfilePhoto), а Telegram принимает фото профиля картинкой JPEG, не SVG.
Исходник знака — avatar.svg; поменяли его — запустите скрипт и закоммитьте оба файла:
сервер бота увидит новую картинку (другой хеш файла) и поставит её после самообновления.

Запуск (нужен Playwright с Chromium, как для графиков: kultura_bot/charts/png.py):

    py -3 scripts/render_bot_avatar.py

Свой Chromium — путь в переменной TG_CHART_CHROMIUM (та же, что у графиков).
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'kultura_bot', 'assets')
SOURCE = os.path.join(ASSETS, 'avatar.svg')
TARGET = os.path.join(ASSETS, 'avatar.jpg')
SIZE_PX = 640            # Telegram показывает фото профиля до 640×640; квадрат, круг вырезает сам
JPEG_QUALITY = 95        # плоские цвета знака: ниже — заметные ореолы у краёв


def render() -> str:
    from playwright.sync_api import sync_playwright

    with open(SOURCE, encoding='utf-8') as f:
        svg = f.read()
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0}'
            f'svg{{display:block;width:{SIZE_PX}px;height:{SIZE_PX}px}}</style></head><body>{svg}</body></html>')
    executable = (os.environ.get('TG_CHART_CHROMIUM') or '').strip() or None
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        try:
            page = browser.new_page(viewport={'width': SIZE_PX, 'height': SIZE_PX}, device_scale_factor=1)
            page.set_content(html, wait_until='load')
            page.screenshot(path=TARGET, type='jpeg', quality=JPEG_QUALITY,
                            clip={'x': 0, 'y': 0, 'width': SIZE_PX, 'height': SIZE_PX})
        finally:
            browser.close()
    return TARGET


if __name__ == '__main__':
    print(render())

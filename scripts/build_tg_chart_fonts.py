"""Собрать woff2-шрифты мини-приложения «Графики» из IBM Plex Mono (TTF в static/fonts).

Зачем: мини-приложение открывают с телефона, а TTF одного начертания весит ~135 КБ.
Подмножество латиницы, кириллицы и знаков, которые пишут карточки (₽, −, –, «», ·, ≈,
№, ×), в woff2 весит ~25 КБ. Лицензия шрифта (OFL, static/fonts/OFL.txt) разрешает
подмножества; имя семейства остаётся «IBM Plex Mono».

Запуск (нужны fonttools и brotli):

    py -3 -m pip install fonttools brotli
    py -3 scripts/build_tg_chart_fonts.py

Результат: static/fonts/ibm-plex-mono/IBMPlexMono-<Начертание>.subset.woff2 для 400,
500, 600 и 700 (их подключает static/tg_chart/tg_chart.css).
"""
import os

from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, 'static', 'fonts', 'ibm-plex-mono')
WEIGHTS = ('Regular', 'Medium', 'SemiBold', 'Bold')

# Диапазоны символов: латиница и Latin-1 (цифры, знаки, NBSP), кириллица, общая
# пунктуация (тире, кавычки, многоточие, узкие пробелы), №, ₽, минус, ≈, ×.
UNICODES = (
    list(range(0x0020, 0x007F)) + list(range(0x00A0, 0x0100)) + list(range(0x0400, 0x0460)) +
    [0x0490, 0x0491] + list(range(0x2010, 0x2028)) + list(range(0x2030, 0x203B)) +
    [0x2116, 0x20BD, 0x2212, 0x2248, 0x00D7]
)


def build(weight: str) -> str:
    source = os.path.join(FONT_DIR, f'IBMPlexMono-{weight}.ttf')
    target = os.path.join(FONT_DIR, f'IBMPlexMono-{weight}.subset.woff2')
    options = subset.Options()
    options.flavor = 'woff2'
    options.layout_features = ['*']
    options.name_IDs = ['*']
    options.name_languages = ['*']
    options.notdef_outline = True
    options.hinting = False          # экраны телефонов не используют хинтинг TrueType
    font = subset.load_font(source, options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=UNICODES)
    subsetter.subset(font)
    subset.save_font(font, target, options)
    return target


if __name__ == '__main__':
    for w in WEIGHTS:
        path = build(w)
        print(f'{os.path.relpath(path, ROOT)}: {os.path.getsize(path) // 1024} КБ')

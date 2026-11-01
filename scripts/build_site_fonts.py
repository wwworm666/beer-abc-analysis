"""Собрать woff2-шрифты сайта из IBM Plex Mono (TTF в static/fonts/ibm-plex-mono).

Зачем: сайт открывают с телефона, а TTF одного начертания весит ~135 КБ, четыре — ~540 КБ.
Пока они грузятся, телефон показывает запасной шрифт; на Android запасной «Courier New» —
это «печатная машинка» Cutive Mono без кириллицы (владелец 2026-11-01: «Это что за шрифт?»).
woff2 с нужными сайту символами весит ~20 КБ на начертание. Лицензия шрифта (OFL,
static/fonts/ibm-plex-mono/OFL.txt) разрешает подмножества; имя семейства остаётся
«IBM Plex Mono».

Набор шире, чем у мини-приложения «Графики» (scripts/build_tg_chart_fonts.py): сайт пишет
ещё стрелки (← → ↑ ↓ ↗ ↘ ↻), ✓, ≤ и ≥. В подмножество попадает только то, что есть в самом
шрифте: символов, которых нет и в TTF (Σ, Δ, ▲, ★…), браузер берёт из следующего шрифта
списка — как и раньше.

Запуск (нужны fonttools и brotli):

    py -3 -m pip install fonttools brotli
    py -3 scripts/build_site_fonts.py

Результат: static/fonts/ibm-plex-mono/IBMPlexMono-<Начертание>.site.woff2 для 400, 500,
600 и 700 (их подключает static/dashboard/styles/fonts.css).
"""
import os

from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, 'static', 'fonts', 'ibm-plex-mono')
WEIGHTS = ('Regular', 'Medium', 'SemiBold', 'Bold')

# Блоки Юникода целиком (из каждого берётся только то, что есть в шрифте): латиница с
# Latin-1 и Latin Extended-A, кириллица, общая пунктуация (пробелы, тире, кавычки,
# многоточие), валюты (₽), буквоподобные (№), стрелки, математика (−, ≈, ≤, ≥),
# геометрические фигуры, дингбаты (✓).
BLOCKS = (
    (0x0020, 0x007E), (0x00A0, 0x017F), (0x0400, 0x04FF), (0x2000, 0x206F),
    (0x20A0, 0x20CF), (0x2100, 0x214F), (0x2190, 0x21FF), (0x2200, 0x22FF),
    (0x25A0, 0x25FF), (0x2700, 0x27BF),
)
UNICODES = [cp for start, end in BLOCKS for cp in range(start, end + 1)]


def build(weight: str) -> str:
    source = os.path.join(FONT_DIR, f'IBMPlexMono-{weight}.ttf')
    target = os.path.join(FONT_DIR, f'IBMPlexMono-{weight}.site.woff2')
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

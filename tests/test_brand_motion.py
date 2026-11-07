"""Набор бренда «Grid motion» (brand/kultura-grid-motion, docs/brand.md): кадры считает исходник рендера
grid.cjs — тот же, из которого собраны ролики. Без node тест пропускается (в CI на ubuntu он есть).
"""
import json
import math
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, 'brand', 'kultura-grid-motion', 'source')
NODE = shutil.which('node')

HARNESS = r'''
const g = require(process.argv[1] + '/grid.cjs');
const frames = {
  avatar_pulse: g.avatar('pulse', 5), avatar_research: g.avatar('research', 5),
  avatar_start: g.avatar('pulse', 0), avatar_end: g.avatar('pulse', 8),
  research_dark: g.individual('research', 5), research_light: g.individual('research', 5, 'light'),
  research_drawing: g.individual('research', 2.48 - 1.28 + 0.2, 'light'),
  pulse_dark_default: g.individual('pulse', 5) === g.individual('pulse', 5, 'dark'),
  scale: g.AVATAR_SCALE,
  avatar_frames: ['pulse', 'research'].flatMap(k => [0.6, 1.2, 2.5, 5, 7.2].map(t => g.avatar(k, t))),
};
process.stdout.write(JSON.stringify(frames));
'''


@pytest.fixture(scope='module')
def frames():
    if NODE is None:
        pytest.skip('node не установлен')
    run = subprocess.run([NODE, '-e', HARNESS, SOURCE], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_bot_avatar_is_mark_only_large_and_light(frames):
    """2026-11-07: «с подписью плохо, логотип слишком маленький» — у аватарки только знак, крупно."""
    for name in ('avatar_pulse', 'avatar_research'):
        svg = frames[name]
        assert '<path' not in svg, 'без названия: букв нет'
        assert 'fill="white"' in svg.split('<g', 1)[0], 'светлый фон'
        assert 'translate(300 300) scale(1.5)' in svg, 'знак по центру и крупно'
    assert frames['scale'] == 1.5
    assert frames['avatar_start'] == frames['avatar_end'], 'бесшовный цикл: начало и конец — одна точка'


def _farthest_from_mark_center(svg):
    """Дальняя от центра знака (200, 200) точка всех его прямоугольников, в единицах знака.

    Скруглённый прямоугольник с обводкой — это внутренний прямоугольник, раздутый кругом радиуса
    rx + обводка/2; самая дальняя точка — у угла внутреннего прямоугольника плюс этот радиус.
    """
    start = svg.index('translate(300 300) scale(1.5)')
    inner = svg[start:svg.rindex('</g>')]  # затемнение конца цикла лежит после группы знака
    far = 0.0
    for tag in re.findall(r'<rect [^>]*>', inner):
        a = {k: float(v) for k, v in re.findall(r'(x|y|width|height|rx|stroke-width)="([0-9.]+)"', tag)}
        grow = a['stroke-width'] / 2
        r = min(a['rx'], a['width'] / 2, a['height'] / 2) + grow
        x0, y0 = a['x'] - grow + r, a['y'] - grow + r
        x1, y1 = a['x'] + a['width'] + grow - r, a['y'] + a['height'] + grow - r
        far = max(far, max(math.hypot(x - 200, y - 200) for x in (x0, x1) for y in (y0, y1)) + r)
    return far


def test_bot_avatar_mark_stays_inside_telegram_circle(frames):
    """Telegram обрезает аватарку кругом, вписанным в квадрат: радиус 300 при кадре 600.
    Дальняя точка — угол внешнего кольца pulse: 171,3 при масштабе 1, в аватарке ~257."""
    far = max(_farthest_from_mark_center(svg) for svg in frames['avatar_frames'])
    assert far == pytest.approx(171.26, abs=0.05)
    assert far * frames['scale'] < 300 * 0.9, 'знак целиком в круге, запас не меньше 10% радиуса'


def test_research_corners_are_rounded_like_pulse(frames):
    """2026-11-07: «скруглить края на kultura.research, чтобы они были такие же, как у пульса»."""
    for name in ('research_dark', 'research_light'):
        svg = frames[name]
        assert 'width="230" height="230" rx="41.4"' in svg, 'рамка: радиус 0,18 стороны, как у колец pulse'
        assert svg.count('width="36"') == 3 and svg.count('rx="6.84"') == 3, 'столбцы: 0,19 ширины'
    assert 'stroke-dasharray' in frames['research_drawing'], 'рамка рисуется линией по контуру'
    assert frames['pulse_dark_default'], 'тёмная тема по умолчанию не тронута'


def test_rendered_files_are_in_the_pack():
    motion = os.path.join(ROOT, 'brand', 'kultura-grid-motion', 'motion')
    for name in ('kultura-pulse-avatar-light.mp4', 'kultura-research-avatar-light.mp4'):
        with open(os.path.join(motion, name), 'rb') as f:
            assert f.read(12)[4:8] == b'ftyp', name
    for name in ('kultura-research.svg', 'kultura-research-light.svg'):
        with open(os.path.join(ROOT, 'brand', 'kultura-grid-motion', 'static', name), encoding='utf-8') as f:
            assert 'rx="41.4"' in f.read(), name
    with open(os.path.join(ROOT, 'kultura_bot', 'assets', 'avatar.mp4'), 'rb') as f, \
            open(os.path.join(motion, 'kultura-research-avatar-light.mp4'), 'rb') as g:
        assert f.read() == g.read(), 'аватарка kultura.research — светлая версия «только знак»'

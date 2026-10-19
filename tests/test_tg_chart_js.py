"""
Запуск tests/test_tg_chart_js.mjs (расчёты и форматирование static/tg_chart/charts.js) под pytest.

Описания графиков для JS-проверок — фикстуры прототипа после kultura_bot/charts/spec.normalize: так
JS проверяется на том же виде описания, какой отдаёт /api/tg/charts/<id>. Без node тест
пропускается (локально на Windows node может не стоять; в CI на ubuntu он есть).
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kultura_bot.charts import spec as tg_charts  # noqa: E402
from kultura_bot.charts.fixtures import FIXTURES  # noqa: E402

NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='node не установлен')
def test_charts_js_calculations(tmp_path):
    path = tmp_path / 'fixtures.json'
    path.write_text(json.dumps([{'name': n, 'chart': tg_charts.normalize(raw)} for n, raw in FIXTURES],
                               ensure_ascii=False), encoding='utf-8')
    run = subprocess.run([NODE, os.path.join(ROOT, 'tests', 'test_tg_chart_js.mjs'), str(path)],
                         capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'проверок прошли' in run.stdout


@pytest.mark.skipif(NODE is None, reason='node не установлен')
def test_static_js_syntax():
    for name in ('charts.js', 'app.js', 'dev.js', 'png.js'):
        run = subprocess.run([NODE, '--check', os.path.join(ROOT, 'static', 'tg_chart', name)],
                             capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, name + ': ' + run.stderr

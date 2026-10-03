"""Тесты хранилища фото накладных приёмки (core/receiving_photo_store.py). Сети нет.

Каталог — временный (set_dir), часы подменяются через msk_time.now.
Что проверяется:
- форма имени r<приёмка>_<ГГГГММДДTЧЧММСС>_<8 hex>.jpg, случайный хвост;
- is_valid_name — единственный допуск к диску: ../, абсолютные пути, перевод
  строки в конце (\\Z), чужие формы имени, не-строки отсекаются;
- check: пусто, больше MAX_PHOTO_BYTES, не JPEG по сигнатуре;
- save: файл на месте, содержимое то же, временного .tmp не остаётся; ошибка
  записи -> (False, текст без пути); delete — best-effort;
- photo_dir создаёт каталог; по умолчанию — get_data_path('receiving_photos');
- грамматика Python 3.10.
"""
import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['SESSION_COOKIE_SECURE'] = '0'

from core import msk_time  # noqa: E402
from core import receiving_photo_store as ps  # noqa: E402

JPEG = ps.JPEG_MAGIC + b'\xe0\x00\x10JFIF\x00' + b'\x00' * 1000 + b'\xff\xd9'
NOW = datetime(2026, 10, 3, 14, 5, 9, tzinfo=msk_time.MOSCOW_TZ)


@pytest.fixture
def photos(tmp_path, monkeypatch):
    folder = tmp_path / 'photos'
    ps.set_dir(str(folder))
    monkeypatch.setattr(msk_time, 'now', lambda: NOW)
    try:
        yield folder
    finally:
        ps.set_dir(None)


def test_make_name_format():
    name = ps.make_name(12, NOW)
    assert name.startswith('r12_20261003T140509_') and name.endswith('.jpg')
    assert ps.is_valid_name(name)
    assert ps.make_name(12, NOW) != name                 # случайный хвост
    assert ps.is_valid_name(ps.make_name(ps.MAX_RECEIPT_ID, NOW))
    for bad in (0, -1, ps.MAX_RECEIPT_ID + 1):
        with pytest.raises(ValueError):
            ps.make_name(bad, NOW)


def test_make_name_default_time_is_msk(monkeypatch):
    monkeypatch.setattr(msk_time, 'now', lambda: NOW)
    assert ps.make_name('7').startswith('r7_20261003T140509_')


@pytest.mark.parametrize('name', [
    'r1_20261003T140509_0a1b2c3d.jpg',
    'r123456789_20261003T140509_ffffffff.jpg',
])
def test_valid_names(name):
    assert ps.is_valid_name(name)


@pytest.mark.parametrize('name', [
    '', None, 12, b'r1_20261003T140509_0a1b2c3d.jpg',
    'r1_20261003T140509_0a1b2c3d.jpg\n',                 # $ пропустил бы перевод строки
    'r1_20261003T140509_0A1B2C3D.jpg',                   # только строчный hex
    'r1234567890_20261003T140509_0a1b2c3d.jpg',          # номер длиннее 9 цифр
    'r_20261003T140509_0a1b2c3d.jpg',
    '1_20261003T140509_0a1b2c3d.jpg',
    'r1_2026-10-03T140509_0a1b2c3d.jpg',
    'r1_20261003T140509_0a1b2c3d.jpeg',
    'r1_20261003T140509_0a1b2c3d.jpg.tmp',               # недописанный файл не раздаётся
    '../r1_20261003T140509_0a1b2c3d.jpg',
    '/etc/r1_20261003T140509_0a1b2c3d.jpg',
    'sub/r1_20261003T140509_0a1b2c3d.jpg',
    '2026-10-03_1_0a1b2c3d.jpg',                          # форма фото приёмки бара — не наша
])
def test_invalid_names(name, photos):
    assert not ps.is_valid_name(name)
    assert ps.photo_path(name) is None
    assert ps.exists(name) is False
    assert ps.delete(name) is False


def test_check():
    assert ps.check(JPEG) == (True, None)
    ok, err = ps.check(b'')
    assert not ok and err == 'Файл пустой'
    ok, err = ps.check(None)
    assert not ok
    ok, err = ps.check(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
    assert not ok and 'JPEG' in err
    big = ps.JPEG_MAGIC + b'\x00' * (ps.MAX_PHOTO_BYTES - len(ps.JPEG_MAGIC))
    assert ps.check(big) == (True, None)                  # ровно потолок — можно
    ok, err = ps.check(big + b'\x00')
    assert not ok and '8 МБ' in err


def test_save_exists_path_delete(photos):
    ok, name = ps.save(JPEG, 12)
    assert ok is True
    assert name.startswith('r12_20261003T140509_') and ps.is_valid_name(name)
    path = ps.photo_path(name)
    assert path == os.path.join(str(photos), name)
    assert ps.exists(name)
    with open(path, 'rb') as f:
        assert f.read() == JPEG
    assert sorted(os.listdir(photos)) == [name]           # .tmp не остался
    assert ps.delete(name) is True
    assert not ps.exists(name)
    assert ps.delete(name) is False                       # повторное удаление — без исключения


def test_save_rejects_bad_content(photos):
    assert ps.save(b'', 1) == (False, 'Файл пустой')
    ok, err = ps.save(b'GIF89a' + b'\x00' * 10, 1)
    assert not ok and 'JPEG' in err
    assert not os.path.exists(str(photos)) or os.listdir(photos) == []


def test_save_write_error_returns_text_without_path(tmp_path, monkeypatch):
    monkeypatch.setattr(msk_time, 'now', lambda: NOW)
    blocker = tmp_path / 'not_a_dir'
    blocker.write_text('файл на месте каталога')
    ps.set_dir(str(blocker))
    try:
        ok, err = ps.save(JPEG, 3)
    finally:
        ps.set_dir(None)
    assert ok is False
    assert err.startswith('Фото не сохранилось')
    assert str(tmp_path) not in err


def test_photo_dir_created_and_default(tmp_path, monkeypatch):
    target = tmp_path / 'deep' / 'receiving_photos'
    ps.set_dir(str(target))
    try:
        assert ps.photo_dir() == str(target) and target.is_dir()
    finally:
        ps.set_dir(None)
    seen = []

    def fake_data_path(name):
        seen.append(name)
        return str(tmp_path / 'kultura' / name)

    monkeypatch.setattr(ps, 'get_data_path', fake_data_path)
    assert ps.photo_dir() == str(tmp_path / 'kultura' / 'receiving_photos')
    assert seen == [ps.PHOTO_DIR_NAME] == ['receiving_photos']


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль должен разбираться грамматикой 3.10 (без PEP 701 и т.п.)."""
    import ast
    src = open(ps.__file__, encoding='utf-8').read()
    ast.parse(src, feature_version=(3, 10))


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))

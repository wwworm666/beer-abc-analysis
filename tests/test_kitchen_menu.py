"""Кухонный YML для Карт: фото с нашего сайта, каталог без сети."""
import xml.etree.ElementTree as ET

from core.auth_guard import PUBLIC_ENDPOINTS
from core.kitchen_menu import PHOTO_DIR, SOURCE, picture_filename, render_kitchen_menu


def _offers(xml):
    root = ET.fromstring(xml)
    return root.find('shop').find('offers').findall('offer')


def test_catalog_photos_are_served_from_our_site():
    xml = render_kitchen_menu('https://beerkultura.ru/')
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(xml)
    assert root.tag == 'yml_catalog'
    assert root.get('date') == '2026-09-20T22:50:51+03:00'
    shop = root.find('shop')
    assert shop.findtext('name') == 'Культура'
    categories = [(node.get('id'), node.text) for node in shop.find('categories')]
    assert categories[0] == ('1', 'Пицца')
    assert categories[-1] == ('7', 'Десерты')
    offers = _offers(xml)
    assert len(offers) == 29
    fries = next(offer for offer in offers if offer.get('id') == 'ttk-s02')
    assert fries.findtext('name') == 'Картофель фри'
    assert fries.findtext('price') == '370'
    assert fries.findtext('picture') == 'https://beerkultura.ru/static/kitchen-menu/Z8A_1318.jpg'
    assert 'storage.yandexcloud.net' not in xml
    pictures = [offer.findtext('picture') for offer in offers if offer.find('picture') is not None]
    assert len(pictures) == 24
    assert all(url.startswith('https://beerkultura.ru/static/kitchen-menu/') for url in pictures)


def test_every_referenced_photo_exists():
    root = ET.parse(SOURCE).getroot()
    names = []
    for picture in root.findall('.//picture'):
        name = picture_filename(picture.text)
        assert name
        assert (PHOTO_DIR / name).is_file()
        names.append(name)
    assert len(names) == 24


def test_missing_or_foreign_picture_is_dropped(tmp_path):
    catalog = tmp_path / 'menu.yml'
    catalog.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<yml_catalog date="2026-09-20T22:50:51+03:00">
  <shop>
    <name>Культура</name>
    <offers>
      <offer id="kept">
        <price>100</price>
        <picture>https://storage.yandexcloud.net/kultura-menu/photos/Z8A_1318.jpg</picture>
        <name>Есть фото</name>
      </offer>
      <offer id="gone">
        <picture>https://storage.yandexcloud.net/kultura-menu/photos/missing.jpg</picture>
        <name>Нет файла</name>
      </offer>
      <offer id="foreign">
        <picture>https://evil.example/../../etc/passwd.jpg</picture>
        <name>Чужая ссылка</name>
      </offer>
    </offers>
  </shop>
</yml_catalog>
""",
        encoding='utf-8',
    )
    photos = tmp_path / 'photos'
    photos.mkdir()
    (photos / 'Z8A_1318.jpg').write_bytes(b'jpeg')
    xml = render_kitchen_menu('https://beerkultura.ru', source=catalog, photo_dir=photos)
    offers = {offer.get('id'): offer for offer in _offers(xml)}
    assert offers['kept'].findtext('picture') == 'https://beerkultura.ru/static/kitchen-menu/Z8A_1318.jpg'
    assert offers['gone'].find('picture') is None
    assert offers['foreign'].find('picture') is None
    assert 'evil.example' not in xml


def test_kitchen_route_is_public():
    assert 'taps.kitchen_yml' in PUBLIC_ENDPOINTS
    assert (PHOTO_DIR / 'Z8A_1318.jpg').is_file()

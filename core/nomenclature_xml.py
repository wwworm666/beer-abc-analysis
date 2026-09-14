"""Полная номенклатура iiko из XML-кэша, приведённая к формату OLAP-номенклатуры.

Зачем. `extensions.get_cached_nomenclature` строит номенклатуру из OLAP
TRANSACTIONS за последние 30 дней, поэтому товар с остатком, но без движения за
месяц, в ней отсутствует и молча пропадал со всех вкладок /stocks (S-02 в
docs/technical/audits/STOCKS_AUDIT_2026-09-10.md). Полный список товаров есть в
XML `/products` — `data/cache/nomenclature__products.xml`, тот же файл, из
которого берутся баркоды (core/iiko_barcodes.py). Но в XML `parentId` — GUID
прямого родителя, а в OLAP — имя верхней группы; из-за этого фильтр «Напитки
Фасовка» на XML находил только подгруппы (S-03).

Что делает модуль: парсит XML один раз (кэш по mtime файла), для каждого
товара поднимается по цепочке групп до верхней и кладёт её имя в `parentId`,
как в OLAP. Результат можно сливать с OLAP-номенклатурой без ветвлений в
потребителях.

Формат записи (совпадает с OLAP): {name, type, category, mainUnit, parentId}
плюс служебные `groupId` (GUID прямого родителя) и `source` = 'xml'.
"""
import os
import threading
import xml.etree.ElementTree as ET
from typing import Dict, Optional

from core.iiko_barcodes import DEFAULT_XML_PATH

# Защита от циклов в parentId (в данных не встречались, но XML внешний).
_MAX_GROUP_DEPTH = 50

_cache: Optional[Dict[str, dict]] = None
_cache_mtime: Optional[float] = None
_cache_path: Optional[str] = None
_cache_lock = threading.Lock()


def _text(el, tag):
    child = el.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _top_group_name(start_parent_id, nodes):
    """Имя верхней группы для товара, чей прямой родитель — start_parent_id.

    Поднимаемся по parentId, пока родитель есть в XML. Узел, чьего родителя в
    XML нет (или parentId пуст), считается верхней группой. Если сам
    start_parent_id в XML отсутствует (товар-сирота) — None.
    """
    current = start_parent_id
    if not current or current not in nodes:
        return None
    for _ in range(_MAX_GROUP_DEPTH):
        node = nodes[current]
        parent = node.get('parentId')
        if not parent or parent not in nodes:
            return node.get('name')
        current = parent
    return nodes[current].get('name')


def parse_products_from_xml(xml_path: str = DEFAULT_XML_PATH) -> Dict[str, dict]:
    """Распарсить XML-номенклатуру в {product_id: запись в формате OLAP}.

    Группы (элементы без productType) в результат не попадают — они нужны
    только чтобы вычислить имя верхней группы. Отсутствующий или битый файл —
    пустой словарь, без исключения: у потребителей есть OLAP-номенклатура.
    """
    if not os.path.exists(xml_path):
        print(f"[NOMENCLATURE-XML] XML not found: {xml_path}")
        return {}
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        print(f"[NOMENCLATURE-XML] XML parse error: {e}")
        return {}

    nodes: Dict[str, dict] = {}
    for el in root.iter('productDto'):
        pid = _text(el, 'id')
        if not pid:
            continue
        nodes[pid] = {
            'name': _text(el, 'name'),
            'type': _text(el, 'productType'),
            'category': _text(el, 'productCategory'),
            'mainUnit': _text(el, 'mainUnit'),
            'parentId': _text(el, 'parentId'),
        }

    products: Dict[str, dict] = {}
    for pid, node in nodes.items():
        if not node.get('type'):
            continue  # группа, не товар
        group_id = node.get('parentId')
        products[pid] = {
            'name': node.get('name'),
            'type': node.get('type'),
            'category': node.get('category'),
            'mainUnit': node.get('mainUnit'),
            'parentId': _top_group_name(group_id, nodes),
            'groupId': group_id,
            'source': 'xml',
        }
    print(f"[NOMENCLATURE-XML] parsed {len(products)} products, {len(nodes) - len(products)} groups")
    return products


def get_xml_nomenclature(xml_path: str = DEFAULT_XML_PATH, force_refresh: bool = False) -> Dict[str, dict]:
    """Номенклатура из XML с кэшем в памяти; перечитывается при смене mtime файла."""
    global _cache, _cache_mtime, _cache_path
    try:
        mtime = os.path.getmtime(xml_path)
    except OSError:
        mtime = None
    with _cache_lock:
        if (not force_refresh and _cache is not None and _cache_path == xml_path
                and _cache_mtime == mtime):
            return _cache
        _cache = parse_products_from_xml(xml_path)
        _cache_mtime = mtime
        _cache_path = xml_path
        return _cache


def merge_nomenclature(primary: Optional[Dict[str, dict]],
                       fallback: Optional[Dict[str, dict]]) -> Dict[str, dict]:
    """Слить две номенклатуры: записи primary (OLAP, свежее) перекрывают fallback (XML).

    Входные словари не изменяются. Если оба пустые — {}.
    """
    merged: Dict[str, dict] = {}
    if fallback:
        merged.update(fallback)
    if primary:
        merged.update(primary)
    return merged

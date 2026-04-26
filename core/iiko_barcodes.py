"""Загрузка баркодов товаров iiko из XML-номенклатуры.

OLAP-кэш `data/cache/nomenclature_full.json` баркодов не содержит — они
есть только в полном XML `data/cache/nomenclature__products.xml`. Этот
модуль парсит XML и строит карту `{gtin14: [product_id, ...]}` для
стыковки с GTIN из Честного Знака.
"""
import os
import threading
import xml.etree.ElementTree as ET
from typing import Dict, List

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_XML_PATH = os.path.join(_BASE_DIR, 'data', 'cache', 'nomenclature__products.xml')

_cache: Dict[str, List[str]] | None = None
_cache_mtime: float | None = None
_cache_lock = threading.Lock()


def _normalize_gtin(raw: str) -> str | None:
    """EAN-13/GTIN-14 → канонический 14-значный с лидирующими нулями."""
    if not raw:
        return None
    s = raw.strip()
    if not s.isdigit():
        return None
    if len(s) > 14:
        return None
    return s.zfill(14)


def parse_barcodes_from_xml(xml_path: str = DEFAULT_XML_PATH) -> Dict[str, List[str]]:
    """Распарсить XML-номенклатуру и собрать {gtin14: [product_id, ...]}.

    Один баркод может относиться к нескольким товарам (редко, но возможно
    при дублях номенклатуры) — храним список product_id.
    """
    if not os.path.exists(xml_path):
        print(f"[BARCODES] XML not found: {xml_path}")
        return {}

    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        print(f"[BARCODES] XML parse error: {e}")
        return {}

    root = tree.getroot()
    barcode_map: Dict[str, List[str]] = {}

    for product in root.findall('productDto'):
        pid_el = product.find('id')
        if pid_el is None or not pid_el.text:
            continue
        pid = pid_el.text

        for bc_el in product.findall('.//barcode'):
            gtin = _normalize_gtin(bc_el.text or '')
            if not gtin:
                continue
            if gtin not in barcode_map:
                barcode_map[gtin] = []
            if pid not in barcode_map[gtin]:
                barcode_map[gtin].append(pid)

    print(f"[BARCODES] Loaded {len(barcode_map)} GTINs from XML")
    return barcode_map


def get_barcode_map(force_refresh: bool = False, xml_path: str = DEFAULT_XML_PATH) -> Dict[str, List[str]]:
    """Получить карту GTIN→product_ids с in-memory кэшем.

    Кэш инвалидируется автоматически при изменении mtime XML-файла или
    принудительно через force_refresh=True.
    """
    global _cache, _cache_mtime

    with _cache_lock:
        if force_refresh:
            _cache = None
            _cache_mtime = None

        try:
            current_mtime = os.path.getmtime(xml_path)
        except OSError:
            current_mtime = None

        if _cache is not None and _cache_mtime == current_mtime:
            return _cache

        _cache = parse_barcodes_from_xml(xml_path)
        _cache_mtime = current_mtime
        return _cache


def invert_to_product_gtins(barcode_map: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """{gtin: [product_id]} → {product_id: [gtin, ...]} для удобства lookup."""
    result: Dict[str, List[str]] = {}
    for gtin, pids in barcode_map.items():
        for pid in pids:
            if pid not in result:
                result[pid] = []
            result[pid].append(gtin)
    return result

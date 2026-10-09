"""Сорта для графа знаний — из реестра Untappd.

С 2026-10-04 реестр (resources/iiko_untappd_registry.json, связь по GUID товара iiko)
— единственный источник правды о пиве; прежний справочник по названиям
(beer_info_mapping.json) не читается. Модуль без Neo4j: загрузчик
(knowledge_graph/etl/loader.py) берёт отсюда готовые строки.

Узел Beer — одна карточка Untappd. Имя узла — как в таплисте
(core/taplist_post.post_name: «Festhaus Helles»), чтобы одинаковые названия разных
пивоварен («Helles» у Festhaus и у Jaws) не склеивались. Совпало имя у разных
карточек — к имени дописывается « #<id Untappd>». Связь кеги с сортом (CONTAINS) —
по точному имени товара iiko с проверенной связью.
"""
from typing import Dict, List, Optional, Tuple

from core.taplist_post import load_names, post_name
from core.untappd_registry import resolve_beer


def registry_beer_rows(registry: dict, names: Optional[dict] = None) -> Tuple[List[Dict], List[Dict]]:
    """-> (сорта, связи кег): сорта [{name, beer_name, brewery, style, abv, ibu,
    description, untappd_url, untappd_id}], связи [{keg_name, beer_name}].

    Обход товаров по GUID — порядок и имена при совпадениях детерминированы."""
    names = names or load_names()
    beers: Dict[str, Dict] = {}
    owner: Dict[str, str] = {}
    contains: List[Dict] = []
    products = registry.get('products') or {}
    for guid in sorted(products):
        card = resolve_beer(registry, guid)
        if not card:
            continue
        bid = str(card['id'])
        if bid not in beers:
            name = post_name({'untappd_beer_id': bid, 'beer_name': card['beer_name'],
                              'brewery': card['brewery']}, names)
            if owner.get(name, bid) != bid:
                name = f'{name} #{bid}'
            owner[name] = bid
            beers[bid] = {'name': name, 'beer_name': card['beer_name'], 'brewery': card['brewery'],
                          'style': card.get('style'), 'abv': card.get('abv_percent'), 'ibu': card.get('ibu'),
                          'description': card.get('description'), 'untappd_url': card['url'],
                          'untappd_id': bid}
        keg_name = (products[guid].get('iiko_name') or '').strip()
        if keg_name:
            contains.append({'keg_name': keg_name, 'beer_name': beers[bid]['name']})
    return list(beers.values()), contains

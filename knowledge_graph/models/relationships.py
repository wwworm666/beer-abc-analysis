"""
Relationship models and Cypher templates for Neo4j.
"""

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ============ Relationship Models ============

class BrewedBy(BaseModel):
    """Beer -[:BREWED_BY]-> Brewery"""
    beer_name: str
    brewery_name: str


class HasStyle(BaseModel):
    """Beer -[:HAS_STYLE]-> BeerStyle"""
    beer_name: str
    style_name: str


class LocatedIn(BaseModel):
    """Tap -[:LOCATED_IN]-> Bar"""
    tap_id: str
    bar_id: str


class OnTap(BaseModel):
    """Keg -[:ON_TAP]-> Tap"""
    keg_name: str
    tap_id: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class Contains(BaseModel):
    """Keg -[:CONTAINS]-> Beer"""
    keg_name: str
    beer_name: str


class MapsTo(BaseModel):
    """Dish -[:MAPS_TO]-> Keg"""
    dish_name: str
    keg_name: str


class SoldAt(BaseModel):
    """Sale -[:SOLD_AT]-> Bar"""
    sale_id: str
    bar_id: str


class OfBeer(BaseModel):
    """Sale -[:OF_BEER]-> Beer"""
    sale_id: str
    beer_name: str


class ServedBy(BaseModel):
    """Sale -[:SERVED_BY]-> Waiter"""
    sale_id: str
    waiter_name: str


class OnDate(BaseModel):
    """Sale -[:ON_DATE]-> Period"""
    sale_id: str
    period_id: str


class HasMetrics(BaseModel):
    """Period -[:HAS_METRICS]-> DailyMetrics"""
    period_id: str
    metrics_id: str


class ForBar(BaseModel):
    """DailyMetrics -[:FOR_BAR]-> Bar"""
    metrics_id: str
    bar_id: str


# ============ Cypher Templates ============

CYPHER_TEMPLATES = {
    # Create nodes
    "create_beer": """
        MERGE (b:Beer {name: $name})
        SET b += $props
        RETURN b
    """,

    "create_brewery": """
        MERGE (br:Brewery {name: $name})
        SET br += $props
        RETURN br
    """,

    "create_style": """
        MERGE (s:BeerStyle {name: $name})
        SET s += $props
        RETURN s
    """,

    "create_bar": """
        MERGE (bar:Bar {id: $id})
        SET bar += $props
        RETURN bar
    """,

    "create_tap": """
        MERGE (t:Tap {id: $id})
        SET t += $props
        RETURN t
    """,

    "create_keg": """
        MERGE (k:Keg {name: $name})
        SET k += $props
        RETURN k
    """,

    "create_dish": """
        MERGE (d:Dish {name: $name})
        SET d += $props
        RETURN d
    """,

    "create_waiter": """
        MERGE (w:Waiter {name: $name})
        RETURN w
    """,

    "create_period": """
        MERGE (p:Period {id: $id})
        SET p += $props
        RETURN p
    """,

    "create_daily_metrics": """
        MERGE (m:DailyMetrics {id: $id})
        SET m += $props
        RETURN m
    """,

    # Create relationships
    "rel_brewed_by": """
        MATCH (b:Beer {name: $beer_name})
        MATCH (br:Brewery {name: $brewery_name})
        MERGE (b)-[:BREWED_BY]->(br)
    """,

    "rel_has_style": """
        MATCH (b:Beer {name: $beer_name})
        MATCH (s:BeerStyle {name: $style_name})
        MERGE (b)-[:HAS_STYLE]->(s)
    """,

    "rel_located_in": """
        MATCH (t:Tap {id: $tap_id})
        MATCH (bar:Bar {id: $bar_id})
        MERGE (t)-[:LOCATED_IN]->(bar)
    """,

    "rel_on_tap": """
        MATCH (k:Keg {name: $keg_name})
        MATCH (t:Tap {id: $tap_id})
        MERGE (k)-[r:ON_TAP]->(t)
        SET r.started_at = $started_at, r.ended_at = $ended_at
    """,

    "rel_contains": """
        MATCH (k:Keg {name: $keg_name})
        MATCH (b:Beer {name: $beer_name})
        MERGE (k)-[:CONTAINS]->(b)
    """,

    "rel_maps_to": """
        MATCH (d:Dish {name: $dish_name})
        MATCH (k:Keg {name: $keg_name})
        MERGE (d)-[:MAPS_TO]->(k)
    """,

    "rel_for_bar": """
        MATCH (m:DailyMetrics {id: $metrics_id})
        MATCH (bar:Bar {id: $bar_id})
        MERGE (m)-[:FOR_BAR]->(bar)
    """,

    "rel_on_date": """
        MATCH (m:DailyMetrics {id: $metrics_id})
        MATCH (p:Period {id: $period_id})
        MERGE (m)-[:ON_DATE]->(p)
    """,

    # Batch operations
    "batch_create_beers": """
        UNWIND $batch AS item
        MERGE (b:Beer {name: item.name})
        SET b += item.props
    """,

    "batch_create_breweries": """
        UNWIND $batch AS item
        MERGE (br:Brewery {name: item.name})
        SET br += item.props
    """,

    "batch_create_styles": """
        UNWIND $batch AS item
        MERGE (s:BeerStyle {name: item.name})
        SET s += item.props
    """,

    "batch_rel_brewed_by": """
        UNWIND $batch AS item
        MATCH (b:Beer {name: item.beer_name})
        MATCH (br:Brewery {name: item.brewery_name})
        MERGE (b)-[:BREWED_BY]->(br)
    """,

    "batch_rel_has_style": """
        UNWIND $batch AS item
        MATCH (b:Beer {name: item.beer_name})
        MATCH (s:BeerStyle {name: item.style_name})
        MERGE (b)-[:HAS_STYLE]->(s)
    """,
}

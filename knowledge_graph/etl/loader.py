"""
ETL Loader for loading reference data into Neo4j.
Loads data from JSON mappings into the graph.
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from knowledge_graph.db import Neo4jConnection
from knowledge_graph.models.nodes import (
    Beer, Brewery, BeerStyle, Bar, Tap, Keg, Dish
)
from knowledge_graph.models.relationships import CYPHER_TEMPLATES

logger = logging.getLogger(__name__)


class ReferenceDataLoader:
    """
    Loader for reference/master data from JSON files.
    Loads: Beers, Breweries, Styles, Bars, Taps, Kegs, Dishes
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize loader.

        Args:
            data_dir: Path to data directory with JSON files
        """
        self.data_dir = Path(data_dir)
        self.db = Neo4jConnection()

    def load_all(self) -> Dict[str, int]:
        """
        Load all reference data into Neo4j.

        Returns:
            Dict with counts of loaded entities
        """
        results = {}

        with self.db:
            # 1. Load beers, breweries, styles from beer_info_mapping.json
            beer_results = self._load_beer_info()
            results.update(beer_results)

            # 2. Load bars and taps from taps_data.json
            bar_results = self._load_bars_and_taps()
            results.update(bar_results)

            # 3. Load kegs and dish mappings from dish_to_keg_mapping.json
            keg_results = self._load_kegs_and_dishes()
            results.update(keg_results)

            # 4. Create indexes for performance
            self._create_indexes()

        return results

    def _load_beer_info(self) -> Dict[str, int]:
        """Load beer info from beer_info_mapping.json"""
        file_path = self.data_dir / "beer_info_mapping.json"

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return {"beers": 0, "breweries": 0, "styles": 0}

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        beers: List[Dict] = []
        breweries: Set[str] = set()
        styles: Set[str] = set()
        beer_brewery_rels: List[Dict] = []
        beer_style_rels: List[Dict] = []

        for keg_name, info in data.items():
            beer_name = info.get("beer_name", keg_name)
            brewery_name = info.get("brewery")
            style_name = info.get("style")

            # Parse ABV (remove % sign)
            abv = None
            abv_str = info.get("abv", "")
            if abv_str:
                try:
                    abv = float(abv_str.replace("%", "").strip())
                except ValueError:
                    pass

            # Parse IBU
            ibu = None
            ibu_str = info.get("ibu", "")
            if ibu_str:
                try:
                    ibu = int(ibu_str)
                except ValueError:
                    pass

            # Create beer
            beer = Beer(
                name=beer_name,
                brewery=brewery_name,
                style=style_name,
                abv=abv,
                ibu=ibu,
                description=info.get("description"),
                untappd_url=info.get("untappd_url")
            )
            beers.append({
                "name": beer.name,
                "props": beer.to_cypher_props()
            })

            # Collect breweries
            if brewery_name:
                breweries.add(brewery_name)
                beer_brewery_rels.append({
                    "beer_name": beer_name,
                    "brewery_name": brewery_name
                })

            # Collect styles
            if style_name:
                styles.add(style_name)
                beer_style_rels.append({
                    "beer_name": beer_name,
                    "style_name": style_name
                })

        # Batch insert beers
        logger.info(f"Loading {len(beers)} beers...")
        self.db.execute_write(
            CYPHER_TEMPLATES["batch_create_beers"],
            {"batch": beers}
        )

        # Batch insert breweries
        brewery_batch = [{"name": b, "props": {"name": b}} for b in breweries]
        logger.info(f"Loading {len(brewery_batch)} breweries...")
        self.db.execute_write(
            CYPHER_TEMPLATES["batch_create_breweries"],
            {"batch": brewery_batch}
        )

        # Batch insert styles
        style_batch = [{"name": s, "props": self._parse_style(s)} for s in styles]
        logger.info(f"Loading {len(style_batch)} styles...")
        self.db.execute_write(
            CYPHER_TEMPLATES["batch_create_styles"],
            {"batch": style_batch}
        )

        # Create relationships
        logger.info("Creating BREWED_BY relationships...")
        self.db.execute_write(
            CYPHER_TEMPLATES["batch_rel_brewed_by"],
            {"batch": beer_brewery_rels}
        )

        logger.info("Creating HAS_STYLE relationships...")
        self.db.execute_write(
            CYPHER_TEMPLATES["batch_rel_has_style"],
            {"batch": beer_style_rels}
        )

        return {
            "beers": len(beers),
            "breweries": len(breweries),
            "styles": len(styles)
        }

    def _load_bars_and_taps(self) -> Dict[str, int]:
        """Load bars and taps from taps_data.json"""
        file_path = self.data_dir / "taps_data.json"

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return {"bars": 0, "taps": 0}

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        bars_count = 0
        taps_count = 0

        for bar_id, bar_data in data.items():
            bar_name = bar_data.get("name", bar_id)
            taps = bar_data.get("taps", [])

            # Create bar
            bar = Bar(
                id=bar_id,
                name=bar_name,
                tap_count=len(taps)
            )
            self.db.execute_write(
                CYPHER_TEMPLATES["create_bar"],
                {"id": bar.id, "props": bar.to_cypher_props()}
            )
            bars_count += 1

            # Create taps
            for tap_data in taps:
                tap_number = tap_data.get("tap_number", 0)
                tap_id = f"{bar_id}_tap{tap_number}"

                tap = Tap(
                    id=tap_id,
                    bar_id=bar_id,
                    tap_number=tap_number,
                    status=tap_data.get("status", "empty")
                )
                self.db.execute_write(
                    CYPHER_TEMPLATES["create_tap"],
                    {"id": tap.id, "props": tap.to_cypher_props()}
                )

                # Create LOCATED_IN relationship
                self.db.execute_write(
                    CYPHER_TEMPLATES["rel_located_in"],
                    {"tap_id": tap_id, "bar_id": bar_id}
                )
                taps_count += 1

        logger.info(f"Loaded {bars_count} bars, {taps_count} taps")
        return {"bars": bars_count, "taps": taps_count}

    def _load_kegs_and_dishes(self) -> Dict[str, int]:
        """Load kegs and dish mappings from dish_to_keg_mapping.json"""
        file_path = self.data_dir / "dish_to_keg_mapping.json"

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return {"kegs": 0, "dishes": 0}

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        kegs: Set[str] = set()
        dishes: Set[str] = set()
        dish_keg_rels: List[Dict] = []

        for dish_name, keg_name in data.items():
            dishes.add(dish_name)
            kegs.add(keg_name)
            dish_keg_rels.append({
                "dish_name": dish_name,
                "keg_name": keg_name
            })

        # Create kegs
        logger.info(f"Loading {len(kegs)} kegs...")
        for keg_name in kegs:
            volume = self._parse_volume(keg_name)
            keg = Keg(name=keg_name, volume_liters=volume)
            self.db.execute_write(
                CYPHER_TEMPLATES["create_keg"],
                {"name": keg.name, "props": keg.to_cypher_props()}
            )

        # Create dishes
        logger.info(f"Loading {len(dishes)} dishes...")
        for dish_name in dishes:
            dish = Dish(name=dish_name)
            self.db.execute_write(
                CYPHER_TEMPLATES["create_dish"],
                {"name": dish.name, "props": dish.to_cypher_props()}
            )

        # Create MAPS_TO relationships
        logger.info("Creating MAPS_TO relationships...")
        for rel in dish_keg_rels:
            self.db.execute_write(
                CYPHER_TEMPLATES["rel_maps_to"],
                rel
            )

        return {"kegs": len(kegs), "dishes": len(dishes)}

    def _create_indexes(self):
        """Create indexes for better query performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (b:Beer) ON (b.name)",
            "CREATE INDEX IF NOT EXISTS FOR (br:Brewery) ON (br.name)",
            "CREATE INDEX IF NOT EXISTS FOR (s:BeerStyle) ON (s.name)",
            "CREATE INDEX IF NOT EXISTS FOR (bar:Bar) ON (bar.id)",
            "CREATE INDEX IF NOT EXISTS FOR (bar:Bar) ON (bar.name)",
            "CREATE INDEX IF NOT EXISTS FOR (t:Tap) ON (t.id)",
            "CREATE INDEX IF NOT EXISTS FOR (k:Keg) ON (k.name)",
            "CREATE INDEX IF NOT EXISTS FOR (d:Dish) ON (d.name)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Period) ON (p.id)",
            "CREATE INDEX IF NOT EXISTS FOR (m:DailyMetrics) ON (m.id)",
        ]

        logger.info("Creating indexes...")
        for idx in indexes:
            try:
                self.db.execute(idx)
            except Exception as e:
                logger.debug(f"Index may already exist: {e}")

    def _parse_style(self, style_name: str) -> Dict:
        """Parse style name and extract category"""
        props = {"name": style_name}

        # Common categories
        categories = {
            "IPA": "IPA",
            "Stout": "Stout",
            "Porter": "Porter",
            "Lager": "Lager",
            "Pilsner": "Lager",
            "Wheat": "Wheat",
            "Sour": "Sour",
            "Mead": "Mead",
            "Cider": "Cider",
            "Ale": "Ale",
            "Bitter": "Ale",
            "Gose": "Sour",
        }

        for key, category in categories.items():
            if key.lower() in style_name.lower():
                props["category"] = category
                break

        return props

    def _parse_volume(self, keg_name: str) -> Optional[float]:
        """Extract volume in liters from keg name"""
        # Patterns: "20 л", "30л", "20л."
        match = re.search(r'(\d+)\s*л', keg_name.lower())
        if match:
            return float(match.group(1))
        return None


def load_reference_data(data_dir: str = "data") -> Dict[str, int]:
    """
    Convenience function to load all reference data.

    Args:
        data_dir: Path to data directory

    Returns:
        Dict with counts of loaded entities
    """
    loader = ReferenceDataLoader(data_dir)
    return loader.load_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = load_reference_data()
    print("\nLoading complete!")
    print("-" * 30)
    for entity, count in results.items():
        print(f"  {entity}: {count}")

"""
ETL for loading sales data from iiko OLAP API into Neo4j.
All data comes from iiko API, no local JSON files.
Optimized with batch operations for speed.
"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from knowledge_graph.db import Neo4jConnection
from core.olap_reports import OlapReports

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class SalesDataLoader:
    """
    Loader for sales data from iiko OLAP API.
    Uses batch operations for fast loading.
    """

    def __init__(self):
        self.db = Neo4jConnection()
        self.olap = OlapReports()

    def load_sales(
        self,
        date_from: str,
        date_to: str,
        bar_name: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Load sales data for a date range.

        Args:
            date_from: Start date YYYY-MM-DD
            date_to: End date YYYY-MM-DD
            bar_name: Optional bar name filter

        Returns:
            Dict with counts of loaded entities
        """
        results = {
            "sales": 0,
            "beers": 0,
            "styles": 0,
            "bars": 0,
            "periods": 0,
            "waiters": 0
        }

        # Connect to iiko
        logger.info("Connecting to iiko API...")
        if not self.olap.connect():
            logger.error("Failed to connect to iiko API")
            return results

        try:
            # Collect all data first
            all_records = []

            # Get draft beer sales
            logger.info(f"Fetching draft sales {date_from} to {date_to}...")
            draft_data = self.olap.get_draft_sales_by_waiter_report(
                date_from, date_to, bar_name
            )
            if draft_data and "data" in draft_data:
                for r in draft_data["data"]:
                    r["_category"] = "draft"
                all_records.extend(draft_data["data"])
                logger.info(f"Got {len(draft_data['data'])} draft records")

            # Get bottled beer sales
            logger.info(f"Fetching bottled sales {date_from} to {date_to}...")
            bottles_data = self.olap.get_beer_sales_report(
                date_from, date_to, bar_name
            )
            if bottles_data and "data" in bottles_data:
                for r in bottles_data["data"]:
                    r["_category"] = "bottles"
                all_records.extend(bottles_data["data"])
                logger.info(f"Got {len(bottles_data['data'])} bottled records")

            logger.info(f"Total records to process: {len(all_records)}")

            # Process and load into Neo4j
            with self.db:
                results = self._batch_load(all_records)
                self._create_indexes()

        finally:
            self.olap.disconnect()

        return results

    def _batch_load(self, records: List[Dict]) -> Dict[str, int]:
        """
        Load all records using batch operations.
        """
        # Collect unique entities
        beers: Dict[str, Dict] = {}
        styles: Set[str] = set()
        bars: Set[str] = set()
        periods: Set[str] = set()
        waiters: Set[str] = set()
        sales: List[Dict] = []

        # Beer-style relationships
        beer_styles: List[Dict] = []

        for record in records:
            dish_name = record.get("DishName", "")
            bar_name = record.get("Store.Name", "")
            style_name = record.get("DishGroup.ThirdParent", "")
            date_str = record.get("OpenDate.Typed", "")
            waiter_name = record.get("WaiterName", "")
            category = record.get("_category", "draft")

            quantity = float(record.get("DishAmountInt", 0) or 0)
            revenue = float(record.get("DishDiscountSumInt", 0) or 0)
            cost = float(record.get("ProductCostBase.ProductCost", 0) or 0)
            markup = float(record.get("ProductCostBase.MarkUp", 0) or 0)
            discount = float(record.get("DiscountSum", 0) or 0)

            if not dish_name or not bar_name:
                continue

            # Generate sale ID
            sale_id = self._generate_sale_id(
                dish_name, bar_name, date_str, waiter_name, quantity
            )

            # Period ID (just date part)
            period_id = date_str.split("T")[0] if "T" in date_str else date_str

            # Collect entities
            beers[dish_name] = {"name": dish_name}
            bars.add(bar_name)
            if style_name:
                styles.add(style_name)
                beer_styles.append({
                    "beer_name": dish_name,
                    "style_name": style_name
                })
            if period_id:
                periods.add(period_id)
            if waiter_name:
                waiters.add(waiter_name)

            # Sale data
            sales.append({
                "id": sale_id,
                "dish_name": dish_name,
                "bar_name": bar_name,
                "period_id": period_id,
                "waiter_name": waiter_name,
                "quantity": quantity,
                "revenue": revenue,
                "cost": cost,
                "margin": revenue - cost,
                "markup": markup,
                "discount": discount,
                "category": category
            })

        # Batch create nodes
        logger.info(f"Creating {len(beers)} beers...")
        self.db.execute_write("""
            UNWIND $batch AS item
            MERGE (b:Beer {name: item.name})
        """, {"batch": list(beers.values())})

        logger.info(f"Creating {len(styles)} styles...")
        self.db.execute_write("""
            UNWIND $batch AS name
            MERGE (s:BeerStyle {name: name})
        """, {"batch": list(styles)})

        logger.info(f"Creating {len(bars)} bars...")
        self.db.execute_write("""
            UNWIND $batch AS name
            MERGE (bar:Bar {name: name})
        """, {"batch": list(bars)})

        logger.info(f"Creating {len(periods)} periods...")
        self.db.execute_write("""
            UNWIND $batch AS id
            MERGE (p:Period {id: id})
            SET p.date = id
        """, {"batch": list(periods)})

        logger.info(f"Creating {len(waiters)} waiters...")
        self.db.execute_write("""
            UNWIND $batch AS name
            MERGE (w:Waiter {name: name})
        """, {"batch": list(waiters)})

        # Batch create beer-style relationships
        logger.info(f"Creating {len(beer_styles)} beer-style relationships...")
        self.db.execute_write("""
            UNWIND $batch AS item
            MATCH (b:Beer {name: item.beer_name})
            MATCH (s:BeerStyle {name: item.style_name})
            MERGE (b)-[:HAS_STYLE]->(s)
        """, {"batch": beer_styles})

        # Batch create sales with all relationships
        logger.info(f"Creating {len(sales)} sales with relationships...")

        # Process in chunks of 500
        chunk_size = 500
        for i in range(0, len(sales), chunk_size):
            chunk = sales[i:i + chunk_size]
            logger.info(f"Processing sales {i} to {i + len(chunk)}...")

            self.db.execute_write("""
                UNWIND $batch AS item
                MERGE (s:Sale {id: item.id})
                SET s.dish_name = item.dish_name,
                    s.quantity = item.quantity,
                    s.revenue = item.revenue,
                    s.cost = item.cost,
                    s.margin = item.margin,
                    s.markup = item.markup,
                    s.discount = item.discount,
                    s.category = item.category,
                    s.date = item.period_id
                WITH s, item
                MATCH (b:Beer {name: item.dish_name})
                MERGE (s)-[:OF_BEER]->(b)
                WITH s, item
                MATCH (bar:Bar {name: item.bar_name})
                MERGE (s)-[:SOLD_AT]->(bar)
                WITH s, item
                MATCH (p:Period {id: item.period_id})
                MERGE (s)-[:ON_DATE]->(p)
            """, {"batch": chunk})

            # Waiter relationships separately (not all sales have waiters)
            waiter_sales = [s for s in chunk if s.get("waiter_name")]
            if waiter_sales:
                self.db.execute_write("""
                    UNWIND $batch AS item
                    MATCH (s:Sale {id: item.id})
                    MATCH (w:Waiter {name: item.waiter_name})
                    MERGE (s)-[:SERVED_BY]->(w)
                """, {"batch": waiter_sales})

        return {
            "sales": len(sales),
            "beers": len(beers),
            "styles": len(styles),
            "bars": len(bars),
            "periods": len(periods),
            "waiters": len(waiters)
        }

    def _generate_sale_id(
        self,
        dish_name: str,
        bar_name: str,
        date_str: str,
        waiter_name: str,
        quantity: float
    ) -> str:
        """Generate unique sale ID from components."""
        components = f"{dish_name}|{bar_name}|{date_str}|{waiter_name}|{quantity}"
        return hashlib.md5(components.encode()).hexdigest()[:16]

    def _create_indexes(self):
        """Create indexes for better query performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (s:Sale) ON (s.id)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Sale) ON (s.date)",
            "CREATE INDEX IF NOT EXISTS FOR (b:Beer) ON (b.name)",
            "CREATE INDEX IF NOT EXISTS FOR (bar:Bar) ON (bar.name)",
            "CREATE INDEX IF NOT EXISTS FOR (st:BeerStyle) ON (st.name)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Period) ON (p.id)",
            "CREATE INDEX IF NOT EXISTS FOR (w:Waiter) ON (w.name)",
        ]

        logger.info("Creating indexes...")
        for idx in indexes:
            try:
                self.db.execute(idx)
            except Exception as e:
                logger.debug(f"Index may already exist: {e}")


def load_sales(
    date_from: str,
    date_to: str,
    bar_name: Optional[str] = None
) -> Dict[str, int]:
    """Load sales data."""
    loader = SalesDataLoader()
    return loader.load_sales(date_from, date_to, bar_name)


def load_last_month() -> Dict[str, int]:
    """Load sales for the last 30 days."""
    now = datetime.now(MOSCOW_TZ)
    date_to = now.strftime("%Y-%m-%d")
    date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    return load_sales(date_from, date_to)


def load_last_year() -> Dict[str, int]:
    """Load sales for the last 365 days."""
    now = datetime.now(MOSCOW_TZ)
    date_to = now.strftime("%Y-%m-%d")
    date_from = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    return load_sales(date_from, date_to)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Loading last 30 days of sales...")
    results = load_last_month()
    print("\nLoading complete!")
    print("-" * 30)
    for entity, count in results.items():
        print(f"  {entity}: {count}")

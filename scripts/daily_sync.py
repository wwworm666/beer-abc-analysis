"""
Daily sync script for Knowledge Graph.
Loads yesterday's data from iiko API into Neo4j.

Schedule this to run daily (e.g., 6:00 AM via Task Scheduler or cron).

Usage:
    python scripts/daily_sync.py           # sync yesterday
    python scripts/daily_sync.py 7         # sync last 7 days
    python scripts/daily_sync.py 30        # sync last 30 days
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_graph.etl.sales_loader import SalesDataLoader
from knowledge_graph.load_workshifts import load_workshifts

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def sync_data(days_back: int = 1):
    """
    Sync data for the specified number of days.

    Args:
        days_back: Number of days to sync (default: 1 = yesterday)
    """
    today = datetime.now()
    date_to = today.strftime('%Y-%m-%d')
    date_from = (today - timedelta(days=days_back)).strftime('%Y-%m-%d')

    logger.info("=" * 50)
    logger.info("DAILY SYNC - Knowledge Graph")
    logger.info("=" * 50)
    logger.info(f"Period: {date_from} to {date_to}")
    logger.info("")

    # 1. Sync sales data
    logger.info("[1/2] Syncing SALES data...")
    try:
        sales_loader = SalesDataLoader()
        sales_result = sales_loader.load_sales(date_from, date_to)
        logger.info(f"  Sales: {sales_result.get('sales', 0)}")
        logger.info(f"  Beers: {sales_result.get('beers', 0)}")
        logger.info(f"  Bars: {sales_result.get('bars', 0)}")
        logger.info(f"  Waiters: {sales_result.get('waiters', 0)}")
    except Exception as e:
        logger.error(f"  Failed to sync sales: {e}")

    # 2. Sync work shifts (attendance)
    logger.info("")
    logger.info("[2/2] Syncing WORK SHIFTS data...")
    try:
        load_workshifts(date_from, date_to)
    except Exception as e:
        logger.error(f"  Failed to sync work shifts: {e}")

    logger.info("")
    logger.info("=" * 50)
    logger.info("SYNC COMPLETE")
    logger.info("=" * 50)


if __name__ == "__main__":
    # Default: sync 1 day (yesterday)
    days = 1

    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python {sys.argv[0]} [days_back]")
            print(f"  Example: python {sys.argv[0]} 7  # sync last 7 days")
            sys.exit(1)

    sync_data(days)

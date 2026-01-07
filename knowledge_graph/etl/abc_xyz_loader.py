"""
ETL for loading ABC/XYZ analysis into Knowledge Graph.

ABC Analysis (per bar):
- ABC_Revenue: cumulative 80%/95%/100% by revenue
- ABC_Markup: fixed thresholds A≥120%, B=100-120%, C<100%
- ABC_Margin: cumulative 80%/95%/100% by margin

XYZ Analysis (per bar):
- CV = (StdDev / Mean) × 100%
- X: CV < 10% (stable)
- Y: CV 10-25% (medium)
- Z: CV > 25% (unstable)
"""

import numpy as np
from collections import defaultdict
from knowledge_graph.db import Neo4jConnection


class ABCXYZLoader:
    """Load ABC/XYZ analysis data into Neo4j."""

    def __init__(self):
        self.db = Neo4jConnection()

    def load_abc_xyz(self):
        """Main method to calculate and load ABC/XYZ metrics."""
        print("=" * 60)
        print("ABC/XYZ Analysis Loader")
        print("=" * 60)

        with self.db:
            # 1. Get aggregated data per beer per bar
            print("\n[1/5] Fetching aggregated sales data...")
            agg_data = self._get_aggregated_data()
            print(f"      Found {len(agg_data)} beer-bar combinations")

            # 2. Get weekly sales for XYZ
            print("\n[2/5] Fetching weekly sales for XYZ...")
            weekly_data = self._get_weekly_data()
            print(f"      Found {len(weekly_data)} weekly records")

            # 3. Calculate ABC for each bar
            print("\n[3/5] Calculating ABC categories...")
            abc_results = self._calculate_abc(agg_data)

            # 4. Calculate XYZ for each bar
            print("\n[4/5] Calculating XYZ categories...")
            xyz_results = self._calculate_xyz(weekly_data)

            # 5. Merge and load into graph
            print("\n[5/5] Loading into Neo4j...")
            self._load_to_graph(abc_results, xyz_results)

        print("\n" + "=" * 60)
        print("ABC/XYZ Analysis Complete!")
        print("=" * 60)

    def _get_aggregated_data(self):
        """Get aggregated sales per beer per bar."""
        query = """
        MATCH (s:Sale)-[:OF_BEER]->(b:Beer)
        MATCH (s)-[:SOLD_AT]->(bar:Bar)
        WITH bar.name as bar_name, b.name as beer_name,
             sum(s.revenue) as total_revenue,
             sum(s.margin) as total_margin,
             sum(s.quantity) as total_qty,
             sum(s.cost) as total_cost
        WHERE total_revenue > 0
        RETURN bar_name, beer_name, total_revenue, total_margin, total_qty, total_cost,
               CASE WHEN total_cost > 0
                    THEN (total_revenue - total_cost) / total_cost
                    ELSE 0 END as markup_percent
        ORDER BY bar_name, total_revenue DESC
        """
        return self.db.execute(query)

    def _get_weekly_data(self):
        """Get weekly sales for XYZ analysis."""
        # Group by ISO week using date function
        query = """
        MATCH (s:Sale)-[:OF_BEER]->(b:Beer)
        MATCH (s)-[:SOLD_AT]->(bar:Bar)
        MATCH (s)-[:ON_DATE]->(p:Period)
        WITH bar.name as bar_name, b.name as beer_name, p.date as sale_date,
             s.quantity as qty
        WITH bar_name, beer_name,
             substring(sale_date, 0, 4) + '-W' +
             toString(toInteger(substring(sale_date, 8, 2)) / 7 + 1) as year_week,
             qty
        WITH bar_name, beer_name, year_week, sum(qty) as weekly_qty
        RETURN bar_name, beer_name, year_week, weekly_qty
        ORDER BY bar_name, beer_name, year_week
        """
        return self.db.execute(query)

    def _calculate_abc(self, agg_data):
        """Calculate ABC categories for each bar."""
        # Group by bar
        by_bar = defaultdict(list)
        for row in agg_data:
            by_bar[row['bar_name']].append(row)

        results = {}
        for bar_name, beers in by_bar.items():
            print(f"      Processing {bar_name}: {len(beers)} beers")

            # Sort by revenue descending
            beers_sorted = sorted(beers, key=lambda x: x['total_revenue'], reverse=True)

            # Calculate cumulative percentages for revenue
            total_revenue = sum(b['total_revenue'] for b in beers_sorted)
            total_margin = sum(b['total_margin'] for b in beers_sorted)

            cumsum_rev = 0
            cumsum_margin = 0

            for beer in beers_sorted:
                cumsum_rev += beer['total_revenue']
                cumsum_margin += beer['total_margin']

                pct_rev = (cumsum_rev / total_revenue * 100) if total_revenue > 0 else 100
                pct_margin = (cumsum_margin / total_margin * 100) if total_margin > 0 else 100

                # ABC Revenue (cumulative)
                if pct_rev <= 80:
                    abc_rev = 'A'
                elif pct_rev <= 95:
                    abc_rev = 'B'
                else:
                    abc_rev = 'C'

                # ABC Markup (fixed thresholds)
                markup = beer.get('markup_percent', 0)
                if markup >= 1.2:
                    abc_markup = 'A'
                elif markup >= 1.0:
                    abc_markup = 'B'
                else:
                    abc_markup = 'C'

                # ABC Margin (cumulative)
                if pct_margin <= 80:
                    abc_margin = 'A'
                elif pct_margin <= 95:
                    abc_margin = 'B'
                else:
                    abc_margin = 'C'

                key = (bar_name, beer['beer_name'])
                results[key] = {
                    'abc_revenue': abc_rev,
                    'abc_markup': abc_markup,
                    'abc_margin': abc_margin,
                    'abc_combined': abc_rev + abc_markup + abc_margin,
                    'total_revenue': beer['total_revenue'],
                    'total_margin': beer['total_margin'],
                    'total_qty': beer['total_qty'],
                    'markup_percent': markup
                }

        return results

    def _calculate_xyz(self, weekly_data):
        """Calculate XYZ categories based on coefficient of variation."""
        # Group by bar+beer
        by_beer_bar = defaultdict(list)
        for row in weekly_data:
            key = (row['bar_name'], row['beer_name'])
            by_beer_bar[key].append(row['weekly_qty'])

        results = {}
        for key, weekly_sales in by_beer_bar.items():
            bar_name, beer_name = key

            # Calculate coefficient of variation
            cv = self._calc_cv(weekly_sales)

            # Categorize
            if cv < 10:
                xyz = 'X'
            elif cv < 25:
                xyz = 'Y'
            else:
                xyz = 'Z'

            results[key] = {
                'xyz_category': xyz,
                'cv_percent': round(cv, 2),
                'weeks_count': len(weekly_sales)
            }

        return results

    def _calc_cv(self, values):
        """Calculate coefficient of variation."""
        if len(values) < 2:
            return 100.0

        arr = np.array(values)
        non_zero = arr[arr > 0]

        if len(non_zero) == 0:
            return 100.0

        mean = np.mean(non_zero)
        if mean == 0:
            return 100.0

        std = np.std(non_zero)
        return (std / mean) * 100

    def _load_to_graph(self, abc_results, xyz_results):
        """Load ABC/XYZ results into Neo4j as ANALYZED_IN relationships."""
        # Merge results
        all_keys = set(abc_results.keys()) | set(xyz_results.keys())

        batch = []
        for key in all_keys:
            bar_name, beer_name = key
            abc = abc_results.get(key, {})
            xyz = xyz_results.get(key, {})

            record = {
                'bar_name': bar_name,
                'beer_name': beer_name,
                'abc_revenue': abc.get('abc_revenue', 'C'),
                'abc_markup': abc.get('abc_markup', 'C'),
                'abc_margin': abc.get('abc_margin', 'C'),
                'abc_combined': abc.get('abc_combined', 'CCC'),
                'xyz_category': xyz.get('xyz_category', 'Z'),
                'cv_percent': xyz.get('cv_percent', 100.0),
                'total_revenue': abc.get('total_revenue', 0),
                'total_margin': abc.get('total_margin', 0),
                'total_qty': abc.get('total_qty', 0),
                'markup_percent': abc.get('markup_percent', 0),
                'weeks_count': xyz.get('weeks_count', 0)
            }
            batch.append(record)

        # Batch load
        query = """
        UNWIND $batch as row
        MATCH (b:Beer {name: row.beer_name})
        MATCH (bar:Bar {name: row.bar_name})
        MERGE (b)-[r:ANALYZED_IN]->(bar)
        SET r.abc_revenue = row.abc_revenue,
            r.abc_markup = row.abc_markup,
            r.abc_margin = row.abc_margin,
            r.abc_combined = row.abc_combined,
            r.xyz_category = row.xyz_category,
            r.cv_percent = row.cv_percent,
            r.total_revenue = row.total_revenue,
            r.total_margin = row.total_margin,
            r.total_qty = row.total_qty,
            r.markup_percent = row.markup_percent,
            r.weeks_count = row.weeks_count
        """

        self.db.execute(query, {'batch': batch})
        print(f"      Created {len(batch)} ANALYZED_IN relationships")

        # Print summary
        self._print_summary(batch)

    def _print_summary(self, batch):
        """Print analysis summary."""
        print("\n" + "-" * 40)
        print("ABC Distribution:")

        # Count ABC combinations
        abc_counts = defaultdict(int)
        xyz_counts = defaultdict(int)
        for row in batch:
            abc_counts[row['abc_combined']] += 1
            xyz_counts[row['xyz_category']] += 1

        # Top ABC combinations
        sorted_abc = sorted(abc_counts.items(), key=lambda x: -x[1])[:10]
        for combo, count in sorted_abc:
            print(f"  {combo}: {count}")

        print("\nXYZ Distribution:")
        for cat in ['X', 'Y', 'Z']:
            print(f"  {cat}: {xyz_counts.get(cat, 0)}")


def main():
    """Run ABC/XYZ loader."""
    loader = ABCXYZLoader()
    loader.load_abc_xyz()


if __name__ == '__main__':
    main()

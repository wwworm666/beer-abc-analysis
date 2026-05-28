# Regression Matrix — 2026-04-03

## Implemented Offline Checks

| ID | Type | Target | Current status | Notes |
|---|---|---|---|---|
| REG-001 | `expectedFailure` unit test | `core.revenue_metrics.RevenueMetricsCalculator` must use a full-sales source for actual revenue | Implemented | Protects defect `L-001` without turning the suite red. |
| REG-002 | `expectedFailure` API test | `/api/discount-analyze` must not collapse repeated `OrderNum` values across different dates | Implemented | Protects defect `L-002`. |
| REG-003 | `expectedFailure` API test | `/api/dashboard-analytics` must return markup table rows in percent units, consistent with top-level fields | Implemented | Protects defect `L-003`. |
| REG-004 | Passing unit test | All-sales builder must keep `OpenDate.Typed`, `UniqOrderId.Id`, and delete filters | Implemented | Guards the main dashboard request contract. |
| REG-005 | Passing unit test | Waiter-aware sales builders must not add `OrderWaiter.Name` to grouping | Implemented | Guards against duplicate sales rows. |

## Fixture Catalog

| Fixture | Path | Used by |
|---|---|---|
| `all_sales_sample.json` | `tests/fixtures/audit/all_sales_sample.json` | `REG-001`, `REG-003` |
| `discount_order_collision.json` | `tests/fixtures/audit/discount_order_collision.json` | `REG-002` |

## Pending Live-Smoke Checklist

- Fetch `/v2/reports/olap/columns?reportType=SALES` from the target server and diff it against the locally assumed field set.
- Replay 2-3 production requests in read-only mode:
  - full sales
  - discount report
  - employee aggregated metrics
- Verify that the target server still exposes:
  - `ProductCostBase.MarkUp`
  - `Delivery.CustomerCreatedDateTyped`
  - `AuthUser`
  - `UniqOrderId.Id`

## Execution

Run the offline regression suite with:

```bash
python -m unittest -v tests.test_logic_audit_regressions
```

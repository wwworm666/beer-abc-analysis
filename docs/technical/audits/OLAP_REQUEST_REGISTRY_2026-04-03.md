# OLAP Request Registry — 2026-04-03

## Scope

This registry is the offline source map for every important iiko OLAP request used by the project.
The audit baseline comes from:

- `docs/iiko-api/md/formirovanie-olap-otcheta-v-api.md`
- `docs/iiko-api/md/olap-otchety-v2.md`
- local code in `core/`, `routes/`, `scripts/`, `tests/`, and `knowledge_graph/`

## Source-Of-Truth Rules

- Use OLAP v2 semantics first.
- For `SALES` reports, the audit treats `OpenDate.Typed` as the accounting day.
- `DateRange.to` is treated as exclusive, so application code must add `+1 day` when the UI period is inclusive.
- `DeletedWithWriteoff=NOT_DELETED` and `OrderDeleted=NOT_DELETED` are the default guard rails for normal sales analytics.
- `OrderNum` is not treated as a globally unique order identity.
- `ProductCostBase.MarkUp` is a `PERCENT` field in iiko metadata, i.e. a fraction from `0` to `1`.
- If local docs and live `/v2/reports/olap/columns` ever diverge, live metadata wins.

## Core Registry

| Query | Builder / Entry Point | reportType | Date field | Key fields | Main consumers | Audit note |
|---|---|---|---|---|---|---|
| Bottled sales | `core/olap_reports.py:151`, `core/olap_reports.py:627` with `draft=False` | `SALES` | `OpenDate.Typed` | group by `Store.Name`, `DishName`, `DishGroup.ThirdParent`, `DishForeignName`, `OpenDate.Typed`; aggregates include `DishDiscountSumInt`, `DiscountSum`, `ProductCostBase.ProductCost`, `ProductCostBase.MarkUp` | `routes/analysis.py`, `knowledge_graph/etl/sales_loader.py`, `core/revenue_metrics.py` | Despite the generic name, this request is filtered to `DishGroup.TopParent = Напитки Фасовка`. It is unsafe as a total-revenue source. |
| Draft sales | `core/olap_reports.py:198`, `core/olap_reports.py:627` with `draft=True` | `SALES` | `OpenDate.Typed` | same shape as bottled sales, but filtered to `Напитки Розлив` | `routes/analysis.py`, `core/draft_analysis.py` | Main source for draft liters, ABC/XYZ and waiter draft analytics. |
| Draft sales by waiter | `core/olap_reports.py:245`, `core/olap_reports.py:627` with `draft=True`, `include_waiter=True` | `SALES` | `OpenDate.Typed` | same as draft plus `WaiterName` | `routes/analysis.py`, `routes/employee.py`, `knowledge_graph/etl/sales_loader.py` | Builder explicitly avoids `OrderWaiter.Name` to prevent row duplication. |
| Kitchen sales | `core/olap_reports.py:292`, `core/olap_reports.py:519` | `SALES` | `OpenDate.Typed` | same financial aggregates, filter excludes draft and bottled top parents | `routes/employee.py`, dashboard derivations | Kitchen is defined as “everything not in draft/bottles”, so category drift here affects dashboard shares. |
| All sales | `core/olap_reports.py:339`, `core/olap_reports.py:573` | `SALES` | `OpenDate.Typed` | group by `Store.Name`, `DishName`, `DishGroup.TopParent`, `DishForeignName`, `OpenDate.Typed`, `UniqOrderId.Id`; aggregates include `UniqOrderId.OrdersCount`, `DishDiscountSumInt`, `DiscountSum`, `ProductCostBase.ProductCost`, `ProductCostBase.MarkUp` | `routes/dashboard.py`, exports, widgets | This is the only project request that carries category split plus `UniqOrderId.Id` in one payload. |
| Orders count | `core/olap_reports.py:699` | `SALES` | `OpenDate.Typed` | group by `Store.Name`, `OpenDate.Typed`; aggregate `UniqOrderId.OrdersCount` | fallback / explicit checks counting | Correct pattern for counting checks without `DishName` fan-out. |
| Bottled sales by waiter | `core/olap_reports.py:795`, `core/olap_reports.py:627` with `draft=False`, `include_waiter=True` | `SALES` | `OpenDate.Typed` | bottled request plus `WaiterName` | `routes/employee.py` | Same semantics as bottled sales, but waiter-scoped. |
| Kitchen sales by waiter | `core/olap_reports.py:842`, `core/olap_reports.py:936` | `SALES` | `OpenDate.Typed` | kitchen request plus `WaiterName` | `routes/employee.py` | Category shares depend on this request matching dashboard kitchen semantics. |
| Cancelled orders by waiter | `core/olap_reports.py:889`, `core/olap_reports.py:990` | `SALES` | `OpenDate.Typed` | group by `WaiterName`; aggregate `OrderNum`; filter `DeletedWithWriteoff != NOT_DELETED` | `core/employee_analysis.py` | Uses `OrderNum` for deleted-check counts, so uniqueness is weaker than `UniqOrderId`. |
| Employee aggregated metrics | `core/olap_reports.py:1025` | `SALES` | `OpenDate.Typed` | group by `AuthUser`; aggregates `UniqOrderId.OrdersCount`, `DishDiscountSumInt`, `DiscountSum`, `DishAmountInt` | `routes/employee.py`, `core/employee_analysis.py` | This is keyed by `AuthUser`, not `WaiterName`; downstream joins are therefore fragile. |
| Employee daily revenue | `core/olap_reports.py:1199` | `SALES` | `OpenDate.Typed` | group by `WaiterName`, `OpenDate.Typed`; aggregate `DishDiscountSumInt` | diagnostics / bonus logic support | Daily revenue semantics align with waiter ownership, not cashier/auth user ownership. |
| New loyalty cards by waiter | `core/olap_reports.py:1292` | `SALES` | `OpenDate.Typed` and `Delivery.CustomerCreatedDateTyped` | group by `WaiterName`, `Delivery.CustomerPhone`; aggregate `UniqOrderId.OrdersCount` | `routes/employee.py` | Depends on delivery/customer fields being available in the target server metadata. |
| Discount names | `core/olap_reports.py:1396` | `SALES` | `OpenDate.Typed` | group by `ItemSaleEventDiscountType`; aggregate `DishDiscountSumInt` | `routes/analysis.py` | Light discovery request, not suitable for revenue math. |
| Discount report | `core/olap_reports.py:1446` | `SALES` | `OpenDate.Typed` | group by `Store.Name`, customer card/name, `OrderNum`, `DishName`, discount type, `OpenDate.Typed`; aggregates `DishDiscountSumInt`, `DiscountSum` | `routes/analysis.py` | Uses `OrderNum` instead of a unique order id; downstream Python aggregation must build a safer composite key. |
| RFM report | `core/olap_reports.py:1535` | `SALES` | `OpenDate.Typed` | group by `Store.Name`, customer card/name, `OrderNum`, `OpenDate.Typed`; aggregates `DishDiscountSumInt`, `DiscountSum` | `routes/analysis.py` | Same order-identity risk as the discount report. |

## Ad-Hoc Requests Outside `core/olap_reports.py`

| Location | Purpose | Audit note |
|---|---|---|
| `tests/debug/test_date_variants.py` | Manual check for `OrderNum` vs `UniqOrderId.OrdersCount` and date bounds | Useful evidence that date exclusivity and order counters are still confusing project-wide. |
| `tests/debug/test_daily_checks.py` | Manual daily checks inspection | Groups by `WaiterName` + `OpenDate.Typed` and aggregates `OrderNum`; should not be treated as a reusable production counting pattern. |
| `tests/test_weihenstephan_data.py` | Manual field-probing for one bottled SKU | Useful for validating `ProductCostBase.MarkUp` as a fraction. |
| `scripts/import_export/export_draft_sales.py` | Historical export script | Treats `ProductCostBase.MarkUp` as a percent for presentation even though OLAP metadata describes it as a fraction. |
| `scripts/maintenance/investigate_delivery_user.py` | One-off investigation | Intentionally broad; not a production contract. |

## Business Flow Map

- Dashboard and revenue widgets depend on `get_all_sales_report` for category revenue, checks, markup and loyalty write-offs.
- Draft analytics depend on `get_draft_sales_report` and then recompute liters, shares, ABC/XYZ, margin and markup locally.
- Waiter analytics depend on `get_draft_sales_by_waiter_report`.
- Employee analytics join five OLAP datasets plus cash shifts, which creates the biggest risk surface for inconsistent identities.
- Discount and RFM analytics depend on Python-side aggregation after a denormalized OLAP pull; this is where order identity rules matter most.
- `knowledge_graph/etl/sales_loader.py` reuses bottled and draft requests and therefore inherits their semantic limits.

## Offline Status

- Request inventory completed for core production flows.
- Spec alignment completed for the main `SALES` requests.
- Read-only live smoke against the target iiko server is still pending.

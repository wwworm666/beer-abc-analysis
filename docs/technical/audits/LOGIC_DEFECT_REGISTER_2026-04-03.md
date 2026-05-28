# Logic Defect Register — 2026-04-03

## Confirmed Defects

### L-001 — Total revenue calculator uses bottled-sales query only

- Severity: High
- Status: Confirmed offline
- Location: `core/revenue_metrics.py:129`
- Problem:
  `_calculate_actual_revenue()` calls `OlapReports.get_beer_sales_report()`, but that request is filtered to `DishGroup.TopParent = Напитки Фасовка`.
- Why it is wrong:
  The method is documented and consumed as a total-fact revenue calculator. Using the bottled-sales request excludes draft and kitchen revenue.
- Impact:
  Revenue widgets and any caller of `RevenueMetricsCalculator` can materially undercount actual revenue.
- Expected behavior:
  Use the full-sales request or another source that includes draft, bottles and kitchen in one consistent total.
- Regression:
  `REG-001` in `tests/test_logic_audit_regressions.py`

### L-002 — Discount analytics undercount orders when `OrderNum` repeats across days

- Severity: High
- Status: Confirmed offline
- Location: `routes/analysis.py:989-1009`
- Problem:
  Store-level discount summaries keep `orders` as a `set(OrderNum)`.
- Why it is wrong:
  `OrderNum` is not a globally unique identity for the whole reporting period. Repeated order numbers on different dates collapse into one order.
- Impact:
  `stores_summary[*].orders_count` can undercount visits/orders for long periods or busy stores.
- Expected behavior:
  Use a composite identity such as `Store.Name + OpenDate.Typed + OrderNum`, or better, switch the OLAP request to a true unique order id.
- Regression:
  `REG-002` in `tests/test_logic_audit_regressions.py`

### L-003 — Dashboard response mixes markup fractions and percentages in the same payload

- Severity: Medium
- Status: Confirmed offline
- Location: `routes/dashboard.py:97-158`, `core/dashboard_analysis.py:110-133`
- Problem:
  Top-level response fields (`markupPercent`, `markupDraft`, `markupPackaged`, `markupKitchen`) are multiplied by `100`, but `table_data` keeps the raw fractional values from `DashboardMetrics`.
- Why it is wrong:
  The same API response exposes the same logical metric in two different units while labeling both as percent values.
- Impact:
  UI tables, exports or secondary consumers can show `1.31%` where the rest of the page shows `131.0%`.
- Expected behavior:
  Convert table rows that represent markup to percent units before returning them.
- Regression:
  `REG-003` in `tests/test_logic_audit_regressions.py`

## High-Risk Hypotheses

### H-001 — Employee breakdown mixes `AuthUser` totals with `WaiterName` category splits

- Severity: High-risk hypothesis
- Location: `core/employee_analysis.py:57-92`, `routes/employee.py:895-955`
- Risk:
  Total revenue/checks/discounts come from `AuthUser`, while category revenue and cost come from waiter-scoped datasets. If the “authorized user” and the dish waiter differ, shares and markups become internally inconsistent.
- Needed to confirm:
  Read-only live smoke on a period where `AuthUser != WaiterName` exists.

### H-002 — Discount and RFM “visits” collapse multiple same-day orders into one visit

- Severity: Medium-risk hypothesis
- Location: `routes/analysis.py:962-966`, `routes/analysis.py:1157-1161`
- Risk:
  Frequency is derived from unique `visit_dates`, not a unique order identity. Multiple same-day orders by one guest are treated as one visit.
- Needed to confirm:
  Product decision: is “visit” defined as a unique day or a unique check/order?

### H-003 — Knowledge graph loses bottled-sales waiter attribution

- Severity: Medium-risk hypothesis
- Location: `knowledge_graph/etl/sales_loader.py:65-75`
- Risk:
  Draft sales are loaded from the waiter-aware request, but bottled sales are loaded from `get_beer_sales_report()` without waiter fields. Graph edges to `Waiter` are therefore asymmetric by category.
- Needed to confirm:
  Decide whether bottled waiter attribution is required in the graph model.

## Audit Notes

- The OLAP builders consistently use `OpenDate.Typed` plus deletion filters in the main sales flows. This part is healthy.
- The highest-value follow-up is a read-only live smoke against `/v2/reports/olap/columns` and 2-3 production requests to validate field availability on the target server.

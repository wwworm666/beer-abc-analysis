# Audit Execution Report — 2026-04-03

## What was executed

### Offline

Command:

```bash
python -m unittest -v tests.test_logic_audit_regressions
```

Result:

- 5 tests executed
- 2 passing guard tests
- 3 expected failures documenting confirmed open defects

Observed result:

- `REG-001` reproduced the revenue-source defect
- `REG-002` reproduced the `OrderNum` collision defect in discount analytics
- `REG-003` reproduced the mixed-unit markup defect in dashboard output

### Live read-only smoke

Target:

- `https://first-federation.iiko.it:443/resto/api`

Checks performed:

1. Authentication
2. `GET /v2/reports/olap/columns?reportType=SALES`
3. Production-like `all_sales` builder for `2026-04-01` to `2026-04-03`
4. Production-like `draft + waiter` builder for `2026-04-01` to `2026-04-03`
5. `AuthUser` employee aggregate query for `2026-04-01` to `2026-04-03`

All checks were read-only.

## Live findings

### Field compatibility confirmed

The target server exposes and accepts the following fields:

- `OpenDate.Typed`
- `UniqOrderId.Id`
- `ProductCostBase.MarkUp`
- `AuthUser`
- `Delivery.CustomerCreatedDateTyped`
- `ItemSaleEventDiscountType`
- `WaiterName`
- `OrderWaiter.Name`
- `Store.Name`

Important metadata confirmed live:

- `ProductCostBase.MarkUp` type = `PERCENT`
- `AuthUser` is groupable and filterable
- `UniqOrderId.Id` is groupable and filterable

### Builder compatibility confirmed

`all_sales_builder`

- HTTP 200
- row count on short sample period: `288`
- sample keys included:
  - `DiscountSum`
  - `DishAmountInt`
  - `DishDiscountSumInt`
  - `DishGroup.TopParent`
  - `OpenDate.Typed`
  - `ProductCostBase.MarkUp`
  - `ProductCostBase.ProductCost`
  - `Store.Name`
  - `UniqOrderId.Id`

`draft_waiter_builder`

- HTTP 200
- row count on short sample period: `112`
- sample keys included:
  - `DiscountSum`
  - `DishAmountInt`
  - `DishDiscountSumInt`
  - `DishGroup.ThirdParent`
  - `OpenDate.Typed`
  - `ProductCostBase.MarkUp`
  - `ProductCostBase.ProductCost`
  - `Store.Name`
  - `UniqOrderId`

`employee AuthUser aggregate`

- HTTP 200
- row count on short sample period: `4`
- sample keys included:
  - `AuthUser`
  - `DiscountSum`
  - `DishAmountInt`
  - `DishDiscountSumInt`
  - `UniqOrderId`
  - `UniqOrderId.OrdersCount`

## Interpretation

- The main project OLAP builders are compatible with the current target iiko server.
- The current confirmed defects are therefore not caused by missing live fields.
- They are local business-logic defects in how the project chooses or interprets OLAP data.

## Confirmed Defects After Execution

- `L-001`: total revenue calculator uses bottled-sales source only
- `L-002`: discount analytics collapses repeated `OrderNum` values across dates
- `L-003`: dashboard response mixes markup fractions and percent units

## Remaining Open Questions

- `H-001`: whether `AuthUser` vs `WaiterName` creates real employee metric drift on production periods where they differ
- `H-002`: whether discount/RFM “visit” is intended to mean unique day or unique order
- `H-003`: whether bottled-sales waiter attribution is required in `knowledge_graph`

## Related Artifacts

- [OLAP_REQUEST_REGISTRY_2026-04-03.md](/c:/Users/wwwor/OneDrive/Документы/GitHub/beer-abc-analysis/docs/technical/audits/OLAP_REQUEST_REGISTRY_2026-04-03.md)
- [LOGIC_DEFECT_REGISTER_2026-04-03.md](/c:/Users/wwwor/OneDrive/Документы/GitHub/beer-abc-analysis/docs/technical/audits/LOGIC_DEFECT_REGISTER_2026-04-03.md)
- [REGRESSION_MATRIX_2026-04-03.md](/c:/Users/wwwor/OneDrive/Документы/GitHub/beer-abc-analysis/docs/technical/audits/REGRESSION_MATRIX_2026-04-03.md)
- [test_logic_audit_regressions.py](/c:/Users/wwwor/OneDrive/Документы/GitHub/beer-abc-analysis/tests/test_logic_audit_regressions.py)

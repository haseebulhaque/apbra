# Power BI modelling standards

Version: 1.0.0 | Synthetic customer: Contoso Sales Demo

## Star schema and date modelling
Use a simple star schema with single-direction dimension-to-fact relationships. Use the dedicated contiguous `DimDate` table and `DimDate[Date]` for calendar comparisons. Never fabricate missing prior-year values.

## Measures and executive KPIs
The executive sales view should include Total Sales, distinct Total Orders, Average Order Value, and Sales YoY %. Measures must state their business definition and use the confirmed currency and date coverage.

## Security boundary
A Region slicer is a filter, not access control. Do not claim row-level security unless it was explicitly requested, implemented, and tested in Power BI runtime.

# Power BI modelling standards

Version: 1.0.0 | Synthetic customer: Contoso Sales Demo

## Star schema and date modelling
Use a simple star schema with single-direction dimension-to-fact relationships. Use the dedicated contiguous `DimDate` table and `DimDate[Date]` for calendar comparisons. Never fabricate missing prior-year values.

Declare the grain of each fact table before defining measures. Dimensions should have stable unique keys, while fact foreign keys may repeat. Avoid bidirectional filters and many-to-many relationships in the bounded generator. A relationship inferred from matching names still requires key and cardinality evidence.

## Measures and executive KPIs
The executive sales view should include Total Sales, distinct Total Orders, Average Order Value, and Sales YoY %. Measures must state their business definition and use the confirmed currency and date coverage.

Explicit measures are preferred over implicit aggregation. Ratios must reference named numerator and denominator measures and handle empty or zero denominators. Counts must distinguish rows from business entities. AI-generated formula intent is advisory until deterministic compilation and runtime validation succeed.

## Security boundary
A Region slicer is a filter, not access control. Do not claim row-level security unless it was explicitly requested, implemented, and tested in Power BI runtime.

Security design requires an identified user-to-scope mapping and a trusted identity source. Hidden pages, filters, bookmarks, and visual interactions do not enforce access control. If security intent is ambiguous, generation requires human verification rather than an inferred role.

## Data quality and nulls
Record nullability, duplicate-key risk, incomplete periods, and type inference as design assumptions or warnings. Do not coerce identifiers into measures or treat missing values as zero without a confirmed business rule. Sample values help interpretation but are not evidence of full-dataset quality.

## Relationship validation
Every generated relationship must reference uploaded tables and columns and must match a discovered or explicitly confirmed key path. Active relationship identifiers must be unique. Unsupported composite, inactive, or many-to-many relationships require review instead of silent substitution.

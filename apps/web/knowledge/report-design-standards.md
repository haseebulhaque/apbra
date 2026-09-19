# Report design standards

Version: 1.0.0 | Synthetic customer: Contoso Sales Demo

## Visual selection
Prefer standard Power BI visuals. Use KPI cards for headline measures, a line chart for time trends, and bar charts for regional or category comparisons. Avoid pie or donut charts when precise comparison matters.

Tables are appropriate when exact values and several attributes must be scanned together. Slicers should correspond to decisions users actually make. Each visual needs a clear title, valid field bindings, and an explicit purpose. Unsupported or custom visuals require review.

## Page density and navigation
Keep executive pages focused and readable. Avoid excessive or unnecessary visuals; the bounded demo supports no more than 20 visuals on one page. Put the most important KPIs first and use clear page names and predictable navigation.

Use a consistent grid with aligned edges and sufficient whitespace. Place high-level KPIs before explanatory trends and comparisons. Long scrolling canvases, overlapping elements, and dense walls of visuals should be redesigned or routed for human review.

## Filters and interactions
Use persistent slicers only for high-value dimensions. Report and page filters should have a documented reason. Cross-highlighting may be used where it supports analysis, but advanced bookmarks, drill-through, custom tooltips, and complex interaction editing are outside the bounded compiler unless explicitly supported.

## Analytical narrative
Every page should answer a small set of business questions. Titles should describe the measure and comparison rather than generic chart types. Warnings, missing comparison periods, and limitations should be visible in the Report Design instead of hidden by formatting.

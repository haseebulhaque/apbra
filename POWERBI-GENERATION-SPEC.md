# Power BI generation and assurance contract

APBRA compiles a bounded structured Report Design into an editable PBIP/PBIR candidate. It does not generate Power BI files directly from free-form model text.

## Processing contract

```text
Original AI Report Design
→ deterministic normalization
→ strict integrity validation
→ deterministic guardrails
→ bounded PBIP/PBIR compiler
→ deterministic candidate validation
```

The original AI design remains immutable evidence. The compiler consumes a separate normalized design only after integrity and policy checks pass.

## Normalization

The normalizer handles supported intent expressed in a compiler-invalid shape. Independent slicer bindings become separate single-binding slicers; identical field/category bindings collapse; distinct supported bindings split safely. Resulting visual IDs are stable, deterministic and collision-safe.

Normalization does not invent fields or repair zero-binding slicers, measure-bound slicers, unknown fields, ambiguous semantics or layouts that cannot fit. These produce typed findings and stop before guardrails/compiler. Strict APBRA-138 integrity still evaluates the normalized result.

## Integrity rules

Deterministic checks enforce canonical unique measure IDs/names, supported aggregations, present and resolved ratio operands, no direct self-reference, no dependency cycles, validity of unused measures, resolved visual measure references, and visual-type cardinality.

- Cards require their supported measure binding.
- Charts require the supported category/field and measure contract.
- Tables require at least one supported field or measure.
- Slicers require exactly one field/category binding and zero measures.

The compiler repeats defensive validation; invalid structures cannot rely solely on upstream checks.

## Supported bounded profile

The current compiler supports common KPI cards, bar/column/line charts, tables, slicers, multiple bounded pages, explicit SUM/DISTINCTCOUNT/COUNT/AVERAGE and supported ratio measures, simple discovered relationships, embedded synthetic CSV data and tenant theme colours.

It does not execute arbitrary model-authored DAX, M, SQL or shell content. Custom visuals, DirectQuery/Direct Lake, predictive services, write-back, automatic RLS inference, gateway configuration, credential setup and production publishing are unsupported unless separately implemented and verified.

## Page geometry

Pages are 1,280 × 720. The compiler grid uses x=20 or x=630 and `y = 30 + row × 260`. Cards are 285 × 120; other supported visuals are 580 × 230. Every visual must remain non-negative and satisfy right edge ≤ 1,280 and bottom edge ≤ 720.

Normalization accounts for every existing visual, not only newly expanded slicers. If deterministic placement cannot fit without overlap or leaving the page, `LAYOUT_CAPACITY_EXCEEDED` records the attempted positions and compiler status remains `NOT_STARTED`. The obsolete arbitrary 12-visual threshold is not the current rule.

## Candidate validation

The validator checks the project/package structure, required files, report/model references, supported visual definitions, measures, fields, relationships and generated identifiers. Static PASS does not prove Power BI Desktop openability, rendering, refresh, numeric correctness or RLS behaviour. Those require exact-candidate Desktop evidence.

Any byte change creates a different candidate and requires validation again. Historical Desktop results do not authorize new bytes.

## Handover boundary

A successful run can download the project archive and dynamically generate lazy-loaded `Report-Deployment-Guide.pdf`. The guide explains deployment, configuration and validation actions. It does not publish, configure credentials or prove deployment.

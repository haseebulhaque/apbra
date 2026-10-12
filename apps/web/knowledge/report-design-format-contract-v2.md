# Report design format contract

Version: 2.0.0 | Technical representation only; no business-layout policy

## AI-authored geometry
The model authors schema2 page displayOption and every visual position. Page2.1.0 requires displayOption: DeprecatedDynamic, FitToPage, FitToWidth, ActualSize or ActualSizeTopLeft. All five values remain representable. Optional page width and height are numbers; absent choices remain absent. The renderer does not choose FitToPage or page dimensions.

## Visual container representation
VisualContainer2.9.0 requires numeric x, y, width and height. Optional z, tabOrder and angle are numbers, including fractional values. Nullable optional wire fields are omitted from the file. No grid, visual-count, positivity, inside-canvas, overlap or readability condition is inferred from this schema. The renderer preserves model-authored values exactly rather than choosing a report layout.

## Integrity and evidence
Supported typed fields and measure operands must resolve to the supplied source. Untrusted output never grants access, executes arbitrary code or authorizes publication. Existing saved schema1 designs and files remain immutable; a fresh explicit design proposal supplies new geometry. Technical file validity is not Power BI Desktop, calculation, business quality or deployment qualification.

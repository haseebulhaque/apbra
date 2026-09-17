import {confirmRequirements, type RequirementsSnapshot} from './requirements';
import {retrieveCuratedKnowledge, type CuratedKnowledge} from './knowledge';

export function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical((value as Record<string, unknown>)[k])).join(',') + '}';
}

function validatedInputs(snapshot: RequirementsSnapshot, evidence: CuratedKnowledge) {
  if (!snapshot || !snapshot.submission ||
      canonical(Object.keys(snapshot.submission).sort()) !== canonical(['answers','original_request','original_schema']) ||
      snapshot.confirmation !== 'EXPLICIT_LOCAL_USER_CONFIRMATION' ||
      canonical(snapshot) !== canonical(confirmRequirements(snapshot.submission, true)))
    throw new Error('DESIGN_REQUIREMENTS_INVALID: confirmed supported snapshot required');
  if (canonical(evidence) !== canonical(retrieveCuratedKnowledge('sales-v1')))
    throw new Error('DESIGN_EVIDENCE_INVALID: exact current curated source and version required');
}

// Implementation declarations, not imported expected-results fixtures. This is a
// deterministic golden-scenario planner, not an LLM or arbitrary prose interpreter.
function compose(snapshot: RequirementsSnapshot, evidence: CuratedKnowledge) {
  const measures = [
    {id:'total-sales', name:'Total Sales', dax:'SUM(FactSales[SalesAmount])', format:'"AUD "#,0.00'},
    {id:'total-orders', name:'Total Orders', dax:'DISTINCTCOUNT(FactSales[OrderId])', format:'0'},
    {id:'average-order-value', name:'Average Order Value', dax:'DIVIDE([Total Sales], [Total Orders])', format:'"AUD "#,0.00'},
    {id:'sales-previous-year', name:'Sales Previous Year', dax:'CALCULATE([Total Sales], DATEADD(DimDate[Date], -1, YEAR))', format:'"AUD "#,0.00'},
    {id:'sales-yoy-change', name:'Sales YoY Change', dax:'IF(ISBLANK([Sales Previous Year]), BLANK(), [Total Sales] - [Sales Previous Year])', format:'"AUD "#,0.00'},
    {id:'sales-yoy-percent', name:'Sales YoY %', dax:'DIVIDE([Sales YoY Change], [Sales Previous Year])', format:'0.00%'},
  ];
  const kpis=['total-sales','total-orders','average-order-value','sales-yoy-percent'];
  const visual = (id: string, kind: string, axis: string | null, measureIds: string[], title: string) =>
    ({id, kind, axis, measureIds, title, altText:title});
  return {
    artifact_kind:'DesignPlan' as const, schema_version:1 as const, planner_version:'capstone-deterministic-1',
    processing:'DETERMINISTIC_GOLDEN_FIXTURE' as const,
    provenance:{requirements:snapshot, knowledge:evidence, citations:evidence.rules.map(r=>r.citation)},
    projectName:'SalesPerformance',
    model:{tables:snapshot.submission.original_schema.tables, relationships:snapshot.submission.original_schema.relationships,
      dateTable:'DimDate', dateColumn:'Date', measures},
    pages:[
      {id:'executive-summary', name:'Executive Summary', visuals:[
        ...kpis.map(id=>visual('kpi-'+id,'card',null,[id],measures.find(m=>m.id===id)!.name)),
        visual('sales-trend','line','DimDate.YearMonth',['total-sales'],'Sales over time'),
        visual('sales-region','bar','DimRegion.RegionName',['total-sales'],'Sales by region'),
        visual('sales-category','bar','DimProduct.ProductCategory',['total-sales'],'Sales by product category')]},
      {id:'regional-performance',name:'Regional Performance',visuals:[
        visual('regional-sales','bar','DimRegion.RegionName',['total-sales'],'Regional sales'),
        visual('regional-detail','table','DimRegion.RegionName',kpis,'Regional performance detail')]},
    ],
    filters:snapshot.requirements.filters, initialYear:2025,
    theme:{name:'Sales Demo',background:'#FFFFFF',foreground:'#172B4D',primary:'#005A9C'},
    rls:{required:false,roles:[],securityClaim:'None; Region slicer is not RLS'},
    runtime:{desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN'},
  };
}
export type DesignPlan = ReturnType<typeof compose>;

export function createDesignPlan(snapshot: RequirementsSnapshot, evidence: CuratedKnowledge): DesignPlan {
  validatedInputs(snapshot,evidence);
  return structuredClone(compose(snapshot,evidence));
}

/** Strict runtime schema/semantic validation for the only supported plan version.
 * Unknown fields, stale source bytes and altered output bindings fail closed.
 * This validates the plan contract, never Power BI candidate/runtime correctness.
 */
export function validateDesignPlan(value: unknown): asserts value is DesignPlan {
  try {
    const plan=value as DesignPlan;
    validatedInputs(plan.provenance.requirements,plan.provenance.knowledge);
    if(canonical(plan)!==canonical(compose(plan.provenance.requirements,plan.provenance.knowledge))) throw new Error('mismatch');
  } catch { throw new Error('DESIGN_PLAN_INVALID: unsupported schema, source binding or plan content'); }
}

export function serializeDesignPlan(plan: unknown): string {
  validateDesignPlan(plan);
  return JSON.stringify(plan,null,2)+'\n';
}

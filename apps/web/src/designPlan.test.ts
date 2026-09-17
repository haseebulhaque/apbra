import {it,expect} from 'vitest';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import expected from '../../../tests/bootstrap/fixtures/sales-v1/design.expected.json';
import {confirmRequirements} from './requirements';
import {retrieveCuratedKnowledge} from './knowledge';
import {createDesignPlan,validateDesignPlan,serializeDesignPlan} from './designPlan';
const snapshot=()=>confirmRequirements({original_request:request.original_text,original_schema:schema,answers:Object.fromEntries(request.clarifications.map(c=>[c.id,c.golden_answer]))},true);
const plan=()=>createDesignPlan(snapshot(),retrieveCuratedKnowledge('sales-v1'));
it('creates inspectable persisted plan matching independent golden assertions',()=>{
 const p=plan(); validateDesignPlan(JSON.parse(serializeDesignPlan(p)));
 expect(p.projectName).toBe(expected.project_name);
 expect(p.model.tables.map(t=>t.name)).toEqual(expected.required_tables);
 expect(p.model.relationships).toEqual(expected.relationships);
 expect(p.model.measures.map(m=>({id:m.id,name:m.name}))).toEqual(expected.measures.map(m=>({id:m.id,name:m.name})));
 expect(p.pages.map(p=>p.name)).toEqual(expected.pages.map(p=>p.name));
 expect(p.filters).toEqual(expected.page_filters); expect(p.initialYear).toBe(expected.initial_date_filter.year);
 expect(p.rls.required).toBe(false); expect(p.rls.roles).toEqual([]);
 for(const id of expected.required_evidence_ids) expect(p.provenance.knowledge.orderedEvidenceIds).toContain(id);
 expect(p.model.measures.find(m=>m.id==='total-orders')!.dax).toBe('DISTINCTCOUNT(FactSales[OrderId])');
 expect(p.pages[0].visuals.filter(v=>v.kind==='card').map(v=>v.measureIds[0])).toEqual(['total-sales','total-orders','average-order-value','sales-yoy-percent']);
});
it('rejects tampered confirmed requirements and stale or forged evidence',()=>{
 const s=snapshot(); s.requirements.rls_required=true;
 expect(()=>createDesignPlan(s,retrieveCuratedKnowledge('sales-v1'))).toThrow();
 for(const mutate of [(e:any)=>e.fixtureVersion='stale',(e:any)=>e.rules[0].text='forged',(e:any)=>e.rules.pop(),(e:any)=>e.authorization='ADMIN']){
  const e=retrieveCuratedKnowledge('sales-v1');mutate(e);expect(()=>createDesignPlan(snapshot(),e)).toThrow();
 }
});
it('rejects incomplete schemas, changed bindings, injected DAX, citations and claims',()=>{
 for(const value of [null,{},[],{artifact_kind:'DesignPlan'}])expect(()=>validateDesignPlan(value)).toThrow();
 for(const mutate of [(p:any)=>p.schema_version=2,(p:any)=>p.pages[0].visuals[0].measureIds=['unknown'],(p:any)=>p.model.measures[0].dax='1',(p:any)=>p.provenance.citations.pop(),(p:any)=>p.runtime.desktop='PASS',(p:any)=>p.extra=true,(p:any)=>p.provenance.requirements.submission.extra=true]){
  const p=plan();mutate(p);expect(()=>validateDesignPlan(p)).toThrow();expect(()=>serializeDesignPlan(p)).toThrow();
 }
});
it('isolates plan/source mutations and accepts reordered JSON object keys',()=>{
 const s=snapshot(),e=retrieveCuratedKnowledge('sales-v1'),p=createDesignPlan(s,e);
 s.requirements.filters.length=0;e.rules[0].text='changed';validateDesignPlan(p);
 p.model.tables[0].name='changed';expect(plan().model.tables[0].name).toBe('DimDate');
 const fresh=plan();validateDesignPlan(Object.fromEntries(Object.entries(fresh).reverse()));
});

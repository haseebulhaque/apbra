import {it,expect} from 'vitest';
import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import expected from '../../../tests/bootstrap/fixtures/sales-v1/design.expected.json';
import {confirmRequirements} from './requirements';
import {retrieveCuratedKnowledge} from './knowledge';
import {createDesignPlan} from './designPlan';
import {generatePowerBI} from './powerbi';
import {zipFiles,crc32} from './archive';
const plan=()=>createDesignPlan(confirmRequirements({original_request:request.original_text,original_schema:schema,answers:Object.fromEntries(request.clarifications.map(c=>[c.id,c.golden_answer]))},true),retrieveCuratedKnowledge('sales-v1'));
it('generates actual linked PBIP/PBIR/TMDL with frozen data and design provenance',()=>{
 const p=plan(),c=generatePowerBI(p),f=c.files;
 expect(JSON.parse(f['SalesPerformance.pbip']).artifacts[0].report.path).toBe('SalesPerformance.Report');
 expect(JSON.parse(f['SalesPerformance.Report/definition.pbir']).datasetReference.byPath.path).toBe('../SalesPerformance.SemanticModel');
 expect(JSON.parse(f['DesignPlan.json'])).toEqual(p);
 expect(c.runtime).toEqual({desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN'});expect(c.release).toBe('NOT_ELIGIBLE');
 for(const name of expected.required_tables){const t=f[`SalesPerformance.SemanticModel/definition/tables/${name}.tmdl`];expect(t).toContain('mode: import');const b64=t.match(/Binary.FromText\("([A-Za-z0-9+/=]+)"/)![1];expect(atob(b64)).toBe(f['data/'+name+'.csv']);}
 const fact=f['SalesPerformance.SemanticModel/definition/tables/FactSales.tmdl'];
 for(const m of p.model.measures)expect(fact).toContain(`measure '${m.name}' = ${m.dax}`);
 expect(fact).toContain('formatString: """AUD ""#,0.00"');
 const rels=f['SalesPerformance.SemanticModel/definition/relationships.tmdl'];
 for(const rel of expected.relationships){expect(rels).toContain(`fromColumn: ${rel.from_table}.${rel.from_column}`);expect(rels).toContain(`toColumn: ${rel.to_table}.${rel.to_column}`);}
 expect(Object.values(f).join('')).not.toMatch(/Sql\.Database|Web\.Contents|File\.Contents/);
 expect(generatePowerBI(p)).toEqual(c);p.model.tables[0].name='mutated';expect(JSON.parse(f['DesignPlan.json']).model.tables[0].name).toBe('DimDate');
});
it('emits page/visual/query/filter bindings with explicit year and accessible titles',()=>{
 const p=plan(),f=generatePowerBI(p).files;
 const report=JSON.parse(f['SalesPerformance.Report/definition/report.json']);expect(report.filterConfig.filters).toHaveLength(4);
 expect(report.filterConfig.filters[3].filter.Where[0].Condition.In.Values[0][0].Literal.Value).toBe('2025L');
 for(const page of p.pages){const root=`SalesPerformance.Report/definition/pages/${page.id}`;expect(JSON.parse(f[root+'/page.json']).displayName).toBe(page.name);
 for(const v of page.visuals){const visual=JSON.parse(f[root+`/visuals/${v.id}/visual.json`]);expect(visual.visual.visualContainerObjects.general[0].properties.altText.expr.Literal.Value).toBe(`'${v.altText}'`);const text=JSON.stringify(visual.visual.query);for(const id of v.measureIds)expect(text).toContain(p.model.measures.find(m=>m.id===id)!.name);if(v.axis)expect(text).toContain(v.axis);}
 expect(Object.keys(f).filter(k=>k.startsWith(root+'/visuals/slicer-'))).toHaveLength(3);}
});
it('rejects raw prompt, missing confirmation and modified plans before output',()=>{
 for(const invalid of [request.original_text,{},null])expect(()=>generatePowerBI(invalid)).toThrow('DESIGN_PLAN_INVALID');
 const p=plan();p.model.measures[0].dax='malicious';expect(()=>generatePowerBI(p)).toThrow();
});
it('writes a deterministic ZIP with valid local and central records and safe limits',()=>{
 expect(crc32(new TextEncoder().encode('123456789'))).toBe(0xcbf43926);
 const files=generatePowerBI(plan()).files,bytes=zipFiles(files),dv=new DataView(bytes.buffer),decoder=new TextDecoder();let off=0;const seen:Record<string,string>={};
 while(dv.getUint32(off,true)===0x04034b50){expect(dv.getUint16(off+8,true)).toBe(0);const len=dv.getUint32(off+18,true),nl=dv.getUint16(off+26,true),extra=dv.getUint16(off+28,true);const name=decoder.decode(bytes.slice(off+30,off+30+nl)),start=off+30+nl+extra,data=bytes.slice(start,start+len);expect(crc32(data)).toBe(dv.getUint32(off+14,true));seen[name]=decoder.decode(data);off=start+len;}
 expect(seen).toEqual(files);expect(dv.getUint32(off,true)).toBe(0x02014b50);expect(dv.getUint32(bytes.length-22,true)).toBe(0x06054b50);expect(dv.getUint16(bytes.length-12,true)).toBe(Object.keys(files).length);expect(zipFiles(files)).toEqual(bytes);
 for(const path of ['../x','/absolute','a/../x','a//b','a\\b'])expect(()=>zipFiles({[path]:'x'})).toThrow('ARCHIVE_UNSAFE_PATH');
 expect(()=>zipFiles({})).toThrow();expect(()=>zipFiles({'x':'x'.repeat(2_000_001)})).toThrow('ARCHIVE_SIZE_LIMIT');
});

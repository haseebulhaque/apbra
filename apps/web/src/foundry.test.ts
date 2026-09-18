import {afterEach,expect,it,vi} from 'vitest';
import {generateGroundedReportDesign,interpretRequirement,validateInterpretation,validateReportDesign} from './foundry';
import {defaultTenantSettings} from './tenant';

const interpretation={request_kind:'POWER_BI_REPORT',objective:'Track sales',businessQuestions:['How much revenue?'],kpis:['Total Sales'],dimensions:['Region'],filters:['Sales.Region'],audience:'Executives',pages:['Executive Summary'],assumptions:[],ambiguities:['Sales definition'],clarifications:[{id:'sales-definition',category:'METRIC_DEFINITION',question:'How is sales defined?',reason:'The schema contains several monetary fields.',required:true}]};
afterEach(()=>vi.unstubAllGlobals());
it('validates structured interpretation and rejects malformed responses',()=>{
  expect(validateInterpretation(interpretation).clarifications[0].question).toContain('sales');
  expect(()=>validateInterpretation({...interpretation,kpis:'sales'})).toThrow('AI_RESPONSE_INVALID');
  expect(()=>validateInterpretation({...interpretation,clarifications:[interpretation.clarifications[0],interpretation.clarifications[0]]})).toThrow('AI_RESPONSE_INVALID');
});
it('parses a real-shaped chat completion and retains measured usage',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({model:'gpt-4.1',choices:[{message:{content:JSON.stringify(interpretation)}}],usage:{prompt_tokens:120,completion_tokens:80,total_tokens:200}}),{status:200,headers:{'Content-Type':'application/json'}})));
  const result=await interpretRequirement('build a sales report',{},defaultTenantSettings);
  expect(result.value.objective).toBe('Track sales');expect(result.metrics).toMatchObject({model:'gpt-4.1',promptTokens:120,completionTokens:80,totalTokens:200});
});
it('fails closed when Foundry is unavailable or returns invalid JSON',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));await expect(interpretRequirement('x',{},defaultTenantSettings)).rejects.toThrow('AI_SERVICE_UNAVAILABLE');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({choices:[{message:{content:'not-json'}}]}),{status:200})));await expect(interpretRequirement('x',{},defaultTenantSettings)).rejects.toThrow('AI_RESPONSE_INVALID');
});
it('requires grounded Report Design citations to come from retrieved chunks',async()=>{
  const plan={artifact_kind:'ReportDesign',schema_version:1,projectName:'SalesReport',overview:'Sales',audience:'Executives',dataModel:{factTables:['Sales'],dimensionTables:[],relationships:[]},measures:[],pages:[],filters:[],branding:{themeName:'Tenant',primary:'#005A9C',accent:'#2D7D9A'},accessibility:[],standardsApplied:[{citation:'local-knowledge:test.md@1#T-001',decision:'Use standard'}],assumptions:[],warnings:[],generationRequirements:[]};
  expect(validateReportDesign(plan,[plan.standardsApplied[0].citation])).toEqual(plan);expect(()=>validateReportDesign(plan,['other'])).toThrow('REPORT_DESIGN_CITATION_INVALID');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({model:'gpt-4.1',choices:[{message:{content:JSON.stringify(plan)}}],usage:{total_tokens:50}}),{status:200})));
  expect((await generateGroundedReportDesign({}, {},defaultTenantSettings,[{citation:plan.standardsApplied[0].citation,text:'rule'}])).value.standardsApplied).toHaveLength(1);
});

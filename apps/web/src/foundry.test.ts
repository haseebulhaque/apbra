import {afterEach,expect,it,vi} from 'vitest';
import {generateGroundedDesignPlan,interpretRequirement,validateAIDesignPlan,validateInterpretation} from './foundry';

const interpretation={request_kind:'POWER_BI_REPORT',objective:'Track sales',kpis:['Total Sales'],dimensions:['Region'],filters:['Region'],pages:['Executive Summary'],assumptions:[],clarifications:[{id:'sales-definition',category:'METRIC_DEFINITION',question:'How is sales defined?',reason:'The schema contains several monetary fields.',required:true}]};
afterEach(()=>vi.unstubAllGlobals());
it('validates structured interpretation and rejects malformed responses',()=>{
  expect(validateInterpretation(interpretation).clarifications[0].question).toContain('sales');
  expect(()=>validateInterpretation({...interpretation,kpis:'sales'})).toThrow('AI_RESPONSE_INVALID');
  expect(()=>validateInterpretation({...interpretation,clarifications:[interpretation.clarifications[0],interpretation.clarifications[0]]})).toThrow('AI_RESPONSE_INVALID');
});
it('parses a real-shaped chat completion and retains measured usage',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({model:'gpt-4.1',choices:[{message:{content:JSON.stringify(interpretation)}}],usage:{prompt_tokens:120,completion_tokens:80,total_tokens:200}}),{status:200,headers:{'Content-Type':'application/json'}})));
  const result=await interpretRequirement('build a sales report',{});
  expect(result.value.objective).toBe('Track sales');expect(result.metrics).toMatchObject({model:'gpt-4.1',promptTokens:120,completionTokens:80,totalTokens:200});
});
it('fails closed when Foundry is unavailable or returns invalid JSON',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));await expect(interpretRequirement('x',{})).rejects.toThrow('AI_SERVICE_UNAVAILABLE');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({choices:[{message:{content:'not-json'}}]}),{status:200})));await expect(interpretRequirement('x',{})).rejects.toThrow('AI_RESPONSE_INVALID');
});
it('requires grounded DesignPlan citations to come from retrieved chunks',async()=>{
  const plan={artifact_kind:'AIDesignPlan',schema_version:1,objective:'Sales',semantic_model:{grain:'SaleId',date_table:'DimDate',relationships:[],measures:[]},pages:[],applied_standards:[{citation:'local-knowledge:test.md@1#T-001',application:'Use standard'}],assumptions:[],limitations:[]};
  expect(validateAIDesignPlan(plan,[plan.applied_standards[0].citation])).toEqual(plan);expect(()=>validateAIDesignPlan(plan,['other'])).toThrow('AI_DESIGN_CITATION_INVALID');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({model:'gpt-4.1',choices:[{message:{content:JSON.stringify(plan)}}],usage:{total_tokens:50}}),{status:200})));
  expect((await generateGroundedDesignPlan({}, {},[{citation:plan.applied_standards[0].citation,text:'rule'}])).value.applied_standards).toHaveLength(1);
});

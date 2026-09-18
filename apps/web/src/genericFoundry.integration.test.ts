import fs from 'node:fs';
import path from 'node:path';
import {afterAll,beforeAll,expect,it} from 'vitest';
import {interpretRequirement,generateGroundedReportDesign,type Clarification} from './foundry';
import {retrieveKnowledge,evaluateRetrieval,clearRagIndex} from './rag';
import {evaluateGuardrails} from './guardrail';
import {compilePowerBI,validateGenericCandidate} from './genericPowerBI';
import {zipFiles} from './archive';
import {defaultTenantSettings} from './tenant';
import type {DataStructure} from './schemaIngestion';

const enabled=process.env.RUN_FOUNDRY_INTEGRATION==='1';
const base=process.env.FOUNDRY_BASE_URL||'http://127.0.0.1:5176';
const nativeFetch=globalThis.fetch;
const output=path.resolve(process.cwd(),'../../artifacts/local');
const evidence:{executedAt:string;scenarios:unknown[];retrieval?:unknown}={executedAt:new Date().toISOString(),scenarios:[]};

function schema(fileName:string,tableName:string,header:string[],rows:string[][]):DataStructure{return{kind:'REQUEST_DATA_STRUCTURE',fileName,format:'CSV',parsedAt:new Date().toISOString(),tables:[{name:tableName,sourceName:tableName,rowCount:rows.length,rows,columns:header.map((name,index)=>{const values=rows.map(row=>row[index]);return{name,sourceName:name,type:/date/i.test(name)?'date':values.every(value=>/^\d+(?:\.\d+)?$/.test(value))?'decimal':'text',nullable:false,sampleValues:[...new Set(values)].slice(0,3)}})}],relationships:[]}}
const scenarios=[
  {name:'RevenueOperations',requirement:'Build a Power BI report for revenue operations leaders. Show total revenue, distinct orders, and average order value. Include monthly revenue trend, revenue by region, and region and channel filters.',data:schema('revenue.csv','Revenue',['OrderId','OrderDate','Region','Channel','Revenue'],[['O1','2025-01-01','East','Direct','1200'],['O2','2025-02-02','West','Partner','800'],['O3','2025-03-03','East','Partner','1500']])},
  {name:'ServiceOperations',requirement:'Create a Power BI service desk report for operations managers. Show ticket count and average resolution hours, tickets by priority and state, a monthly opened-ticket trend, and priority and state filters.',data:schema('tickets.csv','Tickets',['TicketId','OpenedDate','Priority','State','ResolutionHours'],[['T1','2025-01-02','High','Closed','4'],['T2','2025-02-03','Low','Open','12'],['T3','2025-03-04','Medium','Closed','7']])},
];
function answer(question:Clarification){switch(question.category){case'TIME_COMPARISON':return'Use the uploaded date field and monthly calendar periods; show blanks where comparison data is unavailable.';case'SECURITY':return'Filters are report slicers only and do not grant data access.';case'AUDIENCE':return'Use the audience stated in the requirement.';case'PAGE_SCOPE':return'Use one focused summary page.';case'FILTER_SCOPE':return'Use the requested fields as report slicers.';case'METRIC_DEFINITION':return'Use the exact uploaded numeric and identifier fields named in the requirement, with conventional sum, distinct count, and average calculations.';default:return'Use only the uploaded fields and record any unresolved choice as a warning.'}}

beforeAll(()=>{if(enabled)globalThis.fetch=((input:RequestInfo|URL,init?:RequestInit)=>nativeFetch(typeof input==='string'&&input.startsWith('/')?base+input:input,init)) as typeof fetch});
afterAll(()=>{globalThis.fetch=nativeFetch;if(enabled){fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'final-architecture-evaluation.json'),JSON.stringify(evidence,null,2)+'\n')}});

it.runIf(enabled)('uses real Foundry and the bounded compiler for two materially different requests',async()=>{
  clearRagIndex();
  for(const scenario of scenarios){
    const interpretation=await interpretRequirement(scenario.requirement,scenario.data,defaultTenantSettings);
    expect(interpretation.value.request_kind).toBe('POWER_BI_REPORT');
    const answers=Object.fromEntries(interpretation.value.clarifications.map(question=>[question.id,answer(question)]));
    const snapshot={requirement:scenario.requirement,interpretation:interpretation.value,clarificationAnswers:answers,confirmation:'CONFIRMED'};
    const query=[scenario.requirement,interpretation.value.objective,...interpretation.value.kpis,...interpretation.value.dimensions,...Object.values(answers)].join('\n');
    const retrieval=await retrieveKnowledge(query,defaultTenantSettings.rag.topK);
    const design=await generateGroundedReportDesign(snapshot,scenario.data,defaultTenantSettings,retrieval.retrieved.map(({citation,text})=>({citation,text})));
    const decision=evaluateGuardrails(interpretation.value,design.value,scenario.data,defaultTenantSettings);
    if(!['PASS','WARNING'].includes(decision.outcome))throw new Error(JSON.stringify({scenario:scenario.name,decision,design:design.value},null,2));
    const candidate=compilePowerBI(design.value,scenario.data,defaultTenantSettings);
    const validation=validateGenericCandidate(candidate,design.value,scenario.data);
    expect(validation.status).toBe('PASS');
    fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,`${candidate.projectName}.candidate.zip`),Buffer.from(zipFiles(candidate.files)));
    evidence.scenarios.push({name:scenario.name,status:'PASS',interpretationMetrics:interpretation.metrics,clarifications:interpretation.value.clarifications,rag:{model:retrieval.embeddingModel,chunksIndexed:retrieval.chunksIndexed,citations:retrieval.retrieved.map(chunk=>chunk.citation),indexMetrics:retrieval.indexMetrics,queryMetrics:retrieval.queryMetrics},designMetrics:design.metrics,projectName:candidate.projectName,policy:decision,validation,artifact:`${candidate.projectName}.candidate.zip`});
  }
},120_000);

it.runIf(enabled)('routes a natural unrelated request outside generation',async()=>{
  const data=scenarios[0].data;const request='Write a marketing campaign for our new product.';
  const interpretation=await interpretRequirement(request,data,defaultTenantSettings);
  const decision=evaluateGuardrails(interpretation.value,null,data,defaultTenantSettings);
  expect(interpretation.value.request_kind).toBe('OUT_OF_SCOPE');expect(decision.outcome).toBe('OUT_OF_SCOPE');expect(decision.generation).toBe('NOT_STARTED');
  evidence.scenarios.push({name:'UnrelatedRequest',status:'OUT_OF_SCOPE',interpretationMetrics:interpretation.metrics,policy:decision,artifact:null});
},60_000);

it.runIf(enabled)('measures semantic retrieval against the governed corpus',async()=>{
  const result=await evaluateRetrieval(undefined,3);expect(result.hitRate).toBeGreaterThanOrEqual(0.85);evidence.retrieval=result;
},120_000);

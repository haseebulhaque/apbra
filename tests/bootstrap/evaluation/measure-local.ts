/** APBRA-124 bounded sequential local workload; not a non-AI API/SLA test. */
import {writeFileSync} from 'node:fs';
import {cpus,release,totalmem} from 'node:os';
import request from '../fixtures/sales-v1/request.json';import schema from '../fixtures/sales-v1/schema.json';
import {confirmRequirements} from '../../../apps/web/src/requirements';import {retrieveCuratedKnowledge} from '../../../apps/web/src/knowledge';import {createDesignPlan} from '../../../apps/web/src/designPlan';import {generatePowerBI} from '../../../apps/web/src/powerbi';import {validateCandidate,createFailureCandidate} from '../../../apps/web/src/validation';
async function main(){const samples:any[]=[];for(let i=0;i<20;i++){
 const durations:any={};function measure<T>(name:string,fn:()=>T){const start=performance.now();try{return fn();}finally{durations[name]=performance.now()-start;}}
 const started=performance.now();let status='COMPLETE',error=null,result:any;try{
 const s=measure('requirements',()=>confirmRequirements({original_request:request.original_text,original_schema:schema,answers:Object.fromEntries(request.clarifications.map(c=>[c.id,c.golden_answer]))},true));
 const k=measure('retrieval',()=>retrieveCuratedKnowledge('sales-v1'));const p=measure('design',()=>createDesignPlan(s,k));const c=measure('generation',()=>generatePowerBI(p));const candidate=i%5===4?createFailureCandidate(c):c;const vstart=performance.now();result=await validateCandidate(candidate);durations.validation=performance.now()-vstart;
 }catch(e){status='ERROR';error=(e as Error).message;}samples.push({index:i,state:i===0?'FIRST_INVOCATION_AFTER_MODULE_LOAD':'WARM',declaredFailure:i%5===4,status,error,durations,totalMs:performance.now()-started,validation:result});}
 const stages=['requirements','retrieval','design','generation','validation'];const summary=Object.fromEntries(stages.map(stage=>{const a=samples.map(s=>s.durations[stage]).filter(x=>typeof x==='number').sort((a,b)=>a-b);return[stage,{n:a.length,min:a[0],max:a.at(-1),p50:a[Math.ceil(a.length*.5)-1],p95:a[Math.ceil(a.length*.95)-1],method:'nearest_rank'}];}));
 writeFileSync(process.argv[2],JSON.stringify({sourceRevision:process.env.APBRA_SOURCE_REVISION,environment:{node:process.version,os:process.platform,osRelease:release(),architecture:process.arch,cpu:cpus()[0].model,memoryBytes:totalmem(),concurrency:1,sampleCount:20,warmup:0,model:'NOT_INVOKED',costCap:'Zero provider calls',fixtureTables:schema.tables.length,fixtureVersion:schema.fixture_version},workload:'20 sequential local module flows; every fifth candidate deliberately removes date relationship. All samples retained. Initial module load/startup excluded; first invocation identified.',apiTarget:'NOT_APPLICABLE: no API in bounded local Capstone',providerCost:null,localCost:'UNMEASURED',samples,summary},null,2)+'\n',{flag:'wx'});
}
main().catch(e=>{console.error(e);process.exitCode=1;});

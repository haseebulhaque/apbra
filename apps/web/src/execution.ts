/** Local observations, never authorization or proof of external runtime. */
export type EvidenceClass='REAL_LOCAL_PROCESSING'|'SIMULATED_IDENTITY';
export type Step={id:string;stage:string;generation:number;parents:string[];startedAt:string;durationMs:number|null;status:'RUNNING'|'COMPLETE'|'ERROR';evidenceClass:EvidenceClass;input?:unknown;output?:unknown;error?:string};
export function createExecutionTrace(clock=()=>performance.now(),wall=()=>new Date().toISOString(),uuid:()=>string=()=>crypto.randomUUID()){
 const id=uuid(),startedAt=wall();let generation=1;const steps:Step[]=[],timers=new Map<string,number>(),active=new Map<string,string>();let governanceEpoch=0;const epochs=new Map<string,number>();
 const clone=<T,>(value:T):T=>JSON.parse(JSON.stringify(value));
 function start(stage:string,evidenceClass:EvidenceClass='REAL_LOCAL_PROCESSING',input?:unknown){
  const step:Step={id:uuid(),stage,generation,parents:[...active.values()],startedAt:wall(),durationMs:null,status:'RUNNING',evidenceClass,input:input===undefined?undefined:clone(input)};
  steps.push(step);epochs.set(step.id,governanceEpoch);timers.set(step.id,clock());return step.id;
 }
 function finish(token:string,output:unknown,error?:string){
  const step=steps.find(s=>s.id===token);if(!step||step.status!=='RUNNING')throw new Error('INVALID_TRACE_TOKEN');
  const copied=output===undefined?undefined:clone(output);
  step.durationMs=Math.max(0,clock()-timers.get(token)!);step.status=error?'ERROR':'COMPLETE';step.output=copied;step.error=error;timers.delete(token);
  if(!error&&step.generation===generation&&(step.evidenceClass!=='SIMULATED_IDENTITY'||epochs.get(token)===governanceEpoch))active.set(step.stage,step.id);
 }
 function invalidate(reason:string){const token=start('INVALIDATED');finish(token,{reason});generation++;active.clear();}
 function invalidateGovernance(reason:string){const token=start('GOVERNANCE_INVALIDATED','SIMULATED_IDENTITY');finish(token,{reason});governanceEpoch++;for(const [stage,id] of active){if(steps.find(s=>s.id===id)?.evidenceClass==='SIMULATED_IDENTITY')active.delete(stage);}}
 return {id,start,finish,invalidate,invalidateGovernance,
  sync<T>(stage:string,work:()=>T){const token=start(stage);try{const output=work();finish(token,output);return output;}catch(e){finish(token,undefined,'STEP_FAILED');throw e;}},
  export(){return clone({kind:'CapstoneExecution',version:1,id,startedAt,exportedAt:wall(),generation,active:Object.fromEntries(active),steps,
   provenance:{fixture:'sales-v1/1.0.0',architecture:'21.03/v2',implementation:'APBRA-136/execution-1',pipelineBaseline:'b471a49e3faef825ca694b5b734c66ed36e28ebb'},
   timingBasis:'Monotonic local processing duration per observed action; excludes user think time. No percentile or cross-environment claim.',
   usage:{modelCalls:0,modelTokens:0,providerCost:null,currency:null,basis:'Deterministic local fixture processing; no model/provider invocation. Infrastructure, electricity and engineering costs not measured.'},
   evidenceBoundary:{identity:'SIMULATED',planning:'DETERMINISTIC_GOLDEN_FIXTURE',desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN',deployment:'NOT_RUN',automaticRepair:'UNSUPPORTED'},
   retention:'Browser memory until refresh; saved export retains these observations. Local editable evidence is not a signed authorization record.'});}
 };
}
export type ExecutionTrace=ReturnType<typeof createExecutionTrace>;

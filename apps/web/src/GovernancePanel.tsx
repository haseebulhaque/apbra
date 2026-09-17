import type {ExecutionTrace} from './execution';
import {useEffect,useRef,useState} from 'react';
import {createDemoGovernance,type OperationView,type Release} from './governance';
import type {Candidate} from './powerbi';
import {createFailureCandidate} from './validation';
import {zipFiles} from './archive';
export function GovernancePanel({candidate,onState,trace,notify}:{candidate:Candidate|null;onState:(state:string)=>void;trace:ExecutionTrace;notify:()=>void}){
 const [adapter]=useState(createDemoGovernance);
 const [sessions]=useState(()=>({requester:adapter.issueDemoSession('requester'),reviewer:adapter.issueDemoSession('reviewer'),trusted:adapter.issueDemoSession('trusted')}));
 const [route,setRoute]=useState<'requester'|'trusted'>('requester'),[operation,setOperation]=useState<OperationView|null>(null);
 const [release,setRelease]=useState<Release|null>(null),[url,setUrl]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [reason,setReason]=useState('Reviewed synthetic source checks and acknowledged NOT_RUN runtime limits.');
 const [evidence,setEvidence]=useState(adapter.exportEvidence());const epoch=useRef(0),active=useRef<string|null>(null);
 useEffect(()=>onState(operation?.status??'NOT_RUN'),[operation,onState]);
 useEffect(()=>{epoch.current++;if(active.current){adapter.invalidate(active.current);trace.invalidateGovernance('Candidate or route changed');notify();}active.current=null;setOperation(null);setRelease(null);setBusy(false);setError('');setEvidence(adapter.exportEvidence());},[candidate,route,adapter,trace,notify]);
 useEffect(()=>{if(!release){setUrl(null);return;}const value=URL.createObjectURL(new Blob([zipFiles(release.files)],{type:'application/zip'}));setUrl(value);return()=>URL.revokeObjectURL(value);},[release]);
 async function observed(stage:string,work:()=>void|Promise<void>){
  if(stage.includes('SUBMISSION')&&active.current)trace.invalidateGovernance('Replacement submission');
  const before=adapter.exportEvidence().audit.length;
  const token=trace.start(stage,'SIMULATED_IDENTITY',{route,operationId:operation?.id??null,revision:operation?.revision??null,reason,candidate});notify();
  let error:string|undefined;
  try{await work();}catch(e){error=(e as Error).message;}
  finally{trace.finish(token,{events:adapter.exportEvidence().audit.slice(before)},error);notify();}
 }
 async function submit(failure=false){if(!candidate)return;const token=epoch.current;setBusy(true);setError('');try{
  const next=await adapter.submit(sessions[route],failure?createFailureCandidate(candidate):candidate);
  if(token!==epoch.current){adapter.invalidate(next.id);throw new Error('STALE_UI_EXECUTION');}if(active.current)adapter.invalidate(active.current);active.current=next.id;setOperation(next);setRelease(null);
 }catch(e){if(token===epoch.current)setError((e as Error).message);throw e;}finally{setEvidence(adapter.exportEvidence());if(token===epoch.current)setBusy(false);}}
 function decide(decision:'APPROVE'|'REQUEST_CHANGES'|'DECLINE'){if(!operation)return;try{setOperation(adapter.review(sessions.reviewer,operation.id,operation.revision,operation.validation.candidateSha256!,decision,reason));setError('');}catch(e){setError((e as Error).message);throw e;}setEvidence(adapter.exportEvidence());}
 async function resubmit(){if(!operation||!candidate)return;const token=epoch.current;setBusy(true);try{const next=await adapter.resubmit(sessions[route],operation.id,operation.revision,candidate);if(token===epoch.current)setOperation(next);else throw new Error('STALE_UI_EXECUTION');}catch(e){if(token===epoch.current)setError((e as Error).message);throw e;}finally{setEvidence(adapter.exportEvidence());if(token===epoch.current)setBusy(false);}}
 async function pack(){if(!operation)return;const token=epoch.current;setBusy(true);setError('');try{const output=await adapter.package(sessions[route],operation.id,operation.revision);if(token===epoch.current){setRelease(output);setOperation(adapter.inspect(sessions[route],operation.id));}else throw new Error('STALE_UI_EXECUTION');}catch(e){if(token===epoch.current)setError((e as Error).message);throw e;}finally{setEvidence(adapter.exportEvidence());if(token===epoch.current)setBusy(false);}}
 return <section aria-labelledby="governance-heading"><h2 id="governance-heading">06 · Demo governance and package</h2>
 <p>ISOLATED DEMO · Identity and reviewer actions are simulated fixture roles. This is not production authentication, human approval or tenant authorization.</p>
 <label htmlFor="demo-route">Simulated submission route</label><select id="demo-route" value={route} disabled={busy} onChange={e=>setRoute(e.target.value as typeof route)}><option value="requester">Business requester demo</option><option value="trusted">Trusted author demo</option></select>
 <button disabled={!candidate||busy} onClick={()=>void observed('GOVERNANCE_SUBMISSION',()=>submit())}>Submit validated candidate to demo governance</button>
 <button className="secondary" disabled={!candidate||busy} onClick={()=>void observed('FAILED_GOVERNANCE_SUBMISSION',()=>submit(true))}>Test failed-candidate governance rejection</button>
 {operation&&<><p role="status">Demo eligibility: {operation.status} · revision {operation.revision}</p><p className="small">Operation {operation.id}</p>
 {operation.status==='PENDING_REVIEW'&&<><label htmlFor="review-reason">Demo reviewer decision reason</label><textarea id="review-reason" value={reason} maxLength={1000} onChange={e=>setReason(e.target.value)}/><button disabled={busy} onClick={()=>void observed('DEMO_APPROVAL',()=>decide('APPROVE'))}>Simulate independent reviewer approval</button><button disabled={busy} onClick={()=>void observed('DEMO_CHANGES_REQUESTED',()=>decide('REQUEST_CHANGES'))}>Simulate request changes</button><button disabled={busy} onClick={()=>void observed('DEMO_DECLINE',()=>decide('DECLINE'))}>Simulate decline</button></>}
 {['CHANGES_REQUESTED','DECLINED','VALIDATION_FAILED'].includes(operation.status)&&<button disabled={!candidate||busy} onClick={()=>void observed('GOVERNANCE_RESUBMISSION',resubmit)}>Resubmit preserved golden candidate</button>}
 <button disabled={busy||!['APPROVED','TRUSTED_ELIGIBLE'].includes(operation.status)} onClick={()=>void observed('DEMO_PACKAGE',pack)}>Create demo release package</button></>}
 {error&&<p role="alert">{error} · no release generated</p>}{busy&&<p role="status">Checking demo governance · wait for completion</p>}
 {url&&release&&<><a href={url} download="SalesPerformance.demo-release.zip">Save demo release ZIP</a><details><summary>Inspect release manifest</summary><pre>{JSON.stringify(release.manifest,null,2)}</pre></details></>}
 {evidence.audit.length>0&&<a download="SalesPerformance.governance-evidence.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(evidence,null,2))}>Save demo governance evidence</a>}
 </section>;
}

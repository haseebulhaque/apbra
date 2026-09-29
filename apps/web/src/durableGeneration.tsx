import React,{useEffect,useRef,useState} from 'react';
import {ApiError,generationApi,reviewedDesignApi,type DurableContract,type GenerationAttempt,type ReviewedDesign} from './api';

type Mode='BUILD'|'RETRY'|'REGENERATE';
const statusLabel=(status:GenerationAttempt['status'])=>({PENDING:'Waiting to build',RUNNING:'Building',SUCCEEDED:'Report ready',FAILED:'Build failed',CANCELLED:'Cancelled'}[status]);

export function DurableGeneration({caseId,contract,csrfToken,actorRole='MEMBER',onReportReady,onError}:{caseId:string;contract:DurableContract|null;csrfToken:string;actorRole?:string;onReportReady?:(ready:boolean)=>void;onError:(error:unknown)=>void}){
  const [attempts,setAttempts]=useState<GenerationAttempt[]>([]);
  const [designs,setDesigns]=useState<ReviewedDesign[]>([]);
  const [canBuild,setCanBuild]=useState<boolean|null>(null);
  const [canSubmit,setCanSubmit]=useState<boolean|null>(null);
  const [selected,setSelected]=useState('');
  const [expertDraft,setExpertDraft]=useState('');
  const [busy,setBusy]=useState(false);
  const [reviewBusy,setReviewBusy]=useState(false);
  const [cancelling,setCancelling]=useState<string|null>(null);
  const [downloading,setDownloading]=useState<string|null>(null);
  const [downloadError,setDownloadError]=useState('');
  const [unavailableDownloads,setUnavailableDownloads]=useState<Set<string>>(new Set());
  const buildCommand=useRef<{signature:string;key:string}|null>(null);
  const activeKey=useRef('');
  const key=caseId+':'+(contract?.current?contract.id:'not-current');
  activeKey.current=key;

  const refresh=async()=>{
    const [history,available]=await Promise.all([
      generationApi.list(caseId),
      contract?.current?reviewedDesignApi.list(caseId,contract.id):Promise.resolve({items:[] as ReviewedDesign[],can_build:false,can_submit:false}),
    ]);
    if(activeKey.current!==key)return;
    setAttempts(history.items);
    onReportReady?.(Boolean(contract?.current&&history.items.some(item=>item.status==='SUCCEEDED'&&item.confirmed_contract_id===contract.id)));
    setDesigns(available.items);
    setCanBuild(available.can_build);
    setCanSubmit(available.can_submit);
    setSelected(current=>available.items.some(item=>item.id===current)?current:(available.items[0]?.id??''));
  };
  useEffect(()=>{
    setAttempts([]);
    setDesigns([]);
    setCanBuild(null);
    setCanSubmit(null);
    setSelected('');
    setDownloadError('');
    setUnavailableDownloads(new Set());
    buildCommand.current=null;
    void refresh().catch(onError);
  },[caseId,contract?.id,contract?.current]);
  useEffect(()=>{
    if(!busy)return;
    const timer=window.setInterval(()=>void refresh().catch(onError),1000);
    return()=>window.clearInterval(timer);
  },[busy,caseId,contract?.id]);

  async function run(mode:Mode,source?:GenerationAttempt){
    if(!contract?.current||!canBuild)return;
    const designId=mode==='RETRY'?source?.reviewed_design_id:selected;
    if(!designId)return;
    const signature=[contract.id,designId,mode,source?.id??''].join(':');
    if(!buildCommand.current||buildCommand.current.signature!==signature){
      buildCommand.current={signature,key:crypto.randomUUID()};
    }
    setBusy(true);
    try{
      const attempt=await generationApi.start(caseId,contract.id,designId,buildCommand.current.key,csrfToken,mode,source?.id);
      buildCommand.current=null;
      if(activeKey.current!==key)return;
      setAttempts(current=>[attempt,...current.filter(item=>item.id!==attempt.id)]);
      await refresh();
    }catch(error){onError(error)}finally{setBusy(false)}
  }

  async function cancel(attempt:GenerationAttempt){
    if(!canBuild)return;
    setCancelling(attempt.id);
    try{
      const updated=await generationApi.cancel(caseId,attempt.id,csrfToken);
      if(activeKey.current===key)setAttempts(current=>current.map(item=>item.id===updated.id?updated:item));
    }catch(error){onError(error)}finally{setCancelling(null)}
  }

  async function submitExpertReview(){
    if(actorRole!=='EXPERT'||!canSubmit||!contract?.current||!expertDraft.trim())return;
    setReviewBusy(true);
    try{
      const parsed:unknown=JSON.parse(expertDraft);
      if(typeof parsed!=='object'||parsed===null||Array.isArray(parsed))throw new Error('The expert report plan must be a JSON object.');
      await reviewedDesignApi.intake(caseId,contract.id,parsed as Record<string,unknown>,csrfToken);
      if(activeKey.current!==key)return;
      setExpertDraft('');
      await refresh();
    }catch(error){onError(error)}finally{setReviewBusy(false)}
  }

  async function download(attempt:GenerationAttempt){
    if(!attempt.artifact)return;
    setDownloading(attempt.id);
    setDownloadError('');
    try{
      const blob=await generationApi.download(caseId,attempt.id);
      setUnavailableDownloads(current=>{const updated=new Set(current);updated.delete(attempt.id);return updated});
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');
      link.href=url;
      link.download=attempt.artifact.filename;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){
      if(error instanceof ApiError&&[404,410].includes(error.status))
        setUnavailableDownloads(current=>new Set(current).add(attempt.id));
      setDownloadError(error instanceof ApiError?error.message:'The download could not be completed. Check your connection and retry, or ask for help.');
    }finally{setDownloading(null)}
  }

  const latest=attempts[0];
  const latestForContract=contract?.current?attempts.find(item=>item.confirmed_contract_id===contract.id):undefined;
  const current=contract?.current?attempts.find(item=>item.status==='SUCCEEDED'&&item.confirmed_contract_id===contract.id):undefined;
  const currentFileAvailable=Boolean(current?.artifact&&!unavailableDownloads.has(current.id));
  const retryable=latestForContract&&['FAILED','CANCELLED'].includes(latestForContract.status)&&latestForContract.reviewed_design_id&&designs.some(item=>item.id===latestForContract.reviewed_design_id);
  return <section className="generation-panel" aria-labelledby={'generation-'+caseId}>
    <div className="section-title"><div><span className="eyebrow">Build and output</span><h3 id={'generation-'+caseId}>Build and find reports</h3><p>A confirmed request and expert-reviewed plan are required. Candidate files stay private.</p></div><span className="status-badge">{attempts.length} build{attempts.length===1?'':'s'}</span></div>
    {!contract?.current?<div role="status" className="state-callout info"><strong>Confirm your understanding to continue</strong><p>Review and confirm the current meaning before building. Earlier reports remain available below.</p></div>:designs.length===0?<div role="status" className="state-callout warning review-needed"><strong>Expert review needed</strong><p>An authorised expert must supply and review a report plan for this exact confirmed request. You can still read earlier build history.</p></div>:<div className="build-readiness"><div className="readiness-heading"><span className="readiness-mark" aria-hidden="true">✓</span><div><span className="eyebrow">Ready for your next step</span><h4>Reviewed plan available</h4><p>An expert has reviewed a report plan for this confirmed request.</p></div></div><label htmlFor={'reviewed-plan-'+caseId}>Reviewed report plan</label><select id={'reviewed-plan-'+caseId} value={selected} onChange={event=>setSelected(event.target.value)}>{designs.map((item,index)=><option key={item.id} value={item.id}>Plan {designs.length-index} · {item.summary.page_count} page{item.summary.page_count===1?'':'s'} · {item.summary.visual_count} visual{item.summary.visual_count===1?'':'s'} · reviewed {new Date(item.reviewed_at).toLocaleDateString()}</option>)}</select><div className="plan-facts"><span><strong>{designs.find(item=>item.id===selected)?.summary.page_count??0}</strong> pages</span><span><strong>{designs.find(item=>item.id===selected)?.summary.visual_count??0}</strong> visuals</span><span>Reviewed {designs.find(item=>item.id===selected)?.reviewed_at?new Date(designs.find(item=>item.id===selected)!.reviewed_at).toLocaleDateString():'—'}</span></div><p className="supporting-copy">{designs.find(item=>item.id===selected)?.summary.description} APBRA checks eligibility again when you build.</p>{canBuild&&<div className="command-bar"><button disabled={busy||!selected} onClick={()=>void run(current?'REGENERATE':'BUILD')}>{busy?'Building report…':current?'Build another version':'Build report'} <span aria-hidden="true">→</span></button>{retryable&&<button className="subtle" disabled={busy} onClick={()=>void run('RETRY',latestForContract)}>Retry failed build</button>}</div>}</div>}
    {contract?.current&&canBuild===false&&<p role="status">You can inspect this private case, but building or cancelling a report requires editor access. Ask the case owner if you need to build.</p>}
    {latestForContract&&['PENDING','RUNNING'].includes(latestForContract.status)&&<div role="status" aria-live="polite" className="state-callout info building-state"><span className="processing-spinner" aria-hidden="true"/><div><strong>{statusLabel(latestForContract.status)}</strong><p>{canBuild?'You may cancel this attempt; it will remain in history.':'An editor can cancel this attempt; it will remain in history.'}</p></div>{canBuild&&<button className="subtle" disabled={cancelling===latestForContract.id} onClick={()=>void cancel(latestForContract)}>{cancelling===latestForContract.id?'Cancelling…':'Cancel build'}</button>}</div>}
    {latestForContract&&['FAILED','CANCELLED'].includes(latestForContract.status)&&!retryable&&<p role="status">This earlier plan is no longer eligible for retry. Ask an authorised expert to review a current plan.</p>}
    {current?<div className="current-report" aria-label="Current report"><div className="report-cover" aria-hidden="true"><span>APBRA</span><span>▥</span><small>REPORT CANDIDATE</small></div><div className="report-content"><div className="report-kicker"><span className="status-badge status-success">Current report</span><span>Version {current.attempt_number}</span></div><h4>Your report candidate is ready</h4><p>{currentFileAvailable?'Validated candidate recorded for inspection. File access is checked again when you download.':'This completed build has no available file. Its history remains saved; reload or ask for help.'}</p><div className="report-facts"><span>Built {new Date(current.completed_at??current.created_at).toLocaleString()}</span><span>Private candidate · not published or deployed</span></div>{current.artifact&&<button disabled={downloading===current.id} onClick={()=>void download(current)}>{downloading===current.id?'Preparing download…':unavailableDownloads.has(current.id)?'Try current report download again':'Download current report candidate'} <span aria-hidden="true">↓</span></button>}</div></div>:<div role="status" className="report-empty"><span aria-hidden="true">▤</span><div><strong>No current report yet</strong><p>Once a build completes, the private candidate will appear here. Earlier candidates remain in history.</p></div></div>}
    {downloadError&&<p role="alert" className="review-needed">{downloadError}</p>}
    <details className="report-history"><summary>Earlier builds and history <span className="status-badge">{attempts.length}</span></summary>{attempts.length===0?<p className="quiet-empty">No report builds yet.</p>:<ol className="generation-history">{attempts.map(attempt=><li key={attempt.id} className={attempt.id===current?.id?'history-current':''}><span className="history-marker" aria-hidden="true"/><div className="history-main"><div className="history-heading"><strong>Version {attempt.attempt_number}</strong><span className={'status-badge '+(attempt.status==='SUCCEEDED'?'status-success':attempt.status==='FAILED'?'status-danger':attempt.status==='CANCELLED'?'status-warning':'status-info')}>{attempt.status==='SUCCEEDED'&&(!attempt.artifact||unavailableDownloads.has(attempt.id))?'Completed, file unavailable':statusLabel(attempt.status)}</span>{attempt.id===current?.id&&<span className="history-current-label">Current</span>}</div><time>{new Date(attempt.created_at).toLocaleString()}</time>{attempt.failure&&<p role="alert" className="state-callout danger">{attempt.failure.message}</p>}{attempt.status==='SUCCEEDED'&&(!attempt.artifact||unavailableDownloads.has(attempt.id))&&<p role="status">This earlier file is unavailable. The build record remains saved.</p>}{attempt.artifact&&attempt.id!==current?.id&&<button className="subtle" disabled={downloading===attempt.id} onClick={()=>void download(attempt)}>{downloading===attempt.id?'Preparing download…':unavailableDownloads.has(attempt.id)?'Try earlier report download again':'Download earlier report candidate'}</button>}</div></li>)}</ol>}</details>
    <details className="expert-details"><summary>Details for experts</summary><p>This local validation does not call an AI design model. The supplied plan passes through the existing canonical validation and generation pipeline at build time. Power BI Desktop, DAX, RLS, publication and deployment validation are not run.</p>{actorRole==='EXPERT'&&contract?.current&&(canSubmit?<div className="expert-intake"><h4>Submit a reviewed report plan</h4><p>Only an active expert with edit access to this private case may submit a complete design. Successful server intake records the expert review; it does not claim the design will pass build validation.</p><label htmlFor={'expert-plan-'+caseId}>Expert report plan JSON</label><textarea id={'expert-plan-'+caseId} value={expertDraft} onChange={event=>setExpertDraft(event.target.value)} rows={8}/><button disabled={reviewBusy||!expertDraft.trim()} onClick={()=>void submitExpertReview()}>{reviewBusy?'Recording expert review…':'Submit reviewed plan'}</button></div>:canSubmit===false?<p>Report-plan submission requires expert edit access to this private case. Ask the case owner for access if you need to submit a plan.</p>:<p role="status">Checking expert case access…</p>)}{attempts.length>0&&<p>Latest attempt reference: {latest?.id}. Historical candidate digests are available from protected downloads.</p>}</details>
  </section>;
}
